"""
Zero-dependency pure-Python Uvicorn-compatible HTTP server for SENTINEL//TRACE.
Serves FastAPI applications over ThreadingHTTPServer with full lifespan support.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("uvicorn")


class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _load_app(app_target: Any) -> Any:
    if not isinstance(app_target, str):
        return app_target
    mod_name, _, attr_name = app_target.partition(":")
    attr_name = attr_name or "app"
    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    mod = importlib.import_module(mod_name)
    return getattr(mod, attr_name)


def _ensure_canonical_database() -> None:
    """Ensures canonical data/operational.db exists and is seeded before server startup."""
    repo_root = Path(__file__).resolve().parent.parent
    op_db = repo_root / "data" / "operational.db"
    gt_db = repo_root / "data" / "ground_truth.db"
    if not op_db.is_file() or op_db.stat().st_size == 0:
        logger.info("Operational database not found at %s; generating canonical seed=42 dataset...", op_db)
        from db.seed import generate_dataset

        generate_dataset(seed=42, ops_db_path=op_db, gt_db_path=gt_db, overwrite=True)


def _make_handler(app: Any):
    class _FastAPIRequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _dispatch(self, method: str) -> None:
            try:
                content_len = int(self.headers.get("Content-Length", "0") or "0")
                body = self.rfile.read(content_len) if content_len > 0 else b""
                headers_dict: Dict[str, str] = {k: v for k, v in self.headers.items()}
                resp = app.handle_request(
                    method=method,
                    raw_url=self.path,
                    headers=headers_dict,
                    body=body,
                )
                payload = resp.body
                self.send_response(resp.status_code)
                for hk, hv in resp.headers.items():
                    if hk.lower() == "content-length":
                        continue
                    self.send_header(hk, hv)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                if method != "HEAD":
                    self.wfile.write(payload)
            except BrokenPipeError:
                pass
            except Exception as exc:
                logger.exception("Unhandled error serving %s %s: %s", method, self.path, exc)
                err_bytes = b'{"detail":"Internal Server Error"}'
                try:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(err_bytes)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(err_bytes)
                except Exception:
                    pass

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def do_PATCH(self) -> None:
            self._dispatch("PATCH")

        def do_PUT(self) -> None:
            self._dispatch("PUT")

        def do_DELETE(self) -> None:
            self._dispatch("DELETE")

        def do_OPTIONS(self) -> None:
            self._dispatch("OPTIONS")

        def do_HEAD(self) -> None:
            self._dispatch("HEAD")

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return _FastAPIRequestHandler


def run(
    app: Any,
    host: str = "0.0.0.0",
    port: int = 3000,
    reload: bool = False,
    extra_ports: Optional[list[int]] = None,
    **kwargs: Any,
) -> None:
    logging.basicConfig(level=logging.INFO)
    _ensure_canonical_database()
    fastapi_app = _load_app(app)

    lifespan_cm = None
    if getattr(fastapi_app, "lifespan", None) is not None:
        lifespan_cm = fastapi_app.lifespan(fastapi_app)
        asyncio.run(lifespan_cm.__aenter__())

    handler_cls = _make_handler(fastapi_app)
    server = _ReusableThreadingHTTPServer((host, port), handler_cls)

    logger.info("Uvicorn running on http://%s:%d (Press CTRL+C to quit)", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if lifespan_cm is not None:
            try:
                asyncio.run(lifespan_cm.__aexit__(None, None, None))
            except Exception:
                pass
