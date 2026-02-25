# Runtime Data Directory

This directory stores runtime data, exports, and state files. **All contents are gitignored** to prevent committing sensitive or large data files.

## Directory Structure

```
data/
├── state/                    # Runtime state files
│   └── .bridge_cursor.json  # Cursor tracking (last processed timestamp)
├── exports/                  # Data exports and dumps
│   └── *.json               # Azure App Insights exports, sample data
└── partner_submissions/      # Partner data submissions (deprecated)
    └── (use ../partner_data/ instead)
```

## Contents

### state/
Runtime state files for the bridge service:
- **`.bridge_cursor.json`** - Tracks the last processed timestamp for polling
  - Format: `{"last_processed_time": "ISO8601", "last_run_time": "ISO8601", "events_processed": N}`
  - Updated after each successful polling cycle
  - Used to prevent reprocessing events

### exports/
Data dumps and exports for analysis and testing:
- **`app_insights_export.json`** - Sample export from Azure Application Insights
- Ad-hoc exports from manual queries
- Test data dumps for validation

### partner_submissions/
**Note**: This directory is deprecated. Use `../partner_data/` instead for partner data validation workflows.

## Usage

### Bridge Service
The bridge automatically creates and updates files in `data/state/`:
```bash
cd copilot-insights-bridge
python -m src.main  # Creates/updates data/state/.bridge_cursor.json
```

### Manual Data Export
Export App Insights data for testing:
```bash
# Query Azure App Insights
az monitor app-insights query \
  --app ryoung-app-insights \
  --resource-group rg-ryoung-5164 \
  --analytics-query "customEvents | where timestamp > ago(7d)" \
  --output json > data/exports/manual_export_$(date +%Y%m%d).json
```

### Processing Exported Data
Process data dumps through the bridge:
```bash
cd copilot-insights-bridge
python scripts/process_partner_data.py ../data/exports/manual_export_*.json --stats
```

## Gitignore

All data files are excluded from git:
```gitignore
data/
!data/.gitkeep
!data/*/README.md
!data/*/.gitkeep
```

This ensures:
- No sensitive customer data is committed
- No large JSON exports bloat the repository
- State files remain local to each environment

## Backup & Recovery

### Backing Up State
To preserve cursor state between environments:
```bash
# Backup
cp data/state/.bridge_cursor.json .bridge_cursor.backup.json

# Restore
cp .bridge_cursor.backup.json data/state/.bridge_cursor.json
```

### Resetting State
To start fresh (reprocess all events):
```bash
rm data/state/.bridge_cursor.json
# Next run will use BRIDGE_INITIAL_LOOKBACK_HOURS from config
```

## Multi-Instance Deployment

**Warning**: The file-based cursor in `data/state/` is **NOT safe for multi-instance deployments**.

For production with multiple instances:
- Replace file-based cursor with Redis or Azure Blob Storage
- See `docs/planning/` for production deployment plans

## Related Directories

- **`partner_data/`** - Partner data validation system (use this for partner submissions)
- **`copilot-insights-bridge/tests/fixtures/`** - Test fixtures (committed to git)
- **`docs/research/`** - Sample data documentation and schemas
