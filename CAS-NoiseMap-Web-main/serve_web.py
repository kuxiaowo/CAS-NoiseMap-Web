import http.server
import socket
import socketserver
import sys
from pathlib import Path

PORT = 8080
BIND_HOST = "0.0.0.0"


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main() -> None:
    web_root = Path(__file__).parent.resolve()
    print(f"Serving directory: {web_root}")

    handler = http.server.SimpleHTTPRequestHandler
    socketserver.TCPServer.allow_reuse_address = True

    with socketserver.TCPServer((BIND_HOST, PORT), handler) as httpd:
        local_ip = get_local_ip()
        print("======================================")
        print("Web server is running")
        print(f"Local access : http://127.0.0.1:{PORT}")
        print(f"LAN access   : http://{local_ip}:{PORT}")
        print("Press Ctrl+C to stop")
        print("======================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server")
            sys.exit(0)


if __name__ == "__main__":
    main()
