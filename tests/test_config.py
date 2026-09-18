"""Tests for configuration management."""

from pathlib import Path
from gaggimate_mcp.config import GaggimateConfig


class TestGaggimateConfig:
    """Test configuration management."""

    def test_default_values(self):
        """Test default configuration values load correctly."""
        config = GaggimateConfig()
        assert config.gaggimate_host == "gaggimate.local"
        assert config.gaggimate_protocol == "ws"
        assert config.request_timeout == 15.0
        assert config.max_temperature == 100.0
        assert config.min_temperature == 25.0
        assert config.max_pressure == 12.0
        assert config.min_pressure == 0.0

    def test_config_override(self):
        """Test configuration values can be overridden."""
        config = GaggimateConfig(
            gaggimate_host="192.168.1.100",
            gaggimate_protocol="wss",
            max_temperature=95.0
        )
        assert config.gaggimate_host == "192.168.1.100"
        assert config.gaggimate_protocol == "wss"
        assert config.max_temperature == 95.0

    def test_websocket_url_generation(self):
        """Test WebSocket URL is generated correctly."""
        config = GaggimateConfig()
        assert config.websocket_url == "ws://gaggimate.local/ws"

    def test_websocket_url_wss(self):
        """Test WebSocket URL with wss protocol."""
        config = GaggimateConfig(gaggimate_protocol="wss")
        assert config.websocket_url == "wss://gaggimate.local/ws"

    def test_http_base_url_generation(self):
        """Test HTTP base URL is generated correctly."""
        config = GaggimateConfig()
        assert config.http_base_url == "http://gaggimate.local"

    def test_http_base_url_https(self):
        """Test HTTP base URL with https when using wss."""
        config = GaggimateConfig(gaggimate_protocol="wss")
        assert config.http_base_url == "https://gaggimate.local"

    def test_temperature_clamping_max(self):
        """Test temperature is clamped to maximum limit."""
        config = GaggimateConfig()
        assert config.max_temperature == 100.0
        assert config.validate_temperature(150.0) == 100.0
        assert config.validate_temperature(100.5) == 100.0
        # A brew target plus the display temperature offset must survive
        # unclamped: a 92.5C profile with a 5C offset targets 97.5C.
        assert config.validate_temperature(97.5) == 97.5

    def test_temperature_clamping_min(self):
        """Test temperature is clamped to minimum limit."""
        config = GaggimateConfig()
        assert config.min_temperature == 25.0
        assert config.validate_temperature(0.0) == 25.0
        assert config.validate_temperature(24.9) == 25.0

    def test_temperature_within_range(self):
        """Test temperature within range is unchanged."""
        config = GaggimateConfig()
        assert config.validate_temperature(93.0) == 93.0
        assert config.validate_temperature(85.5) == 85.5

    def test_pressure_clamping_max(self):
        """Test pressure is clamped to maximum limit."""
        config = GaggimateConfig()
        assert config.validate_pressure(15.0) == 12.0
        assert config.validate_pressure(13.0) == 12.0

    def test_pressure_clamping_min(self):
        """Test pressure is clamped to minimum limit."""
        config = GaggimateConfig()
        assert config.validate_pressure(-1.0) == 0.0
        assert config.validate_pressure(-5.0) == 0.0

    def test_pressure_within_range(self):
        """Test pressure within range is unchanged."""
        config = GaggimateConfig()
        assert config.validate_pressure(9.0) == 9.0
        assert config.validate_pressure(6.5) == 6.5

    def test_profiles_dir_is_path(self):
        """Test profiles_dir is a Path object."""
        config = GaggimateConfig()
        assert isinstance(config.profiles_dir, Path)

    def test_custom_profiles_dir(self):
        """Test custom profiles directory can be set."""
        config = GaggimateConfig(profiles_dir=Path("/custom/path/profiles"))
        assert config.profiles_dir == Path("/custom/path/profiles")

    def test_log_level_default(self):
        """Test default log level is INFO."""
        config = GaggimateConfig()
        assert config.log_level == "INFO"

    def test_metrics_enabled_default(self):
        """Test metrics are enabled by default."""
        config = GaggimateConfig()
        assert config.enable_metrics is True
