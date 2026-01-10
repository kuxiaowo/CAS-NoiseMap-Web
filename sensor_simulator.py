import random
import time
import threading
import requests

POST_URL = "http://127.0.0.1:9660/data"
SEND_INTERVAL_SEC = 1

NOISE_MIN = 20.0
NOISE_MAX = 100.0
NOISE_STEP = 10.0

SENSOR_IDS = [1, 2, 3, 4, 5]


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def sensor_loop(sensor_id: int) -> None:
    noise = random.uniform(NOISE_MIN, NOISE_MAX)
    while True:
        delta = random.uniform(-NOISE_STEP, NOISE_STEP)
        noise = clamp(noise + delta, NOISE_MIN, NOISE_MAX)

        payload = {
            "id": sensor_id,
            "noise": round(noise, 2),
        }

        try:
            response = requests.post(POST_URL, json=payload, timeout=3)
            ok = response.status_code == 200
            status = f"ok ({response.status_code})" if ok else f"error ({response.status_code})"
        except requests.RequestException as exc:
            status = f"error ({exc})"

        print(f"[sensor {sensor_id}] noise={payload['noise']} status={status}")
        time.sleep(SEND_INTERVAL_SEC)


def main() -> None:
    threads = []
    for sid in SENSOR_IDS:
        t = threading.Thread(target=sensor_loop, args=(sid,), daemon=True)
        threads.append(t)
        t.start()

    # 保持主线程存活
    while True:
        time.sleep(10)


if __name__ == "__main__":
    main()
