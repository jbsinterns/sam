"""
SAM Rover - USB Camera Manager with Auto-Detection & Resilient Fallback
Scans for functional USB webcams. If absent or disconnected, automatically
generates a simulated telemetry HUD test card without crashing the server.
"""

import time
import platform
import threading
from typing import Dict, Any, Optional

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    cv2 = None
    np = None
    HAS_CV2 = False


def _open_capture(idx: int) -> Optional[Any]:
    """Opens platform-optimized video capture (CAP_V4L2 for Linux Pi, CAP_DSHOW for Windows)."""
    if not HAS_CV2 or cv2 is None:
        return None
    try:
        sys_name = platform.system()
        if sys_name == "Windows":
            return cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        elif sys_name == "Linux":
            return cv2.VideoCapture(idx, cv2.CAP_V4L2)
    except Exception:
        pass
    return cv2.VideoCapture(idx)

FALLBACK_EMPTY_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06"
    b"\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14"
    b"\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' \",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00"
    b"\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01"
    b"\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda"
    b"\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
)


class CameraManager:
    """
    Manages USB webcam video capture in a dedicated thread.
    Auto-detects available video indices.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.width = config.get("width", 1280)
        self.height = config.get("height", 720)
        self.fps = config.get("fps", 25)
        self.jpeg_quality = config.get("jpeg_quality", 80)
        self.preferred_index = config.get("preferred_index", 0)

        self.cap: Optional[cv2.VideoCapture] = None
        self.active_index: Optional[int] = None
        self.is_running = False
        self.last_frame_bytes: Optional[bytes] = None
        self.last_raw_frame: Optional[Any] = None
        self.last_frame_time = 0.0
        self._last_init_attempt = 0.0

        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._mock_counter = 0

    def start(self) -> None:
        """Starts background frame acquisition thread with immediate hardware re-initialization."""
        with self._lifecycle_lock:
            if self.is_running:
                return
            self.is_running = True
            self._last_init_attempt = time.time()
            self._init_camera()
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stops capture thread and releases camera cleanly."""
        with self._lifecycle_lock:
            if not self.is_running:
                self._release_camera()
                return
            self.is_running = False
            t = self._thread
            if t and t.is_alive():
                t.join(timeout=0.6)
            self._release_camera()
            self._thread = None

    def _auto_detect_camera(self) -> Optional[int]:
        """
        Scans indices [preferred, 0, 1, 2, 3] to find an active camera.
        """
        if not HAS_CV2 or cv2 is None:
            return None
        candidates = [self.preferred_index] + [i for i in range(4) if i != self.preferred_index]
        for idx in candidates:
            try:
                cap = _open_capture(idx)
                if cap and cap.isOpened():
                    ret, _ = cap.read()
                    if ret:
                        cap.release()
                        print(f"[Camera] Successfully auto-detected camera at index {idx}")
                        return idx
                if cap:
                    cap.release()
            except Exception:
                continue
        return None

    def test_camera_port(self) -> Optional[int]:
        """
        Tests and detects active camera port on boot without leaving stream open.
        Guarantees physical device (/dev/video0) is released immediately.
        """
        detected_idx = self._auto_detect_camera()
        if detected_idx is not None:
            self.preferred_index = detected_idx
            print(f"[Camera] Probe complete: Port {detected_idx} validated (camera released, waiting for UI claim).")
        else:
            print("[Camera] Probe complete: No physical camera detected (HUD standby mode ready).")
        return detected_idx

    def _init_camera(self) -> bool:
        """Attempts to open physical camera; returns False if not found."""
        cam_idx = self._auto_detect_camera()
        if cam_idx is None:
            self.active_index = None
            return False

        try:
            self.cap = _open_capture(cam_idx)
            if self.cap is None or not self.cap.isOpened():
                self.active_index = None
                return False

            # Dynamically request 1280x720 HD widescreen
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            
            # Read actual negotiated hardware resolution
            actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if actual_w > 0 and actual_h > 0:
                self.width = actual_w
                self.height = actual_h
                print(f"[Camera] Dynamically negotiated resolution: {self.width}x{self.height} @ {self.fps}FPS")

            self.active_index = cam_idx
            return True
        except Exception as e:
            print(f"[Camera] Failed to open index {cam_idx}: {e}")
            self.active_index = None
            return False

    def _release_camera(self) -> None:
        with self._lock:
            if self.cap:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
            self.active_index = None

    def _create_synthetic_raw(self) -> Any:
        """Generates synthetic raw BGR frame numpy array."""
        if not HAS_CV2 or cv2 is None or np is None:
            return np.zeros((self.height, self.width, 3), dtype=np.uint8) if np is not None else None

        self._mock_counter += 1
        img = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        # Background gradient grid
        img[:] = (20, 24, 33)
        grid_color = (35, 42, 58)
        step = 40
        for x in range(0, self.width, step):
            cv2.line(img, (x, 0), (x, self.height), grid_color, 1)
        for y in range(0, self.height, step):
            cv2.line(img, (0, y), (self.width, y), grid_color, 1)

        # Crosshair HUD
        cx, cy = self.width // 2, self.height // 2
        cv2.circle(img, (cx, cy), 60, (0, 180, 240), 1)
        cv2.circle(img, (cx, cy), 15, (0, 240, 200), -1)
        cv2.line(img, (cx - 80, cy), (cx + 80, cy), (0, 180, 240), 1)
        cv2.line(img, (cx, cy - 80), (cx, cy + 80), (0, 180, 240), 1)

        # Text HUD
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(img, "SAM ROVER // VISION SUBSYSTEM", (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 220, 255), 2)
        cv2.putText(img, "STATUS: HARDWARE RELEASED / DEV/VIDEO0 FREE", (20, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 200, 255), 1)
        cv2.putText(img, f"TIMESTAMP: {ts}", (20, self.height - 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 180, 200), 1)
        cv2.putText(img, f"RES: {self.width}x{self.height} @ {self.fps}FPS", (self.width - 220, self.height - 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 180, 200), 1)

        return img

    def _create_synthetic_frame(self) -> bytes:
        """Generates a synthetic telemetry HUD JPEG pattern when physical camera is absent."""
        if not HAS_CV2 or cv2 is None or np is None:
            return FALLBACK_EMPTY_JPEG

        img = self._create_synthetic_raw()
        _, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        return jpeg.tobytes()

    def _capture_loop(self) -> None:
        """Dedicated background loop that updates current frame buffer."""
        consecutive_failures = 0

        # Attempt immediate camera initialization if not opened yet
        if self.cap is None:
            self._init_camera()

        try:
            while self.is_running:
                frame_bytes: Optional[bytes] = None
                raw_frame: Optional[Any] = None

                # Attempt capture if camera is open
                cap = self.cap
                if cap and cap.isOpened():
                    ret, frame = cap.read()
                    if not self.is_running:
                        break
                    if ret and frame is not None:
                        consecutive_failures = 0
                        raw_frame = frame
                        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
                        frame_bytes = jpeg.tobytes()
                    else:
                        consecutive_failures += 1
                        if consecutive_failures > 5:
                            print("[Camera] Physical stream lost. Re-detecting...")
                            self._release_camera()

                # If no physical camera active, attempt to re-open every 2.0 seconds
                if frame_bytes is None:
                    now = time.time()
                    if self.cap is None and (now - self._last_init_attempt > 2.0):
                        self._last_init_attempt = now
                        self._init_camera()
                    raw_frame = self._create_synthetic_raw()
                    if HAS_CV2 and cv2 is not None and raw_frame is not None:
                        _, jpeg = cv2.imencode(".jpg", raw_frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
                        frame_bytes = jpeg.tobytes()
                    else:
                        frame_bytes = FALLBACK_EMPTY_JPEG

                with self._lock:
                    self.last_frame_bytes = frame_bytes
                    self.last_raw_frame = raw_frame
                    self.last_frame_time = time.time()

                time.sleep(1.0 / self.fps)
        finally:
            self._release_camera()

    def get_latest_frame(self) -> bytes:
        """Returns the most recent JPEG frame safely."""
        with self._lock:
            if self.last_frame_bytes is not None:
                return self.last_frame_bytes
        return self._create_synthetic_frame()

    def get_latest_raw_frame(self) -> Any:
        """Returns the most recent raw BGR numpy ndarray for computer vision or analysis."""
        with self._lock:
            if self.last_raw_frame is not None:
                return self.last_raw_frame
        return self._create_synthetic_raw()

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_running": self.is_running,
            "has_physical_cam": self.active_index is not None,
            "active_index": self.active_index,
            "resolution": f"{self.width}x{self.height}",
            "fps": self.fps,
        }
