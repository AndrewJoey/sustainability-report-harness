"""Operational logging tests mapped to M1 security and recoverability requirements."""

import json
from pathlib import Path

import pytest
from report_harness.audit import append_event
from report_harness.errors import HarnessError


def test_audit_log_is_jsonl_without_customer_text(tmp_path: Path):
    append_event(
        tmp_path,
        project_id="demo-project",
        event="workflow.transitioned",
        message="Workflow advanced",
        details={"from_state": "created", "to_state": "awaiting_data_consent"},
    )
    record = json.loads((tmp_path / "logs" / "harness.jsonl").read_text(encoding="utf-8"))
    assert record["project_id"] == "demo-project"
    assert record["details"]["to_state"] == "awaiting_data_consent"


def test_audit_log_rejects_customer_content_fields(tmp_path: Path):
    with pytest.raises(HarnessError, match="UNSAFE_LOG_FIELD"):
        append_event(
            tmp_path,
            project_id="demo-project",
            event="unsafe",
            message="Unsafe event",
            details={"customer_text": "confidential"},
        )
