#!/usr/bin/env python3
"""Validate the Skill, JSON schemas, and every bundled example project."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from report_harness.manifest import validate_manifest
from report_harness.project import validate_project


def main() -> int:
    repository = Path(__file__).resolve().parents[3]
    errors: list[str] = []
    skill_dir = Path(__file__).resolve().parents[1]
    errors.extend(validate_manifest(skill_dir))
    for schema in sorted((skill_dir / "schemas").glob("*.json")):
        try:
            json.loads(schema.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{schema}: {exc}")
    for project in sorted((repository / "examples").glob("*/project.yaml")):
        project_errors = validate_project(project.parent)
        errors.extend(f"{project.parent}: {error}" for error in project_errors)
    if not list((repository / "examples").glob("*/project.yaml")):
        errors.append("examples: no example project found")
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
