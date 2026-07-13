"""Reusable simulated M4 project builders; no confidential or official content."""

from __future__ import annotations

from pathlib import Path

from fixture_builders import write_xlsx
from report_harness.drafting import build_draft, finalize_draft, review_draft_item
from report_harness.ingestion import ingest_project_sources
from report_harness.io import read_json, read_jsonl, write_json
from report_harness.mapping import (
    build_requirement_union,
    finalize_requirement_union,
    review_evidence_link,
    review_gap,
    review_mapping,
)
from report_harness.outline import build_formal_outline, review_outline
from test_mapping import create_m3_project, mapping_plan


def prepare_outline_project(tmp_path: Path, *, with_peer: bool = False) -> tuple[Path, str | None]:
    project, client_evidence_id = create_m3_project(tmp_path)
    peer_evidence_id = None
    if with_peer:
        write_xlsx(project / "sources/peer/peer.xlsx")
        ingest_project_sources(project)
        peer_evidence_id = next(
            item["evidence_id"]
            for item in read_jsonl(project / "state/evidence.jsonl")
            if item["classification"] == "peer_reference" and "Emissions" in item["excerpt"]
        )
    plan_path = tmp_path / "mapping-plan.json"
    write_json(plan_path, mapping_plan(client_evidence_id))
    build_requirement_union(project, plan_path)
    ledger = read_jsonl(project / "state/disclosure_ledger.jsonl")
    for mapping in [item for row in ledger for item in row["mappings"]]:
        review_mapping(project, mapping["mapping_id"], "accepted", reviewed_by="consultant")
    review_evidence_link(
        project,
        "SIM-LINK-EMISSIONS",
        "accepted",
        reviewed_by="consultant",
    )
    ledger = read_jsonl(project / "state/disclosure_ledger.jsonl")
    for gap in [item for row in ledger for item in row["gaps"]]:
        review_gap(
            project,
            gap["gap_id"],
            "accepted",
            reviewed_by="consultant",
            criticality="critical",
            notes="保留为模拟补件缺口。",
        )
    finalize_requirement_union(project, reviewed_by="consultant")
    return project, peer_evidence_id


def outline_plan() -> dict:
    return {
        "schema_version": "1.0.0",
        "anchor_section_id": "SEC-ENV",
        "sections": [
            {
                "section_id": "SEC-SCOPE",
                "title": "报告范围",
                "objective": "说明模拟报告的组织与期间范围。",
                "target_length_words": 300,
                "granularity": "standard",
                "unified_ids": ["SIM-UNI-SCOPE"],
                "tables": [],
                "cases": [],
                "chart_suggestions": [],
            },
            {
                "section_id": "SEC-ENV",
                "title": "环境数据",
                "objective": "披露模拟排放数据、期间和单位。",
                "target_length_words": 500,
                "granularity": "detailed",
                "unified_ids": ["SIM-UNI-EMISSIONS"],
                "tables": ["模拟排放数据表"],
                "cases": [],
                "chart_suggestions": ["按期间展示模拟数据"],
            },
            {
                "section_id": "SEC-GOV",
                "title": "治理职责",
                "objective": "说明模拟治理职责。",
                "target_length_words": 300,
                "granularity": "standard",
                "unified_ids": ["SIM-UNI-GOVERNANCE"],
                "tables": [],
                "cases": [],
                "chart_suggestions": [],
            },
        ],
        "conflicts": [],
    }


def build_and_approve_outline(project: Path, tmp_path: Path) -> None:
    path = tmp_path / "outline-plan.json"
    write_json(path, outline_plan())
    build_formal_outline(project, path)
    review_outline(project, "approved", reviewed_by="consultant")


def draft_proposal(
    project: Path,
    *,
    stage: str,
    section_ids: set[str],
    peer_evidence_id: str | None = None,
) -> dict:
    outline = read_json(project / "state/outline.json")
    ledger = read_jsonl(project / "state/disclosure_ledger.jsonl")
    row_by_unified = {row["unified_disclosure"]["unified_id"]: row for row in ledger}
    sections = []
    for section in outline["sections"]:
        if section["section_id"] not in section_ids:
            continue
        content = []
        assessments = []
        peers = []
        for unified_id in section["unified_ids"]:
            row = row_by_unified[unified_id]
            evidence_ids = [
                link["evidence_id"]
                for link in row.get("evidence_links", [])
                if link["review_status"] in {"accepted", "edited"}
                and link["relationship"] in {"direct", "supporting"}
            ]
            content_id = f"CNT-{stage}-{unified_id}"
            is_covered = bool(evidence_ids)
            content.append(
                {
                    "content_id": content_id,
                    "section_id": section["section_id"],
                    "text": (
                        "模拟客户资料显示，2025 年模拟排放数据为 12.5，相关期间和单位待顾问核对。"
                        if is_covered
                        else "当前资料未提供该项模拟披露所需信息。"
                    ),
                    "content_type": "confirmed_fact" if is_covered else "information_gap",
                    "unified_ids": [unified_id],
                    "evidence_ids": evidence_ids,
                    "review_status": "unreviewed",
                    "last_modified_by": "agent",
                    "confirmation_note": None,
                }
            )
            for requirement in row["requirements"]:
                requirement_id = requirement["requirement_id"]
                assessments.append(
                    {
                        "assessment_id": f"ASM-{stage}-{requirement_id}",
                        "requirement_id": requirement_id,
                        "response_status": "fully_addressed" if is_covered else "not_addressed",
                        "rationale": "存在模拟直接证据。" if is_covered else "未找到模拟客户证据。",
                        "confidence": "high" if is_covered else "medium",
                        "confidence_reason": "证据已定位。" if is_covered else "缺少客户资料。",
                        "review_status": "unreviewed",
                        "content_ids": [content_id],
                        "evidence_ids": evidence_ids,
                        "missing_information": None if is_covered else "模拟治理或范围资料",
                        "improvement_suggestion": None if is_covered else "补充相关制度或说明。",
                        "human_notes": None,
                    }
                )
                use_peer = bool(peer_evidence_id and unified_id == "SIM-UNI-EMISSIONS")
                peers.append(
                    {
                        "peer_assessment_id": f"PEER-{stage}-{requirement_id}",
                        "requirement_id": requirement_id,
                        "peer_position": "comparable" if use_peer else "not_assessed",
                        "rationale": "模拟同行披露深度相近。" if use_peer else "未确认同行样本。",
                        "review_status": "unreviewed",
                        "evidence_ids": [peer_evidence_id] if use_peer else [],
                        "reviewed_by": None,
                        "human_notes": None,
                    }
                )
        sections.append(
            {
                "section_id": section["section_id"],
                "content": content,
                "assessments": assessments,
                "peer_assessments": peers,
            }
        )
    return {"schema_version": "1.0.0", "stage": stage, "sections": sections}


def build_anchor(project: Path, tmp_path: Path, *, peer_evidence_id: str | None = None) -> None:
    proposal = draft_proposal(
        project,
        stage="anchor",
        section_ids={"SEC-ENV"},
        peer_evidence_id=peer_evidence_id,
    )
    path = tmp_path / "anchor-proposal.json"
    write_json(path, proposal)
    build_draft(project, path, stage="anchor")


def accept_items(project: Path, *, section_ids: set[str], convert_gaps: bool = False) -> None:
    outline = read_json(project / "state/outline.json")
    section_by_unified = {
        unified_id: section["section_id"]
        for section in outline["sections"]
        for unified_id in section["unified_ids"]
    }
    ledger = read_jsonl(project / "state/disclosure_ledger.jsonl")
    for row in ledger:
        unified_id = row["unified_disclosure"]["unified_id"]
        if section_by_unified[unified_id] not in section_ids:
            continue
        for content in row.get("content", []):
            if content["review_status"] in {"accepted", "edited"}:
                continue
            if convert_gaps and content["content_type"] == "information_gap":
                review_draft_item(
                    project,
                    "content",
                    content["content_id"],
                    "edited",
                    reviewed_by="consultant",
                    changes={"content_type": "suggested_text"},
                    notes="顾问确认作为建议文本保留。",
                )
            else:
                review_draft_item(
                    project,
                    "content",
                    content["content_id"],
                    "accepted",
                    reviewed_by="consultant",
                    notes="顾问确认内部粗稿标记。",
                )
        for assessment in row.get("assessments", []):
            if assessment["review_status"] not in {"accepted", "edited"}:
                review_draft_item(
                    project,
                    "assessments",
                    assessment["assessment_id"],
                    "accepted",
                    reviewed_by="consultant",
                    notes="顾问确认模拟评价。",
                )
        for peer in row.get("peer_assessments", []):
            if peer["review_status"] not in {"accepted", "edited"}:
                review_draft_item(
                    project,
                    "peer_assessments",
                    peer["peer_assessment_id"],
                    "accepted",
                    reviewed_by="consultant",
                    notes="顾问确认同行评价与准则评价分开。",
                )


def build_master(project: Path, tmp_path: Path) -> None:
    proposal = draft_proposal(
        project,
        stage="master",
        section_ids={"SEC-SCOPE", "SEC-GOV"},
    )
    path = tmp_path / "master-proposal.json"
    write_json(path, proposal)
    build_draft(project, path, stage="master")


def complete_master(project: Path, tmp_path: Path, *, convert_gaps: bool = False) -> None:
    accept_items(project, section_ids={"SEC-ENV"})
    finalize_draft(project, "anchor", reviewed_by="consultant")
    build_master(project, tmp_path)
    accept_items(
        project,
        section_ids={"SEC-SCOPE", "SEC-GOV"},
        convert_gaps=convert_gaps,
    )
