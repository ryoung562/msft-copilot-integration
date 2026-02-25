# Analysis Report: {partner_name}

**Date**: {date}
**Analyst**: {analyst_name}
**Submission**: {version}
**Status**: {status}

---

## Executive Summary

{summary_paragraph}

**Key Metrics**:
- ✅ Data validated: {validation_status}
- ⚠️ Issues found: {issue_count}
- 📊 Traces exported: {trace_count}
- 🎯 Compatibility: {compatibility_percentage}%

---

## Data Overview

### Volume
- **Total Events**: {event_count}
- **Conversations**: {conversation_count}
- **Date Range**: {date_start} to {date_end}
- **Time Span**: {duration_days} days

### Channels
{channels_list}

### Event Distribution
| Event Type | Count | Percentage |
|------------|-------|------------|
| ConversationUpdate | {conv_update_count} | {conv_update_pct}% |
| ImBack | {imback_count} | {imback_pct}% |
| Activity | {activity_count} | {activity_pct}% |
| Other | {other_count} | {other_pct}% |

---

## Feature Detection

### Knowledge Search
- **Traces with knowledge search**: {knowledge_search_count}
- **GenerativeAnswersInvoked events**: {gen_answers_count}
- **GenerativeAnswersCompleted events**: {gen_answers_complete_count}
- **Status**: {knowledge_search_status}

### System Topics
- **System topic spans**: {system_topic_count}
- **Most common**: {top_system_topics}

### Custom Topics
- **Custom topic spans**: {custom_topic_count}
- **Total unique topics**: {unique_topics_count}
- **Sample topics**: {sample_custom_topics}

### Generative Answers (LLM)
- **LLM spans detected**: {llm_count}
- **Average response tokens**: {avg_response_tokens}

### Actions/Tools
- **Tool spans detected**: {tool_count}
- **Tool types**: {tool_types_list}

---

## Data Quality Assessment

### Completeness
- [x] Conversation boundaries clear (ConversationUpdate events)
- [x] Turn structure identifiable (ImBack events)
- [x] Topic lifecycle events present (TopicStart)
- [ ] TopicEnd events: {topic_end_coverage}% coverage (⚠️ {missing_topic_end_count} missing)
- [x] Timestamps consistent

### Coverage
- **Locale information**: {locale_status}
- **User/bot identification**: {user_bot_status}
- **Session IDs**: {session_id_status}
- **Conversation IDs**: {conversation_id_status}

---

## Issues Found

{issues_section}

### Issue Details

#### 1. {issue_1_title} - {issue_1_severity}
- **Count**: {issue_1_count}
- **Impact**: {issue_1_impact}
- **Description**: {issue_1_description}
- **Recommendation**: {issue_1_recommendation}

#### 2. {issue_2_title} - {issue_2_severity}
- **Count**: {issue_2_count}
- **Impact**: {issue_2_impact}
- **Description**: {issue_2_description}
- **Recommendation**: {issue_2_recommendation}

---

## Compatibility Analysis

### Bridge Processing
- **Successfully reconstructed traces**: {successful_traces}
- **Failed traces**: {failed_traces}
- **Warnings**: {warning_count}

### OpenInference Mapping
- **Span creation**: {span_creation_status}
- **Parent-child linking**: {parent_child_status}
- **Attribute mapping**: {attribute_mapping_status}

### Arize Export
- **Export status**: {export_status}
- **Spans exported**: {spans_exported}
- **Verification**: {verification_status}

---

## Recommendations

### For Data Collection
{data_collection_recommendations}

### For Agent Configuration
{agent_config_recommendations}

### For Next Submission
{next_submission_recommendations}

---

## Next Steps

1. **Immediate** (Priority: High)
   {immediate_action_items}

2. **Short-term** (Priority: Medium)
   {short_term_action_items}

3. **Long-term** (Priority: Low)
   {long_term_action_items}

---

## Sample Conversations

### Conversation 1: {conv_1_id}
- **Turns**: {conv_1_turns}
- **Knowledge search**: {conv_1_knowledge}
- **Topics**: {conv_1_topics}
- **Duration**: {conv_1_duration}
- **Status**: {conv_1_status}

### Conversation 2: {conv_2_id}
- **Turns**: {conv_2_turns}
- **Knowledge search**: {conv_2_knowledge}
- **Topics**: {conv_2_topics}
- **Duration**: {conv_2_duration}
- **Status**: {conv_2_status}

---

## Appendix

### Files Processed
- **Source**: `{source_file_path}`
- **Size**: {file_size_mb} MB
- **Format**: Azure Application Insights JSON export

### Processing Details
- **Bridge version**: {bridge_version}
- **Processing time**: {processing_time_seconds}s
- **Test results**: {test_results}

---

**Thank you for participating in the Copilot Studio → Arize AX integration validation!**

For questions or follow-up, contact: {contact_email}
