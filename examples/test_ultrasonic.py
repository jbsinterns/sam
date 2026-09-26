"""
SAM Rover - 4-Directional Ultrasonic Sensor Test
Polls Front, Rear, Left, and Right HC-SR04 sensors in real time.
"""

import time
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover

def main():
    print("--- [SAM Rover] Ultrasonic Array Live Telemetry (Press Ctrl+C to stop) ---")
    
    with SamRover() as rover:
        try:
            while True:
                distances = rover.get_distances()
                front = f"{distances.get('front', 'N/A')} cm"
                rear = f"{distances.get('rear', 'N/A')} cm"
                left = f"{distances.get('left', 'N/A')} cm"
                right = f"{distances.get('right', 'N/A')} cm"

                print(f"[RADAR] FRONT: {front:<10} | REAR: {rear:<10} | LEFT: {left:<10} | RIGHT: {right:<10}")
                time.sleep(0.3)
        except KeyboardInterrupt:
            print("\nTest stopped by user.")

if __name__ == "__main__":
    main()
