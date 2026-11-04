"""
FastAPI response classes for SENTINEL//TRACE.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


class Response:
    def __init__(
        self,
        content: Any = "",
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        media_type: str = "text/plain; charset=utf-8",
    ) -> None:
        self.status_code = int(status_code)
        self.headers: Dict[str, str] = dict(headers or {})
        self.media_type = media_type
        if isinstance(content, bytes):
            self.body = content
        elif isinstance(content, str):
            self.body = content.encode("utf-8")
        else:
            self.body = json.dumps(content, ensure_ascii=False).encode("utf-8")
        if "content-type" not in {k.lower() for k in self.headers}:
            self.headers["Content-Type"] = self.media_type


class JSONResponse(Response):
    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        raw = json.dumps(content, ensure_ascii=False).encode("utf-8")
        super().__init__(
            content=raw,
            status_code=status_code,
            headers=headers,
            media_type="application/json",
        )


class HTMLResponse(Response):
    def __init__(
        self,
        content: str = "",
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__(
            content=content,
            status_code=status_code,
            headers=headers,
            media_type="text/html; charset=utf-8",
        )
