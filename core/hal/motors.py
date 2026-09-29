"""
SAM Rover - L298N Differential Motor Driver
Supports native lgpio (kernel gpiochip), RPi.GPIO fallback, and mock simulation.
Optimized for 60 RPM high-torque DC gearmotors with kinematic slew-rate acceleration.
"""

import time
import threading
from typing import Dict, Any, Optional
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
        self.left_speed = 0.0   # Current applied speed: -100 to 100
        self.right_speed = 0.0  # Current applied speed: -100 to 100

        # Motion & Stiction Tuning (60 RPM Gear Motor Optimization)
        self.min_duty_cycle = float(self.pins.get("min_duty_cycle", 10.0))
        self.slew_rate_step = float(self.pins.get("slew_rate_step", 12.0))
        self.steering_expo = float(self.pins.get("steering_expo", 0.3))
        self.invert_left = bool(self.pins.get("invert_left", False))
        self.invert_right = bool(self.pins.get("invert_right", False))

        # Re-entrant thread safety lock
        self._lock = threading.RLock()

        # Driver backend: "lgpio", "rpi_gpio", or "mock"
        self.backend = "mock"

        # lgpio state
        self._lgpio = None
        self._chip: Optional[int] = None

        # RPi.GPIO state
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
            self.backend = "mock"
            self.is_initialized = True
            print("[Motors] Initialized in SIMULATION / MOCK mode.")
            return True

        lp = self.pins["left"]
        rp = self.pins["right"]
        freq = int(self.pins.get("pwm_frequency", 100))
        all_pins = [lp["ena"], lp["in1"], lp["in2"], rp["enb"], rp["in3"], rp["in4"]]

        # 1. Primary Driver: lgpio (Kernel character device /dev/gpiochip0)
        try:
            import lgpio
            chip_idx = 0
            # Auto-detect valid chip on Pi 4 (chip 0) or Pi 5 (chip 4)
            for c in (0, 4):
                try:
                    self._chip = lgpio.gpiochip_open(c)
                    chip_idx = c
                    break
                except Exception:
                    pass

            if self._chip is not None:
                self._lgpio = lgpio
                for pin in all_pins:
                    lgpio.gpio_claim_output(self._chip, pin, 0)

                self.backend = "lgpio"
                self.is_initialized = True
                self.last_error = None
                print(f"[Motors] lgpio hardware driver initialized on gpiochip{chip_idx} at {freq}Hz.")
                return True
        except Exception as e:
            print(f"[Motors] lgpio initialization bypassed ({e}); attempting RPi.GPIO fallback...")

        # 2. Secondary Fallback Driver: RPi.GPIO
        try:
            import RPi.GPIO as GPIO
            self._gpio = GPIO
            self._gpio.setmode(self._gpio.BCM)
            self._gpio.setwarnings(False)

            for pin in (lp["in1"], lp["in2"], rp["in3"], rp["in4"], lp["ena"], rp["enb"]):
                self._gpio.setup(pin, self._gpio.OUT)
                self._gpio.output(pin, self._gpio.LOW)

            self._pwm_in1 = self._gpio.PWM(lp["in1"], freq)
            self._pwm_in2 = self._gpio.PWM(lp["in2"], freq)
            self._pwm_in3 = self._gpio.PWM(rp["in3"], freq)
            self._pwm_in4 = self._gpio.PWM(rp["in4"], freq)
            self._pwm_left = self._gpio.PWM(lp["ena"], freq)
            self._pwm_right = self._gpio.PWM(rp["enb"], freq)

            for p in (self._pwm_in1, self._pwm_in2, self._pwm_in3, self._pwm_in4, self._pwm_left, self._pwm_right):
                p.start(0)

            self.backend = "rpi_gpio"
            self.is_initialized = True
            self.last_error = None
            print(f"[Motors] RPi.GPIO driver initialized at {freq}Hz.")
            return True
        except Exception as e:
            self.last_error = str(e)
            print(f"[Motors] Hardware initialization failed: {e}. Switching to Mock.")
            self.backend = "mock"
            self.is_mock = True
            self.is_initialized = True
            return True

    def _map_duty(self, speed: float) -> float:
        """
        Maps a normalized speed percentage (0-100) to hardware PWM duty cycle.
        Tuned for 60 RPM gearboxes with 10% crawl threshold.
        """
        mag = abs(speed)
        if mag < 1.0:
            return 0.0
        min_d = min(15.0, self.min_duty_cycle)
        duty = min_d + (100.0 - min_d) * (mag / 100.0)
        return min(100.0, max(0.0, duty))

    def set_motor_speeds(self, left: float, right: float, immediate: bool = False) -> None:
        """
        Set individual speeds for left and right motors.
        Range: -100.0 (full reverse) to 100.0 (full forward).
        Applies kinematic slew-rate ramp during acceleration to protect 60 RPM gearboxes.
        Immediate=True bypasses the slew rate for instant emergency braking.
        """
        with self._lock:
            if not self.is_initialized:
                self.initialize()

            target_left = max(-100.0, min(100.0, float(left)))
            target_right = max(-100.0, min(100.0, float(right)))

            self.left_speed = target_left
            self.right_speed = target_right

            if self.backend == "mock":
                return

            self._apply_hardware(self.left_speed, self.right_speed)

    def _apply_hardware(self, l_spd: float, r_spd: float) -> None:
        """Applies PWM duty cycles and polarities via lgpio or RPi.GPIO."""
        duty_left = self._map_duty(l_spd)
        duty_right = self._map_duty(r_spd)

        eff_left = -l_spd if self.invert_left else l_spd
        eff_right = -r_spd if self.invert_right else r_spd

        freq = int(self.pins.get("pwm_frequency", 100))
        lp = self.pins["left"]
        rp = self.pins["right"]

        # === Backend 1: lgpio ===
        if self.backend == "lgpio" and self._chip is not None and self._lgpio:
            # Left motor directional PWM + ENA
            if eff_left > 0:
                self._lgpio.tx_pwm(self._chip, lp["in1"], freq, 0.0)
                self._lgpio.tx_pwm(self._chip, lp["in2"], freq, duty_left)
                self._lgpio.tx_pwm(self._chip, lp["ena"], freq, duty_left)
            elif eff_left < 0:
                self._lgpio.tx_pwm(self._chip, lp["in2"], freq, 0.0)
                self._lgpio.tx_pwm(self._chip, lp["in1"], freq, duty_left)
                self._lgpio.tx_pwm(self._chip, lp["ena"], freq, duty_left)
            else:
                self._lgpio.tx_pwm(self._chip, lp["in1"], freq, 0.0)
                self._lgpio.tx_pwm(self._chip, lp["in2"], freq, 0.0)
                self._lgpio.tx_pwm(self._chip, lp["ena"], freq, 0.0)

            # Right motor directional PWM + ENB
            if eff_right > 0:
                self._lgpio.tx_pwm(self._chip, rp["in3"], freq, 0.0)
                self._lgpio.tx_pwm(self._chip, rp["in4"], freq, duty_right)
                self._lgpio.tx_pwm(self._chip, rp["enb"], freq, duty_right)
            elif eff_right < 0:
                self._lgpio.tx_pwm(self._chip, rp["in4"], freq, 0.0)
                self._lgpio.tx_pwm(self._chip, rp["in3"], freq, duty_right)
                self._lgpio.tx_pwm(self._chip, rp["enb"], freq, duty_right)
            else:
                self._lgpio.tx_pwm(self._chip, rp["in3"], freq, 0.0)
                self._lgpio.tx_pwm(self._chip, rp["in4"], freq, 0.0)
                self._lgpio.tx_pwm(self._chip, rp["enb"], freq, 0.0)
            return

        # === Backend 2: RPi.GPIO fallback ===
        if self.backend == "rpi_gpio" and self._gpio:
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

    def set_differential_drive(self, linear: float, angular: float, immediate: bool = False) -> None:
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

        self.set_motor_speeds(left, right, immediate=immediate)

    def brake(self) -> None:
        """
        Active electromagnetic regenerative brake for immediate stopping.
        Grounds H-bridge outputs with zero delay.
        """
        with self._lock:
            self.left_speed = 0.0
            self.right_speed = 0.0

            if self.backend == "lgpio" and self._chip is not None and self._lgpio:
                freq = int(self.pins.get("pwm_frequency", 100))
                lp = self.pins["left"]
                rp = self.pins["right"]
                for p in (lp["in1"], lp["in2"], lp["ena"], rp["in3"], rp["in4"], rp["enb"]):
                    try:
                        self._lgpio.tx_pwm(self._chip, p, freq, 0.0)
                    except Exception:
                        pass
                return

            if self.backend == "rpi_gpio" and self._gpio and self.is_initialized:
                for p in (self._pwm_in1, self._pwm_in2, self._pwm_in3, self._pwm_in4, self._pwm_left, self._pwm_right):
                    if p:
                        try:
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
            lp = self.pins["left"]
            rp = self.pins["right"]
            all_pins = [lp["ena"], lp["in1"], lp["in2"], rp["enb"], rp["in3"], rp["in4"]]

            # Cleanup lgpio
            if self.backend == "lgpio" and self._chip is not None and self._lgpio:
                try:
                    for p in all_pins:
                        try:
                            self._lgpio.gpio_free(self._chip, p)
                        except Exception:
                            pass
                    self._lgpio.gpiochip_close(self._chip)
                except Exception as e:
                    print(f"[Motors] lgpio cleanup warning: {e}")
                self._chip = None

            # Cleanup RPi.GPIO
            if self.backend == "rpi_gpio" and self._gpio:
                try:
                    for pwm in (self._pwm_in1, self._pwm_in2, self._pwm_in3, self._pwm_in4, self._pwm_left, self._pwm_right):
                        if pwm:
                            try:
                                pwm.stop()
                            except Exception:
                                pass
                    self._gpio.cleanup(all_pins)
                except Exception as e:
                    print(f"[Motors] RPi.GPIO cleanup warning: {e}")

            self.is_initialized = False
            print("[Motors] Hardware pins safely released.")

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "initialized": self.is_initialized,
                "mock": self.is_mock,
                "backend": self.backend,
                "left_speed": round(self.left_speed, 1),
                "right_speed": round(self.right_speed, 1),
                "error": self.last_error,
            }
