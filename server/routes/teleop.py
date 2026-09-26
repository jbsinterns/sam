"""
SAM Rover - WebSocket Teleoperation & Realtime Telemetry
Handles bidirectional control, analog joystick vectors, heartbeat packets,
and live ultrasonic sensor feedback.
"""

import asyncio
import json
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from core.hardware_manager import hw_manager

router = APIRouter(tags=["Teleop"])


@router.websocket("/ws/teleop")
async def websocket_teleop_endpoint(websocket: WebSocket):
    """
    Bidirectional WebSocket for low-latency teleoperation and telemetry streaming.
    Preserves current hardware lease status on connect/refresh.
    """
    await websocket.accept()


    async def telemetry_broadcaster():
        """Pushes telemetry every 100ms."""
        try:
            while True:
                telemetry = hw_manager.get_telemetry()
                await websocket.send_text(json.dumps({
                    "type": "telemetry",
                    "data": telemetry,
                }))
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    broadcast_task = asyncio.create_task(telemetry_broadcaster())

    client_operator_id: Optional[str] = None

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                mtype = msg.get("type")
                if "operator_id" in msg and msg["operator_id"]:
                    client_operator_id = str(msg["operator_id"])

                if mtype == "heartbeat":
                    hw_manager.heartbeat(operator_id=msg.get("operator_id"))

                elif mtype == "ping":
                    # Echo timestamp back immediately for round-trip latency (RTT) calculation
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "t": msg.get("t", 0),
                    }))

                elif mtype == "drive":
                    linear = float(msg.get("linear", 0.0))
                    angular = float(msg.get("angular", 0.0))
                    res = hw_manager.drive(linear, angular, operator_id=msg.get("operator_id"))
                    if res.get("blocked"):
                        await websocket.send_text(json.dumps({
                            "type": "warning",
                            "message": res.get("reason"),
                        }))
                    elif res.get("throttled"):
                        await websocket.send_text(json.dumps({
                            "type": "caution",
                            "message": res.get("reason"),
                        }))

                elif mtype == "stop":
                    hw_manager.emergency_stop()

                elif mtype == "toggle_motors":
                    val = bool(msg.get("value", True))
                    hw_manager.motors_enabled = val
                    if not val:
                        hw_manager.emergency_stop()

                elif mtype == "toggle_camera":
                    val = bool(msg.get("value", True))
                    hw_manager.camera_enabled = val

                elif mtype == "toggle_sensors":
                    val = bool(msg.get("value", True))
                    hw_manager.sensors_enabled = val

                elif mtype == "set_led":
                    direction = msg.get("direction", "")
                    state = bool(msg.get("state", False))
                    hw_manager.leds.set_led(direction, state)

                elif mtype == "toggle_led":
                    direction = msg.get("direction", "")
                    hw_manager.leds.toggle(direction)

                elif mtype in ("set_all_leds", "toggle_all_leds"):
                    state = msg.get("state")
                    if state is None:
                        any_on = any(hw_manager.leds.state.values())
                        hw_manager.leds.set_all(not any_on)
                    else:
                        hw_manager.leds.set_all(bool(state))

                elif mtype == "toggle_buzzer":
                    hw_manager.buzzer.toggle()

                elif mtype == "set_buzzer":
                    state = bool(msg.get("state", False))
                    if state:
                        hw_manager.buzzer.on()
                    else:
                        hw_manager.buzzer.off()

                elif mtype == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "t": msg.get("t", 0),
                    }))

            except json.JSONDecodeError:
                pass
            except Exception as e:
                print(f"[Teleop WS] Error processing packet: {e}")

    except WebSocketDisconnect:
        pass
    finally:
        broadcast_task.cancel()
        # Only stop drive if this disconnecting WebSocket was the active operator
        is_active_driver = (
            hw_manager.is_hardware_leased
            and hw_manager.active_operator_id
            and client_operator_id
            and (
                client_operator_id == hw_manager.active_operator_id
                or client_operator_id in ("driver", "primary-operator")
            )
        )
        if is_active_driver:
            print(f"[Teleop WS] Active operator ({client_operator_id}) disconnected. Safe emergency stop triggered.")
            hw_manager.emergency_stop()
        else:
            print(f"[Teleop WS] Disconnected client ({client_operator_id or 'observer'}). Active driver unaffected.")
