# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

Bridge service that polls Microsoft Copilot Studio telemetry from Azure Application Insights and exports it to Arize AX as OpenTelemetry/OpenInference spans. Located in `copilot-insights-bridge/`.

## Commands

All commands run from the `copilot-insights-bridge/` directory.

```bash
# Run all tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_reconstruction.py -v

# Run a single test
python -m pytest tests/test_reconstruction.py::TestTraceTreeBuilder::test_single_conversation_produces_one_root

# Lint
ruff check src/ tests/

# Type check
mypy src/

# Run the bridge (continuous polling)
python -m src.main

# Import a data file (default: inspect mode — stats + diagnostics)
python scripts/import_to_arize.py tests/fixtures/live_data_dump.json

# Import and export to Arize (requires BRIDGE_* env vars)
python scripts/import_to_arize.py data.json --export --shift-to-now

# Offline gap analysis (detailed per-span report)
python scripts/diagnose_gaps.py live_data_dump.json
```

## Architecture

### Pipeline Stages

```
Azure App Insights (customEvents) → Extraction → Reconstruction → Transformation → Export → Arize AX (OTLP)
```

1. **Extraction** (`src/extraction/`) — KQL queries against Azure App Insights via `LogsQueryClient`. `AppInsightsEvent` is the Pydantic model for raw rows. Handles both camelCase and PascalCase `customDimensions` fields.

2. **Reconstruction** (`src/reconstruction/`) — `TraceTreeBuilder.build_trees()` converts flat events into a tree of `SpanNode` objects. Groups by `conversation_id`, splits into per-turn traces at each `BotMessageReceived`, pairs `TopicStart`/`TopicEnd` into time windows, assigns events to windows by timestamp overlap.

3. **Transformation** (`src/transformation/`) — `OpenInferenceMapper.map_attributes()` converts a `SpanNode` into a flat `dict[str, Any]` of OpenInference attributes (`openinference.span.kind`, `input.value`, `session.id`, `tag.tags`, etc.).

4. **Export** (`src/export/`) — `SpanBuilder.export_trace_tree()` walks the tree depth-first, creating OTel SDK spans with explicit timestamps and parent-child links via `SpanContext`. `create_tracer_provider()` sets up OTLP/gRPC export to `otlp.arize.com:443`.

5. **State** (`src/state/`) — `Cursor` reads/writes a JSON high-water mark file so the poller doesn't reprocess events. Atomic writes via temp file + `os.replace()`.

6. **Orchestration** (`src/main.py`) — `BridgePipeline.run_once()` executes one poll cycle; `run_loop()` polls continuously at `poll_interval_minutes`.

### Span Hierarchy

```
AGENT (root, one per user-message turn)
├── CHAIN (topic execution window, one per TopicStart/TopicEnd pair)
│   ├── LLM (GenerativeAnswers event)
│   ├── LLM (AgentStarted/AgentCompleted pair)
│   └── TOOL (Action/TopicAction event)
└── orphan events (outside any topic window, attached to root)
```

### Configuration

All env vars use `BRIDGE_` prefix, loaded via `BridgeSettings(BaseSettings)` in `src/config.py`:

| Variable | Required | Default |
|----------|----------|---------|
| `BRIDGE_APPINSIGHTS_RESOURCE_ID` | yes | — |
| `BRIDGE_ARIZE_SPACE_ID` | yes | — |
| `BRIDGE_ARIZE_API_KEY` | yes | — |
| `BRIDGE_ARIZE_PROJECT_NAME` | no | `copilot-studio` |
| `BRIDGE_POLL_INTERVAL_MINUTES` | no | `5` |
| `BRIDGE_INITIAL_LOOKBACK_HOURS` | no | `24` |
| `BRIDGE_EXCLUDE_DESIGN_MODE` | no | `true` |
| `BRIDGE_CURSOR_PATH` | no | `.bridge_cursor.json` |

## Key Technical Details

- **Turn splitting**: A new trace starts at each `BotMessageReceived` with `activity_type in {"message", None}`. Non-message activities (event, installationUpdate, invoke, messageReaction) don't split.

- **Topic window assignment**: Events are assigned to the most-recently-started overlapping `TopicStart`/`TopicEnd` window. Many topics never emit `TopicEnd` — implicit close at the last event timestamp handles this.

- **Session ID**: Use `conversation_id` as Arize `session.id`, NOT Copilot's `session_Id` (which is a persistent user/channel ID). IDs > 128 chars are SHA-256 hashed (Arize limit).

- **Parent-child span linking**: Must read `span.get_span_context().span_id` after creation to get the SDK-assigned ID. Passing deterministic IDs to `start_span()` doesn't work — the SDK ignores them.

- **OTel attribute types**: `tag.tags` must be a native `list[str]`, not `json.dumps()`. OTel SDK supports `Sequence[str]` natively.

- **LLM span display**: Arize renders `input.value`/`output.value` in the span detail panel, not `llm.input_messages.*`. Both must be set on LLM spans.

- **Arize time window issue**: `TraceSlideoverSpanDetailsQuery` builds a narrow 2-day window from span `startTime`. Historical re-exports need `--shift-to-now` so `recordTimestamp` aligns with span times.

- **`shift_tree_timestamps()`** in `src/reconstruction/tree_builder.py` is the shared function for recursively offsetting all span times in a tree. Used by `scripts/import_to_arize.py --shift-to-now`.

- **OTel SDK import**: `InMemorySpanExporter` is at `opentelemetry.sdk.trace.export.in_memory_span_exporter` (not `.in_memory`) on this machine.

## Test Patterns

- Synthetic fixtures in `tests/fixtures/*.json` — small hand-crafted scenarios
- Real data fixtures: `live_data_dump.json` (Azure table format with `columns` + `rows`)
- `src/extraction/loader.py` provides `load_events_from_file()` for auto-detecting 4 JSON formats
- `conftest.py` provides `load_real_data_table(name)` for table-format fixtures (raw dicts)
- Tests use `InMemorySpanExporter` to capture and assert on exported spans without hitting Arize
- Current count: 116 tests

## Reference Docs

- `PLAN.md` — Full 10-step implementation plan and architecture decisions
- `DATA_SCHEMA.md` — Complete field catalog, event types, and data mapping reference
