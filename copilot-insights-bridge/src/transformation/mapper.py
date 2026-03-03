"""Map reconstructed SpanNode trees to OpenInference attribute dictionaries."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.reconstruction.span_models import SpanKind, SpanNode

# ---------------------------------------------------------------------------
# OpenInference semantic-convention attribute keys (string literals to avoid
# a hard dependency on the openinference-semantic-conventions package).
# ---------------------------------------------------------------------------
OPENINFERENCE_SPAN_KIND = "openinference.span.kind"
INPUT_VALUE = "input.value"
INPUT_MIME_TYPE = "input.mime_type"
OUTPUT_VALUE = "output.value"
OUTPUT_MIME_TYPE = "output.mime_type"
SESSION_ID = "session.id"
USER_ID = "user.id"
METADATA = "metadata"
TAG_TAGS = "tag.tags"
LLM_MODEL_NAME = "llm.model_name"
LLM_INPUT_MESSAGES = "llm.input_messages"
LLM_OUTPUT_MESSAGES = "llm.output_messages"
LLM_TOKEN_COUNT_PROMPT = "llm.token_count.prompt"
LLM_TOKEN_COUNT_COMPLETION = "llm.token_count.completion"
TOOL_NAME = "tool.name"

MIME_TEXT_PLAIN = "text/plain"

# GenAI passthrough source keys
_GENAI_OPERATION_NAME = "gen_ai.operation.name"
_GENAI_REQUEST_MODEL = "gen_ai.request.model"
_GENAI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
_GENAI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

# Arize enforces a 128-char limit on session.id.
_MAX_SESSION_ID_LEN = 128


def _truncate_session_id(value: str) -> str:
    """Shorten *value* to fit Arize's 128-char session ID limit.

    Uses a SHA-256 hex digest (64 chars) for deterministic, collision-resistant
    mapping when the raw ID exceeds the limit.
    """
    if len(value) <= _MAX_SESSION_ID_LEN:
        return value
    return hashlib.sha256(value.encode()).hexdigest()


class OpenInferenceMapper:
    """Convert a ``SpanNode`` into a flat OpenInference attribute dict."""

    def map_attributes(
        self,
        node: SpanNode,
        genai_attrs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return OpenInference attributes for *node*.

        Parameters
        ----------
        node:
            The reconstructed span to map.
        genai_attrs:
            Optional dictionary of ``gen_ai.*`` attributes extracted from the
            raw telemetry.  When provided, recognised keys are mapped to their
            OpenInference equivalents and take precedence over values derived
            from the SpanNode.
        """
        attrs: dict[str, Any] = {}

        # -- Span kind --
        attrs[OPENINFERENCE_SPAN_KIND] = node.span_kind.value

        # -- Input / Output values --
        if node.input_messages:
            attrs[INPUT_VALUE] = "\n".join(node.input_messages)
            attrs[INPUT_MIME_TYPE] = MIME_TEXT_PLAIN

        if node.output_messages:
            attrs[OUTPUT_VALUE] = "\n".join(node.output_messages)
            attrs[OUTPUT_MIME_TYPE] = MIME_TEXT_PLAIN

        # -- Session / user context --
        # Use conversation_id as the Arize session ID so each conversation
        # groups independently.  Copilot Studio's session_Id is a persistent
        # user/channel identifier that doesn't reset per conversation.
        attrs[SESSION_ID] = _truncate_session_id(node.conversation_id or node.session_id)
        attrs[USER_ID] = node.user_id

        # -- Metadata --
        metadata: dict[str, Any] = {
            "conversation_id": node.conversation_id,
            "session_id": node.session_id,
            "channel_id": node.channel_id,
        }
        if node.topic_name is not None:
            metadata["topic_name"] = node.topic_name
        if node.agent_type is not None:
            metadata["agent_type"] = node.agent_type
        if node.action_id is not None:
            metadata["action_id"] = node.action_id
        if node.locale is not None:
            metadata["locale"] = node.locale
        if node.knowledge_search_detected:
            metadata["knowledge_search_detected"] = True
        if node.is_system_topic:
            metadata["is_system_topic"] = True
            metadata["topic_type"] = "system"
        elif node.topic_name is not None:
            metadata["topic_type"] = "custom"
        attrs[METADATA] = json.dumps(metadata)

        # -- Tags --
        tags: list[str] = [node.channel_id]
        if node.topic_name is not None:
            tags.append(node.topic_name)
        if node.knowledge_search_detected:
            tags.append("knowledge_search")
        if node.is_system_topic:
            tags.append("system_topic")
        elif node.topic_name is not None:
            tags.append("custom_topic")
        if node.design_mode:
            tags.append("design_mode")
        else:
            tags.append("production")
        if node.locale:
            tags.append(node.locale)
        if node.errors:
            tags.append("has_error")
        tags.append(node.span_kind.value.lower())
        # OTel natively supports Sequence[str]; Arize expects a native list.
        attrs[TAG_TAGS] = tags

        # -- LLM-specific attributes --
        if node.span_kind == SpanKind.LLM:
            if node.agent_type == "SubAgent":
                attrs[LLM_MODEL_NAME] = "copilot-studio-subagent"
            else:
                attrs[LLM_MODEL_NAME] = "copilot-studio-generative"
            if node.llm_input is not None:
                attrs[f"{LLM_INPUT_MESSAGES}.0.message.role"] = "user"
                attrs[f"{LLM_INPUT_MESSAGES}.0.message.content"] = node.llm_input
                # Also set input.value so Arize shows it in the span detail panel
                if not node.input_messages:
                    attrs[INPUT_VALUE] = node.llm_input
                    attrs[INPUT_MIME_TYPE] = MIME_TEXT_PLAIN
            if node.llm_output is not None:
                attrs[f"{LLM_OUTPUT_MESSAGES}.0.message.role"] = "assistant"
                attrs[f"{LLM_OUTPUT_MESSAGES}.0.message.content"] = node.llm_output
                # Also set output.value so Arize shows it in the span detail panel
                if not node.output_messages:
                    attrs[OUTPUT_VALUE] = node.llm_output
                    attrs[OUTPUT_MIME_TYPE] = MIME_TEXT_PLAIN

        # -- TOOL-specific attributes --
        if node.span_kind == SpanKind.TOOL:
            if node.tool_name is not None:
                attrs[TOOL_NAME] = node.tool_name
            # Prefer explicit input_messages; fall back to llm_input for tool input.
            if node.input_messages:
                attrs[INPUT_VALUE] = "\n".join(node.input_messages)
                attrs[INPUT_MIME_TYPE] = MIME_TEXT_PLAIN
            elif node.llm_input is not None:
                attrs[INPUT_VALUE] = node.llm_input
                attrs[INPUT_MIME_TYPE] = MIME_TEXT_PLAIN

        # -- GenAI passthrough --
        if genai_attrs:
            self._apply_genai_passthrough(attrs, genai_attrs)

        return attrs

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_genai_passthrough(
        attrs: dict[str, Any],
        genai_attrs: dict[str, Any],
    ) -> None:
        """Overlay recognised ``gen_ai.*`` attributes onto *attrs*."""
        mapping: dict[str, str] = {
            _GENAI_OPERATION_NAME: OPENINFERENCE_SPAN_KIND,
            _GENAI_REQUEST_MODEL: LLM_MODEL_NAME,
            _GENAI_USAGE_INPUT_TOKENS: LLM_TOKEN_COUNT_PROMPT,
            _GENAI_USAGE_OUTPUT_TOKENS: LLM_TOKEN_COUNT_COMPLETION,
        }
        for src_key, dest_key in mapping.items():
            if src_key in genai_attrs:
                attrs[dest_key] = genai_attrs[src_key]
