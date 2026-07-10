"""Shared command-line presentation helpers."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

from .errors import HarnessError


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def run(action: Callable[[], Any]) -> int:
    try:
        result = action()
        if result is not None:
            emit(result)
        return 0
    except HarnessError as exc:
        print(json.dumps(exc.to_dict(), ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
