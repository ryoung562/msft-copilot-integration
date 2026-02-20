"""Tests for the OpenInference transformation mapper."""

from datetime import datetime, timezone

from src.reconstruction.span_models import SpanKind, SpanNode
from src.transformation.mapper import OpenInferenceMapper


def _make_node(**overrides) -> SpanNode:
    defaults = dict(
        name="test-span",
        span_kind=SpanKind.AGENT,
        start_time=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2025, 1, 15, 10, 1, 0, tzinfo=timezone.utc),
        conversation_id="conv-test",
        session_id="sess-test",
        user_id="user-test",
        channel_id="msteams",
    )
    defaults.update(overrides)
    return SpanNode(**defaults)


class TestOpenInferenceMapper:
    def setup_method(self) -> None:
        self.mapper = OpenInferenceMapper()

    def test_agent_span_kind(self) -> None:
        node = _make_node(span_kind=SpanKind.AGENT)
        attrs = self.mapper.map_attributes(node)
        assert attrs["openinference.span.kind"] == "AGENT"

    def test_chain_span_kind(self) -> None:
        node = _make_node(span_kind=SpanKind.CHAIN)
        attrs = self.mapper.map_attributes(node)
        assert attrs["openinference.span.kind"] == "CHAIN"

    def test_session_id_uses_conversation_id(self) -> None:
        node = _make_node(conversation_id="conv-abc", session_id="sess-123", user_id="user-456")
        attrs = self.mapper.map_attributes(node)
        # session.id should be conversation_id for per-conversation grouping
        assert attrs["session.id"] == "conv-abc"
        assert attrs["user.id"] == "user-456"

    def test_session_id_falls_back_to_session_id(self) -> None:
        node = _make_node(conversation_id="", session_id="sess-123")
        attrs = self.mapper.map_attributes(node)
        assert attrs["session.id"] == "sess-123"

    def test_long_session_id_is_hashed(self) -> None:
        long_id = "a:" + "x" * 140  # 142 chars, over the 128 limit
        node = _make_node(conversation_id=long_id)
        attrs = self.mapper.map_attributes(node)
        assert len(attrs["session.id"]) == 64  # SHA-256 hex digest
        # Deterministic — same input always gives same hash
        node2 = _make_node(conversation_id=long_id)
        attrs2 = self.mapper.map_attributes(node2)
        assert attrs["session.id"] == attrs2["session.id"]

    def test_input_output_values(self) -> None:
        node = _make_node(
            input_messages=["Hello", "How are you?"],
            output_messages=["I'm fine, thanks!"],
        )
        attrs = self.mapper.map_attributes(node)
        assert attrs["input.value"] == "Hello\nHow are you?"
        assert attrs["input.mime_type"] == "text/plain"
        assert attrs["output.value"] == "I'm fine, thanks!"
        assert attrs["output.mime_type"] == "text/plain"

    def test_no_input_output_when_empty(self) -> None:
        node = _make_node()
        attrs = self.mapper.map_attributes(node)
        assert "input.value" not in attrs
        assert "output.value" not in attrs

    def test_metadata_contains_conversation_session_and_channel(self) -> None:
        import json

        node = _make_node(
            conversation_id="conv-x",
            session_id="sess-y",
            channel_id="webchat",
            topic_name="MyTopic",
        )
        attrs = self.mapper.map_attributes(node)
        metadata = json.loads(attrs["metadata"])
        assert metadata["conversation_id"] == "conv-x"
        assert metadata["session_id"] == "sess-y"
        assert metadata["channel_id"] == "webchat"
        assert metadata["topic_name"] == "MyTopic"

    def test_tags_include_channel_and_topic(self) -> None:
        node = _make_node(channel_id="webchat", topic_name="BillingHelp")
        attrs = self.mapper.map_attributes(node)
        assert "webchat" in attrs["tag.tags"]
        assert "BillingHelp" in attrs["tag.tags"]

    def test_llm_span_attributes(self) -> None:
        node = _make_node(
            span_kind=SpanKind.LLM,
            llm_input="What is the policy?",
            llm_output="The policy states...",
        )
        attrs = self.mapper.map_attributes(node)
        assert attrs["llm.model_name"] == "copilot-studio-generative"
        assert attrs["llm.input_messages.0.message.role"] == "user"
        assert attrs["llm.input_messages.0.message.content"] == "What is the policy?"
        assert attrs["llm.output_messages.0.message.role"] == "assistant"
        assert attrs["llm.output_messages.0.message.content"] == "The policy states..."

    def test_tool_span_attributes(self) -> None:
        node = _make_node(
            span_kind=SpanKind.TOOL,
            tool_name="SearchKnowledgeBase",
            input_messages=["query: billing"],
        )
        attrs = self.mapper.map_attributes(node)
        assert attrs["tool.name"] == "SearchKnowledgeBase"
        assert attrs["input.value"] == "query: billing"

    def test_genai_passthrough(self) -> None:
        node = _make_node(span_kind=SpanKind.LLM)
        genai = {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.usage.input_tokens": 150,
            "gen_ai.usage.output_tokens": 80,
        }
        attrs = self.mapper.map_attributes(node, genai_attrs=genai)
        assert attrs["openinference.span.kind"] == "chat"
        assert attrs["llm.model_name"] == "gpt-4o"
        assert attrs["llm.token_count.prompt"] == 150
        assert attrs["llm.token_count.completion"] == 80

    def test_subagent_llm_model_name(self) -> None:
        node = _make_node(span_kind=SpanKind.LLM, agent_type="SubAgent")
        attrs = self.mapper.map_attributes(node)
        assert attrs["llm.model_name"] == "copilot-studio-subagent"

    def test_default_llm_model_name(self) -> None:
        node = _make_node(span_kind=SpanKind.LLM, agent_type=None)
        attrs = self.mapper.map_attributes(node)
        assert attrs["llm.model_name"] == "copilot-studio-generative"

    def test_metadata_includes_agent_type(self) -> None:
        import json

        node = _make_node(agent_type="SubAgent")
        attrs = self.mapper.map_attributes(node)
        metadata = json.loads(attrs["metadata"])
        assert metadata["agent_type"] == "SubAgent"

    def test_metadata_includes_action_id(self) -> None:
        import json

        node = _make_node(span_kind=SpanKind.TOOL, action_id="sendMessage_abc123")
        attrs = self.mapper.map_attributes(node)
        metadata = json.loads(attrs["metadata"])
        assert metadata["action_id"] == "sendMessage_abc123"

    def test_metadata_excludes_none_agent_type(self) -> None:
        import json

        node = _make_node(agent_type=None, action_id=None)
        attrs = self.mapper.map_attributes(node)
        metadata = json.loads(attrs["metadata"])
        assert "agent_type" not in metadata
        assert "action_id" not in metadata

    def test_metadata_includes_locale(self) -> None:
        import json

        node = _make_node(locale="en-us")
        attrs = self.mapper.map_attributes(node)
        metadata = json.loads(attrs["metadata"])
        assert metadata["locale"] == "en-us"

    def test_metadata_excludes_none_locale(self) -> None:
        import json

        node = _make_node(locale=None)
        attrs = self.mapper.map_attributes(node)
        metadata = json.loads(attrs["metadata"])
        assert "locale" not in metadata

    def test_knowledge_search_in_metadata_and_tags(self) -> None:
        import json

        node = _make_node(knowledge_search_detected=True)
        attrs = self.mapper.map_attributes(node)
        metadata = json.loads(attrs["metadata"])
        assert metadata["knowledge_search_detected"] is True
        assert "knowledge_search" in attrs["tag.tags"]

    def test_no_knowledge_search_when_false(self) -> None:
        import json

        node = _make_node(knowledge_search_detected=False)
        attrs = self.mapper.map_attributes(node)
        metadata = json.loads(attrs["metadata"])
        assert "knowledge_search_detected" not in metadata
        assert "knowledge_search" not in attrs["tag.tags"]

    def test_system_topic_in_metadata_and_tags(self) -> None:
        import json

        node = _make_node(
            span_kind=SpanKind.CHAIN,
            is_system_topic=True,
            topic_name="Greeting",
        )
        attrs = self.mapper.map_attributes(node)
        metadata = json.loads(attrs["metadata"])
        assert metadata["is_system_topic"] is True
        assert metadata["topic_type"] == "system"
        assert "system_topic" in attrs["tag.tags"]

    def test_custom_topic_type(self) -> None:
        import json

        node = _make_node(
            span_kind=SpanKind.CHAIN,
            is_system_topic=False,
            topic_name="BillingSupport",
        )
        attrs = self.mapper.map_attributes(node)
        metadata = json.loads(attrs["metadata"])
        assert "is_system_topic" not in metadata
        assert metadata["topic_type"] == "custom"
        assert "system_topic" not in attrs["tag.tags"]

    def test_no_topic_type_when_no_topic(self) -> None:
        import json

        node = _make_node(is_system_topic=False, topic_name=None)
        attrs = self.mapper.map_attributes(node)
        metadata = json.loads(attrs["metadata"])
        assert "topic_type" not in metadata
