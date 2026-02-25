# Documentation Index

This directory contains all project documentation organized by purpose.

## Directory Structure

### 📚 [research/](research/)
Research documents, specifications, and reference materials:
- **arize-integration-research.md** - Original research on Microsoft Copilot Studio → Arize AX integration pathways
- **copilot-event-types.md** - Comprehensive research on Copilot Studio event types in Application Insights
- **openinference-spec.md** - OpenInference semantic conventions specification (reference)

### 📝 [planning/](planning/)
Implementation planning documents and design artifacts:
- **session-3-completeness-plan.md** - Detailed plan for OpenInference completeness improvements (Session 3, interrupted)

### 🔄 [session-continuity/](session-continuity/)
Session handoff documentation for context preservation between Claude Code sessions:
- **CURRENT_STATUS.md** - ⭐ **START HERE** - Current project state, next steps, decision log
- **SESSION_LOG.md** - Detailed history of all sessions with what was done and where we left off
- **SESSION_HANDOFF_CHECKLIST.md** - Step-by-step procedures for ending/starting sessions

## Quick Navigation

### New to the Project?
1. Start with [`session-continuity/CURRENT_STATUS.md`](session-continuity/CURRENT_STATUS.md) for latest state
2. Read [`session-continuity/SESSION_LOG.md`](session-continuity/SESSION_LOG.md) for full history
3. Review [`research/arize-integration-research.md`](research/arize-integration-research.md) for background

### Understanding the Data
- **Data structures**: See `../copilot-insights-bridge/DATA_SCHEMA.md`
- **Event types**: See [`research/copilot-event-types.md`](research/copilot-event-types.md)
- **OpenInference spec**: See [`research/openinference-spec.md`](research/openinference-spec.md)

### Implementation Details
- **Architecture & plan**: See `../copilot-insights-bridge/PLAN.md`
- **User guide**: See `../copilot-insights-bridge/README.md`
- **Session 3 planning**: See [`planning/session-3-completeness-plan.md`](planning/session-3-completeness-plan.md)

## Document Types

| Type | Location | Purpose |
|------|----------|---------|
| Research & Reference | `research/` | Background research, specifications, external docs |
| Planning & Design | `planning/` | Implementation plans, design documents |
| Session Continuity | `session-continuity/` | Project state, history, handoff procedures |
| Technical Docs | `../copilot-insights-bridge/` | Implementation details, API docs, user guides |
| Partner Collaboration | `../partner_data_guides/` | Partner-facing documentation |
| Project Overview | `../START_HERE.md` | Entry point for new sessions |

## Maintenance

### When to Update
- **CURRENT_STATUS.md**: At the end of every session
- **SESSION_LOG.md**: At the end of every session (append new section)
- **Research docs**: When new research is conducted
- **Planning docs**: When creating new implementation plans

### Adding New Documentation
- **Research findings**: Add to `research/` with descriptive filename
- **Implementation plans**: Add to `planning/` with date and topic in filename
- **Session notes**: Update existing session-continuity files (don't create new ones)

## Related Documentation

- **Project entry point**: [`../START_HERE.md`](../START_HERE.md)
- **Implementation**: [`../copilot-insights-bridge/`](../copilot-insights-bridge/)
- **Partner guides**: [`../partner_data_guides/`](../partner_data_guides/)
- **Partner data system**: [`../partner_data/`](../partner_data/)
