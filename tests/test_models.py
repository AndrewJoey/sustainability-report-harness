"""Core model tests mapped to FR-05, FR-06, FR-09, and AC-03 through AC-07."""

import pytest
from report_harness.errors import HarnessError
from report_harness.models import (
    Assessment,
    DisclosureContent,
    Evidence,
    Requirement,
    StandardVersion,
    UnifiedDisclosure,
)


@pytest.mark.parametrize(
    "model",
    [
        StandardVersion(
            standard_id="simulated-standard-a",
            name="模拟准则 A",
            version_id="fixture-1",
            effective_from="2025-01-01",
            source_uri="urn:simulated:a",
            review_status="draft",
            content_hash="abc123",
        ),
        Requirement(
            requirement_id="SIM-REQ-001",
            standard_id="simulated-standard-a",
            version_id="fixture-1",
            clause_id="SIM-A-1",
            original_text="模拟条款",
            check_text="说明模拟范围",
            requirement_level="custom",
            review_status="draft",
        ),
        UnifiedDisclosure(
            unified_id="SIM-UNI-001",
            title="模拟范围",
            description="说明模拟项目范围",
            requirement_ids=["SIM-REQ-001"],
            review_status="draft",
        ),
        Evidence(
            evidence_id="SIM-EV-001",
            source_file="sources/client/simulated.docx",
            source_hash="hash",
            source_type="word",
            locator={"paragraph": 1},
            excerpt="模拟证据",
            classification="client_evidence",
        ),
        DisclosureContent(
            content_id="SIM-CONT-001",
            section_id="SIM-SEC-001",
            text="模拟内容",
            content_type="confirmed_fact",
            unified_ids=["SIM-UNI-001"],
            review_status="accepted",
            last_modified_by="human",
            evidence_ids=["SIM-EV-001"],
        ),
        Assessment(
            assessment_id="SIM-ASMT-001",
            requirement_id="SIM-REQ-001",
            response_status="fully_addressed",
            rationale="模拟理由",
            confidence="high",
            confidence_reason="存在模拟证据",
            review_status="accepted",
            content_ids=["SIM-CONT-001"],
            evidence_ids=["SIM-EV-001"],
        ),
    ],
)
def test_models_round_trip(model):
    model.validate()
    restored = type(model).from_dict(model.to_dict())
    assert restored == model


def test_model_rejects_invalid_enum():
    model = Evidence(
        evidence_id="SIM-EV-001",
        source_file="sources/client/simulated.docx",
        source_hash="hash",
        source_type="email",
        locator={"paragraph": 1},
        excerpt="模拟证据",
        classification="client_evidence",
    )
    with pytest.raises(HarnessError, match="INVALID_ENUM"):
        model.validate()
