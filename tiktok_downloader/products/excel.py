"""Build the affiliate sheet in the exact layout of NOV11IC.xlsx, with no extra packages.

Row 1: Original Link * | Sub_id1 .. Sub_id5   (Arial 10)
Row 3, 6, 9, ...: clickable link (Arial 11) | sub ID (Arial 10), two empty rows between entries.

An .xlsx file is a zip of a few XML files, so we write them directly (works in the .exe too).
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HEADERS = ["Original Link *", "Sub_id1", "Sub_id2", "Sub_id3", "Sub_id4", "Sub_id5"]
WIDTHS = {"A": 35.73, "B": 41.64, "C": 20.14}
FIRST_ROW, STEP = 3, 3   # data starts on row 3, then every 3rd row (2 blank rows between)

# style ids in styles.xml: 0 = Arial 10, 1 = Arial 11, 2 = Arial 11 blue underlined (link)
SMALL, LARGE, LINK = 0, 1, 2


def lines(text: str) -> list[str]:
    """Non-empty lines, trimmed, in order."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def safe_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]+', "", (name or "").strip()) or "subids"
    return name if name.lower().endswith(".xlsx") else name + ".xlsx"


def _clean(text: str) -> str:
    """Drop characters XML can't hold (stray control characters from copy-paste)."""
    return "".join(ch for ch in text if ch in "\t\n\r" or ord(ch) >= 32)


def _cell(ref: str, text: str, style: int) -> str:
    value = escape(_clean(text))
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{value}</t></is></c>'


def build(links: list[str], sub_ids: list[str], path: Path) -> int:
    """Write the sheet; returns how many rows were written (the longer list wins)."""
    count = max(len(links), len(sub_ids))
    rows = ['<row r="1">' + "".join(_cell(f"{chr(65 + i)}1", h, SMALL) for i, h in enumerate(HEADERS)) + "</row>"]
    hyperlinks, relations = [], []
    for i in range(count):
        r = FIRST_ROW + i * STEP
        cells = []
        if i < len(links):
            is_url = links[i].lower().startswith(("http://", "https://"))
            cells.append(_cell(f"A{r}", links[i], LINK if is_url else LARGE))
            if is_url:
                rid = f"rId{len(relations) + 1}"
                hyperlinks.append(f'<hyperlink ref="A{r}" r:id="{rid}"/>')
                target = escape(_clean(links[i]), {'"': "&quot;"})
                relations.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/'
                                 f'2006/relationships/hyperlink" Target="{target}" TargetMode="External"/>')
        if i < len(sub_ids):
            cells.append(_cell(f"B{r}", sub_ids[i], SMALL))
        rows.append(f'<row r="{r}">' + "".join(cells) + "</row>")

    cols = "".join(f'<col min="{ord(c) - 64}" max="{ord(c) - 64}" width="{w}" customWidth="1"/>'
                   for c, w in WIDTHS.items())
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheetFormatPr defaultRowHeight="15.75"/>'
        f"<cols>{cols}</cols><sheetData>{''.join(rows)}</sheetData>"
        + (f"<hyperlinks>{''.join(hyperlinks)}</hyperlinks>" if hyperlinks else "")
        + "</worksheet>"
    )
    files = {
        "[Content_Types].xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            "</Types>",
        "_rels/.rels":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        "xl/workbook.xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>",
        "xl/styles.xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="3">'
            '<font><sz val="10"/><name val="Arial"/></font>'
            '<font><sz val="11"/><name val="Arial"/></font>'
            '<font><u/><sz val="11"/><color rgb="FF0563C1"/><name val="Arial"/></font>'
            "</fonts>"
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="3">'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
            '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
            "</cellXfs>"
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            "</styleSheet>",
        "xl/worksheets/sheet1.xml": sheet,
    }
    if relations:
        files["xl/worksheets/_rels/sheet1.xml.rels"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(relations) + "</Relationships>")

    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    temp.replace(path)
    return count


# ------------------------------------------------------------------ reading

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def read_rows(path: Path) -> list[tuple[str, str]]:
    """(link, sub ID) pairs from a sheet in this layout: column A links, column B sub IDs.

    Works for files made here and for Excel/Google Sheets files (shared strings)."""
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter(f"{_NS}t")) for si in root.iter(f"{_NS}si")]
        sheet = "xl/worksheets/sheet1.xml" if "xl/worksheets/sheet1.xml" in names else \
            sorted(n for n in names if n.startswith("xl/worksheets/sheet"))[0]
        root = ET.fromstring(archive.read(sheet))

    rows: dict[int, dict[str, str]] = {}
    for cell in root.iter(f"{_NS}c"):
        ref = cell.get("r", "")
        match = re.match(r"([A-Z]+)(\d+)", ref)
        if not match:
            continue
        kind, value = cell.get("t"), ""
        if kind == "s":
            v = cell.find(f"{_NS}v")
            value = shared[int(v.text)] if v is not None and v.text and v.text.isdigit() else ""
        elif kind == "inlineStr":
            value = "".join(t.text or "" for t in cell.iter(f"{_NS}t"))
        else:
            v = cell.find(f"{_NS}v")
            value = v.text if v is not None and v.text else ""
        rows.setdefault(int(match.group(2)), {})[match.group(1)] = value.strip()

    # Boss's converted file has a header row with "Convert Link": use only those links.
    link_col, sub_col = "A", "B"
    for number in sorted(rows)[:5]:
        for col, text in rows[number].items():
            if text.strip().lower() == "convert link":
                link_col = col

    pairs = []
    for number in sorted(rows):
        original = rows[number].get("A", "")
        if not original.lower().startswith(("http://", "https://")):
            continue   # header, title or blank spacer row
        link = rows[number].get(link_col, "")
        pairs.append((link if link.lower().startswith(("http://", "https://")) else "",
                      rows[number].get(sub_col, "")))
    return pairs
