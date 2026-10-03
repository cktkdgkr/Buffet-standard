"""
Write each formula's result into the workbook beside the formula.

openpyxl writes `<f>B2*C2</f>` and nothing else. Desktop Excel recalculates on
open and fills the value in, but phone and web viewers generally do not, so
every derived cell reads as blank - which is why the workbook looked empty on a
phone while the figures were there all along.

This computes each formula with the evaluator already used to verify the
workbook, then adds the result as a cached `<v>` next to the `<f>`. Both are
kept: a reader with no recalculation sees numbers, and anyone who wants to know
where a number came from still has the formula in the formula bar.

The edit is made on the sheet XML rather than through openpyxl, which has no
way to hold a formula and its value at once. After writing, the workbook is
reopened with data_only=True - the view a non-recalculating reader gets - and
every cached value is checked against the analysis engine. A cached value that
disagrees with the formula is worse than no cached value at all, because it
looks authoritative.

    python3 embed_xlsx_values.py
"""

import json
import os
import re
import shutil
import sys
import zipfile
from xml.etree import ElementTree as ET

from openpyxl import load_workbook

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from verify_exports import Evaluator, close                    # noqa: E402

XLSX = os.path.join(HERE, "미국50개사_ROIC_WACC비교.xlsx")
ROIC = os.path.join(HERE, "roic", "roic.json")

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CELL = re.compile(r'<c\b[^>]*?r="([A-Z]+\d+)"[^>]*>(.*?)</c>', re.S)
HAS_F = re.compile(r"<f[ >]")


def compute(wb):
    """Every formula cell's evaluated result, keyed by sheet and coordinate."""
    ev = Evaluator(wb)
    values, failures = {}, []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if not isinstance(cell.value, str) or \
                        not cell.value.startswith("="):
                    continue
                try:
                    values[(ws.title, cell.coordinate)] = \
                        ev.value(ws.title, cell.coordinate)
                except Exception as exc:                       # noqa: BLE001
                    failures.append(f"{ws.title}!{cell.coordinate}: {exc}")
    return values, failures


def as_xml_value(v):
    """The cached value as it has to appear in the sheet XML."""
    if v is None or v == "":
        # A formula whose result is the empty string. Excel stores the type and
        # an empty value; leaving the value out entirely makes some readers
        # show the cell as zero.
        return ' t="str"', "<v></v>"
    if isinstance(v, bool):
        return ' t="b"', f"<v>{1 if v else 0}</v>"
    if isinstance(v, (int, float)):
        return "", f"<v>{v!r}</v>"
    text = (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))
    return ' t="str"', f"<v>{text}</v>"


def inject(xml, sheet_values):
    """Add a cached value to every formula cell in one sheet's XML."""
    count = 0

    def repl(m):
        nonlocal count
        coord, inner = m.group(1), m.group(2)
        if not HAS_F.search(inner) or coord not in sheet_values:
            return m.group(0)
        whole = m.group(0)
        # Drop any existing value, then append the new one after the formula.
        # openpyxl already emits an empty self-closing <v /> after each
        # formula, which is what a non-recalculating viewer renders as a blank
        # cell. Both that and a populated <v> have to go before the real value
        # is appended.
        inner_clean = re.sub(r"<v\s*/>", "", inner, flags=re.S)
        inner_clean = re.sub(r"<v[^>]*>.*?</v>", "", inner_clean, flags=re.S)
        inner_clean = re.sub(r"<is>.*?</is>", "", inner_clean, flags=re.S)
        attr, value = as_xml_value(sheet_values[coord])
        open_tag = whole[:whole.index(">") + 1]
        open_tag = re.sub(r'\s+t="[^"]*"', "", open_tag)
        if attr:
            open_tag = open_tag[:-1] + attr + ">"
        count += 1
        return f"{open_tag}{inner_clean}{value}</c>"

    return CELL.sub(repl, xml), count


def sheet_paths(zf):
    """
    Sheet title to the XML part that holds it, in workbook order.

    Parsed rather than pattern-matched. Attribute order in XML carries no
    meaning, and openpyxl happens to write the relationship id last
    (Type, Target, Id), so a pattern expecting Id before Target silently
    matched nothing and no values were embedded at all.
    """
    wbxml = ET.fromstring(zf.read("xl/workbook.xml"))
    relxml = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_target = {r.get("Id"): r.get("Target") for r in relxml}
    rid_attr = f"{{{RELNS}}}id"
    out = []
    sheets = wbxml.find(f"{{{NS}}}sheets")
    for sheet in (sheets if sheets is not None else []):
        name, rid = sheet.get("name"), sheet.get(rid_attr)
        target = rel_target.get(rid) or ""
        if not target:
            continue
        # openpyxl writes these as absolute package paths ("/xl/worksheets/
        # sheet1.xml"); the relationship spec also allows them relative to the
        # part's folder. Both have to resolve to the zip entry name.
        out.append((name, target.lstrip("/") if target.startswith("/")
                    else "xl/" + target))
    return out


def main():
    wb = load_workbook(XLSX, data_only=False)
    values, failures = compute(wb)
    if failures:
        print(f"수식 평가 실패 {len(failures)}건 — 값을 심지 않았습니다")
        for f in failures[:10]:
            print(f"  {f}")
        return 1
    print(f"수식 {len(values)}개 평가 완료")

    backup = XLSX + ".formulas-only"
    shutil.copy2(XLSX, backup)

    src = zipfile.ZipFile(XLSX)
    titles = sheet_paths(src)
    by_sheet = {}
    for (title, coord), v in values.items():
        by_sheet.setdefault(title, {})[coord] = v

    tmp = XLSX + ".tmp"
    injected = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        path_of = dict(titles)
        wanted = {path_of[t]: by_sheet[t] for t in by_sheet if t in path_of}
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename in wanted:
                xml, n = inject(data.decode("utf-8"), wanted[item.filename])
                data = xml.encode("utf-8")
                injected += n
            dst.writestr(item, data)
    src.close()
    os.replace(tmp, XLSX)
    print(f"셀 {injected}개에 계산값을 심었습니다 "
          f"(수식은 유지, 원본은 {os.path.basename(backup)})")

    # Now read it the way a viewer that does not recalculate reads it.
    check = load_workbook(XLSX, data_only=True)
    data = json.load(open(ROIC))
    by = {c["ticker"]: {y["fiscal_year"]: y for y in c["years"]}
          for c in data["companies"]}

    ws = check["계산 명세"]
    checks, fails = 0, []
    for r in range(2, ws.max_row + 1):
        tk = ws.cell(row=r, column=2).value
        fy = ws.cell(row=r, column=3).value
        if not tk or not fy or fy == 2015:
            continue
        y = by[tk][fy]
        for col, key, nd in ((10, "nopat", None), (14, "invested_capital",
                                                   None),
                             (16, "invested_capital_avg", None),
                             (18, "roic", None)):
            checks += 1
            got = ws.cell(row=r, column=col).value
            want = y[key]
            if want is None:
                if got not in (None, "", "—"):
                    fails.append(f"{tk} FY{fy} {key}: 값이 있어야 "
                                 f"하지 않음 ({got})")
            elif not isinstance(got, (int, float)) or not close(got, want):
                fails.append(f"{tk} FY{fy} {key}: {got!r} != {want!r}")

    grid = check["ROIC 연도별"]
    for r in range(3, grid.max_row + 1):
        tk = grid.cell(row=r, column=3).value
        if not tk or tk not in by:
            continue
        for i, fy in enumerate(range(2016, 2026)):
            checks += 1
            got = grid.cell(row=r, column=4 + i).value
            y = by[tk].get(fy)
            want = None if (y is None or y["roic"] is None) else y["roic"]
            if want is None:
                if isinstance(got, (int, float)):
                    fails.append(f"{tk} FY{fy} 연도별: 값이 있어야 "
                                 f"하지 않음 ({got})")
            elif not isinstance(got, (int, float)) or not close(got, want):
                fails.append(f"{tk} FY{fy} 연도별: {got!r} != {want!r}")

    print(f"재계산 없이 읽은 값 {checks}건 중 통과 {checks - len(fails)}건, "
          f"실패 {len(fails)}건")
    for f in fails[:15]:
        print(f"  실패: {f}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
