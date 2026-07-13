#!/usr/bin/env python3
"""Review M4 content/assessments and finalize Anchor or master Checkpoints."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.drafting import (
    draft_status,
    finalize_draft,
    request_draft_changes,
    review_draft_item,
)
from report_harness.io import read_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status")
    status.add_argument("project_dir", type=Path)
    status.add_argument("stage", choices=["anchor", "master"])
    item = subparsers.add_parser("item")
    item.add_argument("project_dir", type=Path)
    item.add_argument("collection", choices=["content", "assessments", "peer_assessments"])
    item.add_argument("item_id")
    item.add_argument("decision", choices=["accepted", "rejected", "edited"])
    item.add_argument("--reviewed-by", required=True)
    item.add_argument("--changes", type=Path)
    item.add_argument("--notes")
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("project_dir", type=Path)
    finalize.add_argument("stage", choices=["anchor", "master"])
    finalize.add_argument("--reviewed-by", required=True)
    finalize.add_argument("--notes")
    changes = subparsers.add_parser("request-changes")
    changes.add_argument("project_dir", type=Path)
    changes.add_argument("stage", choices=["anchor", "master"])
    changes.add_argument("--reviewed-by", required=True)
    changes.add_argument("--notes", required=True)
    args = parser.parse_args()

    def action() -> object:
        if args.command == "status":
            return draft_status(args.project_dir, args.stage)
        if args.command == "item":
            return review_draft_item(
                args.project_dir,
                args.collection,
                args.item_id,
                args.decision,
                reviewed_by=args.reviewed_by,
                changes=read_json(args.changes) if args.changes else None,
                notes=args.notes,
            )
        if args.command == "finalize":
            return finalize_draft(
                args.project_dir,
                args.stage,
                reviewed_by=args.reviewed_by,
                notes=args.notes,
            )
        return request_draft_changes(
            args.project_dir,
            args.stage,
            reviewed_by=args.reviewed_by,
            notes=args.notes,
        )

    return run(action)


if __name__ == "__main__":
    raise SystemExit(main())
