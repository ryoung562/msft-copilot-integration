"""Shared logging configuration for the bridge."""

import logging

from pythonjsonlogger.jsonlogger import JsonFormatter


def configure_logging(fmt: str = "text", level: int = logging.INFO) -> None:
    """Set up the root logger with the given format and level.

    Args:
        fmt: ``"text"`` for human-readable output, ``"json"`` for structured JSON.
        level: Logging level (default ``logging.INFO``).
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Clear existing handlers (idempotent setup)
    root.handlers.clear()

    handler = logging.StreamHandler()
    if fmt == "json":
        handler.setFormatter(
            JsonFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                rename_fields={"asctime": "timestamp", "levelname": "level"},
            )
        )
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )

    root.addHandler(handler)
