"""Bridge configuration via environment variables."""

from pydantic_settings import BaseSettings


class ArizeSettings(BaseSettings):
    """Arize-only settings used by both the bridge service and import script.

    All settings are loaded from environment variables with the ``BRIDGE_`` prefix.
    """

    model_config = {"env_prefix": "BRIDGE_"}

    # Arize AX OTLP destination
    arize_space_id: str
    arize_api_key: str
    arize_project_name: str = "copilot-studio"


class BridgeSettings(ArizeSettings):
    """Full settings for the continuous bridge service (adds Azure + polling config).

    Inherits Arize credentials from :class:`ArizeSettings`.
    """

    # Azure Application Insights
    appinsights_resource_id: str

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

    # Event buffer
    buffer_grace_seconds: int = 0  # 0 = disabled (immediate export)

    # Health check
    health_check_enabled: bool = True
    health_check_port: int = 8080
