# Partner Data Validation Checklist

Partner: ________________
Submission Version: ________________
Date: ________________
Validator: ________________

---

## 1. File Format & Structure

- [ ] File is valid JSON
- [ ] Contains array of events
- [ ] Each event has required fields:
  - [ ] `timestamp`
  - [ ] `customDimensions`
  - [ ] `operation_Id` (conversation ID)
- [ ] File size reasonable (< 100MB for initial testing)

**Notes**:
```

```

---

## 2. Event Coverage

- [ ] Contains `ConversationUpdate` events (conversation boundaries)
- [ ] Contains `ImBack` events (user messages/turns)
- [ ] Contains `Activity` events (topic lifecycle)
- [ ] Contains at least one complete conversation (start to end)
- [ ] Time range is reasonable (not too sparse, not too old)

**Event counts**:
- ConversationUpdate: _______
- ImBack: _______
- Activity: _______
- Other: _______
- **Total**: _______

**Date range**: __________ to __________

---

## 3. Conversation Quality

- [ ] Can identify distinct conversations (unique conversation IDs)
- [ ] Conversations have clear start events
- [ ] User messages are present
- [ ] Bot responses are present
- [ ] Topics are triggered and tracked

**Conversation count**: _______
**Average events per conversation**: _______

---

## 4. Feature Detection

### Knowledge Search
- [ ] `GenerativeAnswersInvoked` events present
- [ ] `GenerativeAnswersCompleted` events present
- [ ] Search queries identifiable
- [ ] Search results captured

**Knowledge search conversations**: _______

### Custom Topics
- [ ] `TopicStart` events present
- [ ] Topic names identifiable
- [ ] Mix of system and custom topics
- [ ] Topic state transitions tracked

**Custom topics detected**: _______
**System topics detected**: _______

### Generative Answers (LLM)
- [ ] LLM responses identifiable
- [ ] Prompt/response pairs complete
- [ ] Token counts available (if any)

**LLM responses**: _______

### Actions/Tools
- [ ] Power Automate flows (if applicable)
- [ ] Custom actions (if applicable)
- [ ] External API calls (if applicable)

**Tool calls**: _______

---

## 5. Data Completeness

### Required Fields
- [ ] `activityId` - Present and unique
- [ ] `conversation_id` - Present for all events
- [ ] `activityType` - Present and valid
- [ ] `locale` - Present (or acceptable if missing)

### Optional but Valuable
- [ ] `from_name` (bot/user identification)
- [ ] `recipient_name`
- [ ] `session_Id` (channel session)
- [ ] `text` (message content)

**Missing critical fields**: _______________

---

## 6. Data Quality Issues

### Missing Events
- [ ] No missing `TopicStart` for topics
- [ ] TopicEnd coverage: _______% (⚠️ if < 50%)
- [ ] No orphaned events (events without conversation context)

### Timestamp Issues
- [ ] Timestamps are sequential within conversations
- [ ] No large gaps (> 1 hour) mid-conversation
- [ ] Timezone consistent

### Identifiers
- [ ] Conversation IDs stable throughout conversation
- [ ] Activity IDs unique
- [ ] Session IDs consistent (if present)

**Issues found**: _______

---

## 7. Privacy & Sanitization

- [ ] PII reviewed (if processing real data)
- [ ] Sensitive information sanitized (if needed)
- [ ] User consent obtained (if real user data)
- [ ] Complies with data sharing policies

**Sanitization applied**: Yes / No
**Sanitization method**: _______________

---

## 8. Bridge Processing

- [ ] File loads without errors
- [ ] Events parse successfully
- [ ] Conversations reconstruct into traces
- [ ] Spans create successfully
- [ ] Parent-child relationships valid

**Processing result**: Pass / Fail
**Error messages** (if any):
```

```

---

## 9. Arize Export

- [ ] Spans export to Arize successfully
- [ ] Trace count matches expectation
- [ ] Spans visible in Arize UI
- [ ] Metadata fields populated:
  - [ ] `knowledge_search`
  - [ ] `system_topic`
  - [ ] `locale`
  - [ ] `topic_type`
  - [ ] `channel`

**Traces exported**: _______
**Arize project**: _______________
**Verification status**: Pass / Fail

---

## 10. Partner Communication

- [ ] Analysis report generated
- [ ] Issues documented
- [ ] Recommendations provided
- [ ] Follow-up items identified

**Report sent**: Yes / No
**Partner response**: _______________

---

## Overall Assessment

**Status**: ✅ Pass / ⚠️ Pass with Issues / ❌ Fail

**Compatibility**: _______% (0-100%)

**Summary**:
```




```

**Next steps**:
1.
2.
3.

---

**Validator signature**: _______________
**Date completed**: _______________
