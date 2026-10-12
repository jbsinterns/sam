"""
SAM Rover SDK - Client Library
Provides intuitive APIs for moving the rover, reading ultrasonic distances,
controlling LEDs, buzzer, IMU, camera, and ArUco computer vision tracking.
"""

import time
import shutil
import subprocess
import threading
from typing import Dict, Any, Optional, List, Tuple
import numpy as np

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False


class LEDDevice:
    """Wrapper for an individual directional LED with non-blocking blink support."""

    def __init__(self, rover: "SamRover", direction: str):
        self.rover = rover
        self.direction = direction
        self._blink_thread: Optional[threading.Thread] = None
        self._blinking = False

    def on(self) -> None:
        self.stop_blink()
        self.rover.set_led(self.direction, True)

    def off(self) -> None:
        self.stop_blink()
        self.rover.set_led(self.direction, False)

    def toggle(self) -> None:
        if self.rover._local_hw:
            self.rover._local_hw.leds.toggle(self.direction)

    def start_blink(self, interval: float = 0.5) -> None:
        """Starts non-blocking background blinking at the given interval (seconds)."""
        self.stop_blink()
        self._blinking = True

        def _blink_worker():
            state = True
            while self._blinking:
                self.rover.set_led(self.direction, state)
                state = not state
                time.sleep(max(0.05, interval))
            self.rover.set_led(self.direction, False)

        self._blink_thread = threading.Thread(target=_blink_worker, daemon=True, name=f"Blink-{self.direction}")
        self._blink_thread.start()

    def stop_blink(self) -> None:
        """Stops background blinking and ensures the LED is OFF."""
        self._blinking = False
        if self._blink_thread and self._blink_thread.is_alive():
            self._blink_thread.join(timeout=0.2)
        self._blink_thread = None
        self.rover.set_led(self.direction, False)


class UltrasonicDevice:
    """Wrapper for an individual ultrasonic distance sensor."""

    def __init__(self, rover: "SamRover", direction: str):
        self.rover = rover
        self.direction = direction

    def get_distance(self, fallback: float = 999.0) -> float:
        """Reads distance in centimeters. Returns fallback on timeout or error."""
        val = self.rover.get_distance(self.direction)
        if val is None or val < 0:
            return fallback
        return val


class BuzzerDevice:
    """Wrapper for the piezo buzzer / audio horn."""

    def __init__(self, rover: "SamRover"):
        self.rover = rover
        self._beep_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def on(self) -> None:
        if self.rover._local_hw:
            self.rover._local_hw.buzzer.on()

    def off(self) -> None:
        self.stop_beep()
        if self.rover._local_hw:
            self.rover._local_hw.buzzer.off()

    def toggle(self) -> None:
        if self.rover._local_hw:
            self.rover._local_hw.buzzer.toggle()

    def beep(self, duration: float = 0.2, count: int = 1, delay: float = 0.1, blocking: bool = True) -> None:
        """Plays one or more audible chirps blockingly or in a background thread."""
        # Handle Arduino/tone(freq, duration) style calls, e.g. beep(1000, 0.2)
        if duration > 10.0 and isinstance(count, (int, float)) and count < 10.0:
            duration = float(count)
            count = 1

        self.stop_beep()
        self._stop_event.clear()

        def _worker():
            for i in range(int(count)):
                if self._stop_event.is_set():
                    break
                if self.rover._local_hw:
                    self.rover._local_hw.buzzer.on()
                time.sleep(duration)
                if self.rover._local_hw:
                    self.rover._local_hw.buzzer.off()
                if i < count - 1 and not self._stop_event.is_set():
                    time.sleep(delay)

        if blocking:
            _worker()
        else:
            self._beep_thread = threading.Thread(target=_worker, daemon=True, name="BuzzerBeepThread")
            self._beep_thread.start()

    def stop_beep(self) -> None:
        """Aborts any background beeping sequence immediately."""
        self._stop_event.set()
        if self.rover._local_hw:
            self.rover._local_hw.buzzer.off()
        if self._beep_thread and self._beep_thread.is_alive():
            self._beep_thread.join(timeout=0.2)
        self._beep_thread = None


class DrivetrainDevice:
    """Wrapper for differential drivetrain locomotion."""

    def __init__(self, rover: "SamRover"):
        self.rover = rover

    def forward(self, speed: float = 50.0) -> None:
        self.rover.forward(speed)

    def backward(self, speed: float = 50.0) -> None:
        self.rover.backward(speed)

    def turn_left(self, speed: float = 50.0) -> None:
        self.rover.turn_left(speed)

    def turn_right(self, speed: float = 50.0) -> None:
        self.rover.turn_right(speed)

    def drive(self, left_speed: float, right_speed: float) -> None:
        """Sets raw left and right motor velocities (-100 to 100, or -1.0 to 1.0 normalized)."""
        if -1.0 <= left_speed <= 1.0 and -1.0 <= right_speed <= 1.0 and (left_speed != 0 or right_speed != 0):
            left_speed *= 100.0
            right_speed *= 100.0
        self.rover.set_motors(left_speed, right_speed)

    def stop(self) -> None:
        self.rover.stop()


class IMUDevice:
    """Wrapper for I2C 6-DOF / 9-DOF IMU."""

    def __init__(self, rover: "SamRover"):
        self.rover = rover

    def read_sensors(self) -> Dict[str, float]:
        """Returns dictionary of {'ax', 'ay', 'az', 'gx', 'gy', 'gz', 'pitch', 'roll', 'temp_c'}."""
        return self.rover.get_imu()

    def read(self) -> Dict[str, float]:
        return self.read_sensors()

    def close(self) -> None:
        pass


class CameraDevice:
    """Wrapper for onboard camera video capture."""

    def __init__(self, rover: "SamRover"):
        self.rover = rover
        self._cap = None

    def get_capture(self, device_index: int = 0) -> Optional["cv2.VideoCapture"]:
        if not HAS_OPENCV:
            return None
        if self._cap is None or not self._cap.isOpened():
            self._cap = cv2.VideoCapture(device_index)
        return self._cap

    def capture_frame(self, device_index: int = 0) -> Optional[np.ndarray]:
        if not HAS_OPENCV:
            return None
        cap = cv2.VideoCapture(device_index)
        if not cap.isOpened():
            return None
        try:
            ret, frame = cap.read()
            return frame if ret else None
        finally:
            cap.release()

    def release(self) -> None:
        if self._cap and self._cap.isOpened():
            self._cap.release()
        self._cap = None


class ArUcoTracker:
    """Detects and overlays DICT_4X4_50 ArUco tracking markers on captured frames."""

    def __init__(self, dictionary_id: Optional[int] = None):
        if not HAS_OPENCV:
            raise RuntimeError("OpenCV (cv2) is required for ArUcoTracker.")
        dict_id = dictionary_id if dictionary_id is not None else cv2.aruco.DICT_4X4_50
        self.dictionary = cv2.aruco.getPredefinedDictionary(dict_id)
        self.parameters = cv2.aruco.DetectorParameters()
        self.detector = cv2.aruco.ArucoDetector(self.dictionary, self.parameters)

    def detect(self, frame: np.ndarray) -> Tuple[List, List[int], List]:
        """Detects markers and returns (corners, flat ID list, rejected)."""
        if frame is None:
            return [], [], []
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, rejected = self.detector.detectMarkers(gray)
        flat_ids = [int(i[0]) for i in ids] if ids is not None else []
        return corners, flat_ids, rejected

    def draw_markers(self, frame: np.ndarray, corners: list, ids: list) -> Optional[np.ndarray]:
        """Draws bounding boxes and numeric ID labels onto the frame, returning an annotated copy."""
        if frame is None:
            return None
        annotated = frame.copy()
        if len(corners) > 0 and len(ids) > 0:
            ids_arr = np.array([[i] for i in ids], dtype=np.int32)
            cv2.aruco.drawDetectedMarkers(annotated, corners, ids_arr)
        return annotated


class IMUTracker:
    """Manages background polling and integration of gyro readings for yaw tracking."""

    def __init__(self, imu_device: IMUDevice):
        self.imu = imu_device
        self.yaw = 0.0
        self.gyro_bias_z = 0.0
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

    def calibrate(self, samples: int = 100, delay: float = 0.01) -> None:
        """Calculates gyroscope zero-rate offset by averaging static readings."""
        print("[IMUTracker] Calibrating gyroscope. Keep robot completely still...")
        bias_sum = 0.0
        valid_samples = 0
        for _ in range(samples):
            vals = self.imu.read_sensors()
            if vals and "gz" in vals:
                bias_sum += vals["gz"]
                valid_samples += 1
            time.sleep(delay)
        if valid_samples > 0:
            self.gyro_bias_z = bias_sum / valid_samples
        else:
            self.gyro_bias_z = 0.0
        print(f"[IMUTracker] Calibration complete. Gyro Z-bias offset: {self.gyro_bias_z:+.3f} deg/s")

    def start(self) -> None:
        """Starts the background tracking thread."""
        self.running = True
        self.thread = threading.Thread(target=self._update_loop, daemon=True, name="IMUTrackerLoop")
        self.thread.start()

    def stop(self) -> None:
        """Stops the background tracking thread."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.5)

    def _update_loop(self) -> None:
        last_time = time.perf_counter()
        while self.running:
            time.sleep(0.01)  # ~100Hz
            current_time = time.perf_counter()
            dt = current_time - last_time
            last_time = current_time
            vals = self.imu.read_sensors()
            if vals and "gz" in vals:
                gz_corrected = vals["gz"] - self.gyro_bias_z
                with self.lock:
                    self.yaw += gz_corrected * dt

    def get_yaw(self) -> float:
        """Returns relative integrated yaw angle in degrees."""
        with self.lock:
            return self.yaw

    def reset_yaw(self) -> None:
        with self.lock:
            self.yaw = 0.0


class SamRover:
    """
    Main SDK class for controlling the SAM Rover.
    Works natively on hardware via lgpio and in mock simulation.
    """

    def __init__(self, host: Optional[str] = None):
        self.host = host
        self._local_hw = None

        if self.host is None:
            from core.hardware_manager import hw_manager
            self._local_hw = hw_manager
            self._local_hw.acquire_control(operator_id="sdk_script", operator_name="SDK Script")

        # Child device wrappers
        self.led_front = LEDDevice(self, "front")
        self.led_rear = LEDDevice(self, "rear")
        self.led_back = self.led_rear  # Alias for backward compatibility
        self.led_left = LEDDevice(self, "left")
        self.led_right = LEDDevice(self, "right")

        self.ultra_front = UltrasonicDevice(self, "front")
        self.ultra_rear = UltrasonicDevice(self, "rear")
        self.ultra_back = self.ultra_rear  # Alias
        self.ultra_left = UltrasonicDevice(self, "left")
        self.ultra_right = UltrasonicDevice(self, "right")

        self.buzzer = BuzzerDevice(self)
        self.drivetrain = DrivetrainDevice(self)
        self.imu = IMUDevice(self)
        self.camera = CameraDevice(self)

    @property
    def name(self) -> str:
        return "SAM Rover"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        self.release()

    # --- Locomotion Commands ---

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
        """Differential steering drive (linear: -100 to 100, angular: -100 to 100)."""
        if self._local_hw:
            return self._local_hw.drive(linear, angular)
        return {"linear": linear, "angular": angular}

    def set_motors(self, left_speed: float, right_speed: float) -> None:
        """Sets individual motor velocities (-100 to 100)."""
        if self._local_hw:
            self._local_hw.motors.set_motor_speeds(left_speed, right_speed)

    def stop(self) -> None:
        """Immediately stops all motor movement and turns off blinking LEDs."""
        self.led_front.stop_blink()
        self.led_back.stop_blink()
        self.led_left.stop_blink()
        self.led_right.stop_blink()
        if self._local_hw:
            self._local_hw.emergency_stop()

    def release(self) -> None:
        """Releases GPIO pins and camera handle so background services can resume."""
        self.stop()
        self.camera.release()
        if self._local_hw:
            self._local_hw.release_control(operator_id="sdk_script")

    def cleanup(self) -> None:
        self.release()

    # --- Sensor, Buzzer & LED Commands ---

    def get_distances(self) -> Dict[str, Optional[float]]:
        if self._local_hw:
            return self._local_hw.ultrasonic.read_all()
        return {}

    def get_distance(self, direction: str) -> Optional[float]:
        if self._local_hw:
            return self._local_hw.ultrasonic.read_distance(direction)
        return None

    def set_led(self, direction: str, state: bool) -> None:
        if self._local_hw:
            self._local_hw.leds.set_led(direction, state)

    def set_all_leds(self, state: bool) -> None:
        if self._local_hw:
            self._local_hw.leds.set_all(state)

    def beep(self, duration: float = 0.15) -> None:
        self.buzzer.beep(duration)

    def get_imu(self) -> Dict[str, float]:
        if self._local_hw:
            return self._local_hw.imu.read()
        return {"ax": 0.0, "ay": 0.0, "az": 1.0, "gx": 0.0, "gy": 0.0, "gz": 0.0, "pitch": 0.0, "roll": 0.0, "temp_c": 25.0}

    def get_telemetry(self) -> Dict[str, Any]:
        if self._local_hw:
            return self._local_hw.get_telemetry()
        return {}
