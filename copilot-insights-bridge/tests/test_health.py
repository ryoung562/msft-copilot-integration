"""Tests for the health check endpoint and HealthState."""

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import urllib.request

from src.health import HealthState, start_health_server


# ---------------------------------------------------------------------------
# HealthState unit tests
# ---------------------------------------------------------------------------

class TestHealthState:
    def test_initial_state_is_unhealthy(self):
        state = HealthState()
        snap = state.snapshot()
        assert snap["status"] == "unhealthy"
        assert snap["last_run_at"] is None
        assert snap["consecutive_failures"] == 0

    def test_record_success_sets_healthy(self):
        state = HealthState()
        now = datetime.now(timezone.utc)
        cursor = SimpleNamespace(
            last_processed_timestamp=now - timedelta(minutes=2),
            events_processed_count=42,
        )
        state.record_success(cursor)
        snap = state.snapshot()
        assert snap["status"] == "healthy"
        assert snap["events_processed_count"] == 42
        assert snap["consecutive_failures"] == 0
        assert snap["last_error"] is None
        # last_run_at is set to ~now by record_success, not from cursor
        assert snap["time_since_last_run_seconds"] < 2

    def test_record_failure_increments_and_captures_error(self):
        state = HealthState()
        state.record_failure(ValueError("test error"))
        snap = state.snapshot()
        assert snap["consecutive_failures"] == 1
        assert "ValueError: test error" in snap["last_error"]

    def test_record_success_after_failure_resets(self):
        state = HealthState()
        state.record_failure(RuntimeError("oops"))
        assert state.snapshot()["consecutive_failures"] == 1

        now = datetime.now(timezone.utc)
        cursor = SimpleNamespace(
            last_processed_timestamp=now,
            events_processed_count=1,
        )
        state.record_success(cursor)
        snap = state.snapshot()
        assert snap["consecutive_failures"] == 0
        assert snap["last_error"] is None
        assert snap["status"] == "healthy"

    def test_status_transitions_degraded_then_unhealthy(self):
        state = HealthState(max_consecutive_failures=3)
        # Need at least one success so "no last_run" doesn't make it unhealthy
        now = datetime.now(timezone.utc)
        cursor = SimpleNamespace(
            last_processed_timestamp=now,
            events_processed_count=1,
        )
        state.record_success(cursor)

        # 1 failure → degraded
        state.record_failure(RuntimeError("f1"))
        assert state.snapshot()["status"] == "degraded"

        # 2 failures → still degraded
        state.record_failure(RuntimeError("f2"))
        assert state.snapshot()["status"] == "degraded"

        # 3 failures → unhealthy (== max_consecutive_failures)
        state.record_failure(RuntimeError("f3"))
        assert state.snapshot()["status"] == "unhealthy"

    def test_staleness_makes_unhealthy(self):
        state = HealthState(poll_interval_seconds=60)
        old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        cursor = SimpleNamespace(
            last_processed_timestamp=old_time,
            events_processed_count=5,
        )
        # Mock datetime.now so record_success sets _last_run_at to 10 min ago
        with patch("src.health.datetime") as mock_dt:
            mock_dt.now.return_value = old_time
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            state.record_success(cursor)
        # 10 minutes ago with a 60s interval → stale (> 3x interval)
        snap = state.snapshot()
        assert snap["status"] == "unhealthy"

    def test_is_ready_false_then_true(self):
        state = HealthState()
        assert state.is_ready() is False

        now = datetime.now(timezone.utc)
        cursor = SimpleNamespace(
            last_processed_timestamp=now,
            events_processed_count=1,
        )
        state.record_success(cursor)
        assert state.is_ready() is True


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def health_server():
    """Start a health server on an ephemeral port and yield (state, base_url)."""
    state = HealthState(poll_interval_seconds=300, max_consecutive_failures=5)
    # Port 0 → OS picks a free port
    server = start_health_server(state, port=0)
    port = server.server_address[1]
    base_url = f"http://localhost:{port}"
    yield state, base_url
    server.shutdown()


def _get(url: str) -> tuple[int, dict]:
    """GET a URL, return (status_code, parsed_json)."""
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class TestHealthHTTP:
    def test_healthy_returns_200(self, health_server):
        state, base_url = health_server
        now = datetime.now(timezone.utc)
        cursor = SimpleNamespace(
            last_processed_timestamp=now,
            events_processed_count=10,
        )
        state.record_success(cursor)

        code, body = _get(f"{base_url}/health")
        assert code == 200
        assert body["status"] == "healthy"
        assert body["events_processed_count"] == 10

    def test_unhealthy_returns_503(self, health_server):
        state, base_url = health_server
        # No runs yet → unhealthy
        code, body = _get(f"{base_url}/health")
        assert code == 503
        assert body["status"] == "unhealthy"

    def test_ready_503_before_first_success(self, health_server):
        state, base_url = health_server
        code, body = _get(f"{base_url}/ready")
        assert code == 503
        assert body["ready"] is False

    def test_ready_200_after_first_success(self, health_server):
        state, base_url = health_server
        now = datetime.now(timezone.utc)
        cursor = SimpleNamespace(
            last_processed_timestamp=now,
            events_processed_count=1,
        )
        state.record_success(cursor)

        code, body = _get(f"{base_url}/ready")
        assert code == 200
        assert body["ready"] is True

    def test_not_found(self, health_server):
        _, base_url = health_server
        code, body = _get(f"{base_url}/nonexistent")
        assert code == 404
