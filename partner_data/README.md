# Partner Data Directory

This directory organizes partner Copilot Studio telemetry submissions for validation and testing.

## Directory Structure

```
partner_data/
├── _inbox/              # Drop new partner submissions here
├── _templates/          # Reusable templates for metadata and reports
├── _archive/            # Completed/archived partner validations
├── guides/              # Partner-facing collection guides and workflow docs
├── partner_<name>/      # Per-partner directories (created as needed)
│   ├── metadata.yaml    # Partner information and submission history
│   ├── data/            # All data submissions (versioned)
│   ├── analysis/        # Analysis results per submission
│   ├── issues/          # Tracked issues and findings
│   └── notes.md         # Free-form notes
└── TRACKING.md          # Master tracking log (all partners)
```

## Quick Workflow

### 1. Receive Partner Data
```bash
# Save partner submission to inbox
mv ~/Downloads/partner_abc_data.json partner_data/_inbox/
```

### 2. Create Partner Directory
```bash
mkdir -p partner_data/partner_<name>/{data,analysis,issues}
cp partner_data/_templates/partner_metadata.yaml partner_data/partner_<name>/metadata.yaml
# Edit metadata.yaml with partner details
```

### 3. Process Submission
```bash
# Move file from inbox
mv partner_data/_inbox/<file>.json partner_data/partner_<name>/data/v1_$(date +%Y-%m-%d).json

# Run diagnostics (from copilot-insights-bridge/)
cd copilot-insights-bridge
python scripts/import_to_arize.py ../partner_data/partner_<name>/data/v1_*.json

# Export to Arize
python scripts/import_to_arize.py ../partner_data/partner_<name>/data/v1_*.json --export --shift-to-now
```

### 4. Update Tracking
Manually update `TRACKING.md` with partner status.

## Templates

See `_templates/` directory for:
- `partner_metadata.yaml` - Partner information structure
- `analysis_report.md` - Report template
- `validation_checklist.md` - Validation checklist

## Related Documentation

- **Collection Guide**: `guides/PARTNER_DATA_COLLECTION_GUIDE.md` - Send this to partners
- **Internal Workflow**: `guides/PARTNER_DATA_WORKFLOW.md` - Detailed workflow documentation
- **Processing Tool**: `../copilot-insights-bridge/scripts/import_to_arize.py` - Import and export tool

## Status Tracking

See `TRACKING.md` for master status of all partners.
