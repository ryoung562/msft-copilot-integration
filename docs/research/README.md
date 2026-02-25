# Research Documentation

This directory contains research documents, specifications, and reference materials gathered during project development.

## Documents

### [arize-integration-research.md](arize-integration-research.md)
**Original research document** (converted from DOCX) that investigated integration pathways for connecting Microsoft Copilot Studio to Arize AX.

**Contents**:
- Three integration pathway options (SDK in Copilot, Power Automate, App Insights Bridge)
- Detailed analysis of Pathway C (App Insights → OTLP Bridge) - the chosen approach
- Architecture diagrams and data flow
- Implementation considerations
- OpenInference semantic conventions mapping

**When to reference**: Understanding project background, architectural decisions, why this approach was chosen

---

### [copilot-event-types.md](copilot-event-types.md)
**Comprehensive research** on Microsoft Copilot Studio event types captured in Azure Application Insights.

**Contents**:
- Complete inventory of all App Insights event names
- `customDimensions` field catalog with descriptions
- KQL query patterns for extracting telemetry
- Telemetry coverage analysis for Copilot features
- Feature-to-event mapping for all 12+ Copilot Studio capabilities

**When to reference**: Understanding event structure, writing KQL queries, mapping new features

---

### [openinference-spec.md](openinference-spec.md)
**Reference specification** for OpenInference semantic conventions (from Arize documentation).

**Contents**:
- Span kinds: AGENT, CHAIN, LLM, TOOL, RETRIEVER, EMBEDDING, GUARDRAIL, EVALUATOR, RERANKER
- Required and optional attributes for each span kind
- Session and user attribute conventions
- Metadata and tag recommendations
- Examples of properly formatted spans

**When to reference**: Implementing OpenInference mappings, ensuring spec compliance, adding new span attributes

---

## Research Process

### How Research Was Conducted
1. **Session 1**: Manual review of Arize documentation and Microsoft docs
2. **Session 2**: Parallel agent research using Claude Code explore agents
   - Agent 1: Deep-dive on telemetry and App Insights
   - Agent 2: Feature inventory and telemetry coverage mapping
3. **Session 3**: Gap analysis between captured data and OpenInference spec

### Research Artifacts Created
- Session 1: `arize-integration-research.md`
- Session 2: `copilot-event-types.md` (60+ pages of findings)
- Session 3: Gap analysis (in `../planning/session-3-completeness-plan.md`)

## Adding New Research

When conducting new research:
1. Create a new markdown file with descriptive name: `<topic>-research-YYYY-MM-DD.md`
2. Include date, researcher, methodology, findings, and references
3. Update this README with a new section describing the document
4. Link from relevant documentation (PLAN.md, CURRENT_STATUS.md, etc.)

## Related Documentation

- **Implementation plan**: `../copilot-insights-bridge/PLAN.md` (incorporates research findings)
- **Data schema**: `../copilot-insights-bridge/DATA_SCHEMA.md` (derived from copilot-event-types.md)
- **Session history**: `../session-continuity/SESSION_LOG.md` (documents research sessions)
