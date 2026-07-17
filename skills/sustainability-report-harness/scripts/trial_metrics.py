#!/usr/bin/env python3
"""Record or summarize append-only MVP trial metrics."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.io import read_json
from report_harness.trial import record_trial, write_trial_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    record = subparsers.add_parser("record")
    record.add_argument("project_dir", type=Path)
    record.add_argument("record_json", type=Path)
    record.add_argument("--recorded-by", required=True)
    summary = subparsers.add_parser("summary")
    summary.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    if args.command == "record":
        return run(
            lambda: record_trial(
                args.project_dir,
                read_json(args.record_json),
                recorded_by=args.recorded_by,
            )
        )
    return run(lambda: write_trial_summary(args.project_dir))


if __name__ == "__main__":
    raise SystemExit(main())
