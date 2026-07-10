"""Minimal structured audit logging without customer-content fields."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import HarnessError

ALLOWED_LEVELS = {"info", "warning", "error"}
FORBIDDEN_DETAIL_KEYS = {"content", "customer_text", "excerpt", "original_text", "text"}


def append_event(
    project_dir: Path,
    *,
    project_id: str,
    event: str,
    message: str,
    level: str = "info",
    details: dict[str, Any] | None = None,
) -> None:
    """Append a compact JSONL operational event to logs/harness.jsonl."""

    if level not in ALLOWED_LEVELS:
        allowed = sorted(ALLOWED_LEVELS)
        raise HarnessError("INVALID_LOG_LEVEL", f"Log level must be one of {allowed}")
    safe_details = details or {}
    forbidden = FORBIDDEN_DETAIL_KEYS & safe_details.keys()
    if forbidden:
        raise HarnessError(
            "UNSAFE_LOG_FIELD",
            "Customer text fields are not allowed in operational logs",
            details={"fields": sorted(forbidden)},
        )
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": level,
        "event": event,
        "project_id": project_id,
        "message": message,
        "details": safe_details,
    }
    path = project_dir / "logs" / "harness.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
