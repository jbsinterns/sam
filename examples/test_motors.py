"""
SAM Rover - Motor Driver Test Example for Students
Tests forward, backward, pivot left, and pivot right motion sequences.
"""

import time
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover

def main():
    print("--- [SAM Rover] Motor Subsystem Test ---")
    
    with SamRover() as rover:
        speed = 50.0  # 50% power

        print(f"Driving FORWARD at {speed}%...")
        rover.forward(speed)
        time.sleep(1.5)

        print("STOPPING...")
        rover.stop()
        time.sleep(0.5)

        print(f"Driving BACKWARD at {speed}%...")
        rover.backward(speed)
        time.sleep(1.5)

        print("STOPPING...")
        rover.stop()
        time.sleep(0.5)

        print(f"Turning LEFT at {speed}%...")
        rover.turn_left(speed)
        time.sleep(1.0)

        print(f"Turning RIGHT at {speed}%...")
        rover.turn_right(speed)
        time.sleep(1.0)

        print("Sequence complete. Stopping motors.")
        rover.stop()

    print("Motor test completed safely.")

if __name__ == "__main__":
    main()
