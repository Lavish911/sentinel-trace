"""
CLI test runner for `python -m pytest`.
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List

from pytest import MonkeyPatch


def _load_module_from_path(mod_name: str, file_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(mod_name, str(file_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def _collect_fixtures(module: Any) -> Dict[str, Callable[..., Any]]:
    fixtures: Dict[str, Callable[..., Any]] = {}
    for name, obj in inspect.getmembers(module):
        if callable(obj) and getattr(obj, "_pytest_fixture", False):
            fixtures[name] = obj
    return fixtures


def main() -> int:
    parser = argparse.ArgumentParser(prog="pytest")
    parser.add_argument("paths", nargs="*", default=["backend/tests"])
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("-k", default="")
    args, _ = parser.parse_known_args()

    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    test_files: List[Path] = []
    for raw_p in args.paths:
        p = (repo_root / raw_p).resolve() if not Path(raw_p).is_absolute() else Path(raw_p)
        if p.is_file():
            test_files.append(p)
        elif p.is_dir():
            test_files.extend(sorted(p.rglob("test_*.py")))

    global_fixtures: Dict[str, Callable[..., Any]] = {}
    conftest_path = repo_root / "backend" / "tests" / "conftest.py"
    if conftest_path.is_file():
        conf_mod = _load_module_from_path("conftest", conftest_path)
        global_fixtures.update(_collect_fixtures(conf_mod))

    passed = 0
    failed = 0

    for tf in test_files:
        mod_name = f"tests.{tf.stem}"
        mod = _load_module_from_path(mod_name, tf)
        local_fixtures = dict(global_fixtures)
        local_fixtures.update(_collect_fixtures(mod))

        module_cache: Dict[str, Any] = {}
        module_teardowns: List[Any] = []

        test_funcs = sorted(
            [
                (name, obj)
                for name, obj in inspect.getmembers(mod, inspect.isfunction)
                if name.startswith("test_") and (not args.k or args.k in name)
            ],
            key=lambda item: item[1].__code__.co_firstlineno,
        )

        for tname, tfn in test_funcs:
            func_teardowns: List[Any] = []
            func_cache: Dict[str, Any] = {}

            def resolve_fixture(fname: str) -> Any:
                if fname in func_cache:
                    return func_cache[fname]
                if fname in module_cache:
                    return module_cache[fname]
                if fname == "monkeypatch":
                    mp = MonkeyPatch()
                    func_teardowns.append(mp.undo)
                    func_cache[fname] = mp
                    return mp
                if fname == "tmp_path":
                    td = Path(tempfile.mkdtemp(prefix="pytest_tmp_"))
                    func_teardowns.append(lambda: shutil.rmtree(td, ignore_errors=True))
                    func_cache[fname] = td
                    return td
                if fname not in local_fixtures:
                    raise RuntimeError(f"Unknown fixture '{fname}' required by {tname}")

                ffn = local_fixtures[fname]
                scope = getattr(ffn, "_pytest_scope", "function")
                sig = inspect.signature(ffn)
                f_kwargs = {p: resolve_fixture(p) for p in sig.parameters}
                res = ffn(**f_kwargs)
                if inspect.isgenerator(res):
                    val = next(res)
                    if scope == "module":
                        module_teardowns.append(res)
                        module_cache[fname] = val
                    else:
                        func_teardowns.append(res)
                        func_cache[fname] = val
                    return val
                else:
                    if scope == "module":
                        module_cache[fname] = res
                    else:
                        func_cache[fname] = res
                    return res

            rel_file = tf.relative_to(repo_root)
            try:
                sig = inspect.signature(tfn)
                call_kwargs = {p: resolve_fixture(p) for p in sig.parameters}
                tfn(**call_kwargs)
                passed += 1
                if not args.quiet:
                    print(f"{rel_file}::{tname} PASSED")
            except Exception as exc:
                failed += 1
                print(f"{rel_file}::{tname} FAILED: {exc}")
                traceback.print_exc()
            finally:
                for td in reversed(func_teardowns):
                    try:
                        if inspect.isgenerator(td):
                            next(td, None)
                        elif callable(td):
                            td()
                    except Exception:
                        pass

        for mtd in reversed(module_teardowns):
            try:
                if inspect.isgenerator(mtd):
                    next(mtd, None)
                elif callable(mtd):
                    mtd()
            except Exception:
                pass

    print(f"\n=== {passed} passed, {failed} failed ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
