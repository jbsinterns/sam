"""
SAM Rover - Hardware Manager & Central Supervisor
Coordinates dynamic hardware leasing, watchdog timeout safety, obstacle avoidance,
and component health tracking.
"""

import time
import threading
from typing import Dict, Any, Optional
from core.config import config_manager
from core.hal.motors import MotorDriver
from core.hal.ultrasonic import UltrasonicSensorArray
from core.hal.leds import LEDController
from core.hal.buzzer import Buzzer
from core.hal.camera import CameraManager
from core.hal.network import NetworkManager


class HardwareManager:
    """
    Central coordinator of all SAM subsystems.
    Implements dynamic GPIO lease/release and failsafe watchdog.
    """

    def __init__(self):
        self.cfg = config_manager.config
        self.is_mock = config_manager.is_mock

        # Instantiation of HAL devices (uninitialized until acquired)
        self.motors = MotorDriver(self.cfg["gpio"]["motors"], is_mock=self.is_mock)
        self.ultrasonic = UltrasonicSensorArray(self.cfg["gpio"]["ultrasonic"], is_mock=self.is_mock)
        self.leds = LEDController(self.cfg["gpio"]["leds"], is_mock=self.is_mock)
        self.buzzer = Buzzer(self.cfg["gpio"].get("buzzer", 20), is_mock=self.is_mock)
        self.camera = CameraManager(self.cfg["camera"])
        self.network = NetworkManager()

        # Dynamic Lease & Control States
        self.is_hardware_leased = False
        self.active_operator_id: Optional[str] = None
        self.active_operator_name: Optional[str] = None
        self.last_heartbeat_time = time.time()
        self.last_activity_time = time.time()

        # Driving & Safety Parameters
        self.motors_enabled = True       # Master motor output switch
        self.camera_enabled = True       # Video feed streaming switch
        self.sensors_enabled = True      # Polling enabled / disabled (Assisted drive if ON, Manual if OFF)
        self.watchdog_timeout = self.cfg["safety"].get("watchdog_timeout_sec", 0.5)
        self.idle_release_timeout = self.cfg["safety"].get("idle_hardware_release_sec", 60.0)
        self.warning_stop_cm = self.cfg["safety"].get("obstacle_warning_cm", 35.0)
        self.critical_stop_cm = self.cfg["safety"].get("obstacle_critical_stop_cm", 15.0)

        # Background Supervisors
        self._is_running = True
        self._supervisor_thread = threading.Thread(target=self._supervisor_loop, daemon=True)
        self._sensor_thread = threading.Thread(target=self._sensor_polling_loop, daemon=True)

        # Test camera port on startup if present, but keep physical device released (unclaimed)
        self.camera.test_camera_port()

        # Start background supervisors (sensors/watchdog idle until claimed)
        self._supervisor_thread.start()
        self._sensor_thread.start()

    def acquire_control(self, operator_id: Optional[str] = None, operator_name: Optional[str] = None, force: bool = True) -> Dict[str, Any]:
        """
        Dynamically claims GPIO pins when web UI or operator requests drive control.
        Always grants control to the claiming operator, seamlessly handing over the active lease.
        """
        now = time.time()
        client_key = operator_id or "driver"

        self.active_operator_id = client_key
        self.active_operator_name = operator_name or "Driver"

        if not self.is_hardware_leased:
            print(f"[HardwareManager] Acquiring hardware pins & camera for {self.active_operator_name} ({self.active_operator_id})...")
            self.motors.initialize()
            if self.sensors_enabled:
                self.ultrasonic.initialize()
            self.leds.initialize()
            self.buzzer.initialize()
            self.camera.start()
            self.is_hardware_leased = True

        self.last_activity_time = now
        self.last_heartbeat_time = now
        return {
            "success": True,
            "role": "operator",
            "operator_id": self.active_operator_id,
            "operator_name": self.active_operator_name,
            "hardware_leased": True,
        }

    def release_control(self, operator_id: Optional[str] = None, force: bool = True) -> Dict[str, Any]:
        """
        Explicitly releases all GPIO pins and camera, leaving hardware completely free.
        """
        if self.is_hardware_leased:
            print("[HardwareManager] Releasing hardware pins & camera to free state...")
            self.motors.cleanup()
            self.ultrasonic.cleanup()
            self.leds.cleanup()
            self.buzzer.cleanup()
            self.camera.stop()
            self.is_hardware_leased = False
            self.active_operator_id = None
            self.active_operator_name = None

        return {"success": True, "hardware_leased": False}

    def heartbeat(self, operator_id: Optional[str] = None) -> None:
        """Refreshes watchdog timer from teleop client."""
        if (
            not operator_id
            or not self.active_operator_id
            or operator_id == self.active_operator_id
            or self.active_operator_id in ("driver", "primary-operator")
            or operator_id in ("driver", "primary-operator")
        ):
            self.last_heartbeat_time = time.time()
            self.last_activity_time = time.time()

    def drive(self, linear: float, angular: float, operator_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes drive command with safety and multi-client lease arbitration checks.
        linear: -100 (reverse) to +100 (forward)
        angular: -100 (left) to +100 (right)
        """
        self.heartbeat(operator_id)
        if not self.is_hardware_leased:
            return {
                "blocked": True,
                "throttled": False,
                "reason": "Hardware unclaimed. Press Claim button to control.",
                "linear": 0.0,
                "angular": 0.0,
            }

        if (
            self.active_operator_id
            and operator_id
            and operator_id != self.active_operator_id
            and self.active_operator_id not in ("driver", "primary-operator")
            and operator_id not in ("driver", "primary-operator")
        ):
            return {
                "blocked": True,
                "throttled": False,
                "reason": f"Observer mode: Rover controlled by {self.active_operator_name or 'active driver'}",
                "linear": 0.0,
                "angular": 0.0,
            }

        if not self.motors_enabled:
            self.motors.stop()
            return {
                "blocked": True,
                "throttled": False,
                "reason": "Motors disabled via toggle",
                "linear": 0.0,
                "angular": 0.0,
            }

        throttled = False
        throttled_reason = None

        # Obstacle avoidance check (active only when sensors are enabled)
        if self.sensors_enabled:
            front_dist = self.ultrasonic.distances.get("front")
            rear_dist = self.ultrasonic.distances.get("rear")

            # 1. Forward checks
            if linear > 0 and front_dist is not None:
                if front_dist <= self.critical_stop_cm:
                    self.motors.stop()
                    try:
                        from server.routes.metrics import increment_counter
                        increment_counter("obstacle_stops")
                    except Exception:
                        pass
                    try:
                        from core.logger import log_warn
                        log_warn("safety.obstacle", "OBSTACLE_CRITICAL_STOP", direction="front", distance_cm=front_dist)
                    except Exception:
                        pass
                    return {
                        "blocked": True,
                        "throttled": False,
                        "reason": f"Front obstacle too close ({front_dist}cm)",
                        "linear": 0.0,
                        "angular": 0.0,
                    }
                elif front_dist < self.warning_stop_cm:
                    # Progressive proportional deceleration: scale speed between 20% and 100%
                    ratio = (front_dist - self.critical_stop_cm) / max(1.0, (self.warning_stop_cm - self.critical_stop_cm))
                    speed_cap = max(20.0, ratio * 100.0)
                    if linear > speed_cap:
                        linear = speed_cap
                        throttled = True
                        throttled_reason = f"Proximity slowdown (Front: {front_dist}cm)"

            # 2. Reverse checks
            if linear < 0 and rear_dist is not None:
                if rear_dist <= self.critical_stop_cm:
                    self.motors.stop()
                    try:
                        from server.routes.metrics import increment_counter
                        increment_counter("obstacle_stops")
                    except Exception:
                        pass
                    try:
                        from core.logger import log_warn
                        log_warn("safety.obstacle", "OBSTACLE_CRITICAL_STOP", direction="rear", distance_cm=rear_dist)
                    except Exception:
                        pass
                    return {
                        "blocked": True,
                        "throttled": False,
                        "reason": f"Rear obstacle too close ({rear_dist}cm)",
                        "linear": 0.0,
                        "angular": 0.0,
                    }
                elif rear_dist < self.warning_stop_cm:
                    ratio = (rear_dist - self.critical_stop_cm) / max(1.0, (self.warning_stop_cm - self.critical_stop_cm))
                    speed_cap = max(20.0, ratio * 100.0)
                    if abs(linear) > speed_cap:
                        linear = -speed_cap
                        throttled = True
                        throttled_reason = f"Proximity slowdown (Rear: {rear_dist}cm)"

        try:
            from server.routes.metrics import increment_counter
            increment_counter("drive_commands")
        except Exception:
            pass

        self.motors.set_differential_drive(linear, angular)
        return {
            "blocked": False,
            "throttled": throttled,
            "reason": throttled_reason,
            "linear": linear,
            "angular": angular,
        }

    def emergency_stop(self) -> None:
        """Instantly cuts all motor drive."""
        self.motors.stop()
        try:
            from core.logger import log_warn
            log_warn("safety.estop", "EMERGENCY_STOP_TRIGGERED")
        except Exception:
            pass

    def _sensor_polling_loop(self) -> None:
        """Continuously reads ultrasonic sensors if enabled and hardware leased."""
        while self._is_running:
            if self.sensors_enabled and self.is_hardware_leased:
                try:
                    self.ultrasonic.read_all()
                except Exception as e:
                    try:
                        from core.logger import log_error
                        log_error("hal.ultrasonic", "SENSOR_POLL_ERROR", error=str(e))
                    except Exception:
                        pass
            time.sleep(0.1)

    def _supervisor_loop(self) -> None:
        """
        Supervises watchdog timeout and idle hardware auto-release.
        """
        while self._is_running:
            now = time.time()

            # 1. Teleop Watchdog: if driving and no heartbeat received within watchdog_timeout
            if self.is_hardware_leased:
                if (abs(self.motors.left_speed) > 0 or abs(self.motors.right_speed) > 0):
                    if (now - self.last_heartbeat_time) > self.watchdog_timeout:
                        self.motors.stop()
                        try:
                            from server.routes.metrics import increment_counter
                            increment_counter("watchdog_cuts")
                        except Exception:
                            pass
                        try:
                            from core.logger import log_warn
                            delta_ms = round((now - self.last_heartbeat_time) * 1000, 1)
                            log_warn("safety.watchdog", "WATCHDOG_TIMEOUT_CUT", delta_ms=delta_ms)
                        except Exception:
                            pass

                # 2. Idle Hardware Auto-Release (frees pins for students if browser is closed)
                if (now - self.last_activity_time) > self.idle_release_timeout:
                    self.release_control()
                    try:
                        from core.logger import log_info
                        log_info("safety.lease", "IDLE_AUTO_RELEASE_TRIGGERED")
                    except Exception:
                        pass

            time.sleep(0.1)

    def get_pi_vitals(self) -> Dict[str, Any]:
        """Reads Raspberry Pi vital statistics (temperature, load, memory, undervoltage)."""
        vitals = {
            "cpu_temp": None,
            "cpu_load": 0.0,
            "ram_usage": 0.0,
            "throttled": False,
            "undervoltage": False,
        }
        # 1. CPU Temperature (Linux / Raspberry Pi thermal zone)
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                vitals["cpu_temp"] = round(int(f.read().strip()) / 1000.0, 1)
        except Exception:
            vitals["cpu_temp"] = 46.5

        # 2. CPU Load & RAM Usage
        try:
            import psutil
            vitals["cpu_load"] = round(psutil.cpu_percent(interval=None), 1)
            vitals["ram_usage"] = round(psutil.virtual_memory().percent, 1)
        except Exception:
            vitals["cpu_load"] = 12.0
            vitals["ram_usage"] = 28.5

        # 3. Throttled / Under-voltage Check (Raspberry Pi specific)
        try:
            import subprocess
            res = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=0.1)
            if res.returncode == 0 and "throttled=" in res.stdout:
                val = int(res.stdout.strip().split("=")[1], 16)
                vitals["throttled"] = (val != 0)
                vitals["undervoltage"] = bool(val & 0x1)  # Bit 0: Under-voltage detected
        except Exception:
            pass

        return vitals

    def get_telemetry(self) -> Dict[str, Any]:
        """Provides full aggregated telemetry payload for WebSocket / REST."""
        return {
            "rover_name": self.cfg["system"]["name"],
            "version": self.cfg["system"]["version"],
            "is_mock": self.is_mock,
            "hardware_leased": self.is_hardware_leased,
            "active_operator_id": self.active_operator_id,
            "active_operator_name": self.active_operator_name,
            "motors_enabled": self.motors_enabled,
            "camera_enabled": self.camera_enabled,
            "sensors_enabled": self.sensors_enabled,
            "motors": self.motors.get_status(),
            "ultrasonic": self.ultrasonic.get_status(),
            "leds": self.leds.get_status(),
            "buzzer": self.buzzer.get_status(),
            "vitals": self.get_pi_vitals(),
            "camera": self.camera.get_status(),
            "system_time": time.time(),
        }

    def shutdown(self) -> None:
        """Clean shutdown of all subsystems."""
        self._is_running = False
        self.release_control()
        self.camera.stop()


# Global Singleton instance
hw_manager = HardwareManager()
