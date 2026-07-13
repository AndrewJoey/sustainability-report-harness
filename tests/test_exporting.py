"""M4 business-export tests mapped to AC-07, AC-08, AC-10, and AC-26."""

import zipfile
from pathlib import Path

import pytest
from m4_helpers import (
    build_anchor,
    build_and_approve_outline,
    complete_master,
    prepare_outline_project,
)
from report_harness.drafting import finalize_draft
from report_harness.errors import HarnessError
from report_harness.exporting import export_project, validate_export_manifest
from report_harness.workflow import WorkflowStore


def test_internal_export_contains_markers_comments_and_fixed_workbooks(tmp_path: Path):
    project, _ = prepare_outline_project(tmp_path)
    build_and_approve_outline(project, tmp_path)
    build_anchor(project, tmp_path)
    complete_master(project, tmp_path)

    result = export_project(project, mode="internal")
    report = project / "outputs/internal/master_report_internal.docx"
    with zipfile.ZipFile(report) as package:
        document = package.read("word/document.xml").decode()
        comments = package.read("word/comments.xml").decode()
    with zipfile.ZipFile(project / "outputs/internal/response_matrix.xlsx") as package:
        response_sheet = package.read("xl/worksheets/sheet1.xml").decode()

    assert len(result["files"]) == 5
    assert "[信息缺口]" in document
    assert "内容编号" in comments
    assert "准则名称" in response_sheet
    assert "人工备注" in response_sheet
    assert validate_export_manifest(project, "internal") == []


def test_clean_export_remains_blocked_by_information_gaps(tmp_path: Path):
    project, _ = prepare_outline_project(tmp_path)
    build_and_approve_outline(project, tmp_path)
    build_anchor(project, tmp_path)
    complete_master(project, tmp_path)
    finalize_draft(project, "master", reviewed_by="consultant")
    store = WorkflowStore(project)
    store.set_checkpoint("export", "approved", approved_by="consultant")
    store.transition("ready_for_export")

    with pytest.raises(HarnessError, match="CLEAN_EXPORT_BLOCKED"):
        export_project(project, mode="clean")


def test_clean_export_after_human_resolution_has_no_internal_markers(tmp_path: Path):
    project, _ = prepare_outline_project(tmp_path)
    build_and_approve_outline(project, tmp_path)
    build_anchor(project, tmp_path)
    complete_master(project, tmp_path, convert_gaps=True)
    finalize_draft(project, "master", reviewed_by="consultant")
    store = WorkflowStore(project)
    store.set_checkpoint("export", "approved", approved_by="consultant")
    store.transition("ready_for_export")

    export_project(project, mode="clean")
    report = project / "outputs/clean/master_report_clean.docx"
    with zipfile.ZipFile(report) as package:
        document = package.read("word/document.xml").decode()
        names = package.namelist()

    assert "[待确认-推断]" not in document
    assert "[建议文本]" not in document
    assert "[信息缺口]" not in document
    assert "word/comments.xml" not in names
    assert validate_export_manifest(project, "clean") == []
