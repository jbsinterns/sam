"""
SAM Rover - Video Streaming Routes
Provides high-efficiency, zero-overhead MJPEG streaming for HTML5 and mobile teleoperation.
"""

import time
import asyncio
from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
from core.hardware_manager import hw_manager

router = APIRouter(prefix="/api/video", tags=["Video"])


async def generate_frames():
    """Asynchronous generator yielding multipart JPEG frames with low latency and zero duplicate transmissions."""
    last_frame_sent = None

    try:
        while hw_manager._is_running:
            frame = hw_manager.camera.get_latest_frame()
            if frame is not last_frame_sent:
                last_frame_sent = frame
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
            await asyncio.sleep(0.02)
    except (asyncio.CancelledError, GeneratorExit, BrokenPipeError, ConnectionResetError):
        pass
    except Exception:
        pass


@router.get("/feed")
async def video_feed():
    """
    Dedicated async MJPEG streaming endpoint for HTML <img src='/api/video/feed'>.
    Low latency, native async socket polling on Linux (epoll) & Windows.
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
