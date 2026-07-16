#!/usr/bin/env python3
"""Review M5 adaptation actions and finish configured target standards."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.adaptation import (
    adaptation_status,
    finalize_adaptation,
    review_adaptation_item,
)
from report_harness.command import run
from report_harness.io import read_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status")
    status.add_argument("project_dir", type=Path)
    status.add_argument("target_standard_id")
    item = subparsers.add_parser("item")
    item.add_argument("project_dir", type=Path)
    item.add_argument("target_standard_id")
    item.add_argument("adaptation_id")
    item.add_argument("decision", choices=["accepted", "rejected", "edited"])
    item.add_argument("--reviewed-by", required=True)
    item.add_argument("--changes", type=Path)
    item.add_argument("--notes")
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("project_dir", type=Path)
    finalize.add_argument("target_standard_id")
    finalize.add_argument("--reviewed-by", required=True)
    finalize.add_argument("--notes")
    args = parser.parse_args()

    def action() -> object:
        if args.command == "status":
            return adaptation_status(args.project_dir, args.target_standard_id)
        if args.command == "item":
            return review_adaptation_item(
                args.project_dir,
                args.target_standard_id,
                args.adaptation_id,
                args.decision,
                reviewed_by=args.reviewed_by,
                changes=read_json(args.changes) if args.changes else None,
                notes=args.notes,
            )
        return finalize_adaptation(
            args.project_dir,
            args.target_standard_id,
            reviewed_by=args.reviewed_by,
            notes=args.notes,
        )

    return run(action)


if __name__ == "__main__":
    raise SystemExit(main())
