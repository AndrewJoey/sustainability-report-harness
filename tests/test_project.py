"""Project scaffold and configuration tests mapped to FR-01, FR-02, and AC-01."""

from pathlib import Path

import pytest
from report_harness.config import load_project_config, validate_project_config
from report_harness.errors import HarnessError
from report_harness.project import (
    PROJECT_DIRECTORIES,
    PROJECT_FILES,
    default_project_config,
    scaffold_project,
    validate_project,
)


def config():
    return default_project_config(
        "demo-project",
        "模拟报告项目",
        "模拟客户",
        "2025-01-01",
        "2025-12-31",
    )


def test_scaffold_creates_public_contract(tmp_path: Path):
    project = tmp_path / "demo"
    scaffold_project(project, config())

    for relative in PROJECT_DIRECTORIES:
        assert (project / relative).is_dir()
    for relative in PROJECT_FILES:
        assert (project / relative).is_file()
    assert load_project_config(project)["data_policy"]["cloud_processing_allowed"] is False
    assert validate_project(project) == []


def test_scaffold_refuses_to_overwrite(tmp_path: Path):
    project = tmp_path / "demo"
    project.mkdir()
    (project / "human.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(HarnessError, match="PROJECT_NOT_EMPTY"):
        scaffold_project(project, config())
    assert (project / "human.txt").read_text(encoding="utf-8") == "keep"


def test_invalid_config_reports_all_actionable_paths():
    invalid = config()
    invalid["reporting_period_end"] = "not-a-date"
    invalid["data_policy"]["cloud_processing_allowed"] = "yes"
    invalid["granularity"] = "verbose"

    errors = validate_project_config(invalid)
    assert any(item.startswith("reporting_period_end:") for item in errors)
    assert any(item.startswith("data_policy.cloud_processing_allowed:") for item in errors)
    assert any(item.startswith("granularity:") for item in errors)
