"""Deterministic DOCX export derived only from the disclosure ledger."""

# ruff: noqa: E501 - OOXML template lines are intentionally kept intact.

from __future__ import annotations

import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

CONTENT_LABELS = {
    "inference": "[待确认-推断] ",
    "suggested_text": "[建议文本] ",
    "information_gap": "[信息缺口] ",
}
LABEL_COLORS = {
    "inference": "7A5A00",
    "suggested_text": "1F4D78",
    "information_gap": "9B1C1C",
}
CJK_FONT = "Songti SC"


def write_master_docx(
    path: Path,
    *,
    config: dict[str, Any],
    outline: dict[str, Any],
    ledger: list[dict[str, Any]],
    internal: bool,
) -> None:
    """Create a narrative-proposal DOCX with an editorial-cover title pattern."""

    path.parent.mkdir(parents=True, exist_ok=True)
    document_xml, comments = _document_xml(config, outline, ledger, internal)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", _content_types(internal))
        package.writestr("_rels/.rels", _root_relationships())
        package.writestr("docProps/core.xml", _core_properties(config))
        package.writestr("docProps/app.xml", _app_properties())
        package.writestr("word/document.xml", document_xml)
        package.writestr("word/styles.xml", _styles_xml())
        package.writestr("word/fontTable.xml", _font_table_xml())
        package.writestr("word/settings.xml", _settings_xml())
        package.writestr("word/header1.xml", _header_xml(config, internal))
        package.writestr("word/footer1.xml", _footer_xml())
        package.writestr("word/_rels/document.xml.rels", _document_relationships(internal))
        if internal:
            package.writestr("word/comments.xml", _comments_xml(comments))


def _document_xml(
    config: dict[str, Any],
    outline: dict[str, Any],
    ledger: list[dict[str, Any]],
    internal: bool,
) -> tuple[str, list[dict[str, Any]]]:
    row_by_unified = {row["unified_disclosure"]["unified_id"]: row for row in ledger}
    comments: list[dict[str, Any]] = []
    paragraphs = [
        _paragraph("内部专业审阅底稿" if internal else "可持续披露报告", "Kicker"),
        _paragraph(config["client_name"], "Title"),
        _paragraph(config["project_name"], "Subtitle"),
        _paragraph(
            f"报告期间：{config['reporting_period_start']} 至 {config['reporting_period_end']}",
            "Meta",
        ),
        _paragraph("由 Sustainability Report Harness 依据已确认账本生成", "Meta"),
        _page_break(),
        _paragraph("目录", "Heading1"),
    ]
    for index, section in enumerate(outline["sections"], start=1):
        paragraphs.append(_paragraph(f"{index}. {section['title']}", "TOC1"))
    paragraphs.append(_page_break())

    for section in outline["sections"]:
        paragraphs.append(_paragraph(section["title"], "Heading1"))
        if internal:
            paragraphs.append(
                _paragraph(
                    f"章节目标：{section['objective']}｜字数预算："
                    f"{section['target_length_words']}｜章节编号：{section['section_id']}",
                    "SectionObjective",
                )
            )
        for unified_id in section["unified_ids"]:
            row = row_by_unified[unified_id]
            paragraphs.append(_paragraph(row["unified_disclosure"]["title"], "Heading2"))
            for content in row.get("content", []):
                if not internal and content["content_type"] == "information_gap":
                    continue
                comment_id = None
                if internal:
                    comment_id = len(comments)
                    comments.append(
                        {
                            "id": comment_id,
                            "content_id": content["content_id"],
                            "content_type": content["content_type"],
                            "evidence_ids": content.get("evidence_ids", []),
                            "unified_ids": content.get("unified_ids", []),
                            "review_status": content["review_status"],
                        }
                    )
                paragraphs.append(_content_paragraph(content, internal, comment_id))
    paragraphs.append(
        """<w:sectPr><w:headerReference w:type="default" r:id="rId2"/><w:footerReference w:type="default" r:id="rId3"/><w:titlePg/><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/><w:cols w:space="708"/><w:docGrid w:linePitch="360"/></w:sectPr>"""
    )
    body = "".join(paragraphs)
    return (
        f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>{body}</w:body></w:document>""",
        comments,
    )


def _paragraph(text: str, style: str) -> str:
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{_text_run(text)}</w:p>'


def _content_paragraph(content: dict[str, Any], internal: bool, comment_id: int | None) -> str:
    marker = CONTENT_LABELS.get(content["content_type"], "") if internal else ""
    marker_run = ""
    if marker:
        color = LABEL_COLORS[content["content_type"]]
        marker_run = (
            f'<w:r><w:rPr><w:rFonts w:ascii="{CJK_FONT}" w:hAnsi="{CJK_FONT}" '
            f'w:eastAsia="{CJK_FONT}" w:cs="{CJK_FONT}" w:hint="eastAsia"/>'
            f'<w:lang w:val="zh-CN" w:eastAsia="zh-CN"/><w:b/><w:color w:val="{color}"/></w:rPr>'
            f'<w:t xml:space="preserve">{escape(marker)}</w:t></w:r>'
        )
    start = f'<w:commentRangeStart w:id="{comment_id}"/>' if comment_id is not None else ""
    end = ""
    if comment_id is not None:
        end = (
            f'<w:commentRangeEnd w:id="{comment_id}"/>'
            f'<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>'
            f'<w:commentReference w:id="{comment_id}"/></w:r>'
        )
    return (
        '<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
        f"{start}{marker_run}{_text_run(content['text'])}{end}</w:p>"
    )


def _text_run(text: str) -> str:
    pieces = re.split(r"\n", _sanitize_xml(text))
    runs = []
    for index, piece in enumerate(pieces):
        if index:
            runs.append("<w:r><w:br/></w:r>")
        runs.append(
            f'<w:r><w:rPr><w:rFonts w:ascii="{CJK_FONT}" w:hAnsi="{CJK_FONT}" '
            f'w:eastAsia="{CJK_FONT}" w:cs="{CJK_FONT}" w:hint="eastAsia"/>'
            f'<w:lang w:val="zh-CN" w:eastAsia="zh-CN"/></w:rPr>'
            f'<w:t xml:space="preserve">{escape(piece)}</w:t></w:r>'
        )
    return "".join(runs)


def _page_break() -> str:
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def _comments_xml(comments: list[dict[str, Any]]) -> str:
    timestamp = datetime.now(UTC).isoformat()
    values = []
    for item in comments:
        evidence = ", ".join(item["evidence_ids"]) or "无"
        unified = ", ".join(item["unified_ids"])
        text = (
            f"内容编号：{item['content_id']}\n内容类型：{item['content_type']}\n"
            f"统一披露要求：{unified}\n证据编号：{evidence}\n"
            f"人工审阅状态：{item['review_status']}"
        )
        values.append(
            f'<w:comment w:id="{item["id"]}" w:author="Sustainability Report Harness" '
            f'w:initials="SRH" w:date="{timestamp}"><w:p>{_text_run(text)}</w:p></w:comment>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"{''.join(values)}</w:comments>"
    )


def _styles_xml() -> str:
    xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/><w:szCs w:val="22"/><w:color w:val="202020"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="320" w:lineRule="auto"/><w:jc w:val="both"/></w:pPr></w:pPrDefault></w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/><w:pPr><w:widowControl/><w:spacing w:before="0" w:after="160" w:line="320" w:lineRule="auto"/><w:jc w:val="both"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:qFormat/><w:pPr><w:spacing w:before="0" w:after="160"/><w:jc w:val="center"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Microsoft YaHei"/><w:b/><w:color w:val="203748"/><w:sz w:val="60"/><w:szCs w:val="60"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:qFormat/><w:pPr><w:spacing w:after="560"/><w:jc w:val="center"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Microsoft YaHei"/><w:color w:val="2B5163"/><w:sz w:val="30"/><w:szCs w:val="30"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Kicker"><w:name w:val="Kicker"/><w:pPr><w:spacing w:before="2640" w:after="360"/><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:caps/><w:color w:val="7A5A00"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Meta"><w:name w:val="Meta"/><w:pPr><w:spacing w:after="80"/><w:jc w:val="center"/></w:pPr><w:rPr><w:i/><w:color w:val="505050"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="360" w:after="200"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="2E74B5"/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:color w:val="2E74B5"/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="160" w:after="80"/><w:outlineLvl w:val="2"/></w:pPr><w:rPr><w:b/><w:color w:val="1F4D78"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="80"/><w:ind w:left="240"/></w:pPr><w:rPr><w:color w:val="1F4D78"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="SectionObjective"><w:name w:val="Section Objective"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="160"/><w:ind w:left="240" w:right="240"/></w:pPr><w:rPr><w:i/><w:color w:val="556270"/><w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr></w:style>
  <w:style w:type="character" w:styleId="CommentReference"><w:name w:val="Comment Reference"/><w:uiPriority w:val="99"/><w:semiHidden/><w:unhideWhenUsed/><w:rPr><w:vertAlign w:val="superscript"/><w:color w:val="2E74B5"/></w:rPr></w:style>
</w:styles>"""
    return (
        xml.replace("Calibri", CJK_FONT)
        .replace("Microsoft YaHei", CJK_FONT)
        .replace(
            f'w:eastAsia="{CJK_FONT}"/>',
            f'w:eastAsia="{CJK_FONT}" w:hint="eastAsia"/>',
        )
    )


def _font_table_xml() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:fonts xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:font w:name="{CJK_FONT}"><w:panose1 w:val="020B0500000000000000"/><w:charset w:val="86"/><w:family w:val="swiss"/><w:pitch w:val="variable"/></w:font>
</w:fonts>'''


def _header_xml(config: dict[str, Any], internal: bool) -> str:
    label = f"{config['project_name']} | {'内部审阅版' if internal else '报告草稿'}"
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:pPr><w:jc w:val="right"/><w:spacing w:after="0"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii="{CJK_FONT}" w:hAnsi="{CJK_FONT}" w:eastAsia="{CJK_FONT}" w:hint="eastAsia"/><w:lang w:val="zh-CN" w:eastAsia="zh-CN"/><w:color w:val="6B7280"/><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr><w:t>{escape(_sanitize_xml(label))}</w:t></w:r></w:p></w:hdr>'''


def _footer_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:pPr><w:jc w:val="right"/></w:pPr><w:r><w:rPr><w:color w:val="6B7280"/><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>"""


def _content_types(internal: bool) -> str:
    comments = (
        '<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>'
        if internal
        else ""
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/fontTable.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"/><Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/><Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/><Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>{comments}<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""


def _root_relationships() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>"""


def _document_relationships(internal: bool) -> str:
    comments = (
        '<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>'
        if internal
        else ""
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/><Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable" Target="fontTable.xml"/>{comments}</Relationships>"""


def _settings_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:updateFields w:val="true"/><w:defaultTabStop w:val="720"/><w:characterSpacingControl w:val="doNotCompress"/></w:settings>"""


def _core_properties(config: dict[str, Any]) -> str:
    timestamp = datetime.now(UTC).isoformat()
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>{escape(config["project_name"])}</dc:title><dc:creator>Sustainability Report Harness</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:modified></cp:coreProperties>"""


def _app_properties() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Sustainability Report Harness</Application><AppVersion>0.5</AppVersion></Properties>"""


def _sanitize_xml(value: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value))
