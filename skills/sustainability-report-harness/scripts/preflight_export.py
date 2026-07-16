#!/usr/bin/env python3
"""Block clean export when content or workflow conditions are unsafe."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.adaptation import adaptation_preflight
from report_harness.command import run
from report_harness.config import load_project_config
from report_harness.io import read_jsonl
from report_harness.ledger import preflight_clean_export, validate_ledger
from report_harness.workflow import WorkflowStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    exit_code = 0

    def action() -> dict[str, object]:
        nonlocal exit_code
        project_dir = args.project_dir.resolve()
        records = read_jsonl(project_dir / "state" / "disclosure_ledger.jsonl")
        ledger_errors = validate_ledger(records)
        workflow = WorkflowStore(project_dir).load()
        config = load_project_config(project_dir)
        blockers = (
            preflight_clean_export(records) if config["deliverables"]["master_report"] else []
        )
        blockers.extend(adaptation_preflight(project_dir, records))
        if workflow["checkpoints"]["master"]["status"] != "approved":
            blockers.append(
                {
                    "content_id": "workflow",
                    "section_id": "master",
                    "reason": "master Checkpoint is not approved",
                }
            )
        if workflow["checkpoints"]["export"]["status"] != "approved":
            blockers.append(
                {
                    "content_id": "workflow",
                    "section_id": "export",
                    "reason": "export Checkpoint is not approved",
                }
            )
        allowed = not ledger_errors and not blockers
        exit_code = 0 if allowed else 1
        return {
            "allowed": allowed,
            "ledger_errors": ledger_errors,
            "blockers": blockers,
        }

    tool_error = run(action)
    return tool_error or exit_code


if __name__ == "__main__":
    raise SystemExit(main())
