#!/usr/bin/env python3
"""Build one M4 Anchor section or the remaining master draft from an Agent proposal."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.drafting import build_draft


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("proposal", type=Path)
    parser.add_argument("stage", choices=["anchor", "master"])
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    return run(
        lambda: build_draft(args.project_dir, args.proposal, stage=args.stage, replace=args.replace)
    )


if __name__ == "__main__":
    raise SystemExit(main())
