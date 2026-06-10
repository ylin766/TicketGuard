#!/usr/bin/env python3
"""Serve backend/seats/seats-data so photo_urls can be opened by the frontend."""

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEATS_DATA_DIR = os.path.join(SCRIPT_DIR, "seats-data")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    return parser.parse_args()


def main():
    args = parse_args()
    handler = partial(SimpleHTTPRequestHandler, directory=SEATS_DATA_DIR)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving seat images from {SEATS_DATA_DIR}")
    print(f"Image URL base: http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSeat image server stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
