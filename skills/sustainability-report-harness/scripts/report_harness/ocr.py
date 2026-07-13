"""Persist human decisions for scanned-PDF fallback without executing OCR implicitly."""

from __future__ import annotations

from pathlib import Path
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

    manifest = read_jsonl(project_dir / "state/source_manifest.jsonl")
    manifest_record = next(
        (item for item in manifest if item.get("source_file") == source_file), None
    )
    if not manifest_record or manifest_record.get("status") not in {
        "needs_ocr",
        "awaiting_ocr_action",
        "skipped_by_user",
    }:
        raise HarnessError(
            "OCR_DECISION_NOT_ALLOWED",
            "Source is not currently classified as a scanned PDF needing a decision",
            source_file,
        )
    source_hash = sha256_file(source_path)
    if source_hash != manifest_record.get("source_hash"):
        raise HarnessError(
            "SOURCE_CHANGED",
            "Source changed after ingestion; ingest it again before recording a decision",
            source_file,
        )

    record = {
        "source_file": source_file,
        "source_hash": source_hash,
        "decision": decision,
        "criticality": criticality,
        "decided_by": decided_by,
        "decided_at": utc_now(),
        "notes": notes,
    }
    path = project_dir / DECISION_PATH
    records = [item for item in read_jsonl(path) if item.get("source_file") != source_file]
    records.append(record)
    records.sort(key=lambda item: item["source_file"])
    write_jsonl(path, records)
    append_event(
        project_dir,
        project_id=str(load_project_config(project_dir)["project_id"]),
        event="ocr.decision_recorded",
        message=f"OCR fallback selected for {source_file}",
        details={
            "source_file": source_file,
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
            return record
    return None


def list_ocr_decisions(project_dir: Path) -> list[dict[str, Any]]:
    return read_jsonl(project_dir.resolve() / DECISION_PATH)
