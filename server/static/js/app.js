/**
 * SAM Rover - Main Application & WebSocket Telemetry Manager
 * Supports:
 * - Live camera stream & pause toggle
 * - Motor master output toggle
 * - Ultrasonic sensor toggle
 * - Manual override toggle (color-highlighted)
 * - Compact ultrasonic proximity strip
 * - Speed presets below controls
 * - Gamepad & Touch Joystick
 */

document.addEventListener('DOMContentLoaded', () => {
  let ws = null;
  let heartbeatTimer = null;
  let controls = null;
  let joystick = null;
  let isHardwareLeased = false;

  // Client Session & Operator Lease Arbitration
  let clientId = localStorage.getItem('sam_client_id');
  if (!clientId) {
    clientId = 'user_' + Math.random().toString(36).substring(2, 8);
    localStorage.setItem('sam_client_id', clientId);
  }
  let currentOperatorId = null;
  let activeOperatorName = null;

  // Toggle states
  let motorsEnabled = true;
  let cameraEnabled = true;
  let sensorsEnabled = true;

  const connectionDot = document.getElementById('connection-dot');
  const leaseBadge = document.getElementById('lease-badge');
  const btnToggleLease = document.getElementById('btn-toggle-lease');
  const leaseBtnText = document.getElementById('lease-btn-text');
  const leaseIconWrap = document.getElementById('lease-icon-wrap');
  const hudWarningBox = document.getElementById('hud-warning-box');
  const hudWarningText = document.getElementById('hud-warning-text');
  const hudMotors = document.getElementById('hud-motors');
  const hudMode = document.getElementById('hud-mode');
  const cameraStreamImg = document.getElementById('camera-stream');
  const cameraPausedOverlay = document.getElementById('camera-paused-overlay');
  const cameraReconnectOverlay = document.getElementById('camera-reconnecting-overlay');

  let videoRetryTimer = null;
  let videoRetryDelay = 800;

  // Desktop Mission Telemetry Elements (Below Video Feed on Left)
  const telemActionBadge = document.getElementById('telem-action-badge');
  const telemActionText = document.getElementById('telem-action-text');
  const telemCmdLinear = document.getElementById('telem-cmd-linear');
  const telemCmdAngular = document.getElementById('telem-cmd-angular');
  const telemMotorsLr = document.getElementById('telem-motors-lr');
  const telemWsPill = document.getElementById('telem-ws-pill');
  const telemWsState = document.getElementById('telem-ws-state');
  const telemRtt = document.getElementById('telem-rtt');
  const telemRate = document.getElementById('telem-rate');
  const telemPackets = document.getElementById('telem-packets');
  const telemLeaseStatus = document.getElementById('telem-lease-status');
  const navRtt = document.getElementById('nav-rtt');
  const navRttBadge = document.getElementById('nav-rtt-badge');

  let txPackets = 0;
  let rxPackets = 0;
  let pingInterval = null;
  let frameCounter = 0;
  let lastRateTimestamp = performance.now();

  let lastLinearCmd = 0.0;
  let lastAngularCmd = 0.0;
  let currentAction = 'STOPPED';

  // Blackbox Flight Session Logger
  let isLogging = false;
  let logBuffer = [];

  const ICON_LOCKED = `<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>`;
  const ICON_UNLOCKED = `<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 9.9-1"></path></svg>`;

  // Prevent sticky mobile button glow / focus lock
  document.addEventListener('touchend', () => {
    if (document.activeElement && document.activeElement.blur) {
      document.activeElement.blur();
    }
  }, { passive: true });

  // Toggle pill elements (Supports both mobile header and desktop right-panel instances)
  const toggleMotorsBtns = document.querySelectorAll('.toggle-motors-btn');
  const toggleCameraBtns = document.querySelectorAll('.toggle-camera-btn');
  const toggleSensorsBtns = document.querySelectorAll('.toggle-sensors-btn');
  const toggleLedsBtns = document.querySelectorAll('.toggle-leds-btn');
  const toggleHornBtns = document.querySelectorAll('.toggle-horn-btn, #btn-horn');

  // --- WebSocket Connection ---
  function connectWebSocket() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/teleop`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      connectionDot.classList.remove('disconnected');
      connectionDot.classList.add('pulse');
      console.log('[SAM] WebSocket connected.');

      if (telemWsState) telemWsState.textContent = 'LIVE';
      if (telemWsPill) {
        telemWsPill.classList.remove('disconnected');
        telemWsPill.classList.add('connected');
      }

      // Immediately recover video feed if network reconnected after drop
      reloadVideoStream();

      // Immediately send first ping for instant RTT measurement
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping', t: performance.now() }));
      }

      // Start 250ms heartbeat
      clearInterval(heartbeatTimer);
      heartbeatTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'heartbeat', operator_id: clientId }));
        }
      }, 250);

      // Start 2000ms WebSocket latency (RTT) ping
      clearInterval(pingInterval);
      pingInterval = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping', t: performance.now() }));
        }
      }, 2000);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'telemetry') {
          rxPackets++;
          frameCounter++;
          const now = performance.now();
          const elapsed = (now - lastRateTimestamp) / 1000;
          if (elapsed >= 1.0) {
            const hz = Math.round(frameCounter / elapsed);
            if (telemRate) telemRate.textContent = `${hz} Hz`;
            frameCounter = 0;
            lastRateTimestamp = now;
          }
          if (telemPackets) telemPackets.textContent = `TX: ${txPackets} | RX: ${rxPackets}`;
          handleTelemetry(msg.data);
        } else if (msg.type === 'pong') {
          const rtt = Math.round(performance.now() - msg.t);
          const colorClass = (
            rtt < 40 ? 'val-green' :
            rtt < 100 ? 'val-cyan' :
            rtt < 200 ? 'val-amber' : 'val-red'
          );
          if (telemRtt) {
            telemRtt.textContent = `${rtt} ms`;
            telemRtt.className = `telem-val ${colorClass}`;
          }
          if (navRtt) {
            navRtt.textContent = `${rtt} ms`;
            if (navRttBadge) {
              const badgeClass = (
                rtt < 40 ? 'rtt-green' :
                rtt < 100 ? 'rtt-cyan' :
                rtt < 200 ? 'rtt-amber' : 'rtt-red'
              );
              navRttBadge.className = `nav-rtt-pill ${badgeClass}`;
            }
          }
        } else if (msg.type === 'warning') {
          showHUDWarning(msg.message, 'warning');
        } else if (msg.type === 'caution') {
          showHUDWarning(msg.message, 'caution');
        }
      } catch (e) {
        console.error('Error parsing WS message:', e);
      }
    };

    ws.onclose = () => {
      connectionDot.classList.remove('pulse');
      connectionDot.classList.add('disconnected');
      if (telemWsState) telemWsState.textContent = 'OFFLINE';
      if (telemWsPill) {
        telemWsPill.classList.remove('connected');
        telemWsPill.classList.add('disconnected');
      }
      if (telemRtt) {
        telemRtt.textContent = '-- ms';
        telemRtt.className = 'telem-val';
      }
      if (navRtt) {
        navRtt.textContent = '-- ms';
        if (navRttBadge) navRttBadge.className = 'nav-rtt-pill';
      }
      clearInterval(heartbeatTimer);
      clearInterval(pingInterval);
      setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = (err) => {
      console.error('[SAM] WebSocket error:', err);
    };
  }

  // --- Drive Sender ---
  function sendDriveCommand(linear, angular) {
    const lin = parseFloat(linear);
    const ang = parseFloat(angular);
    lastLinearCmd = lin;
    lastAngularCmd = ang;

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'drive',
        linear: lin,
        angular: ang,
        operator_id: clientId,
      }));
      txPackets++;
      if (telemPackets) telemPackets.textContent = `TX: ${txPackets} | RX: ${rxPackets}`;
    }

    // Resolve motion action for desktop telemetry
    let action = 'STOPPED';
    let badgeClass = 'idle';

    if (Math.abs(lin) < 0.04 && Math.abs(ang) < 0.04) {
      action = 'STOPPED';
      badgeClass = 'idle';
    } else if (lin > 0.04 && Math.abs(ang) <= 0.25) {
      action = 'FORWARD';
      badgeClass = 'moving';
    } else if (lin < -0.04 && Math.abs(ang) <= 0.25) {
      action = 'REVERSE';
      badgeClass = 'moving';
    } else if (ang > 0.25 && lin > 0.04) {
      action = 'CURVE RIGHT';
      badgeClass = 'turning';
    } else if (ang < -0.25 && lin > 0.04) {
      action = 'CURVE LEFT';
      badgeClass = 'turning';
    } else if (ang > 0.25 && lin < -0.04) {
      action = 'REV RIGHT';
      badgeClass = 'turning';
    } else if (ang < -0.25 && lin < -0.04) {
      action = 'REV LEFT';
      badgeClass = 'turning';
    } else if (ang > 0.25) {
      action = 'PIVOT RIGHT';
      badgeClass = 'turning';
    } else if (ang < -0.25) {
      action = 'PIVOT LEFT';
      badgeClass = 'turning';
    }

    if (telemActionBadge) {
      telemActionBadge.textContent = action;
      telemActionBadge.className = `telem-badge ${badgeClass}`;
    }
    if (telemActionText) telemActionText.textContent = action;
    if (telemCmdLinear) telemCmdLinear.textContent = `${(lin * 100).toFixed(0)}%`;
    if (telemCmdAngular) telemCmdAngular.textContent = `${(ang * 100).toFixed(0)}%`;
  }

  // --- Lease & Role UI Helper ---
  function updateLeaseUI() {
    const isMe = isHardwareLeased && (
      !currentOperatorId ||
      currentOperatorId === clientId ||
      currentOperatorId === 'driver' ||
      currentOperatorId === 'primary-operator'
    );

    if (!isHardwareLeased) {
      leaseBadge.textContent = 'STANDBY';
      leaseBadge.className = 'badge';
      btnToggleLease.className = 'btn btn-lease free';
      leaseBtnText.textContent = 'Claim';
      if (leaseIconWrap) leaseIconWrap.innerHTML = ICON_UNLOCKED;
    } else if (isMe) {
      leaseBadge.textContent = 'DRIVER (YOU)';
      leaseBadge.className = 'badge active';
      btnToggleLease.className = 'btn btn-lease claimed';
      leaseBtnText.textContent = 'Release';
      if (leaseIconWrap) leaseIconWrap.innerHTML = ICON_LOCKED;
    } else {
      leaseBadge.textContent = 'OBSERVER';
      leaseBadge.className = 'badge observer';
      btnToggleLease.className = 'btn btn-lease free';
      leaseBtnText.textContent = 'Take Control';
      if (leaseIconWrap) leaseIconWrap.innerHTML = ICON_UNLOCKED;
    }

    if (telemLeaseStatus) {
      telemLeaseStatus.textContent = isHardwareLeased ? (isMe ? 'CLAIMED (YOU)' : 'OBSERVER') : 'UNCLAIMED';
      telemLeaseStatus.className = `telem-val val-lease ${isHardwareLeased ? 'claimed' : 'unclaimed'}`;
    }
  }

  // --- Telemetry Visualizer ---
  function handleTelemetry(data) {
    // 1. Hardware Lease & Multi-Operator Role Status
    isHardwareLeased = !!data.hardware_leased;
    currentOperatorId = data.active_operator_id || null;
    activeOperatorName = data.active_operator_name || null;
    updateLeaseUI();

    // Proactive Vitals & Power Alerts (Top Navigation)
    const vitalsAlertPill = document.getElementById('vitals-alert-pill');
    const vitalsAlertLabel = document.getElementById('vitals-alert-label');
    if (vitalsAlertPill && vitalsAlertLabel && data.vitals) {
      if (data.vitals.undervoltage) {
        vitalsAlertPill.style.display = 'inline-flex';
        vitalsAlertPill.className = 'vitals-alert-pill';
        vitalsAlertLabel.textContent = 'LOW VOLT';
      } else if (data.vitals.cpu_temp && data.vitals.cpu_temp >= 75.0) {
        vitalsAlertPill.style.display = 'inline-flex';
        vitalsAlertPill.className = 'vitals-alert-pill caution';
        vitalsAlertLabel.textContent = `HOT ${Math.round(data.vitals.cpu_temp)}°C`;
      } else {
        vitalsAlertPill.style.display = 'none';
      }
    }

    // 2. Sync Toggle States
    motorsEnabled = data.motors_enabled !== undefined ? data.motors_enabled : motorsEnabled;
    cameraEnabled = data.camera_enabled !== undefined ? data.camera_enabled : cameraEnabled;
    sensorsEnabled = data.sensors_enabled !== undefined ? data.sensors_enabled : sensorsEnabled;

    toggleMotorsBtns.forEach(btn => btn.classList.toggle('active', motorsEnabled));
    toggleCameraBtns.forEach(btn => btn.classList.toggle('active', cameraEnabled));
    toggleSensorsBtns.forEach(btn => btn.classList.toggle('active', sensorsEnabled));

    if (cameraEnabled) {
      cameraPausedOverlay.classList.remove('show');
    } else {
      cameraPausedOverlay.classList.add('show');
    }

    // 3. Operating Mode HUD (Assisted with safety stop when sensors ON, Manual when OFF)
    if (!sensorsEnabled) {
      hudMode.textContent = 'MANUAL';
      hudMode.style.color = 'var(--accent-amber)';
    } else {
      hudMode.textContent = 'ASSISTED';
      hudMode.style.color = 'var(--accent-cyan)';
    }

    // 4. Motor Readouts
    if (data.motors) {
      const ls = Math.round(data.motors.left_speed || 0);
      const rs = Math.round(data.motors.right_speed || 0);
      hudMotors.textContent = `L:${ls}% R:${rs}%`;
      if (telemMotorsLr) telemMotorsLr.textContent = `L: ${ls}% | R: ${rs}%`;
    }

    if (telemLeaseStatus) {
      telemLeaseStatus.textContent = isHardwareLeased ? 'CLAIMED' : 'UNCLAIMED';
      telemLeaseStatus.className = `telem-val val-lease ${isHardwareLeased ? 'claimed' : 'unclaimed'}`;
    }

    // 5. Ultrasonic Proximity Strip Updates
    if (data.ultrasonic && data.ultrasonic.distances) {
      const dists = data.ultrasonic.distances;
      for (const [dir, dist] of Object.entries(dists)) {
        const valEl = document.getElementById(`val-sensor-${dir}`);
        const barEl = document.getElementById(`bar-sensor-${dir}`);
        if (!valEl || !barEl) continue;

        if (!sensorsEnabled) {
          valEl.textContent = 'OFF';
          valEl.className = 'prox-val';
          barEl.style.width = '0%';
        } else if (dist === null || dist === undefined) {
          valEl.textContent = '--';
          valEl.className = 'prox-val alert';
          barEl.style.width = '0%';
        } else {
          valEl.textContent = `${dist}cm`;
          valEl.className = 'prox-val';

          const pct = Math.min(100, Math.max(5, (dist / 140) * 100));
          barEl.style.width = `${pct}%`;

          if (dist <= 15.0) {
            valEl.classList.add('alert');
            barEl.style.backgroundColor = 'var(--accent-red)';
          } else if (dist <= 30.0) {
            valEl.classList.add('warn');
            barEl.style.backgroundColor = 'var(--accent-amber)';
          } else {
            barEl.style.backgroundColor = 'var(--accent-green)';
          }
        }
      }
    }

    // 6. LED Indicators (Front, Rear, Left, Right, All)
    if (data.leds && data.leds.state) {
      let anyOff = false;
      for (const [dir, state] of Object.entries(data.leds.state)) {
        const btn = document.getElementById(`led-${dir}`);
        if (btn) {
          btn.classList.toggle('active', !!state);
        }
        if (!state) anyOff = true;
      }
      const allBtn = document.getElementById('btn-leds-all');
      if (allBtn) {
        allBtn.classList.toggle('active', !anyOff);
        allLedsOn = !anyOff;
      }
    }

    // 7. 2D Sonar Radar Cones Visualizer
    if (data.ultrasonic && data.ultrasonic.distances) {
      for (const [dir, dist] of Object.entries(data.ultrasonic.distances)) {
        const arc = document.getElementById(`radar-arc-${dir}`);
        if (!arc) continue;
        if (!sensorsEnabled || dist === null || dist === undefined) {
          arc.setAttribute('fill', 'rgba(51, 65, 85, 0.25)');
        } else if (dist <= 15.0) {
          arc.setAttribute('fill', 'rgba(239, 68, 68, 0.85)');
        } else if (dist <= 30.0) {
          arc.setAttribute('fill', 'rgba(245, 158, 11, 0.85)');
        } else {
          arc.setAttribute('fill', 'rgba(16, 185, 129, 0.55)');
        }
      }
    }

    // 8. Raspberry Pi Vital Statistics
    if (data.vitals) {
      const telemCpuTemp = document.getElementById('telem-cpu-temp');
      const telemCpuLoad = document.getElementById('telem-cpu-load');
      const telemRamUsage = document.getElementById('telem-ram-usage');
      const telemPwrStatus = document.getElementById('telem-pwr-status');

      if (telemCpuTemp) telemCpuTemp.textContent = `${data.vitals.cpu_temp ?? '--'}°C`;
      if (telemCpuLoad) telemCpuLoad.textContent = `${data.vitals.cpu_load ?? 0}%`;
      if (telemRamUsage) telemRamUsage.textContent = `${data.vitals.ram_usage ?? 0}%`;
      if (telemPwrStatus) {
        if (data.vitals.undervoltage) {
          telemPwrStatus.textContent = 'LOW VOLT';
          telemPwrStatus.className = 'telem-val val-red';
        } else {
          telemPwrStatus.textContent = 'OK';
          telemPwrStatus.className = 'telem-val val-green';
        }
      }
    }

    // 9. Blackbox Telemetry Frame Capture
    if (isLogging) {
      logBuffer.push({
        timestamp: new Date().toISOString(),
        action: currentAction,
        cmd_linear: (lastLinearCmd * 100).toFixed(1),
        cmd_angular: (lastAngularCmd * 100).toFixed(1),
        motor_left: data.motors ? Math.round(data.motors.left_speed || 0) : 0,
        motor_right: data.motors ? Math.round(data.motors.right_speed || 0) : 0,
        sonar_front: data.ultrasonic && data.ultrasonic.distances ? data.ultrasonic.distances.front : '',
        sonar_rear: data.ultrasonic && data.ultrasonic.distances ? data.ultrasonic.distances.rear : '',
        sonar_left: data.ultrasonic && data.ultrasonic.distances ? data.ultrasonic.distances.left : '',
        sonar_right: data.ultrasonic && data.ultrasonic.distances ? data.ultrasonic.distances.right : '',
        cpu_temp: data.vitals ? data.vitals.cpu_temp : '',
      });
    }
  }

  let hudWarnTimeout = null;
  function showHUDWarning(msg, type = 'warning') {
    hudWarningBox.classList.remove('warning', 'caution');
    hudWarningBox.classList.add(type);
    hudWarningText.textContent = msg;
    clearTimeout(hudWarnTimeout);
    hudWarnTimeout = setTimeout(() => {
      hudWarningBox.classList.remove('warning', 'caution');
      hudWarningText.textContent = 'READY';
    }, type === 'caution' ? 1400 : 2200);
  }

  // --- Initialize Teleop Controls ---
  controls = new TeleopControls(sendDriveCommand);

  joystick = new VirtualJoystick('joystick-canvas', (linear, angular) => {
    const scaledLinear = linear * controls.speedLimit;
    const scaledAngular = angular * controls.speedLimit;
    sendDriveCommand(scaledLinear, scaledAngular);
  });

  // --- Toggle Buttons Event Listeners (WS + REST fallback) ---
  toggleMotorsBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      motorsEnabled = !motorsEnabled;
      toggleMotorsBtns.forEach(b => b.classList.toggle('active', motorsEnabled));
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'toggle_motors', value: motorsEnabled }));
      }
      fetch('/api/hardware/motors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: motorsEnabled }),
      }).catch(() => { });
    });
  });

  // --- Direct Video Stream Watchdog & Reconnection ---
  function reloadVideoStream() {
    if (!cameraStreamImg || !cameraEnabled) return;
    cameraStreamImg.src = `/api/video/feed?t=${Date.now()}`;
    cameraStreamImg.style.display = 'block';
  }

  function setupVideoStreamWatchdog() {
    if (!cameraStreamImg) return;

    cameraStreamImg.addEventListener('load', () => {
      videoRetryDelay = 800;
      if (cameraReconnectOverlay) cameraReconnectOverlay.classList.remove('show');
    });

    cameraStreamImg.addEventListener('error', () => {
      if (!cameraEnabled) return;
      console.warn(`[SAM] Video feed interrupted. Auto-reconnecting in ${videoRetryDelay}ms...`);
      if (cameraReconnectOverlay) cameraReconnectOverlay.classList.add('show');

      clearTimeout(videoRetryTimer);
      videoRetryTimer = setTimeout(() => {
        reloadVideoStream();
        videoRetryDelay = Math.min(videoRetryDelay * 1.5, 4000);
      }, videoRetryDelay);
    });
  }

  toggleCameraBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      cameraEnabled = !cameraEnabled;
      toggleCameraBtns.forEach(b => b.classList.toggle('active', cameraEnabled));
      cameraPausedOverlay.classList.toggle('show', !cameraEnabled);
      if (cameraReconnectOverlay && !cameraEnabled) {
        cameraReconnectOverlay.classList.remove('show');
      }
      if (cameraStreamImg) {
        if (cameraEnabled) {
          reloadVideoStream();
        } else {
          cameraStreamImg.src = '';
          cameraStreamImg.style.display = 'none';
        }
      }
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'toggle_camera', value: cameraEnabled }));
      }
      fetch('/api/hardware/camera', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: cameraEnabled }),
      }).catch(() => { });
    });
  });

  toggleSensorsBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      sensorsEnabled = !sensorsEnabled;
      toggleSensorsBtns.forEach(b => b.classList.toggle('active', sensorsEnabled));
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'toggle_sensors', value: sensorsEnabled }));
      }
      fetch('/api/hardware/sensors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: sensorsEnabled }),
      }).catch(() => { });
    });
  });

  // --- Control Tabs (Joystick vs D-Pad) with Persistent Selection ---
  const tabJoystick = document.getElementById('tab-btn-joystick');
  const tabDpad = document.getElementById('tab-btn-dpad');
  const viewJoystick = document.getElementById('view-joystick');
  const viewDpad = document.getElementById('view-dpad');

  function switchTab(tabName, saveStorage = true) {
    if (tabName === 'dpad') {
      tabDpad.classList.add('active');
      tabJoystick.classList.remove('active');
      viewDpad.classList.add('active');
      viewJoystick.classList.remove('active');
    } else {
      tabJoystick.classList.add('active');
      tabDpad.classList.remove('active');
      viewJoystick.classList.add('active');
      viewDpad.classList.remove('active');
      if (joystick && typeof joystick.resize === 'function') {
        setTimeout(() => joystick.resize(), 30);
      }
    }
    if (saveStorage) {
      try {
        localStorage.setItem('sam_active_tab', tabName);
      } catch (e) { }
    }
  }

  tabJoystick.addEventListener('click', () => switchTab('joystick'));
  tabDpad.addEventListener('click', () => switchTab('dpad'));

  // Restore saved tab (defaults to 'dpad')
  try {
    const savedTab = localStorage.getItem('sam_active_tab') || 'dpad';
    switchTab(savedTab, false);
  } catch (e) {
    switchTab('dpad', false);
  }

  // --- Emergency Stop Button ---
  document.getElementById('btn-estop').addEventListener('click', () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'stop' }));
    }
    showHUDWarning('EMERGENCY STOPPED');
  });

  // --- Hardware Lease Toggle (Claim / Release / Take Control) ---
  let isLeaseToggling = false;
  btnToggleLease.addEventListener('click', async () => {
    if (isLeaseToggling) return;
    isLeaseToggling = true;
    btnToggleLease.style.pointerEvents = 'none';

    const isClaimedByMe = isHardwareLeased && (
      !currentOperatorId ||
      currentOperatorId === clientId ||
      currentOperatorId === 'driver' ||
      currentOperatorId === 'primary-operator'
    );
    const endpoint = isClaimedByMe ? '/api/hardware/release' : '/api/hardware/acquire';

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          operator_id: clientId,
          operator_name: 'Driver',
          force: true,
        }),
      });
      const data = await res.json();
      if (data && typeof data.hardware_leased === 'boolean') {
        const wasLeased = isHardwareLeased;
        isHardwareLeased = data.hardware_leased;
        if (isHardwareLeased) {
          currentOperatorId = data.operator_id || clientId;
          activeOperatorName = data.operator_name || 'Driver';
        } else {
          currentOperatorId = null;
          activeOperatorName = null;
        }
        updateLeaseUI();

        // Only reload stream when acquiring physical camera, avoiding socket churn on release
        if (!wasLeased && isHardwareLeased) {
          setTimeout(() => {
            if (cameraStreamImg) {
              reloadVideoStream();
            }
          }, 350);
        }
      }
    } catch (e) {
      console.error('Lease toggle failed:', e);
    } finally {
      setTimeout(() => {
        isLeaseToggling = false;
        btnToggleLease.style.pointerEvents = 'auto';
      }, 300);
    }
  });

  // --- Instant Camera Snapshot Handler with Shutter Flash ---
  const btnSnapshot = document.getElementById('btn-snapshot');
  const shutterOverlay = document.getElementById('shutter-flash-overlay');

  if (btnSnapshot) {
    btnSnapshot.addEventListener('click', async () => {
      try {
        btnSnapshot.classList.add('capturing');
        if (shutterOverlay) {
          shutterOverlay.classList.add('active');
          setTimeout(() => shutterOverlay.classList.remove('active'), 250);
        }

        const res = await fetch(`/api/video/snapshot?t=${Date.now()}`);
        if (!res.ok) throw new Error('Snapshot failed');
        const blob = await res.blob();

        const now = new Date();
        const pad = (n) => String(n).padStart(2, '0');
        const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
        const filename = `SAM_snapshot_${ts}.jpg`;

        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);

        showHUDWarning('SNAPSHOT SAVED', 'caution');
      } catch (err) {
        console.error('[SAM] Snapshot capture error:', err);
        showHUDWarning('SNAPSHOT FAILED', 'warning');
      } finally {
        btnSnapshot.classList.remove('capturing');
      }
    });
  }

  // --- Directional 4 LEDs (Front, Rear, Left, Right) ---
  document.querySelectorAll('.btn-led[data-dir]').forEach(btn => {
    btn.addEventListener('click', () => {
      const dir = btn.dataset.dir;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'toggle_led', direction: dir }));
      } else {
        fetch(`/api/hardware/leds/${dir}/toggle`, { method: 'POST' }).catch(() => {});
      }
    });
  });

  // --- All LEDs Toggle (Excludes Horn) ---
  let allLedsOn = false;
  const btnLedsAll = document.getElementById('btn-leds-all');
  if (btnLedsAll) {
    btnLedsAll.addEventListener('click', async () => {
      allLedsOn = !allLedsOn;
      btnLedsAll.classList.toggle('active', allLedsOn);
      document.querySelectorAll('.btn-led[data-dir]').forEach(b => {
        b.classList.toggle('active', allLedsOn);
      });
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'toggle_all_leds', state: allLedsOn }));
      }
      try {
        await fetch('/api/hardware/leds/all', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: allLedsOn }),
        });
      } catch (e) {
        console.error('Failed to toggle all LEDs:', e);
      }
    });
  }

  // --- Manual Buzzer (Horn) Controls ---
  let hornActive = false;

  function triggerHorn(state) {
    hornActive = state;
    toggleHornBtns.forEach(btn => btn.classList.toggle('active', state));
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'set_buzzer', state: state }));
    } else {
      fetch('/api/hardware/buzzer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: state }),
      }).catch(() => { });
    }
  }

  toggleHornBtns.forEach(btn => {
    btn.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      triggerHorn(true);
    });
    btn.addEventListener('pointerup', (e) => {
      e.preventDefault();
      triggerHorn(false);
    });
    btn.addEventListener('pointerleave', () => {
      if (hornActive) triggerHorn(false);
    });
    btn.addEventListener('pointercancel', () => {
      if (hornActive) triggerHorn(false);
    });
  });

  // --- Blackbox Flight Data Recorder Controls ---
  const btnToggleLog = document.getElementById('btn-toggle-log');
  const btnExportLog = document.getElementById('btn-export-log');

  if (btnToggleLog) {
    btnToggleLog.addEventListener('click', () => {
      isLogging = !isLogging;
      btnToggleLog.classList.toggle('recording', isLogging);
      btnToggleLog.textContent = isLogging ? 'STOP' : 'REC';
      if (isLogging) {
        logBuffer = [];
        if (btnExportLog) btnExportLog.disabled = true;
      } else {
        if (btnExportLog) btnExportLog.disabled = logBuffer.length === 0;
      }
    });
  }

  if (btnExportLog) {
    btnExportLog.addEventListener('click', () => {
      if (logBuffer.length === 0) return;
      const headers = Object.keys(logBuffer[0]);
      const csvLines = [
        headers.join(','),
        ...logBuffer.map(row => headers.map(h => `"${row[h] !== undefined ? row[h] : ''}"`).join(','))
      ];
      const blob = new Blob([csvLines.join('\n')], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `sam_blackbox_${new Date().toISOString().replace(/[:.]/g, '-')}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  }

  // --- Wi-Fi & Network Modal ---
  const wifiModal = document.getElementById('wifi-modal');
  const btnOpenWifi = document.getElementById('btn-open-wifi');
  const btnCloseWifi = document.getElementById('btn-close-wifi');
  const interfacesList = document.getElementById('interfaces-list');
  const wifiNetworksList = document.getElementById('wifi-networks-list');
  const btnRescanWifi = document.getElementById('btn-rescan-wifi');
  const btnSubmitWifi = document.getElementById('btn-submit-wifi');
  const wifiSsidInput = document.getElementById('wifi-ssid');
  const wifiPasswordInput = document.getElementById('wifi-password');
  const wifiMsg = document.getElementById('wifi-msg');

  btnOpenWifi.addEventListener('click', () => {
    wifiModal.classList.add('open');
    loadNetworkInfo();
  });

  btnCloseWifi.addEventListener('click', () => {
    wifiModal.classList.remove('open');
  });

  document.querySelector('.modal-backdrop').addEventListener('click', () => {
    wifiModal.classList.remove('open');
  });

  async function loadNetworkInfo() {
    try {
      const res = await fetch('/api/network/interfaces');
      const data = await res.json();
      interfacesList.innerHTML = '';
      data.interfaces.forEach(iface => {
        const item = document.createElement('div');
        item.className = 'interface-item';
        item.innerHTML = `
          <div>
            <strong>${iface.label}</strong>
            ${iface.is_external ? '<span class="tag-ext">USB DONGLE</span>' : ''}
            <div style="color:var(--text-muted); font-size:0.7rem;">State: ${iface.state} (${iface.connection})</div>
          </div>
          <div style="font-family:var(--font-mono); color:var(--accent-cyan); font-weight:600;">${iface.ip}</div>
        `;
        interfacesList.appendChild(item);
      });
    } catch (e) {
      interfacesList.innerHTML = '<div style="color:var(--accent-red);">Failed to read interfaces.</div>';
    }

    scanWifiNetworks();
  }

  async function scanWifiNetworks() {
    wifiNetworksList.innerHTML = '<div style="color:var(--text-muted); padding:6px;">Scanning Wi-Fi SSIDs...</div>';
    try {
      const res = await fetch('/api/network/wifi/scan');
      const data = await res.json();
      wifiNetworksList.innerHTML = '';
      if (!data.networks || data.networks.length === 0) {
        wifiNetworksList.innerHTML = '<div style="color:var(--text-muted); padding:6px;">No Wi-Fi networks found.</div>';
        return;
      }
      data.networks.forEach(net => {
        const row = document.createElement('div');
        row.className = 'wifi-item';
        row.innerHTML = `
          <div><strong>${net.ssid}</strong> <span style="font-size:0.7rem; color:var(--text-muted);">(${net.security})</span></div>
          <div style="color:var(--accent-cyan); font-family:var(--font-mono);">${net.signal}%</div>
        `;
        row.addEventListener('click', () => {
          wifiSsidInput.value = net.ssid;
          wifiPasswordInput.focus();
        });
        wifiNetworksList.appendChild(row);
      });
    } catch (e) {
      wifiNetworksList.innerHTML = '<div style="color:var(--accent-red);">Wi-Fi scan failed.</div>';
    }
  }

  btnRescanWifi.addEventListener('click', scanWifiNetworks);

  btnSubmitWifi.addEventListener('click', async () => {
    const ssid = wifiSsidInput.value.trim();
    const password = wifiPasswordInput.value;
    if (!ssid) {
      wifiMsg.textContent = 'Please choose or type an SSID';
      wifiMsg.style.color = 'var(--accent-amber)';
      return;
    }

    wifiMsg.textContent = `Connecting to ${ssid}...`;
    wifiMsg.style.color = 'var(--accent-cyan)';

    try {
      const res = await fetch('/api/network/wifi/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ssid, password }),
      });
      const data = await res.json();
      if (data.success) {
        wifiMsg.textContent = data.message;
        wifiMsg.style.color = 'var(--accent-green)';
        setTimeout(loadNetworkInfo, 3000);
      } else {
        wifiMsg.textContent = `Failed: ${data.message}`;
        wifiMsg.style.color = 'var(--accent-red)';
      }
    } catch (e) {
      wifiMsg.textContent = 'Connection request error.';
      wifiMsg.style.color = 'var(--accent-red)';
    }
  });

  // --- Initial Telemetry Hydration from Embedded Server State ---
  const initDataEl = document.getElementById('initial-telemetry-data');
  if (initDataEl && initDataEl.textContent.trim()) {
    try {
      const initData = JSON.parse(initDataEl.textContent);
      handleTelemetry(initData);
    } catch (e) {
      console.warn('[SAM] Error parsing initial embedded telemetry:', e);
    }
  }

  // Backup fetch to verify freshness if page was served from browser back/forward cache
  fetch('/api/hardware/telemetry')
    .then(r => r.json())
    .then(data => handleTelemetry(data))
    .catch(() => { });

  // Initialize Direct MJPEG Video Stream & Watchdog
  setupVideoStreamWatchdog();
  if (cameraStreamImg && cameraEnabled) {
    reloadVideoStream();
  }

  // Start WebSocket
  connectWebSocket();
});
