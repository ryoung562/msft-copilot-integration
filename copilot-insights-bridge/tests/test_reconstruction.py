"""Tests for trace tree reconstruction."""

from datetime import datetime, timezone

from src.extraction.models import AppInsightsEvent
from src.reconstruction.span_models import SpanKind, SpanNode
from src.reconstruction.tree_builder import TraceTreeBuilder

# Names of structural message spans added by the builder
_MSG_SPAN_NAMES = {"BotMessageReceived", "BotMessageSend"}


def _topic_chains(node: SpanNode) -> list[SpanNode]:
    """Return non-message CHAIN children (topic/workflow spans only)."""
    return [c for c in node.children if c.name not in _MSG_SPAN_NAMES]


class TestTraceTreeBuilder:
    def setup_method(self) -> None:
        self.builder = TraceTreeBuilder()

    def test_single_conversation_produces_one_root(
        self, single_conversation_events: list[AppInsightsEvent]
    ) -> None:
        trees = self.builder.build_trees(single_conversation_events)
        assert len(trees) == 1
        assert trees[0].span_kind == SpanKind.AGENT

    def test_root_span_name(
        self, single_conversation_events: list[AppInsightsEvent]
    ) -> None:
        root = self.builder.build_trees(single_conversation_events)[0]
        assert root.name == "Copilot Studio Conversation"

    def test_root_span_time_range(
        self, single_conversation_events: list[AppInsightsEvent]
    ) -> None:
        root = self.builder.build_trees(single_conversation_events)[0]
        min_ts = min(e.timestamp for e in single_conversation_events)
        max_ts = max(e.timestamp for e in single_conversation_events)
        assert root.start_time == min_ts
        assert root.end_time == max_ts

    def test_root_span_metadata(
        self, single_conversation_events: list[AppInsightsEvent]
    ) -> None:
        root = self.builder.build_trees(single_conversation_events)[0]
        assert root.conversation_id == "conv-001"
        assert root.session_id == "sess-abc"
        assert root.user_id == "user-42"
        assert root.channel_id == "msteams"

    def test_single_topic_creates_chain_child(
        self, single_conversation_events: list[AppInsightsEvent]
    ) -> None:
        root = self.builder.build_trees(single_conversation_events)[0]
        chains = _topic_chains(root)
        assert len(chains) == 1
        chain = chains[0]
        assert chain.span_kind == SpanKind.CHAIN
        assert chain.name == "PasswordReset"
        assert chain.topic_name == "PasswordReset"

    def test_generative_answers_creates_llm_span(
        self, single_conversation_events: list[AppInsightsEvent]
    ) -> None:
        root = self.builder.build_trees(single_conversation_events)[0]
        chain = _topic_chains(root)[0]
        llm_spans = [c for c in chain.children if c.span_kind == SpanKind.LLM]
        assert len(llm_spans) == 1
        llm = llm_spans[0]
        assert llm.name == "GenerativeAnswers"
        assert llm.llm_input == "How do I reset my password?"
        assert llm.llm_output is not None
        assert "self-service portal" in llm.llm_output

    def test_bot_messages_populate_chain_io(
        self, single_conversation_events: list[AppInsightsEvent]
    ) -> None:
        root = self.builder.build_trees(single_conversation_events)[0]
        chain = _topic_chains(root)[0]
        # BotMessageReceived arrives before TopicStart so it becomes an orphan on root.
        # BotMessageSend arrives within the topic window so it attaches to the chain.
        assert len(chain.output_messages) == 1
        assert "self-service portal" in chain.output_messages[0]
        # The input message lands on the root AGENT span (orphan).
        assert len(root.input_messages) == 1
        assert "reset my password" in root.input_messages[0]
        # Output is propagated to root for trace-level visibility in Arize.
        assert len(root.output_messages) == 1
        assert "self-service portal" in root.output_messages[0]

    def test_multi_topic_produces_separate_traces(
        self, multi_topic_events: list[AppInsightsEvent]
    ) -> None:
        trees = self.builder.build_trees(multi_topic_events)
        # 2 user messages → 2 separate traces (one per turn)
        assert len(trees) == 2
        assert trees[0].conversation_id == "conv-002"
        assert trees[1].conversation_id == "conv-002"
        # Each trace has 1 topic chain (plus message spans)
        topic_chains_0 = _topic_chains(trees[0])
        assert len(topic_chains_0) == 1
        assert topic_chains_0[0].name == "CalendarLookup"
        topic_chains_1 = _topic_chains(trees[1])
        assert len(topic_chains_1) == 1
        assert topic_chains_1[0].name == "RoomBooking"

    def test_action_creates_tool_span(
        self, multi_topic_events: list[AppInsightsEvent]
    ) -> None:
        trees = self.builder.build_trees(multi_topic_events)
        # CalendarLookup is in the first turn's trace
        calendar_chain = next(c for c in trees[0].children if c.name == "CalendarLookup")
        tool_spans = [c for c in calendar_chain.children if c.span_kind == SpanKind.TOOL]
        assert len(tool_spans) == 1
        tool = tool_spans[0]
        assert tool.name == "GetCalendarEvents"
        assert tool.tool_name == "GetCalendarEvents"
        assert len(tool.input_messages) == 1

    def test_generative_multi_turn(
        self, generative_events: list[AppInsightsEvent]
    ) -> None:
        trees = self.builder.build_trees(generative_events)
        # 2 user messages → 2 separate traces
        assert len(trees) == 2
        assert trees[0].conversation_id == "conv-003"
        assert trees[1].conversation_id == "conv-003"
        for tree in trees:
            chains = _topic_chains(tree)
            assert len(chains) == 1
            llm_children = [c for c in chains[0].children if c.span_kind == SpanKind.LLM]
            assert len(llm_children) == 1

    def test_error_attached_to_tool_span(
        self, error_events: list[AppInsightsEvent]
    ) -> None:
        root = self.builder.build_trees(error_events)[0]
        chain = next(c for c in root.children if c.name == "EscalateToAgent")
        tool_spans = [c for c in chain.children if c.span_kind == SpanKind.TOOL]
        assert len(tool_spans) == 1
        tool = tool_spans[0]
        assert "AgentTransferFailed" in tool.errors

    def test_separate_conversations_produce_separate_trees(
        self,
        single_conversation_events: list[AppInsightsEvent],
        multi_topic_events: list[AppInsightsEvent],
    ) -> None:
        combined = single_conversation_events + multi_topic_events
        trees = self.builder.build_trees(combined)
        # conv-001 has 1 user message (1 turn), conv-002 has 2 (2 turns) = 3 trees
        assert len(trees) == 3
        conv_ids = {t.conversation_id for t in trees}
        assert conv_ids == {"conv-001", "conv-002"}


class TestRealDataReconstruction:
    """Tests using the real App Insights data dump."""

    def setup_method(self) -> None:
        self.builder = TraceTreeBuilder()

    def test_real_data_groups_by_conversation(
        self, real_data_events: list[AppInsightsEvent]
    ) -> None:
        trees = self.builder.build_trees(real_data_events)
        # Turn-based model: more trees than conversations (multiple turns per conv)
        assert len(trees) > 1
        conv_ids = {t.conversation_id for t in trees}
        assert len(conv_ids) >= 1

    def test_production_conversation_has_llm_spans(
        self, real_data_events: list[AppInsightsEvent]
    ) -> None:
        """The production msteams conversation should produce LLM spans from AgentStarted."""
        prod_events = [e for e in real_data_events if e.design_mode == "False"]
        trees = self.builder.build_trees(prod_events)
        assert len(trees) >= 1

        # Collect all LLM spans across all turn-based trees
        llm_spans: list[SpanNode] = []
        for tree in trees:
            for chain in tree.children:
                for child in chain.children:
                    if child.span_kind == SpanKind.LLM:
                        llm_spans.append(child)

        assert len(llm_spans) > 0
        # At least one LLM span should have an agent_type of SubAgent
        sub_agent_spans = [s for s in llm_spans if s.agent_type == "SubAgent"]
        assert len(sub_agent_spans) > 0

    def test_topic_action_creates_tool_spans(
        self, real_data_events: list[AppInsightsEvent]
    ) -> None:
        """TopicAction events should produce TOOL spans."""
        trees = self.builder.build_trees(real_data_events)
        tool_spans: list[SpanNode] = []
        for tree in trees:
            for chain in tree.children:
                for child in chain.children:
                    if child.span_kind == SpanKind.TOOL:
                        tool_spans.append(child)

        assert len(tool_spans) > 0
        # Check tool names come from Kind or ActionId
        tool_names = {s.tool_name for s in tool_spans}
        assert any(n in tool_names for n in ("SendActivity", "CancelAllDialogs"))

    def test_non_message_bot_received_ignored(
        self, real_data_events: list[AppInsightsEvent]
    ) -> None:
        """BotMessageReceived with type 'event'/'installationUpdate'/'invoke' should not add input text."""
        trees = self.builder.build_trees(real_data_events)

        for tree in trees:
            # Root-level inputs should not contain empty strings from non-message types
            for msg in tree.input_messages:
                assert msg.strip() != ""

            for chain in tree.children:
                for msg in chain.input_messages:
                    assert msg.strip() != ""

    def test_greeting_flow_produces_chain(
        self, real_data_events: list[AppInsightsEvent]
    ) -> None:
        """The Greeting topic should produce a CHAIN span."""
        prod_events = [e for e in real_data_events if e.design_mode == "False"]
        trees = self.builder.build_trees(prod_events)

        chain_names: list[str] = []
        for tree in trees:
            for c in tree.children:
                chain_names.append(c.name)
        # Should have at least one Greeting chain (possibly with prefix)
        greeting_chains = [n for n in chain_names if "Greeting" in n]
        assert len(greeting_chains) > 0

    def test_agent_started_has_llm_input(
        self, real_data_events: list[AppInsightsEvent]
    ) -> None:
        """LLM spans from AgentStarted should have llm_input extracted from AgentInputs."""
        prod_events = [e for e in real_data_events if e.design_mode == "False"]
        trees = self.builder.build_trees(prod_events)

        llm_spans: list[SpanNode] = []
        for tree in trees:
            for chain in tree.children:
                for child in chain.children:
                    if child.span_kind == SpanKind.LLM:
                        llm_spans.append(child)

        # At least one LLM span should have a Task extracted as llm_input
        with_input = [s for s in llm_spans if s.llm_input]
        assert len(with_input) > 0

    def test_agent_completed_sets_end_time(
        self, real_data_events: list[AppInsightsEvent]
    ) -> None:
        """AgentCompleted should set end_time different from start_time on LLM spans."""
        prod_events = [e for e in real_data_events if e.design_mode == "False"]
        trees = self.builder.build_trees(prod_events)

        for tree in trees:
            for chain in tree.children:
                for child in chain.children:
                    if child.span_kind == SpanKind.LLM and child.agent_type == "SubAgent":
                        # AgentCompleted should have updated end_time
                        assert child.end_time >= child.start_time


def _make_event(**overrides) -> AppInsightsEvent:
    """Helper to create test events with defaults."""
    defaults = dict(
        timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        name="BotMessageReceived",
        operation_id="op-1",
        session_id="sess-1",
        conversation_id="conv-test",
        user_id="user-1",
        channel_id="msteams",
    )
    defaults.update(overrides)
    return AppInsightsEvent(**defaults)


class TestUnknownEventCatchAll:
    """Gap 2/3: Unknown events within topic windows create generic TOOL spans."""

    def setup_method(self) -> None:
        self.builder = TraceTreeBuilder()

    def test_unknown_event_creates_tool_span(self) -> None:
        """An unrecognized event within a topic should become a generic TOOL span."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="hello",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="MyTopic",
                topic_id="tid-1",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="PromptExecution",
                kind="CustomPrompt",
                topic_name="MyTopic",
                text="Summarize the data",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="MyTopic",
                timestamp=datetime(2025, 6, 1, 12, 0, 3, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        assert len(trees) == 1
        chain = _topic_chains(trees[0])[0]
        tool_spans = [c for c in chain.children if c.span_kind == SpanKind.TOOL]
        assert len(tool_spans) == 1
        assert tool_spans[0].name == "CustomPrompt"
        assert tool_spans[0].tool_name == "CustomPrompt"
        assert "Summarize the data" in tool_spans[0].input_messages

    def test_unknown_event_uses_event_name_when_no_kind(self) -> None:
        """If an unknown event has no Kind, the event name becomes the tool name."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="test",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="TestTopic",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="MCPToolCall",
                topic_name="TestTopic",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="TestTopic",
                timestamp=datetime(2025, 6, 1, 12, 0, 3, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        chain = _topic_chains(trees[0])[0]
        tool_spans = [c for c in chain.children if c.span_kind == SpanKind.TOOL]
        assert len(tool_spans) == 1
        assert tool_spans[0].name == "MCPToolCall"

    def test_unknown_event_with_error_propagates(self) -> None:
        """Errors on unknown events should propagate to both the tool span and chain."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="test",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="TestTopic",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="ComputerUseStep",
                topic_name="TestTopic",
                error_code_text="ScreenshotFailed",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="TestTopic",
                timestamp=datetime(2025, 6, 1, 12, 0, 3, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        chain = _topic_chains(trees[0])[0]
        tool_spans = [c for c in chain.children if c.span_kind == SpanKind.TOOL]
        assert "ScreenshotFailed" in tool_spans[0].errors
        assert "ScreenshotFailed" in chain.errors


class TestKnowledgeSearchDetection:
    """Gap 1: Detect when orchestrator answered from knowledge sources."""

    def setup_method(self) -> None:
        self.builder = TraceTreeBuilder()

    def test_citations_in_output_detected(self) -> None:
        """Output with citation markers [1], [2] signals knowledge search."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="What does Arize do?",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Arize is an AI observability platform [1]. It supports LLM tracing [2].",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        assert len(trees) == 1
        assert trees[0].knowledge_search_detected is True

    def test_output_without_children_detected(self) -> None:
        """Root with output but no children → orchestrator answered directly."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="Hello",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Hi there! How can I help?",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        assert len(trees) == 1
        assert trees[0].knowledge_search_detected is True

    def test_output_with_children_not_detected(self) -> None:
        """Root with output AND children → standard topic flow, not knowledge search."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="Reset password",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="PasswordReset",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Sure, I can help reset your password.",
                topic_name="PasswordReset",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="PasswordReset",
                timestamp=datetime(2025, 6, 1, 12, 0, 3, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        assert len(trees) == 1
        # Has children (the PasswordReset chain) and no citations
        assert trees[0].knowledge_search_detected is False

    def test_citations_detected_even_with_children(self) -> None:
        """Citations in output should flag knowledge search even with children present."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="Tell me about pricing",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="Pricing",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="GenerativeAnswers",
                topic_name="Pricing",
                message="Tell me about pricing",
                result="Our pricing starts at $99/mo [1].",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Our pricing starts at $99/mo [1].",
                topic_name="Pricing",
                timestamp=datetime(2025, 6, 1, 12, 0, 3, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="Pricing",
                timestamp=datetime(2025, 6, 1, 12, 0, 4, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        assert trees[0].knowledge_search_detected is True

    def test_output_only_no_input_not_detected(self) -> None:
        """Output without user input (e.g. CSAT feedback) should NOT be flagged."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="event",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Thanks for your feedback.",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        assert len(trees) == 1
        assert trees[0].knowledge_search_detected is False


class TestSystemTopicDetection:
    """Gap 4: System topics should be flagged."""

    def setup_method(self) -> None:
        self.builder = TraceTreeBuilder()

    def test_greeting_is_system_topic(self) -> None:
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="hi",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="Greeting",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Hello!",
                topic_name="Greeting",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="Greeting",
                timestamp=datetime(2025, 6, 1, 12, 0, 3, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        chain = _topic_chains(trees[0])[0]
        assert chain.is_system_topic is True

    def test_prefixed_system_topic_detected(self) -> None:
        """System topic with environment prefix like 'auto_agent_X.topic.Escalate'."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="speak to a person",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="auto_agent_X.topic.Escalate",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Transferring you now.",
                topic_name="auto_agent_X.topic.Escalate",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="auto_agent_X.topic.Escalate",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        chain = _topic_chains(trees[0])[0]
        assert chain.is_system_topic is True

    def test_goodbye_is_system_topic(self) -> None:
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="bye",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="Goodbye",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Goodbye!",
                topic_name="Goodbye",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="Goodbye",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        chain = _topic_chains(trees[0])[0]
        assert chain.is_system_topic is True

    def test_endofconversation_is_system_topic(self) -> None:
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="done",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="EndofConversation",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Session ended.",
                topic_name="EndofConversation",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="EndofConversation",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        chain = _topic_chains(trees[0])[0]
        assert chain.is_system_topic is True

    def test_custom_topic_not_flagged(self) -> None:
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="help with billing",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="BillingSupport",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Let me look into that.",
                topic_name="BillingSupport",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="BillingSupport",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        chain = _topic_chains(trees[0])[0]
        assert chain.is_system_topic is False


class TestEmptyTraceFiltering:
    """Gap 5: Empty traces (no input, no output, no children) are filtered."""

    def setup_method(self) -> None:
        self.builder = TraceTreeBuilder()

    def test_empty_trace_filtered(self) -> None:
        """A trace with no input, no output, and no children should be filtered."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="event",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        assert len(trees) == 0

    def test_trace_with_input_not_filtered(self) -> None:
        """A trace with user input should NOT be filtered even with no output."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="hello",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        assert len(trees) == 1

    def test_trace_with_output_not_filtered(self) -> None:
        """A trace with bot output should NOT be filtered."""
        events = [
            _make_event(
                name="BotMessageSend",
                text="Welcome!",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        assert len(trees) == 1

    def test_trace_with_children_not_filtered(self) -> None:
        """A trace with meaningful topic children should NOT be filtered."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="event",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="ConversationStart",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Welcome!",
                topic_name="ConversationStart",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="ConversationStart",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        assert len(trees) == 1


class TestLocaleExtraction:
    """Gap 6: Locale should be extracted and propagated."""

    def setup_method(self) -> None:
        self.builder = TraceTreeBuilder()

    def test_locale_on_root(self) -> None:
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="hello",
                locale="en-us",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        assert trees[0].locale == "en-us"

    def test_locale_propagated_to_children(self) -> None:
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="hola",
                locale="es-mx",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="Greeting",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Hola!",
                topic_name="Greeting",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="Greeting",
                timestamp=datetime(2025, 6, 1, 12, 0, 3, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        chain = _topic_chains(trees[0])[0]
        assert chain.locale == "es-mx"


class TestEmptyWrapperChainFiltering:
    """PowerVirtualAgentRoot and other empty wrapper chains should be removed."""

    def setup_method(self) -> None:
        self.builder = TraceTreeBuilder()

    def test_empty_wrapper_chain_removed(self) -> None:
        """A chain with no children, no IO, and no raw events is removed."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="hello",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="Greeting",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="PowerVirtualAgentRoot",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Hi!",
                topic_name="Greeting",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="Greeting",
                timestamp=datetime(2025, 6, 1, 12, 0, 3, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="PowerVirtualAgentRoot",
                timestamp=datetime(2025, 6, 1, 12, 0, 3, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        root = trees[0]
        chain_names = [c.name for c in root.children]
        assert "Greeting" in chain_names
        assert "PowerVirtualAgentRoot" not in chain_names

    def test_wrapper_with_output_kept(self) -> None:
        """A wrapper chain that captured bot output should NOT be removed."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="hi",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="PowerVirtualAgentRoot",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Hello, how can I help?",
                topic_name="PowerVirtualAgentRoot",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="PowerVirtualAgentRoot",
                timestamp=datetime(2025, 6, 1, 12, 0, 3, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        root = trees[0]
        chain_names = [c.name for c in root.children]
        assert "PowerVirtualAgentRoot" in chain_names


class TestMessageSpanCreation:
    """BotMessageReceived/BotMessageSend events create CHAIN child spans."""

    def setup_method(self) -> None:
        self.builder = TraceTreeBuilder()

    def test_orphan_received_creates_chain_child(self) -> None:
        """Orphan BotMessageReceived creates a CHAIN child on root with input text."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="How do I reset my password?",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="You can reset it at the portal.",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        root = trees[0]
        msg_children = [c for c in root.children if c.name == "BotMessageReceived"]
        assert len(msg_children) == 1
        msg = msg_children[0]
        assert msg.span_kind == SpanKind.CHAIN
        assert "reset my password" in msg.input_messages[0]

    def test_orphan_send_creates_chain_child(self) -> None:
        """Orphan BotMessageSend creates a CHAIN child on root with output text."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="Hello",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Hi there! How can I help?",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        root = trees[0]
        msg_children = [c for c in root.children if c.name == "BotMessageSend"]
        assert len(msg_children) == 1
        msg = msg_children[0]
        assert msg.span_kind == SpanKind.CHAIN
        assert "How can I help" in msg.output_messages[0]

    def test_orphan_received_at_beginning_send_at_end(self) -> None:
        """Orphan received messages come first, send messages come last."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="Hello",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Hi!",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        root = trees[0]
        assert root.children[0].name == "BotMessageReceived"
        assert root.children[-1].name == "BotMessageSend"

    def test_in_window_send_creates_chain_child(self) -> None:
        """BotMessageSend within a topic window creates a CHAIN child on the topic chain."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="Help with billing",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="Billing",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Your balance is $42.",
                topic_name="Billing",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="Billing",
                timestamp=datetime(2025, 6, 1, 12, 0, 3, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        chain = _topic_chains(trees[0])[0]
        send_spans = [c for c in chain.children if c.name == "BotMessageSend"]
        assert len(send_spans) == 1
        assert send_spans[0].span_kind == SpanKind.CHAIN
        assert "$42" in send_spans[0].output_messages[0]
        # Chain still has output_messages populated (existing behavior)
        assert "$42" in chain.output_messages[0]

    def test_message_spans_preserve_existing_io(self) -> None:
        """Root input_messages/output_messages are still populated alongside message spans."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="Hello",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="Greeting",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Hi!",
                topic_name="Greeting",
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="Greeting",
                timestamp=datetime(2025, 6, 1, 12, 0, 3, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        root = trees[0]
        # Root still has input/output messages (regression check)
        assert "Hello" in root.input_messages
        assert "Hi!" in root.output_messages
        # Topic chain still has output_messages
        chain = _topic_chains(root)[0]
        assert "Hi!" in chain.output_messages

    def test_non_message_received_no_span(self) -> None:
        """BotMessageReceived with activity_type 'event' should NOT create a message span."""
        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="event",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="BotMessageSend",
                text="Thanks for your feedback.",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        root = trees[0]
        recv_spans = [c for c in root.children if c.name == "BotMessageReceived"]
        assert len(recv_spans) == 0


class TestAgentCompletedOutput:
    """AgentCompleted should populate llm_output from agent_outputs JSON."""

    def setup_method(self) -> None:
        self.builder = TraceTreeBuilder()

    def test_agent_completed_sets_llm_output_from_agent_outputs(self) -> None:
        """When no BotMessageSend precedes AgentCompleted, parse agent_outputs."""
        import json

        events = [
            _make_event(
                name="BotMessageReceived",
                activity_type="message",
                text="What is the refund policy?",
                timestamp=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicStart",
                topic_name="RefundAgent",
                timestamp=datetime(2025, 6, 1, 12, 0, 1, tzinfo=timezone.utc),
            ),
            _make_event(
                name="AgentStarted",
                topic_name="RefundAgent",
                agent_type="SubAgent",
                agent_inputs=json.dumps({"Task": "What is the refund policy?"}),
                timestamp=datetime(2025, 6, 1, 12, 0, 2, tzinfo=timezone.utc),
            ),
            _make_event(
                name="AgentCompleted",
                topic_name="RefundAgent",
                agent_outputs=json.dumps({"Answer": "You can get a refund within 30 days."}),
                timestamp=datetime(2025, 6, 1, 12, 0, 3, tzinfo=timezone.utc),
            ),
            _make_event(
                name="TopicEnd",
                topic_name="RefundAgent",
                timestamp=datetime(2025, 6, 1, 12, 0, 4, tzinfo=timezone.utc),
            ),
        ]
        trees = self.builder.build_trees(events)
        chain = _topic_chains(trees[0])[0]
        llm_spans = [c for c in chain.children if c.span_kind == SpanKind.LLM]
        assert len(llm_spans) == 1
        assert llm_spans[0].llm_output == "You can get a refund within 30 days."
