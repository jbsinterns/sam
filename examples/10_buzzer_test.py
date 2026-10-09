#!/usr/bin/env python3
"""
SAM SDK Example: 10_buzzer_test.py
----------------------------------
Demonstrates using the Buzzer SDK wrapper class for blocking and non-blocking sound generation.
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

    try:
        # 1. Direct on/off control
        print("\n--- 1. Testing Manual On/Off Control ---")
        print("Buzzer ON for 1.5 seconds...")
        robot.buzzer.on()
        time.sleep(1.5)
        print("Buzzer OFF...")
        robot.buzzer.off()
        time.sleep(0.5)

        # 2. Testing blocking beeps
        print("\n--- 2. Testing Blocking Beeps ---")
        print("Performing 3 short blocking beeps...")
        robot.buzzer.beep(duration=0.15, count=3, delay=0.15, blocking=True)
        print("Blocking beeps finished.")
        time.sleep(0.5)

        # 3. Testing non-blocking beeps
        print("\n--- 3. Testing Asynchronous (Non-Blocking) Beeps ---")
        print("Triggering 10 asynchronous beeps in the background...")
        robot.buzzer.beep(duration=0.1, count=10, delay=0.2, blocking=False)
        
        # Perform other work in the main thread while the buzzer beeps
        for i in range(5, 0, -1):
            print(f"[Main Thread] Doing other computations... {i}s remaining")
            time.sleep(0.6)

        # 4. Stopping any active beeps
        print("\n--- 4. Stopping Active Beeps ---")
        print("Triggering background beeps again...")
        robot.buzzer.beep(duration=0.2, count=20, delay=0.2, blocking=False)
        time.sleep(1.0)
        print("Aborting the remaining beeps now...")
        robot.buzzer.stop_beep()
        print("Buzzer successfully silenced.")

    except KeyboardInterrupt:
        print("\nTest cancelled by user.")
    finally:
        print("\nReleasing Buzzer resources...")
        try:
            robot.buzzer.off()
            robot.cleanup()
        except Exception:
            pass
        print("Cleanup complete.")

if __name__ == "__main__":
    main()