"""
SAM Rover - Structured JSON Logging Framework
Emits structured JSON lines for production observability (Grafana Loki, Datadog, systemd).
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Formats log records into single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "event": getattr(record, "event", record.getMessage()),
        }

        # Include any extra structured context passed via kwargs
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            log_payload.update(record.extra_fields)

        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload)


# Configure root robotics logger
_logger = logging.getLogger("sam_rover")
_logger.setLevel(logging.INFO)

# Console handler with JSONFormatter
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JSONFormatter())
_logger.handlers = [_handler]
_logger.propagate = False


def log_event(level: str, component: str, event: str, **kwargs: Any) -> None:
    """
    Emits a structured JSON log entry.
    
    Usage:
        log_event("info", "motors", "RAMP_START", target_linear=60.0, slew_rate=0.08)
        log_event("warn", "obstacle", "CRITICAL_STOP", direction="front", distance_cm=11.5)
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    extra = {
        "component": component,
        "event": event,
        "extra_fields": kwargs,
    }
    _logger.log(numeric_level, event, extra=extra)


# Convenience functions
def log_info(component: str, event: str, **kwargs: Any) -> None:
    log_event("info", component, event, **kwargs)


def log_warn(component: str, event: str, **kwargs: Any) -> None:
    log_event("warn", component, event, **kwargs)


def log_error(component: str, event: str, **kwargs: Any) -> None:
    log_event("error", component, event, **kwargs)
