# Copilot Studio → Arize AX Bridge

A bridge service that exports Microsoft Copilot Studio telemetry from Azure Application Insights to Arize AX via OTLP, enabling full observability of Copilot Studio agents in Arize.

## Architecture

```
Copilot Studio Agent
    → Azure Application Insights (customEvents table)
        → Bridge Service (polls every ~5 min via REST API)
            → Arize AX OTLP Endpoint (otlp.arize.com:443)
```

The bridge reconstructs hierarchical trace trees from flat Application Insights events and maps them to [OpenInference](https://github.com/Arize-ai/openinference) spans:

| App Insights Event | OpenInference Span Kind |
|---|---|
| Conversation (group) | **AGENT** — root span covering the full conversation |
| TopicStart / TopicEnd | **CHAIN** — one child span per topic |
| GenerativeAnswers | **LLM** — generative AI call within a topic |
| Action | **TOOL** — action/connector invocation within a topic |

## Prerequisites

- **Azure subscription** with an Application Insights resource receiving Copilot Studio telemetry
- **Arize AX account** with a space ID and API key
- **Python 3.10+** (for standalone) or **Docker** (for containerized)
- Azure credentials configured (Azure CLI login, managed identity, or service principal)

## Copilot Studio Setup

1. Open your Copilot Studio agent in the Power Platform admin center
2. Navigate to **Settings → Advanced → Application Insights**
3. Enter your Application Insights **Connection String**
4. Save and publish the agent

Telemetry will start flowing to the `customEvents` table within minutes.

## Configuration

All settings use environment variables with the `BRIDGE_` prefix:

| Variable | Required | Default | Description |
|---|---|---|---|
| `BRIDGE_APPINSIGHTS_RESOURCE_ID` | Yes | — | Azure resource ID for the Application Insights instance |
| `BRIDGE_ARIZE_SPACE_ID` | Yes | — | Arize AX workspace identifier |
| `BRIDGE_ARIZE_API_KEY` | Yes | — | Arize AX API key |
| `BRIDGE_ARIZE_PROJECT_NAME` | No | `copilot-studio` | Project name in Arize AX |
| `BRIDGE_POLL_INTERVAL_MINUTES` | No | `5` | Polling interval in minutes |
| `BRIDGE_INITIAL_LOOKBACK_HOURS` | No | `24` | Hours to look back on first run |
| `BRIDGE_EXCLUDE_DESIGN_MODE` | No | `true` | Filter out test canvas conversations |
| `BRIDGE_CURSOR_PATH` | No | `.bridge_cursor.json` | Path to the polling cursor state file |

## Quick Start

### Standalone

```bash
# Install
pip install .

# Configure (copy .env.example and fill in values)
cp .env.example .env
source .env  # or export variables individually

# Run
python -m src.main
```

### Docker

```bash
# Build
docker build -t copilot-insights-bridge .

# Run
docker run --rm \
  -e BRIDGE_APPINSIGHTS_RESOURCE_ID="/subscriptions/.../components/my-app-insights" \
  -e BRIDGE_ARIZE_SPACE_ID="your-space-id" \
  -e BRIDGE_ARIZE_API_KEY="your-api-key" \
  -e BRIDGE_ARIZE_PROJECT_NAME="copilot-studio" \
  copilot-insights-bridge
```

For Azure authentication in Docker, mount your Azure credentials or configure a service principal:

```bash
docker run --rm \
  -e AZURE_CLIENT_ID="..." \
  -e AZURE_CLIENT_SECRET="..." \
  -e AZURE_TENANT_ID="..." \
  -e BRIDGE_APPINSIGHTS_RESOURCE_ID="..." \
  -e BRIDGE_ARIZE_SPACE_ID="..." \
  -e BRIDGE_ARIZE_API_KEY="..." \
  copilot-insights-bridge
```

## How It Works

1. **Poll**: The bridge queries the Application Insights `customEvents` table via the `azure-monitor-query` SDK using KQL, fetching events since the last high-water mark
2. **Group**: Events are grouped by `conversationId` to form logical conversations
3. **Reconstruct**: Within each conversation, `TopicStart`/`TopicEnd` pairs define topic windows; events within those windows become child spans (LLM for GenerativeAnswers, TOOL for Actions)
4. **Transform**: Each span node is mapped to OpenInference attributes (`openinference.span.kind`, `input.value`, `output.value`, `session.id`, etc.)
5. **Export**: Spans are exported via OTLP gRPC to Arize AX with deterministic trace IDs derived from conversation IDs
6. **Cursor**: A file-based cursor (`.bridge_cursor.json`) tracks the last processed timestamp to avoid reprocessing

## Extending

### Adding new event types

Edit `src/reconstruction/tree_builder.py` — in the `_build_topic_span` method, add a new `elif` branch for your event name and create the appropriate `SpanNode`.

### Custom attributes

Edit `src/transformation/mapper.py` — add new attribute mappings in the `map_attributes` method.

### GenAI convention passthrough

The mapper supports `gen_ai.*` attributes from the emerging OpenTelemetry GenAI semantic conventions. If your App Insights telemetry includes these attributes (e.g., from the Agent 365 SDK), they will be mapped to their OpenInference equivalents automatically.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

## Known Limitations

- **Near real-time only**: ~5 min latency due to polling interval + App Insights ingestion delay (includes a 2-minute safety buffer for ingestion lag)
- **LLM model name**: Not available in Copilot Studio telemetry; defaults to `copilot-studio-generative`. Overridden automatically if `gen_ai.request.model` is present in raw telemetry.
- **Token counts and costs**: Not available from Copilot Studio telemetry. Populated automatically if `gen_ai.usage.*` fields are present.
- **Single-point timestamps**: GenerativeAnswers and Action events have a single timestamp (no duration); their spans have zero duration. The enclosing CHAIN span covers the full topic window.
- **Parent-child accuracy**: Depends on `TopicStart`/`TopicEnd` pairs being emitted; orphan events fall back to the root AGENT span
- **File-based cursor**: The cursor is a local JSON file. For multi-instance deployments, replace with a shared store (e.g., Redis, database).
- **App Insights API rate limits**: The REST API supports ~100 queries/minute; the default 5-minute polling interval is well within limits

## Troubleshooting

### No events returned

- Verify that Copilot Studio is configured to send telemetry to the correct Application Insights resource.
- Check that `BRIDGE_APPINSIGHTS_RESOURCE_ID` is the full resource ID (not just the instrumentation key). It should look like `/subscriptions/<sub>/resourceGroups/<rg>/providers/microsoft.insights/components/<name>`.
- Ensure your Azure credentials have **Reader** or **Log Analytics Reader** permissions on the Application Insights resource.
- Try increasing `BRIDGE_INITIAL_LOOKBACK_HOURS` to widen the initial query window.

### Authentication errors

- The bridge uses `DefaultAzureCredential`. Ensure at least one credential method is available: `az login` (local dev), environment variables (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`), or managed identity (Azure-hosted).
- Run `az account show` to verify the active subscription.

### Spans not appearing in Arize AX

- Confirm `BRIDGE_ARIZE_SPACE_ID` and `BRIDGE_ARIZE_API_KEY` are correct.
- Check logs for OTLP export errors (the bridge logs at INFO level by default).
- Ensure the bridge can reach `otlp.arize.com:443` (check firewall/proxy rules).
- Spans are batched by the OpenTelemetry SDK; there may be a short delay before they appear in the Arize UI.

### Duplicate traces after restart

- If `.bridge_cursor.json` is deleted, the bridge re-processes the lookback window. Trace IDs are deterministic (derived from conversationId), so Arize AX will deduplicate spans with identical trace and span IDs.
- To force a clean re-import, delete `.bridge_cursor.json` and set `BRIDGE_INITIAL_LOOKBACK_HOURS` to the desired window.

### Design-mode events appearing

- Set `BRIDGE_EXCLUDE_DESIGN_MODE=true` (the default) to filter out events generated from the Copilot Studio test canvas.
