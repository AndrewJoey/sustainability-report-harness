#!/usr/bin/env python3
"""Build the formal M4 outline from an Agent proposal after Evidence approval."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.outline import build_formal_outline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("proposal", type=Path)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    return run(lambda: build_formal_outline(args.project_dir, args.proposal, replace=args.replace))


if __name__ == "__main__":
    raise SystemExit(main())
