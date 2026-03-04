"""Bridge configuration via environment variables."""

from pydantic_settings import BaseSettings


class BridgeSettings(BaseSettings):
    """Configuration for the Copilot Studio → Arize AX bridge.

    All settings are loaded from environment variables with the ``BRIDGE_`` prefix.
    """

    model_config = {"env_prefix": "BRIDGE_"}

    # Azure Application Insights
    appinsights_resource_id: str

    # Arize AX OTLP destination
    arize_space_id: str
    arize_api_key: str
    arize_project_name: str = "copilot-studio"

    # Polling
    poll_interval_minutes: int = 5
    initial_lookback_hours: int = 24

    # Filtering
    exclude_design_mode: bool = True

    # State
    cursor_path: str = ".bridge_cursor.json"

    # Logging
    log_format: str = "text"  # "text" or "json"

    # Resilience
    max_consecutive_failures: int = 5
    backoff_base_seconds: float = 60.0
    backoff_max_seconds: float = 900.0  # 15 minutes
