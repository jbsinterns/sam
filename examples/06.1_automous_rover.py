#!/usr/bin/env python3
"""
SAM SDK Example: 06.1_automous_rover.py
----------------------------------------
Advanced autonomous rover demo integrating:
  - 4 Ultrasonic sensors (front, rear, left, right)
  - IMU closed-loop heading stabilization
  - Directional indicator LEDs
  - Audible buzzer notifications
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
        print(f"Successfully initialized autonomous rover: {robot.name}")

        tracker = IMUTracker(robot.imu)
        tracker.calibrate(samples=80)
        tracker.start()

        # Startup sound chirp
        robot.buzzer.beep(0.1)
        time.sleep(0.15)
        robot.buzzer.beep(0.1)

        target_yaw = 0.0
        Kp = 1.8

        print("\n=== Autonomous Navigation Active ===")
        print("Press Ctrl+C to stop.\n")

        try:
            while True:
                d_front = robot.ultra_front.get_distance()
                d_left = robot.ultra_left.get_distance()
                d_right = robot.ultra_right.get_distance()
                d_rear = robot.ultra_rear.get_distance()
                yaw = tracker.get_yaw()

                print(f"Yaw:{yaw:+5.1f}° | F:{d_front:4.1f}cm L:{d_left:4.1f}cm R:{d_right:4.1f}cm B:{d_rear:4.1f}cm", end="\r")

                if d_front < OBSTACLE_LIMIT_CM:
                    robot.drivetrain.stop()
                    robot.buzzer.beep(0.08)
                    print(f"\n[BLOCKED] Front distance: {d_front:.1f}cm")

                    if d_left > d_right and d_left > OBSTACLE_LIMIT_CM:
                        print("Action: Navigating LEFT")
                        robot.led_left.start_blink(0.2)
                        target_yaw += 90.0
                        while abs(target_yaw - tracker.get_yaw()) > 4.0:
                            robot.drivetrain.turn_left(45)
                            time.sleep(0.02)
                        robot.led_left.stop_blink()
                    elif d_right >= d_left and d_right > OBSTACLE_LIMIT_CM:
                        print("Action: Navigating RIGHT")
                        robot.led_right.start_blink(0.2)
                        target_yaw -= 90.0
                        while abs(target_yaw - tracker.get_yaw()) > 4.0:
                            robot.drivetrain.turn_right(45)
                            time.sleep(0.02)
                        robot.led_right.stop_blink()
                    elif d_rear > OBSTACLE_LIMIT_CM:
                        print("Action: Reversing")
                        robot.led_back.start_blink(0.2)
                        robot.buzzer.beep(0.2)
                        robot.drivetrain.backward(40)
                        time.sleep(1.2)
                        robot.led_back.stop_blink()
                        target_yaw += 180.0
                    else:
                        print("Trapped! Full halt.")
                        robot.buzzer.beep(0.5)
                        time.sleep(1.0)
                    robot.drivetrain.stop()
                else:
                    err = target_yaw - yaw
                    corr = max(-25.0, min(25.0, Kp * err))
                    robot.drivetrain.drive(45 - corr, 45 + corr)

                time.sleep(0.03)
        except KeyboardInterrupt:
            print("\nAutonomous mission halted.")
        finally:
            tracker.stop()
            robot.drivetrain.stop()

if __name__ == "__main__":
    main()
