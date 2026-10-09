#!/usr/bin/env python3
"""
SAM SDK Example: 13_face_tracking.py
------------------------------------
Tracks human faces in the camera feed using OpenCV Haar Cascades and
steers the drivetrain to keep the detected face centered in view.
Natively runs via lgpio on hardware or simulation mode on PC.
"""

import time
import sys
import os
from pathlib import Path

# Allow importing samsdk from the parent directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover

try:
    import cv2
except ImportError:
    print("Error: OpenCV (cv2) is required for face tracking. Install with: pip3 install opencv-python")
    sys.exit(1)

def find_cascade_path() -> str:
    """Finds the frontal face cascade XML across standard repository and system locations."""
    repo_root = Path(__file__).resolve().parent.parent
    candidates = [
        repo_root / "data" / "haarcascade_frontalface_default.xml",
        Path("/home/sam3/Desktop/Pi-Robot/Bigrover_febUI/haarcascade_frontalface_default.xml"),
        Path("/home/sam3/Desktop/Pi-Robot/data/haarcascade_frontalface_default.xml"),
    ]
    if hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
        candidates.append(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")

    for p in candidates:
        if p.exists():
            return str(p)
    return ""

def main():
    print("Loading SAM Rover configuration...")
    try:
        robot = SamRover()
        print(f"Successfully initialized robot: {robot.name}")
    except Exception as e:
        print(f"Error initializing SDK: {e}")
        sys.exit(1)

    cascade_path = find_cascade_path()
    if not cascade_path:
        print("Error: Haar Cascade classifier file not found in repository or system paths.")
        robot.cleanup()
        sys.exit(1)

    print(f"Loaded face model from: {cascade_path}")
    detector = cv2.CascadeClassifier(cascade_path)

    # Initialize Camera Capture
    device_index = 0
    cap = cv2.VideoCapture(device_index)
    if not cap.isOpened():
        print(f"Error: Could not open camera device (index {device_index}).")
        robot.cleanup()
        sys.exit(1)

    print("\n--- Face Tracking Active ---")
    print("Aligning drivetrain to look at faces. Press Ctrl+C to exit.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40))

            if len(faces) > 0:
                # Find the largest face bounding box
                x, y, w, h = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)[0]
                cx = x + w // 2
                frame_width = frame.shape[1]

                print(f"Face detected at center X: {cx:4d} (Frame width: {frame_width})", end="\r", flush=True)

                # Steer toward face center
                if cx < frame_width * 0.4:
                    # Face is on left, turn left slowly
                    robot.drivetrain.drive(-35.0, 35.0)
                    robot.led_left.on()
                    robot.led_right.off()
                elif cx > frame_width * 0.6:
                    # Face is on right, turn right slowly
                    robot.drivetrain.drive(35.0, -35.0)
                    robot.led_right.on()
                    robot.led_left.off()
                else:
                    # Face centered, hold position
                    robot.drivetrain.stop()
                    robot.led_left.off()
                    robot.led_right.off()
            else:
                # No face detected, stop and turn off turn LEDs
                robot.drivetrain.stop()
                robot.led_left.off()
                robot.led_right.off()

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nStopping face tracking...")
    finally:
        robot.drivetrain.stop()
        robot.led_left.off()
        robot.led_right.off()
        cap.release()
        robot.cleanup()
        print("Cleanup complete.")

if __name__ == "__main__":
    main()