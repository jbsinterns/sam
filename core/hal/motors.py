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

        # Re-entrant thread safety lock
        self._lock = threading.RLock()

        # Physical GPIO objects (None when uninitialized or in mock mode)
        self._gpio = None
        self._pwm_left = None
        self._pwm_right = None

    def initialize(self) -> bool:
        if self.is_initialized:
            return True

        if self.is_mock:
            self.is_initialized = True
            print("[Motors] Initialized in SIMULATION / MOCK mode.")
            return True

        try:
            # Try importing RPi.GPIO or lgpio safely
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
            freq = self.pins.get("pwm_frequency", 1000)

            # Setup Direction Pins
            for pin in (lp["in1"], lp["in2"], rp["in3"], rp["in4"]):
                self._gpio.setup(pin, self._gpio.OUT)
                self._gpio.output(pin, self._gpio.LOW)

            # Setup PWM Enable Pins
            self._gpio.setup(lp["ena"], self._gpio.OUT)
            self._gpio.setup(rp["enb"], self._gpio.OUT)

            self._pwm_left = self._gpio.PWM(lp["ena"], freq)
            self._pwm_right = self._gpio.PWM(rp["enb"], freq)

            self._pwm_left.start(0)
            self._pwm_right.start(0)

            self.is_initialized = True
            self.last_error = None
            print("[Motors] Hardware L298N initialized successfully.")
            return True
        except Exception as e:
            self.last_error = str(e)
            print(f"[Motors] Initialization failed: {e}. Switching to Mock.")
            self.is_mock = True
            self.is_initialized = True
            return True

    def _map_duty(self, speed: float) -> float:
        """
        Maps a normalized speed percentage (0-100) to hardware PWM duty cycle,
        incorporating deadband stiction compensation so low speed inputs produce
        effective torque rather than stalling 20 RPM gearboxes.
        """
        mag = abs(speed)
        if mag < 1.0:
            return 0.0
        duty = self.min_duty_cycle + (100.0 - self.min_duty_cycle) * (mag / 100.0)
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

            # 20 RPM Gear Motor Micro-Slew Ramping
            # Cushions gearbox backlash when leaping from 0% to high PWM, instant on emergency stop
            prev_left = self.left_speed
            prev_right = self.right_speed

            self.left_speed = target_left
            self.right_speed = target_right

            if self.is_mock or not self._gpio:
                return

            # Micro-slew step if transitioning from idle to significant drive (>30% jump)
            needs_ramp = (abs(prev_left) < 5 and abs(target_left) > 30) or (abs(prev_right) < 5 and abs(target_right) > 30)

            lp = self.pins["left"]
            rp = self.pins["right"]

            def _apply_hardware(l_spd, r_spd):
                duty_left = self._map_duty(l_spd)
                duty_right = self._map_duty(r_spd)

                # Left Motor
                if l_spd > 0:
                    self._gpio.output(lp["in1"], self._gpio.HIGH)
                    self._gpio.output(lp["in2"], self._gpio.LOW)
                    self._pwm_left.ChangeDutyCycle(duty_left)
                elif l_spd < 0:
                    self._gpio.output(lp["in1"], self._gpio.LOW)
                    self._gpio.output(lp["in2"], self._gpio.HIGH)
                    self._pwm_left.ChangeDutyCycle(duty_left)
                else:
                    self._gpio.output(lp["in1"], self._gpio.LOW)
                    self._gpio.output(lp["in2"], self._gpio.LOW)
                    self._pwm_left.ChangeDutyCycle(0)

                # Right Motor
                if r_spd > 0:
                    self._gpio.output(rp["in3"], self._gpio.HIGH)
                    self._gpio.output(rp["in4"], self._gpio.LOW)
                    self._pwm_right.ChangeDutyCycle(duty_right)
                elif r_spd < 0:
                    self._gpio.output(rp["in3"], self._gpio.LOW)
                    self._gpio.output(rp["in4"], self._gpio.HIGH)
                    self._pwm_right.ChangeDutyCycle(duty_right)
                else:
                    self._gpio.output(rp["in3"], self._gpio.LOW)
                    self._gpio.output(rp["in4"], self._gpio.LOW)
                    self._pwm_right.ChangeDutyCycle(0)

            if needs_ramp:
                # Step 1: 55% intermediate cushion for 35ms
                _apply_hardware(target_left * 0.55, target_right * 0.55)
                time.sleep(0.035)

            # Final target speed
            _apply_hardware(target_left, target_right)

    def set_differential_drive(self, linear: float, angular: float) -> None:
        """
        Differential steering mixer with exponential sensitivity curve.
        linear: -100 (back) to +100 (forward)
        angular: -100 (turn left) to +100 (turn right)
        """
        # Apply exponential steering curve: y = expo * x^3 + (1 - expo) * x
        # Softens sensitivity around neutral center while keeping full authority at limits
        norm_ang = max(-1.0, min(1.0, angular / 100.0))
        curved_ang = (self.steering_expo * (norm_ang ** 3) + (1.0 - self.steering_expo) * norm_ang) * 100.0

        left = linear + curved_ang
        right = linear - curved_ang

        # Normalize if exceed 100
        max_mag = max(abs(left), abs(right), 100.0)
        left = (left / max_mag) * 100.0
        right = (right / max_mag) * 100.0

        self.set_motor_speeds(left, right)

    def stop(self) -> None:
        """Instantly stops all motor rotation."""
        self.set_motor_speeds(0.0, 0.0)

    def cleanup(self) -> None:
        """Releases GPIO pins and stops PWM."""
        with self._lock:
            self.stop()
            if not self.is_mock and self._gpio:
                try:
                    if self._pwm_left:
                        self._pwm_left.stop()
                    if self._pwm_right:
                        self._pwm_right.stop()
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
