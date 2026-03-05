"""Tests for the event buffer with grace period in BridgePipeline."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.config import BridgeSettings
from src.extraction.models import AppInsightsEvent
from src.main import BridgePipeline
from src.state.cursor import CursorState


def _make_settings(**overrides) -> BridgeSettings:
    defaults = dict(
        appinsights_resource_id="/subscriptions/test/resourceGroups/test/providers/microsoft.insights/components/test",
        arize_space_id="test-space",
        arize_api_key="test-key",
        arize_project_name="test-project",
        poll_interval_minutes=1,
        initial_lookback_hours=1,
        buffer_grace_seconds=0,
    )
    defaults.update(overrides)
    return BridgeSettings(**defaults)


def _make_pipeline(settings: BridgeSettings) -> BridgePipeline:
    """Create a BridgePipeline with mocked external dependencies."""
    with (
        patch("src.main.AppInsightsClient") as MockClient,
        patch("src.main.create_tracer_provider") as MockProvider,
        patch("src.main.Cursor") as MockCursor,
    ):
        mock_provider = MagicMock()
        mock_provider.get_tracer.return_value = MagicMock()
        mock_provider.force_flush.return_value = True
        MockProvider.return_value = mock_provider

        mock_cursor = MagicMock()
        mock_cursor.load.return_value = CursorState()
        MockCursor.return_value = mock_cursor

        pipeline = BridgePipeline(settings)
    return pipeline


def _make_event(
    name: str = "BotMessageReceived",
    conversation_id: str = "conv-1",
    timestamp: datetime | None = None,
    text: str | None = "hello",
) -> AppInsightsEvent:
    if timestamp is None:
        timestamp = datetime(2026, 3, 4, 12, 0, 0, tzinfo=timezone.utc)
    return AppInsightsEvent(
        timestamp=timestamp,
        name=name,
        conversation_id=conversation_id,
        text=text,
    )


class TestGraceZeroBackwardCompat:
    """When buffer_grace_seconds=0, behavior is identical to pre-buffer."""

    def test_events_exported_immediately(self) -> None:
        """With grace=0, all events are exported in the same cycle."""
        settings = _make_settings(buffer_grace_seconds=0)
        pipeline = _make_pipeline(settings)

        e1 = _make_event(name="BotMessageReceived", conversation_id="conv-1")
        e2 = _make_event(name="BotMessageSend", conversation_id="conv-1")
        pipeline._client.query_events.return_value = [e1, e2]
        pipeline._tree_builder.build_trees = MagicMock(return_value=[MagicMock()])

        result = pipeline.run_once()

        assert result == 2
        pipeline._tree_builder.build_trees.assert_called_once()
        # Buffer should be empty after export
        assert len(pipeline._event_buffer) == 0

    def test_no_events_returns_zero(self) -> None:
        """Empty query returns 0."""
        settings = _make_settings(buffer_grace_seconds=0)
        pipeline = _make_pipeline(settings)
        pipeline._client.query_events.return_value = []

        result = pipeline.run_once()

        assert result == 0

    def test_cursor_advances_to_end_time(self) -> None:
        """With grace=0 and no remaining buffer, cursor advances to end_time."""
        settings = _make_settings(buffer_grace_seconds=0)
        pipeline = _make_pipeline(settings)

        e1 = _make_event()
        pipeline._client.query_events.return_value = [e1]
        pipeline._tree_builder.build_trees = MagicMock(return_value=[])

        pipeline.run_once()

        save_call = pipeline._cursor.save.call_args[0][0]
        # Cursor should be set to end_time (now - 2min ingestion lag)
        assert save_call.last_processed_timestamp is not None
        assert save_call.events_processed_count == 1


class TestGracePeriodBuffering:
    """When buffer_grace_seconds > 0, events are held until grace elapses."""

    def test_events_buffered_not_exported_within_grace(self) -> None:
        """Events arriving within grace period are not exported."""
        settings = _make_settings(buffer_grace_seconds=120)
        pipeline = _make_pipeline(settings)

        e1 = _make_event(name="BotMessageReceived", conversation_id="conv-1")
        pipeline._client.query_events.return_value = [e1]

        result = pipeline.run_once()

        assert result == 0
        assert "conv-1" in pipeline._event_buffer
        assert len(pipeline._event_buffer["conv-1"]) == 1

    def test_events_exported_after_grace_elapses(self) -> None:
        """Events are exported once the grace period has elapsed."""
        settings = _make_settings(buffer_grace_seconds=60)
        pipeline = _make_pipeline(settings)

        e1 = _make_event(name="BotMessageReceived", conversation_id="conv-1")
        pipeline._client.query_events.return_value = [e1]
        pipeline._tree_builder.build_trees = MagicMock(return_value=[MagicMock()])

        # First cycle: events buffered
        pipeline.run_once()
        assert len(pipeline._event_buffer) == 1

        # Simulate time passing: set first_seen to 120 seconds ago
        pipeline._buffer_first_seen["conv-1"] = datetime.now(
            timezone.utc
        ) - timedelta(seconds=120)

        # Second cycle: no new events, but existing are now mature
        pipeline._client.query_events.return_value = []
        result = pipeline.run_once()

        assert result == 1
        assert len(pipeline._event_buffer) == 0
        pipeline._tree_builder.build_trees.assert_called_once()

    def test_cross_cycle_merge(self) -> None:
        """Events from the same conversation across two cycles merge into one tree."""
        settings = _make_settings(buffer_grace_seconds=60)
        pipeline = _make_pipeline(settings)
        pipeline._tree_builder.build_trees = MagicMock(return_value=[MagicMock()])

        t1 = datetime(2026, 3, 4, 12, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 4, 12, 0, 3, tzinfo=timezone.utc)

        # Cycle 1: BotMessageReceived arrives
        e1 = _make_event(
            name="BotMessageReceived", conversation_id="conv-1", timestamp=t1
        )
        pipeline._client.query_events.return_value = [e1]
        pipeline.run_once()
        assert len(pipeline._event_buffer["conv-1"]) == 1

        # Cycle 2: BotMessageSend arrives (late) for same conversation
        e2 = _make_event(
            name="BotMessageSend", conversation_id="conv-1", timestamp=t2
        )
        pipeline._client.query_events.return_value = [e2]
        pipeline.run_once()
        assert len(pipeline._event_buffer["conv-1"]) == 2

        # Mature the conversation
        pipeline._buffer_first_seen["conv-1"] = datetime.now(
            timezone.utc
        ) - timedelta(seconds=120)
        pipeline._client.query_events.return_value = []
        result = pipeline.run_once()

        assert result == 2
        # build_trees was called with both events merged
        call_events = pipeline._tree_builder.build_trees.call_args[0][0]
        assert len(call_events) == 2
        assert {e.name for e in call_events} == {"BotMessageReceived", "BotMessageSend"}


class TestDedup:
    """Events re-queried due to overlapping cursor window are not duplicated."""

    def test_duplicate_events_not_added_twice(self) -> None:
        """Same event appearing in two consecutive queries is only buffered once."""
        settings = _make_settings(buffer_grace_seconds=60)
        pipeline = _make_pipeline(settings)

        t1 = datetime(2026, 3, 4, 12, 0, 0, tzinfo=timezone.utc)
        e1 = _make_event(
            name="BotMessageReceived", conversation_id="conv-1", timestamp=t1
        )

        # Cycle 1
        pipeline._client.query_events.return_value = [e1]
        pipeline.run_once()
        assert len(pipeline._event_buffer["conv-1"]) == 1

        # Cycle 2: same event returned again (overlapping query window)
        pipeline._client.query_events.return_value = [e1]
        pipeline.run_once()
        assert len(pipeline._event_buffer["conv-1"]) == 1  # still 1, not 2


class TestCursorSafety:
    """Cursor must not advance past buffered (unexported) events."""

    def test_cursor_held_back_with_buffered_events(self) -> None:
        """When some conversations are still buffered, cursor stays before them."""
        settings = _make_settings(buffer_grace_seconds=60)
        pipeline = _make_pipeline(settings)
        pipeline._tree_builder.build_trees = MagicMock(return_value=[MagicMock()])

        t1 = datetime(2026, 3, 4, 12, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 4, 12, 0, 5, tzinfo=timezone.utc)

        e1 = _make_event(
            name="BotMessageReceived", conversation_id="conv-mature", timestamp=t1
        )
        e2 = _make_event(
            name="BotMessageReceived", conversation_id="conv-pending", timestamp=t2
        )
        pipeline._client.query_events.return_value = [e1, e2]

        # First cycle: both buffered
        pipeline.run_once()

        # Mature conv-mature only
        pipeline._buffer_first_seen["conv-mature"] = datetime.now(
            timezone.utc
        ) - timedelta(seconds=120)

        # Second cycle: conv-mature exported, conv-pending still buffered
        pipeline._client.query_events.return_value = []
        pipeline.run_once()

        save_call = pipeline._cursor.save.call_args[0][0]
        # Cursor should be just before the oldest buffered event (t2 - 1us)
        expected = t2 - timedelta(microseconds=1)
        assert save_call.last_processed_timestamp == expected

    def test_cursor_advances_fully_when_buffer_empty(self) -> None:
        """When buffer is empty after export, cursor advances to end_time."""
        settings = _make_settings(buffer_grace_seconds=60)
        pipeline = _make_pipeline(settings)
        pipeline._tree_builder.build_trees = MagicMock(return_value=[])

        e1 = _make_event(name="BotMessageReceived", conversation_id="conv-1")
        pipeline._client.query_events.return_value = [e1]

        # Buffer it
        pipeline.run_once()

        # Mature it
        pipeline._buffer_first_seen["conv-1"] = datetime.now(
            timezone.utc
        ) - timedelta(seconds=120)
        pipeline._client.query_events.return_value = []

        pipeline.run_once()

        save_call = pipeline._cursor.save.call_args[0][0]
        # With empty buffer, cursor should be at end_time (not held back)
        assert save_call.last_processed_timestamp is not None
        assert len(pipeline._event_buffer) == 0


class TestFlushBuffer:
    """_flush_buffer() exports everything regardless of grace period."""

    def test_flush_exports_all_buffered(self) -> None:
        """Flushing exports all buffered events even if grace hasn't elapsed."""
        settings = _make_settings(buffer_grace_seconds=300)
        pipeline = _make_pipeline(settings)
        pipeline._tree_builder.build_trees = MagicMock(return_value=[MagicMock()])

        e1 = _make_event(name="BotMessageReceived", conversation_id="conv-1")
        e2 = _make_event(name="BotMessageSend", conversation_id="conv-2")
        pipeline._client.query_events.return_value = [e1, e2]

        # Buffer events (not yet mature)
        pipeline.run_once()
        assert len(pipeline._event_buffer) == 2

        # Flush
        flushed = pipeline._flush_buffer()

        assert flushed == 2
        assert len(pipeline._event_buffer) == 0
        assert len(pipeline._buffer_first_seen) == 0
        assert len(pipeline._seen_event_keys) == 0
        pipeline._tree_builder.build_trees.assert_called_once()

    def test_flush_empty_buffer_returns_zero(self) -> None:
        """Flushing an empty buffer is a no-op."""
        settings = _make_settings(buffer_grace_seconds=60)
        pipeline = _make_pipeline(settings)

        result = pipeline._flush_buffer()

        assert result == 0

    def test_run_loop_flushes_on_shutdown(self) -> None:
        """run_loop() calls _flush_buffer() in its finally block."""
        settings = _make_settings(buffer_grace_seconds=60)
        pipeline = _make_pipeline(settings)
        pipeline.run_once = MagicMock(side_effect=KeyboardInterrupt)
        pipeline._flush_buffer = MagicMock(return_value=0)

        pipeline.run_loop()

        pipeline._flush_buffer.assert_called_once()
