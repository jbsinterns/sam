#!/usr/bin/env python3
"""
SAM SDK Example: 08_wasd_motors_leds_avoid_obstacle.py
-------------------------------------------------------
Keyboard driving with 4-sensor safety interlock.
  - W (Forward): Blocked if front distance <= 35cm (Front LED illuminates)
  - S (Reverse): Blocked if rear distance <= 35cm (Rear LED illuminates)
  - A (Left): Blocked if left distance <= 35cm (Left LED illuminates)
  - D (Right): Blocked if right distance <= 35cm (Right LED illuminates)
"""

import time
import sys
import curses
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover

SPEEDS = {'1': 30.0, '2': 60.0, '3': 90.0}
LIMIT_CM = 35.0

def curses_app(stdscr, robot):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(50)

    speed = SPEEDS['2']
    last_key_time = time.perf_counter()
    action = "STOPPED"

    while True:
        stdscr.erase()
        stdscr.addstr(0, 0, "=== SAM Rover Keyboard + Obstacle Interlock ===", curses.A_BOLD)
        stdscr.addstr(2, 0, "W/S: Drive | A/D: Turn | Space: Stop | 1-3: Speed | Q: Quit")

        # Read all 4 ultrasonic distances
        d_f = robot.ultra_front.get_distance()
        d_b = robot.ultra_back.get_distance()
        d_l = robot.ultra_left.get_distance()
        d_r = robot.ultra_right.get_distance()

        # Update LED warning indicators on blocked sides
        robot.set_led('front', d_f < LIMIT_CM)
        robot.set_led('rear', d_b < LIMIT_CM)
        robot.set_led('left', d_l < LIMIT_CM)
        robot.set_led('right', d_r < LIMIT_CM)

        stdscr.addstr(4, 0, f"Sensors: Front:{d_f:4.1f}cm | Rear:{d_b:4.1f}cm | Left:{d_l:4.1f}cm | Right:{d_r:4.1f}cm")
        stdscr.addstr(5, 0, f"Current Speed: {speed:.0f}% | State: {action}")

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
                    robot.drivetrain.forward(speed)
                    action = "FORWARD"
                else:
                    robot.drivetrain.stop()
                    action = "BLOCKED (FRONT)"
                    robot.buzzer.beep(0.08)
            elif ch == 's':
                if d_b >= LIMIT_CM:
                    robot.drivetrain.backward(speed)
                    action = "BACKWARD"
                else:
                    robot.drivetrain.stop()
                    action = "BLOCKED (REAR)"
                    robot.buzzer.beep(0.08)
            elif ch == 'a':
                if d_l >= LIMIT_CM:
                    robot.drivetrain.turn_left(speed)
                    action = "PIVOT LEFT"
                else:
                    robot.drivetrain.stop()
                    action = "BLOCKED (LEFT)"
                    robot.buzzer.beep(0.08)
            elif ch == 'd':
                if d_r >= LIMIT_CM:
                    robot.drivetrain.turn_right(speed)
                    action = "PIVOT RIGHT"
                else:
                    robot.drivetrain.stop()
                    action = "BLOCKED (RIGHT)"
                    robot.buzzer.beep(0.08)
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

def main():
    with SamRover() as robot:
        curses.wrapper(curses_app, robot)

if __name__ == "__main__":
    main()
