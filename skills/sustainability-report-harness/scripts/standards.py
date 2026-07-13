#!/usr/bin/env python3
"""Recommend or lock reviewed standard packages for a project."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.config import load_project_config
from report_harness.standards import lock_standard_versions, recommend_standard_versions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    recommend = subparsers.add_parser("recommend")
    recommend.add_argument("project_dir", type=Path)
    recommend.add_argument("--standard-id", action="append", required=True)
    recommend.add_argument("--package", action="append", type=Path, required=True)
    lock = subparsers.add_parser("lock")
    lock.add_argument("project_dir", type=Path)
    lock.add_argument("--package", action="append", type=Path, required=True)
    lock.add_argument("--confirmed-by", required=True)
    lock.add_argument("--allow-simulated", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    def action():
        if args.command == "recommend":
            config = load_project_config(args.project_dir.resolve())
            return recommend_standard_versions(
                str(config["reporting_period_end"]), args.standard_id, args.package
            )
        return lock_standard_versions(
            args.project_dir,
            args.package,
            confirmed_by=args.confirmed_by,
            allow_simulated=args.allow_simulated,
        )

    return run(action)


if __name__ == "__main__":
    raise SystemExit(main())
