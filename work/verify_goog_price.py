#!/usr/bin/env python3
"""
goog_price.json 검증.

세 종류의 검사를 겁니다.

- **항등식.** 공시 표 안에서 반드시 맞아야 하는 관계. 매출 − 비용 = 영업이익,
  영업이익 + 기타수익 = 세전이익, 유형자산 가동분 + 미가동분 − 감가상각누계 =
  순장부가, FCF = 영업현금흐름 − capex, 사업부 합 = 연결 합계. 파서가 열을
  밀어 읽거나 행을 잘못 집으면 여기서 깨집니다.

- **앵커.** 8-K 발표문과 10-Q 표지에서 손으로 읽은 숫자. 항등식과
  트립와이어는 검사 대상과 같은 데이터로 계산되므로 *내부적으로 일관된 틀린
  값은 둘 다 통과합니다.* 공시 원문에서 눈으로 읽은 앵커만이 데이터 자체가
  틀렸을 때 실패합니다.

- **재산출.** analysis 블록의 모든 파생값을 financials 원표에서 다시 계산해
  대조합니다. analysis를 믿지 않고 원표에서 출발합니다.

--mutate 는 값을 고의로 훼손해 검사가 실제로 실패하는지 확인합니다. 훼손해도
통과하는 검사는 검사가 아닙니다.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "goog", "goog_price.json")
M = 1_000_000.0
WACC = 0.10
# 유형자산 주석에서 각 범주의 금액 행 라벨. 같은 범주에 "..., percentage" 행이
# 함께 있어 부분일치로는 특정되지 않습니다.
GROSS = "Property, plant and equipment, gross"

# 8-K(0001652044-26-000080) 발표문과 10-Q(0001652044-26-000084) 재무제표에서
# 손으로 읽은 값. 단위는 공시 그대로 백만 달러.
ANCHORS = {
    # 발표문 Q3 2026 Financial Highlights
    "q3_revenue": 127577,
    "q3_operating_income": 40576,
    "q3_other_income": -8221,
    "q3_net_income_to_common": 26170,
    "q3_eps_diluted": 2.12,
    "q3_operating_margin": 0.32,
    # 발표문 Supplemental Information — 사업부
    "q3_cloud_revenue": 30709,
    "q3_cloud_operating_income": 11121,
    "q3_services_operating_income": 39157,
    "q3_other_bets_operating_income": -2047,
    "q3_alphabet_level": -7655,
    "q3_employees": 204757,
    # 발표문 FCF 조정표 (분기 4개 + TTM)
    "ocf_q4_25": 52402, "capex_q4_25": -27851, "fcf_q4_25": 24551,
    "ocf_q1_26": 45790, "capex_q1_26": -35674, "fcf_q1_26": 10116,
    "ocf_q2_26": 39069, "capex_q2_26": -44924, "fcf_q2_26": -5855,
    "ocf_q3_26": 42290, "capex_q3_26": -51355, "fcf_q3_26": -9065,
    "ocf_ttm": 179551, "capex_ttm": -159804, "fcf_ttm": 19747,
    # 10-Q 손익계산서 9개월
    "nm_revenue": 357269,
    "nm_operating_income": 121042,
    "nm_other_income": 127478,
    "nm_pretax": 248520,
    "nm_tax": 47281,
    "nm_net_income": 201239,
    "nm_pretax_2025": 119709,
    "nm_net_income_2025": 97715,
    "nm_eps_diluted": 16.33,
    "nm_eps_diluted_2025": 7.99,
    "nm_eps_basic": 16.51,
    "nm_preferred_dividends": 384,
    # 10-Q 현금흐름표 9개월 — 자사주 매입이 0인 것이 이 분석의 핵심 사실
    "nm_repurchases": 0,
    "nm_debt_issued": 85222,
    "nm_common_issued": 42870,
    "nm_preferred_issued": 19063,
    "nm_depreciation": 21955,
    "nm_securities_gain": -126755,
    "nm_deferred_tax": 33077,
    # 10-Q 유형자산 주석
    # 발표문 Supplemental Information — 사업부·직원
    "q3_search_revenue": 63350,
    "q3_youtube_revenue": 11207,
    "q3_services_revenue": 96302,
    "q3_other_bets_revenue": 372,
    "q3_hedging": 194,
    "q3_cloud_revenue_exact": 30709,
    "not_in_service_sep26": 145270,
    "not_in_service_dec25": 78592,
    "ppe_net_sep26": 372827,
    "ppe_gross_in_service_sep26": 341100,
    "accum_depreciation_sep26": -113543,
}


class Checks:
    def __init__(self):
        self.passed = 0
        self.failures = []

    def eq(self, name, got, want, tol=0.0, rel=None):
        if got is None or want is None:
            self.failures.append(f"{name}: 값 없음 (got={got!r} want={want!r})")
            return
        limit = tol if rel is None else max(tol, abs(want) * rel)
        if abs(got - want) <= limit:
            self.passed += 1
        else:
            self.failures.append(
                f"{name}: {got:,.6g} != {want:,.6g} (허용 {limit:,.6g})")

    def true(self, name, cond, detail=""):
        if cond:
            self.passed += 1
        else:
            self.failures.append(f"{name}: 거짓 {detail}")


def row(table, label=None, element=None, context=None, index=None,
        monetary=None, label_exact=None):
    """
    표에서 행 하나. 값 없는 표제 행과 Abstract 태그는 건너뜁니다.

    label_exact 는 유형자산 주석 때문에 필요합니다. 각 범주 아래에 금액 행과
    "..., percentage" 행이 같은 context 로 나란히 있고, 수집기가 60.0(%)을
    monetary 로 표시해 두었습니다. 부분일치로는 두 행이 모두 걸립니다.

    반환값은 **달러**입니다. 공시 표는 백만 단위("$ in Millions")로 저장되어
    있고 analysis 블록은 달러로 계산하므로, 금액 행에 표의 배율을 곱해
    돌려줍니다. 두 단위를 섞으면 앵커가 1,000,000배 틀립니다.
    """
    best = None
    for r in table["rows"]:
        if all(v is None for v in r["values"]):
            continue
        el = r.get("element") or ""
        if el.endswith(("Abstract", "LineItems")):
            continue
        if monetary is not None and bool(r.get("monetary")) != monetary:
            continue
        if element and not el.endswith(element):
            continue
        if label and label.lower() not in r["label"].lower():
            continue
        if label_exact and r["label"].strip() != label_exact:
            continue
        if context is not None and (r.get("context") or "") != context:
            continue
        if best is None:
            best = r
        elif index is None:
            # 같은 조건에 두 행이 맞으면 어느 것을 집었는지 알 수 없습니다.
            raise SystemExit(
                f"행 특정 실패: label={label!r} element={element!r} "
                f"context={context!r} — '{best['label']}' 와 '{r['label']}' 둘 다 맞음")
    if best is None:
        raise SystemExit(f"행 없음: label={label!r} element={element!r} "
                         f"context={context!r} ({table['short_name']})")
    k = table["scale"] if best.get("monetary") else 1.0
    vals = [None if v is None else v * k for v in best["values"]]
    return vals if index is None else vals[index]


def verify(d, c):
    fin = d["financials"]
    ops, bs, cf, ppe, seg = (fin["operations"], fin["balance_sheet"],
                             fin["cash_flows"], fin["ppe"], fin["segments"])
    rel = d["release"]
    a = d["analysis"]
    Q3, Q3P, NM, NMP = 0, 1, 2, 3
    SEP, DEC = 0, 1

    # ---- 표 구조 ----------------------------------------------------------
    c.true("손익계산서 4열(분기2+9개월2)", len(ops["columns"]) == 4,
           str(ops["columns"]))
    c.true("대차대조표 2열", len(bs["columns"]) == 2, str(bs["columns"]))
    c.true("손익계산서 배율 백만", ops["scale"] == M, str(ops["scale"]))
    c.true("대차대조표 배율 백만", bs["scale"] == M, str(bs["scale"]))

    # ---- 항등식: 손익계산서 ------------------------------------------------
    rev = row(ops, element="Revenues")
    costs = row(ops, element="CostsAndExpenses")
    oi = row(ops, element="OperatingIncomeLoss")
    other = row(ops, element="NonoperatingIncomeExpense")
    pretax = row(ops, element="NoncontrollingInterest")
    tax = row(ops, element="IncomeTaxExpenseBenefit")
    net = row(ops, element="NetIncomeLoss")
    pref_div = row(ops, element="PreferredStockDividendsIncomeStatementImpact")
    to_common = row(ops, element="NetIncomeLossAvailableToCommonStockholdersBasic")
    for i, nm in ((Q3, "Q3'26"), (Q3P, "Q3'25"), (NM, "9M'26"), (NMP, "9M'25")):
        c.eq(f"항등식 매출−비용=영업이익 {nm}", rev[i] - costs[i], oi[i], tol=1)
        c.eq(f"항등식 영업이익+기타=세전 {nm}", oi[i] + other[i], pretax[i], tol=1)
        c.eq(f"항등식 세전−법인세=순이익 {nm}", pretax[i] - tax[i], net[i], tol=1)
        c.eq(f"항등식 순이익−우선주배당=보통주귀속 {nm}",
             net[i] - pref_div[i], to_common[i], tol=1)
    # 비용 소계는 네 항목의 합
    parts = [row(ops, element=e) for e in
             ("CostOfRevenue", "ResearchAndDevelopmentExpense",
              "SellingAndMarketingExpense", "GeneralAndAdministrativeExpense")]
    for i, nm in ((Q3, "Q3'26"), (NM, "9M'26")):
        c.eq(f"항등식 비용 4항목 합 {nm}", sum(p[i] for p in parts), costs[i], tol=1)

    # ---- 항등식: 유형자산 --------------------------------------------------
    gross_in_service = row(ppe, context="Property and equipment, in service",
                           label_exact=GROSS)
    not_in_service = row(ppe, context="Assets not yet in service",
                         label_exact=GROSS)
    accum = row(ppe, label="accumulated depreciation")
    ppe_net = row(ppe, label="Property and equipment, net")
    for i, nm in ((SEP, "2026-09"), (DEC, "2025-12")):
        c.eq(f"항등식 가동+미가동−감가누계=순장부 {nm}",
             gross_in_service[i] + not_in_service[i] + accum[i], ppe_net[i],
             tol=1)
    # 가동분 총액은 세 범주의 합
    cats = [row(ppe, context=k, label_exact=GROSS) for k in
            ("Technical infrastructure", "Office space",
             "Corporate and other assets")]
    for i, nm in ((SEP, "2026-09"), (DEC, "2025-12")):
        c.eq(f"항등식 가동자산 3범주 합 {nm}", sum(x[i] for x in cats),
             gross_in_service[i], tol=1)

    # ---- 항등식: 현금흐름표 ------------------------------------------------
    ocf_q = row(cf, label="Net cash provided by operating activities")
    inv_q = row(cf, label="Net cash used in investing activities")
    fnc_q = row(cf, label="Net cash provided by (used in) financing")
    fx = row(cf, label="Effect of exchange rate")
    chg = row(cf, label="Net increase (decrease) in cash")
    beg = row(cf, label="beginning of period")
    end = row(cf, label="end of period")
    for i, nm in ((0, "9M'26"), (1, "9M'25")):
        c.eq(f"항등식 영업+투자+재무+환율=현금증감 {nm}",
             ocf_q[i] + inv_q[i] + fnc_q[i] + fx[i], chg[i], tol=1)
        c.eq(f"항등식 기초+증감=기말 {nm}", beg[i] + chg[i], end[i], tol=1)

    # ---- 항등식: FCF 조정표 (발표문) ---------------------------------------
    periods = rel["cash_flow"]
    c.true("FCF 표 5기간(분기4+TTM)", len(periods) == 5,
           str([p["period"] for p in periods]))
    quarters = [p for p in periods if not p["period"].startswith("TTM")]
    ttm = [p for p in periods if p["period"].startswith("TTM")][0]
    for p in periods:
        c.eq(f"항등식 FCF=영업현금+capex {p['period']}",
             p["operating_cash_flow"] + p["capex"], p["free_cash_flow"],
             tol=1.0, rel=1e-9)
    c.true("FCF 표 분기 4개", len(quarters) == 4, str(len(quarters)))
    for key in ("operating_cash_flow", "capex", "free_cash_flow"):
        c.eq(f"항등식 TTM={{4개 분기 합}} {key}",
             sum(q[key] for q in quarters), ttm[key], tol=1.0, rel=1e-9)

    # ---- 항등식: 사업부 ----------------------------------------------------
    seg_rev_total = row(seg, element="Revenues", context=None)
    c.true("사업부 표 매출 합계행 존재", seg_rev_total is not None)

    # ---- 앵커 (공시 원문에서 손으로 읽음) ----------------------------------
    A = ANCHORS
    c.eq("앵커 Q3 매출", rev[Q3], A["q3_revenue"] * M, rel=0)
    c.eq("앵커 Q3 영업이익", oi[Q3], A["q3_operating_income"] * M, rel=0)
    c.eq("앵커 Q3 기타수익", other[Q3], A["q3_other_income"] * M, rel=0)
    c.eq("앵커 Q3 보통주귀속순이익", to_common[Q3],
         A["q3_net_income_to_common"] * M, rel=0)
    c.eq("앵커 9M 매출", rev[NM], A["nm_revenue"] * M, rel=0)
    c.eq("앵커 9M 영업이익", oi[NM], A["nm_operating_income"] * M, rel=0)
    c.eq("앵커 9M 기타수익", other[NM], A["nm_other_income"] * M, rel=0)
    c.eq("앵커 9M 세전이익", pretax[NM], A["nm_pretax"] * M, rel=0)
    c.eq("앵커 9M 법인세", tax[NM], A["nm_tax"] * M, rel=0)
    c.eq("앵커 9M 순이익", net[NM], A["nm_net_income"] * M, rel=0)
    c.eq("앵커 Q3 영업이익률", oi[Q3] / rev[Q3], A["q3_operating_margin"],
         tol=0.005)
    c.eq("앵커 9M 세전이익 2025", pretax[NMP], A["nm_pretax_2025"] * M, rel=0)
    c.eq("앵커 9M 순이익 2025", net[NMP], A["nm_net_income_2025"] * M, rel=0)
    c.eq("앵커 9M 우선주배당", pref_div[NM], A["nm_preferred_dividends"] * M,
         rel=0)

    # 배율을 잘못 적용하는 세 종류 — 주식수, 퍼센트, 주당금액. 전부 실제로
    # 틀렸던 것이고, 각각 달러로 환산되면 안 됩니다.
    eps_d = row(ops, element="EarningsPerShareDiluted")
    eps_b = row(ops, element="EarningsPerShareBasic")
    c.eq("앵커 9M 희석EPS", eps_d[NM], A["nm_eps_diluted"], tol=0.001)
    c.eq("앵커 9M 희석EPS 2025", eps_d[NMP], A["nm_eps_diluted_2025"],
         tol=0.001)
    c.eq("앵커 9M 기본EPS", eps_b[NM], A["nm_eps_basic"], tol=0.001)
    c.eq("앵커 Q3 희석EPS (10-Q)", eps_d[Q3], A["q3_eps_diluted"], tol=0.001)
    c.true("트립와이어 EPS에 백만 배율이 적용되지 않음",
           all(0 < v < 1000 for v in eps_d + eps_b),
           str(eps_d + eps_b))
    c.true("트립와이어 기본EPS ≥ 희석EPS",
           all(b >= d - 1e-9 for b, d in zip(eps_b, eps_d)),
           f"{eps_b} vs {eps_d}")
    # 그리고 EPS 는 순이익과 주식수로 되짚을 수 있어야 합니다.
    c.eq("역산 9M 희석EPS ≈ 보통주귀속순이익 / 희석주식수",
         to_common[NM] / eps_d[NM] / 1e9, 12.3, tol=0.5)
    pct_rows = [r for r in ppe["rows"]
                if "percentage" in r["label"].lower()
                and any(v is not None for v in r["values"])]
    c.true("유형자산 주석에 퍼센트 행이 있음", len(pct_rows) > 0)
    c.true("트립와이어 퍼센트 행에 배율이 적용되지 않음",
           all(not r["monetary"] and all(0 <= v <= 100 for v in r["values"]
                                         if v is not None)
               for r in pct_rows),
           str([(r["monetary"], r["values"]) for r in pct_rows]))

    h = rel["headline"]
    c.eq("앵커 발표문 Q3 매출", h["revenue_q3_2026"], A["q3_revenue"] * M, rel=0)
    c.eq("앵커 발표문 Q3 영업이익", h["operating_income_q3_2026"],
         A["q3_operating_income"] * M, rel=0)
    c.eq("앵커 발표문 Q3 기타수익", h["other_income_q3_2026"],
         A["q3_other_income"] * M, rel=0)
    c.eq("앵커 발표문 Q3 희석EPS", h["eps_q3_2026"], A["q3_eps_diluted"],
         tol=0.001)
    c.eq("앵커 발표문 Q3 클라우드 매출", h["cloud_revenue_q3_2026"],
         A["q3_cloud_revenue"] * M, rel=0.001)
    # 발표문 수치는 10-Q 손익계산서와 같아야 합니다 — 두 공시가 어긋나면 파싱 오류.
    c.eq("교차확인 발표문 Q3 매출 = 10-Q", h["revenue_q3_2026"], rev[Q3], rel=0)
    c.eq("교차확인 발표문 Q3 영업이익 = 10-Q", h["operating_income_q3_2026"],
         oi[Q3], rel=0)
    c.eq("교차확인 발표문 Q3 기타수익 = 10-Q", h["other_income_q3_2026"],
         other[Q3], rel=0)
    c.eq("교차확인 발표문 Q3 보통주귀속 = 10-Q", h["net_income_q3_2026"],
         to_common[Q3], rel=0)

    for per, kq in (("Q4 2025", "q4_25"), ("Q1 2026", "q1_26"),
                    ("Q2 2026", "q2_26"), ("Q3 2026", "q3_26"),
                    ("TTM Q3 2026", "ttm")):
        p = [x for x in periods if x["period"] == per]
        c.true(f"FCF 표 기간 존재 {per}", len(p) == 1)
        if len(p) != 1:
            continue
        p = p[0]
        c.eq(f"앵커 영업현금 {per}", p["operating_cash_flow"],
             A[f"ocf_{kq}"] * M, rel=0)
        c.eq(f"앵커 capex {per}", p["capex"], A[f"capex_{kq}"] * M, rel=0)
        c.eq(f"앵커 FCF {per}", p["free_cash_flow"], A[f"fcf_{kq}"] * M, rel=0)

    c.eq("앵커 미가동자산 2026-09", not_in_service[SEP],
         A["not_in_service_sep26"] * M, rel=0)
    c.eq("앵커 미가동자산 2025-12", not_in_service[DEC],
         A["not_in_service_dec25"] * M, rel=0)
    c.eq("앵커 유형자산순액 2026-09", ppe_net[SEP], A["ppe_net_sep26"] * M, rel=0)
    c.eq("앵커 가동자산총액 2026-09", gross_in_service[SEP],
         A["ppe_gross_in_service_sep26"] * M, rel=0)
    c.eq("앵커 감가상각누계 2026-09", accum[SEP],
         A["accum_depreciation_sep26"] * M, rel=0)

    rep = row(cf, label="Repurchases of stock")
    c.eq("앵커 9M 자사주매입(=0)", rep[0], A["nm_repurchases"] * M, rel=0)
    c.true("자사주매입 전년 동기는 0이 아님 — 비교 기준", rep[1] < -1e10,
           f"{rep[1]:,.0f}")
    c.eq("앵커 9M 차입조달", row(cf, label="issuance of debt")[0],
         A["nm_debt_issued"] * M, rel=0)
    c.eq("앵커 9M 보통주발행", row(cf, label="issuance of common stock")[0],
         A["nm_common_issued"] * M, rel=0)
    c.eq("앵커 9M 우선주발행", row(cf, label="mandatory convertible preferred")[0],
         A["nm_preferred_issued"] * M, rel=0)
    c.eq("앵커 9M 감가상각비", row(cf, element="Depreciation")[0],
         A["nm_depreciation"] * M, rel=0)
    c.eq("앵커 9M 유가증권평가손익", row(cf, label="on debt and equity securities")[0],
         A["nm_securities_gain"] * M, rel=0)
    c.eq("앵커 9M 이연법인세", row(cf, label="Deferred income taxes")[0],
         A["nm_deferred_tax"] * M, rel=0)

    # ---- 재산출: analysis 블록을 원표에서 다시 계산 -------------------------
    fy = d["fy2025_from_engine"]
    oi_ttm = fy["operating_income"] - oi[NMP] + oi[NM]
    c.eq("재산출 TTM 영업이익", a["operating_income_ttm"], oi_ttm, rel=1e-9)
    c.eq("재산출 9M 영업이익 2026", a["operating_income_9m_2026"], oi[NM], rel=0)
    c.eq("재산출 9M 영업이익 2025", a["operating_income_9m_2025"], oi[NMP], rel=0)
    c.eq("재산출 9M 매출 2026", a["revenue_9m_2026"], rev[NM], rel=0)
    c.eq("재산출 9M 기타수익", a["other_income_9m_2026"], other[NM], rel=0)
    c.eq("재산출 TTM 실효세율", a["tax_rate_ttm"], tax[NM] / pretax[NM], rel=1e-12)
    c.eq("재산출 NOPAT(TTM 세율)", a["nopat_ttm"],
         oi_ttm * (1 - tax[NM] / pretax[NM]), rel=1e-12)
    c.eq("재산출 NOPAT(FY2025 세율)", a["nopat_fy2025"],
         oi_ttm * (1 - fy["effective_tax_rate"]), rel=1e-12)
    c.eq("재산출 감가상각 TTM", a["depreciation_ttm"],
         fy["depreciation"] - row(cf, element="Depreciation")[1]
         + row(cf, element="Depreciation")[0], rel=1e-9)
    c.eq("재산출 영업이익 성장률 9M", a["actual_growth_operating_income_9m"],
         oi[NM] / oi[NMP] - 1, rel=1e-12)
    c.eq("재산출 매출 성장률 9M", a["actual_growth_revenue_9m"],
         rev[NM] / rev[NMP] - 1, rel=1e-12)

    # 투하자본: 네 가지 분모를 대차대조표에서 다시 쌓습니다.
    def bsv(element, i):
        return row(bs, element=element, index=i)

    for label, i in (("2026-09-30", SEP), ("2025-12-31", DEC)):
        s = a["balance_sheets"][label]
        eq_ = bsv("StockholdersEquity", i)
        debt_ = bsv("LongTermDebtNoncurrent", i)
        cash_ = bsv("CashCashEquivalentsAndShortTermInvestments", i)
        gw = bsv("Goodwill", i)
        intang = bsv("IntangibleAssetsNetExcludingGoodwill", i)
        nis = not_in_service[i]
        nonm = bsv("OtherLongTermInvestments", i)
        c.eq(f"재산출 자기자본 {label}", s["equity"], eq_, rel=0)
        c.eq(f"재산출 이자부차입 {label}", s["debt"], debt_, rel=0)
        c.eq(f"재산출 현금·단기투자 {label}", s["cash_and_securities"], cash_, rel=0)
        c.eq(f"재산출 미가동자산 {label}", s["assets_not_yet_in_service"], nis, rel=0)
        c.eq(f"항등식 투하자본(보고)=자본+차입−현금 {label}",
             s["reported"], eq_ + debt_ - cash_, rel=1e-12)
        c.eq(f"항등식 투하자본(영업)=보고−영업권−무형 {label}",
             s["operating"], eq_ + debt_ - cash_ - gw - intang, rel=1e-12)
        c.eq(f"항등식 투하자본(가동)=영업−미가동 {label}",
             s["in_service"], eq_ + debt_ - cash_ - gw - intang - nis, rel=1e-12)
        c.eq(f"항등식 투하자본(가동−지분)=가동−비시장성 {label}",
             s["in_service_ex_stakes"],
             eq_ + debt_ - cash_ - gw - intang - nis - nonm, rel=1e-12)

    for name, v in a["views"].items():
        o_ = a["balance_sheets"]["2025-12-31"][name]
        c_ = a["balance_sheets"]["2026-09-30"][name]
        c.eq(f"재산출 기초자본 {name}", v["opening"], o_, rel=0)
        c.eq(f"재산출 기말자본 {name}", v["closing"], c_, rel=0)
        c.eq(f"항등식 평균=({name} 기초+기말)/2", v["average"], (o_ + c_) / 2,
             rel=1e-12)
        c.eq(f"항등식 ROIC(TTM)=NOPAT/평균 {name}", v["roic_ttm"],
             a["nopat_ttm"] / v["average"], rel=1e-12)
        c.eq(f"항등식 스프레드=ROIC−10% {name}", v["spread_ttm"],
             v["roic_ttm"] - WACC, rel=1e-12)
        c.true(f"트립와이어 {name} 기초·기말 모두 양수",
               v["opening"] > 0 and v["closing"] > 0,
               f"{v['opening']:,.0f}/{v['closing']:,.0f}")

    # 시가총액과 배수
    c.eq("항등식 시가총액=주가×주식수", a["market_cap"],
         a["price"] * a["shares_outstanding"], rel=1e-12)
    c.eq("항등식 NOPAT 수익률=NOPAT/시가총액", a["nopat_yield"],
         a["nopat_ttm"] / a["market_cap"], rel=1e-12)
    c.eq("항등식 주가/NOPAT=1/수익률", a["price_to_nopat"],
         1 / a["nopat_yield"], rel=1e-12)
    c.eq("항등식 주가/FCF", a["price_to_fcf_ttm"],
         a["market_cap"] / a["free_cash_flow_ttm"], rel=1e-9)
    c.eq("항등식 10% 필요 NOPAT=시가총액×10%", a["nopat_required_for_10pct"],
         a["market_cap"] * WACC, rel=1e-12)
    c.eq("항등식 필요배수=필요NOPAT/현NOPAT", a["multiple_of_current_nopat"],
         a["nopat_required_for_10pct"] / a["nopat_ttm"], rel=1e-12)
    c.eq("재산출 TTM FCF = 발표문", a["free_cash_flow_ttm"],
         ttm["free_cash_flow"], rel=0)
    c.eq("재산출 TTM 영업현금 = 발표문", a["operating_cash_flow_ttm"],
         ttm["operating_cash_flow"], rel=0)
    c.eq("재산출 TTM capex = 발표문", a["capex_ttm"], ttm["capex"], rel=0)

    # 주주이익 밴드
    c.eq("항등식 주주이익 하단 = TTM FCF", a["owner_earnings_lower"],
         ttm["free_cash_flow"], rel=0)
    c.eq("항등식 주주이익 상단 = 영업현금−감가상각", a["owner_earnings_upper"],
         ttm["operating_cash_flow"] - a["depreciation_ttm"], rel=1e-9)
    c.eq("항등식 함의수익률 하단", a["implied_return_lower"],
         a["owner_earnings_lower"] / a["market_cap"], rel=1e-12)
    c.eq("항등식 함의수익률 상단", a["implied_return_upper"],
         a["owner_earnings_upper"] / a["market_cap"], rel=1e-12)
    c.eq("항등식 미가동자산 증가분", a["increase_in_assets_not_yet_in_service"],
         not_in_service[SEP] - not_in_service[DEC], rel=1e-9)
    c.eq("항등식 신규건설 제외 FCF", a["free_cash_flow_before_new_construction"],
         ttm["free_cash_flow"] + a["increase_in_assets_not_yet_in_service"],
         rel=1e-9)

    # 증분 ROIC
    inc = a["incremental"]
    c.eq("항등식 ΔNOPAT", inc["delta_nopat"],
         a["nopat_ttm"] - fy["nopat"], rel=1e-9)
    c.eq("항등식 Δ자본(보고)", inc["delta_capital_reported"],
         a["balance_sheets"]["2026-09-30"]["reported"]
         - a["balance_sheets"]["2025-12-31"]["reported"], rel=1e-9)
    c.eq("항등식 증분ROIC(보고)=ΔNOPAT/Δ자본", inc["incremental_roic_reported"],
         inc["delta_nopat"] / inc["delta_capital_reported"], rel=1e-12)
    c.eq("항등식 Δ자본(가동−지분)", inc["delta_capital_in_service_ex_stakes"],
         a["balance_sheets"]["2026-09-30"]["in_service_ex_stakes"]
         - a["balance_sheets"]["2025-12-31"]["in_service_ex_stakes"], rel=1e-9)
    c.eq("항등식 증분ROIC(가동−지분)",
         inc["incremental_roic_in_service_ex_stakes"],
         inc["delta_nopat"] / inc["delta_capital_in_service_ex_stakes"],
         rel=1e-12)

    # 영구성장 모형. g 를 모형에 되넣으면 시가총액이 나와야 합니다.
    r = a["views"]["in_service"]["roic_ttm"]
    g = a["implied_growth_at_10pct"]
    c.eq("역산 함의성장률을 모형에 되넣으면 시가총액",
         a["nopat_ttm"] * (1 - g / r) / (WACC - g), a["market_cap"], rel=1e-6)
    c.true("트립와이어 함의성장률 < 할인율", g < WACC, f"{g:.4f}")
    c.true("트립와이어 함의성장률 > 0", g > 0, f"{g:.4f}")
    for e in a["growth_sensitivity"]:
        c.eq(f"재산출 민감도 가치 g={e['growth']:.0%}", e["value"],
             a["nopat_ttm"] * (1 - e["growth"] / r) / (WACC - e["growth"]),
             rel=1e-12)
        c.eq(f"항등식 민감도 주당 g={e['growth']:.0%}", e["value_per_share"],
             e["value"] / a["shares_outstanding"], rel=1e-12)
        c.eq(f"항등식 민감도 현재가대비 g={e['growth']:.0%}", e["vs_price"],
             e["value_per_share"] / a["price"] - 1, rel=1e-12)
    gs = [e["growth"] for e in a["growth_sensitivity"]]
    vs = [e["value"] for e in a["growth_sensitivity"]]
    c.true("트립와이어 민감도 성장률 오름차순", gs == sorted(gs), str(gs))
    c.true("트립와이어 성장률↑ ⇒ 가치↑", vs == sorted(vs), str(vs))
    for e in a["implied_growth_by_price"]:
        c.eq(f"항등식 가격별 시가총액 ${e['price']:.2f}", e["market_cap"],
             e["price"] * a["shares_outstanding"], rel=1e-9)
        gg = e["implied_growth"]
        c.eq(f"역산 가격별 함의성장률 ${e['price']:.2f}",
             a["nopat_ttm"] * (1 - gg / r) / (WACC - gg), e["market_cap"],
             rel=1e-6)
    pg = [e["implied_growth"] for e in a["implied_growth_by_price"]]
    c.true("트립와이어 가격↑ ⇒ 함의성장률↑", pg == sorted(pg), str(pg))
    cur = [e for e in a["implied_growth_by_price"]
           if abs(e["price"] - a["price"]) < 0.01]
    c.true("가격표에 현재가 포함", len(cur) == 1)
    if cur:
        c.eq("교차확인 현재가 함의성장률", cur[0]["implied_growth"], g, rel=1e-9)

    # ---- 사업부 (발표문) ---------------------------------------------------
    sg = a["segments"]
    for name, block, parts, total_row in (
            ("매출", sg["revenue"],
             ("services_total", "cloud", "other_bets", "hedging"), rev),
            ("영업이익", sg["operating_income"],
             ("services", "cloud", "other_bets", "alphabet_level"), oi)):
        for q, i in (("q3_2025", Q3P), ("q3_2026", Q3)):
            got = sum(block[k][q] for k in parts)
            c.eq(f"항등식 사업부 {name} 합 = 연결 {q}", got, block["total"][q],
                 tol=1.0, rel=1e-9)
            # 그리고 연결 합계는 10-Q 손익계산서와 같아야 합니다.
            c.eq(f"교차확인 사업부 {name} 합계 = 10-Q {q}", block["total"][q],
                 total_row[i], rel=0)
    c.eq("앵커 Q3 검색매출", sg["revenue"]["search"]["q3_2026"],
         A["q3_search_revenue"] * M, rel=0)
    c.eq("앵커 Q3 유튜브 광고매출", sg["revenue"]["youtube_ads"]["q3_2026"],
         A["q3_youtube_revenue"] * M, rel=0)
    c.eq("앵커 Q3 서비스 매출", sg["revenue"]["services_total"]["q3_2026"],
         A["q3_services_revenue"] * M, rel=0)
    c.eq("앵커 Q3 클라우드 매출(정확)", sg["revenue"]["cloud"]["q3_2026"],
         A["q3_cloud_revenue_exact"] * M, rel=0)
    c.eq("앵커 Q3 환헤지", sg["revenue"]["hedging"]["q3_2026"],
         A["q3_hedging"] * M, rel=0)
    c.eq("앵커 Q3 클라우드 영업이익", sg["operating_income"]["cloud"]["q3_2026"],
         A["q3_cloud_operating_income"] * M, rel=0)
    c.eq("앵커 Q3 서비스 영업이익", sg["operating_income"]["services"]["q3_2026"],
         A["q3_services_operating_income"] * M, rel=0)
    c.eq("앵커 Q3 Other Bets 영업이익",
         sg["operating_income"]["other_bets"]["q3_2026"],
         A["q3_other_bets_operating_income"] * M, rel=0)
    c.eq("앵커 Q3 Alphabet-level",
         sg["operating_income"]["alphabet_level"]["q3_2026"],
         A["q3_alphabet_level"] * M, rel=0)
    c.eq("앵커 Q3 직원수", sg["employees"]["q3_2026"], A["q3_employees"],
         rel=0)
    # 직원수에 배율을 곱하면 안 됩니다 — 실제로 틀렸던 종류의 오류.
    c.true("트립와이어 직원수가 사람 단위(10만~100만)",
           1e5 < sg["employees"]["q3_2026"] < 1e6,
           f"{sg['employees']['q3_2026']:,.0f}")
    c.true("트립와이어 클라우드 매출 2배 이상 증가",
           sg["revenue"]["cloud"]["q3_2026"]
           / sg["revenue"]["cloud"]["q3_2025"] > 2.0)
    c.true("트립와이어 클라우드 영업이익 < 클라우드 매출",
           sg["operating_income"]["cloud"]["q3_2026"]
           < sg["revenue"]["cloud"]["q3_2026"],
           "영업이익 표에서 매출 행을 집으면 여기서 걸립니다")

    # ---- 재무활동 (10-Q 현금흐름표) ----------------------------------------
    f = a["financing"]
    c.eq("재산출 9M 자사주매입", f["repurchases"]["nine_months_2026"],
         row(cf, label="Repurchases of stock", index=0), rel=0)
    c.eq("앵커 9M 자사주매입 전년", f["repurchases"]["nine_months_2025"],
         -39810 * M, rel=0)
    c.eq("항등식 외부조달 = 차입+보통주+우선주",
         f["external_capital_raised_9m_2026"],
         f["debt_issued"]["nine_months_2026"]
         + f["common_issued"]["nine_months_2026"]
         + f["preferred_issued"]["nine_months_2026"], tol=1.0, rel=1e-9)
    c.true("트립와이어 자사주매입 0 — 전년에는 있었음",
           f["repurchases"]["nine_months_2026"] == 0
           and f["repurchases"]["nine_months_2025"] < 0,
           f"{f['repurchases']['nine_months_2026']:,.0f} / "
           f"{f['repurchases']['nine_months_2025']:,.0f}")
    c.true("트립와이어 외부조달이 TTM FCF를 넘음",
           f["external_capital_raised_9m_2026"] > a["free_cash_flow_ttm"],
           f"{f['external_capital_raised_9m_2026']:,.0f} vs "
           f"{a['free_cash_flow_ttm']:,.0f}")

    # ---- 세율 민감도 -------------------------------------------------------
    c.eq("항등식 법정세율 21% NOPAT", a["nopat_at_statutory_21"],
         a["operating_income_ttm"] * 0.79, rel=1e-12)
    c.true("트립와이어 세율을 21%로 바꿔도 판정 불변 (ROIC 가동 > 10%)",
           a["nopat_at_statutory_21"]
           / a["views"]["in_service"]["average"] > WACC)

    # ---- 10년 기록 (50개사 조사) -------------------------------------------
    t = a["ten_year_record"]
    c.true("10년 기록 존재", t is not None)
    if t:
        c.true("10년 기록 티커", t["ticker"] in ("GOOG", "GOOGL"), t["ticker"])
        c.eq("10년 기록 연수", len(t["years"]), 10, rel=0)
        rs = [y["roic"] for y in t["years"] if y.get("roic")]
        c.eq("10년 기록 사용가능 연수", len(rs), 10, rel=0)
        c.true("10년 기록 전 기간 문턱 초과", all(r > WACC for r in rs),
               str([round(r, 3) for r in rs]))
        c.eq("10년 기록 요약과 일치: 문턱 초과 연수",
             t["summary"]["years_above_wacc"], 10, rel=0)
        import statistics
        c.eq("재산출 10년 중위 ROIC", t["summary"]["roic_median"],
             statistics.median(rs), rel=1e-9)
        c.eq("재산출 10년 최고 ROIC", t["summary"]["roic_max"], max(rs),
              rel=1e-9)
        c.eq("재산출 10년 최저 ROIC", t["summary"]["roic_min"], min(rs),
              rel=1e-9)
        peak = max(t["years"], key=lambda y: y["roic"] or 0)
        last = max(t["years"], key=lambda y: y["fiscal_year"])
        c.true("트립와이어 ROIC 고점이 최근 연도가 아님 — 하락 추세",
               peak["fiscal_year"] < last["fiscal_year"],
               f"고점 FY{peak['fiscal_year']} {peak['roic']:.1%} vs "
               f"최근 FY{last['fiscal_year']} {last['roic']:.1%}")
        c.true("트립와이어 최근 연도 ROIC < 고점",
               last["roic"] < peak["roic"])
        c.true("트립와이어 투하자본이 영업이익보다 빠르게 증가 (고점 이후)",
               (last["invested_capital_avg"] / peak["invested_capital_avg"])
               > (last["operating_income"] / peak["operating_income"]),
               f"자본 {last['invested_capital_avg'] / peak['invested_capital_avg']:.2f}배 "
               f"vs 이익 {last['operating_income'] / peak['operating_income']:.2f}배")
        c.true("10년 기록 조사 WACC = 10%", t["wacc"] == WACC, str(t["wacc"]))

    # ---- 트립와이어: 결론을 떠받치는 사실들 --------------------------------
    c.true("트립와이어 TTM 실효세율 0~35%", 0 < a["tax_rate_ttm"] < 0.35,
           f"{a['tax_rate_ttm']:.4f}")
    c.true("트립와이어 ROIC 네 관점 모두 문턱 초과",
           all(v["roic_ttm"] > WACC for v in a["views"].values()),
           str({k: round(v["roic_ttm"], 3) for k, v in a["views"].items()}))
    order = ["reported", "operating", "in_service", "in_service_ex_stakes"]
    roics = [a["views"][k]["roic_ttm"] for k in order]
    c.true("트립와이어 분모를 좁히면 ROIC 상승", roics == sorted(roics),
           str([round(x, 3) for x in roics]))
    c.true("트립와이어 TTM capex 음수", a["capex_ttm"] < 0, f"{a['capex_ttm']:,.0f}")
    c.true("트립와이어 TTM 영업현금 양수", a["operating_cash_flow_ttm"] > 0)
    c.true("트립와이어 최근 2개 분기 FCF 음수",
           quarters[2]["free_cash_flow"] < 0 and quarters[3]["free_cash_flow"] < 0,
           f"{quarters[2]['free_cash_flow']:,.0f}/"
           f"{quarters[3]['free_cash_flow']:,.0f}")
    c.true("트립와이어 Q3 capex > Q3 영업현금",
           abs(quarters[3]["capex"]) > quarters[3]["operating_cash_flow"])
    c.true("트립와이어 주주이익 밴드 하단 ≤ 상단",
           a["owner_earnings_lower"] <= a["owner_earnings_upper"])
    c.true("트립와이어 함의수익률 상단 < 10% 문턱",
           a["implied_return_upper"] < WACC,
           f"{a['implied_return_upper']:.4f}")
    c.true("트립와이어 주식수 120억~130억", 1.2e10 < a["shares_outstanding"] < 1.3e10,
           f"{a['shares_outstanding']:,.0f}")

    ph = d["price_history"]
    c.true("트립와이어 주가가 52주 범위 안",
           ph["fifty_two_week_low"] <= a["price"] <= ph["fifty_two_week_high"],
           f"{ph['fifty_two_week_low']}–{a['price']:.2f}–"
           f"{ph['fifty_two_week_high']}")
    c.eq("교차확인 분석 주가 = 시세 종가", a["price"], ph["last"]["close"], rel=0)
    c.eq("항등식 고점대비 하락률", ph["from_high"],
         ph["last"]["close"] / ph["high"]["close"] - 1, rel=1e-9)
    c.true("트립와이어 급락일이 수집일",
           ph["big_moves"] and ph["big_moves"][-1]["date"] == ph["last"]["date"],
           str(ph["big_moves"][-1] if ph["big_moves"] else None))
    for mv in ph["big_moves"]:
        c.eq(f"항등식 변동률 {mv['date']}", mv["change"],
             mv["to"] / mv["from"] - 1, rel=1e-9)

    # ---- 신선도 -----------------------------------------------------------
    # 분석이 공시보다 오래되면 안 됩니다. 같은 날일 필요는 없습니다 — 공시
    # 다음 날 돌려도 그 공시를 읽은 것은 맞습니다. 거꾸로 생성일이 제출일보다
    # 이르면 그 공시를 읽지 않은 산출물입니다.
    c.true("신선도 생성일 ≥ 10-Q 제출일",
           d["generated"] >= d["filings"]["10-Q"]["filed"],
           f"생성 {d['generated']} vs 제출 {d['filings']['10-Q']['filed']}")
    c.true("신선도 생성일 ≥ 8-K 제출일",
           d["generated"] >= d["filings"]["8-K"]["filed"],
           f"생성 {d['generated']} vs 제출 {d['filings']['8-K']['filed']}")
    c.true("신선도 시세일 ≤ 생성일",
           d["price_history"]["last"]["date"] <= d["generated"],
           f"시세 {d['price_history']['last']['date']} vs 생성 {d['generated']}")
    c.true("상장·티커를 기억이 아니라 조회로",
           "GOOGL" in d["tickers"] and "Nasdaq" in d["exchanges"],
           f"{d['tickers']} / {d['exchanges']}")
    return c


MUTATIONS = [
    ("Q3 영업이익 훼손", lambda d: _setrow(d, "operations",
                                     "OperatingIncomeLoss", 0, 41000.0)),
    ("9M 기타수익 훼손", lambda d: _setrow(d, "operations",
                                     "NonoperatingIncomeExpense", 2, 1000.0)),
    ("9M 법인세 훼손", lambda d: _setrow(d, "operations",
                                   "IncomeTaxExpenseBenefit", 2, 30000.0)),
    ("비용 소계 훼손", lambda d: _setrow(d, "operations",
                                  "CostsAndExpenses", 0, 87500.0)),
    ("미가동자산 훼손", lambda d: _setctx(d, "ppe",
                                   "Assets not yet in service", 0, 100000.0)),
    ("감가상각누계 훼손", lambda d: _setlabel(d, "ppe",
                                     "accumulated depreciation", 0, -100000.0)),
    ("자사주매입 훼손(0 → 음수)", lambda d: _setlabel(
        d, "cash_flows", "Repurchases of stock", 0, -20000.0)),
    ("차입조달 훼손", lambda d: _setlabel(d, "cash_flows",
                                   "issuance of debt", 0, 50000.0)),
    ("Q3 capex 훼손", lambda d: _setfcf(d, "Q3 2026", "capex", -40000.0)),
    ("Q3 FCF 훼손(항등식 깨짐)", lambda d: _setfcf(
        d, "Q3 2026", "free_cash_flow", 5000.0)),
    ("TTM 영업현금 훼손(합계 불일치)", lambda d: _setfcf(
        d, "TTM Q3 2026", "operating_cash_flow", 170000.0)),
    ("자기자본 훼손", lambda d: _setrow(d, "balance_sheet",
                                  "StockholdersEquity", 0, 600000.0)),
    ("현금·단기투자 훼손", lambda d: _setrow(
        d, "balance_sheet", "CashCashEquivalentsAndShortTermInvestments", 0,
        400000.0)),
    ("NOPAT 훼손", lambda d: d["analysis"].__setitem__(
        "nopat_ttm", d["analysis"]["nopat_ttm"] * 1.15)),
    ("ROIC 훼손", lambda d: d["analysis"]["views"]["in_service"].__setitem__(
        "roic_ttm", 0.09)),
    ("함의성장률 훼손", lambda d: d["analysis"].__setitem__(
        "implied_growth_at_10pct", 0.04)),
    ("민감도 가치 훼손", lambda d: d["analysis"]["growth_sensitivity"][3]
        .__setitem__("value", 3.5e12)),
    ("주식수 훼손", lambda d: d["analysis"].__setitem__(
        "shares_outstanding", 1.0e10)),
    ("주가 훼손", lambda d: d["analysis"].__setitem__("price", 350.0)),
    ("발표문 Q3 매출 훼손(교차확인 깨짐)", lambda d: d["release"]["headline"]
        .__setitem__("revenue_q3_2026", 130000e6)),
    ("고점대비 하락률 훼손", lambda d: d["price_history"].__setitem__(
        "from_high", -0.10)),
    ("실효세율 훼손", lambda d: d["analysis"].__setitem__("tax_rate_ttm", 0.25)),
    ("생성일을 공시보다 이르게 훼손", lambda d: d.__setitem__(
        "generated", "2026-10-01")),
    ("티커·거래소 훼손", lambda d: d.__setitem__("tickers", ["PRIVATE"])),
    ("클라우드 영업이익에 매출을 넣음", lambda d:
     d["analysis"]["segments"]["operating_income"]["cloud"].__setitem__(
         "q3_2026",
         d["analysis"]["segments"]["revenue"]["cloud"]["q3_2026"])),
    ("직원수에 백만 배율 적용", lambda d:
     d["analysis"]["segments"]["employees"].__setitem__(
         "q3_2026", 204757 * M)),
    ("사업부 매출 한 항목 훼손", lambda d:
     d["analysis"]["segments"]["revenue"]["search"].__setitem__(
         "q3_2026", 60000 * M)),
    ("자사주매입을 0이 아니게 훼손", lambda d:
     d["analysis"]["financing"]["repurchases"].__setitem__(
         "nine_months_2026", -10000 * M)),
    ("외부조달 합계 훼손", lambda d: d["analysis"]["financing"].__setitem__(
        "external_capital_raised_9m_2026", 50000 * M)),
    ("10년 중위 ROIC 훼손", lambda d:
     d["analysis"]["ten_year_record"]["summary"].__setitem__(
         "roic_median", 0.08)),
    ("10년 중 한 해를 문턱 아래로 훼손", lambda d:
     d["analysis"]["ten_year_record"]["years"][3].__setitem__("roic", 0.05)),
    ("법정세율 NOPAT 훼손", lambda d: d["analysis"].__setitem__(
        "nopat_at_statutory_21", 200e9)),
    ("EPS 행에 백만 배율 적용", lambda d: _scale(
        d, "operations", "EarningsPerShareDiluted")),
    ("퍼센트 행에 백만 배율 적용", lambda d: _mark_monetary(
        d, "ppe", "percentage")),
    ("9M 희석EPS 훼손", lambda d: _setrow(
        d, "operations", "EarningsPerShareDiluted", 2, 12.0)),
]


def _find(d, table, **kw):
    for r in d["financials"][table]["rows"]:
        if all(v is None for v in r["values"]):
            continue
        el = r.get("element") or ""
        if el.endswith(("Abstract", "LineItems")):
            continue
        if "monetary" in kw and bool(r.get("monetary")) != kw["monetary"]:
            continue
        if "label_exact" in kw and r["label"].strip() != kw["label_exact"]:
            continue
        if "element" in kw and not el.endswith(kw["element"]):
            continue
        if "label" in kw and kw["label"].lower() not in r["label"].lower():
            continue
        if "context" in kw and (r.get("context") or "") != kw["context"]:
            continue
        return r
    raise SystemExit(f"변이 대상 없음: {table} {kw}")


# 변이 값은 공시 표와 같은 백만 단위로 씁니다(release.cash_flow 만 달러 단위).
def _setrow(d, table, element, i, val):
    _find(d, table, element=element)["values"][i] = val


def _setlabel(d, table, label, i, val):
    _find(d, table, label=label)["values"][i] = val


def _setctx(d, table, context, i, val):
    _find(d, table, context=context, label_exact=GROSS)["values"][i] = val


def _scale(d, table, element):
    """금액이 아닌 행에 표의 배율을 먹입니다 — 실제로 났던 오류의 재현."""
    r = _find(d, table, element=element)
    r["monetary"] = True


def _mark_monetary(d, table, label):
    r = _find(d, table, label=label)
    r["monetary"] = True


def _setfcf(d, period, key, val):
    for p in d["release"]["cash_flow"]:
        if p["period"] == period:
            p[key] = val * M
            return
    raise SystemExit(f"변이 대상 기간 없음: {period}")


def main():
    mutate = "--mutate" in sys.argv
    verbose = "--verbose" in sys.argv
    with open(PATH, encoding="utf-8") as fh:
        raw = fh.read()
    d = json.loads(raw)

    c = verify(d, Checks())
    print(f"검사 {c.passed + len(c.failures)}건 — 통과 {c.passed}, "
          f"실패 {len(c.failures)}")
    for f in c.failures:
        print("  ✗", f)
    if verbose and not c.failures:
        a = d["analysis"]
        print(f"  TTM 영업이익 {a['operating_income_ttm'] / 1e9:,.1f}십억 · "
              f"NOPAT {a['nopat_ttm'] / 1e9:,.1f}십억 · "
              f"ROIC(가동) {a['views']['in_service']['roic_ttm']:.1%} · "
              f"TTM FCF {a['free_cash_flow_ttm'] / 1e9:,.1f}십억 · "
              f"함의성장률 {a['implied_growth_at_10pct']:.2%}")
    if c.failures:
        return 1

    if mutate:
        print(f"\n변이 검정 {len(MUTATIONS)}건 — 값을 훼손해 검사가 "
              f"실제로 실패하는지 확인")
        survived = []
        for name, mutator in MUTATIONS:
            m = json.loads(raw)
            mutator(m)
            mc = Checks()
            try:
                verify(m, mc)
            except SystemExit as exc:
                print(f"  ✓ {name}: 구조 검사에서 중단 — {exc}")
                continue
            if mc.failures:
                print(f"  ✓ {name}: {len(mc.failures)}건 실패 "
                      f"— {mc.failures[0][:88]}")
            else:
                survived.append(name)
                print(f"  ✗ {name}: 아무 검사도 실패하지 않음 — 검사 구멍")
        if survived:
            print(f"\n변이 {len(survived)}건이 검사를 통과했습니다: {survived}")
            return 1
        print(f"  변이 {len(MUTATIONS)}/{len(MUTATIONS)}건 모두 포착")
    return 0


if __name__ == "__main__":
    sys.exit(main())
