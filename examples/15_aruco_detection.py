#!/usr/bin/env python3
"""
SAM SDK Example: 15_aruco_detection.py
--------------------------------------
Detects ArUco markers in the camera feed using the samsdk tracker,
printing details of detected IDs in real-time.
Natively runs via lgpio on hardware or simulation mode on PC.
"""

import time
import sys
from pathlib import Path

# Allow importing samsdk from the parent directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover, ArUcoTracker

try:
    import cv2
except ImportError:
    print("Error: OpenCV (cv2) is required for ArUco detection. Install with: pip3 install opencv-python")
    sys.exit(1)

def main():
    print("Loading SAM Rover configuration...")
    try:
        robot = SamRover()
        print(f"Successfully initialized robot: {robot.name}")
    except Exception as e:
        print(f"Error initializing SDK: {e}")
        sys.exit(1)

    try:
        tracker = ArUcoTracker()
    except Exception as e:
        print(f"Error initializing ArUcoTracker: {e}")
        robot.cleanup()
        sys.exit(1)

    # Initialize Camera Capture
    device_index = 0
    cap = cv2.VideoCapture(device_index)
    if not cap.isOpened():
        print(f"Error: Could not open camera device (index {device_index}).")
        robot.cleanup()
        sys.exit(1)

    print("\n--- ArUco Detection Active ---")
    print("Detecting DICT_4X4_50 marker IDs. Press Ctrl+C to exit.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue

            # Perform detection using SDK tracker
            corners, ids, rejected = tracker.detect(frame)

            if ids:
                # Blink/turn on LEDs indicating detection
                robot.led_front.on()
                robot.led_back.on()
                print(f"Detected ArUco Marker IDs: {ids}         ", end="\r", flush=True)
            else:
                robot.led_front.off()
                robot.led_back.off()
                print("Scanning for markers...                  ", end="\r", flush=True)

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nStopping ArUco detection...")
    finally:
        robot.led_front.off()
        robot.led_back.off()
        cap.release()
        robot.cleanup()
        print("Cleanup complete.")

if __name__ == "__main__":
    main()