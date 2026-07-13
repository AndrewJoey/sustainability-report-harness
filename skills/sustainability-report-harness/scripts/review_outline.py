#!/usr/bin/env python3
"""Approve the formal outline or request changes while preserving the Checkpoint."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.outline import review_outline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("decision", choices=["approved", "changes_requested"])
    parser.add_argument("--reviewed-by", required=True)
    parser.add_argument("--notes")
    args = parser.parse_args()
    return run(
        lambda: review_outline(
            args.project_dir,
            args.decision,
            reviewed_by=args.reviewed_by,
            notes=args.notes,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
