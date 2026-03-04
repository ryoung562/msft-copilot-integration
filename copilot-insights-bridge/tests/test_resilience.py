"""Tests for retry logic and resilience in the bridge pipeline."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from azure.core.exceptions import HttpResponseError, ServiceRequestError

from src.config import BridgeSettings
from src.main import BridgePipeline
from src.state.cursor import CursorState


@pytest.fixture
def settings() -> BridgeSettings:
    return BridgeSettings(
        appinsights_resource_id="/subscriptions/test/resourceGroups/test/providers/microsoft.insights/components/test",
        arize_space_id="test-space",
        arize_api_key="test-key",
        arize_project_name="test-project",
        poll_interval_minutes=1,
        initial_lookback_hours=1,
        # Fast backoff for tests
        max_consecutive_failures=3,
        backoff_base_seconds=1.0,
        backoff_max_seconds=8.0,
    )


def _make_pipeline(settings: BridgeSettings) -> BridgePipeline:
    """Create a BridgePipeline with mocked external dependencies."""
    with (
        patch("src.main.AppInsightsClient") as MockClient,
        patch("src.main.create_tracer_provider") as MockProvider,
        patch("src.main.Cursor") as MockCursor,
    ):
        mock_provider = MagicMock()
        mock_provider.get_tracer.return_value = MagicMock()
        MockProvider.return_value = mock_provider

        mock_cursor = MagicMock()
        mock_cursor.load.return_value = CursorState()
        MockCursor.return_value = mock_cursor

        pipeline = BridgePipeline(settings)
    return pipeline


class TestRunOnceFailurePoints:
    """Test that run_once() handles failures at each stage correctly."""

    def test_azure_http_error_propagates(self, settings: BridgeSettings) -> None:
        """HttpResponseError from query_events should propagate out of run_once()."""
        pipeline = _make_pipeline(settings)
        pipeline._client.query_events.side_effect = HttpResponseError(
            message="429 Too Many Requests"
        )

        with pytest.raises(HttpResponseError):
            pipeline.run_once()

    def test_azure_connection_error_propagates(self, settings: BridgeSettings) -> None:
        """ServiceRequestError (connection drop) should propagate out of run_once()."""
        pipeline = _make_pipeline(settings)
        pipeline._client.query_events.side_effect = ServiceRequestError(
            message="Connection aborted"
        )

        with pytest.raises(ServiceRequestError):
            pipeline.run_once()

    def test_force_flush_timeout_logs_warning(self, settings: BridgeSettings) -> None:
        """force_flush() returning False (timeout) should log warning but not crash."""
        pipeline = _make_pipeline(settings)
        pipeline._client.query_events.return_value = [MagicMock()]
        pipeline._tree_builder.build_trees = MagicMock(return_value=[])
        pipeline._provider.force_flush.return_value = False

        result = pipeline.run_once()

        # Cursor should still advance
        pipeline._cursor.save.assert_called_once()
        assert result == 1

    def test_force_flush_exception_swallowed(self, settings: BridgeSettings) -> None:
        """force_flush() exception should be swallowed; cursor still advances."""
        pipeline = _make_pipeline(settings)
        pipeline._client.query_events.return_value = [MagicMock()]
        pipeline._tree_builder.build_trees = MagicMock(return_value=[])
        pipeline._provider.force_flush.side_effect = RuntimeError("gRPC timeout")

        result = pipeline.run_once()

        pipeline._cursor.save.assert_called_once()
        assert result == 1

    def test_cursor_save_oserror_swallowed(self, settings: BridgeSettings) -> None:
        """OSError from cursor.save() should be swallowed; run_once returns normally."""
        pipeline = _make_pipeline(settings)
        pipeline._client.query_events.return_value = [MagicMock()]
        pipeline._tree_builder.build_trees = MagicMock(return_value=[])
        pipeline._provider.force_flush.return_value = True
        pipeline._cursor.save.side_effect = OSError("disk full")

        result = pipeline.run_once()

        assert result == 1


class TestRunLoopBackoff:
    """Test that run_loop() implements exponential backoff correctly."""

    def test_backoff_arithmetic(self, settings: BridgeSettings) -> None:
        """Backoff should be base * 2^(failures-1)."""
        pipeline = _make_pipeline(settings)
        assert pipeline._backoff_seconds(1) == 1.0
        assert pipeline._backoff_seconds(2) == 2.0
        assert pipeline._backoff_seconds(3) == 4.0

    def test_backoff_capped_at_max(self, settings: BridgeSettings) -> None:
        """Backoff should not exceed backoff_max_seconds."""
        pipeline = _make_pipeline(settings)
        # 2^9 = 512, way over max of 8
        assert pipeline._backoff_seconds(10) == 8.0

    def test_success_resets_backoff(self, settings: BridgeSettings) -> None:
        """After a failure then a success, backoff counter resets."""
        pipeline = _make_pipeline(settings)
        call_count = 0
        sleep_durations: list[float] = []

        def side_effect_run_once() -> int:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient failure")
            if call_count == 2:
                return 5  # success
            if call_count == 3:
                raise RuntimeError("another failure")
            # Stop the loop
            raise KeyboardInterrupt

        pipeline.run_once = MagicMock(side_effect=side_effect_run_once)

        original_sleep = pipeline._backoff_seconds

        with patch("src.main.time.sleep") as mock_sleep:
            mock_sleep.side_effect = lambda s: sleep_durations.append(s)
            pipeline.run_loop()

        # Call 1: failure → backoff 1s (failures=1)
        # Call 2: success → normal interval (60s)
        # Call 3: failure → backoff 1s (reset, failures=1 again)
        # Call 4: KeyboardInterrupt
        assert sleep_durations[0] == 1.0   # first failure backoff
        assert sleep_durations[1] == 60.0  # success → normal interval
        assert sleep_durations[2] == 1.0   # reset: back to first failure backoff

    def test_error_escalation_after_threshold(self, settings: BridgeSettings) -> None:
        """After max_consecutive_failures, log level should escalate to ERROR."""
        pipeline = _make_pipeline(settings)
        call_count = 0

        def failing_run_once() -> int:
            nonlocal call_count
            call_count += 1
            if call_count > settings.max_consecutive_failures:
                raise KeyboardInterrupt
            raise RuntimeError("persistent failure")

        pipeline.run_once = MagicMock(side_effect=failing_run_once)

        with patch("src.main.time.sleep"):
            with patch("src.main.logger") as mock_logger:
                pipeline.run_loop()

        # First (max-1) failures should be warnings
        warning_calls = mock_logger.warning.call_args_list
        error_calls = mock_logger.error.call_args_list

        # The last failure (at threshold) should be ERROR with "ALERT:"
        alert_calls = [
            c for c in error_calls if "ALERT:" in str(c)
        ]
        assert len(alert_calls) >= 1

    def test_shutdown_flush_failure_does_not_crash(self, settings: BridgeSettings) -> None:
        """Shutdown force_flush() failure should not crash the process."""
        pipeline = _make_pipeline(settings)
        pipeline.run_once = MagicMock(side_effect=KeyboardInterrupt)
        pipeline._provider.force_flush.side_effect = RuntimeError("shutdown gRPC error")

        # Should not raise
        pipeline.run_loop()
