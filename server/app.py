"""
SAM Rover - Main FastAPI Application
"""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from core.config import config_manager
from core.hardware_manager import hw_manager
from server.routes import video, teleop, hardware, network, health, metrics

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("====================================================")
    print("   SAM Rover Core Services Starting...")
    print(f"   Platform: {'Simulation (Mock)' if config_manager.is_mock else 'Hardware (RPi)'}")
    print("====================================================")
    yield
    print("[Shutdown] Stopping SAM Rover services...")
    hw_manager.shutdown()


app = FastAPI(
    title="SAM Rover Teleoperation & Autonomy",
    version=config_manager.get("system", "version", default="2.0.0"),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Files and Templates
static_dir = BASE_DIR / "static"
templates_dir = BASE_DIR / "templates"
static_dir.mkdir(parents=True, exist_ok=True)
templates_dir.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))

# Include API Routers
app.include_router(video.router)
app.include_router(teleop.router)
app.include_router(hardware.router)
app.include_router(network.router)
app.include_router(health.router)
app.include_router(metrics.router)


import json

@app.get("/")
def index(request: Request):
    """Renders the main robotics teleoperation dashboard."""
    telemetry = hw_manager.get_telemetry()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "rover_name": config_manager.get("system", "name", default="SAM"),
            "version": config_manager.get("system", "version", default="2.0.0"),
            "is_mock": config_manager.is_mock,
            "initial_telemetry": telemetry,
            "json_initial_telemetry": json.dumps(telemetry),
        },
    )



if __name__ == "__main__":
    import uvicorn
    host = config_manager.get("system", "host", default="0.0.0.0")
    port = config_manager.get("system", "port", default=8000)
    uvicorn.run("server.app:app", host=host, port=port, reload=False)
