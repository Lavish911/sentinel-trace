"""
Zero-dependency pure-Python FastAPI compatibility layer for SENTINEL//TRACE.
Supports FastAPI, APIRouter, Depends, HTTPException, Query, Request, exception handlers,
lifespan context, dependency_overrides, and interactive /docs & /redoc endpoints.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, get_args, get_origin

from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ValidationError


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: Any = None) -> None:
        super().__init__(str(detail))
        self.status_code = int(status_code)
        self.detail = detail


class DependsInfo:
    def __init__(self, dependency: Optional[Callable[..., Any]] = None) -> None:
        self.dependency = dependency


def Depends(dependency: Optional[Callable[..., Any]] = None) -> Any:
    return DependsInfo(dependency)


class QueryInfo:
    def __init__(
        self,
        default: Any = ...,
        *,
        ge: Optional[float] = None,
        le: Optional[float] = None,
        gt: Optional[float] = None,
        lt: Optional[float] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        pattern: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self.default = default
        self.ge = ge
        self.le = le
        self.gt = gt
        self.lt = lt
        self.min_length = min_length
        self.max_length = max_length
        self.pattern = pattern
        self.extra = kwargs


def Query(
    default: Any = ...,
    *,
    ge: Optional[float] = None,
    le: Optional[float] = None,
    gt: Optional[float] = None,
    lt: Optional[float] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    pattern: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    return QueryInfo(
        default=default,
        ge=ge,
        le=le,
        gt=gt,
        lt=lt,
        min_length=min_length,
        max_length=max_length,
        pattern=pattern,
        **kwargs,
    )


class _CaseInsensitiveHeaders(dict):
    def __init__(self, headers: Optional[Dict[str, str]] = None) -> None:
        super().__init__()
        if headers:
            for k, v in headers.items():
                self[k.lower()] = v

    def get(self, key: str, default: Any = None) -> Any:
        return super().get(str(key).lower(), default)

    def __getitem__(self, key: str) -> Any:
        return super().__getitem__(str(key).lower())

    def __contains__(self, key: object) -> bool:
        return super().__contains__(str(key).lower())


class _URL:
    def __init__(self, raw_url: str) -> None:
        parsed = urllib.parse.urlsplit(raw_url)
        self.path = parsed.path or "/"
        self.query = parsed.query or ""

    def __str__(self) -> str:
        return self.path + (f"?{self.query}" if self.query else "")


class Request:
    def __init__(
        self,
        method: str = "GET",
        url: str = "/",
        headers: Optional[Dict[str, str]] = None,
        body: bytes = b"",
    ) -> None:
        self.method = method.upper()
        self.url = _URL(url)
        self.headers = _CaseInsensitiveHeaders(headers)
        self._body = body

    async def body(self) -> bytes:
        return self._body

    async def json(self) -> Any:
        return json.loads(self._body.decode("utf-8"))


@dataclass
class RouteEntry:
    method: str
    path: str
    endpoint: Callable[..., Any]
    status_code: int = 200
    response_model: Any = None
    response_class: Any = None
    tags: List[str] = field(default_factory=list)

    @property
    def regex(self) -> Tuple[re.Pattern[str], List[str]]:
        param_names: List[str] = []
        pattern = "^"
        pos = 0
        norm_path = self.path if self.path != "" else "/"
        for m in re.finditer(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", norm_path):
            pattern += re.escape(norm_path[pos : m.start()])
            pname = m.group(1)
            param_names.append(pname)
            pattern += f"(?P<{pname}>[^/]+)"
            pos = m.end()
        pattern += re.escape(norm_path[pos:]) + "$"
        return re.compile(pattern), param_names


def _join_paths(prefix: str, path: str) -> str:
    p1 = (prefix or "").rstrip("/")
    p2 = (path or "").strip("/")
    if not p1 and not p2:
        return "/"
    if not p2:
        return p1 if p1.startswith("/") else "/" + p1
    if not p1:
        return "/" + p2
    combined = f"{p1}/{p2}"
    return combined if combined.startswith("/") else "/" + combined


class APIRouter:
    def __init__(self, prefix: str = "", tags: Optional[List[str]] = None) -> None:
        self.prefix = prefix
        self.tags = list(tags or [])
        self.routes: List[RouteEntry] = []

    def add_api_route(
        self,
        path: str,
        endpoint: Callable[..., Any],
        methods: List[str],
        status_code: int = 200,
        response_model: Any = None,
        response_class: Any = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        full_path = _join_paths(self.prefix, path)
        merged_tags = list(self.tags) + list(tags or [])
        for m in methods:
            self.routes.append(
                RouteEntry(
                    method=m.upper(),
                    path=full_path,
                    endpoint=endpoint,
                    status_code=status_code,
                    response_model=response_model,
                    response_class=response_class,
                    tags=merged_tags,
                )
            )

    def get(
        self,
        path: str,
        *,
        status_code: int = 200,
        response_model: Any = None,
        response_class: Any = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.add_api_route(
                path,
                fn,
                ["GET"],
                status_code=status_code,
                response_model=response_model,
                response_class=response_class,
                tags=tags,
            )
            return fn

        return decorator

    def post(
        self,
        path: str,
        *,
        status_code: int = 200,
        response_model: Any = None,
        response_class: Any = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.add_api_route(
                path,
                fn,
                ["POST"],
                status_code=status_code,
                response_model=response_model,
                response_class=response_class,
                tags=tags,
            )
            return fn

        return decorator

    def patch(
        self,
        path: str,
        *,
        status_code: int = 200,
        response_model: Any = None,
        response_class: Any = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.add_api_route(
                path,
                fn,
                ["PATCH"],
                status_code=status_code,
                response_model=response_model,
                response_class=response_class,
                tags=tags,
            )
            return fn

        return decorator

    def include_router(
        self,
        router: "APIRouter",
        *,
        prefix: str = "",
        tags: Optional[List[str]] = None,
    ) -> None:
        merged_prefix = _join_paths(self.prefix, prefix) if prefix else self.prefix
        for r in router.routes:
            sub_path = _join_paths(merged_prefix, r.path)
            self.routes.append(
                RouteEntry(
                    method=r.method,
                    path=sub_path,
                    endpoint=r.endpoint,
                    status_code=r.status_code,
                    response_model=r.response_model,
                    response_class=r.response_class,
                    tags=list(self.tags) + list(tags or []) + list(r.tags),
                )
            )


def _unwrap_optional_type(ann: Any) -> Any:
    if ann is inspect.Parameter.empty or ann is Any:
        return str
    if isinstance(ann, str):
        if "int" in ann:
            return int
        if "float" in ann:
            return float
        if "bool" in ann:
            return bool
        return str
    origin = get_origin(ann)
    if origin is not None:
        args = [a for a in get_args(ann) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return ann


def _coerce_primitive(val: str, target_type: Any, name: str) -> Any:
    t = _unwrap_optional_type(target_type)
    try:
        if t is int:
            return int(val)
        if t is float:
            return float(val)
        if t is bool:
            return val.lower() in ("1", "true", "yes", "on")
        return str(val)
    except Exception as exc:
        raise ValidationError(f"Invalid value for parameter '{name}': {val}") from exc


class FastAPI(APIRouter):
    def __init__(
        self,
        *,
        title: str = "FastAPI",
        description: str = "",
        version: str = "0.1.0",
        lifespan: Any = None,
        docs_url: Optional[str] = "/docs",
        redoc_url: Optional[str] = "/redoc",
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.title = title
        self.description = description
        self.version = version
        self.lifespan = lifespan
        self.docs_url = docs_url
        self.redoc_url = redoc_url
        self.dependency_overrides: Dict[Callable[..., Any], Callable[..., Any]] = {}
        self.exception_handlers: Dict[Type[BaseException], Callable[..., Any]] = {}
        self.middlewares: List[Tuple[Any, Dict[str, Any]]] = []

        if self.docs_url:
            self.add_api_route(self.docs_url, self._serve_docs, ["GET"], response_class=HTMLResponse)
        if self.redoc_url:
            self.add_api_route(self.redoc_url, self._serve_redoc, ["GET"], response_class=HTMLResponse)
        self.add_api_route("/openapi.json", self._serve_openapi, ["GET"])

    def add_middleware(self, middleware_cls: Any, **options: Any) -> None:
        self.middlewares.append((middleware_cls, options))

    def exception_handler(
        self, exc_class: Type[BaseException]
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.exception_handlers[exc_class] = fn
            return fn

        return decorator

    def _serve_openapi(self) -> Dict[str, Any]:
        paths: Dict[str, Any] = {}
        for r in self.routes:
            if r.path in ("/docs", "/redoc", "/openapi.json"):
                continue
            paths.setdefault(r.path, {})[r.method.lower()] = {
                "summary": (r.endpoint.__doc__ or r.endpoint.__name__).strip().splitlines()[0],
                "tags": r.tags,
                "responses": {str(r.status_code): {"description": "Successful Response"}},
            }
        return {
            "openapi": "3.1.0",
            "info": {
                "title": self.title,
                "description": self.description,
                "version": self.version,
            },
            "paths": paths,
        }

    def _serve_docs(self) -> HTMLResponse:
        spec = json.dumps(self._serve_openapi(), indent=2)
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{self.title} — OpenAPI Documentation</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; background: #F6F3EC; color: #242820; margin: 0; padding: 32px; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; }}
  h1 {{ margin: 0 0 8px; font-size: 26px; }}
  p {{ color: #6B6E5E; margin: 0 0 24px; }}
  .ep {{ background: #FCFAF4; border: 1px solid #DAD3C1; border-radius: 6px; padding: 12px 16px; margin-bottom: 10px; display: flex; gap: 14px; align-items: center; }}
  .m {{ font-family: monospace; font-weight: 700; font-size: 12px; padding: 3px 8px; border-radius: 3px; background: #242820; color: #F6F3EC; min-width: 58px; text-align: center; }}
  .p {{ font-family: monospace; font-weight: 600; font-size: 13.5px; }}
  .s {{ color: #6B6E5E; font-size: 13px; margin-left: auto; }}
  pre {{ background: #EFEBE0; border: 1px solid #DAD3C1; border-radius: 6px; padding: 16px; overflow: auto; font-size: 12px; }}
  a {{ color: #B85C43; }}
</style>
</head>
<body>
<div class="wrap">
  <p><a href="/">← Back to SENTINEL//TRACE Forensic Cockpit</a></p>
  <h1>{self.title} <small style="font-size:14px;color:#6B6E5E">v{self.version}</small></h1>
  <p>{self.description}</p>
  {"".join(f'<div class="ep"><span class="m">{r.method}</span><span class="p">{r.path}</span><span class="s">{(r.endpoint.__doc__ or "").strip().splitlines()[0] if r.endpoint.__doc__ else ""}</span></div>' for r in self.routes if r.path not in ("/docs", "/redoc", "/openapi.json"))}
  <h2 style="margin-top:28px;font-size:16px">OpenAPI 3.1 Specification</h2>
  <pre>{spec}</pre>
</div>
</body>
</html>"""
        return HTMLResponse(content=html)

    def _serve_redoc(self) -> HTMLResponse:
        return self._serve_docs()

    def handle_request(
        self,
        method: str,
        raw_url: str,
        headers: Optional[Dict[str, str]] = None,
        body: bytes = b"",
    ) -> Response:
        req = Request(method=method, url=raw_url, headers=headers, body=body)
        parsed = urllib.parse.urlsplit(raw_url)
        path = parsed.path or "/"
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
        query_dict = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))

        if method.upper() == "OPTIONS":
            return Response(
                content="",
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, PATCH, PUT, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                },
            )

        matched_route: Optional[RouteEntry] = None
        path_params: Dict[str, str] = {}
        path_matched_wrong_method = False

        for r in self.routes:
            regex, _ = r.regex
            m = regex.match(path)
            if m:
                if r.method == method.upper():
                    matched_route = r
                    path_params = m.groupdict()
                    break
                path_matched_wrong_method = True

        if matched_route is None:
            if path_matched_wrong_method:
                return JSONResponse({"detail": "Method Not Allowed"}, status_code=405)
            return JSONResponse({"detail": "Not Found"}, status_code=404)

        cleanups: List[Any] = []
        try:
            kwargs = self._build_endpoint_kwargs(
                matched_route.endpoint,
                req,
                path_params,
                query_dict,
                body,
                cleanups,
            )
            result = matched_route.endpoint(**kwargs)
            if inspect.iscoroutine(result):
                result = asyncio.run(result)
            resp = self._serialize_response(result, matched_route)
        except HTTPException as exc:
            resp = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        except ValidationError as exc:
            resp = JSONResponse({"detail": str(exc)}, status_code=422)
        except BaseException as exc:
            handler = self._find_exception_handler(exc)
            if handler is not None:
                res = handler(req, exc)
                if inspect.iscoroutine(res):
                    res = asyncio.run(res)
                resp = res if isinstance(res, Response) else JSONResponse(res, status_code=500)
            else:
                raise
        finally:
            for gen in reversed(cleanups):
                try:
                    gen.close()
                except Exception:
                    pass

        resp.headers.setdefault("Access-Control-Allow-Origin", "*")
        return resp

    def _find_exception_handler(self, exc: BaseException) -> Optional[Callable[..., Any]]:
        for exc_cls, fn in self.exception_handlers.items():
            if isinstance(exc, exc_cls):
                return fn
        return None

    def _build_endpoint_kwargs(
        self,
        endpoint: Callable[..., Any],
        req: Request,
        path_params: Dict[str, str],
        query_params: Dict[str, str],
        body: bytes,
        cleanups: List[Any],
    ) -> Dict[str, Any]:
        sig = inspect.signature(endpoint)
        type_hints: Dict[str, Any] = {}
        try:
            type_hints = inspect.get_annotations(endpoint, eval_str=True)
        except Exception:
            type_hints = getattr(endpoint, "__annotations__", {})

        kwargs: Dict[str, Any] = {}
        for name, param in sig.parameters.items():
            ann = type_hints.get(name, param.annotation)
            default = param.default

            if ann is Request or name == "request":
                kwargs[name] = req
                continue

            if isinstance(default, DependsInfo):
                dep_fn = default.dependency
                if dep_fn is not None:
                    override = self.dependency_overrides.get(dep_fn, dep_fn)
                    dep_val = override()
                    if inspect.isgenerator(dep_val):
                        kwargs[name] = next(dep_val)
                        cleanups.append(dep_val)
                    else:
                        kwargs[name] = dep_val
                continue

            unwrapped_ann = _unwrap_optional_type(ann)
            is_model = (
                isinstance(unwrapped_ann, type) and issubclass(unwrapped_ann, BaseModel)
            ) or isinstance(default, BaseModel)

            if is_model:
                model_cls = (
                    unwrapped_ann
                    if (isinstance(unwrapped_ann, type) and issubclass(unwrapped_ann, BaseModel))
                    else default.__class__
                )
                if body and body.strip():
                    try:
                        parsed_json = json.loads(body.decode("utf-8"))
                    except Exception as exc:
                        raise ValidationError(f"Invalid JSON body: {exc}") from exc
                    if not isinstance(parsed_json, dict):
                        raise ValidationError("JSON body must be an object")
                    kwargs[name] = model_cls(**parsed_json)
                elif isinstance(default, BaseModel):
                    kwargs[name] = model_cls()
                elif default is not inspect.Parameter.empty:
                    kwargs[name] = default
                else:
                    raise ValidationError(f"Missing required request body for '{name}'")
                continue

            if name in path_params:
                kwargs[name] = _coerce_primitive(path_params[name], ann, name)
                continue

            q_info = default if isinstance(default, QueryInfo) else None
            if name in query_params:
                val = _coerce_primitive(query_params[name], ann, name)
                if q_info is not None:
                    if q_info.ge is not None and isinstance(val, (int, float)) and val < q_info.ge:
                        raise ValidationError(f"Query param '{name}' must be >= {q_info.ge}")
                    if q_info.le is not None and isinstance(val, (int, float)) and val > q_info.le:
                        raise ValidationError(f"Query param '{name}' must be <= {q_info.le}")
                kwargs[name] = val
            else:
                if q_info is not None:
                    if q_info.default is ...:
                        raise ValidationError(f"Missing required query parameter '{name}'")
                    kwargs[name] = q_info.default
                elif default is not inspect.Parameter.empty:
                    kwargs[name] = default
                else:
                    kwargs[name] = None

        return kwargs

    @staticmethod
    def _serialize_response(result: Any, route: RouteEntry) -> Response:
        if isinstance(result, Response):
            return result
        if isinstance(result, BaseModel):
            return JSONResponse(result.model_dump(), status_code=route.status_code)
        if route.response_class is HTMLResponse and isinstance(result, str):
            return HTMLResponse(result, status_code=route.status_code)
        return JSONResponse(result, status_code=route.status_code)
