"""
SAM Rover - LED Test Example for Students
Demonstrates turning on, turning off, and blinking the 4 directional LEDs.
"""

import time
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover

def main():
    print("--- [SAM Rover] LED Subsystem Test ---")
    
    with SamRover() as rover:
        # 1. Turn on LEDs sequentially
        for direction in ("front", "right", "rear", "left"):
            print(f"Turning ON {direction.upper()} LED...")
            rover.set_led(direction, True)
            time.sleep(0.5)
            rover.set_led(direction, False)
            time.sleep(0.2)

        # 2. Blink all LEDs together 3 times
        print("Blinking ALL LEDs...")
        for _ in range(3):
            rover.set_all_leds(True)
            time.sleep(0.3)
            rover.set_all_leds(False)
            time.sleep(0.3)

    print("LED test completed successfully!")

if __name__ == "__main__":
    main()
