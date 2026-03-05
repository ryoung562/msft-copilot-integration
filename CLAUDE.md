# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Two approaches for getting Microsoft Copilot Studio telemetry into Arize AX as OpenTelemetry/OpenInference spans. Both share the same reconstruction and export pipeline (`copilot-insights-bridge/`). The core pipeline is complete and live-validated.

## Commands

All commands run from `copilot-insights-bridge/`.

```bash
# Install
pip install .
pip install ".[dev]"      # includes pytest, ruff, mypy

# Tests (168 tests)
pytest tests/ -v
pytest tests/test_reconstruction.py -v                    # single file
pytest tests/test_reconstruction.py::TestClass::test_fn   # single test

# Lint and type check
ruff check src/ tests/
mypy src/

# Approach 1: File export & import (requires only BRIDGE_ARIZE_* env vars)
python scripts/import_to_arize.py data.json                          # inspect (stats + diagnostics)
python scripts/import_to_arize.py data.json --export --shift-to-now  # export to Arize
python scripts/diagnose_gaps.py live_data_dump.json                  # detailed per-span analysis

# Approach 2: Continuous bridge service (requires full .env with Azure + Arize creds)
python -m src.main
```

## Architecture

See `copilot-insights-bridge/CLAUDE.md` for detailed architecture, span hierarchy, configuration table, and technical gotchas.

Two approaches, same pipeline:
- **File import** (`scripts/import_to_arize.py`) — Load JSON files, reconstruct, export. Uses `ArizeSettings` (Arize creds only).
- **Continuous bridge** (`src/main.py`) — Poll Azure App Insights, reconstruct, export. Uses `BridgeSettings` (Arize + Azure creds).

Pipeline: `extraction/ → reconstruction/ → transformation/ → export/`

The reconstruction stage (`tree_builder.py`) is the most complex — it converts flat Azure events into hierarchical `SpanNode` trees grouped by conversation, split into per-turn traces.

## Critical Gotchas

- **Session ID**: Use `conversation_id` as Arize `session.id`, NOT Copilot's `session_Id` (persistent user/channel ID). IDs > 128 chars are SHA-256 hashed.
- **Parent-child spans**: Must use `span.get_span_context().span_id` (SDK-assigned), not deterministic IDs.
- **Missing TopicEnd**: Many topics never emit TopicEnd — implicit-close at turn boundary handles this.
- **OTel attributes**: `tag.tags` must be native `list[str]`, not `json.dumps()`.
- **Arize time window**: Historical re-exports need `--shift-to-now` so ingestion time aligns with span times.

## File Loader Formats

`src/extraction/loader.py` auto-detects four JSON formats:
1. **SDK table** — `{"tables": [{"columns": [...], "rows": [...]}]}`
2. **Azure CLI** — `{"tables": [{"rows": [[...], ...]}]}` (positional arrays, no column metadata)
3. **Event array** — `[{"timestamp": ..., "name": ..., "customDimensions": {...}}, ...]`
4. **Flat row-dict** — `[{"timestamp": ..., "name": ..., "operation_Id": ..., ...}]` (synthetic fixtures)

## Configuration

Environment variables (prefix `BRIDGE_`), loaded via Pydantic `BaseSettings` in `src/config.py`:
- `BRIDGE_APPINSIGHTS_RESOURCE_ID` — Azure resource ID (required)
- `BRIDGE_ARIZE_SPACE_ID`, `BRIDGE_ARIZE_API_KEY` — Arize credentials (required)
- `BRIDGE_ARIZE_PROJECT_NAME` (default: `copilot-studio`)
- `BRIDGE_POLL_INTERVAL_MINUTES` (default: 5), `BRIDGE_INITIAL_LOOKBACK_HOURS` (default: 24)
- `BRIDGE_EXCLUDE_DESIGN_MODE` (default: true)
- `BRIDGE_CURSOR_PATH` (default: `.bridge_cursor.json`)
- `BRIDGE_LOG_FORMAT` (default: `text`, or `json` for structured logging)
- `BRIDGE_MAX_CONSECUTIVE_FAILURES` (default: 5), `BRIDGE_BACKOFF_BASE_SECONDS` (default: 60), `BRIDGE_BACKOFF_MAX_SECONDS` (default: 900)
- `BRIDGE_BUFFER_GRACE_SECONDS` (default: 0, set >0 to buffer events and merge cross-cycle arrivals)
- `BRIDGE_HEALTH_CHECK_ENABLED` (default: true), `BRIDGE_HEALTH_CHECK_PORT` (default: 8080)
