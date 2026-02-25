# Partner Data Validation Workflow

This document describes how to work with partner-provided Copilot Studio telemetry data to validate the bridge across different use cases.

---

## Quick Start

### 1. Send Collection Guide to Partners

Send partners the `PARTNER_DATA_COLLECTION_GUIDE.md` file with instructions on:
- How to query their Application Insights data
- How to sanitize sensitive information
- What format to provide (JSON)
- How to share securely

### 2. Receive Partner Data

Partners will send you a JSON file, typically named:
- `copilot_events_sample_sanitized.json`
- Or similar descriptive name

### 3. Process the Data

Use the `process_partner_data.py` script to validate:

```bash
cd copilot-insights-bridge

# Show statistics and run diagnostics
python scripts/process_partner_data.py ../partner_data/partner_name_data.json

# Just statistics
python scripts/process_partner_data.py ../partner_data/partner_name_data.json --stats

# Just diagnostics (gap analysis)
python scripts/process_partner_data.py ../partner_data/partner_name_data.json --diagnose

# Export to Arize (requires .env configuration)
python scripts/process_partner_data.py ../partner_data/partner_name_data.json --export
```

### 4. Analyze Results

Review the output for:
- Event type distribution
- Trace structure compatibility
- Feature detection (knowledge search, system topics, etc.)
- Any errors or warnings

### 5. Report Back to Partner

Share findings with the partner:
- Confirmation that data was processed successfully
- Any issues discovered
- Recommendations for configuration improvements (if any)

---

## Detailed Workflow

### Step 1: Organize Partner Data

Create a directory structure:

```
msft-copilot-integration/
├── partner_data/
│   ├── partner_a/
│   │   ├── sanitized_data.json
│   │   ├── notes.txt
│   │   └── analysis_results.txt
│   ├── partner_b/
│   │   ├── sanitized_data.json
│   │   └── notes.txt
│   └── README.md
```

### Step 2: Initial Validation

Run statistics to understand the data:

```bash
python scripts/process_partner_data.py partner_data/partner_a/sanitized_data.json --stats
```

**What to check:**
- ✅ Event count (50-200 is ideal, more is fine)
- ✅ Date range (should be recent)
- ✅ Event type distribution (should have variety)
- ✅ Production vs design mode (should be mostly production)
- ✅ Conversation count (at least 2-3)
- ⚠️ Any warnings about missing fields

### Step 3: Gap Analysis

Run diagnostics to check feature detection:

```bash
python scripts/process_partner_data.py partner_data/partner_a/sanitized_data.json --diagnose
```

**What to check:**
- ✅ Traces built successfully
- ✅ Knowledge search detection working
- ✅ System topic detection working
- ✅ Locale extraction working
- ✅ Tree structure looks correct
- ⚠️ Any empty traces (would be filtered)
- ⚠️ Any unusual patterns

### Step 4: Test Processing

Create a test fixture from partner data:

```bash
# Save processed events to fixture file
python scripts/process_partner_data.py \
  partner_data/partner_a/sanitized_data.json \
  --output tests/fixtures/partner_a_sample.json
```

Then run tests to ensure compatibility:

```bash
# Add partner data to test suite
# Edit tests/test_reconstruction.py or test_end_to_end.py to include new fixture

pytest tests/ -v
```

### Step 5: Export to Arize (Optional)

If you want to verify end-to-end export:

```bash
# Ensure .env is configured with Arize credentials
python scripts/process_partner_data.py \
  partner_data/partner_a/sanitized_data.json \
  --export
```

Then check Arize UI for the traces (they'll be in your configured project).

### Step 6: Document Findings

Create an analysis report for each partner:

**Template** (`partner_data/partner_a/analysis_results.txt`):

```
Partner: Partner A
Date: 2026-02-20
Data file: sanitized_data.json

=== STATISTICS ===
Events: 150
Conversations: 5
Date range: 2026-02-15 to 2026-02-18
Channels: msteams

Event types:
- BotMessageSend: 40
- BotMessageReceived: 35
- TopicStart: 30
- TopicAction: 25
- AgentStarted: 10
- AgentCompleted: 10

=== FINDINGS ===
✅ Data processed successfully
✅ All event types recognized
✅ Knowledge search detected in 2 conversations
✅ System topics working correctly
✅ Locale extracted: en-US

⚠️  3 empty traces detected (will be filtered automatically)

=== ISSUES DISCOVERED ===
None

=== RECOMMENDATIONS ===
- Configuration looks good
- No bridge changes needed for this use case

=== EXPORT TEST ===
✅ Successfully exported 5 traces to Arize AX
✅ Traces visible in UI
✅ All metadata fields present

=== NEXT STEPS ===
- Add to test suite as partner_a_sample.json
- Use as validation case for future releases
```

---

## Common Scenarios

### Scenario 1: Partner Uses Custom Topics Heavily

**Expected:**
- Many TopicStart/TopicEnd events
- TopicAction events within topic windows
- Custom topic names in metadata
- `topic_type = "custom"` for most topics

**Validation:**
- Check that topic windows are correctly identified
- Verify CHAIN spans created for each topic
- Confirm TOOL spans nested under correct CHAIN parents

### Scenario 2: Partner Uses Generative AI/Agents

**Expected:**
- AgentStarted/AgentCompleted events
- GenerativeAnswers events (possibly)
- Sub-agent LLM calls
- `llm.model_name = "copilot-studio-subagent"`

**Validation:**
- Check LLM spans created from AgentStarted/Completed pairs
- Verify llm.input_messages and llm.output_messages populated
- Confirm agent_type captured in metadata

### Scenario 3: Partner Uses Knowledge Sources

**Expected:**
- Bot responses with citation markers `[1]`, `[2]`
- OR output without child spans (direct knowledge answer)
- `knowledge_search_detected = true`

**Validation:**
- Check knowledge search detection working
- Verify `knowledge_search` tag added
- Confirm metadata includes `knowledge_search_detected`

### Scenario 4: Partner Has Multi-Lingual Agent

**Expected:**
- Events with different locale values (en-US, es-ES, fr-FR, etc.)
- Locale should propagate to all spans in tree

**Validation:**
- Check locale extraction working
- Verify locale in metadata for all spans
- Confirm correct locale per conversation

### Scenario 5: Partner Has Complex Action Chains

**Expected:**
- Many TopicAction events
- Multiple action kinds (SendActivity, CancelAllDialogs, etc.)
- TOOL spans with various tool_name values

**Validation:**
- Check TOOL spans created for each action
- Verify tool_name set correctly from action kind
- Confirm action_id captured in metadata

---

## Troubleshooting

### "Error loading data: Unexpected data format"

**Cause:** JSON file format doesn't match expected structure

**Fix:**
1. Check if file is valid JSON: `cat file.json | jq`
2. Inspect first few lines: `head -20 file.json`
3. Verify it's either:
   - Azure CLI format: `{"tables": [{"rows": [...]}]}`
   - Direct array: `[{...}, {...}]`

### "No events loaded"

**Cause:** File is empty or has wrong structure

**Fix:**
1. Check file size: `ls -lh file.json`
2. Verify content: `cat file.json | jq length`
3. Ask partner to re-export with correct query

### "Permission denied" when exporting

**Cause:** Arize credentials not configured or invalid

**Fix:**
1. Check `.env` file exists: `ls -la .env`
2. Verify credentials are correct
3. Test with existing fixture first: `python scripts/export_to_arize.py tests/fixtures/live_data_dump.json`

### "Traces built but look wrong"

**Cause:** Partner's data has unexpected patterns

**Fix:**
1. Review statistics output to understand data structure
2. Check for missing event types or unusual ordering
3. Create a minimal reproduction case
4. File issue with details for investigation

---

## Partner Communication Templates

### Initial Request

```
Subject: Request for Copilot Studio Telemetry Sample

Hi [Partner Name],

We're validating our Copilot Studio → Arize AX bridge service across different
customer configurations and would appreciate your help by providing a sample of
your agent's telemetry data.

Attached is a guide (PARTNER_DATA_COLLECTION_GUIDE.md) with step-by-step
instructions on:
- How to export the data from your Application Insights
- How to sanitize sensitive information
- What format we need (JSON)

The process should take 5-10 minutes. We only need 50-200 events from test
conversations – no production data required.

This will help us ensure the bridge works correctly with your specific
configuration and use cases.

Let me know if you have any questions!

Thanks,
[Your name]
```

### Results Report

```
Subject: Analysis Results - Copilot Studio Data Validation

Hi [Partner Name],

Thank you for providing the telemetry sample! I've completed the analysis and
everything looks great.

Summary:
✅ Data processed successfully
✅ All event types recognized
✅ 5 traces exported to our test environment
✅ No compatibility issues found

Details:
- Events processed: 150
- Conversations: 5
- Features detected: Knowledge search (2 traces), System topics (8 spans)
- Bridge compatibility: 100%

Your configuration is fully compatible with the bridge service. We've added your
data as a test case to ensure future updates continue to work with your setup.

Let me know if you'd like more details or have any questions about the integration.

Thanks again for your help!

[Your name]
```

---

## Best Practices

1. **Organize partner data systematically** - Use dedicated directories per partner
2. **Document findings** - Create analysis reports for each dataset
3. **Communicate results** - Always report back to partners on what you found
4. **Expand test coverage** - Add partner data to automated test suite
5. **Track compatibility** - Maintain a matrix of tested configurations
6. **Respect privacy** - Never commit raw partner data to git, only sanitized samples

---

## Reference

- **Collection guide**: `PARTNER_DATA_COLLECTION_GUIDE.md` (send to partners)
- **Processing script**: `copilot-insights-bridge/scripts/process_partner_data.py`
- **This workflow**: `PARTNER_DATA_WORKFLOW.md` (your reference)
