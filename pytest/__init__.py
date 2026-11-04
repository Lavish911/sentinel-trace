"""
Zero-dependency pure-Python pytest runner and API compatibility layer for SENTINEL//TRACE.
Supports @pytest.fixture (function/module scope), pytest.raises, pytest.fail,
conftest.py loading, monkeypatch, and tmp_path built-in fixtures.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Tuple, Type, Union


class Failed(AssertionError):
    """Raised by pytest.fail()."""


def fail(reason: str = "") -> None:
    raise Failed(reason)


class _ExceptionInfo:
    def __init__(self) -> None:
        self.type: Optional[Type[BaseException]] = None
        self.value: Optional[BaseException] = None
        self.tb: Any = None


class _RaisesContext:
    def __init__(
        self,
        expected_exception: Union[Type[BaseException], Tuple[Type[BaseException], ...]],
    ) -> None:
        self.expected = expected_exception
        self.excinfo = _ExceptionInfo()

    def __enter__(self) -> _ExceptionInfo:
        return self.excinfo

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        if exc_type is None:
            raise AssertionError(f"DID NOT RAISE {self.expected}")
        if issubclass(exc_type, self.expected):
            self.excinfo.type = exc_type
            self.excinfo.value = exc_val
            self.excinfo.tb = exc_tb
            return True
        return False


def raises(
    expected_exception: Union[Type[BaseException], Tuple[Type[BaseException], ...]],
) -> _RaisesContext:
    return _RaisesContext(expected_exception)


def fixture(
    func: Optional[Callable[..., Any]] = None,
    *,
    scope: str = "function",
    **kwargs: Any,
) -> Any:
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        setattr(fn, "_pytest_fixture", True)
        setattr(fn, "_pytest_scope", scope)
        return fn

    if func is not None and callable(func):
        return decorator(func)
    return decorator


class MonkeyPatch:
    def __init__(self) -> None:
        self._undo: list[Callable[[], None]] = []

    def setattr(self, target: Any, name: str, value: Any) -> None:
        had = hasattr(target, name)
        old = getattr(target, name, None)
        setattr(target, name, value)
        self._undo.append(
            lambda: setattr(target, name, old) if had else delattr(target, name)
        )

    def setenv(self, name: str, value: str) -> None:
        import os

        old = os.environ.get(name)
        os.environ[name] = str(value)
        self._undo.append(
            lambda: os.environ.__setitem__(name, old)
            if old is not None
            else os.environ.pop(name, None)
        )

    def undo(self) -> None:
        for fn in reversed(self._undo):
            try:
                fn()
            except Exception:
                pass
        self._undo.clear()
