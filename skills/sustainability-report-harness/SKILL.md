---
name: sustainability-report-harness
description: Build or continue a local, traceable Chinese sustainability or climate report project from client DOCX/PDF/XLSX materials and consultant-reviewed standard packages. Use when an Agent must ask for report inputs, ingest evidence, map multiple frameworks, draft a union master, create one Markdown adaptation per framework, preserve human checkpoints, or hand the same project to another Agent without inventing regulatory content.
---

# Sustainability Report Harness

Use the project directory—not chat history—as the source of truth. Keep all customer material local unless the user explicitly approves otherwise.

## Start with mandatory questions

Before drafting, ask for and confirm:

1. client materials;
2. an existing report or client template, or an explicit statement that none exists;
3. the reporting frameworks selected by the consultant;
4. excellent/reference reports, or an explicit decision not to provide them;
5. report purpose, audience, tone, and required topics;
6. project-specific data-processing consent.

Reference reports are optional. Client materials and at least one target framework are required. If references are provided, ask whether they are for `style_reference`, `quality_benchmark`, or `both`. Never use peer material as client evidence.

Read [INTAKE-PROTOCOL.md](references/INTAKE-PROTOCOL.md), place files in the scaffolded source directories, and persist the confirmed answers with `confirm_intake.py`. Do not approve `project_spec` through the generic workflow command.

## Use the deterministic commands

Resolve all paths relative to this file. Treat a nonzero exit code as a failed gate.

- `scripts/scaffold_project.py`: create a non-overwriting project scaffold.
- `scripts/confirm_intake.py`: persist confirmed materials, frameworks, references, and preferences.
- `scripts/standards.py`: recommend and lock consultant-reviewed standard packages.
- `scripts/ingest_sources.py`: parse local DOCX, text PDF, and XLSX into reusable evidence.
- `scripts/review_ocr.py`: record the user's scanned-PDF fallback decision.
- `scripts/build_requirement_union.py` / `review_requirement_union.py`: build and review the complete requirement union.
- `scripts/build_outline.py` / `review_outline.py`: build and approve the formal outline and Anchor.
- `scripts/build_draft.py` / `review_draft.py`: build and review Anchor and master proposals.
- `scripts/build_adaptation.py` / `review_adaptation.py`: derive framework-specific proposals from master content IDs.
- `scripts/export_markdown.py`: generate and validate the Markdown master, per-framework drafts, and hash manifest.
- `scripts/handoff_project.py`: create or validate a cross-Agent integrity snapshot.
- `scripts/trial_metrics.py`: record trial effort and correction metrics.
- `scripts/validate_project.py`: validate the complete project.
- `scripts/workflow.py`: inspect state and update only the generic data-consent gate.

Word/Excel export commands remain available as legacy internal review outputs. Do not expand or present them as the default MVP delivery.

## Follow the gated workflow

1. Scaffold the project and confirm data consent.
2. Ask the mandatory questions and persist `state/intake.json`.
3. Lock exactly the frameworks confirmed in intake. Never silently select or upgrade a standard.
4. Ingest customer and optional peer sources.
5. Build the full requirement union; stop for mapping, evidence, conflict, and gap review.
6. Build and confirm the formal outline.
7. Build one representative Anchor; stop for review.
8. Build and approve the full union master.
9. Build a complete adaptation proposal for every confirmed framework.
10. Generate the Markdown delivery and validate its manifest.
11. Create or refresh the handoff before another Agent continues.

Never bypass a Checkpoint. Record only decisions the user or named reviewer actually made.

## Handle OCR as a user decision

For a scanned PDF, inspect which local options are available, such as PaddleOCR or Tesseract, and explain how each could be used. If no suitable local tool exists, offer authorized cloud OCR, a searchable replacement file, manual transcription, pause, or an explicit noncritical gap. Let the user decide and record that decision with `review_ocr.py`. Do not install, invoke, or upload to an OCR service without permission.

Read [EVIDENCE-PROTOCOL.md](references/EVIDENCE-PROTOCOL.md) for evidence and OCR rules.

## Separate deterministic and semantic work

Scripts validate paths, hashes, IDs, schemas, coverage, references, workflow state, and output integrity. The Agent proposes semantic mapping, evidence relevance, outlines, report prose, assessments, and adaptations. Every new semantic judgment starts `unreviewed`.

Use these references only for the active stage:

- Evidence and OCR: [EVIDENCE-PROTOCOL.md](references/EVIDENCE-PROTOCOL.md)
- Standards and mapping: [MAPPING-PROTOCOL.md](references/MAPPING-PROTOCOL.md)
- Outline: [OUTLINE-FORMAT.md](references/OUTLINE-FORMAT.md)
- Anchor/master drafting: [DRAFTING-PROTOCOL.md](references/DRAFTING-PROTOCOL.md)
- Response and peer assessment: [ASSESSMENT-PROTOCOL.md](references/ASSESSMENT-PROTOCOL.md)
- Framework adaptation: [ADAPTATION-PROTOCOL.md](references/ADAPTATION-PROTOCOL.md)
- Markdown delivery: [MARKDOWN-OUTPUT.md](references/MARKDOWN-OUTPUT.md)
- Cross-Agent continuation: [HANDOFF-PROTOCOL.md](references/HANDOFF-PROTOCOL.md) and [AGENT-COMPATIBILITY.md](references/AGENT-COMPATIBILITY.md)
- Final checks: [QA-CHECKLISTS.md](references/QA-CHECKLISTS.md)

## Preserve truth boundaries

- Use only imported, reviewed packages for real regulatory text. Fixtures are never official.
- Require client evidence for `confirmed_fact`.
- Mark `inference`, `suggested_text`, and `information_gap` explicitly.
- Preserve human edits and accepted review decisions.
- Do not remove framework-specific requirements during union mapping or adaptation.
- Keep `state/disclosure_ledger.jsonl` as the only business truth source.
- Derive every Markdown, Word, Excel, JSON snapshot, and manifest from current project state.

## Deliver Markdown first

After the master is approved and every confirmed framework has a complete adaptation proposal, run `export_markdown.py generate`. The expected files are:

```text
outputs/markdown/master_report.md
outputs/markdown/adapted_<standard-id>.md
outputs/markdown/report_manifest.json
```

Retain `[待确认-推断]`, `[建议文本]`, and `[信息缺口]`. Keep content and evidence IDs in HTML comments. Run `export_markdown.py validate` after any edit; regenerate if inputs or output hashes are stale.

## Apply the quality loop

For every stage perform: generate → validate → repair → revalidate → report. Run the project validator after state changes. Do not claim completion while any required input, framework adaptation, hash, Checkpoint, or professional review is missing.
