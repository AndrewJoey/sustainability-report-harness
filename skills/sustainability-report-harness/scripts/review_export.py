#!/usr/bin/env python3
"""Approve clean export after validating current internal review artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.exporting import approve_export


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--reviewed-by", required=True)
    parser.add_argument("--notes")
    args = parser.parse_args()

    return run(
        lambda: approve_export(
            args.project_dir,
            reviewed_by=args.reviewed_by,
            notes=args.notes,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
