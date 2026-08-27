"""Small DOCX writer for the browser-rendered document preview."""

from __future__ import annotations

from io import BytesIO
from typing import Any, Mapping
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


DOCX_MIMETYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DEFAULT_WORD_FILENAME = "analysis_request.docx"


def word_filename() -> str:
    """Use a stable safe name; Word export does not generate request titles."""
    return DEFAULT_WORD_FILENAME


def _text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _run(value: Any, *, bold: bool = False) -> str:
    text = escape(_text(value) or "-")
    properties = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f"<w:r>{properties}<w:t>{text}</w:t></w:r>"


def _paragraph(value: Any, *, heading: bool = False, bold: bool = False) -> str:
    style = '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr>' if heading else ""
    return f"<w:p>{style}{_run(value, bold=bold)}</w:p>"


def _cell(value: Any, *, bold: bool = False) -> str:
    return f"<w:tc><w:tcPr><w:tcW w:w=\"2400\" w:type=\"dxa\"/></w:tcPr><w:p>{_run(value, bold=bold)}</w:p></w:tc>"


def _table(table: Mapping[str, Any]) -> str:
    rows: list[str] = []
    headers = [_text(item) for item in _items(table.get("headers"))]
    if headers:
        rows.append("<w:tr>" + "".join(_cell(item, bold=True) for item in headers) + "</w:tr>")
    for row in _items(table.get("rows")):
        values = [_text(item) for item in _items(row)]
        if values:
            rows.append("<w:tr>" + "".join(_cell(item) for item in values) + "</w:tr>")
    return "<w:tbl><w:tblPr><w:tblStyle w:val=\"TableGrid\"/></w:tblPr>" + "".join(rows) + "</w:tbl>"


def build_word_docx(preview: Mapping[str, Any]) -> bytes:
    """Create a DOCX from a serialized current preview DOM, in DOM order."""
    body = [_paragraph("해석 의뢰서", bold=True)]
    for section_value in _items(preview.get("sections")):
        section = _mapping(section_value)
        title = _text(section.get("title"))
        if title:
            body.append(_paragraph(title, heading=True))
        for block_value in _items(section.get("blocks")):
            block = _mapping(block_value)
            kind = _text(block.get("type"))
            if kind == "field":
                body.append(_paragraph(f"{_text(block.get('label'))}: {_text(block.get('value'))}"))
            elif kind == "stale":
                body.append(_paragraph(block.get("text"), bold=True))
            elif kind == "table":
                caption = _text(block.get("caption"))
                if caption:
                    body.append(_paragraph(caption, bold=True))
                body.append(_table(block))

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body)}<w:sectPr/></w:body></w:document>"
    )
    content_types = ('<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>')
    relationships = ('<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>')
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()
