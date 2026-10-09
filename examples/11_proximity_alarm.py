#!/usr/bin/env python3
"""
SAM SDK Example: 11_proximity_alarm.py
--------------------------------------
Uses the back ultrasonic sensor to detect obstacles and increases the frequency
of warning beeps and LED indicators as the obstacle gets closer.
Natively runs via lgpio on hardware or simulation mode on PC.
"""

import time
import sys
from pathlib import Path

# Allow importing samsdk from the parent directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover

def main():
    print("Loading SAM Rover configuration...")
    try:
        robot = SamRover()
        print(f"Successfully initialized robot: {robot.name}")
    except Exception as e:
        print(f"Error initializing SDK: {e}")
        sys.exit(1)

    print("\n--- Proximity Alarm Active ---")
    print("Move an object close to the Back Ultrasonic sensor to trigger alerts.")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            # Measure back distance (in cm)
            distance = robot.ultra_back.get_distance()
            print(f"Back distance: {distance:6.1f} cm", end="\r", flush=True)

            # Determine alert level and timing based on distance
            if distance < 10.0:
                # Critical block: Continuous beep & LEDs on
                robot.buzzer.on()
                robot.led_back.on()
                time.sleep(0.1)
            elif distance < 20.0:
                # High alert: Rapid beeping and blinking (50ms beep, 100ms cycle)
                robot.led_back.on()
                robot.buzzer.beep(duration=0.05, count=1, blocking=True)
                robot.led_back.off()
                time.sleep(0.05)
            elif distance < 40.0:
                # Medium alert: Moderate beeping and blinking (100ms beep, 300ms cycle)
                robot.led_back.on()
                robot.buzzer.beep(duration=0.1, count=1, blocking=True)
                robot.led_back.off()
                time.sleep(0.2)
            elif distance < 80.0:
                # Low alert: Slow warning (150ms beep, 800ms cycle)
                robot.led_back.on()
                robot.buzzer.beep(duration=0.15, count=1, blocking=True)
                robot.led_back.off()
                time.sleep(0.65)
            else:
                # Safe zone: No alerts, wait before next measurement
                robot.buzzer.off()
                robot.led_back.off()
                time.sleep(0.2)

    except KeyboardInterrupt:
        print("\nStopping proximity alarm...")
    finally:
        print("\nReleasing indicator resources...")
        try:
            robot.buzzer.off()
            robot.led_back.off()
            robot.cleanup()
        except Exception:
            pass
        print("Cleanup complete.")

if __name__ == "__main__":
    main()