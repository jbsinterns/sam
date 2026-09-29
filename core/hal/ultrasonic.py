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

    _FORWARD_PERIPHERALS = ("rear", "left", "right")
    _REVERSE_PERIPHERALS = ("front", "left", "right")
    _ALL_DIRECTIONS = ("front", "rear", "left", "right")

    def __init__(self, pin_config: Dict[str, Any], is_mock: bool = False):
        super().__init__("UltrasonicArray", is_mock)
        self.pins = pin_config
        self._peripheral_idx = 0
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
            # 10us trigger pulse
            self._gpio.output(trig, self._gpio.HIGH)
            time.sleep(0.00001)
            self._gpio.output(trig, self._gpio.LOW)

            timeout_start = time.perf_counter()
            start_time = timeout_start
            # Wait for ECHO to go HIGH (fast 5ms timeout: sensor always starts within 0.5ms)
            while self._gpio.input(echo) == 0:
                start_time = time.perf_counter()
                if start_time - timeout_start > 0.005:
                    with self._lock:
                        self.sensor_health[direction] = False
                        self.distances[direction] = None
                    return None

            stop_time = start_time
            # Wait for ECHO to go LOW (16ms timeout = ~274cm max range; beyond this is clear)
            while self._gpio.input(echo) == 1:
                stop_time = time.perf_counter()
                if stop_time - start_time > 0.016:
                    with self._lock:
                        self.sensor_health[direction] = False
                        self.distances[direction] = None
                    return None

            # Calculate distance: (elapsed * speed of sound 34300 cm/s) / 2
            elapsed = stop_time - start_time
            distance = (elapsed * 34300.0) / 2.0
            distance = round(distance, 1)

            if 2.0 <= distance <= 350.0:
                with self._lock:
                    prev_dist = self.distances.get(direction)

                    # ASYMMETRIC SAFETY FILTER:
                    # When approaching an obstacle (distance decreasing), update IMMEDIATELY!
                    # A median filter causes a 2-sample delay which leads to collisions at speed.
                    if prev_dist is None or distance < prev_dist:
                        filtered_dist = distance
                        self._samples[direction] = [distance, distance, distance]
                    else:
                        # When distance is increasing (clearing obstacle), smooth with rolling median
                        # to eliminate spurious single-sample multipath acoustic scatter
                        buf = self._samples.setdefault(direction, [distance, distance, distance])
                        buf.pop(0)
                        buf.append(distance)
                        filtered_dist = round(sorted(buf)[1], 1)

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

    def read_cycle(self, motion_hint: Optional[str] = None) -> Dict[str, Optional[float]]:
        """
        Smart motion-prioritized sensor scanning:
        - When moving forward: Reads 'front' at 2x rate, interleaving 1 peripheral sensor.
        - When moving backward: Reads 'rear' at 2x rate.
        - When idle or turning: Cycles through all 4 sensors.
        Acoustic pulse dissipation pause reduced to 5ms for rapid 20-30Hz updates.
        """
        if motion_hint == "forward":
            self.read_distance("front")
            time.sleep(0.005)
            self._peripheral_idx = (self._peripheral_idx + 1) % len(self._FORWARD_PERIPHERALS)
            self.read_distance(self._FORWARD_PERIPHERALS[self._peripheral_idx])
            time.sleep(0.005)
            self.read_distance("front")
        elif motion_hint == "reverse":
            self.read_distance("rear")
            time.sleep(0.005)
            self._peripheral_idx = (self._peripheral_idx + 1) % len(self._REVERSE_PERIPHERALS)
            self.read_distance(self._REVERSE_PERIPHERALS[self._peripheral_idx])
            time.sleep(0.005)
            self.read_distance("rear")
        else:
            for direction in self._ALL_DIRECTIONS:
                self.read_distance(direction)
                time.sleep(0.005)

        with self._lock:
            return self.distances.copy()

    def read_all(self) -> Dict[str, Optional[float]]:
        """Reads all sensors, delegating to read_cycle."""
        return self.read_cycle()

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
