# Microsoft Copilot Studio → Arize AX Integration

Export Microsoft Copilot Studio telemetry to Arize AX as OpenTelemetry/OpenInference spans for AI observability.

## What This Does

**Problem**: Microsoft Copilot Studio agents only export telemetry to Azure Application Insights. Arize AX requires OpenTelemetry/OTLP format with OpenInference semantic conventions.

**Solution**: Two approaches to get Copilot Studio data into Arize AX — both share the same reconstruction and export pipeline:

```
┌─────────────────────┐
│ Copilot Studio Agent│
└──────────┬──────────┘
           │ Events
           ▼
┌─────────────────────┐
│ Azure App Insights  │
│  (customEvents)     │
└──────┬────────┬─────┘
       │        │
   ┌───┘        └──────────────┐
   │ Export JSON               │ REST API (5-min poll)
   ▼                           ▼
┌──────────────┐     ┌──────────────────┐      ┌─────────────────┐
│ Import Script│     │  Bridge Service  │──────▶│    Arize AX     │
│ (one-time)   │────▶│  (continuous)    │ OTLP  │ (Observability) │
└──────────────┘     └──────────────────┘       └─────────────────┘
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

### Approach 1: File Export & Import

Best for one-time analysis, partner data, or when you don't need Azure API access.

```bash
cd copilot-insights-bridge
pip install .
cp .env.example .env          # Add your Arize credentials

# Inspect a data file
python scripts/import_to_arize.py data.json

# Export to Arize
source .env
python scripts/import_to_arize.py data.json --export --shift-to-now
```

### Approach 2: Continuous Bridge Service

Best for ongoing production monitoring with automated polling.

```bash
cd copilot-insights-bridge
pip install .
cp .env.bridge.example .env   # Add your Azure + Arize credentials

source .env
python -m src.main
```

See [copilot-insights-bridge/README.md](copilot-insights-bridge/README.md) for full documentation of both approaches.

## Testing

```bash
cd copilot-insights-bridge
pytest tests/ -v          # 168 tests
```

## Documentation

- **[Full README](copilot-insights-bridge/README.md)** — Both approaches, configuration, troubleshooting
- **[Architecture & Design](copilot-insights-bridge/PLAN.md)** — Implementation plan and decisions
- **[Data Schemas](copilot-insights-bridge/DATA_SCHEMA.md)** — Event structures and mappings
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
