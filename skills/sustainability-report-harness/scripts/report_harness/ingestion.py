"""Project-level source ingestion, evidence persistence, and hash reuse."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .audit import append_event
from .errors import HarnessError
from .io import read_jsonl, write_jsonl
from .models import Evidence
from .parsers import PARSER_VERSION, ParsedItem, ParseResult, parse_source
from .workflow import WorkflowStore

SUPPORTED_EXTENSIONS = {".docx": "word", ".pdf": "pdf", ".xlsx": "excel"}
SOURCE_ROOTS = {"sources/client": "client_evidence", "sources/peer": "peer_reference"}
MAX_SOURCE_BYTES = 50 * 1024 * 1024
ALLOWED_WORKFLOW_STATES = {
    "ingesting_sources",
    "building_requirement_union",
    "awaiting_evidence_confirmation",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ingest_project_sources(project_dir: Path, *, force: bool = False) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    workflow_store = WorkflowStore(project_dir)
    workflow = workflow_store.load()
    state = workflow["workflow_state"]
    if state not in ALLOWED_WORKFLOW_STATES:
        raise HarnessError(
            "INGESTION_NOT_ALLOWED",
            f"Source ingestion is not allowed while workflow_state is {state}",
            "workflow_state",
        )
    if workflow["checkpoints"]["standards"]["status"] != "approved":
        raise HarnessError(
            "CHECKPOINT_REQUIRED",
            "Checkpoint standards must be approved before source ingestion",
            "standards",
        )
    if workflow["checkpoints"]["evidence"]["status"] == "approved":
        raise HarnessError(
            "EVIDENCE_ALREADY_APPROVED",
            "Approved evidence cannot be replaced without an explicit review workflow",
            "evidence",
        )

    manifest_path = project_dir / "state" / "source_manifest.jsonl"
    evidence_path = project_dir / "state" / "evidence.jsonl"
    previous_manifest = read_jsonl(manifest_path)
    previous_evidence = read_jsonl(evidence_path)
    previous_by_path = {record.get("source_file"): record for record in previous_manifest}
    evidence_by_id = {record.get("evidence_id"): record for record in previous_evidence}

    records: list[dict[str, Any]] = []
    evidence_records: list[dict[str, Any]] = []
    parse_cache = _build_parse_cache(previous_manifest, previous_evidence)
    stats = {
        "discovered": 0,
        "supported": 0,
        "parsed": 0,
        "reused": 0,
        "unsupported": 0,
        "blocked": 0,
    }

    for path, classification in _discover_sources(project_dir):
        stats["discovered"] += 1
        relative = path.relative_to(project_dir).as_posix()
        extension = path.suffix.lower()
        source_type = SUPPORTED_EXTENSIONS.get(extension)
        checked_at = utc_now()
        if source_type is None:
            records.append(
                {
                    "source_file": relative,
                    "source_hash": sha256_file(path),
                    "source_type": "unsupported",
                    "classification": classification,
                    "size_bytes": path.stat().st_size,
                    "parser_version": PARSER_VERSION,
                    "status": "unsupported",
                    "evidence_ids": [],
                    "parsed_at": None,
                    "checked_at": checked_at,
                    "message": f"Unsupported extension: {extension or '[none]'}",
                }
            )
            stats["unsupported"] += 1
            continue
        stats["supported"] += 1
        if path.stat().st_size > MAX_SOURCE_BYTES:
            records.append(
                _blocked_record(
                    relative,
                    path,
                    source_type,
                    classification,
                    checked_at,
                    "source_too_large",
                    f"Source exceeds {MAX_SOURCE_BYTES} bytes",
                )
            )
            stats["blocked"] += 1
            continue

        source_hash = sha256_file(path)
        previous = previous_by_path.get(relative)
        reusable = (
            not force
            and previous
            and previous.get("source_hash") == source_hash
            and previous.get("parser_version") == PARSER_VERSION
            and previous.get("status") in {"parsed", "needs_ocr", "empty"}
            and all(item in evidence_by_id for item in previous.get("evidence_ids", []))
        )
        if reusable:
            source_evidence = [evidence_by_id[item] for item in previous["evidence_ids"]]
            evidence_records.extend(source_evidence)
            reused_record = dict(previous)
            reused_record["checked_at"] = checked_at
            records.append(reused_record)
            stats["reused"] += 1
            if reused_record["status"] != "parsed":
                stats["blocked"] += 1
            continue

        cache_key = (source_hash, source_type)
        result = parse_cache.get(cache_key)
        if result is None or force:
            try:
                result = parse_source(path, source_type)
            except HarnessError as exc:
                records.append(
                    _blocked_record(
                        relative,
                        path,
                        source_type,
                        classification,
                        checked_at,
                        "error",
                        str(exc),
                        source_hash=source_hash,
                    )
                )
                stats["blocked"] += 1
                continue
            parse_cache[cache_key] = result

        source_evidence = [
            _evidence_record(
                relative,
                source_hash,
                source_type,
                classification,
                item,
            )
            for item in result.items
        ]
        evidence_records.extend(source_evidence)
        records.append(
            {
                "source_file": relative,
                "source_hash": source_hash,
                "source_type": source_type,
                "classification": classification,
                "size_bytes": path.stat().st_size,
                "parser_version": PARSER_VERSION,
                "status": result.status,
                "evidence_ids": [item["evidence_id"] for item in source_evidence],
                "parsed_at": checked_at,
                "checked_at": checked_at,
                "message": result.message,
            }
        )
        stats["parsed"] += 1
        if result.status != "parsed":
            stats["blocked"] += 1

    records.sort(key=lambda item: item["source_file"])
    evidence_records.sort(key=lambda item: (item["source_file"], item["evidence_id"]))
    _validate_unique_evidence(evidence_records)
    write_jsonl(manifest_path, records)
    write_jsonl(evidence_path, evidence_records)

    if stats["supported"] == 0:
        stats["blocked"] += 1
    complete = stats["blocked"] == 0
    if complete:
        note = (
            f"Evidence ingestion complete: {len(evidence_records)} records; "
            "requirement union pending"
        )
    elif stats["supported"] == 0:
        note = "Evidence ingestion blocked: no supported DOCX, text PDF, or XLSX sources found"
    else:
        note = f"Evidence ingestion blocked for {stats['blocked']} source(s)"
    workflow_store.set_checkpoint(
        "evidence",
        "ready" if complete else "blocked",
        artifacts=["state/source_manifest.jsonl", "state/evidence.jsonl"],
        notes=note,
    )
    if complete and state == "ingesting_sources":
        workflow_store.transition("building_requirement_union")
    append_event(
        project_dir,
        project_id=_project_id(project_dir),
        event="sources.ingested",
        message=note,
        details={**stats, "evidence_records": len(evidence_records), "force": force},
    )
    return {
        "valid": complete,
        "workflow_state": WorkflowStore(project_dir).load()["workflow_state"],
        "manifest": "state/source_manifest.jsonl",
        "evidence": "state/evidence.jsonl",
        "evidence_records": len(evidence_records),
        **stats,
    }


def validate_source_manifest(path: Path) -> list[str]:
    errors: list[str] = []
    records = read_jsonl(path)
    seen: set[str] = set()
    for index, record in enumerate(records, start=1):
        prefix = f"line {index}"
        source_file = record.get("source_file")
        if not isinstance(source_file, str) or not source_file:
            errors.append(f"{prefix}.source_file: non-empty string required")
        elif source_file in seen:
            errors.append(f"{prefix}.source_file: duplicate path {source_file}")
        else:
            seen.add(source_file)
            source_path = PurePosixPath(source_file)
            if (
                source_path.is_absolute()
                or ".." in source_path.parts
                or not any(source_file.startswith(f"{root}/") for root in SOURCE_ROOTS)
            ):
                errors.append(f"{prefix}.source_file: must stay under a public source root")
        source_hash = record.get("source_hash")
        if not isinstance(source_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", source_hash):
            errors.append(f"{prefix}.source_hash: SHA-256 hex digest required")
        if record.get("status") not in {
            "parsed",
            "needs_ocr",
            "empty",
            "unsupported",
            "source_too_large",
            "error",
        }:
            errors.append(f"{prefix}.status: invalid status")
        if not isinstance(record.get("evidence_ids"), list):
            errors.append(f"{prefix}.evidence_ids: list required")
        elif len(record["evidence_ids"]) != len(set(record["evidence_ids"])):
            errors.append(f"{prefix}.evidence_ids: values must be unique")
        if record.get("classification") not in SOURCE_ROOTS.values():
            errors.append(f"{prefix}.classification: invalid classification")
        elif isinstance(source_file, str):
            expected_classification = next(
                (
                    classification
                    for root, classification in SOURCE_ROOTS.items()
                    if source_file.startswith(f"{root}/")
                ),
                None,
            )
            if expected_classification != record.get("classification"):
                errors.append(f"{prefix}.classification: does not match source root")
        if not isinstance(record.get("parser_version"), str) or not record["parser_version"]:
            errors.append(f"{prefix}.parser_version: non-empty string required")
    return errors


def validate_evidence_file(path: Path, manifest_path: Path | None = None) -> list[str]:
    errors: list[str] = []
    records = read_jsonl(path)
    manifest_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    if manifest_path is not None:
        manifest_by_pair = {
            (record.get("source_file", ""), record.get("source_hash", "")): record
            for record in read_jsonl(manifest_path)
        }
    seen: set[str] = set()
    for index, record in enumerate(records, start=1):
        prefix = f"line {index}"
        try:
            evidence = Evidence.from_dict(record)
        except HarnessError as exc:
            errors.append(f"{prefix}: {exc}")
            continue
        if evidence.evidence_id in seen:
            errors.append(f"{prefix}.evidence_id: duplicate ID {evidence.evidence_id}")
        seen.add(evidence.evidence_id)
        source_pair = (evidence.source_file, evidence.source_hash)
        if manifest_by_pair and source_pair not in manifest_by_pair:
            errors.append(f"{prefix}.source_file: source/hash pair is absent from manifest")
            continue
        manifest_record = manifest_by_pair.get(source_pair)
        if manifest_record:
            if evidence.evidence_id not in manifest_record.get("evidence_ids", []):
                errors.append(f"{prefix}.evidence_id: ID is absent from its manifest record")
            if evidence.source_type != manifest_record.get("source_type"):
                errors.append(f"{prefix}.source_type: does not match the manifest")
            if evidence.classification != manifest_record.get("classification"):
                errors.append(f"{prefix}.classification: does not match the manifest")
        errors.extend(_validate_locator(evidence, prefix))
    if manifest_by_pair:
        manifest_evidence_ids = {
            evidence_id
            for record in manifest_by_pair.values()
            for evidence_id in record.get("evidence_ids", [])
        }
        for missing_id in sorted(manifest_evidence_ids - seen):
            errors.append(f"manifest.evidence_ids: missing evidence record {missing_id}")
    return errors


def _discover_sources(project_dir: Path) -> list[tuple[Path, str]]:
    discovered: list[tuple[Path, str]] = []
    for relative_root, classification in SOURCE_ROOTS.items():
        root = project_dir / relative_root
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.is_symlink():
                raise HarnessError(
                    "SYMLINK_SOURCE_BLOCKED", "Source symlinks are not allowed", str(path)
                )
            try:
                path.resolve().relative_to(project_dir)
            except ValueError as exc:
                raise HarnessError(
                    "SOURCE_OUTSIDE_PROJECT", "Source resolves outside the project", str(path)
                ) from exc
            discovered.append((path, classification))
    return sorted(discovered, key=lambda item: item[0].relative_to(project_dir).as_posix())


def _build_parse_cache(
    manifest: list[dict[str, Any]], evidence: list[dict[str, Any]]
) -> dict[tuple[str, str], ParseResult]:
    evidence_by_id = {record.get("evidence_id"): record for record in evidence}
    cache: dict[tuple[str, str], ParseResult] = {}
    for record in manifest:
        if record.get("parser_version") != PARSER_VERSION or record.get("status") != "parsed":
            continue
        items: list[ParsedItem] = []
        for evidence_id in record.get("evidence_ids", []):
            item = evidence_by_id.get(evidence_id)
            if item:
                items.append(ParsedItem(locator=item["locator"], excerpt=item["excerpt"]))
        if len(items) == len(record.get("evidence_ids", [])):
            cache[(record["source_hash"], record["source_type"])] = ParseResult(items=items)
    return cache


def _evidence_record(
    source_file: str,
    source_hash: str,
    source_type: str,
    classification: str,
    item: ParsedItem,
) -> dict[str, Any]:
    locator_json = json.dumps(
        item.locator, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    stable_value = f"{source_file}\0{source_hash}\0{classification}\0{locator_json}"
    evidence_id = f"EVD-{hashlib.sha256(stable_value.encode()).hexdigest()[:16].upper()}"
    evidence = Evidence(
        evidence_id=evidence_id,
        source_file=source_file,
        source_hash=source_hash,
        source_type=source_type,
        locator=item.locator,
        excerpt=item.excerpt,
        classification=classification,
        period=_explicit_period(item.excerpt),
        unit=_explicit_unit(item.excerpt),
    )
    return evidence.to_dict()


def _blocked_record(
    relative: str,
    path: Path,
    source_type: str,
    classification: str,
    checked_at: str,
    status: str,
    message: str,
    *,
    source_hash: str | None = None,
) -> dict[str, Any]:
    return {
        "source_file": relative,
        "source_hash": source_hash or sha256_file(path),
        "source_type": source_type,
        "classification": classification,
        "size_bytes": path.stat().st_size,
        "parser_version": PARSER_VERSION,
        "status": status,
        "evidence_ids": [],
        "parsed_at": None,
        "checked_at": checked_at,
        "message": message,
    }


def _validate_unique_evidence(records: list[dict[str, Any]]) -> None:
    ids = [record["evidence_id"] for record in records]
    if len(ids) != len(set(ids)):
        raise HarnessError("DUPLICATE_EVIDENCE_ID", "Generated evidence IDs are not unique")


def _explicit_period(excerpt: str) -> str | None:
    years = list(dict.fromkeys(re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", excerpt)))
    return years[0] if len(years) == 1 else None


def _explicit_unit(excerpt: str) -> str | None:
    pattern = (
        r"(?<!\w)(tCO2e|kgCO2e|gCO2e|GWh|MWh|kWh|m3|m³|kg|tonnes?|tons?|"
        r"RMB|CNY|USD|HKD|%)(?!\w)"
    )
    matches = list(dict.fromkeys(match.group(0) for match in re.finditer(pattern, excerpt, re.I)))
    return matches[0] if len(matches) == 1 else None


def _validate_locator(evidence: Evidence, prefix: str) -> list[str]:
    locator = evidence.locator
    errors: list[str] = []
    if evidence.source_type == "word":
        if locator.get("kind") == "paragraph":
            if not _positive_int(locator.get("paragraph_index")):
                errors.append(f"{prefix}.locator.paragraph_index: positive integer required")
        elif locator.get("kind") == "table_row":
            for field in ("table_index", "row_index", "column_start", "column_end"):
                if not _positive_int(locator.get(field)):
                    errors.append(f"{prefix}.locator.{field}: positive integer required")
        else:
            errors.append(f"{prefix}.locator.kind: invalid Word locator")
        if not isinstance(locator.get("heading_path"), list):
            errors.append(f"{prefix}.locator.heading_path: list required")
    elif evidence.source_type == "pdf":
        if locator.get("kind") != "text_block":
            errors.append(f"{prefix}.locator.kind: invalid PDF locator")
        for field in ("page", "block_index"):
            if not _positive_int(locator.get(field)):
                errors.append(f"{prefix}.locator.{field}: positive integer required")
    elif evidence.source_type == "excel":
        if locator.get("kind") != "cell_range":
            errors.append(f"{prefix}.locator.kind: invalid Excel locator")
        if not isinstance(locator.get("sheet"), str) or not locator["sheet"]:
            errors.append(f"{prefix}.locator.sheet: non-empty string required")
        cell_range = locator.get("range")
        if not isinstance(cell_range, str) or not re.fullmatch(
            r"[A-Z]+[1-9]\d*(?::[A-Z]+[1-9]\d*)?", cell_range
        ):
            errors.append(f"{prefix}.locator.range: A1 cell or range required")
    return errors


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _project_id(project_dir: Path) -> str:
    from .config import load_project_config

    return str(load_project_config(project_dir)["project_id"])
