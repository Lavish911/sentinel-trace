"""
CLI entry point for `python -m uvicorn`.
"""

from __future__ import annotations

import argparse
import sys
from uvicorn import run


def main() -> None:
    parser = argparse.ArgumentParser(prog="uvicorn", add_help=False)
    parser.add_argument("app", nargs="?", default="backend.app.main:app")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, action="append", default=[])
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--log-level", default="info")
    args, _ = parser.parse_known_args()

    ports = args.port or [3000]
    primary_port = ports[-1]
    extra_ports = [p for p in ports[:-1] if p != primary_port]

    run(
        args.app,
        host=args.host,
        port=primary_port,
        reload=args.reload,
        extra_ports=extra_ports,
    )


if __name__ == "__main__":
    main()
