# Drafting Protocol

Use this protocol for Anchor and master drafting after the formal outline is approved.

## Content controls

- Draft confirmed facts only from locatable customer evidence.
- Use exactly one content type: `confirmed_fact`, `inference`, `suggested_text`, or `information_gap`.
- Link every content block to unified disclosure IDs and applicable evidence IDs.
- Preserve human edits and record the last modifier.
- Do not repeat wording merely to satisfy a length target.
- Mark every Agent-created content block and assessment `unreviewed`.
- Write reviewed draft state into `state/disclosure_ledger.jsonl` first; Markdown and JSON snapshots
  under `drafts/master/` are derived views, not independent truth sources.

## Anchor gate

Generate one representative section with its evidence links, matrix rows, and gaps. Validate it, obtain approval for depth, tone, labels, and assessment behavior, then generate remaining sections from that approved pattern.

The Anchor proposal must contain only the selected `anchor_section_id`. The master proposal must
contain all remaining outline sections. Use `review_draft.py item` for each content, standards
assessment, and peer assessment; finalize the Anchor before building the master. Rebuilding must
preserve accepted or human-edited content when its stable ID is unchanged.
