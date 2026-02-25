# Azure Configuration Guide

Step-by-step guide for setting up Azure Application Insights to work with the Copilot Studio → Arize AX bridge.

## Prerequisites

- Azure subscription with appropriate permissions
- Microsoft Copilot Studio agent created
- Azure CLI installed (`az` command)
- Basic understanding of Azure resources

## Step 1: Create Application Insights Resource

### Option A: Azure Portal

1. Navigate to [Azure Portal](https://portal.azure.com)
2. Click "Create a resource"
3. Search for "Application Insights"
4. Click "Create"
5. Fill in details:
   - **Subscription**: Select your subscription
   - **Resource Group**: Create new or select existing (e.g., `rg-copilot-monitoring`)
   - **Name**: Choose a name (e.g., `copilot-insights-prod`)
   - **Region**: Select closest to your users
   - **Workspace**: Create new Log Analytics workspace or use existing
6. Click "Review + Create" → "Create"
7. Wait for deployment to complete

### Option B: Azure CLI

```bash
# Set variables
SUBSCRIPTION="Your Subscription Name"
RESOURCE_GROUP="rg-copilot-monitoring"
LOCATION="eastus"
APP_INSIGHTS_NAME="copilot-insights-prod"
WORKSPACE_NAME="copilot-logs"

# Login to Azure
az login
az account set --subscription "$SUBSCRIPTION"

# Create resource group
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION"

# Create Log Analytics workspace
az monitor log-analytics workspace create \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --location "$LOCATION"

# Get workspace ID
WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --query id -o tsv)

# Create Application Insights
az monitor app-insights component create \
  --app "$APP_INSIGHTS_NAME" \
  --location "$LOCATION" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace "$WORKSPACE_ID"
```

## Step 2: Get Application Insights Resource ID

### Azure Portal

1. Navigate to your Application Insights resource
2. Click "Properties" in the left menu
3. Copy the **Resource ID** (format: `/subscriptions/{sub}/resourceGroups/{rg}/providers/microsoft.insights/components/{name}`)

### Azure CLI

```bash
az monitor app-insights component show \
  --app "$APP_INSIGHTS_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query id -o tsv
```

Save this Resource ID for your `.env` configuration.

## Step 3: Configure Copilot Studio

1. Open [Copilot Studio](https://copilotstudio.microsoft.com/)
2. Select your agent
3. Click **Settings** → **Analytics**
4. Under "Application Insights":
   - Click "Connect" or "Edit"
   - Select your Application Insights resource
   - Click "Save"
5. Confirm connection shows "Connected"

**Note**: It may take 5-10 minutes for telemetry to start flowing after initial connection.

## Step 4: Verify Telemetry Collection

### Test with KQL Query

Wait 10-15 minutes after connecting, then query:

```bash
# Query for recent events
az monitor app-insights query \
  --app "$APP_INSIGHTS_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --analytics-query "customEvents | where timestamp > ago(1h) | take 10" \
  --output table
```

Expected output: Events with `name` like "ConversationUpdate", "ImBack", "Activity"

### Check Event Types

```bash
# Get distinct event types
az monitor app-insights query \
  --app "$APP_INSIGHTS_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --analytics-query "customEvents | summarize count() by name" \
  --output table
```

You should see:
- `ConversationUpdate` - Conversation start/end
- `ImBack` - User messages
- `Activity` - Bot responses, topic events

## Step 5: Configure Azure Credentials for Bridge

The bridge needs permissions to query Application Insights.

### Option A: Azure CLI Authentication (Local Development)

```bash
# Login to Azure
az login

# Set subscription
az account set --subscription "$SUBSCRIPTION"

# Test query
az monitor app-insights query \
  --app "$APP_INSIGHTS_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --analytics-query "customEvents | take 1" \
  --output json
```

**In .env**: Set `BRIDGE_AZURE_CREDENTIAL=cli` (default)

### Option B: Managed Identity (Production - Recommended)

If running bridge in Azure (App Service, Container Apps, etc.):

1. **Enable managed identity** on your Azure resource
   ```bash
   # For App Service
   az webapp identity assign \
     --name <your-app-service> \
     --resource-group <your-rg>

   # Get the principal ID
   PRINCIPAL_ID=$(az webapp identity show \
     --name <your-app-service> \
     --resource-group <your-rg> \
     --query principalId -o tsv)
   ```

2. **Grant permissions** to Application Insights
   ```bash
   # Get App Insights resource ID
   APP_INSIGHTS_ID=$(az monitor app-insights component show \
     --app "$APP_INSIGHTS_NAME" \
     --resource-group "$RESOURCE_GROUP" \
     --query id -o tsv)

   # Assign "Monitoring Reader" role
   az role assignment create \
     --assignee "$PRINCIPAL_ID" \
     --role "Monitoring Reader" \
     --scope "$APP_INSIGHTS_ID"
   ```

**In .env**: Set `BRIDGE_AZURE_CREDENTIAL=managed_identity`

### Option C: Service Principal (CI/CD)

For automated deployments:

```bash
# Create service principal
az ad sp create-for-rbac \
  --name "copilot-bridge-sp" \
  --role "Monitoring Reader" \
  --scopes "$APP_INSIGHTS_ID" \
  --sdk-auth

# Output includes:
# - clientId
# - clientSecret
# - tenantId
# - subscriptionId
```

Set environment variables:
```bash
export AZURE_CLIENT_ID="..."
export AZURE_CLIENT_SECRET="..."
export AZURE_TENANT_ID="..."
```

**In .env**: Set `BRIDGE_AZURE_CREDENTIAL=environment`

## Step 6: Test Connection

```bash
# Navigate to bridge directory
cd copilot-insights-bridge

# Copy configuration
cp ../examples/env/.env.development.example .env

# Edit .env with your values
vi .env

# Test query
python -c "
from src.extraction.client import AppInsightsClient
from src.config import settings
from datetime import datetime, timezone, timedelta

client = AppInsightsClient(settings.appinsights_resource_id)
end = datetime.now(timezone.utc)
start = end - timedelta(hours=1)

events = client.query_events(start, end)
print(f'Found {len(events)} events')
for event in events[:5]:
    print(f'  - {event.name} at {event.timestamp}')
"
```

Expected: List of recent events from your Copilot Studio agent.

## Troubleshooting

### No Events Found

**Cause**: Telemetry not flowing yet or no conversations in timeframe

**Solutions**:
- Wait 10-15 minutes after connecting Copilot Studio
- Test your Copilot agent (have a conversation)
- Increase lookback time: `--analytics-query "customEvents | where timestamp > ago(24h)"`
- Verify connection in Copilot Studio settings

### Permission Denied

**Cause**: Azure credentials don't have access to Application Insights

**Solutions**:
- Check you're logged in: `az account show`
- Verify subscription: `az account set --subscription "Your Subscription"`
- Check role assignments:
  ```bash
  az role assignment list \
    --scope "$APP_INSIGHTS_ID" \
    --output table
  ```
- Ensure you have "Monitoring Reader" or higher role

### Invalid Resource ID

**Cause**: Incorrect BRIDGE_APPINSIGHTS_RESOURCE_ID format

**Solution**: Copy exact Resource ID from Azure Portal or CLI:
```bash
az monitor app-insights component show \
  --app "$APP_INSIGHTS_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query id -o tsv
```

### Rate Limiting

**Cause**: Too many queries to Application Insights API

**Solutions**:
- Increase `BRIDGE_POLL_INTERVAL_MINUTES` in `.env`
- Reduce `BRIDGE_BATCH_SIZE` if queries are very large
- Monitor query costs in Azure Cost Management

## Next Steps

1. ✅ Configure Arize credentials (see main README)
2. ✅ Run bridge in single-cycle mode: `python -m src.main`
3. ✅ Verify traces appear in Arize AX
4. ✅ Set up continuous polling for production
5. ✅ Configure monitoring and alerts

## Related Documentation

- **Bridge README**: `../../copilot-insights-bridge/README.md`
- **Configuration examples**: `.env.development.example`, `.env.production.example`
- **Azure App Insights docs**: https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview
- **Copilot Studio analytics**: https://learn.microsoft.com/en-us/microsoft-copilot-studio/analytics-overview
