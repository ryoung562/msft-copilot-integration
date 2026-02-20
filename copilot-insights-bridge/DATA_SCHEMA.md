# Data Schema Reference

Comprehensive reference for the Copilot Insights Bridge data pipeline, covering the raw Application Insights telemetry, the internal extraction and reconstruction models, and the final OpenInference/OpenTelemetry mapping.

---

## Table of Contents

1. [Raw Application Insights Schema](#1-raw-application-insights-schema)
2. [Event Types Deep Dive](#2-event-types-deep-dive)
3. [Field Catalog](#3-field-catalog)
4. [Data Patterns and Relationships](#4-data-patterns-and-relationships)
5. [Internal Models](#5-internal-models)
6. [Trace Tree Reconstruction](#6-trace-tree-reconstruction)
7. [OpenInference Attribute Mapping](#7-openinference-attribute-mapping)
8. [OTel Span Export](#8-otel-span-export)
9. [End-to-End Data Flow Example](#9-end-to-end-data-flow-example)

---

## 1. Raw Application Insights Schema

Events are extracted from the `customEvents` table in Azure Application Insights. Each row represents a single telemetry event emitted by Microsoft Copilot Studio.

### 1.1 Dataset Statistics (from `app_insights_export.json`)

| Metric | Value |
|--------|-------|
| Total events | 127 |
| Unique conversations | 10 |
| Unique sessions | 10 |
| Design-mode events | 86 |
| Production (Teams) events | 41 |
| Distinct channels | `pva-studio`, `msteams` |
| Distinct user IDs | 2 |

### 1.2 Event Type Distribution

| Event Type | Count | Description |
|------------|-------|-------------|
| `BotMessageSend` | 30 | Bot sends a message to the user |
| `TopicStart` | 26 | A topic/agent begins execution |
| `BotMessageReceived` | 25 | Bot receives a message or system event from the user/channel |
| `TopicAction` | 19 | An action node executes within a topic |
| `AgentCompleted` | 11 | A sub-agent finishes its work |
| `TopicEnd` | 10 | A topic completes execution |
| `AgentStarted` | 6 | A sub-agent is invoked to handle a task |

### 1.3 All Fields

Every event in the export carries these 27 fields. Fields marked "always present" have a non-null, non-empty value on every event of the indicated type; fields marked "conditional" are populated only on certain event types or under certain conditions.

| # | Field | Type | Description |
|---|-------|------|-------------|
| 1 | `timestamp` | ISO 8601 datetime | Event timestamp with timezone (always present on all events) |
| 2 | `name` | string | Event type identifier (always present) |
| 3 | `operation_id` | string | App Insights operation ID (always empty string `""` in observed data) |
| 4 | `operation_parent_id` | string | App Insights parent operation ID (always empty string `""`) |
| 5 | `session_id` | string | Base64-encoded session hash (always present, non-empty) |
| 6 | `conversation_id` | string | UUID identifying the conversation (always present, non-empty) |
| 7 | `user_id` | string | UUID or Teams ID of the user (present on `BotMessageReceived` only) |
| 8 | `channel_id` | string | Channel identifier (always present: `"pva-studio"` or `"msteams"`) |
| 9 | `topic_name` | string or null | Name of the topic; format depends on event type |
| 10 | `topic_id` | string or null | Fully-qualified topic identifier |
| 11 | `kind` | string or null | Action kind within a topic |
| 12 | `text` | string or null | User message text or bot response text |
| 13 | `from_id` | string or null | Sender identifier |
| 14 | `from_name` | string or null | Sender display name |
| 15 | `recipient_id` | string or null | Recipient identifier |
| 16 | `recipient_name` | string or null | Recipient display name (bot name or user name) |
| 17 | `activity_type` | string or null | Bot Framework activity type |
| 18 | `error_code_text` | string or null | Error description if the event represents a failure |
| 19 | `message` | string or null | Input message for generative answers (not observed in current data) |
| 20 | `result` | string or null | Output result for generative answers (not observed in current data) |
| 21 | `summary` | string or null | Summary text (not observed in current data) |
| 22 | `design_mode` | string | `"True"` for Copilot Studio test canvas; `"False"` for production channels |
| 23 | `action_id` | string or null | Unique identifier for the action node being executed |
| 24 | `agent_type` | string or null | Type of sub-agent (only on `AgentStarted`/`AgentCompleted`) |
| 25 | `agent_inputs` | string or null | JSON string with agent task inputs |
| 26 | `agent_outputs` | string or null | JSON string with agent output schema |
| 27 | `speak` | string or null | SSML/text-to-speech version of the bot response |

---

## 2. Event Types Deep Dive

### 2.1 BotMessageReceived

Emitted when the bot runtime receives any inbound activity from the channel. This includes actual user messages, system events, and other Bot Framework activities.

**Fields populated on this event type:**

| Field | Presence | Values / Notes |
|-------|----------|----------------|
| `timestamp` | Always | |
| `session_id` | Always | Base64 hash |
| `conversation_id` | Always | UUID |
| `user_id` | Always | Same as `from_id` |
| `channel_id` | Always | `"pva-studio"` or `"msteams"` |
| `text` | Conditional | Present only when `activity_type = "message"` (13 of 25 events) |
| `from_id` | Always | User's ID (UUID for studio, Teams ID for msteams) |
| `from_name` | Conditional | Present only on `msteams` channel (e.g., `"Richard Young"`) |
| `recipient_id` | Always | Bot's ID (e.g., `"Default-4c10d796.../a45baa76..."`) |
| `recipient_name` | Always | Bot name (e.g., `"auto_agent_Y6JvM"`, `"Arize Copilot Agent"`) |
| `activity_type` | Always | Determines the nature of the inbound activity |
| `design_mode` | Always | |
| All other fields | Always null | |

**Activity type breakdown:**

| `activity_type` | Count | Has `text`? | Meaning |
|-----------------|-------|-------------|---------|
| `"message"` | 13 | Yes (always) | Actual user-typed message -- the primary input for traces |
| `"event"` | 9 | Never | System event, typically `conversationUpdate` or session init |
| `"installationUpdate"` | 1 | Never | Bot installed/added to a channel (Teams only) |
| `"invoke"` | 1 | Never | Adaptive card action or other invocation (Teams only) |
| `"messageReaction"` | 1 | Never | User reacted to a message (Teams only) |

**Key insight:** Only `activity_type = "message"` events represent actual user input. The bridge filters on this to identify turn boundaries and extract user query text.

### 2.2 BotMessageSend

Emitted when the bot sends a message to the user. A single turn can produce multiple `BotMessageSend` events (e.g., a detailed response followed by a summary).

**Fields populated on this event type:**

| Field | Presence | Values / Notes |
|-------|----------|----------------|
| `timestamp` | Always | |
| `session_id` | Always | |
| `conversation_id` | Always | |
| `user_id` | Always empty | Bot sends do not carry user_id |
| `channel_id` | Always | |
| `text` | Usually | Bot response text; 27 of 30 events have text. 3 events (all on `msteams`) have null text (system/typing indicator messages) |
| `recipient_id` | Always | User's ID (the recipient of the bot's message) |
| `recipient_name` | Conditional | Present only on `msteams` channel (e.g., `"Richard Young"`) |
| `speak` | Conditional | SSML text-to-speech content; present on 14 of 30 events (greeting/scripted messages only) |
| `design_mode` | Always | |
| All other fields | Always null | |

**Key insight:** The `text` field contains the bot's response, which becomes `output.value` in OpenInference. The `speak` field is an alternative TTS representation used for voice channels and contains SSML markup like `<break strength="medium" />`. It is only present on scripted greeting messages, never on generative AI responses.

### 2.3 TopicStart

Emitted when a topic (dialog/agent) begins execution. Topics are the primary workflow unit in Copilot Studio.

**Fields populated on this event type:**

| Field | Presence | Values / Notes |
|-------|----------|----------------|
| `timestamp` | Always | |
| `session_id` | Always | |
| `conversation_id` | Always | |
| `user_id` | Always empty | |
| `channel_id` | Always | |
| `topic_name` | Always | Fully-qualified name (e.g., `"auto_agent_Y6JvM.topic.ConversationStart"`) |
| `topic_id` | Always null | Not populated on TopicStart |
| `design_mode` | Always | |
| All other fields | Always null | |

**Observed topic names:**

| Topic Name | Meaning | Frequency |
|------------|---------|-----------|
| `auto_agent_Y6JvM.topic.ConversationStart` | Conversation initialization topic | Most common |
| `auto_agent_UUrzZ.topic.ConversationStart` | Same, for a different agent | 1 conversation |
| `auto_agent_Y6JvM.topic.Greeting` | Greeting topic triggered by "hello" | Multiple |
| `auto_agent_Y6JvM.agent.Agent_OM0` | Generative AI agent topic | When AI is invoked |
| `PowerVirtualAgentRoot` | Fallback/root topic after dialog cancellation | After `CancelAllDialogs` |

**Key insight:** Not all `TopicStart` events have a matching `TopicEnd`. Of 26 TopicStart events, only 10 have matching TopicEnd events. Topics like `PowerVirtualAgentRoot`, `auto_agent_Y6JvM.agent.Agent_OM0`, and `auto_agent_Y6JvM.topic.Greeting` frequently lack explicit TopicEnd events. The tree builder handles this by closing unclosed windows at the last event timestamp.

### 2.4 TopicEnd

Emitted when a topic completes execution.

**Fields populated on this event type:**

| Field | Presence | Values / Notes |
|-------|----------|----------------|
| `timestamp` | Always | |
| `session_id` | Always | |
| `conversation_id` | Always | |
| `user_id` | Always empty | |
| `channel_id` | Always | |
| `topic_name` | Always | Fully-qualified name matching the corresponding TopicStart |
| `topic_id` | Always null | |
| `design_mode` | Always | |
| All other fields | Always null | |

**Key insight:** TopicEnd is only emitted for short-lived topics (primarily `ConversationStart`). Agent topics and Greeting topics that redirect via `CancelAllDialogs` do not produce TopicEnd events.

### 2.5 TopicAction

Emitted for each action node that executes within a topic.

**Fields populated on this event type:**

| Field | Presence | Values / Notes |
|-------|----------|----------------|
| `timestamp` | Always | |
| `session_id` | Always | |
| `conversation_id` | Always | |
| `user_id` | Always empty | |
| `channel_id` | Always | |
| `topic_name` | Always | Short name (e.g., `"Conversation Start"`, `"Greeting"`) -- different format from TopicStart |
| `topic_id` | Always | Fully-qualified topic ID (e.g., `"auto_agent_Y6JvM.topic.ConversationStart"`) |
| `kind` | Always | Action type |
| `action_id` | Always | Unique action node identifier |
| `design_mode` | Always | |
| All other fields | Always null | |

**Observed `kind` values:**

| `kind` | Meaning | `action_id` examples |
|--------|---------|---------------------|
| `"SendActivity"` | Sends a message to the user | `sendMessage_M0LuhV`, `sendMessage_abmysR` |
| `"CancelAllDialogs"` | Cancels all active dialogs and redirects to a new topic | `cancelAllDialogs_01At22` |

**Key naming discrepancy:** On `TopicAction`, the `topic_name` is the short/display name (e.g., `"Greeting"`) while `topic_id` is the fully-qualified name (e.g., `"auto_agent_Y6JvM.topic.Greeting"`). On `TopicStart`/`TopicEnd`, the `topic_name` is the fully-qualified name and `topic_id` is always null. The tree builder uses fuzzy matching (`_topic_names_match`) to reconcile these formats.

### 2.6 AgentStarted

Emitted when a generative AI sub-agent is invoked.

**Fields populated on this event type:**

| Field | Presence | Values / Notes |
|-------|----------|----------------|
| `timestamp` | Always | |
| `session_id` | Always | |
| `conversation_id` | Always | |
| `user_id` | Always empty | |
| `channel_id` | Always | |
| `agent_type` | Always | Always `"SubAgent"` in observed data |
| `agent_inputs` | Always | JSON string containing `{"Task": "..."}` |
| `design_mode` | Always | |
| All other fields | Always null | |

**`agent_inputs` structure:**

```json
{
  "Task": "Provide details about the integration between Copilot and Arize AX."
}
```

The `Task` field contains the rephrased/refined version of the user's question that the orchestrator passes to the sub-agent. This is extracted by the tree builder and used as `llm_input` on the resulting LLM span.

### 2.7 AgentCompleted

Emitted when a sub-agent finishes its work.

**Fields populated on this event type:**

| Field | Presence | Values / Notes |
|-------|----------|----------------|
| `timestamp` | Always | |
| `session_id` | Always | |
| `conversation_id` | Always | |
| `user_id` | Always empty | |
| `channel_id` | Always | |
| `agent_type` | Always | Always `"SubAgent"` |
| `agent_inputs` | Always null | Not populated on completion events |
| `agent_outputs` | Always | JSON string with output schema definition (identical across all events) |
| `design_mode` | Always | |
| All other fields | Always null | |

**`agent_outputs` structure (schema definition, not actual output):**

```json
{
  "$kind": "Record",
  "properties": {
    "Summary": {
      "$kind": "PropertyInfo",
      "displayName": "Description",
      "description": "A concise summary of the execution so far, **limited to 500 words**...",
      "isRequired": true,
      "type": { "$kind": "String" }
    }
  }
}
```

**Important:** The `agent_outputs` field contains the *schema definition* of expected output, not the actual generated response. The actual bot response text appears in the subsequent `BotMessageSend` event(s).

**Double-completion pattern:** In observed data, each `AgentStarted` is followed by *two* `AgentCompleted` events (pattern: 1 start, 2 completions). The first `AgentCompleted` is separated from the start by a shorter interval (sub-agent internal completion), and the second appears just before or concurrent with the `BotMessageSend`. The tree builder handles this by updating the `end_time` on the pending agent span for each completion event it encounters.

---

## 3. Field Catalog

### 3.1 Field Presence Matrix

| Field | BMR | BMS | TS | TE | TA | AS | AC |
|-------|:---:|:---:|:--:|:--:|:--:|:--:|:--:|
| `timestamp` | Y | Y | Y | Y | Y | Y | Y |
| `session_id` | Y | Y | Y | Y | Y | Y | Y |
| `conversation_id` | Y | Y | Y | Y | Y | Y | Y |
| `user_id` | Y | - | - | - | - | - | - |
| `channel_id` | Y | Y | Y | Y | Y | Y | Y |
| `topic_name` | - | - | Y | Y | Y | - | - |
| `topic_id` | - | - | - | - | Y | - | - |
| `kind` | - | - | - | - | Y | - | - |
| `text` | C | C | - | - | - | - | - |
| `from_id` | Y | - | - | - | - | - | - |
| `from_name` | C | - | - | - | - | - | - |
| `recipient_id` | Y | Y | - | - | - | - | - |
| `recipient_name` | Y | C | - | - | - | - | - |
| `activity_type` | Y | - | - | - | - | - | - |
| `design_mode` | Y | Y | Y | Y | Y | Y | Y |
| `action_id` | - | - | - | - | Y | - | - |
| `agent_type` | - | - | - | - | - | Y | Y |
| `agent_inputs` | - | - | - | - | - | Y | - |
| `agent_outputs` | - | - | - | - | - | - | Y |
| `speak` | - | C | - | - | - | - | - |
| `error_code_text` | - | - | - | - | - | - | - |
| `message` | - | - | - | - | - | - | - |
| `result` | - | - | - | - | - | - | - |
| `summary` | - | - | - | - | - | - | - |
| `operation_id` | - | - | - | - | - | - | - |
| `operation_parent_id` | - | - | - | - | - | - | - |

Legend: **Y** = always present and non-empty, **C** = conditionally present, **-** = always null or empty.

Event type abbreviations: BMR = BotMessageReceived, BMS = BotMessageSend, TS = TopicStart, TE = TopicEnd, TA = TopicAction, AS = AgentStarted, AC = AgentCompleted.

### 3.2 Fields Never Populated in Observed Data

The following fields exist in the schema but were always null/empty across all 127 events:

| Field | Purpose | Expected Source |
|-------|---------|-----------------|
| `operation_id` | App Insights distributed tracing correlation | Would be populated if Copilot Studio emitted correlated traces |
| `operation_parent_id` | Parent operation for correlation | Same as above |
| `error_code_text` | Error descriptions | Would appear on failed generative calls or action errors |
| `message` | Input to generative answers | Populated on `GenerativeAnswers` events (not present in this dataset) |
| `result` | Output from generative answers | Same as above |
| `summary` | Summary text | Populated on certain completion events |

### 3.3 Design Mode vs Production

| Characteristic | Design Mode (`"True"`) | Production (`"False"`) |
|---------------|----------------------|----------------------|
| Channel | `pva-studio` | `msteams` |
| Event count | 86 | 41 |
| Conversations | 9 | 1 |
| `from_name` on BMR | Never populated | Always `"Richard Young"` |
| `recipient_name` on BMS | Never populated | Always user's display name |
| `user_id` format | UUID (`ac54f4e8-...`) | Teams ID (`29:1W6aRX...`) |
| `recipient_id` (on BMR) | `Default-4c10d796.../...` | `28:c40c1118-...` |
| `conversation_id` format | UUID | Long Teams thread ID (`a:1EBqwy...`) |
| Empty-text BMS events | Never | 3 events (typing indicators, system messages) |
| `installationUpdate` | Never | 1 event |
| `invoke` / `messageReaction` | Never | 1 each |

---

## 4. Data Patterns and Relationships

### 4.1 Conversation Structure

A conversation is identified by `conversation_id` and has a 1:1 mapping with `session_id` in the observed data. Each conversation starts with a session initialization sequence and may contain multiple user-agent turns.

**Session initialization sequence (always present):**

```
BotMessageReceived (activity_type="event", text=null)  -- session init event
  TopicStart (topic_name="*.topic.ConversationStart")
    TopicAction (kind="SendActivity", action_id="sendMessage_M0LuhV")
  TopicEnd (topic_name="*.topic.ConversationStart")
BotMessageSend (text="Hello, I'm Agent. How can I help?", speak="...")
```

This produces the initial greeting. The `speak` field contains the TTS version.

### 4.2 Turn Patterns

A "turn" is a user query and the corresponding bot response(s). The bridge splits conversations into turns at each `BotMessageReceived` with `activity_type="message"`.

**Simple greeting turn (topic-based, no AI):**

```
BotMessageReceived (activity_type="message", text="hello")
  TopicStart (topic_name="*.topic.Greeting")
    TopicAction (kind="SendActivity", action_id="sendMessage_abmysR")
    TopicAction (kind="CancelAllDialogs", action_id="cancelAllDialogs_01At22")
  TopicStart (topic_name="PowerVirtualAgentRoot")
BotMessageSend (text="Hello, how can I help you today?", speak="...")
```

**AI-powered turn (generative agent):**

```
BotMessageReceived (activity_type="message", text="what is copilot and arize ax integration details")
  TopicStart (topic_name="*.agent.Agent_OM0")
    AgentStarted (agent_type="SubAgent", agent_inputs={"Task":"..."})
    AgentCompleted (agent_type="SubAgent", agent_outputs={schema})
    AgentCompleted (agent_type="SubAgent", agent_outputs={schema})   -- duplicate
  BotMessageSend (text="**Copilot and Arize AX Integration Details**...")  -- detailed response
  BotMessageSend (text="The integration between Copilot...")               -- summary response
```

### 4.3 Event Ordering Rules

1. `BotMessageReceived` always precedes the corresponding `TopicStart`
2. `TopicStart` always precedes `TopicAction` / `AgentStarted` within its window
3. `TopicEnd` (when present) always follows the last action within a topic
4. `BotMessageSend` follows after topic processing completes
5. Multiple `BotMessageSend` events can follow a single turn (detailed + summary)
6. `AgentStarted` is always followed by one or more `AgentCompleted` events
7. The timestamp gap between events varies: initialization events are milliseconds apart; AI responses take seconds

### 4.4 Topic Nesting

Topics can nest or chain:

1. **ConversationStart** -- short-lived, always has TopicEnd, produces greeting
2. **Greeting** -- triggered by "hello", has `SendActivity` then `CancelAllDialogs` which chains to:
3. **PowerVirtualAgentRoot** -- the fallback root topic after dialog cancellation, never has TopicEnd
4. **Agent_OM0** -- generative AI agent topic, contains AgentStarted/AgentCompleted pairs, never has TopicEnd

### 4.5 Session and Conversation Relationship

In observed data, the relationship is 1:1:

| Session (Base64 hash) | Conversation (UUID) |
|----------------------|-------------------|
| `h7OGCan4x...` | `38f5a365-...` |
| `D62zt4C3w...` | `ec21adf2-...` |
| `GcRq+wDZp...` | `80b24afc-...` |
| etc. | etc. |

The bridge uses `session_id` from the first event of each conversation as the value for `session.id` in OpenInference. In multi-turn conversations (same session_id), turns are split but share the same session identity.

### 4.6 Dual BotMessageSend Pattern

When the generative AI agent responds, two `BotMessageSend` events are commonly emitted:
1. **First send:** Detailed response with markdown formatting, citations, and references (appears ~0-1 seconds after `AgentCompleted`)
2. **Second send:** Condensed summary of the same response (appears ~5-6 seconds later)

Both target the same `recipient_id`. The bridge captures both as output messages.

---

## 5. Internal Models

### 5.1 AppInsightsEvent (Extraction Model)

**File:** `/Users/richardyoung/Documents/msft-copilot-integration/copilot-insights-bridge/src/extraction/models.py`

Pydantic model that normalizes raw App Insights query rows. Handles:
- `customDimensions` arriving as JSON string or dict
- Case-insensitive field lookups (camelCase and PascalCase)
- User ID resolution chain: `userId` -> `fromId` -> `user_Id`
- Session ID resolution: `session_Id` -> `dims.sessionId`

```python
class AppInsightsEvent(BaseModel):
    timestamp: datetime
    name: str
    operation_id: str = ""
    operation_parent_id: str = ""
    session_id: str = ""
    conversation_id: str = ""
    user_id: str = ""
    channel_id: str = ""
    topic_name: Optional[str] = None
    topic_id: Optional[str] = None
    kind: Optional[str] = None
    text: Optional[str] = None
    from_id: Optional[str] = None
    from_name: Optional[str] = None
    recipient_id: Optional[str] = None
    recipient_name: Optional[str] = None
    activity_type: Optional[str] = None
    error_code_text: Optional[str] = None
    message: Optional[str] = None
    result: Optional[str] = None
    summary: Optional[str] = None
    design_mode: Optional[str] = None
    action_id: Optional[str] = None
    agent_type: Optional[str] = None
    agent_inputs: Optional[str] = None
    agent_outputs: Optional[str] = None
    speak: Optional[str] = None
```

**customDimensions field mapping:**

| App Insights `customDimensions` Key(s) | Model Field |
|---------------------------------------|-------------|
| `conversationId` | `conversation_id` |
| `userId`, `fromId`, or top-level `user_Id` | `user_id` |
| `channelId` | `channel_id` |
| `topicName`, `TopicName` | `topic_name` |
| `topicId`, `TopicId` | `topic_id` |
| `kind`, `Kind` | `kind` |
| `text` | `text` |
| `fromId` | `from_id` |
| `fromName` | `from_name` |
| `recipientId` | `recipient_id` |
| `recipientName` | `recipient_name` |
| `activityType`, `type` | `activity_type` |
| `errorCodeText` | `error_code_text` |
| `message` | `message` |
| `result` | `result` |
| `summary` | `summary` |
| `designMode`, `DesignMode` | `design_mode` |
| `actionId`, `ActionId` | `action_id` |
| `agentType`, `AgentType` | `agent_type` |
| `agentInputs`, `AgentInputs` | `agent_inputs` |
| `agentOutputs`, `AgentOutputs` | `agent_outputs` |
| `speak` | `speak` |

### 5.2 SpanNode (Reconstruction Model)

**File:** `/Users/richardyoung/Documents/msft-copilot-integration/copilot-insights-bridge/src/reconstruction/span_models.py`

Internal tree node representing a logical span derived from one or more App Insights events.

```python
class SpanKind(Enum):
    AGENT = "AGENT"
    CHAIN = "CHAIN"
    LLM   = "LLM"
    TOOL  = "TOOL"

@dataclass
class SpanNode:
    name: str                          # Span display name
    span_kind: SpanKind                # AGENT, CHAIN, LLM, or TOOL
    start_time: datetime               # Earliest event timestamp
    end_time: datetime                 # Latest event timestamp
    children: list[SpanNode]           # Child spans
    input_messages: list[str]          # User input text(s)
    output_messages: list[str]         # Bot response text(s)
    errors: list[str]                  # Error messages
    conversation_id: str               # Conversation identifier
    session_id: str                    # Session identifier
    user_id: str                       # User identifier
    channel_id: str                    # Channel identifier
    topic_name: Optional[str]          # Topic name
    topic_id: Optional[str]            # Topic ID
    tool_name: Optional[str]           # Tool/action name (TOOL spans)
    llm_input: Optional[str]           # LLM input text (LLM spans)
    llm_output: Optional[str]          # LLM output text (LLM spans)
    agent_type: Optional[str]          # Agent type (LLM spans from AgentStarted)
    action_id: Optional[str]           # Action ID (TOOL spans)
    raw_events: list[Any]              # Source events for debugging
```

---

## 6. Trace Tree Reconstruction

**File:** `/Users/richardyoung/Documents/msft-copilot-integration/copilot-insights-bridge/src/reconstruction/tree_builder.py`

### 6.1 Processing Pipeline

```
Flat events -> Group by conversation -> Split into turns -> Build tree per turn
```

1. **Group by conversation:** Events grouped by `conversation_id` (fallback: `session_id`, then `operation_id`)
2. **Split into turns:** Each `BotMessageReceived` with `activity_type="message"` (or null) starts a new turn. Pre-turn events (system/init events before the first user message) are merged into the first turn.
3. **Build tree per turn:** One root `AGENT` span per turn, with `CHAIN` children for topics and `LLM`/`TOOL` grandchildren for actions.

### 6.2 Turn Splitting Logic

Events are split into turns at each user message. The definition of a "user message" is:

```python
is_user_message = (
    event.name == "BotMessageReceived"
    and event.activity_type not in {"event", "installationUpdate", "invoke", "messageReaction"}
)
```

Non-message activity types (`event`, `installationUpdate`, `invoke`, `messageReaction`) do NOT start new turns; they are included in the current/adjacent turn.

### 6.3 Resulting Span Tree Hierarchy

```
AGENT (root: "Copilot Studio Conversation")
  |-- session_id, user_id, conversation_id, channel_id
  |-- input_messages: [user query text from orphan BotMessageReceived]
  |-- output_messages: [propagated from children]
  |
  +-- CHAIN (topic: "auto_agent_Y6JvM.agent.Agent_OM0")
  |     |-- input_messages: [user text from BotMessageReceived within topic]
  |     |-- output_messages: [bot text from BotMessageSend within topic]
  |     |
  |     +-- LLM ("AgentCall")
  |     |     |-- llm_input: Task from AgentStarted.agent_inputs
  |     |     |-- llm_output: text from subsequent BotMessageSend
  |     |     |-- agent_type: "SubAgent"
  |     |     |-- start_time: AgentStarted timestamp
  |     |     |-- end_time: AgentCompleted timestamp
  |     |
  |     +-- TOOL ("SendActivity")
  |           |-- tool_name: "SendActivity"
  |           |-- action_id: "sendMessage_M0LuhV"
  |
  +-- CHAIN (topic: "auto_agent_Y6JvM.topic.Greeting")
        |-- TOOL ("SendActivity")
        |-- TOOL ("CancelAllDialogs")
```

### 6.4 Topic Window Detection

The tree builder uses a stack-based algorithm with fuzzy name matching:

1. Each `TopicStart` opens a new window on the stack
2. Each `TopicEnd` closes the matching window (fuzzy match on name)
3. A new `TopicStart` for the same topic name implicitly closes the previous window
4. Unclosed windows at the end are closed at the last event timestamp
5. Non-structural events (`BotMessageReceived`, `BotMessageSend`, `AgentStarted`, etc.) are assigned to topic windows by:
   - First pass: Match by `topic_id` or `topic_name` within the time range (most recent window first)
   - Fallback: Match by time range alone
   - Events outside all windows become "orphans" attached to the root span

### 6.5 Fuzzy Topic Name Matching

```python
def _topic_names_match(name_a, name_b):
    # "auto_agent_Y6JvM.topic.Greeting" -> "Greeting"
    # Strips the prefix portion before comparing
```

This handles the naming discrepancy where `TopicAction` uses short names (e.g., `"Greeting"`) while `TopicStart`/`TopicEnd` use fully-qualified names (e.g., `"auto_agent_Y6JvM.topic.Greeting"`).

### 6.6 Event-to-Span Mapping Rules

| Source Event | Span Type | Span Name | Input Source | Output Source |
|-------------|-----------|-----------|--------------|---------------|
| Turn boundary | `AGENT` | `"Copilot Studio Conversation"` | Orphan `BotMessageReceived.text` | Propagated from children |
| Topic window | `CHAIN` | `topic_name` from TopicStart | `BotMessageReceived.text` within window | `BotMessageSend.text` within window |
| `GenerativeAnswers` | `LLM` | `"GenerativeAnswers"` | `event.message` | `event.result` |
| `AgentStarted`/`AgentCompleted` | `LLM` | `"AgentCall"` | `agent_inputs.Task` | `BotMessageSend.text` after AgentCompleted |
| `TopicAction` / `Action` | `TOOL` | `event.kind` or `event.action_id` | `event.text` | -- |

### 6.7 Context Propagation

After tree construction:
1. Child chain outputs are copied up to the root if root has no outputs (ensures Arize shows bot response on root span)
2. All descendants inherit root's `user_id` and `session_id` (fills blanks from raw telemetry where child events lack these fields)

---

## 7. OpenInference Attribute Mapping

**File:** `/Users/richardyoung/Documents/msft-copilot-integration/copilot-insights-bridge/src/transformation/mapper.py`

### 7.1 Core Attribute Mapping

| SpanNode Property | OpenInference Attribute | Value |
|-------------------|------------------------|-------|
| `span_kind` | `openinference.span.kind` | `"AGENT"`, `"CHAIN"`, `"LLM"`, or `"TOOL"` |
| `input_messages` (joined) | `input.value` | Newline-joined user input texts |
| -- | `input.mime_type` | `"text/plain"` (when input present) |
| `output_messages` (joined) | `output.value` | Newline-joined bot response texts |
| -- | `output.mime_type` | `"text/plain"` (when output present) |
| `session_id` | `session.id` | Base64 session hash from App Insights |
| `user_id` | `user.id` | UUID or Teams user ID |
| metadata dict | `metadata` | JSON string (see below) |
| tags list | `tag.tags` | List of strings |

### 7.2 Metadata JSON Structure

```json
{
  "conversation_id": "80b24afc-7655-4c06-841a-c6e396ced301",
  "channel_id": "pva-studio",
  "topic_name": "auto_agent_Y6JvM.agent.Agent_OM0",     // optional
  "agent_type": "SubAgent",                               // optional
  "action_id": "sendMessage_M0LuhV"                       // optional
}
```

Fields `topic_name`, `agent_type`, and `action_id` are included only when non-null on the SpanNode.

### 7.3 Tags

Tags always include `channel_id` and optionally `topic_name`:

```python
tags = [node.channel_id]                    # e.g., ["pva-studio"]
if node.topic_name:
    tags.append(node.topic_name)            # e.g., ["pva-studio", "Greeting"]
```

### 7.4 LLM-Specific Attributes

When `span_kind == SpanKind.LLM`:

| SpanNode Property | OpenInference Attribute | Value |
|-------------------|------------------------|-------|
| `agent_type` | `llm.model_name` | `"copilot-studio-subagent"` if `agent_type == "SubAgent"`, else `"copilot-studio-generative"` |
| `llm_input` | `llm.input_messages.0.message.role` | `"user"` |
| `llm_input` | `llm.input_messages.0.message.content` | Task text from AgentStarted |
| `llm_output` | `llm.output_messages.0.message.role` | `"assistant"` |
| `llm_output` | `llm.output_messages.0.message.content` | Response text from BotMessageSend |

### 7.5 TOOL-Specific Attributes

When `span_kind == SpanKind.TOOL`:

| SpanNode Property | OpenInference Attribute | Value |
|-------------------|------------------------|-------|
| `tool_name` | `tool.name` | e.g., `"SendActivity"`, `"CancelAllDialogs"` |
| `input_messages` or `llm_input` | `input.value` | Tool input text (fallback chain) |

### 7.6 GenAI Passthrough Mapping

When `gen_ai.*` attributes are provided (from raw telemetry or external enrichment), they override the derived values:

| Source Key | Destination Key |
|-----------|----------------|
| `gen_ai.operation.name` | `openinference.span.kind` |
| `gen_ai.request.model` | `llm.model_name` |
| `gen_ai.usage.input_tokens` | `llm.token_count.prompt` |
| `gen_ai.usage.output_tokens` | `llm.token_count.completion` |

Note: Token counts are not available in the current Copilot Studio telemetry. This mapping exists for future compatibility if Microsoft adds token usage reporting.

### 7.7 Session ID and User ID Derivation

**`session.id`:** Taken directly from the `session_id` field of the first event in the conversation. This is a Base64-encoded hash assigned by Copilot Studio (e.g., `"GcRq+wDZpgO+BiwAfVTkHMUhX7usAaBuykLrrWAnXzE="`). All turns within the same conversation share this value, enabling session-level analysis in Arize.

**`user.id`:** Derived via a priority chain:
1. First `BotMessageReceived` with `activity_type="message"` and non-empty `from_id` in the turn
2. Fallback: `user_id` from the first event in the conversation
3. Propagated to all descendant spans that lack a `user_id`

---

## 8. OTel Span Export

**File:** `/Users/richardyoung/Documents/msft-copilot-integration/copilot-insights-bridge/src/export/span_builder.py`

### 8.1 Span Builder Architecture

The `SpanBuilder` creates real OTel SDK spans from the `SpanNode` tree. It is designed for *historical* span export, meaning start/end times and parent-child relationships are explicitly set rather than captured from live instrumentation.

### 8.2 Span Creation Process

```
For each turn:
  1. Root AGENT span created with no parent context (SDK assigns random trace_id)
  2. For each child CHAIN span:
     - Created with parent context linking to root's span_id and trace_id
     3. For each grandchild LLM/TOOL span:
        - Created with parent context linking to CHAIN's span_id and trace_id
```

### 8.3 Key Implementation Details

| Aspect | Implementation |
|--------|---------------|
| **Trace ID** | SDK-assigned random ID for the root span; inherited by all children |
| **Span ID** | SDK-assigned for each span; actual value read back via `span.get_span_context().span_id` |
| **Parent linkage** | Uses `NonRecordingSpan` with `SpanContext` to represent historical parent |
| **Timestamps** | Converted from Python `datetime` to nanoseconds since epoch (`int(dt.timestamp() * 1e9)`) |
| **Errors** | Recorded as `exception` events on spans; span status set to `ERROR` |
| **Attributes** | Set via the `attributes_map` callable (OpenInferenceMapper) |
| **Traversal** | Depth-first recursion over SpanNode tree |

### 8.4 Resulting OTel Span Structure

```
Trace (random trace_id)
  |
  +-- Span: "Copilot Studio Conversation" (kind=AGENT)
        attributes:
          openinference.span.kind = "AGENT"
          input.value = "what is copilot and arize ax integration details"
          output.value = "**Copilot and Arize AX Integration Details**..."
          session.id = "GcRq+wDZpgO+BiwAfVTkHMUhX7usAaBuykLrrWAnXzE="
          user.id = "ac54f4e8-737f-472c-901f-ca8c51748964"
          metadata = '{"conversation_id":"80b24afc-...","channel_id":"pva-studio"}'
          tag.tags = ["pva-studio"]
        |
        +-- Span: "auto_agent_Y6JvM.agent.Agent_OM0" (kind=CHAIN)
              attributes:
                openinference.span.kind = "CHAIN"
                session.id = "GcRq+wDZpgO+..."
                user.id = "ac54f4e8-..."
                metadata = '{"conversation_id":"80b24afc-...","channel_id":"pva-studio","topic_name":"auto_agent_Y6JvM.agent.Agent_OM0"}'
                tag.tags = ["pva-studio", "auto_agent_Y6JvM.agent.Agent_OM0"]
              |
              +-- Span: "AgentCall" (kind=LLM)
                    attributes:
                      openinference.span.kind = "LLM"
                      llm.model_name = "copilot-studio-subagent"
                      llm.input_messages.0.message.role = "user"
                      llm.input_messages.0.message.content = "Provide details about the integration..."
                      llm.output_messages.0.message.role = "assistant"
                      llm.output_messages.0.message.content = "**Copilot and Arize AX Integration..."
                      session.id = "GcRq+wDZpgO+..."
                      user.id = "ac54f4e8-..."
                      metadata = '{"conversation_id":"80b24afc-...","channel_id":"pva-studio","topic_name":"auto_agent_Y6JvM.agent.Agent_OM0","agent_type":"SubAgent"}'
```

---

## 9. End-to-End Data Flow Example

This traces a single user question through the entire pipeline.

### 9.1 Raw App Insights Events

User asks: *"what is copilot and arize ax integration details"*

```
20:23:00.883  BotMessageReceived  activity_type="message"  text="what is copilot and arize ax integration details"
20:23:02.426  TopicStart          topic_name="auto_agent_Y6JvM.agent.Agent_OM0"
20:23:02.430  AgentStarted        agent_type="SubAgent"  agent_inputs={"Task":"Provide details about..."}
20:23:10.191  AgentCompleted      agent_type="SubAgent"  agent_outputs={schema}
20:23:15.819  AgentCompleted      agent_type="SubAgent"  agent_outputs={schema}
20:23:15.820  BotMessageSend      text="**Copilot and Arize AX Integration Details**..."
20:23:21.269  BotMessageSend      text="The integration between Copilot and Arize AX is..."
```

### 9.2 After Extraction (AppInsightsEvent)

7 `AppInsightsEvent` Pydantic objects created with normalized fields. All share `conversation_id="80b24afc-..."`, `session_id="GcRq+wDZp..."`.

### 9.3 After Tree Building (SpanNode)

```
SpanNode(
  name="Copilot Studio Conversation",
  span_kind=AGENT,
  start_time=20:23:00.883,
  end_time=20:23:21.269,
  session_id="GcRq+wDZp...",
  user_id="ac54f4e8-...",
  input_messages=["what is copilot and arize ax integration details"],
  output_messages=["**Copilot and Arize AX...", "The integration between..."],
  children=[
    SpanNode(
      name="auto_agent_Y6JvM.agent.Agent_OM0",
      span_kind=CHAIN,
      start_time=20:23:02.426,
      end_time=20:23:21.269,  # closed at last event (no TopicEnd)
      children=[
        SpanNode(
          name="AgentCall",
          span_kind=LLM,
          start_time=20:23:02.430,
          end_time=20:23:15.819,  # updated by last AgentCompleted
          llm_input="Provide details about the integration between Copilot and Arize AX.",
          llm_output="**Copilot and Arize AX Integration Details**...",
          agent_type="SubAgent",
        )
      ]
    )
  ]
)
```

### 9.4 After Mapping (OpenInference Attributes)

Root AGENT span attributes:
```
openinference.span.kind = "AGENT"
input.value = "what is copilot and arize ax integration details"
input.mime_type = "text/plain"
output.value = "**Copilot and Arize AX Integration Details**...\nThe integration between..."
output.mime_type = "text/plain"
session.id = "GcRq+wDZpgO+BiwAfVTkHMUhX7usAaBuykLrrWAnXzE="
user.id = "ac54f4e8-737f-472c-901f-ca8c51748964"
metadata = '{"conversation_id":"80b24afc-7655-4c06-841a-c6e396ced301","channel_id":"pva-studio"}'
tag.tags = ["pva-studio"]
```

LLM child span attributes:
```
openinference.span.kind = "LLM"
llm.model_name = "copilot-studio-subagent"
llm.input_messages.0.message.role = "user"
llm.input_messages.0.message.content = "Provide details about the integration between Copilot and Arize AX."
llm.output_messages.0.message.role = "assistant"
llm.output_messages.0.message.content = "**Copilot and Arize AX Integration Details**..."
session.id = "GcRq+wDZpgO+BiwAfVTkHMUhX7usAaBuykLrrWAnXzE="
user.id = "ac54f4e8-737f-472c-901f-ca8c51748964"
metadata = '{"conversation_id":"80b24afc-...","channel_id":"pva-studio","topic_name":"auto_agent_Y6JvM.agent.Agent_OM0","agent_type":"SubAgent"}'
tag.tags = ["pva-studio", "auto_agent_Y6JvM.agent.Agent_OM0"]
```

### 9.5 After Export (OTel SDK Spans)

Exported via `SpanBuilder` to OTel SDK:
- 3 spans emitted (AGENT root, CHAIN child, LLM grandchild)
- All share the same `trace_id` (SDK-assigned)
- Parent-child relationships established via `SpanContext` linkage
- Timestamps converted to nanoseconds since epoch
- Attributes flattened into span attribute dictionaries
- Exported via configured OTLP exporter to Arize AX

---

## Appendix A: Complete Attribute Reference

| OpenInference Attribute | Type | Set On | Source |
|-------------------------|------|--------|--------|
| `openinference.span.kind` | string | All spans | `SpanNode.span_kind.value` |
| `input.value` | string | AGENT, CHAIN, TOOL | `"\n".join(node.input_messages)` or `node.llm_input` |
| `input.mime_type` | string | When input present | `"text/plain"` |
| `output.value` | string | AGENT, CHAIN | `"\n".join(node.output_messages)` |
| `output.mime_type` | string | When output present | `"text/plain"` |
| `session.id` | string | All spans | `node.session_id` |
| `user.id` | string | All spans | `node.user_id` |
| `metadata` | JSON string | All spans | Composite of conversation_id, channel_id, topic_name, agent_type, action_id |
| `tag.tags` | list[string] | All spans | `[channel_id]` + optional `[topic_name]` |
| `llm.model_name` | string | LLM spans | `"copilot-studio-subagent"` or `"copilot-studio-generative"` |
| `llm.input_messages.0.message.role` | string | LLM spans | `"user"` |
| `llm.input_messages.0.message.content` | string | LLM spans | `node.llm_input` |
| `llm.output_messages.0.message.role` | string | LLM spans | `"assistant"` |
| `llm.output_messages.0.message.content` | string | LLM spans | `node.llm_output` |
| `llm.token_count.prompt` | int | LLM spans (when GenAI attrs provided) | `gen_ai.usage.input_tokens` |
| `llm.token_count.completion` | int | LLM spans (when GenAI attrs provided) | `gen_ai.usage.output_tokens` |
| `tool.name` | string | TOOL spans | `node.tool_name` |

## Appendix B: Event Type to Span Kind Mapping

| App Insights Event | Condition | Resulting Span Kind | Span Name |
|-------------------|-----------|-------------------|-----------|
| Turn boundary (virtual) | Always | `AGENT` | `"Copilot Studio Conversation"` |
| `TopicStart`/`TopicEnd` pair | Always | `CHAIN` | Topic name from TopicStart |
| `GenerativeAnswers` | Within topic window | `LLM` | `"GenerativeAnswers"` |
| `AgentStarted` | Within topic window | `LLM` | `"AgentCall"` |
| `TopicAction` or `Action` | Within topic window | `TOOL` | `event.kind` or `event.action_id` or `"UnknownAction"` |
| `BotMessageReceived` | Orphan (outside topic) | Contributes to parent AGENT `input_messages` | -- |
| `BotMessageReceived` | Within topic window | Contributes to parent CHAIN `input_messages` | -- |
| `BotMessageSend` | Orphan (outside topic) | Contributes to parent AGENT `output_messages` | -- |
| `BotMessageSend` | Within topic window | Contributes to parent CHAIN `output_messages` | -- |
| `AgentCompleted` | After `AgentStarted` | Updates pending LLM span `end_time` | -- |
| `TopicEnd` | Closes topic window | -- (structural only) | -- |
