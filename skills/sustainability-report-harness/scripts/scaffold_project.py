#!/usr/bin/env python3
"""Create a new standard local project without overwriting existing content."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.project import default_project_config, scaffold_project


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--client-name", required=True)
    parser.add_argument("--period-start", required=True)
    parser.add_argument("--period-end", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    def action() -> dict[str, str]:
        config = default_project_config(
            project_id=args.project_id,
            project_name=args.project_name,
            client_name=args.client_name,
            reporting_period_start=args.period_start,
            reporting_period_end=args.period_end,
        )
        scaffold_project(args.project_dir.resolve(), config)
        return {"status": "created", "project_dir": str(args.project_dir.resolve())}

    return run(action)


if __name__ == "__main__":
    raise SystemExit(main())
