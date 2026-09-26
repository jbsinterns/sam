"""
SAM Rover - Configuration Loader
Loads and validates config.yaml with platform awareness and fallback defaults.
"""

import os
import platform
from pathlib import Path
from typing import Any, Dict
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

DEFAULT_CONFIG: Dict[str, Any] = {
    "system": {
        "name": "SAM",
        "version": "2.0.0",
        "mock_hardware": "auto",
        "port": 8000,
        "host": "0.0.0.0",
    },
    "gpio": {
        "motors": {
            "left": {"ena": 12, "in1": 5, "in2": 6},
            "right": {"enb": 13, "in3": 19, "in4": 26},
            "pwm_frequency": 1000,
        },
        "ultrasonic": {
            "front": {"trigger": 23, "echo": 24},
            "rear": {"trigger": 27, "echo": 22},
            "left": {"trigger": 17, "echo": 18},
            "right": {"trigger": 25, "echo": 8},
        },
        "leds": {
            "front": 4,
            "rear": 14,
            "left": 15,
            "right": 16,
        },
        "imu": {
            "bus": 1,
            "addresses": [0x68, 0x69],
        },
    },
    "safety": {
        "watchdog_timeout_sec": 0.50,
        "obstacle_warning_cm": 30.0,
        "obstacle_critical_stop_cm": 15.0,
        "idle_hardware_release_sec": 60.0,
    },
    "camera": {
        "preferred_index": 0,
        "width": 640,
        "height": 480,
        "fps": 25,
        "jpeg_quality": 75,
    },
    "network": {
        "ap_interface": "wlan0",
        "ap_ssid": "SAM-Rover-Setup",
        "ap_ip": "192.168.4.1",
        "external_interface": "wlan1",
        "wifi_check_interval_sec": 15,
    },
}


class ConfigManager:
    """Manages the lifecycle of configuration settings for SAM."""

    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self.config: Dict[str, Any] = {}
        self.reload()

    def reload(self) -> Dict[str, Any]:
        """Reload configuration from disk or fallback to defaults."""
        if self.path.exists() and HAS_YAML:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                    self.config = self._deep_merge(DEFAULT_CONFIG, loaded or {})
            except Exception as e:
                print(f"[Config] Error reading {self.path}: {e}. Using defaults.")
                self.config = DEFAULT_CONFIG.copy()
        else:
            self.config = DEFAULT_CONFIG.copy()

        # Validate through Pydantic v2 schema for pin collision and boundary checks
        try:
            from core.config_schema import RoverConfigSchema
            self.validated_schema = RoverConfigSchema.model_validate(self.config)
            print("[Config] Pydantic v2 schema validation passed. GPIO pin mappings & safety bounds verified.")
        except Exception as e:
            print(f"[Config CRITICAL] Configuration validation error: {e}")
            self.validated_schema = None

        # Resolve mock_hardware auto-detection
        mock_setting = self.config.get("system", {}).get("mock_hardware", "auto")
        if mock_setting == "auto":
            # If not running on Linux with ARM architecture, default to Mock
            is_pi = (
                platform.system() == "Linux"
                and ("arm" in platform.machine().lower() or "aarch" in platform.machine().lower())
            )
            self.is_mock = not is_pi
        else:
            self.is_mock = bool(mock_setting)

        return self.config

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Recursively merge override into base."""
        merged = base.copy()
        for key, value in override.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    def get(self, *keys: str, default: Any = None) -> Any:
        """Safe dotted lookup in nested configuration dict."""
        curr = self.config
        for k in keys:
            if isinstance(curr, dict) and k in curr:
                curr = curr[k]
            else:
                return default
        return curr


# Singleton instance
config_manager = ConfigManager()
config = config_manager.config
