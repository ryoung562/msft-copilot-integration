"""Tests for the extraction layer (models and queries)."""

from datetime import datetime, timezone

from src.extraction.models import AppInsightsEvent
from src.extraction.queries import build_custom_events_query


class TestAppInsightsEvent:
    def test_from_query_row_parses_all_fields(self, single_conversation_raw: list[dict]) -> None:
        row = single_conversation_raw[0]
        event = AppInsightsEvent.from_query_row(row)

        assert event.name == "BotMessageReceived"
        assert event.conversation_id == "conv-001"
        assert event.session_id == "sess-abc"
        assert event.user_id == "user-42"
        assert event.channel_id == "msteams"
        assert event.from_id == "user-42"
        assert event.from_name == "Alice"
        assert event.text == "How do I reset my password?"
        assert event.design_mode == "False"

    def test_from_query_row_optional_fields_default_to_none(
        self, single_conversation_raw: list[dict]
    ) -> None:
        row = single_conversation_raw[0]
        event = AppInsightsEvent.from_query_row(row)

        assert event.topic_name is None
        assert event.topic_id is None
        assert event.kind is None
        assert event.error_code_text is None
        assert event.message is None
        assert event.result is None

    def test_from_query_row_topic_start_has_topic_fields(
        self, single_conversation_raw: list[dict]
    ) -> None:
        row = single_conversation_raw[1]  # TopicStart
        event = AppInsightsEvent.from_query_row(row)

        assert event.name == "TopicStart"
        assert event.topic_name == "PasswordReset"
        assert event.topic_id == "topic-pw-reset"

    def test_from_query_row_generative_answers(
        self, single_conversation_raw: list[dict]
    ) -> None:
        row = single_conversation_raw[2]  # GenerativeAnswers
        event = AppInsightsEvent.from_query_row(row)

        assert event.name == "GenerativeAnswers"
        assert event.message == "How do I reset my password?"
        assert event.result is not None
        assert "self-service portal" in event.result

    def test_from_query_row_timestamp_parsing(
        self, single_conversation_raw: list[dict]
    ) -> None:
        event = AppInsightsEvent.from_query_row(single_conversation_raw[0])
        assert isinstance(event.timestamp, datetime)
        assert event.timestamp.year == 2025

    def test_from_query_row_error_event(self, error_raw: list[dict]) -> None:
        action_row = error_raw[2]  # Action with error
        event = AppInsightsEvent.from_query_row(action_row)

        assert event.name == "Action"
        assert event.error_code_text == "AgentTransferFailed"
        assert event.kind == "TransferToAgent"

    def test_from_query_row_missing_custom_dimensions(self) -> None:
        """Row without customDimensions still parses without error."""
        row = {
            "timestamp": "2025-01-15T10:00:00.000Z",
            "name": "SomeEvent",
        }
        event = AppInsightsEvent.from_query_row(row)
        assert event.name == "SomeEvent"
        assert event.conversation_id == ""
        assert event.user_id == ""


    def test_json_string_custom_dimensions(self) -> None:
        """customDimensions arriving as a JSON string should be parsed correctly."""
        row = {
            "timestamp": "2026-02-18T01:16:04.000Z",
            "name": "BotMessageReceived",
            "customDimensions": '{"conversationId":"conv-json","channelId":"msteams","fromId":"user-99","type":"message","text":"hello","DesignMode":"False"}',
        }
        event = AppInsightsEvent.from_query_row(row)
        assert event.conversation_id == "conv-json"
        assert event.channel_id == "msteams"
        assert event.from_id == "user-99"
        assert event.text == "hello"
        assert event.activity_type == "message"
        assert event.design_mode == "False"

    def test_pascal_case_field_names(self) -> None:
        """PascalCase fields (TopicName, TopicId, Kind, DesignMode) should be parsed."""
        row = {
            "timestamp": "2026-02-18T01:16:04.000Z",
            "name": "TopicAction",
            "customDimensions": {
                "TopicName": "Greeting",
                "TopicId": "auto_agent.topic.Greeting",
                "Kind": "SendActivity",
                "ActionId": "sendMessage_abmysR",
                "DesignMode": "False",
                "channelId": "msteams",
                "conversationId": "conv-pascal",
            },
        }
        event = AppInsightsEvent.from_query_row(row)
        assert event.topic_name == "Greeting"
        assert event.topic_id == "auto_agent.topic.Greeting"
        assert event.kind == "SendActivity"
        assert event.action_id == "sendMessage_abmysR"
        assert event.design_mode == "False"

    def test_agent_started_fields(self) -> None:
        """AgentStarted event should parse AgentType and AgentInputs."""
        row = {
            "timestamp": "2026-02-18T01:25:28.000Z",
            "name": "AgentStarted",
            "customDimensions": {
                "AgentType": "SubAgent",
                "AgentInputs": '{"Task":"Explain something"}',
                "channelId": "msteams",
                "conversationId": "conv-agent",
                "DesignMode": "False",
            },
        }
        event = AppInsightsEvent.from_query_row(row)
        assert event.agent_type == "SubAgent"
        assert event.agent_inputs == '{"Task":"Explain something"}'
        assert event.conversation_id == "conv-agent"

    def test_topic_action_fields(self) -> None:
        """TopicAction event should parse ActionId and Kind."""
        row = {
            "timestamp": "2026-02-18T01:24:36.000Z",
            "name": "TopicAction",
            "customDimensions": '{"ActionId":"cancelAllDialogs_01At22","TopicName":"Greeting","TopicId":"auto_agent.topic.Greeting","Kind":"CancelAllDialogs","channelId":"msteams","conversationId":"conv-ta","DesignMode":"False"}',
        }
        event = AppInsightsEvent.from_query_row(row)
        assert event.action_id == "cancelAllDialogs_01At22"
        assert event.kind == "CancelAllDialogs"
        assert event.topic_name == "Greeting"

    def test_bot_message_received_type_field(self) -> None:
        """BotMessageReceived should parse 'type' as activity_type."""
        for msg_type in ["message", "event", "installationUpdate", "invoke", "messageReaction"]:
            row = {
                "timestamp": "2026-02-18T01:24:36.000Z",
                "name": "BotMessageReceived",
                "customDimensions": f'{{"type":"{msg_type}","conversationId":"conv-type","channelId":"msteams"}}',
            }
            event = AppInsightsEvent.from_query_row(row)
            assert event.activity_type == msg_type

    def test_user_id_fallback_to_from_id(self) -> None:
        """When userId is absent, user_id should fall back to fromId."""
        row = {
            "timestamp": "2026-02-18T01:24:36.000Z",
            "name": "BotMessageReceived",
            "customDimensions": '{"fromId":"user-from-fallback","conversationId":"conv-fb","channelId":"msteams"}',
        }
        event = AppInsightsEvent.from_query_row(row)
        assert event.user_id == "user-from-fallback"

    def test_speak_field_on_bot_message_send(self) -> None:
        """BotMessageSend with a speak field should be parsed."""
        row = {
            "timestamp": "2026-02-18T01:24:36.000Z",
            "name": "BotMessageSend",
            "customDimensions": '{"speak":"Hello there","text":"Hi","conversationId":"conv-speak","channelId":"msteams"}',
        }
        event = AppInsightsEvent.from_query_row(row)
        assert event.speak == "Hello there"
        assert event.text == "Hi"

    def test_real_data_parses_all_rows(self, real_data_events: list[AppInsightsEvent]) -> None:
        """All rows in the real data dump should parse without error."""
        assert len(real_data_events) > 0
        # Every event should have a conversation_id
        for event in real_data_events:
            assert event.conversation_id != ""

    def test_real_data_design_mode_detected(self, real_data_events: list[AppInsightsEvent]) -> None:
        """Real data should correctly detect PascalCase DesignMode."""
        design_false = [e for e in real_data_events if e.design_mode == "False"]
        assert len(design_false) > 0


class TestBuildQuery:
    def test_basic_query(self) -> None:
        start = datetime(2025, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 15, 1, 0, 0, tzinfo=timezone.utc)
        query = build_custom_events_query(start, end, exclude_design_mode=False)

        assert "customEvents" in query
        assert "timestamp" in query
        assert "order by timestamp asc" in query
        assert "DesignMode" not in query

    def test_design_mode_filter(self) -> None:
        start = datetime(2025, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 15, 1, 0, 0, tzinfo=timezone.utc)
        query = build_custom_events_query(start, end, exclude_design_mode=True)

        assert "DesignMode" in query
        assert "designMode" in query
        assert '"True"' in query

    def test_query_includes_time_bounds(self) -> None:
        start = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 15, 11, 0, 0, tzinfo=timezone.utc)
        query = build_custom_events_query(start, end, exclude_design_mode=False)

        assert start.isoformat() in query
        assert end.isoformat() in query
