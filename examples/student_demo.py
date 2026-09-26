"""
SAM Rover - Autonomous Obstacle Avoidance Demo
An educational template for students:
Drives forward until an obstacle is detected within 30cm,
then stops, blinks LEDs, looks for a clear direction, and turns.
"""

import time
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover

def autonomous_navigator():
    print("=== [SAM Rover] Autonomous Avoidance Routine Starting ===")
    print("Press Ctrl+C at any time to halt.")

    CRITICAL_DISTANCE_CM = 25.0

    with SamRover() as rover:
        try:
            while True:
                # 1. Read front distance
                front_dist = rover.get_distance("front")
                left_dist = rover.get_distance("left")
                right_dist = rover.get_distance("right")

                print(f"[NAV] Front: {front_dist}cm | Left: {left_dist}cm | Right: {right_dist}cm")

                # 2. Check for obstacle
                if front_dist is not None and front_dist < CRITICAL_DISTANCE_CM:
                    print(f"⚠️ Obstacle detected ahead ({front_dist}cm)! Stopping...")
                    rover.stop()
                    rover.set_led("front", True)
                    time.sleep(0.3)

                    # Decide turn direction based on side clearance
                    l_val = left_dist if left_dist is not None else 0
                    r_val = right_dist if right_dist is not None else 0

                    if l_val >= r_val:
                        print("Turning LEFT towards clearer space...")
                        rover.set_led("left", True)
                        rover.turn_left(speed=50)
                        time.sleep(0.8)
                        rover.set_led("left", False)
                    else:
                        print("Turning RIGHT towards clearer space...")
                        rover.set_led("right", True)
                        rover.turn_right(speed=50)
                        time.sleep(0.8)
                        rover.set_led("right", False)

                    rover.stop()
                    rover.set_led("front", False)
                else:
                    # Clear path: drive forward smoothly
                    rover.forward(speed=45)
                    time.sleep(0.1)

        except KeyboardInterrupt:
            print("\nAutonomous routine halted by user.")
            rover.stop()

if __name__ == "__main__":
    autonomous_navigator()
