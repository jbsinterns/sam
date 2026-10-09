#!/usr/bin/env python3
"""
SAM SDK Example: 04_motors_leds.py
-----------------------------------
Demonstrates synchronized motor driving and indicator LED flashing.
Forward (Front LED), Backward (Rear LED), Left (Left LED), Right (Right LED).
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover

def run_phase(name, movement_func, led, drivetrain, duration=2.5):
    print(f"\n--- Running Phase: {name} ---")
    led.start_blink(0.25)
    movement_func()
    time.sleep(duration)
    drivetrain.stop()
    led.stop_blink()
    time.sleep(1.0)

def main():
    print("Initializing SAM Rover SDK...")
    with SamRover() as robot:
        print(f"Successfully initialized robot: {robot.name}")

        try:
            run_phase("Drive Forward (Front LED Blink)", lambda: robot.drivetrain.forward(50), robot.led_front, robot.drivetrain)
            run_phase("Drive Backward (Rear LED Blink)", lambda: robot.drivetrain.backward(50), robot.led_back, robot.drivetrain)
            run_phase("Pivot Left (Left LED Blink)", lambda: robot.drivetrain.turn_left(50), robot.led_left, robot.drivetrain)
            run_phase("Pivot Right (Right LED Blink)", lambda: robot.drivetrain.turn_right(50), robot.led_right, robot.drivetrain)

            print("\nMotors & LEDs test completed successfully!")
        except KeyboardInterrupt:
            print("\nTest interrupted by user.")
        finally:
            robot.drivetrain.stop()

if __name__ == "__main__":
    main()
