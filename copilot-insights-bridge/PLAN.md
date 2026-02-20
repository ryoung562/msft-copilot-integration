# Implementation Plan: Pathway C — Application Insights to OTLP Bridge (Copilot Studio)

## Context

Microsoft Copilot Studio is a low-code platform for building conversational AI agents. Its only telemetry extensibility point is Azure Application Insights — there is no way to configure an arbitrary OTLP exporter directly. To get Copilot Studio agent observability into Arize AX, we need a bridge service that:

1. Queries Copilot Studio telemetry from Application Insights (via KQL/REST API)
2. Reconstructs hierarchical trace trees from flat events
3. Transforms the data to OpenInference-formatted OpenTelemetry spans
4. Exports to Arize AX via OTLP

This is a **reference implementation** — a well-documented sample showing customers how to bridge Copilot Studio telemetry to Arize AX. It should be clear, well-tested against mock data, and easy to adapt for production use.

**Deployment targets**: Docker container + standalone Python script (no Azure Function).

---

## Architecture

```
Copilot Studio Agent
    --> Azure Application Insights (customEvents / traces tables)
        --> Bridge Service (poll every ~5 min via REST API)
            --> Arize AX OTLP Endpoint (otlp.arize.com:443)
```

**Polling approach**: Query the Application Insights REST API on a schedule using `azure-monitor-query` SDK. A high-water mark cursor tracks the last processed timestamp to avoid reprocessing.

---

## Project Structure

```
copilot-insights-bridge/
├── pyproject.toml
├── Dockerfile
├── .env.example
├── README.md                          # Setup guide, architecture, configuration docs
│
├── scripts/
│   ├── diagnose_gaps.py               # Offline diagnostic — reports on gap-analysis flags
│   └── export_to_arize.py             # Export a data dump to Arize AX
│
├── src/
│   ├── __init__.py
│   ├── config.py                      # Pydantic settings (env vars)
│   ├── main.py                        # Standalone entry point (poll loop)
│   │
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── client.py                  # App Insights query client (azure-monitor-query SDK)
│   │   ├── queries.py                 # KQL query definitions
│   │   └── models.py                  # Pydantic models for raw App Insights rows
│   │
│   ├── reconstruction/
│   │   ├── __init__.py
│   │   ├── tree_builder.py            # Builds trace trees from flat events
│   │   └── span_models.py             # Internal span tree dataclasses
│   │
│   ├── transformation/
│   │   ├── __init__.py
│   │   └── mapper.py                  # App Insights -> OpenInference attribute mapping
│   │
│   ├── export/
│   │   ├── __init__.py
│   │   ├── otel_exporter.py           # TracerProvider + OTLP exporter setup for Arize
│   │   └── span_builder.py            # Creates OTel SDK spans from internal models
│   │
│   └── state/
│       ├── __init__.py
│       └── cursor.py                  # High-water mark cursor (file-based)
│
└── tests/
    ├── conftest.py
    ├── fixtures/                       # Sample App Insights response JSON
    │   ├── single_conversation.json
    │   ├── multi_topic_conversation.json
    │   ├── generative_answers.json
    │   ├── error_conversation.json
    │   ├── real_data_dump.json         # Original real data (Session 1)
    │   └── live_data_dump.json         # Live msteams data (Session 2)
    ├── test_extraction.py
    ├── test_reconstruction.py
    ├── test_transformation.py
    ├── test_export.py
    ├── test_cursor.py
    └── test_end_to_end.py
```

---

## Implementation Steps

### Step 1: Project scaffolding and configuration
**Files**: `pyproject.toml`, `.env.example`, `src/config.py`
**Status**: COMPLETE

- Dependencies: azure-monitor-query, azure-identity, opentelemetry-api/sdk/exporter-otlp-proto-grpc, openinference-semantic-conventions, pydantic/pydantic-settings
- Configuration via environment variables with `BRIDGE_` prefix:
  - `BRIDGE_APPINSIGHTS_RESOURCE_ID` — Azure resource ID for App Insights
  - `BRIDGE_ARIZE_SPACE_ID`, `BRIDGE_ARIZE_API_KEY`, `BRIDGE_ARIZE_PROJECT_NAME`
  - `BRIDGE_POLL_INTERVAL_MINUTES` (default: 5)
  - `BRIDGE_EXCLUDE_DESIGN_MODE` (default: true)
  - `BRIDGE_INITIAL_LOOKBACK_HOURS` (default: 24)

### Step 2: Data extraction from Application Insights
**Files**: `src/extraction/client.py`, `src/extraction/queries.py`, `src/extraction/models.py`
**Status**: COMPLETE

- Client wraps `azure-monitor-query.LogsQueryClient.query_resource()` with `DefaultAzureCredential`
- KQL query against `customEvents` table extracting from `customDimensions`: conversationId, sessionId, userId, channelId, topicName, topicId, kind, text, fromId, fromName, recipientId, recipientName, activityType, errorCodeText, message, result, summary
- Standard fields: timestamp, name, operation_Id, operation_ParentId
- Optional design mode filter: `where customDimensions['designMode'] == "False"`
- Pydantic models for parsed rows (`AppInsightsEvent`) with `from_query_row()` class method

### Step 3: Trace tree reconstruction
**Files**: `src/reconstruction/tree_builder.py`, `src/reconstruction/span_models.py`
**Status**: COMPLETE

Most complex piece — Application Insights stores flat events, not hierarchical spans.

**Algorithm**:
1. Group events by `conversationId` (fallback: `session_Id`, `operation_Id`)
2. For each conversation, create a root AGENT span covering the full time range
3. Pair `TopicStart`/`TopicEnd` events into CHAIN child spans under the root
4. Within each topic's time window:
   - `GenerativeAnswers` events → LLM child spans (message as input, result as output)
   - `Action` events → TOOL child spans (kind as tool name)
   - `BotMessageReceived` → accumulated as input messages on the topic span
   - `BotMessageSend` → accumulated as output messages on the topic span
   - Events with `errorCodeText` → exception events on the nearest parent span
5. Orphan events (outside any topic window) attach to the root AGENT span

**SpanNode dataclass**: name, span_kind enum, start/end times, children list, input/output message lists, error list, raw event reference, conversation/session/user metadata.

### Step 4: OpenInference transformation
**File**: `src/transformation/mapper.py`
**Status**: COMPLETE

| SpanNode field | OpenInference attribute |
|---|---|
| span_kind (AGENT/CHAIN/LLM/TOOL) | openinference.span.kind |
| Accumulated input messages (text) | input.value + input.mime_type |
| Accumulated output messages (text) | output.value + output.mime_type |
| conversation_id (hashed if >128 chars) | session.id |
| user_id | user.id |
| conversation_id, session_id, channel_id, topic_name, locale, knowledge_search_detected, is_system_topic, topic_type | metadata dict |
| channel_id, topic_name, knowledge_search, system_topic | tag.tags list |

**LLM span specifics** (from GenerativeAnswers events):
- event.message → `llm.input_messages.0.message.role` = "user", `.content` = message
- event.result → `llm.output_messages.0.message.role` = "assistant", `.content` = result
- `llm.model_name` = "copilot-studio-generative" (model name not exposed in telemetry)

**TOOL span specifics**:
- event.kind → `tool.name`
- event.text → `input.value`

**GenAI convention passthrough** (for future Agent 365 SDK telemetry):

| GenAI Convention | OpenInference Equivalent |
|---|---|
| gen_ai.operation.name | openinference.span.kind |
| gen_ai.request.model | llm.model_name |
| gen_ai.usage.input_tokens | llm.token_count.prompt |
| gen_ai.usage.output_tokens | llm.token_count.completion |

### Step 5: OTel span creation and OTLP export
**Files**: `src/export/otel_exporter.py`, `src/export/span_builder.py`
**Status**: COMPLETE (with bug fix applied)

Creates OTel spans from historical data (not live instrumentation). Sets explicit start/end times and establishes parent-child relationships programmatically.

- `TracerProvider` setup with `BatchSpanProcessor` + `OTLPSpanExporter` targeting `otlp.arize.com:443` with space_id/api_key headers
- Span building: For each SpanNode in the tree:
  a. Create parent context using `NonRecordingSpan` + `SpanContext` to control trace ID (derived deterministically from conversationId) and parent span ID
  b. Call `tracer.start_span()` with historical timestamp
  c. Add exception events for errors
  d. Call `span.end()` with historical timestamp
  e. Recurse into children
- **Deterministic IDs**: trace_id from SHA256 of conversation ID, span_id from event identity

**Bug fix applied**: Original code passed deterministic span IDs to children, but OTel SDK assigns its own random IDs. Fix captures `span.get_span_context().span_id` after creation and passes that to children.

### Step 6: State management (cursor)
**File**: `src/state/cursor.py`
**Status**: COMPLETE

- File-based JSON cursor: `last_processed_timestamp`, `last_run_at`, `events_processed_count`
- Before each poll: load cursor → set query start_time
- After successful export: save cursor with latest event timestamp
- First run (no cursor): look back `initial_lookback_hours`
- Safety buffer: `end_time = now() - 2 minutes` for App Insights ingestion lag

### Step 7: Pipeline orchestration and entry points
**File**: `src/main.py`
**Status**: COMPLETE

- `BridgePipeline` class wires: extraction → reconstruction → transformation → export → cursor update
- `run_once()`: single poll cycle
- `run_loop()`: continuous loop with `poll_interval_minutes` sleep
- Error handling: catch exceptions per-trace (one bad conversation doesn't block the batch)
- Graceful shutdown: `tracer_provider.force_flush()` + `shutdown()`

### Step 8: Docker container
**File**: `Dockerfile`
**Status**: COMPLETE

### Step 9: Test fixtures and unit tests
**Files**: `tests/fixtures/*.json`, `tests/test_*.py`
**Status**: COMPLETE — 98/98 passing

- Fixtures: Synthetic App Insights response JSON + real data dumps (single conversation, multi-topic, generative answers, error cases, live msteams data)
- Extraction tests: Mock LogsQueryClient, verify Pydantic model parsing (10 tests)
- Reconstruction tests: Feed fixtures through TraceTreeBuilder, assert tree structure (11 tests + 25 gap-analysis tests)
- Transformation tests: Feed SpanNode trees through OpenInferenceMapper, assert correct attributes (10 tests + 8 gap-analysis tests)
- Export tests: Use InMemorySpanExporter to capture spans, assert hierarchy (8 tests)
- Cursor tests: File-based cursor CRUD (5 tests)
- End-to-end test: Full pipeline with mocked App Insights + InMemorySpanExporter (4 tests)

### Step 10: Documentation
**File**: `README.md`
**Status**: COMPLETE

---

## Key Technical Decisions

1. **Python** — Best SDK support for both `azure-monitor-query` and `opentelemetry-sdk`/`arize-otel`/`openinference-semantic-conventions`
2. **Polling over streaming** — Simpler, fewer dependencies, sufficient for observability (~5 min latency)
3. **File-based cursor** — Simple for reference implementation; easily swappable for Azure Blob/Table in production
4. **Deterministic span IDs** — SHA256-based ID generation from conversation/event identity for idempotent reprocessing
5. **Timeline-based nesting** — Use TopicStart/TopicEnd time windows for parent-child assignment since operation_ParentId isn't reliably set by Copilot Studio

---

## Known Limitations

- Near real-time only (~5 min latency due to polling + App Insights ingestion delay)
- LLM model name not available in Copilot Studio telemetry — defaults to "copilot-studio-generative"
- Token counts and costs not available from Copilot Studio telemetry
- Parent-child accuracy depends on TopicStart/TopicEnd pairs being emitted; orphan events fall back to root span
- App Insights API rate limits — ~100 queries/minute; the 5-min interval is well within limits
- **Knowledge retrieval details in generative orchestration mode**: Copilot Studio does not emit telemetry for knowledge source searches when using generative orchestration. The bridge can only infer it happened (via citations or output-without-children pattern). This is a Microsoft platform limitation.
- **Prompt/MCP/Computer Use tool internals**: No dedicated telemetry for these newer features. The bridge creates generic TOOL spans via the catch-all handler when they appear as unrecognized event types.
- **Orchestration decisions**: No telemetry about WHY the orchestrator chose a particular tool/topic/knowledge source. The selection logic is opaque.
- **Session ID semantics**: Copilot Studio's `session_Id` is a persistent user/channel identifier, not a per-conversation session. The bridge uses `conversation_id` as Arize's `session.id` for proper per-conversation grouping. Long IDs (>128 chars) are SHA-256 hashed to meet Arize's limit.

---

## Verification Plan

1. Unit tests pass: `pytest tests/` — all fixture-based tests green (**DONE** — 98/98)
2. Linting/types: `ruff check src/` + `mypy src/` clean
3. Docker build: `docker build -t copilot-insights-bridge .` succeeds
4. Standalone dry run: Run `python -m src.main` with mock mode to verify pipeline wiring
5. Live validation (**DONE**):
   - Configured Copilot Studio agent with App Insights (**DONE**)
   - Ran test conversations on msteams channel (**DONE**)
   - Pulled 60 live events, ran diagnostic script (**DONE**)
   - Exported 10 traces to Arize AX project `copilot-studio` (**DONE**)
   - Validated: root AGENT spans, CHAIN children for topics, LLM spans for agents, TOOL spans for actions (**DONE**)
   - Verified new metadata: knowledge_search, system_topic, topic_type, locale (**DONE**)
