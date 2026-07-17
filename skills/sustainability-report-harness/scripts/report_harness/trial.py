"""Append-only MVP trial metrics and deterministic summary generation."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .audit import append_event
from .config import load_project_config
from .errors import HarnessError
from .io import atomic_write_text, read_json, read_jsonl, write_json, write_jsonl
from .workflow import utc_now

TRIAL_METRICS_PATH = Path("logs/trial_metrics.jsonl")
TRIAL_SUMMARY_JSON = Path("logs/trial_summary.json")
TRIAL_SUMMARY_MD = Path("logs/trial_summary.md")
TRIAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
NUMBER_FIELDS = (
    "baseline_minutes",
    "agent_runtime_minutes",
    "human_review_minutes",
)
COUNT_FIELDS = (
    "repeat_parse_count",
    "repeat_write_count",
    "mapping_correction_count",
    "evidence_location_error_count",
    "content_total",
    "content_kept",
    "content_modified",
    "content_rewritten",
    "selected_requirements_total",
    "selected_requirements_covered",
    "cross_agent_reprocessed_files",
)
INPUT_FIELDS = {
    "trial_id",
    "scope",
    *NUMBER_FIELDS,
    *COUNT_FIELDS,
    "notes",
}
RECORD_FIELDS = INPUT_FIELDS | {"schema_version", "recorded_at", "recorded_by"}


def record_trial(
    project_dir: Path,
    input_record: dict[str, Any],
    *,
    recorded_by: str,
) -> dict[str, Any]:
    """Validate and append one user-supplied trial observation."""

    project_dir = project_dir.resolve()
    if not recorded_by.strip():
        raise HarnessError("RECORDER_REQUIRED", "recorded_by is required")
    record = {
        **input_record,
        "schema_version": "1.0.0",
        "recorded_at": utc_now(),
        "recorded_by": recorded_by.strip(),
    }
    errors = validate_trial_record(record)
    if errors:
        raise HarnessError(
            "INVALID_TRIAL_METRICS",
            "Trial metrics failed validation",
            details={"errors": errors},
        )
    path = project_dir / TRIAL_METRICS_PATH
    existing = read_jsonl(path) if path.is_file() else []
    if any(item.get("trial_id") == record["trial_id"] for item in existing):
        raise HarnessError("DUPLICATE_TRIAL_ID", f"Trial ID already exists: {record['trial_id']}")
    records = [*existing, record]
    write_jsonl(path, records)
    summary = write_trial_summary(project_dir, records=records)
    append_event(
        project_dir,
        project_id=str(load_project_config(project_dir)["project_id"]),
        event="trial.recorded",
        message="MVP trial metrics recorded and summary refreshed",
        details={"trial_id": record["trial_id"], "recorded_by": recorded_by.strip()},
    )
    return {"record": record, "summary": summary}


def validate_trial_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(RECORD_FIELDS - set(record))
    if missing:
        errors.append(f"missing fields: {missing}")
    unknown = sorted(set(record) - RECORD_FIELDS)
    if unknown:
        errors.append(f"unknown fields: {unknown}")
    if record.get("schema_version") != "1.0.0":
        errors.append("schema_version: must be 1.0.0")
    trial_id = record.get("trial_id")
    if not isinstance(trial_id, str) or not TRIAL_ID_PATTERN.fullmatch(trial_id):
        errors.append("trial_id: must be a safe stable ID")
    scope = record.get("scope")
    if not isinstance(scope, str) or not scope.strip():
        errors.append("scope: must be a non-empty string")
    for field in ("recorded_at", "recorded_by"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            errors.append(f"{field}: must be a non-empty string")
    for field in NUMBER_FIELDS:
        value = record.get(field)
        if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
            errors.append(f"{field}: must be a non-negative number")
    for field in COUNT_FIELDS:
        value = record.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(f"{field}: must be a non-negative integer")
    content_values = [
        record.get(field) for field in ("content_kept", "content_modified", "content_rewritten")
    ]
    if all(isinstance(value, int) and not isinstance(value, bool) for value in content_values):
        if sum(content_values) != record.get("content_total"):
            errors.append("content_total: must equal kept + modified + rewritten")
    total = record.get("selected_requirements_total")
    covered = record.get("selected_requirements_covered")
    if isinstance(total, int) and isinstance(covered, int) and covered > total:
        errors.append("selected_requirements_covered: cannot exceed total")
    notes = record.get("notes")
    if notes is not None and not isinstance(notes, str):
        errors.append("notes: must be a string or null")
    return errors


def validate_trial_metrics(project_dir: Path) -> list[str]:
    project_dir = project_dir.resolve()
    path = project_dir / TRIAL_METRICS_PATH
    if not path.is_file():
        summaries = [project_dir / TRIAL_SUMMARY_JSON, project_dir / TRIAL_SUMMARY_MD]
        return (
            ["logs/trial_metrics.jsonl: source records are missing for the trial summary"]
            if any(summary.is_file() for summary in summaries)
            else []
        )
    try:
        records = read_jsonl(path)
    except HarnessError as exc:
        return [str(exc)]
    errors: list[str] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        errors.extend(
            f"logs/trial_metrics.jsonl[{index}].{error}" for error in validate_trial_record(record)
        )
        trial_id = str(record.get("trial_id"))
        if trial_id in seen:
            errors.append(f"logs/trial_metrics.jsonl[{index}].trial_id: duplicate ID")
        seen.add(trial_id)
    summary_path = project_dir / TRIAL_SUMMARY_JSON
    if summary_path.is_file():
        try:
            summary = read_json(summary_path)
            if not isinstance(summary, dict):
                errors.append("logs/trial_summary.json: root must be an object")
                return errors
            if summary.get("source_records_hash") != _records_hash(records):
                errors.append("logs/trial_summary.json.source_records_hash: summary is stale")
            generated_at = summary.get("generated_at")
            if not isinstance(generated_at, str) or not generated_at.strip():
                errors.append("logs/trial_summary.json.generated_at: must be a non-empty string")
            expected = _build_summary(
                project_id=load_project_config(project_dir)["project_id"],
                records=records,
                generated_at=generated_at,
            )
            if summary != expected:
                errors.append("logs/trial_summary.json: summary values are invalid or stale")
            markdown_path = project_dir / TRIAL_SUMMARY_MD
            if not markdown_path.is_file():
                errors.append("logs/trial_summary.md: summary is missing")
            elif markdown_path.read_text(encoding="utf-8") != _summary_markdown(expected):
                errors.append("logs/trial_summary.md: summary is invalid or stale")
        except (HarnessError, OSError) as exc:
            errors.append(str(exc))
    return errors


def write_trial_summary(
    project_dir: Path,
    *,
    records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    path = project_dir / TRIAL_METRICS_PATH
    records = records if records is not None else read_jsonl(path)
    errors = [error for record in records for error in validate_trial_record(record)]
    if errors:
        raise HarnessError(
            "INVALID_TRIAL_METRICS",
            "Cannot summarize invalid trial metrics",
            details={"errors": errors},
        )
    summary = _build_summary(
        project_id=load_project_config(project_dir)["project_id"],
        records=records,
        generated_at=utc_now(),
    )
    write_json(project_dir / TRIAL_SUMMARY_JSON, summary)
    atomic_write_text(project_dir / TRIAL_SUMMARY_MD, _summary_markdown(summary))
    return summary


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _build_summary(
    *,
    project_id: str,
    records: list[dict[str, Any]],
    generated_at: Any,
) -> dict[str, Any]:
    totals = {
        field: sum(record[field] for record in records) for field in (*NUMBER_FIELDS, *COUNT_FIELDS)
    }
    actual_minutes = totals["agent_runtime_minutes"] + totals["human_review_minutes"]
    return {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "project_id": project_id,
        "trial_count": len(records),
        "source_records_hash": _records_hash(records),
        "totals": totals,
        "derived": {
            "actual_minutes": actual_minutes,
            "net_minutes_saved": totals["baseline_minutes"] - actual_minutes,
            "content_keep_ratio": _ratio(totals["content_kept"], totals["content_total"]),
            "content_modify_ratio": _ratio(totals["content_modified"], totals["content_total"]),
            "content_rewrite_ratio": _ratio(totals["content_rewritten"], totals["content_total"]),
            "requirement_coverage_ratio": _ratio(
                totals["selected_requirements_covered"],
                totals["selected_requirements_total"],
            ),
        },
    }


def _records_hash(records: list[dict[str, Any]]) -> str:
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _summary_markdown(summary: dict[str, Any]) -> str:
    totals = summary["totals"]
    derived = summary["derived"]
    return (
        "# MVP 试用指标汇总\n\n"
        f"- 试用记录：{summary['trial_count']}\n"
        f"- 人工基线：{totals['baseline_minutes']} 分钟\n"
        f"- Agent 运行：{totals['agent_runtime_minutes']} 分钟\n"
        f"- 人工审阅修正：{totals['human_review_minutes']} 分钟\n"
        f"- 净节省：{derived['net_minutes_saved']} 分钟\n"
        f"- 映射纠错：{totals['mapping_correction_count']} 次\n"
        f"- 证据位置错误：{totals['evidence_location_error_count']} 次\n"
        f"- 跨 Agent 重复处理文件：{totals['cross_agent_reprocessed_files']} 个\n"
        f"- 内容直接保留比例：{_format_ratio(derived['content_keep_ratio'])}\n"
        f"- 内容局部修改比例：{_format_ratio(derived['content_modify_ratio'])}\n"
        f"- 内容重写比例：{_format_ratio(derived['content_rewrite_ratio'])}\n"
        f"- 所选要求覆盖率：{_format_ratio(derived['requirement_coverage_ratio'])}\n"
    )


def _format_ratio(value: float | None) -> str:
    return "无分母" if value is None else f"{value:.1%}"
