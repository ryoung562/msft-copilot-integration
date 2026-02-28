# Partner Data Tracking

**Last updated**: 2026-02-24

---

## Summary

| Partner | Submissions | Latest | Status | Issues | Exported | Priority |
|---------|-------------|--------|--------|--------|----------|----------|
| pg | 1 | v1 (2026-02-27) | ✅ Validated | 0 | 📋 Ready | High |

**Total partners**: 1
**Total submissions**: 1
**Validated**: 1
**Exported to Arize**: 0
**Pending review**: 0

---

## Active Partners

_(Partners currently being processed or validated)_

#### pg
- **Contact**: tasneem.abdalla@arize.com (Internal)
- **Company**: Arize AI
- **Use case**: Test agent for bridge validation
- **Channels**: pva-studio (Test in Bot)
- **Submissions**: v1 (2026-02-27)
- **Status**: ✅ Validated - 100% compatibility
- **Compatibility**: 100%
- **Issues**:
  - ✅ RESOLVED: Timestamp field name (Portal vs CLI export)
    - Bridge updated to handle both formats automatically
- **Exported**: Not yet (ready for export)
- **Next steps**:
  - Update collection guide (clarify test data is acceptable)
  - Export to Arize for visual verification
  - Send validation results to partner

---

## Pending Review

_(Partners with submissions needing review)_

---

## Archived

_(Partners with completed validation - moved to `_archive/`)_

---

## Issue Summary

### Common Issues Across Partners

| Issue | Partners Affected | Severity | Status |
|-------|------------------|----------|--------|
| Timestamp field name (Portal export) | pg | High | ✅ Resolved (bridge updated) |
| Missing TopicEnd events | pg (16/26) | Low | ✅ Expected for system topics |
| Test data compatibility | - | - | ✅ Confirmed compatible |

---

## Statistics

### Submission Timeline
```
2026-02-27: 1 submission (pg v1)
```

### Feature Coverage
- **Knowledge search detected**: 0 partners
- **Custom topics**: 1 partner (pg)
- **LLM responses**: 0 partners
- **Actions/Tools**: 1 partner (pg)

### Data Quality
- **Average compatibility**: 100%
- **Average issues per partner**: 0 (1 issue resolved automatically)
- **Most common issue**: Azure Portal export format (resolved)

---

## Notes

### Partner Onboarding Process
1. Send COLLECTION_GUIDE.pdf (from `partner_data_guides/`)
2. Receive data submission
3. Initialize partner directory
4. Process and validate
5. Export to Arize (if valid)
6. Send analysis report back to partner

### Data Collection Tips
- Request at least 50 events for meaningful analysis
- Prefer recent data (last 30 days)
- Full conversation exports work best
- Include knowledge search if agent uses it

### Quality Standards
- **Minimum compatibility**: 70% for Arize export
- **Required events**: ConversationUpdate, ImBack, Activity
- **Preferred**: TopicEnd coverage > 50%

---

## Quick Commands

```bash
# List all partners
ls -1 partner_data/ | grep -v "^_" | grep -v "TRACKING.md" | grep -v "README.md"

# Check inbox
ls -lh partner_data/_inbox/

# Process inbox (when automation script is ready)
python scripts/partner_data_manager.py process-inbox

# Generate summary report
python scripts/partner_data_manager.py summary
```

---

## Change Log

- **2026-02-27**: First partner submission! PG (Tasneem Abdalla) - 100% validated
  - Bridge updated to handle Azure Portal export format
  - Confirmed test data (DesignMode=True) is fully compatible
- **2026-02-24**: Initial tracking file created
