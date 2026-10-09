#!/usr/bin/env python3
"""
SAM SDK Example: 09_wasd_motors_leds_avoid_obstacle_imu.py
-----------------------------------------------------------
Advanced keyboard teleoperation featuring:
  - 4-Sensor obstacle safety interlock
  - Closed-loop IMU heading lock (straight-line stabilization when driving W / S)
  - Automatic watchdog motor cutoff
"""

import time
import sys
import curses
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover, IMUTracker

SPEEDS = {'1': 30.0, '2': 60.0, '3': 90.0}
LIMIT_CM = 35.0

def curses_app(stdscr, robot):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(50)

    tracker = IMUTracker(robot.imu)
    tracker.calibrate(samples=60)
    tracker.start()

    speed = SPEEDS['2']
    last_key_time = time.perf_counter()
    action = "STOPPED"
    locked_yaw = 0.0
    Kp = 1.6

    try:
        while True:
            stdscr.erase()
            stdscr.addstr(0, 0, "=== SAM Rover WASD + Obstacle + IMU Lock ===", curses.A_BOLD)
            stdscr.addstr(2, 0, "W/S: Drive (IMU-Locked) | A/D: Turn | 1-3: Speed | Q: Quit")

            d_f = robot.ultra_front.get_distance()
            d_b = robot.ultra_back.get_distance()
            d_l = robot.ultra_left.get_distance()
            d_r = robot.ultra_right.get_distance()
            yaw = tracker.get_yaw()

            stdscr.addstr(4, 0, f"Heading: {yaw:+5.1f}° | F:{d_f:4.1f}cm B:{d_b:4.1f}cm L:{d_l:4.1f}cm R:{d_r:4.1f}cm")
            stdscr.addstr(5, 0, f"Speed: {speed:.0f}% | State: {action}")

            try:
                key = stdscr.getch()
            except Exception:
                key = -1

            now = time.perf_counter()

            if key != -1:
                last_key_time = now
                ch = chr(key).lower() if 0 <= key < 256 else ''

                if ch == 'q':
                    break
                elif ch == 'w':
                    if d_f >= LIMIT_CM:
                        if action != "FORWARD":
                            locked_yaw = yaw
                        err = locked_yaw - yaw
                        corr = max(-25.0, min(25.0, Kp * err))
                        robot.drivetrain.drive(speed - corr, speed + corr)
                        action = "FORWARD"
                    else:
                        robot.drivetrain.stop()
                        action = "BLOCKED (FRONT)"
                elif ch == 's':
                    if d_b >= LIMIT_CM:
                        if action != "BACKWARD":
                            locked_yaw = yaw
                        err = locked_yaw - yaw
                        corr = max(-25.0, min(25.0, Kp * err))
                        robot.drivetrain.drive(-speed - corr, -speed + corr)
                        action = "BACKWARD"
                    else:
                        robot.drivetrain.stop()
                        action = "BLOCKED (REAR)"
                elif ch == 'a':
                    if d_l >= LIMIT_CM:
                        robot.drivetrain.turn_left(speed)
                        action = "PIVOT LEFT"
                    else:
                        robot.drivetrain.stop()
                        action = "BLOCKED (LEFT)"
                elif ch == 'd':
                    if d_r >= LIMIT_CM:
                        robot.drivetrain.turn_right(speed)
                        action = "PIVOT RIGHT"
                    else:
                        robot.drivetrain.stop()
                        action = "BLOCKED (RIGHT)"
                elif ch == ' ':
                    robot.drivetrain.stop()
                    action = "STOPPED"
                elif ch in SPEEDS:
                    speed = SPEEDS[ch]
            else:
                if now - last_key_time > 0.30 and "BLOCKED" not in action:
                    robot.drivetrain.stop()
                    action = "STOPPED"

            stdscr.refresh()
            time.sleep(0.02)
    finally:
        tracker.stop()

def main():
    with SamRover() as robot:
        curses.wrapper(curses_app, robot)

if __name__ == "__main__":
    main()
