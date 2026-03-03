"""Tests for the OTel export layer (span builder)."""

from datetime import datetime, timezone

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.export.span_builder import SpanBuilder
from src.reconstruction.span_models import SpanKind, SpanNode


def _make_provider_and_exporter() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def _make_tree() -> SpanNode:
    """Build a simple two-level tree for testing."""
    child_llm = SpanNode(
        name="GenerativeAnswers",
        span_kind=SpanKind.LLM,
        start_time=datetime(2025, 1, 15, 10, 0, 1, tzinfo=timezone.utc),
        end_time=datetime(2025, 1, 15, 10, 0, 1, tzinfo=timezone.utc),
        conversation_id="conv-test",
        session_id="sess-test",
        user_id="user-test",
        channel_id="msteams",
        llm_input="Hello",
        llm_output="Hi there!",
    )
    child_tool = SpanNode(
        name="SearchAction",
        span_kind=SpanKind.TOOL,
        start_time=datetime(2025, 1, 15, 10, 0, 2, tzinfo=timezone.utc),
        end_time=datetime(2025, 1, 15, 10, 0, 2, tzinfo=timezone.utc),
        conversation_id="conv-test",
        session_id="sess-test",
        user_id="user-test",
        channel_id="msteams",
        tool_name="SearchAction",
    )
    chain = SpanNode(
        name="HelpTopic",
        span_kind=SpanKind.CHAIN,
        start_time=datetime(2025, 1, 15, 10, 0, 0, 500000, tzinfo=timezone.utc),
        end_time=datetime(2025, 1, 15, 10, 0, 3, tzinfo=timezone.utc),
        conversation_id="conv-test",
        session_id="sess-test",
        user_id="user-test",
        channel_id="msteams",
        topic_name="HelpTopic",
        children=[child_llm, child_tool],
    )
    root = SpanNode(
        name="Copilot Studio Conversation",
        span_kind=SpanKind.AGENT,
        start_time=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2025, 1, 15, 10, 0, 3, tzinfo=timezone.utc),
        conversation_id="conv-test",
        session_id="sess-test",
        user_id="user-test",
        channel_id="msteams",
        children=[chain],
    )
    return root


def _identity_mapper(node: SpanNode) -> dict:
    return {"openinference.span.kind": node.span_kind.value}


class TestSpanBuilder:
    def test_exports_correct_number_of_spans(self) -> None:
        provider, exporter = _make_provider_and_exporter()
        builder = SpanBuilder(provider.get_tracer("test"))
        builder.export_trace_tree(_make_tree(), attributes_map=_identity_mapper)
        provider.force_flush()

        spans = exporter.get_finished_spans()
        # root + chain + llm + tool = 4 spans
        assert len(spans) == 4

    def test_span_names(self) -> None:
        provider, exporter = _make_provider_and_exporter()
        builder = SpanBuilder(provider.get_tracer("test"))
        builder.export_trace_tree(_make_tree(), attributes_map=_identity_mapper)
        provider.force_flush()

        names = {s.name for s in exporter.get_finished_spans()}
        assert names == {
            "Copilot Studio Conversation",
            "HelpTopic",
            "GenerativeAnswers",
            "SearchAction",
        }

    def test_all_spans_share_trace_id(self) -> None:
        provider, exporter = _make_provider_and_exporter()
        builder = SpanBuilder(provider.get_tracer("test"))
        builder.export_trace_tree(_make_tree(), attributes_map=_identity_mapper)
        provider.force_flush()

        trace_ids = {s.context.trace_id for s in exporter.get_finished_spans()}
        assert len(trace_ids) == 1

    def test_parent_child_relationships(self) -> None:
        provider, exporter = _make_provider_and_exporter()
        builder = SpanBuilder(provider.get_tracer("test"))
        builder.export_trace_tree(_make_tree(), attributes_map=_identity_mapper)
        provider.force_flush()

        spans = {s.name: s for s in exporter.get_finished_spans()}
        root = spans["Copilot Studio Conversation"]
        chain = spans["HelpTopic"]
        llm = spans["GenerativeAnswers"]
        tool = spans["SearchAction"]

        # Root span should have no parent
        assert root.parent is None

        # Chain's parent should be root
        assert chain.parent.span_id == root.context.span_id
        # LLM and TOOL parents should be chain
        assert llm.parent.span_id == chain.context.span_id
        assert tool.parent.span_id == chain.context.span_id

    def test_separate_trees_have_different_trace_ids(self) -> None:
        provider, exporter = _make_provider_and_exporter()
        builder = SpanBuilder(provider.get_tracer("test"))

        tree1 = _make_tree()
        tree2 = _make_tree()
        tree2.conversation_id = "conv-other"

        builder.export_trace_tree(tree1, attributes_map=_identity_mapper)
        builder.export_trace_tree(tree2, attributes_map=_identity_mapper)
        provider.force_flush()

        spans = exporter.get_finished_spans()
        trace_ids = {s.context.trace_id for s in spans}
        # Two separate trees should have two different trace IDs
        assert len(trace_ids) == 2

    def test_error_events_recorded(self) -> None:
        provider, exporter = _make_provider_and_exporter()
        builder = SpanBuilder(provider.get_tracer("test"))

        error_node = SpanNode(
            name="ErrorConversation",
            span_kind=SpanKind.AGENT,
            start_time=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 15, 10, 0, 1, tzinfo=timezone.utc),
            conversation_id="conv-err",
            session_id="sess-err",
            user_id="user-err",
            channel_id="msteams",
            errors=["AgentTransferFailed"],
        )
        builder.export_trace_tree(error_node, attributes_map=_identity_mapper)
        provider.force_flush()

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert len(span.events) == 1
        assert span.events[0].name == "exception"
        assert span.events[0].attributes["exception.message"] == "AgentTransferFailed"

    def test_span_attributes_from_mapper(self) -> None:
        provider, exporter = _make_provider_and_exporter()
        builder = SpanBuilder(provider.get_tracer("test"))

        node = SpanNode(
            name="TestSpan",
            span_kind=SpanKind.AGENT,
            start_time=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 15, 10, 0, 1, tzinfo=timezone.utc),
            conversation_id="conv-attr",
            session_id="sess-attr",
            user_id="user-attr",
            channel_id="webchat",
        )

        def custom_mapper(n: SpanNode) -> dict:
            return {"custom.attr": "test-value", "openinference.span.kind": "AGENT"}

        builder.export_trace_tree(node, attributes_map=custom_mapper)
        provider.force_flush()

        span = exporter.get_finished_spans()[0]
        assert span.attributes["custom.attr"] == "test-value"

    def test_error_event_has_exception_type(self) -> None:
        provider, exporter = _make_provider_and_exporter()
        builder = SpanBuilder(provider.get_tracer("test"))

        error_node = SpanNode(
            name="ErrorSpan",
            span_kind=SpanKind.AGENT,
            start_time=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 15, 10, 0, 1, tzinfo=timezone.utc),
            conversation_id="conv-err",
            session_id="sess-err",
            user_id="user-err",
            channel_id="msteams",
            errors=["AgentTransferFailed"],
        )
        builder.export_trace_tree(error_node, attributes_map=_identity_mapper)
        provider.force_flush()

        span = exporter.get_finished_spans()[0]
        assert span.events[0].attributes["exception.type"] == "AgentTransferFailed"
        assert span.events[0].attributes["exception.message"] == "AgentTransferFailed"
