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
from core.hal.imu import IMUDriver
from core.logger import log_info, log_warn, log_error

_metrics_increment_fn = None


def _safe_increment_counter(key: str, count: int = 1) -> None:
    """Thread-safe cached dispatch to Prometheus metrics counter."""
    global _metrics_increment_fn
    if _metrics_increment_fn is None:
        try:
            from server.routes.metrics import increment_counter
            _metrics_increment_fn = increment_counter
        except Exception:
            return
    try:
        _metrics_increment_fn(key, count)
    except Exception:
        pass


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
        self.buzzer = Buzzer(self.cfg["gpio"].get("buzzer", 25), is_mock=self.is_mock)
        self.camera = CameraManager(self.cfg["camera"])
        self.network = NetworkManager()
        self.imu = IMUDriver(self.cfg["gpio"].get("imu", {"bus": 1, "addresses": [0x68, 0x69]}), is_mock=self.is_mock)

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
        self.speed_limit = 60

        # Cached Pi Vitals (1.5s TTL to avoid high-frequency fork/exec of vcgencmd)
        self._last_vitals: Dict[str, Any] = {
            "cpu_temp": 45.0,
            "cpu_load": 0.0,
            "ram_usage": 0.0,
            "throttled": False,
            "undervoltage": False,
        }
        self._last_vitals_time = 0.0

        # Background Supervisors
        self._lease_lock = threading.RLock()
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
        Seamlessly hands over the active lease to the requesting operator for local network control.
        """
        with self._lease_lock:
            now = time.time()
            client_key = operator_id or "driver"

            client_name = operator_name or "Driver"
            if not self.is_hardware_leased:
                print(f"[HardwareManager] Acquiring hardware pins & camera for {client_name} ({client_key})...")
                self.motors.initialize()
                if self.sensors_enabled:
                    self.ultrasonic.initialize()
                self.leds.initialize()
                self.buzzer.initialize()
                self.imu.initialize()
                self.camera.start()
                self.is_hardware_leased = True

            self.active_operator_id = client_key
            self.active_operator_name = client_name

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
        with self._lease_lock:
            if self.is_hardware_leased:
                print(f"[HardwareManager] Releasing hardware pins & camera (released by {operator_id or 'operator'})...")
                self.motors.cleanup()
                self.ultrasonic.cleanup()
                self.leds.cleanup()
                self.buzzer.cleanup()
                self.imu.cleanup()
                self.camera.stop()
                self.is_hardware_leased = False
                self.active_operator_id = None
                self.active_operator_name = None

            return {"success": True, "hardware_leased": False}

    def heartbeat(self, operator_id: Optional[str] = None) -> None:
        """Refreshes watchdog timer from teleop client."""
        # Only refresh watchdog if heartbeat comes from active operator (or during standby)
        if not self.active_operator_id or (operator_id and operator_id == self.active_operator_id):
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

        if self.active_operator_id and (not operator_id or operator_id != self.active_operator_id):
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

        # IMU Straight-Line Heading-Hold Assist (counteracts DC gearmotor asymmetry)
        effective_angular = angular
        if abs(linear) > 5.0 and abs(angular) < 1.0 and getattr(self, "imu", None) and self.imu.is_initialized:
            gz = self.imu.data.get("gz", 0.0)
            if abs(gz) > 1.2:
                # Proportional gyro feedback trim (max ±5%)
                trim = max(-5.0, min(5.0, -gz * 0.15))
                effective_angular += trim

        # Speed-Adaptive Obstacle Distance for 60 RPM Motors
        speed_factor = abs(linear) / 100.0
        effective_warning_cm = self.warning_stop_cm + (speed_factor * 15.0)

        # Obstacle avoidance check (active only when sensors are enabled)
        if self.sensors_enabled:
            front_dist = self.ultrasonic.distances.get("front")
            rear_dist = self.ultrasonic.distances.get("rear")

            # 1. Forward checks
            if linear > 0 and front_dist is not None:
                if front_dist <= self.critical_stop_cm:
                    # Critical zone: block forward drive, but allow steering away (angular) or reverse
                    if abs(effective_angular) > 0.01:
                        self.motors.set_differential_drive(0.0, effective_angular, immediate=True)
                    else:
                        self.motors.stop()
                    _safe_increment_counter("obstacle_stops")
                    log_warn("safety.obstacle", "OBSTACLE_CRITICAL_STOP", direction="front", distance_cm=front_dist)
                    return {
                        "blocked": True,
                        "throttled": False,
                        "reason": f"Front obstacle too close ({front_dist}cm)",
                        "linear": 0.0,
                        "angular": effective_angular,
                    }
                elif front_dist < effective_warning_cm:
                    # Progressive smooth deceleration towards critical threshold
                    span = max(1.0, float(effective_warning_cm - self.critical_stop_cm))
                    ratio = max(0.0, min(1.0, (front_dist - self.critical_stop_cm) / span))
                    min_crawl = 20.0
                    max_allowed = float(self.speed_limit)
                    speed_cap = min_crawl + (ratio ** 1.3) * (max_allowed - min_crawl)
                    if linear > speed_cap:
                        linear = speed_cap
                        throttled = True
                        throttled_reason = f"Proximity slowdown (Front: {front_dist}cm)"

            # 2. Reverse checks
            if linear < 0 and rear_dist is not None:
                if rear_dist <= self.critical_stop_cm:
                    if abs(effective_angular) > 0.01:
                        self.motors.set_differential_drive(0.0, effective_angular, immediate=True)
                    else:
                        self.motors.stop()
                    _safe_increment_counter("obstacle_stops")
                    log_warn("safety.obstacle", "OBSTACLE_CRITICAL_STOP", direction="rear", distance_cm=rear_dist)
                    return {
                        "blocked": True,
                        "throttled": False,
                        "reason": f"Rear obstacle too close ({rear_dist}cm)",
                        "linear": 0.0,
                        "angular": effective_angular,
                    }
                elif rear_dist < effective_warning_cm:
                    span = max(1.0, float(effective_warning_cm - self.critical_stop_cm))
                    ratio = max(0.0, min(1.0, (rear_dist - self.critical_stop_cm) / span))
                    min_crawl = 20.0
                    max_allowed = float(self.speed_limit)
                    speed_cap = min_crawl + (ratio ** 1.3) * (max_allowed - min_crawl)
                    if abs(linear) > speed_cap:
                        linear = -speed_cap
                        throttled = True
                        throttled_reason = f"Proximity slowdown (Rear: {rear_dist}cm)"

        _safe_increment_counter("drive_commands")

        self.motors.set_differential_drive(linear, effective_angular)
        return {
            "blocked": False,
            "throttled": throttled,
            "reason": throttled_reason,
            "linear": linear,
            "angular": effective_angular,
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
        """
        Continuously reads ultrasonic sensors and IMU.
        Actively intervenes in real time if rover in motion approaches an obstacle:
        - Dynamically decelerates motors in warning zone.
        - Actively brakes and halts before critical collision zone.
        """
        while self._is_running:
            if self.sensors_enabled and self.is_hardware_leased:
                try:
                    curr_l = self.motors.left_speed
                    curr_r = self.motors.right_speed

                    # Determine motion hint for ultrasonic priority scanning
                    motion_hint = None
                    if curr_l > 5 or curr_r > 5:
                        motion_hint = "forward"
                    elif curr_l < -5 or curr_r < -5:
                        motion_hint = "reverse"

                    self.ultrasonic.read_cycle(motion_hint=motion_hint)
                    self.imu.read_sensors()

                    # REAL-TIME COLLISION PREVENTION WHILE ROVER IS IN MOTION:
                    front_dist = self.ultrasonic.distances.get("front")
                    rear_dist = self.ultrasonic.distances.get("rear")

                    speed_factor = max(abs(curr_l), abs(curr_r)) / 100.0
                    adaptive_warning_cm = self.warning_stop_cm + (speed_factor * 15.0)

                    # 1. Forward motion safety check
                    if (curr_l > 0 or curr_r > 0) and front_dist is not None:
                        if front_dist <= self.critical_stop_cm:
                            # CRITICAL OBSTACLE: Apply active electromagnetic brake immediately!
                            self.motors.stop()
                            _safe_increment_counter("obstacle_stops")
                            log_warn("safety.obstacle", "ACTIVE_MOTION_CRITICAL_STOP", direction="front", distance_cm=front_dist)
                        elif front_dist < adaptive_warning_cm:
                            # PROXIMITY DECELERATION: Proactively slow down motors in real time
                            span = max(1.0, float(adaptive_warning_cm - self.critical_stop_cm))
                            ratio = max(0.0, min(1.0, (front_dist - self.critical_stop_cm) / span))
                            min_crawl = 20.0
                            max_allowed = float(self.speed_limit)
                            speed_cap = min_crawl + (ratio ** 1.3) * (max_allowed - min_crawl)
                            max_speed = max(curr_l, curr_r)
                            if max_speed > speed_cap:
                                scale = speed_cap / max_speed
                                self.motors.set_motor_speeds(curr_l * scale, curr_r * scale)

                    # 2. Reverse motion safety check
                    elif (curr_l < 0 or curr_r < 0) and rear_dist is not None:
                        if rear_dist <= self.critical_stop_cm:
                            self.motors.stop()
                            _safe_increment_counter("obstacle_stops")
                            log_warn("safety.obstacle", "ACTIVE_MOTION_CRITICAL_STOP", direction="rear", distance_cm=rear_dist)
                        elif rear_dist < adaptive_warning_cm:
                            span = max(1.0, float(adaptive_warning_cm - self.critical_stop_cm))
                            ratio = max(0.0, min(1.0, (rear_dist - self.critical_stop_cm) / span))
                            min_crawl = 20.0
                            max_allowed = float(self.speed_limit)
                            speed_cap = min_crawl + (ratio ** 1.3) * (max_allowed - min_crawl)
                            min_speed = min(curr_l, curr_r)
                            if abs(min_speed) > speed_cap:
                                scale = speed_cap / abs(min_speed)
                                self.motors.set_motor_speeds(curr_l * scale, curr_r * scale)

                except Exception as e:
                    log_error("hal.ultrasonic", "SENSOR_POLL_ERROR", error=str(e))

            time.sleep(0.015)

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
                        _safe_increment_counter("watchdog_cuts")
                        delta_ms = round((now - self.last_heartbeat_time) * 1000, 1)
                        log_warn("safety.watchdog", "WATCHDOG_TIMEOUT_CUT", delta_ms=delta_ms)

                # 2. Idle Hardware Auto-Release (frees pins for students if browser is closed)
                if (now - self.last_activity_time) > self.idle_release_timeout:
                    self.release_control(force=True)
                    log_info("safety.lease", "IDLE_AUTO_RELEASE_TRIGGERED")

            time.sleep(0.1)

    def get_pi_vitals(self) -> Dict[str, Any]:
        """Reads Raspberry Pi vital statistics with 1.5s cache to minimize CPU overhead."""
        now = time.time()
        if (now - self._last_vitals_time) < 1.5:
            return self._last_vitals.copy()

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

        self._last_vitals = vitals
        self._last_vitals_time = now
        return vitals

    def get_telemetry(self) -> Dict[str, Any]:
        """Provides full aggregated telemetry payload for WebSocket / REST."""
        return {
            "rover_name": self.cfg["system"]["name"],
            "version": self.cfg["system"]["version"],
            "is_mock": self.is_mock,
            "hardware_leased": bool(self.is_hardware_leased and self.active_operator_id),
            "active_operator_id": self.active_operator_id if self.is_hardware_leased else None,
            "active_operator_name": self.active_operator_name if self.is_hardware_leased else None,
            "motors_enabled": self.motors_enabled,
            "camera_enabled": self.camera_enabled,
            "sensors_enabled": self.sensors_enabled,
            "speed_limit": self.speed_limit,
            "motors": self.motors.get_status(),
            "ultrasonic": self.ultrasonic.get_status(),
            "leds": self.leds.get_status(),
            "buzzer": self.buzzer.get_status(),
            "imu": self.imu.get_status(),
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
