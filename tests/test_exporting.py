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
from report_harness.exporting import approve_export, export_project, validate_export_manifest
from report_harness.io import read_json, read_yaml, write_json, write_yaml


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
    export_project(project, mode="internal")

    with pytest.raises(HarnessError, match="EXPORT_REVIEW_BLOCKED"):
        approve_export(project, reviewed_by="consultant")


def test_clean_export_after_human_resolution_has_no_internal_markers(tmp_path: Path):
    project, _ = prepare_outline_project(tmp_path)
    build_and_approve_outline(project, tmp_path)
    build_anchor(project, tmp_path)
    complete_master(project, tmp_path, convert_gaps=True)
    finalize_draft(project, "master", reviewed_by="consultant")
    export_project(project, mode="internal")
    approve_export(project, reviewed_by="consultant")

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


def test_export_rejects_an_outline_with_tampered_derived_coverage(tmp_path: Path):
    project, _ = prepare_outline_project(tmp_path)
    build_and_approve_outline(project, tmp_path)
    build_anchor(project, tmp_path)
    complete_master(project, tmp_path)
    outline_path = project / "state/outline.json"
    outline = read_json(outline_path)
    outline["sections"][0]["evidence_coverage"]["total_requirements"] = 999
    write_json(outline_path, outline)

    with pytest.raises(HarnessError, match="INVALID_OUTLINE"):
        export_project(project, mode="internal")


def test_export_manifest_binds_all_inputs_and_required_files(tmp_path: Path):
    project, _ = prepare_outline_project(tmp_path)
    build_and_approve_outline(project, tmp_path)
    build_anchor(project, tmp_path)
    complete_master(project, tmp_path)
    export_project(project, mode="internal")
    manifest_path = project / "outputs/internal/export_manifest.json"
    manifest = read_json(manifest_path)
    manifest["files"] = []
    write_json(manifest_path, manifest)

    errors = validate_export_manifest(project, "internal")

    assert any("file list does not match" in error for error in errors)

    export_project(project, mode="internal")
    outline_path = project / "state/outline.json"
    outline = read_json(outline_path)
    outline["sections"][0]["title"] = "Changed after export"
    write_json(outline_path, outline)

    errors = validate_export_manifest(project, "internal")

    assert any("outline/config/standards inputs" in error for error in errors)


def test_internal_export_respects_disabled_deliverables(tmp_path: Path):
    project, _ = prepare_outline_project(tmp_path)
    build_and_approve_outline(project, tmp_path)
    build_anchor(project, tmp_path)
    complete_master(project, tmp_path)
    config_path = project / "project.yaml"
    config = read_yaml(config_path)
    config["deliverables"]["gap_list"] = False
    config["deliverables"]["evidence_list"] = False
    write_yaml(config_path, config)

    result = export_project(project, mode="internal")

    assert len(result["files"]) == 3
    assert "outputs/internal/gap_list.xlsx" not in result["files"]
    assert "outputs/internal/evidence_list.xlsx" not in result["files"]
    assert not (project / "outputs/internal/gap_list.xlsx").exists()
    assert not (project / "outputs/internal/evidence_list.xlsx").exists()
    assert validate_export_manifest(project, "internal") == []
