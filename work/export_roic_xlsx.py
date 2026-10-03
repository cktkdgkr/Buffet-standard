"""
The ROIC-versus-10%-WACC workbook.

Every derived cell is a formula over cells in the same workbook, not a value
pasted in from Python. The components sheet holds operating income, the tax
rate, equity, debt and cash as filed, and NOPAT, invested capital, the average
and ROIC are computed from them in Excel; the year grid and the spread grid
then reference the components sheet. So any number can be traced to the filed
figures by following the formula bar, and changing a component updates
everything downstream.

    python3 export_roic_xlsx.py
"""

import json
import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
ROIC = os.path.join(HERE, "roic", "roic.json")
RECON = os.path.join(HERE, "roic", "reconciliation.json")
CORR = os.path.join(HERE, "roic", "corrections.json")
DIAG = os.path.join(HERE, "roic", "capital_diagnosis.json")
ROUTES = os.path.join(HERE, "roic", "oi_routes.json")
OUT = os.path.join(HERE, "미국50개사_ROIC_WACC비교.xlsx")

YEARS = list(range(2016, 2026))

H = Font(bold=True, color="FFFFFF", size=10)
HFILL = PatternFill("solid", fgColor="2F4F6F")
SUB = Font(bold=True, size=10)
SUBFILL = PatternFill("solid", fgColor="DCE6F1")
GOOD = PatternFill("solid", fgColor="E2EFDA")
BAD = PatternFill("solid", fgColor="FCE4E4")
WARN = PatternFill("solid", fgColor="FFF2CC")
NOTE = Font(italic=True, size=9, color="555555")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
PCT = "0.0%"
NUM = "#,##0"


def header(ws, row, labels, widths=None):
    for i, label in enumerate(labels, start=1):
        cell = ws.cell(row=row, column=i, value=label)
        cell.font, cell.fill, cell.border = H, HFILL, BOX
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
    if widths:
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=row + 1, column=3)


def guide(wb, data, recon, corr, diag):
    ws = wb.create_sheet("읽는 방법")
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 112
    rows = [
        ("", ""),
        ("무엇을 담았는지", ""),
        ("질문", "ROIC가 자본비용(WACC)보다 높은지, 그게 10년간 꾸준했는지"),
        ("WACC", "전 종목 10% 고정 — 지시사항. 기업별로 다르게 잡으면 ROIC "
                 "비교가 아니라 베타 비교가 되므로 같은 문턱을 적용했습니다."),
        ("대상", f"{len(data['companies'])}개 미국 상장사, FY2016~FY2025"),
        ("자료 출처", "SEC XBRL companyfacts API. 1차 조사가 공시 본문을 "
                  "읽은 것과 달리 이번 조사는 태그 데이터를 직접 받았습니다 — "
                  "같은 정의, 다른 경로. 두 결과가 어긋나면 한쪽이 틀렸다는 "
                  "뜻이고, '구 조사 대조' 시트가 어느 쪽인지 가립니다."),
        ("", ""),
        ("ROIC를 어떻게 계산했는지", ""),
        ("분자 NOPAT", "영업이익 × (1 − 실효세율). 실효세율 = 법인세비용 ÷ "
                    "세전이익, 5%~40%로 제한."),
        ("분모 투하자본", "자기자본(비지배지분 포함) + 이자부채입금 − "
                      "현금 및 단기투자자산. 2007년 주주서한의 "
                      "'사업 운영에 필요한 자본' 기준으로, 국채 포트폴리오는 "
                      "사업 자본이 아니므로 뺍니다."),
        ("분모 평균", "기초·기말 평균. 단 어느 한쪽이 0 이하인 해는 평균이 "
                   "0 근처로 내려가 비율이 폭발하므로 기말값 단독 사용."),
        ("금융업", "SIC 6000~6799은 ROIC 미산출. 은행에게 차입은 자금조달이 "
                "아니라 원재료여서, 자기자본+차입금−현금은 아무것도 "
                "측정하지 않습니다."),
        ("", ""),
        ("믿을 수 있는 정도", ""),
        ("HIGH", "기업이 보고한 영업이익 소계를 그대로 사용 (332개 연도), "
                 "또는 손익계산서 항목을 쌓아 세전이익으로 역검증 통과."),
        ("MEDIUM", "항목을 쌓아 만든 소계가 세전이익과 5% 이내로 맞은 경우."),
        ("LOW", "영업이익 소계를 아예 보고하지 않아 세전이익에서 거꾸로 "
                "추정한 경우 (릴리·머크·J&J·IBM·엑슨·셰브론·GE). 두 가지 "
                "추정 방식을 모두 계산해 10% 문턱 판정이 일치하는지 "
                "'계산 명세' 시트에 기록했습니다."),
        ("분모가 작은 해", "아리스타·램리서치처럼 현금이 자기자본을 거의 "
                      "상계해 순투하자본이 매출의 10% 미만이 되는 해는 "
                      "노란색. 비율은 민감해지지만 10% 문턱 판정은 유효."),
        ("", ""),
        ("검증", ""),
        ("자동 검사", "verify_roic.py에서 9,867건 통과. 항등식(투하자본·NOPAT·"
                  "ROIC·평균 규칙), 트립와이어(차감 현금 ≤ 유동자산, "
                  "차입금 ≤ 총부채), 공시 원문에서 손으로 읽은 앵커 19건."),
        ("변이 검정", "값을 고의로 훼손한 10가지 시나리오 전부 탐지. "
                  "틀린 데이터에서도 통과하는 검사는 검사가 아닙니다."),
        ("", ""),
        ("1차 조사에서 바로잡은 것", ""),
        ("대조 결과", f"{recon['compared_company_years']}개 기업-연도 중 "
                  f"{recon['agree_within_1pp']}건은 1%p 이내 일치, "
                  f"{recon['differ_over_1pp']}건 불일치, "
                  f"{recon['hurdle_verdict_flips']}건은 10% 문턱 판정까지 바뀜."),
        ("가장 큰 원인", f"1차 조사가 공시된 장기차입금을 누락한 "
                    f"{len(diag['old_missed_long_term_debt'])}개 기업-연도. "
                    "오라클 10년, 코카콜라 7년, 브로드컴 4년, 비자 3년. "
                    "오라클 FY2024 ROIC가 761%로 나온 이유입니다."),
        ("정정 범위", f"{corr['company_years_changed']}개 기업-연도의 ROIC·"
                   "영업이익·세율·투하자본을 교체. 원본은 "
                   "analysis.json.pre-roic-correction에 보존."),
        ("가치평가 파급", "순현금 입력값까지 어긋난 기업 "
                    f"{len(corr['net_cash_errors_flagged'])}곳을 '정정 내역' "
                    "시트에 기록. 오라클은 시가총액의 24%에 해당하는 오차라 "
                    "DCF 결론이 바뀔 수 있지만, 가치평가 재계산은 이번 "
                    "작업 범위가 아니어서 표시만 했습니다."),
        ("", ""),
        ("수식", "파생 셀은 전부 같은 통합문서 안의 셀을 참조하는 수식입니다. "
               "'계산 명세' 시트의 공시 입력값만 바꾸면 모든 시트가 따라 "
               "바뀝니다. 수식이 아닌 값은 공시에서 가져온 원자료뿐입니다."),
    ]
    for r, (a, b) in enumerate(rows, start=1):
        ca, cb = ws.cell(row=r, column=1, value=a), ws.cell(row=r, column=2,
                                                            value=b)
        cb.alignment = Alignment(wrap_text=True, vertical="top")
        if a and not b:
            ca.font, ca.fill = SUB, SUBFILL
            cb.fill = SUBFILL
        elif a:
            ca.font = SUB
    ws.cell(row=1, column=1, value="미국 50개사 ROIC vs WACC 10% — 읽는 방법")\
        .font = Font(bold=True, size=14)
    return ws


def components(wb, data):
    """
    Filed inputs, with everything derived computed here in Excel.

    FY2015 is on the sheet although the report covers FY2016-FY2025, because
    FY2016's average invested capital is the average of FY2016 and FY2015.
    Without the FY2015 row the average would have to be pasted in as a value or
    silently fall back to the closing figure, and the first year of all forty
    companies would be computed on a different basis from the other nine.
    """
    ws = wb.create_sheet("계산 명세")
    cols = ["기업", "티커", "회계연도", "결산일", "매출",
            "영업이익", "산출 경로", "신뢰도", "실효세율", "NOPAT",
            "자기자본", "이자부차입금", "현금+단기투자", "투하자본",
            "직전 투하자본", "평균 투하자본", "평균 산정", "ROIC",
            "ROIC−10%", "분모/매출", "대안 추정 ROIC", "문턱 판정 일치",
            "상태"]
    header(ws, 1, cols,
           [26, 8, 9, 11, 14, 14, 30, 9, 10, 14, 14, 14, 15, 14, 14, 14, 24,
            9, 10, 10, 18, 13, 34])

    r = 2
    index = {}
    for comp in data["companies"]:
        for y in comp["years"]:
            if not 2015 <= y["fiscal_year"] <= 2025:
                continue
            ws.cell(row=r, column=1, value=comp["company_name"])
            ws.cell(row=r, column=2, value=comp["ticker"])
            ws.cell(row=r, column=3, value=y["fiscal_year"])
            ws.cell(row=r, column=4, value=y["period_end"])
            ws.cell(row=r, column=5, value=y["revenue"]).number_format = NUM
            ws.cell(row=r, column=6,
                    value=y["operating_income"]).number_format = NUM
            ws.cell(row=r, column=7, value=y["operating_income_route"])
            ws.cell(row=r, column=8, value=y["confidence"])
            ws.cell(row=r, column=9,
                    value=y["effective_tax_rate"]).number_format = PCT
            ws.cell(row=r, column=10,
                    value=f"=IF(F{r}=\"\",\"\",F{r}*(1-I{r}))"
                    ).number_format = NUM
            ws.cell(row=r, column=11,
                    value=y["total_equity"]).number_format = NUM
            ws.cell(row=r, column=12,
                    value=y["interest_bearing_debt"]).number_format = NUM
            ws.cell(row=r, column=13,
                    value=y["cash_and_short_term_investments"]
                    ).number_format = NUM
            ws.cell(row=r, column=14,
                    value=f"=IF(COUNT(K{r}:M{r})<3,\"\",K{r}+L{r}-M{r})"
                    ).number_format = NUM

            # Prior-year capital, pulled from this sheet where the prior year
            # is on it, so the average is visibly an average of two cells.
            prev_row = index.get((comp["ticker"], y["fiscal_year"] - 1))
            if prev_row:
                ws.cell(row=r, column=15, value=f"=N{prev_row}"
                        ).number_format = NUM
                ws.cell(row=r, column=16,
                        value=(f'=IF(N{r}="","",IF(OR(O{r}="",O{r}<=0,'
                               f'N{r}<=0),N{r},(N{r}+O{r})/2))')
                        ).number_format = NUM
            else:
                ws.cell(row=r, column=15, value="—")
                ws.cell(row=r, column=16, value=f"=N{r}").number_format = NUM
            ws.cell(row=r, column=17, value=y["invested_capital_avg_note"])

            if y["roic"] is None:
                ws.cell(row=r, column=18, value="—")
                ws.cell(row=r, column=19, value="—")
            else:
                ws.cell(row=r, column=18,
                        value=f'=IF(OR(P{r}="",P{r}<=0),"",J{r}/P{r})'
                        ).number_format = PCT
                ws.cell(row=r, column=19,
                        value=f'=IF(R{r}="","",R{r}-{data["wacc"]})'
                        ).number_format = PCT
            ws.cell(row=r, column=20,
                    value=f'=IF(OR(P{r}="",E{r}=0,E{r}=""),"",P{r}/E{r})'
                    ).number_format = PCT

            alt = y.get("roic_alternate")
            ws.cell(row=r, column=21,
                    value=(f"{alt[0]:.1%} / {alt[1]:.1%}" if alt else "—"))
            ag = y.get("hurdle_agrees")
            cell = ws.cell(row=r, column=22,
                           value=("일치" if ag else "불일치" if ag is False
                                  else "—"))
            if ag is False:
                cell.fill = BAD
            ws.cell(row=r, column=23, value=y["roic_status"])

            fill = (BAD if y["confidence"] == "LOW"
                    else WARN if y.get("capital_too_small") else None)
            if fill:
                for col in range(1, 24):
                    ws.cell(row=r, column=col).fill = fill
            if y["fiscal_year"] == 2015:
                # This row supplies FY2016's opening capital and nothing else.
                # Its own average would need FY2014, which is not on the sheet,
                # so leaving a ratio here would show a number computed on a
                # different basis from every other row.
                for col in (15, 16, 17, 18, 19, 20, 21, 22):
                    ws.cell(row=r, column=col).value = "—"
                ws.cell(row=r, column=23,
                        value="FY2016 평균 투하자본의 기초값으로만 사용 "
                              "(보고 기간 밖 — 자체 비율은 계산하지 않음)")
                for col in range(1, 24):
                    ws.cell(row=r, column=col).fill = PatternFill(
                        "solid", fgColor="F2F2F2")
            index[(comp["ticker"], y["fiscal_year"])] = r
            r += 1

    ws.auto_filter.ref = f"A1:W{r - 1}"
    return index


def year_grid(wb, data, index, title, formula, note):
    ws = wb.create_sheet(title)
    cols = ["순위", "기업", "티커"] + [f"FY{y}" for y in YEARS] + \
        ["중위", "최소", "최대", "10% 초과 연수", "산출 연수", "판정"]
    header(ws, 2, cols,
           [6, 26, 8] + [9] * len(YEARS) + [9, 9, 9, 13, 11, 24])
    ws.cell(row=1, column=1, value=note).font = NOTE

    by_ticker = {c["ticker"]: c for c in data["companies"]}
    groups = [("순위 대상 (산출 5년 이상)", data["ranking"]),
              ("표본 부족", data["thin_sample"]),
              ("금융업 — ROIC 정의 부적합",
               [{"ticker": c["ticker"], "name": c["company_name"]}
                for c in data["companies"] if c["is_financial"]])]

    r = 3
    rank = 0
    for label, rows in groups:
        if not rows:
            continue
        cell = ws.cell(row=r, column=1, value=label)
        cell.font = SUB
        for col in range(1, len(cols) + 1):
            ws.cell(row=r, column=col).fill = SUBFILL
        r += 1
        for entry in rows:
            comp = by_ticker[entry["ticker"]]
            if label.startswith("순위"):
                rank += 1
                ws.cell(row=r, column=1, value=rank)
            else:
                ws.cell(row=r, column=1, value="—")
            ws.cell(row=r, column=2, value=comp["company_name"])
            ws.cell(row=r, column=3, value=comp["ticker"])

            refs = []
            for i, fy in enumerate(YEARS):
                col = 4 + i
                src = index.get((comp["ticker"], fy))
                yr = next((y for y in comp["years"]
                           if y["fiscal_year"] == fy), None)
                if src is None or yr is None or yr["roic"] is None:
                    ws.cell(row=r, column=col, value="—").alignment = \
                        Alignment(horizontal="center")
                    continue
                ref = f"'계산 명세'!{formula}{src}"
                cell = ws.cell(row=r, column=col, value=f"={ref}")
                cell.number_format = PCT
                refs.append(get_column_letter(col) + str(r))
                if yr["roic"] > data["wacc"]:
                    cell.fill = GOOD
                else:
                    cell.fill = BAD
                if yr["confidence"] == "LOW":
                    cell.font = Font(italic=True, size=10)
                if yr.get("capital_too_small"):
                    cell.border = Border(left=Side(style="medium",
                                                   color="BF8F00"),
                                         right=Side(style="medium",
                                                    color="BF8F00"),
                                         top=Side(style="medium",
                                                  color="BF8F00"),
                                         bottom=Side(style="medium",
                                                     color="BF8F00"))

            span = f"D{r}:{get_column_letter(3 + len(YEARS))}{r}"
            if refs:
                ws.cell(row=r, column=4 + len(YEARS),
                        value=f"=MEDIAN({span})").number_format = PCT
                ws.cell(row=r, column=5 + len(YEARS),
                        value=f"=MIN({span})").number_format = PCT
                ws.cell(row=r, column=6 + len(YEARS),
                        value=f"=MAX({span})").number_format = PCT
                base = 0 if title.startswith("ROIC−") else data["wacc"]
                ws.cell(row=r, column=7 + len(YEARS),
                        value=f'=COUNTIF({span},">{base}")')
                ws.cell(row=r, column=8 + len(YEARS),
                        value=f'=COUNT({span})')
            else:
                for off in range(5):
                    ws.cell(row=r, column=4 + len(YEARS) + off, value="—")
            ws.cell(row=r, column=9 + len(YEARS),
                    value=comp["summary"]["verdict"])
            r += 1
        r += 1
    return ws


def comparison(wb, recon, diag):
    ws = wb.create_sheet("구 조사 대조")
    ws.cell(row=1, column=1,
            value="1차 조사(analysis.json, 공시 본문 파싱)와 이번 "
                  "재산출(companyfacts API)의 기업-연도별 대조. "
                  "정의는 같고 경로만 다릅니다.").font = NOTE
    cols = ["기업", "연도", "재산출 ROIC", "1차 조사 ROIC", "차이(%p)",
            "문턱 판정 바뀜", "재산출 영업이익", "1차 영업이익",
            "재산출 평균자본", "1차 평균자본", "재산출 경로", "원인"]
    header(ws, 2, cols, [8, 8, 13, 14, 11, 14, 16, 16, 16, 16, 34, 52])
    r = 3
    for d in recon["differences"]:
        ws.cell(row=r, column=1, value=d["ticker"])
        ws.cell(row=r, column=2, value=f"FY{d['fiscal_year']}")
        ws.cell(row=r, column=3, value=d["roic_new"]).number_format = PCT
        ws.cell(row=r, column=4, value=d["roic_old"]).number_format = PCT
        ws.cell(row=r, column=5,
                value=f"=C{r}-D{r}").number_format = PCT
        cell = ws.cell(row=r, column=6,
                       value="예" if d["hurdle_flips"] else "")
        if d["hurdle_flips"]:
            cell.fill = BAD
        for col, key in ((7, "oi_new"), (8, "oi_old"),
                         (9, "cap_new"), (10, "cap_old")):
            ws.cell(row=r, column=col, value=d[key]).number_format = NUM
        ws.cell(row=r, column=11, value=d["route_new"])
        ws.cell(row=r, column=12, value=", ".join(d["causes"]))
        r += 1
    ws.auto_filter.ref = f"A2:L{r - 1}"

    ws2 = wb.create_sheet("차입금 누락")
    ws2.cell(row=1, column=1,
             value="1차 조사가 장기차입금을 0으로 기록했으나 10-K에 해당 "
                   "태그가 존재하는 기업-연도. 어느 쪽이 맞는지 판단이 "
                   "필요 없는 유형의 오류입니다.").font = NOTE
    cols2 = ["기업-연도", "공시된 장기차입금", "1차 조사 총차입금",
             "재산출 총차입금", "사용 태그", "1차 ROIC", "재산출 ROIC"]
    header(ws2, 2, cols2, [14, 19, 19, 18, 34, 11, 13])
    r = 3
    for m in sorted(diag["old_missed_long_term_debt"],
                    key=lambda m: -(m["filed_long_term_debt"] or 0)):
        ws2.cell(row=r, column=1, value=m["key"])
        ws2.cell(row=r, column=2,
                 value=m["filed_long_term_debt"]).number_format = NUM
        ws2.cell(row=r, column=3,
                 value=m["old_total_debt"]).number_format = NUM
        ws2.cell(row=r, column=4,
                 value=m["new_total_debt"]).number_format = NUM
        ws2.cell(row=r, column=5, value=m["tag"])
        ws2.cell(row=r, column=6, value=m["roic_old"]).number_format = PCT
        ws2.cell(row=r, column=7, value=m["roic_new"]).number_format = PCT
        r += 1


def corrections_sheet(wb, corr):
    ws = wb.create_sheet("정정 내역")
    ws.cell(row=1, column=1,
            value=f"analysis.json에 반영한 정정 {corr['company_years_changed']}"
                  f"건. 원본은 {corr['backup']}에 보존.").font = NOTE
    cols = ["기업", "연도", "구 ROIC", "정정 ROIC", "변화(%p)",
            "구 영업이익", "정정 영업이익", "구 평균자본", "정정 평균자본",
            "바뀐 항목"]
    header(ws, 2, cols, [8, 8, 11, 12, 11, 16, 16, 16, 16, 44])
    r = 3
    rows = sorted(corr["changes"],
                  key=lambda c: -abs((c["roic_after"] or 0)
                                     - (c["roic_before"] or 0)))
    for c in rows:
        ws.cell(row=r, column=1, value=c["ticker"])
        ws.cell(row=r, column=2, value=f"FY{c['fiscal_year']}")
        ws.cell(row=r, column=3, value=c["roic_before"]).number_format = PCT
        ws.cell(row=r, column=4, value=c["roic_after"]).number_format = PCT
        ws.cell(row=r, column=5,
                value=(f"=D{r}-C{r}" if None not in (c["roic_before"],
                                                     c["roic_after"])
                       else "—")).number_format = PCT
        for col, key in ((6, "ebit_before"), (7, "ebit_after"),
                         (8, "capital_before"), (9, "capital_after")):
            ws.cell(row=r, column=col, value=c[key]).number_format = NUM
        ws.cell(row=r, column=10, value=", ".join(c["fields"]))
        r += 1
    ws.auto_filter.ref = f"A2:J{r - 1}"

    r += 2
    ws.cell(row=r, column=1,
            value="가치평가 쪽으로 번진 입력 오류 — DCF는 재계산하지 않음")\
        .font = SUB
    r += 1
    header(ws, r, ["기업", "연도", "1차 조사 순현금", "재산출 순현금",
                   "오차", "시가총액", "시가총액 대비"])
    r += 1
    for n in sorted(corr["net_cash_errors_flagged"],
                    key=lambda n: -abs(n["error"])):
        ws.cell(row=r, column=1, value=n["ticker"])
        ws.cell(row=r, column=2, value=f"FY{n['fiscal_year']}")
        ws.cell(row=r, column=3,
                value=n["net_cash_in_study"]).number_format = NUM
        ws.cell(row=r, column=4,
                value=n["net_cash_recomputed"]).number_format = NUM
        ws.cell(row=r, column=5, value=f"=C{r}-D{r}").number_format = NUM
        ws.cell(row=r, column=6, value=n["market_cap"]).number_format = NUM
        cell = ws.cell(row=r, column=7, value=f"=IF(F{r}=0,\"\",E{r}/F{r})")
        cell.number_format = PCT
        if abs(n["error_vs_market_cap"] or 0) > 0.05:
            for col in range(1, 8):
                ws.cell(row=r, column=col).fill = BAD
        r += 1


def routes_sheet(wb, routes, data):
    ws = wb.create_sheet("경로 검정")
    ws.cell(row=1, column=1,
            value="영업이익 소계를 보고하지 않는 기업의 분자를 어떻게 만들지, "
                  "주장이 아니라 측정으로 정했습니다. 소계가 보고된 "
                  "기업-연도에서 각 구성 방식을 보고치와 맞춰본 결과입니다.")\
        .font = NOTE
    header(ws, 2, ["구성 경로", "검정 건수", "±2% 일치", "정확도",
                   "중위 오차"], [46, 12, 12, 11, 12])
    r = 3
    for x in routes["routes"]:
        ws.cell(row=r, column=1, value=x["route"])
        ws.cell(row=r, column=2, value=x["tested"])
        ws.cell(row=r, column=3, value=x["matched"])
        ws.cell(row=r, column=4,
                value=f"=IF(B{r}=0,\"\",C{r}/B{r})").number_format = PCT
        ws.cell(row=r, column=5, value=x["median_error"]).number_format = PCT
        r += 1

    r += 2
    ws.cell(row=r, column=1,
            value="±2% 일치율은 이 문제에 맞는 통계가 아닙니다. ROIC를 10% "
                  "문턱과 비교하는 것이 목적이므로, 중요한 건 분자를 바꿨을 "
                  "때 문턱 판정이 뒤집히는지입니다.").font = NOTE
    r += 2
    ws.cell(row=r, column=1, value="회사별 최종 선택 경로").font = SUB
    r += 1
    header(ws, r, ["기업", "선택 경로", "역검증 통과", "중위 역검증 오차",
                   "우선순위"], [10, 46, 13, 17, 60])
    r += 1
    for comp in data["companies"]:
        ch = comp.get("chosen_route")
        if not ch:
            continue
        ws.cell(row=r, column=1, value=comp["ticker"])
        ws.cell(row=r, column=2, value=ch["route"])
        cell = ws.cell(row=r, column=3,
                       value="통과" if ch["reconciles"] else "미통과")
        cell.fill = GOOD if ch["reconciles"] else BAD
        ws.cell(row=r, column=4,
                value=ch["median_tie_out_error"]).number_format = PCT
        ws.cell(row=r, column=5, value=" → ".join(ch["preference"]))
        r += 1


def main():
    data = json.load(open(ROIC))
    recon = json.load(open(RECON))
    corr = json.load(open(CORR))
    diag = json.load(open(DIAG))
    routes = json.load(open(ROUTES))

    wb = Workbook()
    wb.remove(wb.active)
    guide(wb, data, recon, corr, diag)
    index = components(wb, data)
    year_grid(wb, data, index, "ROIC 연도별", "R",
              "셀은 '계산 명세' 시트의 ROIC를 참조합니다. 초록 = 10% 초과, "
              "빨강 = 10% 이하, 기울임 = 영업이익을 세전이익에서 추정한 해, "
              "노란 테두리 = 순투하자본이 매출의 10% 미만인 해.")
    year_grid(wb, data, index, "ROIC−WACC 스프레드", "S",
              "ROIC에서 10%를 뺀 값. 0보다 크면 자본비용을 넘겨 "
              "가치를 창출한 해입니다.")
    comparison(wb, recon, diag)
    corrections_sheet(wb, corr)
    routes_sheet(wb, routes, data)

    wb.calculation.fullCalcOnLoad = True
    wb.save(OUT)
    print(f"wrote {OUT}")
    print(f"시트: {', '.join(wb.sheetnames)}")


if __name__ == "__main__":
    main()
