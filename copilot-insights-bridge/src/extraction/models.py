"""Pydantic models for raw Application Insights event rows."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


def _get_dim(dims: dict, *keys: str) -> object | None:
    """Case-insensitive lookup that tries multiple key variants."""
    for key in keys:
        if key in dims:
            return dims[key]
    return None


class AppInsightsEvent(BaseModel):
    """A single event row extracted from the Application Insights customEvents table.

    Top-level fields come directly from the query result columns, while most
    domain-specific fields are nested inside ``customDimensions``.
    """

    timestamp: datetime
    name: str
    operation_id: str = Field(default="")
    operation_parent_id: str = Field(default="")
    session_id: str = Field(default="")

    # Fields sourced from customDimensions
    conversation_id: str = Field(default="")
    user_id: str = Field(default="")
    channel_id: str = Field(default="")

    topic_name: Optional[str] = None
    topic_id: Optional[str] = None
    kind: Optional[str] = None
    text: Optional[str] = None
    from_id: Optional[str] = None
    from_name: Optional[str] = None
    recipient_id: Optional[str] = None
    recipient_name: Optional[str] = None
    activity_type: Optional[str] = None
    error_code_text: Optional[str] = None
    message: Optional[str] = None
    result: Optional[str] = None
    summary: Optional[str] = None
    design_mode: Optional[str] = None

    # New fields for real Copilot Studio telemetry
    action_id: Optional[str] = None
    agent_type: Optional[str] = None
    agent_inputs: Optional[str] = None
    agent_outputs: Optional[str] = None
    speak: Optional[str] = None
    locale: Optional[str] = None

    @classmethod
    def from_query_row(cls, row: dict[str, object]) -> AppInsightsEvent:
        """Build an ``AppInsightsEvent`` from a raw query-result row.

        The *row* dict may contain top-level columns (``timestamp``, ``name``,
        ``operation_Id``, etc.) as well as a nested ``customDimensions`` dict
        (or pre-flattened ``customDimensions_*`` columns depending on how the
        query is structured).

        Handles ``customDimensions`` arriving as either a JSON string or a dict.
        Supports both camelCase and PascalCase field names.

        Also handles timestamp field variations from different export methods:
        - Azure CLI: "timestamp"
        - Azure Portal: "timestamp [UTC]"
        """
        raw_dims = row.get("customDimensions")
        if isinstance(raw_dims, str):
            dims = json.loads(raw_dims)
        elif isinstance(raw_dims, dict):
            dims = raw_dims
        else:
            dims = {}

        # user_id: try userId, then fromId, then top-level user_Id
        user_id = (
            _get_dim(dims, "userId")
            or _get_dim(dims, "fromId")
            or row.get("user_Id")
            or ""
        )

        # timestamp: handle both Azure CLI ("timestamp") and Portal ("timestamp [UTC]") formats
        timestamp_value = row.get("timestamp") or row.get("timestamp [UTC]")

        return cls(
            timestamp=_require_datetime(timestamp_value),
            name=str(row.get("name", "")),
            operation_id=str(row.get("operation_Id", "") or ""),
            operation_parent_id=str(row.get("operation_ParentId", "") or ""),
            # session_id: Copilot Studio assigns a session_Id per conversation.
            # A new session starts when a user opens a new conversation; after
            # 30 min of inactivity Copilot Studio issues a new session_Id.
            # We prefer the top-level column, falling back to customDimensions.
            session_id=str(
                row.get("session_Id", "")
                or _get_dim(dims, "sessionId")
                or ""
            ),
            conversation_id=str(_get_dim(dims, "conversationId") or ""),
            user_id=str(user_id),
            channel_id=str(_get_dim(dims, "channelId") or ""),
            topic_name=_opt_str(_get_dim(dims, "topicName", "TopicName")),
            topic_id=_opt_str(_get_dim(dims, "topicId", "TopicId")),
            kind=_opt_str(_get_dim(dims, "kind", "Kind")),
            text=_opt_str(_get_dim(dims, "text")),
            from_id=_opt_str(_get_dim(dims, "fromId")),
            from_name=_opt_str(_get_dim(dims, "fromName")),
            recipient_id=_opt_str(_get_dim(dims, "recipientId")),
            recipient_name=_opt_str(_get_dim(dims, "recipientName")),
            activity_type=_opt_str(_get_dim(dims, "activityType", "type")),
            error_code_text=_opt_str(_get_dim(dims, "errorCodeText")),
            message=_opt_str(_get_dim(dims, "message")),
            result=_opt_str(_get_dim(dims, "result")),
            summary=_opt_str(_get_dim(dims, "summary")),
            design_mode=_opt_str(_get_dim(dims, "designMode", "DesignMode")),
            action_id=_opt_str(_get_dim(dims, "actionId", "ActionId")),
            agent_type=_opt_str(_get_dim(dims, "agentType", "AgentType")),
            agent_inputs=_opt_str(_get_dim(dims, "agentInputs", "AgentInputs")),
            agent_outputs=_opt_str(_get_dim(dims, "agentOutputs", "AgentOutputs")),
            speak=_opt_str(_get_dim(dims, "speak")),
            locale=_opt_str(_get_dim(dims, "locale")),
        )


def _opt_str(value: object) -> Optional[str]:
    """Return *value* as a string, or ``None`` if it is falsy."""
    if value is None:
        return None
    return str(value)


def _require_datetime(value: object) -> datetime:
    """Coerce *value* to a ``datetime``, raising on failure.

    Supports multiple timestamp formats:
    - ISO 8601: "2026-02-27T14:30:00Z"
    - Azure Portal export: "2/27/2026, 2:47:13.411 PM"
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Try ISO 8601 format first (most common)
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass

        # Try Azure Portal export format: "M/D/YYYY, H:MM:SS.mmm AM/PM"
        if "/" in value and "," in value:
            try:
                # With milliseconds
                return datetime.strptime(value, "%m/%d/%Y, %I:%M:%S.%f %p")
            except ValueError:
                try:
                    # Without milliseconds
                    return datetime.strptime(value, "%m/%d/%Y, %I:%M:%S %p")
                except ValueError:
                    pass

        raise ValueError(f"Cannot parse timestamp string: {value}")

    raise TypeError(f"Cannot convert {type(value).__name__} to datetime")
