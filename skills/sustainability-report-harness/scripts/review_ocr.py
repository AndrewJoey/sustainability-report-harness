#!/usr/bin/env python3
"""Record or inspect the user's scanned-PDF fallback decisions."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.ocr import DECISIONS, list_ocr_decisions, record_ocr_decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status")
    status.add_argument("project_dir", type=Path)
    decide = subparsers.add_parser("decide")
    decide.add_argument("project_dir", type=Path)
    decide.add_argument("source_file")
    decide.add_argument("decision", choices=sorted(DECISIONS))
    decide.add_argument("--criticality", choices=["critical", "noncritical"], required=True)
    decide.add_argument("--decided-by", required=True)
    decide.add_argument("--notes")
    args = parser.parse_args()

    def action() -> object:
        if args.command == "status":
            return {"decisions": list_ocr_decisions(args.project_dir)}
        return record_ocr_decision(
            args.project_dir,
            args.source_file,
            args.decision,
            decided_by=args.decided_by,
            criticality=args.criticality,
            notes=args.notes,
        )

    return run(action)


if __name__ == "__main__":
    raise SystemExit(main())
