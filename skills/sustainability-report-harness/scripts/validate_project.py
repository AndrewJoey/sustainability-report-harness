#!/usr/bin/env python3
"""Validate a project directory, configuration, workflow, and ledger."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import emit
from report_harness.project import validate_project


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    errors = validate_project(args.project_dir.resolve())
    emit({"valid": not errors, "errors": errors})
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
