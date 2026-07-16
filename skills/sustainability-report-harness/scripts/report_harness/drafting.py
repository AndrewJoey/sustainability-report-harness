"""M4 Anchor/master proposal validation, ledger merge, and human review gates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .audit import append_event
from .config import load_project_config
from .errors import HarnessError
from .io import atomic_write_text, read_json, read_jsonl, write_json, write_jsonl
from .ledger import validate_ledger
from .models import Assessment, DisclosureContent, PeerAssessment
from .outline import OUTLINE_JSON, validate_outline
from .workflow import WorkflowStore, utc_now

LEDGER_PATH = Path("state/disclosure_ledger.jsonl")
ANCHOR_JSON = Path("drafts/master/anchor.json")
ANCHOR_MD = Path("drafts/master/anchor.md")
MASTER_JSON = Path("drafts/master/master.json")
MASTER_MD = Path("drafts/master/master.md")
REVIEW_DECISIONS = {"accepted", "rejected", "edited"}
COLLECTION_MODELS = {
    "content": DisclosureContent,
    "assessments": Assessment,
    "peer_assessments": PeerAssessment,
}
COLLECTION_IDS = {
    "content": "content_id",
    "assessments": "assessment_id",
    "peer_assessments": "peer_assessment_id",
}


def build_draft(
    project_dir: Path,
    proposal_path: Path,
    *,
    stage: str,
    replace: bool = False,
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    if stage not in {"anchor", "master"}:
        raise HarnessError("INVALID_DRAFT_STAGE", "stage must be anchor or master")
    store = WorkflowStore(project_dir)
    workflow = store.load()
    allowed_states = {
        "anchor": {"generating_anchor"} | ({"awaiting_anchor_confirmation"} if replace else set()),
        "master": {"generating_master"} | ({"reviewing_master"} if replace else set()),
    }
    if workflow["workflow_state"] not in allowed_states[stage]:
        raise HarnessError(
            "DRAFT_BUILD_NOT_ALLOWED",
            f"Cannot build {stage} while workflow_state is {workflow['workflow_state']}",
        )
    dependency = "outline" if stage == "anchor" else "anchor"
    if workflow["checkpoints"][dependency]["status"] != "approved":
        raise HarnessError(
            "CHECKPOINT_REQUIRED", f"Checkpoint {dependency} must be approved", dependency
        )

    outline = read_json(project_dir / OUTLINE_JSON)
    ledger = read_jsonl(project_dir / LEDGER_PATH)
    outline_errors = validate_outline(outline, ledger)
    if outline_errors:
        raise HarnessError(
            "INVALID_OUTLINE",
            "Drafting requires an outline consistent with the current requirement union",
            details={"errors": outline_errors},
        )
    proposal = read_json(proposal_path.resolve())
    scope_sections = _stage_scope(project_dir, outline, stage)
    normalized = _normalize_proposal(proposal, stage, scope_sections, outline, ledger, project_dir)
    merged = _merge_into_ledger(ledger, normalized, outline)
    errors = validate_ledger(merged)
    if errors:
        raise HarnessError("INVALID_DRAFT", "Draft merge failed ledger validation", details=errors)
    _validate_stage_completeness(merged, scope_sections, outline)
    write_jsonl(project_dir / LEDGER_PATH, merged)
    _write_snapshot(project_dir, stage, scope_sections, outline, merged)

    checkpoint = "anchor" if stage == "anchor" else "master"
    json_path, md_path = _snapshot_paths(stage)
    store.set_checkpoint(
        checkpoint,
        "awaiting_confirmation",
        artifacts=[json_path.as_posix(), md_path.as_posix(), LEDGER_PATH.as_posix()],
        notes=f"Review {stage} content, response assessments, and independent peer assessments",
    )
    if stage == "anchor" and workflow["workflow_state"] == "generating_anchor":
        store.transition("awaiting_anchor_confirmation")
    if stage == "master" and workflow["workflow_state"] == "generating_master":
        store.transition("reviewing_master")
    append_event(
        project_dir,
        project_id=str(load_project_config(project_dir)["project_id"]),
        event=f"draft.{stage}_{'rebuilt' if replace else 'built'}",
        message=f"{stage.title()} draft generated and awaiting review",
        details={"section_ids": sorted(scope_sections)},
    )
    return draft_status(project_dir, stage)


def review_draft_item(
    project_dir: Path,
    collection: str,
    item_id: str,
    decision: str,
    *,
    reviewed_by: str,
    changes: dict[str, Any] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    if collection not in COLLECTION_MODELS:
        raise HarnessError("INVALID_COLLECTION", f"Unknown draft collection: {collection}")
    if decision not in REVIEW_DECISIONS:
        raise HarnessError("INVALID_REVIEW_DECISION", f"Unknown decision: {decision}")
    if not reviewed_by.strip():
        raise HarnessError("APPROVER_REQUIRED", "reviewed_by is required")
    state = WorkflowStore(project_dir).load()["workflow_state"]
    if state not in {"awaiting_anchor_confirmation", "reviewing_master"}:
        raise HarnessError(
            "DRAFT_REVIEW_NOT_ALLOWED", "Draft item review requires an active review state"
        )
    changes = changes or {}
    allowed_changes = {
        "content": {
            "text",
            "content_type",
            "unified_ids",
            "evidence_ids",
            "confirmation_note",
        },
        "assessments": {
            "response_status",
            "rationale",
            "confidence",
            "confidence_reason",
            "content_ids",
            "evidence_ids",
            "missing_information",
            "improvement_suggestion",
            "human_notes",
        },
        "peer_assessments": {
            "peer_position",
            "rationale",
            "evidence_ids",
            "human_notes",
        },
    }[collection]
    unknown = set(changes) - allowed_changes
    if unknown:
        raise HarnessError("INVALID_REVIEW_CHANGE", f"Unsupported fields: {sorted(unknown)}")

    records = read_jsonl(project_dir / LEDGER_PATH)
    target: dict[str, Any] | None = None
    target_row: dict[str, Any] | None = None
    for row in records:
        for item in row.get(collection, []):
            if item.get(COLLECTION_IDS[collection]) == item_id:
                target = item
                target_row = row
                break
    if target is None:
        raise HarnessError("ITEM_NOT_FOUND", f"Unknown {COLLECTION_IDS[collection]} {item_id}")
    if decision == "edited" and not changes:
        raise HarnessError("CHANGES_REQUIRED", "An edited decision requires field changes")
    if decision != "edited" and changes:
        raise HarnessError(
            "INVALID_REVIEW_CHANGE", "Field changes require the edited review decision"
        )
    target.update(changes)
    target["review_status"] = decision
    if collection == "content" and decision == "edited":
        target["last_modified_by"] = "human"
    if collection == "content" and notes:
        target["confirmation_note"] = notes
    if collection == "assessments" and notes:
        target["human_notes"] = notes
    if collection == "peer_assessments":
        target["reviewed_by"] = reviewed_by
        if notes:
            target["human_notes"] = notes
    validated_item = COLLECTION_MODELS[collection].from_dict(target)
    if collection == "content" and target_row is not None:
        _validate_content_evidence(
            validated_item,
            {item["evidence_id"]: item for item in target_row.get("evidence", [])},
        )
    if collection == "assessments" and target_row is not None:
        evidence_by_id = {item["evidence_id"]: item for item in target_row.get("evidence", [])}
        if any(
            evidence_by_id.get(evidence_id, {}).get("classification") != "client_evidence"
            for evidence_id in validated_item.evidence_ids
        ):
            raise HarnessError(
                "PEER_EVIDENCE_NOT_ALLOWED",
                "Standards response assessments may cite only client evidence",
                item_id,
            )
    if collection == "peer_assessments" and target_row is not None:
        evidence_by_id = {item["evidence_id"]: item for item in target_row.get("evidence", [])}
        if any(
            evidence_by_id.get(evidence_id, {}).get("classification") != "peer_reference"
            for evidence_id in validated_item.evidence_ids
        ):
            raise HarnessError(
                "INVALID_PEER_EVIDENCE",
                "Peer assessments may cite only peer_reference evidence",
                item_id,
            )
    errors = validate_ledger(records)
    if errors:
        raise HarnessError(
            "INVALID_REVIEW_CHANGE", "Review would invalidate ledger", details=errors
        )
    write_jsonl(project_dir / LEDGER_PATH, records)
    stage = "anchor" if state == "awaiting_anchor_confirmation" else "master"
    outline = read_json(project_dir / OUTLINE_JSON)
    _write_snapshot(project_dir, stage, _stage_scope(project_dir, outline, stage), outline, records)
    append_event(
        project_dir,
        project_id=str(load_project_config(project_dir)["project_id"]),
        event=f"draft.{collection}_reviewed",
        message=f"{item_id} marked {decision}",
        details={"item_id": item_id, "decision": decision, "reviewed_by": reviewed_by},
    )
    return draft_status(project_dir, stage)


def finalize_draft(
    project_dir: Path, stage: str, *, reviewed_by: str, notes: str | None = None
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    if stage not in {"anchor", "master"}:
        raise HarnessError("INVALID_DRAFT_STAGE", "stage must be anchor or master")
    if not reviewed_by.strip():
        raise HarnessError("APPROVER_REQUIRED", "reviewed_by is required")
    store = WorkflowStore(project_dir)
    workflow = store.load()
    expected_state = "awaiting_anchor_confirmation" if stage == "anchor" else "reviewing_master"
    if workflow["workflow_state"] != expected_state:
        raise HarnessError(
            "DRAFT_FINALIZE_NOT_ALLOWED", f"{stage} finalization requires {expected_state}"
        )
    outline = read_json(project_dir / OUTLINE_JSON)
    scope = (
        _stage_scope(project_dir, outline, stage)
        if stage == "anchor"
        else {item["section_id"] for item in outline["sections"]}
    )
    ledger = read_jsonl(project_dir / LEDGER_PATH)
    _validate_stage_completeness(ledger, scope, outline)
    blockers = _review_blockers(ledger, scope, outline)
    if blockers:
        raise HarnessError(
            "DRAFT_REVIEW_INCOMPLETE",
            f"{stage.title()} contains unreviewed or rejected items",
            details={"blockers": blockers},
        )
    json_path, md_path = _snapshot_paths(stage)
    store.set_checkpoint(
        stage,
        "approved",
        approved_by=reviewed_by,
        artifacts=[json_path.as_posix(), md_path.as_posix(), LEDGER_PATH.as_posix()],
        notes=notes,
    )
    if stage == "anchor":
        store.transition("generating_master")
    else:
        adaptations = load_project_config(project_dir)["deliverables"]["adaptations"]
        store.transition("adapting_standard" if adaptations else "awaiting_export_confirmation")
    append_event(
        project_dir,
        project_id=str(load_project_config(project_dir)["project_id"]),
        event=f"draft.{stage}_approved",
        message=f"{stage.title()} approved",
        details={"reviewed_by": reviewed_by, "notes": notes},
    )
    return draft_status(project_dir, stage)


def request_draft_changes(
    project_dir: Path, stage: str, *, reviewed_by: str, notes: str
) -> dict[str, Any]:
    if stage not in {"anchor", "master"}:
        raise HarnessError("INVALID_DRAFT_STAGE", "stage must be anchor or master")
    if not reviewed_by.strip():
        raise HarnessError("APPROVER_REQUIRED", "reviewed_by is required")
    if not notes.strip():
        raise HarnessError("NOTES_REQUIRED", "Change requests require notes")
    project_dir = project_dir.resolve()
    store = WorkflowStore(project_dir)
    expected = "awaiting_anchor_confirmation" if stage == "anchor" else "reviewing_master"
    if store.load()["workflow_state"] != expected:
        raise HarnessError("DRAFT_REVIEW_NOT_ALLOWED", f"{stage} is not awaiting review")
    json_path, md_path = _snapshot_paths(stage)
    store.set_checkpoint(
        stage,
        "changes_requested",
        artifacts=[json_path.as_posix(), md_path.as_posix(), LEDGER_PATH.as_posix()],
        notes=notes,
    )
    append_event(
        project_dir,
        project_id=str(load_project_config(project_dir)["project_id"]),
        event=f"draft.{stage}_changes_requested",
        message=f"Changes requested for {stage}",
        details={"reviewed_by": reviewed_by, "notes": notes},
    )
    return draft_status(project_dir, stage)


def draft_status(project_dir: Path, stage: str) -> dict[str, Any]:
    if stage not in {"anchor", "master"}:
        raise HarnessError("INVALID_DRAFT_STAGE", "stage must be anchor or master")
    project_dir = project_dir.resolve()
    outline = read_json(project_dir / OUTLINE_JSON)
    scope = (
        _stage_scope(project_dir, outline, stage)
        if stage == "anchor"
        else {item["section_id"] for item in outline["sections"]}
    )
    ledger = read_jsonl(project_dir / LEDGER_PATH)
    blockers = _review_blockers(ledger, scope, outline)
    return {
        "valid": not validate_ledger(ledger),
        "stage": stage,
        "workflow_state": WorkflowStore(project_dir).load()["workflow_state"],
        "section_ids": sorted(scope),
        "review_blockers": blockers,
        "artifacts": [path.as_posix() for path in _snapshot_paths(stage)],
    }


def _normalize_proposal(
    proposal: Any,
    stage: str,
    scope_sections: set[str],
    outline: dict[str, Any],
    ledger: list[dict[str, Any]],
    project_dir: Path,
) -> dict[str, Any]:
    if not isinstance(proposal, dict) or proposal.get("schema_version") != "1.0.0":
        raise HarnessError("INVALID_DRAFT_PROPOSAL", "schema_version must be 1.0.0")
    if proposal.get("stage") != stage:
        raise HarnessError("INVALID_DRAFT_PROPOSAL", f"stage must be {stage}")
    sections = proposal.get("sections")
    if not isinstance(sections, list):
        raise HarnessError("INVALID_DRAFT_PROPOSAL", "sections list is required")
    if not all(isinstance(item, dict) for item in sections):
        raise HarnessError("INVALID_DRAFT_PROPOSAL", "Every section must be an object")
    proposed_id_list = [item.get("section_id") for item in sections]
    if len(proposed_id_list) != len(set(proposed_id_list)):
        raise HarnessError("DUPLICATE_SECTION", "Draft proposal section IDs must be unique")
    proposed_ids = set(proposed_id_list)
    if proposed_ids != scope_sections:
        raise HarnessError(
            "INVALID_DRAFT_SCOPE",
            f"{stage} must contain exactly its assigned sections",
            details={"expected": sorted(scope_sections), "actual": sorted(map(str, proposed_ids))},
        )
    outline_by_section = {item["section_id"]: item for item in outline["sections"]}
    ledger_by_unified = {row["unified_disclosure"]["unified_id"]: row for row in ledger}
    all_evidence = {
        item["evidence_id"]: item for item in read_jsonl(project_dir / "state/evidence.jsonl")
    }
    normalized_sections = []
    seen_content: set[str] = set()
    seen_assessments: set[str] = set()
    seen_peer: set[str] = set()
    used_peer_evidence: set[str] = set()
    for raw_section in sections:
        section_id = raw_section["section_id"]
        outline_section = outline_by_section[section_id]
        allowed_unified = set(outline_section["unified_ids"])
        allowed_requirements = set(outline_section["requirement_ids"])
        content = _model_list(DisclosureContent, raw_section.get("content"), "content")
        assessments = _model_list(Assessment, raw_section.get("assessments"), "assessments")
        peer = _model_list(PeerAssessment, raw_section.get("peer_assessments"), "peer_assessments")
        for item in content:
            if item.section_id != section_id or len(item.unified_ids) != 1:
                raise HarnessError(
                    "INVALID_CONTENT_SCOPE",
                    "Each content block must belong to this section and one unified disclosure",
                    item.content_id,
                )
            if set(item.unified_ids) - allowed_unified:
                raise HarnessError("INVALID_CONTENT_SCOPE", "Unknown unified disclosure")
            row = ledger_by_unified[item.unified_ids[0]]
            row_evidence = {value["evidence_id"]: value for value in row.get("evidence", [])}
            _validate_content_truth(item, row_evidence)
            _unique(item.content_id, seen_content, "content_id")
        by_content = {item.content_id: item for item in content}
        content_unified = {item.content_id: item.unified_ids[0] for item in content}
        requirement_unified = {
            requirement["requirement_id"]: unified_id
            for unified_id in allowed_unified
            for requirement in ledger_by_unified[unified_id]["requirements"]
        }
        for item in assessments:
            if item.requirement_id not in allowed_requirements:
                raise HarnessError("INVALID_ASSESSMENT_SCOPE", item.requirement_id)
            if set(item.content_ids) - set(by_content):
                raise HarnessError(
                    "UNKNOWN_CONTENT", f"Unknown content IDs in {item.assessment_id}"
                )
            if any(
                content_unified[content_id] != requirement_unified[item.requirement_id]
                for content_id in item.content_ids
            ):
                raise HarnessError(
                    "INVALID_ASSESSMENT_SCOPE",
                    "Assessment content must belong to the same unified disclosure",
                    item.assessment_id,
                )
            row = ledger_by_unified[requirement_unified[item.requirement_id]]
            row_evidence = {value["evidence_id"]: value for value in row.get("evidence", [])}
            if set(item.evidence_ids) - set(row_evidence):
                raise HarnessError("UNKNOWN_EVIDENCE", f"Unknown evidence in {item.assessment_id}")
            if item.review_status != "unreviewed":
                raise HarnessError(
                    "AGENT_REVIEW_BOUNDARY", "New Agent assessments must be unreviewed"
                )
            _unique(item.assessment_id, seen_assessments, "assessment_id")
        for item in peer:
            if item.requirement_id not in allowed_requirements:
                raise HarnessError("INVALID_PEER_ASSESSMENT_SCOPE", item.requirement_id)
            for evidence_id in item.evidence_ids:
                evidence = all_evidence.get(evidence_id)
                if not evidence or evidence.get("classification") != "peer_reference":
                    raise HarnessError(
                        "INVALID_PEER_EVIDENCE",
                        "Peer assessment evidence must be a locatable peer_reference",
                        evidence_id,
                    )
                used_peer_evidence.add(evidence_id)
            if item.peer_position != "not_assessed" and not item.evidence_ids:
                raise HarnessError(
                    "PEER_EVIDENCE_REQUIRED",
                    "A peer position other than not_assessed requires peer evidence",
                    item.peer_assessment_id,
                )
            if item.review_status != "unreviewed" or item.reviewed_by is not None:
                raise HarnessError(
                    "AGENT_REVIEW_BOUNDARY", "New Agent peer assessments must be unreviewed"
                )
            _unique(item.peer_assessment_id, seen_peer, "peer_assessment_id")
        if {item.requirement_id for item in assessments} != allowed_requirements:
            raise HarnessError(
                "INCOMPLETE_ASSESSMENTS", f"Section {section_id} must assess every requirement"
            )
        if {item.requirement_id for item in peer} != allowed_requirements:
            raise HarnessError(
                "INCOMPLETE_PEER_ASSESSMENTS",
                f"Section {section_id} must independently assess every peer position",
            )
        if {item.unified_ids[0] for item in content} != allowed_unified:
            raise HarnessError(
                "INCOMPLETE_DRAFT_CONTENT",
                f"Section {section_id} needs at least one content block per unified disclosure",
            )
        normalized_sections.append(
            {
                "section_id": section_id,
                "content": [item.to_dict() for item in content],
                "assessments": [item.to_dict() for item in assessments],
                "peer_assessments": [item.to_dict() for item in peer],
            }
        )
    return {
        "schema_version": "1.0.0",
        "stage": stage,
        "sections": normalized_sections,
        "peer_evidence": [all_evidence[item] for item in sorted(used_peer_evidence)],
    }


def _merge_into_ledger(
    ledger: list[dict[str, Any]], proposal: dict[str, Any], outline: dict[str, Any]
) -> list[dict[str, Any]]:
    row_by_unified = {row["unified_disclosure"]["unified_id"]: row for row in ledger}
    requirement_to_row = {
        item["requirement_id"]: row for row in ledger for item in row.get("requirements", [])
    }
    peer_evidence = {item["evidence_id"]: item for item in proposal.get("peer_evidence", [])}
    scope_unified = {
        unified_id
        for section in proposal["sections"]
        for unified_id in next(
            item["unified_ids"]
            for item in outline["sections"]
            if item["section_id"] == section["section_id"]
        )
    }
    for unified_id in scope_unified:
        row = row_by_unified[unified_id]
        row["content"] = [
            item for item in row.get("content", []) if item.get("last_modified_by") == "human"
        ]
        row["assessments"] = [
            item
            for item in row.get("assessments", [])
            if item.get("review_status") in {"accepted", "edited"}
        ]
        row["peer_assessments"] = [
            item
            for item in row.get("peer_assessments", [])
            if item.get("review_status") in {"accepted", "edited"}
        ]
    for section in proposal["sections"]:
        for collection, id_field in COLLECTION_IDS.items():
            for incoming in section[collection]:
                row = (
                    row_by_unified[incoming["unified_ids"][0]]
                    if collection == "content"
                    else requirement_to_row[incoming["requirement_id"]]
                )
                if collection == "peer_assessments":
                    existing_evidence = {item["evidence_id"] for item in row.get("evidence", [])}
                    for evidence_id in incoming.get("evidence_ids", []):
                        if evidence_id not in existing_evidence:
                            row.setdefault("evidence", []).append(peer_evidence[evidence_id])
                existing = next(
                    (
                        item
                        for item in row.get(collection, [])
                        if item.get(id_field) == incoming[id_field]
                    ),
                    None,
                )
                if existing is None:
                    row.setdefault(collection, []).append(incoming)
    return ledger


def _validate_content_truth(
    content: DisclosureContent, evidence_by_id: dict[str, dict[str, Any]]
) -> None:
    if content.review_status != "unreviewed" or content.last_modified_by != "agent":
        raise HarnessError(
            "AGENT_REVIEW_BOUNDARY",
            "New Agent content must be unreviewed and last_modified_by agent",
            content.content_id,
        )
    _validate_content_evidence(content, evidence_by_id)


def _validate_content_evidence(
    content: DisclosureContent, evidence_by_id: dict[str, dict[str, Any]]
) -> None:
    unknown = set(content.evidence_ids) - set(evidence_by_id)
    if unknown:
        raise HarnessError("UNKNOWN_EVIDENCE", f"Unknown evidence IDs {sorted(unknown)}")
    for evidence_id in content.evidence_ids:
        if evidence_by_id[evidence_id].get("classification") != "client_evidence":
            raise HarnessError(
                "PEER_EVIDENCE_NOT_ALLOWED",
                "Report content cannot use peer material as customer facts",
                evidence_id,
            )
    if content.content_type == "confirmed_fact" and not content.evidence_ids:
        raise HarnessError(
            "EVIDENCE_REQUIRED", "confirmed_fact requires client evidence", content.content_id
        )
    if content.content_type == "information_gap" and content.evidence_ids:
        raise HarnessError("INVALID_GAP_CONTENT", "information_gap cannot cite supporting evidence")


def _validate_stage_completeness(
    ledger: list[dict[str, Any]], scope_sections: set[str], outline: dict[str, Any]
) -> None:
    section_by_unified = {
        unified_id: section["section_id"]
        for section in outline["sections"]
        for unified_id in section["unified_ids"]
    }
    for row in ledger:
        unified_id = row["unified_disclosure"]["unified_id"]
        if section_by_unified[unified_id] not in scope_sections:
            continue
        if not row.get("content"):
            raise HarnessError("INCOMPLETE_DRAFT_CONTENT", f"No content for {unified_id}")
        required = {item["requirement_id"] for item in row["requirements"]}
        if {item["requirement_id"] for item in row.get("assessments", [])} != required:
            raise HarnessError("INCOMPLETE_ASSESSMENTS", f"Incomplete assessments for {unified_id}")
        if {item["requirement_id"] for item in row.get("peer_assessments", [])} != required:
            raise HarnessError(
                "INCOMPLETE_PEER_ASSESSMENTS", f"Incomplete peer assessments for {unified_id}"
            )


def _review_blockers(
    ledger: list[dict[str, Any]], scope_sections: set[str], outline: dict[str, Any]
) -> list[dict[str, str]]:
    section_by_unified = {
        unified_id: section["section_id"]
        for section in outline["sections"]
        for unified_id in section["unified_ids"]
    }
    blockers: list[dict[str, str]] = []
    for row in ledger:
        unified_id = row["unified_disclosure"]["unified_id"]
        section_id = section_by_unified[unified_id]
        if section_id not in scope_sections:
            continue
        for collection, id_field in COLLECTION_IDS.items():
            for item in row.get(collection, []):
                if item.get("review_status") not in {"accepted", "edited"}:
                    blockers.append(
                        {
                            "collection": collection,
                            "item_id": str(item.get(id_field)),
                            "section_id": section_id,
                            "reason": f"review_status is {item.get('review_status')}",
                        }
                    )
    return blockers


def _write_snapshot(
    project_dir: Path,
    stage: str,
    scope_sections: set[str],
    outline: dict[str, Any],
    ledger: list[dict[str, Any]],
) -> None:
    json_path, md_path = _snapshot_paths(stage)
    snapshot_scope = (
        {item["section_id"] for item in outline["sections"]}
        if stage == "master"
        else scope_sections
    )
    snapshot = {
        "schema_version": "1.0.0",
        "stage": stage,
        "generated_at": utc_now(),
        "section_ids": sorted(snapshot_scope),
        "ledger_hash": _ledger_hash(ledger),
    }
    write_json(project_dir / json_path, snapshot)
    atomic_write_text(project_dir / md_path, _draft_markdown(snapshot_scope, outline, ledger))


def _draft_markdown(
    scope_sections: set[str], outline: dict[str, Any], ledger: list[dict[str, Any]]
) -> str:
    row_by_unified = {row["unified_disclosure"]["unified_id"]: row for row in ledger}
    labels = {
        "confirmed_fact": "已确认事实",
        "inference": "待确认-推断",
        "suggested_text": "建议文本",
        "information_gap": "信息缺口",
    }
    lines = ["# 报告母版粗稿", "", "> 本文件由 disclosure_ledger.jsonl 派生。", ""]
    for section in outline["sections"]:
        if section["section_id"] not in scope_sections:
            continue
        lines.extend([f"## {section['title']}", ""])
        for unified_id in section["unified_ids"]:
            row = row_by_unified[unified_id]
            for content in row.get("content", []):
                label = labels[content["content_type"]]
                lines.extend(
                    [
                        f"[{label}] {content['text']}",
                        "",
                        f"<!-- {content['content_id']} | evidence: "
                        f"{', '.join(content.get('evidence_ids', [])) or 'none'} -->",
                        "",
                    ]
                )
    return "\n".join(lines)


def _stage_scope(project_dir: Path, outline: dict[str, Any], stage: str) -> set[str]:
    all_sections = [item["section_id"] for item in outline["sections"]]
    if stage == "anchor":
        anchor_path = project_dir / ANCHOR_JSON
        if anchor_path.is_file():
            saved = read_json(anchor_path)
            if saved.get("section_ids"):
                return {saved["section_ids"][0]}
        return {outline["anchor_section_id"]}
    anchor = read_json(project_dir / ANCHOR_JSON)
    return set(all_sections) - set(anchor["section_ids"])


def _snapshot_paths(stage: str) -> tuple[Path, Path]:
    return (ANCHOR_JSON, ANCHOR_MD) if stage == "anchor" else (MASTER_JSON, MASTER_MD)


def _model_list(model_type: type, value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise HarnessError("INVALID_DRAFT_PROPOSAL", f"{path} list is required")
    return [model_type.from_dict(item) for item in value]


def _unique(value: str, seen: set[str], field: str) -> None:
    if value in seen:
        raise HarnessError("DUPLICATE_ID", f"Duplicate {field} {value}")
    seen.add(value)


def _ledger_hash(ledger: list[dict[str, Any]]) -> str:
    payload = json.dumps(ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
