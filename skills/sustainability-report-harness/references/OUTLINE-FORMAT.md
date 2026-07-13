# Outline Format

Use this protocol only after evidence and requirement-union construction.

For every section record:

- stable section ID and title;
- objective and target length;
- linked unified disclosure IDs and original requirements;
- available evidence coverage;
- expected gaps;
- requested depth, tables, cases, or chart suggestions.

A Phase 1 outline is a candidate only. Generate the formal `state/outline.json` and derived
`state/outline.md` after the Evidence Checkpoint. Every unified disclosure must appear exactly once,
unresolved conflicts must remain visible, and one `anchor_section_id` must be selected explicitly.

Run `build_outline.py`, then use `review_outline.py` to approve or request changes. Outline approval
is required before generating an Anchor. Rebuilding preserves the human decision only when the
validated proposal is unchanged; changed plans return to review.
