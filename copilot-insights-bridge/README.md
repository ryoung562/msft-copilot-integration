# Copilot Studio → Arize AX

Export Microsoft Copilot Studio telemetry to Arize AX for AI observability.

## Overview

Copilot Studio agents emit telemetry to Azure Application Insights as flat `customEvents`. This project reconstructs those events into hierarchical OpenInference traces and exports them to Arize AX via OTLP, giving you full conversation-level observability: traces, sessions, topics, LLM calls, and tool invocations.

Both approaches share the same core pipeline:

```
Raw events → Reconstruct trace trees → Map to OpenInference → Export via OTLP → Arize AX
```

## Choose Your Approach

| | File Export & Import | Continuous Bridge Service |
|---|---|---|
| **Use case** | One-time analysis, partner data, ad-hoc investigation | Ongoing monitoring, production observability |
| **Prerequisites** | Python, Arize credentials | Python, Arize credentials, Azure credentials |
| **Data source** | JSON files exported from App Insights portal | Live polling from Azure App Insights REST API |
| **Setup time** | ~5 minutes | ~10 minutes |
| **Automation** | Manual (run per file) | Fully automated (polls every N minutes) |

## Approach 1: File Export & Import

Best for one-time analysis, processing partner-submitted data, or when you don't have (or need) Azure API access.

### Prerequisites

- Python 3.10+
- Arize AX account (space ID + API key)

### Quick Start

**1. Export data from Azure Application Insights**

In the Azure portal: Application Insights → Logs → run a KQL query → Export → JSON.

Example KQL:
```kql
customEvents
| where timestamp > ago(7d)
| order by timestamp asc
```

**2. Install**

```bash
cd copilot-insights-bridge
pip install .
```

**3. Configure Arize credentials**

```bash
cp .env.example .env
# Edit .env with your Arize space ID and API key
```

**4. Inspect the data**

```bash
# Default: shows statistics + gap analysis diagnostics
python scripts/import_to_arize.py data.json

# Statistics only
python scripts/import_to_arize.py data.json --stats

# Gap analysis only
python scripts/import_to_arize.py data.json --diagnose
```

**5. Export to Arize**

```bash
source .env
python scripts/import_to_arize.py data.json --export --shift-to-now
```

The `--shift-to-now` flag adjusts timestamps so Arize's span detail panel renders correctly for historical data.

### Supported File Formats

The loader auto-detects four JSON formats:

| Format | Structure | Source |
|---|---|---|
| SDK table | `{"tables": [{"columns": [...], "rows": [...]}]}` | Azure SDK / portal export |
| Azure CLI | `{"tables": [{"rows": [[...], ...]}]}` | `az monitor app-insights query` |
| Event array | `[{"timestamp": ..., "customDimensions": {...}}]` | Custom export tools |
| Flat row-dict | `[{"timestamp": ..., "name": ..., "conversation_id": ...}]` | Synthetic fixtures |

### Command Reference

```bash
python scripts/import_to_arize.py <files> [options]

Options:
  --stats                Show event statistics (counts, time range, channels, topics)
  --diagnose             Run trace reconstruction and report gap analysis
  --export               Push traces to Arize AX (requires BRIDGE_ARIZE_* env vars)
  --shift-to-now         Shift timestamps so the latest span ends at current time
  --include-design-mode  Include test canvas traffic (default: excluded)
```

## Approach 2: Continuous Bridge Service

Best for ongoing production monitoring. Polls Azure Application Insights on a schedule, tracks state via a cursor file, and exports new traces automatically.

### Prerequisites

- Python 3.10+
- Arize AX account (space ID + API key)
- Azure subscription with Application Insights receiving Copilot Studio telemetry
- Azure credentials (`az login`, managed identity, or service principal)

### Copilot Studio Setup

1. Open your agent in Copilot Studio
2. Navigate to **Settings → Advanced → Application Insights**
3. Enter your Application Insights **Connection String**
4. Save and publish

### Quick Start

**Standalone:**

```bash
cd copilot-insights-bridge
pip install .

cp .env.bridge.example .env
# Edit .env with your Azure and Arize credentials

source .env
python -m src.main
```

**Docker:**

```bash
docker build -t copilot-insights-bridge .

docker run --rm \
  -e BRIDGE_APPINSIGHTS_RESOURCE_ID="/subscriptions/.../components/my-app-insights" \
  -e BRIDGE_ARIZE_SPACE_ID="your-space-id" \
  -e BRIDGE_ARIZE_API_KEY="your-api-key" \
  copilot-insights-bridge
```

### Configuration Reference

All settings use environment variables with the `BRIDGE_` prefix:

| Variable | Required | Default | Description |
|---|---|---|---|
| `BRIDGE_ARIZE_SPACE_ID` | Yes | — | Arize AX workspace identifier |
| `BRIDGE_ARIZE_API_KEY` | Yes | — | Arize AX API key |
| `BRIDGE_ARIZE_PROJECT_NAME` | No | `copilot-studio` | Project name in Arize AX |
| `BRIDGE_APPINSIGHTS_RESOURCE_ID` | Yes (bridge only) | — | Azure resource ID for Application Insights |
| `BRIDGE_POLL_INTERVAL_MINUTES` | No | `5` | Polling interval in minutes |
| `BRIDGE_INITIAL_LOOKBACK_HOURS` | No | `24` | Hours to look back on first run |
| `BRIDGE_EXCLUDE_DESIGN_MODE` | No | `true` | Filter out test canvas conversations |
| `BRIDGE_CURSOR_PATH` | No | `.bridge_cursor.json` | Path to the polling cursor state file |
| `BRIDGE_LOG_FORMAT` | No | `text` | `text` or `json` (structured logging) |
| `BRIDGE_MAX_CONSECUTIVE_FAILURES` | No | `5` | Escalate to ERROR log level after N failures |
| `BRIDGE_BACKOFF_BASE_SECONDS` | No | `60` | Exponential backoff base (seconds) |
| `BRIDGE_BACKOFF_MAX_SECONDS` | No | `900` | Backoff cap (15 minutes) |
| `BRIDGE_BUFFER_GRACE_SECONDS` | No | `0` | Set >0 to buffer events and merge cross-cycle arrivals |
| `BRIDGE_HEALTH_CHECK_ENABLED` | No | `true` | Enable `/health` and `/ready` endpoints |
| `BRIDGE_HEALTH_CHECK_PORT` | No | `8080` | Health check HTTP port |

### Health Checks

The bridge exposes two HTTP endpoints (enabled by default on port 8080):

- **`GET /health`** — Returns 200 (healthy/degraded) or 503 (unhealthy) with JSON status
- **`GET /ready`** — Returns 200 after the first successful poll cycle (Kubernetes readiness probe)

### Resilience & Buffering

- **Cursor-based resume**: On restart, the bridge picks up from its last high-water mark — no duplicate processing
- **Exponential backoff**: On Azure connection drops, retries with exponential backoff (base 60s, cap 900s)
- **Event buffering**: Set `BRIDGE_BUFFER_GRACE_SECONDS` > 0 to hold events in memory and merge late-arriving events from the same conversation turn into a single trace

## How It Works

### Pipeline

```
Copilot Studio Agent
    → Azure Application Insights (customEvents table)
        → Extraction (KQL query or file load)
            → Reconstruction (flat events → trace trees)
                → Transformation (OpenInference attribute mapping)
                    → Export (OTLP/gRPC → Arize AX)
```

### Span Hierarchy

Each user message turn produces one trace:

```
AGENT (root, one per user-message turn)
├── CHAIN "BotMessageReceived" (user message)
├── CHAIN (topic execution window)
│   ├── LLM (GenerativeAnswers)
│   ├── LLM (AgentStarted/AgentCompleted pair)
│   ├── TOOL (Action/TopicAction)
│   └── CHAIN "BotMessageSend" (bot response)
└── CHAIN "BotMessageSend" (orphan bot response)
```

## Development

```bash
cd copilot-insights-bridge

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests (168 tests)
pytest tests/ -v

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

## Extending

### Adding new event types

Edit `src/reconstruction/tree_builder.py` — add a new `elif` branch in `_build_topic_span` for your event name.

### Custom attributes

Edit `src/transformation/mapper.py` — add new attribute mappings in `map_attributes`.

### GenAI convention passthrough

The mapper supports `gen_ai.*` attributes from emerging OpenTelemetry GenAI semantic conventions. If your telemetry includes these attributes, they map to OpenInference equivalents automatically.

## Known Limitations

- **Near real-time only**: ~5 min latency (polling interval + App Insights ingestion delay)
- **No LLM model names**: Copilot Studio doesn't expose model names; defaults to `copilot-studio-generative`
- **No token counts**: Not available from Copilot Studio telemetry; Arize estimates its own
- **No sub-agent display names**: Only opaque topic IDs like `auto_agent_Y6JvM.agent.Agent_9eM` — platform limitation
- **Single-point timestamps**: GenerativeAnswers/Action events have zero duration; the enclosing CHAIN span covers the topic window
- **File-based cursor**: Not safe for multi-instance deployments; replace with Redis or database for HA

## Troubleshooting

### No events returned (bridge)

- Verify Copilot Studio is sending telemetry to your Application Insights resource
- Check that `BRIDGE_APPINSIGHTS_RESOURCE_ID` is the full resource ID (not the instrumentation key)
- Ensure Azure credentials have **Reader** or **Log Analytics Reader** permissions
- Try increasing `BRIDGE_INITIAL_LOOKBACK_HOURS`

### Authentication errors (bridge)

- The bridge uses `DefaultAzureCredential`. Ensure at least one method is available: `az login`, environment variables, or managed identity
- Run `az account show` to verify the active subscription

### Spans not appearing in Arize

- Confirm `BRIDGE_ARIZE_SPACE_ID` and `BRIDGE_ARIZE_API_KEY` are correct
- Check logs for OTLP export errors
- Ensure network access to `otlp.arize.com:443`

### Blank span detail panel in Arize (file import)

- Use `--shift-to-now` when exporting historical data. Arize queries a narrow time window around each span's `startTime`; if ingestion time is far from span time, the panel renders blank.

### Design-mode events appearing

- Set `BRIDGE_EXCLUDE_DESIGN_MODE=true` (the default) or omit `--include-design-mode` for the import script
