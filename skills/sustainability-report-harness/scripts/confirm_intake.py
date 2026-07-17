#!/usr/bin/env python3
"""Confirm conversational report inputs and approve the project specification."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.intake import confirm_project_intake, intake_status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    confirm = subparsers.add_parser("confirm")
    confirm.add_argument("project_dir", type=Path)
    confirm.add_argument("proposal_json", type=Path)
    confirm.add_argument("--confirmed-by", required=True)
    status = subparsers.add_parser("status")
    status.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    if args.command == "confirm":
        return run(
            lambda: confirm_project_intake(
                args.project_dir,
                args.proposal_json,
                confirmed_by=args.confirmed_by,
            )
        )
    return run(lambda: intake_status(args.project_dir))


if __name__ == "__main__":
    raise SystemExit(main())
