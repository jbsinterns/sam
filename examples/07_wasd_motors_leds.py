#!/usr/bin/env python3
"""
SAM SDK Example: 07_wasd_motors_leds.py
----------------------------------------
Interactive terminal keyboard control using curses.
  - W / S: Drive Forward / Backward
  - A / D: Pivot Left / Right
  - Space: Emergency Brake
  - 1 / 2 / 3: Speed Presets (LOW 30%, MED 60%, HIGH 90%)
  - F / B / L / R: Toggle Directional LEDs
  - Watchdog: Automatically cuts motor power within 300ms of key release
"""

import time
import sys
import curses
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from samsdk import SamRover

SPEEDS = {'1': 30.0, '2': 60.0, '3': 90.0}

def curses_app(stdscr, robot):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(50)

    speed = SPEEDS['2']
    last_key_time = time.perf_counter()
    active_action = "STOPPED"

    while True:
        stdscr.erase()
        stdscr.addstr(0, 0, "=== SAM Rover Keyboard Teleoperation ===", curses.A_BOLD)
        stdscr.addstr(2, 0, "W/S: Drive | A/D: Turn | Space: Stop")
        stdscr.addstr(3, 0, "1: LOW (30%) | 2: MED (60%) | 3: HIGH (90%)")
        stdscr.addstr(4, 0, "F/B/L/R: Toggle LEDs | Q: Quit")
        stdscr.addstr(6, 0, f"Current Speed: {speed:.0f}% | State: {active_action}")

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
                robot.drivetrain.forward(speed)
                active_action = "FORWARD"
            elif ch == 's':
                robot.drivetrain.backward(speed)
                active_action = "BACKWARD"
            elif ch == 'a':
                robot.drivetrain.turn_left(speed)
                active_action = "PIVOT LEFT"
            elif ch == 'd':
                robot.drivetrain.turn_right(speed)
                active_action = "PIVOT RIGHT"
            elif ch == ' ' or key == 27:
                robot.drivetrain.stop()
                active_action = "STOPPED"
            elif ch in SPEEDS:
                speed = SPEEDS[ch]
            elif ch == 'f':
                robot.led_front.toggle()
            elif ch == 'b':
                robot.led_back.toggle()
            elif ch == 'l':
                robot.led_left.toggle()
            elif ch == 'r':
                robot.led_right.toggle()
        else:
            # Watchdog timeout: halt if no key pressed in 300ms
            if now - last_key_time > 0.30 and active_action != "STOPPED":
                robot.drivetrain.stop()
                active_action = "STOPPED"

        stdscr.refresh()
        time.sleep(0.02)

def main():
    with SamRover() as robot:
        curses.wrapper(curses_app, robot)

if __name__ == "__main__":
    main()
