# QA Checklists

Apply the relevant checklist before approving a Checkpoint.

## Deterministic checks

- Project configuration is valid.
- Confirmed intake names existing customer files, an explicit existing-report choice, target
  frameworks, an explicit reference-case choice, and reporting preferences.
- Workflow state and Checkpoint dependencies are valid.
- IDs are nonempty and unique.
- All ledger references resolve.
- Selected requirements are not silently lost.
- Every source clause has at least one matching decomposed requirement.
- Locked standard versions match `project.yaml` and their content hashes.
- Every requirement appears exactly once in the union.
- Mapping and evidence-link IDs are unique and all references resolve.
- Evidence includes source hash and locator.
- Output names and fixed fields match the PRD.
- Formal outline covers every unified disclosure exactly once and has an approved Anchor selection.
- Anchor and master proposals cover only their permitted section scopes.
- Confirmed facts use accepted client evidence; peer evidence appears only in independent peer review.
- Every configured adaptation covers each master content block once, preserves master links, and
  does not entirely omit a target-standard requirement row.
- Internal DOCX/XLSX exports match the current ledger hash and their manifest file hashes.
- Markdown delivery contains one union master and exactly one adaptation per confirmed framework;
  risk labels and evidence comments remain present and the report manifest hashes are current.
- Clean export contains no unresolved content or unapproved gate.
- Cross-Agent handoff hashes match the current workflow, Checkpoints, contracts, and source
  fingerprints.
- Unchanged source paths, hashes, and parser versions are reused without `--force`.
- Trial records include time, correction, retention, coverage, and repeated-file fields; their
  summary hash matches the append-only source records.

## Human or model-assisted checks

- Mapping preserves meaningful differences and conditions.
- Every Agent-created mapping, evidence relationship, contradiction, and gap has a recorded human decision before Evidence approval.
- Evidence actually supports the statement.
- Content is accurate, editable, and appropriate in depth.
- Peer comparison remains separate from compliance response.
- Improvement suggestions do not invent customer facts.
- A named reviewer has decided every drafted content block and both assessment tracks.
- A named reviewer has accepted or edited every adaptation action before clean export.
- A receiving Agent preserves human edits and accepted decisions and reports correction cost
  together with time saved.

## Completion rule

Perform generate → validate → repair → revalidate → report. A checklist report with unresolved failures is not completion.
