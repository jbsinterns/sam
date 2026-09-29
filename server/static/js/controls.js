/**
 * SAM Rover - Multi-Modal Teleoperation Controls
 * Coordinates Keyboard, D-Pad, Speed presets, and Gamepad API.
 */

class TeleopControls {
  constructor(onDriveCommand, onSpeedChange = null, callbacks = {}) {
    this.sendDrive = onDriveCommand;
    this.onSpeedChange = onSpeedChange;
    this.callbacks = callbacks || {};
    this.speedLimit = 60; // Default gear (60%)
    this.activeKeys = new Set();
    this.activeDpadDirection = null;

    this.gamepadIndex = null;
    this.gamepadLoopId = null;
    this.gamepadWasMoving = false;
    this.lastButtonStates = {};
    this.enabled = false;

    this._initKeyboard();
    this._initDpad();
    this._initGearSelector();
    this._initGamepad();
    this._preventUnwantedGestures();
  }

  setEnabled(enabled) {
    this.enabled = !!enabled;
    if (!this.enabled && this.activeKeys.size > 0) {
      this.activeKeys.clear();
    }
  }

  setSpeed(val, saveStorage = true) {
    this.speedLimit = Math.max(25, Math.min(100, parseInt(val, 10)));
    const hudGear = document.getElementById('hud-gear');
    if (hudGear) hudGear.textContent = `${this.speedLimit}%`;
    const sliderVal = document.getElementById('speed-slider-val');
    if (sliderVal) sliderVal.textContent = `${this.speedLimit}%`;
    const slider = document.getElementById('speed-slider');
    if (slider) slider.value = this.speedLimit;

    // Update active class on gear buttons
    document.querySelectorAll('.btn-gear').forEach(btn => {
      btn.classList.toggle('active', parseInt(btn.dataset.speed, 10) === this.speedLimit);
    });

    if (saveStorage) {
      try {
        localStorage.setItem('sam_speed_limit', this.speedLimit);
      } catch (e) {}
    }

    if (typeof this.onSpeedChange === 'function') {
      this.onSpeedChange(this.speedLimit);
    }
  }

  shiftGear(direction) {
    const gears = [25, 50, 75, 100];
    let currentIndex = gears.indexOf(this.speedLimit);
    if (currentIndex === -1) {
      currentIndex = gears.reduce((prev, curr, idx) => 
        Math.abs(curr - this.speedLimit) < Math.abs(gears[prev] - this.speedLimit) ? idx : prev, 0);
    }
    const newIndex = Math.max(0, Math.min(gears.length - 1, currentIndex + direction));
    if (newIndex !== currentIndex) {
      this.setSpeed(gears[newIndex]);
    }
  }

  _applyDeadzoneAndExpo(val, deadzone = 0.12, expo = 1.4) {
    const abs = Math.abs(val);
    if (abs < deadzone) return 0.0;
    // Map [deadzone, 1.0] linearly to [0.0, 1.0]
    const normalized = (abs - deadzone) / (1.0 - deadzone);
    // Apply exponential curve for ultra-fine low-throttle precision
    const shaped = Math.pow(Math.min(1.0, Math.max(0.0, normalized)), expo);
    return Math.sign(val) * shaped;
  }

  _initGearSelector() {
    // Restore saved speed preset if available
    try {
      const savedSpeed = localStorage.getItem('sam_speed_limit');
      if (savedSpeed) {
        this.setSpeed(savedSpeed, false);
      }
    } catch (e) {}

    document.querySelectorAll('.btn-gear').forEach(btn => {
      btn.addEventListener('click', () => {
        this.setSpeed(btn.dataset.speed);
      });
    });

    const slider = document.getElementById('speed-slider');
    if (slider) {
      slider.addEventListener('input', (e) => {
        this.setSpeed(e.target.value);
      });
    }

    // --- Software Motor Trim Slider (Desktop) ---
    this.trim = 0;
    const trimSlider = document.getElementById('trim-slider');
    const trimVal = document.getElementById('trim-val');
    try {
      const savedTrim = localStorage.getItem('sam_motor_trim');
      if (savedTrim !== null) {
        this.trim = parseInt(savedTrim, 10);
        if (trimSlider) trimSlider.value = this.trim;
        if (trimVal) trimVal.textContent = this.trim > 0 ? `+${this.trim}` : `${this.trim}`;
      }
    } catch (e) {}

    if (trimSlider) {
      trimSlider.addEventListener('input', (e) => {
        this.trim = parseInt(e.target.value, 10);
        if (trimVal) trimVal.textContent = this.trim > 0 ? `+${this.trim}` : `${this.trim}`;
        try { localStorage.setItem('sam_motor_trim', this.trim); } catch (err) {}
      });
    }
  }

  _initKeyboard() {
    window.addEventListener('keydown', (e) => {
      if (document.activeElement?.tagName && ['input', 'textarea'].includes(document.activeElement.tagName.toLowerCase())) return;
      const key = e.key.toLowerCase();
      if (['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright', ' '].includes(key)) {
        e.preventDefault();
        this.activeKeys.add(key);
        this._processKeyboardDrive();
      } else if (key === 'h' && !e.repeat) {
        e.preventDefault();
        if (typeof this.callbacks.onHorn === 'function') {
          this.callbacks.onHorn(true);
        }
      } else if (key === 'l' && !e.repeat) {
        e.preventDefault();
        if (typeof this.callbacks.onToggleLeds === 'function') {
          this.callbacks.onToggleLeds();
        }
      }
    });

    window.addEventListener('keyup', (e) => {
      const key = e.key.toLowerCase();
      if (this.activeKeys.has(key)) {
        this.activeKeys.delete(key);
        this._processKeyboardDrive();
      } else if (key === 'h') {
        if (typeof this.callbacks.onHorn === 'function') {
          this.callbacks.onHorn(false);
        }
      }
    });

    // Failsafe: clear pressed keys and halt drive when browser loses focus (Alt-Tab, window change)
    window.addEventListener('blur', () => {
      if (this.activeKeys.size > 0) {
        this.activeKeys.clear();
        this.sendDrive(0.0, 0.0);
      }
      if (typeof this.callbacks.onHorn === 'function') {
        this.callbacks.onHorn(false);
      }
    });
  }

  _processKeyboardDrive() {
    if (!this.enabled) return;
    if (this.activeKeys.has(' ')) {
      this.sendDrive(0.0, 0.0);
      return;
    }

    let linear = 0.0;
    let angular = 0.0;

    if (this.activeKeys.has('w') || this.activeKeys.has('arrowup')) linear += 1.0;
    if (this.activeKeys.has('s') || this.activeKeys.has('arrowdown')) linear -= 1.0;
    if (this.activeKeys.has('a') || this.activeKeys.has('arrowleft')) angular -= 1.0;
    if (this.activeKeys.has('d') || this.activeKeys.has('arrowright')) angular += 1.0;

    let actualLinear = linear * this.speedLimit;
    let actualAngular = angular * this.speedLimit;

    // Apply software motor steering trim proportionally
    if (Math.abs(actualLinear) > 0.01) {
      actualAngular += (this.trim / 100.0) * Math.abs(actualLinear);
    }

    this.sendDrive(actualLinear, actualAngular);
  }

  _initDpad() {
    const dpadButtons = document.querySelectorAll('.dpad-btn');

    dpadButtons.forEach(btn => {
      const dir = btn.dataset.dir;

      const startDrive = (e) => {
        e.preventDefault();
        try {
          if (btn.setPointerCapture && e.pointerId !== undefined) {
            btn.setPointerCapture(e.pointerId);
          }
        } catch (err) {}
        btn.classList.add('pressed');
        this.activeDpadDirection = dir;

        let linear = 0;
        let angular = 0;
        if (dir === 'forward') linear = this.speedLimit;
        else if (dir === 'backward') linear = -this.speedLimit;
        else if (dir === 'left') angular = -this.speedLimit;
        else if (dir === 'right') angular = this.speedLimit;
        else if (dir === 'stop') { linear = 0; angular = 0; }

        this.sendDrive(linear, angular);
      };

      const stopDrive = (e) => {
        e.preventDefault();
        try {
          if (btn.releasePointerCapture && e.pointerId !== undefined && btn.hasPointerCapture && btn.hasPointerCapture(e.pointerId)) {
            btn.releasePointerCapture(e.pointerId);
          }
        } catch (err) {}
        btn.classList.remove('pressed');
        if (this.activeDpadDirection === dir) {
          this.activeDpadDirection = null;
          this.sendDrive(0, 0);
        }
      };

      // Pointer events for universal touch/mouse handle
      btn.addEventListener('pointerdown', startDrive);
      btn.addEventListener('pointerup', stopDrive);
      btn.addEventListener('pointercancel', stopDrive);
    });
  }

  _initGamepad() {
    window.addEventListener('gamepadconnected', (e) => {
      this.gamepadIndex = e.gamepad.index;
      const statusEl = document.getElementById('gamepad-status');
      const labelEl = document.getElementById('gamepad-label');
      if (statusEl) statusEl.classList.add('active');
      if (labelEl) labelEl.textContent = `Connected: ${e.gamepad.id.slice(0, 20)}...`;
      this.lastButtonStates = {};
      this._startGamepadPoll();
    });

    window.addEventListener('gamepaddisconnected', (e) => {
      if (this.gamepadIndex === e.gamepad.index) {
        this.gamepadIndex = null;
        if (this.gamepadLoopId) {
          cancelAnimationFrame(this.gamepadLoopId);
          this.gamepadLoopId = null;
        }
        if (this.gamepadWasMoving) {
          this.sendDrive(0.0, 0.0);
          this.gamepadWasMoving = false;
        }
        if (this.lastButtonStates['A'] && typeof this.callbacks.onHorn === 'function') {
          this.callbacks.onHorn(false);
        }
        this.lastButtonStates = {};
        const statusEl = document.getElementById('gamepad-status');
        const labelEl = document.getElementById('gamepad-label');
        if (statusEl) statusEl.classList.remove('active');
        if (labelEl) labelEl.textContent = 'Gamepad Off';
      }
    });
  }

  _startGamepadPoll() {
    if (this.gamepadLoopId) {
      cancelAnimationFrame(this.gamepadLoopId);
    }

    const isBtnPressed = (btn) => {
      if (!btn) return false;
      if (typeof btn === 'object') return !!btn.pressed || (typeof btn.value === 'number' && btn.value > 0.5);
      return btn > 0.5;
    };

    const getBtnValue = (btn) => {
      if (!btn) return 0.0;
      if (typeof btn.value === 'number') return btn.value;
      return btn.pressed ? 1.0 : 0.0;
    };

    const poll = () => {
      if (this.gamepadIndex === null) return;
      const gp = navigator.getGamepads()[this.gamepadIndex];
      if (gp) {
        // --- 1. Action Buttons ---
        const btnA = isBtnPressed(gp.buttons[0]); // Xbox A / PS Cross
        const btnB = isBtnPressed(gp.buttons[1]); // Xbox B / PS Circle
        const btnX = isBtnPressed(gp.buttons[2]); // Xbox X / PS Square
        const btnLB = isBtnPressed(gp.buttons[4]); // Left Bumper
        const btnRB = isBtnPressed(gp.buttons[5]); // Right Bumper
        const btnDpadUp = isBtnPressed(gp.buttons[12]);
        const btnDpadDown = isBtnPressed(gp.buttons[13]);

        // A Button: Horn / Buzzer chirp (continuous state)
        if (btnA !== !!this.lastButtonStates['A']) {
          this.lastButtonStates['A'] = btnA;
          if (typeof this.callbacks.onHorn === 'function') {
            this.callbacks.onHorn(btnA);
          }
        }

        // X Button: Headlights / Directional LEDs (rising edge click)
        if (btnX && !this.lastButtonStates['X']) {
          if (typeof this.callbacks.onToggleLeds === 'function') {
            this.callbacks.onToggleLeds();
          }
        }
        this.lastButtonStates['X'] = btnX;

        // B Button: Emergency Stop (rising edge click)
        if (btnB && !this.lastButtonStates['B']) {
          if (typeof this.callbacks.onEStop === 'function') {
            this.callbacks.onEStop();
          }
        }
        this.lastButtonStates['B'] = btnB;

        // Shift Gears: LB / DpadDown = Shift Down, RB / DpadUp = Shift Up (rising edge)
        const shiftDown = btnLB || btnDpadDown;
        const shiftUp = btnRB || btnDpadUp;

        if (shiftDown && !this.lastButtonStates['shiftDown']) {
          this.shiftGear(-1);
        }
        this.lastButtonStates['shiftDown'] = shiftDown;

        if (shiftUp && !this.lastButtonStates['shiftUp']) {
          this.shiftGear(1);
        }
        this.lastButtonStates['shiftUp'] = shiftUp;

        // --- 2. Dual Driving Mode (RC Trigger Throttle vs Left Stick) ---
        let rt = getBtnValue(gp.buttons[7]); // Right Trigger (Forward gas)
        let lt = getBtnValue(gp.buttons[6]); // Left Trigger (Reverse/Brake)
        if (rt < 0.08) rt = 0.0;
        if (lt < 0.08) lt = 0.0;

        let throttle = 0.0;
        if (rt > 0.0 || lt > 0.0) {
          // Racing mode: RT accelerates forward, LT reverses
          throttle = this._applyDeadzoneAndExpo(rt - lt, 0.05, 1.4);
        } else {
          // Classic Left Stick mode (Axis 1 inverted)
          const rawStickY = -gp.axes[1];
          throttle = this._applyDeadzoneAndExpo(rawStickY, 0.12, 1.4);
        }

        // Steering: Left Stick Horizontal (Axis 0)
        const rawStickX = gp.axes[0];
        let steering = this._applyDeadzoneAndExpo(rawStickX, 0.12, 1.4);

        // --- 3. Velocity Dispatch & Zero Failsafe ---
        if (throttle !== 0.0 || steering !== 0.0) {
          let linear = throttle * this.speedLimit;
          let angular = steering * this.speedLimit;

          // Apply software motor steering trim proportionally
          if (Math.abs(linear) > 0.01 && this.trim) {
            angular += (this.trim / 100.0) * Math.abs(linear);
          }

          this.sendDrive(linear, angular);
          this.gamepadWasMoving = true;
        } else if (this.gamepadWasMoving) {
          // Immediately halt rover when stick/triggers return to neutral center
          this.sendDrive(0.0, 0.0);
          this.gamepadWasMoving = false;
        }
      }
      this.gamepadLoopId = requestAnimationFrame(poll);
    };
    this.gamepadLoopId = requestAnimationFrame(poll);
  }

  _preventUnwantedGestures() {
    // Stop context menu on controls
    document.querySelectorAll('.touch-control-zone, .dpad-btn, .btn-gear, .btn-led').forEach(el => {
      el.addEventListener('contextmenu', (e) => e.preventDefault());
    });
  }
}
