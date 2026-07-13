"""Standard registry and version-lock tests mapped to FR-04 and AC-02."""

from copy import deepcopy
from pathlib import Path

import pytest
from report_harness.config import load_project_config
from report_harness.errors import HarnessError
from report_harness.io import read_json, write_json
from report_harness.project import default_project_config, scaffold_project, validate_project
from report_harness.standards import (
    calculate_standard_content_hash,
    load_standard_package,
    lock_standard_versions,
    recommend_standard_versions,
    validate_standard_package,
)
from report_harness.workflow import WorkflowStore

FIXTURE_DIR = Path("skills/sustainability-report-harness/standards/fixtures")
STANDARD_A = FIXTURE_DIR / "simulated-standard-a.json"
STANDARD_B = FIXTURE_DIR / "simulated-standard-b.json"


def create_standard_project(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    scaffold_project(
        project,
        default_project_config(
            "m3-demo",
            "M3 simulated demo",
            "Simulated client",
            "2025-01-01",
            "2025-12-31",
        ),
    )
    store = WorkflowStore(project)
    store.transition("awaiting_data_consent")
    store.set_checkpoint("data_consent", "approved", approved_by="reviewer")
    store.transition("awaiting_spec_confirmation")
    store.set_checkpoint("project_spec", "approved", approved_by="reviewer")
    store.transition("awaiting_standard_confirmation")
    return project


def test_simulated_packages_are_integrity_checked_and_clearly_marked():
    package_a = load_standard_package(STANDARD_A)
    package_b = load_standard_package(STANDARD_B)

    assert package_a["package_status"] == "simulated"
    assert package_b["package_status"] == "simulated"
    assert "NOT AN OFFICIAL STANDARD" in package_a["fixture_notice"]

    tampered = deepcopy(package_a)
    tampered["requirements"][0]["check_text"] = "tampered"
    assert any("content_hash" in error for error in validate_standard_package(tampered))

    omitted = deepcopy(package_a)
    omitted["clauses"].append({"clause_id": "SIM-A-UNMAPPED", "original_text": "模拟未拆解条款。"})
    omitted["standard_version"]["content_hash"] = calculate_standard_content_hash(
        omitted["clauses"], omitted["requirements"]
    )
    assert any(
        "has no decomposed requirement" in error for error in validate_standard_package(omitted)
    )


def test_reviewed_package_requires_rule_review_governance():
    package = deepcopy(load_standard_package(STANDARD_A))
    package["package_status"] = "reviewed"
    package["standard_version"]["review_status"] = "reviewed"
    package["standard_version"]["source_uri"] = "https://example.invalid/official-source"
    for requirement in package["requirements"]:
        requirement["review_status"] = "reviewed"
    package["standard_version"]["content_hash"] = calculate_standard_content_hash(
        package["clauses"], package["requirements"]
    )

    errors = validate_standard_package(package)

    assert "reviewed_by: reviewed packages require a named reviewer" in errors
    assert "reviewed_at: reviewed packages require a review timestamp" in errors


def test_recommendation_uses_reporting_period_and_reports_missing_standard():
    result = recommend_standard_versions(
        "2025-12-31",
        ["simulated-standard-a", "missing-standard"],
        [STANDARD_A, STANDARD_B],
    )

    assert result["recommendations"][0]["standard_version"]["version_id"] == "fixture-1"
    assert result["missing_standard_ids"] == ["missing-standard"]


def test_standard_lock_requires_explicit_simulated_fixture_confirmation(tmp_path: Path):
    project = create_standard_project(tmp_path)

    with pytest.raises(HarnessError, match="SIMULATED_STANDARD_REQUIRES_CONFIRMATION"):
        lock_standard_versions(project, [STANDARD_A], confirmed_by="reviewer")

    result = lock_standard_versions(
        project,
        [STANDARD_A, STANDARD_B],
        confirmed_by="reviewer",
        allow_simulated=True,
    )

    assert result["workflow_state"] == "ingesting_sources"
    assert len(load_project_config(project)["selected_standards"]) == 2
    assert validate_project(project) == []
    with pytest.raises(HarnessError, match="STANDARD_LOCK_NOT_ALLOWED"):
        lock_standard_versions(
            project,
            [STANDARD_A],
            confirmed_by="reviewer",
            allow_simulated=True,
        )


def test_fixture_hash_helper_matches_locked_payload():
    package = load_standard_package(STANDARD_A)
    assert package["standard_version"]["content_hash"] == calculate_standard_content_hash(
        package["clauses"], package["requirements"]
    )
    split_clause = [item for item in package["requirements"] if item["clause_id"] == "SIM-A-2"]
    assert len(split_clause) == 2


def test_project_validation_detects_locked_metadata_changes(tmp_path: Path):
    project = create_standard_project(tmp_path)
    lock_standard_versions(
        project,
        [STANDARD_A],
        confirmed_by="reviewer",
        allow_simulated=True,
    )
    path = project / "state/standards.lock.json"
    lock = read_json(path)
    lock["standards"][0]["standard_version"]["effective_from"] = "2024-01-01"
    write_json(path, lock)

    errors = validate_project(project)

    assert any("lock_hash: locked payload has changed" in error for error in errors)
