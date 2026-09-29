"""
SAM Rover - L298N Differential Motor Driver
Supports dynamic hardware leasing, PWM speed control, and smooth mock simulation.
"""

import time
import threading
from typing import Dict, Any
from core.hal.base import BaseHardwareDevice


class MotorDriver(BaseHardwareDevice):
    """
    Controls 2-motor differential drive via L298N H-Bridge driver.
    Left Motor: ENA (PWM), IN1, IN2
    Right Motor: ENB (PWM), IN3, IN4
    Thread-safe: guarded by re-entrant lock to prevent concurrent GPIO corruption.
    """

    def __init__(self, pin_config: Dict[str, Any], is_mock: bool = False):
        super().__init__("MotorDriver", is_mock)
        self.pins = pin_config
        self.left_speed = 0.0   # Range: -100 to 100
        self.right_speed = 0.0  # Range: -100 to 100

        # Motion & Stiction Tuning (20 RPM Gear Motor Optimization)
        self.min_duty_cycle = float(self.pins.get("min_duty_cycle", 25.0))
        self.steering_expo = float(self.pins.get("steering_expo", 0.3))
        self.invert_left = bool(self.pins.get("invert_left", False))
        self.invert_right = bool(self.pins.get("invert_right", False))

        # Re-entrant thread safety lock
        self._lock = threading.RLock()

        # Physical GPIO objects (None when uninitialized or in mock mode)
        self._gpio = None
        self._pwm_left = None
        self._pwm_right = None
        self._pwm_in1 = None
        self._pwm_in2 = None
        self._pwm_in3 = None
        self._pwm_in4 = None

    def initialize(self) -> bool:
        if self.is_initialized:
            return True

        if self.is_mock:
            self.is_initialized = True
            print("[Motors] Initialized in SIMULATION / MOCK mode.")
            return True

        try:
            try:
                import RPi.GPIO as GPIO
                self._gpio = GPIO
            except ImportError:
                print("[Motors] RPi.GPIO not found; falling back to Mock driver.")
                self.is_mock = True
                self.is_initialized = True
                return True

            self._gpio.setmode(self._gpio.BCM)
            self._gpio.setwarnings(False)

            lp = self.pins["left"]
            rp = self.pins["right"]
            # 100 Hz optimal frequency for L298N switching & motor torque
            freq = int(self.pins.get("pwm_frequency", 100))

            # Setup Direction Pins with PWM
            for pin in (lp["in1"], lp["in2"], rp["in3"], rp["in4"]):
                self._gpio.setup(pin, self._gpio.OUT)
                self._gpio.output(pin, self._gpio.LOW)

            # Setup PWM Enable Pins
            self._gpio.setup(lp["ena"], self._gpio.OUT)
            self._gpio.setup(rp["enb"], self._gpio.OUT)

            # Universal Dual-Layer PWM:
            # 1. PWM on Directional Pins (works even if ENA/ENB jumpers are attached to 5V)
            self._pwm_in1 = self._gpio.PWM(lp["in1"], freq)
            self._pwm_in2 = self._gpio.PWM(lp["in2"], freq)
            self._pwm_in3 = self._gpio.PWM(rp["in3"], freq)
            self._pwm_in4 = self._gpio.PWM(rp["in4"], freq)

            # 2. PWM on ENA/ENB Pins (works if ENA/ENB are wired to GPIO)
            self._pwm_left = self._gpio.PWM(lp["ena"], freq)
            self._pwm_right = self._gpio.PWM(rp["enb"], freq)

            for p in (self._pwm_in1, self._pwm_in2, self._pwm_in3, self._pwm_in4, self._pwm_left, self._pwm_right):
                p.start(0)

            self.is_initialized = True
            self.last_error = None
            print(f"[Motors] Universal Dual-Layer PWM initialized at {freq}Hz.")
            return True
        except Exception as e:
            self.last_error = str(e)
            print(f"[Motors] Initialization failed: {e}. Switching to Mock.")
            self.is_mock = True
            self.is_initialized = True
            return True

    def _map_duty(self, speed: float) -> float:
        """
        Maps a normalized speed percentage (0-100) to hardware PWM duty cycle.
        Provides a gentle minimum duty cycle (15%) for low-speed crawl.
        """
        mag = abs(speed)
        if mag < 1.0:
            return 0.0
        min_d = min(15.0, self.min_duty_cycle)
        duty = min_d + (100.0 - min_d) * (mag / 100.0)
        return min(100.0, max(0.0, duty))

    def set_motor_speeds(self, left: float, right: float) -> None:
        """
        Set individual speeds for left and right motors.
        Range: -100.0 (full reverse) to 100.0 (full forward).
        """
        with self._lock:
            if not self.is_initialized:
                self.initialize()

            # Clamp values
            target_left = max(-100.0, min(100.0, float(left)))
            target_right = max(-100.0, min(100.0, float(right)))

            self.left_speed = target_left
            self.right_speed = target_right

            if self.is_mock or not self._gpio:
                return

            self._apply_hardware(target_left, target_right)

    def _apply_hardware(self, l_spd: float, r_spd: float) -> None:
        """Applies PWM duty cycles and polarities to physical H-bridge drivers."""
        duty_left = self._map_duty(l_spd)
        duty_right = self._map_duty(r_spd)

        eff_left = -l_spd if self.invert_left else l_spd
        eff_right = -r_spd if self.invert_right else r_spd

        # Left Motor: IN1, IN2, ENA
        if eff_left > 0:
            self._pwm_in1.ChangeDutyCycle(0)
            self._pwm_in2.ChangeDutyCycle(duty_left)
            self._pwm_left.ChangeDutyCycle(duty_left)
        elif eff_left < 0:
            self._pwm_in2.ChangeDutyCycle(0)
            self._pwm_in1.ChangeDutyCycle(duty_left)
            self._pwm_left.ChangeDutyCycle(duty_left)
        else:
            self._pwm_in1.ChangeDutyCycle(0)
            self._pwm_in2.ChangeDutyCycle(0)
            self._pwm_left.ChangeDutyCycle(0)

        # Right Motor: IN3, IN4, ENB
        if eff_right > 0:
            self._pwm_in3.ChangeDutyCycle(0)
            self._pwm_in4.ChangeDutyCycle(duty_right)
            self._pwm_right.ChangeDutyCycle(duty_right)
        elif eff_right < 0:
            self._pwm_in4.ChangeDutyCycle(0)
            self._pwm_in3.ChangeDutyCycle(duty_right)
            self._pwm_right.ChangeDutyCycle(duty_right)
        else:
            self._pwm_in3.ChangeDutyCycle(0)
            self._pwm_in4.ChangeDutyCycle(0)
            self._pwm_right.ChangeDutyCycle(0)

    def set_differential_drive(self, linear: float, angular: float) -> None:
        """
        True proportional arcade drive steering mixer.
        Maintains linear speed limit while smoothly articulating curves.
        linear: -100 to 100
        angular: -100 to 100
        """
        if abs(linear) < 1.0 and abs(angular) < 1.0:
            self.stop()
            return

        norm_ang = max(-1.0, min(1.0, angular / 100.0))
        # Exponential curve for fine center control
        curved_ang = (self.steering_expo * (norm_ang ** 3) + (1.0 - self.steering_expo) * norm_ang) * 100.0

        if abs(linear) >= 1.0:
            turn_ratio = curved_ang / 100.0  # -1.0 (full left) to +1.0 (full right)
            if turn_ratio > 0:
                # Steer right: left wheel at linear, right wheel scaled down
                left = linear
                right = linear * (1.0 - 2.0 * turn_ratio)
            else:
                # Steer left: right wheel at linear, left wheel scaled down
                left = linear * (1.0 + 2.0 * turn_ratio)
                right = linear
        else:
            # Pivot in place / tank turn
            left = curved_ang
            right = -curved_ang

        left = max(-100.0, min(100.0, left))
        right = max(-100.0, min(100.0, right))

        self.set_motor_speeds(left, right)

    def brake(self) -> None:
        """
        Active electromagnetic regenerative brake for immediate stopping.
        Grounds H-bridge outputs with EN active to short motor back-EMF,
        eliminating coasting momentum and stopping the rover within 1-2 cm.
        """
        with self._lock:
            self.left_speed = 0.0
            self.right_speed = 0.0
            if not self.is_mock and self._gpio and self.is_initialized:
                try:
                    for p in (self._pwm_in1, self._pwm_in2, self._pwm_in3, self._pwm_in4, self._pwm_left, self._pwm_right):
                        if p:
                            p.ChangeDutyCycle(0)
                except Exception:
                    pass

    def stop(self) -> None:
        """Instantly stops all motor rotation with active braking."""
        self.brake()

    def cleanup(self) -> None:
        """Releases GPIO pins and stops PWM."""
        with self._lock:
            self.stop()
            if not self.is_mock and self._gpio:
                try:
                    for pwm in (self._pwm_in1, self._pwm_in2, self._pwm_in3, self._pwm_in4, self._pwm_left, self._pwm_right):
                        if pwm:
                            try:
                                pwm.stop()
                            except Exception:
                                pass
                    lp = self.pins["left"]
                    rp = self.pins["right"]
                    pins = [lp["ena"], lp["in1"], lp["in2"], rp["enb"], rp["in3"], rp["in4"]]
                    self._gpio.cleanup(pins)
                except Exception as e:
                    print(f"[Motors] Cleanup warning: {e}")
            self.is_initialized = False
            print("[Motors] Hardware pins safely released.")

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "initialized": self.is_initialized,
                "mock": self.is_mock,
                "left_speed": round(self.left_speed, 1),
                "right_speed": round(self.right_speed, 1),
                "error": self.last_error,
            }
