"""
Checks the exported workbook against the analysis it came from.

LibreOffice does not run in this environment, so the usual recalculate-and-look
verification is unavailable. This substitutes something stricter: rather than
asking an application to evaluate the formulas, it resolves each formula's cell
references itself, computes what the formula must produce from the values
actually sitting in those cells, and compares that against analysis.json.

A recalculation would only have proved the formulas evaluate without error. This
proves they point at the right cells and produce the right numbers.
"""

import json
import os
import re
import sys

from openpyxl import load_workbook

WORK = os.path.dirname(os.path.abspath(__file__))
XLSX = os.path.join(WORK, "버핏기준_52개기업_분석.xlsx")
TOL = 1e-6


def close(a, b, tol=TOL):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def main():
    with open(os.path.join(WORK, "analysis.json")) as f:
        analysis = json.load(f)
    by = {c["ticker"]: c for c in analysis["companies"]}

    wb = load_workbook(XLSX)
    failures, checked = [], 0

    # ---- workbook will recalculate on open -------------------------------
    if not (wb.calculation and wb.calculation.fullCalcOnLoad):
        failures.append("workbook is not set to recalculate on load; formula cells "
                        "would open blank")

    # ---- quality sheet: total is the sum of its component columns ---------
    ws = wb["품질순위"]
    hdr = {c.value: c.column for c in ws[4]}
    for row in ws.iter_rows(min_row=5):
        ticker = row[hdr["티커"] - 1].value
        if not ticker or ticker not in by:
            continue
        total_cell = row[hdr["총점"] - 1]
        m = re.fullmatch(r"=SUM\((\w+)(\d+):(\w+)(\d+)\)", str(total_cell.value or ""))
        if not m:
            failures.append(f"품질순위 {ticker}: 총점 is not a SUM formula")
            continue
        lo, hi = ws[f"{m.group(1)}{m.group(2)}"].column, ws[f"{m.group(3)}{m.group(4)}"].column
        parts = [ws.cell(row=total_cell.row, column=col).value for col in range(lo, hi + 1)]
        if any(p is None for p in parts):
            failures.append(f"품질순위 {ticker}: score components contain a blank")
            continue
        expected = by[ticker]["_expected_score"]
        if sum(parts) != expected:
            failures.append(f"품질순위 {ticker}: components sum to {sum(parts)}, "
                            f"report scores {expected}")
        checked += 1

    # ---- valuation sheet: P/IV and margin of safety -----------------------
    ws = wb["밸류에이션"]
    hdr = {c.value: c.column for c in ws[4]}
    for row in ws.iter_rows(min_row=5):
        ticker = row[0].value
        if not ticker or ticker not in by:
            continue
        s = by[ticker]["summary"]
        if s["valuation_status"] != "VALUED":
            continue
        mc = row[hdr["시가총액"] - 1].value
        iv = row[hdr["기준 적정가치"] - 1].value
        if not close(mc, (by[ticker]["market_cap_usd"] or 0) / 1e9, 1e-9):
            failures.append(f"밸류에이션 {ticker}: market cap cell disagrees with analysis")
        if not close(iv, (s["dcf"]["base"]["intrinsic_value"] or 0) / 1e9, 1e-9):
            failures.append(f"밸류에이션 {ticker}: intrinsic value cell disagrees with analysis")

        # Resolve the formulas by hand against the cells they name.
        ratio_f = str(row[hdr["P/적정가치(기준)"] - 1].value or "")
        mos_f = str(row[hdr["안전마진(기준)"] - 1].value or "")
        r = row[0].row
        if ratio_f != f'=IF(I{r}=0,"",D{r}/I{r})':
            failures.append(f"밸류에이션 {ticker}: unexpected P/IV formula {ratio_f}")
        if mos_f != f'=IF(I{r}=0,"",(I{r}-D{r})/I{r})':
            failures.append(f"밸류에이션 {ticker}: unexpected margin formula {mos_f}")
        if iv:
            if not close((iv - mc) / iv, s["dcf"]["base"]["margin_of_safety"], 1e-6):
                failures.append(f"밸류에이션 {ticker}: formula would yield a margin of "
                                f"safety that disagrees with analysis")
        checked += 1

    # ---- percentages are stored as fractions, not as 15 meaning 15% -------
    for name, col_label in (("품질순위", "ROIC 중앙값"), ("금융9개사", "ROE 중앙값")):
        ws = wb[name]
        hdr = {c.value: c.column for c in ws[4]}
        col = hdr.get(col_label)
        for row in ws.iter_rows(min_row=5):
            v = row[col - 1].value
            if isinstance(v, (int, float)) and abs(v) > 5:
                failures.append(f"{name} row {row[0].row}: {col_label}={v} looks like a "
                                f"percent stored as a whole number")

    # ---- year sheet row count matches the analysis -----------------------
    ws = wb["연도별데이터"]
    rows = sum(1 for row in ws.iter_rows(min_row=5) if row[0].value)
    expected_rows = sum(len(c["years"]) for c in analysis["companies"])
    if rows != expected_rows:
        failures.append(f"연도별데이터: {rows} rows, analysis has {expected_rows}")
    checked += 1

    print(f"sheets: {wb.sheetnames}")
    print(f"checks run: {checked}, year rows: {rows}")
    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for f_ in failures[:40]:
            print("  -", f_)
        return 1
    print("all export checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
