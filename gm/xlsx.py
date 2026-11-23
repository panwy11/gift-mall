# -*- coding: utf-8 -*-
"""极简 xlsx 生成器：只用标准库 zipfile 手写 OOXML，不依赖 openpyxl。

build_xlsx([(sheet_name, headers, rows, col_widths), ...]) -> bytes
rows 中的元素：str / int / float / tuple(值, "num"|"text")
"""
import io
import zipfile
from xml.sax.saxutils import escape

FONT = "微软雅黑"


def _col(i):
    """0 -> A, 25 -> Z, 26 -> AA"""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref, val, style=0):
    if val is None or val == "":
        return '<c r="%s" s="%d"/>' % (ref, style)
    if isinstance(val, bool):
        val = "是" if val else "否"
    if isinstance(val, (int, float)):
        return '<c r="%s" s="%d"><v>%s</v></c>' % (ref, style, repr(val) if isinstance(val, float) else val)
    txt = escape(str(val))
    return ('<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
            % (ref, style, txt))


STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="3">
  <font><sz val="10.5"/><name val="{f}"/></font>
  <font><b/><sz val="10.5"/><color rgb="FFFFFFFF"/><name val="{f}"/></font>
  <font><sz val="10.5"/><name val="{f}"/></font>
</fonts>
<fills count="3">
  <fill><patternFill patternType="none"/></fill>
  <fill><patternFill patternType="gray125"/></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FF2E2A24"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
  <border><left/><right/><top/><bottom/><diagonal/></border>
  <border>
    <left style="thin"><color rgb="FFE4E0D7"/></left>
    <right style="thin"><color rgb="FFE4E0D7"/></right>
    <top style="thin"><color rgb="FFE4E0D7"/></top>
    <bottom style="thin"><color rgb="FFE4E0D7"/></bottom>
    <diagonal/>
  </border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3">
  <xf numFmtId="0" fontId="0" fillId="0" borderId="1" applyBorder="1" applyAlignment="1">
    <alignment vertical="center" horizontal="left" wrapText="1"/></xf>
  <xf numFmtId="0" fontId="1" fillId="2" borderId="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">
    <alignment vertical="center" horizontal="center"/></xf>
  <xf numFmtId="0" fontId="2" fillId="0" borderId="1" applyBorder="1" applyAlignment="1">
    <alignment vertical="center" horizontal="right"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>""".format(f=FONT)


def _sheet_xml(headers, rows, widths):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           '<sheetViews><sheetView workbookViewId="0">',
           '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>',
           '</sheetView></sheetViews>',
           '<sheetFormatPr defaultRowHeight="18"/>']
    if widths:
        out.append("<cols>")
        for i, w in enumerate(widths):
            out.append('<col min="%d" max="%d" width="%s" customWidth="1"/>' % (i + 1, i + 1, w))
        out.append("</cols>")
    out.append("<sheetData>")
    out.append('<row r="1" ht="26" customHeight="1">')
    for i, h in enumerate(headers):
        out.append(_cell("%s1" % _col(i), h, 1))
    out.append("</row>")
    for ri, row in enumerate(rows, start=2):
        out.append('<row r="%d" ht="20" customHeight="1">' % ri)
        for ci, v in enumerate(row):
            style = 0
            if isinstance(v, tuple):
                v, kind = v[0], v[1]
                style = 2 if kind == "num" else 0
            elif isinstance(v, (int, float)):
                style = 2
            out.append(_cell("%s%d" % (_col(ci), ri), v, style))
        out.append("</row>")
    out.append("</sheetData>")
    out.append('<autoFilter ref="A1:%s1"/>' % _col(len(headers) - 1))
    out.append("</worksheet>")
    return "".join(out)


def build_xlsx(sheets) -> bytes:
    n = len(sheets)
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    for i in range(n):
        ct.append('<Override PartName="/xl/worksheets/sheet%d.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1))
    ct.append("</Types>")

    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>')

    wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>']
    for i, (name, *_rest) in enumerate(sheets):
        wb.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>'
                  % (escape(name[:31]), i + 1, i + 1))
    wb.append("</sheets></workbook>")

    wbrels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
              '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i in range(n):
        wbrels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1))
    wbrels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' % (n + 1))
    wbrels.append("</Relationships>")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", "".join(wb))
        z.writestr("xl/_rels/workbook.xml.rels", "".join(wbrels))
        z.writestr("xl/styles.xml", STYLES)
        for i, (name, headers, rows, widths) in enumerate(sheets):
            z.writestr("xl/worksheets/sheet%d.xml" % (i + 1),
                       _sheet_xml(headers, rows, widths))
    return buf.getvalue()
