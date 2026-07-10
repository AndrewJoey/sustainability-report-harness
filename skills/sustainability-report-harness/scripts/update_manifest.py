#!/usr/bin/env python3
"""Refresh the immutable-release integrity fields in manifest.json."""

from __future__ import annotations

import json
from pathlib import Path

from report_harness.io import atomic_write_text
from report_harness.manifest import build_manifest


def main() -> int:
    skill_dir = Path(__file__).resolve().parent.parent
    manifest = build_manifest(skill_dir)
    atomic_write_text(
        skill_dir / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    print(manifest["integrity"]["bundle_hash"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
