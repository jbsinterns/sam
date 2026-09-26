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
    this.handleX = this.centerX;
    this.handleY = this.centerY;
    this.isDragging = false;

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
    this.radius = size * 0.42;
    this.handleRadius = size * 0.17;
    if (!this.isDragging) {
      this.handleX = this.centerX;
      this.handleY = this.centerY;
    }
    this.draw();
  }

  _bindEvents() {
    // Touch Events
    this.canvas.addEventListener('touchstart', (e) => this._onTouchStart(e), { passive: false });
    this.canvas.addEventListener('touchmove', (e) => this._onTouchMove(e), { passive: false });
    this.canvas.addEventListener('touchend', (e) => this._onTouchEnd(e), { passive: false });
    this.canvas.addEventListener('touchcancel', (e) => this._onTouchEnd(e), { passive: false });

    // Mouse Fallback
    this.canvas.addEventListener('mousedown', (e) => this._onMouseDown(e));
    window.addEventListener('mousemove', (e) => this._onMouseMove(e));
    window.addEventListener('mouseup', () => this._onMouseUp());

    // Explicitly prevent context menu on right click or touch long-press
    this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());
  }

  _getTouchPos(touch) {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: touch.clientX - rect.left,
      y: touch.clientY - rect.top,
    };
  }

  _onTouchStart(e) {
    e.preventDefault();
    if (this.isDragging) return;
    const touch = e.changedTouches[0];
    this.touchId = touch.identifier;
    this.isDragging = true;
    this._updateHandle(this._getTouchPos(touch));
  }

  _onTouchMove(e) {
    e.preventDefault();
    if (!this.isDragging) return;
    for (let i = 0; i < e.changedTouches.length; i++) {
      if (e.changedTouches[i].identifier === this.touchId) {
        this._updateHandle(this._getTouchPos(e.changedTouches[i]));
        break;
      }
    }
  }

  _onTouchEnd(e) {
    e.preventDefault();
    if (!this.isDragging) return;
    for (let i = 0; i < e.changedTouches.length; i++) {
      if (e.changedTouches[i].identifier === this.touchId) {
        this._resetHandle();
        break;
      }
    }
  }

  _onMouseDown(e) {
    if (e.button !== 0) return; // Left click only
    this.isDragging = true;
    const rect = this.canvas.getBoundingClientRect();
    this._updateHandle({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  }

  _onMouseMove(e) {
    if (!this.isDragging || this.touchId !== null) return;
    const rect = this.canvas.getBoundingClientRect();
    this._updateHandle({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  }

  _onMouseUp() {
    if (this.isDragging && this.touchId === null) {
      this._resetHandle();
    }
  }

  _updateHandle(pos) {
    const dx = pos.x - this.centerX;
    const dy = pos.y - this.centerY;
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (dist <= this.radius) {
      this.handleX = pos.x;
      this.handleY = pos.y;
    } else {
      const angle = Math.atan2(dy, dx);
      this.handleX = this.centerX + Math.cos(angle) * this.radius;
      this.handleY = this.centerY + Math.sin(angle) * this.radius;
    }

    this.draw();

    // Compute normalized coordinates: x in [-1, 1], y in [-1, 1] (forward is +y)
    const normX = (this.handleX - this.centerX) / this.radius;
    const normY = -(this.handleY - this.centerY) / this.radius;

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

    // Outer boundary ring
    this.ctx.beginPath();
    this.ctx.arc(this.centerX, this.centerY, this.radius, 0, Math.PI * 2);
    this.ctx.fillStyle = 'rgba(15, 23, 42, 0.8)';
    this.ctx.fill();
    this.ctx.lineWidth = 3;
    this.ctx.strokeStyle = 'rgba(6, 182, 212, 0.4)';
    this.ctx.stroke();

    // Cross guides
    this.ctx.beginPath();
    this.ctx.moveTo(this.centerX - this.radius, this.centerY);
    this.ctx.lineTo(this.centerX + this.radius, this.centerY);
    this.ctx.moveTo(this.centerX, this.centerY - this.radius);
    this.ctx.lineTo(this.centerX, this.centerY + this.radius);
    this.ctx.lineWidth = 1;
    this.ctx.strokeStyle = 'rgba(100, 116, 139, 0.25)';
    this.ctx.stroke();

    // Center handle
    this.ctx.beginPath();
    this.ctx.arc(this.handleX, this.handleY, this.handleRadius, 0, Math.PI * 2);
    const grad = this.ctx.createRadialGradient(
      this.handleX, this.handleY, 5,
      this.handleX, this.handleY, this.handleRadius
    );
    grad.addColorStop(0, '#06b6d4');
    grad.addColorStop(1, '#0891b2');
    this.ctx.fillStyle = grad;
    this.ctx.fill();
    this.ctx.lineWidth = 2;
    this.ctx.strokeStyle = '#ffffff';
    this.ctx.stroke();
  }
}
