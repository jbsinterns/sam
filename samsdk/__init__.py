"""
SAM Rover SDK (Samsdk)
A Python toolkit for robotics students, researchers, and developers.
"""

import sys
from pathlib import Path

# Automatically ensure SAM repository root is in sys.path so core modules resolve from anywhere
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.append(_repo_root)

from samsdk.client import SamRover, ArUcoTracker, IMUTracker

__all__ = ["SamRover", "ArUcoTracker", "IMUTracker"]
__version__ = "2.0.0"

