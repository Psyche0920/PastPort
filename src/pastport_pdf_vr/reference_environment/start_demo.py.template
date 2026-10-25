"""Serve the initialized reference snapshot without regenerating user data."""

import argparse
from http.server import ThreadingHTTPServer

import review_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the three original PastPort demos")
    parser.add_argument("--port", type=int, default=8793)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Port must be between 1024 and 65535")
    review_server.PORT = args.port
    with ThreadingHTTPServer(("127.0.0.1", args.port), review_server.ReviewHandler) as server:
        print(f"Three demos: http://127.0.0.1:{args.port}/demo.html", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
