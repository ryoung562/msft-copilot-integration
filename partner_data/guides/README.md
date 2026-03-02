# Partner Data Guides

This directory contains documentation and tools for collecting and validating Copilot Studio telemetry data from partners.

## Files

### For Partners

**`COLLECTION_GUIDE.md`** - Send this to partners
- Complete step-by-step instructions for exporting data from Azure Application Insights
- Data sanitization scripts to protect sensitive information
- Export methods: Azure CLI (automated) and Azure Portal (manual)
- Sharing instructions and templates

**`COLLECTION_GUIDE.html`** - HTML version for easy viewing
- Generated from the markdown file
- Can be converted to PDF for professional sharing

### For Internal Use

**`WORKFLOW.md`** - Your workflow for processing partner data
- How to process received partner data
- Validation checklists and common scenarios
- Analysis report templates
- Partner communication templates

### Tools

**`generate_pdf.py`** - PDF generation utility
- Converts COLLECTION_GUIDE.html to PDF
- Instructions for manual PDF creation if automated fails

## Quick Start

### Sending to Partners

1. Generate PDF from collection guide:
   ```bash
   # Option 1: Open HTML and print to PDF
   open COLLECTION_GUIDE.html
   # Then: Cmd+P → Save as PDF

   # Option 2: Use generation script
   python generate_pdf.py
   ```

2. Email the PDF to partners with request template (see WORKFLOW.md)

### Processing Partner Data

When you receive data from a partner:

```bash
# Process with the bridge script
cd ../copilot-insights-bridge
python scripts/process_partner_data.py <path-to-partner-file.json>

# See WORKFLOW.md for detailed processing steps
```

## Directory Structure

```
partner_data_guides/
├── README.md                           ← You are here
├── COLLECTION_GUIDE.md                 ← For partners
├── COLLECTION_GUIDE.html               ← Generated HTML
├── WORKFLOW.md                         ← Internal workflow
└── generate_pdf.py                     ← PDF generation tool
```

## Related Files

- **Processing script**: `../copilot-insights-bridge/scripts/process_partner_data.py`
- **Test fixtures**: `../copilot-insights-bridge/tests/fixtures/`
- **Project overview**: `../START_HERE.md`
