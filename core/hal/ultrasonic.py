"""
SAM Rover - 4-Directional HC-SR04 Ultrasonic Sensor Controller
Fault-isolated: A sensor failure or timeout will not hang the other sensors or server.
"""

import time
import math
import threading
from typing import Dict, Any, Optional
from core.hal.base import BaseHardwareDevice


class UltrasonicSensorArray(BaseHardwareDevice):
    """
    Manages 4 HC-SR04 ultrasonic sensors (front, rear, left, right).
    Measures distances in centimeters with strict microsecond timeouts.
    """

    def __init__(self, pin_config: Dict[str, Any], is_mock: bool = False):
        super().__init__("UltrasonicArray", is_mock)
        self.pins = pin_config
        self.distances: Dict[str, Optional[float]] = {
            "front": 100.0,
            "rear": 100.0,
            "left": 100.0,
            "right": 100.0,
        }
        self.sensor_health: Dict[str, bool] = {
            "front": True,
            "rear": True,
            "left": True,
            "right": True,
        }
        # 3-Sample rolling median filter buffer for acoustic echo de-noising
        self._samples: Dict[str, list] = {
            d: [100.0, 100.0, 100.0] for d in ("front", "rear", "left", "right")
        }
        self._gpio = None
        self._mock_step = 0
        self._lock = threading.Lock()

    def initialize(self) -> bool:
        if self.is_initialized:
            return True

        if self.is_mock:
            self.is_initialized = True
            print("[Ultrasonic] Initialized in SIMULATION / MOCK mode.")
            return True

        try:
            import RPi.GPIO as GPIO
            self._gpio = GPIO
            self._gpio.setmode(self._gpio.BCM)
            self._gpio.setwarnings(False)

            for direction, cfg in self.pins.items():
                trig = cfg["trigger"]
                echo = cfg["echo"]
                self._gpio.setup(trig, self._gpio.OUT)
                self._gpio.setup(echo, self._gpio.IN)
                self._gpio.output(trig, self._gpio.LOW)

            time.sleep(0.05)  # Allow sensors to settle
            self.is_initialized = True
            self.last_error = None
            print("[Ultrasonic] Hardware HC-SR04 array initialized.")
            return True
        except Exception as e:
            self.last_error = str(e)
            print(f"[Ultrasonic] Hardware init failed: {e}. Falling back to Mock.")
            self.is_mock = True
            self.is_initialized = True
            return True

    def read_distance(self, direction: str) -> Optional[float]:
        """
        Reads distance in centimeters for a specific direction.
        Returns distance (float) or None if timeout / error.
        Resets stale distances on failure so obstacles don't cause permanent lockouts.
        """
        if direction not in self.pins:
            return None

        if self.is_mock or not self._gpio:
            # Generate gentle mock values oscillating between 45cm and 150cm
            self._mock_step += 0.05
            offset = {"front": 0.0, "rear": 1.5, "left": 3.0, "right": 4.5}.get(direction, 0)
            mock_dist = 85.0 + 35.0 * math.sin(self._mock_step + offset)
            val = round(max(10.0, mock_dist), 1)
            with self._lock:
                self.distances[direction] = val
            return val

        # Physical reading with strict safety timeout
        cfg = self.pins[direction]
        trig = cfg["trigger"]
        echo = cfg["echo"]

        try:
            # 10us pulse to trigger
            self._gpio.output(trig, self._gpio.HIGH)
            time.sleep(0.00001)
            self._gpio.output(trig, self._gpio.LOW)

            timeout_start = time.time()
            start_time = timeout_start
            # Wait for ECHO to go HIGH (max 30ms timeout)
            while self._gpio.input(echo) == 0:
                start_time = time.time()
                if start_time - timeout_start > 0.03:
                    with self._lock:
                        self.sensor_health[direction] = False
                        self.distances[direction] = None
                    return None

            stop_time = start_time
            # Wait for ECHO to go LOW (max 30ms timeout ~ 5 meters)
            while self._gpio.input(echo) == 1:
                stop_time = time.time()
                if stop_time - start_time > 0.03:
                    with self._lock:
                        self.sensor_health[direction] = False
                        self.distances[direction] = None
                    return None

            # Calculate distance: (elapsed * speed of sound 34300 cm/s) / 2
            elapsed = stop_time - start_time
            distance = (elapsed * 34300.0) / 2.0
            distance = round(distance, 1)

            if 2.0 <= distance <= 450.0:
                # 3-Sample rolling median filter: eliminates phantom acoustic echoes
                with self._lock:
                    if direction in self._samples:
                        buf = self._samples[direction]
                        buf.pop(0)
                        buf.append(distance)
                        filtered_dist = round(sorted(buf)[1], 1)
                    else:
                        filtered_dist = distance

                    self.distances[direction] = filtered_dist
                    self.sensor_health[direction] = True
                return filtered_dist
            else:
                with self._lock:
                    self.distances[direction] = None
                return None
        except Exception:
            with self._lock:
                self.sensor_health[direction] = False
                self.distances[direction] = None
            return None

    def read_all(self) -> Dict[str, Optional[float]]:
        """
        Reads all 4 sensors sequentially with 15ms acoustic settling delay
        to eliminate reverberation cross-talk between sensors.
        """
        for direction in ("front", "rear", "left", "right"):
            self.read_distance(direction)
            time.sleep(0.015)  # Acoustic pulse dissipation pause
        with self._lock:
            return self.distances.copy()

    def cleanup(self) -> None:
        """Releases GPIO pins."""
        if not self.is_mock and self._gpio:
            try:
                pins = []
                for cfg in self.pins.values():
                    pins.extend([cfg["trigger"], cfg["echo"]])
                self._gpio.cleanup(pins)
            except Exception as e:
                print(f"[Ultrasonic] Cleanup warning: {e}")
        self.is_initialized = False
        print("[Ultrasonic] Hardware pins released.")

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "initialized": self.is_initialized,
            "mock": self.is_mock,
            "distances": self.distances,
            "health": self.sensor_health,
            "error": self.last_error,
        }
