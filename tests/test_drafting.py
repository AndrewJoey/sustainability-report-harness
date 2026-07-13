"""M4 Anchor/master drafting tests mapped to AC-05, AC-06, and AC-22 through AC-24."""

from pathlib import Path

import pytest
from m4_helpers import (
    accept_items,
    build_anchor,
    build_and_approve_outline,
    build_master,
    draft_proposal,
    prepare_outline_project,
)
from report_harness.drafting import (
    build_draft,
    finalize_draft,
    request_draft_changes,
    review_draft_item,
)
from report_harness.errors import HarnessError
from report_harness.io import read_jsonl, write_json
from report_harness.workflow import WorkflowStore


def test_anchor_only_generates_representative_section_and_blocks_master(tmp_path: Path):
    project, peer_evidence_id = prepare_outline_project(tmp_path, with_peer=True)
    build_and_approve_outline(project, tmp_path)
    build_anchor(project, tmp_path, peer_evidence_id=peer_evidence_id)
    ledger = read_jsonl(project / "state/disclosure_ledger.jsonl")

    assert WorkflowStore(project).load()["workflow_state"] == "awaiting_anchor_confirmation"
    assert {item["section_id"] for row in ledger for item in row["content"]} == {"SEC-ENV"}
    assert any(
        item["peer_position"] == "comparable"
        for row in ledger
        for item in row.get("peer_assessments", [])
    )
    with pytest.raises(HarnessError, match="DRAFT_REVIEW_INCOMPLETE"):
        finalize_draft(project, "anchor", reviewed_by="consultant")


def test_anchor_human_edit_survives_agent_rebuild(tmp_path: Path):
    project, _ = prepare_outline_project(tmp_path)
    build_and_approve_outline(project, tmp_path)
    build_anchor(project, tmp_path)
    content_id = next(
        item["content_id"]
        for row in read_jsonl(project / "state/disclosure_ledger.jsonl")
        for item in row["content"]
    )
    review_draft_item(
        project,
        "content",
        content_id,
        "edited",
        reviewed_by="consultant",
        changes={"text": "顾问人工修改后的模拟 Anchor 正文。"},
    )
    request_draft_changes(
        project,
        "anchor",
        reviewed_by="consultant",
        notes="重生成其他评价字段。",
    )
    proposal = draft_proposal(project, stage="anchor", section_ids={"SEC-ENV"})
    proposal_path = tmp_path / "replacement-anchor.json"
    write_json(proposal_path, proposal)

    build_draft(project, proposal_path, stage="anchor", replace=True)
    preserved = next(
        item
        for row in read_jsonl(project / "state/disclosure_ledger.jsonl")
        for item in row["content"]
        if item["content_id"] == content_id
    )

    assert preserved["text"] == "顾问人工修改后的模拟 Anchor 正文。"
    assert preserved["last_modified_by"] == "human"


def test_approved_anchor_unlocks_complete_master_generation(tmp_path: Path):
    project, _ = prepare_outline_project(tmp_path)
    build_and_approve_outline(project, tmp_path)
    build_anchor(project, tmp_path)
    accept_items(project, section_ids={"SEC-ENV"})
    finalize_draft(project, "anchor", reviewed_by="consultant")
    build_master(project, tmp_path)
    ledger = read_jsonl(project / "state/disclosure_ledger.jsonl")

    assert WorkflowStore(project).load()["workflow_state"] == "reviewing_master"
    assert {item["section_id"] for row in ledger for item in row["content"]} == {
        "SEC-SCOPE",
        "SEC-ENV",
        "SEC-GOV",
    }
    assert {item["content_type"] for row in ledger for item in row["content"]} == {
        "confirmed_fact",
        "information_gap",
    }
