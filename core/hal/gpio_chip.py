"""
SAM Rover - Centralized lgpio Kernel Chip Manager
Provides a shared, thread-safe connection to the Linux GPIO character device (/dev/gpiochip0).
Guarantees clean pin allocation and prevents file descriptor churn across HAL devices.
Supports selective pin freeing and safe full-system teardown.
"""

import threading
from typing import Optional, Set

try:
    import lgpio
    HAS_LGPIO = True
except ImportError:
    lgpio = None
    HAS_LGPIO = False


class GPIOChipManager:
    """
    Singleton coordinator for the Linux GPIO character device (/dev/gpiochip0).
    Allows motors, ultrasonic, LEDs, and buzzer to share one kernel handle safely.
    """

    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._chip: Optional[int] = None
                cls._instance._claimed_pins: Set[int] = set()
            return cls._instance

    @property
    def is_available(self) -> bool:
        return HAS_LGPIO and lgpio is not None

    def get_chip(self) -> Optional[int]:
        """
        Returns the open gpiochip handle (chip 0 on Pi 4, chip 4 on Pi 5).
        Opens the handle lazily upon first request.
        """
        with self._lock:
            if not self.is_available:
                return None
            if self._chip is not None:
                return self._chip

            # Auto-detect Pi 4 (chip 0) or Pi 5 (chip 4)
            for c in (0, 4):
                try:
                    self._chip = lgpio.gpiochip_open(c)
                    return self._chip
                except Exception:
                    pass
            return None

    def claim_output(self, pin: int, initial_level: int = 0) -> bool:
        """Claims a pin as output through the shared chip handle. Idempotent."""
        with self._lock:
            chip = self.get_chip()
            if chip is None:
                return False
            if pin in self._claimed_pins:
                try:
                    lgpio.gpio_write(chip, pin, initial_level)
                    return True
                except Exception:
                    self._claimed_pins.discard(pin)
            try:
                lgpio.gpio_claim_output(chip, pin, initial_level)
                self._claimed_pins.add(pin)
                return True
            except Exception:
                try:
                    lgpio.gpio_free(chip, pin)
                    lgpio.gpio_claim_output(chip, pin, initial_level)
                    self._claimed_pins.add(pin)
                    return True
                except Exception:
                    return False

    def claim_input(self, pin: int) -> bool:
        """Claims a pin as input through the shared chip handle. Idempotent."""
        with self._lock:
            chip = self.get_chip()
            if chip is None:
                return False
            if pin in self._claimed_pins:
                return True
            try:
                lgpio.gpio_claim_input(chip, pin)
                self._claimed_pins.add(pin)
                return True
            except Exception:
                try:
                    lgpio.gpio_free(chip, pin)
                    lgpio.gpio_claim_input(chip, pin)
                    self._claimed_pins.add(pin)
                    return True
                except Exception:
                    return False

    def write_pin(self, pin: int, level: int) -> None:
        """Writes a digital value (0 or 1) to a claimed output pin."""
        with self._lock:
            if self._chip is not None and self.is_available:
                try:
                    lgpio.gpio_write(self._chip, pin, level)
                except Exception:
                    pass

    def read_pin(self, pin: int) -> int:
        """Reads digital level from a claimed input pin."""
        with self._lock:
            if self._chip is not None and self.is_available:
                try:
                    return lgpio.gpio_read(self._chip, pin)
                except Exception:
                    return 0
            return 0

    def tx_pwm(self, pin: int, freq: int, duty: float) -> None:
        """Outputs hardware-timed PWM on an output pin."""
        with self._lock:
            if self._chip is not None and self.is_available:
                try:
                    lgpio.tx_pwm(self._chip, pin, freq, float(duty))
                except Exception:
                    pass

    def free_pin(self, pin: int) -> None:
        """Frees an individual claimed pin without closing the shared chip handle."""
        with self._lock:
            if self._chip is not None and pin in self._claimed_pins:
                try:
                    lgpio.gpio_free(self._chip, pin)
                except Exception:
                    pass
                self._claimed_pins.discard(pin)

    def close_chip(self) -> None:
        """
        Frees all claimed pins and safely closes the kernel gpiochip handle.
        Called on hardware lease release and server shutdown.
        """
        with self._lock:
            if self._chip is not None:
                for pin in list(self._claimed_pins):
                    try:
                        lgpio.gpio_free(self._chip, pin)
                    except Exception:
                        pass
                self._claimed_pins.clear()
                try:
                    lgpio.gpiochip_close(self._chip)
                except Exception:
                    pass
                self._chip = None


gpio_chip_manager = GPIOChipManager()
