"""Persistent gate tests mapped to AC-20 through AC-25."""

from pathlib import Path

import pytest
from report_harness.errors import HarnessError
from report_harness.project import default_project_config, scaffold_project
from report_harness.workflow import WorkflowStore


def create_project(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    scaffold_project(
        project,
        default_project_config(
            "demo-project",
            "模拟报告项目",
            "模拟客户",
            "2025-01-01",
            "2025-12-31",
        ),
    )
    return project


def approve(store: WorkflowStore, name: str) -> None:
    store.set_checkpoint(name, "approved", approved_by="test-reviewer")


def test_checkpoint_cannot_be_bypassed_and_state_recovers(tmp_path: Path):
    store = WorkflowStore(create_project(tmp_path))
    store.transition("awaiting_data_consent")
    approve(store, "data_consent")
    store.transition("awaiting_spec_confirmation")
    approve(store, "project_spec")
    store.transition("awaiting_standard_confirmation")
    approve(store, "standards")
    store.transition("ingesting_sources")
    store.transition("building_requirement_union")
    store.transition("awaiting_evidence_confirmation")

    with pytest.raises(HarnessError, match="CHECKPOINT_REQUIRED"):
        store.transition("generating_outline")
    approve(store, "evidence")
    store.transition("generating_outline")
    store.transition("awaiting_outline_confirmation")
    approve(store, "outline")
    store.transition("generating_anchor")
    store.transition("awaiting_anchor_confirmation")

    with pytest.raises(HarnessError, match="CHECKPOINT_REQUIRED"):
        store.transition("generating_master")
    approve(store, "anchor")
    store.transition("generating_master")
    assert WorkflowStore(store.path.parents[1]).load()["workflow_state"] == "generating_master"


def test_block_and_resume_preserves_previous_state(tmp_path: Path):
    store = WorkflowStore(create_project(tmp_path))
    store.transition("awaiting_data_consent")
    store.transition("blocked")
    assert store.load()["previous_state"] == "awaiting_data_consent"
    assert store.resume()["workflow_state"] == "awaiting_data_consent"


def test_approval_requires_reviewer(tmp_path: Path):
    store = WorkflowStore(create_project(tmp_path))
    with pytest.raises(HarnessError, match="APPROVER_REQUIRED"):
        store.set_checkpoint("data_consent", "approved")
