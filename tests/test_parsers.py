"""Synthetic parser tests mapped to PRD stage 2 and AC-04."""

from pathlib import Path

from fixture_builders import write_docx, write_pdf, write_xlsx
from report_harness.parsers import parse_docx, parse_pdf, parse_xlsx


def test_docx_preserves_paragraph_heading_and_table_locations(tmp_path: Path):
    source = tmp_path / "evidence.docx"
    write_docx(source)

    result = parse_docx(source)

    assert result.status == "parsed"
    assert result.items[1].locator == {
        "kind": "paragraph",
        "paragraph_index": 2,
        "heading_path": ["Environment"],
    }
    assert result.items[-1].locator["table_index"] == 1
    assert result.items[-1].locator["row_index"] == 2
    assert result.items[-1].excerpt == "Water | 18 m3"


def test_pdf_preserves_page_and_text_block_location(tmp_path: Path):
    source = tmp_path / "evidence.pdf"
    write_pdf(source)

    result = parse_pdf(source)

    assert result.status == "parsed"
    assert result.items[0].locator == {"kind": "text_block", "page": 1, "block_index": 1}
    assert result.items[0].excerpt == "Climate target 2030"


def test_pdf_without_extractable_text_requires_ocr(tmp_path: Path):
    source = tmp_path / "scan.pdf"
    write_pdf(source, text=None)

    result = parse_pdf(source)

    assert result.status == "needs_ocr"
    assert result.items == []
    assert "OCR" in (result.message or "")


def test_xlsx_preserves_sheet_and_cell_range(tmp_path: Path):
    source = tmp_path / "metrics.xlsx"
    write_xlsx(source)

    result = parse_xlsx(source)

    assert result.status == "parsed"
    assert result.items[1].locator == {
        "kind": "cell_range",
        "sheet": "Metrics",
        "range": "A2:C2",
    }
    assert result.items[1].excerpt == "Emissions | 2025 | 12.5"


def test_xlsx_preserves_formula_and_cached_value(tmp_path: Path):
    source = tmp_path / "formula.xlsx"
    write_xlsx(source, with_formula=True)

    result = parse_xlsx(source)

    assert result.items[1].excerpt == "Emissions | 2025 | 4050"
    assert result.items[1].locator["formulas"] == {"C2": "B2*2"}
    assert result.items[1].locator["formula_status"] == "not_recalculated"


def test_xlsx_preserves_formula_without_a_cached_value(tmp_path: Path):
    source = tmp_path / "uncached-formula.xlsx"
    write_xlsx(source, with_formula=True, formula_has_cached_value=False)

    result = parse_xlsx(source)

    assert result.items[1].locator["formulas"] == {"C2": "B2*2"}
    assert result.items[1].locator["formula_status"] == "not_recalculated"
    assert "=B2*2" in result.items[1].excerpt


def test_empty_xlsx_is_not_claimed_as_parsed_evidence(tmp_path: Path):
    source = tmp_path / "empty.xlsx"
    write_xlsx(source, empty=True)

    result = parse_xlsx(source)

    assert result.status == "empty"
    assert result.items == []
