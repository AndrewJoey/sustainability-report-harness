"""MVP conversational intake tests mapped to AC-27."""

import json
import subprocess
import sys
from pathlib import Path

from fixture_builders import write_docx, write_xlsx
from report_harness.config import load_project_config
from report_harness.intake import confirm_project_intake, intake_status
from report_harness.io import write_json
from report_harness.project import default_project_config, scaffold_project
from report_harness.standards import lock_standard_versions
from report_harness.workflow import WorkflowStore
from test_standards import STANDARD_A


def _proposal(*, reference: bool = False) -> dict:
    return {
        "client_materials": {"files": ["sources/client/metrics.xlsx"]},
        "existing_report_or_template": {"status": "none", "files": []},
        "reference_cases": {
            "status": "provided" if reference else "none",
            "usage": "quality_benchmark" if reference else "none",
            "files": ["sources/peer/example.docx"] if reference else [],
        },
        "requested_standard_ids": ["simulated-standard-a"],
        "reporting_preferences": {
            "purpose": "生成内部评审用可持续发展报告初版",
            "audience": "管理层与项目顾问",
            "tone": "专业、克制、可核验",
            "required_topics": ["排放数据"],
        },
    }


def _create_intake_project(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    scaffold_project(
        project,
        default_project_config(
            "intake-demo",
            "Intake demo",
            "Simulated client",
            "2025-01-01",
            "2025-12-31",
        ),
    )
    store = WorkflowStore(project)
    store.transition("awaiting_data_consent")
    store.set_checkpoint("data_consent", "approved", approved_by="consultant")
    store.transition("awaiting_spec_confirmation")
    return project


def test_intake_persists_answers_and_drives_framework_delivery(tmp_path: Path):
    project = _create_intake_project(tmp_path)
    write_xlsx(project / "sources/client/metrics.xlsx")
    proposal = tmp_path / "intake.json"
    write_json(proposal, _proposal())

    result = confirm_project_intake(project, proposal, confirmed_by="consultant")
    locked = lock_standard_versions(
        project,
        [STANDARD_A],
        confirmed_by="consultant",
        allow_simulated=True,
    )

    assert result["valid"] is True
    assert result["reference_status"] == "none"
    assert locked["workflow_state"] == "ingesting_sources"
    assert load_project_config(project)["deliverables"]["adaptations"] == ["simulated-standard-a"]
    assert intake_status(project)["confirmed_by"] == "consultant"
    assert "状态：已由 consultant" in (project / "brief.md").read_text(encoding="utf-8")


def test_reference_case_updates_confirmed_usage(tmp_path: Path):
    project = _create_intake_project(tmp_path)
    workflow = WorkflowStore(project).load()
    write_xlsx(project / "sources/client/metrics.xlsx")
    write_docx(project / "sources/peer/example.docx")
    proposal = tmp_path / "intake.json"
    write_json(proposal, _proposal(reference=True))

    result = confirm_project_intake(project, proposal, confirmed_by="consultant")

    assert workflow["workflow_state"] == "awaiting_spec_confirmation"
    assert result["valid"] is True
    assert load_project_config(project)["peer_reference_mode"] == "quality_benchmark"


def test_generic_workflow_command_cannot_approve_project_spec(tmp_path: Path):
    project = _create_intake_project(tmp_path)
    script = Path("skills/sustainability-report-harness/scripts/workflow.py")
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            str(project),
            "checkpoint",
            "project_spec",
            "approved",
            "--approved-by",
            "consultant",
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    assert json.loads(result.stderr)["error"]["code"] == "DOMAIN_REVIEW_REQUIRED"


def test_confirm_intake_cli_matches_beginner_guide(tmp_path: Path):
    project = _create_intake_project(tmp_path)
    write_xlsx(project / "sources/client/metrics.xlsx")
    proposal = tmp_path / "intake.json"
    write_json(proposal, _proposal())
    script = Path("skills/sustainability-report-harness/scripts/confirm_intake.py")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "confirm",
            str(project),
            str(proposal),
            "--confirmed-by",
            "consultant",
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["valid"] is True
    assert WorkflowStore(project).load()["workflow_state"] == "awaiting_standard_confirmation"
