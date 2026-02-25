╭────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ Plan to implement                                                                                                  │
│                                                                                                                    │
│ Plan: OpenInference & App Insights Mapping Completeness Fixes                                                      │
│                                                                                                                    │
│ Context                                                                                                            │
│                                                                                                                    │
│ After reviewing the OpenInference semantic conventions spec and the Copilot Studio App Insights event research doc │
│  against our current implementation, 8 gaps were identified. This plan addresses each gap in priority order to     │
│ bring our bridge into fuller compliance with OpenInference conventions and extract more value from available       │
│ telemetry.                                                                                                         │
│                                                                                                                    │
│ Files to Modify                                                                                                    │
│                                                                                                                    │
│ 1. src/reconstruction/span_models.py — Add agent_name field, RETRIEVER span kind                                   │
│ 2. src/reconstruction/tree_builder.py — Add ConversationStart to known events, use agent_outputs on                │
│ AgentCompleted, extract agent name, create RETRIEVER spans                                                         │
│ 3. src/transformation/mapper.py — Add agent.name, llm.system, llm.provider, tool.id, summary metadata              │
│ 4. src/export/span_builder.py — Add exception.type to error events                                                 │
│ 5. tests/test_reconstruction.py — Tests for RETRIEVER spans, ConversationStart, agent_outputs                      │
│ 6. tests/test_transformation.py — Tests for new attributes                                                         │
│ 7. tests/test_export.py — Test for exception.type                                                                  │
│                                                                                                                    │
│ Implementation Steps                                                                                               │
│                                                                                                                    │
│ Step 1: Add ConversationStart to known events (Trivial — bug prevention)                                           │
│                                                                                                                    │
│ File: src/reconstruction/tree_builder.py                                                                           │
│                                                                                                                    │
│ Add "ConversationStart" to _KNOWN_TOPIC_EVENTS set so it doesn't produce spurious TOOL spans via the catch-all     │
│ handler.                                                                                                           │
│                                                                                                                    │
│ Step 2: Add RETRIEVER span kind and create synthetic retriever spans (Medium)                                      │
│                                                                                                                    │
│ File: src/reconstruction/span_models.py                                                                            │
│ - Add RETRIEVER = "RETRIEVER" to SpanKind enum                                                                     │
│                                                                                                                    │
│ File: src/reconstruction/tree_builder.py                                                                           │
│ - In _detect_knowledge_search(): when knowledge search is detected, instead of just setting a flag, also create a  │
│ synthetic RETRIEVER child span on the root:                                                                        │
│ child = SpanNode(                                                                                                  │
│     name="KnowledgeSearch",                                                                                        │
│     span_kind=SpanKind.RETRIEVER,                                                                                  │
│     start_time=root.start_time,                                                                                    │
│     end_time=root.end_time,                                                                                        │
│     ...                                                                                                            │
│     knowledge_search_detected=True,                                                                                │
│ )                                                                                                                  │
│ root.children.append(child)                                                                                        │
│ - Populate the RETRIEVER span's input_messages from root's input and output_messages from root's output            │
│                                                                                                                    │
│ File: src/transformation/mapper.py                                                                                 │
│ - Add RETRIEVER span handling: no special attributes needed beyond what CHAIN gets (input/output/metadata) —       │
│ retrieval.documents requires document content which App Insights doesn't provide                                   │
│                                                                                                                    │
│ Step 3: Set llm.system and llm.provider on LLM spans (Trivial)                                                     │
│                                                                                                                    │
│ File: src/transformation/mapper.py                                                                                 │
│ - Add constants: LLM_SYSTEM = "llm.system", LLM_PROVIDER = "llm.provider"                                          │
│ - In the LLM-specific block, set:                                                                                  │
│   - attrs[LLM_SYSTEM] = "copilot-studio"                                                                           │
│   - attrs[LLM_PROVIDER] = "azure"                                                                                  │
│                                                                                                                    │
│ Step 4: Set agent.name on AGENT and sub-agent spans (Low)                                                          │
│                                                                                                                    │
│ File: src/reconstruction/span_models.py                                                                            │
│ - Add agent_name: Optional[str] = None field                                                                       │
│                                                                                                                    │
│ File: src/reconstruction/tree_builder.py                                                                           │
│ - In _build_conversation_tree(): extract agent name from topic name prefix (e.g., auto_agent_Y6JvM from            │
│ auto_agent_Y6JvM.topic.Greeting). Set root.agent_name.                                                             │
│ - In _build_topic_span() for AgentStarted: set pending_agent_span.agent_name from the topic name or agent_type.    │
│                                                                                                                    │
│ File: src/transformation/mapper.py                                                                                 │
│ - Add constant: AGENT_NAME = "agent.name"                                                                          │
│ - If node.agent_name is set, add attrs[AGENT_NAME] = node.agent_name                                               │
│                                                                                                                    │
│ Step 5: Set tool.id on TOOL spans from action_id (Trivial)                                                         │
│                                                                                                                    │
│ File: src/transformation/mapper.py                                                                                 │
│ - Add constant: TOOL_ID = "tool.id"                                                                                │
│ - In the TOOL-specific block, if node.action_id is set, add attrs[TOOL_ID] = node.action_id                        │
│                                                                                                                    │
│ Step 6: Add exception.type to error span events (Low)                                                              │
│                                                                                                                    │
│ File: src/export/span_builder.py                                                                                   │
│ - Change the error event from:                                                                                     │
│ span.add_event("exception", {"exception.message": error})                                                          │
│ - to:                                                                                                              │
│ span.add_event("exception", {                                                                                      │
│     "exception.type": error,                                                                                       │
│     "exception.message": error,                                                                                    │
│ })                                                                                                                 │
│ - (Using error_code_text as both type and message since that's all Copilot Studio provides.)                       │
│                                                                                                                    │
│ Step 7: Use agent_outputs from AgentCompleted events (Low)                                                         │
│                                                                                                                    │
│ File: src/reconstruction/tree_builder.py                                                                           │
│ - In the AgentCompleted handler (currently only updates end_time), also:                                           │
│   - Parse event.agent_outputs JSON to extract Summary or other structured output                                   │
│   - Set pending_agent_span.llm_output from the parsed output if not already set by a BotMessageSend                │
│                                                                                                                    │
│ Step 8: Map summary field to metadata (Trivial)                                                                    │
│                                                                                                                    │
│ File: src/reconstruction/span_models.py                                                                            │
│ - Add summary: Optional[str] = None field                                                                          │
│                                                                                                                    │
│ File: src/reconstruction/tree_builder.py                                                                           │
│ - In _build_topic_span() for GenerativeAnswers: set child.summary = event.summary                                  │
│                                                                                                                    │
│ File: src/transformation/mapper.py                                                                                 │
│ - If node.summary is set, add to metadata: metadata["summary"] = node.summary                                      │
│                                                                                                                    │
│ Step 9: Tests                                                                                                      │
│                                                                                                                    │
│ File: tests/test_reconstruction.py                                                                                 │
│ - Test RETRIEVER span created when knowledge search detected (with citations, without citations but                │
│ output-no-children)                                                                                                │
│ - Test RETRIEVER span NOT created for non-knowledge traces                                                         │
│ - Test ConversationStart doesn't create spurious TOOL span                                                         │
│ - Test agent_outputs populates llm_output on AgentCompleted                                                        │
│ - Test agent_name extracted from topic prefix                                                                      │
│                                                                                                                    │
│ File: tests/test_transformation.py                                                                                 │
│ - Test llm.system = "copilot-studio" on LLM spans                                                                  │
│ - Test llm.provider = "azure" on LLM spans                                                                         │
│ - Test agent.name set on AGENT spans                                                                               │
│ - Test tool.id set on TOOL spans with action_id                                                                    │
│ - Test summary in metadata when present                                                                            │
│                                                                                                                    │
│ File: tests/test_export.py                                                                                         │
│ - Test exception events include both exception.type and exception.message                                          │
│                                                                                                                    │
│ Not Implementing (confirmed platform limitations)                                                                  │
│                                                                                                                    │
│ - TimeDifference field: The research doc mentions this, but it's NOT present in our live App Insights data.        │
│ Copilot Studio doesn't appear to emit it for the event types we see. If it appears in future data, the extraction  │
│ model can be extended.                                                                                             │
│ - retrieval.documents with content: App Insights doesn't provide retrieved document bodies — only the final        │
│ response with citations.                                                                                           │
│ - llm.token_count.*: Not exposed by Copilot Studio.                                                                │
│ - llm.cost.*: Not exposed by Copilot Studio.                                                                       │
│ - llm.invocation_parameters: Not exposed by Copilot Studio.                                                        │
│                                                                                                                    │
│ Verification                                                                                                       │
│                                                                                                                    │
│ 1. pytest tests/ -v — all existing 100 tests pass (no regressions) + new tests pass                                │
│ 2. Run python scripts/diagnose_gaps.py live_data_dump.json — verify RETRIEVER spans appear for knowledge search    │
│ traces, agent names populated                                                                                      │
│ 3. Optionally re-export to Arize and verify new attributes visible in UI                                           │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

⏺ I'll start by reading the key source files to understand the current implementation before making changes.

⏺ Read 4 files (ctrl+o to expand)

⏺ Now let me read the test files and the extraction model.

⏺ Read 4 files (ctrl+o to expand)

⏺ Let me also check the conftest for fixtures.

⏺ Searched for 1 pattern, read 1 file (ctrl+o to expand)

⏺ Good, I have a complete picture of the codebase. Let me now run the existing tests to confirm baseline.

⏺ Bash(cd /Users/richardyoung/Documents/msft-copilot-integration/copilot-insights-bridge && python -m pytest tests/ -q
       2>&1 | tail -5)
  ⎿  <frozen importlib._bootstrap>:488
       <frozen importlib._bootstrap>:488: DeprecationWarning: Type google.protobuf.pyext._message.MessageMapConta
     iner uses PyType_Spec with a metaclass that has custom tp_new. This is deprecated and will no longer be allo
     … +4 lines (ctrl+o to expand)

⏺ 100 tests passing. Now I'll implement all the changes. The steps are largely independent at the file level, so I'll
  work through them systematically.

  Step 1: Add ConversationStart to known events

⏺ Update(src/reconstruction/tree_builder.py)
  ⎿  Added 1 line
      35      "BotMessageReceived", "BotMessageSend",
      36      "BotMessageUpdate", "BotMessageDelete",
      37      "TopicStart", "TopicEnd",
      38 +    "ConversationStart",                                                                             
      39  }
      40  
      41  # Regex to detect citation markers like [1], [2] in bot output

⏺ Step 2: Add RETRIEVER span kind and create synthetic retriever spans

⏺ Update(src/reconstruction/span_models.py)
  ⎿  Added 1 line
      14      AGENT = "AGENT"
      15      CHAIN = "CHAIN"
      16      LLM = "LLM"
      17 +    RETRIEVER = "RETRIEVER"                                                                          
      18      TOOL = "TOOL"
      19  
      20  

⏺ Now add agent_name and summary fields to SpanNode:

⏺ Update(src/reconstruction/span_models.py)
  ⎿  Added 2 lines
      44      llm_output: Optional[str] = None
      45      agent_type: Optional[str] = None
      46      action_id: Optional[str] = None
      47 +    agent_name: Optional[str] = None                                                                 
      48      locale: Optional[str] = None
      49 +    summary: Optional[str] = None                                                                    
      50      knowledge_search_detected: bool = False
      51      is_system_topic: bool = False
      52      raw_events: list[Any] = field(default_factory=list)

⏺ Now update _detect_knowledge_search in tree_builder.py to create synthetic RETRIEVER spans:

⏺ Update(src/reconstruction/tree_builder.py)
  ⎿  Added 20 lines
      602          - Root has *user input* and output but no child spans, meaning the
      603            orchestrator answered directly without triggering a topic.  Requires
      604            input to avoid false positives on system messages like CSAT feedback.
      605 +                                                                                                    
      606 +        When knowledge search is detected, a synthetic RETRIEVER child span is                      
      607 +        created on the root to represent the knowledge retrieval step in the                        
      608 +        trace tree (OpenInference convention).                                                      
      609          """
      610          has_input = bool(root.input_messages)
      611          has_output = bool(root.output_messages)
     ...
      615          elif has_input and has_output and not has_children:
      616              root.knowledge_search_detected = True
      617  
      618 +        if root.knowledge_search_detected:                                                          
      619 +            retriever = SpanNode(                                                                   
      620 +                name="KnowledgeSearch",                                                             
      621 +                span_kind=SpanKind.RETRIEVER,                                                       
      622 +                start_time=root.start_time,                                                         
      623 +                end_time=root.end_time,                                                             
      624 +                conversation_id=root.conversation_id,                                               
      625 +                session_id=root.session_id,                                                         
      626 +                user_id=root.user_id,                                                               
      627 +                channel_id=root.channel_id,                                                         
      628 +                input_messages=list(root.input_messages),                                           
      629 +                output_messages=list(root.output_messages),                                         
      630 +                knowledge_search_detected=True,                                                     
      631 +            )                                                                                       
      632 +            root.children.append(retriever)                                                         
      633 +                                                                                                    
      634      @staticmethod
      635      def _propagate_locale(root: SpanNode) -> None:
      636          """Copy the root's locale to all descendants that lack one."""

⏺ Step 3: Set llm.system and llm.provider on LLM spans

⏺ Update(src/transformation/mapper.py)
  ⎿  Added 4 lines
      27  LLM_TOKEN_COUNT_PROMPT = "llm.token_count.prompt"
      28  LLM_TOKEN_COUNT_COMPLETION = "llm.token_count.completion"
      29  TOOL_NAME = "tool.name"
      30 +TOOL_ID = "tool.id"                                                                                  
      31 +LLM_SYSTEM = "llm.system"                                                                            
      32 +LLM_PROVIDER = "llm.provider"                                                                        
      33 +AGENT_NAME = "agent.name"                                                                            
      34  
      35  MIME_TEXT_PLAIN = "text/plain"
      36  

⏺ Now add llm.system and llm.provider to the LLM-specific block:

⏺ Update(src/transformation/mapper.py)
  ⎿  Added 2 lines
      135                  attrs[LLM_MODEL_NAME] = "copilot-studio-subagent"
      136              else:
      137                  attrs[LLM_MODEL_NAME] = "copilot-studio-generative"
      138 +            attrs[LLM_SYSTEM] = "copilot-studio"                                                    
      139 +            attrs[LLM_PROVIDER] = "azure"                                                           
      140              if node.llm_input is not None:
      141                  attrs[f"{LLM_INPUT_MESSAGES}.0.message.role"] = "user"
      142                  attrs[f"{LLM_INPUT_MESSAGES}.0.message.content"] = node.llm_input
  ⎿  You're out of extra usage · resets Feb 23, 9pm (America/Los_Angeles)


