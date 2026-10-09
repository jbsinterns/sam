"""
SAM Rover - System Power & Lifecycle Management API
Provides graceful shutdown, reboot, and service restart operations.
"""

import os
import sys
import time
import subprocess
import threading
from typing import Dict, Any
from fastapi import APIRouter
from core.hardware_manager import hw_manager
from core.config import config_manager

router = APIRouter(prefix="/api/system", tags=["System Management"])


def _schedule_system_command(cmd: list, delay_sec: float = 1.5):
    """Executes a system shell command after a short delay so the HTTP response is sent."""
    def _delayed_exec():
        time.sleep(delay_sec)
        try:
            hw_manager.emergency_stop()
            hw_manager.release_control(operator_id="system_shutdown", force=True)
            hw_manager.shutdown()
        except Exception as e:
            print(f"[System] Error shutting down hardware manager: {e}")

        if config_manager.is_mock or os.name == "nt":
            cmd_str = " ".join(cmd)
            print(f"[System Mock] Would execute command: {cmd_str}")
            return

        try:
            subprocess.run(cmd, check=False)
        except Exception as e:
            print(f"[System] Failed to execute {cmd}: {e}")

    thread = threading.Thread(target=_delayed_exec, daemon=True, name="SystemCommandThread")
    thread.start()


@router.get("/status")
def get_system_status() -> Dict[str, Any]:
    """Returns system status, uptime, and host details."""
    return {
        "rover": config_manager.get("system", "name", default="SAM"),
        "version": config_manager.get("system", "version", default="2.0.0"),
        "is_mock": config_manager.is_mock,
        "platform": sys.platform,
    }


@router.post("/shutdown")
def system_shutdown() -> Dict[str, Any]:
    """Safely halts Raspberry Pi OS filesystem writes and prepares for power cut."""
    print("[System API] Graceful shutdown requested.")
    _schedule_system_command(["sudo", "shutdown", "-h", "now"], delay_sec=1.5)
    return {
        "success": True,
        "action": "shutdown",
        "message": "Shutting down SAM Rover. Safe to power off in 15 seconds.",
        "countdown_sec": 15,
    }


@router.post("/reboot")
def system_reboot() -> Dict[str, Any]:
    """Safely reboots the Raspberry Pi system."""
    print("[System API] System reboot requested.")
    _schedule_system_command(["sudo", "reboot"], delay_sec=1.5)
    return {
        "success": True,
        "action": "reboot",
        "message": "Rebooting SAM Rover. Reconnecting in 45 seconds.",
        "countdown_sec": 45,
    }


@router.post("/restart-service")
def system_restart_service() -> Dict[str, Any]:
    """Restarts the SAM background systemd service without rebooting the OS."""
    print("[System API] Service restart requested.")
    _schedule_system_command(["sudo", "systemctl", "restart", "sam.service"], delay_sec=1.0)
    return {
        "success": True,
        "action": "restart_service",
        "message": "Restarting SAM Rover service daemon. Reconnecting in 5 seconds.",
        "countdown_sec": 5,
    }
