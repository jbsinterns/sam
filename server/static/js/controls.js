/**
 * SAM Rover - Multi-Modal Teleoperation Controls
 * Coordinates Keyboard, D-Pad, Speed presets, and Gamepad API.
 */

class TeleopControls {
  constructor(onDriveCommand) {
    this.sendDrive = onDriveCommand;
    this.speedLimit = 60; // Default gear (60%)
    this.activeKeys = new Set();
    this.activeDpadDirection = null;

    this.gamepadIndex = null;
    this.gamepadLoopId = null;

    this._initKeyboard();
    this._initDpad();
    this._initGearSelector();
    this._initGamepad();
    this._preventUnwantedGestures();
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
      if (['input', 'textarea'].includes(document.activeElement.tagName.toLowerCase())) return;
      const key = e.key.toLowerCase();
      if (['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright', ' '].includes(key)) {
        e.preventDefault();
        this.activeKeys.add(key);
        this._processKeyboardDrive();
      }
    });

    window.addEventListener('keyup', (e) => {
      const key = e.key.toLowerCase();
      if (this.activeKeys.has(key)) {
        this.activeKeys.delete(key);
        this._processKeyboardDrive();
      }
    });

    // Failsafe: clear pressed keys and halt drive when browser loses focus (Alt-Tab, window change)
    window.addEventListener('blur', () => {
      if (this.activeKeys.size > 0) {
        this.activeKeys.clear();
        this.sendDrive(0.0, 0.0);
      }
    });
  }

  _processKeyboardDrive() {
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
      statusEl.classList.add('active');
      labelEl.textContent = `Connected: ${e.gamepad.id.slice(0, 28)}...`;
      this._startGamepadPoll();
    });

    window.addEventListener('gamepaddisconnected', (e) => {
      if (this.gamepadIndex === e.gamepad.index) {
        this.gamepadIndex = null;
        const statusEl = document.getElementById('gamepad-status');
        const labelEl = document.getElementById('gamepad-label');
        statusEl.classList.remove('active');
        labelEl.textContent = 'Gamepad: Disconnected (Plug in USB/Xbox controller)';
      }
    });
  }

  _startGamepadPoll() {
    const poll = () => {
      if (this.gamepadIndex === null) return;
      const gp = navigator.getGamepads()[this.gamepadIndex];
      if (gp) {
        // Read Left Stick: Axis 1 (Linear/Throttle invert), Axis 0 (Angular/Steering)
        let rawLinear = -gp.axes[1];
        let rawAngular = gp.axes[0];

        // Deadzone threshold (15%)
        if (Math.abs(rawLinear) < 0.15) rawLinear = 0;
        if (Math.abs(rawAngular) < 0.15) rawAngular = 0;

        // If stick is moved, send command
        if (rawLinear !== 0 || rawAngular !== 0) {
          this.sendDrive(rawLinear * this.speedLimit, rawAngular * this.speedLimit);
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
