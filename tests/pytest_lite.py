"""Stdlib stand-in for the few pytest features the lane tests use: tmp_path, mark.skipif, mark.parametrize."""
from __future__ import annotations

import inspect
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any, Callable


class _Mark:
    """Namespace for the two marks the suites use."""

    @staticmethod
    def skipif(condition: bool, reason: str = "") -> Callable:
        """Skip the test when condition is true."""
        def wrap(function: Callable) -> Callable:
            function._skip_reason = reason if condition else None
            return function
        return wrap

    @staticmethod
    def parametrize(names: str, cases: list) -> Callable:
        """Run the test once per case; names is a comma-separated argument list."""
        keys = [name.strip() for name in names.split(",")]
        def wrap(function: Callable) -> Callable:
            function._cases = [dict(zip(keys, case if len(keys) > 1 else (case,))) for case in cases]
            return function
        return wrap


mark = _Mark()


def main(namespace: dict[str, Any]) -> int:
    """Run every test_* function in namespace; return 1 when any fails."""
    failures = passed = skipped = 0
    for name, function in list(namespace.items()):
        if not (name.startswith("test_") and callable(function)):
            continue
        if getattr(function, "_skip_reason", None) is not None:
            print(f"SKIP {name}: {function._skip_reason}")
            skipped += 1
            continue
        for case in getattr(function, "_cases", [{}]):
            arguments = dict(case)
            with tempfile.TemporaryDirectory() as scratch:
                if "tmp_path" in inspect.signature(function).parameters:
                    arguments["tmp_path"] = Path(scratch).resolve()
                try:
                    function(**arguments)
                    passed += 1
                except Exception:  # a failing assertion or error is reported, then the run continues
                    failures += 1
                    print(f"FAIL {name} {case}\n{traceback.format_exc()}", file=sys.stderr)
    print(f"{passed} passed, {failures} failed, {skipped} skipped")
    return 1 if failures else 0
