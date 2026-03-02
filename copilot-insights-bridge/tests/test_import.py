"""Tests for the universal file loader and import script."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.extraction.loader import load_events_from_file
from src.extraction.models import AppInsightsEvent
from src.reconstruction.span_models import SpanKind, SpanNode
from src.reconstruction.tree_builder import shift_tree_timestamps

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# shift_tree_timestamps tests (carried over from test_backfill.py)
# ---------------------------------------------------------------------------


def _make_tree() -> SpanNode:
    """Build a small 3-node tree for timestamp shift tests."""
    root = SpanNode(
        name="root",
        span_kind=SpanKind.AGENT,
        start_time=datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 10, 12, 5, 0, tzinfo=timezone.utc),
        session_id="s1",
        user_id="u1",
        channel_id="msteams",
    )
    child = SpanNode(
        name="child",
        span_kind=SpanKind.CHAIN,
        start_time=datetime(2026, 1, 10, 12, 1, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 10, 12, 3, 0, tzinfo=timezone.utc),
        session_id="s1",
        user_id="u1",
        channel_id="msteams",
    )
    grandchild = SpanNode(
        name="grandchild",
        span_kind=SpanKind.LLM,
        start_time=datetime(2026, 1, 10, 12, 1, 30, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 10, 12, 2, 30, tzinfo=timezone.utc),
        session_id="s1",
        user_id="u1",
        channel_id="msteams",
    )
    child.children.append(grandchild)
    root.children.append(child)
    return root


class TestShiftTreeTimestamps:
    def test_shift_forward(self):
        tree = _make_tree()
        offset = timedelta(days=5)
        shift_tree_timestamps(tree, offset)

        assert tree.start_time == datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert tree.end_time == datetime(2026, 1, 15, 12, 5, 0, tzinfo=timezone.utc)

        child = tree.children[0]
        assert child.start_time == datetime(2026, 1, 15, 12, 1, 0, tzinfo=timezone.utc)
        assert child.end_time == datetime(2026, 1, 15, 12, 3, 0, tzinfo=timezone.utc)

        grandchild = child.children[0]
        assert grandchild.start_time == datetime(2026, 1, 15, 12, 1, 30, tzinfo=timezone.utc)
        assert grandchild.end_time == datetime(2026, 1, 15, 12, 2, 30, tzinfo=timezone.utc)

    def test_shift_backward(self):
        tree = _make_tree()
        offset = timedelta(hours=-2)
        shift_tree_timestamps(tree, offset)

        assert tree.start_time == datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc)
        assert tree.end_time == datetime(2026, 1, 10, 10, 5, 0, tzinfo=timezone.utc)

    def test_zero_offset_is_noop(self):
        tree = _make_tree()
        original_start = tree.start_time
        original_end = tree.end_time
        shift_tree_timestamps(tree, timedelta(0))

        assert tree.start_time == original_start
        assert tree.end_time == original_end

    def test_preserves_relative_durations(self):
        tree = _make_tree()
        root_duration = tree.end_time - tree.start_time
        child_duration = tree.children[0].end_time - tree.children[0].start_time

        shift_tree_timestamps(tree, timedelta(days=30))

        assert tree.end_time - tree.start_time == root_duration
        assert tree.children[0].end_time - tree.children[0].start_time == child_duration

    def test_leaf_node(self):
        """Shifting a leaf node (no children) works without error."""
        leaf = SpanNode(
            name="leaf",
            span_kind=SpanKind.LLM,
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
            session_id="s1",
            user_id="u1",
            channel_id="ch",
        )
        shift_tree_timestamps(leaf, timedelta(hours=1))
        assert leaf.start_time == datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# load_events_from_file tests — format auto-detection
# ---------------------------------------------------------------------------


class TestLoadEventsFromFile:
    def test_flat_row_dict_format(self):
        """Format 4: array of dicts with top-level keys (synthetic fixtures)."""
        events = load_events_from_file(FIXTURES_DIR / "single_conversation.json")
        assert len(events) > 0
        assert all(isinstance(e, AppInsightsEvent) for e in events)
        # Should be sorted by timestamp
        for i in range(len(events) - 1):
            assert events[i].timestamp <= events[i + 1].timestamp

    def test_sdk_table_format(self):
        """Format 1: SDK table with columns + rows (live_data_dump.json)."""
        events = load_events_from_file(FIXTURES_DIR / "live_data_dump.json")
        assert len(events) > 0
        assert all(isinstance(e, AppInsightsEvent) for e in events)

    def test_azure_cli_format(self, tmp_path: Path):
        """Format 2: Azure CLI table with positional row arrays."""
        data = {
            "tables": [
                {
                    "rows": [
                        [
                            "2026-01-15T10:00:00Z",
                            "BotMessageReceived",
                            "op-001",
                            "",
                            {
                                "conversationId": "conv-cli-1",
                                "channelId": "msteams",
                                "text": "Hello from CLI",
                            },
                        ],
                        [
                            "2026-01-15T10:01:00Z",
                            "BotMessageSent",
                            "op-001",
                            "",
                            {
                                "conversationId": "conv-cli-1",
                                "channelId": "msteams",
                                "text": "Hi there!",
                            },
                        ],
                    ]
                }
            ]
        }
        f = tmp_path / "cli_data.json"
        f.write_text(json.dumps(data))

        events = load_events_from_file(f)
        assert len(events) == 2
        assert events[0].name == "BotMessageReceived"
        assert events[0].conversation_id == "conv-cli-1"
        assert events[1].name == "BotMessageSent"

    def test_azure_cli_format_string_dims(self, tmp_path: Path):
        """Azure CLI format where customDimensions is a JSON string."""
        data = {
            "tables": [
                {
                    "rows": [
                        [
                            "2026-01-15T10:00:00Z",
                            "BotMessageReceived",
                            "op-001",
                            "",
                            json.dumps({"conversationId": "conv-str", "channelId": "web"}),
                        ],
                    ]
                }
            ]
        }
        f = tmp_path / "cli_string_dims.json"
        f.write_text(json.dumps(data))

        events = load_events_from_file(f)
        assert len(events) == 1
        assert events[0].conversation_id == "conv-str"

    def test_event_array_format(self, tmp_path: Path):
        """Format 3: direct array of event dicts with customDimensions."""
        data = [
            {
                "timestamp": "2026-01-15T10:00:00Z",
                "name": "BotMessageReceived",
                "operation_Id": "op-001",
                "customDimensions": {
                    "conversationId": "conv-arr-1",
                    "channelId": "msteams",
                    "text": "Array format test",
                },
            }
        ]
        f = tmp_path / "array_data.json"
        f.write_text(json.dumps(data))

        events = load_events_from_file(f)
        assert len(events) == 1
        assert events[0].conversation_id == "conv-arr-1"

    def test_empty_table(self, tmp_path: Path):
        """Empty table produces empty event list."""
        data = {"tables": [{"columns": [{"name": "timestamp", "type": "datetime"}], "rows": []}]}
        f = tmp_path / "empty.json"
        f.write_text(json.dumps(data))

        events = load_events_from_file(f)
        assert events == []

    def test_empty_array(self, tmp_path: Path):
        """Empty array produces empty event list."""
        f = tmp_path / "empty_arr.json"
        f.write_text("[]")

        events = load_events_from_file(f)
        assert events == []

    def test_invalid_format_raises(self, tmp_path: Path):
        """Non-dict, non-list top-level JSON raises ValueError."""
        f = tmp_path / "bad.json"
        f.write_text('"just a string"')

        with pytest.raises(ValueError, match="Unexpected JSON structure"):
            load_events_from_file(f)


# ---------------------------------------------------------------------------
# import_to_arize CLI tests
# ---------------------------------------------------------------------------


class TestImportCli:
    def test_help_renders(self):
        """--help exits cleanly with usage info."""
        import subprocess

        result = subprocess.run(
            ["python", "scripts/import_to_arize.py", "--help"],
            capture_output=True,
            text=True,
            cwd=str(FIXTURES_DIR.parent.parent),
        )
        assert result.returncode == 0
        assert "Import Copilot Studio telemetry" in result.stdout

    def test_default_is_inspect_mode(self):
        """No action flags → stats + diagnose (no export)."""
        import subprocess

        result = subprocess.run(
            ["python", "scripts/import_to_arize.py", "tests/fixtures/single_conversation.json"],
            capture_output=True,
            text=True,
            cwd=str(FIXTURES_DIR.parent.parent),
        )
        assert result.returncode == 0
        assert "DATA STATISTICS" in result.stdout
        assert "GAP ANALYSIS DIAGNOSTICS" in result.stdout

    def test_stats_only(self):
        """--stats shows statistics but not diagnostics."""
        import subprocess

        result = subprocess.run(
            ["python", "scripts/import_to_arize.py", "--stats", "tests/fixtures/single_conversation.json"],
            capture_output=True,
            text=True,
            cwd=str(FIXTURES_DIR.parent.parent),
        )
        assert result.returncode == 0
        assert "DATA STATISTICS" in result.stdout
        assert "GAP ANALYSIS DIAGNOSTICS" not in result.stdout
