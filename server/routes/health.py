"""
SAM Rover - Kubernetes & Edge Health Probes
Provides /healthz (liveness) and /readyz (readiness) endpoints for systemd, Docker, and K3s.
"""

import time
from fastapi import APIRouter, Response, status
from core.config import config_manager
from core.hardware_manager import hw_manager

router = APIRouter(tags=["Health & Probes"])

_start_time = time.time()


@router.get("/healthz")
def liveness_probe() -> dict:
    """
    Liveness Probe:
    Confirms that the FastAPI process and asyncio event loop are responsive.
    If this endpoint hangs or fails, systemd / Docker restarts the service.
    """
    return {
        "status": "alive",
        "rover": config_manager.get("system", "name", default="SAM"),
        "version": config_manager.get("system", "version", default="2.0.0"),
        "uptime_sec": round(time.time() - _start_time, 1),
    }


@router.get("/readyz")
def readiness_probe(response: Response) -> dict:
    """
    Readiness Probe:
    Performs non-blocking diagnostic checks on all hardware supervisor threads,
    pin configurations, and camera availability.
    Returns 200 OK if ready for traffic, or 503 if any subsystem is degraded.
    """
    # 1. Background Supervisor Thread Liveness
    supervisor_ok = bool(
        hasattr(hw_manager, "_supervisor_thread") and hw_manager._supervisor_thread.is_alive()
    )

    # 2. Sensor Polling Thread Liveness
    sensor_thread_ok = bool(
        hasattr(hw_manager, "_sensor_thread") and hw_manager._sensor_thread.is_alive()
    )

    # 3. Pydantic Configuration Validation Check
    config_ok = getattr(config_manager, "validated_schema", None) is not None

    # 4. Camera Readiness (device port tested or simulation ready)
    camera_ok = bool(
        hw_manager.camera.is_running or hw_manager.camera.cap is not None or config_manager.is_mock
    )

    checks = {
        "supervisor_thread": supervisor_ok,
        "sensor_thread": sensor_thread_ok,
        "config_schema_valid": config_ok,
        "camera_ready": camera_ok,
        "hardware_mode": "mock" if config_manager.is_mock else "rpi_physical",
    }

    critical_passed = supervisor_ok and sensor_thread_ok and config_ok and camera_ok

    if not critical_passed:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "degraded",
            "ready": False,
            "checks": checks,
        }

    return {
        "status": "ready",
        "ready": True,
        "checks": checks,
    }
