"""
SAM Rover - Video Streaming Routes
Provides high-efficiency, zero-overhead MJPEG streaming for HTML5 and mobile teleoperation.
"""

import time
from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
from core.hardware_manager import hw_manager

router = APIRouter(prefix="/api/video", tags=["Video"])


def generate_frames():
    """Generator yielding multipart JPEG frames for low-overhead browser streaming."""
    fps = hw_manager.camera.fps or 25
    frame_interval = 1.0 / fps

    try:
        while hw_manager._is_running:
            start_time = time.time()
            frame = hw_manager.camera.get_latest_frame()

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )

            elapsed = time.time() - start_time
            sleep_time = max(0.005, frame_interval - elapsed)
            time.sleep(sleep_time)
    except (GeneratorExit, BrokenPipeError, ConnectionResetError):
        pass
    except Exception as e:
        pass


@router.get("/feed")
def video_feed():
    """
    Dedicated MJPEG streaming endpoint for HTML <img src='/api/video/feed'>.
    Low latency, sharp resolution, and zero complex signaling.
    """
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/snapshot")
def video_snapshot():
    """Returns a single latest JPEG frame capture."""
    frame = hw_manager.camera.get_latest_frame()
    return Response(content=frame, media_type="image/jpeg")


@router.get("/capabilities")
def video_capabilities():
    """Returns video transmission protocol status."""
    return {
        "mjpeg": True,
        "default": "mjpeg",
        "resolution": f"{hw_manager.camera.width}x{hw_manager.camera.height}",
        "fps": hw_manager.camera.fps,
    }


@router.get("/status")
def video_status():
    """Returns camera diagnostic status."""
    return hw_manager.camera.get_status()
