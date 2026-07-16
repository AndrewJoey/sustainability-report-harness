# Adaptation Protocol

Use this protocol only after the master Checkpoint is approved.

- Derive adaptations from master content IDs and the shared disclosure ledger.
- Use only the PRD actions `keep`, `condense`, `reorganize`, `supplement`, and `omit`.
- Cover every master content ID exactly once for each configured target standard. A row containing a
  target-standard requirement cannot be entirely omitted.
- Record the target standard, reason, target section, added evidence, content status, and review status.
- `keep`, `reorganize`, and `omit` must not contain rewritten text. `condense` and `supplement` must
  provide explicit adapted text.
- Keep every proposal `unreviewed`. Use `review_adaptation.py` to record named human decisions.
- Do not create an unlinked copy of a customer fact or use peer evidence as supplemental evidence.
- Re-run ledger and export checks after adaptation.

Generate the internal adaptation DOCX and difference XLSX before finalization. After every action is
accepted or edited, finalize the target, regenerate the internal package, and pass Export review
before generating the clean adaptation DOCX.
