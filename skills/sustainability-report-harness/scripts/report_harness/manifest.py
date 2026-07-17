"""Deterministic Skill bundle integrity manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

EXCLUDED_PARTS = {"__pycache__", ".DS_Store"}
EXCLUDED_FILES = {"manifest.json"}


def calculate_file_hashes(skill_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path.name in EXCLUDED_FILES:
            continue
        if any(part in EXCLUDED_PARTS for part in path.relative_to(skill_dir).parts):
            continue
        relative = path.relative_to(skill_dir).as_posix()
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def calculate_bundle_hash(file_hashes: dict[str, str]) -> str:
    canonical = json.dumps(file_hashes, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def build_manifest(skill_dir: Path) -> dict[str, Any]:
    files = calculate_file_hashes(skill_dir)
    return {
        "name": "sustainability-report-harness",
        "version": "0.6.0",
        "maturity": "m5.3-markdown-mvp",
        "schema_version": "1.0.0",
        "entrypoints": {
            "scaffold": "scripts/scaffold_project.py",
            "intake_confirmation": "scripts/confirm_intake.py",
            "source_ingestion": "scripts/ingest_sources.py",
            "ocr_review": "scripts/review_ocr.py",
            "standards": "scripts/standards.py",
            "union_builder": "scripts/build_requirement_union.py",
            "union_review": "scripts/review_requirement_union.py",
            "outline_builder": "scripts/build_outline.py",
            "outline_review": "scripts/review_outline.py",
            "draft_builder": "scripts/build_draft.py",
            "draft_review": "scripts/review_draft.py",
            "adaptation_builder": "scripts/build_adaptation.py",
            "adaptation_review": "scripts/review_adaptation.py",
            "markdown_export": "scripts/export_markdown.py",
            "project_handoff": "scripts/handoff_project.py",
            "trial_metrics": "scripts/trial_metrics.py",
            "project_validator": "scripts/validate_project.py",
            "ledger_validator": "scripts/validate_ledger.py",
            "workflow": "scripts/workflow.py",
            "export_preflight": "scripts/preflight_export.py",
            "project_export": "scripts/export_project.py",
            "export_review": "scripts/review_export.py",
        },
        "fixtures_are_official": False,
        "integrity": {
            "algorithm": "sha256",
            "bundle_hash": calculate_bundle_hash(files),
            "files": files,
        },
    }


def validate_manifest(skill_dir: Path) -> list[str]:
    manifest_path = skill_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"manifest.json: {exc}"]
    actual = calculate_file_hashes(skill_dir)
    expected_manifest = build_manifest(skill_dir)
    expected = manifest.get("integrity", {}).get("files")
    errors: list[str] = []
    for field in (
        "name",
        "version",
        "maturity",
        "schema_version",
        "entrypoints",
        "fixtures_are_official",
    ):
        if manifest.get(field) != expected_manifest[field]:
            errors.append(f"manifest.json: {field} does not match the release contract")
    if expected != actual:
        errors.append("manifest.json: file checksums do not match the Skill contents")
    bundle_hash = manifest.get("integrity", {}).get("bundle_hash")
    if bundle_hash != expected_manifest["integrity"]["bundle_hash"]:
        errors.append("manifest.json: bundle hash does not match the Skill contents")
    return errors
