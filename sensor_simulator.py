import argparse
import random
import socket
import threading
import time
from dataclasses import dataclass

import requests

DEFAULT_BACKEND = "http://127.0.0.1:9880"
UPLOAD_PATH = "/api/upload"
DEVICE_CONFIG_PATH = "/api/device-config"
DEFAULT_SENSOR_COUNT = 10
DEFAULT_REPORT_INTERVAL_MS = 1000
RMS_MIN = 6.0
RMS_MAX = 160.0
RMS_STEP = 12.0


@dataclass
class SensorRuntime:
    sensor_id: int
    current_rms: float
    report_interval_ms: int
    enabled: bool = True


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def get_local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


def fetch_device_config(backend: str, runtime: SensorRuntime) -> None:
    response = requests.get(
        f"{backend}{DEVICE_CONFIG_PATH}",
        params={"id": runtime.sensor_id},
        timeout=3,
    )
    response.raise_for_status()
    payload = response.json()
    runtime.enabled = bool(payload.get("enabled", True))
    runtime.report_interval_ms = max(200, int(payload.get("report_interval_ms", runtime.report_interval_ms)))


def upload_loop(runtime: SensorRuntime, backend: str, ip: str) -> None:
    rms = runtime.current_rms
    last_sync = 0.0

    while True:
        now = time.time()
        if now - last_sync >= 5:
            try:
                fetch_device_config(backend, runtime)
            except Exception:
                pass
            last_sync = now

        rms = clamp(rms + random.uniform(-RMS_STEP, RMS_STEP), RMS_MIN, RMS_MAX)
        runtime.current_rms = round(rms, 2)

        if runtime.enabled:
            payload = {
                "id": runtime.sensor_id,
                "ip": ip,
                "raw_rms": runtime.current_rms,
                "sample_min": int(-runtime.current_rms * 20),
                "sample_max": int(runtime.current_rms * 20),
                "uptime_ms": int(time.monotonic() * 1000),
                "wifi_rssi": -45,
            }
            try:
                response = requests.post(f"{backend}{UPLOAD_PATH}", json=payload, timeout=3)
                response.raise_for_status()
                response_payload = response.json()
                device = response_payload.get("device") or {}
                runtime.enabled = bool(device.get("enabled", runtime.enabled))
                runtime.report_interval_ms = max(200, int(device.get("report_interval_ms", runtime.report_interval_ms)))
            except Exception:
                pass

        time.sleep(runtime.report_interval_ms / 1000.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CAS active-upload sensor simulator")
    parser.add_argument("--backend", type=str, default=DEFAULT_BACKEND, help="Backend base URL")
    parser.add_argument("--ip", type=str, default="", help="IP to report")
    parser.add_argument("--count", type=int, default=DEFAULT_SENSOR_COUNT, help="How many simulated sensors to start")
    parser.add_argument("--start-id", type=int, default=1, help="First sensor id")
    parser.add_argument("--interval", type=int, default=DEFAULT_REPORT_INTERVAL_MS, help="Initial report interval in ms")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ip = args.ip.strip() or get_local_ip()

    runtimes: list[SensorRuntime] = []
    for offset in range(args.count):
        sensor_id = args.start_id + offset
        runtime = SensorRuntime(
            sensor_id=sensor_id,
            current_rms=round(random.uniform(RMS_MIN, RMS_MAX), 2),
            report_interval_ms=max(200, args.interval),
        )
        worker = threading.Thread(target=upload_loop, args=(runtime, args.backend, ip), daemon=True)
        worker.start()
        runtimes.append(runtime)
        print(f"started simulated sensor id={sensor_id} ip={ip} interval={runtime.report_interval_ms}ms")

    while True:
        time.sleep(10)


if __name__ == "__main__":
    main()
