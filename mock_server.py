import json
import logging
import math
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

BASE_DIR = Path(__file__).parent.resolve()
SENSORS_CONFIG_PATH = BASE_DIR / "sensors.json"
SYSTEM_CONFIG_PATH = BASE_DIR / "system_config.json"
LEGACY_POSITIONS_PATH = BASE_DIR / "sensor_positions.json"
LEGACY_CALIBRATION_PATH = BASE_DIR / "sensor_calibration.json"
LOG_PATH = BASE_DIR / "backend.log"
API_PREFIX = "/api"
MAX_SENSOR_ID = 100
DEFAULT_DEVICE_PORT = 8000
OFFLINE_GRACE_MS = 3000

DEFAULT_SYSTEM_CONFIG = {
    "frontend": {
        "poll_interval_ms": 1000,
        "scale": 2,
        "point_radius": 6,
        "influence_radius": 90,
        "influence_opacity": 0.26,
        "map_image": "map.png",
        "map_anchor": {"x": 800, "y": 780},
        "map_scale": 0.5,
        "outside_color": "#d7dde7",
        "axis_color": "rgba(140, 154, 179, 0.45)",
        "show_labels": True,
        "glow_intensity": 1,
        "grid_enabled": False,
        "legend": [
            {"label": "低噪音", "color": [0, 200, 0], "desc": "< 55"},
            {"label": "中噪音", "color": [255, 200, 0], "desc": "55 - 75"},
            {"label": "高噪音", "color": [255, 0, 0], "desc": ">= 75"},
        ],
    }
}

DEFAULT_SENSORS_CONFIG = {
    "defaults": {
        "enabled": True,
        "label_prefix": "传感器 ",
        "report_interval_ms": 1000,
        "x": 0,
        "y": 0,
        "reference_raw_rms": 120.0,
        "reference_db": 60.0,
        "noise_floor_raw_rms": 8.0,
        "min_db": 30.0,
        "max_db": 130.0,
    },
    "thresholds": [
        {"max": 55.0, "rgb": [0, 200, 0], "name": "green"},
        {"max": 75.0, "rgb": [255, 200, 0], "name": "yellow"},
        {"max": 1000000.0, "rgb": [255, 0, 0], "name": "red"},
    ],
    "sensors": {},
}

runtime_lock = threading.Lock()
config_lock = threading.Lock()
runtime_state: dict[int, dict[str, Any]] = {}
system_config: dict[str, Any] = {}
sensors_config: dict[str, Any] = {}

logger = logging.getLogger("cas-noise-backend")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

app = FastAPI(title="CAS Noise Map Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["*"],
)


def deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def read_json_file(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return deep_copy(default)

    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass
    return deep_copy(default)


def build_legacy_sensor_config() -> dict[str, Any]:
    merged = deep_copy(DEFAULT_SENSORS_CONFIG)
    positions_raw = read_json_file(LEGACY_POSITIONS_PATH, {}) if LEGACY_POSITIONS_PATH.exists() else {}
    calibration_raw = read_json_file(LEGACY_CALIBRATION_PATH, {}) if LEGACY_CALIBRATION_PATH.exists() else {}

    if isinstance(calibration_raw.get("default"), dict):
        merged["defaults"].update(calibration_raw["default"])
    if isinstance(calibration_raw.get("thresholds"), list) and calibration_raw["thresholds"]:
        merged["thresholds"] = calibration_raw["thresholds"]

    legacy_sensors = calibration_raw.get("sensors", {}) if isinstance(calibration_raw, dict) else {}

    all_ids = set()
    if isinstance(positions_raw, dict):
        all_ids.update(positions_raw.keys())
    if isinstance(legacy_sensors, dict):
        all_ids.update(legacy_sensors.keys())

    for raw_id in sorted(all_ids, key=lambda value: int(value)):
        sensor_id = int(raw_id)
        sensor = make_default_sensor(sensor_id)
        if isinstance(positions_raw, dict) and isinstance(positions_raw.get(raw_id), dict):
            pos = positions_raw[raw_id]
            sensor["x"] = float(pos.get("x", sensor["x"]))
            sensor["y"] = float(pos.get("y", sensor["y"]))
            label = str(pos.get("label", "")).strip()
            if label:
                sensor["label"] = label
        if isinstance(legacy_sensors, dict) and isinstance(legacy_sensors.get(raw_id), dict):
            sensor.update(legacy_sensors[raw_id])
        merged["sensors"][str(sensor_id)] = normalize_sensor_config(sensor_id, sensor)
    return merged


def load_system_config() -> dict[str, Any]:
    loaded = read_json_file(SYSTEM_CONFIG_PATH, DEFAULT_SYSTEM_CONFIG)
    merged = deep_copy(DEFAULT_SYSTEM_CONFIG)
    if isinstance(loaded.get("frontend"), dict):
        merged["frontend"].update(loaded["frontend"])
    return merged


def load_sensors_config() -> dict[str, Any]:
    if SENSORS_CONFIG_PATH.exists():
        loaded = read_json_file(SENSORS_CONFIG_PATH, DEFAULT_SENSORS_CONFIG)
    else:
        loaded = build_legacy_sensor_config()
        SENSORS_CONFIG_PATH.write_text(json.dumps(loaded, ensure_ascii=False, indent=2), encoding="utf-8")

    merged = deep_copy(DEFAULT_SENSORS_CONFIG)
    if isinstance(loaded.get("defaults"), dict):
        merged["defaults"].update(loaded["defaults"])
    if isinstance(loaded.get("thresholds"), list) and loaded["thresholds"]:
        merged["thresholds"] = loaded["thresholds"]
    if isinstance(loaded.get("sensors"), dict):
        for raw_id, value in loaded["sensors"].items():
            try:
                sensor_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if isinstance(value, dict):
                merged["sensors"][str(sensor_id)] = normalize_sensor_config(sensor_id, value)
    return merged


def save_system_config() -> None:
    with config_lock:
        SYSTEM_CONFIG_PATH.write_text(json.dumps(system_config, ensure_ascii=False, indent=2), encoding="utf-8")


def save_sensors_config() -> None:
    with config_lock:
        SENSORS_CONFIG_PATH.write_text(json.dumps(sensors_config, ensure_ascii=False, indent=2), encoding="utf-8")


def make_default_sensor(sensor_id: int) -> dict[str, Any]:
    defaults = DEFAULT_SENSORS_CONFIG["defaults"]
    return {
        "id": sensor_id,
        "enabled": bool(defaults["enabled"]),
        "label": f"{defaults['label_prefix']}{sensor_id}",
        "x": float(defaults["x"]),
        "y": float(defaults["y"]),
        "report_interval_ms": int(defaults["report_interval_ms"]),
        "reference_raw_rms": float(defaults["reference_raw_rms"]),
        "reference_db": float(defaults["reference_db"]),
        "noise_floor_raw_rms": float(defaults["noise_floor_raw_rms"]),
        "min_db": float(defaults["min_db"]),
        "max_db": float(defaults["max_db"]),
    }


def normalize_sensor_config(sensor_id: int, raw: dict[str, Any]) -> dict[str, Any]:
    sensor = make_default_sensor(sensor_id)
    sensor["enabled"] = bool(raw.get("enabled", sensor["enabled"]))
    label = str(raw.get("label", sensor["label"]))
    sensor["label"] = label.strip() or sensor["label"]
    sensor["x"] = float(raw.get("x", sensor["x"]))
    sensor["y"] = float(raw.get("y", sensor["y"]))
    sensor["report_interval_ms"] = max(200, int(raw.get("report_interval_ms", sensor["report_interval_ms"])))
    sensor["reference_raw_rms"] = max(1.0, float(raw.get("reference_raw_rms", sensor["reference_raw_rms"])))
    sensor["reference_db"] = float(raw.get("reference_db", sensor["reference_db"]))
    sensor["noise_floor_raw_rms"] = max(0.0, float(raw.get("noise_floor_raw_rms", sensor["noise_floor_raw_rms"])))
    sensor["min_db"] = float(raw.get("min_db", sensor["min_db"]))
    sensor["max_db"] = float(raw.get("max_db", sensor["max_db"]))
    if sensor["max_db"] < sensor["min_db"]:
        sensor["max_db"] = sensor["min_db"]
    return sensor


def get_sensor_config(sensor_id: int, create: bool = False) -> dict[str, Any] | None:
    key = str(sensor_id)
    sensor = sensors_config["sensors"].get(key)
    if sensor is None and create:
        sensor = make_default_sensor(sensor_id)
        sensors_config["sensors"][key] = sensor
        save_sensors_config()
    return sensor


def merge_sensor_patch(sensor_id: int, patch: dict[str, Any]) -> dict[str, Any]:
    current = deep_copy(get_sensor_config(sensor_id, create=True))
    current.update(patch)
    normalized = normalize_sensor_config(sensor_id, current)
    sensors_config["sensors"][str(sensor_id)] = normalized
    save_sensors_config()
    return normalized


def sensor_online(sensor_id: int, sensor: dict[str, Any], runtime: dict[str, Any] | None) -> bool:
    if not runtime or runtime.get("last_seen") is None:
        return False
    report_interval_ms = int(sensor.get("report_interval_ms", DEFAULT_SENSORS_CONFIG["defaults"]["report_interval_ms"]))
    offline_after = max(3000, report_interval_ms * 3 + OFFLINE_GRACE_MS) / 1000.0
    return (time.time() - float(runtime["last_seen"])) <= offline_after


def get_thresholds() -> list[dict[str, Any]]:
    thresholds = sensors_config.get("thresholds", DEFAULT_SENSORS_CONFIG["thresholds"])
    return thresholds if isinstance(thresholds, list) else DEFAULT_SENSORS_CONFIG["thresholds"]


def raw_rms_to_db(raw_rms: float, sensor: dict[str, Any]) -> float:
    if raw_rms <= 0:
        return float(sensor["min_db"])
    noise_floor = float(sensor["noise_floor_raw_rms"])
    effective_raw = max(raw_rms - noise_floor, 1.0)
    effective_reference = max(float(sensor["reference_raw_rms"]) - noise_floor, 1.0)
    db = float(sensor["reference_db"]) + 20.0 * math.log10(effective_raw / effective_reference)
    return max(float(sensor["min_db"]), min(float(sensor["max_db"]), db))


def noise_to_color(noise: float) -> dict[str, Any]:
    for rule in get_thresholds():
        try:
            max_value = float(rule["max"])
            if noise < max_value:
                return {"rgb": rule["rgb"], "level": rule["name"]}
        except (KeyError, TypeError, ValueError):
            continue
    return {"rgb": [120, 120, 120], "level": "unknown"}


def build_device_view(sensor_id: int) -> dict[str, Any]:
    sensor = get_sensor_config(sensor_id, create=True)
    with runtime_lock:
        runtime = deep_copy(runtime_state.get(sensor_id, {}))
    online = sensor_online(sensor_id, sensor, runtime)
    last_noise = runtime.get("last_noise")
    color = noise_to_color(last_noise) if last_noise is not None else {"rgb": [120, 120, 120], "level": "unknown"}
    return {
        "id": sensor_id,
        "label": sensor["label"],
        "enabled": sensor["enabled"],
        "x": sensor["x"],
        "y": sensor["y"],
        "report_interval_ms": sensor["report_interval_ms"],
        "reference_raw_rms": sensor["reference_raw_rms"],
        "reference_db": sensor["reference_db"],
        "noise_floor_raw_rms": sensor["noise_floor_raw_rms"],
        "min_db": sensor["min_db"],
        "max_db": sensor["max_db"],
        "online": online,
        "last_seen": runtime.get("last_seen"),
        "last_noise": last_noise,
        "last_raw_rms": runtime.get("last_raw_rms"),
        "sample_min": runtime.get("sample_min"),
        "sample_max": runtime.get("sample_max"),
        "device_ip": runtime.get("device_ip"),
        "device_port": runtime.get("device_port", DEFAULT_DEVICE_PORT),
        "uptime_ms": runtime.get("uptime_ms"),
        "wifi_rssi": runtime.get("wifi_rssi"),
        "last_error": runtime.get("last_error"),
        "level": color["level"],
        "rgb": color["rgb"],
    }


def build_point(sensor_id: int) -> dict[str, Any] | None:
    device = build_device_view(sensor_id)
    if not device["enabled"] or device["last_noise"] is None:
        return None
    return {
        "id": sensor_id,
        "label": device["label"],
        "x": device["x"],
        "y": device["y"],
        "noise": round(device["last_noise"], 2),
        "raw_rms": round(device["last_raw_rms"], 2) if device["last_raw_rms"] is not None else None,
        "rgb": device["rgb"],
        "level": device["level"],
        "online": device["online"],
        "last_seen": device["last_seen"],
        "device_ip": device["device_ip"],
        "report_interval_ms": device["report_interval_ms"],
    }


def frontend_config() -> dict[str, Any]:
    return deep_copy(system_config.get("frontend", DEFAULT_SYSTEM_CONFIG["frontend"]))


def parse_upload_payload(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    try:
        sensor_id = int(payload.get("id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="invalid sensor id")
    if sensor_id < 0 or sensor_id > MAX_SENSOR_ID:
        raise HTTPException(status_code=400, detail="sensor id out of range")

    parsed: dict[str, Any] = {
        "device_ip": str(payload.get("ip") or payload.get("device_ip") or "").strip() or None,
        "device_port": int(payload.get("port", DEFAULT_DEVICE_PORT) or DEFAULT_DEVICE_PORT),
        "uptime_ms": int(payload.get("uptime_ms", 0) or 0),
        "wifi_rssi": int(payload.get("wifi_rssi", 0) or 0),
        "last_error": str(payload.get("last_error", "")).strip() or None,
    }

    if payload.get("raw_rms") is not None:
        parsed["last_raw_rms"] = float(payload["raw_rms"])
    elif payload.get("rms") is not None:
        parsed["last_raw_rms"] = float(payload["rms"])
    else:
        parsed["last_raw_rms"] = None

    if payload.get("noise") is not None:
        parsed["last_noise"] = float(payload["noise"])
    else:
        parsed["last_noise"] = None

    parsed["sample_min"] = int(payload["sample_min"]) if payload.get("sample_min") is not None else None
    parsed["sample_max"] = int(payload["sample_max"]) if payload.get("sample_max") is not None else None
    return sensor_id, parsed


def apply_runtime_update(sensor_id: int, update: dict[str, Any]) -> None:
    with runtime_lock:
        current = runtime_state.get(sensor_id, {})
        current.update(update)
        current["last_seen"] = time.time()
        runtime_state[sensor_id] = current


def response_device_config(sensor_id: int) -> dict[str, Any]:
    sensor = get_sensor_config(sensor_id, create=True)
    return {
        "id": sensor_id,
        "enabled": sensor["enabled"],
        "report_interval_ms": sensor["report_interval_ms"],
        "label": sensor["label"],
        "x": sensor["x"],
        "y": sensor["y"],
    }


@app.get(f"{API_PREFIX}/frontend-config")
async def api_frontend_config():
    return frontend_config()


@app.get(f"{API_PREFIX}/config")
async def api_config():
    sensor_ids = sorted(int(key) for key in sensors_config["sensors"].keys())
    sensors = [build_device_view(sensor_id) for sensor_id in sensor_ids]
    return {
        "frontend": frontend_config(),
        "thresholds": get_thresholds(),
        "defaults": deep_copy(sensors_config.get("defaults", DEFAULT_SENSORS_CONFIG["defaults"])),
        "sensors": sensors,
    }


@app.get(f"{API_PREFIX}/points")
@app.post(f"{API_PREFIX}/points")
async def api_points():
    points = []
    for key in sorted(sensors_config["sensors"].keys(), key=int):
        point = build_point(int(key))
        if point is not None:
            points.append(point)
    return points


@app.get(f"{API_PREFIX}/devices")
async def api_devices():
    sensor_ids = sorted(int(key) for key in sensors_config["sensors"].keys())
    sensors = [build_device_view(sensor_id) for sensor_id in sensor_ids]
    return {"count": len(sensors), "sensors": sensors}


@app.get(f"{API_PREFIX}/status")
async def api_status():
    sensor_ids = sorted(int(key) for key in sensors_config["sensors"].keys())
    devices = [build_device_view(sensor_id) for sensor_id in sensor_ids]
    online_count = sum(1 for sensor in devices if sensor["online"])
    enabled_count = sum(1 for sensor in devices if sensor["enabled"])
    return {
        "registered_count": len(devices),
        "enabled_count": enabled_count,
        "online_count": online_count,
        "sensors": devices,
        "thresholds": get_thresholds(),
        "frontend": frontend_config(),
    }


@app.post(f"{API_PREFIX}/sensors")
async def api_create_sensor(request: Request):
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    try:
        sensor_id = int(payload.get("id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="invalid sensor id")
    if sensor_id < 0 or sensor_id > MAX_SENSOR_ID:
        raise HTTPException(status_code=400, detail="sensor id out of range")
    if str(sensor_id) in sensors_config["sensors"]:
        raise HTTPException(status_code=409, detail="sensor already exists")
    sensor = merge_sensor_patch(sensor_id, payload)
    return sensor


@app.patch(f"{API_PREFIX}/sensors/{{sensor_id}}")
async def api_patch_sensor(sensor_id: int, request: Request):
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    sensor = merge_sensor_patch(sensor_id, payload)
    return sensor


@app.post(f"{API_PREFIX}/sensors/{{sensor_id}}/toggle")
async def api_toggle_sensor(sensor_id: int, request: Request):
    payload = await request.json()
    enabled = bool(payload.get("enabled", True))
    sensor = merge_sensor_patch(sensor_id, {"enabled": enabled})
    return sensor


@app.delete(f"{API_PREFIX}/sensors/{{sensor_id}}")
async def api_delete_sensor(sensor_id: int):
    removed = sensors_config["sensors"].pop(str(sensor_id), None)
    if removed is None:
        raise HTTPException(status_code=404, detail="sensor not found")
    with runtime_lock:
        runtime_state.pop(sensor_id, None)
    save_sensors_config()
    return {"status": "ok", "id": sensor_id}


@app.patch(f"{API_PREFIX}/frontend-config")
async def api_patch_frontend_config(request: Request):
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    frontend = system_config.setdefault("frontend", deep_copy(DEFAULT_SYSTEM_CONFIG["frontend"]))
    frontend.update(payload)
    save_system_config()
    return frontend


@app.patch(f"{API_PREFIX}/thresholds")
async def api_patch_thresholds(request: Request):
    payload = await request.json()
    thresholds = payload.get("thresholds") if isinstance(payload, dict) else None
    if not isinstance(thresholds, list) or not thresholds:
        raise HTTPException(status_code=400, detail="invalid thresholds")
    sensors_config["thresholds"] = thresholds
    save_sensors_config()
    return {"thresholds": thresholds}


@app.post(f"{API_PREFIX}/upload")
async def api_upload(request: Request):
    try:
        payload = await request.json()
    except Exception:
        logger.warning("upload rejected: invalid json from %s", request.client.host if request.client else "unknown")
        return JSONResponse(status_code=400, content={"error": "invalid json"})
    if not isinstance(payload, dict):
        logger.warning("upload rejected: invalid payload type from %s", request.client.host if request.client else "unknown")
        return JSONResponse(status_code=400, content={"error": "invalid payload"})

    sensor_id, parsed = parse_upload_payload(payload)
    sensor = get_sensor_config(sensor_id, create=True)
    if parsed["last_noise"] is None and parsed["last_raw_rms"] is not None:
        parsed["last_noise"] = raw_rms_to_db(parsed["last_raw_rms"], sensor)
    apply_runtime_update(sensor_id, parsed)
    logger.info(
        "upload ok sensor=%s ip=%s raw_rms=%s noise=%s min=%s max=%s rssi=%s enabled=%s interval_ms=%s",
        sensor_id,
        parsed.get("device_ip"),
        parsed.get("last_raw_rms"),
        parsed.get("last_noise"),
        parsed.get("sample_min"),
        parsed.get("sample_max"),
        parsed.get("wifi_rssi"),
        sensor.get("enabled"),
        sensor.get("report_interval_ms"),
    )
    return {"status": "ok", "device": response_device_config(sensor_id)}


@app.get(f"{API_PREFIX}/device-config")
async def api_device_config(id: int):
    return response_device_config(id)


def main() -> None:
    global system_config, sensors_config
    system_config = load_system_config()
    sensors_config = load_sensors_config()

    logger.info("backend starting host=0.0.0.0 port=9880 log=%s", LOG_PATH)
    logger.info("loaded config sensors=%s", len(sensors_config.get("sensors", {})))

    config = uvicorn.Config(app, host="0.0.0.0", port=9880, log_level="info")
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
