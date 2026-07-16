"""M5 standard adaptation tests mapped to FR-13 and AC-09."""

import zipfile
from pathlib import Path

import pytest
from m4_helpers import (
    build_anchor,
    build_and_approve_outline,
    complete_master,
    prepare_outline_project,
)
from report_harness.adaptation import (
    build_adaptation,
    finalize_adaptation,
    review_adaptation_item,
)
from report_harness.drafting import finalize_draft
from report_harness.errors import HarnessError
from report_harness.exporting import approve_export, export_project, validate_export_manifest
from report_harness.io import read_jsonl, read_yaml, write_json, write_yaml
from report_harness.project import validate_project
from report_harness.workflow import WorkflowStore

TARGET = "simulated-standard-a"


def _prepare_adaptation_project(tmp_path: Path, *, convert_gaps: bool = False) -> Path:
    project, _ = prepare_outline_project(tmp_path)
    build_and_approve_outline(project, tmp_path)
    build_anchor(project, tmp_path)
    config_path = project / "project.yaml"
    config = read_yaml(config_path)
    config["deliverables"]["adaptations"] = [TARGET]
    write_yaml(config_path, config)
    complete_master(project, tmp_path, convert_gaps=convert_gaps)
    finalize_draft(project, "master", reviewed_by="consultant")
    assert WorkflowStore(project).load()["workflow_state"] == "adapting_standard"
    return project


def _proposal(project: Path) -> dict:
    outline = read_jsonl(project / "state/disclosure_ledger.jsonl")
    items = []
    for row in outline:
        unified_id = row["unified_disclosure"]["unified_id"]
        for content in row["content"]:
            action = "keep"
            target_section_id = content["section_id"]
            adapted_text = None
            reason = "母版内容直接回应目标准则。"
            if unified_id == "SIM-UNI-EMISSIONS":
                action = "condense"
                adapted_text = "2025 年模拟排放数据为 12.5。"
                reason = "按目标准则压缩为核心量化披露。"
            elif unified_id == "SIM-UNI-GOVERNANCE":
                action = "omit"
                target_section_id = None
                reason = "该模拟内容仅对应另一套准则。"
            items.append(
                {
                    "adaptation_id": f"ADAPT-A-{content['content_id']}",
                    "source_content_id": content["content_id"],
                    "action": action,
                    "reason": reason,
                    "target_section_id": target_section_id,
                    "adapted_text": adapted_text,
                    "supplemental_evidence_ids": [],
                    "content_type": content["content_type"],
                    "review_status": "unreviewed",
                    "reviewed_by": None,
                    "human_notes": None,
                }
            )
    return {
        "schema_version": "1.0.0",
        "target_standard_id": TARGET,
        "items": items,
    }


def _build(project: Path, tmp_path: Path) -> dict:
    proposal_path = tmp_path / "adaptation-proposal.json"
    write_json(proposal_path, _proposal(project))
    return build_adaptation(project, proposal_path)


def _accept_all(project: Path) -> None:
    ledger = read_jsonl(project / "state/disclosure_ledger.jsonl")
    for item in [
        item
        for row in ledger
        for item in row.get("adaptations", [])
        if item["target_standard_id"] == TARGET
    ]:
        review_adaptation_item(
            project,
            TARGET,
            item["adaptation_id"],
            "accepted",
            reviewed_by="consultant",
            notes="顾问确认适配动作。",
        )


def test_adaptation_covers_master_once_and_exports_internal_diff(tmp_path: Path):
    project = _prepare_adaptation_project(tmp_path)

    result = _build(project, tmp_path)
    exported = export_project(project, mode="internal")

    assert result["items_total"] == 3
    assert result["review_counts"]["unreviewed"] == 3
    assert "outputs/internal/adapted_simulated-standard-a_internal.docx" in exported["files"]
    assert "outputs/internal/adaptation_diff_simulated-standard-a.xlsx" in exported["files"]
    with zipfile.ZipFile(
        project / "outputs/internal/adapted_simulated-standard-a_internal.docx"
    ) as package:
        document = package.read("word/document.xml").decode()
    assert "2025 年模拟排放数据为 12.5。" in document
    assert "模拟治理" not in document
    assert validate_export_manifest(project, "internal") == []
    assert validate_project(project) == []


def test_adaptation_cannot_silently_omit_a_target_requirement(tmp_path: Path):
    project = _prepare_adaptation_project(tmp_path)
    proposal = _proposal(project)
    scope = next(item for item in proposal["items"] if "SIM-UNI-SCOPE" in item["source_content_id"])
    scope["action"] = "omit"
    scope["target_section_id"] = None
    proposal_path = tmp_path / "invalid-adaptation.json"
    write_json(proposal_path, proposal)

    with pytest.raises(HarnessError, match="INVALID_ADAPTATION_PROPOSAL") as exc_info:
        build_adaptation(project, proposal_path)

    assert any("cannot be entirely omitted" in error for error in exc_info.value.details["errors"])


def test_adaptation_requires_item_review_before_finalization(tmp_path: Path):
    project = _prepare_adaptation_project(tmp_path)
    _build(project, tmp_path)

    with pytest.raises(HarnessError, match="ADAPTATION_REVIEW_INCOMPLETE"):
        finalize_adaptation(project, TARGET, reviewed_by="consultant")

    _accept_all(project)
    result = finalize_adaptation(project, TARGET, reviewed_by="consultant")

    assert result["workflow_state"] == "awaiting_export_confirmation"
    assert result["review_blockers"] == []


def test_each_configured_target_can_be_built_before_other_targets(tmp_path: Path):
    project = _prepare_adaptation_project(tmp_path)
    config_path = project / "project.yaml"
    config = read_yaml(config_path)
    config["deliverables"]["adaptations"].append("simulated-standard-b")
    write_yaml(config_path, config)

    result = _build(project, tmp_path)

    assert result["target_standard_id"] == TARGET
    assert result["valid"] is True
    _accept_all(project)
    finalized = finalize_adaptation(project, TARGET, reviewed_by="consultant")
    assert finalized["workflow_state"] == "adapting_standard"


def test_reviewed_adaptation_enters_clean_export_and_manifest(tmp_path: Path):
    project = _prepare_adaptation_project(tmp_path, convert_gaps=True)
    _build(project, tmp_path)
    _accept_all(project)
    finalize_adaptation(project, TARGET, reviewed_by="consultant")
    export_project(project, mode="internal")
    approve_export(project, reviewed_by="consultant")

    result = export_project(project, mode="clean")

    assert "outputs/clean/adapted_simulated-standard-a_clean.docx" in result["files"]
    with zipfile.ZipFile(
        project / "outputs/clean/adapted_simulated-standard-a_clean.docx"
    ) as package:
        names = package.namelist()
        document = package.read("word/document.xml").decode()
    assert "word/comments.xml" not in names
    assert "[建议文本]" not in document
    assert validate_export_manifest(project, "clean") == []


def test_clean_export_can_contain_only_configured_adaptation(tmp_path: Path):
    project = _prepare_adaptation_project(tmp_path, convert_gaps=True)
    _build(project, tmp_path)
    _accept_all(project)
    finalize_adaptation(project, TARGET, reviewed_by="consultant")
    config_path = project / "project.yaml"
    config = read_yaml(config_path)
    config["deliverables"]["master_report"] = False
    write_yaml(config_path, config)
    export_project(project, mode="internal")
    approve_export(project, reviewed_by="consultant")

    result = export_project(project, mode="clean")

    assert result["files"] == ["outputs/clean/adapted_simulated-standard-a_clean.docx"]
