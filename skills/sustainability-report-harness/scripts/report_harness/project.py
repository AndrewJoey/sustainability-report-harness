"""Project scaffolding and project-level validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .audit import append_event
from .config import load_project_config, validate_project_config
from .errors import HarnessError
from .exporting import validate_export_manifest
from .ingestion import validate_evidence_file, validate_source_manifest
from .io import atomic_write_text, read_jsonl, write_yaml
from .ledger import validate_ledger_file
from .mapping import validate_union_completeness
from .ocr import validate_ocr_decisions
from .outline import validate_outline
from .standards import validate_project_standard_lock
from .workflow import WorkflowStore, validate_workflow

PROJECT_DIRECTORIES = (
    "sources/client",
    "sources/peer",
    "sources/requirements",
    "state",
    "drafts/master",
    "drafts/adaptations",
    "outputs/internal",
    "outputs/clean",
    "logs",
)

PROJECT_FILES = (
    "project.yaml",
    "brief.md",
    "state/workflow.json",
    "state/source_manifest.jsonl",
    "state/evidence.jsonl",
    "state/ocr_decisions.jsonl",
    "state/disclosure_ledger.jsonl",
    "state/outline.md",
    "logs/harness.jsonl",
)


def default_project_config(
    project_id: str,
    project_name: str,
    client_name: str,
    reporting_period_start: str,
    reporting_period_end: str,
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "project_name": project_name,
        "client_name": client_name,
        "reporting_period_start": reporting_period_start,
        "reporting_period_end": reporting_period_end,
        "report_type": "sustainability",
        "primary_language": "zh-CN",
        "target_length_words": None,
        "granularity": "standard",
        "selected_standards": [],
        "custom_requirements": [],
        "gap_handling": "questionnaire",
        "peer_reference_mode": "none",
        "data_policy": {
            "cloud_processing_allowed": False,
            "web_search_allowed": False,
            "anonymization_required": True,
            "retention": "ask",
        },
        "deliverables": {
            "master_report": True,
            "response_matrix": True,
            "gap_list": True,
            "evidence_list": True,
            "adaptations": [],
        },
    }


def scaffold_project(project_dir: Path, config: dict[str, Any]) -> None:
    if project_dir.exists() and any(project_dir.iterdir()):
        raise HarnessError(
            "PROJECT_NOT_EMPTY", "Refusing to overwrite a non-empty directory", str(project_dir)
        )
    errors = validate_project_config(config)
    if errors:
        raise HarnessError(
            "INVALID_PROJECT_CONFIG", "Project configuration is invalid", details={"errors": errors}
        )
    project_dir.mkdir(parents=True, exist_ok=True)
    for relative in PROJECT_DIRECTORIES:
        (project_dir / relative).mkdir(parents=True, exist_ok=True)
    write_yaml(project_dir / "project.yaml", config)
    atomic_write_text(
        project_dir / "brief.md",
        "# 项目规格\n\n> 状态：待顾问确认。不得将本文件视为已确认项目规格。\n",
    )
    atomic_write_text(
        project_dir / "state" / "outline.md",
        "# 候选目录\n\n> 正式目录必须在 Evidence Checkpoint 通过后生成并由顾问确认。\n",
    )
    for filename in (
        "source_manifest.jsonl",
        "evidence.jsonl",
        "ocr_decisions.jsonl",
        "disclosure_ledger.jsonl",
    ):
        atomic_write_text(project_dir / "state" / filename, "")
    WorkflowStore(project_dir).initialize()
    append_event(
        project_dir,
        project_id=config["project_id"],
        event="project.created",
        message="Project scaffold created with restrictive data defaults",
    )


def validate_project(project_dir: Path) -> list[str]:
    errors: list[str] = []
    for relative in PROJECT_DIRECTORIES:
        if not (project_dir / relative).is_dir():
            errors.append(f"{relative}: required directory is missing")
    for relative in PROJECT_FILES:
        if not (project_dir / relative).is_file():
            errors.append(f"{relative}: required file is missing")
    if (project_dir / "project.yaml").is_file():
        try:
            errors.extend(validate_project_config(load_project_config(project_dir)))
        except HarnessError as exc:
            errors.append(str(exc))
    if (project_dir / "state" / "workflow.json").is_file():
        try:
            workflow = json.loads(
                (project_dir / "state" / "workflow.json").read_text(encoding="utf-8")
            )
            errors.extend(validate_workflow(workflow))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"state/workflow.json: {exc}")
    ledger = project_dir / "state" / "disclosure_ledger.jsonl"
    if ledger.is_file():
        try:
            errors.extend(validate_ledger_file(ledger))
        except HarnessError as exc:
            errors.append(str(exc))
    manifest = project_dir / "state" / "source_manifest.jsonl"
    evidence = project_dir / "state" / "evidence.jsonl"
    if manifest.is_file():
        try:
            errors.extend(validate_source_manifest(manifest))
        except HarnessError as exc:
            errors.append(str(exc))
    if evidence.is_file():
        try:
            errors.extend(
                validate_evidence_file(evidence, manifest if manifest.is_file() else None)
            )
        except HarnessError as exc:
            errors.append(str(exc))
    ocr_decisions = project_dir / "state" / "ocr_decisions.jsonl"
    if ocr_decisions.is_file():
        try:
            errors.extend(validate_ocr_decisions(read_jsonl(ocr_decisions)))
        except HarnessError as exc:
            errors.append(str(exc))
    errors.extend(validate_project_standard_lock(project_dir))
    errors.extend(validate_union_completeness(project_dir))
    outline_json = project_dir / "state" / "outline.json"
    if outline_json.is_file() and ledger.is_file():
        try:
            errors.extend(
                validate_outline(
                    json.loads(outline_json.read_text(encoding="utf-8")),
                    read_jsonl(ledger),
                )
            )
        except (OSError, json.JSONDecodeError, HarnessError) as exc:
            errors.append(f"state/outline.json: {exc}")
    errors.extend(validate_export_manifest(project_dir, "internal"))
    errors.extend(validate_export_manifest(project_dir, "clean"))
    return errors
