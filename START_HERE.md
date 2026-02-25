# Microsoft Copilot Studio → Arize AX Integration Project

**New Claude Code Session?** Start here for orientation.

---

## Quick Start

1. **Read the current status first**:
   ```
   docs/session-continuity/CURRENT_STATUS.md
   ```
   This file always contains the latest project state, decisions needed, and next steps.

2. **Understand the project**:
   ```
   copilot-insights-bridge/README.md            - User-facing documentation
   copilot-insights-bridge/PLAN.md              - Implementation plan & architecture
   docs/session-continuity/SESSION_LOG.md       - What was done in each session
   docs/research/arize-integration-research.md  - Original research document
   ```

3. **Check git status**:
   ```bash
   cd copilot-insights-bridge
   git status
   ```

---

## Project Structure

```
msft-copilot-integration/
├── START_HERE.md                          ← You are here
│
├── docs/                                  ← All documentation
│   ├── session-continuity/               ← **START HERE** for session handoffs
│   │   ├── CURRENT_STATUS.md             ← Always-current project state
│   │   ├── SESSION_LOG.md                ← Complete session history
│   │   └── SESSION_HANDOFF_CHECKLIST.md  ← Procedures
│   ├── research/                         ← Research & reference materials
│   │   ├── arize-integration-research.md
│   │   ├── copilot-event-types.md
│   │   └── openinference-spec.md
│   └── planning/                         ← Implementation plans
│       └── session-3-completeness-plan.md
│
├── partner_data/                         ← Partner data validation system
│   ├── _inbox/                           ← Drop zone for submissions
│   ├── _templates/                       ← Templates for metadata & reports
│   └── _archive/                         ← Completed validations
│
├── partner_data_guides/                  ← Partner-facing documentation
│   ├── COLLECTION_GUIDE.md               ← Send this to partners
│   └── WORKFLOW.md                       ← Internal workflow
│
└── copilot-insights-bridge/              ← Main implementation
    ├── PLAN.md                           ← Implementation plan
    ├── DATA_SCHEMA.md                    ← Data structure reference
    ├── README.md                         ← User documentation
    ├── pyproject.toml                    ← Python dependencies
    ├── Dockerfile                        ← Container build
    ├── .env.example                      ← Configuration template
    │
    ├── src/                              ← Source code (3,712 lines Python)
    │   ├── extraction/                   ← Azure App Insights query
    │   ├── reconstruction/               ← Trace tree building
    │   ├── transformation/               ← OpenInference mapping
    │   ├── export/                       ← OTel span export to Arize
    │   ├── state/                        ← File-based cursor
    │   ├── config.py                     ← Pydantic settings
    │   └── main.py                       ← Pipeline orchestration
    │
    ├── tests/                            ← 100/100 tests passing
    │   ├── fixtures/                     ← Test data (synthetic + real)
    │   └── test_*.py                     ← Unit + integration tests
    │
    └── scripts/                          ← Utility scripts
        ├── diagnose_gaps.py              ← Offline diagnostic
        ├── export_to_arize.py            ← Ad-hoc export
        └── process_partner_data.py       ← Partner data processing
```

---

## What This Project Does

**Problem**: Microsoft Copilot Studio agents only export telemetry to Azure Application Insights. Arize AX requires OpenTelemetry/OTLP format.

**Solution**: A polling-based bridge service that:
1. Queries Application Insights for Copilot Studio events (via Azure Monitor Query API)
2. Reconstructs hierarchical conversation traces from flat events
3. Transforms to OpenInference-formatted OpenTelemetry spans
4. Exports to Arize AX via OTLP/gRPC

**Architecture**:
```
Copilot Studio Agent
  → Azure Application Insights (customEvents table)
    → Bridge Service (polls every 5 min via REST API)
      → Arize AX OTLP Endpoint (otlp.arize.com:443)
```

---

## Current Project State

- **Implementation**: ~85% complete
- **Core pipeline**: ✅ Fully working
- **Live validation**: ✅ 10 traces exported to Arize AX
- **Tests**: ✅ 100/100 passing
- **Git status**: ⚠️ Uncommitted changes (two work streams need resolution)
- **Production ready**: ❌ Needs operational hardening (monitoring, multi-instance support)

---

## Key Decisions & Discoveries

1. **Session ID confusion** (Session 2): Copilot Studio's `session_Id` is a persistent user/channel identifier, NOT per-conversation. Bridge uses `conversation_id` for Arize session.id.

2. **Missing TopicEnd events** (Session 1-2): Many topics never emit TopicEnd (agents, Greeting, PowerVirtualAgentRoot). Implicit-close at turn boundary handles this.

3. **128-char session ID limit** (Session 2): Arize enforces 128-char max. Copilot conversation IDs can be 131+ chars. SHA-256 hashing applied.

4. **Parent-child span linking** (Session 1): Must use actual SDK-assigned span IDs via `span.get_span_context().span_id`, not deterministic IDs.

5. **OTel SDK import path** (Session 1): `InMemorySpanExporter` is at `opentelemetry.sdk.trace.export.in_memory_span_exporter` (not `.in_memory`).

---

## Configuration

Create `.env` file in `copilot-insights-bridge/`:

```bash
# Azure Application Insights
BRIDGE_APPINSIGHTS_RESOURCE_ID=/subscriptions/<sub>/resourceGroups/<rg>/providers/microsoft.insights/components/<name>

# Arize AX
BRIDGE_ARIZE_SPACE_ID=your-space-id
BRIDGE_ARIZE_API_KEY=your-api-key
BRIDGE_ARIZE_PROJECT_NAME=copilot-studio

# Polling
BRIDGE_POLL_INTERVAL_MINUTES=5
BRIDGE_INITIAL_LOOKBACK_HOURS=24

# Filtering
BRIDGE_EXCLUDE_DESIGN_MODE=true
```

---

## Azure Resources

- **Subscription**: "Arize 1"
- **Resource Group**: `rg-ryoung-5164`
- **Application Insights**: `ryoung-app-insights`

---

## Running the Bridge

```bash
cd copilot-insights-bridge

# Install dependencies
pip install .

# Configure environment
cp .env.example .env
# Edit .env with your values

# Run single cycle
python -m src.main

# Run tests
pytest tests/
```

---

## Important Reminders

1. **Always read `docs/session-continuity/CURRENT_STATUS.md` first** when starting a new session
2. **Update `docs/session-continuity/CURRENT_STATUS.md` at end of session** with latest state and next steps
3. **Update `docs/session-continuity/SESSION_LOG.md`** with what was done in the session
4. **Update `MEMORY.md`** (in `.claude/projects/.../memory/`) with critical discoveries
5. **Commit frequently** to avoid losing work
6. **Check git status** before starting new work to understand uncommitted changes

---

## Questions?

- Read `docs/session-continuity/CURRENT_STATUS.md` for latest state and decisions needed
- Read `docs/session-continuity/SESSION_LOG.md` for detailed history
- Read `copilot-insights-bridge/PLAN.md` for architecture and design decisions
- Read `copilot-insights-bridge/DATA_SCHEMA.md` for data structure reference
- Read `docs/README.md` for complete documentation index
