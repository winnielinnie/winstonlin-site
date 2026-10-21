import http.server
from pathlib import Path

PORT = 8892
DIST_DIR = Path(__file__).resolve().parent / "docs"


def main():
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(*args, directory=str(DIST_DIR), **kwargs)
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler) as server:
        print(f"Serving site at http://127.0.0.1:{PORT}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
