"""
Excel export - the analysis as a workbook someone can actually work in.

Seven sheets: the headline findings, the quality ranking with its score broken
into components, the DCF across all three scenarios, the financials on their own
terms, the full year-by-year dataset behind everything, the PHASE 6 verification
record with source URLs, and the universe with its selection provenance.

Ratios that a reader might want to re-derive are written as formulas rather than
as computed constants, so changing a market cap in the sheet moves the margin of
safety with it. Percentages are stored as fractions and formatted, never as 15
meaning 15%.

Writes work/버핏기준_52개기업_분석.xlsx.
"""

import json
import os
import sys

from openpyxl import Workbook
from openpyxl.workbook.properties import CalcProperties
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

WORK = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(WORK, "버핏기준_52개기업_분석.xlsx")

FONT = "Arial"
PCT = "0.0%"
MULT = '0.0"x"'
USD_B = '$#,##0.0;($#,##0.0);-'
INT = "#,##0"

HEAD_FILL = PatternFill("solid", fgColor="1F3864")
HEAD_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
TITLE_FONT = Font(name=FONT, bold=True, size=14, color="1F3864")
BODY = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
NOTE = Font(name=FONT, size=9, italic=True, color="595959")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(bottom=THIN)


def bn(v):
    """USD into billions, keeping None as None so blanks stay blank."""
    return None if v is None else v / 1e9


def header(ws, row, labels, widths=None):
    for i, label in enumerate(labels, 1):
        c = ws.cell(row=row, column=i, value=label)
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    if widths:
        for i, wdt in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = wdt
    ws.row_dimensions[row].height = 30
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def write_row(ws, row, values, formats=None):
    for i, v in enumerate(values, 1):
        c = ws.cell(row=row, column=i, value=v)
        c.font = BODY
        c.border = BORDER
        if formats and formats[i - 1]:
            c.number_format = formats[i - 1]
    return row + 1


def title_block(ws, title, subtitle=None):
    ws["A1"] = title
    ws["A1"].font = TITLE_FONT
    if subtitle:
        ws["A2"] = subtitle
        ws["A2"].font = NOTE
    return 4 if subtitle else 3


# ---------------------------------------------------------------------------

def sheet_summary(wb, analysis, verification, std, fin):
    ws = wb.create_sheet("요약")
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 88
    r = title_block(ws, "버핏 기준 52개 기업 분석",
                    f"생성 {analysis['generated_at_utc'][:16].replace('T', ' ')} UTC · "
                    f"미국 50개사 정량 + 한국 2개사 정성")

    valued = [c for c in std if c["summary"]["valuation_status"] == "VALUED"]
    investable = [c for c in valued if c["summary"]["dcf"]["base"]["verdict"] == "INVESTABLE_RANGE"]
    borderline = [c for c in valued if c["summary"]["dcf"]["base"]["verdict"] == "BORDERLINE"]
    negoe = [c for c in std if c["summary"]["valuation_status"] == "NEGATIVE_OWNER_EARNINGS"]
    above_wacc = sum(1 for c in std if (c["summary"].get("roic_wacc_spread") or -1) > 0)

    rows = [
        ("핵심 결론",
         f"비금융 {len(std)}개사 중 {above_wacc}개사가 ROIC로 자본비용을 넘겼지만, "
         f"할인율 10% 기준 DCF에서 안전마진 30% 이상인 기업은 {len(investable)}개입니다."),
        ("경계선",
         f"{len(borderline)}개사 ({', '.join(c['ticker'] for c in borderline) or '없음'}). "
         f"나머지는 전부 적정가치 추정 범위 밖에서 거래되고 있습니다."),
        ("주주이익 음수",
         f"{len(negoe)}개사 ({', '.join(c['ticker'] for c in negoe)}). 이익이 없어서가 아니라 "
         f"설비투자와 운전자본이 순이익을 넘어서기 때문이며, 데이터 공백이 아니라 사업 판정입니다."),
        ("금융업 처리",
         f"{len(fin)}개사는 ROIC·주주이익을 산출하지 않았습니다. 은행에서 부채는 자금조달이 아니라 "
         f"원재료라 투하자본이 정의되지 않습니다. SIC 6000~6799 기준으로 분류했습니다."),
        ("한국 2개사",
         "삼성전자·SK하이닉스는 정성 분석만 했습니다. DART 접근에 인증키가 필요해 "
         "감사받은 1차 출처를 확보할 수 없었고, 기억으로 숫자를 채우지 않았습니다."),
        ("", ""),
        ("검증 (PHASE 6)",
         f"{verification['summary']['companies_passed']}/{verification['summary']['companies_checked']}개사 통과. "
         f"각 수치를 해당 10-K 원문의 인라인 XBRL과 대조하고, 인용 접수번호가 EDGAR에 "
         f"실재하는지 확인하고, 주식수를 재파싱으로 재현하고, 주가를 재조회했습니다."),
        ("", ""),
        ("무위험수익률",
         f"{analysis['risk_free_rate']['rate']:.2%} ({analysis['risk_free_rate']['as_of']}) · "
         f"{analysis['risk_free_rate']['series']}"),
        ("주식위험프리미엄",
         f"{analysis['equity_risk_premium']['erp']:.2%} ({analysis['equity_risk_premium']['as_of']}) · "
         f"Damodaran (NYU Stern)"),
        ("", ""),
        ("EBIT 산출", analysis["method_notes"]["ebit"]),
        ("수익률 분모", analysis["method_notes"]["returns_denominator"]),
        ("DCF 기준 현금흐름", "최근 5년 주주이익 마진의 중앙값 × 최근 매출"),
        ("DCF 시나리오", "보수 할인율 12%·영구성장 2.0% / 기준 10%·2.5% / 낙관 8%·3.0%, 예측기간 10년"),
    ]
    for label, text in rows:
        if not label:
            r += 1
            continue
        a = ws.cell(row=r, column=1, value=label)
        a.font = BOLD
        a.alignment = Alignment(vertical="top")
        b = ws.cell(row=r, column=2, value=text)
        b.font = BODY
        b.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[r].height = max(15, 13 * (len(text) // 60 + 1))
        r += 1

    r += 1
    c = ws.cell(row=r, column=1, value="주의")
    c.font = BOLD
    n = ws.cell(row=r, column=2, value=(
        "이 분석은 '지금 투자 가능 구간 안인가'라는 질문에만 답합니다. 목표주가가 아니며, "
        "DCF는 3개 시나리오의 범위로만 읽어야 합니다. 비자의 시가총액은 클래스 B·C 전환분이 "
        "빠져 과소평가돼 있어 실제 안전마진은 표시된 값보다 나쁩니다."))
    n.font = NOTE
    n.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[r].height = 45


def sheet_quality(wb, std):
    ws = wb.create_sheet("품질순위")
    r = title_block(ws, "품질 순위 — 비금융 42개사",
                    "사업의 질만 평가합니다. 가격은 '밸류에이션' 시트에서 따로 다룹니다. "
                    "총점은 우측 7개 배점 항목의 합계(수식)입니다.")
    cols = ["순위", "티커", "기업", "총점", "ROIC 중앙값", "두자릿수 유지",
            "신규 ROIC", "ROIC−WACC", "WACC", "주주이익 마진", "순부채/EBITDA",
            "이자보상배율", "해자 판정",
            "배점:ROIC", "배점:지속성", "배점:신규ROIC", "배점:스프레드",
            "배점:주주이익", "배점:순부채", "배점:이자보상"]
    header(ws, r, cols,
           [6, 8, 30, 8, 12, 12, 12, 11, 9, 12, 12, 12, 40] + [10] * 7)
    fmts = [None, None, None, INT, PCT, None, PCT, PCT, PCT, PCT, MULT, MULT, None] + [INT] * 7
    r += 1
    first = r
    for i, c in enumerate(std, 1):
        s, d = c["summary"], c["_detail"]
        rev = s.get("_latest_revenue")
        oe = s.get("owner_earnings_normalised")
        row = [
            i, c["ticker"], c["company_name"], None,
            s.get("roic_10y_median"),
            f"{s.get('roic_above_10pct_years')}/{s.get('roic_years_observed')}",
            s.get("incremental_roic"), s.get("roic_wacc_spread"), s.get("wacc"),
            (oe / rev) if (oe is not None and rev) else None,
            s.get("net_debt_to_ebitda_latest"), s.get("interest_coverage_latest"),
            c["_moat"],
            d["ROIC 중앙값"], d["ROIC 지속성"], d["신규 ROIC"], d["ROIC-WACC 스프레드"],
            d["주주이익 마진"], d["순부채/EBITDA"], d["이자보상배율"],
        ]
        r = write_row(ws, r, row, fmts)
        ws.cell(row=r - 1, column=4).value = f"=SUM(N{r-1}:T{r-1})"
        ws.cell(row=r - 1, column=4).font = BOLD
        ws.cell(row=r - 1, column=4).number_format = INT
    ws.auto_filter.ref = f"A{first-1}:T{r-1}"

    r += 1
    ws.cell(row=r, column=1, value=(
        "배점: ROIC 중앙값 25 · 지속성 20 · 신규 ROIC 20 · ROIC−WACC 15 · 주주이익 마진 10 · "
        "순부채/EBITDA 5 · 이자보상배율 5 (합계 100). 백분위가 아니라 절대 기준입니다 — "
        "비싼 시장에서 나머지 49개사를 이기는 것이 아니라 사업 품질의 절대 수준을 넘어야 합니다."
    )).font = NOTE


def sheet_valuation(wb, std):
    ws = wb.create_sheet("밸류에이션")
    r = title_block(ws, "적정가치와 안전마진 — 원칙 5·6",
                    "주주이익 기준 2단계 DCF. P/적정가치와 안전마진은 수식이므로 "
                    "시가총액이나 적정가치를 바꾸면 함께 움직입니다.")
    cols = ["티커", "기업", "정규화 주주이익", "시가총액", "PER", "PBR", "PSR",
            "보수 적정가치", "기준 적정가치", "낙관 적정가치",
            "P/적정가치(기준)", "안전마진(기준)", "판정(기준)", "정규화 방식"]
    header(ws, r, cols, [8, 28, 15, 14, 9, 9, 9, 14, 14, 14, 14, 13, 18, 52])
    fmts = [None, None, USD_B, USD_B, MULT, MULT, MULT, USD_B, USD_B, USD_B,
            MULT, PCT, None, None]
    r += 1
    first = r
    valued = [c for c in std if c["summary"]["valuation_status"] == "VALUED"]
    valued.sort(key=lambda c: -(c["summary"]["dcf"]["base"]["margin_of_safety"] or -99))
    for c in valued:
        s = c["summary"]
        dcf = s["dcf"]
        row = [
            c["ticker"], c["company_name"], bn(s.get("owner_earnings_normalised")),
            bn(c.get("market_cap_usd")), s.get("per"), s.get("pbr"), s.get("psr"),
            bn(dcf["conservative"]["intrinsic_value"]),
            bn(dcf["base"]["intrinsic_value"]),
            bn(dcf["optimistic"]["intrinsic_value"]),
            None, None, dcf["base"]["verdict"], s.get("owner_earnings_normalisation"),
        ]
        r = write_row(ws, r, row, fmts)
        ws.cell(row=r - 1, column=11).value = f"=IF(I{r-1}=0,\"\",D{r-1}/I{r-1})"
        ws.cell(row=r - 1, column=11).number_format = MULT
        ws.cell(row=r - 1, column=12).value = f"=IF(I{r-1}=0,\"\",(I{r-1}-D{r-1})/I{r-1})"
        ws.cell(row=r - 1, column=12).number_format = PCT
    ws.auto_filter.ref = f"A{first-1}:N{r-1}"

    r += 2
    ws.cell(row=r, column=1, value="밸류에이션을 내지 않은 기업").font = BOLD
    r += 1
    header(ws, r, ["티커", "기업", "구분", "사유"], [8, 28, 22, 100])
    r += 1
    for c in std:
        s = c["summary"]
        if s["valuation_status"] == "NEGATIVE_OWNER_EARNINGS":
            r = write_row(ws, r, [
                c["ticker"], c["company_name"], "주주이익 음수",
                f"정규화 주주이익 {s['owner_earnings_normalised']/1e9:.1f}십억 달러. 설비투자와 "
                f"운전자본이 순이익을 넘어서 할인할 현금흐름이 없습니다. 사업에 대한 판정입니다."])


def sheet_financials(wb, fin):
    ws = wb.create_sheet("금융9개사")
    r = title_block(ws, "금융업 — 별도 기준",
                    "ROIC와 주주이익은 산출하지 않았습니다. 은행·보험의 대차대조표에서 부채는 "
                    "영업 자산이고 유동자산·유동부채 구분이 없어 투하자본과 운전자본이 정의되지 않습니다.")
    cols = ["티커", "기업", "SIC", "업종", "ROE 중앙값", "최근 ROE", "PER", "PBR",
            "시가총액", "자기자본", "순이익"]
    header(ws, r, cols, [8, 28, 7, 32, 12, 11, 9, 9, 14, 14, 14])
    fmts = [None, None, None, None, PCT, PCT, MULT, MULT, USD_B, USD_B, USD_B]
    r += 1
    first = r
    for c in fin:
        s = c["summary"]
        latest = c["years"][-1] if c["years"] else {}
        r = write_row(ws, r, [
            c["ticker"], c["company_name"], c.get("sic"), c.get("sic_description"),
            s.get("roe_10y_median"), s.get("roe_latest"), s.get("per"), s.get("pbr"),
            bn(c.get("market_cap_usd")), bn(latest.get("total_equity")),
            bn(latest.get("net_income")),
        ], fmts)
    ws.auto_filter.ref = f"A{first-1}:K{r-1}"


def sheet_yearly(wb, companies):
    ws = wb.create_sheet("연도별데이터")
    r = title_block(ws, "연도별 원천 데이터",
                    "모든 지표가 이 표에서 나옵니다. 각 행은 한 기업의 한 회계연도이며, "
                    "접수번호로 해당 10-K를 특정할 수 있습니다. 금액 단위는 십억 USD.")
    cols = ["티커", "기업", "구분", "회계연도", "결산일", "접수번호", "매출", "영업이익(EBIT)",
            "EBIT 산출방식", "순이익", "실효세율", "NOPAT", "투하자본", "투하자본(평균)",
            "ROIC", "ROIC 상태", "ROE", "ROE−ROIC", "자기자본", "현금", "이자부부채",
            "부채 비고", "EBITDA", "순부채/EBITDA", "이자보상배율", "주주이익",
            "주주이익 산출방식", "주주이익률", "영업이익률", "주식수"]
    header(ws, r, cols,
           [8, 24, 10, 9, 11, 22, 12, 13, 34, 12, 10, 12, 13, 13, 9, 30, 9, 10,
            13, 12, 13, 34, 12, 12, 12, 12, 44, 11, 11, 14])
    fmts = ([None] * 6 + [USD_B, USD_B, None, USD_B, PCT, USD_B, USD_B, USD_B, PCT,
             None, PCT, PCT, USD_B, USD_B, USD_B, None, USD_B, MULT, MULT, USD_B,
             None, PCT, PCT, INT])
    r += 1
    first = r
    for c in companies:
        for y in c["years"]:
            r = write_row(ws, r, [
                c["ticker"], c["company_name"], c["sector_treatment"],
                y.get("fiscal_year"), y.get("period_end"), y.get("accession"),
                bn(y.get("revenue")), bn(y.get("ebit")), y.get("ebit_method"),
                bn(y.get("net_income")), y.get("tax_rate"), bn(y.get("nopat")),
                bn(y.get("invested_capital")), bn(y.get("invested_capital_avg")),
                y.get("roic"), y.get("roic_status"), y.get("roe"),
                y.get("roe_roic_spread"), bn(y.get("total_equity")), bn(y.get("cash")),
                bn(y.get("interest_bearing_debt")), y.get("debt_note"),
                bn(y.get("ebitda")), y.get("net_debt_to_ebitda"),
                y.get("interest_coverage"), bn(y.get("owner_earnings")),
                y.get("owner_earnings_method"), y.get("owner_earnings_margin"),
                y.get("operating_margin"), y.get("shares_outstanding"),
            ], fmts)
    ws.auto_filter.ref = f"A{first-1}:AD{r-1}"


def sheet_verification(wb, analysis, verification):
    ws = wb.create_sheet("검증결과")
    r = title_block(ws, "PHASE 6 — 출처 재검증",
                    "각 수치를 해당 10-K 원문의 인라인 XBRL과 대조했습니다. "
                    "companyfacts API가 아니라 제출서류 자체를 다시 읽어 비교한 결과입니다.")
    cols = ["티커", "판정", "항목 통과", "접수번호 확인", "주식수 재현", "주가 재조회",
            "검증한 제출서류", "companyfacts 출처"]
    header(ws, r, cols, [8, 8, 11, 13, 12, 12, 74, 74])
    r += 1
    first = r
    src = {c["ticker"]: c.get("source_url") for c in analysis["companies"]}
    for t, v in verification["companies"].items():
        n_pass = sum(1 for m in v["metrics"] if m["result"] == "PASS")
        n_ck = sum(1 for m in v["metrics"] if m["result"] in ("PASS", "FAIL"))
        r = write_row(ws, r, [
            t, v["verdict"], f"{n_pass}/{n_ck}", v["accessions"]["result"],
            v["cover_shares"]["result"], v["price"]["result"],
            v.get("filing_verified"), src.get(t),
        ])
    ws.auto_filter.ref = f"A{first-1}:H{r-1}"

    r += 2
    for label, node in (("무위험수익률", verification["macro"]["risk_free_rate"]),
                        ("주식위험프리미엄", verification["macro"]["equity_risk_premium"])):
        ws.cell(row=r, column=1, value=label).font = BOLD
        ws.cell(row=r, column=2, value=node["result"]).font = BODY
        ws.cell(row=r, column=3, value=node["source_url"]).font = BODY
        r += 1


def sheet_universe(wb, universe, analysis):
    ws = wb.create_sheet("유니버스")
    r = title_block(ws, "유니버스 52개사 — 선정 근거",
                    "미국 50개사는 시가총액 상위 기준으로 선정했습니다. 선정에 쓴 외부 시가총액은 "
                    "구성 결정에만 사용했고, 보고서의 어떤 수치로도 인용하지 않았습니다.")
    cols = ["티커", "기업", "국가", "분석 방식", "CIK", "선정 순위",
            "선정용 시가총액", "계산된 시가총액", "주식수 출처", "비고"]
    header(ws, r, cols, [10, 32, 7, 18, 11, 10, 16, 16, 52, 62])
    fmts = [None, None, None, None, None, INT, USD_B, USD_B, None, None]
    r += 1
    first = r
    rec = {c["ticker"]: c for c in analysis["companies"]}
    for c in universe["companies"]:
        a = rec.get(c["ticker"], {})
        sel = c.get("selection") or {}
        notes = []
        if c.get("cik_override"):
            notes.append(f"CIK 교정: {c['cik_override']['reason']}")
        if c.get("reason"):
            notes.append(c["reason"])
        cov = (a.get("shares_cover_page") or {})
        if cov.get("incomplete"):
            notes.append(cov.get("conversion_note", ""))
        r = write_row(ws, r, [
            c["ticker"], c["company_name"], c["exchange_country"],
            "정량" if c.get("analysis_mode") == "QUANTITATIVE" else "정성만",
            c.get("cik"), sel.get("screen_rank"), bn(sel.get("screen_market_cap_usd")),
            bn(a.get("market_cap_usd")), a.get("shares_source"), " / ".join(notes),
        ], fmts)
    ws.auto_filter.ref = f"A{first-1}:J{r-1}"

    r += 2
    ws.cell(row=r, column=1, value=(
        "제외: SPCX(SpaceX) — 비상장으로 10-K 제출 이력이 없어 감사받은 연간 시계열이 "
        "존재하지 않습니다. 차순위인 IBM을 승격했습니다."
    )).font = NOTE


def main():
    with open(os.path.join(WORK, "analysis.json")) as f:
        analysis = json.load(f)
    with open(os.path.join(WORK, "verification.json")) as f:
        verification = json.load(f)
    with open(os.path.join(WORK, "universe.json")) as f:
        universe = json.load(f)

    # Reuse the report's scoring so the workbook and the document cannot diverge.
    sys.path.insert(0, WORK)
    import report as rp

    for c in analysis["companies"]:
        c["summary"]["_latest_revenue"] = next(
            (r["revenue"] for r in reversed(c["years"]) if r.get("revenue")), None)
        c["_score"], c["_detail"] = rp.quality_score(c["summary"])
        c["_moat"] = rp.moat_read(c["summary"])

    std = [c for c in analysis["companies"] if c["sector_treatment"] == "STANDARD"]
    fin = [c for c in analysis["companies"] if c["sector_treatment"] == "FINANCIAL"]
    std.sort(key=lambda c: (-c["_score"], -(c["summary"].get("roic_10y_median") or -9)))
    fin.sort(key=lambda c: -(c["summary"].get("roe_10y_median") or -9))

    with open(os.path.join(WORK, "analysis.json")) as f:
        stamped = json.load(f)
    scores = {c["ticker"]: c["_score"] for c in analysis["companies"]}
    for c in stamped["companies"]:
        c["_expected_score"] = scores.get(c["ticker"])
    with open(os.path.join(WORK, "analysis.json"), "w") as f:
        json.dump(stamped, f, indent=2)

    wb = Workbook()
    wb.remove(wb.active)
    sheet_summary(wb, analysis, verification, std, fin)
    sheet_quality(wb, std)
    sheet_valuation(wb, std)
    sheet_financials(wb, fin)
    sheet_yearly(wb, analysis["companies"])
    sheet_verification(wb, analysis, verification)
    sheet_universe(wb, universe, analysis)
    # openpyxl writes formulas with no cached result, so a reader that trusts the
    # cached value sees blanks. This tells the application to recalculate the
    # whole book on open, which Excel, LibreOffice and Sheets all honour.
    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    wb.save(OUT)
    print(f"xlsx -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
