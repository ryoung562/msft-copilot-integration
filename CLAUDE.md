# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A bridge service (`copilot-insights-bridge/`) that pulls Microsoft Copilot Studio telemetry from Azure Application Insights and exports it to Arize AX as OpenTelemetry/OpenInference spans. The core pipeline is complete and live-validated (10 traces exported).

## Session Continuity

This project uses a documentation system for cross-session context. At session start, read:
1. `docs/session-continuity/CURRENT_STATUS.md` — Latest state, next steps
2. `copilot-insights-bridge/PLAN.md` — Architecture and design decisions
3. `copilot-insights-bridge/DATA_SCHEMA.md` — Data structures and field mappings

## Commands

All commands run from `copilot-insights-bridge/` unless noted.

```bash
# Install dependencies
pip install .
pip install ".[dev]"      # includes pytest, ruff, mypy

# Run tests (116 tests)
pytest tests/ -v
pytest tests/test_reconstruction.py -v   # single file
pytest tests/test_reconstruction.py::test_name -v  # single test

# Lint and type check
ruff check src/
ruff format src/ --check
mypy src/

# Run the bridge (continuous polling, requires .env with Azure/Arize creds)
python -m src.main

# Import a data file (default: inspect mode — stats + diagnostics)
python scripts/import_to_arize.py tests/fixtures/live_data_dump.json

# Import and export to Arize
python scripts/import_to_arize.py data.json --export --shift-to-now

# Offline gap analysis (detailed per-span report)
python scripts/diagnose_gaps.py live_data_dump.json
```

## Architecture

The pipeline has four stages, each in its own module under `copilot-insights-bridge/src/`:

```
extraction/ → reconstruction/ → transformation/ → export/
```

1. **Extraction** (`extraction/client.py`): Queries Azure App Insights `customEvents` table via `azure-monitor-query` SDK. KQL queries defined in `queries.py`. Raw rows parsed into `AppInsightsEvent` Pydantic models (`models.py`).

2. **Reconstruction** (`reconstruction/tree_builder.py`): The most complex stage. Converts flat events into hierarchical span trees:
   - Groups events by `conversation_id`
   - Splits conversations into turns at each user message (`BotMessageReceived`)
   - Pairs `TopicStart`/`TopicEnd` into time windows using a stack with fuzzy name matching
   - Assigns events to topic windows by timestamp + topic name
   - Creates: root AGENT span → CHAIN children (topics) → LLM/TOOL leaf spans

3. **Transformation** (`transformation/mapper.py`): Maps `SpanNode` trees to OpenInference attribute dictionaries. Handles session ID hashing (SHA-256 for IDs >128 chars), LLM message formatting, metadata/tag assembly.

4. **Export** (`export/span_builder.py`, `export/otel_exporter.py`): Creates real OTel SDK spans from historical data with explicit timestamps. Uses `NonRecordingSpan` + `SpanContext` for parent-child linking. Exports via `OTLPSpanExporter` to `otlp.arize.com:443`.

**State**: `state/cursor.py` — File-based JSON high-water mark cursor tracking `last_processed_timestamp`.

**Config**: `config.py` — Pydantic `BaseSettings` with `BRIDGE_` env var prefix.

**Orchestration**: `main.py` — `BridgePipeline.run_once()` executes one poll cycle; `run_loop()` runs continuously.

## Critical Technical Gotchas

- **Session ID semantics**: Copilot Studio's `session_Id` is a persistent user/channel identifier, NOT per-conversation. The bridge uses `conversation_id` as Arize's `session.id`.
- **Parent-child span linking**: Must use `span.get_span_context().span_id` (SDK-assigned) for parent references, not deterministic IDs.
- **Missing TopicEnd events**: Many Copilot topics never emit TopicEnd. The reconstruction handles this via implicit-close at the last event timestamp.
- **OTel import path**: `InMemorySpanExporter` is at `opentelemetry.sdk.trace.export.in_memory_span_exporter` (not `.in_memory`).
- **Topic name matching**: Real data uses prefixed names like `auto_agent_Y6JvM.topic.Greeting` alongside short names like `Greeting`. Fuzzy matching strips prefixes.
- **Arize session.id limit**: 128 chars max. Copilot conversation IDs can be 131+ chars, requiring SHA-256 hashing.

## Test Structure

Tests are in `copilot-insights-bridge/tests/` with fixtures in `tests/fixtures/` (JSON files with synthetic and real App Insights data). Key fixtures:
- `single_conversation.json`, `multi_topic_conversation.json` — synthetic scenarios
- `real_data_dump.json`, `live_data_dump.json` — real Azure data (table format, converted via `conftest.py:load_real_data_table()`)

## Configuration

Environment variables (prefix `BRIDGE_`):
- `BRIDGE_APPINSIGHTS_RESOURCE_ID` — Azure resource ID
- `BRIDGE_ARIZE_SPACE_ID`, `BRIDGE_ARIZE_API_KEY`, `BRIDGE_ARIZE_PROJECT_NAME`
- `BRIDGE_POLL_INTERVAL_MINUTES` (default: 5), `BRIDGE_INITIAL_LOOKBACK_HOURS` (default: 24)
- `BRIDGE_EXCLUDE_DESIGN_MODE` (default: true)

Example configs in `examples/env/`.
