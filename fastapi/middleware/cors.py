"""CORS middleware compatibility class for FastAPI."""

from typing import Any


class CORSMiddleware:
    def __init__(self, app: Any = None, **kwargs: Any) -> None:
        self.app = app
        self.options = kwargs
