"""M5 standard-specific adaptation proposals, review gates, and derived outputs."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .audit import append_event
from .config import load_project_config
from .docx_export import write_master_docx
from .errors import HarnessError
from .io import read_json, read_jsonl, write_json, write_jsonl
from .ledger import preflight_clean_export, validate_ledger
from .models import Adaptation
from .outline import OUTLINE_JSON
from .standards import LOCK_PATH
from .workflow import WorkflowStore, utc_now
from .xlsx_export import write_review_workbook

LEDGER_PATH = Path("state/disclosure_ledger.jsonl")
REVIEW_DECISIONS = {"accepted", "rejected", "edited"}
STANDARD_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
DIFF_HEADERS = [
    "母版内容编号",
    "目标准则",
    "动作",
    "适配原因",
    "适配后章节",
    "补充证据",
    "内容状态",
    "人工审阅状态",
]


def build_adaptation(
    project_dir: Path,
    proposal_path: Path,
    *,
    replace: bool = False,
) -> dict[str, Any]:
    """Validate an Agent proposal and persist it as ledger-linked review work."""

    project_dir = project_dir.resolve()
    store = WorkflowStore(project_dir)
    workflow = store.load()
    if workflow["checkpoints"]["master"]["status"] != "approved":
        raise HarnessError("CHECKPOINT_REQUIRED", "Master Checkpoint must be approved", "master")
    if workflow["workflow_state"] not in {
        "adapting_standard",
        "awaiting_export_confirmation",
    }:
        raise HarnessError(
            "ADAPTATION_BUILD_NOT_ALLOWED",
            "Adaptation requires adapting_standard or awaiting_export_confirmation",
            "workflow_state",
        )

    proposal = read_json(proposal_path.resolve())
    ledger = read_jsonl(project_dir / LEDGER_PATH)
    ledger_errors = validate_ledger(ledger)
    if ledger_errors:
        raise HarnessError(
            "INVALID_LEDGER",
            "Adaptation requires a valid ledger",
            details=ledger_errors,
        )
    normalized = _normalize_proposal(project_dir, proposal, ledger)
    target_standard_id = normalized[0]["target_standard_id"]
    existing = _target_items(ledger, target_standard_id)
    if existing and not replace:
        raise HarnessError(
            "ADAPTATION_EXISTS",
            f"Adaptation for {target_standard_id} already exists; use replace to rebuild it",
        )
    merged = _merge_target(ledger, target_standard_id, normalized)
    errors = validate_ledger(merged)
    errors.extend(validate_project_adaptations(project_dir, ledger=merged, require_complete=False))
    if errors:
        raise HarnessError(
            "INVALID_ADAPTATION_PROPOSAL",
            "Adaptation proposal failed deterministic validation",
            details={"errors": errors},
        )
    write_jsonl(project_dir / LEDGER_PATH, merged)
    _write_all_snapshots(project_dir, merged)
    if workflow["workflow_state"] == "awaiting_export_confirmation":
        store.transition("adapting_standard")
    append_event(
        project_dir,
        project_id=str(load_project_config(project_dir)["project_id"]),
        event=f"adaptation.{'rebuilt' if replace else 'built'}",
        message=f"Adaptation proposal for {target_standard_id} is awaiting human review",
        details={"target_standard_id": target_standard_id, "items": len(normalized)},
    )
    return adaptation_status(project_dir, target_standard_id)


def review_adaptation_item(
    project_dir: Path,
    target_standard_id: str,
    adaptation_id: str,
    decision: str,
    *,
    reviewed_by: str,
    changes: dict[str, Any] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Persist a named human decision for one adaptation action."""

    project_dir = project_dir.resolve()
    if decision not in REVIEW_DECISIONS:
        raise HarnessError("INVALID_REVIEW_DECISION", f"Unknown decision: {decision}")
    if not reviewed_by.strip():
        raise HarnessError("APPROVER_REQUIRED", "reviewed_by is required")
    if WorkflowStore(project_dir).load()["workflow_state"] != "adapting_standard":
        raise HarnessError(
            "ADAPTATION_REVIEW_NOT_ALLOWED",
            "Adaptation item review requires adapting_standard",
            "workflow_state",
        )
    changes = changes or {}
    allowed_changes = {
        "action",
        "reason",
        "target_section_id",
        "adapted_text",
        "supplemental_evidence_ids",
        "content_type",
        "human_notes",
    }
    unknown = set(changes) - allowed_changes
    if unknown:
        raise HarnessError(
            "INVALID_REVIEW_CHANGE",
            f"Unsupported adaptation changes: {sorted(unknown)}",
        )
    if decision == "edited" and not changes:
        raise HarnessError("CHANGES_REQUIRED", "An edited decision requires field changes")
    if decision != "edited" and changes:
        raise HarnessError(
            "INVALID_REVIEW_CHANGE", "Field changes require the edited review decision"
        )

    ledger = read_jsonl(project_dir / LEDGER_PATH)
    target: dict[str, Any] | None = None
    for row in ledger:
        for item in row.get("adaptations", []):
            if (
                item.get("target_standard_id") == target_standard_id
                and item.get("adaptation_id") == adaptation_id
            ):
                target = item
                break
    if target is None:
        raise HarnessError("ITEM_NOT_FOUND", f"Unknown adaptation item {adaptation_id}")
    target.update(changes)
    if notes is not None:
        target["human_notes"] = notes
    target["review_status"] = decision
    target["reviewed_by"] = reviewed_by
    Adaptation.from_dict(target)
    errors = validate_ledger(ledger)
    errors.extend(validate_project_adaptations(project_dir, ledger=ledger, require_complete=False))
    if errors:
        raise HarnessError(
            "INVALID_REVIEW_CHANGE",
            "Adaptation review would invalidate the project",
            details={"errors": errors},
        )
    write_jsonl(project_dir / LEDGER_PATH, ledger)
    _write_all_snapshots(project_dir, ledger)
    append_event(
        project_dir,
        project_id=str(load_project_config(project_dir)["project_id"]),
        event="adaptation.item_reviewed",
        message=f"{adaptation_id} marked {decision}",
        details={
            "target_standard_id": target_standard_id,
            "adaptation_id": adaptation_id,
            "decision": decision,
            "reviewed_by": reviewed_by,
        },
    )
    return adaptation_status(project_dir, target_standard_id)


def finalize_adaptation(
    project_dir: Path,
    target_standard_id: str,
    *,
    reviewed_by: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Finish a target after all of its actions have named human decisions."""

    project_dir = project_dir.resolve()
    if not reviewed_by.strip():
        raise HarnessError("APPROVER_REQUIRED", "reviewed_by is required")
    store = WorkflowStore(project_dir)
    if store.load()["workflow_state"] != "adapting_standard":
        raise HarnessError(
            "ADAPTATION_FINALIZE_NOT_ALLOWED",
            "Adaptation finalization requires adapting_standard",
            "workflow_state",
        )
    ledger = read_jsonl(project_dir / LEDGER_PATH)
    errors = validate_project_adaptations(project_dir, ledger=ledger, require_complete=False)
    if errors:
        raise HarnessError(
            "INVALID_ADAPTATION",
            "Adaptation state is invalid",
            details={"errors": errors},
        )
    target_items = _target_items(ledger, target_standard_id)
    if not target_items:
        raise HarnessError("ADAPTATION_NOT_FOUND", f"No adaptation for {target_standard_id}")
    blockers = [
        item["adaptation_id"]
        for item in target_items
        if item.get("review_status") not in {"accepted", "edited"}
    ]
    if blockers:
        raise HarnessError(
            "ADAPTATION_REVIEW_INCOMPLETE",
            "Every adaptation action must be accepted or edited",
            details={"adaptation_ids": blockers},
        )
    _write_snapshot(project_dir, target_standard_id, ledger)
    configured = load_project_config(project_dir)["deliverables"]["adaptations"]
    all_complete = all(
        _target_items(ledger, standard_id)
        and all(
            item.get("review_status") in {"accepted", "edited"}
            for item in _target_items(ledger, standard_id)
        )
        for standard_id in configured
    )
    if all_complete:
        store.transition("awaiting_export_confirmation")
    append_event(
        project_dir,
        project_id=str(load_project_config(project_dir)["project_id"]),
        event="adaptation.approved",
        message=f"Adaptation for {target_standard_id} completed human review",
        details={
            "target_standard_id": target_standard_id,
            "reviewed_by": reviewed_by,
            "notes": notes,
        },
    )
    return adaptation_status(project_dir, target_standard_id)


def adaptation_status(project_dir: Path, target_standard_id: str) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    ledger = read_jsonl(project_dir / LEDGER_PATH)
    items = _target_items(ledger, target_standard_id)
    counts = {
        status: sum(item.get("review_status") == status for item in items)
        for status in ("unreviewed", "accepted", "rejected", "edited")
    }
    return {
        "valid": not validate_project_adaptations(
            project_dir, ledger=ledger, require_complete=False
        ),
        "target_standard_id": target_standard_id,
        "workflow_state": WorkflowStore(project_dir).load()["workflow_state"],
        "items_total": len(items),
        "review_counts": counts,
        "review_blockers": [
            item["adaptation_id"]
            for item in items
            if item.get("review_status") not in {"accepted", "edited"}
        ],
        "artifact": _snapshot_path(target_standard_id).as_posix(),
    }


def validate_project_adaptations(
    project_dir: Path,
    *,
    ledger: list[dict[str, Any]] | None = None,
    require_complete: bool = False,
) -> list[str]:
    """Validate locked targets, master links, coverage, sections, and evidence classes."""

    project_dir = project_dir.resolve()
    ledger = ledger if ledger is not None else read_jsonl(project_dir / LEDGER_PATH)
    config = load_project_config(project_dir)
    configured = config["deliverables"]["adaptations"]
    errors: list[str] = []
    if not (project_dir / LOCK_PATH).is_file():
        return errors
    locked = _locked_versions(project_dir)
    outline_path = project_dir / OUTLINE_JSON
    outline = read_json(outline_path) if outline_path.is_file() else {"sections": []}
    section_ids = {
        section.get("section_id")
        for section in outline.get("sections", [])
        if isinstance(section, dict)
    }
    content_by_id, row_by_content = _content_index(ledger)
    all_items = [item for row in ledger for item in row.get("adaptations", [])]
    unexpected = sorted(
        {
            str(item.get("target_standard_id"))
            for item in all_items
            if item.get("target_standard_id") not in configured
        }
    )
    if unexpected:
        errors.append(f"adaptations: targets are not configured deliverables {unexpected}")

    for target_standard_id in configured:
        target_version = locked.get(target_standard_id)
        if target_version is None:
            errors.append(
                f"adaptations.{target_standard_id}: target must be one uniquely locked standard"
            )
            continue
        items = [item for item in all_items if item.get("target_standard_id") == target_standard_id]
        if not items:
            if require_complete:
                errors.append(f"adaptations.{target_standard_id}: adaptation proposal is missing")
            continue
        source_ids = [item.get("source_content_id") for item in items]
        if len(source_ids) != len(set(source_ids)):
            errors.append(f"adaptations.{target_standard_id}: source content IDs must be unique")
        if set(source_ids) != set(content_by_id):
            missing = sorted(set(content_by_id) - set(source_ids))
            extra = sorted(set(source_ids) - set(content_by_id))
            errors.append(
                f"adaptations.{target_standard_id}: every master content block must appear "
                f"exactly once; missing={missing}, unknown={extra}"
            )
        non_omitted_by_row: dict[str, int] = {}
        for index, item in enumerate(items):
            prefix = f"adaptations.{target_standard_id}[{index}]"
            try:
                model = Adaptation.from_dict(item)
            except HarnessError as exc:
                errors.append(f"{prefix}: {exc}")
                continue
            if model.target_version_id != target_version:
                errors.append(f"{prefix}.target_version_id: does not match the locked version")
            source = content_by_id.get(model.source_content_id)
            row = row_by_content.get(model.source_content_id)
            if source is None or row is None:
                continue
            if source.get("review_status") not in {"accepted", "edited"}:
                errors.append(f"{prefix}.source_content_id: master content is not approved")
            if model.action != "omit":
                non_omitted_by_row[row["ledger_id"]] = (
                    non_omitted_by_row.get(row["ledger_id"], 0) + 1
                )
                if model.target_section_id not in section_ids:
                    errors.append(f"{prefix}.target_section_id: unknown formal outline section")
            evidence_by_id = {
                evidence["evidence_id"]: evidence for evidence in row.get("evidence", [])
            }
            evidence_ids = set(source.get("evidence_ids", [])) | set(
                model.supplemental_evidence_ids
            )
            if model.content_type == "confirmed_fact" and not evidence_ids:
                errors.append(f"{prefix}: confirmed_fact requires client evidence")
            if model.content_type == "information_gap" and evidence_ids:
                errors.append(f"{prefix}: information_gap cannot cite evidence")
            for evidence_id in model.supplemental_evidence_ids:
                evidence = evidence_by_id.get(evidence_id)
                if evidence and evidence.get("classification") != "client_evidence":
                    errors.append(f"{prefix}: supplemental evidence must be client_evidence")
        for row in ledger:
            applies = any(
                requirement.get("standard_id") == target_standard_id
                for requirement in row.get("requirements", [])
            )
            if applies and not non_omitted_by_row.get(row.get("ledger_id")):
                errors.append(
                    f"adaptations.{target_standard_id}: target requirement row "
                    f"{row.get('ledger_id')} cannot be entirely omitted"
                )
    return errors


def validate_adaptation_snapshots(
    project_dir: Path,
    *,
    ledger: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Ensure derived adaptation snapshots match the current ledger exactly."""

    project_dir = project_dir.resolve()
    ledger = ledger if ledger is not None else read_jsonl(project_dir / LEDGER_PATH)
    current_hash = _json_hash(ledger)
    errors: list[str] = []
    targets = sorted(
        {
            str(item.get("target_standard_id"))
            for row in ledger
            for item in row.get("adaptations", [])
        }
    )
    for target_standard_id in targets:
        snapshot_path = project_dir / _snapshot_path(target_standard_id)
        if not snapshot_path.is_file():
            errors.append(f"{snapshot_path.relative_to(project_dir)}: snapshot is missing")
            continue
        try:
            snapshot = read_json(snapshot_path)
        except HarnessError as exc:
            errors.append(str(exc))
            continue
        prefix = snapshot_path.relative_to(project_dir).as_posix()
        if snapshot.get("schema_version") != "1.0.0":
            errors.append(f"{prefix}.schema_version: must be 1.0.0")
        if snapshot.get("target_standard_id") != target_standard_id:
            errors.append(f"{prefix}.target_standard_id: does not match the filename target")
        if snapshot.get("source_ledger_hash") != current_hash:
            errors.append(f"{prefix}.source_ledger_hash: snapshot is stale")
        if snapshot.get("items") != _target_items(ledger, target_standard_id):
            errors.append(f"{prefix}.items: does not match current ledger adaptations")
    return errors


def adaptation_preflight(project_dir: Path, ledger: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Return clean-export blockers for configured standard adaptations."""

    blockers: list[dict[str, str]] = []
    for error in validate_project_adaptations(project_dir, ledger=ledger, require_complete=True):
        blockers.append({"adaptation_id": "project", "reason": error})
    for target_standard_id in load_project_config(project_dir)["deliverables"]["adaptations"]:
        for item in _target_items(ledger, target_standard_id):
            if item.get("review_status") not in {"accepted", "edited"}:
                blockers.append(
                    {
                        "adaptation_id": str(item.get("adaptation_id", "unknown")),
                        "reason": "adaptation action has not been accepted or edited",
                    }
                )
        try:
            _, adapted_ledger = _adapted_view(project_dir, target_standard_id, ledger)
        except HarnessError as exc:
            blockers.append({"adaptation_id": target_standard_id, "reason": str(exc)})
            continue
        for blocker in preflight_clean_export(adapted_ledger):
            blockers.append(
                {
                    "adaptation_id": blocker["content_id"],
                    "reason": blocker["reason"],
                }
            )
    return blockers


def write_adaptation_outputs(
    project_dir: Path,
    output_dir: Path,
    *,
    mode: str,
    ledger: list[dict[str, Any]],
) -> list[Path]:
    """Write configured adaptations and their review matrices from current ledger state."""

    if mode not in {"internal", "clean"}:
        raise HarnessError("INVALID_EXPORT_MODE", "mode must be internal or clean")
    errors = validate_project_adaptations(project_dir, ledger=ledger, require_complete=True)
    if errors:
        raise HarnessError(
            "INVALID_ADAPTATION",
            "Configured adaptations are incomplete or invalid",
            details={"errors": errors},
        )
    config = load_project_config(project_dir)
    locked_names = _locked_names(project_dir)
    expected_names = {Path(path).name for path in expected_adaptation_files(project_dir, mode)}
    patterns = (
        ("adapted_*_internal.docx", "adaptation_diff_*.xlsx")
        if mode == "internal"
        else ("adapted_*_clean.docx",)
    )
    for pattern in patterns:
        for stale in output_dir.glob(pattern):
            if stale.name not in expected_names and stale.is_file():
                stale.unlink()
    files: list[Path] = []
    for target_standard_id in config["deliverables"]["adaptations"]:
        safe_id = safe_standard_id(target_standard_id)
        adapted_outline, adapted_ledger = _adapted_view(project_dir, target_standard_id, ledger)
        report_config = {
            **config,
            "project_name": (
                f"{config['project_name']}｜"
                f"{locked_names.get(target_standard_id, target_standard_id)}"
            ),
        }
        report = output_dir / f"adapted_{safe_id}_{mode}.docx"
        write_master_docx(
            report,
            config=report_config,
            outline=adapted_outline,
            ledger=adapted_ledger,
            internal=mode == "internal",
        )
        files.append(report)
        if mode == "internal":
            diff = output_dir / f"adaptation_diff_{safe_id}.xlsx"
            write_review_workbook(
                diff,
                sheet_name="适配差异",
                title=f"{locked_names.get(target_standard_id, target_standard_id)} 适配差异清单",
                headers=DIFF_HEADERS,
                rows=_diff_rows(ledger, target_standard_id),
            )
            files.append(diff)
    return files


def adapted_view(
    project_dir: Path,
    target_standard_id: str,
    ledger: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return a validated, derived framework-specific view of the master ledger."""

    errors = validate_project_adaptations(
        project_dir.resolve(), ledger=ledger, require_complete=True
    )
    if errors:
        raise HarnessError(
            "INVALID_ADAPTATION",
            "Framework-specific Markdown requires complete adaptation proposals",
            details={"errors": errors},
        )
    return _adapted_view(project_dir.resolve(), target_standard_id, ledger)


def expected_adaptation_files(project_dir: Path, mode: str) -> set[str]:
    targets = load_project_config(project_dir)["deliverables"]["adaptations"]
    files: set[str] = set()
    for target in targets:
        safe_id = safe_standard_id(target)
        files.add(f"outputs/{mode}/adapted_{safe_id}_{mode}.docx")
        if mode == "internal":
            files.add(f"outputs/internal/adaptation_diff_{safe_id}.xlsx")
    return files


def safe_standard_id(value: str) -> str:
    if not isinstance(value, str) or not STANDARD_ID_PATTERN.fullmatch(value):
        raise HarnessError(
            "INVALID_STANDARD_ID",
            "standard_id must use only letters, numbers, dot, underscore, or hyphen",
            str(value),
        )
    return value


def _normalize_proposal(
    project_dir: Path,
    proposal: Any,
    ledger: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(proposal, dict) or proposal.get("schema_version") != "1.0.0":
        raise HarnessError("INVALID_ADAPTATION_PROPOSAL", "schema_version must be 1.0.0")
    target_standard_id = proposal.get("target_standard_id")
    safe_standard_id(target_standard_id)
    configured = load_project_config(project_dir)["deliverables"]["adaptations"]
    if target_standard_id not in configured:
        raise HarnessError(
            "ADAPTATION_NOT_CONFIGURED",
            f"{target_standard_id} is not listed in deliverables.adaptations",
        )
    locked = _locked_versions(project_dir)
    target_version_id = locked.get(target_standard_id)
    if target_version_id is None:
        raise HarnessError(
            "STANDARD_NOT_LOCKED",
            f"{target_standard_id} must be one uniquely locked standard",
        )
    items = proposal.get("items")
    if not isinstance(items, list) or not items:
        raise HarnessError("INVALID_ADAPTATION_PROPOSAL", "items must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise HarnessError(
                "INVALID_ADAPTATION_PROPOSAL", "Every adaptation item must be an object"
            )
        item = {
            **raw,
            "target_standard_id": target_standard_id,
            "target_version_id": target_version_id,
        }
        if item.get("review_status") != "unreviewed":
            raise HarnessError(
                "HUMAN_REVIEW_REQUIRED",
                "Agent adaptation proposals must start as unreviewed",
                f"items[{index}].review_status",
            )
        if item.get("reviewed_by") is not None:
            raise HarnessError(
                "HUMAN_REVIEW_REQUIRED",
                "Agent proposals cannot pre-populate reviewed_by",
                f"items[{index}].reviewed_by",
            )
        normalized.append(Adaptation.from_dict(item).to_dict())
    candidate = _merge_target(ledger, target_standard_id, normalized)
    errors = validate_project_adaptations(project_dir, ledger=candidate, require_complete=False)
    if errors:
        raise HarnessError(
            "INVALID_ADAPTATION_PROPOSAL",
            "Adaptation proposal is incomplete or inconsistent",
            details={"errors": errors},
        )
    return normalized


def _merge_target(
    ledger: list[dict[str, Any]],
    target_standard_id: str,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output = json.loads(json.dumps(ledger, ensure_ascii=False))
    row_by_content = {
        content["content_id"]: row for row in output for content in row.get("content", [])
    }
    for row in output:
        row["adaptations"] = [
            item
            for item in row.get("adaptations", [])
            if item.get("target_standard_id") != target_standard_id
        ]
    for item in items:
        row = row_by_content.get(item["source_content_id"])
        if row is not None:
            row.setdefault("adaptations", []).append(item)
    for row in output:
        row["adaptations"].sort(
            key=lambda item: (item["target_standard_id"], item["source_content_id"])
        )
    return output


def _adapted_view(
    project_dir: Path,
    target_standard_id: str,
    ledger: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    outline = read_json(project_dir / OUTLINE_JSON)
    section_by_id = {section["section_id"]: section for section in outline["sections"]}
    adapted_ids_by_section: dict[str, list[str]] = {section_id: [] for section_id in section_by_id}
    content_by_id, row_by_content = _content_index(ledger)
    adapted_ledger: list[dict[str, Any]] = []
    for item in _target_items(ledger, target_standard_id):
        model = Adaptation.from_dict(item)
        if model.action == "omit":
            continue
        source = content_by_id[model.source_content_id]
        source_row = row_by_content[model.source_content_id]
        text = model.adapted_text if model.adapted_text is not None else source["text"]
        evidence_ids = sorted(
            set(source.get("evidence_ids", [])) | set(model.supplemental_evidence_ids)
        )
        adapted_id = model.adaptation_id
        adapted_ids_by_section[model.target_section_id].append(adapted_id)  # type: ignore[index]
        adapted_ledger.append(
            {
                "ledger_id": f"ADAPTED-{adapted_id}",
                "unified_disclosure": {
                    "unified_id": adapted_id,
                    "title": source_row["unified_disclosure"]["title"],
                    "description": source_row["unified_disclosure"]["description"],
                    "requirement_ids": [
                        requirement["requirement_id"]
                        for requirement in source_row.get("requirements", [])
                        if requirement.get("standard_id") == target_standard_id
                    ]
                    or [model.source_content_id],
                    "review_status": "reviewed",
                    "mapping_notes": f"Derived from master content {model.source_content_id}",
                },
                "requirements": [],
                "evidence": source_row.get("evidence", []),
                "content": [
                    {
                        "content_id": adapted_id,
                        "section_id": model.target_section_id,
                        "text": text,
                        "content_type": model.content_type,
                        "unified_ids": [adapted_id],
                        "evidence_ids": evidence_ids,
                        "review_status": model.review_status,
                        "last_modified_by": (
                            "human" if model.review_status == "edited" else "agent"
                        ),
                        "confirmation_note": model.human_notes or source.get("confirmation_note"),
                    }
                ],
                "assessments": [],
                "review_status": model.review_status,
            }
        )
    sections = []
    for section in outline["sections"]:
        adapted_ids = adapted_ids_by_section[section["section_id"]]
        if adapted_ids:
            sections.append({**section, "unified_ids": adapted_ids})
    if not sections:
        raise HarnessError(
            "EMPTY_ADAPTATION", f"Adaptation for {target_standard_id} has no output content"
        )
    adapted_outline = {
        **outline,
        "sections": sections,
        "anchor_section_id": sections[0]["section_id"],
    }
    return adapted_outline, adapted_ledger


def _diff_rows(ledger: list[dict[str, Any]], target_standard_id: str) -> list[list[Any]]:
    return [
        [
            item["source_content_id"],
            f"{item['target_standard_id']} / {item['target_version_id']}",
            item["action"],
            item["reason"],
            item.get("target_section_id"),
            item.get("supplemental_evidence_ids", []),
            item["content_type"],
            item["review_status"],
        ]
        for item in _target_items(ledger, target_standard_id)
    ]


def _content_index(
    ledger: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    content_by_id: dict[str, dict[str, Any]] = {}
    row_by_content: dict[str, dict[str, Any]] = {}
    for row in ledger:
        for content in row.get("content", []):
            content_by_id[content["content_id"]] = content
            row_by_content[content["content_id"]] = row
    return content_by_id, row_by_content


def _target_items(ledger: list[dict[str, Any]], target_standard_id: str) -> list[dict[str, Any]]:
    return [
        item
        for row in ledger
        for item in row.get("adaptations", [])
        if item.get("target_standard_id") == target_standard_id
    ]


def _locked_versions(project_dir: Path) -> dict[str, str]:
    lock = read_json(project_dir / LOCK_PATH)
    versions: dict[str, list[str]] = {}
    for package in lock.get("standards", []):
        standard = package.get("standard_version", {})
        versions.setdefault(str(standard.get("standard_id")), []).append(
            str(standard.get("version_id"))
        )
    return {standard_id: values[0] for standard_id, values in versions.items() if len(values) == 1}


def _locked_names(project_dir: Path) -> dict[str, str]:
    lock = read_json(project_dir / LOCK_PATH)
    return {
        package["standard_version"]["standard_id"]: package["standard_version"]["name"]
        for package in lock["standards"]
    }


def _snapshot_path(target_standard_id: str) -> Path:
    return Path("drafts/adaptations") / f"{safe_standard_id(target_standard_id)}.json"


def _write_snapshot(
    project_dir: Path, target_standard_id: str, ledger: list[dict[str, Any]]
) -> None:
    items = _target_items(ledger, target_standard_id)
    write_json(
        project_dir / _snapshot_path(target_standard_id),
        {
            "schema_version": "1.0.0",
            "generated_at": utc_now(),
            "target_standard_id": target_standard_id,
            "source_ledger_hash": _json_hash(ledger),
            "review_status": (
                "approved"
                if items
                and all(item.get("review_status") in {"accepted", "edited"} for item in items)
                else "awaiting_confirmation"
            ),
            "items": items,
        },
    )


def _write_all_snapshots(project_dir: Path, ledger: list[dict[str, Any]]) -> None:
    """Refresh every derived target snapshot after any adaptation ledger mutation."""

    targets = sorted(
        {
            str(item.get("target_standard_id"))
            for row in ledger
            for item in row.get("adaptations", [])
        }
    )
    for target_standard_id in targets:
        _write_snapshot(project_dir, target_standard_id, ledger)


def _json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
