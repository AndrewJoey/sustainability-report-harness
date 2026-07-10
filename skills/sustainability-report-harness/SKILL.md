---
name: sustainability-report-harness
description: Create, validate, inspect, and resume local multi-standard sustainability or climate disclosure report projects with persistent Checkpoints and a traceable disclosure ledger. Use when Codex must start or continue an ESG reporting project, confirm project data boundaries and specifications, validate project.yaml or disclosure_ledger.jsonl, enforce human review gates, or prepare later evidence, mapping, drafting, assessment, adaptation, and export work without inventing regulatory content.
---

# Sustainability Report Harness

Operate a local, traceable disclosure project. Keep deterministic state in the project directory and never treat the conversation as the source of truth.

## Establish the operating mode

1. Detect whether local Python scripts can run and whether project policy permits required model or web use.
2. State one mode before processing customer content:
   - `Full`: local scripts and permitted model capabilities are available.
   - `Local Restricted`: customer text cannot leave the local boundary; degrade semantic work explicitly.
   - `Advisor`: scripts cannot run; provide instructions only and do not claim verified artifacts.
3. Obtain project-specific data consent. Never infer consent from a different project or past conversation.

## Locate the deterministic commands

Resolve paths relative to this `SKILL.md`. Use scripts in `scripts/`:

- `scaffold_project.py`: create a project without overwriting existing content.
- `validate_project.py`: validate directories, configuration, workflow, and ledger.
- `workflow.py`: read state, update Checkpoints, and perform allowed transitions.
- `validate_ledger.py`: validate models, stable IDs, and references.
- `preflight_export.py`: block unsafe clean export.

Treat a nonzero exit code as a failed gate. Present the structured error and fix the cause before retrying.

## Start or resume a project

### Create

Confirm the client, reporting period, project name, and local destination. Then run:

```text
python scripts/scaffold_project.py <project-dir> \
  --project-id <stable-id> \
  --project-name <name> \
  --client-name <client> \
  --period-start YYYY-MM-DD \
  --period-end YYYY-MM-DD
```

The scaffold defaults cloud processing and web search to false, requires anonymization, and leaves standards unselected. Update these only from explicit user confirmation.

### Resume

Run `python scripts/workflow.py <project-dir> status`, inspect `project.yaml`, and read only the references needed for the current state. Preserve human-authored content and existing confirmed values.

## Follow the hard-gated workflow

1. Confirm data consent.
2. Confirm the project specification and user-selected standard versions.
3. Build evidence and the requirement union.
4. Confirm evidence gaps, mappings, and conflicts.
5. Generate and confirm the formal outline.
6. Generate one representative Anchor section and confirm it.
7. Generate and review the complete master draft.
8. Adapt from the master and pass export preflight.

M1 implements the scaffold, contracts, persistence, validators, and gate enforcement. Treat document parsing, semantic mapping, drafting, assessment, adaptation, and business-file export as later-phase capabilities until their implementations and reviewed fixtures exist.

## Load stage references only when needed

- Project setup or specification: read [PROJECT-BRIEF.md](references/PROJECT-BRIEF.md).
- Evidence work: read [EVIDENCE-PROTOCOL.md](references/EVIDENCE-PROTOCOL.md).
- Standards or mapping work: read [MAPPING-PROTOCOL.md](references/MAPPING-PROTOCOL.md).
- Formal outline work: read [OUTLINE-FORMAT.md](references/OUTLINE-FORMAT.md).
- Anchor or master drafting: read [DRAFTING-PROTOCOL.md](references/DRAFTING-PROTOCOL.md).
- Response assessment: read [ASSESSMENT-PROTOCOL.md](references/ASSESSMENT-PROTOCOL.md).
- Standard adaptation: read [ADAPTATION-PROTOCOL.md](references/ADAPTATION-PROTOCOL.md).
- Any gate or final validation: read [QA-CHECKLISTS.md](references/QA-CHECKLISTS.md).

## Preserve truth and review boundaries

- Let the consultant choose applicable standards; only recommend versions by reporting period.
- Never label simulated or unreviewed rules as official.
- Keep peer material out of the customer evidence classification.
- Require client evidence for confirmed facts.
- Mark inference, suggested text, and information gaps explicitly.
- Never silently upgrade standards, remove requirements, overwrite human edits, or bypass a Checkpoint.
- Derive Word, Excel, and adaptations from `state/disclosure_ledger.jsonl`; do not create independent business judgments in exports.

## Apply the quality loop

For every supported stage, perform: generate → validate → repair → revalidate → report. Run `validate_project.py` after project changes and `validate_ledger.py` after ledger changes. Before any clean export, run `preflight_export.py` and stop on every listed blocker.

