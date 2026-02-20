"""Internal span tree dataclasses for trace reconstruction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class SpanKind(Enum):
    """Kinds of spans in a reconstructed trace tree."""

    AGENT = "AGENT"
    CHAIN = "CHAIN"
    LLM = "LLM"
    TOOL = "TOOL"


@dataclass
class SpanNode:
    """A node in the reconstructed trace tree.

    Represents a logical span derived from one or more App Insights events.
    """

    name: str
    span_kind: SpanKind
    start_time: datetime
    end_time: datetime
    children: list[SpanNode] = field(default_factory=list)
    input_messages: list[str] = field(default_factory=list)
    output_messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    conversation_id: str = ""
    session_id: str = ""
    user_id: str = ""
    channel_id: str = ""
    topic_name: Optional[str] = None
    topic_id: Optional[str] = None
    tool_name: Optional[str] = None
    llm_input: Optional[str] = None
    llm_output: Optional[str] = None
    agent_type: Optional[str] = None
    action_id: Optional[str] = None
    locale: Optional[str] = None
    knowledge_search_detected: bool = False
    is_system_topic: bool = False
    raw_events: list[Any] = field(default_factory=list)
