"""Universal file loader for Application Insights event data.

Auto-detects and parses four JSON formats:

1. **SDK table format** — ``{"tables": [{"columns": [...], "rows": [[...], ...]}]}``
   Used by ``real_data_dump.json``, ``live_data_dump.json``.

2. **Azure CLI format** — ``{"tables": [{"rows": [[...], ...]}]}``
   Rows are arrays without column definitions.  Used by partners following the
   collection guide.

3. **Event array format** — ``[{...}, {...}]`` where each dict has a
   ``customDimensions`` key.

4. **Flat row-dict format** — ``[{...}, {...}]`` with top-level keys like
   ``timestamp``, ``name``, ``operation_Id``.  Used by synthetic test fixtures.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.extraction.models import AppInsightsEvent

logger = logging.getLogger(__name__)


def load_events_from_file(path: str | Path) -> list[AppInsightsEvent]:
    """Load events from any supported JSON format.  Auto-detects format."""
    path = Path(path)
    data = json.loads(path.read_text())

    if isinstance(data, dict) and "tables" in data:
        rows = _parse_table_format(data)
    elif isinstance(data, list):
        rows = data
    else:
        raise ValueError(f"Unexpected JSON structure in {path.name}: {type(data)}")

    events = [AppInsightsEvent.from_query_row(row) for row in rows]
    events.sort(key=lambda e: e.timestamp)
    logger.info("Loaded %d events from %s", len(events), path.name)
    return events


def _parse_table_format(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse Azure table-format JSON into a list of row dicts.

    Handles two sub-variants:
    - **SDK format**: ``columns`` key present with column name/type metadata.
      Each row is zipped with column names to produce a dict.
    - **Azure CLI format**: No ``columns`` key (or columns lack names).
      Rows are positional arrays:
      ``[timestamp, name, operation_Id, operation_ParentId, customDimensions]``.
    """
    table = data["tables"][0]
    raw_rows = table["rows"]

    if not raw_rows:
        return []

    columns_meta = table.get("columns")

    # SDK format: columns have name metadata
    if columns_meta and isinstance(columns_meta[0], dict) and "name" in columns_meta[0]:
        col_names = [col["name"] for col in columns_meta]
        return [dict(zip(col_names, row)) for row in raw_rows]

    # Azure CLI format: rows are positional arrays
    if isinstance(raw_rows[0], list):
        return [_cli_row_to_dict(row) for row in raw_rows]

    # Rows are already dicts (unlikely but handle gracefully)
    if isinstance(raw_rows[0], dict):
        return raw_rows

    raise ValueError(
        f"Cannot parse table rows: first row is {type(raw_rows[0]).__name__}"
    )


def _cli_row_to_dict(row: list[Any]) -> dict[str, Any]:
    """Convert a positional Azure CLI row to a keyed dict.

    Expected positions: [timestamp, name, operation_Id, operation_ParentId, customDimensions]
    """
    if len(row) < 5:
        raise ValueError(f"Azure CLI row has {len(row)} columns, expected at least 5")

    custom_dims = row[4]
    if isinstance(custom_dims, str):
        custom_dims = json.loads(custom_dims)

    return {
        "timestamp": row[0],
        "name": row[1],
        "operation_Id": row[2] or "",
        "operation_ParentId": row[3] or "",
        "customDimensions": custom_dims,
    }
