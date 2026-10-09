#!/usr/bin/env python3
"""
SAM SDK Example: 03_avoid_obstacles.py
--------------------------------------
Demonstrates combining distance sensors and driving controls to avoid obstacles reactively.
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover

OBSTACLE_LIMIT_CM = 35.0

def main():
    print("Initializing SAM Rover SDK...")
    with SamRover() as robot:
        print(f"Successfully initialized robot: {robot.name}")
        print(f"\nStarting reactive obstacle avoidance (Threshold: {OBSTACLE_LIMIT_CM}cm).")
        print("Press Ctrl+C to stop the robot.\n")

        try:
            while True:
                dist_front = robot.ultra_front.get_distance()
                dist_left = robot.ultra_left.get_distance()
                dist_right = robot.ultra_right.get_distance()

                print(f"Front: {dist_front:5.1f}cm | Left: {dist_left:5.1f}cm | Right: {dist_right:5.1f}cm", end="\r")

                if dist_front < OBSTACLE_LIMIT_CM:
                    robot.drivetrain.stop()
                    print(f"\n[OBSTACLE] Front obstacle at {dist_front:.1f}cm! Deciding escape route...")
                    
                    if dist_left > dist_right and dist_left > OBSTACLE_LIMIT_CM:
                        print("Turning LEFT...")
                        robot.led_left.on()
                        robot.drivetrain.turn_left(50)
                        time.sleep(0.8)
                        robot.led_left.off()
                    elif dist_right >= dist_left and dist_right > OBSTACLE_LIMIT_CM:
                        print("Turning RIGHT...")
                        robot.led_right.on()
                        robot.drivetrain.turn_right(50)
                        time.sleep(0.8)
                        robot.led_right.off()
                    else:
                        print("Trapped! Reversing...")
                        robot.led_back.on()
                        robot.drivetrain.backward(40)
                        time.sleep(1.2)
                        robot.led_back.off()
                        robot.drivetrain.turn_right(50)
                        time.sleep(0.8)
                    robot.drivetrain.stop()
                else:
                    robot.drivetrain.forward(45)

                time.sleep(0.05)
        except KeyboardInterrupt:
            print("\nObstacle avoidance stopped by user.")
        finally:
            robot.drivetrain.stop()

if __name__ == "__main__":
    main()
