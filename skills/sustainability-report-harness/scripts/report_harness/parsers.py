"""Deterministic local parsers for M2 evidence sources."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader

from .errors import HarnessError

PARSER_VERSION = "m2.2"
MAX_EXCERPT_CHARS = 2_000

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


@dataclass(slots=True)
class ParsedItem:
    locator: dict[str, object]
    excerpt: str


@dataclass(slots=True)
class ParseResult:
    items: list[ParsedItem] = field(default_factory=list)
    status: str = "parsed"
    message: str | None = None


def parse_source(path: Path, source_type: str) -> ParseResult:
    try:
        if source_type == "word":
            return parse_docx(path)
        if source_type == "pdf":
            return parse_pdf(path)
        if source_type == "excel":
            return parse_xlsx(path)
    except HarnessError:
        raise
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise HarnessError("SOURCE_PARSE_FAILED", str(exc), str(path)) from exc
    raise HarnessError("UNSUPPORTED_SOURCE_TYPE", f"Unsupported source type: {source_type}")


def parse_docx(path: Path) -> ParseResult:
    """Extract paragraphs and table rows with auditable Word locations."""

    try:
        with zipfile.ZipFile(path) as package:
            document = ElementTree.fromstring(package.read("word/document.xml"))
    except KeyError as exc:
        raise HarnessError("INVALID_DOCX", "word/document.xml is missing", str(path)) from exc

    body = document.find(f"{{{WORD_NS}}}body")
    if body is None:
        raise HarnessError("INVALID_DOCX", "Word document body is missing", str(path))

    items: list[ParsedItem] = []
    heading_path: list[str] = []
    paragraph_index = 0
    table_index = 0
    for child in body:
        if child.tag == f"{{{WORD_NS}}}p":
            paragraph_index += 1
            text = _word_text(child)
            if not text:
                continue
            heading_level = _word_heading_level(child)
            if heading_level:
                heading_path = heading_path[: heading_level - 1]
                heading_path.append(text)
            items.append(
                ParsedItem(
                    locator={
                        "kind": "paragraph",
                        "paragraph_index": paragraph_index,
                        "heading_path": list(heading_path),
                    },
                    excerpt=_clip(text),
                )
            )
        elif child.tag == f"{{{WORD_NS}}}tbl":
            table_index += 1
            for row_index, row in enumerate(child.findall(f"{{{WORD_NS}}}tr"), start=1):
                cells = [_word_text(cell) for cell in row.findall(f"{{{WORD_NS}}}tc")]
                nonempty = [cell for cell in cells if cell]
                if not nonempty:
                    continue
                items.append(
                    ParsedItem(
                        locator={
                            "kind": "table_row",
                            "table_index": table_index,
                            "row_index": row_index,
                            "column_start": 1,
                            "column_end": len(cells),
                            "heading_path": list(heading_path),
                        },
                        excerpt=_clip(" | ".join(cells)),
                    )
                )
    if not items:
        return ParseResult(status="empty", message="No extractable Word content found")
    return ParseResult(items=items)


def parse_pdf(path: Path) -> ParseResult:
    """Extract text PDF pages; explicitly flag image-only/scanned PDFs."""

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # pypdf exposes several parser-specific exceptions
        raise HarnessError("INVALID_PDF", str(exc), str(path)) from exc
    if reader.is_encrypted:
        try:
            unlocked = reader.decrypt("")
        except Exception as exc:
            raise HarnessError("ENCRYPTED_PDF", "PDF requires a password", str(path)) from exc
        if not unlocked:
            raise HarnessError("ENCRYPTED_PDF", "PDF requires a password", str(path))

    items: list[ParsedItem] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            raise HarnessError(
                "PDF_TEXT_EXTRACTION_FAILED", str(exc), f"{path}#page={page_number}"
            ) from exc
        for block_index, block in enumerate(_pdf_blocks(text), start=1):
            items.append(
                ParsedItem(
                    locator={
                        "kind": "text_block",
                        "page": page_number,
                        "block_index": block_index,
                    },
                    excerpt=_clip(block),
                )
            )
    if not items:
        return ParseResult(
            status="needs_ocr",
            message="No extractable text found; OCR is required for this PDF",
        )
    return ParseResult(items=items)


def parse_xlsx(path: Path) -> ParseResult:
    """Extract non-empty worksheet rows using only OOXML and standard-library code."""

    try:
        with zipfile.ZipFile(path) as package:
            workbook = ElementTree.fromstring(package.read("xl/workbook.xml"))
            relationships = ElementTree.fromstring(package.read("xl/_rels/workbook.xml.rels"))
            shared_strings = _xlsx_shared_strings(package)
            relation_targets = {
                rel.attrib["Id"]: rel.attrib["Target"]
                for rel in relationships.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
            }
            items: list[ParsedItem] = []
            sheets = workbook.find(f"{{{SHEET_NS}}}sheets")
            if sheets is None:
                raise HarnessError("INVALID_XLSX", "Workbook contains no sheets", str(path))
            for sheet in sheets.findall(f"{{{SHEET_NS}}}sheet"):
                sheet_name = sheet.attrib.get("name", "")
                relation_id = sheet.attrib.get(f"{{{REL_NS}}}id")
                target = relation_targets.get(relation_id or "")
                if not target:
                    raise HarnessError(
                        "INVALID_XLSX",
                        f"Missing worksheet relationship for {sheet_name}",
                        str(path),
                    )
                worksheet_path = _worksheet_package_path(target)
                worksheet = ElementTree.fromstring(package.read(worksheet_path))
                items.extend(_xlsx_rows(worksheet, sheet_name, shared_strings))
    except KeyError as exc:
        raise HarnessError("INVALID_XLSX", f"Missing workbook part: {exc}", str(path)) from exc
    if not items:
        return ParseResult(status="empty", message="No non-empty worksheet cells found")
    return ParseResult(items=items)


def _word_text(element: ElementTree.Element) -> str:
    if element.tag == f"{{{WORD_NS}}}tc":
        paragraphs = [_word_text(paragraph) for paragraph in element.findall(f".//{{{WORD_NS}}}p")]
        return _normalize_text(" ".join(text for text in paragraphs if text))
    parts = [node.text or "" for node in element.iter(f"{{{WORD_NS}}}t")]
    return _normalize_text("".join(parts))


def _word_heading_level(paragraph: ElementTree.Element) -> int | None:
    style = paragraph.find(f"{{{WORD_NS}}}pPr/{{{WORD_NS}}}pStyle")
    if style is None:
        return None
    value = style.attrib.get(f"{{{WORD_NS}}}val", "")
    match = re.fullmatch(r"Heading([1-9])", value, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _pdf_blocks(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", normalized)
    if len(blocks) == 1:
        blocks = normalized.splitlines()
    return [_normalize_text(block) for block in blocks if _normalize_text(block)]


def _xlsx_shared_strings(package: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in package.namelist():
        return []
    root = ElementTree.fromstring(package.read("xl/sharedStrings.xml"))
    return [
        _normalize_text("".join(node.text or "" for node in item.iter(f"{{{SHEET_NS}}}t")))
        for item in root.findall(f"{{{SHEET_NS}}}si")
    ]


def _worksheet_package_path(target: str) -> str:
    normalized = target.lstrip("/")
    if normalized.startswith("xl/"):
        return normalized
    return f"xl/{normalized}"


def _xlsx_rows(
    worksheet: ElementTree.Element, sheet_name: str, shared_strings: list[str]
) -> list[ParsedItem]:
    items: list[ParsedItem] = []
    for row in worksheet.findall(f".//{{{SHEET_NS}}}row"):
        values: list[tuple[str, str]] = []
        formulas: dict[str, str] = {}
        for cell in row.findall(f"{{{SHEET_NS}}}c"):
            reference = cell.attrib.get("r")
            value = _xlsx_cell_value(cell, shared_strings)
            formula = _xlsx_cell_formula(cell)
            if reference and formula:
                formulas[reference] = formula
            if reference and value:
                values.append((reference, value))
        if not values:
            continue
        start, end = values[0][0], values[-1][0]
        locator: dict[str, object] = {
            "kind": "cell_range",
            "sheet": sheet_name,
            "range": start if start == end else f"{start}:{end}",
        }
        if formulas:
            locator["formulas"] = formulas
            locator["formula_status"] = "not_recalculated"
        items.append(
            ParsedItem(
                locator=locator,
                excerpt=_clip(" | ".join(value for _, value in values)),
            )
        )
    return items


def _xlsx_cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return _normalize_text("".join(node.text or "" for node in cell.iter(f"{{{SHEET_NS}}}t")))
    value_node = cell.find(f"{{{SHEET_NS}}}v")
    if value_node is None or value_node.text is None:
        return ""
    raw = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError) as exc:
            raise HarnessError("INVALID_XLSX", f"Invalid shared string index: {raw}") from exc
    if cell_type == "b":
        return "TRUE" if raw == "1" else "FALSE"
    return _normalize_text(raw)


def _xlsx_cell_formula(cell: ElementTree.Element) -> str:
    formula = cell.find(f"{{{SHEET_NS}}}f")
    if formula is None or formula.text is None:
        return ""
    return _normalize_text(formula.text)


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _clip(value: str) -> str:
    if len(value) <= MAX_EXCERPT_CHARS:
        return value
    return value[: MAX_EXCERPT_CHARS - 1].rstrip() + "…"
