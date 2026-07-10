"""Skill package integrity tests for M1 release reproducibility."""

import json
from pathlib import Path

from report_harness.manifest import build_manifest, calculate_bundle_hash


def test_manifest_build_is_deterministic():
    skill_dir = Path("skills/sustainability-report-harness")
    first = build_manifest(skill_dir)
    second = build_manifest(skill_dir)
    assert first == second
    assert first["integrity"]["bundle_hash"] == calculate_bundle_hash(first["integrity"]["files"])
    assert first["fixtures_are_official"] is False


def test_all_json_schemas_parse():
    for path in Path("skills/sustainability-report-harness/schemas").glob("*.json"):
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
