#!/usr/bin/env python3
"""Read and update persistent project workflow state."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.errors import HarnessError
from report_harness.workflow import CHECKPOINT_STATUSES, CHECKPOINTS, WORKFLOW_STATES, WorkflowStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    transition = subparsers.add_parser("transition")
    transition.add_argument("state", choices=sorted(WORKFLOW_STATES))
    checkpoint = subparsers.add_parser("checkpoint")
    checkpoint.add_argument("name", choices=CHECKPOINTS)
    checkpoint.add_argument("status", choices=sorted(CHECKPOINT_STATUSES))
    checkpoint.add_argument("--approved-by")
    checkpoint.add_argument("--artifact", action="append", default=[])
    checkpoint.add_argument("--notes")
    subparsers.add_parser("resume")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = WorkflowStore(args.project_dir.resolve())

    def action():
        if args.command == "status":
            return store.load()
        if args.command == "transition":
            return store.transition(args.state)
        if args.command == "checkpoint":
            if args.name != "data_consent":
                raise HarnessError(
                    "DOMAIN_REVIEW_REQUIRED",
                    f"Checkpoint {args.name} must be updated by its stage-specific command",
                    args.name,
                )
            return store.set_checkpoint(
                args.name,
                args.status,
                approved_by=args.approved_by,
                artifacts=args.artifact,
                notes=args.notes,
            )
        return store.resume()

    return run(action)


if __name__ == "__main__":
    raise SystemExit(main())
