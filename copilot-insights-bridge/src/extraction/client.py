"""Application Insights query client for extracting Copilot Studio telemetry."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

from src.extraction.models import AppInsightsEvent
from src.extraction.queries import build_custom_events_query

logger = logging.getLogger(__name__)


class AppInsightsClient:
    """Thin wrapper around :class:`LogsQueryClient` for Copilot Studio events.

    Parameters
    ----------
    resource_id:
        The fully-qualified Azure resource ID for the Application Insights
        instance, e.g.
        ``/subscriptions/<sub>/resourceGroups/<rg>/providers/microsoft.insights/components/<name>``.
    """

    def __init__(self, resource_id: str) -> None:
        self._resource_id = resource_id
        self._credential = DefaultAzureCredential()
        self._client = LogsQueryClient(
            self._credential,
            retry_total=3,
            retry_backoff_factor=0.8,
            retry_backoff_max=30,
        )

    def query_events(
        self,
        start_time: datetime,
        end_time: datetime,
        exclude_design_mode: bool = True,
    ) -> list[AppInsightsEvent]:
        """Execute a KQL query and return parsed :class:`AppInsightsEvent` objects.

        Parameters
        ----------
        start_time:
            Inclusive lower bound.
        end_time:
            Exclusive upper bound.
        exclude_design_mode:
            Filter out design-mode (test canvas) traffic.

        Returns
        -------
        list[AppInsightsEvent]
            Events ordered by timestamp ascending.
        """
        query = build_custom_events_query(start_time, end_time, exclude_design_mode)

        timespan = (start_time, end_time)
        response = self._client.query_resource(
            resource_id=self._resource_id,
            query=query,
            timespan=timespan,
        )

        if response.status == LogsQueryStatus.SUCCESS:
            table = response.tables[0]
        elif hasattr(response, "partial_data") and response.partial_data:
            logger.warning("Partial query results returned; processing available data.")
            table = response.partial_data[0]
        else:
            logger.error("Query failed: %s", getattr(response, "message", "unknown error"))
            return []

        # Columns may be plain strings or objects with a .name attribute
        # depending on the azure-monitor-query SDK version.
        columns = [
            col.name if hasattr(col, "name") else str(col)
            for col in table.columns
        ]
        events: list[AppInsightsEvent] = []

        for row in table.rows:
            row_dict = dict(zip(columns, row))
            events.append(AppInsightsEvent.from_query_row(row_dict))

        logger.info("Extracted %d events from %s to %s", len(events), start_time, end_time)
        return events
