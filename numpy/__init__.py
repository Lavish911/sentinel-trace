"""
Zero-dependency pure-Python 1D numeric array layer for SENTINEL//TRACE.
Supports float64 arrays, boolean masks, elementwise arithmetic, mean, std, sum, abs, and max.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Iterator, List, Union

float64 = float
bool_ = bool


class ndarray:
    """1D numerical/boolean array supporting NumPy vector and mask operations."""

    def __init__(self, data: Iterable[Any], dtype: Any = float64) -> None:
        self.dtype = dtype
        if dtype is bool:
            self._data: List[Any] = [bool(x) for x in data]
        elif dtype is float or dtype is float64:
            self._data = [float(x) for x in data]
        else:
            self._data = list(data)

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._data)

    def __repr__(self) -> str:
        return f"array({self._data!r})"

    def tolist(self) -> List[Any]:
        return list(self._data)

    def __getitem__(self, key: Union[int, slice, "ndarray", List[bool]]) -> Any:
        if isinstance(key, int):
            return self._data[key]
        if isinstance(key, slice):
            return ndarray(self._data[key], dtype=self.dtype)
        if isinstance(key, ndarray):
            mask = key._data
            return ndarray(
                [v for v, m in zip(self._data, mask) if m],
                dtype=self.dtype,
            )
        if isinstance(key, list):
            return ndarray(
                [v for v, m in zip(self._data, key) if m],
                dtype=self.dtype,
            )
        raise TypeError(f"Unsupported index type: {type(key)}")

    def __setitem__(self, key: Union[int, "ndarray", List[bool]], value: Any) -> None:
        if isinstance(key, int):
            self._data[key] = float(value) if self.dtype is float64 else value
            return
        mask = key._data if isinstance(key, ndarray) else list(key)
        if isinstance(value, (ndarray, list)):
            val_iter = iter(value)
            for i, m in enumerate(mask):
                if m:
                    self._data[i] = next(val_iter)
        else:
            for i, m in enumerate(mask):
                if m:
                    self._data[i] = value

    def __invert__(self) -> "ndarray":
        return ndarray([not bool(x) for x in self._data], dtype=bool)

    def _binop(self, other: Any, op: Any, out_dtype: Any = float64) -> "ndarray":
        if isinstance(other, ndarray):
            return ndarray([op(a, b) for a, b in zip(self._data, other._data)], dtype=out_dtype)
        if isinstance(other, list):
            return ndarray([op(a, b) for a, b in zip(self._data, other)], dtype=out_dtype)
        return ndarray([op(a, other) for a in self._data], dtype=out_dtype)

    def __add__(self, other: Any) -> "ndarray":
        return self._binop(other, lambda a, b: a + b)

    def __radd__(self, other: Any) -> "ndarray":
        return self._binop(other, lambda a, b: b + a)

    def __sub__(self, other: Any) -> "ndarray":
        return self._binop(other, lambda a, b: a - b)

    def __rsub__(self, other: Any) -> "ndarray":
        return self._binop(other, lambda a, b: b - a)

    def __mul__(self, other: Any) -> "ndarray":
        return self._binop(other, lambda a, b: a * b)

    def __rmul__(self, other: Any) -> "ndarray":
        return self._binop(other, lambda a, b: b * a)

    def __truediv__(self, other: Any) -> "ndarray":
        return self._binop(other, lambda a, b: a / b)

    def __rtruediv__(self, other: Any) -> "ndarray":
        return self._binop(other, lambda a, b: b / a)

    def __eq__(self, other: Any) -> "ndarray":  # type: ignore[override]
        return self._binop(other, lambda a, b: a == b, out_dtype=bool)


def array(obj: Iterable[Any], dtype: Any = float64) -> ndarray:
    if isinstance(obj, ndarray):
        return ndarray(obj._data, dtype=dtype)
    return ndarray(obj, dtype=dtype)


def zeros(shape: int, dtype: Any = float64) -> ndarray:
    return ndarray([0.0] * int(shape), dtype=dtype)


def full(shape: int, fill_value: Any, dtype: Any = float64) -> ndarray:
    return ndarray([fill_value] * int(shape), dtype=dtype)


def sum(a: Union[ndarray, Iterable[Any]]) -> float:
    return float(math.fsum(a._data if isinstance(a, ndarray) else a))


def mean(a: Union[ndarray, Iterable[Any]]) -> float:
    vals = a._data if isinstance(a, ndarray) else list(a)
    if not vals:
        return 0.0
    return float(math.fsum(vals) / len(vals))


def std(a: Union[ndarray, Iterable[Any]], ddof: int = 0) -> float:
    vals = a._data if isinstance(a, ndarray) else list(a)
    n = len(vals)
    if n <= ddof:
        return 0.0
    mu = mean(vals)
    var = math.fsum((float(x) - mu) ** 2 for x in vals) / (n - ddof)
    return float(math.sqrt(var))


def abs(a: Union[ndarray, Iterable[Any], float]) -> Any:
    if isinstance(a, ndarray):
        return ndarray([builtins_abs(x) for x in a._data], dtype=a.dtype)
    if isinstance(a, (int, float)):
        return builtins_abs(a)
    return ndarray([builtins_abs(x) for x in a], dtype=float64)


builtins_abs = __builtins__["abs"] if isinstance(__builtins__, dict) else getattr(__builtins__, "abs")
builtins_max = __builtins__["max"] if isinstance(__builtins__, dict) else getattr(__builtins__, "max")


def max(a: Union[ndarray, Iterable[Any]]) -> float:
    vals = a._data if isinstance(a, ndarray) else list(a)
    return float(builtins_max(vals)) if vals else 0.0
