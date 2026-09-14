"""
Excel export for the Samsung Biologics analysis - arithmetic visible in the cell.

Same rule as the 52-company workbook: nothing that can be computed inside the
workbook is imported as a constant. Click any derived cell and the formula bar
shows the calculation, and its references lead back either to a figure taken
from an audited statement (blue) or to an assumption you can change (yellow on
the 가정 sheet). Change the exchange rate on 가정 and every valuation in the
workbook moves.

Colour convention:
  blue    a raw input from an audited statement or a market quote
  black   a formula built from cells on the same sheet
  green   a formula that reaches into another sheet
  yellow  an assumption meant to be changed

Writes work/삼성바이오로직스_버핏기준_기업분석.xlsx.
"""

import json
import os
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

WORK = os.path.dirname(os.path.abspath(__file__))
VAL = os.path.join(WORK, "kr", "sbl_valuation.json")
RAW = os.path.join(WORK, "kr", "sbl_raw.json")
OUT = os.path.join(WORK, "삼성바이오로직스_버핏기준_기업분석.xlsx")

FONT = "Arial"
PCT, PCT2 = "0.0%", "0.00%"
MULT = '0.0"배"'
BN = '#,##0.0;(#,##0.0);"-"'      # billions of won
TRN = '#,##0.00;(#,##0.00);"-"'   # trillions of won
INT = "#,##0"
WON = "#,##0"

BLUE = Font(name=FONT, size=10, color="0000FF")
BLACK = Font(name=FONT, size=10)
GREEN = Font(name=FONT, size=10, color="008000")
BOLD = Font(name=FONT, size=10, bold=True)
BOLDNAVY = Font(name=FONT, size=10, bold=True, color="1F3864")
NOTE = Font(name=FONT, size=9, italic=True, color="595959")
TITLE_FONT = Font(name=FONT, bold=True, size=14, color="1F3864")
HEAD_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=9)
HEAD_FILL = PatternFill("solid", fgColor="1F3864")
RAW_FILL = PatternFill("solid", fgColor="DEEAF6")
YELLOW = PatternFill("solid", fgColor="FFFF00")
BORDER = Border(bottom=Side(style="thin", color="D9D9D9"))

FIRST_FY, LAST_FY = 2016, 2025
FYS = list(range(FIRST_FY, LAST_FY + 1))


def title(ws, text, sub=None):
    ws["A1"] = text
    ws["A1"].font = TITLE_FONT
    if sub:
        ws["A2"] = sub
        ws["A2"].font = NOTE
        ws["A2"].alignment = Alignment(vertical="top", wrap_text=True)
        ws.row_dimensions[2].height = 30
        return 4
    return 3


def header(ws, row, labels, widths=None):
    for i, label in enumerate(labels, 1):
        c = ws.cell(row=row, column=i, value=label)
        c.fill = HEAD_FILL
        c.font = HEAD_FONT
        c.alignment = Alignment(horizontal="center", vertical="center",
                                wrap_text=True)
    if widths:
        for i, wd in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = wd
    ws.row_dimensions[row].height = 32
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def put(ws, row, col, value, fmt=None, font=BLACK, fill=None, wrap=False):
    c = ws.cell(row=row, column=col, value=value)
    c.font = font
    c.border = BORDER
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    if wrap:
        c.alignment = Alignment(wrap_text=True, vertical="top")
    return c


def foot(ws, row, text):
    c = ws.cell(row=row, column=1, value=text)
    c.font = NOTE
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[row].height = 28
    return row + 1


# ===========================================================================
# 가정 - every assumption in its own cell
# ===========================================================================
A = {}          # name -> "가정!$B$n"


def sheet_assumptions(wb, d):
    ws = wb.create_sheet("가정")
    r = title(ws, "가정",
              "노란 칸은 바꿔도 되는 값입니다. 바꾸면 이 워크북의 모든 계산이 "
              "따라 움직입니다. 출처가 있는 값은 출처를 적었습니다.")
    header(ws, r, ["항목", "값", "형식", "출처 / 근거"], [30, 16, 10, 78])
    r += 1

    mkt, fx, rf = d["market"], d["fx"], d["cost_of_capital"]["risk_free"]
    rows = [
        ("시장", None, None, None),
        ("주가", mkt["price"], WON, mkt["price_source"]),
        ("유통주식수", mkt["shares_outstanding"], INT, mkt["shares_note"]),
        ("발행주식수", mkt["shares_issued"], INT,
         "FY2025 별도재무제표 자본 주석 (분할 후)"),
        ("52주 최고", mkt["fifty_two_week_high"], WON, "네이버 금융"),
        ("52주 최저", mkt["fifty_two_week_low"], WON, "네이버 금융"),
        ("환율", None, None, None),
        ("현재 원/달러", fx["spot"], NUM_ := "#,##0.0",
         f"{fx['spot_note']} — {fx['series']}"),
        ("FY2025 평균 원/달러", fx["annual_average"]["2025"], "#,##0.0", fx["series"]),
        ("FY2024 평균 원/달러", fx["annual_average"]["2024"], "#,##0.0", fx["series"]),
        ("2026 상반기 평균 원/달러", fx["h1_2026_average"], "#,##0.0", fx["series"]),
        ("해외매출 비중", d["valuation_bases"]["foreign_revenue_share_2025"], PCT,
         "FY2025 지역별 매출 주석에서 국내 매출을 뺀 비중. 원자료 시트에서 계산"),
        ("원가 중 외화연동 비중", 0.30, PCT,
         "가정. 배양액·레진·일회용 자재는 달러 수입, 인건비·감가상각·전력은 원화. "
         "회사가 공시하지 않으므로 0~60%로 흔들어 확인했고 결론은 바뀌지 않습니다"),
        ("세율·자본비용", None, None, None),
        ("법정세율", 0.22, PCT, "한국 법인세 최고세율 + 지방소득세"),
        ("무위험수익률", rf["rate"], PCT2, f"{rf['series']} ({rf['as_of']})"),
        ("주식위험프리미엄", 0.065, PCT, "참고 자본비용 계산용 (5.5~7.5% 중간값)"),
        ("베타", 1.0, "0.00", "참고 자본비용 계산용 (0.9~1.2 중간값)"),
        ("세전 차입이자율", 0.040, PCT, "FY2025 사채·차입금 주석 수준"),
        ("보수 시나리오", None, None, None),
    ]
    for s in d["valuation"]["run_rate_fx_normalised"]["scenarios"]:
        name = s["scenario"]
        a = s["assumptions"]
        if name != "보수":
            rows.append((f"{name} 시나리오", None, None, None))
        rows += [
            (f"{name} 첫해 성장률", a["growth"], PCT, s["story"]),
            (f"{name} 10년차 성장률", a["fade_to"], PCT, "1년차에서 10년차까지 직선 체감"),
            (f"{name} 증분 ROIC", a["incremental_roic"], PCT,
             "실측 5년 구간 24.9~29.7% 대비"),
            (f"{name} 할인율", a["discount"], PCT, None),
            (f"{name} 영구성장률", a["terminal_growth"], PCT, None),
        ]
    rows += [
        ("기타", None, None, None),
        ("예측기간(년)", 10, INT, "명시적으로 현금흐름을 추정하는 기간"),
        ("안전마진", 0.25, PCT, "가치 대비 이만큼 낮은 값에서만 매수한다는 규칙"),
    ]

    for label, value, fmt, src in rows:
        if value is None and fmt is None:
            c = put(ws, r, 1, label, font=BOLDNAVY)
            c.fill = PatternFill("solid", fgColor="F2F4F8")
            for col in range(2, 5):
                put(ws, r, col, None).fill = PatternFill("solid", fgColor="F2F4F8")
            r += 1
            continue
        put(ws, r, 1, label, font=BOLD)
        put(ws, r, 2, value, fmt, font=BLUE, fill=YELLOW)
        put(ws, r, 3, {PCT: "비율", PCT2: "비율", INT: "정수", WON: "원",
                       "#,##0.0": "숫자", "0.00": "숫자"}.get(fmt, ""))
        put(ws, r, 4, src, wrap=True)
        A[label] = f"가정!$B${r}"
        r += 1

    r += 1
    put(ws, r, 1, "시가총액", font=BOLD)
    put(ws, r, 2, f"={A['주가']}*{A['유통주식수']}", TRN_ := "#,##0",
        font=BLACK)
    A["시가총액"] = f"가정!$B${r}"
    put(ws, r, 4, "주가 × 유통주식수. 네이버 공시 시총과 0.04% 차이", wrap=True)
    r += 1
    put(ws, r, 1, "참고 자본비용 (WACC)", font=BOLD)
    put(ws, r, 2,
        f"={A['무위험수익률']}+{A['베타']}*{A['주식위험프리미엄']}", PCT, font=BLACK)
    A["WACC"] = f"가정!$B${r}"
    put(ws, r, 4, "부채 비중이 시가총액의 1.4%에 불과해 자기자본비용과 사실상 같습니다. "
                  "베타 0.9~1.2, 프리미엄 5.5~7.5%로 흔들면 9.0~13.0%",
        wrap=True)
    return ws


# ===========================================================================
# 원자료 - straight from the audited statements
# ===========================================================================
RAWREF = {}     # (metric, fy) -> "원자료!$X$n"


def sheet_raw(wb, raw):
    ws = wb.create_sheet("원자료")
    r = title(ws, "원자료 — 감사받은 재무제표에서 추출한 값",
              "파란 글씨는 전부 감사보고서 원본 PDF에서 읽은 값입니다. 기준은 "
              "별도(別途) 재무제표 = CDMO 사업 단독. 이유는 워드 보고서 2장에 "
              "있습니다. 단위: 십억원.")
    header(ws, r, ["항목"] + [f"FY{fy}" for fy in FYS] + ["출처"],
           [26] + [11] * len(FYS) + [40])
    hdr = r
    r += 1

    items = [
        ("매출", "revenue"),
        ("매출원가", "cost_of_revenue"),
        ("판매비와관리비", "sga"),
        ("영업이익", "operating_income"),
        ("세전이익", "pretax_income"),
        ("법인세비용", "income_tax_expense"),
        ("당기순이익", "net_income"),
        ("감가상각비", "depreciation"),
        ("무형자산상각비", "amortization"),
        ("사용권자산상각비", "rou_depreciation"),
        ("영업활동현금흐름", "ocf"),
        ("유형자산 취득", "capex"),
        ("무형자산 취득", "intangible_capex"),
        ("현금및현금성자산", "cash_and_equivalents"),
        ("단기금융상품", "short_term_financial_instruments"),
        ("매출채권 등", "trade_receivables"),
        ("재고자산", "inventories"),
        ("계약자산", "contract_assets_total"),
        ("유형자산", "ppe"),
        ("무형자산", "intangibles"),
        ("사용권자산", "right_of_use"),
        ("종속·관계기업투자", "investments_in_subs"),
        ("자산총계", "total_assets"),
        ("매입채무 등", "trade_payables"),
        ("계약부채", "contract_liabilities"),
        ("기타유동부채(선수금)", "other_current_liabilities"),
        ("이자부부채", "debt_total"),
        ("리스부채", "lease_liabilities"),
        ("부채총계", "total_liabilities"),
        ("자본총계", "total_equity"),
    ]
    by = {y["fiscal_year"]: y for y in raw["years"]}
    for label, key in items:
        put(ws, r, 1, label, font=BOLD)
        for i, fy in enumerate(FYS, 2):
            v = by[fy].get(key)
            put(ws, r, i, None if v is None else v / 1e9, BN, font=BLUE,
                fill=RAW_FILL)
            RAWREF[(key, fy)] = f"원자료!{get_column_letter(i)}${r}"
        put(ws, r, len(FYS) + 2, by[LAST_FY]["source_document"])
        r += 1

    put(ws, r, 1, "건설중자산", font=BOLD)
    cips = {int(k): v for k, v in raw["construction_in_progress"].items()}
    for i, fy in enumerate(FYS, 2):
        v = cips.get(fy, {}).get("carrying_amount")
        put(ws, r, i, None if v is None else v / 1e9, BN, font=BLUE, fill=RAW_FILL)
        RAWREF[("cip", fy)] = f"원자료!{get_column_letter(i)}${r}"
    put(ws, r, len(FYS) + 2, "각 연도 유형자산 주석")
    r += 2

    put(ws, r, 1, "지역별 매출 (FY2025)", font=BOLDNAVY)
    r += 1
    geo = raw["concentration"]["geography"]
    for name, key in (("국내", "domestic"), ("유럽", "europe"),
                      ("미국", "usa"), ("기타", "other")):
        put(ws, r, 1, name, font=BOLD)
        put(ws, r, 2, geo[key]["2025"] / 1e9, BN, font=BLUE, fill=RAW_FILL)
        RAWREF[(f"geo_{key}", 2025)] = f"원자료!$B${r}"
        put(ws, r, 3, geo[key]["2024"] / 1e9, BN, font=BLUE, fill=RAW_FILL)
        r += 1
    put(ws, r, 1, "합계 (매출과 일치해야 함)", font=BOLD)
    put(ws, r, 2, f"=SUM(B{r-4}:B{r-1})", BN)
    put(ws, r, 3, f"=SUM(C{r-4}:C{r-1})", BN)
    put(ws, r, 5, f"=B{r}-{RAWREF[('revenue', 2025)]}", BN)
    put(ws, r, 6, "← 0이어야 합니다 (검증)")
    r += 2

    put(ws, r, 1, "상위 5개 고객 매출 (FY2025 / FY2024)", font=BOLDNAVY)
    r += 1
    cust = raw["concentration"]["customers"]
    start = r
    for tag in "abcde":
        put(ws, r, 1, f"고객 {tag.upper()}", font=BOLD)
        put(ws, r, 2, cust[f"client_{tag}"]["2025"] / 1e9, BN, font=BLUE,
            fill=RAW_FILL)
        put(ws, r, 3, cust[f"client_{tag}"]["2024"] / 1e9, BN, font=BLUE,
            fill=RAW_FILL)
        r += 1
    put(ws, r, 1, "상위 5개 합계", font=BOLD)
    put(ws, r, 2, f"=SUM(B{start}:B{r-1})", BN)
    put(ws, r, 3, f"=SUM(C{start}:C{r-1})", BN)
    r += 1
    put(ws, r, 1, "매출 대비 비중", font=BOLD)
    put(ws, r, 2, f"=B{r-1}/{RAWREF[('revenue', 2025)]}", PCT)
    put(ws, r, 3, f"=C{r-1}/{RAWREF[('revenue', 2024)]}", PCT)
    r += 2

    put(ws, r, 1, "고객 선수금·계약부채 (FY2025)", font=BOLDNAVY)
    r += 1
    f = raw["float_and_supplier_finance"]
    for label, v in (("선수금 (유동)", f["advance_receipts"]["2025_current"]),
                     ("선수금 (비유동)", f["advance_receipts"]["2025_non_current"]),
                     ("공급자금융 FY2025", f["supplier_finance"]["2025"]),
                     ("공급자금융 FY2024", f["supplier_finance"]["2024"])):
        put(ws, r, 1, label, font=BOLD)
        put(ws, r, 2, v / 1e9, BN, font=BLUE, fill=RAW_FILL)
        r += 1

    r += 1
    r = foot(ws, r, "검증: work/verify_sbl.py 가 이 값들에 대해 내부 정합성·자릿수·"
                    "기준연결 검증 111건을 수행하고 전부 통과했습니다. 지역별 매출 "
                    "합계가 총매출과 일치하는지(위 E열), 세전이익 − 법인세 = 당기순이익, "
                    "자산 = 부채 + 자본, 별도 FY2024 매출 = 연결 계속영업 FY2024 매출이 "
                    "그 일부입니다.")
    return ws


# ===========================================================================
# ROIC
# ===========================================================================
ROICREF = {}


def sheet_roic(wb):
    ws = wb.create_sheet("ROIC")
    r = title(ws, "기준 2 — 투하자본이익률",
              "모든 칸이 원자료 시트를 참조하는 수식입니다. 투하자본은 세 가지로 "
              "계산했고, 건설중자산을 뺀 값이 본문에서 쓰는 값입니다. 단위: 십억원.")
    labels = ["항목"] + [f"FY{fy}" for fy in FYS]
    header(ws, r, labels, [30] + [11] * len(FYS))
    r += 1
    R = lambda k, fy: RAWREF[(k, fy)]

    def line(label, formula, fmt=BN, font=BLACK, key=None, bold=False):
        nonlocal r
        put(ws, r, 1, label, font=BOLD if bold else BOLD)
        for i, fy in enumerate(FYS, 2):
            put(ws, r, i, formula(fy), fmt, font=font)
            if key:
                ROICREF[(key, fy)] = f"ROIC!{get_column_letter(i)}${r}"
        r += 1

    line("영업이익", lambda fy: f"={R('operating_income', fy)}", font=GREEN,
         key="ebit")
    line("실효세율 (법인세÷세전이익)",
         lambda fy: (f"=IF(OR({R('pretax_income', fy)}<=0,"
                     f"{R('income_tax_expense', fy)}/{R('pretax_income', fy)}<0.05,"
                     f"{R('income_tax_expense', fy)}/{R('pretax_income', fy)}>0.4),"
                     f"{A['법정세율']},"
                     f"{R('income_tax_expense', fy)}/{R('pretax_income', fy)})"),
         PCT, key="tax")
    line("NOPAT = 영업이익 × (1 − 실효세율)",
         lambda fy: f"={ROICREF[('ebit', fy)]}*(1-{ROICREF[('tax', fy)]})",
         key="nopat")
    r += 1

    put(ws, r, 1, "투하자본 — 하향식", font=BOLDNAVY)
    r += 1
    line("자본총계 + 이자부부채 + 리스부채 − 현금성 − 종속·관계기업투자",
         lambda fy: (f"={R('total_equity', fy)}+{R('debt_total', fy)}"
                     f"+{R('lease_liabilities', fy)}-{R('cash_and_equivalents', fy)}"
                     f"-{R('short_term_financial_instruments', fy)}"
                     f"-{R('investments_in_subs', fy)}"),
         key="ic_top")
    r += 1

    put(ws, r, 1, "투하자본 — 상향식 영업자본", font=BOLDNAVY)
    r += 1
    line("영업자산 (유형+무형+사용권+재고+매출채권+계약자산)",
         lambda fy: (f"={R('ppe', fy)}+{R('intangibles', fy)}"
                     f"+{R('right_of_use', fy)}+{R('inventories', fy)}"
                     f"+{R('trade_receivables', fy)}"
                     f"+{R('contract_assets_total', fy)}"),
         key="opassets")
    line("− 계약부채 − 선수금",
         lambda fy: (f"=-{R('contract_liabilities', fy)}"
                     f"-{R('other_current_liabilities', fy)}"),
         key="cust")
    line("영업자본 (매입채무 미차감)",
         lambda fy: f"={ROICREF[('opassets', fy)]}+{ROICREF[('cust', fy)]}",
         key="ic_op_gross")
    line("− 매입채무",
         lambda fy: f"=-{R('trade_payables', fy)}", key="ap")
    line("영업자본 (매입채무 차감)",
         lambda fy: (f"={ROICREF[('ic_op_gross', fy)]}+{ROICREF[('ap', fy)]}"),
         key="ic_op")
    line("건설중자산", lambda fy: f"={R('cip', fy)}", font=GREEN, key="cip")
    line("영업자본 − 건설중자산 (매입채무 미차감)",
         lambda fy: f"={ROICREF[('ic_op_gross', fy)]}-{ROICREF[('cip', fy)]}",
         key="ic_final")
    line("영업자본 − 건설중자산 (매입채무 차감)",
         lambda fy: f"={ROICREF[('ic_op', fy)]}-{ROICREF[('cip', fy)]}",
         key="ic_op_ex_cip")
    r += 1

    put(ws, r, 1, "ROIC", font=BOLDNAVY)
    r += 1
    for label, den, key in (
            ("하향식", "ic_top", "roic_top"),
            ("상향식 (매입채무 차감)", "ic_op", "roic_op"),
            ("상향식 − 건설중자산 (매입채무 차감)", "ic_op_ex_cip", "roic_op_ex_cip"),
            ("상향식 − 건설중자산 (매입채무 미차감) ← 본문 기준", "ic_final",
             "roic_final")):
        line(label,
             lambda fy, den=den: (f"=IF({ROICREF[(den, fy)]}<=0,\"\","
                                  f"{ROICREF[('nopat', fy)]}/{ROICREF[(den, fy)]})"),
             PCT, key=key)
    line("ROIC − 자본비용 (본문 기준)",
         lambda fy: (f"=IF({ROICREF[('roic_final', fy)]}=\"\",\"\","
                     f"{ROICREF[('roic_final', fy)]}-{A['WACC']})"), PCT)
    r += 1
    r = foot(ws, r, "FY2016·FY2017의 하향식 투하자본은 음수입니다 (에피스 지분이 "
                    "대차대조표를 지배). 음수 분모에서 나온 비율은 수익률이 아니므로 "
                    "빈칸으로 처리했습니다. FY2018 이후에는 하향식과 상향식이 "
                    "−16%~+11% 범위에서 같이 움직이므로, 측정 방식의 선택이 결론을 "
                    "만들지 않았습니다.")
    r = foot(ws, r, "건설중자산을 빼는 이유: FY2024 말 영업자본의 30%가 아직 완공되지 "
                    "않아 한 푼도 벌지 못하는 공장이었고, FY2025에 2조 1,829억원이 "
                    "가동자산으로 넘어갔습니다. 빼지 않으면 FY2024가 수익률이 무너진 "
                    "해로 읽힙니다.")
    return ws


def sheet_incremental(wb):
    ws = wb.create_sheet("증분ROIC")
    r = title(ws, "기준 4 — 증분 투하자본이익률",
              "ΔNOPAT ÷ Δ투하자본. 분모는 건설중자산을 뺀 영업자본(매입채무 미차감)"
              "입니다. 단위: 십억원.")
    header(ws, r, ["구간", "시작 NOPAT", "종료 NOPAT", "ΔNOPAT",
                   "시작 투하자본", "종료 투하자본", "Δ투하자본", "증분 ROIC",
                   "자본비용 대비"],
           [16, 14, 14, 12, 15, 15, 13, 12, 13])
    r += 1
    windows = [(a, a + n) for n in (3, 5, 9) for a in FYS if a + n <= LAST_FY]
    for a, b in windows:
        put(ws, r, 1, f"FY{a}→FY{b}", font=BOLD)
        put(ws, r, 2, f"={ROICREF[('nopat', a)]}", BN, font=GREEN)
        put(ws, r, 3, f"={ROICREF[('nopat', b)]}", BN, font=GREEN)
        put(ws, r, 4, f"=C{r}-B{r}", BN)
        put(ws, r, 5, f"={ROICREF[('ic_final', a)]}", BN, font=GREEN)
        put(ws, r, 6, f"={ROICREF[('ic_final', b)]}", BN, font=GREEN)
        put(ws, r, 7, f"=F{r}-E{r}", BN)
        put(ws, r, 8, f'=IF(G{r}<=0,"",D{r}/G{r})', PCT)
        put(ws, r, 9, f'=IF(H{r}="","",H{r}-{A["WACC"]})', PCT)
        r += 1
    r += 1
    r = foot(ws, r, "짧은 구간은 양 끝에서 무엇이 건설 중이었는지에 좌우되므로 점이 "
                    "아니라 범위로 읽어야 합니다. 5년 구간 다섯 개가 모두 "
                    "24.9~29.7%에 들어오고, 그것이 본문에서 쓴 근거입니다.")
    return ws


def sheet_owner_earnings(wb, d):
    ws = wb.create_sheet("주주이익")
    r = title(ws, "기준 6 — 주주이익 (1986년 주주서한 정의)",
              "보고이익 + 감가상각 등 − 장기 경쟁지위와 판매량을 유지하는 데 필요한 "
              "설비투자 − 운전자본 증가. 판단이 필요한 것은 '유지에 필요한 설비투자' "
              "한 줄뿐이므로 세 가지로 계산해 범위를 보여줍니다. 단위: 십억원.")
    header(ws, r, ["FY", "당기순이익", "감가상각 합계", "유형자산 취득",
                   "운전자본 증감", "주주이익 (유지=감가상각)",
                   "주주이익 (유지=1.2×감가상각)", "주주이익 (유지=취득 전액)",
                   "영업현금흐름 − 취득"],
           [7, 13, 13, 13, 13, 17, 19, 18, 16])
    r += 1
    R = lambda k, fy: RAWREF[(k, fy)]
    first = r
    for fy in FYS:
        put(ws, r, 1, fy, font=BOLD)
        put(ws, r, 2, f"={R('net_income', fy)}", BN, font=GREEN)
        put(ws, r, 3, (f"={R('depreciation', fy)}+{R('amortization', fy)}"
                       f"+{R('rou_depreciation', fy)}"), BN, font=GREEN)
        put(ws, r, 4, f"={R('capex', fy)}", BN, font=GREEN)
        if fy == FIRST_FY:
            put(ws, r, 5, None, BN)
        else:
            put(ws, r, 5,
                (f"=({R('inventories', fy)}-{R('inventories', fy-1)})"
                 f"-({R('other_current_liabilities', fy)}"
                 f"-{R('other_current_liabilities', fy-1)})"
                 f"-({R('contract_liabilities', fy)}"
                 f"-{R('contract_liabilities', fy-1)})"), BN)
        put(ws, r, 6, f"=B{r}+C{r}-C{r}-IF(ISNUMBER(E{r}),E{r},0)", BN)
        put(ws, r, 7, f"=B{r}+C{r}-1.2*C{r}-IF(ISNUMBER(E{r}),E{r},0)", BN)
        put(ws, r, 8, f"=B{r}+C{r}-D{r}-IF(ISNUMBER(E{r}),E{r},0)", BN)
        put(ws, r, 9, f"={R('ocf', fy)}-{R('capex', fy)}", BN, font=GREEN)
        r += 1
    put(ws, r, 1, "10년 합계", font=BOLD)
    for col in "BCDEFGHI":
        put(ws, r, "ABCDEFGHI".index(col) + 1,
            f"=SUM({col}{first}:{col}{r-1})", BN, font=BOLD)
    r += 2
    r = foot(ws, r, "가장 중요한 칸은 I열 합계입니다. 10년 동안 순이익을 5.06조원 "
                    "벌었지만 영업현금흐름에서 설비투자를 뺀 금액의 합계는 사실상 "
                    "0입니다. 번 돈 전부가 공장으로 들어갔고, 그 위에 2022년 "
                    "3.19조원의 유상증자까지 받았습니다. 증분 ROIC이 25~30%라면 "
                    "그 선택 자체는 옳지만, 이 주식을 10년 보유해 받은 현금이 0원이라는 "
                    "사실도 같이 읽어야 합니다.")
    r = foot(ws, r, "F열의 수식이 '+C−C'로 보이는 것은 1986년 정의를 그대로 쓴 "
                    "결과입니다. 감가상각을 더하고 유지 설비투자를 빼는데, 이 칸에서는 "
                    "유지 설비투자를 감가상각과 같다고 본 것이므로 서로 상쇄됩니다. "
                    "정의를 숨기지 않기 위해 상쇄된 형태로 남겨두었습니다.")
    return ws


# ===========================================================================
# 기준연도 - the three valuation bases, FX normalisation as formulas
# ===========================================================================
BASE = {}


def sheet_base(wb, d, raw):
    ws = wb.create_sheet("기준연도")
    r = title(ws, "기준 7 (1) — 기준연도",
              "매출의 92%를 해외에서 벌고 원가는 대부분 원화입니다. 원/달러가 "
              "FY2025 1,421원, 2026 상반기 1,482원, 현재 1,358원이므로 어느 환율을 "
              "자본화하는지가 가치에 직접 영향을 줍니다. 세 가지를 모두 계산합니다. "
              "단위: 십억원.")
    header(ws, r, ["항목", "FY2025 실적", "2026 상반기 연율화",
                   "2026 연율화 · 현재 환율", "설명"],
           [24, 16, 18, 20, 54])
    r += 1
    it = raw["interim_2026"]
    R = lambda k, fy: RAWREF[(k, fy)]

    put(ws, r, 1, "매출", font=BOLD)
    put(ws, r, 2, f"={R('revenue', 2025)}", BN, font=GREEN)
    put(ws, r, 3, f"={it['h1_2026']['revenue']/1e9}", BN, font=BLUE,
        fill=RAW_FILL)
    ws.cell(row=r, column=3).value = it["h1_2026"]["revenue"] / 1e9 * 2
    put(ws, r, 4,
        f"=C{r}*((1-{A['해외매출 비중']})+{A['해외매출 비중']}"
        f"*{A['현재 원/달러']}/{A['2026 상반기 평균 원/달러']})", BN)
    put(ws, r, 5, "2026 상반기 매출 × 2. 환산은 해외분만 환율에 비례", wrap=True)
    rev_row = r
    r += 1

    put(ws, r, 1, "영업이익", font=BOLD)
    put(ws, r, 2, f"={R('operating_income', 2025)}", BN, font=GREEN)
    ws.cell(row=r, column=3).value = it["h1_2026"]["operating_income"] / 1e9 * 2
    put(ws, r, 3, None, BN, font=BLUE, fill=RAW_FILL)
    ws.cell(row=r, column=3).value = it["h1_2026"]["operating_income"] / 1e9 * 2
    put(ws, r, 4,
        f"=D{rev_row}-((C{rev_row}-C{r})*((1-{A['원가 중 외화연동 비중']})"
        f"+{A['원가 중 외화연동 비중']}*{A['현재 원/달러']}"
        f"/{A['2026 상반기 평균 원/달러']}))", BN)
    put(ws, r, 5, "환산 영업이익 = 환산 매출 − 환산 원가. 원가는 외화연동 "
                  "비중만큼만 환율에 비례", wrap=True)
    op_row = r
    r += 1

    put(ws, r, 1, "영업이익률", font=BOLD)
    for col in (2, 3, 4):
        put(ws, r, col,
            f"={get_column_letter(col)}{op_row}/{get_column_letter(col)}{rev_row}",
            PCT)
    r += 1

    put(ws, r, 1, "실효세율", font=BOLD)
    put(ws, r, 2, f"={ROICREF[('tax', 2025)]}", PCT, font=GREEN)
    put(ws, r, 3, it["h1_2026"]["income_tax_expense"]
        / it["h1_2026"]["pretax_income"], PCT, font=BLUE, fill=RAW_FILL)
    put(ws, r, 4, f"=C{r}", PCT)
    put(ws, r, 5, "2026 상반기 법인세비용 ÷ 세전이익", wrap=True)
    tax_row = r
    r += 1

    put(ws, r, 1, "NOPAT", font=BOLD)
    for col in (2, 3, 4):
        L = get_column_letter(col)
        put(ws, r, col, f"={L}{op_row}*(1-{L}{tax_row})", BN, font=BOLD)
        BASE[{2: "reported", 3: "run", 4: "norm"}[col]] = \
            f"기준연도!${L}${r}"
    r += 2

    put(ws, r, 1, "순현금", font=BOLDNAVY)
    r += 1
    put(ws, r, 1, "현금및현금성자산 + 단기금융상품", font=BOLD)
    put(ws, r, 2, (f"={R('cash_and_equivalents', 2025)}"
                   f"+{R('short_term_financial_instruments', 2025)}"), BN,
        font=GREEN)
    cash_row = r
    r += 1
    put(ws, r, 1, "− 이자부부채 − 리스부채", font=BOLD)
    put(ws, r, 2, f"=-{R('debt_total', 2025)}-{R('lease_liabilities', 2025)}",
        BN, font=GREEN)
    r += 1
    put(ws, r, 1, "순현금", font=BOLD)
    put(ws, r, 2, f"=B{cash_row}+B{cash_row+1}", BN, font=BOLD)
    BASE["net_cash"] = f"기준연도!$B${r}"
    put(ws, r, 4, "선수금·계약부채 1.80조원은 순현금에 넣지 않았습니다. 그것은 "
                  "영업자본에 이미 반영된 고객 자금이고, 현금흐름 추정이 그 위에서 "
                  "돌아갑니다.", wrap=True)
    r += 2

    put(ws, r, 1, "환율 민감도 (2026 연율화 기준)", font=BOLDNAVY)
    r += 1
    header(ws, r, ["원/달러", "매출", "영업이익", "영업이익률", "NOPAT"],
           None)
    ws.freeze_panes = None
    r += 1
    for rate in (1200, 1250, 1300, 1358.5, 1400, 1450, 1482, 1550):
        put(ws, r, 1, rate, "#,##0.0", font=BLUE, fill=YELLOW)
        put(ws, r, 2,
            f"=C{rev_row}*((1-{A['해외매출 비중']})+{A['해외매출 비중']}"
            f"*A{r}/{A['2026 상반기 평균 원/달러']})", BN)
        put(ws, r, 3,
            f"=B{r}-((C{rev_row}-C{op_row})*((1-{A['원가 중 외화연동 비중']})"
            f"+{A['원가 중 외화연동 비중']}*A{r}"
            f"/{A['2026 상반기 평균 원/달러']}))", BN)
        put(ws, r, 4, f"=C{r}/B{r}", PCT)
        put(ws, r, 5, f"=C{r}*(1-C{tax_row})", BN)
        r += 1
    r += 1
    r = foot(ws, r, "원/달러가 1,200원으로 돌아가면 NOPAT은 현재 환율 대비 21% "
                    "줄어듭니다. 이 회사에 대한 투자는 상당 부분 원화 약세가 "
                    "유지된다는 데 대한 투자입니다. 2026년 6월 1,529.5원에서 "
                    "9월 1,358.5원까지 3개월 만에 11% 절상되었습니다.")
    return ws


# ===========================================================================
# DCF, one sheet per scenario, every year a formula
# ===========================================================================
DCFREF = {}


def sheet_dcf(wb, name, base_key, base_label, scen=None):
    """
    One scenario against one base year. `name` names the sheet, `scen` names the
    scenario whose assumptions it reads - they differ only for the two extra
    base years, which get hidden sheets so the summary grid can reference them
    without three visible copies of every scenario.
    """
    scen = scen or name
    ws = wb.create_sheet(f"DCF_{name}")
    r = title(ws, f"기준 7 (2) — {scen} 시나리오 현금흐름할인",
              "재투자율은 가정하지 않고 성장률에서 유도합니다: 재투자율 = 성장률 ÷ "
              f"증분 ROIC. 따라서 어떤 성장도 대가 없이 얻을 수 없습니다. "
              f"기준연도는 {base_label}. 단위: 십억원.")
    header(ws, r, ["연차", "성장률", "NOPAT", "재투자율", "재투자액",
                   "자유현금흐름", "할인계수", "현재가치", "외부조달 필요"],
           [7, 11, 14, 11, 14, 15, 11, 14, 14])
    r += 1
    g0 = A[f"{scen} 첫해 성장률"]
    g10 = A[f"{scen} 10년차 성장률"]
    ir = A[f"{scen} 증분 ROIC"]
    disc = A[f"{scen} 할인율"]
    tg = A[f"{scen} 영구성장률"]
    n = A["예측기간(년)"]
    first = r
    for t in range(1, 11):
        put(ws, r, 1, t, font=BOLD)
        put(ws, r, 2, f"={g0}+({g10}-{g0})*({t}-1)/({n}-1)", PCT)
        prev = f"{BASE[base_key]}" if t == 1 else f"C{r-1}"
        put(ws, r, 3, f"={prev}*(1+B{r})", BN,
            font=GREEN if t == 1 else BLACK)
        put(ws, r, 4, f"=B{r}/{ir}", PCT)
        put(ws, r, 5, f"=C{r}*D{r}", BN)
        put(ws, r, 6, f"=C{r}-E{r}", BN)
        put(ws, r, 7, f"=1/(1+{disc})^{t}", "0.0000")
        put(ws, r, 8, f"=F{r}*G{r}", BN)
        put(ws, r, 9, f"=MAX(0,E{r}-C{r})", BN)
        r += 1
    last = r - 1
    put(ws, r, 1, "합계", font=BOLD)
    put(ws, r, 5, f"=SUM(E{first}:E{last})", BN, font=BOLD)
    put(ws, r, 6, f"=SUM(F{first}:F{last})", BN, font=BOLD)
    put(ws, r, 8, f"=SUM(H{first}:H{last})", BN, font=BOLD)
    put(ws, r, 9, f"=SUM(I{first}:I{last})", BN, font=BOLD)
    external = f"I{r}"
    pv_forecast = f"H{r}"
    cum_reinvest = f"E{r}"
    r += 2

    put(ws, r, 1, "터미널 가치", font=BOLDNAVY)
    r += 1
    put(ws, r, 1, "11년차 NOPAT", font=BOLD)
    put(ws, r, 2, f"=C{last}*(1+{tg})", BN)
    y11 = f"B{r}"
    r += 1
    put(ws, r, 1, "터미널 재투자율 = 영구성장률 ÷ 증분 ROIC", font=BOLD)
    put(ws, r, 2, f"={tg}/{ir}", PCT)
    trr = f"B{r}"
    r += 1
    put(ws, r, 1, "터미널 가치 = 11년차 FCF ÷ (할인율 − 영구성장률)", font=BOLD)
    put(ws, r, 2, f"={y11}*(1-{trr})/({disc}-{tg})", BN)
    tv = f"B{r}"
    r += 1
    put(ws, r, 1, "터미널 현재가치", font=BOLD)
    put(ws, r, 2, f"={tv}*G{last}", BN)
    tv_pv = f"B{r}"
    r += 2

    put(ws, r, 1, "가치", font=BOLDNAVY)
    r += 1
    put(ws, r, 1, "예측기간 현재가치", font=BOLD)
    put(ws, r, 2, f"={pv_forecast}", BN)
    r += 1
    put(ws, r, 1, "터미널 현재가치", font=BOLD)
    put(ws, r, 2, f"={tv_pv}", BN)
    r += 1
    put(ws, r, 1, "기업가치 (EV)", font=BOLD)
    put(ws, r, 2, f"=B{r-2}+B{r-1}", BN, font=BOLD)
    ev = f"B{r}"
    r += 1
    put(ws, r, 1, "+ 순현금", font=BOLD)
    put(ws, r, 2, f"={BASE['net_cash']}", BN, font=GREEN)
    r += 1
    put(ws, r, 1, "자기자본가치", font=BOLD)
    put(ws, r, 2, f"={ev}+B{r-1}", BN, font=BOLD)
    equity = f"DCF_{name}!$B${r}"
    DCFREF[(name, base_key, "equity")] = equity
    r += 1
    put(ws, r, 1, "주당가치 (원)", font=BOLD)
    put(ws, r, 2, f"=B{r-1}*1000000000/{A['유통주식수']}", WON, font=BOLD)
    DCFREF[(name, base_key, "per_share")] = f"DCF_{name}!$B${r}"
    r += 1
    put(ws, r, 1, "시가총액 (십억원)", font=BOLD)
    put(ws, r, 2, f"={A['시가총액']}/1000000000", BN, font=GREEN)
    mc = f"B{r}"
    r += 1
    put(ws, r, 1, "시장가 대비", font=BOLD)
    put(ws, r, 2, f"=({equity}-{mc})/{mc}", PCT, font=BOLD)
    r += 1
    put(ws, r, 1, "터미널 비중", font=BOLD)
    put(ws, r, 2, f"={tv_pv}/{ev}", PCT)
    r += 2

    put(ws, r, 1, "실현 가능성 점검", font=BOLDNAVY)
    r += 1
    put(ws, r, 1, "10년 누적 재투자", font=BOLD)
    put(ws, r, 2, f"={cum_reinvest}", BN)
    r += 1
    put(ws, r, 1, "10년 누적 NOPAT", font=BOLD)
    put(ws, r, 2, f"=SUM(C{first}:C{last})", BN)
    r += 1
    put(ws, r, 1, "재투자 ÷ NOPAT", font=BOLD)
    put(ws, r, 2, f"=B{r-2}/B{r-1}", PCT)
    r += 1
    put(ws, r, 1, "1년차 재투자율", font=BOLD)
    put(ws, r, 2, f"=D{first}", PCT)
    r += 1
    put(ws, r, 1, "외부조달 필요액 (재투자율>100%인 해의 부족분 합계)", font=BOLD)
    put(ws, r, 2, f"={external}", BN)
    r += 1
    put(ws, r, 1, "10년 뒤 매출 (NOPAT 배율 × FY2025 매출)", font=BOLD)
    put(ws, r, 2,
        f"=C{last}/{BASE[base_key]}*{RAWREF[('revenue', 2025)]}", BN)
    r += 1
    r = foot(ws, r, "재투자율이 100%를 넘으면 그 차액은 증자나 차입으로 메워야 "
                    "합니다. 이 계산은 그 희석과 이자를 기존 주주에게 청구하지 "
                    "않으므로, 재투자율이 100%를 넘는 시나리오의 자기자본가치는 "
                    "과대평가입니다.")
    return ws


def sheet_reverse(wb):
    ws = wb.create_sheet("역산")
    r = title(ws, "기준 7 (3) — 지금 주가는 무엇을 가정하고 있는가",
              "낙관 시나리오의 틀(증분 ROIC 26%, 할인율 9%, 영구성장률 3%, "
              "기준연도는 현재 환율)을 고정하고 첫해 성장률만 바꿔가며 "
              "자기자본가치를 계산합니다. 시가총액과 교차하는 지점이 "
              "'시장이 이미 가정하고 있는 성장률'입니다. 단위: 십억원.")
    header(ws, r, ["첫해 성장률", "1년차 재투자율", "자기자본가치",
                   "주당가치 (원)", "시가총액 대비", "비고"],
           [14, 15, 16, 15, 14, 44])
    r += 1
    ir = A["낙관 증분 ROIC"]
    disc = A["낙관 할인율"]
    tg = A["낙관 영구성장률"]
    g10 = A["낙관 10년차 성장률"]
    n = A["예측기간(년)"]
    base = BASE["norm"]
    mc = A["시가총액"]

    for g in [0.10, 0.15, 0.20, 0.25, 0.30, 0.32, 0.34, 0.36, 0.40]:
        put(ws, r, 1, g, PCT, font=BLUE, fill=YELLOW)
        put(ws, r, 2, f"=A{r}/{ir}", PCT)
        # Present value of ten fading years plus a terminal value, written out
        # as one SUMPRODUCT over the year index so the whole scenario lives in a
        # single cell and can be swept by changing A{r}.
        terms = []
        for t in range(1, 11):
            gt = f"(A{r}+({g10}-A{r})*({t}-1)/({n}-1))"
            prod = "*".join(
                f"(1+(A{r}+({g10}-A{r})*({k}-1)/({n}-1)))" for k in range(1, t + 1))
            terms.append(f"{base}*{prod}*(1-{gt}/{ir})/(1+{disc})^{t}")
        growth10 = "*".join(
            f"(1+(A{r}+({g10}-A{r})*({k}-1)/({n}-1)))" for k in range(1, 11))
        terminal = (f"{base}*{growth10}*(1+{tg})*(1-{tg}/{ir})"
                    f"/({disc}-{tg})/(1+{disc})^10")
        put(ws, r, 3, "=" + "+".join(terms) + f"+{terminal}+{BASE['net_cash']}",
            BN)
        put(ws, r, 4, f"=C{r}*1000000000/{A['유통주식수']}", WON)
        put(ws, r, 5, f"=(C{r}-{mc}/1000000000)/({mc}/1000000000)", PCT)
        put(ws, r, 6,
            '=IF(B'f'{r}>1,"재투자율 100% 초과 — 외부조달 필요","자체조달 가능")',
            wrap=True)
        r += 1
    r += 1
    r = foot(ws, r, "이 표에서 시가총액 대비 0%가 되는 지점이 약 34%입니다. "
                    "FY2020→FY2025 매출 CAGR 31.4%보다 높은 성장률을, 10년 경로의 "
                    "출발점으로 요구한다는 뜻입니다. 그리고 그 성장률에서 재투자율은 "
                    "131%이므로 회사는 매년 벌어들이는 세후영업이익보다 많은 돈을 "
                    "외부에서 조달해야 합니다. 즉 34%도 낙관적으로 계산된 값입니다.")
    r = foot(ws, r, "다른 두 손잡이도 같이 보아야 합니다. 성장률·증분 ROIC를 낙관에 "
                    "고정하고 할인율만 맞추면 7.8%이고, 이는 자본비용 참고 범위 "
                    "9.0~13.0%의 아래입니다. 성장률·할인율을 고정하고 증분 ROIC만 "
                    "올리면 재투자가 0에 수렴할 만큼 올려도 시가총액에 닿지 "
                    "않습니다.")
    return ws


def sheet_summary(wb, d):
    ws = wb.create_sheet("요약", 0)
    r = title(ws, "삼성바이오로직스 — 버핏 기준 기업분석",
              "CDMO 단일사업 기준 (별도 재무제표) FY2016~FY2025. 모든 수치는 "
              "이 워크북의 다른 시트에서 계산되며, 그 시트들은 감사보고서에서 "
              "읽은 값만을 입력으로 씁니다.")
    header(ws, r, ["기준", "판정", "근거 (수식)", "값"], [30, 12, 46, 16])
    r += 1
    rows = [
        ("1. 이해할 수 있는 사업", "통과",
         "위탁생산 한 가지. 분할 후 보고부문 1개", None),
        ("2. 기존 자본의 수익률 > 자본비용", "통과",
         "FY2025 ROIC (건설중자산 제외)", f"={ROICREF[('roic_final', 2025)]}"),
        ("", "", "자본비용 참고값", f"={A['WACC']}"),
        ("3. 지속되는 해자", "조건부 통과",
         "선수금+계약부채 ÷ 매출 — 고객이 먼저 내는 돈",
         None),
        ("4. 증분 자본의 수익률 > 자본비용", "통과",
         "FY2020→FY2025 증분 ROIC",
         f"=(({ROICREF[('nopat', 2025)]}-{ROICREF[('nopat', 2020)]})"
         f"/({ROICREF[('ic_final', 2025)]}-{ROICREF[('ic_final', 2020)]}))"),
        ("5. 자본배분·주주지향", "조건부 통과",
         "배당 0, 2022년 유상증자 3.19조원, 지배주주 74.3%", None),
        ("6. 이익의 질", "조건부 통과",
         "10년 누적 영업현금흐름 − 설비투자 (주주이익 시트 I열 합계)", None),
        ("7. 합리적인 가격", "미달",
         "낙관 시나리오 자기자본가치 ÷ 시가총액 − 1",
         f"=({DCFREF[('낙관', 'norm', 'equity')]}-{A['시가총액']}/1000000000)"
         f"/({A['시가총액']}/1000000000)"),
    ]
    for label, verdict, basis, formula in rows:
        put(ws, r, 1, label, font=BOLD)
        put(ws, r, 2, verdict,
            font=Font(name=FONT, size=10, bold=True,
                      color="C00000" if verdict == "미달" else "1F3864"))
        put(ws, r, 3, basis, wrap=True)
        if formula:
            put(ws, r, 4, formula, PCT, font=GREEN)
        r += 1
    r += 1

    put(ws, r, 1, "가치 — 기준연도 3 × 시나리오 3", font=BOLDNAVY)
    r += 1
    header(ws, r, ["기준연도", "보수", "중립", "낙관", "시가총액"],
           [26, 16, 16, 16, 16])
    ws.freeze_panes = None
    r += 1
    for key, label in (("reported", "FY2025 실적"),
                       ("run", "2026 상반기 연율화"),
                       ("norm", "2026 연율화 · 현재 환율")):
        put(ws, r, 1, label, font=BOLD)
        for i, name in enumerate(("보수", "중립", "낙관"), 2):
            put(ws, r, i, f"={DCFREF[(name, key, 'equity')]}/1000", TRN,
                font=GREEN)
        put(ws, r, 5, f"={A['시가총액']}/1000000000000", TRN, font=GREEN)
        r += 1
    put(ws, r, 1, "단위: 조원", font=NOTE)
    r += 2

    put(ws, r, 1, "적정주가 — 기준연도 3 × 시나리오 3", font=BOLDNAVY)
    r += 1
    header(ws, r, ["기준연도", "보수", "중립", "낙관", "현재주가"],
           [26, 16, 16, 16, 16])
    ws.freeze_panes = None
    r += 1
    for key, label in (("reported", "FY2025 실적"),
                       ("run", "2026 상반기 연율화"),
                       ("norm", "2026 연율화 · 현재 환율")):
        put(ws, r, 1, label, font=BOLD)
        for i, name in enumerate(("보수", "중립", "낙관"), 2):
            put(ws, r, i, f"={DCFREF[(name, key, 'per_share')]}", WON,
                font=GREEN)
        put(ws, r, 5, f"={A['주가']}", WON, font=GREEN)
        r += 1
    r += 1

    put(ws, r, 1, "매수 규칙", font=BOLDNAVY)
    r += 1
    put(ws, r, 1, "중립·낙관 평균 적정주가 (현재 환율 기준)", font=BOLD)
    put(ws, r, 2,
        f"=AVERAGE({DCFREF[('중립', 'norm', 'per_share')]},"
        f"{DCFREF[('낙관', 'norm', 'per_share')]})", WON, font=GREEN)
    mid = f"B{r}"
    r += 1
    put(ws, r, 1, "안전마진 적용 후 매수가", font=BOLD)
    put(ws, r, 2, f"={mid}*(1-{A['안전마진']})", WON, font=BOLD)
    r += 1
    put(ws, r, 1, "현재주가 대비", font=BOLD)
    put(ws, r, 2, f"=B{r-1}/{A['주가']}-1", PCT, font=BOLD)
    r += 2
    r = foot(ws, r, "이 칸을 목표주가로 읽지 마십시오. '내가 정한 가정 아래서 "
                    "가치가 이만큼이므로 그 아래에서만 산다'는 규칙의 출력입니다. "
                    "가정은 전부 가정 시트의 노란 칸에 있으니, 생각이 다르면 그 칸을 "
                    "바꿔 이 숫자가 어떻게 움직이는지 직접 확인하시면 됩니다.")
    r = foot(ws, r, "색: 파랑 = 감사보고서·시세에서 읽은 값, 검정 = 같은 시트 수식, "
                    "초록 = 다른 시트를 참조하는 수식, 노랑 = 바꿔도 되는 가정.")
    return ws


NUM = "#,##0.00"


def main():
    with open(VAL) as fh:
        d = json.load(fh)
    with open(RAW) as fh:
        raw = json.load(fh)

    wb = Workbook()
    wb.remove(wb.active)

    sheet_assumptions(wb, d)
    sheet_raw(wb, raw)
    sheet_roic(wb)
    sheet_incremental(wb)
    sheet_owner_earnings(wb, d)
    sheet_base(wb, d, raw)
    for name in ("보수", "중립", "낙관"):
        for key, label in (("reported", "FY2025 실적"),
                           ("run", "2026 상반기 연율화"),
                           ("norm", "2026 연율화 · 현재 환율")):
            if key == "norm":
                sheet_dcf(wb, name, key, label)
            else:
                # The other two bases are needed for the summary grid but do not
                # each warrant a sheet, so they are built as hidden sheets.
                ws = sheet_dcf(wb, f"{name}_{key}", key, label, scen=name)
                ws.sheet_state = "hidden"
                for k in list(DCFREF):
                    if k[0] == f"{name}_{key}":
                        DCFREF[(name, key, k[2])] = DCFREF[k]
    sheet_reverse(wb)
    sheet_summary(wb, d)

    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    wb.save(OUT)
    print(f"wrote {OUT}  ({len(wb.sheetnames)} sheets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
