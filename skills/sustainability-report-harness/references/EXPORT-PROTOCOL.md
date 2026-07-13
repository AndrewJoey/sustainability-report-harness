# Export Protocol

Use this protocol after the master draft has been generated and reviewed.

## Internal review package

Run `export_project.py <project-dir> internal`. Derive every file from the current outline, locked
standards, evidence index, and `state/disclosure_ledger.jsonl`:

- `master_report_internal.docx` with explicit content markers and review comments;
- `response_matrix.xlsx` with the fixed PRD field order;
- `gap_list.xlsx` and `evidence_list.xlsx`;
- `peer_assessment.xlsx` as a separate internal best-practice track;
- `export_manifest.json` with the ledger hash and every output hash.

Do not edit exported files to create new business judgments. Update the ledger and regenerate them.

## Clean package gate

Run clean export only after the master and export Checkpoints are approved and preflight reports no
unconfirmed inference, suggested text, information gap, rejected item, or stale output. The clean
DOCX omits internal markers, comments, and information-gap content. Any ledger change makes an older
manifest stale and requires regeneration.
