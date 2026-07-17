# Markdown Output Contract

## Required files

Generate one union master and exactly one file per framework confirmed in intake:

```text
outputs/markdown/master_report.md
outputs/markdown/adapted_<standard-id>.md
outputs/markdown/report_manifest.json
```

Do not generate a framework file until its adaptation proposal covers every master content block exactly once and retains every applicable framework requirement.

## Content markers

- Render confirmed facts without a risk prefix, but keep their evidence IDs.
- Render inference as `[待确认-推断]`.
- Render proposed wording as `[建议文本]`.
- Render missing information as `[信息缺口]`.
- Put `content_id` and `evidence_ids` in a nearby HTML comment.

The Markdown files are editable internal drafts. They are not clean external reports.

## Integrity

`report_manifest.json` binds `project.yaml`, confirmed intake, every customer/reference/template file
named in intake, the standard lock, requirement union, ledger, formal outline, and all generated
Markdown by SHA-256. Validate after any edit. A stale manifest means regenerate from the ledger; do
not manually update hashes.
