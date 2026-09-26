# SAM Rover (Smart Autonomous Mobile Rover)

An educational, modular robotics software platform and teleoperation dashboard for Raspberry Pi 4 running Ubuntu.

---

## 🌟 Key Architecture & Highlights

1. **SAM Python SDK (`Samsdk`)**:
   * Clean, expressive Python toolkit for students, classes, and research labs.
   * Auto-detects camera ports and I2C IMU addresses (`0x68` / `0x69`).
   * Can be used directly or within custom autonomous scripts without interfering with web services.

2. **Dynamic GPIO Leasing (No "Device or Resource Busy" Conflicts)**:
   * The FastAPI web server runs 24/7 in the background upon boot, but **leaves GPIO uninitialized** by default.
   * Hardware is claimed only when the web UI is active and automatically released after an inactivity timeout (or via UI toggle), allowing student scripts to execute freely.

3. **Multi-Modal Web Teleoperation Dashboard**:
   * **Live Video Streaming**: Realtime low-latency MJPEG stream over `/api/video/feed` with animated synthetic HUD fallback if no USB camera is plugged in.
   * **Virtual Analog Joystick**: HTML5 canvas touch joystick with smooth spring return, differential steering, and **protection against mobile scrolling & long-press right-clicks**.
   * **D-Pad & Keyboard**: Directional buttons with hold-to-drive and full WASD / Arrow keys.
   * **Speed Gears**: 30% (Crawl), 60% (Cruising), 90% (Turbo), and variable slider.
   * **Gamepad API**: Native support for Xbox / PlayStation / USB controllers.
   * **Failsafe Watchdog**: Automatic motor cutoff within 500ms if the browser disconnects.

4. **Safety & Autonomy Modes**:
   * **Assisted Mode (Default)**: Ultrasonic collision avoidance stops motors if obstacles are within 15 cm.
   * **Manual Override Toggle**: Allows 100% direct manual drive ignoring ultrasonic safety stops.
   * **Sensor Toggle**: Disables ultrasonic polling on demand.

5. **Networking Autonomy (AP Hotspot ⟷ Wi-Fi STA Fallback)**:
   * Automatic AP Hotspot creation (`SAM-Rover-Setup`, `192.168.4.1`) on first boot or when saved Wi-Fi is out of range.
   * External USB Wi-Fi adapter auto-detection (`wlan1` / External Dongle).
   * Web UI Wi-Fi scanner and network connection manager.

6. **Auto-Mock / Simulation Engine**:
   * Automatically detects if running on a PC/Laptop vs Raspberry Pi. On non-Pi systems, full simulation runs with realistic mock sensors, motors, and HUD video frames.

---

## 📁 Repository Structure

```
raspberry/
├── config.yaml                    # Central configuration (pins, limits, timeouts)
├── requirements.txt               # Dependencies
├── samsdk/                        # SAM Python SDK
│   ├── __init__.py                # Exposes SamRover
│   └── client.py                  # High-level API (forward, turn, distances, leds)
├── core/
│   ├── config.py                  # YAML configuration loader & validator
│   ├── hardware_manager.py        # Dynamic lease manager, watchdog, & safety supervisor
│   └── hal/                       # Hardware Abstraction Layer
│       ├── base.py                # Abstract base device
│       ├── motors.py              # L298N differential drive & PWM
│       ├── ultrasonic.py          # 4-channel HC-SR04 reader with timeout isolation
│       ├── leds.py                # 4 directional indicator LEDs
│       ├── camera.py              # USB webcam auto-detection & synthetic fallback
│       └── network.py             # NetworkManager inspector (wlan0, wlan1)
├── server/
│   ├── app.py                     # FastAPI application entry point
│   ├── routes/
│   │   ├── video.py               # MJPEG stream endpoint
│   │   ├── teleop.py              # WebSocket teleop & telemetry
│   │   ├── hardware.py            # Hardware lease & actuator REST API
│   │   └── network.py             # Wi-Fi scanner & interface API
│   ├── static/                    # Cyber-themed CSS and JavaScript controls
│   └── templates/                 # HTML5 Dashboard
├── examples/                      # Student demonstration scripts
│   ├── test_leds.py
│   ├── test_motors.py
│   ├── test_ultrasonic.py
│   └── student_demo.py            # Autonomous obstacle avoidance algorithm
└── scripts/
    ├── install_services.sh        # One-step systemd installer for auto-boot
    ├── sam.service                # Systemd service definition
    └── wifi_fallback.sh           # NetworkManager AP/STA auto-failover script
```

---

## 🚀 Quick Start

### 1. Running the Web Control Server
```bash
python -m uvicorn server.app:app --host 0.0.0.0 --port 8000
```
Open your browser at `http://<pi-ip>:8000` or `http://localhost:8000`.

### 2. Using the SAM Python SDK in Custom Scripts
Students can control the rover with simple Python scripts:

```python
from samsdk import SamRover

with SamRover() as rover:
    # Read 4-directional ultrasonic distances
    distances = rover.get_distances()
    print("Front distance:", distances['front'], "cm")

    # Turn on headlights / indicators
    rover.set_led("front", True)

    # Drive forward at 50% speed
    rover.forward(speed=50)

    # Differential drive: drive(linear, angular)
    rover.drive(linear=40, angular=-20)

    # Stop all motion
    rover.stop()
# Hardware pins are automatically released on exit!
```

---

## 🔌 Hardware Pin Mapping (Customizable in `config.yaml`)

| Subsystem | Signal | Raspberry Pi Pin (BCM) | Physical Pin |
| :--- | :--- | :--- | :--- |
| **Left Motor** | ENA (PWM), IN1, IN2 | GPIO 12, 5, 6 | Pins 32, 29, 31 |
| **Right Motor** | ENB (PWM), IN3, IN4 | GPIO 13, 19, 26 | Pins 33, 35, 37 |
| **Front Ultrasonic** | TRIG, ECHO (via divider) | GPIO 23, 24 | Pins 16, 18 |
| **Rear Ultrasonic** | TRIG, ECHO (via divider) | GPIO 27, 22 | Pins 13, 15 |
| **Left Ultrasonic** | TRIG, ECHO (via divider) | GPIO 17, 18 | Pins 11, 12 |
| **Right Ultrasonic** | TRIG, ECHO (via divider) | GPIO 25, 8 | Pins 22, 24 |
| **Directional LEDs** | Front, Rear, Left, Right | GPIO 4, 14, 15, 16 | Pins 7, 8, 10, 36 |
| **IMU (I2C)** | SDA, SCL | GPIO 2, 3 | Pins 3, 5 |
| **Camera** | USB 2.0 / 3.0 | `/dev/video0` | USB Port |

---

## 🛠️ Raspberry Pi Deployment (Ubuntu)

Run the installer with root privileges on the Pi:
```bash
sudo bash scripts/install_services.sh
```
This automatically:
1. Installs system packages and Python dependencies.
2. Installs and starts the `sam.service` systemd service for 24/7 auto-boot.
3. Sets up `wifi_fallback.sh` to automatically host the `SAM-Rover-Setup` Hotspot if disconnected.