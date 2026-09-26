"""
SAM Rover - Network Management API
Provides interface discovery (wlan0, external wlan1), Wi-Fi scanning, and connection.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from core.hardware_manager import hw_manager

router = APIRouter(prefix="/api/network", tags=["Network"])


class WifiConnectPayload(BaseModel):
    ssid: str
    password: str = ""


@router.get("/interfaces")
def get_interfaces():
    """Lists all network interfaces, identifying external Wi-Fi dongles."""
    return {"interfaces": hw_manager.network.get_interfaces()}


@router.get("/wifi/scan")
def scan_wifi():
    """Scans and returns available Wi-Fi access points."""
    return {"networks": hw_manager.network.scan_wifi()}


@router.post("/wifi/connect")
def connect_wifi(payload: WifiConnectPayload):
    """Initiates connection to a target Wi-Fi network."""
    result = hw_manager.network.connect_wifi(payload.ssid, payload.password)
    return result
