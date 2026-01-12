import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import requests
import uvicorn

MAX_ID = 100
GREEN_MAX = 55
YELLOW_MAX = 75

GREEN_RGB = [0, 200, 0]
YELLOW_RGB = [255, 200, 0]
RED_RGB = [255, 0, 0]

COORD_RADIUS = 220

NOISE_VALUES = [None] * (MAX_ID + 1)
SENSOR_IPS = [None] * (MAX_ID + 1)
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


API_PREFIX = "/api"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

def format_status() -> str:
    with LOCK:
        registrations = [
            (idx, ip)
            for idx, ip in enumerate(SENSOR_IPS)
            if ip
        ]
        readings = [
            (idx, NOISE_VALUES[idx])
            for idx, _ in registrations
            if NOISE_VALUES[idx] is not None
        ]
    reg_text = ", ".join([f"{idx}:{ip}" for idx, ip in registrations]) or "none"
    noise_text = ", ".join([f"{idx}:{noise}" for idx, noise in readings]) or "none"
    return f"registered=[{reg_text}] noise=[{noise_text}]"


@app.post(f"{API_PREFIX}/register")
async def register_sensor(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid json"})
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"error": "invalid payload"})
    if "id" not in payload or "ip" not in payload:
        return JSONResponse(status_code=400, content={"error": "missing id or ip"})
    try:
        idx = int(payload["id"])
        ip = str(payload["ip"]).strip()
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "invalid id or ip type"})
    if idx < 0 or idx > MAX_ID:
        return JSONResponse(status_code=400, content={"error": "id out of range"})
    with LOCK:
        SENSOR_IPS[idx] = ip
    print(f"[register] {SENSOR_IPS}")
    return {"status": "ok"}


@app.post(f"{API_PREFIX}/points")
async def post_points():
    with LOCK:
        points = collect_points()
    return points


def run_server(app: FastAPI, host: str, port: int) -> None:
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


def fetch_noise(ip: str) -> tuple[int | None, float | None]:
    try:
        response = requests.get(f"http://{ip}:8000/noise", timeout=3)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None, None

    if not isinstance(payload, dict):
        return None, None
    try:
        idx = int(payload.get("id"))
        noise = float(payload.get("noise"))
    except (TypeError, ValueError):
        return None, None
    if idx < 0 or idx > MAX_ID:
        return None, None
    return idx, noise


def poll_sensors() -> None:
    while True:
        start = time.monotonic()
        with LOCK:
            targets = [(idx, ip) for idx, ip in enumerate(SENSOR_IPS) if ip]

        if targets:
            max_workers = min(20, len(targets))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(fetch_noise, ip) for _, ip in targets]
                for future in futures:
                    idx, noise = future.result()
                    if idx is None:
                        continue
                    with LOCK:
                        NOISE_VALUES[idx] = noise
            print(f"[poll] {format_status()},{SENSOR_IPS}")

        elapsed = time.monotonic() - start
        time.sleep(max(0, 2 - elapsed))


def main() -> None:
    poller = threading.Thread(target=poll_sensors, daemon=True)
    poller.start()
    run_server(app, "0.0.0.0", 9880)


if __name__ == "__main__":
    main()
