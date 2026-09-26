"""
SAM Rover - Hardware Abstraction Layer (HAL) Base Interfaces
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseHardwareDevice(ABC):
    """Abstract base class for all SAM hardware devices."""

    def __init__(self, name: str, is_mock: bool = False):
        self.name = name
        self.is_mock = is_mock
        self.is_initialized = False
        self.last_error: str | None = None

    @abstractmethod
    def initialize(self) -> bool:
        """Initialize physical pins or mock resources. Return True on success."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Safely release physical pins or mock resources."""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic health status."""
        pass
