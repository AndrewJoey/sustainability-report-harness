"""M4 dynamic outline and Outline Checkpoint tests mapped to AC-20 and AC-21."""

from pathlib import Path

import pytest
from m4_helpers import outline_plan, prepare_outline_project
from report_harness.errors import HarnessError
from report_harness.io import read_json, read_jsonl, write_json
from report_harness.outline import build_formal_outline, review_outline, validate_outline
from report_harness.workflow import WorkflowStore


def test_formal_outline_derives_coverage_and_covers_union_once(tmp_path: Path):
    project, _ = prepare_outline_project(tmp_path)
    proposal = tmp_path / "outline.json"
    write_json(proposal, outline_plan())

    result = build_formal_outline(project, proposal)
    outline = read_json(project / "state/outline.json")

    assert result["workflow_state"] == "awaiting_outline_confirmation"
    assert result["sections"] == 3
    assert outline["anchor_section_id"] == "SEC-ENV"
    assert outline["sections"][1]["evidence_coverage"] == {
        "covered_requirements": 3,
        "total_requirements": 3,
    }
    assert outline["sections"][0]["expected_gap_ids"]
    assert WorkflowStore(project).load()["checkpoints"]["outline"]["status"] == (
        "awaiting_confirmation"
    )


def test_outline_rejects_silent_unified_disclosure_loss(tmp_path: Path):
    project, _ = prepare_outline_project(tmp_path)
    plan = outline_plan()
    plan["sections"] = plan["sections"][:-1]
    proposal = tmp_path / "incomplete-outline.json"
    write_json(proposal, plan)

    with pytest.raises(HarnessError, match="INVALID_OUTLINE_PROPOSAL"):
        build_formal_outline(project, proposal)


def test_outline_change_request_blocks_anchor_transition(tmp_path: Path):
    project, _ = prepare_outline_project(tmp_path)
    proposal = tmp_path / "outline.json"
    write_json(proposal, outline_plan())
    build_formal_outline(project, proposal)

    result = review_outline(
        project,
        "changes_requested",
        reviewed_by="consultant",
        notes="调整章节篇幅。",
    )

    assert result["workflow_state"] == "awaiting_outline_confirmation"
    assert WorkflowStore(project).load()["checkpoints"]["outline"]["status"] == (
        "changes_requested"
    )


def test_unresolved_outline_conflict_requires_human_resolution(tmp_path: Path):
    project, _ = prepare_outline_project(tmp_path)
    plan = outline_plan()
    plan["conflicts"] = [
        {
            "conflict_id": "CONFLICT-001",
            "description": "模拟客户字数要求可能压缩准则特有条件。",
            "status": "unresolved",
        }
    ]
    proposal = tmp_path / "conflicted-outline.json"
    write_json(proposal, plan)
    build_formal_outline(project, proposal)

    with pytest.raises(HarnessError, match="OUTLINE_CONFLICTS_UNRESOLVED"):
        review_outline(project, "approved", reviewed_by="consultant")


def test_outline_detects_changed_requirement_inputs_and_derived_fields(tmp_path: Path):
    project, _ = prepare_outline_project(tmp_path)
    proposal = tmp_path / "outline.json"
    write_json(proposal, outline_plan())
    build_formal_outline(project, proposal)
    outline = read_json(project / "state/outline.json")
    ledger = read_jsonl(project / "state/disclosure_ledger.jsonl")

    outline["sections"][0]["requirement_ids"] = []
    ledger[0]["requirements"][0]["check_text"] = "Changed after outline generation"
    errors = validate_outline(outline, ledger)

    assert any("source_ledger_hash" in error for error in errors)
    assert any("requirement_ids: inconsistent" in error for error in errors)
