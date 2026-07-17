# Conversational Intake Protocol

## Ask before generating

Ask in ordinary business language for:

- customer factual materials under `sources/client/`;
- an existing report or template, or an explicit `none` decision;
- framework IDs chosen by the consultant;
- excellent/reference cases, or an explicit `none` decision;
- purpose, audience, tone, and required topics.

Do not assume that silence means no reference case. References are optional, but the decision is required.

## Persist the decision

Start from `templates/intake.json.template`. Use only project-relative paths and supported DOCX, PDF, or XLSX files. Run:

```text
python scripts/confirm_intake.py confirm <project-dir> <proposal.json> --confirmed-by <name>
```

This writes `state/intake.json`, approves the project-specification Checkpoint, and advances to standard confirmation. The selected standard IDs must later match the locked packages exactly.

## Reference boundaries

Set `reference_cases.usage` to `style_reference`, `quality_benchmark`, `both`, or `none`, and keep `project.yaml.peer_reference_mode` consistent. Reference evidence stays under `sources/peer/` and never supports customer facts.
