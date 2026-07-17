"""Framework-neutral project handoff snapshots for cross-Agent continuity."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .audit import append_event
from .config import load_project_config
from .errors import HarnessError
from .ingestion import SOURCE_ROOTS, sha256_file
from .io import read_json, read_jsonl, write_json
from .workflow import WorkflowStore, utc_now

HANDOFF_PATH = Path("state/handoff.json")
HANDOFF_SCHEMA_VERSION = "1.0.0"


def create_handoff(project_dir: Path, *, produced_by: str) -> dict[str, Any]:
    """Create a portable snapshot only after the underlying project validates."""

    project_dir = project_dir.resolve()
    if not produced_by.strip():
        raise HarnessError("AGENT_ID_REQUIRED", "produced_by is required")
    from .project import validate_project

    project_errors = validate_project(project_dir, include_handoff=False)
    if project_errors:
        raise HarnessError(
            "INVALID_PROJECT",
            "Project must validate before handoff",
            details={"errors": project_errors},
        )
    config = load_project_config(project_dir)
    workflow = WorkflowStore(project_dir).load()
    contracts = {
        relative: _sha256_file(project_dir / relative) for relative in _contract_paths(project_dir)
    }
    sources = _source_fingerprints(project_dir)
    source_errors = _source_integrity_errors(sources, workflow["workflow_state"])
    if source_errors:
        raise HarnessError(
            "STALE_SOURCE_MANIFEST",
            "Source files must be ingested before creating a handoff",
            details={"errors": source_errors},
        )
    snapshot = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "project_id": config["project_id"],
        "produced_by": produced_by.strip(),
        "workflow_state": workflow["workflow_state"],
        "checkpoints": workflow["checkpoints"],
        "contracts": contracts,
        "sources": sources,
        "continuation": {
            "truth_source": "state/disclosure_ledger.jsonl",
            "preserve_human_edits": True,
            "reparse_unchanged_sources": False,
            "next_action": _next_action(workflow["workflow_state"]),
        },
    }
    write_json(project_dir / HANDOFF_PATH, snapshot)
    append_event(
        project_dir,
        project_id=str(config["project_id"]),
        event="handoff.created",
        message="Framework-neutral project handoff snapshot created",
        details={
            "produced_by": produced_by.strip(),
            "workflow_state": workflow["workflow_state"],
            "contract_files": len(contracts),
            "source_files": len(sources),
        },
    )
    return handoff_status(project_dir)


def handoff_status(project_dir: Path) -> dict[str, Any]:
    """Read and verify the current handoff without changing project state."""

    project_dir = project_dir.resolve()
    path = project_dir / HANDOFF_PATH
    if not path.is_file():
        return {
            "valid": False,
            "handoff": HANDOFF_PATH.as_posix(),
            "errors": ["state/handoff.json: handoff has not been created"],
        }
    snapshot = read_json(path)
    errors = validate_handoff(project_dir, snapshot=snapshot)
    if not isinstance(snapshot, dict):
        return {
            "valid": False,
            "handoff": HANDOFF_PATH.as_posix(),
            "errors": errors,
        }
    continuation = snapshot.get("continuation")
    sources = snapshot.get("sources")
    return {
        "valid": not errors,
        "handoff": HANDOFF_PATH.as_posix(),
        "project_id": snapshot.get("project_id"),
        "produced_by": snapshot.get("produced_by"),
        "workflow_state": snapshot.get("workflow_state"),
        "next_action": continuation.get("next_action") if isinstance(continuation, dict) else None,
        "source_files": len(sources) if isinstance(sources, list) else 0,
        "errors": errors,
    }


def validate_handoff(
    project_dir: Path,
    *,
    snapshot: dict[str, Any] | None = None,
) -> list[str]:
    """Validate snapshot identity, current file hashes, workflow, and source fingerprints."""

    project_dir = project_dir.resolve()
    path = project_dir / HANDOFF_PATH
    if snapshot is None:
        if not path.is_file():
            return []
        try:
            snapshot = read_json(path)
        except HarnessError as exc:
            return [str(exc)]
    errors: list[str] = []
    if not isinstance(snapshot, dict):
        return ["state/handoff.json: root must be an object"]
    if snapshot.get("schema_version") != HANDOFF_SCHEMA_VERSION:
        errors.append("state/handoff.json.schema_version: must be 1.0.0")
    try:
        config = load_project_config(project_dir)
        workflow = WorkflowStore(project_dir).load()
    except HarnessError as exc:
        return [str(exc)]
    if snapshot.get("project_id") != config.get("project_id"):
        errors.append("state/handoff.json.project_id: does not match project.yaml")
    if snapshot.get("workflow_state") != workflow.get("workflow_state"):
        errors.append("state/handoff.json.workflow_state: snapshot is stale")
    if snapshot.get("checkpoints") != workflow.get("checkpoints"):
        errors.append("state/handoff.json.checkpoints: snapshot is stale")
    produced_by = snapshot.get("produced_by")
    if not isinstance(produced_by, str) or not produced_by.strip():
        errors.append("state/handoff.json.produced_by: must be a non-empty string")

    expected_paths = _contract_paths(project_dir)
    contracts = snapshot.get("contracts")
    if not isinstance(contracts, dict):
        errors.append("state/handoff.json.contracts: must be an object")
    else:
        if set(contracts) != set(expected_paths):
            errors.append("state/handoff.json.contracts: tracked file set is stale")
        for relative in sorted(set(contracts) & set(expected_paths)):
            if contracts.get(relative) != _sha256_file(project_dir / relative):
                errors.append(f"state/handoff.json.contracts.{relative}: file hash is stale")
    try:
        current_sources = _source_fingerprints(project_dir)
        if snapshot.get("sources") != current_sources:
            errors.append("state/handoff.json.sources: source reuse fingerprints are stale")
        errors.extend(_source_integrity_errors(current_sources, workflow["workflow_state"]))
    except HarnessError as exc:
        errors.append(str(exc))
    continuation = snapshot.get("continuation")
    if not isinstance(continuation, dict):
        errors.append("state/handoff.json.continuation: must be an object")
    else:
        if continuation.get("truth_source") != "state/disclosure_ledger.jsonl":
            errors.append("state/handoff.json.continuation.truth_source: invalid")
        if continuation.get("preserve_human_edits") is not True:
            errors.append("state/handoff.json.continuation.preserve_human_edits: must be true")
        if continuation.get("reparse_unchanged_sources") is not False:
            errors.append(
                "state/handoff.json.continuation.reparse_unchanged_sources: must be false"
            )
    return errors


def _contract_paths(project_dir: Path) -> list[str]:
    candidates = [
        "project.yaml",
        "brief.md",
        "state/intake.json",
        "state/workflow.json",
        "state/standards.lock.json",
        "state/source_manifest.jsonl",
        "state/evidence.jsonl",
        "state/ocr_decisions.jsonl",
        "state/requirement_union.json",
        "state/disclosure_ledger.jsonl",
        "state/outline.json",
        "state/outline.md",
        "logs/trial_metrics.jsonl",
        "logs/trial_summary.json",
        "logs/trial_summary.md",
        "outputs/internal/export_manifest.json",
        "outputs/clean/export_manifest.json",
        "outputs/markdown/report_manifest.json",
    ]
    markdown_root = project_dir / "outputs/markdown"
    if markdown_root.is_dir():
        for path in markdown_root.glob("*.md"):
            if path.is_file():
                candidates.append(path.relative_to(project_dir).as_posix())
    for root in (project_dir / "drafts/master", project_dir / "drafts/adaptations"):
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file() and path.suffix.lower() in {".json", ".md"}:
                    candidates.append(path.relative_to(project_dir).as_posix())
    requirements_root = project_dir / "sources/requirements"
    if requirements_root.is_dir():
        for path in requirements_root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                candidates.append(path.relative_to(project_dir).as_posix())
    return sorted({relative for relative in candidates if (project_dir / relative).is_file()})


def _source_fingerprints(project_dir: Path) -> list[dict[str, Any]]:
    manifest_path = project_dir / "state/source_manifest.jsonl"
    manifest = read_jsonl(manifest_path) if manifest_path.is_file() else []
    manifest_by_path = {str(record.get("source_file")): record for record in manifest}
    current_by_path: dict[str, str] = {}
    for relative_root in SOURCE_ROOTS:
        root = project_dir / relative_root
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.is_symlink():
                raise HarnessError(
                    "SYMLINK_SOURCE_BLOCKED", "Source symlinks are not allowed", str(path)
                )
            relative = path.relative_to(project_dir).as_posix()
            current_by_path[relative] = sha256_file(path)
    fingerprints = []
    for relative in sorted(set(manifest_by_path) | set(current_by_path)):
        record = manifest_by_path.get(relative, {})
        fingerprints.append(
            {
                "source_file": relative,
                "manifest_source_hash": record.get("source_hash"),
                "current_file_hash": current_by_path.get(relative),
                "parser_version": record.get("parser_version"),
                "status": record.get("status", "not_ingested"),
                "evidence_ids": record.get("evidence_ids", []),
            }
        )
    return fingerprints


def _source_integrity_errors(sources: list[dict[str, Any]], workflow_state: str) -> list[str]:
    errors: list[str] = []
    pre_ingestion_states = {
        "created",
        "awaiting_data_consent",
        "awaiting_spec_confirmation",
        "awaiting_standard_confirmation",
        "ingesting_sources",
    }
    for source in sources:
        relative = source["source_file"]
        manifest_hash = source.get("manifest_source_hash")
        current_hash = source.get("current_file_hash")
        if manifest_hash is not None and manifest_hash != current_hash:
            errors.append(f"{relative}: current file does not match the ingested source hash")
        elif manifest_hash is None and workflow_state not in pre_ingestion_states:
            errors.append(f"{relative}: source has not been ingested for the current workflow")
    return errors


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _next_action(workflow_state: str) -> str:
    actions = {
        "created": "confirm data consent",
        "awaiting_data_consent": "confirm data consent",
        "awaiting_spec_confirmation": "confirm project specification",
        "awaiting_standard_confirmation": "confirm and lock standard versions",
        "ingesting_sources": "ingest or resolve blocked sources",
        "building_requirement_union": "build the requirement union",
        "awaiting_evidence_confirmation": "review evidence mappings and gaps",
        "generating_outline": "build the formal outline",
        "awaiting_outline_confirmation": "review the formal outline",
        "generating_anchor": "build the Anchor proposal",
        "awaiting_anchor_confirmation": "review the Anchor proposal",
        "generating_master": "build the remaining master proposal",
        "reviewing_master": "review and finalize the master",
        "adapting_standard": "build or review configured adaptations",
        "awaiting_export_confirmation": "export and review the internal package",
        "ready_for_export": "export the clean package",
        "blocked": "resolve the recorded blocker before continuing",
    }
    return actions.get(workflow_state, "inspect workflow and validate the project")
