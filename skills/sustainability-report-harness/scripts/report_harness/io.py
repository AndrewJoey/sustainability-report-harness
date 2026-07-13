"""Safe file I/O helpers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .errors import HarnessError


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HarnessError("FILE_NOT_FOUND", "Required file does not exist", str(path)) from exc
    except json.JSONDecodeError as exc:
        raise HarnessError(
            "INVALID_JSON",
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}",
            str(path),
        ) from exc


def write_json(path: Path, value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text)


def read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HarnessError("FILE_NOT_FOUND", "Required file does not exist", str(path)) from exc
    except yaml.YAMLError as exc:
        raise HarnessError("INVALID_YAML", f"Invalid YAML: {exc}", str(path)) from exc


def write_yaml(path: Path, value: Any) -> None:
    text = yaml.safe_dump(value, allow_unicode=True, sort_keys=False)
    atomic_write_text(path, text)


def atomic_write_text(path: Path, text: str) -> None:
    """Replace a file atomically without leaving a partial state."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise HarnessError("FILE_NOT_FOUND", "Required file does not exist", str(path)) from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HarnessError(
                "INVALID_JSONL",
                f"Invalid JSON on line {line_number}: {exc.msg}",
                str(path),
            ) from exc
        if not isinstance(value, dict):
            raise HarnessError(
                "INVALID_JSONL_RECORD",
                f"Line {line_number} must contain a JSON object",
                str(path),
            )
        records.append(value)
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Atomically write JSON objects as deterministic JSON Lines."""

    text = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    )
    atomic_write_text(path, text)
