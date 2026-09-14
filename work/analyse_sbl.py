"""
Samsung Biologics against the seven Buffett criteria, and a valuation on the
same engine as the rest of this work.

The engine is the one the Alphabet work settled on. Free cash flow is NOPAT less
the cost of growth, with the reinvestment rate derived rather than assumed:

    FCF = NOPAT x (1 - g / incremental ROIC)

so no scenario is allowed to grow without paying for it. Ten forecast years
with the growth rate fading, a terminal value on the same identity, then net
cash. That identity does more work here than it did for Alphabet, because this
company's growth rate has been running close to - at times above - its
incremental return on capital, which is the arithmetic definition of a business
that consumes cash while it grows.

Three measurement decisions are made explicitly rather than by default, and
each is reported alongside the alternative it was chosen over:

  1. Invested capital is measured bottom-up from the operating assets and
     liabilities, not top-down from equity plus debt less cash. Top-down breaks
     twice for this company: the Samsung Bioepis stake dominated the balance
     sheet through 2021 (FY2017 top-down invested capital is negative), and the
     1 November 2025 spin-off cut equity by W1,865bn for reasons that have
     nothing to do with the contract-manufacturing business. Both measures are
     computed and printed; they agree from FY2018 to FY2024 apart from the
     spin-off year, which is the evidence the choice is not doing the work.

  2. Construction-in-progress is taken out of invested capital. At the end of
     FY2024, W1,823bn - 30% of operating capital - was an unfinished plant
     earning nothing, and W2,183bn transferred into service during FY2025.
     Leaving it in reads FY2024 as a year of collapsing returns when nothing
     had collapsed. This is the same correction the Alphabet review applied to
     assets not yet in service.

  3. The valuation base is normalised for the exchange rate. 91.8% of FY2025
     revenue was earned outside Korea while most of the cost base is in won, and
     the won averaged 1,421/USD in FY2025 and 1,482 in the first half of 2026
     against 1,358 today. Capitalising an exchange rate the market has already
     left is not conservatism, it is an error. All three bases - FY2025 as
     reported, the 2026 half-year annualised, and that run-rate at today's rate
     - are carried through to the end.

Writes work/kr/sbl_valuation.json.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calc  # noqa: E402

RAW = os.path.join(HERE, "kr", "sbl_raw.json")
OUT = os.path.join(HERE, "kr", "sbl_valuation.json")

BN = 1e9

# ---------------------------------------------------------------- market data
MARKET = {
    "price": 1_408_000.0,
    "price_date": "2026-09-14",
    "price_source": "네이버 금융 일별시세 (207940), 2026-09-14 종가",
    "shares_outstanding": 46_239_518,
    "shares_issued": 46_290_951,
    "shares_note": ("분할 후 발행주식 46,290,951주에서 자기주식 51,433주를 차감한 "
                    "유통주식 46,239,518주 기준. 분할 전 71,174,000주였으므로 "
                    "분할 전 주가·EPS와는 직접 비교할 수 없습니다."),
    "market_cap_naver": 65_131_400_000_000.0,
    "market_cap_note": "네이버 공시 시총 65조 1,314억원 (자체 계산 65조 1,052억원과 0.04% 차이)",
    "fifty_two_week_high": 1_987_000.0,
    "fifty_two_week_low": 1_228_000.0,
    "trailing_per_naver": 38.87,
    "pbr_naver": 7.78,
    "dividend": None,
}

FX = {
    "spot": 1_358.5,
    "spot_note": "2026년 9월 평균 (FRED DEXKOUS 월평균)",
    "annual_average": {2016: 1_159.3, 2017: 1_129.0, 2018: 1_099.3,
                       2019: 1_165.8, 2020: 1_180.6, 2021: 1_144.9,
                       2022: 1_291.8, 2023: 1_306.8, 2024: 1_363.4,
                       2025: 1_421.4},
    "h1_2026_average": 1_482.0,
    "series": "FRED DEXKOUS (Korea / U.S. Foreign Exchange Rate)",
    "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXKOUS",
}

RISK_FREE_KR = {
    "rate": 0.04181, "as_of": "2026-06",
    "series": "FRED IRLTLT01KRM156N (Korea 10-year government bond yield)",
    "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=IRLTLT01KRM156N",
}

# Share of the cost base that moves with the exchange rate. Culture media,
# resins and single-use assemblies are imported and invoiced in dollars; labour,
# depreciation on won-built plant, and utilities are not. The company does not
# disclose the split, so it is an assumption, carried at 30% and swept from 0%
# to 60% in the sensitivity below.
FX_LINKED_COST_SHARE = 0.30

TAX_STATUTORY = 0.22          # Korea's headline corporate rate incl. surtax
TAX_FLOOR, TAX_CEIL = 0.05, 0.40

# Scenarios. Growth has to be calibrated against what the company has actually
# done, not against what feels prudent: revenue compounded at 31.4% over
# FY2020-FY2025 and 23.2% over FY2022-FY2025, and the 2026 half-year was 28.0%
# ahead of the same period of 2025. So the optimistic case starts at 25% - at
# the low end of the record rather than below it - and the conservative case at
# 8%, which is what a company that stops adding capacity and grows with price
# and mix alone would do. The incremental returns are set from the measured
# five-year windows on the primary capital measure: FY2016-FY2021 24.9%,
# FY2017-FY2022 25.1%, FY2018-FY2023 28.0%, FY2019-FY2024 29.7%,
# FY2020-FY2025 27.6%.
SCENARIOS = [
    {"name": "보수", "growth": 0.08, "fade_to": 0.025, "incremental_roic": 0.15,
     "discount": 0.11, "terminal_growth": 0.020,
     "story": "증설을 멈추고 기존 공장의 가동률·가격·믹스 개선만으로 성장. "
              "증분 ROIC은 실측 5년 구간 최저치(24.9%)보다 크게 낮은 15%를 적용."},
    {"name": "중립", "growth": 0.15, "fade_to": 0.040, "incremental_roic": 0.20,
     "discount": 0.10, "terminal_growth": 0.025,
     "story": "증설을 계속하되 10년에 걸쳐 성장률이 GDP 수준으로 수렴. "
              "증분 ROIC 20%는 실측 구간(24.9~29.7%) 하단 아래."},
    {"name": "낙관", "growth": 0.25, "fade_to": 0.050, "incremental_roic": 0.26,
     "discount": 0.09, "terminal_growth": 0.030,
     "story": "최근 5년 실적(매출 CAGR 31.4%, 2026 상반기 +28.0%)의 하단에서 출발해 "
              "10년간 체감. 증분 ROIC 26%는 FY2020→FY2025 실측치(27.6%)에 근접."},
]


def div(a, b):
    return None if (a is None or not b) else a / b


def ratio(num, den):
    """
    A return on capital, suppressed when the capital is negative.

    FY2016 top-down invested capital is minus W249bn and NOPAT is minus W24bn,
    which divides out to a healthy-looking +9.5%. Two negatives do not make a
    return, so the figure is withheld rather than printed.
    """
    if num is None or den is None or den <= 0:
        return None
    return num / den


def load():
    with open(RAW) as fh:
        return json.load(fh)


def effective_tax(row):
    tax, pretax = row.get("income_tax_expense"), row.get("pretax_income")
    if tax is None or pretax is None or pretax <= 0:
        return TAX_STATUTORY, "세전이익이 없거나 음수여서 법정세율 22% 적용"
    r = tax / pretax
    if not (TAX_FLOOR <= r <= TAX_CEIL):
        return TAX_STATUTORY, f"실효세율 {r:.1%}가 밴드를 벗어나 법정세율 22% 적용"
    return r, f"실효 {r:.1%}"


# --------------------------------------------------------------------- capital
def capital_measures(row, cip):
    """
    Three readings of the capital the business is using, so the choice between
    them is visible rather than buried.

      top_down       equity + interest-bearing debt + leases - cash and
                     short-term instruments - investments in other companies.
                     The measure the rest of this work uses.
      operating      the operating assets less the operating liabilities they
                     are funded by. Immune to the holding-company noise and to
                     the spin-off.
      operating_ex_payables
                     the same, but without netting trade and other payables.
                     Payables at this company include construction payables -
                     W1,629bn in FY2022 - which fund plant, not working
                     capital, so netting them flatters returns in build years.

    Each is also reported net of construction-in-progress.
    """
    g = lambda k: (row.get(k) or 0)
    top = (row["total_equity"] + g("debt_total") + g("lease_liabilities")
           - g("cash_and_equivalents") - g("short_term_financial_instruments")
           - g("investments_in_subs"))
    assets = (g("ppe") + g("intangibles") + g("right_of_use") + g("inventories")
              + g("trade_receivables") + g("contract_assets_total"))
    op = (assets - g("trade_payables") - g("contract_liabilities")
          - g("other_current_liabilities"))
    op_ex_pay = assets - g("contract_liabilities") - g("other_current_liabilities")
    return {
        "top_down": top,
        "operating": op,
        "operating_ex_payables": op_ex_pay,
        "construction_in_progress": cip,
        "top_down_ex_cip": top - cip,
        "operating_ex_cip": op - cip,
        "operating_ex_payables_ex_cip": op_ex_pay - cip,
    }


def build_years(raw):
    cips = {int(k): v["carrying_amount"]
            for k, v in raw["construction_in_progress"].items()}
    rows = []
    for y in raw["years"]:
        fy = y["fiscal_year"]
        tax, tax_note = effective_tax(y)
        op = y["operating_income"]
        nop = op * (1 - tax)
        cap = capital_measures(y, cips.get(fy, 0))
        rows.append({
            "fiscal_year": fy,
            "revenue": y["revenue"],
            "operating_income": op,
            "operating_margin": div(op, y["revenue"]),
            "effective_tax_rate": tax,
            "tax_note": tax_note,
            "nopat": nop,
            "net_income": y["net_income"],
            "capital": cap,
            "roic_top_down": ratio(nop, cap["top_down"]),
            "roic_operating": ratio(nop, cap["operating"]),
            "roic_operating_ex_cip": ratio(nop, cap["operating_ex_cip"]),
            "roic_operating_ex_payables_ex_cip":
                ratio(nop, cap["operating_ex_payables_ex_cip"]),
            "depreciation_amortization": y.get("depreciation_amortization"),
            "capex": y.get("capex"),
            "intangible_capex": y.get("intangible_capex"),
            "ocf": y.get("ocf"),
            "ppe": y.get("ppe"),
            "inventories": y.get("inventories"),
            "contract_liabilities": y.get("contract_liabilities"),
            "advance_receipts": y.get("other_current_liabilities"),
            "trade_payables": y.get("trade_payables"),
            "total_equity": y["total_equity"],
            "debt_total": y.get("debt_total"),
            "lease_liabilities": y.get("lease_liabilities"),
            "cash_total": ((y.get("cash_and_equivalents") or 0)
                           + (y.get("short_term_financial_instruments") or 0)),
            "source_document": y["source_document"],
        })
    return rows


def incremental_returns(rows):
    """
    Incremental ROIC over every window of three years or more, on each capital
    measure. Reported as a range rather than a point, because a single window
    can be an artefact of what happened to be under construction at each end.
    """
    by = {r["fiscal_year"]: r for r in rows}
    out = []
    for a in sorted(by):
        for b in sorted(by):
            if b - a < 3:
                continue
            d_nopat = by[b]["nopat"] - by[a]["nopat"]
            entry = {"from": a, "to": b, "years": b - a,
                     "delta_nopat": d_nopat}
            for key in ("operating", "operating_ex_cip",
                        "operating_ex_payables_ex_cip", "top_down"):
                d_cap = by[b]["capital"][key] - by[a]["capital"][key]
                entry[key] = {"delta_capital": d_cap,
                              "incremental_roic": div(d_nopat, d_cap)}
            out.append(entry)
    return out


def owner_earnings(rows):
    """
    Buffett's 1986 definition: reported earnings plus depreciation and other
    non-cash charges, less "the average annual amount of capitalized
    expenditures for plant and equipment, etc. that the business requires to
    fully maintain its long-term competitive position and its unit volume."

    The whole question for this company is the last clause. Capex was 3.7x
    depreciation in FY2025 because it is adding plants, not maintaining them.
    Three readings are reported and the gap between them is the answer:

      maintenance = D&A      the conventional proxy: what it costs to keep the
                             existing plant standing and producing
      maintenance = 1.2x D&A the same, with a replacement-cost uplift, since
                             this plant was built at earlier prices
      maintenance = capex    all-in free cash flow, which is what the owner can
                             actually take out this year

    Neither end is the answer on its own. The first says what the business earns
    once it stops growing; the last says what it pays its owner while it grows.
    """
    out = []
    prev = None
    for r in rows:
        da, capex, ni = (r["depreciation_amortization"], r["capex"],
                         r["net_income"])
        ocf = r["ocf"]
        wc = None
        if prev is not None and None not in (r["inventories"], prev["inventories"]):
            wc = ((r["inventories"] - prev["inventories"])
                  - ((r["advance_receipts"] or 0) - (prev["advance_receipts"] or 0))
                  - ((r["contract_liabilities"] or 0)
                     - (prev["contract_liabilities"] or 0)))
        entry = {"fiscal_year": r["fiscal_year"], "net_income": ni,
                 "depreciation_amortization": da, "capex": capex,
                 "working_capital_change": wc,
                 "oe_maintenance_equals_da":
                     None if None in (ni, da) else ni + da - da - (wc or 0),
                 "oe_maintenance_1_2x_da":
                     None if None in (ni, da) else ni + da - 1.2 * da - (wc or 0),
                 "oe_all_in_capex":
                     None if None in (ni, da, capex) else ni + da - capex - (wc or 0),
                 "fcf_from_cash_flow_statement":
                     None if None in (ocf, capex) else ocf - capex}
        out.append(entry)
        prev = r
    return out


# ------------------------------------------------------------------- FX bases
def fx_normalise(revenue, operating_income, foreign_share, from_rate, to_rate,
                 cost_share=FX_LINKED_COST_SHARE):
    """
    Restate a year's revenue and operating income at a different exchange rate.

    Foreign revenue moves one-for-one with the rate; the share of the cost base
    that is itself in foreign currency moves with it too, and the rest does not.
    """
    factor = to_rate / from_rate
    rev = revenue * ((1 - foreign_share) + foreign_share * factor)
    cost = revenue - operating_income
    cost_adj = cost * ((1 - cost_share) + cost_share * factor)
    return {"rate_from": from_rate, "rate_to": to_rate,
            "revenue": rev, "operating_income": rev - cost_adj,
            "operating_margin": div(rev - cost_adj, rev),
            "cost_share_assumed": cost_share}


def margin_decomposition(raw, rows):
    """
    The operating margin went from 37.8% in FY2024 to 45.4% in FY2025. Some of
    that is the won: the average rate moved from 1,363.4 to 1,421.4 while 92% of
    revenue is earned abroad. Restating FY2025 at the FY2024 rate separates the
    currency from the operating improvement.
    """
    by = {r["fiscal_year"]: r for r in rows}
    geo = raw["concentration"]["geography"]
    foreign = 1 - div(geo["domestic"]["2025"], by[2025]["revenue"])
    at_2024_rate = fx_normalise(by[2025]["revenue"], by[2025]["operating_income"],
                                foreign, FX["annual_average"][2025],
                                FX["annual_average"][2024])
    total = by[2025]["operating_margin"] - by[2024]["operating_margin"]
    fx_part = by[2025]["operating_margin"] - at_2024_rate["operating_margin"]
    return {
        "fy2024_margin": by[2024]["operating_margin"],
        "fy2025_margin": by[2025]["operating_margin"],
        "fy2025_margin_at_fy2024_rate": at_2024_rate["operating_margin"],
        "total_change": total,
        "fx_contribution": fx_part,
        "operating_contribution": total - fx_part,
        "fx_share_of_change": div(fx_part, total),
        "foreign_revenue_share": foreign,
        "note": ("환율이 아닌 부분은 5공장 가동에 따른 가동률 상승과 "
                 "고정비 레버리지입니다. FY2025 중 2조 1,829억원이 건설중자산에서 "
                 "가동자산으로 이전되었습니다."),
    }


def valuation_bases(raw, rows):
    by = {r["fiscal_year"]: r for r in rows}
    fy25, it = by[2025], raw["interim_2026"]
    geo = raw["concentration"]["geography"]
    foreign = 1 - div(geo["domestic"]["2025"], fy25["revenue"])

    h1_tax = div(it["h1_2026"]["income_tax_expense"],
                 it["h1_2026"]["pretax_income"])
    run_rev = it["h1_2026"]["revenue"] * 2
    run_op = it["h1_2026"]["operating_income"] * 2

    reported = {
        "label": "FY2025 실적 기준",
        "revenue": fy25["revenue"], "operating_income": fy25["operating_income"],
        "tax_rate": fy25["effective_tax_rate"],
        "note": "감사받은 FY2025 별도 손익계산서. 평균환율 1,421.4원/USD.",
    }
    run_rate = {
        "label": "2026 상반기 연율화",
        "revenue": run_rev, "operating_income": run_op, "tax_rate": h1_tax,
        "note": ("검토받은 2026 상반기 × 2. 평균환율 1,482원/USD. "
                 "상반기 매출은 전년 동기 대비 +28.0%."),
    }
    norm = fx_normalise(run_rev, run_op, foreign, FX["h1_2026_average"],
                        FX["spot"])
    normalised = {
        "label": "2026 상반기 연율화 · 현재 환율로 환산",
        "revenue": norm["revenue"], "operating_income": norm["operating_income"],
        "tax_rate": h1_tax,
        "note": (f"해외매출 비중 {foreign:.1%}, 원가 중 외화연동 비중 "
                 f"{FX_LINKED_COST_SHARE:.0%} 가정. 1,482원 → 1,358.5원."),
    }
    out = {"foreign_revenue_share_2025": foreign,
           "h1_2026_effective_tax_rate": h1_tax}
    for key, b in (("reported_fy2025", reported), ("run_rate_2026", run_rate),
                   ("run_rate_fx_normalised", normalised)):
        b["nopat"] = b["operating_income"] * (1 - b["tax_rate"])
        out[key] = b
    out["fx_sensitivity_of_run_rate"] = [
        dict(fx_normalise(run_rev, run_op, foreign, FX["h1_2026_average"], rate),
             nopat=fx_normalise(run_rev, run_op, foreign,
                                FX["h1_2026_average"], rate)["operating_income"]
             * (1 - h1_tax))
        for rate in (1_200, 1_250, 1_300, 1_358.5, 1_400, 1_450, 1_482, 1_550)
    ]
    out["cost_share_sensitivity"] = [
        dict(cost_share=cs,
             operating_income=fx_normalise(run_rev, run_op, foreign,
                                           FX["h1_2026_average"], FX["spot"],
                                           cs)["operating_income"])
        for cs in (0.0, 0.15, 0.30, 0.45, 0.60)
    ]
    return out


# ------------------------------------------------------------------------ DCF
def dcf(base_nopat, net_cash, market_cap, shares, scenarios=None):
    out = []
    for s in (scenarios or SCENARIOS):
        proj, pv_sum, nopat = [], 0.0, base_nopat
        n = 10
        for t in range(1, n + 1):
            g = s["growth"] + (s["fade_to"] - s["growth"]) * (t - 1) / (n - 1)
            rr = g / s["incremental_roic"]
            nopat *= (1 + g)
            fcf = nopat * (1 - rr)
            pv = fcf / (1 + s["discount"]) ** t
            pv_sum += pv
            proj.append({"year": t, "growth": g, "nopat": nopat,
                         "reinvestment_rate": rr, "free_cash_flow": fcf,
                         "present_value": pv})
        tg = s["terminal_growth"]
        trr = tg / s["incremental_roic"]
        terminal = proj[-1]["nopat"] * (1 + tg) * (1 - trr) / (s["discount"] - tg)
        terminal_pv = terminal / (1 + s["discount"]) ** n
        ev = pv_sum + terminal_pv
        equity = ev + net_cash
        out.append({
            "scenario": s["name"],
            "story": s.get("story"),
            "assumptions": {k: s[k] for k in
                            ("growth", "fade_to", "incremental_roic",
                             "discount", "terminal_growth")},
            "first_year_reinvestment_rate": proj[0]["reinvestment_rate"],
            "years_with_negative_fcf": sum(1 for p in proj
                                           if p["free_cash_flow"] < 0),
            "cumulative_fcf_first_five": sum(p["free_cash_flow"]
                                             for p in proj[:5]),
            "projection": proj,
            "pv_of_forecast": pv_sum,
            "pv_of_terminal": terminal_pv,
            "terminal_share_of_value": div(terminal_pv, ev),
            "enterprise_value": ev,
            "equity_value": equity,
            "value_per_share": equity / shares,
            "upside_vs_market": div(equity - market_cap, market_cap),
            "margin_of_safety": div(equity - market_cap, equity),
        })
    return out


def feasibility(scenario, base_nopat, base_capital, base_revenue, base_da):
    """
    What a scenario actually requires the company to do, in won and in plant.

    The discounted cash flow will happily value a growth rate the company
    cannot physically finance, because the reinvestment it subtracts from cash
    flow is allowed to exceed the cash flow itself: a reinvestment rate above
    100% means the shortfall is raised outside, and the equity value never
    charges the existing owner for the dilution or interest. So every scenario
    is also reported as the capital it consumes.
    """
    n, nopat = 10, base_nopat
    cum_reinvest = cum_nopat = external = 0.0
    ic = base_capital
    rows = []
    for t in range(1, n + 1):
        g = scenario["growth"] + (scenario["fade_to"] - scenario["growth"]) \
            * (t - 1) / (n - 1)
        rr = g / scenario["incremental_roic"]
        nopat *= (1 + g)
        reinvest = nopat * rr
        cum_reinvest += reinvest
        cum_nopat += nopat
        external += max(0.0, reinvest - nopat)
        ic += reinvest
        rows.append({"year": t, "growth": g, "reinvestment_rate": rr,
                     "nopat": nopat, "reinvestment": reinvest,
                     "invested_capital": ic})
    end = rows[-1]
    return {
        "cumulative_nopat": cum_nopat,
        "cumulative_reinvestment": cum_reinvest,
        "reinvestment_as_share_of_nopat": div(cum_reinvest, cum_nopat),
        "external_capital_required": external,
        "invested_capital_end": end["invested_capital"],
        "invested_capital_multiple": div(end["invested_capital"], base_capital),
        "implied_revenue_end": base_revenue * div(end["nopat"], base_nopat),
        "implied_revenue_end_usd_bn":
            base_revenue * div(end["nopat"], base_nopat) / FX["spot"] / 1e9,
        "average_annual_capex": (cum_reinvest / n) + base_da,
        "average_annual_capex_vs_fy2025":
            div((cum_reinvest / n) + base_da, 1_376_344_214_595),
        "note": ("증분 ROIC이 성장률보다 낮으면 재투자율이 100%를 넘고, 그 차액은 "
                 "외부에서 조달해야 합니다. 현금흐름할인은 그 조달의 희석·이자 "
                 "비용을 기존 주주에게 청구하지 않으므로, 그런 시나리오의 가치는 "
                 "과대평가입니다."),
    }


def implied(base_nopat, net_cash, market_cap, template):
    """
    Turn the question round. Rather than asking what the business is worth,
    ask what the market is already assuming - the growth rate, then the
    discount rate, that makes the quoted price exactly right.
    """
    def value(overrides):
        s = dict(template)
        s.update(overrides)
        return dcf(base_nopat, net_cash, market_cap, 1.0, [s])[0]["equity_value"]

    lo, hi = 0.0, 0.60
    for _ in range(80):
        mid = (lo + hi) / 2
        if value({"growth": mid, "fade_to": min(mid, template["fade_to"])}) \
                < market_cap:
            lo = mid
        else:
            hi = mid
    implied_growth = (lo + hi) / 2

    lo, hi = template["terminal_growth"] + 0.005, 0.40
    for _ in range(80):
        mid = (lo + hi) / 2
        if value({"discount": mid}) > market_cap:
            lo = mid
        else:
            hi = mid
    implied_discount = (lo + hi) / 2

    # And the third lever: hold the growth and the discount rate at the
    # template's values and ask what return on incremental capital the price
    # requires. This one is the most searching of the three, because the
    # incremental return is the thing that has actually been measured.
    lo, hi = 0.05, 3.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if value({"incremental_roic": mid}) < market_cap:
            lo = mid
        else:
            hi = mid
    implied_inc_roic = (lo + hi) / 2
    # The search tops out at 300%. Hitting the ceiling is itself the answer: at
    # that point reinvestment is nearly nil and the cash flow is nearly all of
    # NOPAT, so if the value is still short of the price, no return on
    # incremental capital reaches it and the binding constraints are the growth
    # rate and the discount rate.
    unattainable = implied_inc_roic > 2.5

    return {"implied_initial_growth": implied_growth,
            "implied_incremental_roic":
                None if unattainable else implied_inc_roic,
            "incremental_roic_cannot_reach_price": unattainable,
            "implied_first_year_reinvestment_rate":
                implied_growth / template["incremental_roic"],
            "implied_discount_rate": implied_discount,
            "template": {k: template[k] for k in
                         ("growth", "fade_to", "incremental_roic",
                          "discount", "terminal_growth")}}


def cost_of_capital(rows):
    """
    A reference cost of capital, so the scenario discount rates can be judged
    rather than taken on trust. The scenarios still use 9-11% directly, as the
    rest of this work does.
    """
    fy25 = rows[-1]
    debt = (fy25["debt_total"] or 0)
    equity_mv = MARKET["price"] * MARKET["shares_outstanding"]
    rf = RISK_FREE_KR["rate"]
    out = []
    for beta in (0.9, 1.0, 1.2):
        for erp in (0.055, 0.065, 0.075):
            ke = rf + beta * erp
            kd = 0.040
            w_d = debt / (debt + equity_mv)
            out.append({"beta": beta, "erp": erp, "cost_of_equity": ke,
                        "cost_of_debt_pretax": kd, "debt_weight": w_d,
                        "wacc": (1 - w_d) * ke + w_d * kd * (1 - TAX_STATUTORY)})
    return {"risk_free": RISK_FREE_KR, "grid": out,
            "range": [min(o["wacc"] for o in out), max(o["wacc"] for o in out)]}


def concentration_view(raw, rows):
    by = {r["fiscal_year"]: r for r in rows}
    c = raw["concentration"]["customers"]
    out = {}
    for yr in ("2025", "2024"):
        vals = sorted((v[yr] for v in c.values()), reverse=True)
        rev = by[int(yr)]["revenue"]
        out[yr] = {"top5_revenue": sum(vals), "top5_share": div(sum(vals), rev),
                   "largest_share": div(vals[0], rev), "clients": vals}
    # How much of the top-five roster turned over between the two years is the
    # question the moat argument turns on, and the disclosure is anonymised, so
    # what can be said is how much the individual balances moved.
    out["largest_client_change"] = div(c["client_a"]["2025"], c["client_a"]["2024"]) - 1
    out["geography"] = raw["concentration"]["geography"]
    return out


def float_view(raw, rows):
    fy25 = rows[-1]
    f = raw["float_and_supplier_finance"]
    adv = f["advance_receipts"]
    total_float = (adv["2025_current"] + adv["2025_non_current"]
                   + fy25["contract_liabilities"])
    return {
        "advance_receipts_2025": adv["2025_current"] + adv["2025_non_current"],
        "contract_liabilities_2025": fy25["contract_liabilities"],
        "total_customer_funding_2025": total_float,
        "as_share_of_revenue": div(total_float, fy25["revenue"]),
        "as_share_of_operating_capital":
            div(total_float, fy25["capital"]["operating_ex_payables_ex_cip"]),
        "supplier_finance": f["supplier_finance"],
        "related_party_payables_million": f["related_party_payables_million"],
        "note": ("선수금과 계약부채는 일이 끝나기 전에 받은 고객 자금입니다. "
                 "공급자금융은 반대 방향으로, FY2024 매입채무에 5,406억원이 "
                 "들어 있었고 거의 전액이 특수관계자에 대한 채무였습니다. "
                 "FY2025에 138억원으로 청산되었으므로 FY2024 영업현금흐름은 "
                 "그만큼 부풀려졌고 FY2025는 그만큼 깎였습니다."),
    }


def main():
    raw = load()
    rows = build_years(raw)
    bases = valuation_bases(raw, rows)
    fy25 = rows[-1]

    # Lease liabilities are treated as debt in the capital measures above, so
    # they are deducted here too. After the 1 November 2025 land purchase they
    # are only W7.4bn, but leaving them out would make the two halves of this
    # file disagree.
    net_cash = (fy25["cash_total"] - (fy25["debt_total"] or 0)
                - (fy25["lease_liabilities"] or 0))
    market_cap = MARKET["price"] * MARKET["shares_outstanding"]

    result = {
        "company": "삼성바이오로직스 (207940.KS)",
        "basis": raw["basis"],
        "market": dict(MARKET, market_cap_computed=market_cap),
        "fx": FX,
        "years": rows,
        "incremental_returns": incremental_returns(rows),
        "owner_earnings": owner_earnings(rows),
        "cost_of_capital": cost_of_capital(rows),
        "valuation_bases": bases,
        "margin_decomposition": margin_decomposition(raw, rows),
        "net_cash": {"cash_and_short_term_instruments": fy25["cash_total"],
                     "interest_bearing_debt": fy25["debt_total"],
                     "lease_liabilities": fy25["lease_liabilities"],
                     "net_cash": net_cash},
        "concentration": concentration_view(raw, rows),
        "customer_funding": float_view(raw, rows),
        "valuation": {},
        "implied": {},
    }

    base_capital = fy25["capital"]["operating_ex_payables_ex_cip"]
    for key in ("reported_fy2025", "run_rate_2026", "run_rate_fx_normalised"):
        base = bases[key]["nopat"]
        scen = dcf(base, net_cash, market_cap, MARKET["shares_outstanding"])
        for s, spec in zip(scen, SCENARIOS):
            s["feasibility"] = feasibility(
                spec, base, base_capital, bases[key]["revenue"],
                fy25["depreciation_amortization"])
        result["valuation"][key] = {
            "label": bases[key]["label"],
            "base_nopat": base,
            "base_operating_capital": base_capital,
            "scenarios": scen,
        }
        result["implied"][key] = {
            "label": bases[key]["label"],
            "against_neutral": implied(base, net_cash, market_cap, SCENARIOS[1]),
            "against_optimistic": implied(base, net_cash, market_cap,
                                          SCENARIOS[2]),
        }

    with open(OUT, "w") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------- console view
    print("삼성바이오로직스 — CDMO 단일사업 기준 (별도 재무제표)\n")
    print(f"{'FY':>5}{'매출':>9}{'영업익':>9}{'마진':>7}{'NOPAT':>9}"
          f"{'영업자본':>10}{'건설중':>9}{'ROIC':>7}{'ROIC(건설중제외)':>18}")
    for r in rows:
        c = r["capital"]
        print(f"{r['fiscal_year']:>5}{r['revenue']/BN:>9,.0f}"
              f"{r['operating_income']/BN:>9,.0f}{r['operating_margin']:>7.1%}"
              f"{r['nopat']/BN:>9,.0f}{c['operating']/BN:>10,.0f}"
              f"{c['construction_in_progress']/BN:>9,.0f}"
              f"{r['roic_operating']:>7.1%}{r['roic_operating_ex_cip']:>18.1%}")

    print("\n증분 ROIC (5년 구간, 매입채무 차감하지 않은 영업자본 · 건설중자산 제외)")
    for e in result["incremental_returns"]:
        if e["years"] == 5:
            k = e["operating_ex_payables_ex_cip"]
            print(f"  FY{e['from']}→FY{e['to']}  ΔNOPAT "
                  f"{e['delta_nopat']/BN:>7,.0f}  ΔIC "
                  f"{k['delta_capital']/BN:>7,.0f}  "
                  f"증분ROIC {k['incremental_roic']:>7.1%}")

    lo, hi = result["cost_of_capital"]["range"]
    print(f"\n자본비용 참고 범위 {lo:.1%} ~ {hi:.1%}")

    md = result["margin_decomposition"]
    print(f"\n영업이익률 FY2024 {md['fy2024_margin']:.1%} → FY2025 "
          f"{md['fy2025_margin']:.1%} (+{md['total_change']*100:.1f}pp)  "
          f"이 중 환율 {md['fx_contribution']*100:+.1f}pp "
          f"({md['fx_share_of_change']:.0%}), 영업 "
          f"{md['operating_contribution']*100:+.1f}pp")
    print("\n환율별 2026 연율화 영업이익")
    for e in bases["fx_sensitivity_of_run_rate"]:
        print(f"  {e['rate_to']:>8,.1f}원/USD  매출 {e['revenue']/1e12:>5,.2f}조  "
              f"영업익 {e['operating_income']/1e12:>5,.2f}조  "
              f"마진 {e['operating_margin']:>6.1%}  NOPAT {e['nopat']/1e12:>5,.2f}조")

    print(f"\n시가총액 {market_cap/1e12:,.2f}조원  "
          f"(주가 {MARKET['price']:,.0f}원 × {MARKET['shares_outstanding']:,}주)")
    print(f"순현금 {net_cash/BN:,.0f}십억원\n")

    for key, v in result["valuation"].items():
        print(f"— {v['label']}  기준 NOPAT {v['base_nopat']/BN:,.0f}십억원")
        for s in v["scenarios"]:
            print(f"    {s['scenario']}  가치 {s['equity_value']/1e12:>6,.2f}조원  "
                  f"주당 {s['value_per_share']:>11,.0f}원  "
                  f"시장대비 {s['upside_vs_market']:>+8.1%}  "
                  f"터미널비중 {s['terminal_share_of_value']:>6.1%}  "
                  f"1년차 재투자율 {s['first_year_reinvestment_rate']:>6.1%}")
            f = s["feasibility"]
            print(f"          10년 누적 재투자 {f['cumulative_reinvestment']/1e12:>5,.1f}조원 "
                  f"(NOPAT의 {f['reinvestment_as_share_of_nopat']:.0%}), "
                  f"외부조달 필요 {f['external_capital_required']/1e12:>4,.1f}조원, "
                  f"투하자본 {f['invested_capital_multiple']:>4,.1f}배, "
                  f"10년후 매출 {f['implied_revenue_end']/1e12:>5,.1f}조원 "
                  f"(US$ {f['implied_revenue_end_usd_bn']:,.0f}십억)")
        im = result["implied"][key]
        print(f"    현재가가 요구하는 초기성장률 (중립 틀) "
              f"{im['against_neutral']['implied_initial_growth']:.1%} "
              f"→ 재투자율 {im['against_neutral']['implied_first_year_reinvestment_rate']:.0%}, "
              f"(낙관 틀) {im['against_optimistic']['implied_initial_growth']:.1%} "
              f"→ 재투자율 {im['against_optimistic']['implied_first_year_reinvestment_rate']:.0%}")
        print(f"    현재가의 내재할인율 (중립 틀) "
              f"{im['against_neutral']['implied_discount_rate']:.1%}, "
              f"(낙관 틀) {im['against_optimistic']['implied_discount_rate']:.1%}\n")

    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
