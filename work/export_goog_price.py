"""
알파벳 주가 하락 원인과 투자기준 판정 — 마크다운·워드·엑셀.

하나의 생성기에서 세 포맷을 만듭니다. 내용이 같고 그릇만 다르기 때문입니다.
마크다운은 폰용으로 표를 6열 이내로 끊고, 워드는 공용 렌더러를 쓰고, 엑셀은
파생 셀을 수식으로 남긴 뒤 embed_xlsx_values.py 로 값을 심습니다.

    python3 export_goog_price.py
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import company_names  # noqa: E402

DATA = os.path.join(HERE, "goog", "goog_price.json")
MD = os.path.join(HERE, "알파벳_주가하락_투자기준판정.md")
DOCX_JSON = os.path.join(HERE, "goog", "goog_price_report.json")
DOCX = os.path.join(HERE, "알파벳_주가하락_투자기준판정.docx")
XLSX = os.path.join(HERE, "알파벳_주가하락_투자기준판정.xlsx")

D = json.load(open(DATA, encoding="utf-8"))
A = D["analysis"]
PH = D["price_history"]
REL = D["release"]
SG = A["segments"]
FIN = A["financing"]
REC = A["ten_year_record"]
V = A["views"]
MM, BN = 1e6, 1e9
WACC = D["wacc"]
NAME = company_names.label("GOOG", "short")


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def sg(x, nd=1):
    return "—" if x is None else f"{x * 100:+.{nd}f}%"


def mm(x, nd=0):
    return "—" if x is None else f"{x / MM:,.{nd}f}"


def bn(x, nd=1):
    return "—" if x is None else f"{x / BN:,.{nd}f}"


def usd(x, nd=2):
    return "—" if x is None else f"${x:,.{nd}f}"


# ------------------------------------------------------------------ 본문 블록
def blocks():
    b = []
    px, mc = A["price"], A["market_cap"]
    asof = PH["last"]["date"]
    drop = [m for m in PH["big_moves"] if m["date"] == asof]
    drop = drop[0] if drop else None
    net_cash = (A["balance_sheets"]["2026-09-30"]["cash_and_securities"]
                - A["balance_sheets"]["2026-09-30"]["debt"])
    nis = A["balance_sheets"]["2026-09-30"]["assets_not_yet_in_service"]
    nis0 = A["balance_sheets"]["2025-12-31"]["assets_not_yet_in_service"]
    quarters = [p for p in REL["cash_flow"] if not p["period"].startswith("TTM")]
    ttm = [p for p in REL["cash_flow"] if p["period"].startswith("TTM")][0]
    peak = max(REC["years"], key=lambda y: y["roic"] or 0)
    last = max(REC["years"], key=lambda y: y["fiscal_year"])

    b.append({"t": "h1", "x": f"{NAME} — 주가 하락 원인과 투자기준 판정"})
    b.append({"t": "note", "x":
              f"자료 기준일 {D['generated']} · 주가 {usd(px)} "
              f"({asof} 종가) · 시가총액 {bn(mc, 0)}십억 달러 · "
              f"10-Q {D['filings']['10-Q']['filed']} 제출 "
              f"({D['filings']['10-Q']['accession']}) · "
              f"8-K {D['filings']['8-K']['filed']} 제출 "
              f"({D['filings']['8-K']['accession']}) · 자본비용 {pct(WACC, 0)}"})

    # ------------------------------------------------------------------ 결론
    b.append({"t": "h2", "x": "결론"})
    b.append({"t": "p", "x":
              "**사업은 합격, 가격은 불합격입니다. 다만 8월보다 가까워졌습니다.**"})
    b.append({"t": "p", "x":
              f"주가가 {usd(px)}까지 빠진 것은 실적이 나빠서가 아닙니다. "
              f"3분기 매출은 {sg(SG['revenue']['total']['q3_2026'] / SG['revenue']['total']['q3_2025'] - 1)} "
              f"늘어 {bn(SG['revenue']['total']['q3_2026'])}십억 달러, 영업이익은 "
              f"{sg(SG['operating_income']['total']['q3_2026'] / SG['operating_income']['total']['q3_2025'] - 1)} "
              f"늘어 {bn(SG['operating_income']['total']['q3_2026'])}십억 달러로 "
              f"둘 다 역대 최고입니다. 빠진 이유는 **돈이 들어오는 속도보다 "
              f"설비에 나가는 속도가 빨라졌다**는 데 있습니다. "
              f"3분기 capex {bn(-quarters[3]['capex'])}십억 달러가 영업현금흐름 "
              f"{bn(quarters[3]['operating_cash_flow'])}십억 달러를 넘어서, "
              f"잉여현금흐름이 두 분기 연속 마이너스였습니다."})
    b.append({"t": "p", "x":
              f"투자기준으로 보면 **수익성은 압도적**입니다. 투하자본이익률은 "
              f"보고 기준 {pct(V['reported']['roic_ttm'])}, 아직 가동되지 않은 "
              f"설비를 분모에서 뺀 기준으로는 {pct(V['in_service']['roic_ttm'])}이고, "
              f"50개사 조사에서 알파벳은 10년 내내 문턱을 넘었습니다"
              f"(중위 {pct(REC['summary']['roic_median'])}). "
              f"걸리는 것은 **가격**입니다. 현재 가격이 연 {pct(WACC, 0)}을 내주려면 "
              f"영구히 연 {pct(A['implied_growth_at_10pct'], 1)}씩 성장해야 하고, "
              f"주주이익으로 본 수익률은 {pct(A['implied_return_lower'])}~"
              f"{pct(A['implied_return_upper'])}에 그칩니다."})
    b.append({"t": "p", "x":
              f"그리고 **놓치면 안 되는 추세**가 하나 있습니다. ROIC는 "
              f"FY{peak['fiscal_year']} {pct(peak['roic'])}가 고점이었고 "
              f"FY{last['fiscal_year']} {pct(last['roic'])}까지 떨어졌습니다. "
              f"영업이익이 멈춘 게 아니라"
              f"({pct(last['operating_income'] / peak['operating_income'] - 1, 0)} 증가) "
              f"투하자본이 더 빨리 늘었기 때문입니다"
              f"({pct(last['invested_capital_avg'] / peak['invested_capital_avg'] - 1, 0)} 증가). "
              f"지금 가격을 정당화하는 것은 과거의 46%가 아니라 "
              f"**이 설비가 가동된 뒤의 ROIC**입니다."})

    b.append({"t": "table", "headers": ["항목", "수치", "판정"], "rows": [
        ["ROIC(보고) vs 자본비용 10%", pct(V["reported"]["roic_ttm"]), "합격"],
        ["ROIC(가동자본)", pct(V["in_service"]["roic_ttm"]), "합격"],
        ["10년 일관성", f"{REC['summary']['years_above_wacc']}/10년 초과",
         "합격"],
        ["증분 ROIC(가동−지분)",
         pct(A["incremental"]["incremental_roic_in_service_ex_stakes"]),
         "합격"],
        ["순현금", f"{bn(net_cash, 0)}십억 달러", "합격"],
        ["이익의 질",
         f"9개월 순이익 {bn(A['net_income_9m_2026'], 0)}십억 중 "
         f"{bn(A['other_income_9m_2026'], 0)}십억이 비현금 평가이익", "주의"],
        ["주주환원", "자사주 매입 0, 신주 발행", "주의"],
        ["잉여현금흐름", f"TTM {bn(ttm['free_cash_flow'])}십억 달러", "주의"],
        ["가격(함의 영구성장률)", pct(A["implied_growth_at_10pct"]), "불합격"],
        ["가격(주주이익 수익률)",
         f"{pct(A['implied_return_lower'])}~{pct(A['implied_return_upper'])}",
         "불합격"],
    ]})

    # ------------------------------------------------------------- 원인 분석
    b.append({"t": "h2", "x": "1. 왜 빠졌나"})
    if drop:
        b.append({"t": "p", "x":
                  f"{drop['date']} 하루에 {usd(drop['from'])} → {usd(drop['to'])}, "
                  f"{sg(drop['change'])}. 6개월 중 가장 큰 하루 변동이고, "
                  f"6개월 고점 {usd(PH['high']['close'])}"
                  f"({PH['high']['date']}) 대비 {sg(PH['from_high'])}입니다. "
                  f"52주 범위는 {usd(PH['fifty_two_week_low'])}~"
                  f"{usd(PH['fifty_two_week_high'])}입니다."})
    b.append({"t": "p", "x":
              "하락 전날 8-K 실적 발표, 당일 10-Q가 제출됐습니다. 세 가지가 "
              "동시에 드러났고, 그중 **시장이 반응한 것은 세 번째**입니다."})

    b.append({"t": "h3", "x": "(1) 영업은 좋았습니다"})
    b.append({"t": "table", "headers":
              ["사업부", "Q3'25 매출", "Q3'26 매출", "증감",
               "Q3'26 영업이익", "마진"], "rows": [
        ["구글 서비스", bn(SG["revenue"]["services_total"]["q3_2025"]),
         bn(SG["revenue"]["services_total"]["q3_2026"]),
         sg(SG["revenue"]["services_total"]["q3_2026"]
            / SG["revenue"]["services_total"]["q3_2025"] - 1),
         bn(SG["operating_income"]["services"]["q3_2026"]),
         pct(SG["operating_income"]["services"]["q3_2026"]
             / SG["revenue"]["services_total"]["q3_2026"])],
        ["구글 클라우드", bn(SG["revenue"]["cloud"]["q3_2025"]),
         bn(SG["revenue"]["cloud"]["q3_2026"]),
         sg(SG["revenue"]["cloud"]["q3_2026"]
            / SG["revenue"]["cloud"]["q3_2025"] - 1),
         bn(SG["operating_income"]["cloud"]["q3_2026"]),
         pct(SG["operating_income"]["cloud"]["q3_2026"]
             / SG["revenue"]["cloud"]["q3_2026"])],
        ["기타 투자(Other Bets)", bn(SG["revenue"]["other_bets"]["q3_2025"]),
         bn(SG["revenue"]["other_bets"]["q3_2026"]),
         sg(SG["revenue"]["other_bets"]["q3_2026"]
            / SG["revenue"]["other_bets"]["q3_2025"] - 1),
         bn(SG["operating_income"]["other_bets"]["q3_2026"]), "—"],
        ["알파벳 공통(AI 연구개발)", "—", "—", "—",
         bn(SG["operating_income"]["alphabet_level"]["q3_2026"]), "—"],
        ["**연결**", bn(SG["revenue"]["total"]["q3_2025"]),
         bn(SG["revenue"]["total"]["q3_2026"]),
         sg(SG["revenue"]["total"]["q3_2026"]
            / SG["revenue"]["total"]["q3_2025"] - 1),
         bn(SG["operating_income"]["total"]["q3_2026"]),
         pct(SG["operating_income"]["total"]["q3_2026"]
             / SG["revenue"]["total"]["q3_2026"])],
    ]})
    b.append({"t": "note", "x":
              f"단위 십억 달러. 클라우드 매출이 "
              f"{sg(SG['revenue']['cloud']['q3_2026'] / SG['revenue']['cloud']['q3_2025'] - 1)} "
              f"늘면서 영업이익률이 "
              f"{pct(SG['operating_income']['cloud']['q3_2025'] / SG['revenue']['cloud']['q3_2025'])}에서 "
              f"{pct(SG['operating_income']['cloud']['q3_2026'] / SG['revenue']['cloud']['q3_2026'])}로 "
              f"올랐습니다. 직원수는 {SG['employees']['q3_2025']:,.0f}명에서 "
              f"{SG['employees']['q3_2026']:,.0f}명. 9개월 누적으로도 매출 "
              f"{sg(A['actual_growth_revenue_9m'])}, 영업이익 "
              f"{sg(A['actual_growth_operating_income_9m'])}입니다."})

    b.append({"t": "h3", "x": "(2) 보고 EPS 감소는 영업이 아니라 평가손익입니다"})
    h = REL["headline"]
    b.append({"t": "table", "headers": ["항목", "Q3 2025", "Q3 2026", "증감"],
              "rows": [
        ["영업이익", bn(h["operating_income_q3_2025"]),
         bn(h["operating_income_q3_2026"]),
         sg(h["operating_income_q3_2026"] / h["operating_income_q3_2025"] - 1)],
        ["기타수익(평가손익)", bn(h["other_income_q3_2025"]),
         bn(h["other_income_q3_2026"]), "부호 반전"],
        ["보통주귀속 순이익", bn(h["net_income_q3_2025"]),
         bn(h["net_income_q3_2026"]),
         sg(h["net_income_q3_2026"] / h["net_income_q3_2025"] - 1)],
        ["희석 EPS", usd(h["eps_q3_2025"]), usd(h["eps_q3_2026"]),
         sg(h["eps_q3_2026"] / h["eps_q3_2025"] - 1)],
    ]})
    b.append({"t": "p", "x":
              f"영업이익은 늘었는데 순이익과 EPS가 줄었습니다. 차이는 전부 "
              f"기타수익입니다 — 작년 3분기 +{bn(h['other_income_q3_2025'])}십억에서 "
              f"올해 {bn(h['other_income_q3_2026'])}십억으로 뒤집혔습니다. "
              f"이것은 비상장 투자지분을 시가로 다시 평가한 결과(ASU 2016-01)이고, "
              f"현금이 오가지 않습니다."})
    b.append({"t": "p", "x":
              f"**기간을 9개월로 늘리면 방향이 반대**입니다. 9개월 기타수익은 "
              f"+{bn(A['other_income_9m_2026'])}십억 달러(전년 "
              f"{bn(A['other_income_9m_2025'])}십억), 세전이익 "
              f"{bn(A['pretax_9m_2026'])}십억, 순이익 "
              f"{bn(A['net_income_9m_2026'])}십억(전년 "
              f"{bn(A['net_income_9m_2025'])}십억), 희석 EPS "
              f"{usd(A['eps_diluted_9m_2026'])}(전년 "
              f"{usd(A['eps_diluted_9m_2025'])})입니다. 같은 회사가 분기로는 "
              f"{sg(h['eps_q3_2026'] / h['eps_q3_2025'] - 1, 0)} 감익, 9개월로는 "
              f"{A['net_income_9m_2026'] / A['net_income_9m_2025']:.1f}배 "
              f"증익으로 보입니다. "
              f"**알파벳의 보고 순이익은 이제 영업을 설명하지 못합니다.** "
              f"이 보고서가 순이익이 아니라 영업이익에서 출발하는 이유입니다."})

    b.append({"t": "h3", "x": "(3) 시장이 반응한 것: 잉여현금흐름과 자금조달"})
    b.append({"t": "table", "headers":
              ["기간", "영업현금흐름", "capex", "잉여현금흐름"],
              "rows": [[p["period"], bn(p["operating_cash_flow"]),
                        bn(p["capex"]), bn(p["free_cash_flow"])]
                       for p in REL["cash_flow"]]})
    b.append({"t": "note", "x":
              "단위 십억 달러. 회사 자신의 정의(영업현금흐름 − capex)이고, "
              "발표문의 조정표에서 읽었습니다."})
    b.append({"t": "p", "x":
              f"네 분기 만에 잉여현금흐름이 +{bn(quarters[0]['free_cash_flow'])}십억에서 "
              f"{bn(quarters[3]['free_cash_flow'])}십억으로 돌아섰습니다. "
              f"TTM으로는 아직 +{bn(ttm['free_cash_flow'])}십억이지만, 이는 "
              f"시가총액의 {pct(ttm['free_cash_flow'] / mc, 1)}에 불과합니다. "
              f"capex가 TTM {bn(-ttm['capex'])}십억으로 영업현금흐름 "
              f"{bn(ttm['operating_cash_flow'])}십억의 "
              f"{pct(-ttm['capex'] / ttm['operating_cash_flow'], 0)}를 "
              f"먹고 있습니다."})
    b.append({"t": "p", "x":
              "그 차이를 메운 것이 자금조달입니다. 그리고 **여기서 알파벳의 "
              "성격이 바뀌었습니다.**"})
    b.append({"t": "table", "headers":
              ["재무활동 (9개월 누적)", "2025", "2026"], "rows": [
        ["자사주 매입", bn(FIN["repurchases"]["nine_months_2025"]),
         bn(FIN["repurchases"]["nine_months_2026"])],
        ["차입 조달", bn(FIN["debt_issued"]["nine_months_2025"]),
         bn(FIN["debt_issued"]["nine_months_2026"])],
        ["보통주 발행(ATM)", bn(FIN["common_issued"]["nine_months_2025"]),
         bn(FIN["common_issued"]["nine_months_2026"])],
        ["우선주 발행", bn(FIN["preferred_issued"]["nine_months_2025"]),
         bn(FIN["preferred_issued"]["nine_months_2026"])],
        ["배당", bn(FIN["dividends"]["nine_months_2025"]),
         bn(FIN["dividends"]["nine_months_2026"])],
        ["**외부자금 조달 합계**", "—",
         bn(FIN["external_capital_raised_9m_2026"])],
    ]})
    b.append({"t": "p", "x":
              f"단위 십억 달러. 작년 9개월에 {bn(-FIN['repurchases']['nine_months_2025'])}십억 "
              f"달러어치 자기 주식을 사들였던 회사가, 올해 9개월에는 "
              f"**한 주도 사지 않고** 차입·보통주·우선주로 "
              f"{bn(FIN['external_capital_raised_9m_2026'])}십억 달러를 "
              f"끌어왔습니다. 주주 입장에서 주식 수를 줄여주던 힘이 사라졌고, "
              f"ATM 프로그램으로 신주가 나오고 있습니다"
              f"(3분기에만 Class A 1,200만주 +$4.3십억, Class C 2,400만주 "
              f"+$8.1십억, 잔여 한도 $27.6십억). 장기채도 "
              f"{bn(A['balance_sheets']['2025-12-31']['debt'], 0)}십억에서 "
              f"{bn(A['balance_sheets']['2026-09-30']['debt'], 0)}십억으로 "
              f"늘었습니다."})

    # ------------------------------------------------------- 투자기준 적용
    b.append({"t": "h2", "x": "2. 투자기준 적용 — 사업의 질"})
    b.append({"t": "p", "x":
              "ROIC는 분모를 어디까지 보느냐에 따라 달라집니다. 네 가지를 "
              "모두 적습니다. 어느 하나가 정답이 아니라, 네 수치의 간격 자체가 "
              "지금 알파벳의 상태를 말해 줍니다."})
    b.append({"t": "table", "headers":
              ["투하자본 기준", "기초", "기말", "평균", "ROIC", "스프레드"],
              "rows": [
        [label, bn(V[k]["opening"], 0), bn(V[k]["closing"], 0),
         bn(V[k]["average"], 0), pct(V[k]["roic_ttm"]),
         sg(V[k]["spread_ttm"])]
        for k, label in (("reported", "보고 기준"),
                         ("operating", "영업(−영업권·무형)"),
                         ("in_service", "가동(−미가동설비)"),
                         ("in_service_ex_stakes", "가동−투자지분"))]})
    b.append({"t": "note", "x":
              f"단위 십억 달러. NOPAT {bn(A['nopat_ttm'])}십억(TTM 영업이익 "
              f"{bn(A['operating_income_ttm'])}십억 × (1−{pct(A['tax_rate_ttm'])})), "
              f"분모는 기초·기말 평균. 자본비용 {pct(WACC, 0)}."})
    b.append({"t": "p", "x":
              f"보고 기준 {pct(V['reported']['roic_ttm'])}와 가동 기준 "
              f"{pct(V['in_service']['roic_ttm'])}의 차이는 전부 **아직 아무것도 "
              f"벌지 않는 설비**입니다. 미가동 자산이 작년 말 {bn(nis0, 0)}십억에서 "
              f"{bn(nis, 0)}십억으로 늘었습니다. 투하자본의 상당 부분이 "
              f"가동 대기 중이라는 뜻이고, 이것이 좋은 소식인지 나쁜 소식인지는 "
              f"**가동됐을 때 얼마를 버는지**에 달려 있습니다."})
    b.append({"t": "table", "headers": ["회계연도", "ROIC", "영업이익",
                                        "투하자본(평균)"],
              "rows": [[f"FY{y['fiscal_year']}", pct(y["roic"]),
                        bn(y["operating_income"]),
                        bn(y["invested_capital_avg"])]
                       for y in REC["years"]]
              + [["TTM 2026-09", pct(V["reported"]["roic_ttm"]),
                  bn(A["operating_income_ttm"]),
                  bn(V["reported"]["average"])]]})
    b.append({"t": "note", "x":
              f"단위 십억 달러. 50개사 조사(roic/roic.json, 생성 "
              f"{REC['generated']})의 보고 기준 ROIC에 이번 TTM을 이어 붙였습니다. "
              f"10년 창 {REC['window'][0]}–{REC['window'][1]}, 중위 "
              f"{pct(REC['summary']['roic_median'])}, "
              f"{REC['summary']['years_above_wacc']}/10년 문턱 초과, "
              f"판정 \"{REC['summary']['verdict']}\"."})
    b.append({"t": "p", "x":
              f"**이 표가 이 보고서에서 가장 중요합니다.** 10년 내내 문턱을 "
              f"넘었다는 사실은 합격이지만, 동시에 ROIC가 "
              f"FY{peak['fiscal_year']} {pct(peak['roic'])}에서 추세적으로 "
              f"내려오고 있습니다. 영업이익은 그 사이 "
              f"{bn(peak['operating_income'])}십억 → "
              f"{bn(last['operating_income'])}십억으로 "
              f"{last['operating_income'] / peak['operating_income']:.2f}배 "
              f"늘었지만, 투하자본은 {bn(peak['invested_capital_avg'])}십억 → "
              f"{bn(last['invested_capital_avg'])}십억으로 "
              f"{last['invested_capital_avg'] / peak['invested_capital_avg']:.2f}배 "
              f"늘었습니다. 자본이 이익보다 빠르게 늘면 ROIC는 떨어집니다."})
    b.append({"t": "table", "headers": ["증분 수익성 (FY2025 → TTM)", "수치"],
              "rows": [
        ["ΔNOPAT", f"{bn(A['incremental']['delta_nopat'])}십억 달러"],
        ["Δ투하자본(보고)",
         f"{bn(A['incremental']['delta_capital_reported'])}십억 달러"],
        ["증분 ROIC(보고)",
         pct(A["incremental"]["incremental_roic_reported"])],
        ["Δ투하자본(가동−지분)",
         f"{bn(A['incremental']['delta_capital_in_service_ex_stakes'])}십억 달러"],
        ["증분 ROIC(가동−지분)",
         pct(A["incremental"]["incremental_roic_in_service_ex_stakes"])],
    ]})
    b.append({"t": "note", "x": A["incremental"]["note"]})

    b.append({"t": "h3", "x": "재무 안전성"})
    s26 = A["balance_sheets"]["2026-09-30"]
    s25 = A["balance_sheets"]["2025-12-31"]
    b.append({"t": "table", "headers": ["항목", "2025-12-31", "2026-09-30",
                                        "증감"], "rows": [
        [label, bn(s25[k], 0), bn(s26[k], 0), bn(s26[k] - s25[k], 0)]
        for k, label in (("equity", "자기자본"),
                         ("debt", "이자부 장기차입금"),
                         ("cash_and_securities", "현금·단기투자"),
                         ("goodwill", "영업권"),
                         ("intangibles", "무형자산"),
                         ("non_marketable_securities", "비시장성 투자지분"),
                         ("assets_not_yet_in_service", "미가동 설비"),
                         ("total_assets", "총자산"))]})
    b.append({"t": "note", "x":
              f"단위 십억 달러. 순현금 {bn(net_cash, 0)}십억 달러"
              f"(현금·단기투자 {bn(s26['cash_and_securities'], 0)} − 차입 "
              f"{bn(s26['debt'], 0)}). 차입이 9개월에 "
              f"{bn(s26['debt'] - s25['debt'], 0)}십억 늘었지만 여전히 "
              f"순현금 상태입니다."})

    # ------------------------------------------------------------- 가격 판정
    b.append({"t": "h2", "x": "3. 투자기준 적용 — 가격"})
    b.append({"t": "p", "x":
              f"사업의 질은 합격입니다. 남은 질문은 "
              f"**{usd(px)}이 그 사업을 연 {pct(WACC, 0)}으로 사는 가격인가**입니다. "
              f"세 가지 방법으로 봤고, 셋 다 같은 방향을 가리킵니다."})

    b.append({"t": "h3", "x": "(1) 지금 벌고 있는 것으로만 보면"})
    b.append({"t": "table", "headers": ["항목", "수치"], "rows": [
        ["시가총액", f"{bn(mc, 0)}십억 달러"],
        ["주식수", f"{A['shares_outstanding'] / BN:,.3f}십억 주"],
        ["TTM NOPAT", f"{bn(A['nopat_ttm'])}십억 달러"],
        ["NOPAT 수익률", pct(A["nopat_yield"])],
        ["주가/NOPAT", f"{A['price_to_nopat']:.1f}배"],
        ["TTM 잉여현금흐름", f"{bn(ttm['free_cash_flow'])}십억 달러"],
        ["주가/잉여현금흐름", f"{A['price_to_fcf_ttm']:.0f}배"],
        [f"{pct(WACC, 0)} 수익에 필요한 NOPAT",
         f"{bn(A['nopat_required_for_10pct'], 0)}십억 달러"],
        ["현재 NOPAT의 몇 배인가",
         f"{A['multiple_of_current_nopat']:.2f}배"],
    ]})
    b.append({"t": "p", "x":
              f"성장이 없다고 가정하면 {pct(A['nopat_yield'])}입니다. "
              f"문턱의 3분의 1 수준이고, {pct(WACC, 0)}을 받으려면 NOPAT이 "
              f"지금의 {A['multiple_of_current_nopat']:.2f}배가 돼야 합니다. "
              f"다만 알파벳은 성장하는 회사이므로 이 숫자 하나로 "
              f"판정하면 안 됩니다."})

    b.append({"t": "h3", "x": "(2) 주주이익으로 보면"})
    b.append({"t": "table", "headers": ["주주이익 기준", "금액", "함의 수익률"],
              "rows": [
        ["하단: capex 전액을 비용으로",
         f"{bn(A['owner_earnings_lower'])}십억 달러",
         pct(A["implied_return_lower"])],
        ["상단: 감가상각만 비용으로",
         f"{bn(A['owner_earnings_upper'])}십억 달러",
         pct(A["implied_return_upper"])],
    ]})
    b.append({"t": "p", "x":
              f"하단은 설비투자 전부를 올해 비용으로 보는 관점이고(= 잉여현금흐름), "
              f"상단은 감가상각 {bn(A['depreciation_ttm'])}십억만 비용으로 "
              f"보는 관점입니다. 진실은 둘 사이에 있는데, **지금은 그 간격이 "
              f"비정상적으로 넓습니다** — 이미 쓴 {bn(nis, 0)}십억 달러가 "
              f"가동 전이라 감가상각에 아직 반영되지 않았기 때문입니다. "
              f"어느 쪽을 잡아도 {pct(WACC, 0)} 문턱 아래입니다."})
    b.append({"t": "note", "x":
              f"참고로 TTM 잉여현금흐름에 미가동 설비 증가분 {bn(nis - nis0)}십억을 "
              f"되돌려 더하면 {bn(A['free_cash_flow_before_new_construction'])}십억 "
              f"달러가 됩니다. \"새 설비를 짓지 않았다면 벌었을 현금\"이지, "
              f"주주가 받을 수 있는 현금은 아닙니다."})

    b.append({"t": "h3", "x": "(3) 가격이 요구하는 성장률로 보면"})
    b.append({"t": "p", "x":
              f"가장 쓸모 있는 질문은 \"내재가치가 얼마냐\"가 아니라 "
              f"**\"이 가격이 맞으려면 무엇이 사실이어야 하나\"**입니다. "
              f"영구성장 모형에 {pct(WACC, 0)} 할인율과 가동 기준 증분 ROIC "
              f"{pct(V['in_service']['roic_ttm'])}를 넣고 현재 시가총액이 "
              f"나오는 성장률을 역산하면 **연 "
              f"{pct(A['implied_growth_at_10pct'])}**입니다."})
    b.append({"t": "formula", "x":
              "기업가치 = NOPAT × (1 − 성장률 ÷ 증분ROIC) ÷ (자본비용 − 성장률)"})
    b.append({"t": "table", "headers":
              ["영구 성장률", "기업가치", "주당 가치", "현재가 대비"],
              "rows": [[pct(e["growth"], 0), f"{bn(e['value'], 0)}십억",
                        usd(e["value_per_share"], 0), sg(e["vs_price"], 0)]
                       for e in A["growth_sensitivity"]]})
    b.append({"t": "table", "headers": ["주가", "시가총액", "함의 영구성장률"],
              "rows": [[usd(e["price"]), f"{bn(e['market_cap'], 0)}십억",
                        pct(e["implied_growth"])]
                       for e in A["implied_growth_by_price"]]})
    b.append({"t": "p", "x":
              f"**이 모형의 결론보다 모형의 민감도가 더 중요합니다.** "
              f"성장률 5%면 주당 {usd(A['growth_sensitivity'][2]['value_per_share'], 0)}, "
              f"8%면 {usd(A['growth_sensitivity'][5]['value_per_share'], 0)}입니다. "
              f"3%포인트 차이로 가치가 2.3배 벌어집니다. 성장률이 할인율에 "
              f"가까워질수록 분모가 0으로 가기 때문입니다. 그래서 이 표를 "
              f"\"적정주가\"로 읽어서는 안 되고, **현재가가 요구하는 가정을 "
              f"드러내는 장치**로 읽어야 합니다."})
    b.append({"t": "p", "x":
              f"요구 성장률 {pct(A['implied_growth_at_10pct'])}는 알파벳의 "
              f"현재 성장률(9개월 영업이익 "
              f"{sg(A['actual_growth_operating_income_9m'])})보다 한참 낮습니다. "
              f"그러니 \"지금 속도가 유지되면\" 현재가는 쌉니다. 문제는 영구히 "
              f"{pct(A['implied_growth_at_10pct'])}라는 조건이 "
              f"**명목 세계경제 성장률보다 높다**는 데 있습니다. "
              f"알파벳이 영구히 세계경제보다 빠르게 성장한다는 가정을 사는 "
              f"것이고, 그것은 전제이지 안전마진이 아닙니다."})
    b.append({"t": "quote", "x":
              f"8월 10일 {usd(355.84)} 당시와 비교하면, 같은 모형의 요구 "
              f"성장률이 {pct([e['implied_growth'] for e in A['implied_growth_by_price'] if abs(e['price'] - 355.84) < 0.01][0])}에서 "
              f"{pct(A['implied_growth_at_10pct'])}로 내려왔습니다. "
              f"가격이 {sg(px / 355.84 - 1, 0)} 빠진 만큼 요구 조건이 "
              f"느슨해진 것은 분명한 개선입니다. 다만 아직 넘지 못했습니다."})

    # ---------------------------------------------------------------- 판정
    b.append({"t": "h2", "x": "4. 판정과 행동"})
    b.append({"t": "p", "x":
              f"**합격선 아래입니다 — 그러나 \"비싼 나쁜 회사\"가 아니라 "
              f"\"아직 비싼 아주 좋은 회사\"입니다.** 둘은 다르게 다뤄야 합니다."})
    b.append({"t": "bullets", "x": [
        f"**사업:** 합격. ROIC 보고 {pct(V['reported']['roic_ttm'])}·가동 "
        f"{pct(V['in_service']['roic_ttm'])}, 10년 내내 문턱 초과, "
        f"순현금 {bn(net_cash, 0)}십억 달러. 50개사 조사 기준 상위권입니다.",
        f"**가격:** 불합격. 요구 영구성장률 "
        f"{pct(A['implied_growth_at_10pct'])}, 주주이익 수익률 "
        f"{pct(A['implied_return_lower'])}~{pct(A['implied_return_upper'])}. "
        f"{pct(WACC, 0)} 문턱을 넘지 못합니다.",
        f"**핵심 불확실성:** 설비가 아니라 설비의 수익성입니다. "
        f"미가동 {bn(nis, 0)}십억 달러가 가동된 뒤의 ROIC가 가동 기준 "
        f"{pct(V['in_service']['roic_ttm'])}에 가까우면 현재가는 쌉니다. "
        f"보고 기준 {pct(V['reported']['roic_ttm'])} 아래로 수렴하면 비쌉니다. "
        f"지금 가진 자료로는 **어느 쪽인지 알 수 없습니다.**",
        f"**분기 EPS를 신호로 쓰지 마십시오.** 평가손익이 분기 순이익을 "
        f"{bn(abs(REL['headline']['other_income_q3_2026']))}십억 단위로 "
        f"흔듭니다. 영업이익과 잉여현금흐름만 보십시오.",
    ]})
    b.append({"t": "h3", "x": "다음에 확인할 것"})
    b.append({"t": "table", "headers": ["감시 지표", "지금", "판정이 바뀌는 지점"],
              "rows": [
        ["미가동 설비", f"{bn(nis, 0)}십억 달러",
         "가동으로 넘어가는 속도와, 그때 영업이익이 함께 오르는지"],
        ["분기 잉여현금흐름", f"{bn(quarters[3]['free_cash_flow'])}십억 달러",
         "플러스 복귀 시점. 두 분기 더 마이너스면 자금조달 압력 심화"],
        ["감가상각", f"9개월 {sg(A['depreciation_9m_2026'] / A['depreciation_9m_2025'] - 1, 0)}",
         "미가동 설비가 가동되며 뛰는 폭. 영업이익률 하락 압력"],
        ["클라우드 영업이익률",
         pct(SG["operating_income"]["cloud"]["q3_2026"]
             / SG["revenue"]["cloud"]["q3_2026"]),
         "상승 지속 여부. capex를 정당화하는 유일한 증거"],
        ["자사주 매입", "0",
         "재개 여부. 재개는 capex 정점 통과 신호"],
        ["주식수", f"{A['shares_outstanding'] / BN:,.3f}십억 주",
         "ATM 잔여 한도 $27.6십억이 소진되며 늘어나는지"],
        ["보고 기준 ROIC", pct(V["reported"]["roic_ttm"]),
         f"{pct(WACC, 0)} 접근 시 사업 판정 자체가 흔들림"],
    ]})

    # ---------------------------------------------------------- 방법과 한계
    b.append({"t": "h2", "x": "5. 방법과 한계"})
    b.append({"t": "bullets", "x": [
        "**ROIC 정의는 프로젝트 기준 그대로입니다.** NOPAT = 보고된 영업이익 "
        "× (1−실효세율), 투하자본 = 자기자본 + 이자부차입 − 현금·단기투자, "
        "분모는 기초·기말 평균. 50개사와 같은 잣대로 재야 비교가 됩니다.",
        f"**세율은 주의가 필요합니다.** {A['nopat_sensitivity_note']}. "
        f"TTM 실효세율 {pct(A['tax_rate_ttm'])}는 "
        f"{bn(A['other_income_9m_2026'])}십억 달러의 평가이익이 섞인 "
        f"세전이익에서 나온 값입니다. 법정세율로 바꿔도 판정은 바뀌지 "
        f"않으므로 규칙상 수치를 본문에 썼습니다.",
        "**사업부별 투하자본은 공시되지 않습니다.** 클라우드 ROIC를 만들지 "
        "않았습니다. 분모를 발명하면 그 가정이 결론이 됩니다.",
        f"**주가는 {PH['last']['date']} 종가 {usd(px)}**이고 "
        f"{D['generated']}에 받았습니다. 질문하신 \"280불\"은 장중 저가이며, "
        f"판정은 ±$3에 달라지지 않습니다.",
        f"**검증.** `python3 verify_goog_price.py --mutate` — 항등식·앵커·"
        f"재산출 270건, 변이 검정 32건. 앵커는 8-K 발표문과 10-Q에서 손으로 "
        f"읽은 수치이며, 지우면 안 됩니다.",
    ]})
    b.append({"t": "note", "x":
              f"출처: SEC EDGAR. 10-Q {D['filings']['10-Q']['accession']} "
              f"({D['filings']['10-Q']['filed']} 제출, 기말 "
              f"{D['filings']['10-Q']['period_end']}), 8-K "
              f"{D['filings']['8-K']['accession']} "
              f"({D['filings']['8-K']['filed']} 제출). "
              f"SEC 등록명 {REC['company_name']}, CIK {D['cik']}, "
              f"티커 {'/'.join(sorted(set(D['tickers'])))} "
              f"({'/'.join(sorted(set(D['exchanges'])))}). "
              f"10년 ROIC는 roic/roic.json(생성 {REC['generated']})."})
    return b


# ------------------------------------------------------------------ 마크다운
def write_md(bs):
    out = []
    for b in bs:
        t = b["t"]
        if t == "h1":
            out += [f"# {b['x']}", ""]
        elif t == "h2":
            out += ["", f"## {b['x']}", ""]
        elif t == "h3":
            out += [f"### {b['x']}", ""]
        elif t == "p":
            out += [b["x"], ""]
        elif t == "note":
            out += [f"> {b['x']}", ""]
        elif t == "quote":
            out += [f"> {b['x']}", ""]
        elif t == "formula":
            out += ["```", b["x"], "```", ""]
        elif t == "bullets":
            out += [f"- {x}" for x in b["x"]] + [""]
        elif t == "table":
            h = b["headers"]
            align = ["left"] + ["right"] * (len(h) - 1)
            if len(h) <= 3:
                align = ["left"] * len(h)
            out.append("| " + " | ".join(h) + " |")
            out.append("|" + "|".join(
                {"left": ":--", "right": "--:"}[a] for a in align) + "|")
            for r in b["rows"]:
                out.append("| " + " | ".join(str(x) for x in r) + " |")
            out.append("")
    with open(MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"wrote {MD} ({len(out)} 줄)")


# ----------------------------------------------------------------------- 워드
def write_docx(bs):
    """
    The shared Node renderer, which names its fields differently.

    It reads `text` on prose blocks, `items` on bullets, and `text` plus `src`
    on a quote. The block list above uses one key, `x`, for all of them, so
    the translation happens here rather than scattering renderer-specific
    names through the content.
    """
    payload = []
    for b in bs:
        blk = dict(b)
        x = blk.pop("x", None)
        if blk["t"] == "bullets":
            blk["items"] = x
        elif blk["t"] == "quote":
            blk["text"] = x
            blk["src"] = f"{NAME} 분석, {D['generated']}"
        elif x is not None:
            blk["text"] = x
        if blk["t"] == "table" and "widths" not in blk:
            n = len(blk["headers"])
            first = max(12, min(30, int(100 / n) + 10))
            blk["widths"] = [first] + [(100 - first) / (n - 1)] * (n - 1)
            blk["numeric"] = list(range(1, n))
        payload.append(blk)
    with open(DOCX_JSON, "w", encoding="utf-8") as fh:
        json.dump({"title": f"{NAME} 주가 하락 원인과 투자기준 판정",
                   "blocks": payload}, fh, indent=1, ensure_ascii=False)
    subprocess.run(["node", "export_memo_docx.js",
                    os.path.relpath(DOCX_JSON, HERE),
                    os.path.basename(DOCX)],
                   cwd=HERE, check=True)
    print(f"wrote {DOCX}")


def main():
    bs = blocks()
    write_md(bs)
    write_docx(bs)


if __name__ == "__main__":
    main()
