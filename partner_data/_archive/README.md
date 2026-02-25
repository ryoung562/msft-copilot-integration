# Archive - Completed Partner Validations

This directory stores completed partner validation projects that are no longer actively being worked on.

## When to Archive

Move a partner directory here when:
- Validation is complete and partner has been notified
- Data has been successfully exported to Arize
- No further action items remain
- Partner is no longer actively submitting data

## Archive Structure

Archived partners maintain their original structure:
```
_archive/
└── partner_name/
    ├── metadata.yaml
    ├── data/
    ├── analysis/
    ├── issues/
    └── notes.md
```

## Archive Process

### Automated (When Script is Ready)
```bash
python scripts/partner_data_manager.py archive partner_name
```

### Manual
```bash
# Move partner directory to archive
mv partner_data/partner_name partner_data/_archive/

# Update TRACKING.md to reflect archived status
# (Move entry from "Active Partners" to "Archived" section)
```

## Retrieval

To retrieve an archived partner for follow-up work:
```bash
# Move back from archive
mv partner_data/_archive/partner_name partner_data/

# Update TRACKING.md accordingly
```

## Retention

Archived partner data should be:
- Kept for at least 90 days after archival
- Reviewed periodically for deletion (if no longer needed)
- Backed up if containing valuable reference data

## Notes

- Archived partners are excluded from batch processing commands
- Archive does not get exported to Arize automatically
- Consider creating a summary document before archiving for quick reference
