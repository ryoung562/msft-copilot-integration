"""Builds trace trees from flat App Insights events."""

from __future__ import annotations

import re
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from src.extraction.models import AppInsightsEvent
from src.reconstruction.span_models import SpanKind, SpanNode

_AGENT_SPAN_NAME = "Copilot Studio Conversation"
_LLM_SPAN_NAME = "GenerativeAnswers"

# BotMessageReceived types that represent actual user messages
_MESSAGE_TYPES = {"message", None}
# Types to ignore for input text extraction
_NON_MESSAGE_TYPES = {"event", "installationUpdate", "invoke", "messageReaction"}

# Known system topic names (case-insensitive matching after prefix stripping)
_SYSTEM_TOPIC_NAMES = {
    "greeting", "goodbye", "thankyou", "escalate", "endofconversation",
    "fallback", "conversationstart", "conversationalboosting",
    "multipletopicsmatched", "onerror", "resetconversation", "signin",
    "confirmedsuccess", "confirmedfailure",
}

# Events that are structural or already handled — NOT unknown
_KNOWN_TOPIC_EVENTS = {
    "GenerativeAnswers", "Action", "TopicAction",
    "AgentStarted", "AgentCompleted",
    "BotMessageReceived", "BotMessageSend",
    "BotMessageUpdate", "BotMessageDelete",
    "TopicStart", "TopicEnd",
}

# Regex to detect citation markers like [1], [2] in bot output
_CITATION_PATTERN = re.compile(r"\[\d+\]")


def shift_tree_timestamps(node: SpanNode, offset: timedelta) -> None:
    """Recursively shift all start/end times in a span tree by *offset*."""
    node.start_time = node.start_time + offset
    node.end_time = node.end_time + offset
    for child in node.children:
        shift_tree_timestamps(child, offset)


def _topic_names_match(name_a: str | None, name_b: str | None) -> bool:
    """Check if two topic names match, accounting for prefixed names.

    Real data uses prefixed names like ``auto_agent_Y6JvM.topic.Greeting``
    alongside short names like ``Greeting``.  This helper strips the prefix
    portion (everything up to and including the last ``.``) before comparing.
    """
    if name_a is None or name_b is None:
        return name_a == name_b

    def _short(name: str) -> str:
        # "auto_agent_Y6JvM.topic.Greeting" -> "Greeting"
        # "PowerVirtualAgentRoot" -> "PowerVirtualAgentRoot"
        parts = name.rsplit(".", 1)
        return parts[-1] if len(parts) > 1 else name

    return _short(name_a) == _short(name_b) or name_a == name_b


def _short_topic_name(name: str) -> str:
    """Strip the environment/bot prefix from a topic name.

    ``"auto_agent_Y6JvM.topic.Greeting"`` → ``"Greeting"``
    """
    parts = name.rsplit(".", 1)
    return parts[-1] if len(parts) > 1 else name


def _is_system_topic(topic_name: str) -> bool:
    """Check if *topic_name* is a known Copilot Studio system topic."""
    return _short_topic_name(topic_name).lower() in _SYSTEM_TOPIC_NAMES


@dataclass
class _TopicWindow:
    """Tracks a TopicStart/TopicEnd pair and its contained events."""

    topic_name: str
    topic_id: Optional[str]
    start_time: datetime
    end_time: Optional[datetime] = None
    events: list[AppInsightsEvent] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.events is None:
            self.events = []


class TraceTreeBuilder:
    """Reconstructs span trees from flat App Insights events.

    Groups events by conversation, identifies topic windows, and builds a
    hierarchical trace tree suitable for OTLP export.
    """

    def build_trees(self, events: list[AppInsightsEvent]) -> list[SpanNode]:
        """Build one root SpanNode per *turn* from a flat list of events.

        A turn is defined by each user message (``BotMessageReceived`` with
        type ``"message"``).  All turns from the same conversation share the
        same ``session_id`` so they are linked in Arize.

        Args:
            events: Flat list of App Insights events, in any order.

        Returns:
            List of root SpanNode trees, one per user-message turn.
        """
        grouped = self._group_by_conversation(events)
        roots: list[SpanNode] = []
        for conv_id, conv_events in sorted(grouped.items()):
            turns = self._split_into_turns(conv_events)
            for turn_events in turns:
                root = self._build_conversation_tree(conv_id, turn_events)
                roots.append(root)

        # Post-processing: detect knowledge search patterns and flag traces
        for root in roots:
            self._remove_empty_wrapper_chains(root)
            self._detect_knowledge_search(root)
            self._propagate_locale(root)
            self._propagate_design_mode(root)

        # Filter out empty traces (no input, no output, no children)
        roots = [r for r in roots if not self._is_empty_trace(r)]

        return roots

    # ------------------------------------------------------------------
    # Grouping
    # ------------------------------------------------------------------

    @staticmethod
    def _group_by_conversation(
        events: list[AppInsightsEvent],
    ) -> dict[str, list[AppInsightsEvent]]:
        """Group events by conversation_id, falling back to session_id then operation_id.

        Grouping is by *conversation*, not session.  A single Copilot Studio
        session (``session_Id``) may contain multiple conversations, and the
        bridge does not split or merge sessions — it trusts the session_Id that
        Copilot Studio assigned.  The session_id is later written to every span
        as ``session.id`` so Arize can group all traces from the same session.
        """
        groups: dict[str, list[AppInsightsEvent]] = defaultdict(list)
        for event in events:
            key = event.conversation_id or event.session_id or event.operation_id
            groups[key].append(event)
        # Sort each group chronologically
        for group in groups.values():
            group.sort(key=lambda e: e.timestamp)
        return dict(groups)

    @staticmethod
    def _split_into_turns(
        events: list[AppInsightsEvent],
    ) -> list[list[AppInsightsEvent]]:
        """Split a conversation's events into turns at each user message.

        Each ``BotMessageReceived`` with a message-type activity (``"message"``
        or ``None``) starts a new turn.  Events before the first user message
        are included in the first turn.  This produces one trace per
        user-query / agent-response pair.
        """
        turns: list[list[AppInsightsEvent]] = []
        current_turn: list[AppInsightsEvent] = []

        for event in events:  # already sorted chronologically
            is_user_message = (
                event.name == "BotMessageReceived"
                and event.activity_type not in _NON_MESSAGE_TYPES
            )
            if is_user_message and current_turn:
                turns.append(current_turn)
                current_turn = []
            current_turn.append(event)

        if current_turn:
            turns.append(current_turn)

        # Merge pre-turn events (before the first user message) into the
        # first real turn so we don't emit an empty trace for setup events
        # like installationUpdate.
        if len(turns) >= 2:
            first_has_user_msg = any(
                e.name == "BotMessageReceived"
                and e.activity_type not in _NON_MESSAGE_TYPES
                for e in turns[0]
            )
            if not first_has_user_msg:
                turns[1] = turns[0] + turns[1]
                turns.pop(0)

        return turns if turns else [events]

    # ------------------------------------------------------------------
    # Per-conversation tree building
    # ------------------------------------------------------------------

    def _build_conversation_tree(
        self, conv_id: str, events: list[AppInsightsEvent]
    ) -> SpanNode:
        """Build a single root AGENT span for one conversation."""
        first = events[0]
        start_time = min(e.timestamp for e in events)
        end_time = max(e.timestamp for e in events)

        # Derive user_id from first BotMessageReceived with type "message"
        user_id = first.user_id
        for e in events:
            if e.name == "BotMessageReceived" and e.activity_type in _MESSAGE_TYPES and e.from_id:
                user_id = e.from_id
                break

        # Derive locale from first event that has one
        locale = None
        for e in events:
            if e.locale:
                locale = e.locale
                break

        # Derive design_mode flag — true if any event is flagged as design mode
        design_mode = any(
            e.design_mode and e.design_mode.lower() == "true" for e in events
        )

        root = SpanNode(
            name=_AGENT_SPAN_NAME,
            span_kind=SpanKind.AGENT,
            start_time=start_time,
            end_time=end_time,
            conversation_id=conv_id,
            session_id=first.session_id,
            user_id=user_id,
            channel_id=first.channel_id,
            locale=locale,
            design_mode=design_mode,
        )

        # Identify topic windows and assign events into them
        topic_windows = self._find_topic_windows(events)
        orphans = self._assign_events_to_topics(events, topic_windows)

        # Build CHAIN children for each topic window
        for window in topic_windows:
            chain = self._build_topic_span(window, conv_id, first)
            root.children.append(chain)

        # Attach orphan events directly to root
        self._attach_orphans(root, orphans)

        # Propagate child chain outputs to root for trace-level visibility.
        # The user's BotMessageReceived is typically an orphan (arriving before
        # TopicStart) so it naturally lands on root.input_messages.  But the
        # bot's BotMessageSend usually falls within a topic window and only
        # populates chain.output_messages.  Copy them up so Arize shows the
        # bot response on the root AGENT span.
        if not root.output_messages:
            for child in root.children:
                root.output_messages.extend(child.output_messages)

        # Ensure all descendants inherit root context (user_id, session_id).
        # Some child events don't carry these fields in the raw telemetry.
        self._propagate_root_context(root)

        return root

    # ------------------------------------------------------------------
    # Topic window detection
    # ------------------------------------------------------------------

    @staticmethod
    def _find_topic_windows(events: list[AppInsightsEvent]) -> list[_TopicWindow]:
        """Find TopicStart/TopicEnd pairs and return topic windows.

        Uses a stack-based approach with fuzzy name matching.  When a new
        TopicStart arrives for a topic name that is already open on the stack,
        the previous window is implicitly closed to prevent overlapping windows
        that span the entire conversation.
        """
        stack: list[_TopicWindow] = []
        closed_windows: list[_TopicWindow] = []
        last_ts = max(e.timestamp for e in events) if events else datetime.min

        for event in events:
            if event.name == "TopicStart" and event.topic_name:
                # Implicitly close any existing window for the same topic name.
                # In real Copilot data, a new TopicStart for the same topic
                # means the previous invocation has ended.
                for i in range(len(stack) - 1, -1, -1):
                    if _topic_names_match(stack[i].topic_name, event.topic_name):
                        prev = stack.pop(i)
                        prev.end_time = event.timestamp
                        closed_windows.append(prev)
                        break

                window = _TopicWindow(
                    topic_name=event.topic_name,
                    topic_id=event.topic_id,
                    start_time=event.timestamp,
                )
                stack.append(window)

            elif event.name == "TopicEnd" and event.topic_name:
                # Pop matching entry from stack using fuzzy matching
                matched_idx = None
                for i in range(len(stack) - 1, -1, -1):
                    if _topic_names_match(stack[i].topic_name, event.topic_name):
                        matched_idx = i
                        break

                if matched_idx is not None:
                    window = stack.pop(matched_idx)
                    window.end_time = event.timestamp
                    closed_windows.append(window)

        # Close any remaining open windows at last event time
        for window in stack:
            window.end_time = last_ts
            closed_windows.append(window)

        # Sort by start time for deterministic ordering
        closed_windows.sort(key=lambda w: w.start_time)
        return closed_windows

    @staticmethod
    def _assign_events_to_topics(
        events: list[AppInsightsEvent],
        windows: list[_TopicWindow],
    ) -> list[AppInsightsEvent]:
        """Assign non-structural events to topic windows by time range.

        Returns orphan events that fall outside all topic windows.
        Uses fuzzy topic name matching for assignment.  When multiple windows
        overlap, prefers the most recently started window (locality principle).
        """
        structural = {"TopicStart", "TopicEnd"}
        orphans: list[AppInsightsEvent] = []

        # Pre-sort windows by start_time descending for "most recent first" matching.
        windows_recent_first = sorted(windows, key=lambda w: w.start_time, reverse=True)

        for event in events:
            if event.name in structural:
                continue

            assigned = False

            # First pass: match by topic_id or topic_name (most recent first)
            for window in windows_recent_first:
                assert window.end_time is not None
                if window.start_time <= event.timestamp <= window.end_time:
                    if event.topic_id and event.topic_id == window.topic_id:
                        window.events.append(event)
                        assigned = True
                        break
                    elif event.topic_name and _topic_names_match(event.topic_name, window.topic_name):
                        window.events.append(event)
                        assigned = True
                        break

            # Fallback: assign by time range alone, preferring most recent window
            if not assigned:
                for window in windows_recent_first:
                    assert window.end_time is not None
                    if window.start_time <= event.timestamp <= window.end_time:
                        window.events.append(event)
                        assigned = True
                        break

            if not assigned:
                orphans.append(event)

        return orphans

    # ------------------------------------------------------------------
    # Span construction
    # ------------------------------------------------------------------

    def _build_topic_span(
        self,
        window: _TopicWindow,
        conv_id: str,
        first_event: AppInsightsEvent,
    ) -> SpanNode:
        """Build a CHAIN span for a topic window with LLM/TOOL children."""
        assert window.end_time is not None
        chain = SpanNode(
            name=window.topic_name,
            span_kind=SpanKind.CHAIN,
            start_time=window.start_time,
            end_time=window.end_time,
            conversation_id=conv_id,
            session_id=first_event.session_id,
            user_id=first_event.user_id,
            channel_id=first_event.channel_id,
            topic_name=window.topic_name,
            topic_id=window.topic_id,
        )

        # Track pending agent span for AgentStarted/AgentCompleted pairs
        pending_agent_span: SpanNode | None = None

        for event in window.events:
            chain.raw_events.append(event)

            if event.name == "GenerativeAnswers":
                child = SpanNode(
                    name=_LLM_SPAN_NAME,
                    span_kind=SpanKind.LLM,
                    start_time=event.timestamp,
                    end_time=event.timestamp,
                    conversation_id=conv_id,
                    session_id=event.session_id,
                    user_id=event.user_id,
                    channel_id=event.channel_id,
                    topic_name=window.topic_name,
                    topic_id=window.topic_id,
                    llm_input=event.message,
                    llm_output=event.result,
                    summary=event.summary,
                    raw_events=[event],
                )
                if event.error_code_text:
                    child.errors.append(event.error_code_text)
                chain.children.append(child)

            elif event.name in ("Action", "TopicAction"):
                tool_name = event.kind or event.action_id or "UnknownAction"
                child = SpanNode(
                    name=tool_name,
                    span_kind=SpanKind.TOOL,
                    start_time=event.timestamp,
                    end_time=event.timestamp,
                    conversation_id=conv_id,
                    session_id=event.session_id,
                    user_id=event.user_id,
                    channel_id=event.channel_id,
                    topic_name=window.topic_name,
                    topic_id=window.topic_id,
                    tool_name=tool_name,
                    action_id=event.action_id,
                    raw_events=[event],
                )
                if event.text:
                    child.input_messages.append(event.text)
                if event.error_code_text:
                    child.errors.append(event.error_code_text)
                chain.children.append(child)

            elif event.name == "AgentStarted":
                # Extract task from AgentInputs JSON
                llm_input = None
                if event.agent_inputs:
                    try:
                        inputs = json.loads(event.agent_inputs)
                        llm_input = inputs.get("Task")
                    except (json.JSONDecodeError, AttributeError):
                        llm_input = event.agent_inputs

                pending_agent_span = SpanNode(
                    name="AgentCall",
                    span_kind=SpanKind.LLM,
                    start_time=event.timestamp,
                    end_time=event.timestamp,  # Will be updated by AgentCompleted
                    conversation_id=conv_id,
                    session_id=event.session_id,
                    user_id=event.user_id,
                    channel_id=event.channel_id,
                    topic_name=window.topic_name,
                    topic_id=window.topic_id,
                    llm_input=llm_input,
                    agent_type=event.agent_type,
                    raw_events=[event],
                )
                chain.children.append(pending_agent_span)

            elif event.name == "AgentCompleted":
                if pending_agent_span is not None:
                    pending_agent_span.end_time = event.timestamp
                    pending_agent_span.raw_events.append(event)
                    # Parse agent_outputs as fallback for llm_output
                    # (BotMessageSend takes priority — only set if still None)
                    if pending_agent_span.llm_output is None and event.agent_outputs:
                        try:
                            outputs = json.loads(event.agent_outputs)
                            if isinstance(outputs, dict):
                                # Use "Answer" key if present, else first string value
                                answer = outputs.get("Answer")
                                if answer:
                                    pending_agent_span.llm_output = str(answer)
                                else:
                                    for v in outputs.values():
                                        if isinstance(v, str) and v:
                                            pending_agent_span.llm_output = v
                                            break
                        except (json.JSONDecodeError, AttributeError):
                            pass

            elif event.name == "BotMessageReceived":
                # Only treat actual user messages as input text
                if event.activity_type not in _NON_MESSAGE_TYPES and event.text:
                    chain.input_messages.append(event.text)
                    child = SpanNode(
                        name="BotMessageReceived",
                        span_kind=SpanKind.CHAIN,
                        start_time=event.timestamp,
                        end_time=event.timestamp,
                        conversation_id=conv_id,
                        session_id=event.session_id,
                        user_id=event.user_id,
                        channel_id=event.channel_id,
                        topic_name=window.topic_name,
                        topic_id=window.topic_id,
                        raw_events=[event],
                    )
                    child.input_messages.append(event.text)
                    chain.children.append(child)

            elif event.name == "BotMessageSend":
                if event.text:
                    chain.output_messages.append(event.text)
                    # If there's a pending agent span waiting for output, populate it
                    if pending_agent_span is not None and pending_agent_span.llm_output is None:
                        pending_agent_span.llm_output = event.text
                        pending_agent_span = None
                    child = SpanNode(
                        name="BotMessageSend",
                        span_kind=SpanKind.CHAIN,
                        start_time=event.timestamp,
                        end_time=event.timestamp,
                        conversation_id=conv_id,
                        session_id=event.session_id,
                        user_id=event.user_id,
                        channel_id=event.channel_id,
                        topic_name=window.topic_name,
                        topic_id=window.topic_id,
                        raw_events=[event],
                    )
                    child.output_messages.append(event.text)
                    chain.children.append(child)

            elif event.name not in _KNOWN_TOPIC_EVENTS:
                # Unknown event type within a topic — create a generic TOOL span
                # to avoid silently dropping telemetry from new Copilot features
                # (prompts, MCP tools, computer use, etc.)
                tool_name = event.kind or event.name
                child = SpanNode(
                    name=tool_name,
                    span_kind=SpanKind.TOOL,
                    start_time=event.timestamp,
                    end_time=event.timestamp,
                    conversation_id=conv_id,
                    session_id=event.session_id,
                    user_id=event.user_id,
                    channel_id=event.channel_id,
                    topic_name=window.topic_name,
                    topic_id=window.topic_id,
                    tool_name=tool_name,
                    raw_events=[event],
                )
                if event.text:
                    child.input_messages.append(event.text)
                if event.error_code_text:
                    child.errors.append(event.error_code_text)
                chain.children.append(child)

            # Propagate errors from any event type to the chain span
            if event.error_code_text and event.name not in ("GenerativeAnswers", "Action", "TopicAction"):
                chain.errors.append(event.error_code_text)

        # Set system topic flag on the CHAIN span and its children
        if _is_system_topic(window.topic_name):
            chain.is_system_topic = True
            for child in chain.children:
                child.is_system_topic = True

        return chain

    @staticmethod
    def _attach_orphans(root: SpanNode, orphans: list[AppInsightsEvent]) -> None:
        """Attach orphan events (outside any topic window) to the root AGENT span.

        Also creates CHAIN child spans for user/bot messages so they appear
        in the Arize trace tree.  Received messages are placed at the
        beginning of root.children, send messages at the end.
        """
        received_children: list[SpanNode] = []
        send_children: list[SpanNode] = []

        for event in orphans:
            root.raw_events.append(event)

            if event.name == "BotMessageReceived":
                # Only treat actual user messages as input
                if event.activity_type not in _NON_MESSAGE_TYPES and event.text:
                    root.input_messages.append(event.text)
                    child = SpanNode(
                        name="BotMessageReceived",
                        span_kind=SpanKind.CHAIN,
                        start_time=event.timestamp,
                        end_time=event.timestamp,
                        conversation_id=root.conversation_id,
                        session_id=event.session_id or root.session_id,
                        user_id=event.user_id or root.user_id,
                        channel_id=event.channel_id or root.channel_id,
                        raw_events=[event],
                    )
                    child.input_messages.append(event.text)
                    received_children.append(child)
            elif event.name == "BotMessageSend" and event.text:
                root.output_messages.append(event.text)
                child = SpanNode(
                    name="BotMessageSend",
                    span_kind=SpanKind.CHAIN,
                    start_time=event.timestamp,
                    end_time=event.timestamp,
                    conversation_id=root.conversation_id,
                    session_id=event.session_id or root.session_id,
                    user_id=event.user_id or root.user_id,
                    channel_id=event.channel_id or root.channel_id,
                    raw_events=[event],
                )
                child.output_messages.append(event.text)
                send_children.append(child)

            if event.error_code_text:
                root.errors.append(event.error_code_text)

        # Insert received messages at beginning, send messages at end
        root.children = received_children + root.children + send_children

    @staticmethod
    def _propagate_root_context(root: SpanNode) -> None:
        """Ensure all descendants inherit the root's user_id and session_id.

        Some child events in Copilot Studio telemetry don't carry user or
        session identifiers.  This fills in blanks so every span in a trace
        has consistent context for Arize session/user grouping.

        The bridge does not determine session boundaries — it passes through
        the ``session_Id`` assigned by Copilot Studio (new session on new
        conversation or after 30 min inactivity).
        """

        def _fill(node: SpanNode) -> None:
            if not node.user_id:
                node.user_id = root.user_id
            if not node.session_id:
                node.session_id = root.session_id
            for child in node.children:
                _fill(child)

        for child in root.children:
            _fill(child)

    @staticmethod
    def _remove_empty_wrapper_chains(root: SpanNode) -> None:
        """Remove CHAIN children that have no content.

        Copilot Studio emits ``PowerVirtualAgentRoot`` TopicStart events as
        wrappers alongside real topics.  These produce near-zero-duration CHAIN
        spans with no children, no input, and no output — just noise in the
        trace.  Any bot messages that happened to fall in their time window are
        propagated to the root before removal.
        """
        kept: list[SpanNode] = []
        for child in root.children:
            if child.span_kind != SpanKind.CHAIN:
                kept.append(child)
                continue

            has_content = (
                child.children
                or child.input_messages
                or child.output_messages
                or child.raw_events
            )
            if has_content:
                kept.append(child)
            # else: silently drop the empty wrapper chain

        root.children = kept

    @staticmethod
    def _detect_knowledge_search(root: SpanNode) -> None:
        """Detect traces where the orchestrator answered from knowledge sources.

        Signals:
        - Output text contains citation markers ``[1]``, ``[2]``, etc.
          (strong signal — always flags).
        - Root has *user input* and output but no child spans, meaning the
          orchestrator answered directly without triggering a topic.  Requires
          input to avoid false positives on system messages like CSAT feedback.
        """
        has_input = bool(root.input_messages)
        has_output = bool(root.output_messages)
        # Message spans (BotMessageReceived/BotMessageSend) are structural —
        # don't count them as "real" children for knowledge search detection.
        _msg_names = {"BotMessageReceived", "BotMessageSend"}
        has_children = any(c.name not in _msg_names for c in root.children)
        has_citations = any(
            _CITATION_PATTERN.search(msg) for msg in root.output_messages
        )

        if has_citations:
            root.knowledge_search_detected = True
        elif has_input and has_output and not has_children:
            root.knowledge_search_detected = True

    @staticmethod
    def _propagate_locale(root: SpanNode) -> None:
        """Copy the root's locale to all descendants that lack one."""
        if not root.locale:
            return

        def _fill(node: SpanNode) -> None:
            if not node.locale:
                node.locale = root.locale
            for child in node.children:
                _fill(child)

        for child in root.children:
            _fill(child)

    @staticmethod
    def _propagate_design_mode(root: SpanNode) -> None:
        """Copy the root's design_mode flag to all descendants."""
        if not root.design_mode:
            return

        def _fill(node: SpanNode) -> None:
            node.design_mode = True
            for child in node.children:
                _fill(child)

        for child in root.children:
            _fill(child)

    @staticmethod
    def _is_empty_trace(root: SpanNode) -> bool:
        """Return True if the trace has no user input and no meaningful content.

        Filters out traces like CSAT star-rating submissions that have no input
        text and produce no child spans (just system flow overhead).
        """
        has_input = bool(root.input_messages)
        has_output = bool(root.output_messages)
        has_children = bool(root.children)
        return not has_input and not has_output and not has_children
