"""Dependency-free OOXML writer for fixed M4 review workbooks."""

# ruff: noqa: E501 - OOXML template lines are intentionally kept intact.

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


def write_review_workbook(
    path: Path,
    *,
    sheet_name: str,
    title: str,
    headers: list[str],
    rows: list[list[Any]],
) -> None:
    """Write one styled, filterable review sheet with explicit widths and frozen headers."""

    if any(len(row) != len(headers) for row in rows):
        raise ValueError("Every workbook row must match the fixed header count")
    path.parent.mkdir(parents=True, exist_ok=True)
    last_column = _column_name(len(headers))
    last_row = 4 + max(len(rows), 1)
    widths = _column_widths(headers, rows)
    sheet_xml = _worksheet_xml(title, headers, rows, widths, last_column, last_row)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", _content_types())
        package.writestr("_rels/.rels", _root_relationships())
        package.writestr("docProps/core.xml", _core_properties(title))
        package.writestr("docProps/app.xml", _app_properties(sheet_name))
        package.writestr("xl/workbook.xml", _workbook_xml(sheet_name))
        package.writestr("xl/_rels/workbook.xml.rels", _workbook_relationships())
        package.writestr("xl/styles.xml", _styles_xml())
        package.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def _worksheet_xml(
    title: str,
    headers: list[str],
    rows: list[list[Any]],
    widths: list[float],
    last_column: str,
    last_row: int,
) -> str:
    columns = "".join(
        f'<col min="{index}" max="{index}" width="{width:.1f}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    )
    title_cell = _inline_cell("A1", title, 1)
    note_cell = _inline_cell(
        "A2",
        "内部审阅底稿｜字段顺序依据 PRD 固定｜业务判断以 disclosure_ledger.jsonl 为准",
        2,
    )
    header_cells = "".join(
        _inline_cell(f"{_column_name(index)}4", value, 3)
        for index, value in enumerate(headers, start=1)
    )
    body_rows = []
    for row_index, row in enumerate(rows, start=5):
        cells = "".join(
            _inline_cell(
                f"{_column_name(column_index)}{row_index}",
                _display(value),
                _body_style(value),
            )
            for column_index, value in enumerate(row, start=1)
        )
        body_rows.append(f'<row r="{row_index}">{cells}</row>')
    if not rows:
        body_rows.append(f'<row r="5">{_inline_cell("A5", "当前没有符合条件的记录", 2)}</row>')
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="4" topLeftCell="A5" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
  <sheetFormatPr defaultRowHeight="18"/>
  <cols>{columns}</cols>
  <sheetData>
    <row r="1" ht="28" customHeight="1">{title_cell}</row>
    <row r="2" ht="22" customHeight="1">{note_cell}</row>
    <row r="3" ht="8" customHeight="1"/>
    <row r="4" ht="36" customHeight="1">{header_cells}</row>
    {"".join(body_rows)}
  </sheetData>
  <mergeCells count="2"><mergeCell ref="A1:{last_column}1"/><mergeCell ref="A2:{last_column}2"/></mergeCells>
  <autoFilter ref="A4:{last_column}{last_row}"/>
  <pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
  <pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0" paperSize="9"/>
</worksheet>"""


def _styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="4">
    <font><sz val="10"/><name val="Aptos"/><family val="2"/></font>
    <font><b/><sz val="15"/><color rgb="FFFFFFFF"/><name val="Aptos Display"/></font>
    <font><i/><sz val="9"/><color rgb="FF475569"/><name val="Aptos"/></font>
    <font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font>
  </fonts>
  <fills count="6">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF173F5F"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF206A73"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFF7E6"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFE7E7"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border><left/><right/><top/><bottom style="thin"><color rgb="FFD9E2E8"/></bottom><diagonal/></border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="7">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0"><alignment vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="3" fillId="3" borderId="0" xfId="0"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="0" fillId="5" borderId="1" xfId="0"><alignment vertical="top" wrapText="1"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def _inline_cell(reference: str, value: str, style: int) -> str:
    safe = escape(_sanitize_xml(value))
    preserve = ' xml:space="preserve"' if value != value.strip() else ""
    return f'<c r="{reference}" s="{style}" t="inlineStr"><is><t{preserve}>{safe}</t></is></c>'


def _body_style(value: Any) -> int:
    text = _display(value)
    if text in {"needs_confirmation", "partially_addressed", "medium", "unreviewed"}:
        return 5
    if text in {"not_addressed", "low", "rejected", "critical"}:
        return 6
    return 4


def _column_widths(headers: list[str], rows: list[list[Any]]) -> list[float]:
    widths: list[float] = []
    for index, header in enumerate(headers):
        samples = [header, *(_display(row[index]) for row in rows[:100])]
        longest = max((_visual_length(value) for value in samples), default=12)
        widths.append(min(42.0, max(12.0, longest * 1.05 + 2)))
    return widths


def _visual_length(value: str) -> int:
    return sum(2 if ord(character) > 127 else 1 for character in value[:120])


def _display(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list | tuple | set):
        return "; ".join(map(str, value))
    return str(value)


def _sanitize_xml(value: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)


def _column_name(index: int) -> str:
    output = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        output = chr(65 + remainder) + output
    return output


def _content_types() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""


def _root_relationships() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""


def _workbook_xml(sheet_name: str) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <bookViews><workbookView xWindow="0" yWindow="0" windowWidth="20000" windowHeight="12000"/></bookViews>
  <sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>
  <calcPr calcId="191029" fullCalcOnLoad="1"/>
</workbook>'''


def _workbook_relationships() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _core_properties(title: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{escape(title)}</dc:title><dc:creator>Sustainability Report Harness</dc:creator>
</cp:coreProperties>"""


def _app_properties(sheet_name: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Sustainability Report Harness</Application><TitlesOfParts><vt:vector size="1" baseType="lpstr"><vt:lpstr>{escape(sheet_name)}</vt:lpstr></vt:vector></TitlesOfParts>
</Properties>"""
