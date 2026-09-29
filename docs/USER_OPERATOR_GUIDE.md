# SAM Rover — User & Operator Guide
**Target Audience:** Students, Roboticists, Field Operators, Lab Technicians  
**Web Dashboard Port:** `8000` (e.g., `http://<rover-ip>:8000`)

---

## 1. Quick Start Guide (In 60 Seconds)

1. **Power On**: Connect the battery pack or power supply to the Raspberry Pi and L298N motor driver. Wait ~25 seconds for the system to boot.
2. **Open Browser**: On your phone, tablet, or laptop connected to the same WiFi network, navigate to:
   ```
   http://<rover-ip>:8000
   ```
   *(e.g., `http://192.168.0.144:8000` or `http://192.168.0.187:8000`)*
3. **Claim Control**: Click the amber **`Claim`** button in the top navigation bar. The badge will flip to **`DRIVER (YOU)`** in glowing green.
4. **Drive**: Use **W, A, S, D** or the on-screen joystick to steer the rover!

---

## 2. WiFi & Hotspot Connectivity

The rover uses Linux `NetworkManager` (`nmcli`) for reliable wireless networking in both lab and field environments.

### Option A: Connecting Rover to an Existing WiFi (Lab / Home Router)

Connect a screen & keyboard, or SSH over Ethernet/existing connection:
```bash
# 1. Scan available 2.4GHz & 5GHz WiFi networks
sudo nmcli device wifi list

# 2. Connect to your WiFi network
sudo nmcli device wifi connect "Your_WiFi_SSID" password "Your_WiFi_Password"

# 3. Find the Rover's IP address
ip -br a show wlan0
# or
hostname -I
```
Once connected, the rover will automatically reconnect to this network every time it boots.

---

### Option B: Standalone Autonomous Hotspot Mode (Field Operations Without Router)

When operating outdoors or in an arena without an external WiFi router, configure the Raspberry Pi as a direct WiFi Access Point / Hotspot:

```bash
# 1. Create and start a WiFi hotspot from the rover
sudo nmcli device wifi hotspot ifname wlan0 ssid "SAM_ROVER_WIFI" password "raspberry"

# 2. Check the hotspot IP address (default is 10.42.0.1)
ip -br a show wlan0
```

**To connect:**
1. On your smartphone or laptop, open WiFi settings and connect to `SAM_ROVER_WIFI` (password: `raspberry`).
2. Open your web browser and navigate directly to:
   ```
   http://10.42.0.1:8000
   ```

**To switch back from Hotspot to normal WiFi:**
```bash
# Stop the hotspot and reconnect to your default WiFi network
sudo nmcli connection down Hotspot
sudo nmcli connection up "Your_WiFi_SSID"
```

---

## 3. Web Dashboard & Driving Controls

### 3.1 Operator Lease System (Multi-Client Arbitration)
To prevent accidental conflicting inputs when multiple users view the same rover:
- **STANDBY (Unclaimed)**: The rover is powered, but motor and LED outputs are hardware-locked. Any student can click **`Claim`** to become the active driver.
- **DRIVER (YOU)**: You have full control authority. Heartbeats refresh every 250ms.
- **OBSERVER**: Another user is currently driving. You can view the live HD camera feed, telemetry, and sonar radar, but control inputs are safely blocked.
- **RELEASE**: Click the **`Release`** button when finished. This immediately turns off LEDs, stops PWM, frees all GPIO pins, and allows other users to claim.

---

### 3.2 Control Inputs
- **Keyboard (Desktop / Laptop)**:
  - **`W` / `↑`**: Drive Forward
  - **`S` / `↓`**: Drive Reverse
  - **`A` / `←`**: Pivot Left
  - **`D` / `→`**: Pivot Right
  - **`Spacebar`**: Instant Emergency Brake
  - **`H`**: Audio Horn / Buzzer Chirp
  - **`L`**: Toggle Directional LEDs
- **Touch Virtual Joystick (Mobile / Tablet)**:
  - Drag the thumbstick on the lower-left for proportional omnidirectional steering.
- **Gamepad / Controller (Xbox / PlayStation / USB HID)**:
  - Connect via Bluetooth or USB. Auto-detected with HUD indicator:
    - **Steering**: Left Stick horizontal (`axes[0]`) with 1.4x exponential curve for precision.
    - **Dual Driving Modes**:
      - *RC / Racing Trigger Mode*: Right Trigger (`RT`) accelerates forward, Left Trigger (`LT`) reverses / brakes.
      - *Single-Stick Mode*: Left Stick vertical (`axes[1]`) provides proportional throttle if triggers are idle.
    - **Action Buttons**:
      - **`A` / Cross**: Audio Horn / Buzzer chirp (hold to sound).
      - **`X` / Square**: Toggle Directional Headlights / LEDs.
      - **`B` / Circle**: Instant Emergency Stop (E-Stop).
      - **`LB` / `RB` (Bumpers) or D-Pad Up/Down**: Shift speed gears on the fly (`25%` $\leftrightarrow$ `50%` $\leftrightarrow$ `75%` $\leftrightarrow$ `100%`).

---

### 3.3 Speed Gears (Authority Selector)
Select gears to match your operational environment:
- **`25%` (Crawl)**: Precision maneuvers, tight doorways, obstacle navigation.
- **`50%` (Standard)**: Indoor laboratory cruising.
- **`75%` (Patrol)**: Fast outdoor driving.
- **`100%` (Sprint)**: Full 60 RPM motor speed and maximum torque.

---

## 4. Safety & Assisted Autonomy Features

SAM is equipped with hardware-level safety layers that intervene automatically:

1. **Active Collision Avoidance**:
   - **Warning Zone (<35 cm)**: Proactively scales down motor speed proportionally to distance.
   - **Critical Zone (≤15 cm)**: Instantly halts forward drive while still permitting steering away or reversing.
2. **IMU Straight-Line Heading-Hold**:
   - Built-in complementary filter gyro assist trims wheel speed asymmetry so the rover drives in a true straight line without drifting.
3. **Teleop Watchdog**:
   - If the browser tab is closed or WiFi packets drop for more than 1.5 seconds while driving, the motors automatically stop.
4. **Idle Auto-Release (180s)**:
   - If no commands are sent for 3 minutes, the rover automatically releases its hardware lease so teammates can use it.

---

## 5. Troubleshooting Matrix

| Symptom | Probable Cause | Recommended Action |
|---|---|---|
| **Cannot open `http://<ip>:8000`** | Rover not on network or service down | Check IP via `hostname -I` or router admin. Verify service with `sudo systemctl status sam.service`. |
| **"Hardware unclaimed" warning on click** | Rover in STANDBY mode | Click the amber **`Claim`** button in the top navigation bar to take control. |
| **"Observer mode" message** | Another device has claimed the rover | Wait for the driver to click Release, or click **`Take Control`** to claim the lease. |
| **Motors buzz but do not spin** | Battery voltage low or speed gear too low | Check motor battery pack (minimum 7.4V / 2S LiPo). Switch speed gear to 50% or 100%. |
| **Rover drives backward on `W`** | Motor wiring polarity inverted | In [`config.yaml`](file:///c:/Users/Jbs/Downloads/sam/config.yaml), set `invert_left: true` or `invert_right: true` and restart the service. |
| **Camera feed shows test card HUD** | USB camera disconnected | Unplug and replug the USB webcam. Verify detection with `ls /dev/video*`. |
| **Ultrasonic sensor reads `--`** | Sensor wiring loose or out of range | Check 5V VCC and GND on HC-SR04. Ensure target surface is within 2cm to 300cm range. |
| **LEDs or Horn don't activate** | Hardware unclaimed or pin mismatch | Claim the rover first. Verify GPIO pin mapping in [`config.yaml`](file:///c:/Users/Jbs/Downloads/sam/config.yaml). |
