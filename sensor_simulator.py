import argparse
import random
import socket
import threading
import time

from fastapi import FastAPI
import requests
import uvicorn

DEFAULT_BACKEND = "http://127.0.0.1:9880"
REGISTER_PATH = "/api/register"
NOISE_PATH = "/noise"
DEFAULT_PORT = 8000

NOISE_MIN = 20.0
NOISE_MAX = 100.0
NOISE_STEP = 10.0

app = FastAPI()
NOISE_LOCK = threading.Lock()
CURRENT_NOISE = 0.0
SENSOR_ID = 1


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def noise_loop(interval: float) -> None:
    global CURRENT_NOISE
    noise = random.uniform(NOISE_MIN, NOISE_MAX)
    while True:
        delta = random.uniform(-NOISE_STEP, NOISE_STEP)
        noise = clamp(noise + delta, NOISE_MIN, NOISE_MAX)
        with NOISE_LOCK:
            CURRENT_NOISE = round(noise, 2)
        time.sleep(interval)


@app.get(NOISE_PATH)
def get_noise() -> dict:
    with NOISE_LOCK:
        noise = CURRENT_NOISE
    return {"id": SENSOR_ID, "noise": noise}


def register_sensor(backend: str, sensor_id: int, ip: str) -> None:
    url = f"{backend}{REGISTER_PATH}"
    payload = {"id": sensor_id, "ip": ip}
    try:
        response = requests.post(url, json=payload, timeout=3)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SystemExit(f"register failed: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Noise sensor simulator")
    parser.add_argument("--id", type=int, default=1, help="Sensor id")
    parser.add_argument(
        "--ip",
        type=str,
        default="",
        help="IP to register (default: auto-detect)",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default=DEFAULT_BACKEND,
        help="Backend base URL",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Noise update interval (seconds)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="HTTP port to serve /noise (backend expects 8000)",
    )
    return parser.parse_args()


def main() -> None:
    global SENSOR_ID
    args = parse_args()
    SENSOR_ID = args.id
    ip = args.ip.strip() or get_local_ip()
    register_sensor(args.backend, SENSOR_ID, ip)

    t = threading.Thread(target=noise_loop, args=(args.interval,), daemon=True)
    t.start()

    config = uvicorn.Config(app, host="0.0.0.0", port=args.port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
