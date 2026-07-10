# QA Checklists

Apply the relevant checklist before approving a Checkpoint.

## Deterministic checks

- Project configuration is valid.
- Workflow state and Checkpoint dependencies are valid.
- IDs are nonempty and unique.
- All ledger references resolve.
- Selected requirements are not silently lost.
- Evidence includes source hash and locator.
- Output names and fixed fields match the PRD.
- Clean export contains no unresolved content or unapproved gate.

## Human or model-assisted checks

- Mapping preserves meaningful differences and conditions.
- Evidence actually supports the statement.
- Content is accurate, editable, and appropriate in depth.
- Peer comparison remains separate from compliance response.
- Improvement suggestions do not invent customer facts.

## Completion rule

Perform generate → validate → repair → revalidate → report. A checklist report with unresolved failures is not completion.

