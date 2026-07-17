# Agent Compatibility

## Common contract

Every Agent must read the same `SKILL.md`, execute the same deterministic scripts, and treat the project directory as the source of truth. An adapter may change discovery instructions, but must not change schemas, workflow semantics, IDs, or output paths.

Before continuing work from another Agent:

1. read `project.yaml` and `state/workflow.json`;
2. validate `state/handoff.json` when present;
3. run the project validator;
4. resume the next action recorded by the workflow or handoff;
5. preserve source hashes and human edits.

## MVP compatibility statement

The deterministic commands and project contracts are validated locally through Codex and automated
fresh-process tests. Product-specific live execution in Claude Code, WorkBuddy, or Trae is not an
MVP acceptance requirement and is not claimed as tested.

For Claude Code, place the complete Skill package under
`.claude/skills/sustainability-report-harness/` or explicitly direct Claude to the canonical
`SKILL.md`. WorkBuddy and Trae use the same generic method: configure the project Agent to load the
complete Skill directory and permit local Python commands. Exact discovery folders remain
product-specific; adapters must not fork the project schemas or business state.
