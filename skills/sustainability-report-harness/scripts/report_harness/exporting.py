"""M4 Word/Excel export orchestration and ledger-consistency manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .audit import append_event
from .config import load_project_config
from .docx_export import write_master_docx
from .errors import HarnessError
from .io import read_json, read_jsonl, write_json
from .ledger import preflight_clean_export, validate_ledger
from .outline import OUTLINE_JSON
from .standards import LOCK_PATH
from .workflow import WorkflowStore, utc_now
from .xlsx_export import write_review_workbook

LEDGER_PATH = Path("state/disclosure_ledger.jsonl")
INTERNAL_FILES = {
    "master_report": "master_report_internal.docx",
    "response_matrix": "response_matrix.xlsx",
    "gap_list": "gap_list.xlsx",
    "evidence_list": "evidence_list.xlsx",
    "peer_assessment": "peer_assessment.xlsx",
}

RESPONSE_HEADERS = [
    "准则名称",
    "准则版本",
    "原始条款编号",
    "可检查要求编号",
    "可检查要求",
    "统一披露要求编号",
    "回应状态",
    "母版章节",
    "回应摘要",
    "证据编号",
    "证据位置",
    "判断理由",
    "缺失信息",
    "改进建议",
    "置信度",
    "置信度原因",
    "人工审阅状态",
    "人工备注",
]
GAP_HEADERS = [
    "要求编号",
    "准则与条款",
    "缺失信息",
    "需要原因",
    "建议补件问题",
    "建议责任部门",
    "优先级",
    "建议文本",
    "处理状态",
    "人工备注",
]
EVIDENCE_HEADERS = [
    "证据编号",
    "文件",
    "页码或表格位置",
    "证据摘录",
    "期间",
    "单位",
    "关联统一披露要求",
    "关联准则条款",
    "证据关系",
    "解析状态",
    "人工备注",
]
PEER_HEADERS = [
    "可检查要求编号",
    "统一披露要求编号",
    "同行位置",
    "评价理由",
    "同行证据编号",
    "同行证据位置",
    "人工审阅状态",
    "人工备注",
]


def export_project(project_dir: Path, *, mode: str) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    if mode not in {"internal", "clean"}:
        raise HarnessError("INVALID_EXPORT_MODE", "mode must be internal or clean")
    store = WorkflowStore(project_dir)
    workflow = store.load()
    ledger = read_jsonl(project_dir / LEDGER_PATH)
    errors = validate_ledger(ledger)
    if errors:
        raise HarnessError("INVALID_LEDGER", "Export requires a valid ledger", details=errors)
    outline = read_json(project_dir / OUTLINE_JSON)
    config = load_project_config(project_dir)
    _assert_complete_master(outline, ledger)

    if mode == "clean":
        blockers = preflight_clean_export(ledger)
        if workflow["checkpoints"]["master"]["status"] != "approved":
            blockers.append({"reason": "master Checkpoint is not approved"})
        if workflow["checkpoints"]["export"]["status"] != "approved":
            blockers.append({"reason": "export Checkpoint is not approved"})
        if workflow["workflow_state"] != "ready_for_export":
            blockers.append({"reason": "workflow_state is not ready_for_export"})
        if blockers:
            raise HarnessError(
                "CLEAN_EXPORT_BLOCKED", "Clean export preflight failed", details=blockers
            )
        output_dir = project_dir / "outputs/clean"
        output_dir.mkdir(parents=True, exist_ok=True)
        report = output_dir / "master_report_clean.docx"
        write_master_docx(
            report,
            config=config,
            outline=outline,
            ledger=ledger,
            internal=False,
        )
        files = [report]
    else:
        if workflow["workflow_state"] not in {
            "reviewing_master",
            "awaiting_export_confirmation",
            "ready_for_export",
        }:
            raise HarnessError(
                "INTERNAL_EXPORT_NOT_ALLOWED",
                "Internal export requires a complete generated master",
                "workflow_state",
            )
        output_dir = project_dir / "outputs/internal"
        output_dir.mkdir(parents=True, exist_ok=True)
        files = _write_internal_outputs(output_dir, config, outline, ledger, project_dir)

    manifest = _export_manifest(mode, project_dir, ledger, files)
    manifest_path = output_dir / "export_manifest.json"
    write_json(manifest_path, manifest)
    append_event(
        project_dir,
        project_id=str(config["project_id"]),
        event=f"export.{mode}",
        message=f"{mode.title()} business outputs generated from the ledger",
        details={"files": [path.name for path in files], "ledger_hash": manifest["ledger_hash"]},
    )
    return {
        "valid": True,
        "mode": mode,
        "workflow_state": store.load()["workflow_state"],
        "files": [path.relative_to(project_dir).as_posix() for path in files],
        "manifest": manifest_path.relative_to(project_dir).as_posix(),
    }


def validate_export_manifest(project_dir: Path, mode: str) -> list[str]:
    project_dir = project_dir.resolve()
    path = project_dir / "outputs" / mode / "export_manifest.json"
    if not path.is_file():
        return []
    errors: list[str] = []
    try:
        manifest = read_json(path)
        ledger = read_jsonl(project_dir / LEDGER_PATH)
    except HarnessError as exc:
        return [str(exc)]
    if manifest.get("mode") != mode:
        errors.append(f"{path}: mode does not match directory")
    current_hash = _json_hash(ledger)
    if manifest.get("ledger_hash") != current_hash:
        errors.append(f"{path}: outputs are stale relative to disclosure_ledger.jsonl")
    files = manifest.get("files")
    if not isinstance(files, list):
        return errors + [f"{path}: files list required"]
    for index, item in enumerate(files):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            errors.append(f"{path}: files[{index}] path required")
            continue
        output = (project_dir / item["path"]).resolve()
        try:
            output.relative_to(project_dir / "outputs" / mode)
        except ValueError:
            errors.append(f"{path}: files[{index}] escapes the {mode} output directory")
            continue
        if not output.is_file():
            errors.append(f"{path}: missing output {item['path']}")
        elif item.get("sha256") != _file_hash(output):
            errors.append(f"{path}: hash mismatch for {item['path']}")
        if item.get("source_ledger_hash") != manifest.get("ledger_hash"):
            errors.append(f"{path}: ledger hash mismatch for {item['path']}")
    return errors


def _write_internal_outputs(
    output_dir: Path,
    config: dict[str, Any],
    outline: dict[str, Any],
    ledger: list[dict[str, Any]],
    project_dir: Path,
) -> list[Path]:
    report = output_dir / INTERNAL_FILES["master_report"]
    write_master_docx(report, config=config, outline=outline, ledger=ledger, internal=True)
    response_rows, gap_rows, evidence_rows, peer_rows = _business_rows(project_dir, outline, ledger)
    response = output_dir / INTERNAL_FILES["response_matrix"]
    gaps = output_dir / INTERNAL_FILES["gap_list"]
    evidence = output_dir / INTERNAL_FILES["evidence_list"]
    peer = output_dir / INTERNAL_FILES["peer_assessment"]
    write_review_workbook(
        response,
        sheet_name="回应矩阵",
        title="准则回应矩阵",
        headers=RESPONSE_HEADERS,
        rows=response_rows,
    )
    write_review_workbook(
        gaps,
        sheet_name="缺口清单",
        title="缺口与补件清单",
        headers=GAP_HEADERS,
        rows=gap_rows,
    )
    write_review_workbook(
        evidence,
        sheet_name="证据清单",
        title="内部证据引用清单",
        headers=EVIDENCE_HEADERS,
        rows=evidence_rows,
    )
    write_review_workbook(
        peer,
        sheet_name="同行评价",
        title="同行与最佳实践独立评价",
        headers=PEER_HEADERS,
        rows=peer_rows,
    )
    return [report, response, gaps, evidence, peer]


def _business_rows(
    project_dir: Path, outline: dict[str, Any], ledger: list[dict[str, Any]]
) -> tuple[list[list[Any]], list[list[Any]], list[list[Any]], list[list[Any]]]:
    lock = read_json(project_dir / LOCK_PATH)
    standard_names = {
        (
            package["standard_version"]["standard_id"],
            package["standard_version"]["version_id"],
        ): package["standard_version"]["name"]
        for package in lock["standards"]
    }
    section_by_unified = {
        unified_id: section
        for section in outline["sections"]
        for unified_id in section["unified_ids"]
    }
    response_rows: list[list[Any]] = []
    gap_rows: list[list[Any]] = []
    peer_rows: list[list[Any]] = []
    evidence_aggregation: dict[str, dict[str, Any]] = {}
    manifest = {
        item["source_file"]: item
        for item in read_jsonl(project_dir / "state/source_manifest.jsonl")
    }
    gap_mode = load_project_config(project_dir)["gap_handling"]
    for row in ledger:
        unified = row["unified_disclosure"]
        unified_id = unified["unified_id"]
        section = section_by_unified[unified_id]
        content_by_id = {item["content_id"]: item for item in row.get("content", [])}
        assessment_by_requirement = {
            item["requirement_id"]: item for item in row.get("assessments", [])
        }
        peer_by_requirement = {
            item["requirement_id"]: item for item in row.get("peer_assessments", [])
        }
        evidence_by_id = {item["evidence_id"]: item for item in row.get("evidence", [])}
        gap_by_requirement = {item["requirement_id"]: item for item in row.get("gaps", [])}
        links_by_requirement: dict[str, list[dict[str, Any]]] = {}
        for link in row.get("evidence_links", []):
            for requirement_id in link.get("requirement_ids", []):
                links_by_requirement.setdefault(requirement_id, []).append(link)
        for requirement in row["requirements"]:
            requirement_id = requirement["requirement_id"]
            assessment = assessment_by_requirement[requirement_id]
            linked_content = [content_by_id[item] for item in assessment.get("content_ids", [])]
            linked_evidence = [
                evidence_by_id[item]
                for item in assessment.get("evidence_ids", [])
                if item in evidence_by_id
            ]
            standard_key = (requirement["standard_id"], requirement["version_id"])
            response_rows.append(
                [
                    standard_names.get(standard_key, requirement["standard_id"]),
                    requirement["version_id"],
                    requirement["clause_id"],
                    requirement_id,
                    requirement["check_text"],
                    unified_id,
                    assessment["response_status"],
                    section["title"],
                    "\n".join(item["text"] for item in linked_content),
                    assessment.get("evidence_ids", []),
                    [_locator_text(item["locator"]) for item in linked_evidence],
                    assessment["rationale"],
                    assessment.get("missing_information"),
                    assessment.get("improvement_suggestion"),
                    assessment["confidence"],
                    assessment["confidence_reason"],
                    assessment["review_status"],
                    assessment.get("human_notes"),
                ]
            )
            if assessment["response_status"] != "fully_addressed":
                gap = gap_by_requirement.get(requirement_id, {})
                missing = assessment.get("missing_information") or gap.get("reason") or "待补充"
                gap_rows.append(
                    [
                        requirement_id,
                        f"{standard_names.get(standard_key, requirement['standard_id'])} "
                        f"{requirement['clause_id']}",
                        missing,
                        unified["description"],
                        f"请补充：{missing}" if gap_mode == "questionnaire" else "",
                        "待顾问指定",
                        "高" if gap.get("criticality") == "critical" else "中",
                        assessment.get("improvement_suggestion")
                        if gap_mode == "marked_draft"
                        else "",
                        assessment["response_status"],
                        assessment.get("human_notes") or gap.get("notes"),
                    ]
                )
            peer = peer_by_requirement[requirement_id]
            peer_evidence = [
                evidence_by_id[item]
                for item in peer.get("evidence_ids", [])
                if item in evidence_by_id
            ]
            peer_rows.append(
                [
                    requirement_id,
                    unified_id,
                    peer["peer_position"],
                    peer["rationale"],
                    peer.get("evidence_ids", []),
                    [_locator_text(item["locator"]) for item in peer_evidence],
                    peer["review_status"],
                    peer.get("human_notes"),
                ]
            )
        for evidence in row.get("evidence", []):
            aggregate = evidence_aggregation.setdefault(
                evidence["evidence_id"],
                {
                    **evidence,
                    "unified_ids": set(),
                    "clauses": set(),
                    "relationships": set(),
                },
            )
            aggregate["unified_ids"].add(unified_id)
            for requirement in row["requirements"]:
                if any(
                    link.get("evidence_id") == evidence["evidence_id"]
                    for link in links_by_requirement.get(requirement["requirement_id"], [])
                ):
                    aggregate["clauses"].add(requirement["clause_id"])
            aggregate["relationships"].update(
                link["relationship"]
                for link in row.get("evidence_links", [])
                if link.get("evidence_id") == evidence["evidence_id"]
            )
    evidence_rows = []
    for evidence_id in sorted(evidence_aggregation):
        item = evidence_aggregation[evidence_id]
        parse = manifest.get(item["source_file"], {})
        evidence_rows.append(
            [
                evidence_id,
                item["source_file"],
                _locator_text(item["locator"]),
                item["excerpt"],
                item.get("period"),
                item.get("unit"),
                sorted(item["unified_ids"]),
                sorted(item["clauses"]),
                sorted(item["relationships"]) or ["peer_reference"],
                f"{parse.get('status', 'parsed')} / {item['classification']}",
                "",
            ]
        )
    return response_rows, gap_rows, evidence_rows, peer_rows


def _assert_complete_master(outline: dict[str, Any], ledger: list[dict[str, Any]]) -> None:
    rows = {row["unified_disclosure"]["unified_id"]: row for row in ledger}
    for section in outline["sections"]:
        for unified_id in section["unified_ids"]:
            row = rows.get(unified_id)
            if not row or not row.get("content"):
                raise HarnessError("INCOMPLETE_MASTER", f"Missing content for {unified_id}")
            required = {item["requirement_id"] for item in row["requirements"]}
            if {item["requirement_id"] for item in row.get("assessments", [])} != required:
                raise HarnessError("INCOMPLETE_MASTER", f"Missing assessments for {unified_id}")
            if {item["requirement_id"] for item in row.get("peer_assessments", [])} != required:
                raise HarnessError(
                    "INCOMPLETE_MASTER", f"Missing peer assessments for {unified_id}"
                )


def _locator_text(locator: dict[str, Any]) -> str:
    if locator.get("kind") == "text_block":
        return f"第 {locator.get('page')} 页 / 文本块 {locator.get('block_index')}"
    if locator.get("kind") == "cell_range":
        formula_note = " / 含公式" if locator.get("formulas") else ""
        return f"{locator.get('sheet')}!{locator.get('range')}{formula_note}"
    if locator.get("kind") == "paragraph":
        return f"段落 {locator.get('paragraph_index')}"
    if locator.get("kind") == "table_row":
        return f"表 {locator.get('table_index')} / 行 {locator.get('row_index')}"
    return json.dumps(locator, ensure_ascii=False, sort_keys=True)


def _export_manifest(
    mode: str, project_dir: Path, ledger: list[dict[str, Any]], files: list[Path]
) -> dict[str, Any]:
    ledger_hash = _json_hash(ledger)
    return {
        "schema_version": "1.0.0",
        "mode": mode,
        "generated_at": utc_now(),
        "ledger_path": LEDGER_PATH.as_posix(),
        "ledger_hash": ledger_hash,
        "files": [
            {
                "path": path.relative_to(project_dir).as_posix(),
                "sha256": _file_hash(path),
                "source_ledger_hash": ledger_hash,
            }
            for path in files
        ],
    }


def _json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
