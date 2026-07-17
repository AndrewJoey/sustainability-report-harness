#!/usr/bin/env python3
"""Create or verify a framework-neutral project handoff snapshot."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.errors import HarnessError
from report_harness.handoff import create_handoff, handoff_status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("project_dir", type=Path)
    create.add_argument("--produced-by", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        return run(lambda: create_handoff(args.project_dir, produced_by=args.produced_by))

    def verify_handoff() -> dict[str, object]:
        status = handoff_status(args.project_dir)
        if not status["valid"]:
            raise HarnessError(
                "INVALID_HANDOFF",
                "Project handoff is missing or stale",
                details=status,
            )
        return status

    return run(verify_handoff)


if __name__ == "__main__":
    raise SystemExit(main())
