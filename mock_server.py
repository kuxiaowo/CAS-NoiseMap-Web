import math
import threading

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

MAX_ID = 100
GREEN_MAX = 55
YELLOW_MAX = 75

GREEN_RGB = [0, 200, 0]
YELLOW_RGB = [255, 200, 0]
RED_RGB = [255, 0, 0]

COORD_RADIUS = 220

NOISE_VALUES = [None] * (MAX_ID + 1)
X_COORDS = [0] * (MAX_ID + 1)
Y_COORDS = [0] * (MAX_ID + 1)
LOCK = threading.Lock()

TOTAL_POINTS = MAX_ID + 1
for idx in range(TOTAL_POINTS):
    angle = 2 * math.pi * idx / TOTAL_POINTS
    X_COORDS[idx] = int(round(COORD_RADIUS * math.cos(angle)))
    Y_COORDS[idx] = int(round(COORD_RADIUS * math.sin(angle)))


def noise_to_rgb(noise: float) -> list[int]:
    if noise < GREEN_MAX:
        return GREEN_RGB
    if noise < YELLOW_MAX:
        return YELLOW_RGB
    return RED_RGB


def collect_points() -> list[dict]:
    points = []
    for idx in range(TOTAL_POINTS):
        noise = NOISE_VALUES[idx]
        if noise is None:
            continue
        points.append(
            {
                "id": idx,
                "x": X_COORDS[idx],
                "y": Y_COORDS[idx],
                "rgb": noise_to_rgb(noise),
            }
        )
    return points


sensor_app = FastAPI()
frontend_app = FastAPI()
frontend_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)


@sensor_app.post("/data")
async def receive_data(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid json"})
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"error": "invalid payload"})
    if "id" not in payload or "noise" not in payload:
        return JSONResponse(status_code=400, content={"error": "missing id or noise"})
    try:
        idx = int(payload["id"])
        noise = float(payload["noise"])
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "invalid id or noise type"})
    if idx < 0 or idx > MAX_ID:
        return JSONResponse(status_code=400, content={"error": "id out of range"})
    with LOCK:
        NOISE_VALUES[idx] = noise
    return {"status": "ok"}


@frontend_app.post("/post")
async def post_points():
    with LOCK:
        points = collect_points()
    return points


def run_server(app: FastAPI, host: str, port: int) -> None:
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


def main() -> None:
    sensor_thread = threading.Thread(
        target=run_server, args=(sensor_app, "0.0.0.0", 9660)
    )
    frontend_thread = threading.Thread(
        target=run_server, args=(frontend_app, "127.0.0.1", 9770)
    )
    sensor_thread.start()
    frontend_thread.start()
    sensor_thread.join()
    frontend_thread.join()


if __name__ == "__main__":
    main()