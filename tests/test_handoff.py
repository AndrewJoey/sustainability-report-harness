"""Framework-neutral continuity tests mapped to FR-15, AC-11, and AC-13."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fixture_builders import write_docx
from report_harness.errors import HarnessError
from report_harness.handoff import create_handoff, handoff_status
from report_harness.project import default_project_config, scaffold_project, validate_project
from report_harness.workflow import WorkflowStore

SCRIPTS = Path(__file__).parents[1] / "skills/sustainability-report-harness/scripts"


def _project_at_ingestion(tmp_path: Path) -> Path:
    project = tmp_path / "continuity-demo"
    scaffold_project(
        project,
        default_project_config(
            "continuity-demo",
            "Continuity demo",
            "Synthetic client",
            "2025-01-01",
            "2025-12-31",
        ),
    )
    store = WorkflowStore(project)
    store.transition("awaiting_data_consent")
    store.set_checkpoint("data_consent", "approved", approved_by="consultant")
    store.transition("awaiting_spec_confirmation")
    store.set_checkpoint("project_spec", "approved", approved_by="consultant")
    store.transition("awaiting_standard_confirmation")
    store.set_checkpoint("standards", "approved", approved_by="consultant")
    store.transition("ingesting_sources")
    return project


def _run(script: str, *args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *(str(arg) for arg in args)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_second_process_verifies_same_state_and_preserves_human_edit(tmp_path: Path):
    project = _project_at_ingestion(tmp_path)
    human_brief = "# 项目规格\n\n顾问人工确认：保留现有目录与措辞。\n"
    (project / "brief.md").write_text(human_brief, encoding="utf-8")

    created = create_handoff(project, produced_by="codex")
    verified = _run("handoff_project.py", "verify", project)

    assert created["valid"] is True
    assert verified.returncode == 0
    assert json.loads(verified.stdout)["next_action"] == "ingest or resolve blocked sources"
    assert (project / "brief.md").read_text(encoding="utf-8") == human_brief
    assert validate_project(project) == []


def test_handoff_detects_contract_changes_until_refreshed(tmp_path: Path):
    project = _project_at_ingestion(tmp_path)
    create_handoff(project, produced_by="codex")
    (project / "brief.md").write_text("# 顾问修改后的规格\n", encoding="utf-8")

    stale = handoff_status(project)
    verified = _run("handoff_project.py", "verify", project)

    assert stale["valid"] is False
    assert any("brief.md" in error for error in stale["errors"])
    assert verified.returncode == 2
    refreshed = create_handoff(project, produced_by="codex")
    assert refreshed["valid"] is True


def test_handoff_tracks_customer_requirement_templates(tmp_path: Path):
    project = _project_at_ingestion(tmp_path)
    template = project / "sources/requirements/client-template.docx"
    write_docx(template, body_text="Use this synthetic customer structure.")
    create_handoff(project, produced_by="codex")

    write_docx(template, body_text="Synthetic customer structure changed.")
    stale = handoff_status(project)

    assert stale["valid"] is False
    assert any("sources/requirements/client-template.docx" in error for error in stale["errors"])


def test_second_process_reuses_unchanged_source_without_reparse(tmp_path: Path):
    project = _project_at_ingestion(tmp_path)
    write_docx(project / "sources/client/policy.docx")

    first = _run("ingest_sources.py", project)
    second = _run("ingest_sources.py", project)

    assert first.returncode == 0
    assert json.loads(first.stdout)["parsed"] == 1
    assert second.returncode == 0
    second_result = json.loads(second.stdout)
    assert second_result["parsed"] == 0
    assert second_result["reused"] == 1


def test_changed_source_invalidates_handoff_until_reingested(tmp_path: Path):
    project = _project_at_ingestion(tmp_path)
    source = project / "sources/client/policy.docx"
    write_docx(source)
    assert _run("ingest_sources.py", project).returncode == 0
    create_handoff(project, produced_by="codex")

    write_docx(source, body_text="2025 energy use was 55 MWh")

    stale = handoff_status(project)
    assert stale["valid"] is False
    assert any("source reuse fingerprints are stale" in error for error in stale["errors"])
    with pytest.raises(HarnessError, match="STALE_SOURCE_MANIFEST"):
        create_handoff(project, produced_by="codex")

    assert _run("ingest_sources.py", project).returncode == 0
    assert create_handoff(project, produced_by="codex")["valid"] is True
