"""
SAM Rover - Directional LED Controller
Controls 4 directional LEDs (Front, Rear, Left, Right).
"""

from typing import Dict, Any
from core.hal.base import BaseHardwareDevice


class LEDController(BaseHardwareDevice):
    """
    Manages 4 directional indicator LEDs.
    """

    def __init__(self, pin_config: Dict[str, int], is_mock: bool = False):
        super().__init__("LEDController", is_mock)
        self.pins = pin_config
        self.state: Dict[str, bool] = {
            "front": False,
            "rear": False,
            "left": False,
            "right": False,
        }
        self._gpio = None

    def initialize(self) -> bool:
        if self.is_initialized:
            return True

        if self.is_mock:
            self.is_initialized = True
            print("[LEDs] Initialized in SIMULATION / MOCK mode.")
            return True

        try:
            import RPi.GPIO as GPIO
            self._gpio = GPIO
            self._gpio.setmode(self._gpio.BCM)
            self._gpio.setwarnings(False)

            for direction, pin in self.pins.items():
                self._gpio.setup(pin, self._gpio.OUT)
                self._gpio.output(pin, self._gpio.LOW)

            self.is_initialized = True
            self.last_error = None
            print("[LEDs] Hardware LEDs initialized.")
            return True
        except Exception as e:
            self.last_error = str(e)
            print(f"[LEDs] Hardware init failed: {e}. Falling back to Mock.")
            self.is_mock = True
            self.is_initialized = True
            return True

    def set_led(self, direction: str, is_on: bool) -> bool:
        """Sets the state of a single directional LED."""
        if direction not in self.pins:
            return False

        if not self.is_initialized:
            self.initialize()

        self.state[direction] = bool(is_on)

        if not self.is_mock and self._gpio:
            pin = self.pins[direction]
            self._gpio.output(pin, self._gpio.HIGH if is_on else self._gpio.LOW)

        return True

    def toggle(self, direction: str) -> bool:
        """Toggles the state of a specific LED."""
        curr = self.state.get(direction, False)
        return self.set_led(direction, not curr)

    def set_all(self, is_on: bool) -> None:
        """Turns all LEDs ON or OFF."""
        for d in self.pins.keys():
            self.set_led(d, is_on)

    def cleanup(self) -> None:
        """Turns off all LEDs and releases pins."""
        self.set_all(False)
        if not self.is_mock and self._gpio:
            try:
                self._gpio.cleanup(list(self.pins.values()))
            except Exception as e:
                print(f"[LEDs] Cleanup warning: {e}")
        self.is_initialized = False
        print("[LEDs] Hardware pins released.")

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "initialized": self.is_initialized,
            "mock": self.is_mock,
            "state": self.state,
            "error": self.last_error,
        }
