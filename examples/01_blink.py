#!/usr/bin/env python3
"""
SAM SDK Example: 01_blink.py
----------------------------
Demonstrates importing SamRover and using LED background blinking.
Natively runs via lgpio on hardware or simulation mode on PC.
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover

def main():
    print("Initializing SAM Rover SDK...")
    with SamRover() as robot:
        print(f"Successfully initialized robot: {robot.name}")

        led_sequence = [
            ("Front LED", robot.led_front),
            ("Back LED", robot.led_back),
            ("Right LED", robot.led_right),
            ("Left LED", robot.led_left),
        ]

        for name, led in led_sequence:
            print(f"\nStarting background blinking on {name} (1Hz)...")
            led.start_blink(interval=0.5)

            for i in range(5, 0, -1):
                print(f"Blinking {name}... {i}s remaining")
                time.sleep(1.0)

            led.stop_blink()

        print("\nBlink test complete.")

if __name__ == "__main__":
    main()
