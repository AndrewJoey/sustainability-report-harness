"""Markdown-first master and per-framework delivery tests mapped to AC-28--AC-30."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from report_harness.adaptation import build_adaptation
from report_harness.errors import HarnessError
from report_harness.io import read_jsonl, read_yaml, write_json, write_yaml
from report_harness.markdown_export import (
    export_markdown_reports,
    validate_markdown_manifest,
)
from report_harness.project import validate_project
from test_adaptation import TARGET, _prepare_adaptation_project, _proposal

SECOND_TARGET = "simulated-standard-b"


def _add_confirmed_intake(project: Path) -> None:
    write_json(
        project / "state/intake.json",
        {
            "schema_version": "1.0.0",
            "confirmed_at": "2026-07-17T10:00:00+08:00",
            "confirmed_by": "consultant",
            "client_materials": {"files": ["sources/client/metrics.xlsx"]},
            "existing_report_or_template": {"status": "none", "files": []},
            "reference_cases": {"status": "none", "usage": "none", "files": []},
            "requested_standard_ids": [TARGET, SECOND_TARGET],
            "reporting_preferences": {
                "purpose": "生成报告初版",
                "audience": "管理层与顾问",
                "tone": "专业、克制",
                "required_topics": ["范围", "排放", "治理"],
            },
        },
    )


def _prepare_markdown_project(tmp_path: Path, *, complete_second: bool = True) -> Path:
    project = _prepare_adaptation_project(tmp_path)
    config_path = project / "project.yaml"
    config = read_yaml(config_path)
    config["deliverables"]["adaptations"] = [TARGET, SECOND_TARGET]
    write_yaml(config_path, config)
    first_path = tmp_path / "adaptation-a.json"
    write_json(first_path, _proposal(project))
    build_adaptation(project, first_path)
    if complete_second:
        ledger = read_jsonl(project / "state/disclosure_ledger.jsonl")
        items = []
        for row in ledger:
            for content in row["content"]:
                items.append(
                    {
                        "adaptation_id": f"ADAPT-B-{content['content_id']}",
                        "source_content_id": content["content_id"],
                        "action": "keep",
                        "reason": "保留母版内容以回应模拟准则 B。",
                        "target_section_id": content["section_id"],
                        "adapted_text": None,
                        "supplemental_evidence_ids": [],
                        "content_type": content["content_type"],
                        "review_status": "unreviewed",
                        "reviewed_by": None,
                        "human_notes": None,
                    }
                )
        second_path = tmp_path / "adaptation-b.json"
        write_json(
            second_path,
            {
                "schema_version": "1.0.0",
                "target_standard_id": SECOND_TARGET,
                "items": items,
            },
        )
        build_adaptation(project, second_path)
    _add_confirmed_intake(project)
    return project


def test_exports_union_master_and_one_markdown_per_framework(tmp_path: Path):
    project = _prepare_markdown_project(tmp_path)

    result = export_markdown_reports(project)

    assert result["files"] == [
        "outputs/markdown/master_report.md",
        "outputs/markdown/adapted_simulated-standard-a.md",
        "outputs/markdown/adapted_simulated-standard-b.md",
    ]
    master = (project / result["files"][0]).read_text(encoding="utf-8")
    adapted = (project / result["files"][1]).read_text(encoding="utf-8")
    assert "[信息缺口]" in master
    assert "<!-- content_id:" in master
    assert "evidence_ids: EVD-" in master
    assert "target_standard_id: simulated-standard-a" in adapted
    assert "source_content_id:" in adapted
    assert validate_markdown_manifest(project) == []
    assert validate_project(project) == []


def test_export_blocks_before_every_framework_adaptation_exists(tmp_path: Path):
    project = _prepare_markdown_project(tmp_path, complete_second=False)

    with pytest.raises(HarnessError, match="INVALID_ADAPTATION"):
        export_markdown_reports(project)

    assert not (project / "outputs/markdown/master_report.md").exists()


def test_manifest_detects_manual_markdown_changes(tmp_path: Path):
    project = _prepare_markdown_project(tmp_path)
    export_markdown_reports(project)
    path = project / "outputs/markdown/master_report.md"
    path.write_text(path.read_text(encoding="utf-8") + "manual edit\n", encoding="utf-8")

    errors = validate_markdown_manifest(project)

    assert any("output hash is stale" in error for error in errors)


def test_manifest_detects_changed_client_source(tmp_path: Path):
    project = _prepare_markdown_project(tmp_path)
    export_markdown_reports(project)
    source = project / "sources/client/metrics.xlsx"
    source.write_bytes(source.read_bytes() + b"changed-after-export")

    errors = validate_markdown_manifest(project)

    assert any("source contracts have changed" in error for error in errors)


def test_project_rejects_unmanifested_markdown_output(tmp_path: Path):
    project = _prepare_markdown_project(tmp_path)
    path = project / "outputs/markdown/manual.md"
    path.write_text("# untracked\n", encoding="utf-8")

    errors = validate_project(project)

    assert any("manifest is required" in error for error in errors)


def test_markdown_cli_matches_beginner_guide(tmp_path: Path):
    project = _prepare_markdown_project(tmp_path)
    script = Path("skills/sustainability-report-harness/scripts/export_markdown.py")

    generated = subprocess.run(
        [sys.executable, str(script), "generate", str(project)],
        capture_output=True,
        check=False,
        text=True,
    )
    validated = subprocess.run(
        [sys.executable, str(script), "validate", str(project)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert generated.returncode == 0
    assert len(json.loads(generated.stdout)["files"]) == 3
    assert validated.returncode == 0
    assert json.loads(validated.stdout) == {"valid": True, "errors": []}
