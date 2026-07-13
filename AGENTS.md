# Repository Guidelines

## Project Structure & Module Organization

This repository has completed its M3 multi-standard requirement-union milestone. Read these files before changing behavior:

- `PROJECT_PLAN.md`: status, milestones, dependencies, and handoff instructions.
- `HARNESS_ARCHITECTURE.md`: Garden-inspired Harness structure and stability protocol.
- `PRD.md`: functional requirements, data contracts, workflows, and acceptance cases.
- `REQUIREMENTS.md`: approved business intent and scope.

Start with a self-contained `skills/sustainability-report-harness/` package containing `SKILL.md`, `manifest.json`, phase-specific `references/`, deterministic `scripts/`, project `templates/`, and simulated `standards/fixtures/`. Keep tests under `tests/`, sanitized fixtures under `examples/`, and generated client projects outside source directories.

## Build, Test, and Development Commands

The repository uses Python 3.11+ with dependencies locked by `uv.lock`. Use the single standard command set below and do not add dependencies casually:

```text
make install     Install locked development dependencies
make test        Run the complete automated test suite
make lint        Run static checks without rewriting files
make format      Apply formatting and refresh Skill integrity hashes
make validate    Validate the Skill, schemas, and example projects
```

## Coding Style & Naming Conventions

Prefer small modules aligned with PRD boundaries: project management, source ingestion, standards registry, mapping, evidence, drafting, assessment, and export. Use `snake_case` for files and functions, `PascalCase` for data models, and stable prefixed IDs such as `FR-01`, `AC-01`, and `REQ-001`. Use four-space indentation for Python if Python is selected. Add formatters and linters with the initial scaffold, then record their exact commands here.

## Testing Guidelines

Map every change to stable PRD acceptance IDs; never reuse or renumber them. Put tests under `tests/` and name them `test_<behavior>`. Cover DOCX, PDF, XLSX, schema validation, state recovery, export blocking, and cross-Agent continuity. Never use confidential client files; use sanitized fixtures.

## Commit & Pull Request Guidelines

Use Conventional Commit style, for example `feat(mapping): add unified disclosure model` or `test(export): block unconfirmed content`. Pull requests must state the related `FR`/`AC` IDs, summarize behavior changes, list tests run, and identify PRD or project-plan updates. Include sample output only when it contains no client data.

## Security & Agent Instructions

Treat customer material as local and confidential. Never invent regulatory text, silently upgrade standards, overwrite human edits, or convert inferences into confirmed facts. Skills should orchestrate the Harness; deterministic parsing, state, validation, and export logic belong in core code.
