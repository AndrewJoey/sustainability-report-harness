#!/usr/bin/env python3
"""Validate ledger record schemas, stable IDs, and reference integrity."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.ledger import validate_ledger_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    args = parser.parse_args()
    exit_code = 0

    def action() -> dict[str, object]:
        nonlocal exit_code
        errors = validate_ledger_file(args.ledger.resolve())
        exit_code = 0 if not errors else 1
        return {"valid": not errors, "errors": errors}

    tool_error = run(action)
    return tool_error or exit_code


if __name__ == "__main__":
    raise SystemExit(main())
