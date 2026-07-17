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

After every confirmed framework has a complete proposal, generate the Markdown master and
framework drafts; these internal drafts may retain unreviewed adaptation actions and risk labels.
Human review remains required before any clean external output. The legacy internal DOCX and
difference XLSX may still be generated when the consultant needs them.
