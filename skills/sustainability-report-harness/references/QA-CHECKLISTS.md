# QA Checklists

Apply the relevant checklist before approving a Checkpoint.

## Deterministic checks

- Project configuration is valid.
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
- Clean export contains no unresolved content or unapproved gate.

## Human or model-assisted checks

- Mapping preserves meaningful differences and conditions.
- Every Agent-created mapping, evidence relationship, contradiction, and gap has a recorded human decision before Evidence approval.
- Evidence actually supports the statement.
- Content is accurate, editable, and appropriate in depth.
- Peer comparison remains separate from compliance response.
- Improvement suggestions do not invent customer facts.

## Completion rule

Perform generate → validate → repair → revalidate → report. A checklist report with unresolved failures is not completion.
