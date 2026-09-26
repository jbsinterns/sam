"""
SAM Rover - Active Piezo Buzzer / Horn Driver
Supports hardware GPIO output and simulated mock sound alerts.
"""

import time
import threading
from core.hal.base import BaseHardwareDevice


class Buzzer(BaseHardwareDevice):
    """
    Controls an active piezo buzzer on a single GPIO pin (active HIGH).
    Thread-safe and supports non-blocking audio chirps.
    """

    def __init__(self, pin: int = 20, is_mock: bool = False):
        super().__init__("Buzzer", is_mock)
        self.pin = pin
        self.state = False
        self._gpio = None
        self._lock = threading.Lock()

    def initialize(self) -> bool:
        with self._lock:
            if self.is_initialized:
                return True

            if self.is_mock:
                self.is_initialized = True
                print("[Buzzer] Initialized in SIMULATION / MOCK mode.")
                return True

            try:
                import RPi.GPIO as GPIO
                self._gpio = GPIO
                self._gpio.setmode(self._gpio.BCM)
                self._gpio.setup(self.pin, self._gpio.OUT)
                self._gpio.output(self.pin, self._gpio.LOW)
                self.is_initialized = True
                self.state = False
                print(f"[Buzzer] Hardware buzzer initialized on GPIO {self.pin}.")
                return True
            except Exception as e:
                self.last_error = str(e)
                print(f"[Buzzer] Hardware init failed ({e}), falling back to mock.")
                self.is_mock = True
                self.is_initialized = True
                return True

    def on(self) -> None:
        """Turns the buzzer ON."""
        with self._lock:
            if not self.is_initialized:
                self.initialize()
            self.state = True
            if not self.is_mock and self._gpio:
                try:
                    self._gpio.output(self.pin, self._gpio.HIGH)
                except Exception:
                    pass

    def off(self) -> None:
        """Turns the buzzer OFF."""
        with self._lock:
            self.state = False
            if not self.is_mock and self._gpio:
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
        with self._lock:
            self.state = False
            if not self.is_mock and self._gpio:
                try:
                    self._gpio.output(self.pin, self._gpio.LOW)
                    self._gpio.cleanup(self.pin)
                except Exception:
                    pass
            self.is_initialized = False

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "initialized": self.is_initialized,
            "mock": self.is_mock,
            "pin": self.pin,
            "state": self.state,
        }
