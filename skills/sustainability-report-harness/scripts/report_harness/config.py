"""Project configuration contract and validation."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from .errors import HarnessError
from .io import read_yaml

REPORT_TYPES = {"sustainability", "climate", "combined"}
GRANULARITIES = {"concise", "standard", "detailed", "custom"}
GAP_HANDLING = {"questionnaire", "marked_draft", "gap_only"}
PEER_MODES = {"style_reference", "quality_benchmark", "both", "none"}
RETENTION_POLICIES = {"keep", "delete_after_export", "ask"}
PROJECT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")


def load_project_config(project_dir: Path) -> dict[str, Any]:
    value = read_yaml(project_dir / "project.yaml")
    if not isinstance(value, dict):
        raise HarnessError("INVALID_CONFIG", "project.yaml must contain a mapping", "project.yaml")
    return value


def validate_project_config(config: dict[str, Any]) -> list[str]:
    """Return all configuration failures as stable path-prefixed messages."""

    errors: list[str] = []
    required = {
        "project_id",
        "project_name",
        "client_name",
        "reporting_period_start",
        "reporting_period_end",
        "report_type",
        "primary_language",
        "target_length_words",
        "granularity",
        "selected_standards",
        "custom_requirements",
        "gap_handling",
        "peer_reference_mode",
        "data_policy",
        "deliverables",
    }
    for key in sorted(required - config.keys()):
        errors.append(f"{key}: required field is missing")

    _nonempty_string(config, "project_name", errors)
    _nonempty_string(config, "client_name", errors)
    project_id = config.get("project_id")
    if not isinstance(project_id, str) or not PROJECT_ID_PATTERN.fullmatch(project_id):
        errors.append("project_id: use 3-64 lowercase letters, numbers, or hyphens")

    start = _iso_date(config.get("reporting_period_start"), "reporting_period_start", errors)
    end = _iso_date(config.get("reporting_period_end"), "reporting_period_end", errors)
    if start is not None and end is not None and start > end:
        errors.append("reporting_period_end: must be on or after reporting_period_start")

    _enum(config, "report_type", REPORT_TYPES, errors)
    if config.get("primary_language") != "zh-CN":
        errors.append("primary_language: M1 requires zh-CN")
    _enum(config, "granularity", GRANULARITIES, errors)
    _enum(config, "gap_handling", GAP_HANDLING, errors)
    _enum(config, "peer_reference_mode", PEER_MODES, errors)

    target_length = config.get("target_length_words")
    if target_length is not None and (
        not isinstance(target_length, int) or isinstance(target_length, bool) or target_length <= 0
    ):
        errors.append("target_length_words: must be null or a positive integer")

    standards = config.get("selected_standards")
    if not isinstance(standards, list):
        errors.append("selected_standards: must be a list")
    else:
        seen: set[tuple[str, str]] = set()
        for index, item in enumerate(standards):
            path = f"selected_standards[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{path}: must be a mapping")
                continue
            for key in ("standard_id", "version_id"):
                if not isinstance(item.get(key), str) or not item[key].strip():
                    errors.append(f"{path}.{key}: non-empty string required")
            if not isinstance(item.get("confirmed_by_user"), bool):
                errors.append(f"{path}.confirmed_by_user: boolean required")
            pair = (str(item.get("standard_id", "")), str(item.get("version_id", "")))
            if pair in seen:
                errors.append(f"{path}: duplicate standard and version")
            seen.add(pair)

    if not isinstance(config.get("custom_requirements"), list):
        errors.append("custom_requirements: must be a list")

    policy = config.get("data_policy")
    if not isinstance(policy, dict):
        errors.append("data_policy: must be a mapping")
    else:
        for key in ("cloud_processing_allowed", "web_search_allowed", "anonymization_required"):
            if not isinstance(policy.get(key), bool):
                errors.append(f"data_policy.{key}: boolean required")
        if policy.get("retention") not in RETENTION_POLICIES:
            errors.append(f"data_policy.retention: must be one of {sorted(RETENTION_POLICIES)}")

    deliverables = config.get("deliverables")
    if not isinstance(deliverables, dict):
        errors.append("deliverables: must be a mapping")
    else:
        for key in ("master_report", "response_matrix", "gap_list", "evidence_list"):
            if not isinstance(deliverables.get(key), bool):
                errors.append(f"deliverables.{key}: boolean required")
        adaptations = deliverables.get("adaptations")
        if not isinstance(adaptations, list) or not all(
            isinstance(item, str) for item in adaptations
        ):
            errors.append("deliverables.adaptations: must be a list of standard IDs")

    return errors


def assert_valid_project_config(config: dict[str, Any]) -> None:
    errors = validate_project_config(config)
    if errors:
        raise HarnessError(
            "INVALID_PROJECT_CONFIG", "Project configuration is invalid", details={"errors": errors}
        )


def _nonempty_string(config: dict[str, Any], key: str, errors: list[str]) -> None:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{key}: non-empty string required")


def _iso_date(value: Any, path: str, errors: list[str]) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        errors.append(f"{path}: expected YYYY-MM-DD")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{path}: expected YYYY-MM-DD")
        return None


def _enum(config: dict[str, Any], key: str, allowed: set[str], errors: list[str]) -> None:
    if config.get(key) not in allowed:
        errors.append(f"{key}: must be one of {sorted(allowed)}")
