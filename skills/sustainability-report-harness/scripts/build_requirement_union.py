#!/usr/bin/env python3
"""Build a complete requirement union from a reviewable mapping plan."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.mapping import build_requirement_union


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("mapping_plan", type=Path)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace an unapproved union while preserving unchanged human decisions",
    )
    args = parser.parse_args()
    return run(
        lambda: build_requirement_union(args.project_dir, args.mapping_plan, replace=args.replace)
    )


if __name__ == "__main__":
    raise SystemExit(main())
