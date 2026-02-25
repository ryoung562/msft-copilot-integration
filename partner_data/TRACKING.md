# Partner Data Tracking

**Last updated**: 2026-02-24

---

## Summary

| Partner | Submissions | Latest | Status | Issues | Exported | Priority |
|---------|-------------|--------|--------|--------|----------|----------|
| _(none yet)_ | - | - | - | - | - | - |

**Total partners**: 0
**Total submissions**: 0
**Validated**: 0
**Exported to Arize**: 0
**Pending review**: 0

---

## Active Partners

_(Partners currently being processed or validated)_

### Example Format (Remove this when adding real partners)

#### partner_example
- **Contact**: john@example.com
- **Company**: Example Corp
- **Use case**: Healthcare support chatbot
- **Channels**: Teams, Web
- **Submissions**: v1 (2026-02-15), v2 (2026-02-20)
- **Status**: ✅ Validated
- **Compatibility**: 95%
- **Issues**:
  - Missing TopicEnd events (10 of 25 topics)
- **Exported**: Yes (2026-02-21)
- **Next steps**: None - validation complete

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
| Missing TopicEnd events | - | Medium | - |
| No locale information | - | Low | - |
| Incomplete conversation boundaries | - | High | - |

---

## Statistics

### Submission Timeline
```
2026-02-24: 0 submissions
```

### Feature Coverage
- **Knowledge search detected**: 0 partners
- **Custom topics**: 0 partners
- **LLM responses**: 0 partners
- **Actions/Tools**: 0 partners

### Data Quality
- **Average compatibility**: 0%
- **Average issues per partner**: 0
- **Most common issue**: N/A

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

- **2026-02-24**: Initial tracking file created
