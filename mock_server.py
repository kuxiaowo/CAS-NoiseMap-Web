from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import random

HOST = "127.0.0.1"
PORT = 9770

POINT_COUNT_MIN = 6
POINT_COUNT_MAX = 14
COORD_SPREAD = 240  # max abs coordinate
RGB_MIN = 0
RGB_MAX = 255


def make_points():
    count = random.randint(POINT_COUNT_MIN, POINT_COUNT_MAX)
    points = []
    for i in range(count):
        points.append(
            {
                "id": i + 1,
                "x": random.randint(-COORD_SPREAD, COORD_SPREAD),
                "y": random.randint(-COORD_SPREAD, COORD_SPREAD),
                "rgb": [
                    random.randint(RGB_MIN, RGB_MAX),
                    random.randint(RGB_MIN, RGB_MAX),
                    random.randint(RGB_MIN, RGB_MAX),
                ],
            }
        )
    return points


class Handler(BaseHTTPRequestHandler):
    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_POST(self):
        payload = json.dumps(make_points()).encode("utf-8")
        self.send_response(200)
        self._send_cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return


def main():
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Mock server listening on http://{HOST}:{PORT}/post")
    server.serve_forever()


if __name__ == "__main__":
    main()
