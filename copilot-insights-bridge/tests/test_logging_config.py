"""Tests for src.logging_config."""

import json
import logging

from src.logging_config import configure_logging


class TestConfigureLogging:
    def teardown_method(self) -> None:
        # Reset root logger after each test
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.WARNING)

    def test_text_format_produces_readable_output(self, caplog: object, capsys: object) -> None:
        configure_logging(fmt="text")
        logger = logging.getLogger("test.text")
        logger.info("hello world")
        # Capture stderr where StreamHandler writes
        import sys
        from io import StringIO

        handler = logging.getLogger().handlers[0]
        buf = StringIO()
        handler.stream = buf  # type: ignore[attr-defined]
        logger.info("hello world")
        output = buf.getvalue()
        assert "[INFO]" in output
        assert "test.text" in output
        assert "hello world" in output

    def test_json_format_produces_parseable_json(self) -> None:
        configure_logging(fmt="json")
        logger = logging.getLogger("test.json")

        from io import StringIO

        buf = StringIO()
        logging.getLogger().handlers[0].stream = buf  # type: ignore[attr-defined]
        logger.info("structured msg")
        line = buf.getvalue().strip()
        data = json.loads(line)
        assert data["message"] == "structured msg"
        assert "timestamp" in data
        assert data["level"] == "INFO"
        assert data["name"] == "test.json"

    def test_json_format_includes_exc_info(self) -> None:
        configure_logging(fmt="json")
        logger = logging.getLogger("test.exc")

        from io import StringIO

        buf = StringIO()
        logging.getLogger().handlers[0].stream = buf  # type: ignore[attr-defined]
        try:
            raise ValueError("boom")
        except ValueError:
            logger.exception("something failed")
        line = buf.getvalue().strip()
        data = json.loads(line)
        assert "exc_info" in data
        assert "boom" in data["exc_info"]

    def test_default_is_text_format(self) -> None:
        configure_logging()
        handler = logging.getLogger().handlers[0]
        fmt = handler.formatter
        assert fmt is not None
        # Text formatter uses logging.Formatter, not JsonFormatter
        assert type(fmt).__name__ == "Formatter"

    def test_calling_twice_does_not_duplicate_handlers(self) -> None:
        configure_logging(fmt="text")
        configure_logging(fmt="json")
        assert len(logging.getLogger().handlers) == 1
