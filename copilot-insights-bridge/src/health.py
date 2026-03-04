"""Health check HTTP endpoint for orchestrator liveness/readiness probes."""

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)


@dataclass
class HealthState:
    """Thread-safe health state updated by the pipeline after each cycle."""

    poll_interval_seconds: int = 300
    max_consecutive_failures: int = 5

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _last_run_at: datetime | None = field(default=None, repr=False)
    _last_processed_timestamp: datetime | None = field(default=None, repr=False)
    _events_processed_count: int = field(default=0, repr=False)
    _consecutive_failures: int = field(default=0, repr=False)
    _last_error: str | None = field(default=None, repr=False)
    _first_success: bool = field(default=False, repr=False)

    @property
    def consecutive_failures(self) -> int:
        with self._lock:
            return self._consecutive_failures

    def record_success(self, cursor_state: object) -> None:
        """Update state after a successful poll cycle.

        Args:
            cursor_state: A ``CursorState`` (or any object with
                ``last_run_at``, ``last_processed_timestamp``, and
                ``events_processed_count`` attributes).
        """
        with self._lock:
            self._last_run_at = getattr(cursor_state, "last_run_at", None)
            self._last_processed_timestamp = getattr(
                cursor_state, "last_processed_timestamp", None
            )
            self._events_processed_count = getattr(
                cursor_state, "events_processed_count", 0
            )
            self._consecutive_failures = 0
            self._last_error = None
            self._first_success = True

    def record_failure(self, error: Exception) -> None:
        """Update state after a failed poll cycle."""
        with self._lock:
            self._consecutive_failures += 1
            self._last_error = f"{type(error).__name__}: {error}"

    def snapshot(self) -> dict:
        """Return a point-in-time copy of all health fields."""
        now = datetime.now(timezone.utc)
        with self._lock:
            last_run = self._last_run_at
            time_since = (
                (now - last_run).total_seconds() if last_run is not None else None
            )
            stale = (
                time_since is not None
                and time_since > self.poll_interval_seconds * 3
            )

            failures = self._consecutive_failures
            if failures >= self.max_consecutive_failures or stale:
                status = "unhealthy"
            elif failures > 0:
                status = "degraded"
            elif last_run is None:
                status = "unhealthy"
            else:
                status = "healthy"

            return {
                "status": status,
                "last_run_at": (
                    last_run.isoformat() if last_run is not None else None
                ),
                "last_processed_timestamp": (
                    self._last_processed_timestamp.isoformat()
                    if self._last_processed_timestamp is not None
                    else None
                ),
                "events_processed_count": self._events_processed_count,
                "consecutive_failures": failures,
                "last_error": self._last_error,
                "time_since_last_run_seconds": (
                    round(time_since, 1) if time_since is not None else None
                ),
                "poll_interval_seconds": self.poll_interval_seconds,
            }

    def is_ready(self) -> bool:
        """Return True once at least one successful cycle has completed."""
        with self._lock:
            return self._first_success


class _HealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for /health and /ready endpoints."""

    health_state: HealthState  # set via partial class or attribute

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            snap = self.health_state.snapshot()
            code = (
                HTTPStatus.OK
                if snap["status"] in ("healthy", "degraded")
                else HTTPStatus.SERVICE_UNAVAILABLE
            )
            self._respond(code, snap)
        elif self.path == "/ready":
            if self.health_state.is_ready():
                self._respond(HTTPStatus.OK, {"ready": True})
            else:
                self._respond(
                    HTTPStatus.SERVICE_UNAVAILABLE, {"ready": False}
                )
        else:
            self._respond(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def _respond(self, status: HTTPStatus, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        # Silence default stderr logging; use Python logging instead.
        logger.debug("health: %s", format % args)


def start_health_server(state: HealthState, port: int = 8080) -> HTTPServer:
    """Start the health check HTTP server on a daemon thread.

    Returns the ``HTTPServer`` instance (useful for testing / shutdown).
    """

    # Create a handler class bound to this specific state instance.
    handler = type(
        "_BoundHealthHandler",
        (_HealthHandler,),
        {"health_state": state},
    )

    server = HTTPServer(("0.0.0.0", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health check server listening on port %d", port)
    return server
