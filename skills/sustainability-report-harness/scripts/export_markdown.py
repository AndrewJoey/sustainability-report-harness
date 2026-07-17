#!/usr/bin/env python3
"""Generate the union master and framework-specific Markdown report drafts."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.markdown_export import export_markdown_reports, validate_markdown_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("project_dir", type=Path)
    validate = subparsers.add_parser("validate")
    validate.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    if args.command == "generate":
        return run(lambda: export_markdown_reports(args.project_dir))
    return run(
        lambda: {
            "valid": not (errors := validate_markdown_manifest(args.project_dir)),
            "errors": errors,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
