#!/usr/bin/env python3
"""
SAM SDK Example: 14_line_following.py
------------------------------------
Performs line-following control using camera frame edge analysis
and adjusting motor speeds to steer along lines.
Natively runs via lgpio on hardware or simulation mode on PC.
"""

import time
import sys
from pathlib import Path

# Allow importing samsdk from the parent directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover

try:
    import cv2
except ImportError:
    print("Error: OpenCV (cv2) is required for line following. Install with: pip3 install opencv-python")
    sys.exit(1)

def main():
    print("Loading SAM Rover configuration...")
    try:
        robot = SamRover()
        print(f"Successfully initialized robot: {robot.name}")
    except Exception as e:
        print(f"Error initializing SDK: {e}")
        sys.exit(1)

    # Initialize Camera Capture
    device_index = 0
    cap = cv2.VideoCapture(device_index)
    if not cap.isOpened():
        print(f"Error: Could not open camera device (index {device_index}).")
        robot.cleanup()
        sys.exit(1)

    print("\n--- Line Following Active ---")
    print("Aligning drivetrain to follow detected line edges. Press Ctrl+C to exit.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue

            h, w = frame.shape[:2]
            # Crop to the floor-only band (75% to 95% height)
            roi = frame[int(h * 0.75):int(h * 0.95), :]
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            M = cv2.moments(thresh)
            if M["m00"] > 300:
                cx = int(M["m10"] / M["m00"])
                error = cx - (w // 2)

                print(f"Line Location Offset: {error:4d} px", end="\r", flush=True)

                if error < -35:
                    # Steer left
                    robot.drivetrain.drive(20.0, 40.0)
                    robot.led_left.on()
                    robot.led_right.off()
                elif error > 35:
                    # Steer right
                    robot.drivetrain.drive(40.0, 20.0)
                    robot.led_right.on()
                    robot.led_left.off()
                else:
                    # Drive straight
                    robot.drivetrain.drive(35.0, 35.0)
                    robot.led_left.off()
                    robot.led_right.off()
            else:
                print("Line status: NOT DETECTED (Stopping)    ", end="\r", flush=True)
                robot.drivetrain.stop()
                robot.led_left.off()
                robot.led_right.off()

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nStopping line following...")
    finally:
        robot.drivetrain.stop()
        robot.led_left.off()
        robot.led_right.off()
        cap.release()
        robot.cleanup()
        print("Cleanup complete.")

if __name__ == "__main__":
    main()