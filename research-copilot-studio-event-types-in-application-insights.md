<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# find docs and a dictionary of all copilot agent event types that can be tracked in  application insights

You’re looking at two related but slightly different things:

1) what Copilot Studio agents actually emit into Application Insights, and
2) an authoritative “dictionary” of those event types and fields.

There isn’t a single dedicated “event dictionary” page, but you can reconstruct it from the Copilot Studio + App Insights docs and tables.

## Core documentation links

- **Capture telemetry with Application Insights – Microsoft Copilot Studio** (main schema + how to connect, including agents).[^1_1]
- **Application Insights telemetry with Microsoft Copilot Studio** (table of event names, “Bot Event”, “Topics”, “Kind”, etc.).[^1_2]
- **Enable Application Insights support in Copilot Studio** (enablement \& examples).[^1_3]
- **Capturing telemetry in Microsoft Copilot Studio with Azure Application Insights** (blog-style, but has concrete KQL examples and field names).[^1_4]

Those four together give you the effective “dictionary” of Copilot agent events in App Insights.

## Built‑in event types (Copilot Studio → App Insights)

From the Copilot Studio + App Insights docs, the standard customEvents you’ll see from a Microsoft Copilot Studio agent include at least these logical types:[^1_2][^1_1]

- **ConversationStart** – new conversation/session started (Bot Event or Topic).[^1_2]
- **Greeting** – greeting topic triggered at conversation start.[^1_2]
- **TopicStart / TopicEnd** – topic lifecycle events within a session (often surfaced via “Event group” like `TopicStart_Greetings`, `TopicEnd_Greetings`).[^1_2]
- **BotMessageReceived** – user message received by the agent.[^1_2]
- **BotMessageSend** – agent message sent back to the user.[^1_2]
- **Action** – individual action execution within a topic (question, search, variable setting, etc.).[^1_2]
- **Custom telemetry** – any custom event you emit from topics using the telemetry action.[^1_1][^1_2]

Under the hood, these appear in **customEvents** in Application Insights, with “name” and a set of custom dimensions.[^1_1][^1_2]

## Key dimensions / fields per event

The Copilot Studio + App Insights schema exposes the following important dimensions across these events:[^1_4][^1_1][^1_2]

- **name** (customEvent name)
    - Examples: `Topic Start`, `BotMessageReceived`, `BotMessageSend`, `Action`, `Topic End`, your custom event names.[^1_2]
- **Bot Event**
    - Values like: `Topic Start`, `BotMessageReceived`, `Bot MessageSend`, `Action`, `Topic End`, `Custom Telemetry`.[^1_2]
- **Topics**
    - Topic logical name; for example, `Triggered Topic`, `ConversationStart`, `Greeting`, or your own topic name.[^1_2]
- **Kind**
    - Action subtype inside a topic, e.g. `Question`, `SetVariable`, `SearchandSummarizeContent` (and other action types you use).[^1_2]
- **session_id**
    - Unique ID for the bot/agent session; used to correlate all events within a conversation.[^1_1][^1_2]
- **event group**
    - Logical grouping of actions within a topic, e.g. `TopicStart_Greetings`, `Other`, `TopicEnd_Greetings`; can be customized.[^1_2]
- **TimeDifference**
    - Time to run each action, in milliseconds, letting you measure per‑step latency.[^1_2]
- **Standard App Insights context**
    - `operation_Id` / `operation_ParentId` for end‑to‑end correlation, `cloud_RoleName`, `user_Id`, channel info (varies by channel), plus timestamps and basic envelope fields.[^1_4][^1_1]
- **Custom dimensions**
    - Arbitrary key/values added in topics via custom telemetry: user identifiers, environment flags, conversation attributes, etc.[^1_4][^1_1]


## How to view the “dictionary” in practice

Because the official docs only list some of the event types and dimensions, the practical way to get a full dictionary is:

1. **Connect your agent to App Insights** by adding the instrumentation key/connection string in Copilot Studio as documented in “Capture telemetry with Application Insights”.[^1_3][^1_1]
2. In **Logs (Analytics)** for your Application Insights resource, run a KQL like:[^1_1][^1_4]

```kusto
customEvents
| summarize count() by name
```

to enumerate all event types, then:

```kusto
customEvents
| where name == "Action"
| take 1
```

and inspect `customDimensions` to see the full field set per event.

That effectively gives you the live event dictionary for your specific Copilot Studio agent.

If you want, paste a sample `customEvents | take 5` result (JSON) and I can help you turn it into a structured event‑type/field dictionary you can drop straight into internal docs.
<span style="display:none">[^1_10][^1_11][^1_12][^1_13][^1_14][^1_15][^1_5][^1_6][^1_7][^1_8][^1_9]</span>

<div align="center">⁂</div>

[^1_1]: https://learn.microsoft.com/en-us/microsoft-copilot-studio/advanced-bot-framework-composer-capture-telemetry

[^1_2]: https://learn.microsoft.com/en-us/dynamics365/guidance/resources/copilot-studio-appinsights

[^1_3]: https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/kit-enable-application-insights

[^1_4]: https://holgerimbery.blog/analytics-with-azure-insights

[^1_5]: https://learn.microsoft.com/en-us/azure/copilot/observability-agent

[^1_6]: https://learn.microsoft.com/en-us/azure/azure-monitor/app/agents-view

[^1_7]: https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview

[^1_8]: https://learn.microsoft.com/en-us/azure/azure-monitor/aiops/observability-agent-best-practices

[^1_9]: https://freschesolutions.com/resource/copilot-studio-vs-azure-ai-foundry/

[^1_10]: https://fusiondevblogs.com/Production/2024-07-28-Copilot-Application-Insights/

[^1_11]: https://www.synapx.com/ai-the-ultimate-guide-llms-azure-ai-foundry-copilot/

[^1_12]: https://learn.microsoft.com/en-us/answers/questions/5662319/monitoring-copilot-agent

[^1_13]: https://cloudwars.com/ai/community-summit-na-microsofts-roadmap-for-copilot-studio-azure-ai-foundry-integration/

[^1_14]: https://www.youtube.com/watch?v=1n6NnH-mj28

[^1_15]: https://community.powerplatform.com/forums/thread/details/?threadid=d27f2351-e556-f011-877a-7c1e526b19c2

