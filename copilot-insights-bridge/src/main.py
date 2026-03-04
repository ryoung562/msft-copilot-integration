"""Pipeline orchestration for the Copilot Studio to Arize AX bridge."""

import logging
import math
import time
from datetime import datetime, timedelta, timezone

from azure.core.exceptions import AzureError

from src.config import BridgeSettings
from src.extraction.client import AppInsightsClient
from src.reconstruction.tree_builder import TraceTreeBuilder
from src.transformation.mapper import OpenInferenceMapper
from src.export.otel_exporter import create_tracer_provider, shutdown_tracer_provider
from src.export.span_builder import SpanBuilder
from src.state.cursor import Cursor

logger = logging.getLogger(__name__)

# Safety buffer to account for App Insights ingestion lag.
_INGESTION_LAG = timedelta(minutes=2)


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

    def run_once(self) -> int:
        """Execute a single poll cycle. Returns the number of events processed."""
        state = self._cursor.load()
        now = datetime.now(timezone.utc)

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

        if not events:
            logger.info("No new events in window %s -> %s", start_time, end_time)
            return 0

        logger.info("Fetched %d events, building trace trees", len(events))
        trees = self._tree_builder.build_trees(events)

        exported = 0
        for root in trees:
            try:
                self._span_builder.export_trace_tree(
                    root, attributes_map=self._mapper.map_attributes
                )
                exported += 1
            except Exception:
                logger.exception("Failed to export tree rooted at %s", root)

        # force_flush: swallow errors — spans are queued in BatchSpanProcessor
        # which has its own retry. Don't block cursor advancement.
        try:
            flushed = self._provider.force_flush()
            if not flushed:
                logger.warning("force_flush() timed out; spans may be delayed")
        except Exception:
            logger.warning("force_flush() failed; spans may be delayed", exc_info=True)

        # cursor.save: swallow OSError — worst case is duplicate processing next cycle
        state.last_processed_timestamp = end_time
        state.last_run_at = now
        state.events_processed_count += len(events)
        try:
            self._cursor.save(state)
        except OSError:
            logger.warning("Failed to save cursor; duplicates possible next cycle", exc_info=True)

        logger.info(
            "Cycle complete: %d events, %d trees exported", len(events), exported
        )
        return len(events)

    def _backoff_seconds(self, consecutive_failures: int) -> float:
        """Compute exponential backoff sleep duration."""
        raw = self._settings.backoff_base_seconds * math.pow(
            2, consecutive_failures - 1
        )
        return min(raw, self._settings.backoff_max_seconds)

    def run_loop(self) -> None:
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
                    time.sleep(interval)
                except KeyboardInterrupt:
                    raise
                except Exception:
                    consecutive_failures += 1
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    settings = BridgeSettings()  # type: ignore[call-arg]
    pipeline = BridgePipeline(settings)
    pipeline.run_loop()


if __name__ == "__main__":
    main()
