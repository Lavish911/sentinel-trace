"""
Zero-dependency pure-Python Pydantic compatibility layer for SENTINEL//TRACE.
Supports BaseModel, Field, ValidationError, pattern/range/length constraints, and serialization.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Callable, Dict, Optional, get_args, get_origin


class ValidationError(ValueError):
    """Raised when BaseModel field validation fails."""


class FieldInfo:
    def __init__(
        self,
        default: Any = ...,
        *,
        default_factory: Optional[Callable[[], Any]] = None,
        ge: Optional[float] = None,
        le: Optional[float] = None,
        gt: Optional[float] = None,
        lt: Optional[float] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        pattern: Optional[str] = None,
        **kwargs: Any,
    ):
        self.default = default
        self.default_factory = default_factory
        self.ge = ge
        self.le = le
        self.gt = gt
        self.lt = lt
        self.min_length = min_length
        self.max_length = max_length
        self.pattern = pattern
        self.extra = kwargs


def Field(
    default: Any = ...,
    *,
    default_factory: Optional[Callable[[], Any]] = None,
    ge: Optional[float] = None,
    le: Optional[float] = None,
    gt: Optional[float] = None,
    lt: Optional[float] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    pattern: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    return FieldInfo(
        default=default,
        default_factory=default_factory,
        ge=ge,
        le=le,
        gt=gt,
        lt=lt,
        min_length=min_length,
        max_length=max_length,
        pattern=pattern,
        **kwargs,
    )


def _allows_none(annotation: Any) -> bool:
    if annotation is None or annotation is Any or annotation is type(None):
        return True
    if isinstance(annotation, str):
        return "None" in annotation or "Optional" in annotation
    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        return type(None) in args
    return False


class BaseModel:
    """Lightweight Pydantic-compatible BaseModel supporting validation and dict serialization."""

    def __init__(self, **data: Any) -> None:
        cls = self.__class__
        annotations: Dict[str, Any] = {}
        for base in reversed(cls.__mro__):
            if base is object or base is BaseModel:
                continue
            ann = getattr(base, "__annotations__", {})
            annotations.update(ann)

        model_fields: list[str] = []
        for name, ann in annotations.items():
            if name.startswith("_"):
                continue
            attr_on_cls = getattr(cls, name, ...)
            if isinstance(attr_on_cls, property) or callable(attr_on_cls):
                continue
            model_fields.append(name)

            field_info: Optional[FieldInfo] = (
                attr_on_cls if isinstance(attr_on_cls, FieldInfo) else None
            )

            if name in data:
                val = data[name]
            elif field_info is not None:
                if field_info.default_factory is not None:
                    val = field_info.default_factory()
                elif field_info.default is not ...:
                    val = copy.deepcopy(field_info.default)
                else:
                    raise ValidationError(f"Field '{name}' is required")
            elif attr_on_cls is not ...:
                val = copy.deepcopy(attr_on_cls)
            else:
                if _allows_none(ann):
                    val = None
                else:
                    raise ValidationError(f"Field '{name}' is required")

            val = self._validate_field(name, val, ann, field_info)
            object.__setattr__(self, name, val)

        for k, v in data.items():
            if k not in model_fields:
                object.__setattr__(self, k, v)

        object.__setattr__(self, "_model_fields", model_fields)

    @staticmethod
    def _validate_field(
        name: str,
        val: Any,
        ann: Any,
        field_info: Optional[FieldInfo],
    ) -> Any:
        if val is None:
            if field_info is not None and field_info.default is ... and not _allows_none(ann):
                raise ValidationError(f"Field '{name}' cannot be None")
            return None

        if field_info is not None:
            if field_info.min_length is not None and isinstance(val, str):
                if len(val) < field_info.min_length:
                    raise ValidationError(
                        f"Field '{name}' length must be >= {field_info.min_length}"
                    )
            if field_info.max_length is not None and isinstance(val, str):
                if len(val) > field_info.max_length:
                    raise ValidationError(
                        f"Field '{name}' length must be <= {field_info.max_length}"
                    )
            if field_info.ge is not None and isinstance(val, (int, float)):
                if val < field_info.ge:
                    raise ValidationError(f"Field '{name}' must be >= {field_info.ge}")
            if field_info.le is not None and isinstance(val, (int, float)):
                if val > field_info.le:
                    raise ValidationError(f"Field '{name}' must be <= {field_info.le}")
            if field_info.gt is not None and isinstance(val, (int, float)):
                if val <= field_info.gt:
                    raise ValidationError(f"Field '{name}' must be > {field_info.gt}")
            if field_info.lt is not None and isinstance(val, (int, float)):
                if val >= field_info.lt:
                    raise ValidationError(f"Field '{name}' must be < {field_info.lt}")
            if field_info.pattern is not None:
                if not isinstance(val, str) or not re.match(field_info.pattern, val):
                    raise ValidationError(
                        f"Field '{name}' value '{val}' does not match pattern {field_info.pattern}"
                    )
        return val

    def model_dump(self) -> Dict[str, Any]:
        fields = getattr(self, "_model_fields", [])
        out: Dict[str, Any] = {}
        for f in fields:
            v = getattr(self, f)
            if isinstance(v, BaseModel):
                out[f] = v.model_dump()
            else:
                out[f] = v
        return out

    def dict(self) -> Dict[str, Any]:
        return self.model_dump()
