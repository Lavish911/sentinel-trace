"""
FastAPI TestClient compatibility module for SENTINEL//TRACE.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from fastapi import FastAPI


class TestResponse:
    def __init__(self, status_code: int, body: bytes, headers: Dict[str, str]) -> None:
        self.status_code = status_code
        self.content = body
        self.headers = headers

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)


class TestClient:
    __test__ = False

    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self._lifespan_cm: Any = None

    def __enter__(self) -> "TestClient":
        if self.app.lifespan is not None and not self.app.dependency_overrides:
            self._lifespan_cm = self.app.lifespan(self.app)
            asyncio.run(self._lifespan_cm.__aenter__())
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._lifespan_cm is not None:
            try:
                asyncio.run(self._lifespan_cm.__aexit__(exc_type, exc_val, exc_tb))
            finally:
                self._lifespan_cm = None

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json: Any = None,
        data: Optional[bytes] = None,
    ) -> TestResponse:
        req_headers = dict(headers or {})
        body_bytes = b""
        if json is not None:
            import json as _json

            body_bytes = _json.dumps(json, ensure_ascii=False).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
        elif data is not None:
            body_bytes = data if isinstance(data, bytes) else str(data).encode("utf-8")

        resp = self.app.handle_request(
            method=method,
            raw_url=url,
            headers=req_headers,
            body=body_bytes,
        )
        return TestResponse(
            status_code=resp.status_code,
            body=resp.body,
            headers=resp.headers,
        )

    def get(self, url: str, *, headers: Optional[Dict[str, str]] = None) -> TestResponse:
        return self.request("GET", url, headers=headers)

    def post(
        self,
        url: str,
        *,
        json: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> TestResponse:
        return self.request("POST", url, json=json, headers=headers)

    def patch(
        self,
        url: str,
        *,
        json: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> TestResponse:
        return self.request("PATCH", url, json=json, headers=headers)
