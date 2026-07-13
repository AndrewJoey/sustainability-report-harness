#!/usr/bin/env python3
"""Ingest local DOCX, text PDF, and XLSX evidence sources."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.errors import HarnessError
from report_harness.ingestion import ingest_project_sources


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--force", action="store_true", help="Reparse supported sources")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    def action() -> dict[str, object]:
        result = ingest_project_sources(args.project_dir, force=args.force)
        if not result["valid"]:
            raise HarnessError(
                "INGESTION_INCOMPLETE",
                "One or more sources require attention",
                details=result,
            )
        return result

    return run(action)


if __name__ == "__main__":
    raise SystemExit(main())
