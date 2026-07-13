"""Persist human decisions for scanned-PDF fallback without executing OCR implicitly."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

from .audit import append_event
from .config import load_project_config
from .errors import HarnessError
from .ingestion import sha256_file
from .io import read_jsonl, write_jsonl
from .workflow import utc_now

DECISION_PATH = "state/ocr_decisions.jsonl"
DECISIONS = {
    "run_local_ocr",
    "use_agent_vision",
    "use_cloud_ocr",
    "provide_searchable_source",
    "manual_transcription",
    "skip_as_gap",
    "pause",
}
CRITICALITIES = {"critical", "noncritical"}


def record_ocr_decision(
    project_dir: Path,
    source_file: str,
    decision: str,
    *,
    decided_by: str,
    criticality: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Record the selected fallback; never run a local or cloud OCR tool here."""

    project_dir = project_dir.resolve()
    if decision not in DECISIONS:
        raise HarnessError("INVALID_OCR_DECISION", f"Unknown OCR decision: {decision}")
    if criticality not in CRITICALITIES:
        raise HarnessError(
            "INVALID_CRITICALITY", f"criticality must be one of {sorted(CRITICALITIES)}"
        )
    if not decided_by.strip():
        raise HarnessError("APPROVER_REQUIRED", "decided_by is required")
    if decision == "skip_as_gap" and criticality != "noncritical":
        raise HarnessError(
            "CRITICAL_SOURCE_CANNOT_BE_SKIPPED",
            "Only a source explicitly classified as noncritical can be skipped as a gap",
            source_file,
        )
    if decision == "use_cloud_ocr":
        policy = load_project_config(project_dir)["data_policy"]
        if not policy["cloud_processing_allowed"]:
            raise HarnessError(
                "CLOUD_PROCESSING_NOT_ALLOWED",
                "project.yaml does not allow customer content to be sent to cloud OCR",
                source_file,
            )

    source_path = (project_dir / source_file).resolve()
    try:
        source_path.relative_to(project_dir)
    except ValueError as exc:
        raise HarnessError("SOURCE_OUTSIDE_PROJECT", "Source must stay inside the project") from exc
    if source_path.suffix.lower() != ".pdf" or not source_path.is_file():
        raise HarnessError(
            "INVALID_OCR_SOURCE", "OCR decisions require an existing PDF", source_file
        )

    canonical_source = source_path.relative_to(project_dir).as_posix()
    manifest = read_jsonl(project_dir / "state/source_manifest.jsonl")
    manifest_record = next(
        (item for item in manifest if item.get("source_file") == canonical_source), None
    )
    if not manifest_record or manifest_record.get("status") not in {
        "needs_ocr",
        "awaiting_ocr_action",
        "skipped_by_user",
    }:
        raise HarnessError(
            "OCR_DECISION_NOT_ALLOWED",
            "Source is not currently classified as a scanned PDF needing a decision",
            canonical_source,
        )
    source_hash = sha256_file(source_path)
    if source_hash != manifest_record.get("source_hash"):
        raise HarnessError(
            "SOURCE_CHANGED",
            "Source changed after ingestion; ingest it again before recording a decision",
            canonical_source,
        )

    record = {
        "source_file": canonical_source,
        "source_hash": source_hash,
        "decision": decision,
        "criticality": criticality,
        "decided_by": decided_by,
        "decided_at": utc_now(),
        "notes": notes,
    }
    path = project_dir / DECISION_PATH
    records = [item for item in read_jsonl(path) if item.get("source_file") != canonical_source]
    records.append(record)
    records.sort(key=lambda item: item["source_file"])
    errors = validate_ocr_decisions(records)
    if errors:
        raise HarnessError(
            "INVALID_OCR_DECISIONS", "OCR decisions are invalid", details={"errors": errors}
        )
    write_jsonl(path, records)
    append_event(
        project_dir,
        project_id=str(load_project_config(project_dir)["project_id"]),
        event="ocr.decision_recorded",
        message=f"OCR fallback selected for {canonical_source}",
        details={
            "source_file": canonical_source,
            "source_hash": source_hash,
            "decision": decision,
            "criticality": criticality,
            "decided_by": decided_by,
        },
    )
    return record


def decision_for_source(
    project_dir: Path, source_file: str, source_hash: str
) -> dict[str, Any] | None:
    for record in read_jsonl(project_dir / DECISION_PATH):
        if record.get("source_file") == source_file and record.get("source_hash") == source_hash:
            errors = validate_ocr_decisions([record])
            if errors:
                raise HarnessError(
                    "INVALID_OCR_DECISIONS",
                    "Matching OCR decision is invalid",
                    details={"errors": errors},
                )
            return record
    return None


def list_ocr_decisions(project_dir: Path) -> list[dict[str, Any]]:
    return read_jsonl(project_dir.resolve() / DECISION_PATH)


def validate_ocr_decisions(records: list[dict[str, Any]]) -> list[str]:
    """Validate persisted decisions without executing or authorizing OCR."""

    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for index, record in enumerate(records, start=1):
        prefix = f"line {index}"
        source_file = record.get("source_file")
        if not isinstance(source_file, str) or not source_file:
            errors.append(f"{prefix}.source_file: non-empty string required")
        else:
            source_path = PurePosixPath(source_file)
            if (
                source_path.is_absolute()
                or ".." in source_path.parts
                or not source_file.startswith(("sources/client/", "sources/peer/"))
                or source_path.suffix.lower() != ".pdf"
            ):
                errors.append(f"{prefix}.source_file: must be a PDF under a source root")
        source_hash = record.get("source_hash")
        if not isinstance(source_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", source_hash):
            errors.append(f"{prefix}.source_hash: SHA-256 hex digest required")
        pair = (str(source_file), str(source_hash))
        if pair in seen:
            errors.append(f"{prefix}: duplicate source/hash decision")
        seen.add(pair)
        decision = record.get("decision")
        criticality = record.get("criticality")
        if decision not in DECISIONS:
            errors.append(f"{prefix}.decision: invalid decision")
        if criticality not in CRITICALITIES:
            errors.append(f"{prefix}.criticality: invalid criticality")
        if decision == "skip_as_gap" and criticality != "noncritical":
            errors.append(f"{prefix}: a critical source cannot be skipped")
        for field in ("decided_by", "decided_at"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                errors.append(f"{prefix}.{field}: non-empty string required")
        if record.get("notes") is not None and not isinstance(record.get("notes"), str):
            errors.append(f"{prefix}.notes: string or null required")
    return errors
