"""Evidence ingestion and cross-Agent reuse tests mapped to AC-04 and AC-13."""

from pathlib import Path

from fixture_builders import write_docx, write_pdf, write_xlsx
from report_harness.ingestion import ingest_project_sources
from report_harness.io import read_jsonl, write_jsonl
from report_harness.ocr import record_ocr_decision
from report_harness.project import (
    default_project_config,
    scaffold_project,
    validate_project,
)
from report_harness.workflow import WorkflowStore


def create_ingestion_project(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    scaffold_project(
        project,
        default_project_config(
            "m2-demo",
            "M2 synthetic demo",
            "Synthetic client",
            "2025-01-01",
            "2025-12-31",
        ),
    )
    store = WorkflowStore(project)
    store.transition("awaiting_data_consent")
    store.set_checkpoint("data_consent", "approved", approved_by="test-reviewer")
    store.transition("awaiting_spec_confirmation")
    store.set_checkpoint("project_spec", "approved", approved_by="test-reviewer")
    store.transition("awaiting_standard_confirmation")
    store.set_checkpoint("standards", "approved", approved_by="test-reviewer")
    store.transition("ingesting_sources")
    return project


def test_ingestion_writes_traceable_evidence_and_reuses_unchanged_files(tmp_path: Path):
    project = create_ingestion_project(tmp_path)
    write_docx(project / "sources/client/policy.docx")
    write_pdf(project / "sources/client/climate.pdf")
    write_xlsx(project / "sources/client/metrics.xlsx")

    first = ingest_project_sources(project)
    first_manifest = read_jsonl(project / "state/source_manifest.jsonl")
    first_evidence = read_jsonl(project / "state/evidence.jsonl")
    second = ingest_project_sources(project)
    second_manifest = read_jsonl(project / "state/source_manifest.jsonl")
    second_evidence = read_jsonl(project / "state/evidence.jsonl")

    assert first["valid"] is True
    assert first["parsed"] == 3
    assert first["workflow_state"] == "building_requirement_union"
    assert second["reused"] == 3
    assert second["parsed"] == 0
    assert [item["parsed_at"] for item in second_manifest] == [
        item["parsed_at"] for item in first_manifest
    ]
    assert second_evidence == first_evidence
    assert {item["source_type"] for item in first_evidence} == {"word", "pdf", "excel"}
    energy = next(item for item in first_evidence if "42 MWh" in item["excerpt"])
    assert energy["period"] == "2025"
    assert energy["unit"] == "MWh"
    assert validate_project(project) == []


def test_changed_file_replaces_only_its_prior_evidence(tmp_path: Path):
    project = create_ingestion_project(tmp_path)
    word = project / "sources/client/policy.docx"
    sheet = project / "sources/client/metrics.xlsx"
    write_docx(word)
    write_xlsx(sheet)
    ingest_project_sources(project)
    before = read_jsonl(project / "state/evidence.jsonl")
    excel_before = [item for item in before if item["source_type"] == "excel"]

    write_docx(word, body_text="2025 energy use was 55 MWh")
    result = ingest_project_sources(project)
    after = read_jsonl(project / "state/evidence.jsonl")

    assert result["parsed"] == 1
    assert result["reused"] == 1
    assert [item for item in after if item["source_type"] == "excel"] == excel_before
    assert any("55 MWh" in item["excerpt"] for item in after)
    assert not any("42 MWh" in item["excerpt"] for item in after)


def test_removed_source_removes_stale_manifest_and_evidence_records(tmp_path: Path):
    project = create_ingestion_project(tmp_path)
    word = project / "sources/client/policy.docx"
    sheet = project / "sources/client/metrics.xlsx"
    write_docx(word)
    write_xlsx(sheet)
    ingest_project_sources(project)

    word.unlink()
    result = ingest_project_sources(project)
    manifest = read_jsonl(project / "state/source_manifest.jsonl")
    evidence = read_jsonl(project / "state/evidence.jsonl")

    assert result["reused"] == 1
    assert [item["source_file"] for item in manifest] == ["sources/client/metrics.xlsx"]
    assert {item["source_type"] for item in evidence} == {"excel"}


def test_scanned_pdf_blocks_stage_and_is_reused_without_false_parse_claim(tmp_path: Path):
    project = create_ingestion_project(tmp_path)
    write_pdf(project / "sources/client/scan.pdf", text=None)

    first = ingest_project_sources(project)
    second = ingest_project_sources(project)
    manifest = read_jsonl(project / "state/source_manifest.jsonl")
    workflow = WorkflowStore(project).load()

    assert first["valid"] is False
    assert first["blocked"] == 1
    assert second["reused"] == 1
    assert manifest[0]["status"] == "needs_ocr"
    assert manifest[0]["evidence_ids"] == []
    assert workflow["workflow_state"] == "ingesting_sources"
    assert workflow["checkpoints"]["evidence"]["status"] == "blocked"


def test_user_can_persist_noncritical_ocr_skip_and_continue(tmp_path: Path):
    project = create_ingestion_project(tmp_path)
    write_pdf(project / "sources/client/scan.pdf", text=None)
    ingest_project_sources(project)

    decision = record_ocr_decision(
        project,
        "sources/client/scan.pdf",
        "skip_as_gap",
        decided_by="consultant",
        criticality="noncritical",
        notes="Ancillary source; retain as an explicit evidence gap.",
    )
    result = ingest_project_sources(project)

    assert decision["decision"] == "skip_as_gap"
    assert result["valid"] is True
    assert read_jsonl(project / "state/source_manifest.jsonl")[0]["status"] == "skipped_by_user"


def test_selected_ocr_tool_remains_blocked_until_ocr_output_exists(tmp_path: Path):
    project = create_ingestion_project(tmp_path)
    write_pdf(project / "sources/client/scan.pdf", text=None)
    ingest_project_sources(project)

    record_ocr_decision(
        project,
        "sources/client/scan.pdf",
        "run_local_ocr",
        decided_by="consultant",
        criticality="critical",
    )
    result = ingest_project_sources(project)

    assert result["valid"] is False
    assert read_jsonl(project / "state/source_manifest.jsonl")[0]["status"] == (
        "awaiting_ocr_action"
    )


def test_changed_ocr_decision_replaces_the_reused_manifest_status(tmp_path: Path):
    project = create_ingestion_project(tmp_path)
    write_pdf(project / "sources/client/scan.pdf", text=None)
    ingest_project_sources(project)
    record_ocr_decision(
        project,
        "./sources/client/scan.pdf",
        "run_local_ocr",
        decided_by="consultant",
        criticality="critical",
    )
    ingest_project_sources(project)

    record_ocr_decision(
        project,
        "sources/client/scan.pdf",
        "skip_as_gap",
        decided_by="consultant",
        criticality="noncritical",
    )
    result = ingest_project_sources(project)
    manifest = read_jsonl(project / "state/source_manifest.jsonl")

    assert result["valid"] is True
    assert result["parsed"] == 1
    assert manifest[0]["status"] == "skipped_by_user"
    assert manifest[0]["ocr_decision"] == "skip_as_gap"


def test_project_validation_rejects_corrupted_ocr_decisions(tmp_path: Path):
    project = create_ingestion_project(tmp_path)
    write_jsonl(
        project / "state/ocr_decisions.jsonl",
        [
            {
                "source_file": "../../outside.pdf",
                "source_hash": "invalid",
                "decision": "skip_as_gap",
                "criticality": "critical",
                "decided_by": "",
                "decided_at": "",
                "notes": None,
            }
        ],
    )

    errors = validate_project(project)

    assert any("must be a PDF under a source root" in error for error in errors)
    assert any("critical source cannot be skipped" in error for error in errors)


def test_ingestion_does_not_advance_an_empty_project(tmp_path: Path):
    project = create_ingestion_project(tmp_path)

    result = ingest_project_sources(project)

    assert result["valid"] is False
    assert result["supported"] == 0
    assert result["blocked"] == 1
    assert WorkflowStore(project).load()["workflow_state"] == "ingesting_sources"


def test_project_validation_cross_checks_manifest_and_evidence(tmp_path: Path):
    project = create_ingestion_project(tmp_path)
    write_xlsx(project / "sources/client/metrics.xlsx")
    ingest_project_sources(project)
    evidence_path = project / "state/evidence.jsonl"
    evidence = read_jsonl(evidence_path)
    evidence[0]["classification"] = "peer_reference"
    write_jsonl(evidence_path, evidence)

    errors = validate_project(project)

    assert any("classification: does not match the manifest" in error for error in errors)
