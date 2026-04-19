import argparse
import math
import random
import socket
import threading
import time
from dataclasses import dataclass

from fastapi import FastAPI
import requests
import uvicorn

DEFAULT_BACKEND = "http://127.0.0.1:9880"
REGISTER_PATH = "/api/register"
NOISE_PATH = "/noise"
DEFAULT_BASE_PORT = 8000
DEFAULT_SENSOR_COUNT = 10

# RMS 模拟范围 (0.0 ~ 1.0) - 更大的变化幅度
RMS_MIN = 0.005
RMS_MAX = 1.2
RMS_STEP = 0.25  # 更大的步长，造成数据波动更明显


@dataclass
class SensorRuntime:
    sensor_id: int
    port: int
    current_noise: float
    lock: threading.Lock
    app: FastAPI


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


def rms_to_db(rms: float) -> float:
    """
    将 RMS 值转换为分贝值（仅用于显示）
    公式：dB = 20 * log10(rms + 1.0)
    """
    if rms < 0:
        return 0.0
    return 20.0 * math.log10(rms + 1.0)


def create_sensor_app(runtime: SensorRuntime) -> None:
    @runtime.app.get(NOISE_PATH)
    def get_noise() -> dict:
        """返回 RMS 值（新格式）"""
        with runtime.lock:
            rms = runtime.current_noise
        return {"id": runtime.sensor_id, "rms": rms}


def noise_loop(runtime: SensorRuntime, interval: float) -> None:
    """模拟 RMS 值变化（范围 RMS_MIN ~ RMS_MAX）"""
    rms = random.uniform(RMS_MIN, RMS_MAX)
    while True:
        delta = random.uniform(-RMS_STEP, RMS_STEP)
        rms = clamp(rms + delta, RMS_MIN, RMS_MAX)
        with runtime.lock:
            runtime.current_noise = round(rms, 4)
        time.sleep(interval)


def register_sensor(backend: str, sensor_id: int, ip: str, port: int) -> None:
    url = f"{backend}{REGISTER_PATH}"
    payload = {"id": sensor_id, "ip": ip, "port": port}
    response = requests.post(url, json=payload, timeout=3)
    response.raise_for_status()


def run_sensor_server(runtime: SensorRuntime) -> None:
    config = uvicorn.Config(runtime.app, host="0.0.0.0", port=runtime.port, log_level="warning")
    server = uvicorn.Server(config)
    server.run()


def start_sensor(runtime: SensorRuntime, backend: str, ip: str, interval: float) -> None:
    create_sensor_app(runtime)
    register_sensor(backend, runtime.sensor_id, ip, runtime.port)

    noise_worker = threading.Thread(target=noise_loop, args=(runtime, interval), daemon=True)
    noise_worker.start()

    server_worker = threading.Thread(target=run_sensor_server, args=(runtime,), daemon=True)
    server_worker.start()



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Noise sensor simulator")
    parser.add_argument("--backend", type=str, default=DEFAULT_BACKEND, help="Backend base URL")
    parser.add_argument("--ip", type=str, default="", help="IP to register")
    parser.add_argument("--interval", type=float, default=1.0, help="Noise update interval")
    parser.add_argument("--count", type=int, default=DEFAULT_SENSOR_COUNT, help="How many simulated sensors to start")
    parser.add_argument("--start-id", type=int, default=1, help="First sensor id")
    parser.add_argument("--base-port", type=int, default=DEFAULT_BASE_PORT, help="First sensor port")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ip = args.ip.strip() or get_local_ip()

    runtimes: list[SensorRuntime] = []
    for offset in range(args.count):
        sensor_id = args.start_id + offset
        port = args.base_port + offset
        rms = round(random.uniform(RMS_MIN, RMS_MAX), 4)
        runtime = SensorRuntime(
            sensor_id=sensor_id,
            port=port,
            current_noise=rms,
            lock=threading.Lock(),
            app=FastAPI(),
        )
        start_sensor(runtime, args.backend, ip, args.interval)
        runtimes.append(runtime)
        db_value = rms_to_db(rms)
        print(f"started simulated sensor id={sensor_id} port={port} ip={ip} rms={rms:.4f} ({db_value:.1f} dB)")

    while True:
        time.sleep(10)


if __name__ == "__main__":
    main()
