# Session Handoff Checklist

Use this checklist at the **end of each session** to ensure continuity for the next session.

---

## Before Ending Your Session

### 1. Update Documentation Files

- [ ] **CURRENT_STATUS.md**
  - [ ] Update "Last Updated" date at top
  - [ ] Update "Overall Status" indicator (🟢 🟡 🔴)
  - [ ] Update implementation percentage
  - [ ] Update "Next Steps" section with clear priorities
  - [ ] Note any new decisions required
  - [ ] Update test status (X/X passing)
  - [ ] Update any changed file paths or configurations

- [ ] **SESSION_LOG.md**
  - [ ] Add new session section with date
  - [ ] Document what was done (be specific)
  - [ ] List files modified
  - [ ] Note current state (tests passing, validation results)
  - [ ] Document where you left off
  - [ ] List next steps

- [ ] **MEMORY.md** (in `.claude/projects/.../memory/`)
  - [ ] Update "Current Status" section
  - [ ] Add any critical discoveries or decisions
  - [ ] Update next steps

### 2. Code & Git Status

- [ ] **Check uncommitted changes**
  ```bash
  git status
  git diff
  ```

- [ ] **If changes are ready to commit**:
  - [ ] Run tests: `pytest tests/ -v`
  - [ ] Ensure all tests pass
  - [ ] Write descriptive commit message
  - [ ] Commit changes: `git commit -m "..."`

- [ ] **If changes are NOT ready to commit**:
  - [ ] Document why in CURRENT_STATUS.md
  - [ ] Note which work streams are in progress
  - [ ] List what needs to be completed before commit

### 3. Project State Verification

- [ ] **Tests status**
  ```bash
  pytest tests/ -q
  ```
  - [ ] Note count in CURRENT_STATUS.md

- [ ] **Git status clean or documented**
  ```bash
  git status --short
  ```
  - [ ] List uncommitted files in CURRENT_STATUS.md

- [ ] **Environment files secure**
  - [ ] `.env` file NOT committed to git
  - [ ] `.gitignore` up to date

### 4. Context for Next Session

- [ ] **Decision points clear**
  - [ ] Any blocking decisions documented in CURRENT_STATUS.md
  - [ ] Options laid out with pros/cons
  - [ ] Recommendation provided

- [ ] **Next steps prioritized**
  - [ ] Immediate (🔴)
  - [ ] Short-term (🟡)
  - [ ] Medium-term (🟢)
  - [ ] Long-term (🔵)

- [ ] **Key files reference updated**
  - [ ] All important files listed in CURRENT_STATUS.md
  - [ ] File statuses marked (✅ ⚠️ ❌)

---

## Starting a New Session

### 1. Load Context

- [ ] **Read these files in order**:
  1. [ ] `CURRENT_STATUS.md` - Latest state
  2. [ ] `SESSION_LOG.md` - Recent history
  3. [ ] `PLAN.md` - Architecture & decisions (if needed)
  4. [ ] `DATA_SCHEMA.md` - Data structures (if working on data)

### 2. Verify Environment

- [ ] **Check git status**
  ```bash
  git status
  ```

- [ ] **Check tests**
  ```bash
  pytest tests/ -q
  ```

- [ ] **Check last run**
  ```bash
  cat .bridge_cursor.json
  ```

### 3. Understand Blockers

- [ ] **Read "Decision Required" sections** in CURRENT_STATUS.md
- [ ] **Ask user for decisions** if needed before proceeding
- [ ] **Check "Known Limitations"** for context

### 4. Plan Your Work

- [ ] **Review "Next Steps"** in CURRENT_STATUS.md
- [ ] **Check "Critical Issue"** section for blockers
- [ ] **Confirm approach with user** if unclear

---

## Quick Reference: Key Files to Always Update

| File | When to Update | What to Update |
|------|---------------|----------------|
| `CURRENT_STATUS.md` | **Every session end** | Status, next steps, decisions, test count |
| `SESSION_LOG.md` | **Every session end** | New session entry with date, work done, files modified |
| `MEMORY.md` | **When critical discoveries made** | Current status, key learnings |
| `.gitignore` | **When adding new file types** | Exclude patterns for sensitive/generated files |
| `README.md` | **When user-facing features change** | Installation, usage, configuration docs |
| `PLAN.md` | **When architecture changes** | Implementation steps, design decisions |

---

## Common Mistakes to Avoid

❌ **Don't**: End session with uncommitted, undocumented changes
✅ **Do**: Either commit changes OR document why not in CURRENT_STATUS.md

❌ **Don't**: Leave decisions pending without documentation
✅ **Do**: Document decision points with options and recommendations

❌ **Don't**: Update code without updating tests
✅ **Do**: Add/update tests for any code changes

❌ **Don't**: Forget to update CURRENT_STATUS.md
✅ **Do**: Make it the last file you edit before ending session

❌ **Don't**: Assume next session will remember context
✅ **Do**: Write everything down as if explaining to someone new

---

## Emergency Recovery

If you start a session and find incomplete documentation:

1. **Run git status** to see uncommitted changes
2. **Run pytest** to see test status
3. **Check SESSION_LOG.md** for last completed session
4. **Check git log** for last commit message and date
5. **Ask user** what they were working on last
6. **Reconstruct state** in CURRENT_STATUS.md before proceeding

---

**Remember**: The goal is for any new Claude Code session (or human developer) to pick up the project instantly without manual context seeding. Write documentation as if you'll never see this project again.
