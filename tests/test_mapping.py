"""M3 union, traceability, and Human-in-the-loop tests mapped to AC-03, AC-04, AC-20."""

from pathlib import Path

import pytest
from fixture_builders import write_xlsx
from report_harness.errors import HarnessError
from report_harness.ingestion import ingest_project_sources
from report_harness.io import read_jsonl, write_json
from report_harness.mapping import (
    build_requirement_union,
    finalize_requirement_union,
    review_evidence_link,
    review_gap,
    review_mapping,
    union_review_status,
    validate_union_completeness,
)
from report_harness.project import validate_project
from report_harness.standards import lock_standard_versions
from report_harness.workflow import WorkflowStore
from test_standards import STANDARD_A, STANDARD_B, create_standard_project


def create_m3_project(tmp_path: Path) -> tuple[Path, str]:
    project = create_standard_project(tmp_path)
    lock_standard_versions(
        project,
        [STANDARD_A, STANDARD_B],
        confirmed_by="standards-reviewer",
        allow_simulated=True,
    )
    write_xlsx(project / "sources/client/metrics.xlsx")
    ingest_project_sources(project)
    evidence = read_jsonl(project / "state/evidence.jsonl")
    evidence_id = next(item["evidence_id"] for item in evidence if "Emissions" in item["excerpt"])
    return project, evidence_id


def mapping_plan(evidence_id: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "unified_disclosures": [
            {
                "unified_id": "SIM-UNI-SCOPE",
                "title": "模拟范围",
                "description": "说明模拟项目范围。",
                "mapping_notes": "准则 A 特有要求。",
                "mappings": [_mapping("SIM-MAP-A1", "SIM-REQ-001", "unique", "仅准则 A 包含。")],
                "evidence_links": [],
            },
            {
                "unified_id": "SIM-UNI-EMISSIONS",
                "title": "模拟排放",
                "description": "披露模拟排放数据、期间和单位。",
                "mapping_notes": "两套模拟准则范围存在重叠。",
                "mappings": [
                    _mapping("SIM-MAP-A2", "SIM-A-REQ-002", "overlapping", "准则 A 要求数据。"),
                    _mapping(
                        "SIM-MAP-A3",
                        "SIM-A-REQ-003",
                        "narrower_than",
                        "准则 A 单独要求期间。",
                    ),
                    _mapping(
                        "SIM-MAP-B1",
                        "SIM-B-REQ-001",
                        "broader_than",
                        "准则 B 同时要求计量单位。",
                    ),
                ],
                "evidence_links": [
                    {
                        "link_id": "SIM-LINK-EMISSIONS",
                        "evidence_id": evidence_id,
                        "requirement_ids": [
                            "SIM-A-REQ-002",
                            "SIM-A-REQ-003",
                            "SIM-B-REQ-001",
                        ],
                        "relationship": "direct",
                        "review_status": "unreviewed",
                        "reviewed_by": None,
                        "notes": None,
                    }
                ],
            },
            {
                "unified_id": "SIM-UNI-GOVERNANCE",
                "title": "模拟治理",
                "description": "说明模拟治理职责。",
                "mapping_notes": "准则 B 特有要求。",
                "mappings": [_mapping("SIM-MAP-B2", "SIM-B-REQ-002", "unique", "仅准则 B 包含。")],
                "evidence_links": [],
            },
        ],
    }


def _mapping(mapping_id: str, requirement_id: str, mapping_type: str, notes: str) -> dict:
    return {
        "mapping_id": mapping_id,
        "requirement_id": requirement_id,
        "mapping_type": mapping_type,
        "difference_notes": notes,
        "review_status": "unreviewed",
        "mapped_by": "agent",
        "reviewed_by": None,
        "review_notes": None,
    }


def test_union_preserves_every_requirement_and_stops_for_human_review(tmp_path: Path):
    project, evidence_id = create_m3_project(tmp_path)
    plan_path = tmp_path / "mapping-plan.json"
    write_json(plan_path, mapping_plan(evidence_id))

    result = build_requirement_union(project, plan_path)
    ledger = read_jsonl(project / "state/disclosure_ledger.jsonl")

    assert result["requirements_total"] == 5
    assert result["unified_disclosures_total"] == 3
    assert result["gaps_total"] == 2
    assert result["workflow_state"] == "awaiting_evidence_confirmation"
    assert {item["requirement_id"] for row in ledger for item in row["mappings"]} == {
        "SIM-REQ-001",
        "SIM-A-REQ-002",
        "SIM-A-REQ-003",
        "SIM-B-REQ-001",
        "SIM-B-REQ-002",
    }
    assert WorkflowStore(project).load()["checkpoints"]["evidence"]["status"] == (
        "awaiting_confirmation"
    )
    assert validate_union_completeness(project) == []
    assert validate_project(project) == []


def test_union_rejects_silent_requirement_loss(tmp_path: Path):
    project, evidence_id = create_m3_project(tmp_path)
    incomplete = mapping_plan(evidence_id)
    incomplete["unified_disclosures"] = incomplete["unified_disclosures"][:-1]
    plan_path = tmp_path / "incomplete-plan.json"
    write_json(plan_path, incomplete)

    with pytest.raises(HarnessError, match="INCOMPLETE_REQUIREMENT_UNION"):
        build_requirement_union(project, plan_path)


def test_peer_reference_cannot_be_used_as_customer_requirement_evidence(tmp_path: Path):
    project, client_evidence_id = create_m3_project(tmp_path)
    write_xlsx(project / "sources/peer/peer-metrics.xlsx")
    ingest_project_sources(project)
    peer_evidence = next(
        item
        for item in read_jsonl(project / "state/evidence.jsonl")
        if item["classification"] == "peer_reference" and "Emissions" in item["excerpt"]
    )
    plan = mapping_plan(client_evidence_id)
    plan["unified_disclosures"][1]["evidence_links"][0]["evidence_id"] = peer_evidence[
        "evidence_id"
    ]
    plan_path = tmp_path / "peer-plan.json"
    write_json(plan_path, plan)

    with pytest.raises(HarnessError, match="PEER_EVIDENCE_NOT_ALLOWED"):
        build_requirement_union(project, plan_path)


def test_rejected_evidence_relationship_becomes_explicit_gaps(tmp_path: Path):
    project, evidence_id = create_m3_project(tmp_path)
    plan_path = tmp_path / "mapping-plan.json"
    write_json(plan_path, mapping_plan(evidence_id))
    build_requirement_union(project, plan_path)

    result = review_evidence_link(
        project,
        "SIM-LINK-EMISSIONS",
        "rejected",
        reviewed_by="consultant",
        notes="证据范围不足。",
    )

    assert result["evidence_links_rejected"] == 1
    assert result["requirements_evidence_covered"] == 0
    assert result["gaps_total"] == 5


def test_corrected_plan_preserves_unchanged_reviews_and_resets_changed_items(tmp_path: Path):
    project, evidence_id = create_m3_project(tmp_path)
    plan = mapping_plan(evidence_id)
    plan_path = tmp_path / "mapping-plan.json"
    write_json(plan_path, plan)
    build_requirement_union(project, plan_path)
    review_mapping(project, "SIM-MAP-A1", "accepted", reviewed_by="consultant")
    review_mapping(project, "SIM-MAP-A2", "rejected", reviewed_by="consultant")

    plan["unified_disclosures"][1]["mappings"][0]["difference_notes"] = (
        "顾问要求重新描述准则 A 的数据范围。"
    )
    write_json(plan_path, plan)
    build_requirement_union(project, plan_path, replace=True)
    ledger = read_jsonl(project / "state/disclosure_ledger.jsonl")
    mappings = {item["mapping_id"]: item for row in ledger for item in row["mappings"]}

    assert mappings["SIM-MAP-A1"]["review_status"] == "accepted"
    assert mappings["SIM-MAP-A1"]["reviewed_by"] == "consultant"
    assert mappings["SIM-MAP-A2"]["review_status"] == "unreviewed"
    assert mappings["SIM-MAP-A2"]["reviewed_by"] is None
    assert WorkflowStore(project).load()["workflow_state"] == "awaiting_evidence_confirmation"


def test_human_review_is_required_before_outline_and_persists_across_agents(tmp_path: Path):
    project, evidence_id = create_m3_project(tmp_path)
    plan_path = tmp_path / "mapping-plan.json"
    write_json(plan_path, mapping_plan(evidence_id))
    build_requirement_union(project, plan_path)

    with pytest.raises(HarnessError, match="EVIDENCE_REVIEW_INCOMPLETE"):
        finalize_requirement_union(project, reviewed_by="consultant")

    ledger = read_jsonl(project / "state/disclosure_ledger.jsonl")
    for mapping in [item for row in ledger for item in row["mappings"]]:
        review_mapping(
            project,
            mapping["mapping_id"],
            "accepted",
            reviewed_by="consultant",
        )
    review_evidence_link(
        project,
        "SIM-LINK-EMISSIONS",
        "accepted",
        reviewed_by="consultant",
    )
    current = union_review_status(project)
    assert current["gaps_total"] == 2
    ledger = read_jsonl(project / "state/disclosure_ledger.jsonl")
    for gap in [item for row in ledger for item in row["gaps"]]:
        review_gap(
            project,
            gap["gap_id"],
            "accepted",
            reviewed_by="consultant",
            criticality="critical",
            notes="顾问确认保留为补件缺口。",
        )

    result = finalize_requirement_union(project, reviewed_by="consultant")

    assert result["workflow_state"] == "generating_outline"
    restored = WorkflowStore(project).load()
    assert restored["workflow_state"] == "generating_outline"
    assert restored["checkpoints"]["evidence"]["status"] == "approved"
    assert restored["checkpoints"]["evidence"]["approved_by"] == "consultant"
