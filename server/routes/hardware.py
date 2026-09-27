"""
SAM Rover - Hardware Management & Lease REST API
Enables manual GPIO lock claiming / releasing and hardware status inspection.
"""

from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from core.hardware_manager import hw_manager

router = APIRouter(prefix="/api/hardware", tags=["Hardware"])


class BooleanPayload(BaseModel):
    enabled: bool


class LeasePayload(BaseModel):
    operator_id: Optional[str] = None
    operator_name: Optional[str] = None
    force: bool = True


@router.get("/telemetry")
def get_telemetry():
    """Returns aggregated system telemetry."""
    return hw_manager.get_telemetry()


@router.post("/acquire")
def acquire_hardware(payload: Optional[LeasePayload] = None):
    """Claims GPIO pins for web control with operator lease arbitration."""
    p_id = payload.operator_id if (payload and payload.operator_id) else None
    p_name = payload.operator_name if (payload and payload.operator_name) else "Driver"
    force = payload.force if (payload and payload.force is not None) else True
    return hw_manager.acquire_control(operator_id=p_id, operator_name=p_name, force=force)


@router.post("/release")
def release_hardware(payload: Optional[LeasePayload] = None):
    """Frees all GPIO pins completely."""
    p_id = payload.operator_id if payload else None
    force = payload.force if (payload and payload.force is not None) else True
    return hw_manager.release_control(operator_id=p_id, force=force)



class SpeedPayload(BaseModel):
    speed: int


@router.post("/speed")
def set_speed_limit(payload: SpeedPayload):
    """Updates the active speed limit gear on the rover hardware."""
    hw_manager.speed_limit = int(payload.speed)
    return {"speed_limit": hw_manager.speed_limit}


@router.post("/emergency_stop")
def emergency_stop():
    """Instantly halts all motor drive."""
    hw_manager.emergency_stop()
    return {"success": True, "message": "Emergency stop executed"}


@router.post("/motors")
def toggle_motors(payload: BooleanPayload):
    """Enables or disables motor outputs."""
    hw_manager.motors_enabled = payload.enabled
    if not payload.enabled:
        hw_manager.emergency_stop()
    return {"motors_enabled": hw_manager.motors_enabled}


@router.post("/camera")
def toggle_camera(payload: BooleanPayload):
    """Enables or disables video stream."""
    hw_manager.camera_enabled = payload.enabled
    return {"camera_enabled": hw_manager.camera_enabled}


@router.post("/sensors")
def toggle_sensors(payload: BooleanPayload):
    """Enables or disables ultrasonic sensor polling."""
    hw_manager.sensors_enabled = payload.enabled
    return {"sensors_enabled": hw_manager.sensors_enabled}


@router.post("/leds/{direction}/toggle")
def toggle_led(direction: str):
    """Toggles a specific directional LED."""
    success = hw_manager.leds.toggle(direction)
    return {"success": success, "state": hw_manager.leds.state}


@router.post("/leds/all")
def set_all_leds(payload: BooleanPayload):
    """Turns all LEDs ON or OFF."""
    hw_manager.leds.set_all(payload.enabled)
    return {"state": hw_manager.leds.state}


@router.post("/buzzer")
def set_buzzer(payload: BooleanPayload):
    """Sets manual buzzer ON or OFF."""
    if payload.enabled:
        hw_manager.buzzer.on()
    else:
        hw_manager.buzzer.off()
    return {"state": hw_manager.buzzer.state}


@router.post("/buzzer/toggle")
def toggle_buzzer():
    """Toggles manual buzzer state."""
    state = hw_manager.buzzer.toggle()
    return {"state": state}

