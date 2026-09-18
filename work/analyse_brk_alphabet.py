"""
Why Berkshire bought Alphabet, tested against the filings, and what that
implies for the valuation.

The earlier reports concluded that Alphabet was not attractive at $355. Berkshire
then built Alphabet into its third-largest holding, and paid roughly the same
price. Either the earlier conclusion is wrong, or Berkshire is solving a
different problem. This file tries to tell those apart, and it does so by
computing things rather than asserting them.

Five computations do the work:

  1. Cost basis. The position was built in three acts across four quarters at
     very different prices. Reconstructing it from 13F share counts and the
     volume-weighted price of each quarter shows whether Berkshire bought
     cheaply and watched it run, or paid today's price.

  2. The instrument choice. In the same week that Alphabet sold Berkshire
     $10bn of common stock, it sold $19.25bn of 6.25% mandatory convertible
     preferred to the public market. The preferred is downside-protected and
     pays a coupon; the common is not and does not. Both payoffs can be written
     as functions of the May 2029 share price, and where they cross is the price
     above which Berkshire's choice was the right one. That crossing point is a
     read on Berkshire's own expectation that does not depend on anyone's
     commentary.

  3. The alternative. Berkshire held $324.9bn of Treasury bills at 30 June 2026
     against $323.8bn of equities. The hurdle a Berkshire dollar has to clear is
     not "the best available equity" - it is a 4.14% bill. That is a legitimate
     reason for Berkshire to buy what a different investor should not.

  4. Incremental return on the AI capital. The question the user raises - that
     returns are falling as the mix shifts to capital-heavy AI infrastructure -
     is tested directly: change in NOPAT over change in operating capital,
     year over year, on the bottom-up capital measure.

  5. The arithmetic of the user's hypothesis. "Returns fall but revenue grows,
     so it is still worth it" is either true or false depending entirely on
     where incremental ROIC sits relative to the discount rate, and the identity
     FCF = NOPAT x (1 - g / incremental ROIC) settles it.

Writes work/brk_alphabet_analysis.json.
"""

import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

RAW = os.path.join(HERE, "brk_alphabet.json")
PRICES = os.path.join(HERE, "brk", "goog_closes.json")
OUT = os.path.join(HERE, "brk_alphabet_analysis.json")

M = 1e6          # the filings are in millions
BN = 1e9

# ---------------------------------------------------------------- market data
PRICE_NOW = 347.33
PRICE_DATE = "2026-09-17"
PRICE_SOURCE = "Yahoo Finance GOOGL 종가"

# Rates, each dated and sourced.
RATES = {
    "t_bill_3m": {"rate": 0.0414, "as_of": "2026-09-16",
                  "series": "FRED DGS3MO"},
    "treasury_10y": {"rate": 0.0501, "as_of": "2026-09-16",
                     "series": "FRED DGS10"},
    "treasury_10y_previous_report": {"rate": 0.0465, "as_of": "2026-08",
                                     "note": "직전 보고서에서 쓴 값"},
}

# Alphabet's FY2025 figures, from the 10-K already collected for the earlier
# reports (accession 0001652044-26-000018).
FY2025 = {
    "revenue": 402_836.0,
    "operating_income": 129_039.0,
    "tax_rate": 0.168,
    "shares_diluted": 12_230.0,
    "cloud_revenue": 58_705.0,
    "cloud_operating_income": 13_910.0,
    "services_revenue": 342_721.0,
    "services_operating_income": 139_404.0,
    "backlog": 242_800.0,
    "source": "FY2025 Form 10-K, accession 0001652044-26-000018",
}

# Scenario set carried over from the earlier Alphabet work so the two are
# comparable. The discount rates are unchanged even though the 10-year has
# risen from 4.65% to 5.01%; that change is reported separately rather than
# folded in silently.
SCENARIOS = [
    {"name": "보수", "growth": 0.06, "fade_to": 0.025, "incremental_roic": 0.15,
     "discount": 0.11, "terminal_growth": 0.020},
    {"name": "중립", "growth": 0.12, "fade_to": 0.035, "incremental_roic": 0.22,
     "discount": 0.10, "terminal_growth": 0.025},
    {"name": "낙관", "growth": 0.20, "fade_to": 0.045, "incremental_roic": 0.30,
     "discount": 0.09, "terminal_growth": 0.030},
]


def div(a, b):
    return None if (a is None or not b) else a / b


def load():
    with open(RAW) as fh:
        raw = json.load(fh)
    with open(PRICES) as fh:
        prices = json.load(fh)
    return raw, prices


# ---------------------------------------------------------------------------
# 1. What Berkshire paid
# ---------------------------------------------------------------------------
def quarter_vwap(prices, year, q):
    """Close-weighted average for a calendar quarter, as a purchase proxy."""
    months = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}[q]
    vals = [v for k, v in prices.items()
            if int(k[:4]) == year and months[0] <= int(k[5:7]) <= months[1]]
    return sum(vals) / len(vals) if vals else None


def cost_basis(raw, prices):
    """
    Rebuild the position quarter by quarter.

    A 13F gives the holding at a quarter end, not the trades, so the price paid
    inside a quarter is unknown. The average close over the quarter is the
    neutral assumption; the private placement is the one leg whose price is
    known exactly, and it is substituted in where it applies.
    """
    q13f = raw["berkshire_13f"]
    pp = raw["private_placement"]
    periods = sorted(q13f)
    legs, held = [], 0
    for p in periods:
        a = q13f[p]["alphabet"]
        now = a["shares"] if a else 0
        added = now - held
        year, quarter = int(p[:4]), (int(p[5:7]) - 1) // 3 + 1
        avg = quarter_vwap(prices, year, quarter)
        leg = {"period": p, "shares_held": now, "shares_added": added,
               "quarter_average_price": avg,
               "rank": a["rank"] if a else None,
               "weight": a["weight"] if a else None,
               "value_reported": (a["value"] if a else 0)}
        if added > 0:
            # In Q2 2026 part of the buying is the private placement, whose
            # price is on the record; only the balance is estimated.
            if p == "2026-06-30":
                pp_shares = pp["total_shares"]
                pp_cost = pp["gross_proceeds_bn"] * BN
                rest = added - pp_shares
                leg["private_placement_shares"] = pp_shares
                leg["private_placement_cost"] = pp_cost
                leg["open_market_shares"] = rest
                leg["estimated_cost"] = pp_cost + rest * avg
                leg["blended_price"] = leg["estimated_cost"] / added
            else:
                leg["estimated_cost"] = added * avg
                leg["blended_price"] = avg
        legs.append(leg)
        held = now

    spent = sum(l.get("estimated_cost", 0) for l in legs)
    shares = held
    return {
        "legs": legs,
        "shares_final": shares,
        "estimated_total_cost": spent,
        "estimated_average_cost_per_share": div(spent, shares),
        "price_now": PRICE_NOW,
        "gain_vs_cost": div(PRICE_NOW * shares - spent, spent),
        "share_of_position_bought_in_2026": div(
            sum(l["shares_added"] for l in legs if l["period"].startswith("2026")),
            shares),
        "method_note": ("13F는 분기말 잔고만 알려주므로 분기 중 매입단가는 알 수 없습니다. "
                        "분기 평균 종가를 중립적 가정으로 썼고, 2026년 6월 4일 "
                        "사모발행분만 실제 체결가를 그대로 적용했습니다."),
    }


# ---------------------------------------------------------------------------
# 2. The instrument choice
# ---------------------------------------------------------------------------
def instrument_choice(raw):
    """
    Common versus the 6.25% mandatory convertible, as payoffs at May 2029.

    Per $1,000 invested on 4 June 2026:

      common      1000 / 348.20 shares, worth that many times the 2029 price
      preferred   three years of 6.25% coupons, plus a conversion that hands
                  over the maximum rate below the floor price, $1,000 of stock
                  between floor and cap, and the minimum rate above the cap

    Where the two cross is the 2029 price above which taking the common was the
    better decision. Berkshire took the common.
    """
    mc = raw["mandatory_convertible"]
    pp = raw["private_placement"]

    # Berkshire's blended price across the two classes it was sold.
    berk_price = ((pp["class_a_shares"] * pp["class_a_price"]
                   + pp["class_c_shares"] * pp["class_c_price"])
                  / pp["total_shares"])
    common_shares = 1000.0 / berk_price

    coupon_years = 3.0          # June 2026 issue, May 2029 mandatory conversion
    coupons = mc["coupon"] * 1000.0 * coupon_years
    lo_rate, hi_rate = (mc["series_b_conversion_rate"]["min"],
                        mc["series_b_conversion_rate"]["max"])
    floor, cap = mc["series_b_floor_price"], mc["series_b_cap_price"]

    def preferred_payoff(s):
        if s <= floor:
            shares = hi_rate
        elif s >= cap:
            shares = lo_rate
        else:
            shares = 1000.0 / s
        return shares * s + coupons

    def common_payoff(s):
        return common_shares * s

    # Above the cap both payoffs are linear in s, so the crossing solves
    # exactly; below it the preferred wins by roughly the coupons.
    crossover_above_cap = coupons / (common_shares - lo_rate)
    crossover_mid = (1000.0 + coupons) / common_shares

    if floor <= crossover_mid <= cap:
        breakeven = crossover_mid
        region = "전환 구간 내부 (액면 $1,000 고정 구간)"
    else:
        breakeven = crossover_above_cap
        region = "상한 초과 구간"

    grid = []
    for s in (250, 300, 348.20, 400, 417.8, 440, 480, 530, 600, 700):
        c, p = common_payoff(s), preferred_payoff(s)
        grid.append({"price_2029": s, "common": c, "preferred": p,
                     "common_minus_preferred": c - p,
                     "common_wins": c > p})

    ann = (breakeven / berk_price) ** (1 / 2.95) - 1
    return {
        "berkshire_blended_price": berk_price,
        "common_shares_per_1000": common_shares,
        "preferred_coupon": mc["coupon"],
        "preferred_coupons_total_per_1000": coupons,
        "preferred_floor_price": floor,
        "preferred_cap_price": cap,
        "capped_call_cap": mc["capped_call_cap_class_c"],
        "breakeven_price_2029": breakeven,
        "breakeven_region": region,
        "breakeven_vs_purchase": div(breakeven, berk_price) - 1,
        "implied_minimum_annual_return": ann,
        "payoff_grid": grid,
        "caveat": ("버크셔가 우선주를 인수할 기회를 제안받았는지는 공시에 없습니다. "
                   "다만 우선주는 같은 주에 공모로 팔렸으므로 버크셔를 포함한 "
                   "누구나 시장에서 살 수 있었습니다. 배당 재투자는 계산에 "
                   "넣지 않았고, 넣으면 손익분기 가격은 조금 더 올라갑니다."),
    }


# ---------------------------------------------------------------------------
# 3. The alternative Berkshire actually had
# ---------------------------------------------------------------------------
def opportunity_cost(raw):
    bs = raw["berkshire_balance_sheet"]
    bills = bs["treasury_bills"][0] * M
    cash = bs["cash_and_equivalents"][0] * M
    equities = bs["equity_securities"][0] * M
    rate = RATES["t_bill_3m"]["rate"]
    return {
        "treasury_bills": bills,
        "cash_and_equivalents": cash,
        "equity_securities": equities,
        "bills_over_equities": div(bills, equities),
        "t_bill_yield": rate,
        "annual_income_on_bills": bills * rate,
        "alphabet_position_value": raw["berkshire_13f"]["2026-06-30"]["alphabet"]["value"],
        "position_as_share_of_bills": div(
            raw["berkshire_13f"]["2026-06-30"]["alphabet"]["value"], bills),
        "note": ("버크셔의 한계 대안은 '더 싼 다른 주식'이 아니라 4.14% 재무부 "
                 "단기채입니다. 2026년 6월 말 기준 주식 $323.8bn보다 단기채 "
                 "$324.9bn이 더 많습니다. 요구수익률이 낮아도 되는 이유이지, "
                 "주식이 싸다는 뜻이 아닙니다."),
    }


# ---------------------------------------------------------------------------
# 4. Did the returns actually fall?
# ---------------------------------------------------------------------------
def operating_capital(a, idx):
    """
    Bottom-up operating capital, the measure the Samsung Biologics work settled
    on. Cash, marketable securities and non-marketable securities are excluded:
    at June 2026 Alphabet held $131.5bn of non-marketable securities whose
    mark-ups drove reported net income to more than twice operating income, and
    none of that is capital employed in search or cloud.
    """
    g = lambda k: a[k][idx]
    return (g("ppe_net") + g("operating_lease_assets") + g("goodwill")
            + g("accounts_receivable") - g("total_current_liabilities"))


def returns(raw):
    a26, a25 = raw["alphabet"]["2026q2"], raw["alphabet"]["2025q2"]
    tax = FY2025["tax_rate"]

    # Half-year operating income, annualised, on both sides of the purchase.
    oi_h1_2026 = a26["income_from_operations"][3]
    oi_h1_2025 = a26["income_from_operations"][2]
    nopat_now = oi_h1_2026 * 2 * (1 - tax)
    nopat_then = oi_h1_2025 * 2 * (1 - tax)

    ic_now = operating_capital(a26, 1)           # 2026-06-30
    ic_then = operating_capital(a25, 1)          # 2025-06-30
    goodwill_added = a26["goodwill"][1] - a25["goodwill"][1]

    inc = div(nopat_now - nopat_then, ic_now - ic_then)
    inc_ex_gw = div(nopat_now - nopat_then,
                    (ic_now - ic_then) - goodwill_added)

    cloud_now = a26["segments"]["Google Cloud"]
    cloud_then = a25["segments"]["Google Cloud"]
    svc_now = a26["segments"]["Google Services"]

    return {
        "tax_rate_used": tax,
        "tax_note": ("2026 상반기 실효세율 19.1%는 비상장주식 평가이익 때문에 "
                     "영업이익에 적용할 수 없는 값입니다. FY2025 실효세율 16.8%를 "
                     "썼습니다."),
        "nopat_annualised_2025": nopat_then,
        "nopat_annualised_2026": nopat_now,
        "operating_capital_2025": ic_then,
        "operating_capital_2026": ic_now,
        "roic_2025": div(nopat_then, ic_then),
        "roic_2026": div(nopat_now, ic_now),
        "roic_change": div(nopat_now, ic_now) - div(nopat_then, ic_then),
        "incremental_roic": inc,
        "incremental_roic_ex_goodwill": inc_ex_gw,
        "goodwill_added": goodwill_added,
        "cloud": {
            "revenue_h1_2025": cloud_then["revenue"][3],
            "revenue_h1_2026": cloud_now["revenue"][3],
            "revenue_growth": div(cloud_now["revenue"][3],
                                  cloud_then["revenue"][3]) - 1,
            "revenue_q2_2026": cloud_now["revenue"][1],
            "revenue_growth_q2": div(cloud_now["revenue"][1],
                                     cloud_now["revenue"][0]) - 1,
            "operating_income_h1_2025": cloud_then["operating_income"][3],
            "operating_income_h1_2026": cloud_now["operating_income"][3],
            "margin_h1_2025": div(cloud_then["operating_income"][3],
                                  cloud_then["revenue"][3]),
            "margin_h1_2026": div(cloud_now["operating_income"][3],
                                  cloud_now["revenue"][3]),
            "margin_q2_2026": div(cloud_now["operating_income"][1],
                                  cloud_now["revenue"][1]),
            "incremental_operating_margin": div(
                cloud_now["operating_income"][3] - cloud_then["operating_income"][3],
                cloud_now["revenue"][3] - cloud_then["revenue"][3]),
            "fy2025_margin": div(FY2025["cloud_operating_income"],
                                 FY2025["cloud_revenue"]),
        },
        "services": {
            "revenue_h1_2026": svc_now["revenue"][3],
            "margin_h1_2026": div(svc_now["operating_income"][3],
                                  svc_now["revenue"][3]),
        },
        "capital_intensity": {
            "capex_h1_2025": -a26["capex"][0],
            "capex_h1_2026": -a26["capex"][1],
            "capex_growth": div(a26["capex"][1], a26["capex"][0]) - 1,
            "ocf_h1_2025": a26["ocf"][0],
            "ocf_h1_2026": a26["ocf"][1],
            "fcf_h1_2025": a26["ocf"][0] + a26["capex"][0],
            "fcf_h1_2026": a26["ocf"][1] + a26["capex"][1],
            "depreciation_h1_2026": a26["depreciation"][1],
            "capex_over_depreciation": div(-a26["capex"][1],
                                           a26["depreciation"][1]),
            "buybacks_h1_2025": -a26["buybacks"][0],
            "buybacks_h1_2026": -a26["buybacks"][1],
            "long_term_debt_2025": a26["long_term_debt"][0],
            "long_term_debt_2026": a26["long_term_debt"][1],
        },
        "backlog": raw["alphabet"]["backlog_2026q2"],
    }


# ---------------------------------------------------------------------------
# 5. The user's hypothesis, as arithmetic
# ---------------------------------------------------------------------------
def hypothesis_test(base_nopat, discount=0.10):
    """
    "Returns fall, but revenue gets much bigger, so it is still worth it."

    Under FCF = NOPAT x (1 - g / incremental ROIC), a perpetuity with constant
    growth is worth NOPAT x (1 - g/r_i) / (k - g). Differentiating in g shows
    the sign of the effect of growth is the sign of (r_i - k): growth adds value
    only when the incremental return exceeds the discount rate, and destroys it
    when it does not, no matter how large the revenue becomes. The grid makes
    that visible.
    """
    grid = []
    for r_i in (0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30):
        row = {"incremental_roic": r_i, "values": []}
        for g in (0.00, 0.03, 0.06, 0.09, 0.12):
            if g >= discount:
                row["values"].append({"growth": g, "value": None,
                                      "note": "성장률이 할인율 이상이면 발산"})
                continue
            v = base_nopat * (1 - g / r_i) / (discount - g)
            row["values"].append({"growth": g, "value": v})
        base = row["values"][0]["value"]
        row["value_change_from_growth"] = [
            None if e["value"] is None else e["value"] / base - 1
            for e in row["values"]]
        grid.append(row)
    return {
        "discount_rate": discount,
        "rule": ("성장은 증분 ROIC이 할인율보다 클 때만 가치를 더합니다. "
                 "작으면 매출이 아무리 커져도 가치를 깎습니다. 매출 규모 자체는 "
                 "가치의 변수가 아닙니다."),
        "grid": grid,
    }


# ---------------------------------------------------------------------------
def dcf(base_nopat, net_cash, shares, market_cap):
    out = []
    for s in SCENARIOS:
        proj, pv, nopat = [], 0.0, base_nopat
        n = 10
        for t in range(1, n + 1):
            g = s["growth"] + (s["fade_to"] - s["growth"]) * (t - 1) / (n - 1)
            rr = g / s["incremental_roic"]
            nopat *= (1 + g)
            fcf = nopat * (1 - rr)
            d = fcf / (1 + s["discount"]) ** t
            pv += d
            proj.append({"year": t, "growth": g, "nopat": nopat,
                         "reinvestment_rate": rr, "free_cash_flow": fcf,
                         "present_value": d})
        tg = s["terminal_growth"]
        term = (proj[-1]["nopat"] * (1 + tg) * (1 - tg / s["incremental_roic"])
                / (s["discount"] - tg))
        term_pv = term / (1 + s["discount"]) ** n
        ev = pv + term_pv
        eq = ev + net_cash
        out.append({
            "scenario": s["name"],
            "assumptions": {k: s[k] for k in
                            ("growth", "fade_to", "incremental_roic",
                             "discount", "terminal_growth")},
            "projection": proj,
            "pv_of_forecast": pv, "pv_of_terminal": term_pv,
            "terminal_share": div(term_pv, ev),
            "enterprise_value": ev, "equity_value": eq,
            "value_per_share": eq / shares,
            "upside_vs_market": div(eq - market_cap, market_cap),
            "first_year_reinvestment_rate": proj[0]["reinvestment_rate"],
        })
    return out


def implied_growth(base_nopat, net_cash, shares, market_cap, template):
    lo, hi = 0.0, 0.50
    for _ in range(80):
        mid = (lo + hi) / 2
        s = dict(template)
        s["growth"] = mid
        s["fade_to"] = min(template["fade_to"], mid)
        # dcf() walks the module-level scenario list, so the single-scenario
        # projection is written out here rather than reusing it.
        pv, nopat = 0.0, base_nopat
        for t in range(1, 11):
            g = s["growth"] + (s["fade_to"] - s["growth"]) * (t - 1) / 9
            nopat *= (1 + g)
            pv += nopat * (1 - g / s["incremental_roic"]) / (1 + s["discount"]) ** t
        tg = s["terminal_growth"]
        term = (nopat * (1 + tg) * (1 - tg / s["incremental_roic"])
                / (s["discount"] - tg) / (1 + s["discount"]) ** 10)
        eq = pv + term + net_cash
        if eq < market_cap:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main():
    raw, prices = load()
    a26 = raw["alphabet"]["2026q2"]

    cost = cost_basis(raw, prices)
    choice = instrument_choice(raw)
    opp = opportunity_cost(raw)
    ret = returns(raw)

    # Valuation inputs. Shares: FY2025 diluted plus the June issuance, plus the
    # mandatory convertible at its maximum conversion, which is the conservative
    # end for an existing holder.
    mc = raw["mandatory_convertible"]
    pp = raw["private_placement"]
    new_common = (pp["total_shares"]
                  + pp["public_offering"]["class_a_shares"]
                  + pp["public_offering"]["class_c_shares"]
                  + pp["public_offering"]["overallotment_class_a"]
                  + pp["public_offering"]["overallotment_class_c"]) / M
    conv_max = (mc["preferred_shares_per_series"]
                * (mc["series_a_conversion_rate"]["max"]
                   + mc["series_b_conversion_rate"]["max"])) / M
    shares = FY2025["shares_diluted"] + new_common + conv_max

    net_cash = (a26["cash_and_securities"][1] - a26["long_term_debt"][1]
                - mc["gross_proceeds_total"] / M)
    market_cap = PRICE_NOW * shares
    base_nopat = ret["nopat_annualised_2026"]

    scen = dcf(base_nopat, net_cash, shares, market_cap)
    imp = {s["scenario"]: implied_growth(base_nopat, net_cash, shares,
                                         market_cap, s["assumptions"])
           for s in scen}

    result = {
        "generated": date.today().isoformat(),
        "who_decided": {
            "berkshire_principal_executive_officer": "Gregory E. Abel",
            "evidence": ("버크셔 2026년 2분기 10-Q의 302조 인증서(Exhibit 31.1)에 "
                         "Gregory E. Abel이 President and Principal Executive "
                         "Officer로 서명했습니다 (2026-08-08)."),
            "buyback_policy_language": ("같은 10-Q의 자사주 정책 문구가 "
                                        "'Chief Executive Officer, after "
                                        "consultation with the Chairman of the "
                                        "Board'로 바뀌어 있습니다. 예전에는 "
                                        "버핏 본인을 지목하는 문구였습니다."),
            "implication": ("알파벳 지분의 83%가 2026년 1~2분기에 매입되었으므로 "
                            "그 결정은 아벨 CEO 체제에서, 이사회 의장인 버핏과 "
                            "협의하여 내려진 것입니다. '버핏이 샀다'가 아니라 "
                            "'버크셔가 샀다'로 읽어야 합니다. 또한 100억 달러 "
                            "사모발행은 포트폴리오 매니저의 매매가 아니라 "
                            "회사 대 회사의 협상입니다."),
            "source": "Berkshire Form 10-Q Q2 2026, Exhibit 31.1",
        },
        "price": {"price": PRICE_NOW, "as_of": PRICE_DATE,
                  "source": PRICE_SOURCE},
        "rates": RATES,
        "cost_basis": cost,
        "instrument_choice": choice,
        "opportunity_cost": opp,
        "returns": ret,
        "hypothesis_test": hypothesis_test(base_nopat),
        "valuation": {
            "shares_used": shares,
            "shares_note": ("FY2025 희석주식 12,230백만주 + 2026년 6월 공모·사모 "
                            f"{new_common:,.0f}백만주 + 전환우선주 최대전환 "
                            f"{conv_max:,.0f}백만주"),
            "net_cash": net_cash,
            "net_cash_note": ("현금·유가증권 − 장기차입금 − 전환우선주. "
                              "비상장주식 $131.5bn은 제외했습니다"),
            "market_cap": market_cap,
            "base_nopat": base_nopat,
            "scenarios": scen,
            "implied_initial_growth": imp,
        },
    }
    with open(OUT, "w") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------- console
    print("■ 버크셔가 언제 얼마에 샀는가")
    for l in cost["legs"]:
        if l["shares_added"]:
            print(f"  {l['period']}  +{l['shares_added']:>12,.0f}주  "
                  f"평균 ${l.get('blended_price') or 0:>7,.2f}  "
                  f"누적 {l['shares_held']:>12,.0f}주  "
                  f"순위 {l['rank']}  비중 {l['weight']:.1%}")
    print(f"  → 총 {cost['shares_final']:,.0f}주, 추정 원가 "
          f"${cost['estimated_total_cost']/BN:,.1f}bn, 평균 "
          f"${cost['estimated_average_cost_per_share']:,.2f}/주")
    print(f"  → 현재가 ${PRICE_NOW}, 평가손익 {cost['gain_vs_cost']:+.1%}, "
          f"2026년에 산 비중 {cost['share_of_position_bought_in_2026']:.0%}")

    print("\n■ 우선주 대신 보통주를 골랐다는 사실이 함축하는 것")
    print(f"  버크셔 매입가 ${choice['berkshire_blended_price']:,.2f}, "
          f"우선주 쿠폰 {choice['preferred_coupon']:.2%}, "
          f"전환 하한 ${choice['preferred_floor_price']:,.2f} / 상한 "
          f"${choice['preferred_cap_price']:,.2f}")
    print(f"  → 2029년 5월 주가가 ${choice['breakeven_price_2029']:,.0f} 이상이어야 "
          f"보통주 선택이 옳았던 것이 됩니다 "
          f"({choice['breakeven_vs_purchase']:+.1%}, 연 "
          f"{choice['implied_minimum_annual_return']:.1%})")

    print("\n■ 버크셔의 대안")
    print(f"  단기국채 ${opp['treasury_bills']/BN:,.0f}bn @ "
          f"{opp['t_bill_yield']:.2%}  vs  주식 "
          f"${opp['equity_securities']/BN:,.0f}bn")

    print("\n■ 수익률이 실제로 떨어졌는가")
    print(f"  ROIC {ret['roic_2025']:.1%} → {ret['roic_2026']:.1%} "
          f"({ret['roic_change']*100:+.1f}pp)")
    print(f"  증분 ROIC {ret['incremental_roic']:.1%} "
          f"(영업권 제외 {ret['incremental_roic_ex_goodwill']:.1%})")
    c = ret["cloud"]
    print(f"  클라우드 매출 +{c['revenue_growth']:.1%} (2분기 "
          f"+{c['revenue_growth_q2']:.1%}), 영업이익률 "
          f"{c['margin_h1_2025']:.1%} → {c['margin_h1_2026']:.1%} "
          f"(2분기 {c['margin_q2_2026']:.1%}), 증분 마진 "
          f"{c['incremental_operating_margin']:.1%}")
    ci = ret["capital_intensity"]
    print(f"  설비투자 ${ci['capex_h1_2025']/1000:,.1f}bn → "
          f"${ci['capex_h1_2026']/1000:,.1f}bn, 잉여현금흐름 "
          f"${ci['fcf_h1_2025']/1000:,.1f}bn → ${ci['fcf_h1_2026']/1000:,.1f}bn, "
          f"자사주 ${ci['buybacks_h1_2025']/1000:,.1f}bn → "
          f"${ci['buybacks_h1_2026']/1000:,.1f}bn")

    print("\n■ 가치평가 (2026 상반기 연율화 NOPAT "
          f"${base_nopat/1000:,.1f}bn 기준)")
    print(f"  시가총액 ${market_cap/1000:,.0f}bn, 주식수 {shares:,.0f}백만주")
    for s in scen:
        print(f"    {s['scenario']}  ${s['equity_value']/1000:>7,.0f}bn  "
              f"주당 ${s['value_per_share']:>7,.0f}  "
              f"시장대비 {s['upside_vs_market']:>+7.1%}  "
              f"터미널 {s['terminal_share']:.0%}  "
              f"현재가 정당화 성장률 {imp[s['scenario']]:.1%}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
