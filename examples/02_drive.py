#!/usr/bin/env python3
"""
SAM SDK Example: 02_drive.py
----------------------------
Demonstrates driving motors safely (forward, backward, left, right).
Uses native lgpio motor PWM and dynamic GPIO leasing.
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

        try:
            print("\n1. Driving FORWARD at 50% speed...")
            robot.drivetrain.forward(50)
            time.sleep(2.0)

            print("2. Stopping...")
            robot.drivetrain.stop()
            time.sleep(1.0)

            print("3. Driving BACKWARD at 50% speed...")
            robot.drivetrain.backward(50)
            time.sleep(2.0)

            print("4. Stopping...")
            robot.drivetrain.stop()
            time.sleep(1.0)

            print("5. Turning LEFT at 50% speed...")
            robot.drivetrain.turn_left(50)
            time.sleep(1.5)

            print("6. Stopping...")
            robot.drivetrain.stop()
            time.sleep(1.0)

            print("7. Turning RIGHT at 50% speed...")
            robot.drivetrain.turn_right(50)
            time.sleep(1.5)

            print("8. Stopping...")
            robot.drivetrain.stop()

            print("\nDrive sequence completed successfully!")
        except KeyboardInterrupt:
            print("\nDrive test interrupted by user.")
        finally:
            robot.drivetrain.stop()
            print("Drivetrain safely stopped.")

if __name__ == "__main__":
    main()
