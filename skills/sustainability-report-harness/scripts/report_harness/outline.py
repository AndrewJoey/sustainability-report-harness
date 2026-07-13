"""Formal M4 outline construction and human approval."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .audit import append_event
from .config import load_project_config
from .errors import HarnessError
from .io import atomic_write_text, read_json, read_jsonl, write_json
from .ledger import validate_ledger
from .workflow import WorkflowStore, utc_now

OUTLINE_JSON = Path("state/outline.json")
OUTLINE_MD = Path("state/outline.md")
LEDGER_PATH = Path("state/disclosure_ledger.jsonl")
GRANULARITIES = {"concise", "standard", "detailed", "custom"}
CONFLICT_STATUSES = {"unresolved", "resolved", "accepted_exception"}


def build_formal_outline(
    project_dir: Path, proposal_path: Path, *, replace: bool = False
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    store = WorkflowStore(project_dir)
    workflow = store.load()
    state = workflow["workflow_state"]
    allowed = state == "generating_outline" or (
        state == "awaiting_outline_confirmation" and replace
    )
    if not allowed:
        raise HarnessError(
            "OUTLINE_BUILD_NOT_ALLOWED",
            "Build in generating_outline, or use replace before Outline approval",
            "workflow_state",
        )
    if workflow["checkpoints"]["evidence"]["status"] != "approved":
        raise HarnessError(
            "CHECKPOINT_REQUIRED", "Evidence Checkpoint must be approved", "evidence"
        )

    proposal = read_json(proposal_path.resolve())
    ledger = read_jsonl(project_dir / LEDGER_PATH)
    ledger_errors = validate_ledger(ledger)
    if ledger_errors:
        raise HarnessError(
            "INVALID_LEDGER",
            "Cannot build an outline from an invalid ledger",
            details=ledger_errors,
        )
    outline = _normalize_outline(proposal, ledger, load_project_config(project_dir))
    write_json(project_dir / OUTLINE_JSON, outline)
    atomic_write_text(project_dir / OUTLINE_MD, _outline_markdown(outline))
    store.set_checkpoint(
        "outline",
        "awaiting_confirmation",
        artifacts=[OUTLINE_JSON.as_posix(), OUTLINE_MD.as_posix()],
        notes="Confirm section order, objectives, length, coverage, evidence, and conflicts",
    )
    if state == "generating_outline":
        store.transition("awaiting_outline_confirmation")
    append_event(
        project_dir,
        project_id=str(load_project_config(project_dir)["project_id"]),
        event="outline.rebuilt" if replace else "outline.built",
        message="Formal outline generated and awaiting consultant confirmation",
        details={
            "sections": len(outline["sections"]),
            "target_length_words": outline["target_length_words"],
            "unresolved_conflicts": sum(
                item["status"] == "unresolved" for item in outline["conflicts"]
            ),
        },
    )
    return _outline_summary(project_dir, outline)


def review_outline(
    project_dir: Path,
    decision: str,
    *,
    reviewed_by: str,
    notes: str | None = None,
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    if decision not in {"approved", "changes_requested"}:
        raise HarnessError("INVALID_REVIEW_DECISION", "Use approved or changes_requested")
    if not reviewed_by.strip():
        raise HarnessError("APPROVER_REQUIRED", "reviewed_by is required")
    store = WorkflowStore(project_dir)
    workflow = store.load()
    if workflow["workflow_state"] != "awaiting_outline_confirmation":
        raise HarnessError(
            "OUTLINE_REVIEW_NOT_ALLOWED",
            "Outline review requires awaiting_outline_confirmation",
            "workflow_state",
        )
    outline = read_json(project_dir / OUTLINE_JSON)
    errors = validate_outline(outline, read_jsonl(project_dir / LEDGER_PATH))
    if errors:
        raise HarnessError("INVALID_OUTLINE", "Formal outline is invalid", details=errors)
    unresolved = [
        item["conflict_id"] for item in outline["conflicts"] if item["status"] == "unresolved"
    ]
    if decision == "approved" and unresolved:
        raise HarnessError(
            "OUTLINE_CONFLICTS_UNRESOLVED",
            "Resolve or explicitly accept every outline conflict before approval",
            details={"conflict_ids": unresolved},
        )
    store.set_checkpoint(
        "outline",
        decision,
        approved_by=reviewed_by if decision == "approved" else None,
        artifacts=[OUTLINE_JSON.as_posix(), OUTLINE_MD.as_posix()],
        notes=notes,
    )
    if decision == "approved":
        store.transition("generating_anchor")
    append_event(
        project_dir,
        project_id=str(load_project_config(project_dir)["project_id"]),
        event=f"outline.{decision}",
        message=f"Formal outline {decision.replace('_', ' ')}",
        details={"reviewed_by": reviewed_by, "notes": notes},
    )
    return _outline_summary(project_dir, outline)


def validate_outline(outline: Any, ledger: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not isinstance(outline, dict):
        return ["outline: JSON object required"]
    if outline.get("schema_version") != "1.0.0":
        errors.append("schema_version: must be 1.0.0")
    sections = outline.get("sections")
    if not isinstance(sections, list) or not sections:
        return errors + ["sections: non-empty list required"]
    known_unified = {
        row["unified_disclosure"]["unified_id"]: row
        for row in ledger
        if isinstance(row.get("unified_disclosure"), dict)
    }
    seen_sections: set[str] = set()
    assigned: list[str] = []
    for index, section in enumerate(sections):
        prefix = f"sections[{index}]"
        if not isinstance(section, dict):
            errors.append(f"{prefix}: object required")
            continue
        for field in ("section_id", "title", "objective"):
            if not isinstance(section.get(field), str) or not section[field].strip():
                errors.append(f"{prefix}.{field}: non-empty string required")
        section_id = section.get("section_id")
        if section_id in seen_sections:
            errors.append(f"{prefix}.section_id: duplicate {section_id}")
        elif isinstance(section_id, str):
            seen_sections.add(section_id)
        target = section.get("target_length_words")
        if not isinstance(target, int) or isinstance(target, bool) or target <= 0:
            errors.append(f"{prefix}.target_length_words: positive integer required")
        if section.get("granularity") not in GRANULARITIES:
            errors.append(f"{prefix}.granularity: invalid value")
        unified_ids = section.get("unified_ids")
        if not isinstance(unified_ids, list) or not unified_ids:
            errors.append(f"{prefix}.unified_ids: non-empty list required")
            continue
        if len(unified_ids) != len(set(unified_ids)):
            errors.append(f"{prefix}.unified_ids: values must be unique")
        unknown = set(unified_ids) - set(known_unified)
        if unknown:
            errors.append(f"{prefix}.unified_ids: unknown IDs {sorted(unknown)}")
        assigned.extend(unified_ids)
    if len(assigned) != len(set(assigned)):
        errors.append("sections.unified_ids: each unified disclosure must appear exactly once")
    if set(assigned) != set(known_unified):
        errors.append("sections.unified_ids: must cover the complete requirement union")
    if outline.get("anchor_section_id") not in seen_sections:
        errors.append("anchor_section_id: must reference one formal outline section")
    conflicts = outline.get("conflicts")
    if not isinstance(conflicts, list):
        errors.append("conflicts: list required")
    else:
        conflict_ids: set[str] = set()
        for index, conflict in enumerate(conflicts):
            prefix = f"conflicts[{index}]"
            if not isinstance(conflict, dict):
                errors.append(f"{prefix}: object required")
                continue
            conflict_id = conflict.get("conflict_id")
            if not isinstance(conflict_id, str) or not conflict_id.strip():
                errors.append(f"{prefix}.conflict_id: non-empty string required")
            elif conflict_id in conflict_ids:
                errors.append(f"{prefix}.conflict_id: duplicate {conflict_id}")
            else:
                conflict_ids.add(conflict_id)
            if not isinstance(conflict.get("description"), str) or not conflict["description"]:
                errors.append(f"{prefix}.description: non-empty string required")
            if conflict.get("status") not in CONFLICT_STATUSES:
                errors.append(f"{prefix}.status: invalid value")
    return errors


def _normalize_outline(
    proposal: Any, ledger: list[dict[str, Any]], config: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(proposal, dict) or proposal.get("schema_version") != "1.0.0":
        raise HarnessError("INVALID_OUTLINE_PROPOSAL", "schema_version must be 1.0.0")
    raw_sections = proposal.get("sections")
    if not isinstance(raw_sections, list):
        raise HarnessError("INVALID_OUTLINE_PROPOSAL", "sections list is required")
    ledger_by_unified = {row["unified_disclosure"]["unified_id"]: row for row in ledger}
    sections: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_sections):
        if not isinstance(raw, dict):
            raise HarnessError("INVALID_OUTLINE_PROPOSAL", "Section must be an object")
        unified_ids = raw.get("unified_ids", [])
        rows = [ledger_by_unified[item] for item in unified_ids if item in ledger_by_unified]
        requirement_ids = [
            item["requirement_id"] for row in rows for item in row.get("requirements", [])
        ]
        accepted_links = [
            item
            for row in rows
            for item in row.get("evidence_links", [])
            if item.get("review_status") in {"accepted", "edited"}
            and item.get("relationship") in {"direct", "supporting"}
        ]
        covered_requirements = sorted(
            {
                requirement_id
                for item in accepted_links
                for requirement_id in item.get("requirement_ids", [])
            }
        )
        sections.append(
            {
                "section_id": raw.get("section_id"),
                "title": raw.get("title"),
                "objective": raw.get("objective"),
                "target_length_words": raw.get("target_length_words"),
                "granularity": raw.get("granularity", config["granularity"]),
                "unified_ids": unified_ids,
                "requirement_ids": requirement_ids,
                "evidence_ids": sorted({item["evidence_id"] for item in accepted_links}),
                "evidence_coverage": {
                    "covered_requirements": len(covered_requirements),
                    "total_requirements": len(requirement_ids),
                },
                "expected_gap_ids": sorted(
                    {item["gap_id"] for row in rows for item in row.get("gaps", [])}
                ),
                "tables": _string_list(raw.get("tables", []), f"sections[{index}].tables"),
                "cases": _string_list(raw.get("cases", []), f"sections[{index}].cases"),
                "chart_suggestions": _string_list(
                    raw.get("chart_suggestions", []),
                    f"sections[{index}].chart_suggestions",
                ),
            }
        )
    conflicts = proposal.get("conflicts", [])
    outline = {
        "schema_version": "1.0.0",
        "generated_at": utc_now(),
        "target_length_words": sum(
            item.get("target_length_words", 0)
            for item in sections
            if isinstance(item.get("target_length_words"), int)
        ),
        "source_ledger_hash": _ledger_hash(ledger),
        "anchor_section_id": proposal.get("anchor_section_id"),
        "sections": sections,
        "conflicts": conflicts,
    }
    errors = validate_outline(outline, ledger)
    configured_target = config.get("target_length_words")
    if configured_target is not None and outline["target_length_words"] != configured_target:
        errors.append(
            "target_length_words: section budgets must sum to project.yaml target_length_words"
        )
    if errors:
        raise HarnessError(
            "INVALID_OUTLINE_PROPOSAL", "Outline proposal is invalid", details=errors
        )
    return outline


def _outline_markdown(outline: dict[str, Any]) -> str:
    lines = [
        "# 正式报告目录",
        "",
        "> 状态：待顾问确认。目录确认前不得生成 Anchor。",
        "",
        f"目标总字数：{outline['target_length_words']}",
        f"Anchor 章节：{outline['anchor_section_id']}",
        "",
    ]
    for index, section in enumerate(outline["sections"], start=1):
        coverage = section["evidence_coverage"]
        lines.extend(
            [
                f"## {index}. {section['title']} (`{section['section_id']}`)",
                "",
                section["objective"],
                "",
                f"- 字数预算：{section['target_length_words']}",
                f"- 颗粒度：{section['granularity']}",
                f"- 统一披露要求：{', '.join(section['unified_ids'])}",
                f"- 证据覆盖：{coverage['covered_requirements']}/{coverage['total_requirements']}",
                f"- 预计缺口：{', '.join(section['expected_gap_ids']) or '无'}",
                "",
            ]
        )
    if outline["conflicts"]:
        lines.extend(["## 目录冲突", ""])
        for conflict in outline["conflicts"]:
            lines.append(
                f"- [{conflict['status']}] {conflict['conflict_id']}: {conflict['description']}"
            )
        lines.append("")
    return "\n".join(lines)


def _outline_summary(project_dir: Path, outline: dict[str, Any]) -> dict[str, Any]:
    return {
        "valid": True,
        "workflow_state": WorkflowStore(project_dir).load()["workflow_state"],
        "sections": len(outline["sections"]),
        "target_length_words": outline["target_length_words"],
        "unresolved_conflicts": sum(
            item["status"] == "unresolved" for item in outline["conflicts"]
        ),
        "artifacts": [OUTLINE_JSON.as_posix(), OUTLINE_MD.as_posix()],
    }


def _string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HarnessError("INVALID_OUTLINE_PROPOSAL", "Expected a list of strings", path)
    return value


def _ledger_hash(ledger: list[dict[str, Any]]) -> str:
    payload = json.dumps(ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
