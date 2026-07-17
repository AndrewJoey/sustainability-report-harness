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

## Existing reports and reference cases

- Read `state/intake.json` before proposing the outline or prose.
- Treat an existing customer report or template as a structure, terminology, and tone constraint.
  Do not treat its unsupported statements as current-period facts.
- For `style_reference`, extract abstract traits such as heading depth, sentence length, table use,
  and narrative tone; never copy distinctive wording.
- For `quality_benchmark`, use peer evidence only in `peer_assessments` to compare disclosure
  coverage, depth, quantification, and readability. Turn improvement ideas into `suggested_text` or
  explicit gaps, never customer facts.
- For `both`, apply both controls independently. For `none`, do not infer a peer benchmark.
- If a customer template conflicts with a locked framework requirement, show the conflict and ask
  the consultant; do not silently remove the requirement.

## Anchor gate

Generate one representative section with its evidence links, matrix rows, and gaps. Validate it, obtain approval for depth, tone, labels, and assessment behavior, then generate remaining sections from that approved pattern.

The Anchor proposal must contain only the selected `anchor_section_id`. The master proposal must
contain all remaining outline sections. Use `review_draft.py item` for each content, standards
assessment, and peer assessment; finalize the Anchor before building the master. Rebuilding must
preserve human-edited content when its stable ID is unchanged; changed Agent proposals return to
review.
