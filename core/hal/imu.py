"""
SAM Rover - 6-DOF / 9-DOF IMU Controller (MPU-6050 / MPU-9250 / ICM-20948)
Reads accelerometer, gyroscope, pitch, and roll over I2C bus 1.
"""

import time
import math
import threading
from typing import Dict, Any, Optional
from core.hal.base import BaseHardwareDevice

try:
    import smbus2
    HAS_SMBUS = True
except ImportError:
    HAS_SMBUS = False


class IMUDriver(BaseHardwareDevice):
    """
    Interfaces with I2C IMU (MPU-6050 / ICM-20948) on bus 1 (default 0x68).
    Thread-safe and failsafe: sensor failures degrade gracefully without blocking the rover.
    """

    ACCEL_SCALE = 16384.0  # LSB/g (for +/- 2g range)
    GYRO_SCALE = 131.0     # LSB/(deg/s) (for +/- 250 deg/s range)

    def __init__(self, config: Dict[str, Any], is_mock: bool = False):
        super().__init__("IMUDriver", is_mock)
        self.bus_num = int(config.get("bus", 1))
        self.addresses = config.get("addresses", [0x68, 0x69])
        self.active_address: Optional[int] = None
        self.bus = None

        self._lock = threading.Lock()
        self.data: Dict[str, Any] = {
            "ax": 0.0, "ay": 0.0, "az": 1.0,
            "gx": 0.0, "gy": 0.0, "gz": 0.0,
            "pitch": 0.0,
            "roll": 0.0,
            "temp_c": 25.0,
        }
        self._mock_step = 0.0

    def initialize(self) -> bool:
        if self.is_initialized:
            return True

        if self.is_mock or not HAS_SMBUS:
            self.is_initialized = True
            print("[IMU] Initialized in SIMULATION / MOCK mode.")
            return True

        try:
            self.bus = smbus2.SMBus(self.bus_num)
            for addr in self.addresses:
                try:
                    # Check WHO_AM_I register (0x75)
                    who = self.bus.read_byte_data(addr, 0x75)
                    self.active_address = addr
                    # Wake up MPU-6050 / 9250 (PWR_MGMT_1 at 0x6B, clear sleep bit)
                    self.bus.write_byte_data(addr, 0x6B, 0x00)
                    time.sleep(0.02)
                    self.is_initialized = True
                    self.last_error = None
                    print(f"[IMU] Hardware IMU initialized on I2C bus {self.bus_num} address 0x{addr:02X} (whoami=0x{who:02X})")
                    return True
                except Exception:
                    continue

            # If not detected on either address
            print("[IMU] No physical I2C IMU detected; using fallback.")
            self.is_mock = True
            self.is_initialized = True
            return True
        except Exception as e:
            self.last_error = str(e)
            print(f"[IMU] Initialization failed: {e}. Switching to Mock.")
            self.is_mock = True
            self.is_initialized = True
            return True

    def _read_word_2c(self, reg: int) -> int:
        high = self.bus.read_byte_data(self.active_address, reg)
        low = self.bus.read_byte_data(self.active_address, reg + 1)
        val = (high << 8) | low
        if val >= 0x8000:
            return val - 65536
        return val

    def read_sensors(self) -> Dict[str, Any]:
        """Reads accelerometer, gyro, computes pitch & roll."""
        if not self.is_initialized:
            self.initialize()

        if self.is_mock or not self.bus or self.active_address is None:
            self._mock_step += 0.05
            pitch = round(3.0 * math.sin(self._mock_step), 1)
            with self._lock:
                self.data = {
                    "ax": round(0.05 * math.sin(self._mock_step), 3),
                    "ay": round(0.05 * math.cos(self._mock_step), 3),
                    "az": 1.0,
                    "gx": 0.0, "gy": 0.0, "gz": 0.0,
                    "pitch": pitch,
                    "roll": roll,
                    "temp_c": 26.5,
                }
            return self.data.copy()

        try:
            with self._lock:
                raw_ax = self._read_word_2c(0x3B)
                raw_ay = self._read_word_2c(0x3D)
                raw_az = self._read_word_2c(0x3F)
                raw_temp = self._read_word_2c(0x41)
                raw_gx = self._read_word_2c(0x43)
                raw_gy = self._read_word_2c(0x45)
                raw_gz = self._read_word_2c(0x47)

                ax = round(raw_ax / self.ACCEL_SCALE, 3)
                ay = round(raw_ay / self.ACCEL_SCALE, 3)
                az = round(raw_az / self.ACCEL_SCALE, 3)

                gx = round(raw_gx / self.GYRO_SCALE, 1)
                gy = round(raw_gy / self.GYRO_SCALE, 1)
                gz = round(raw_gz / self.GYRO_SCALE, 1)

                temp_c = round((raw_temp / 340.0) + 36.53, 1)

                # Compute pitch and roll angles from gravity vector
                pitch = round(math.atan2(ax, math.sqrt(ay**2 + az**2)) * 180.0 / math.pi, 1)
                roll = round(math.atan2(ay, math.sqrt(ax**2 + az**2)) * 180.0 / math.pi, 1)

                self.data = {
                    "ax": ax, "ay": ay, "az": az,
                    "gx": gx, "gy": gy, "gz": gz,
                    "pitch": pitch,
                    "roll": roll,
                    "temp_c": temp_c,
                }
            return self.data.copy()
        except Exception:
            return self.data.copy()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "initialized": self.is_initialized,
                "mock": self.is_mock,
                "address": hex(self.active_address) if self.active_address else None,
                "error": self.last_error,
                "data": self.data.copy(),
            }

    def cleanup(self) -> None:
        if self.bus:
            try:
                self.bus.close()
            except Exception:
                pass
            self.bus = None
        self.is_initialized = False
