/**
 * SAM Rover - Virtual Analog Touch Joystick
 * Touch-hardened for mobile & touch laptops:
 * - Cancels unwanted touch-scrolling
 * - Cancels context-menu / long-press right clicks
 * - Smooth spring-return physics
 */

class VirtualJoystick {
  constructor(canvasId, onMoveCallback) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.onMove = onMoveCallback;

    this.width = this.canvas.width;
    this.height = this.canvas.height;
    this.centerX = this.width / 2;
    this.centerY = this.height / 2;
    this.radius = 80;
    this.handleRadius = 32;

    this.touchId = null;
    this.pointerId = null;
    this.handleX = this.centerX;
    this.handleY = this.centerY;
    this.isDragging = false;

    window.virtualJoystick = this;

    this.resize();
    this._bindEvents();
    window.addEventListener('resize', () => this.resize());
  }

  resize() {
    const parent = this.canvas.parentElement;
    let size = 190;
    if (window.innerWidth >= 900) {
      if (parent && parent.clientHeight > 100) {
        size = Math.min(parent.clientWidth || 240, parent.clientHeight || 240, 260);
      } else {
        size = 240;
      }
    }
    if (size < 180) size = 180;
    this.canvas.width = size;
    this.canvas.height = size;
    this.width = size;
    this.height = size;
    this.centerX = size / 2;
    this.centerY = size / 2;
    this.radius = size * 0.44;
    this.handleRadius = size * 0.16;
    this.maxTravel = Math.max(1, this.radius - this.handleRadius);
    if (!this.isDragging) {
      this.handleX = this.centerX;
      this.handleY = this.centerY;
    }
    this.draw();
  }

  _bindEvents() {
    // Unified Pointer Events (Modern touch, mouse, pen with pointer capture)
    this.canvas.addEventListener('pointerdown', (e) => this._onPointerDown(e));
    this.canvas.addEventListener('pointermove', (e) => this._onPointerMove(e));
    this.canvas.addEventListener('pointerup', (e) => this._onPointerUp(e));
    this.canvas.addEventListener('pointercancel', (e) => this._onPointerUp(e));

    // Fallback Mouse Events
    this.canvas.addEventListener('mousedown', (e) => this._onMouseDown(e));
    window.addEventListener('mousemove', (e) => this._onMouseMove(e));
    window.addEventListener('mouseup', () => this._onMouseUp());

    // Prevent default touch gestures (scrolling, pinch zoom) on the joystick canvas
    this.canvas.addEventListener('touchstart', (e) => e.preventDefault(), { passive: false });
    this.canvas.addEventListener('touchmove', (e) => e.preventDefault(), { passive: false });

    // Fail-safes: reset if window loses focus
    window.addEventListener('blur', () => {
      if (this.isDragging) this._resetHandle();
    });

    // Explicitly prevent context menu on right click or touch long-press
    this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());
  }

  _onPointerDown(e) {
    if (e.button !== undefined && e.button !== 0) return; // Left click only
    this.isDragging = true;
    this.pointerId = e.pointerId;
    try {
      this.canvas.setPointerCapture(e.pointerId);
    } catch (_) {}
    this._handlePointerEvent(e);
  }

  _onPointerMove(e) {
    if (!this.isDragging) return;
    if (this.pointerId !== null && e.pointerId !== this.pointerId) return;
    this._handlePointerEvent(e);
  }

  _onPointerUp(e) {
    if (!this.isDragging) return;
    if (this.pointerId !== null && e.pointerId !== this.pointerId) return;
    this.isDragging = false;
    this.pointerId = null;
    try {
      if (this.canvas.hasPointerCapture(e.pointerId)) {
        this.canvas.releasePointerCapture(e.pointerId);
      }
    } catch (_) {}
    this._resetHandle();
  }

  _handlePointerEvent(e) {
    e.preventDefault();
    const rect = this.canvas.getBoundingClientRect();
    this._updateHandle({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
  }

  _onMouseDown(e) {
    if (e.button !== 0) return;
    if (this.isDragging) return;
    this.isDragging = true;
    const rect = this.canvas.getBoundingClientRect();
    this._updateHandle({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  }

  _onMouseMove(e) {
    if (!this.isDragging || this.pointerId !== null) return;
    const rect = this.canvas.getBoundingClientRect();
    this._updateHandle({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  }

  _onMouseUp() {
    if (this.isDragging && this.pointerId === null) {
      this._resetHandle();
    }
  }

  /**
   * Programmatic control / simulation method for diagnostics & hardware testing.
   * Deflects the joystick knob to any normalized coordinate and keeps it there
   * until release() is called.
   * @param {number} linear - Range [-1.0, 1.0], 1.0 = Full Forward, -1.0 = Full Reverse
   * @param {number} angular - Range [-1.0, 1.0], 1.0 = Full Right, -1.0 = Full Left
   */
  setPosition(linear, angular) {
    const clampedLinear = Math.max(-1.0, Math.min(1.0, linear));
    const clampedAngular = Math.max(-1.0, Math.min(1.0, angular));

    this.isDragging = true;
    this.handleX = this.centerX + clampedAngular * this.maxTravel;
    this.handleY = this.centerY - clampedLinear * this.maxTravel;
    this.draw();

    if (this.onMove) {
      this.onMove(clampedLinear, clampedAngular);
    }
  }

  /**
   * Smoothly springs the joystick knob back to center (0.0, 0.0).
   */
  release() {
    this._resetHandle();
  }

  _updateHandle(pos) {
    const dx = pos.x - this.centerX;
    const dy = pos.y - this.centerY;
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (dist <= this.maxTravel) {
      this.handleX = pos.x;
      this.handleY = pos.y;
    } else {
      const angle = Math.atan2(dy, dx);
      this.handleX = this.centerX + Math.cos(angle) * this.maxTravel;
      this.handleY = this.centerY + Math.sin(angle) * this.maxTravel;
    }

    this.draw();

    // Compute normalized coordinates: x in [-1, 1], y in [-1, 1] (forward is +y)
    const normX = (this.handleX - this.centerX) / this.maxTravel;
    const normY = -(this.handleY - this.centerY) / this.maxTravel;

    if (this.onMove) {
      this.onMove(normY, normX); // linear, angular
    }
  }

  _resetHandle() {
    this.isDragging = false;
    this.touchId = null;
    this.handleX = this.centerX;
    this.handleY = this.centerY;
    this.draw();

    if (this.onMove) {
      this.onMove(0.0, 0.0);
    }
  }

  draw() {
    this.ctx.clearRect(0, 0, this.width, this.height);

    // Outer boundary ring (Base Plate)
    this.ctx.beginPath();
    this.ctx.arc(this.centerX, this.centerY, this.radius, 0, Math.PI * 2);
    this.ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
    this.ctx.fill();
    this.ctx.lineWidth = 2.5;
    this.ctx.strokeStyle = 'rgba(6, 182, 212, 0.45)';
    this.ctx.stroke();

    // Subtle inner track guide
    this.ctx.beginPath();
    this.ctx.arc(this.centerX, this.centerY, this.maxTravel, 0, Math.PI * 2);
    this.ctx.lineWidth = 1;
    this.ctx.strokeStyle = 'rgba(6, 182, 212, 0.15)';
    this.ctx.stroke();

    // Cross guides
    this.ctx.beginPath();
    this.ctx.moveTo(this.centerX - this.radius, this.centerY);
    this.ctx.lineTo(this.centerX + this.radius, this.centerY);
    this.ctx.moveTo(this.centerX, this.centerY - this.radius);
    this.ctx.lineTo(this.centerX, this.centerY + this.radius);
    this.ctx.lineWidth = 1;
    this.ctx.strokeStyle = 'rgba(100, 116, 139, 0.22)';
    this.ctx.stroke();

    // Dynamic gimbal tether beam connecting center to deflected handle
    if (Math.abs(this.handleX - this.centerX) > 1 || Math.abs(this.handleY - this.centerY) > 1) {
      this.ctx.beginPath();
      this.ctx.moveTo(this.centerX, this.centerY);
      this.ctx.lineTo(this.handleX, this.handleY);
      this.ctx.lineWidth = 3;
      this.ctx.strokeStyle = 'rgba(6, 182, 212, 0.4)';
      this.ctx.stroke();
    }

    // Center handle (Knob)
    this.ctx.beginPath();
    this.ctx.arc(this.handleX, this.handleY, this.handleRadius, 0, Math.PI * 2);
    const grad = this.ctx.createRadialGradient(
      this.handleX - this.handleRadius * 0.25, this.handleY - this.handleRadius * 0.25, 2,
      this.handleX, this.handleY, this.handleRadius
    );
    grad.addColorStop(0, '#22d3ee');
    grad.addColorStop(0.7, '#0891b2');
    grad.addColorStop(1, '#0e7490');
    this.ctx.fillStyle = grad;
    this.ctx.fill();
    this.ctx.lineWidth = 2;
    this.ctx.strokeStyle = '#ffffff';
    this.ctx.stroke();

    // Center cap accent dot
    this.ctx.beginPath();
    this.ctx.arc(this.handleX, this.handleY, 3.5, 0, Math.PI * 2);
    this.ctx.fillStyle = '#ffffff';
    this.ctx.fill();
  }
}
