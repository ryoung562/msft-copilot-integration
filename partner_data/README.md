# Partner Data Directory

This directory organizes partner Copilot Studio telemetry submissions for validation and testing.

## Directory Structure

```
partner_data/
├── _inbox/              # Drop new partner submissions here
├── _templates/          # Reusable templates for metadata and reports
├── _archive/            # Completed/archived partner validations
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

### 2. Initialize Partner Directory
```bash
# Create partner directory structure
cd ..
python scripts/partner_data_manager.py init-partner \
  --name "partner_abc" \
  --contact "john@partnerabc.com" \
  --description "Healthcare chatbot - Teams channel"
```

### 3. Process Submission
```bash
# Process the submission
python scripts/partner_data_manager.py process \
  --inbox partner_abc_data.json \
  --partner partner_abc
```

This will:
- Move file from inbox to `partner_abc/data/v1_YYYY-MM-DD.json`
- Run diagnostics
- Generate analysis report
- Update TRACKING.md
- Create symlink to latest version

### 4. Review & Export
```bash
# Review analysis
cat partner_data/partner_abc/analysis/v1_analysis.md

# Export to Arize (when ready)
python scripts/partner_data_manager.py export partner_abc
```

## Manual Process (Without Automation Script)

If `partner_data_manager.py` is not yet built, use manual workflow:

### 1. Create Partner Directory
```bash
mkdir -p partner_data/partner_<name>/{data,analysis,issues}
cp partner_data/_templates/partner_metadata.yaml partner_data/partner_<name>/metadata.yaml
# Edit metadata.yaml with partner details
```

### 2. Process Data
```bash
# Move file from inbox
mv partner_data/_inbox/<file>.json partner_data/partner_<name>/data/v1_$(date +%Y-%m-%d).json

# Run processing
cd copilot-insights-bridge
python scripts/process_partner_data.py ../partner_data/partner_<name>/data/v1_*.json \
  --stats --diagnose > ../partner_data/partner_<name>/analysis/v1_analysis.txt

# Export to Arize
python scripts/process_partner_data.py ../partner_data/partner_<name>/data/v1_*.json --export
```

### 3. Update Tracking
Manually update `TRACKING.md` with partner status.

## Templates

See `_templates/` directory for:
- `partner_metadata.yaml` - Partner information structure
- `analysis_report.md` - Report template
- `validation_checklist.md` - Validation checklist

## Related Documentation

- **Collection Guide**: `../partner_data_guides/COLLECTION_GUIDE.md` - Send this to partners
- **Internal Workflow**: `../partner_data_guides/WORKFLOW.md` - Detailed workflow documentation
- **Processing Script**: `../scripts/process_partner_data.py` - Current processing tool

## Status Tracking

See `TRACKING.md` for master status of all partners.
