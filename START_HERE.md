# Microsoft Copilot Studio → Arize AX Integration Project

**New Claude Code Session?** Start here for orientation.

---

## 🚀 Starting a New Session

### **Quick Start (Recommended)**

Ask Claude to read the current status:

```
Can you read docs/session-continuity/CURRENT_STATUS.md and continue from where we left off?
```

This single file contains everything Claude needs:
- Current implementation status
- What was done recently
- Git and test status
- Decisions required
- Next steps prioritized

### **Alternative Options**

**Option 1: Just the essentials**
```
Read docs/session-continuity/CURRENT_STATUS.md
```

**Option 2: With full context**
```
Read START_HERE.md and docs/session-continuity/CURRENT_STATUS.md
```

**Option 3: Deep dive (for complex work)**
```
Read these files in order:
1. docs/session-continuity/CURRENT_STATUS.md
2. docs/session-continuity/SESSION_LOG.md (recent history)
3. copilot-insights-bridge/PLAN.md (architecture)
```

**Option 4: Emergency recovery**
```
I'm not sure what state the project is in. Can you check
docs/session-continuity/CURRENT_STATUS.md and tell me what's going on?
```

---

## 📚 Key Files to Know

1. **docs/session-continuity/CURRENT_STATUS.md** ⭐
   - **Always read this first** when starting a new session
   - Latest project state, decisions needed, and next steps

2. **docs/session-continuity/SESSION_LOG.md**
   - Complete chronological history of all sessions
   - What was done, where we left off, next steps

3. **copilot-insights-bridge/README.md**
   - User-facing documentation
   - Installation and usage instructions

4. **copilot-insights-bridge/PLAN.md**
   - Implementation plan & architecture
   - Design decisions and rationale

5. **docs/research/arize-integration-research.md**
   - Original research document
   - Background and context

---

## ✅ Before Starting (Optional)

Verify project state:

```bash
# Navigate to project
cd /Users/richardyoung/Documents/msft-copilot-integration

# Check git status
git status

# Verify tests pass (optional)
cd copilot-insights-bridge && pytest tests/ -q
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

## 💡 Session Best Practices

### Starting a New Session
1. **Ask Claude to read `docs/session-continuity/CURRENT_STATUS.md` first**
   - This gives Claude complete context automatically
   - See "Starting a New Session" section above for prompt examples
2. **Don't over-explain** - The documentation has everything Claude needs
3. **Trust the session continuity system** - It's designed for instant context loading

### Ending a Session (For Claude)
1. **Update `docs/session-continuity/CURRENT_STATUS.md`** with latest state and next steps
2. **Update `docs/session-continuity/SESSION_LOG.md`** with what was done
3. **Update `MEMORY.md`** (in `.claude/projects/.../memory/`) with critical discoveries
4. **Commit all changes** before ending
5. **Run session handoff checklist** in `docs/session-continuity/SESSION_HANDOFF_CHECKLIST.md`

### General Tips
- **Commit frequently** to avoid losing work
- **Check git status** before starting new work
- **Run tests** after significant changes
- **Update documentation** as you make architectural decisions

---

## Questions?

- Read `docs/session-continuity/CURRENT_STATUS.md` for latest state and decisions needed
- Read `docs/session-continuity/SESSION_LOG.md` for detailed history
- Read `copilot-insights-bridge/PLAN.md` for architecture and design decisions
- Read `copilot-insights-bridge/DATA_SCHEMA.md` for data structure reference
- Read `docs/README.md` for complete documentation index
