# Project Brief Protocol

Use this protocol when creating or confirming `brief.md` and `project.yaml`.

## Required confirmation

Confirm client identity, reporting period, report type, purpose, audience, primary language, target length, granularity, required topics, requested deliverables, gap handling, peer-reference mode, and data policy. Let the consultant select applicable standards; present version recommendations separately and wait for confirmation.

## Persistence rules

- Keep `brief.md` visibly unconfirmed until the project-spec Checkpoint is approved.
- Store machine-readable values in `project.yaml`; do not rely on prose alone.
- Default cloud processing and web search to false.
- Never replace confirmed standards, data policy, or human text silently.
- Validate `project.yaml` after every change.

## MVP behavior

The Agent must ask for customer materials, an existing report or template, selected frameworks,
excellent/reference cases, and reporting preferences. Persist those answers with
`confirm_intake.py`; do not treat chat history as confirmation. The Harness validates and stores the
result but does not make semantic framework-selection decisions for the consultant.
