"""
SAM Rover SDK - Client Library
Provides intuitive APIs for moving the rover, reading ultrasonic distances,
controlling LEDs, and auto-detecting camera & IMU ports.
"""

import time
import shutil
import subprocess
from typing import Dict, Any, Optional, List


class SamRover:
    """
    Main SDK class for controlling the SAM Rover.
    Works both directly on the rover hardware and in mock simulation.
    """

    def __init__(self, host: Optional[str] = None):
        """
        :param host: Optional remote API URL (e.g. 'http://192.168.4.1:8000').
                     If None, attaches directly to local core hardware manager.
        """
        self.host = host
        self._local_hw = None

        if self.host is None:
            # Local Direct HAL Mode
            from core.hardware_manager import hw_manager
            self._local_hw = hw_manager
            self._local_hw.acquire_control()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        self.release()

    # --- Movement Commands ---

    def forward(self, speed: float = 50.0) -> None:
        """Drives forward with speed (0 to 100)."""
        if self._local_hw:
            self._local_hw.drive(abs(speed), 0.0)

    def backward(self, speed: float = 50.0) -> None:
        """Drives backward with speed (0 to 100)."""
        if self._local_hw:
            self._local_hw.drive(-abs(speed), 0.0)

    def turn_left(self, speed: float = 50.0) -> None:
        """Pivot turns to the left on the spot."""
        if self._local_hw:
            self._local_hw.drive(0.0, -abs(speed))

    def turn_right(self, speed: float = 50.0) -> None:
        """Pivot turns to the right on the spot."""
        if self._local_hw:
            self._local_hw.drive(0.0, abs(speed))

    def drive(self, linear: float, angular: float) -> Dict[str, Any]:
        """
        Differential steering.
        linear: -100 to 100
        angular: -100 to 100
        """
        if self._local_hw:
            return self._local_hw.drive(linear, angular)
        return {"linear": linear, "angular": angular}

    def set_motors(self, left_speed: float, right_speed: float) -> None:
        """Sets individual motor velocities (-100 to 100)."""
        if self._local_hw:
            self._local_hw.motors.set_motor_speeds(left_speed, right_speed)

    def stop(self) -> None:
        """Immediately stops all motor movement."""
        if self._local_hw:
            self._local_hw.emergency_stop()

    def release(self) -> None:
        """Releases all GPIO pins so other student scripts can run."""
        if self._local_hw:
            self._local_hw.release_control()

    # --- Sensor & LED Commands ---

    def get_distances(self) -> Dict[str, Optional[float]]:
        """
        Returns distances in cm from all 4 ultrasonic sensors.
        Format: {'front': float, 'rear': float, 'left': float, 'right': float}
        """
        if self._local_hw:
            return self._local_hw.ultrasonic.read_all()
        return {}

    def get_distance(self, direction: str) -> Optional[float]:
        """Returns distance in cm for 'front', 'rear', 'left', or 'right'."""
        if self._local_hw:
            return self._local_hw.ultrasonic.read_distance(direction)
        return None

    def set_led(self, direction: str, state: bool) -> None:
        """Turns on/off a directional LED ('front', 'rear', 'left', 'right')."""
        if self._local_hw:
            self._local_hw.leds.set_led(direction, state)

    def set_all_leds(self, state: bool) -> None:
        """Turns all 4 LEDs on or off."""
        if self._local_hw:
            self._local_hw.leds.set_all(state)

    # --- Hardware Auto-Detection Utilities ---

    @staticmethod
    def detect_camera_port() -> Optional[int]:
        """
        Auto-scans USB webcam ports and returns the first available camera index.
        """
        print("[Samsdk] Scanning for active camera ports...")
        try:
            import cv2
        except ImportError:
            print("[Samsdk] OpenCV (cv2) not installed. Physical camera scan skipped.")
            return None

        for idx in range(5):
            try:
                cap = cv2.VideoCapture(idx)
                if cap.isOpened():
                    ret, _ = cap.read()
                    cap.release()
                    if ret:
                        print(f"[Samsdk] Camera found at index {idx} (/dev/video{idx})")
                        return idx
            except Exception:
                continue
        print("[Samsdk] No physical camera detected.")
        return None

    @staticmethod
    def detect_imu_address(bus_number: int = 1) -> List[int]:
        """
        Scans I2C bus for IMU devices (checks 0x68 and 0x69 typically used by MPU-6050/9250).
        """
        detected = []
        if shutil.which("i2cdetect"):
            try:
                res = subprocess.run(
                    ["i2cdetect", "-y", str(bus_number)],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                for addr_str in ("68", "69"):
                    if addr_str in res.stdout:
                        detected.append(int(addr_str, 16))
            except Exception as e:
                print(f"[Samsdk] I2C scan warning: {e}")
        else:
            # Mock auto-detection
            detected = [0x68]

        print(f"[Samsdk] IMU detected on I2C address(es): {[hex(a) for a in detected]}")
        return detected

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns full diagnostic status."""
        if self._local_hw:
            return self._local_hw.get_telemetry()
        return {}
