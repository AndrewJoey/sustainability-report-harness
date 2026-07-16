#!/usr/bin/env python3
"""Export internal review files or gate-approved clean master/adaptation reports."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.exporting import export_project


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("mode", choices=["internal", "clean"])
    args = parser.parse_args()
    return run(lambda: export_project(args.project_dir, mode=args.mode))


if __name__ == "__main__":
    raise SystemExit(main())
