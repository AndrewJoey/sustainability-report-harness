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

## M1 boundary

M1 validates the Evidence model and references but does not parse Word, PDF, or Excel content.

