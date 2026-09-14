"""
Evaluate the Samsung Biologics workbook's formulas and check them against
work/kr/sbl_valuation.json.

LibreOffice does not run here, so the workbook cannot be recalculated by an
application. This recalculates it instead, reusing the evaluator written for the
52-company workbook, and then compares every evaluated result to the figure the
analysis engine produced.

That is stricter than a recalculation. Recalculating only proves the formulas
evaluate without error; a formula pointing one row off evaluates perfectly and
returns the wrong number. Comparing against the engine proves the workbook
computes what it claims to.

Exit code is non-zero if anything disagrees.
"""

import json
import os
import sys

from openpyxl import load_workbook

WORK = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, WORK)
from verify_exports import Evaluator, close  # noqa: E402

XLSX = os.path.join(WORK, "삼성바이오로직스_버핏기준_기업분석.xlsx")
VAL = os.path.join(WORK, "kr", "sbl_valuation.json")
BN = 1e9
FYS = list(range(2016, 2026))


def main():
    with open(VAL) as fh:
        d = json.load(fh)
    years = {y["fiscal_year"]: y for y in d["years"]}
    oe = {e["fiscal_year"]: e for e in d["owner_earnings"]}

    wb = load_workbook(XLSX)
    ev = Evaluator(wb)
    fails, checked = [], 0

    if not (wb.calculation and wb.calculation.fullCalcOnLoad):
        fails.append("워크북이 열 때 재계산되지 않도록 설정되어 있습니다")

    def check(sheet, coord, expected, label, scale=1.0, rel=1e-5):
        nonlocal checked
        try:
            got = ev.value(sheet, coord)
        except Exception as exc:                          # noqa: BLE001
            fails.append(f"{label} [{sheet}!{coord}]: {exc}")
            return
        exp = None if expected is None else expected / scale
        if not close(got if got != "" else None, exp, rel):
            fails.append(f"{label} [{sheet}!{coord}]: 시트={got!r} 엔진={exp!r}")
        checked += 1

    def find_row(ws, label, col=1):
        for row in range(1, ws.max_row + 1):
            if ws.cell(row=row, column=col).value == label:
                return row
        raise KeyError(f"{ws.title}: '{label}' 행을 찾지 못했습니다")

    # ------------------------------------------------------------------ ROIC
    ws = wb["ROIC"]
    roic_rows = {
        "NOPAT = 영업이익 × (1 − 실효세율)": ("nopat", BN),
        "실효세율 (법인세÷세전이익)": ("effective_tax_rate", 1.0),
        "하향식": ("roic_top_down", 1.0),
        "상향식 (매입채무 차감)": ("roic_operating", 1.0),
        "상향식 − 건설중자산 (매입채무 차감)": ("roic_operating_ex_cip", 1.0),
        "상향식 − 건설중자산 (매입채무 미차감) ← 본문 기준":
            ("roic_operating_ex_payables_ex_cip", 1.0),
    }
    for label, (key, scale) in roic_rows.items():
        row = find_row(ws, label)
        for i, fy in enumerate(FYS, 2):
            coord = ws.cell(row=row, column=i).coordinate
            check("ROIC", coord, years[fy][key], f"ROIC {label} FY{fy}", scale)

    cap_rows = {
        "자본총계 + 이자부부채 + 리스부채 − 현금성 − 종속·관계기업투자": "top_down",
        "영업자본 (매입채무 차감)": "operating",
        "영업자본 (매입채무 미차감)": "operating_ex_payables",
        "영업자본 − 건설중자산 (매입채무 미차감)": "operating_ex_payables_ex_cip",
        "영업자본 − 건설중자산 (매입채무 차감)": "operating_ex_cip",
        "건설중자산": "construction_in_progress",
    }
    for label, key in cap_rows.items():
        row = find_row(ws, label)
        for i, fy in enumerate(FYS, 2):
            coord = ws.cell(row=row, column=i).coordinate
            check("ROIC", coord, years[fy]["capital"][key],
                  f"투하자본 {label} FY{fy}", BN)

    # --------------------------------------------------------- 증분ROIC
    ws = wb["증분ROIC"]
    windows = {(e["from"], e["to"]): e for e in d["incremental_returns"]}
    for row in range(1, ws.max_row + 1):
        v = ws.cell(row=row, column=1).value
        if not (isinstance(v, str) and v.startswith("FY") and "→" in v):
            continue
        a, b = (int(part.replace("FY", "")) for part in v.split("→"))
        e = windows[(a, b)]
        check("증분ROIC", f"D{row}", e["delta_nopat"], f"{v} ΔNOPAT", BN)
        check("증분ROIC", f"G{row}",
              e["operating_ex_payables_ex_cip"]["delta_capital"],
              f"{v} Δ투하자본", BN)
        check("증분ROIC", f"H{row}",
              e["operating_ex_payables_ex_cip"]["incremental_roic"],
              f"{v} 증분ROIC")

    # --------------------------------------------------------- 주주이익
    ws = wb["주주이익"]
    row_of = {}
    for row in range(1, ws.max_row + 1):
        v = ws.cell(row=row, column=1).value
        if isinstance(v, int) and v in oe:
            row_of[v] = row
    for fy, row in row_of.items():
        e = oe[fy]
        check("주주이익", f"C{row}", e["depreciation_amortization"],
              f"주주이익 FY{fy} 감가상각", BN)
        check("주주이익", f"E{row}", e["working_capital_change"],
              f"주주이익 FY{fy} 운전자본", BN)
        check("주주이익", f"F{row}", e["oe_maintenance_equals_da"],
              f"주주이익 FY{fy} 유지=감가상각", BN)
        check("주주이익", f"G{row}", e["oe_maintenance_1_2x_da"],
              f"주주이익 FY{fy} 유지=1.2배", BN)
        check("주주이익", f"H{row}", e["oe_all_in_capex"],
              f"주주이익 FY{fy} 유지=전액", BN)
        check("주주이익", f"I{row}", e["fcf_from_cash_flow_statement"],
              f"주주이익 FY{fy} OCF−capex", BN)

    # --------------------------------------------------------- 기준연도
    ws = wb["기준연도"]
    bases = d["valuation_bases"]
    nopat_row = find_row(ws, "NOPAT")
    margin_row = find_row(ws, "영업이익률")
    for col, key in ((2, "reported_fy2025"), (3, "run_rate_2026"),
                     (4, "run_rate_fx_normalised")):
        coord = ws.cell(row=nopat_row, column=col).coordinate
        check("기준연도", coord, bases[key]["nopat"], f"기준연도 {key} NOPAT", BN)
        coord = ws.cell(row=margin_row, column=col).coordinate
        check("기준연도", coord,
              bases[key]["operating_income"] / bases[key]["revenue"],
              f"기준연도 {key} 영업이익률")
    net_cash_row = find_row(ws, "순현금")
    # There are two rows labelled 순현금 (the section heading and the total);
    # find_row returns the heading, so step to the total below it.
    while ws.cell(row=net_cash_row, column=2).value is None:
        net_cash_row += 1
    while ws.cell(row=net_cash_row, column=1).value != "순현금":
        net_cash_row += 1
    check("기준연도", f"B{net_cash_row}", d["net_cash"]["net_cash"], "순현금", BN)

    # --------------------------------------------------------------- DCF
    for name in ("보수", "중립", "낙관"):
        for suffix, key in (("", "run_rate_fx_normalised"),
                            ("_reported", "reported_fy2025"),
                            ("_run", "run_rate_2026")):
            sheet = f"DCF_{name}{suffix}"
            ws = wb[sheet]
            s = next(x for x in d["valuation"][key]["scenarios"]
                     if x["scenario"] == name)
            first = find_row(ws, 1)
            for t, proj in enumerate(s["projection"], first):
                check(sheet, f"B{t}", proj["growth"], f"{sheet} {t} 성장률")
                check(sheet, f"C{t}", proj["nopat"], f"{sheet} {t} NOPAT", BN)
                check(sheet, f"D{t}", proj["reinvestment_rate"],
                      f"{sheet} {t} 재투자율")
                check(sheet, f"F{t}", proj["free_cash_flow"],
                      f"{sheet} {t} FCF", BN)
                check(sheet, f"H{t}", proj["present_value"],
                      f"{sheet} {t} 현재가치", BN)
            eq = find_row(ws, "자기자본가치")
            check(sheet, f"B{eq}", s["equity_value"], f"{sheet} 자기자본가치", BN)
            ps = find_row(ws, "주당가치 (원)")
            check(sheet, f"B{ps}", s["value_per_share"], f"{sheet} 주당가치")
            tv = find_row(ws, "터미널 현재가치")
            check(sheet, f"B{tv}", s["pv_of_terminal"],
                  f"{sheet} 터미널 현재가치", BN)
            cr = find_row(ws, "10년 누적 재투자")
            check(sheet, f"B{cr}", s["feasibility"]["cumulative_reinvestment"],
                  f"{sheet} 누적 재투자", BN)
            ex = find_row(ws, "외부조달 필요액 (재투자율>100%인 해의 부족분 합계)")
            check(sheet, f"B{ex}", s["feasibility"]["external_capital_required"],
                  f"{sheet} 외부조달", BN)

    # ------------------------------------------------------------- 요약
    ws = wb["요약"]
    row = find_row(ws, "7. 합리적인 가격")
    check("요약", f"D{row}",
          d["valuation"]["run_rate_fx_normalised"]["scenarios"][2]["upside_vs_market"],
          "요약 기준7 시장가 대비", 1.0, rel=1e-4)

    # ------------------------------------------------------------- 역산
    # The reverse sheet writes each growth rate's whole scenario into one cell.
    # Check the row whose growth equals the optimistic scenario's, against the
    # optimistic value computed by the engine.
    ws = wb["역산"]
    target = d["valuation"]["run_rate_fx_normalised"]["scenarios"][2]
    for row in range(1, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == target["assumptions"]["growth"]:
            check("역산", f"C{row}", target["equity_value"],
                  "역산 25% 행이 낙관 시나리오 값과 일치", BN, rel=1e-4)
            break
    else:
        fails.append("역산 시트에 낙관 시나리오 성장률 행이 없습니다")

    for f in fails:
        print(f"  FAIL  {f}")
    print(f"\n수식 검증: {checked}건, 실패 {len(fails)}건")
    if fails:
        return 1
    print("엑셀의 모든 수식이 분석 엔진과 같은 값을 냅니다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
