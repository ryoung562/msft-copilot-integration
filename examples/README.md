# Examples Directory

This directory contains example configurations, sample data, and expected outputs to help users understand and configure the bridge service.

## Directory Structure

```
examples/
├── env/                           # Configuration examples
│   ├── .env.development.example   # Development configuration
│   ├── .env.production.example    # Production configuration
│   └── azure-config-guide.md      # Azure setup guide
├── data/                          # Sample data files
│   ├── sample-conversation.json   # Example Copilot conversation
│   ├── sample-trace-tree.json     # Reconstructed trace tree
│   └── sample-openinference-spans.json  # OpenInference spans
└── outputs/                       # Expected outputs
    └── arize-export-example.json  # Example Arize export
```

## Configuration Examples

### Development Configuration
See [`env/.env.development.example`](env/.env.development.example) for a development environment setup with:
- Faster polling interval (1 minute)
- Design mode events included
- Shorter lookback window

### Production Configuration
See [`env/.env.production.example`](env/.env.production.example) for a production environment setup with:
- Standard polling interval (5 minutes)
- Design mode events excluded
- Longer lookback window

### Azure Setup
See [`env/azure-config-guide.md`](env/azure-config-guide.md) for step-by-step instructions on:
- Creating Azure Application Insights resource
- Configuring Copilot Studio to send telemetry
- Finding resource IDs and connection strings
- Setting up Azure credentials

## Sample Data

### Conversation Example
[`data/sample-conversation.json`](data/sample-conversation.json) - A complete Copilot Studio conversation showing:
- User messages
- Bot responses
- Topic triggers
- Knowledge search (generative answers)
- System topics

**Use for**: Understanding event structure, testing extraction logic

### Trace Tree Example
[`data/sample-trace-tree.json`](data/sample-trace-tree.json) - Reconstructed trace tree showing:
- Hierarchical span relationships
- Parent-child linking
- Span types (AGENT, CHAIN, LLM, TOOL)
- Timestamps and durations

**Use for**: Understanding reconstruction logic, debugging tree building

### OpenInference Spans Example
[`data/sample-openinference-spans.json`](data/sample-openinference-spans.json) - Transformed spans showing:
- OpenInference semantic conventions
- Required and optional attributes
- Metadata and tags
- Session and user information

**Use for**: Understanding transformation logic, validating against spec

## Expected Outputs

### Arize Export Example
[`outputs/arize-export-example.json`](outputs/arize-export-example.json) - Example OTLP export showing:
- Resource attributes
- Span format
- Trace structure
- What Arize receives

**Use for**: Understanding export format, debugging Arize integration

## Usage

### Quick Start with Examples
```bash
# Copy development config
cp examples/env/.env.development.example copilot-insights-bridge/.env

# Edit with your values
vi copilot-insights-bridge/.env

# Test with sample data
cd copilot-insights-bridge
python scripts/process_partner_data.py ../examples/data/sample-conversation.json --stats
```

### Testing Pipeline Stages
```bash
# Test extraction (mock Azure query)
python -c "from src.extraction.client import *; ..."

# Test reconstruction
python scripts/process_partner_data.py ../examples/data/sample-conversation.json --diagnose

# Test transformation
python scripts/process_partner_data.py ../examples/data/sample-conversation.json --export
```

### Validating Your Configuration
```bash
# Check Azure connectivity
az monitor app-insights query \
  --app <your-app-name> \
  --resource-group <your-rg> \
  --analytics-query "customEvents | take 1" \
  --output json

# Test Arize export (dry run)
# (Future: add --dry-run flag to bridge)
```

## Creating Your Own Examples

### Export Real Data for Testing
```bash
# Export from your App Insights
az monitor app-insights query \
  --app <your-app> \
  --resource-group <your-rg> \
  --analytics-query "customEvents | where timestamp > ago(1h)" \
  --output json > examples/data/my-sample-$(date +%Y%m%d).json

# Sanitize sensitive data
python scripts/sanitize_export.py examples/data/my-sample-*.json
```

### Document Your Configuration
1. Copy your working `.env` to `examples/env/.env.<name>.example`
2. Replace sensitive values with placeholders
3. Add comments explaining each setting
4. Update this README with description

## Related Documentation

- **Configuration reference**: `../copilot-insights-bridge/README.md`
- **Azure setup**: `examples/env/azure-config-guide.md`
- **Data schemas**: `../copilot-insights-bridge/DATA_SCHEMA.md`
- **Testing guide**: `../copilot-insights-bridge/tests/README.md` (if exists)

## Contributing Examples

If you have useful configurations or sample data:
1. Sanitize all sensitive information
2. Add to appropriate subdirectory
3. Update this README with description
4. Include comments explaining the example
