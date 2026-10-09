# SAM Rover — Comprehensive User & Operator Field Manual

**Document Version:** 4.2 (Production Stable)  
**Target Audience:** Field Operators, Robotics Students, Lab Technicians, Competition Drivers  
**System Architecture:** Ubuntu/Debian Linux on Raspberry Pi • Hardware-Accurate `lgpio` HAL • FastAPI Teleoperation Server  
**Web Dashboard URL:** `http://<rover-ip>:8000` (or `http://10.42.0.1:8000` in Hotspot Mode)  

---

## 1. Executive Overview & System Specifications

The **SAM (Smart Autonomous Mobile) Rover** is a versatile differential-drive robotics platform engineered for remote teleoperation, real-time computer vision, ultrasonic spatial awareness, and autonomous obstacle mitigation. Built on a modular hardware abstraction layer (HAL) utilizing the Linux kernel GPIO character device interface (`lgpio`), the rover features multi-client arbitration, sub-20ms WebSocket telemetry, dual-layer PWM motor control, and comprehensive failsafe layers.

```
                      +---------------------------------------+
                      |   REMOTE OPERATOR DASHBOARD (BROWSER) |
                      |    Laptop / Tablet / Smartphone       |
                      +-------------------+-------------------+
                                          | WebSocket & REST
                                          | (Port 8000)
                                          v
+-----------------------------------------------------------------------------------+
| SAM ROVER COMPUTATIONAL CORE (Raspberry Pi 4 / Ubuntu Linux)                      |
|                                                                                   |
|  +--------------------+   +-----------------------+   +------------------------+  |
|  | Hardware Manager   |-->| Teleoperation Engine  |-->| Multi-Client Lease     |  |
|  | - Slew rate limit  |   | - 60 FPS motor updates|   | - Driver vs Observer   |  |
|  | - IMU heading hold |   | - Real-time telemetry |   | - Heartbeat watchdog   |  |
|  +---------+----------+   +-----------------------+   +------------------------+  |
|            |                                                                      |
|            +-------------------+---------------------+                            |
|                                |                     |                            |
|                                v                     v                            |
|                     +--------------------+ +--------------------+                 |
|                     | Unified lgpio HAL  | | OpenCV Video Pipe  |                 |
|                     +---------+----------+ +---------+----------+                 |
+-------------------------------|----------------------|----------------------------+
                                |                      |
        +-----------------------+-------------------+  |
        |                       |                   |  |
        v                       v                   v  v
+----------------+      +----------------+      +----------------+
| L298N DRIVER   |      | HC-SR04 SONAR  |      | MPU-6050 IMU   |
| 2x 60 RPM DC   |      | Front/Rear/    |      | I2C (0x68)     |
| Metal Gearbox  |      | Left/Right     |      | Pitch & Roll   |
+----------------+      +----------------+      +----------------+
```

### 1.1 Technical & Operational Specifications

| Parameter | Specification | Operational Notes |
| :--- | :--- | :--- |
| **Compute Platform** | Raspberry Pi 4 Model B (2GB/4GB/8GB) | Pi 3B+ supported with scaled camera FPS |
| **Drive Architecture** | 2-Wheel Differential Drive + Dual Ball Casters | Zero-radius in-place pivot turning capability |
| **Motor Spec** | 2x DC Brushed Motors with 60 RPM Metal Gearboxes | Tuned for indoor precision and high-torque outdoor climb |
| **H-Bridge Driver** | L298N Dual Full-Bridge Driver with dual PWM inputs | PWM Carrier Frequency: 100 Hz (`lgpio` hardware-timed) |
| **Vision Sensor** | USB UVC HD Webcam (720p / 1080p compatible) | Software MJPEG encoding throttled on-demand |
| **Proximity Sensing** | 4x HC-SR04 Ultrasonic Sonar Sensors | Coverage: Front, Rear, Left, Right (2 cm – 300 cm) |
| **Attitude Sensor** | MPU-6050 6-Axis Accelerometer + Gyroscope | I2C Bus 1 (`0x68`) with Complementary Filter |
| **Signals & Alerts** | 4x Directional High-Lumen LEDs + Active 5V Buzzer | Front, Rear, Left, Right illumination & Horn chirp |
| **Logic Power Rail** | 5.0V DC @ 3.0A via USB-C (Power Bank or Buck Regulator) | Monitored by Pi PMIC undervoltage supervisor |
| **Motor Power Rail** | 7.4V (2S LiPo) to 12.0V DC (3S LiPo / Battery Pack) | Isolated ground commoned with Pi ground plane |
| **Telemetry Rate** | 10 Hz WebSocket Stream + 60 FPS Optimistic UI | Typical round-trip network latency: 6 ms – 18 ms |
| **Network Interfaces** | 2.4 GHz / 5.0 GHz 802.11ac Wi-Fi + 1000M Ethernet | Supports Infrastructure Station Mode & AP Hotspot |

---

## 2. Quick Start Guide (Zero to Driving in 60 Seconds)

Follow this step-by-step checklist to deploy and operate the rover immediately:

```
[ Step 1: Power On ]  --->  [ Step 2: Connect Wi-Fi ]  --->  [ Step 3: Open Browser ]
  Batteries Connected         Rover IP or Hotspot            http://<ip>:8000
         |                                                           |
         v                                                           v
[ Step 6: Drive! ]    <---  [ Step 5: Select Gear ]   <---  [ Step 4: Claim Lease ]
  WASD / Joystick /           25%, 50%, 75%, 100%            Click Amber "Claim"
  Keyboard Controller                                         Status: DRIVER (YOU)
```

1. **Verify Power Isolation**: Ensure the logic power switch (Raspberry Pi) and the motor battery switch are both toggled **ON**. Observe steady red power LEDs on the Pi and the red indicator LED on the L298N driver board.
2. **System Boot**: Allow **25–30 seconds** for Ubuntu Linux and the `sam.service` systemd daemon to initialize. The directional LEDs will flash once upon successful hardware claim initialization.
3. **Connect Your Device**:
   - If on lab/office Wi-Fi: Ensure your laptop, tablet, or phone is connected to the same local wireless router.
   - If in the field: Connect to the rover's standalone Wi-Fi hotspot: `SAM_ROVER_WIFI` (Password: `raspberry`).
4. **Launch Dashboard**: Open Google Chrome, Mozilla Firefox, Apple Safari, or Microsoft Edge, and enter:
   ```
   http://<rover-ip>:8000
   ```
   *(e.g., `http://192.168.0.144:8000` or `http://10.42.0.1:8000`)*
5. **Acquire Hardware Lease**: In the top navigation bar, locate the amber button labeled **`Claim`** (showing an unlocked padlock). Click it once. The button transforms to a glowing green badge: **`Release (DRIVER)`**.
6. **Take Control**: Press the **`W`** key or push the on-screen virtual joystick forward. The motors will smoothly spin and drive the rover forward!

---

## 3. Wi-Fi & Hotspot Networking Guide

The rover utilizes Linux `NetworkManager` (`nmcli`) for deterministic wireless management. It supports two operational topologies:

```
TOPOLOGY A: Infrastructure Station Mode             TOPOLOGY B: Autonomous Field Hotspot Mode
(Lab, Classroom, Home Network)                      (Outdoor, Competition Arena, Field Trials)

   +-------------------+                               +-------------------------------------+
   | Local WiFi Router |                               | SAM ROVER (Acts as Access Point)   |
   | (e.g. 192.168.0.1)|                               | SSID: SAM_ROVER_WIFI               |
   +---------+---------+                               | IP:   10.42.0.1                     |
             |                                         +------------------+------------------+
     +-------+-------+                                                    |
     |               |                                                    | Direct 2.4GHz
     v               v                                                    v Wi-Fi Link
+----------+   +----------+                                    +---------------------+
| SAM Rover|   | Operator |                                    | Operator Tablet /   |
| .0.144   |   | Laptop   |                                    | Phone / Laptop      |
+----------+   +----------+                                    +---------------------+
```

### 3.1 Mode A: Connecting to Infrastructure Wi-Fi (Lab / Office Router)

When operating within range of a wireless access point, connect the rover to the local network so any device on the network can access the dashboard.

#### Method 1: Using the Web Dashboard Wi-Fi Modal
1. In the top navigation bar, click the **Wi-Fi Icon** button (located between Snapshot and STOP).
2. The **Wi-Fi & Network Manager** dialog will slide open.
3. Review the live status showing your current connection, signal strength (RSSI), and IP.
4. Under **Scan Nearby Networks**, click **`Scan Networks`**.
5. Select your network SSID, enter the WPA2/WPA3 password, and click **`Connect`**.
6. The rover connects within 5–8 seconds and updates its IP address display.

#### Method 2: Via SSH Command Line (`nmcli`)
If configuring headless via serial console or wired Ethernet:
```bash
# 1. Scan available 2.4 GHz and 5.0 GHz networks
sudo nmcli device wifi list

# 2. Connect to the target SSID
sudo nmcli device wifi connect "Your_Lab_WiFi" password "Your_WiFi_Password"

# 3. Retrieve the assigned DHCP IPv4 address
hostname -I
```

---

### 3.2 Mode B: Standalone Autonomous Hotspot Mode (Field Operations)

When operating outdoors, in industrial facilities, or in robot combat arenas where no external Wi-Fi network exists, configure the Raspberry Pi as a direct Wi-Fi Access Point (Hotspot).

```bash
# 1. Start the standalone rover access point
sudo nmcli device wifi hotspot ifname wlan0 ssid "SAM_ROVER_WIFI" password "raspberry"

# 2. Confirm the hotspot interface is active (IP is 10.42.0.1 by default)
ip -br a show wlan0
```

#### How to Operate in Hotspot Mode:
1. On your operator laptop, iPad, or smartphone, open **Wi-Fi Settings**.
2. Connect to network: **`SAM_ROVER_WIFI`**
3. Enter Password: **`raspberry`**
4. Open your web browser and navigate directly to:
   ```
   http://10.42.0.1:8000
   ```
5. Full teleoperation, HD video streaming, and sensor telemetry will function with zero external internet dependencies!

#### Switching Back to Infrastructure Wi-Fi:
```bash
# Deactivate the hotspot connection profile
sudo nmcli connection down Hotspot

# Reactivate your primary local Wi-Fi connection
sudo nmcli connection up "Your_Lab_WiFi"
```

---

### 3.3 Multi-Rover Fleet IP Addressing

When operating multiple rovers simultaneously in the same environment, ensure each rover possesses a unique hostname and static or reserved DHCP lease:

| Rover Identifier | Hostname | Default Static/DHCP IP | SSH Login | System Service |
| :--- | :--- | :--- | :--- | :--- |
| **Rover Unit 1 (SAM-Alpha)** | `sam` | `192.168.0.100` | `ssh sam@192.168.0.100` | `sam.service` |
| **Rover Unit 2 (SAM-Beta)** | `sam2` | `192.168.0.144` | `ssh sam2@192.168.0.144` | `sam.service` |
| **Rover Unit 3 (SAM-Gamma)** | `sam3` | `192.168.0.187` | `ssh sam3@192.168.0.187` | `sam.service` |

---

## 4. Web Dashboard Interface & Teleoperation Guide

The dashboard is designed for high-stress teleoperation with zero latency, high-contrast HUD optics, and touch-optimized controls.

```
+----------------------------------------------------------------------------------------------------+
| [o] LIVE  | RTT: 12ms | ACTION: STOPPED | CPU: 48°C | [Claim/Release] | [Camera] | [WiFi] | [ STOP ]   |
+---------------------------------------------------+------------------------------------------------+
| LIVE CAMERA VIEWPORT & HUD                        | TELEOPERATION CONTROL DECK                     |
|                                                   |                                                |
|  [MODE: ASSISTED]                    [GEAR: 60%]  |  [ D-PAD CONTROLLER ]    [ JOYSTICK MODE ]     |
|                                                   |                                                |
|                      +                            |                    [ FORWARD ]                 |
|                                                   |            [ LEFT ]   [ STOP ]   [ RIGHT ]     |
|  [MOTORS: L:0% R:0%]              [HUD: READY]    |                   [ REVERSE ]                  |
|                                                   |                                                |
+---------------------------------------------------+------------------------------------------------+
| MISSION TELEMETRY CONSOLE                         | AUTHORITY & PERIPHERALS                        |
|                                                   |                                                |
|  LINK: STABLE   RATE: 10 Hz   LEASE: DRIVER       |  GEARS:  [25%]   [50%]   [75%]   [100%]        |
|  SONAR: F: 82cm  R: 120cm  L: 45cm  R: 62cm       |  STEERING TRIM:  [-20% <====[]====> +20%]      |
|  VITALS: CPU 12%  RAM 34%  PWR: OK  [REC LOG]     |  LIGHTS: [FRONT] [REAR] [LEFT] [RIGHT] [ALL]   |
|  RADAR: 2D Multi-Sector Obstacle Arc Cones        |  AUDIO:  [ HORN / BUZZER ]   [ TOUCH / KEYS ]   |
+---------------------------------------------------+------------------------------------------------+
```

### 4.1 Multi-Client Hardware Lease & Arbitration Engine

To prevent dangerous conflicting commands when multiple operators or observers open the rover's dashboard simultaneously, the platform utilizes a **Stateful Hardware Lease Manager**:

```
                  +--------------------------------+
                  |      STANDBY (UNCLAIMED)       |
                  |  Motors Locked • LEDs Inactive |
                  +---------------+----------------+
                                  |
                   Driver clicks  |  Driver clicks
                   "Claim" button |  "Release" button
                                  v
+------------------------+                 +------------------------+
|      DRIVER (YOU)      |                 |     OBSERVER MODE      |
| Full Command Authority |                 | Read-Only Telemetry    |
| Heartbeat Active 250ms |                 | Video Feed Streaming   |
| Watchdog Monitored     |                 | Control Inputs Gated   |
+------------------------+                 +------------------------+
            |                                           |
            | Driver disconnects / 180s idle            | Takes Control
            +------------------>+<----------------------+ (Preemption)
                                |
                                v
                  +--------------------------------+
                  |  HARDWARE AUTONOMOUS CUTOFF    |
                  |  All GPIOs Cleared to Low      |
                  +--------------------------------+
```

#### Lease States Explained:
1. **`STANDBY` (Amber Badge / Unlocked Padlock)**:
   - The rover is powered and streaming video, but all actuation outputs (PWM, Direction Pins, LEDs, Buzzer) are locked at zero.
   - Any operator can click **`Claim`** to gain control authority.
2. **`DRIVER` (Green Badge / Locked Padlock)**:
   - You possess exclusive driving authority.
   - Your browser transmits periodic keep-alive heartbeats every 250 ms.
   - If you close your browser tab or your wireless connection drops for $>1.5\text{ seconds}$, the server automatically halts the rover.
3. **`OBSERVER` (Purple Badge / Viewer Lock)**:
   - Another operator currently holds driving authority.
   - You can monitor the real-time camera feed, telemetry diagnostics, sonar distances, and system vitals, but your drive buttons, joystick, and light switches are safely disarmed.
   - If necessary, an authorized supervisor can click **`Take Control`** to preempt the lease.
4. **`RELEASE` (Graceful Surrender)**:
   - When finished driving, click **`Release`**.
   - This immediately disarms motor PWM, shuts off all LEDs, silences the buzzer, and returns the rover to `STANDBY` mode.

---

### 4.2 Control Modes & Input Methods

SAM supports three distinct, simultaneously active input modalities:

#### Modality 1: Desktop Keyboard Controls
The fastest and most tactile control method for laptop and desktop workstations:

| Key Binding | Direction / Action | Behavioral Description |
| :--- | :--- | :--- |
| **`W`** or **`↑`** | **Drive Forward** | Both motors spin forward at the configured gear speed limit. |
| **`S`** or **`↓`** | **Drive Reverse** | Both motors reverse symmetrically with red rear warning indication. |
| **`A`** or **`←`** | **Pivot Left (Spin)** | Left motor reverses, Right motor advances; spins on central axis. |
| **`D`** or **`→`** | **Pivot Right (Spin)** | Right motor reverses, Left motor advances; spins on central axis. |
| **`Spacebar`** | **Emergency Brake** | Instant 0-latency motor cutoff; halts all momentum immediately. |
| **`H`** | **Audio Horn** | Momentary sounding of the 5V active piezo buzzer chirp. |
| **`L`** | **Toggle Lights** | Toggles all 4 directional LEDs ON or OFF. |

*Safety Feature: If the browser window loses focus (Alt-Tab, window change), all active keys are cleared and the rover halts immediately.*

---

#### Modality 2: Touch-Optimized Directional D-Pad
For touchscreens, tablets, and mouse clicking:
- Uses **Pointer Capture API** (`pointerdown`, `pointerup`, `pointercancel`) so the button remains engaged even if your finger slides slightly off the button surface.
- Features individual buttons for **Forward**, **Backward**, **Left Pivot**, **Right Pivot**, and **Center Stop**.

---

#### Modality 3: Proportional Virtual Analog Joystick
For smooth omnidirectional steering with nuanced velocity authority:
- Click the **`Joystick`** tab above the control zone.
- Touch or drag the glowing cyan joystick handle:
  - **Vertical Displacement ($Y$-axis)**: Proportional forward/reverse throttle ($0\%$ to $100\%$).
  - **Horizontal Displacement ($X$-axis)**: Proportional angular steering with differential curve blending.
- **Dynamic Cybernetic Tether**: A visual beam anchors the handle to the base ring, providing immediate optical feedback of the deflection vector.
- **Return-to-Center Failsafe**: Releasing your finger snaps the joystick to neutral $(0, 0)$ and commands an instantaneous zero-velocity motor stop.

---

### 4.3 Speed Gears (Authority Selector)

The authority selector scales the maximum duty cycle commanded to the motor H-bridges. Choose gears to match your operational domain:

```
[ 25% CRAWL ] ----------> [ 50% STANDARD ] ---------> [ 75% PATROL ] ---------> [ 100% SPRINT ]
Precision Docking         Indoor Cruising             Outdoor Terrain           High-Torque Climb
Trench & Ramp Maneuver    Classroom Testing           Paved Pathways            60 RPM Full Velocity
```

- **`25%` (Crawl Mode)**: Best for tight clearance, precision alignment, camera close-ups, and novice training.
- **`50%` (Standard Mode)**: Recommended default for indoor laboratories, classroom obstacle courses, and smooth tile floors.
- **`75%` (Patrol Mode)**: For rapid transit across large rooms, hallways, and outdoor sidewalks.
- **`100%` (Sprint Mode)**: Delivers full 60 RPM wheel rotation and maximum H-bridge torque for climbing inclines and traversing low-pile carpet or rough terrain.

---

### 4.4 Software Steering Trim Calibration

Dual brushed DC motors inevitably exhibit slight mechanical RPM variations due to manufacturing tolerances and gearbox friction.
- Located below the speed selector is the **`Steering Trim Slider`** (range: `-20%` to `+20%`).
- If your rover gently veers **Right** when driving straight, adjust the slider toward **Left (`-`)**.
- If your rover gently veers **Left** when driving straight, adjust the slider toward **Right (`+`)**.
- The software trim offset is saved locally in browser `localStorage` and persists across sessions.

---

### 4.5 Directional LED Array & Piezo Audio Signaling

The rover is equipped with four bright 5mm LEDs mapped to individual GPIO output pins:
- **`Front LED`**: Acts as forward headlights for low-light camera operation.
- **`Rear LED`**: Acts as red reversing and braking tail-lights.
- **`Left / Right LEDs`**: Signal pivot turns and identify vehicle orientation in the dark.
- **`All LEDs` Button**: Toggles all four illumination points simultaneously.
- **`Buzzer` Button**: Emits an audible 2.8 kHz chirp for pedestrian warning, mission start signals, and sonar obstacle alerts.

---

## 5. Safety Systems & Autonomous Assistance

SAM features multiple hardware-enforced and software-enforced safety supervisors that operate continuously in the background:

```
                   +-------------------------------------------------+
                   |           DISTANCE TO FRONT OBSTACLE            |
                   +-------------------------------------------------+
                                            |
         +----------------------------------+----------------------------------+
         |                                  |                                  |
         v                                  v                                  v
+-----------------------+        +-----------------------+        +-----------------------+
|     CLEAR ZONE        |        |     WARNING ZONE      |        |     CRITICAL ZONE     |
|   Distance > 35 cm    |        |   15 cm < d <= 35 cm  |        |    Distance <= 15 cm  |
+-----------------------+        +-----------------------+        +-----------------------+
| • Full gear authority |        | • Proportional speed  |        | • Instant Motor CUT   |
| • HUD Status: READY   |        |   reduction cap       |        | • Forward Drive LOCK  |
| • Green Sonar Arc     |        | • HUD Status: CAUTION |        | • HUD: CRITICAL STOP  |
|                       |        | • Amber Sonar Arc     |        | • Red Flashing Arc    |
|                       |        |                       |        | • Reverse/Pivot OK    |
+-----------------------+        +-----------------------+        +-----------------------+
```

### 5.1 3-Tier Active Obstacle Avoidance

The front ultrasonic sonar array continuously measures distance at 10 Hz. If an obstacle is detected in the direct travel path:
1. **Clear Zone ($>35\text{ cm}$)**:
   - Zero throttle intervention. The operator commands uninhibited speed.
2. **Warning Deceleration Zone ($15\text{ cm} < d \le 35\text{ cm}$)**:
   - Proportional speed scaling: The system dynamically caps maximum forward velocity:
     $$\text{Speed Cap} = \text{Speed Limit} \times \left(\frac{d - 15}{20}\right)$$
   - Prevents hard collisions by gently slowing the rover as it approaches an obstacle.
   - The HUD warning box shifts to **amber (`CAUTION`)** and the sonar radar cone lights up yellow.
3. **Critical Braking Zone ($d \le 15\text{ cm}$)**:
   - **Forward Drive Lockout**: Forward commands (`W`, Forward Joystick, `RT`) are instantly clamped to `0%`.
   - The H-bridge cuts power to prevent chassis impact.
   - The HUD flashes **red (`OBSTACLE CRITICAL STOP`)**.
   - **Escape Capability**: The operator is still permitted to command **Reverse (`S`)** or **Pivot Turns (`A`/`D`)** to steer cleanly away from the obstacle!

---

### 5.2 Closed-Loop IMU Straight-Line Heading-Hold

When driving over long distances, small floor imperfections or motor variations can cause heading drift.
- The onboard **MPU-6050 IMU** executes a high-speed complementary filter on Gyroscope $Z$-axis (yaw rate).
- When the operator commands pure forward motion ($\text{Angular} = 0$), the hardware manager activates closed-loop micro-trimming:
  - If unexpected yaw rotation is sensed, wheel velocities are dynamically trimmed by $\pm 2\text{–}5\%$ to lock the heading on a laser-straight trajectory.

---

### 5.3 Communication Loss & Watchdog Cutoff

- If the browser tab is accidentally closed, Wi-Fi signal is lost, or the network drops for more than **1.5 seconds**, the server's background watchdog terminates all PWM outputs within **20 milliseconds**.
- The rover will never run away uncontrollably if communication fails.

---

### 5.4 Automatic Idle Lease Release (180s Timer)

- If a driver claims the rover but performs zero driving or toggle actions for **3 minutes (180 seconds)**, the lease is automatically surrendered back to `STANDBY`.
- This ensures that in educational or laboratory environments, an idle workstation does not lock out other students.

---

## 6. Mission Telemetry & Blackbox Flight Recording

The desktop dashboard features a built-in **Blackbox Mission Flight Logger** for post-drive diagnostics, autonomy research, and performance auditing.

```
+-----------------------------------------------------------------------------------------+
| BLACKBOX TELEMETRY LOG BUFFER                                                           |
|                                                                                         |
| [REC] Button clicked ---> Real-time packet buffering @ 10 Hz ---> [EXPORT] CSV Download |
+-----------------------------------------------------------------------------------------+
```

### 6.1 Recording a Mission Telemetry Session
1. In the **Pi Vitals & Logger** card, click the red **`REC`** button.
2. The button illuminates and begins logging every incoming 100ms telemetry packet into high-speed browser memory.
3. Perform your driving mission, obstacle navigation trial, or battery endurance test.
4. When finished, click **`REC`** again to stop recording.
5. Click **`EXPORT`** to instantly generate and download a timestamped CSV file:
   `sam_flight_log_YYYY-MM-DD_HH-mm-ss.csv`

### 6.2 Telemetry CSV Schema Reference

| Column Header | Data Type | Description |
| :--- | :--- | :--- |
| `timestamp` | ISO-8601 String | High-precision mission clock timestamp |
| `action` | String | Commanded state (`FORWARD`, `REVERSE`, `PIVOT LEFT`, `PIVOT RIGHT`, `STOPPED`) |
| `cmd_linear` | Float ($\pm 100$) | Commanded forward/reverse linear velocity vector |
| `cmd_angular` | Float ($\pm 100$) | Commanded angular steering vector |
| `tx_packets` | Integer | Cumulative WebSocket command frames transmitted |
| `rx_packets` | Integer | Cumulative telemetry frames received from rover |
| `motor_left` | Integer ($\pm 100$) | Actual PWM duty cycle applied to Left Motor H-Bridge |
| `motor_right` | Integer ($\pm 100$) | Actual PWM duty cycle applied to Right Motor H-Bridge |
| `sonar_front` | Float (cm) | Real-time front ultrasonic obstacle clearance |
| `sonar_rear` | Float (cm) | Real-time rear ultrasonic clearance |
| `sonar_left` | Float (cm) | Real-time left ultrasonic clearance |
| `sonar_right` | Float (cm) | Real-time right ultrasonic clearance |
| `cpu_temp` | Float (°C) | Raspberry Pi SoC core temperature |

---

## 7. Operational Troubleshooting Matrix

Use this symptom-cause-action table to diagnose and resolve any field issues:

| Problem / Symptom | Probable Root Cause | Verification & Step-by-Step Resolution |
| :--- | :--- | :--- |
| **Cannot open `http://<ip>:8000` in browser** | 1. Rover powered off.<br>2. Device on different Wi-Fi.<br>3. `sam.service` daemon crashed. | 1. Confirm Pi red power LED is solid.<br>2. Confirm client laptop is on the same Wi-Fi SSID.<br>3. SSH into rover and run `sudo systemctl status sam`.<br>4. Restart with `sudo systemctl restart sam`. |
| **"Hardware unclaimed" warning appears on drive** | Rover is in `STANDBY` mode. Actuation outputs are hardware-locked. | Click the amber **`Claim`** button in the top navigation bar. Confirm badge reads **`Release (DRIVER)`**. |
| **"Observer mode: Rover controlled by..." warning** | Another workstation has claimed the hardware lease. | Ask the active operator to click **`Release`**, or click **`Take Control`** to exercise administrative override. |
| **Motors hum/buzz but wheels do not rotate** | 1. Motor battery discharged ($<7.0\text{V}$).<br>2. Speed gear set too low for friction.<br>3. L298N 5V regulator jumper missing. | 1. Measure motor battery pack with a multimeter; recharge if $<7.4\text{V}$.<br>2. Switch gear selector to **`50%`** or **`100%`**.<br>3. Verify L298N onboard 5V regulator jumper is installed. |
| **Rover drives backward when pressing `W`** | Motor wiring polarity inverted at H-bridge screw terminals. | Edit `/home/sam/sam/config.yaml`. Set `invert_left: true` or `invert_right: true`, then run `sudo systemctl restart sam`. |
| **Rover pivots when commanded to drive straight** | Mechanical gearbox variance or wheel axle slippage. | Adjust the **`Steering Trim Slider`** on the dashboard. Inspect wheel coupler set-screws for tightness. |
| **Front obstacle stop triggers in open space** | Ultrasonic sensor echo pin receiving electrical noise or loose GND wire. | 1. Inspect HC-SR04 header wiring.<br>2. Ensure sensor face is perpendicular to ground and not pointing at floor carpet ($>5\text{ cm}$ ground clearance). |
| **Camera stream displays static test card HUD** | USB webcam unplugged or unmounted by kernel. | 1. Unplug and replug the USB webcam into a blue USB 3.0 port.<br>2. Run `ls -l /dev/video*` to verify detection.<br>3. Restart service: `sudo systemctl restart sam`. |
| **Latency indicator turns RED ($>50\text{ ms}$)** | Wireless interference or weak Wi-Fi signal. | Move rover closer to Wi-Fi access point or switch to 5.0 GHz band. In outdoor settings, activate Autonomous Hotspot mode. |
| **"LOW VOLT" banner appears in navbar** | Raspberry Pi USB-C power supply dropping below 4.63V under CPU/motor load. | Replace thin USB-C cable with a high-current 18 AWG cable or use a dedicated 5V 3A DC-DC buck converter. |

---

## 8. Preventive Maintenance & Battery Management

Adhering to these preventive care guidelines ensures hardware longevity and operational safety:

```
+--------------------------------------------------------------------------------------------------+
| BATTERY OPERATIONAL VOLTAGE BOUNDARIES (2S LiPo / 7.4V Nominal)                                 |
|                                                                                                  |
| [ 6.0V Critical Cutoff ]  <--  [ 7.0V Recharge Warning ]  <--  [ 7.4V Nominal ]  <-- [ 8.4V Peak ]
| Hard Stop: Disconnect Now      Low Power Warning on HUD         Normal Range          Full Charge |
+--------------------------------------------------------------------------------------------------+
```

### 8.1 LiPo / Li-Ion Battery Safety Protocols
- **Never Over-Discharge**: Discontinue motor driving immediately if the 2S battery pack drops below **`7.0V`** (3.5V per cell). Discharging below **`6.0V`** causes irreversible chemical damage to lithium cells.
- **Dedicated Power Isolation**: Never attempt to power the L298N motor driver directly from the Raspberry Pi's 5V GPIO header pins. Inrush motor currents will cause brownout resets and can destroy the Pi's PMIC regulator.
- **Charging Protocol**: Always charge lithium battery packs inside a fire-retardant LiPo safety bag using an intelligent balance charger.

### 8.2 Mechanical & Thermal Care
- **Gearbox Fasteners**: Check motor mount M3 screws periodically. High-frequency floor vibrations can loosen motor brackets over time.
- **Wheel Tread Cleaning**: Clear hair, carpet fibers, and dust from drive wheel hubs and caster ball bearings every 10 operating hours.
- **Raspberry Pi Thermal Headroom**: Ensure the Raspberry Pi's aluminum heatsinks or cooling fan remain unobstructed. The dashboard telemetry bar will highlight **amber (`WARM`)** at $\ge 70^\circ\text{C}$ and **red (`HOT`)** at $\ge 75^\circ\text{C}$.

---

## 9. Quick Command Cheat-Sheet (Terminal Reference)

| Task | Shell Command |
| :--- | :--- |
| **Check Rover Service Status** | `sudo systemctl status sam.service` |
| **Restart Rover Software** | `sudo systemctl restart sam.service` |
| **Stop Rover Software** | `sudo systemctl stop sam.service` |
| **View Live System Logs** | `sudo journalctl -u sam.service -f -n 50` |
| **Find Rover IP Addresses** | `hostname -I` or `ip -br a` |
| **Scan Nearby Wi-Fi** | `sudo nmcli device wifi list` |
| **Connect to Wi-Fi** | `sudo nmcli device wifi connect "SSID" password "PASS"` |
| **Start Field Hotspot** | `sudo nmcli device wifi hotspot ifname wlan0 ssid "SAM_ROVER_WIFI" password "raspberry"` |
| **Check Pi Core Temperature** | `vcgencmd measure_temp` |
| **Check Pi Power Throttling** | `vcgencmd get_throttled` *(0x0 = healthy power)* |
| **Verify I2C IMU Detection** | `i2cdetect -y 1` *(Address 0x68 should appear)* |
