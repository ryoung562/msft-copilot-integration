# Session Continuity Documentation

This directory contains documentation specifically designed to preserve context and state between Claude Code sessions.

## Purpose

These files enable any Claude Code session to:
1. **Quickly understand** the current project state
2. **Pick up exactly** where the previous session left off
3. **Avoid repeating** work or mistakes from earlier sessions
4. **Maintain consistency** across multiple development sessions

## Documents

### ⭐ [CURRENT_STATUS.md](CURRENT_STATUS.md) - START HERE
**Always-current snapshot** of project state, decisions, and next steps.

**Contents**:
- Quick start guide for new sessions
- Implementation status (percentage complete, what works, what doesn't)
- Recent decisions and their rationale
- Current git status and commit history
- Environment configuration (Azure, Arize)
- Known limitations (platform and implementation)
- **Next steps** prioritized by urgency
- Test status and coverage
- Key files reference table

**Update frequency**: End of every session (REQUIRED)

**When to read**:
- **ALWAYS** read this first when starting a new session
- Before making architectural decisions
- When unsure what to work on next

---

### [SESSION_LOG.md](SESSION_LOG.md) - Detailed History
**Chronological log** of all sessions with complete context of what was done.

**Contents**:
- Session-by-session breakdown (Session 1, Session 2, Session 3, etc.)
- What was done in each session (step-by-step)
- Files created/modified
- Current state at end of session
- Where we left off (unfinished work, blockers)
- Next steps (what should happen next)
- Potential future work ideas

**Update frequency**: End of every session (REQUIRED - append new section)

**When to read**:
- Understanding project history
- Finding when/why a decision was made
- Debugging: "When did this break?"
- Learning from past sessions

---

### [SESSION_HANDOFF_CHECKLIST.md](SESSION_HANDOFF_CHECKLIST.md) - Procedures
**Step-by-step procedures** for ending and starting sessions.

**Contents**:
- **Ending a session**: Checklist of what to do before leaving
  - Commit work in progress
  - Update CURRENT_STATUS.md
  - Update SESSION_LOG.md
  - Document blockers and next steps
  - Update MEMORY.md (in ~/.claude)
- **Starting a session**: Checklist of what to do when beginning
  - Read CURRENT_STATUS.md first
  - Check git status
  - Verify environment
  - Review next steps
- **Key files reference**: Table of critical files and their purposes
- **Common mistakes**: What to avoid (e.g., reading old docs, missing updates)

**Update frequency**: Rarely (only when process changes)

**When to read**:
- At the start of every session (quick scan)
- At the end of every session (follow checklist)
- When onboarding to the project

---

## Usage Workflow

### Starting a New Session
```bash
# 1. Navigate to project
cd /Users/richardyoung/Documents/msft-copilot-integration

# 2. Read current status (ALWAYS DO THIS FIRST)
cat docs/session-continuity/CURRENT_STATUS.md

# 3. Check git status
git status
git log --oneline -5

# 4. Verify environment still works
cd copilot-insights-bridge
pytest tests/ -q  # Quick test
```

### Ending a Session
```bash
# 1. Commit all work
git status
git add .
git commit -m "descriptive message"

# 2. Update CURRENT_STATUS.md
# - Update "Last Updated" date
# - Update implementation status if changed
# - Add any new decisions or blockers
# - Update "Next Steps" section

# 3. Update SESSION_LOG.md
# - Add new section for this session
# - Document what was done
# - Document current state
# - Document next steps

# 4. Update MEMORY.md (in ~/.claude)
# - Update current status summary
# - Add any new patterns or learnings

# 5. Final verification
git status  # Should be clean
```

## Document Relationships

```
START_HERE.md (project root)
    ↓ points to
CURRENT_STATUS.md (you are here)
    ↓ references
SESSION_LOG.md (for history)
    ↓ documents sessions using
SESSION_HANDOFF_CHECKLIST.md (procedures)
```

## Best Practices

### For CURRENT_STATUS.md
- ✅ **Always update at session end** (non-negotiable)
- ✅ Keep "Next Steps" prioritized and actionable
- ✅ Document decisions with rationale
- ✅ Update percentages realistically
- ❌ Don't let it get stale (check "Last Updated" date)
- ❌ Don't remove historical decisions (keep "Recent Resolution" section)

### For SESSION_LOG.md
- ✅ Append new section at end (don't modify old sessions)
- ✅ Be specific about files modified
- ✅ Document "Where we left off" clearly
- ✅ Include commit hashes for traceability
- ❌ Don't be vague ("fixed some bugs")
- ❌ Don't duplicate info from CURRENT_STATUS (link to it instead)

### For SESSION_HANDOFF_CHECKLIST.md
- ✅ Follow the checklist at every session boundary
- ✅ Update if you discover missing steps
- ❌ Don't skip steps (even if they seem obvious)

## Maintenance

These files are **critical infrastructure** for multi-session development. Treat updates as mandatory, not optional.

### Update Priority
1. **High**: CURRENT_STATUS.md (every session, non-negotiable)
2. **High**: SESSION_LOG.md (every session, append only)
3. **Medium**: SESSION_HANDOFF_CHECKLIST.md (when process changes)
4. **Medium**: MEMORY.md in ~/.claude (every session)

### Quality Checks
- Is "Last Updated" date current?
- Do "Next Steps" match actual state?
- Are git commit hashes correct?
- Are file paths still accurate?
- Is implementation percentage realistic?

## Related Documentation

- **Project entry**: `../../START_HERE.md`
- **Implementation plan**: `../../copilot-insights-bridge/PLAN.md`
- **Data schema**: `../../copilot-insights-bridge/DATA_SCHEMA.md`
- **Memory file**: `~/.claude/projects/.../memory/MEMORY.md`
- **Research**: `../research/`
- **Planning**: `../planning/`
