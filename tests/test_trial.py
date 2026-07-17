"""MVP trial metric tests mapped to AC-12."""

from pathlib import Path

import pytest
from report_harness.errors import HarnessError
from report_harness.io import read_json, read_jsonl, write_json, write_jsonl
from report_harness.project import default_project_config, scaffold_project, validate_project
from report_harness.trial import record_trial, validate_trial_metrics


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "trial-demo"
    scaffold_project(
        project,
        default_project_config(
            "trial-demo",
            "Trial demo",
            "Synthetic client",
            "2025-01-01",
            "2025-12-31",
        ),
    )
    return project


def _record() -> dict:
    return {
        "trial_id": "TRIAL-001",
        "scope": "端到端模拟项目",
        "baseline_minutes": 300,
        "agent_runtime_minutes": 40,
        "human_review_minutes": 120,
        "repeat_parse_count": 0,
        "repeat_write_count": 1,
        "mapping_correction_count": 2,
        "evidence_location_error_count": 1,
        "content_total": 10,
        "content_kept": 6,
        "content_modified": 3,
        "content_rewritten": 1,
        "selected_requirements_total": 20,
        "selected_requirements_covered": 18,
        "cross_agent_reprocessed_files": 0,
        "notes": "模拟记录，不含客户文本。",
    }


def test_trial_record_is_append_only_and_reports_speed_and_corrections(tmp_path: Path):
    project = _project(tmp_path)

    result = record_trial(project, _record(), recorded_by="consultant")
    summary = read_json(project / "logs/trial_summary.json")

    assert result["summary"]["derived"]["net_minutes_saved"] == 140
    assert summary["totals"]["mapping_correction_count"] == 2
    assert summary["totals"]["evidence_location_error_count"] == 1
    assert summary["derived"]["content_keep_ratio"] == 0.6
    assert summary["derived"]["requirement_coverage_ratio"] == 0.9
    assert len(read_jsonl(project / "logs/trial_metrics.jsonl")) == 1
    assert validate_project(project) == []


def test_trial_metrics_reject_duplicate_id_and_inconsistent_content_counts(tmp_path: Path):
    project = _project(tmp_path)
    record_trial(project, _record(), recorded_by="consultant")

    with pytest.raises(HarnessError, match="DUPLICATE_TRIAL_ID"):
        record_trial(project, _record(), recorded_by="consultant")

    invalid = _record()
    invalid["trial_id"] = "TRIAL-002"
    invalid["content_rewritten"] = 2
    with pytest.raises(HarnessError, match="INVALID_TRIAL_METRICS"):
        record_trial(project, invalid, recorded_by="consultant")


def test_project_validation_detects_stale_trial_summary(tmp_path: Path):
    project = _project(tmp_path)
    record_trial(project, _record(), recorded_by="consultant")
    metrics_path = project / "logs/trial_metrics.jsonl"
    metrics_path.write_text(metrics_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    records = read_jsonl(metrics_path)
    records[0]["mapping_correction_count"] = 3
    write_jsonl(metrics_path, records)

    errors = validate_trial_metrics(project)

    assert any("summary is stale" in error for error in errors)


def test_project_validation_detects_tampered_summary_values(tmp_path: Path):
    project = _project(tmp_path)
    record_trial(project, _record(), recorded_by="consultant")
    summary_path = project / "logs/trial_summary.json"
    summary = read_json(summary_path)
    summary["derived"]["net_minutes_saved"] = 999
    write_json(summary_path, summary)

    errors = validate_trial_metrics(project)

    assert any("summary values are invalid" in error for error in errors)


def test_pre_m5_project_without_trial_log_remains_valid(tmp_path: Path):
    project = _project(tmp_path)
    (project / "logs/trial_metrics.jsonl").unlink()

    assert validate_project(project) == []
