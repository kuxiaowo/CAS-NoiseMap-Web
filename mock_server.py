import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

BASE_DIR = Path(__file__).parent.resolve()
POSITIONS_PATH = BASE_DIR / "sensor_positions.json"
API_PREFIX = "/api"
POLL_INTERVAL_SECONDS = 2.0
MAX_SENSOR_ID = 100
REQUEST_TIMEOUT_SECONDS = 3

COLOR_RULES = [
    {"max": 55.0, "rgb": [0, 200, 0], "name": "green"},
    {"max": 75.0, "rgb": [255, 200, 0], "name": "yellow"},
    {"max": float("inf"), "rgb": [255, 0, 0], "name": "red"},
]


@dataclass
class SensorPosition:
    x: float
    y: float
    label: str | None = None


@dataclass
class SensorState:
    sensor_id: int
    ip: str
    port: int = 8000
    last_noise: float | None = None
    last_seen: float | None = None
    online: bool = False


state_lock = threading.Lock()
sensor_positions: dict[int, SensorPosition] = {}
sensor_states: dict[int, SensorState] = {}

app = FastAPI(title="CAS Noise Map Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def load_positions() -> dict[int, SensorPosition]:
    if not POSITIONS_PATH.exists():
        return {}

    raw = json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))
    positions: dict[int, SensorPosition] = {}
    for key, value in raw.items():
        try:
            sensor_id = int(key)
            positions[sensor_id] = SensorPosition(
                x=float(value["x"]),
                y=float(value["y"]),
                label=str(value.get("label", "")).strip() or None,
            )
        except (KeyError, TypeError, ValueError):
            continue
    return positions


def rms_to_db(rms: float) -> float:
    """
    将 RMS 值转换为分贝值（dB）
    公式：dB = 20 * log10(rms + 1.0)
    +1.0 是为了防止 log10(0) 出现
    """
    if rms < 0:
        return 0.0
    return 20.0 * math.log10(rms + 1.0)


def noise_to_color(noise: float) -> dict[str, Any]:
    for rule in COLOR_RULES:
        if noise < rule["max"]:
            return {"rgb": rule["rgb"], "level": rule["name"]}
    return {"rgb": [120, 120, 120], "level": "unknown"}


def build_point(sensor_id: int, state: SensorState) -> dict[str, Any] | None:
    position = sensor_positions.get(sensor_id)
    if not position or state.last_noise is None:
        return None

    color = noise_to_color(state.last_noise)
    return {
        "id": sensor_id,
        "label": position.label or f"Sensor {sensor_id}",
        "x": position.x,
        "y": position.y,
        "noise": round(state.last_noise, 2),
        "rgb": color["rgb"],
        "level": color["level"],
        "online": state.online,
        "last_seen": state.last_seen,
        "ip": state.ip,
        "port": state.port,
    }


def collect_points() -> list[dict[str, Any]]:
    with state_lock:
        points = []
        for sensor_id in sorted(sensor_states.keys()):
            point = build_point(sensor_id, sensor_states[sensor_id])
            if point is not None:
                points.append(point)
        return points


def collect_status() -> dict[str, Any]:
    with state_lock:
        registered = []
        for sensor_id in sorted(sensor_states.keys()):
            state = sensor_states[sensor_id]
            registered.append(
                {
                    "id": sensor_id,
                    "ip": state.ip,
                    "port": state.port,
                    "online": state.online,
                    "last_noise": state.last_noise,
                    "last_seen": state.last_seen,
                    "has_position": sensor_id in sensor_positions,
                }
            )
        return {
            "registered_count": len(sensor_states),
            "positioned_count": sum(1 for sensor_id in sensor_states if sensor_id in sensor_positions),
            "sensors": registered,
        }


@app.post(f"{API_PREFIX}/register")
async def register_sensor(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid json"})

    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"error": "invalid payload"})

    try:
        sensor_id = int(payload.get("id"))
        ip = str(payload.get("ip", "")).strip()
        port = int(payload.get("port", 8000))
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "invalid id, ip, or port"})

    if sensor_id < 0 or sensor_id > MAX_SENSOR_ID:
        return JSONResponse(status_code=400, content={"error": "id out of range"})
    if not ip:
        return JSONResponse(status_code=400, content={"error": "missing ip"})
    if port <= 0 or port > 65535:
        return JSONResponse(status_code=400, content={"error": "invalid port"})

    with state_lock:
        existing = sensor_states.get(sensor_id)
        if existing is None:
            sensor_states[sensor_id] = SensorState(sensor_id=sensor_id, ip=ip, port=port)
        else:
            existing.ip = ip
            existing.port = port

    return {"status": "ok", "id": sensor_id, "ip": ip, "port": port}


@app.get(f"{API_PREFIX}/points")
@app.post(f"{API_PREFIX}/points")
async def api_points():
    return collect_points()


@app.get(f"{API_PREFIX}/status")
async def api_status():
    return collect_status()


@app.get(f"{API_PREFIX}/devices")
async def api_devices():
    with state_lock:
        registered = []
        for sensor_id in sorted(sensor_states.keys()):
            state = sensor_states[sensor_id]
            registered.append(
                {
                    "id": sensor_id,
                    "ip": state.ip,
                    "port": state.port,
                    "online": state.online,
                    "last_noise": state.last_noise,
                    "last_seen": state.last_seen,
                    "has_position": sensor_id in sensor_positions,
                }
            )
    return {"sensors": registered, "count": len(registered)}


def fetch_sensor_noise(ip: str, port: int) -> tuple[int | None, float | None]:
    """
    从传感器获取 RMS 值或原始 dB 值
    兼容两种格式：
    1. 新格式（推荐）: {"id": 1, "rms": 0.1234}  → 转换为 dB
    2. 旧格式（兼容）: {"id": 1, "noise": 55.3}  → 直接使用
    """
    try:
        response = requests.get(f"http://{ip}:{port}/noise", timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None, None

    if not isinstance(payload, dict):
        return None, None

    try:
        sensor_id = int(payload.get("id"))
        
        # 优先尝试读取 RMS 值（新格式）
        if "rms" in payload:
            rms = float(payload.get("rms"))
            noise_db = rms_to_db(rms)
            return sensor_id, noise_db
        # 其次读取 noise 值（旧格式，兼容）
        elif "noise" in payload:
            noise = float(payload.get("noise"))
            return sensor_id, noise
        else:
            return None, None
    except (TypeError, ValueError):
        return None, None

    return sensor_id, None


def poll_loop() -> None:
    while True:
        started_at = time.monotonic()
        with state_lock:
            targets = [(sensor_id, state.ip, state.port) for sensor_id, state in sensor_states.items() if state.ip]

        if targets:
            with ThreadPoolExecutor(max_workers=min(20, len(targets))) as executor:
                futures = {
                    executor.submit(fetch_sensor_noise, ip, port): known_id
                    for known_id, ip, port in targets
                }
                for future, known_id in futures.items():
                    fetched_id, noise = future.result()
                    now = time.time()
                    with state_lock:
                        state = sensor_states.get(known_id)
                        if state is None:
                            continue
                        if fetched_id is None or noise is None:
                            state.online = False
                            continue
                        state.last_noise = noise
                        state.last_seen = now
                        state.online = True

        elapsed = time.monotonic() - started_at
        time.sleep(max(0.0, POLL_INTERVAL_SECONDS - elapsed))


def main() -> None:
    global sensor_positions
    sensor_positions = load_positions()

    poller = threading.Thread(target=poll_loop, daemon=True)
    poller.start()

    config = uvicorn.Config(app, host="0.0.0.0", port=9880, log_level="info")
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
