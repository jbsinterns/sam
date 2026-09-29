"""
SAM Rover - Pydantic v2 Configuration Schema
Validates rover hardware parameters, safety thresholds, and detects GPIO pin collisions at startup.
"""

from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class MotorSidePins(BaseModel):
    in1: Optional[int] = Field(None, ge=1, le=27, description="BCM forward pin")
    in2: Optional[int] = Field(None, ge=1, le=27, description="BCM reverse pin")
    in3: Optional[int] = Field(None, ge=1, le=27, description="BCM right forward pin")
    in4: Optional[int] = Field(None, ge=1, le=27, description="BCM right reverse pin")
    ena: Optional[int] = Field(None, ge=1, le=27, description="BCM PWM speed pin (left)")
    enb: Optional[int] = Field(None, ge=1, le=27, description="BCM PWM speed pin (right)")

    model_config = {"extra": "allow"}


class MotorsConfig(BaseModel):
    left: MotorSidePins
    right: MotorSidePins
    pwm_frequency: int = Field(default=1000, ge=50, le=50000, description="PWM frequency in Hz")
    min_duty_cycle: float = Field(default=25.0, ge=0.0, le=80.0, description="Minimum duty cycle to overcome gear stiction")
    steering_expo: float = Field(default=0.3, ge=0.0, le=1.0, description="Exponential steering sensitivity curve")

    model_config = {"extra": "allow"}


class UltrasonicSensorPins(BaseModel):
    trigger: int = Field(ge=1, le=27, description="BCM Trigger pin")
    echo: int = Field(ge=1, le=27, description="BCM Echo pin")

    model_config = {"extra": "allow"}


class IMUConfig(BaseModel):
    bus: int = Field(default=1, ge=0, le=10)
    addresses: List[int] = Field(default_factory=lambda: [0x68, 0x69])

    model_config = {"extra": "allow"}


class GPIOConfig(BaseModel):
    motors: MotorsConfig
    ultrasonic: Dict[str, UltrasonicSensorPins]
    leds: Dict[str, int]
    buzzer: Optional[int] = Field(default=20, ge=1, le=27)
    imu: Optional[IMUConfig] = None

    model_config = {"extra": "allow"}

    @model_validator(mode="after")
    def verify_no_pin_collisions(self):
        """
        Critical Enterprise Hardware Guard:
        Verifies that no physical GPIO pin is assigned to multiple components.
        Prevents electrical short-circuits and uncommanded hardware contention.
        """
        pin_usage: Dict[int, str] = {}

        def record_pin(pin: Optional[int], component: str):
            if pin is None:
                return
            if pin in pin_usage:
                raise ValueError(
                    f"GPIO PIN COLLISION DETECTED on BCM {pin}! "
                    f"Assigned to both '{pin_usage[pin]}' and '{component}'. "
                    "Each peripheral must use an electrically independent pin to prevent hardware damage."
                )
            pin_usage[pin] = component

        # 1. Motors
        left = self.motors.left
        right = self.motors.right
        for field, pin in [("in1", left.in1), ("in2", left.in2), ("ena", left.ena)]:
            record_pin(pin, f"motors.left.{field}")
        for field, pin in [("in3", right.in3), ("in4", right.in4), ("enb", right.enb)]:
            record_pin(pin, f"motors.right.{field}")

        # 2. Ultrasonic Sensors
        for name, sensor in self.ultrasonic.items():
            record_pin(sensor.trigger, f"ultrasonic.{name}.trigger")
            record_pin(sensor.echo, f"ultrasonic.{name}.echo")

        # 3. LEDs
        for name, pin in self.leds.items():
            record_pin(pin, f"leds.{name}")

        # 4. Buzzer
        if self.buzzer is not None:
            record_pin(self.buzzer, "buzzer")

        return self


class SafetyConfig(BaseModel):
    watchdog_timeout_sec: float = Field(default=0.5, ge=0.05, le=10.0)
    obstacle_warning_cm: float = Field(default=35.0, ge=5.0, le=300.0)
    obstacle_critical_stop_cm: float = Field(default=15.0, ge=2.0, le=150.0)
    idle_hardware_release_sec: float = Field(default=60.0, ge=1.0)

    model_config = {"extra": "allow"}


class CameraConfig(BaseModel):
    preferred_index: int = Field(default=0, ge=0, le=10)
    width: int = Field(default=640, ge=160, le=3840)
    height: int = Field(default=480, ge=120, le=2160)
    fps: int = Field(default=25, ge=1, le=120)
    jpeg_quality: int = Field(default=75, ge=10, le=100)

    model_config = {"extra": "allow"}


class SystemConfig(BaseModel):
    name: str = Field(default="SAM")
    version: str = Field(default="2.0.0")
    mock_hardware: Union[bool, str] = Field(default="auto")
    port: int = Field(default=8000, ge=1, le=65535)
    host: str = Field(default="0.0.0.0")

    model_config = {"extra": "allow"}


class NetworkConfig(BaseModel):
    ap_interface: str = "wlan0"
    ap_ssid: str = "SAM-Rover-Setup"
    ap_ip: str = "192.168.4.1"
    external_interface: str = "wlan1"
    wifi_check_interval_sec: int = Field(default=15, ge=2)

    model_config = {"extra": "allow"}


class RoverConfigSchema(BaseModel):
    system: SystemConfig = Field(default_factory=SystemConfig)
    gpio: GPIOConfig
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    camera: CameraConfig = Field(default_factory=CameraConfig)
    network: Optional[NetworkConfig] = Field(default_factory=NetworkConfig)

    model_config = {"extra": "allow"}
