"""Conversational project-input confirmation and persistent MVP intake gate."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .audit import append_event
from .config import STANDARD_ID_PATTERN, load_project_config, validate_project_config
from .errors import HarnessError
from .io import atomic_write_text, read_json, write_json, write_yaml
from .workflow import WorkflowStore, utc_now

INTAKE_PATH = Path("state/intake.json")
INTAKE_SCHEMA_VERSION = "1.0.0"
REFERENCE_STATUSES = {"provided", "none"}
REFERENCE_USAGES = {"style_reference", "quality_benchmark", "both", "none"}
SUPPORTED_INPUT_EXTENSIONS = {".docx", ".pdf", ".xlsx"}


def confirm_project_intake(
    project_dir: Path,
    proposal_path: Path,
    *,
    confirmed_by: str,
) -> dict[str, Any]:
    """Persist the user's answers and approve the project specification gate."""

    project_dir = project_dir.resolve()
    if not confirmed_by.strip():
        raise HarnessError("APPROVER_REQUIRED", "confirmed_by is required")
    store = WorkflowStore(project_dir)
    workflow = store.load()
    if workflow["workflow_state"] != "awaiting_spec_confirmation":
        raise HarnessError(
            "INTAKE_CONFIRMATION_NOT_ALLOWED",
            "Project intake can only be confirmed while awaiting project specification",
            "workflow_state",
        )
    if workflow["checkpoints"]["data_consent"]["status"] != "approved":
        raise HarnessError(
            "CHECKPOINT_REQUIRED",
            "Data consent must be approved before project intake",
            "data_consent",
        )
    config = load_project_config(project_dir)
    config_errors = validate_project_config(config)
    if config_errors:
        raise HarnessError(
            "INVALID_PROJECT_CONFIG",
            "Project configuration must be valid before intake confirmation",
            details={"errors": config_errors},
        )
    proposal = read_json(proposal_path.resolve())
    candidate_config = dict(config)
    references = proposal.get("reference_cases") if isinstance(proposal, dict) else None
    if isinstance(references, dict):
        candidate_config["peer_reference_mode"] = (
            references.get("usage") if references.get("status") == "provided" else "none"
        )
    candidate_errors = validate_project_config(candidate_config)
    if candidate_errors:
        raise HarnessError(
            "INVALID_PROJECT_CONFIG",
            "Confirmed reference usage would make project configuration invalid",
            details={"errors": candidate_errors},
        )
    normalized = _normalize_intake(
        project_dir,
        proposal,
        confirmed_by=confirmed_by,
        config=candidate_config,
    )
    write_yaml(project_dir / "project.yaml", candidate_config)
    write_json(project_dir / INTAKE_PATH, normalized)
    atomic_write_text(project_dir / "brief.md", _brief_markdown(candidate_config, normalized))
    store.set_checkpoint(
        "project_spec",
        "approved",
        approved_by=confirmed_by,
        artifacts=["project.yaml", "brief.md", INTAKE_PATH.as_posix()],
        notes="Conversational inputs, target frameworks, and reference-case choice confirmed",
    )
    store.transition("awaiting_standard_confirmation")
    append_event(
        project_dir,
        project_id=str(config["project_id"]),
        event="project.intake_confirmed",
        message="Project materials, target frameworks, references, and preferences confirmed",
        details={
            "confirmed_by": confirmed_by,
            "client_files": len(normalized["client_materials"]["files"]),
            "reference_status": normalized["reference_cases"]["status"],
            "requested_standard_ids": normalized["requested_standard_ids"],
        },
    )
    return intake_status(project_dir)


def intake_status(project_dir: Path) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    path = project_dir / INTAKE_PATH
    if not path.is_file():
        return {
            "valid": False,
            "confirmed": False,
            "intake": INTAKE_PATH.as_posix(),
            "errors": ["state/intake.json: conversational intake has not been confirmed"],
        }
    intake = read_json(path)
    errors = validate_project_intake(project_dir, intake=intake, required=True)
    return {
        "valid": not errors,
        "confirmed": not errors,
        "intake": INTAKE_PATH.as_posix(),
        "confirmed_by": intake.get("confirmed_by") if isinstance(intake, dict) else None,
        "requested_standard_ids": (
            intake.get("requested_standard_ids", []) if isinstance(intake, dict) else []
        ),
        "reference_status": (
            intake.get("reference_cases", {}).get("status")
            if isinstance(intake, dict) and isinstance(intake.get("reference_cases"), dict)
            else None
        ),
        "errors": errors,
    }


def require_confirmed_intake(project_dir: Path) -> dict[str, Any]:
    path = project_dir.resolve() / INTAKE_PATH
    if not path.is_file():
        raise HarnessError(
            "INPUT_CONFIRMATION_REQUIRED",
            "Ask the user for materials, target frameworks, existing reports, and reference cases",
            INTAKE_PATH.as_posix(),
        )
    intake = read_json(path)
    errors = validate_project_intake(project_dir, intake=intake, required=True)
    if errors:
        raise HarnessError(
            "INVALID_PROJECT_INTAKE",
            "Confirmed project intake is invalid or stale",
            details={"errors": errors},
        )
    return intake


def validate_project_intake(
    project_dir: Path,
    *,
    intake: Any | None = None,
    required: bool = False,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Validate an optional legacy-compatible intake record against local source files."""

    project_dir = project_dir.resolve()
    path = project_dir / INTAKE_PATH
    if intake is None:
        if not path.is_file():
            return ["state/intake.json: confirmed intake is required"] if required else []
        try:
            intake = read_json(path)
        except HarnessError as exc:
            return [str(exc)]
    if not isinstance(intake, dict):
        return ["state/intake.json: root must be an object"]
    errors: list[str] = []
    allowed_root = {
        "schema_version",
        "confirmed_at",
        "confirmed_by",
        "client_materials",
        "existing_report_or_template",
        "reference_cases",
        "requested_standard_ids",
        "reporting_preferences",
    }
    missing = sorted(allowed_root - set(intake))
    unknown = sorted(set(intake) - allowed_root)
    if missing:
        errors.append(f"state/intake.json: missing fields {missing}")
    if unknown:
        errors.append(f"state/intake.json: unknown fields {unknown}")
    if intake.get("schema_version") != INTAKE_SCHEMA_VERSION:
        errors.append("state/intake.json.schema_version: must be 1.0.0")
    for field in ("confirmed_at", "confirmed_by"):
        if not isinstance(intake.get(field), str) or not intake[field].strip():
            errors.append(f"state/intake.json.{field}: non-empty string required")
    if isinstance(intake.get("confirmed_at"), str):
        try:
            datetime.fromisoformat(intake["confirmed_at"])
        except ValueError:
            errors.append("state/intake.json.confirmed_at: ISO-8601 timestamp required")

    client = intake.get("client_materials")
    if not isinstance(client, dict):
        errors.append("state/intake.json.client_materials: object required")
    else:
        client_files = client.get("files")
        if not isinstance(client_files, list) or not client_files:
            errors.append("state/intake.json.client_materials.files: at least one file required")
        else:
            errors.extend(
                _validate_input_paths(
                    project_dir,
                    client_files,
                    allowed_roots={"sources/client"},
                    field="client_materials.files",
                )
            )

    existing = intake.get("existing_report_or_template")
    if not isinstance(existing, dict):
        errors.append("state/intake.json.existing_report_or_template: object required")
    else:
        status = existing.get("status")
        files = existing.get("files")
        if status not in {"provided", "none"}:
            errors.append(
                "state/intake.json.existing_report_or_template.status: must be provided or none"
            )
        if not isinstance(files, list):
            errors.append("state/intake.json.existing_report_or_template.files: list required")
        elif status == "provided" and not files:
            errors.append(
                "state/intake.json.existing_report_or_template.files: provided requires files"
            )
        elif status == "none" and files:
            errors.append(
                "state/intake.json.existing_report_or_template.files: none requires an empty list"
            )
        else:
            errors.extend(
                _validate_input_paths(
                    project_dir,
                    files,
                    allowed_roots={"sources/client", "sources/requirements"},
                    field="existing_report_or_template.files",
                )
            )

    references = intake.get("reference_cases")
    if not isinstance(references, dict):
        errors.append("state/intake.json.reference_cases: object required")
    else:
        status = references.get("status")
        usage = references.get("usage")
        files = references.get("files")
        if status not in REFERENCE_STATUSES:
            errors.append("state/intake.json.reference_cases.status: must be provided or none")
        if usage not in REFERENCE_USAGES:
            errors.append("state/intake.json.reference_cases.usage: invalid reference usage")
        if not isinstance(files, list):
            errors.append("state/intake.json.reference_cases.files: list required")
        elif status == "provided" and (not files or usage == "none"):
            errors.append(
                "state/intake.json.reference_cases: provided requires files and a usage mode"
            )
        elif status == "none" and (files or usage != "none"):
            errors.append(
                "state/intake.json.reference_cases: none requires no files and usage none"
            )
        else:
            errors.extend(
                _validate_input_paths(
                    project_dir,
                    files,
                    allowed_roots={"sources/peer"},
                    field="reference_cases.files",
                )
            )

        try:
            configured_mode = (config or load_project_config(project_dir)).get(
                "peer_reference_mode"
            )
        except HarnessError as exc:
            errors.append(str(exc))
        else:
            expected_mode = usage if status == "provided" else "none"
            if configured_mode != expected_mode:
                errors.append(
                    "state/intake.json.reference_cases.usage: must match "
                    "project.yaml.peer_reference_mode"
                )

    requested = intake.get("requested_standard_ids")
    if (
        not isinstance(requested, list)
        or not requested
        or not all(isinstance(item, str) and item.strip() for item in requested)
    ):
        errors.append("state/intake.json.requested_standard_ids: non-empty string list required")
    elif len(requested) != len(set(requested)):
        errors.append("state/intake.json.requested_standard_ids: values must be unique")
    elif any(not STANDARD_ID_PATTERN.fullmatch(item) for item in requested):
        errors.append("state/intake.json.requested_standard_ids: invalid standard ID")

    preferences = intake.get("reporting_preferences")
    if not isinstance(preferences, dict):
        errors.append("state/intake.json.reporting_preferences: object required")
    else:
        expected = {"purpose", "audience", "tone", "required_topics"}
        if set(preferences) != expected:
            errors.append(
                "state/intake.json.reporting_preferences: requires purpose, audience, tone, "
                "and required_topics only"
            )
        for field in ("purpose", "audience", "tone"):
            if not isinstance(preferences.get(field), str) or not preferences[field].strip():
                errors.append(
                    f"state/intake.json.reporting_preferences.{field}: non-empty string required"
                )
        topics = preferences.get("required_topics")
        if not isinstance(topics, list) or not all(
            isinstance(item, str) and item.strip() for item in topics
        ):
            errors.append(
                "state/intake.json.reporting_preferences.required_topics: string list required"
            )
    return errors


def _normalize_intake(
    project_dir: Path,
    proposal: Any,
    *,
    confirmed_by: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(proposal, dict):
        raise HarnessError("INVALID_PROJECT_INTAKE", "Intake proposal must be an object")
    normalized = {
        **proposal,
        "schema_version": INTAKE_SCHEMA_VERSION,
        "confirmed_at": utc_now(),
        "confirmed_by": confirmed_by.strip(),
    }
    errors = validate_project_intake(project_dir, intake=normalized, required=True, config=config)
    if errors:
        raise HarnessError(
            "INVALID_PROJECT_INTAKE",
            "Project intake failed deterministic validation",
            details={"errors": errors},
        )
    return normalized


def _validate_input_paths(
    project_dir: Path,
    values: list[Any],
    *,
    allowed_roots: set[str],
    field: str,
) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        prefix = f"state/intake.json.{field}[{index}]"
        if not isinstance(value, str) or not value:
            errors.append(f"{prefix}: non-empty project-relative path required")
            continue
        pure = PurePosixPath(value)
        if pure.is_absolute() or ".." in pure.parts:
            errors.append(f"{prefix}: path must remain inside the project")
            continue
        if not any(value.startswith(f"{root}/") for root in allowed_roots):
            errors.append(f"{prefix}: path is outside its allowed source directory")
            continue
        if value in seen:
            errors.append(f"{prefix}: duplicate path")
        seen.add(value)
        path = project_dir / value
        if not path.is_file():
            errors.append(f"{prefix}: file does not exist")
        elif path.is_symlink():
            errors.append(f"{prefix}: source symlinks are not allowed")
        elif path.suffix.lower() not in SUPPORTED_INPUT_EXTENSIONS:
            errors.append(f"{prefix}: MVP supports only DOCX, PDF, and XLSX")
    return errors


def _brief_markdown(config: dict[str, Any], intake: dict[str, Any]) -> str:
    references = intake["reference_cases"]
    reference_choice = (
        f"已提供（{references['usage']}）"
        if references["status"] == "provided"
        else "用户已确认不提供"
    )
    existing = intake["existing_report_or_template"]
    existing_choice = "已提供" if existing["status"] == "provided" else "无"
    preferences = intake["reporting_preferences"]
    lines = [
        "# 项目规格",
        "",
        f"> 状态：已由 {intake['confirmed_by']} 于 {intake['confirmed_at']} 确认。",
        "",
        f"- 项目：{config['project_name']}",
        f"- 客户：{config['client_name']}",
        f"- 报告期间：{config['reporting_period_start']} 至 {config['reporting_period_end']}",
        f"- 用途：{preferences['purpose']}",
        f"- 读者：{preferences['audience']}",
        f"- 文风：{preferences['tone']}",
        f"- 目标准则：{', '.join(intake['requested_standard_ids'])}",
        f"- 既有报告或模板：{existing_choice}",
        f"- 优秀案例：{reference_choice}",
        "",
        "## 必须覆盖议题",
        "",
    ]
    topics = preferences["required_topics"]
    lines.extend(f"- {topic}" for topic in topics)
    if not topics:
        lines.append("- 无额外指定议题")
    return "\n".join(lines).rstrip() + "\n"
