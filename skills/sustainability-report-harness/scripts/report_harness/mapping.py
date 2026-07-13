"""Requirement-union construction and human review for M3."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .audit import append_event
from .config import load_project_config
from .errors import HarnessError
from .io import read_json, read_jsonl, write_json, write_jsonl
from .ledger import validate_ledger
from .models import Evidence, EvidenceGap, EvidenceLink, Requirement, RequirementMapping
from .standards import LOCK_PATH, validate_project_standard_lock
from .workflow import WorkflowStore

UNION_PATH = Path("state/requirement_union.json")
LEDGER_PATH = Path("state/disclosure_ledger.jsonl")
EVIDENCE_PATH = Path("state/evidence.jsonl")
REVIEW_DECISIONS = {"accepted", "rejected", "edited"}


def build_requirement_union(
    project_dir: Path, plan_path: Path, *, replace: bool = False
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    store = WorkflowStore(project_dir)
    workflow = store.load()
    state = workflow["workflow_state"]
    is_replacement = state == "awaiting_evidence_confirmation" and replace
    if state != "building_requirement_union" and not is_replacement:
        raise HarnessError(
            "UNION_BUILD_NOT_ALLOWED",
            "Build in building_requirement_union, or use replace before Evidence approval",
            "workflow_state",
        )
    previous_records = (
        read_jsonl(project_dir / LEDGER_PATH)
        if is_replacement and (project_dir / LEDGER_PATH).is_file()
        else []
    )
    lock_errors = validate_project_standard_lock(project_dir)
    if lock_errors:
        raise HarnessError(
            "INVALID_STANDARD_LOCK",
            "Locked standards are invalid",
            details={"errors": lock_errors},
        )
    lock = read_json(project_dir / LOCK_PATH)
    requirements = _locked_requirements(lock, load_project_config(project_dir))
    requirement_by_id = {item.requirement_id: item for item in requirements}
    evidence_by_id = {
        raw["evidence_id"]: Evidence.from_dict(raw)
        for raw in read_jsonl(project_dir / EVIDENCE_PATH)
    }
    plan = read_json(plan_path.resolve())
    if not isinstance(plan, dict) or not isinstance(plan.get("unified_disclosures"), list):
        raise HarnessError(
            "INVALID_MAPPING_PLAN", "unified_disclosures list is required", str(plan_path)
        )
    if plan.get("schema_version") != "1.0.0":
        raise HarnessError("INVALID_MAPPING_PLAN", "schema_version must be 1.0.0", str(plan_path))

    ledger_records: list[dict[str, Any]] = []
    assigned_requirements: dict[str, str] = {}
    seen_unified: set[str] = set()
    seen_mapping_ids: set[str] = set()
    seen_link_ids: set[str] = set()
    for index, raw_unified in enumerate(plan["unified_disclosures"]):
        path = f"unified_disclosures[{index}]"
        if not isinstance(raw_unified, dict):
            raise HarnessError("INVALID_MAPPING_PLAN", "Unified disclosure must be an object", path)
        unified_id = _required_text(raw_unified, "unified_id", path)
        if unified_id in seen_unified:
            raise HarnessError("DUPLICATE_ID", f"Duplicate unified_id {unified_id}", path)
        seen_unified.add(unified_id)
        mappings = _parse_mappings(raw_unified.get("mappings"), path)
        if not mappings:
            raise HarnessError(
                "MISSING_VALUE", "At least one mapping is required", f"{path}.mappings"
            )
        for mapping in mappings:
            if mapping.mapping_id in seen_mapping_ids:
                raise HarnessError("DUPLICATE_ID", f"Duplicate mapping_id {mapping.mapping_id}")
            seen_mapping_ids.add(mapping.mapping_id)
            if mapping.requirement_id not in requirement_by_id:
                raise HarnessError(
                    "UNKNOWN_REQUIREMENT",
                    f"Unknown requirement_id {mapping.requirement_id}",
                    f"{path}.mappings",
                )
            previous = assigned_requirements.get(mapping.requirement_id)
            if previous:
                raise HarnessError(
                    "REQUIREMENT_MAPPED_MORE_THAN_ONCE",
                    f"{mapping.requirement_id} is already assigned to {previous}",
                    f"{path}.mappings",
                )
            assigned_requirements[mapping.requirement_id] = unified_id
        requirement_ids = [mapping.requirement_id for mapping in mappings]
        links = _parse_evidence_links(
            raw_unified.get("evidence_links", []),
            path,
            set(requirement_ids),
            evidence_by_id,
        )
        for link in links:
            if link.link_id in seen_link_ids:
                raise HarnessError("DUPLICATE_ID", f"Duplicate link_id {link.link_id}")
            seen_link_ids.add(link.link_id)
        linked_evidence_ids = list(dict.fromkeys(link.evidence_id for link in links))
        ledger_records.append(
            {
                "ledger_id": f"LED-{unified_id}",
                "unified_disclosure": {
                    "unified_id": unified_id,
                    "title": _required_text(raw_unified, "title", path),
                    "description": _required_text(raw_unified, "description", path),
                    "requirement_ids": requirement_ids,
                    "mapping_notes": raw_unified.get("mapping_notes"),
                    "review_status": "draft",
                },
                "requirements": [
                    requirement_by_id[requirement_id].to_dict()
                    for requirement_id in requirement_ids
                ],
                "mappings": [item.to_dict() for item in mappings],
                "evidence": [evidence_by_id[item].to_dict() for item in linked_evidence_ids],
                "evidence_links": [item.to_dict() for item in links],
                "gaps": [],
                "content": [],
                "assessments": [],
                "review_status": "unreviewed",
            }
        )

    missing = set(requirement_by_id) - set(assigned_requirements)
    if missing:
        raise HarnessError(
            "INCOMPLETE_REQUIREMENT_UNION",
            "Every locked requirement must appear exactly once",
            details={"missing_requirement_ids": sorted(missing)},
        )
    if previous_records:
        _merge_human_reviews(previous_records, ledger_records)
    else:
        _synchronize_gaps(ledger_records)
    errors = validate_ledger(ledger_records)
    if errors:
        raise HarnessError(
            "INVALID_REQUIREMENT_UNION",
            "Generated ledger failed validation",
            details={"errors": errors},
        )
    write_jsonl(project_dir / LEDGER_PATH, ledger_records)
    summary = _write_union_summary(project_dir, ledger_records)
    if state == "building_requirement_union":
        store.transition("awaiting_evidence_confirmation")
    store.set_checkpoint(
        "evidence",
        "awaiting_confirmation",
        artifacts=[LEDGER_PATH.as_posix(), UNION_PATH.as_posix(), EVIDENCE_PATH.as_posix()],
        notes="Confirm mappings, evidence relationships, conflicts, and evidence gaps",
    )
    append_event(
        project_dir,
        project_id=str(load_project_config(project_dir)["project_id"]),
        event="requirement_union.rebuilt" if is_replacement else "requirement_union.built",
        message=(
            "Corrected requirement union built and awaiting human confirmation"
            if is_replacement
            else "Requirement union built and awaiting human confirmation"
        ),
        details={
            "requirements": summary["requirements_total"],
            "unified_disclosures": summary["unified_disclosures_total"],
            "gaps": summary["gaps_total"],
        },
    )
    return {"valid": True, "workflow_state": "awaiting_evidence_confirmation", **summary}


def review_mapping(
    project_dir: Path,
    mapping_id: str,
    decision: str,
    *,
    reviewed_by: str,
    mapping_type: str | None = None,
    difference_notes: str | None = None,
    review_notes: str | None = None,
) -> dict[str, Any]:
    changes = {
        "mapping_type": mapping_type,
        "difference_notes": difference_notes,
        "review_notes": review_notes,
    }
    return _review_item(
        project_dir,
        collection="mappings",
        id_field="mapping_id",
        item_id=mapping_id,
        decision=decision,
        reviewed_by=reviewed_by,
        changes=changes,
        model_type=RequirementMapping,
    )


def review_evidence_link(
    project_dir: Path,
    link_id: str,
    decision: str,
    *,
    reviewed_by: str,
    relationship: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    return _review_item(
        project_dir,
        collection="evidence_links",
        id_field="link_id",
        item_id=link_id,
        decision=decision,
        reviewed_by=reviewed_by,
        changes={"relationship": relationship, "notes": notes},
        model_type=EvidenceLink,
    )


def review_gap(
    project_dir: Path,
    gap_id: str,
    decision: str,
    *,
    reviewed_by: str,
    criticality: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    return _review_item(
        project_dir,
        collection="gaps",
        id_field="gap_id",
        item_id=gap_id,
        decision=decision,
        reviewed_by=reviewed_by,
        changes={"criticality": criticality, "notes": notes},
        model_type=EvidenceGap,
    )


def union_review_status(project_dir: Path) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    records = read_jsonl(project_dir / LEDGER_PATH)
    summary = _write_union_summary(project_dir, records)
    return {"workflow_state": WorkflowStore(project_dir).load()["workflow_state"], **summary}


def finalize_requirement_union(
    project_dir: Path, *, reviewed_by: str, notes: str | None = None
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    _require_review_state(project_dir)
    if not reviewed_by.strip():
        raise HarnessError("APPROVER_REQUIRED", "reviewed_by is required")
    records = read_jsonl(project_dir / LEDGER_PATH)
    blockers: list[dict[str, str]] = []
    for record in records:
        for collection, id_field in (
            ("mappings", "mapping_id"),
            ("evidence_links", "link_id"),
            ("gaps", "gap_id"),
        ):
            for item in record.get(collection, []):
                if item.get("review_status") not in {"accepted", "edited"}:
                    blockers.append(
                        {
                            "item_id": str(item.get(id_field, "unknown")),
                            "reason": f"{collection} review is {item.get('review_status')}",
                        }
                    )
        for gap in record.get("gaps", []):
            if gap.get("criticality") == "needs_confirmation":
                blockers.append(
                    {
                        "item_id": str(gap.get("gap_id", "unknown")),
                        "reason": "gap criticality needs confirmation",
                    }
                )
    if blockers:
        raise HarnessError(
            "EVIDENCE_REVIEW_INCOMPLETE",
            "Mappings, evidence relationships, conflicts, and gaps require human decisions",
            details={"blockers": blockers},
        )
    for record in records:
        record["unified_disclosure"]["review_status"] = "reviewed"
        record["review_status"] = "accepted"
    errors = validate_ledger(records)
    if errors:
        raise HarnessError(
            "INVALID_REQUIREMENT_UNION", "Reviewed ledger is invalid", details={"errors": errors}
        )
    write_jsonl(project_dir / LEDGER_PATH, records)
    summary = _write_union_summary(project_dir, records)
    store = WorkflowStore(project_dir)
    store.set_checkpoint(
        "evidence",
        "approved",
        approved_by=reviewed_by,
        artifacts=[LEDGER_PATH.as_posix(), UNION_PATH.as_posix(), EVIDENCE_PATH.as_posix()],
        notes=notes or "Mappings, evidence relationships, conflicts, and gaps confirmed",
    )
    store.transition("generating_outline")
    append_event(
        project_dir,
        project_id=str(load_project_config(project_dir)["project_id"]),
        event="requirement_union.approved",
        message="Human reviewer approved the requirement union and evidence checkpoint",
        details={"reviewed_by": reviewed_by},
    )
    return {"valid": True, "workflow_state": "generating_outline", **summary}


def validate_union_completeness(project_dir: Path) -> list[str]:
    project_dir = project_dir.resolve()
    if (
        not (project_dir / LOCK_PATH).is_file()
        or not (project_dir / LEDGER_PATH).is_file()
        or not (project_dir / UNION_PATH).is_file()
    ):
        return []
    try:
        lock = read_json(project_dir / LOCK_PATH)
        requirements = _locked_requirements(lock, load_project_config(project_dir))
        records = read_jsonl(project_dir / LEDGER_PATH)
    except HarnessError as exc:
        return [str(exc)]
    expected = {item.requirement_id for item in requirements}
    occurrences: dict[str, int] = {item: 0 for item in expected}
    errors: list[str] = []
    for record in records:
        for mapping in record.get("mappings", []):
            requirement_id = mapping.get("requirement_id")
            if requirement_id not in occurrences:
                errors.append(f"mappings: unknown requirement_id {requirement_id}")
            else:
                occurrences[requirement_id] += 1
    for requirement_id, count in sorted(occurrences.items()):
        if count != 1:
            errors.append(f"requirement {requirement_id}: expected one mapping, found {count}")
    return errors


def _locked_requirements(lock: Any, config: dict[str, Any]) -> list[Requirement]:
    if not isinstance(lock, dict) or not isinstance(lock.get("standards"), list):
        raise HarnessError("INVALID_STANDARD_LOCK", "standards list is required")
    requirements: list[Requirement] = []
    for package in lock["standards"]:
        for raw in package["requirements"]:
            requirements.append(Requirement.from_dict(raw))
    for index, raw in enumerate(config.get("custom_requirements", [])):
        if not isinstance(raw, dict):
            raise HarnessError(
                "INVALID_CUSTOM_REQUIREMENT", "Custom requirement must be an object", str(index)
            )
        requirements.append(Requirement.from_dict(raw))
    ids = [item.requirement_id for item in requirements]
    if len(ids) != len(set(ids)):
        raise HarnessError("DUPLICATE_REQUIREMENT_ID", "Requirement IDs must be globally unique")
    return requirements


def _parse_mappings(raw_items: Any, path: str) -> list[RequirementMapping]:
    if not isinstance(raw_items, list):
        raise HarnessError("INVALID_MAPPING_PLAN", "mappings must be a list", f"{path}.mappings")
    output: list[RequirementMapping] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise HarnessError(
                "INVALID_MAPPING_PLAN", "Mapping must be an object", f"{path}.mappings[{index}]"
            )
        output.append(RequirementMapping.from_dict(raw))
    return output


def _parse_evidence_links(
    raw_items: Any,
    path: str,
    requirement_ids: set[str],
    evidence_by_id: dict[str, Evidence],
) -> list[EvidenceLink]:
    if not isinstance(raw_items, list):
        raise HarnessError(
            "INVALID_MAPPING_PLAN", "evidence_links must be a list", f"{path}.evidence_links"
        )
    output: list[EvidenceLink] = []
    for index, raw in enumerate(raw_items):
        item_path = f"{path}.evidence_links[{index}]"
        if not isinstance(raw, dict):
            raise HarnessError("INVALID_MAPPING_PLAN", "Evidence link must be an object", item_path)
        link = EvidenceLink.from_dict(raw)
        evidence = evidence_by_id.get(link.evidence_id)
        if evidence is None:
            raise HarnessError(
                "UNKNOWN_EVIDENCE", f"Unknown evidence_id {link.evidence_id}", item_path
            )
        if evidence.classification != "client_evidence":
            raise HarnessError(
                "PEER_EVIDENCE_NOT_ALLOWED",
                "Peer references cannot support customer disclosure requirements",
                item_path,
            )
        unknown = set(link.requirement_ids) - requirement_ids
        if unknown:
            raise HarnessError(
                "UNKNOWN_REQUIREMENT",
                "Evidence link references requirements outside its unified disclosure",
                item_path,
                {"requirement_ids": sorted(unknown)},
            )
        output.append(link)
    return output


def _synchronize_gaps(records: list[dict[str, Any]]) -> None:
    for record in records:
        covered = {
            requirement_id
            for link in record.get("evidence_links", [])
            if link.get("relationship") in {"direct", "supporting"}
            and link.get("review_status") != "rejected"
            for requirement_id in link.get("requirement_ids", [])
        }
        existing = {
            gap.get("requirement_id"): gap
            for gap in record.get("gaps", [])
            if isinstance(gap, dict)
        }
        gaps = []
        for requirement_id in record["unified_disclosure"]["requirement_ids"]:
            if requirement_id in covered:
                continue
            gaps.append(existing.get(requirement_id) or _new_gap(requirement_id))
        record["gaps"] = gaps


def _new_gap(requirement_id: str) -> dict[str, Any]:
    digest = hashlib.sha256(requirement_id.encode()).hexdigest()[:16].upper()
    return EvidenceGap(
        gap_id=f"GAP-{digest}",
        requirement_id=requirement_id,
        reason="No direct or supporting client evidence is linked",
        criticality="needs_confirmation",
        review_status="unreviewed",
    ).to_dict()


def _merge_human_reviews(
    previous_records: list[dict[str, Any]], new_records: list[dict[str, Any]]
) -> None:
    previous_mappings = _indexed_items(previous_records, "mappings", "mapping_id")
    previous_links = _indexed_items(previous_records, "evidence_links", "link_id")
    for record in new_records:
        unified_id = record["unified_disclosure"]["unified_id"]
        for index, mapping in enumerate(record.get("mappings", [])):
            previous = previous_mappings.get(mapping.get("mapping_id"))
            if not previous or previous[0] != unified_id:
                continue
            old = previous[1]
            same_requirement = old.get("requirement_id") == mapping.get("requirement_id")
            unchanged = all(
                old.get(field) == mapping.get(field)
                for field in ("requirement_id", "mapping_type", "difference_notes", "mapped_by")
            )
            if same_requirement and (
                old.get("review_status") == "edited"
                or (old.get("review_status") == "accepted" and unchanged)
            ):
                record["mappings"][index] = dict(old)
        for index, link in enumerate(record.get("evidence_links", [])):
            previous = previous_links.get(link.get("link_id"))
            if not previous or previous[0] != unified_id:
                continue
            old = previous[1]
            same_scope = old.get("evidence_id") == link.get("evidence_id") and set(
                old.get("requirement_ids", [])
            ) == set(link.get("requirement_ids", []))
            unchanged = same_scope and old.get("relationship") == link.get("relationship")
            if same_scope and (
                old.get("review_status") == "edited"
                or (old.get("review_status") == "accepted" and unchanged)
            ):
                record["evidence_links"][index] = dict(old)
    _synchronize_gaps(new_records)
    previous_gaps = _indexed_items(previous_records, "gaps", "gap_id")
    for record in new_records:
        for index, gap in enumerate(record.get("gaps", [])):
            previous = previous_gaps.get(gap.get("gap_id"))
            if previous and previous[1].get("review_status") in {"accepted", "edited"}:
                record["gaps"][index] = dict(previous[1])


def _indexed_items(
    records: list[dict[str, Any]], collection: str, id_field: str
) -> dict[str, tuple[str, dict[str, Any]]]:
    return {
        str(item[id_field]): (str(record["unified_disclosure"]["unified_id"]), item)
        for record in records
        for item in record.get(collection, [])
        if isinstance(item, dict) and item.get(id_field)
    }


def _review_item(
    project_dir: Path,
    *,
    collection: str,
    id_field: str,
    item_id: str,
    decision: str,
    reviewed_by: str,
    changes: dict[str, Any],
    model_type: type,
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    _require_review_state(project_dir)
    if decision not in REVIEW_DECISIONS:
        raise HarnessError(
            "INVALID_REVIEW_DECISION", f"Decision must be one of {sorted(REVIEW_DECISIONS)}"
        )
    if not reviewed_by.strip():
        raise HarnessError("APPROVER_REQUIRED", "reviewed_by is required")
    records = read_jsonl(project_dir / LEDGER_PATH)
    found = False
    for record in records:
        for raw in record.get(collection, []):
            if raw.get(id_field) != item_id:
                continue
            found = True
            raw["review_status"] = decision
            raw["reviewed_by"] = reviewed_by
            for key, value in changes.items():
                if value is not None:
                    raw[key] = value
            model_type.from_dict(raw)
    if not found:
        raise HarnessError("REVIEW_ITEM_NOT_FOUND", f"Unknown {id_field} {item_id}")
    _synchronize_gaps(records)
    errors = validate_ledger(records)
    if errors:
        raise HarnessError(
            "INVALID_REVIEW_UPDATE", "Review update is invalid", details={"errors": errors}
        )
    write_jsonl(project_dir / LEDGER_PATH, records)
    summary = _write_union_summary(project_dir, records)
    config = load_project_config(project_dir)
    append_event(
        project_dir,
        project_id=str(config["project_id"]),
        event=f"requirement_union.{collection}.reviewed",
        message=f"Human reviewer recorded {decision} for {item_id}",
        details={"item_id": item_id, "decision": decision, "reviewed_by": reviewed_by},
    )
    return {"valid": True, "reviewed_item": item_id, "decision": decision, **summary}


def _require_review_state(project_dir: Path) -> None:
    state = WorkflowStore(project_dir).load()["workflow_state"]
    if state != "awaiting_evidence_confirmation":
        raise HarnessError(
            "EVIDENCE_REVIEW_NOT_ALLOWED",
            "Evidence review is only allowed while awaiting evidence confirmation",
            "workflow_state",
        )


def _write_union_summary(project_dir: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    mappings = [item for record in records for item in record.get("mappings", [])]
    links = [item for record in records for item in record.get("evidence_links", [])]
    gaps = [item for record in records for item in record.get("gaps", [])]
    requirements = [item for record in records for item in record.get("requirements", [])]
    covered_requirement_ids = {
        requirement_id
        for link in links
        if link.get("relationship") in {"direct", "supporting"}
        and link.get("review_status") != "rejected"
        for requirement_id in link.get("requirement_ids", [])
    }
    standards: list[dict[str, Any]] = []
    standard_ids = sorted({item.get("standard_id") for item in requirements})
    for standard_id in standard_ids:
        standard_requirements = {
            item.get("requirement_id")
            for item in requirements
            if item.get("standard_id") == standard_id
        }
        standards.append(
            {
                "standard_id": standard_id,
                "requirements_total": len(standard_requirements),
                "evidence_covered": len(standard_requirements & covered_requirement_ids),
                "gaps": len(standard_requirements - covered_requirement_ids),
            }
        )
    summary = {
        "schema_version": "1.0.0",
        "requirements_total": len(mappings),
        "unified_disclosures_total": len(records),
        "mappings_unreviewed": sum(item.get("review_status") == "unreviewed" for item in mappings),
        "mappings_rejected": sum(item.get("review_status") == "rejected" for item in mappings),
        "mapping_types": {
            mapping_type: sum(item.get("mapping_type") == mapping_type for item in mappings)
            for mapping_type in sorted(RequirementMapping.MAPPING_TYPES)
        },
        "evidence_links_total": len(links),
        "evidence_links_unreviewed": sum(
            item.get("review_status") == "unreviewed" for item in links
        ),
        "evidence_links_rejected": sum(item.get("review_status") == "rejected" for item in links),
        "requirements_evidence_covered": len(covered_requirement_ids),
        "contradicting_links_total": sum(
            item.get("relationship") == "contradicting" for item in links
        ),
        "gaps_total": len(gaps),
        "gaps_unreviewed": sum(item.get("review_status") == "unreviewed" for item in gaps),
        "gaps_rejected": sum(item.get("review_status") == "rejected" for item in gaps),
        "standards": standards,
        "requirement_ids": sorted(item.get("requirement_id") for item in mappings),
    }
    write_json(project_dir / UNION_PATH, summary)
    return summary


def _required_text(value: dict[str, Any], key: str, path: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise HarnessError("MISSING_VALUE", f"{key} must be a non-empty string", f"{path}.{key}")
    return item
