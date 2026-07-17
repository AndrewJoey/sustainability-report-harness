"""Markdown-first report delivery with traceable labels and integrity hashes."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .adaptation import adapted_view, safe_standard_id
from .audit import append_event
from .config import load_project_config
from .errors import HarnessError
from .intake import require_confirmed_intake
from .io import atomic_write_text, read_json, read_jsonl, write_json
from .ledger import validate_ledger
from .outline import OUTLINE_JSON, validate_outline
from .standards import LOCK_PATH, validate_project_standard_lock
from .workflow import WorkflowStore, utc_now

OUTPUT_DIR = Path("outputs/markdown")
MANIFEST_PATH = OUTPUT_DIR / "report_manifest.json"
MANIFEST_SCHEMA_VERSION = "1.0.0"
INPUT_PATHS = (
    "project.yaml",
    "state/intake.json",
    "state/standards.lock.json",
    "state/requirement_union.json",
    "state/disclosure_ledger.jsonl",
    "state/outline.json",
)
LABELS = {
    "confirmed_fact": None,
    "inference": "待确认-推断",
    "suggested_text": "建议文本",
    "information_gap": "信息缺口",
}


def export_markdown_reports(project_dir: Path) -> dict[str, Any]:
    """Write the union master and one Markdown draft per confirmed framework."""

    project_dir = project_dir.resolve()
    intake = require_confirmed_intake(project_dir)
    store = WorkflowStore(project_dir)
    workflow = store.load()
    if workflow["checkpoints"]["master"]["status"] != "approved":
        raise HarnessError(
            "CHECKPOINT_REQUIRED",
            "Master Checkpoint must be approved before multi-framework delivery",
            "master",
        )
    config = load_project_config(project_dir)
    targets = list(config["deliverables"]["adaptations"])
    if set(targets) != set(intake["requested_standard_ids"]):
        raise HarnessError(
            "FRAMEWORK_DELIVERY_MISMATCH",
            "Markdown targets must match the frameworks confirmed during intake",
        )
    standard_errors = validate_project_standard_lock(project_dir)
    if standard_errors:
        raise HarnessError(
            "INVALID_STANDARD_LOCK",
            "Markdown delivery requires a valid reviewed-standard lock",
            details={"errors": standard_errors},
        )
    governed_inputs = _governed_input_paths(intake)
    missing_inputs = [
        relative for relative in governed_inputs if not (project_dir / relative).is_file()
    ]
    if missing_inputs:
        raise HarnessError(
            "MISSING_MARKDOWN_INPUT",
            "Markdown delivery requires all governed input contracts",
            details={"paths": missing_inputs},
        )
    ledger = read_jsonl(project_dir / "state" / "disclosure_ledger.jsonl")
    ledger_errors = validate_ledger(ledger)
    if ledger_errors:
        raise HarnessError(
            "INVALID_LEDGER",
            "Markdown delivery requires a valid disclosure ledger",
            details={"errors": ledger_errors},
        )
    outline = read_json(project_dir / OUTLINE_JSON)
    outline_errors = validate_outline(outline, ledger)
    if outline_errors:
        raise HarnessError(
            "INVALID_OUTLINE",
            "Markdown delivery requires a current formal outline",
            details={"errors": outline_errors},
        )

    locked = _locked_metadata(project_dir)
    adapted_reports = [(target, *adapted_view(project_dir, target, ledger)) for target in targets]
    output_dir = project_dir / OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    expected_paths = [OUTPUT_DIR / "master_report.md"] + [
        OUTPUT_DIR / f"adapted_{safe_standard_id(target)}.md" for target in targets
    ]
    expected_names = {path.name for path in expected_paths}
    for stale in output_dir.glob("*.md"):
        if stale.name not in expected_names and stale.is_file():
            stale.unlink()

    master_path = project_dir / expected_paths[0]
    atomic_write_text(
        master_path,
        _render_report(
            title=f"{config['project_name']}｜统一母版",
            subtitle="覆盖已确认框架要求的联合报告初版",
            config=config,
            intake=intake,
            outline=outline,
            ledger=ledger,
            target_standard_id=None,
            source_content_ids=None,
        ),
    )
    files = [expected_paths[0]]
    for (target, adapted_outline, adapted_ledger), relative in zip(
        adapted_reports, expected_paths[1:], strict=True
    ):
        metadata = locked[target]
        atomic_write_text(
            project_dir / relative,
            _render_report(
                title=f"{config['project_name']}｜{metadata['name']}",
                subtitle=f"适配 {target} / {metadata['version_id']} 的报告初版",
                config=config,
                intake=intake,
                outline=adapted_outline,
                ledger=adapted_ledger,
                target_standard_id=target,
                source_content_ids={
                    item["adaptation_id"]: item["source_content_id"]
                    for row in ledger
                    for item in row.get("adaptations", [])
                    if item.get("target_standard_id") == target
                },
            ),
        )
        files.append(relative)

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "project_id": config["project_id"],
        "intake_confirmed_by": intake["confirmed_by"],
        "inputs": {relative: _sha256_file(project_dir / relative) for relative in governed_inputs},
        "files": [
            {
                "path": relative.as_posix(),
                "target_standard_id": (
                    None if relative.name == "master_report.md" else targets[index - 1]
                ),
                "sha256": _sha256_file(project_dir / relative),
            }
            for index, relative in enumerate(files)
        ],
    }
    write_json(project_dir / MANIFEST_PATH, manifest)
    append_event(
        project_dir,
        project_id=str(config["project_id"]),
        event="markdown.exported",
        message=f"Generated master and {len(targets)} framework-specific Markdown drafts",
        details={"files": [path.as_posix() for path in files]},
    )
    return {
        "valid": True,
        "files": [path.as_posix() for path in files],
        "manifest": MANIFEST_PATH.as_posix(),
        "frameworks": targets,
    }


def validate_markdown_manifest(project_dir: Path) -> list[str]:
    """Validate the optional Markdown delivery and detect stale inputs or outputs."""

    project_dir = project_dir.resolve()
    path = project_dir / MANIFEST_PATH
    if not path.is_file():
        markdown_files = list((project_dir / OUTPUT_DIR).glob("*.md"))
        return (
            [f"{MANIFEST_PATH}: manifest is required when Markdown outputs exist"]
            if markdown_files
            else []
        )
    try:
        manifest = read_json(path)
    except HarnessError as exc:
        return [str(exc)]
    if not isinstance(manifest, dict):
        return [f"{MANIFEST_PATH}: root must be an object"]
    errors: list[str] = []
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(f"{MANIFEST_PATH}.schema_version: must be 1.0.0")
    try:
        config = load_project_config(project_dir)
        intake = require_confirmed_intake(project_dir)
    except HarnessError as exc:
        return errors + [str(exc)]
    if manifest.get("project_id") != config.get("project_id"):
        errors.append(f"{MANIFEST_PATH}.project_id: does not match project.yaml")
    if manifest.get("intake_confirmed_by") != intake.get("confirmed_by"):
        errors.append(f"{MANIFEST_PATH}.intake_confirmed_by: manifest is stale")
    if set(config["deliverables"]["adaptations"]) != set(intake["requested_standard_ids"]):
        errors.append(f"{MANIFEST_PATH}: configured outputs do not match confirmed frameworks")
    inputs = manifest.get("inputs")
    governed_inputs = _governed_input_paths(intake)
    missing_inputs = [
        relative for relative in governed_inputs if not (project_dir / relative).is_file()
    ]
    errors.extend(f"{relative}: governed Markdown input is missing" for relative in missing_inputs)
    expected_inputs = {
        relative: _sha256_file(project_dir / relative)
        for relative in governed_inputs
        if (project_dir / relative).is_file()
    }
    if inputs != expected_inputs:
        errors.append(f"{MANIFEST_PATH}.inputs: source contracts have changed")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        return errors + [f"{MANIFEST_PATH}.files: list required"]
    targets = list(config["deliverables"]["adaptations"])
    expected = {"outputs/markdown/master_report.md": None} | {
        f"outputs/markdown/adapted_{safe_standard_id(target)}.md": target for target in targets
    }
    actual: dict[str, Any] = {}
    for index, item in enumerate(raw_files):
        if not isinstance(item, dict):
            errors.append(f"{MANIFEST_PATH}.files[{index}]: object required")
            continue
        relative = item.get("path")
        if not isinstance(relative, str):
            errors.append(f"{MANIFEST_PATH}.files[{index}].path: string required")
            continue
        if relative in actual:
            errors.append(f"{MANIFEST_PATH}.files[{index}].path: duplicate output path")
        actual[relative] = item.get("target_standard_id")
        output = project_dir / relative
        if not output.is_file():
            errors.append(f"{relative}: Markdown output is missing")
        elif item.get("sha256") != _sha256_file(output):
            errors.append(f"{relative}: Markdown output hash is stale")
    if actual != expected:
        errors.append(f"{MANIFEST_PATH}.files: output set does not match confirmed frameworks")
    return errors


def _render_report(
    *,
    title: str,
    subtitle: str,
    config: dict[str, Any],
    intake: dict[str, Any],
    outline: dict[str, Any],
    ledger: list[dict[str, Any]],
    target_standard_id: str | None,
    source_content_ids: dict[str, str] | None,
) -> str:
    row_by_unified = {row["unified_disclosure"]["unified_id"]: row for row in ledger}
    lines = [
        f"# {_one_line(title)}",
        "",
        f"> {subtitle}。本文件保留待确认标记，需由顾问复核后方可对外使用。",
        "",
        f"- 报告期间：{config['reporting_period_start']} 至 {config['reporting_period_end']}",
        f"- 目标读者：{intake['reporting_preferences']['audience']}",
        f"- 写作语气：{intake['reporting_preferences']['tone']}",
        f"- 参考案例：{_reference_summary(intake)}",
        "",
        "<!-- report_kind: "
        + ("union_master" if target_standard_id is None else "framework_adaptation")
        + (f" | target_standard_id: {target_standard_id}" if target_standard_id else "")
        + " -->",
        "",
    ]
    for section in outline["sections"]:
        lines.extend([f"## {_one_line(section['title'])}", ""])
        for unified_id in section["unified_ids"]:
            row = row_by_unified[unified_id]
            for content in row.get("content", []):
                label = LABELS[content["content_type"]]
                text = content["text"]
                lines.extend(
                    [
                        f"[{label}] {text}" if label else text,
                        "",
                        "<!-- content_id: "
                        f"{content['content_id']}"
                        + (
                            f" | source_content_id: {source_content_ids[content['content_id']]}"
                            if source_content_ids and content["content_id"] in source_content_ids
                            else ""
                        )
                        + " | evidence_ids: "
                        f"{', '.join(content.get('evidence_ids', [])) or 'none'} -->",
                        "",
                    ]
                )
    return "\n".join(lines).rstrip() + "\n"


def _reference_summary(intake: dict[str, Any]) -> str:
    reference = intake["reference_cases"]
    if reference["status"] == "none":
        return "用户已确认不提供"
    return f"已提供，用途为 {reference['usage']}"


def _one_line(value: Any) -> str:
    return " ".join(str(value).replace("#", "").split())


def _locked_metadata(project_dir: Path) -> dict[str, dict[str, str]]:
    lock = read_json(project_dir / LOCK_PATH)
    return {
        package["standard_version"]["standard_id"]: {
            "version_id": package["standard_version"]["version_id"],
            "name": package["standard_version"]["name"],
        }
        for package in lock["standards"]
    }


def _governed_input_paths(intake: dict[str, Any]) -> list[str]:
    source_paths = [
        *intake["client_materials"]["files"],
        *intake["existing_report_or_template"]["files"],
        *intake["reference_cases"]["files"],
    ]
    return [*INPUT_PATHS, *sorted(set(source_paths) - set(INPUT_PATHS))]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
