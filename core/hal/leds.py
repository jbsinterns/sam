"""
SAM Rover - Directional LED Controller
Supports native lgpio (kernel gpiochip), RPi.GPIO fallback, and mock simulation.
Controls 4 directional LEDs (Front, Rear, Left, Right).
"""

import threading
from typing import Dict, Any, Optional
from core.hal.base import BaseHardwareDevice
from core.hal.gpio_chip import gpio_chip_manager


class LEDController(BaseHardwareDevice):
    """
    Manages 4 directional indicator LEDs with thread-safe control.
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
        self.backend = "mock"
        self._lgpio = None
        self._chip: Optional[int] = None
        self._gpio = None
        self._lock = threading.RLock()

    def initialize(self) -> bool:
        if self.is_initialized:
            return True

        if self.is_mock:
            self.backend = "mock"
            self.is_initialized = True
            print("[LEDs] Initialized in SIMULATION / MOCK mode.")
            return True

        # 1. Primary: lgpio via shared GPIOChipManager
        try:
            if gpio_chip_manager.is_available:
                self._chip = gpio_chip_manager.get_chip()
                if self._chip is not None:
                    import lgpio
                    self._lgpio = lgpio
                    for direction, pin in self.pins.items():
                        gpio_chip_manager.claim_output(pin, 0)
                        gpio_chip_manager.write_pin(pin, 0)

                    self.backend = "lgpio"
                    self.is_initialized = True
                    self.last_error = None
                    print("[LEDs] lgpio hardware LEDs initialized via shared gpiochip.")
                    return True
        except Exception as e:
            print(f"[LEDs] lgpio init bypassed ({e}); falling back to RPi.GPIO...")

        # 2. Secondary Fallback: RPi.GPIO
        try:
            import RPi.GPIO as GPIO
            self._gpio = GPIO
            self._gpio.setmode(self._gpio.BCM)
            self._gpio.setwarnings(False)

            for direction, pin in self.pins.items():
                self._gpio.setup(pin, self._gpio.OUT)
                self._gpio.output(pin, self._gpio.LOW)

            self.backend = "rpi_gpio"
            self.is_initialized = True
            self.last_error = None
            print("[LEDs] RPi.GPIO hardware LEDs initialized.")
            return True
        except Exception as e:
            self.last_error = str(e)
            print(f"[LEDs] Hardware init failed: {e}. Falling back to Mock.")
            self.backend = "mock"
            self.is_mock = True
            self.is_initialized = True
            return True

    def set_led(self, direction: str, is_on: bool) -> bool:
        """Sets the state of a single directional LED."""
        with self._lock:
            if direction not in self.pins:
                return False

            if not self.is_initialized:
                self.initialize()

            self.state[direction] = bool(is_on)
            pin = self.pins[direction]

            if self.backend == "lgpio" and self._chip is not None and self._lgpio:
                try:
                    self._lgpio.gpio_write(self._chip, pin, 1 if is_on else 0)
                except Exception:
                    pass
            elif self.backend == "rpi_gpio" and self._gpio:
                try:
                    self._gpio.output(pin, self._gpio.HIGH if is_on else self._gpio.LOW)
                except Exception:
                    pass

            return True

    def toggle(self, direction: str) -> bool:
        """Toggles the state of a specific LED."""
        with self._lock:
            curr = self.state.get(direction, False)
        return self.set_led(direction, not curr)

    def set_all(self, is_on: bool) -> None:
        """Turns all LEDs ON or OFF."""
        with self._lock:
            keys = list(self.pins.keys())
        for d in keys:
            self.set_led(d, is_on)

    def cleanup(self) -> None:
        """Turns off all LEDs and completely releases pins."""
        with self._lock:
            self.set_all(False)
            if self.backend == "lgpio":
                try:
                    for pin in self.pins.values():
                        gpio_chip_manager.write_pin(pin, 0)
                        gpio_chip_manager.free_pin(pin)
                except Exception as e:
                    print(f"[LEDs] lgpio cleanup warning: {e}")
                self._chip = None

            if self.backend == "rpi_gpio" and self._gpio:
                try:
                    for pin in self.pins.values():
                        try:
                            self._gpio.output(pin, self._gpio.LOW)
                        except Exception:
                            pass
                    self._gpio.cleanup(list(self.pins.values()))
                except Exception as e:
                    print(f"[LEDs] RPi.GPIO cleanup warning: {e}")

            self.is_initialized = False
            print("[LEDs] Hardware pins completely released.")

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            state_copy = dict(self.state)
        return {
            "name": self.name,
            "initialized": self.is_initialized,
            "mock": self.is_mock,
            "backend": self.backend,
            "state": state_copy,
            "error": self.last_error,
        }
