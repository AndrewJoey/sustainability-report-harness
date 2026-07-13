#!/usr/bin/env python3
"""Review M3 mappings, evidence links, gaps, and the Evidence Checkpoint."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_harness.command import run
from report_harness.mapping import (
    finalize_requirement_union,
    review_evidence_link,
    review_gap,
    review_mapping,
    union_review_status,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    mapping = subparsers.add_parser("mapping")
    mapping.add_argument("mapping_id")
    _decision_args(mapping)
    mapping.add_argument("--mapping-type")
    mapping.add_argument("--difference-notes")
    link = subparsers.add_parser("evidence-link")
    link.add_argument("link_id")
    _decision_args(link)
    link.add_argument("--relationship")
    link.add_argument("--notes")
    gap = subparsers.add_parser("gap")
    gap.add_argument("gap_id")
    _decision_args(gap)
    gap.add_argument("--criticality")
    gap.add_argument("--notes")
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--reviewed-by", required=True)
    finalize.add_argument("--notes")
    return parser.parse_args()


def _decision_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("decision", choices=["accepted", "rejected", "edited"])
    parser.add_argument("--reviewed-by", required=True)
    parser.add_argument("--review-notes")


def main() -> int:
    args = parse_args()

    def action():
        if args.command == "status":
            return union_review_status(args.project_dir)
        if args.command == "mapping":
            return review_mapping(
                args.project_dir,
                args.mapping_id,
                args.decision,
                reviewed_by=args.reviewed_by,
                mapping_type=args.mapping_type,
                difference_notes=args.difference_notes,
                review_notes=args.review_notes,
            )
        if args.command == "evidence-link":
            return review_evidence_link(
                args.project_dir,
                args.link_id,
                args.decision,
                reviewed_by=args.reviewed_by,
                relationship=args.relationship,
                notes=args.notes or args.review_notes,
            )
        if args.command == "gap":
            return review_gap(
                args.project_dir,
                args.gap_id,
                args.decision,
                reviewed_by=args.reviewed_by,
                criticality=args.criticality,
                notes=args.notes or args.review_notes,
            )
        return finalize_requirement_union(
            args.project_dir, reviewed_by=args.reviewed_by, notes=args.notes
        )

    return run(action)


if __name__ == "__main__":
    raise SystemExit(main())
