# Partner Data Collection Guide

**Purpose**: Collect sample Copilot Studio telemetry data from partners to validate the Copilot Studio → Arize AX bridge across different use cases and configurations.

---

## Overview for Partners

We need sample telemetry data from your Microsoft Copilot Studio agents to ensure our bridge service works correctly with your configuration. You can export this data directly from your Azure Application Insights resource and share it as a JSON file.

**What we need:**
- 50-200 events from a few representative conversations
- Full `customEvents` records with `customDimensions` intact
- Data can be from test conversations (no production data required)

**Data privacy:**
- Instructions below include sanitization steps
- You control what data you share
- We only need event structure, not actual conversation content

---

## Prerequisites (Partner Requirements)

- ✅ Microsoft Copilot Studio agent configured with Azure Application Insights
- ✅ Azure CLI installed (`az --version` to verify)
- ✅ Access to query the Application Insights resource (Reader or Contributor role)
- ✅ 5-10 minutes to run queries and export data

---

## Option 1: Azure CLI Export (Recommended)

### Step 1: Authenticate with Azure

```bash
az login
az account set --subscription "<your-subscription-id>"
```

### Step 2: Get Your Application Insights App ID

```bash
# Find your App Insights resource
az monitor app-insights component show \
  --app <your-app-insights-name> \
  --resource-group <your-resource-group> \
  --query appId -o tsv
```

Save this App ID for the next step.

### Step 3: Query and Export Data

```bash
# Set variables
APP_ID="<your-app-id-from-step-2>"
START_TIME="2026-02-15T00:00:00Z"  # Adjust to your data range
END_TIME="2026-02-20T23:59:59Z"    # Adjust to your data range

# Query and save to file
az monitor app-insights query \
  --app "$APP_ID" \
  --analytics-query "customEvents
| where timestamp between (datetime($START_TIME) .. datetime($END_TIME))
| where customDimensions.designMode == 'False'
| take 200
| project timestamp, name, operation_Id, operation_ParentId, customDimensions" \
  --output json > copilot_events_sample.json
```

**File created**: `copilot_events_sample.json`

---

## Option 2: Azure Portal Export

### Step 1: Open Application Insights

1. Log into [Azure Portal](https://portal.azure.com)
2. Navigate to your Application Insights resource
3. Click **Logs** in the left sidebar

### Step 2: Run Query

Paste this query:

```kusto
customEvents
| where timestamp > ago(7d)
| where customDimensions.designMode == "False"
| take 200
| project timestamp, name, operation_Id, operation_ParentId, customDimensions
```

### Step 3: Export Results

1. Click **Export** button (top toolbar)
2. Select **Export to CSV** or **Export to JSON**
3. Save file as `copilot_events_sample.json`

---

## Step 3: Sanitize Data

Before sharing, sanitize any sensitive information:

### Quick Sanitization Script

Save this as `sanitize.py`:

```python
import json
import hashlib
import sys

def hash_value(value):
    """Hash a value for privacy."""
    if not value:
        return value
    return hashlib.sha256(str(value).encode()).hexdigest()[:16]

def sanitize_event(event):
    """Remove or hash sensitive fields."""
    dims = event.get('customDimensions', {})

    # Hash user identifiers
    if 'userId' in dims:
        dims['userId'] = f"user_{hash_value(dims['userId'])}"
    if 'fromId' in dims:
        dims['fromId'] = f"user_{hash_value(dims['fromId'])}"
    if 'user_Id' in dims:
        dims['user_Id'] = f"user_{hash_value(dims['user_Id'])}"

    # Hash conversation/session IDs
    if 'conversationId' in dims:
        dims['conversationId'] = f"conv_{hash_value(dims['conversationId'])}"
    if 'session_Id' in dims:
        dims['session_Id'] = f"sess_{hash_value(dims['session_Id'])}"

    # Redact message text (OPTIONAL - or replace with generic text)
    if 'text' in dims and dims['text']:
        dims['text'] = "[REDACTED USER MESSAGE]"

    # Keep these fields as-is (needed for validation):
    # - topicName, topicId, kind, activityType
    # - channelId, agentType, actionId
    # - designMode, locale
    # - All event names and structure

    return event

# Load, sanitize, and save
with open(sys.argv[1], 'r') as f:
    data = json.load(f)

# Handle Azure CLI format (tables array) or direct array
if isinstance(data, dict) and 'tables' in data:
    rows = data['tables'][0]['rows']
    sanitized = [sanitize_event(row) for row in rows]
elif isinstance(data, list):
    sanitized = [sanitize_event(event) for event in data]
else:
    print("Unexpected format")
    sys.exit(1)

output_file = sys.argv[1].replace('.json', '_sanitized.json')
with open(output_file, 'w') as f:
    json.dump(sanitized, f, indent=2)

print(f"Sanitized data saved to: {output_file}")
print(f"Events processed: {len(sanitized)}")
```

Run it:

```bash
python sanitize.py copilot_events_sample.json
# Output: copilot_events_sample_sanitized.json
```

### What Gets Sanitized

**Hashed/Removed:**
- ✅ User IDs (userId, fromId, user_Id) → hashed
- ✅ Conversation IDs → hashed
- ✅ Session IDs → hashed
- ✅ Message text (text field) → redacted or generic (OPTIONAL)

**Preserved (needed for validation):**
- ✅ Event names (BotMessageSend, TopicStart, etc.)
- ✅ Topic names and IDs
- ✅ Action kinds and IDs
- ✅ Channel IDs
- ✅ Agent types
- ✅ Timestamps and structure
- ✅ All field names and relationships

---

## Step 4: Share the Data

### File to Share

📁 **File**: `copilot_events_sample_sanitized.json`

**Size**: Should be ~50-500KB depending on number of events

### Sharing Options

1. **Email**: Attach the JSON file
2. **Cloud storage**: Upload to SharePoint/OneDrive/Dropbox and share link

### What to Include

When sharing, please provide:

1. **The sanitized JSON file**
2. **Brief description** of your Copilot Studio agent:
   - What does the agent do? (e.g., "IT helpdesk bot", "FAQ assistant")
   - Which channels are used? (Teams, Web, etc.)
   - What features are used? (Knowledge sources, generative answers, actions, topics)
3. **Any known issues** or special configurations we should be aware of
4. **Contact info** in case we have questions

---

Thank you for helping us validate the Copilot Studio → Arize AX bridge! 🙏

---

## What We'll Do With Your Data

1. **Validate bridge compatibility** with your agent configuration
2. **Test edge cases** (different event patterns, topic structures, etc.)
3. **Verify metadata extraction** works correctly for your use case
4. **Identify gaps** in our implementation
5. **Add to test suite** (anonymized) to prevent regressions

We will **NOT**:
- ❌ Store or use production data
- ❌ Share your data with third parties
- ❌ Reverse-engineer business logic or content
- ❌ Keep data after validation is complete

---

## Troubleshooting

### "No data returned"
- Check date range in query (`START_TIME` and `END_TIME`)
- Verify Application Insights is receiving data: check "Live Metrics" in portal
- Ensure `designMode == 'False'` filter isn't excluding all data (try removing it for testing)

### "Permission denied"
- Ensure you have Reader role on the Application Insights resource
- Check if Contributor role is required in your organization

### "Too much data"
- Reduce date range (e.g., last 24 hours instead of 7 days)
- Use `take 100` instead of `take 200` in the query

### "Azure CLI not working"
- Update Azure CLI: `az upgrade`
- Try using Azure Portal method instead (Option 2)

---

## Sample Query for Specific Scenarios

### Only Get Conversations with Errors

```kusto
customEvents
| where timestamp > ago(7d)
| where customDimensions.designMode == "False"
| where name has "error" or customDimensions.errorCodeText != ""
| take 50
```

### Only Get Generative AI Conversations

```kusto
customEvents
| where timestamp > ago(7d)
| where customDimensions.designMode == "False"
| where name in ("AgentStarted", "AgentCompleted", "GenerativeAnswers")
| take 200
```

### Only Get Action/Tool Invocations

```kusto
customEvents
| where timestamp > ago(7d)
| where customDimensions.designMode == "False"
| where name in ("Action", "TopicAction")
| take 200
```

---

