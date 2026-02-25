# Inbox - Partner Data Submissions

Drop new partner data files here for processing.

## Naming Convention

Use descriptive filenames:
- `partner_<name>_YYYY-MM-DD.json` - Initial submission
- `partner_<name>_v2_YYYY-MM-DD.json` - Follow-up submission
- `partner_<name>_<description>.json` - Descriptive variant

Examples:
- `partner_abc_healthcare_2026-02-24.json`
- `partner_xyz_v2_2026-02-25.json`

## Processing Workflow

### Automated (Recommended)
```bash
# Validate all files in inbox
python scripts/partner_data_manager.py validate-inbox

# Process all valid files
python scripts/partner_data_manager.py process-inbox
```

### Manual
```bash
# Process single file
python scripts/process_partner_data.py partner_data/_inbox/<file>.json --stats --diagnose

# Then move to appropriate partner directory
```

## What Happens After Processing

Files are automatically:
1. Moved from `_inbox/` to `partner_<name>/data/`
2. Renamed with version number (v1, v2, etc.)
3. Analyzed and reports generated
4. Tracked in `../TRACKING.md`

## Validation

Before processing, files should:
- Be valid JSON format
- Contain Azure Application Insights events
- Have `customDimensions` with Copilot Studio fields
- Include conversation_id and conversationUpdate events

Use the validation command to check:
```bash
python scripts/partner_data_manager.py validate-inbox
```

## Cleanup

After processing, inbox files are either:
- Moved to partner directories (success)
- Left in inbox with error report (failure)

To clean up processed files:
```bash
python scripts/partner_data_manager.py cleanup-inbox
```
