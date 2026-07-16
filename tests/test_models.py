"""Core model tests mapped to FR-05, FR-06, FR-09, and AC-03 through AC-07."""

import pytest
from report_harness.errors import HarnessError
from report_harness.models import (
    Adaptation,
    Assessment,
    DisclosureContent,
    Evidence,
    EvidenceGap,
    EvidenceLink,
    Requirement,
    RequirementMapping,
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
        RequirementMapping(
            mapping_id="SIM-MAP-001",
            requirement_id="SIM-REQ-001",
            mapping_type="unique",
            difference_notes="模拟要求仅出现在准则 A",
            review_status="unreviewed",
            mapped_by="agent",
        ),
        EvidenceLink(
            link_id="SIM-LINK-001",
            evidence_id="SIM-EV-001",
            requirement_ids=["SIM-REQ-001"],
            relationship="direct",
            review_status="unreviewed",
        ),
        EvidenceGap(
            gap_id="SIM-GAP-001",
            requirement_id="SIM-REQ-001",
            reason="模拟缺口",
            criticality="needs_confirmation",
            review_status="unreviewed",
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
        Adaptation(
            adaptation_id="SIM-ADAPT-001",
            target_standard_id="simulated-standard-a",
            target_version_id="fixture-1",
            source_content_id="SIM-CONT-001",
            action="keep",
            reason="模拟母版内容直接适用。",
            target_section_id="SIM-SEC-001",
            content_type="confirmed_fact",
            review_status="unreviewed",
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


def test_assessment_uses_prd_needs_confirmation_status():
    model = Assessment(
        assessment_id="SIM-ASMT-002",
        requirement_id="SIM-REQ-001",
        response_status="needs_confirmation",
        rationale="模拟证据冲突。",
        confidence="low",
        confidence_reason="两份材料存在差异。",
        review_status="unreviewed",
    )

    model.validate()


def test_adaptation_cannot_hide_rewritten_text_behind_keep():
    model = Adaptation(
        adaptation_id="SIM-ADAPT-002",
        target_standard_id="simulated-standard-a",
        target_version_id="fixture-1",
        source_content_id="SIM-CONT-001",
        action="keep",
        reason="模拟保留。",
        target_section_id="SIM-SEC-001",
        adapted_text="未经声明的改写文本",
        content_type="confirmed_fact",
        review_status="unreviewed",
    )

    with pytest.raises(HarnessError, match="must reuse master text"):
        model.validate()
