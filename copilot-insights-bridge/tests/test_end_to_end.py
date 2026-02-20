"""End-to-end test: fixture data → pipeline → exported spans."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.config import BridgeSettings
from src.extraction.models import AppInsightsEvent
from src.main import BridgePipeline
from src.state.cursor import CursorState


def _load_fixture_events(name: str) -> list[AppInsightsEvent]:
    """Load fixture JSON and parse into events."""
    import json

    fixture_path = Path(__file__).parent / "fixtures" / name
    rows = json.loads(fixture_path.read_text())
    return [AppInsightsEvent.from_query_row(row) for row in rows]


@pytest.fixture
def settings(tmp_path: Path) -> BridgeSettings:
    return BridgeSettings(
        appinsights_resource_id="/subscriptions/test/resourceGroups/test/providers/microsoft.insights/components/test",
        arize_space_id="test-space",
        arize_api_key="test-key",
        arize_project_name="test-project",
        poll_interval_minutes=1,
        initial_lookback_hours=1,
    )


class TestEndToEnd:
    def test_single_conversation_pipeline(self, settings: BridgeSettings, tmp_path: Path) -> None:
        events = _load_fixture_events("single_conversation.json")
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        with (
            patch("src.main.AppInsightsClient") as MockClient,
            patch("src.main.create_tracer_provider", return_value=provider),
            patch("src.main.Cursor") as MockCursor,
        ):
            mock_client_instance = MockClient.return_value
            mock_client_instance.query_events.return_value = events

            mock_cursor_instance = MockCursor.return_value
            mock_cursor_instance.load.return_value = CursorState()
            mock_cursor_instance.save = MagicMock()

            pipeline = BridgePipeline(settings)
            # Override the provider and span_builder to use our in-memory exporter
            pipeline._provider = provider
            from src.export.span_builder import SpanBuilder

            pipeline._span_builder = SpanBuilder(provider.get_tracer("test"))

            result = pipeline.run_once()

        provider.force_flush()
        spans = exporter.get_finished_spans()

        # Should have processed 5 events
        assert result == 5

        # Expected spans: root AGENT + 1 CHAIN (PasswordReset) + 1 LLM (GenerativeAnswers)
        # + messages attached to chain (not separate spans)
        assert len(spans) == 3

        span_names = {s.name for s in spans}
        assert "Copilot Studio Conversation" in span_names
        assert "PasswordReset" in span_names
        assert "GenerativeAnswers" in span_names

        # All spans share the same trace ID
        trace_ids = {s.context.trace_id for s in spans}
        assert len(trace_ids) == 1

    def test_multi_topic_pipeline(self, settings: BridgeSettings, tmp_path: Path) -> None:
        events = _load_fixture_events("multi_topic_conversation.json")
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        with (
            patch("src.main.AppInsightsClient") as MockClient,
            patch("src.main.create_tracer_provider", return_value=provider),
            patch("src.main.Cursor") as MockCursor,
        ):
            mock_client_instance = MockClient.return_value
            mock_client_instance.query_events.return_value = events

            mock_cursor_instance = MockCursor.return_value
            mock_cursor_instance.load.return_value = CursorState()
            mock_cursor_instance.save = MagicMock()

            pipeline = BridgePipeline(settings)
            pipeline._provider = provider
            from src.export.span_builder import SpanBuilder

            pipeline._span_builder = SpanBuilder(provider.get_tracer("test"))

            result = pipeline.run_once()

        provider.force_flush()
        spans = exporter.get_finished_spans()

        assert result == 10

        # 2 turns: each has root AGENT + 1 CHAIN + 1 TOOL = 3 spans × 2 = 6
        assert len(spans) == 6
        span_names = {s.name for s in spans}
        assert "Copilot Studio Conversation" in span_names
        assert "CalendarLookup" in span_names
        assert "RoomBooking" in span_names
        assert "GetCalendarEvents" in span_names
        assert "BookMeetingRoom" in span_names

        # Each turn is a separate trace
        trace_ids = {s.context.trace_id for s in spans}
        assert len(trace_ids) == 2

    def test_error_conversation_pipeline(self, settings: BridgeSettings, tmp_path: Path) -> None:
        events = _load_fixture_events("error_conversation.json")
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        with (
            patch("src.main.AppInsightsClient") as MockClient,
            patch("src.main.create_tracer_provider", return_value=provider),
            patch("src.main.Cursor") as MockCursor,
        ):
            mock_client_instance = MockClient.return_value
            mock_client_instance.query_events.return_value = events

            mock_cursor_instance = MockCursor.return_value
            mock_cursor_instance.load.return_value = CursorState()
            mock_cursor_instance.save = MagicMock()

            pipeline = BridgePipeline(settings)
            pipeline._provider = provider
            from src.export.span_builder import SpanBuilder

            pipeline._span_builder = SpanBuilder(provider.get_tracer("test"))

            result = pipeline.run_once()

        provider.force_flush()
        spans = exporter.get_finished_spans()

        # Find the tool span and check it has an error
        tool_spans = [s for s in spans if s.name == "TransferToAgent"]
        assert len(tool_spans) == 1
        tool_span = tool_spans[0]
        assert len(tool_span.events) == 1
        assert tool_span.events[0].attributes["exception.message"] == "AgentTransferFailed"

    def test_empty_query_returns_zero(self, settings: BridgeSettings, tmp_path: Path) -> None:
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        with (
            patch("src.main.AppInsightsClient") as MockClient,
            patch("src.main.create_tracer_provider", return_value=provider),
            patch("src.main.Cursor") as MockCursor,
        ):
            mock_client_instance = MockClient.return_value
            mock_client_instance.query_events.return_value = []

            mock_cursor_instance = MockCursor.return_value
            mock_cursor_instance.load.return_value = CursorState()

            pipeline = BridgePipeline(settings)
            pipeline._provider = provider

            result = pipeline.run_once()

        assert result == 0
        assert len(exporter.get_finished_spans()) == 0

    def test_real_data_pipeline(self, settings: BridgeSettings, tmp_path: Path) -> None:
        """Full pipeline test using real App Insights data (production events only)."""
        from tests.conftest import load_real_data_table

        rows = load_real_data_table()
        all_events = [AppInsightsEvent.from_query_row(r) for r in rows]
        # Filter to production events only (matching what the query would do)
        prod_events = [e for e in all_events if e.design_mode != "True"]

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        with (
            patch("src.main.AppInsightsClient") as MockClient,
            patch("src.main.create_tracer_provider", return_value=provider),
            patch("src.main.Cursor") as MockCursor,
        ):
            mock_client_instance = MockClient.return_value
            mock_client_instance.query_events.return_value = prod_events

            mock_cursor_instance = MockCursor.return_value
            mock_cursor_instance.load.return_value = CursorState()
            mock_cursor_instance.save = MagicMock()

            pipeline = BridgePipeline(settings)
            pipeline._provider = provider
            from src.export.span_builder import SpanBuilder

            pipeline._span_builder = SpanBuilder(provider.get_tracer("test"))

            result = pipeline.run_once()

        provider.force_flush()
        spans = exporter.get_finished_spans()

        # Should have processed all production events
        assert result == len(prod_events)
        assert result > 0

        # Turn-based model: multiple root AGENT spans (one per user message turn)
        assert len(spans) > 0
        root_spans = [s for s in spans if s.name == "Copilot Studio Conversation"]
        assert len(root_spans) >= 2  # Multiple turns produce multiple root spans

        # Each turn is a separate trace
        trace_ids = {s.context.trace_id for s in spans}
        assert len(trace_ids) >= 2

        # Should have at least some child spans (CHAINs, TOOLs, LLMs)
        non_root = [s for s in spans if s.name != "Copilot Studio Conversation"]
        assert len(non_root) > 0
