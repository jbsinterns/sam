"""
SAM Rover - Active Piezo Buzzer / Horn Driver
Supports native lgpio (kernel gpiochip), RPi.GPIO fallback, and mock simulation.
"""

import time
import threading
from typing import Optional
from core.hal.base import BaseHardwareDevice


class Buzzer(BaseHardwareDevice):
    """
    Controls an active piezo buzzer on a single GPIO pin (active HIGH).
    Thread-safe and supports non-blocking audio chirps.
    """

    def __init__(self, pin: int = 25, is_mock: bool = False):
        super().__init__("Buzzer", is_mock)
        self.pin = pin
        self.state = False
        self.backend = "mock"
        self._lgpio = None
        self._chip: Optional[int] = None
        self._gpio = None
        self._lock = threading.RLock()

    def initialize(self) -> bool:
        with self._lock:
            if self.is_initialized:
                return True

            if self.is_mock:
                self.backend = "mock"
                self.is_initialized = True
                print("[Buzzer] Initialized in SIMULATION / MOCK mode.")
                return True

            # 1. Primary: lgpio
            try:
                import lgpio
                for c in (0, 4):
                    try:
                        self._chip = lgpio.gpiochip_open(c)
                        break
                    except Exception:
                        pass

                if self._chip is not None:
                    self._lgpio = lgpio
                    lgpio.gpio_claim_output(self._chip, self.pin, 0)
                    lgpio.gpio_write(self._chip, self.pin, 0)
                    self.backend = "lgpio"
                    self.is_initialized = True
                    self.state = False
                    self.last_error = None
                    print(f"[Buzzer] lgpio buzzer initialized on GPIO {self.pin}.")
                    return True
            except Exception as e:
                print(f"[Buzzer] lgpio init bypassed ({e}); attempting RPi.GPIO fallback...")

            # 2. Secondary Fallback: RPi.GPIO
            try:
                import RPi.GPIO as GPIO
                self._gpio = GPIO
                self._gpio.setmode(self._gpio.BCM)
                self._gpio.setup(self.pin, self._gpio.OUT)
                self._gpio.output(self.pin, self._gpio.LOW)
                self.backend = "rpi_gpio"
                self.is_initialized = True
                self.state = False
                self.last_error = None
                print(f"[Buzzer] RPi.GPIO buzzer initialized on GPIO {self.pin}.")
                return True
            except Exception as e:
                self.last_error = str(e)
                print(f"[Buzzer] Hardware init failed ({e}), falling back to mock.")
                self.backend = "mock"
                self.is_mock = True
                self.is_initialized = True
                return True

    def on(self) -> None:
        """Turns the buzzer ON."""
        with self._lock:
            if not self.is_initialized:
                self.initialize()
            self.state = True
            if self.backend == "lgpio" and self._chip is not None and self._lgpio:
                try:
                    self._lgpio.gpio_write(self._chip, self.pin, 1)
                except Exception:
                    pass
            elif self.backend == "rpi_gpio" and self._gpio:
                try:
                    self._gpio.output(self.pin, self._gpio.HIGH)
                except Exception:
                    pass

    def off(self) -> None:
        """Turns the buzzer OFF."""
        with self._lock:
            self.state = False
            if self.backend == "lgpio" and self._chip is not None and self._lgpio:
                try:
                    self._lgpio.gpio_write(self._chip, self.pin, 0)
                except Exception:
                    pass
            elif self.backend == "rpi_gpio" and self._gpio:
                try:
                    self._gpio.output(self.pin, self._gpio.LOW)
                except Exception:
                    pass

    def toggle(self) -> bool:
        """Toggles buzzer state."""
        if self.state:
            self.off()
        else:
            self.on()
        return self.state

    def beep(self, duration: float = 0.15) -> None:
        """Performs an audible beep non-blockingly in a background daemon thread."""
        def _chirp():
            self.on()
            time.sleep(duration)
            self.off()

        t = threading.Thread(target=_chirp, daemon=True, name="BuzzerChirpThread")
        t.start()

    def cleanup(self) -> None:
        """Silences buzzer and completely releases GPIO pin."""
        with self._lock:
            self.off()
            if self.backend == "lgpio" and self._chip is not None and self._lgpio:
                try:
                    self._lgpio.gpio_write(self._chip, self.pin, 0)
                    self._lgpio.gpio_free(self._chip, self.pin)
                    self._lgpio.gpiochip_close(self._chip)
                except Exception as e:
                    print(f"[Buzzer] lgpio cleanup warning: {e}")
                self._chip = None

            if self.backend == "rpi_gpio" and self._gpio:
                try:
                    self._gpio.output(self.pin, self._gpio.LOW)
                    self._gpio.cleanup(self.pin)
                except Exception as e:
                    print(f"[Buzzer] RPi.GPIO cleanup warning: {e}")

            self.is_initialized = False

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "initialized": self.is_initialized,
            "mock": self.is_mock,
            "backend": self.backend,
            "pin": self.pin,
            "state": self.state,
        }
