"""Disclosure ledger validation and export gating."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import read_jsonl
from .models import (
    Assessment,
    DisclosureContent,
    Evidence,
    EvidenceGap,
    EvidenceLink,
    PeerAssessment,
    Requirement,
    RequirementMapping,
    UnifiedDisclosure,
)

REQUIRED_ENTRY_FIELDS = {
    "ledger_id",
    "unified_disclosure",
    "requirements",
    "evidence",
    "content",
    "assessments",
    "review_status",
}


def validate_ledger_file(path: Path) -> list[str]:
    return validate_ledger(read_jsonl(path))


def validate_ledger(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    ledger_ids: set[str] = set()
    unified_ids: set[str] = set()
    mapping_ids: set[str] = set()
    link_ids: set[str] = set()
    gap_ids: set[str] = set()
    content_ids_global: set[str] = set()
    assessment_ids_global: set[str] = set()
    peer_assessment_ids_global: set[str] = set()
    for index, record in enumerate(records):
        prefix = f"line {index + 1}"
        missing = REQUIRED_ENTRY_FIELDS - record.keys()
        for key in sorted(missing):
            errors.append(f"{prefix}.{key}: required field is missing")
        ledger_id = record.get("ledger_id")
        if not isinstance(ledger_id, str) or not ledger_id.strip():
            errors.append(f"{prefix}.ledger_id: non-empty string required")
        elif ledger_id in ledger_ids:
            errors.append(f"{prefix}.ledger_id: duplicate ID {ledger_id}")
        else:
            ledger_ids.add(ledger_id)

        unified = _model(UnifiedDisclosure, record.get("unified_disclosure"), prefix, errors)
        requirements = _models(
            Requirement, record.get("requirements"), f"{prefix}.requirements", errors
        )
        evidence = _models(Evidence, record.get("evidence"), f"{prefix}.evidence", errors)
        mappings = _models(
            RequirementMapping, record.get("mappings", []), f"{prefix}.mappings", errors
        )
        evidence_links = _models(
            EvidenceLink,
            record.get("evidence_links", []),
            f"{prefix}.evidence_links",
            errors,
        )
        gaps = _models(EvidenceGap, record.get("gaps", []), f"{prefix}.gaps", errors)
        content = _models(DisclosureContent, record.get("content"), f"{prefix}.content", errors)
        assessments = _models(
            Assessment, record.get("assessments"), f"{prefix}.assessments", errors
        )
        peer_assessments = _models(
            PeerAssessment,
            record.get("peer_assessments", []),
            f"{prefix}.peer_assessments",
            errors,
        )

        if unified is None:
            continue
        if unified.unified_id in unified_ids:
            errors.append(
                f"{prefix}.unified_disclosure.unified_id: duplicate ID {unified.unified_id}"
            )
        unified_ids.add(unified.unified_id)
        requirement_ids = {item.requirement_id for item in requirements}
        evidence_ids = {item.evidence_id for item in evidence}
        content_ids = {item.content_id for item in content}
        _duplicates(requirement_ids, requirements, "requirement_id", prefix, errors)
        _duplicates(evidence_ids, evidence, "evidence_id", prefix, errors)
        _duplicates(content_ids, content, "content_id", prefix, errors)

        missing_requirements = set(unified.requirement_ids) - requirement_ids
        if missing_requirements:
            missing_text = sorted(missing_requirements)
            errors.append(
                f"{prefix}.unified_disclosure.requirement_ids: missing records {missing_text}"
            )
        if mappings:
            mapped_requirement_ids = [item.requirement_id for item in mappings]
            if set(mapped_requirement_ids) != set(unified.requirement_ids):
                errors.append(
                    f"{prefix}.mappings: must cover each unified requirement exactly once"
                )
            if len(mapped_requirement_ids) != len(set(mapped_requirement_ids)):
                errors.append(f"{prefix}.mappings: requirement IDs must be unique")
        for mapping in mappings:
            _global_id(mapping.mapping_id, mapping_ids, "mapping_id", prefix, errors)
        for link in evidence_links:
            _global_id(link.link_id, link_ids, "link_id", prefix, errors)
            if link.evidence_id not in evidence_ids:
                errors.append(f"{prefix}.evidence_links.{link.link_id}: unknown evidence_id")
            _missing_refs(
                link.requirement_ids,
                requirement_ids,
                f"{prefix}.evidence_links.{link.link_id}.requirement_ids",
                errors,
            )
        for gap in gaps:
            _global_id(gap.gap_id, gap_ids, "gap_id", prefix, errors)
            if gap.requirement_id not in requirement_ids:
                errors.append(f"{prefix}.gaps.{gap.gap_id}: unknown requirement_id")
        for item in content:
            _global_id(item.content_id, content_ids_global, "content_id", prefix, errors)
            if unified.unified_id not in item.unified_ids:
                errors.append(
                    f"{prefix}.content.{item.content_id}: does not reference {unified.unified_id}"
                )
            _missing_refs(
                item.evidence_ids,
                evidence_ids,
                f"{prefix}.content.{item.content_id}.evidence_ids",
                errors,
            )
        for item in assessments:
            _global_id(item.assessment_id, assessment_ids_global, "assessment_id", prefix, errors)
            if item.requirement_id not in requirement_ids:
                errors.append(f"{prefix}.assessments.{item.assessment_id}: unknown requirement_id")
            _missing_refs(
                item.content_ids,
                content_ids,
                f"{prefix}.assessments.{item.assessment_id}.content_ids",
                errors,
            )
            _missing_refs(
                item.evidence_ids,
                evidence_ids,
                f"{prefix}.assessments.{item.assessment_id}.evidence_ids",
                errors,
            )
        evidence_by_id = {item.evidence_id: item for item in evidence}
        for item in peer_assessments:
            _global_id(
                item.peer_assessment_id,
                peer_assessment_ids_global,
                "peer_assessment_id",
                prefix,
                errors,
            )
            if item.requirement_id not in requirement_ids:
                errors.append(
                    f"{prefix}.peer_assessments.{item.peer_assessment_id}: unknown requirement_id"
                )
            _missing_refs(
                item.evidence_ids,
                evidence_ids,
                f"{prefix}.peer_assessments.{item.peer_assessment_id}.evidence_ids",
                errors,
            )
            for evidence_id in item.evidence_ids:
                peer_evidence = evidence_by_id.get(evidence_id)
                if peer_evidence and peer_evidence.classification != "peer_reference":
                    errors.append(
                        f"{prefix}.peer_assessments.{item.peer_assessment_id}: "
                        "peer comparison requires peer_reference evidence"
                    )
    return errors


def preflight_clean_export(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    for record in records:
        for raw in record.get("content", []):
            if not isinstance(raw, dict):
                continue
            content_type = raw.get("content_type")
            review_status = raw.get("review_status")
            evidence_ids = raw.get("evidence_ids") or []
            confirmation_note = raw.get("confirmation_note")
            reason: str | None = None
            if content_type == "information_gap":
                reason = "information_gap cannot enter a clean export"
            elif content_type in {"inference", "suggested_text"} and review_status not in {
                "accepted",
                "edited",
            }:
                reason = f"{content_type} has not been accepted or edited by a reviewer"
            elif (
                content_type in {"inference", "suggested_text"}
                and not evidence_ids
                and not confirmation_note
            ):
                reason = f"{content_type} requires evidence or a human confirmation note"
            elif content_type == "confirmed_fact" and not evidence_ids:
                reason = "confirmed_fact requires client evidence"
            if reason:
                blockers.append(
                    {
                        "content_id": str(raw.get("content_id", "unknown")),
                        "section_id": str(raw.get("section_id", "unknown")),
                        "reason": reason,
                    }
                )
    return blockers


def _model(model_type: type, value: Any, path: str, errors: list[str]):
    if not isinstance(value, dict):
        errors.append(f"{path}: object required")
        return None
    try:
        return model_type.from_dict(value)
    except Exception as exc:  # Structured model errors are rendered consistently here.
        errors.append(f"{path}: {exc}")
        return None


def _models(model_type: type, value: Any, path: str, errors: list[str]) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{path}: list required")
        return []
    output = []
    for index, item in enumerate(value):
        model = _model(model_type, item, f"{path}[{index}]", errors)
        if model is not None:
            output.append(model)
    return output


def _duplicates(
    ids: set[str], values: list[Any], attribute: str, path: str, errors: list[str]
) -> None:
    if len(ids) != len(values):
        errors.append(f"{path}.{attribute}: IDs must be unique within a ledger entry")


def _missing_refs(values: list[str], known: set[str], path: str, errors: list[str]) -> None:
    missing = set(values) - known
    if missing:
        errors.append(f"{path}: unknown references {sorted(missing)}")


def _global_id(value: str, known: set[str], field: str, path: str, errors: list[str]) -> None:
    if value in known:
        errors.append(f"{path}.{field}: duplicate ID {value}")
    known.add(value)
