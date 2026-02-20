"""KQL query definitions for Azure Application Insights."""

from __future__ import annotations

from datetime import datetime


def build_custom_events_query(
    start_time: datetime,
    end_time: datetime,
    exclude_design_mode: bool = True,
) -> str:
    """Build a KQL query that fetches Copilot Studio events from ``customEvents``.

    Parameters
    ----------
    start_time:
        Inclusive lower bound for the event timestamp.
    end_time:
        Exclusive upper bound for the event timestamp.
    exclude_design_mode:
        When ``True``, rows where ``customDimensions['designMode'] == "True"``
        are filtered out so that only production traffic is returned.

    Returns
    -------
    str
        A ready-to-execute KQL query string.
    """
    start_iso = start_time.isoformat()
    end_iso = end_time.isoformat()

    design_mode_filter = ""
    if exclude_design_mode:
        design_mode_filter = (
            '| extend _dm = coalesce(tostring(customDimensions["DesignMode"]), tostring(customDimensions["designMode"]), "False")\n'
            '| where _dm != "True"\n'
        )

    return (
        "customEvents\n"
        f"| where timestamp >= datetime({start_iso})\n"
        f"| where timestamp < datetime({end_iso})\n"
        f"{design_mode_filter}"
        "| project\n"
        "    timestamp,\n"
        "    name,\n"
        "    operation_Id,\n"
        "    operation_ParentId,\n"
        "    session_Id,\n"
        "    customDimensions\n"
        "| order by timestamp asc"
    )
