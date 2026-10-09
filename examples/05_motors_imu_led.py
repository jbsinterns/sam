#!/usr/bin/env python3
"""
SAM SDK Example: 05_motors_imu_led.py
-------------------------------------
Demonstrates closed-loop motor control using the I2C IMU (gyroscope integration)
and status LEDs. Stabilizes straight-line driving and executes precise turning angles.
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover, IMUTracker

def drive_straight(robot, tracker, speed: float, duration: float, target_yaw: float, led):
    direction = "straight" if speed >= 0 else "backward"
    print(f"\nDriving {direction} (Speed: {speed}%, Target Yaw: {target_yaw:+.1f}°)")

    start_time = time.perf_counter()
    led.start_blink(0.25)
    Kp = 1.8  # Steering correction proportional gain

    while time.perf_counter() - start_time < duration:
        current_yaw = tracker.get_yaw()
        error = target_yaw - current_yaw
        correction = max(-30.0, min(30.0, Kp * error))

        left_speed = speed - correction
        right_speed = speed + correction
        robot.drivetrain.drive(left_speed, right_speed)

        sys.stdout.write(f"\rYaw: {current_yaw:+.1f}° | Err: {error:+.1f}° | Correction: {correction:+.1f}")
        sys.stdout.flush()
        time.sleep(0.02)

    robot.drivetrain.stop()
    led.stop_blink()
    print(f"\nSettled Yaw: {tracker.get_yaw():.1f}°")
    time.sleep(0.5)

def turn_to(robot, tracker, target_yaw: float, led):
    print(f"\nTurning to target yaw: {target_yaw:+.1f}°")
    led.start_blink(0.25)
    Kp = 1.6
    min_speed = 30.0
    max_speed = 65.0
    timeout = time.perf_counter() + 5.0

    while time.perf_counter() < timeout:
        current_yaw = tracker.get_yaw()
        error = target_yaw - current_yaw

        if abs(error) < 2.0:
            break

        speed = Kp * error
        if speed > 0:
            speed = max(min_speed, min(max_speed, speed))
        else:
            speed = min(-min_speed, max(-max_speed, speed))

        robot.drivetrain.drive(-speed, speed)
        sys.stdout.write(f"\rYaw: {current_yaw:+.1f}° | Err: {error:+.1f}° | Speed: {speed:+.1f}")
        sys.stdout.flush()
        time.sleep(0.02)

    robot.drivetrain.stop()
    led.stop_blink()
    print(f"\nTurn complete. Settled Yaw: {tracker.get_yaw():.1f}°")
    time.sleep(0.5)

def main():
    print("Initializing SAM Rover SDK...")
    with SamRover() as robot:
        print(f"Successfully initialized robot: {robot.name}")

        tracker = IMUTracker(robot.imu)
        tracker.calibrate(samples=80)
        tracker.start()

        try:
            print("\n=== STARTING OUTBOUND PATH ===")
            drive_straight(robot, tracker, 45, 2.5, 0.0, robot.led_front)
            turn_to(robot, tracker, -90.0, robot.led_right)
            drive_straight(robot, tracker, 45, 2.5, -90.0, robot.led_front)

            print("\n=== STARTING RETURN PATH ===")
            drive_straight(robot, tracker, -45, 2.5, -90.0, robot.led_back)
            turn_to(robot, tracker, 0.0, robot.led_left)
            drive_straight(robot, tracker, -45, 2.5, 0.0, robot.led_back)

            print(f"\nReturn complete. Final integrated Yaw: {tracker.get_yaw():.1f}°")
        except KeyboardInterrupt:
            print("\nTest interrupted by user.")
        finally:
            tracker.stop()
            robot.drivetrain.stop()

if __name__ == "__main__":
    main()
