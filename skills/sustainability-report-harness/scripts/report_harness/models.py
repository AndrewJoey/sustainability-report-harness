"""Framework-neutral data models from PRD section 9."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, ClassVar, TypeVar

from .errors import HarnessError, require

T = TypeVar("T", bound="SerializableModel")


class SerializableModel:
    """Dataclass serialization and basic construction contract."""

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key, value in result.items():
            if isinstance(value, date):
                result[key] = value.isoformat()
        return result

    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T:
        try:
            instance = cls(**data)
        except (TypeError, ValueError) as exc:
            raise HarnessError("INVALID_MODEL", str(exc), cls.__name__) from exc
        instance.validate()
        return instance

    def validate(self) -> None:
        raise NotImplementedError


@dataclass(slots=True)
class StandardVersion(SerializableModel):
    standard_id: str
    name: str
    version_id: str
    effective_from: str
    source_uri: str
    review_status: str
    content_hash: str
    effective_to: str | None = None

    REVIEW_STATUSES: ClassVar[set[str]] = {"draft", "reviewed", "published"}

    def validate(self) -> None:
        _require_nonempty(self, "standard_id", "name", "version_id", "source_uri", "content_hash")
        _require_date(self.effective_from, "effective_from")
        if self.effective_to is not None:
            _require_date(self.effective_to, "effective_to")
            require(
                date.fromisoformat(self.effective_to) >= date.fromisoformat(self.effective_from),
                "INVALID_DATE_RANGE",
                "effective_to must be on or after effective_from",
                "effective_to",
            )
        require(
            self.review_status in self.REVIEW_STATUSES,
            "INVALID_ENUM",
            f"review_status must be one of {sorted(self.REVIEW_STATUSES)}",
            "review_status",
        )


@dataclass(slots=True)
class Requirement(SerializableModel):
    requirement_id: str
    standard_id: str
    version_id: str
    clause_id: str
    original_text: str
    check_text: str
    requirement_level: str
    review_status: str
    conditions: list[dict[str, Any]] = field(default_factory=list)

    REQUIREMENT_LEVELS: ClassVar[set[str]] = {"mandatory", "explanatory", "recommended", "custom"}
    REVIEW_STATUSES: ClassVar[set[str]] = {"draft", "reviewed", "published"}

    def validate(self) -> None:
        _require_nonempty(
            self,
            "requirement_id",
            "standard_id",
            "version_id",
            "clause_id",
            "original_text",
            "check_text",
        )
        require(
            self.requirement_level in self.REQUIREMENT_LEVELS,
            "INVALID_ENUM",
            f"requirement_level must be one of {sorted(self.REQUIREMENT_LEVELS)}",
            "requirement_level",
        )
        require(
            self.review_status in self.REVIEW_STATUSES,
            "INVALID_ENUM",
            f"review_status must be one of {sorted(self.REVIEW_STATUSES)}",
            "review_status",
        )


@dataclass(slots=True)
class UnifiedDisclosure(SerializableModel):
    unified_id: str
    title: str
    description: str
    requirement_ids: list[str]
    review_status: str
    mapping_notes: str | None = None

    REVIEW_STATUSES: ClassVar[set[str]] = {"draft", "reviewed", "published"}

    def validate(self) -> None:
        _require_nonempty(self, "unified_id", "title", "description")
        require(bool(self.requirement_ids), "MISSING_VALUE", "requirement_ids cannot be empty")
        _require_unique(self.requirement_ids, "requirement_ids")
        require(
            self.review_status in self.REVIEW_STATUSES,
            "INVALID_ENUM",
            f"review_status must be one of {sorted(self.REVIEW_STATUSES)}",
            "review_status",
        )


@dataclass(slots=True)
class RequirementMapping(SerializableModel):
    mapping_id: str
    requirement_id: str
    mapping_type: str
    difference_notes: str
    review_status: str
    mapped_by: str
    reviewed_by: str | None = None
    review_notes: str | None = None

    MAPPING_TYPES: ClassVar[set[str]] = {
        "equivalent",
        "overlapping",
        "broader_than",
        "narrower_than",
        "unique",
    }
    REVIEW_STATUSES: ClassVar[set[str]] = {
        "unreviewed",
        "accepted",
        "rejected",
        "edited",
    }
    MAPPERS: ClassVar[set[str]] = {"agent", "human"}

    def validate(self) -> None:
        _require_nonempty(self, "mapping_id", "requirement_id", "difference_notes")
        _require_enum(self.mapping_type, self.MAPPING_TYPES, "mapping_type")
        _require_enum(self.review_status, self.REVIEW_STATUSES, "review_status")
        _require_enum(self.mapped_by, self.MAPPERS, "mapped_by")
        if self.mapped_by == "agent":
            require(
                self.review_status == "unreviewed" or bool(self.reviewed_by),
                "REVIEWER_REQUIRED",
                "Agent mappings must remain unreviewed until a reviewer is recorded",
                "reviewed_by",
            )
        if self.review_status != "unreviewed":
            require(
                isinstance(self.reviewed_by, str) and bool(self.reviewed_by.strip()),
                "REVIEWER_REQUIRED",
                "reviewed_by is required after review",
                "reviewed_by",
            )


@dataclass(slots=True)
class EvidenceLink(SerializableModel):
    link_id: str
    evidence_id: str
    requirement_ids: list[str]
    relationship: str
    review_status: str
    reviewed_by: str | None = None
    notes: str | None = None

    RELATIONSHIPS: ClassVar[set[str]] = {"direct", "supporting", "contradicting"}
    REVIEW_STATUSES: ClassVar[set[str]] = {
        "unreviewed",
        "accepted",
        "rejected",
        "edited",
    }

    def validate(self) -> None:
        _require_nonempty(self, "link_id", "evidence_id")
        require(bool(self.requirement_ids), "MISSING_VALUE", "requirement_ids cannot be empty")
        _require_unique(self.requirement_ids, "requirement_ids")
        _require_enum(self.relationship, self.RELATIONSHIPS, "relationship")
        _require_enum(self.review_status, self.REVIEW_STATUSES, "review_status")
        if self.review_status != "unreviewed":
            require(
                isinstance(self.reviewed_by, str) and bool(self.reviewed_by.strip()),
                "REVIEWER_REQUIRED",
                "reviewed_by is required after review",
                "reviewed_by",
            )
        if self.relationship == "contradicting":
            require(
                isinstance(self.notes, str) and bool(self.notes.strip()),
                "MISSING_VALUE",
                "Contradicting evidence requires notes",
                "notes",
            )


@dataclass(slots=True)
class EvidenceGap(SerializableModel):
    gap_id: str
    requirement_id: str
    reason: str
    criticality: str
    review_status: str
    reviewed_by: str | None = None
    notes: str | None = None

    CRITICALITIES: ClassVar[set[str]] = {"needs_confirmation", "critical", "noncritical"}
    REVIEW_STATUSES: ClassVar[set[str]] = {
        "unreviewed",
        "accepted",
        "rejected",
        "edited",
    }

    def validate(self) -> None:
        _require_nonempty(self, "gap_id", "requirement_id", "reason")
        _require_enum(self.criticality, self.CRITICALITIES, "criticality")
        _require_enum(self.review_status, self.REVIEW_STATUSES, "review_status")
        if self.review_status != "unreviewed":
            require(
                isinstance(self.reviewed_by, str) and bool(self.reviewed_by.strip()),
                "REVIEWER_REQUIRED",
                "reviewed_by is required after review",
                "reviewed_by",
            )


@dataclass(slots=True)
class Evidence(SerializableModel):
    evidence_id: str
    source_file: str
    source_hash: str
    source_type: str
    locator: dict[str, Any]
    excerpt: str
    classification: str
    period: str | None = None
    unit: str | None = None

    SOURCE_TYPES: ClassVar[set[str]] = {"word", "pdf", "excel"}
    CLASSIFICATIONS: ClassVar[set[str]] = {"client_evidence", "peer_reference"}

    def validate(self) -> None:
        _require_nonempty(self, "evidence_id", "source_file", "source_hash", "excerpt")
        require(bool(self.locator), "MISSING_VALUE", "locator cannot be empty", "locator")
        require(
            self.source_type in self.SOURCE_TYPES,
            "INVALID_ENUM",
            f"source_type must be one of {sorted(self.SOURCE_TYPES)}",
            "source_type",
        )
        require(
            self.classification in self.CLASSIFICATIONS,
            "INVALID_ENUM",
            f"classification must be one of {sorted(self.CLASSIFICATIONS)}",
            "classification",
        )


@dataclass(slots=True)
class DisclosureContent(SerializableModel):
    content_id: str
    section_id: str
    text: str
    content_type: str
    unified_ids: list[str]
    review_status: str
    last_modified_by: str
    evidence_ids: list[str] = field(default_factory=list)
    confirmation_note: str | None = None

    CONTENT_TYPES: ClassVar[set[str]] = {
        "confirmed_fact",
        "inference",
        "suggested_text",
        "information_gap",
    }
    REVIEW_STATUSES: ClassVar[set[str]] = {"unreviewed", "accepted", "rejected", "edited"}
    MODIFIERS: ClassVar[set[str]] = {"agent", "human"}

    def validate(self) -> None:
        _require_nonempty(self, "content_id", "section_id", "text")
        require(bool(self.unified_ids), "MISSING_VALUE", "unified_ids cannot be empty")
        _require_unique(self.unified_ids, "unified_ids")
        _require_unique(self.evidence_ids, "evidence_ids")
        _require_enum(self.content_type, self.CONTENT_TYPES, "content_type")
        _require_enum(self.review_status, self.REVIEW_STATUSES, "review_status")
        _require_enum(self.last_modified_by, self.MODIFIERS, "last_modified_by")


@dataclass(slots=True)
class Assessment(SerializableModel):
    assessment_id: str
    requirement_id: str
    response_status: str
    rationale: str
    confidence: str
    confidence_reason: str
    review_status: str
    content_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    missing_information: str | None = None
    improvement_suggestion: str | None = None
    human_notes: str | None = None

    RESPONSE_STATUSES: ClassVar[set[str]] = {
        "fully_addressed",
        "partially_addressed",
        "not_addressed",
        "not_applicable",
        "needs_confirmation",
    }
    CONFIDENCE_LEVELS: ClassVar[set[str]] = {"high", "medium", "low"}
    REVIEW_STATUSES: ClassVar[set[str]] = {"unreviewed", "accepted", "rejected", "edited"}

    def validate(self) -> None:
        _require_nonempty(
            self,
            "assessment_id",
            "requirement_id",
            "rationale",
            "confidence_reason",
        )
        _require_unique(self.content_ids, "content_ids")
        _require_unique(self.evidence_ids, "evidence_ids")
        _require_enum(self.response_status, self.RESPONSE_STATUSES, "response_status")
        _require_enum(self.confidence, self.CONFIDENCE_LEVELS, "confidence")
        _require_enum(self.review_status, self.REVIEW_STATUSES, "review_status")
        if self.response_status == "not_applicable" and self.review_status in {
            "accepted",
            "edited",
        }:
            require(
                isinstance(self.human_notes, str) and bool(self.human_notes.strip()),
                "HUMAN_REASON_REQUIRED",
                "Accepted not_applicable assessments require human_notes",
                "human_notes",
            )


@dataclass(slots=True)
class PeerAssessment(SerializableModel):
    peer_assessment_id: str
    requirement_id: str
    peer_position: str
    rationale: str
    review_status: str
    evidence_ids: list[str] = field(default_factory=list)
    reviewed_by: str | None = None
    human_notes: str | None = None

    PEER_POSITIONS: ClassVar[set[str]] = {
        "leading",
        "comparable",
        "lagging",
        "not_assessed",
    }
    REVIEW_STATUSES: ClassVar[set[str]] = {"unreviewed", "accepted", "rejected", "edited"}

    def validate(self) -> None:
        _require_nonempty(self, "peer_assessment_id", "requirement_id", "rationale")
        _require_unique(self.evidence_ids, "evidence_ids")
        _require_enum(self.peer_position, self.PEER_POSITIONS, "peer_position")
        _require_enum(self.review_status, self.REVIEW_STATUSES, "review_status")
        if self.review_status != "unreviewed":
            require(
                isinstance(self.reviewed_by, str) and bool(self.reviewed_by.strip()),
                "REVIEWER_REQUIRED",
                "reviewed_by is required after review",
                "reviewed_by",
            )
        if self.peer_position != "not_assessed":
            require(
                bool(self.evidence_ids),
                "PEER_EVIDENCE_REQUIRED",
                "A peer position other than not_assessed requires peer evidence",
                "evidence_ids",
            )


@dataclass(slots=True)
class Adaptation(SerializableModel):
    """One reviewed transformation from a master content block to a target standard."""

    adaptation_id: str
    target_standard_id: str
    target_version_id: str
    source_content_id: str
    action: str
    reason: str
    content_type: str
    review_status: str
    target_section_id: str | None = None
    adapted_text: str | None = None
    supplemental_evidence_ids: list[str] = field(default_factory=list)
    reviewed_by: str | None = None
    human_notes: str | None = None

    ACTIONS: ClassVar[set[str]] = {
        "keep",
        "condense",
        "reorganize",
        "supplement",
        "omit",
    }
    CONTENT_TYPES: ClassVar[set[str]] = DisclosureContent.CONTENT_TYPES
    REVIEW_STATUSES: ClassVar[set[str]] = DisclosureContent.REVIEW_STATUSES

    def validate(self) -> None:
        _require_nonempty(
            self,
            "adaptation_id",
            "target_standard_id",
            "target_version_id",
            "source_content_id",
            "reason",
        )
        _require_enum(self.action, self.ACTIONS, "action")
        _require_enum(self.content_type, self.CONTENT_TYPES, "content_type")
        _require_enum(self.review_status, self.REVIEW_STATUSES, "review_status")
        _require_unique(self.supplemental_evidence_ids, "supplemental_evidence_ids")
        if self.action == "omit":
            require(
                self.target_section_id is None and self.adapted_text is None,
                "INVALID_ADAPTATION",
                "omit cannot have a target section or adapted text",
                "action",
            )
        else:
            require(
                isinstance(self.target_section_id, str) and bool(self.target_section_id.strip()),
                "MISSING_VALUE",
                "A non-omit adaptation requires target_section_id",
                "target_section_id",
            )
        if self.action in {"condense", "supplement"}:
            require(
                isinstance(self.adapted_text, str) and bool(self.adapted_text.strip()),
                "MISSING_VALUE",
                f"{self.action} requires adapted_text",
                "adapted_text",
            )
        else:
            require(
                self.adapted_text is None,
                "INVALID_ADAPTATION",
                f"{self.action} must reuse master text and cannot include adapted_text",
                "adapted_text",
            )
        if self.review_status != "unreviewed":
            require(
                isinstance(self.reviewed_by, str) and bool(self.reviewed_by.strip()),
                "REVIEWER_REQUIRED",
                "reviewed_by is required after adaptation review",
                "reviewed_by",
            )


def _require_nonempty(model: object, *fields: str) -> None:
    for name in fields:
        value = getattr(model, name)
        require(
            isinstance(value, str) and bool(value.strip()),
            "MISSING_VALUE",
            "Value is required",
            name,
        )


def _require_unique(values: list[str], path: str) -> None:
    require(len(values) == len(set(values)), "DUPLICATE_ID", "Values must be unique", path)


def _require_enum(value: str, allowed: set[str], path: str) -> None:
    require(value in allowed, "INVALID_ENUM", f"Value must be one of {sorted(allowed)}", path)


def _require_date(value: str, path: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise HarnessError("INVALID_DATE", "Expected ISO date YYYY-MM-DD", path) from exc
