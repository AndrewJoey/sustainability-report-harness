# Cross-Agent Handoff Protocol

Use this protocol whenever a project moves to a new process, conversation, machine-local Agent, or
supported Agent adapter.

## Source of truth

- Treat `state/disclosure_ledger.jsonl` as the only business truth source.
- Treat `state/handoff.json` as a derived integrity snapshot, never as an editable replacement for
  project state.
- Read `project.yaml`, `state/workflow.json`, the current Checkpoints, and only the stage references
  needed for the recorded workflow state.
- Preserve every human-authored file and every `accepted` or `edited` decision.

## Before handing off

1. Run project validation and fix every error.
2. Run `handoff_project.py create <project-dir> --produced-by <agent-or-adapter>`.
3. Do not modify tracked project contracts after creating the snapshot. If they change, create a
   new snapshot.
4. Do not copy customer material to another location unless the project's data policy and the user
   explicitly permit it.

## When receiving a handoff

1. Run `handoff_project.py verify <project-dir>` in a fresh process.
2. Stop if any contract hash, workflow state, Checkpoint, or source fingerprint is stale.
3. Follow `continuation.next_action`; do not infer a later stage from conversation history.
4. For source ingestion, reuse the recorded path, SHA-256, parser version, evidence IDs, and status.
   Never use `--force` merely because a different Agent is continuing the project.
5. If the Agent lacks a required local capability, state the limitation and use the existing
   Human-in-the-loop decision path. Do not generate a parallel incompatible artifact.

## Trial evidence

Record every end-to-end trial with `trial_metrics.py`. Include both time saved and correction
counts. A successful handoff should normally record zero `cross_agent_reprocessed_files`; any
nonzero value needs an explanation in the trial notes.

The framework-neutral contract does not by itself make an Agent a supported adapter. AC-11 remains
open until a named second Agent has an adapter and passes an actual same-directory continuation
test.
