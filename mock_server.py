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
CALIBRATION_PATH = BASE_DIR / "sensor_calibration.json"
API_PREFIX = "/api"
POLL_INTERVAL_SECONDS = 0.2
MAX_SENSOR_ID = 100
REQUEST_TIMEOUT_SECONDS = 3

DEFAULT_CALIBRATION = {
    "default": {
        "reference_raw_rms": 120.0,
        "reference_db": 60.0,
        "noise_floor_raw_rms": 8.0,
        "min_db": 35.0,
        "max_db": 110.0,
    },
    "thresholds": [
        {"max": 55.0, "rgb": [0, 200, 0], "name": "green"},
        {"max": 75.0, "rgb": [255, 200, 0], "name": "yellow"},
        {"max": float("inf"), "rgb": [255, 0, 0], "name": "red"},
    ],
    "sensors": {
        "1": {"reference_raw_rms": 120.0, "reference_db": 60.0, "noise_floor_raw_rms": 8.0, "min_db": 35.0, "max_db": 110.0},
        "2": {"reference_raw_rms": 120.0, "reference_db": 60.0, "noise_floor_raw_rms": 8.0, "min_db": 35.0, "max_db": 110.0},
        "3": {"reference_raw_rms": 120.0, "reference_db": 60.0, "noise_floor_raw_rms": 8.0, "min_db": 35.0, "max_db": 110.0},
        "4": {"reference_raw_rms": 120.0, "reference_db": 60.0, "noise_floor_raw_rms": 8.0, "min_db": 35.0, "max_db": 110.0},
        "5": {"reference_raw_rms": 120.0, "reference_db": 60.0, "noise_floor_raw_rms": 8.0, "min_db": 35.0, "max_db": 110.0}
    }
}


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
    last_raw_rms: float | None = None
    last_seen: float | None = None
    online: bool = False
    last_sample_min: int | None = None
    last_sample_max: int | None = None


state_lock = threading.Lock()
sensor_positions: dict[int, SensorPosition] = {}
sensor_states: dict[int, SensorState] = {}
calibration_config: dict[str, Any] = DEFAULT_CALIBRATION.copy()

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


def load_calibration() -> dict[str, Any]:
    if not CALIBRATION_PATH.exists():
        CALIBRATION_PATH.write_text(
            json.dumps(DEFAULT_CALIBRATION, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return json.loads(json.dumps(DEFAULT_CALIBRATION))

    try:
        loaded = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(DEFAULT_CALIBRATION))

    merged = json.loads(json.dumps(DEFAULT_CALIBRATION))
    if isinstance(loaded, dict):
        if isinstance(loaded.get("default"), dict):
            merged["default"].update(loaded["default"])
        if isinstance(loaded.get("thresholds"), list) and loaded["thresholds"]:
            merged["thresholds"] = loaded["thresholds"]
        if isinstance(loaded.get("sensors"), dict):
            merged["sensors"] = loaded["sensors"]
    return merged


def get_sensor_calibration(sensor_id: int) -> dict[str, float]:
    default_cfg = calibration_config.get("default", {})
    sensors_cfg = calibration_config.get("sensors", {})
    sensor_cfg = sensors_cfg.get(str(sensor_id))

    if not isinstance(sensor_cfg, dict):
        sensor_cfg = dict(default_cfg)
        sensors_cfg[str(sensor_id)] = sensor_cfg
        calibration_config["sensors"] = sensors_cfg

    cfg = {
        "reference_raw_rms": float(sensor_cfg.get("reference_raw_rms", default_cfg.get("reference_raw_rms", 120.0))),
        "reference_db": float(sensor_cfg.get("reference_db", default_cfg.get("reference_db", 60.0))),
        "noise_floor_raw_rms": float(sensor_cfg.get("noise_floor_raw_rms", default_cfg.get("noise_floor_raw_rms", 8.0))),
        "min_db": float(sensor_cfg.get("min_db", default_cfg.get("min_db", 35.0))),
        "max_db": float(sensor_cfg.get("max_db", default_cfg.get("max_db", 110.0))),
    }
    if cfg["reference_raw_rms"] <= 0:
        cfg["reference_raw_rms"] = 120.0
    if cfg["noise_floor_raw_rms"] < 0:
        cfg["noise_floor_raw_rms"] = 0.0
    return cfg


def raw_rms_to_db(raw_rms: float, sensor_id: int) -> float:
    cfg = get_sensor_calibration(sensor_id)
    if raw_rms <= 0:
        return cfg["min_db"]

    noise_floor = cfg["noise_floor_raw_rms"]
    effective_raw = max(raw_rms - noise_floor, 1.0)
    effective_reference = max(cfg["reference_raw_rms"] - noise_floor, 1.0)

    db = cfg["reference_db"] + 20.0 * math.log10(effective_raw / effective_reference)
    return max(cfg["min_db"], min(cfg["max_db"], db))


def noise_to_color(noise: float) -> dict[str, Any]:
    rules = calibration_config.get("thresholds", DEFAULT_CALIBRATION["thresholds"])
    for rule in rules:
        try:
            max_value = float(rule["max"])
            if noise < max_value:
                return {"rgb": rule["rgb"], "level": rule["name"]}
        except (KeyError, TypeError, ValueError):
            continue
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
        "raw_rms": round(state.last_raw_rms, 2) if state.last_raw_rms is not None else None,
        "rgb": color["rgb"],
        "level": color["level"],
        "online": state.online,
        "last_seen": state.last_seen,
        "ip": state.ip,
        "port": state.port,
        "sample_min": state.last_sample_min,
        "sample_max": state.last_sample_max,
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
                    "last_raw_rms": state.last_raw_rms,
                    "last_seen": state.last_seen,
                    "has_position": sensor_id in sensor_positions,
                    "sample_min": state.last_sample_min,
                    "sample_max": state.last_sample_max,
                }
            )
        return {
            "registered_count": len(sensor_states),
            "positioned_count": sum(1 for sensor_id in sensor_states if sensor_id in sensor_positions),
            "sensors": registered,
            "calibration": calibration_config,
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

    replaced_sensor_id = None
    with state_lock:
        duplicate_ids = [
            known_id
            for known_id, state in sensor_states.items()
            if state.ip == ip and known_id != sensor_id
        ]
        for duplicate_id in duplicate_ids:
            sensor_states.pop(duplicate_id, None)
            replaced_sensor_id = duplicate_id

        existing = sensor_states.get(sensor_id)
        if existing is None:
            sensor_states[sensor_id] = SensorState(sensor_id=sensor_id, ip=ip, port=port)
        else:
            existing.ip = ip
            existing.port = port

    response = {"status": "ok", "id": sensor_id, "ip": ip, "port": port}
    if replaced_sensor_id is not None:
        response["replaced_id"] = replaced_sensor_id
    return response


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
                    "last_raw_rms": state.last_raw_rms,
                    "last_seen": state.last_seen,
                    "has_position": sensor_id in sensor_positions,
                    "sample_min": state.last_sample_min,
                    "sample_max": state.last_sample_max,
                }
            )
    return {"sensors": registered, "count": len(registered)}


def fetch_sensor_noise(ip: str, port: int) -> tuple[int | None, float | None, float | None, int | None, int | None]:
    try:
        response = requests.get(f"http://{ip}:{port}/noise", timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None, None, None, None, None

    if not isinstance(payload, dict):
        return None, None, None, None, None

    try:
        sensor_id = int(payload.get("id"))

        if "raw_rms" in payload:
            raw_rms = float(payload.get("raw_rms"))
            noise_db = raw_rms_to_db(raw_rms, sensor_id)
            sample_min = int(payload.get("sample_min")) if payload.get("sample_min") is not None else None
            sample_max = int(payload.get("sample_max")) if payload.get("sample_max") is not None else None
            return sensor_id, noise_db, raw_rms, sample_min, sample_max
        elif "rms" in payload:
            legacy_rms = float(payload.get("rms"))
            noise_db = raw_rms_to_db(legacy_rms, sensor_id)
            return sensor_id, noise_db, legacy_rms, None, None
        elif "noise" in payload:
            noise = float(payload.get("noise"))
            return sensor_id, noise, None, None, None
        else:
            return None, None, None, None, None
    except (TypeError, ValueError):
        return None, None, None, None, None


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
                    fetched_id, noise, raw_rms, sample_min, sample_max = future.result()
                    now = time.time()
                    with state_lock:
                        state = sensor_states.get(known_id)
                        if state is None:
                            continue
                        if fetched_id is None or noise is None:
                            state.online = False
                            continue
                        state.last_noise = noise
                        state.last_raw_rms = raw_rms
                        state.last_sample_min = sample_min
                        state.last_sample_max = sample_max
                        state.last_seen = now
                        state.online = True

        elapsed = time.monotonic() - started_at
        time.sleep(max(0.0, POLL_INTERVAL_SECONDS - elapsed))


def main() -> None:
    global sensor_positions, calibration_config
    sensor_positions = load_positions()
    calibration_config = load_calibration()

    poller = threading.Thread(target=poll_loop, daemon=True)
    poller.start()

    config = uvicorn.Config(app, host="0.0.0.0", port=9880, log_level="info")
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
