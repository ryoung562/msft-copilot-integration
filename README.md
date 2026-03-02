# Microsoft Copilot Studio → Arize AX Integration

Bridge service that exports Microsoft Copilot Studio telemetry from Azure Application Insights to Arize AX as OpenTelemetry/OpenInference spans for AI observability.

## What This Does

**Problem**: Microsoft Copilot Studio agents only export telemetry to Azure Application Insights. Arize AX requires OpenTelemetry/OTLP format with OpenInference semantic conventions.

**Solution**: A polling-based bridge service that:

1. **Queries** Azure Application Insights for Copilot Studio events via REST API
2. **Reconstructs** hierarchical conversation traces from flat event streams
3. **Transforms** to OpenInference-formatted OpenTelemetry spans
4. **Exports** to Arize AX via OTLP/gRPC for AI observability

```
┌─────────────────────┐
│ Copilot Studio Agent│
└──────────┬──────────┘
           │ Events
           ▼
┌─────────────────────┐
│ Azure App Insights  │
│  (customEvents)     │
└──────────┬──────────┘
           │ Query (5min poll)
           ▼
┌─────────────────────┐      ┌─────────────────────┐
│  Bridge Service     │──────▶│     Arize AX        │
│  - Reconstruct      │ OTLP  │  (Observability)    │
│  - Transform        │       │                     │
│  - Export           │       │  - Traces           │
└─────────────────────┘       │  - Sessions         │
                              │  - Evaluations      │
                              └─────────────────────┘
```

## Project Structure

```
msft-copilot-integration/
├── README.md
├── CLAUDE.md
├── copilot-insights-bridge/    # The product — source, tests, scripts, Dockerfile
├── partner_data/               # Partner telemetry submissions + collection guides
└── docs/                       # Reference docs (research, session log)
```

## Getting Started

### Prerequisites

- Python 3.12+
- Azure subscription with Application Insights
- Copilot Studio agent configured to send telemetry to App Insights
- Arize AX account with API key
- Azure CLI (`az login`)

### Installation

```bash
cd copilot-insights-bridge
pip install .

# Configure environment
cp .env.development.example .env
# Edit .env with your Azure and Arize credentials

# Run the bridge
python -m src.main
```

### Processing Data Files

```bash
cd copilot-insights-bridge

# Inspect a data file (stats + diagnostics)
python scripts/import_to_arize.py data.json

# Export to Arize
python scripts/import_to_arize.py data.json --export --shift-to-now
```

## Testing

```bash
cd copilot-insights-bridge
pytest tests/ -v          # 116 tests
```

## Documentation

- **[Architecture & Design](copilot-insights-bridge/PLAN.md)** — Implementation plan and decisions
- **[Data Schemas](copilot-insights-bridge/DATA_SCHEMA.md)** — Event structures and mappings
- **[Azure Setup Guide](docs/azure-config-guide.md)** — Azure configuration steps
- **[Collection Guide](partner_data/guides/PARTNER_DATA_COLLECTION_GUIDE.md)** — Send this to partners
- **[Research Documents](docs/)** — Background research and specifications

## Key Technical Decisions

1. **Session ID**: Uses `conversation_id` (not `session_Id`) — the latter is a persistent user/channel ID, not per-conversation. SHA-256 hashing for IDs > 128 chars (Arize limit).

2. **Missing TopicEnd Events**: Many topics never emit TopicEnd. Implicit-close at turn boundary handles this gracefully.

3. **Parent-Child Linking**: Uses SDK-assigned span IDs via `span.get_span_context().span_id`. Deterministic IDs don't work with OTel SDK.

## Known Limitations

### Platform (Microsoft Copilot Studio)
- No LLM model names exposed (defaults to "copilot-studio-generative")
- No token counts or cost metrics available
- Missing TopicEnd events for many topic types

### Implementation
- File-based cursor (not safe for multi-instance deployments)
- ~5 min latency (polling interval + ingestion lag)
- No retry logic for failed exports
