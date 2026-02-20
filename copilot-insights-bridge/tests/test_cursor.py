"""Tests for the file-based cursor state management."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.state.cursor import Cursor, CursorState


@pytest.fixture
def cursor_path(tmp_path: Path) -> str:
    return str(tmp_path / "test_cursor.json")


class TestCursor:
    def test_load_missing_file_returns_defaults(self, cursor_path: str) -> None:
        cursor = Cursor(cursor_path)
        state = cursor.load()
        assert state.last_processed_timestamp is None
        assert state.last_run_at is None
        assert state.events_processed_count == 0

    def test_save_and_load_roundtrip(self, cursor_path: str) -> None:
        cursor = Cursor(cursor_path)
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        state = CursorState(
            last_processed_timestamp=now,
            last_run_at=now,
            events_processed_count=42,
        )
        cursor.save(state)

        loaded = cursor.load()
        assert loaded.last_processed_timestamp == now
        assert loaded.last_run_at == now
        assert loaded.events_processed_count == 42

    def test_save_creates_file(self, cursor_path: str) -> None:
        cursor = Cursor(cursor_path)
        cursor.save(CursorState())
        assert Path(cursor_path).exists()

    def test_save_overwrites_previous(self, cursor_path: str) -> None:
        cursor = Cursor(cursor_path)
        cursor.save(CursorState(events_processed_count=10))
        cursor.save(CursorState(events_processed_count=20))

        loaded = cursor.load()
        assert loaded.events_processed_count == 20

    def test_save_produces_valid_json(self, cursor_path: str) -> None:
        cursor = Cursor(cursor_path)
        state = CursorState(
            last_processed_timestamp=datetime(2025, 6, 1, tzinfo=timezone.utc),
            events_processed_count=5,
        )
        cursor.save(state)

        raw = json.loads(Path(cursor_path).read_text())
        assert "last_processed_timestamp" in raw
        assert raw["events_processed_count"] == 5
