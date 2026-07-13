# Evidence Protocol

Use this protocol when M2 evidence ingestion is available or when validating evidence-shaped fixtures.

## Classification and provenance

- Classify customer material as `client_evidence` and peer material as `peer_reference`.
- Preserve relative source path, content hash, file type, locator, excerpt, period, and unit.
- Never use peer material as support for a customer fact.
- Never claim a scanned PDF was parsed when OCR was unavailable.

## Reuse and conflict handling

- Reuse an unchanged source by its hash; do not parse it again.
- Allow one evidence ID to support multiple requirements.
- Surface conflicting periods, units, boundaries, and values without choosing silently.
- Stop at the Evidence Checkpoint for critical gaps, unreviewed mappings, and conflicts.

## M2 deterministic ingestion

- Read only `.docx`, text-based `.pdf`, and `.xlsx` files below `sources/client/` and
  `sources/peer/`.
- Record every discovered file in `state/source_manifest.jsonl`; retain its project-relative path,
  SHA-256, parser version, classification, status, evidence IDs, and timestamps.
- Locate Word content by heading path plus paragraph or table-row index.
- Locate PDF content by page and text-block index. Mark a file `needs_ocr` when no extractable text
  exists; do not emit evidence for it.
- Locate Excel content by worksheet and cell range. Preserve explicit values and formula strings;
  mark formulas `not_recalculated` rather than inventing calculated results.
- Capture a period or unit only when exactly one explicit, deterministic token is present in an
  excerpt. Leave ambiguous metadata empty.
- Remove stale evidence when a source changes or disappears. Preserve evidence IDs and `parsed_at`
  when an unchanged path, hash, and parser version are reused.
- Block ingestion when no supported source exists, a supported source is empty, or a supported
  source cannot be safely parsed. Unsupported files remain visible in the manifest but do not
  masquerade as evidence.

## Scanned-PDF decision gate

When a source is `needs_ocr`, inspect locally available OCR or vision options and present them to the
user. Persist the decision with `review_ocr.py`; the decision recorder never executes a cloud upload
or silently chooses an OCR engine. Cloud OCR requires project permission. `skip_as_gap` is allowed
only when the user explicitly marks the source noncritical. Record decisions in
`state/ocr_decisions.jsonl` bound to the source hash so changed files require a new decision.
