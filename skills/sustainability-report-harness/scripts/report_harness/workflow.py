"""Persistent workflow and hard Checkpoint enforcement."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import HarnessError
from .io import read_json, write_json

WORKFLOW_STATES = {
    "created",
    "awaiting_data_consent",
    "awaiting_spec_confirmation",
    "awaiting_standard_confirmation",
    "ingesting_sources",
    "building_requirement_union",
    "awaiting_evidence_confirmation",
    "generating_outline",
    "awaiting_outline_confirmation",
    "generating_anchor",
    "awaiting_anchor_confirmation",
    "generating_master",
    "reviewing_master",
    "adapting_standard",
    "awaiting_export_confirmation",
    "ready_for_export",
    "blocked",
}

CHECKPOINTS = (
    "data_consent",
    "project_spec",
    "standards",
    "evidence",
    "outline",
    "anchor",
    "master",
    "export",
)
CHECKPOINT_STATUSES = {
    "pending",
    "ready",
    "awaiting_confirmation",
    "approved",
    "changes_requested",
    "blocked",
}
CHECKPOINT_DEPENDENCIES = {
    "project_spec": "data_consent",
    "standards": "project_spec",
    "evidence": "standards",
    "outline": "evidence",
    "anchor": "outline",
    "master": "anchor",
    "export": "master",
}

TRANSITIONS: dict[str, set[str]] = {
    "created": {"awaiting_data_consent"},
    "awaiting_data_consent": {"awaiting_spec_confirmation"},
    "awaiting_spec_confirmation": {"awaiting_standard_confirmation"},
    "awaiting_standard_confirmation": {"ingesting_sources"},
    "ingesting_sources": {"building_requirement_union"},
    "building_requirement_union": {"awaiting_evidence_confirmation"},
    "awaiting_evidence_confirmation": {"generating_outline"},
    "generating_outline": {"awaiting_outline_confirmation"},
    "awaiting_outline_confirmation": {"generating_anchor"},
    "generating_anchor": {"awaiting_anchor_confirmation"},
    "awaiting_anchor_confirmation": {"generating_master"},
    "generating_master": {"reviewing_master"},
    "reviewing_master": {"adapting_standard", "awaiting_export_confirmation"},
    "adapting_standard": {"awaiting_export_confirmation"},
    "awaiting_export_confirmation": {"ready_for_export"},
    "ready_for_export": set(),
    "blocked": set(),
}

TRANSITION_REQUIREMENTS = {
    ("awaiting_data_consent", "awaiting_spec_confirmation"): "data_consent",
    ("awaiting_spec_confirmation", "awaiting_standard_confirmation"): "project_spec",
    ("awaiting_standard_confirmation", "ingesting_sources"): "standards",
    ("awaiting_evidence_confirmation", "generating_outline"): "evidence",
    ("awaiting_outline_confirmation", "generating_anchor"): "outline",
    ("awaiting_anchor_confirmation", "generating_master"): "anchor",
    ("reviewing_master", "adapting_standard"): "master",
    ("reviewing_master", "awaiting_export_confirmation"): "master",
    ("awaiting_export_confirmation", "ready_for_export"): "export",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_workflow() -> dict[str, Any]:
    now = utc_now()
    return {
        "schema_version": "1.0.0",
        "workflow_state": "created",
        "previous_state": None,
        "updated_at": now,
        "checkpoints": {
            name: {
                "status": "pending",
                "updated_at": now,
                "approved_by": None,
                "artifacts": [],
                "notes": None,
            }
            for name in CHECKPOINTS
        },
    }


class WorkflowStore:
    def __init__(self, project_dir: Path):
        self.path = project_dir / "state" / "workflow.json"

    def initialize(self) -> dict[str, Any]:
        workflow = new_workflow()
        write_json(self.path, workflow)
        return workflow

    def load(self) -> dict[str, Any]:
        workflow = read_json(self.path)
        errors = validate_workflow(workflow)
        if errors:
            raise HarnessError(
                "INVALID_WORKFLOW", "Workflow state is invalid", details={"errors": errors}
            )
        return workflow

    def transition(self, next_state: str) -> dict[str, Any]:
        workflow = self.load()
        current = workflow["workflow_state"]
        if next_state == "blocked":
            workflow["previous_state"] = current
        elif next_state not in TRANSITIONS[current]:
            raise HarnessError(
                "INVALID_TRANSITION",
                f"Cannot transition from {current} to {next_state}",
            )
        required = TRANSITION_REQUIREMENTS.get((current, next_state))
        if required and workflow["checkpoints"][required]["status"] != "approved":
            raise HarnessError(
                "CHECKPOINT_REQUIRED",
                f"Checkpoint {required} must be approved before entering {next_state}",
                required,
            )
        workflow["workflow_state"] = next_state
        workflow["updated_at"] = utc_now()
        write_json(self.path, workflow)
        return workflow

    def resume(self) -> dict[str, Any]:
        workflow = self.load()
        if workflow["workflow_state"] != "blocked" or not workflow.get("previous_state"):
            raise HarnessError("NOT_BLOCKED", "Workflow does not have a resumable blocked state")
        workflow["workflow_state"] = workflow["previous_state"]
        workflow["previous_state"] = None
        workflow["updated_at"] = utc_now()
        write_json(self.path, workflow)
        return workflow

    def set_checkpoint(
        self,
        name: str,
        status: str,
        *,
        approved_by: str | None = None,
        artifacts: list[str] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        workflow = self.load()
        if name not in CHECKPOINTS:
            raise HarnessError("UNKNOWN_CHECKPOINT", f"Unknown Checkpoint: {name}", name)
        if status not in CHECKPOINT_STATUSES:
            raise HarnessError(
                "INVALID_CHECKPOINT_STATUS", f"Unknown Checkpoint status: {status}", name
            )
        dependency = CHECKPOINT_DEPENDENCIES.get(name)
        if status == "approved" and dependency:
            if workflow["checkpoints"][dependency]["status"] != "approved":
                raise HarnessError(
                    "CHECKPOINT_REQUIRED",
                    f"Checkpoint {dependency} must be approved first",
                    dependency,
                )
        if status == "approved" and not approved_by:
            raise HarnessError("APPROVER_REQUIRED", "approved_by is required for approval", name)
        checkpoint = workflow["checkpoints"][name]
        checkpoint.update(
            {
                "status": status,
                "updated_at": utc_now(),
                "approved_by": approved_by if status == "approved" else None,
                "artifacts": artifacts or [],
                "notes": notes,
            }
        )
        workflow["updated_at"] = utc_now()
        write_json(self.path, workflow)
        return workflow


def validate_workflow(workflow: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(workflow, dict):
        return ["workflow: must be a JSON object"]
    state = workflow.get("workflow_state")
    if state not in WORKFLOW_STATES:
        errors.append(f"workflow_state: unknown state {state!r}")
    checkpoints = workflow.get("checkpoints")
    if not isinstance(checkpoints, dict):
        return errors + ["checkpoints: must be an object"]
    for name in CHECKPOINTS:
        checkpoint = checkpoints.get(name)
        if not isinstance(checkpoint, dict):
            errors.append(f"checkpoints.{name}: required object is missing")
            continue
        if checkpoint.get("status") not in CHECKPOINT_STATUSES:
            errors.append(f"checkpoints.{name}.status: invalid status")
        if not isinstance(checkpoint.get("updated_at"), str):
            errors.append(f"checkpoints.{name}.updated_at: string required")
        if not isinstance(checkpoint.get("artifacts"), list):
            errors.append(f"checkpoints.{name}.artifacts: list required")
        if checkpoint.get("status") == "approved" and not checkpoint.get("approved_by"):
            errors.append(f"checkpoints.{name}.approved_by: required when approved")
    for name, dependency in CHECKPOINT_DEPENDENCIES.items():
        if (
            isinstance(checkpoints.get(name), dict)
            and checkpoints[name].get("status") == "approved"
            and isinstance(checkpoints.get(dependency), dict)
            and checkpoints[dependency].get("status") != "approved"
        ):
            errors.append(f"checkpoints.{name}: dependency {dependency} is not approved")
    return errors
