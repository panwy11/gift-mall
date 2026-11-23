# -*- coding: utf-8 -*-
"""极简 xlsx 读取器：只用标准库 zipfile + xml，不依赖 openpyxl。

read_sheet(bytes, index=0) -> list[list[str]]
- 支持 sharedStrings / inlineStr / 数字 / 空单元格
- 日期若被 Excel 存成序列号，按数字原样返回（由调用方按列语义转换）
"""
import io
import re
import zipfile
import xml.etree.ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _col_index(letters: str) -> int:
    """A -> 0, Z -> 25, AA -> 26"""
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _all_text(el) -> str:
    return "".join(t.text or "" for t in el.iter(NS + "t"))


def _sheet_paths(zf):
    names = zf.namelist()
    paths = [n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
    paths.sort(key=lambda s: int(re.search(r"sheet(\d+)\.xml$", s).group(1)))
    return paths


def read_sheet(data: bytes, index: int = 0):
    """读取第 index 个工作表，返回二维字符串数组（行优先）。"""
    zf = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in zf.namelist():
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        shared = [_all_text(si) for si in root.findall(NS + "si")]

    paths = _sheet_paths(zf)
    if not paths:
        raise ValueError("文件里没有工作表")
    if index >= len(paths):
        index = 0
    root = ET.fromstring(zf.read(paths[index]))

    rows = []
    for row in root.iter(NS + "row"):
        cells = {}
        for c in row.findall(NS + "c"):
            ref = c.get("r") or ""
            m = re.match(r"([A-Z]+)", ref)
            if not m:
                continue
            ci = _col_index(m.group(1))
            t = c.get("t")
            v = c.find(NS + "v")
            if t == "s" and v is not None:
                try:
                    val = shared[int(v.text)]
                except Exception:
                    val = ""
            elif t == "inlineStr":
                is_el = c.find(NS + "is")
                val = _all_text(is_el) if is_el is not None else ""
            elif v is not None:
                val = v.text or ""
            else:
                val = ""
            cells[ci] = val.strip()
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(i, "") for i in range(width)])
        else:
            rows.append([])
    return rows


def excel_serial_to_date(n: int):
    """Excel 日期序列号（1900 体系）转 datetime.date。"""
    from datetime import date, timedelta
    return date(1899, 12, 30) + timedelta(days=int(n))
