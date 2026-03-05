"""Pipeline orchestration for the Copilot Studio to Arize AX bridge."""

import logging
import math
import time
from datetime import datetime, timedelta, timezone

from azure.core.exceptions import AzureError

from src.config import BridgeSettings
from src.extraction.client import AppInsightsClient
from src.extraction.models import AppInsightsEvent
from src.health import HealthState, start_health_server
from src.logging_config import configure_logging
from src.reconstruction.tree_builder import TraceTreeBuilder
from src.transformation.mapper import OpenInferenceMapper
from src.export.otel_exporter import create_tracer_provider, shutdown_tracer_provider
from src.export.span_builder import SpanBuilder
from src.state.cursor import Cursor

logger = logging.getLogger(__name__)

# Safety buffer to account for App Insights ingestion lag.
_INGESTION_LAG = timedelta(minutes=2)


def _event_dedup_key(event: AppInsightsEvent) -> tuple[str, str, str]:
    """Return a deduplication key for an event."""
    return (event.timestamp.isoformat(), event.name, event.conversation_id)


class BridgePipeline:
    """Wires together extraction, reconstruction, transformation, and export."""

    def __init__(self, settings: BridgeSettings) -> None:
        self._settings = settings
        self._client = AppInsightsClient(resource_id=settings.appinsights_resource_id)
        self._tree_builder = TraceTreeBuilder()
        self._mapper = OpenInferenceMapper()
        self._provider = create_tracer_provider(
            space_id=settings.arize_space_id,
            api_key=settings.arize_api_key,
            project_name=settings.arize_project_name,
        )
        self._span_builder = SpanBuilder(self._provider.get_tracer("copilot-bridge"))
        self._cursor = Cursor(cursor_path=settings.cursor_path)

        # Event buffer: accumulate events per conversation_id until grace period elapses
        self._event_buffer: dict[str, list[AppInsightsEvent]] = {}
        self._buffer_first_seen: dict[str, datetime] = {}
        self._seen_event_keys: set[tuple[str, str, str]] = set()

    def run_once(self) -> int:
        """Execute a single poll cycle. Returns the number of events exported."""
        state = self._cursor.load()
        now = datetime.now(timezone.utc)
        grace = self._settings.buffer_grace_seconds

        start_time = state.last_processed_timestamp or (
            now - timedelta(hours=self._settings.initial_lookback_hours)
        )
        end_time = now - _INGESTION_LAG

        if start_time >= end_time:
            logger.debug("Time window is empty, skipping cycle")
            return 0

        # query_events: let Azure errors propagate so run_loop() can track failures
        events = self._client.query_events(
            start_time=start_time,
            end_time=end_time,
            exclude_design_mode=self._settings.exclude_design_mode,
        )

        # Dedup against already-buffered events (overlapping query window)
        new_events: list[AppInsightsEvent] = []
        for event in events:
            key = _event_dedup_key(event)
            if key not in self._seen_event_keys:
                self._seen_event_keys.add(key)
                new_events.append(event)

        # Buffer new events by conversation_id
        for event in new_events:
            conv_id = event.conversation_id
            if conv_id not in self._event_buffer:
                self._event_buffer[conv_id] = []
                self._buffer_first_seen[conv_id] = now
            self._event_buffer[conv_id].append(event)

        if not self._event_buffer:
            if not events:
                logger.info("No new events in window %s -> %s", start_time, end_time)
            return 0

        # Determine mature conversations
        if grace == 0:
            mature_conv_ids = set(self._event_buffer.keys())
        else:
            mature_conv_ids = {
                conv_id
                for conv_id, first_seen in self._buffer_first_seen.items()
                if (now - first_seen).total_seconds() >= grace
            }

        if not mature_conv_ids:
            logger.info(
                "All %d buffered conversations still within grace period",
                len(self._event_buffer),
            )
            return 0

        # Collect events from mature conversations
        mature_events: list[AppInsightsEvent] = []
        for conv_id in mature_conv_ids:
            mature_events.extend(self._event_buffer.pop(conv_id))
            self._buffer_first_seen.pop(conv_id, None)
            # Clean up seen keys for exported conversations so memory doesn't grow unbounded
            self._seen_event_keys -= {
                _event_dedup_key(e) for e in mature_events if e.conversation_id == conv_id
            }

        logger.info(
            "Exporting %d events from %d mature conversations (%d conversations still buffered)",
            len(mature_events),
            len(mature_conv_ids),
            len(self._event_buffer),
        )
        trees = self._tree_builder.build_trees(mature_events)

        exported = 0
        for root in trees:
            try:
                self._span_builder.export_trace_tree(
                    root, attributes_map=self._mapper.map_attributes
                )
                exported += 1
            except Exception:
                logger.exception("Failed to export tree rooted at %s", root)

        # force_flush: swallow errors -- spans are queued in BatchSpanProcessor
        # which has its own retry. Don't block cursor advancement.
        try:
            flushed = self._provider.force_flush()
            if not flushed:
                logger.warning("force_flush() timed out; spans may be delayed")
        except Exception:
            logger.warning("force_flush() failed; spans may be delayed", exc_info=True)

        # Advance cursor: don't move past events still in the buffer
        if self._event_buffer:
            oldest_buffered = min(
                e.timestamp
                for events_list in self._event_buffer.values()
                for e in events_list
            )
            state.last_processed_timestamp = oldest_buffered - timedelta(microseconds=1)
        else:
            state.last_processed_timestamp = end_time

        state.last_run_at = now
        state.events_processed_count += len(mature_events)
        try:
            self._cursor.save(state)
        except OSError:
            logger.warning("Failed to save cursor; duplicates possible next cycle", exc_info=True)

        logger.info(
            "Cycle complete: %d events, %d trees exported", len(mature_events), exported
        )
        return len(mature_events)

    def _flush_buffer(self) -> int:
        """Export ALL buffered events regardless of grace period.

        Called during shutdown to avoid losing buffered data.
        Returns the number of events flushed.
        """
        if not self._event_buffer:
            return 0

        all_events: list[AppInsightsEvent] = []
        for events_list in self._event_buffer.values():
            all_events.extend(events_list)

        self._event_buffer.clear()
        self._buffer_first_seen.clear()
        self._seen_event_keys.clear()

        if not all_events:
            return 0

        logger.info("Flushing %d buffered events on shutdown", len(all_events))
        trees = self._tree_builder.build_trees(all_events)

        exported = 0
        for root in trees:
            try:
                self._span_builder.export_trace_tree(
                    root, attributes_map=self._mapper.map_attributes
                )
                exported += 1
            except Exception:
                logger.exception("Failed to export tree rooted at %s", root)

        return len(all_events)

    def _backoff_seconds(self, consecutive_failures: int) -> float:
        """Compute exponential backoff sleep duration."""
        raw = self._settings.backoff_base_seconds * math.pow(
            2, consecutive_failures - 1
        )
        return min(raw, self._settings.backoff_max_seconds)

    def run_loop(self, health_state: HealthState | None = None) -> None:
        """Continuously poll until interrupted, with exponential backoff on failures."""
        interval = self._settings.poll_interval_minutes * 60
        consecutive_failures = 0
        logger.info(
            "Starting bridge loop (poll every %d min)", self._settings.poll_interval_minutes
        )
        try:
            while True:
                try:
                    self.run_once()
                    consecutive_failures = 0
                    if health_state is not None:
                        health_state.record_success(self._cursor.load())
                    time.sleep(interval)
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    consecutive_failures += 1
                    if health_state is not None:
                        health_state.record_failure(exc)
                    backoff = self._backoff_seconds(consecutive_failures)
                    if consecutive_failures >= self._settings.max_consecutive_failures:
                        logger.error(
                            "ALERT: %d consecutive failures (backoff %.0fs)",
                            consecutive_failures,
                            backoff,
                            exc_info=True,
                        )
                    else:
                        logger.warning(
                            "Cycle failed (%d consecutive, backoff %.0fs)",
                            consecutive_failures,
                            backoff,
                            exc_info=True,
                        )
                    time.sleep(backoff)
        except KeyboardInterrupt:
            logger.info("Shutting down bridge")
        finally:
            self._flush_buffer()
            try:
                self._provider.force_flush()
            except Exception:
                logger.warning("Shutdown force_flush() failed", exc_info=True)
            try:
                shutdown_tracer_provider(self._provider)
            except Exception:
                logger.warning("Shutdown tracer provider failed", exc_info=True)


def main() -> None:
    """Entry point: load settings and start the polling loop."""
    settings = BridgeSettings()  # type: ignore[call-arg]
    configure_logging(fmt=settings.log_format)

    health_state = HealthState(
        poll_interval_seconds=settings.poll_interval_minutes * 60,
        max_consecutive_failures=settings.max_consecutive_failures,
    )
    if settings.health_check_enabled:
        start_health_server(health_state, port=settings.health_check_port)

    pipeline = BridgePipeline(settings)
    pipeline.run_loop(health_state=health_state)


if __name__ == "__main__":
    main()
