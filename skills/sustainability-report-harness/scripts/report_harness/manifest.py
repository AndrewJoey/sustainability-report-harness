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
        "version": "0.1.0",
        "maturity": "m1",
        "schema_version": "1.0.0",
        "entrypoints": {
            "scaffold": "scripts/scaffold_project.py",
            "project_validator": "scripts/validate_project.py",
            "ledger_validator": "scripts/validate_ledger.py",
            "workflow": "scripts/workflow.py",
            "export_preflight": "scripts/preflight_export.py",
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
    expected = manifest.get("integrity", {}).get("files")
    errors: list[str] = []
    if expected != actual:
        errors.append("manifest.json: file checksums do not match the Skill contents")
    bundle_hash = manifest.get("integrity", {}).get("bundle_hash")
    if bundle_hash != calculate_bundle_hash(actual):
        errors.append("manifest.json: bundle hash does not match the Skill contents")
    return errors
