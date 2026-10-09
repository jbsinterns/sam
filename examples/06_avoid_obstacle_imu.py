#!/usr/bin/env python3
"""
SAM SDK Example: 06_avoid_obstacle_imu.py
-----------------------------------------
Demonstrates closed-loop obstacle avoidance combining 4 ultrasonic sensors
with IMU yaw heading stabilization. Drives straight until an obstacle is detected,
then executes an evasive turn.
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover, IMUTracker

OBSTACLE_LIMIT_CM = 35.0

def main():
    print("Initializing SAM Rover SDK...")
    with SamRover() as robot:
        print(f"Successfully initialized robot: {robot.name}")

        tracker = IMUTracker(robot.imu)
        tracker.calibrate(samples=80)
        tracker.start()

        target_yaw = 0.0
        Kp_heading = 1.8

        print(f"\nStarting IMU-stabilized obstacle avoidance (Threshold: {OBSTACLE_LIMIT_CM}cm).")
        print("Press Ctrl+C to stop.\n")

        try:
            while True:
                dist_front = robot.ultra_front.get_distance()
                dist_left = robot.ultra_left.get_distance()
                dist_right = robot.ultra_right.get_distance()
                current_yaw = tracker.get_yaw()

                print(f"Yaw: {current_yaw:+.1f}° | Front: {dist_front:5.1f}cm | L: {dist_left:5.1f}cm | R: {dist_right:5.1f}cm", end="\r")

                if dist_front < OBSTACLE_LIMIT_CM:
                    robot.drivetrain.stop()
                    print(f"\n[OBSTACLE] Front obstacle at {dist_front:.1f}cm!")

                    if dist_left > dist_right and dist_left > OBSTACLE_LIMIT_CM:
                        print("Evasive 90° LEFT Turn...")
                        robot.led_left.on()
                        target_yaw += 90.0
                        timeout = time.perf_counter() + 3.0
                        while time.perf_counter() < timeout and abs(target_yaw - tracker.get_yaw()) > 4.0:
                            robot.drivetrain.turn_left(45)
                            time.sleep(0.02)
                        robot.led_left.off()
                    elif dist_right >= dist_left and dist_right > OBSTACLE_LIMIT_CM:
                        print("Evasive 90° RIGHT Turn...")
                        robot.led_right.on()
                        target_yaw -= 90.0
                        timeout = time.perf_counter() + 3.0
                        while time.perf_counter() < timeout and abs(target_yaw - tracker.get_yaw()) > 4.0:
                            robot.drivetrain.turn_right(45)
                            time.sleep(0.02)
                        robot.led_right.off()
                    else:
                        print("Reversing from dead end...")
                        robot.led_back.on()
                        robot.drivetrain.backward(40)
                        time.sleep(1.2)
                        robot.led_back.off()
                        target_yaw += 180.0

                    robot.drivetrain.stop()
                else:
                    error = target_yaw - current_yaw
                    correction = max(-25.0, min(25.0, Kp_heading * error))
                    robot.drivetrain.drive(45 - correction, 45 + correction)

                time.sleep(0.03)
        except KeyboardInterrupt:
            print("\nObstacle avoidance stopped by user.")
        finally:
            tracker.stop()
            robot.drivetrain.stop()

if __name__ == "__main__":
    main()
