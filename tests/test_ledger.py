"""Ledger and clean-export tests mapped to FR-14, AC-06, AC-10, and AC-26."""

from copy import deepcopy

from report_harness.ledger import preflight_clean_export, validate_ledger


def valid_record():
    return {
        "ledger_id": "SIM-LEDGER-001",
        "unified_disclosure": {
            "unified_id": "SIM-UNI-001",
            "title": "模拟范围",
            "description": "说明模拟项目范围",
            "requirement_ids": ["SIM-REQ-001"],
            "review_status": "draft",
            "mapping_notes": "仅用于结构测试",
        },
        "requirements": [
            {
                "requirement_id": "SIM-REQ-001",
                "standard_id": "simulated-standard-a",
                "version_id": "fixture-1",
                "clause_id": "SIM-A-1",
                "original_text": "模拟条款",
                "check_text": "说明模拟范围",
                "requirement_level": "custom",
                "conditions": [],
                "review_status": "draft",
            }
        ],
        "evidence": [
            {
                "evidence_id": "SIM-EV-001",
                "source_file": "sources/client/simulated.docx",
                "source_hash": "hash",
                "source_type": "word",
                "locator": {"paragraph": 1},
                "excerpt": "模拟证据",
                "period": "2025",
                "unit": None,
                "classification": "client_evidence",
            }
        ],
        "content": [
            {
                "content_id": "SIM-CONT-001",
                "section_id": "SIM-SEC-001",
                "text": "模拟内容",
                "content_type": "confirmed_fact",
                "unified_ids": ["SIM-UNI-001"],
                "evidence_ids": ["SIM-EV-001"],
                "review_status": "accepted",
                "last_modified_by": "human",
                "confirmation_note": None,
            }
        ],
        "assessments": [
            {
                "assessment_id": "SIM-ASMT-001",
                "requirement_id": "SIM-REQ-001",
                "response_status": "fully_addressed",
                "content_ids": ["SIM-CONT-001"],
                "evidence_ids": ["SIM-EV-001"],
                "rationale": "模拟理由",
                "missing_information": None,
                "improvement_suggestion": None,
                "confidence": "high",
                "confidence_reason": "存在模拟证据",
                "review_status": "accepted",
            }
        ],
        "review_status": "accepted",
    }


def test_valid_ledger_resolves_all_references():
    assert validate_ledger([valid_record()]) == []
    assert preflight_clean_export([valid_record()]) == []


def test_ledger_reports_unknown_evidence_reference():
    record = valid_record()
    record["content"][0]["evidence_ids"] = ["SIM-EV-MISSING"]
    errors = validate_ledger([record])
    assert any("unknown references" in error for error in errors)


def test_clean_export_blocks_unconfirmed_suggestion():
    record = deepcopy(valid_record())
    content = record["content"][0]
    content["content_type"] = "suggested_text"
    content["review_status"] = "unreviewed"
    content["evidence_ids"] = []
    blockers = preflight_clean_export([record])
    assert blockers == [
        {
            "content_id": "SIM-CONT-001",
            "section_id": "SIM-SEC-001",
            "reason": "suggested_text has not been accepted or edited by a reviewer",
        }
    ]


def test_clean_export_blocks_unreviewed_confirmed_fact():
    record = deepcopy(valid_record())
    record["content"][0]["review_status"] = "unreviewed"

    blockers = preflight_clean_export([record])

    assert blockers[0]["reason"] == ("confirmed_fact has not been accepted or edited by a reviewer")


def test_human_confirmed_suggestion_can_pass_content_gate():
    record = deepcopy(valid_record())
    content = record["content"][0]
    content["content_type"] = "suggested_text"
    content["review_status"] = "edited"
    content["evidence_ids"] = []
    content["confirmation_note"] = "顾问已核实并改写"
    assert preflight_clean_export([record]) == []


def test_ledger_rejects_peer_evidence_in_customer_content_and_standard_assessment():
    record = deepcopy(valid_record())
    record["evidence"][0]["classification"] = "peer_reference"

    errors = validate_ledger([record])

    assert any("report content requires client_evidence" in error for error in errors)
    assert any("standards assessment requires client_evidence" in error for error in errors)


def test_ledger_rejects_duplicate_requirement_assessments_and_invalid_row_status():
    record = deepcopy(valid_record())
    duplicate = deepcopy(record["assessments"][0])
    duplicate["assessment_id"] = "SIM-ASMT-002"
    record["assessments"].append(duplicate)
    record["review_status"] = "draft"

    errors = validate_ledger([record])

    assert any("assessments: requirement IDs must be unique" in error for error in errors)
    assert any("review_status: invalid review status" in error for error in errors)
