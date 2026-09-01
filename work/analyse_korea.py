"""
Samsung Electronics and SK hynix, valued on the same basis as the rest.

The valuation is the one the Alphabet work settled on: free cash flow is NOPAT
less the capital growth costs, with the reinvestment rate derived rather than
assumed - RR = g / incremental ROIC - so no scenario can grow without paying
for it. Ten forecast years with the growth rate fading, then a terminal value
on the same identity, then net cash added.

One thing has to be handled differently, and it is not a detail. These are
memory-cycle businesses. SK hynix lost W7.7 trillion at the operating line in
FY2023 and made W47.2 trillion in FY2025. Starting a discounted cash flow from
whichever year happens to be latest capitalises a point in the cycle and calls
it intrinsic value. So every figure below is produced twice: once from the
latest fiscal year, and once from a cycle-normalised base. The normalised run
is the one to read.

Writes work/kr/korea_valuation.json.
"""

import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calc  # noqa: E402

RAW = os.path.join(HERE, "kr", "korea_raw.json")
OUT = os.path.join(HERE, "kr", "korea_valuation.json")

# Market data, each with its source and date.
MARKET = {
    "005930.KS": {
        "price": 261_000.0,
        "price_preferred": 190_300.0,
        "shares_ordinary": 5_827_808_935,
        "shares_preferred": 802_371_203,
        "shares_note": ("보통주·우선주 모두 자기주식 차감 후 유통주식수 "
                        "(FY2025 감사보고서 자본 주석). 우선주는 별도 종목코드 "
                        "005935로 거래되므로 각자의 종가로 평가했습니다."),
        "price_source": "네이버 금융 일별시세 (005930 / 005935), 2026-09-01 종가",
    },
    "000660.KS": {
        "price": 1_693_000.0,
        "shares_issued": 728_002_365,
        "treasury_shares": 26_310_845,
        "shares_note": ("발행주식 728,002,365주에서 자기주식 26,310,845주를 차감. "
                        "자기주식에는 교환사채 발행으로 한국예탁결제원에 예탁된 "
                        "8,932,547주가 포함됩니다 (F-1 주석)."),
        "price_source": "네이버 금융 일별시세 (000660), 2026-09-01 종가",
    },
}

FX = {"krw_per_usd": 1379.41, "as_of": "2026-08-28",
      "series": "FRED DEXKOUS (Korea / U.S. Foreign Exchange Rate)",
      "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXKOUS"}

RISK_FREE_KR = {"rate": 0.04181, "as_of": "2026-06",
                "series": "FRED IRLTLT01KRM156N (Korea 10-year government bond yield)",
                "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=IRLTLT01KRM156N"}

# The same three scenarios the Alphabet valuation used, so the numbers are
# comparable across the report. Korea's 10-year yield (4.18%) sits close enough
# to the US 10-year (4.65%) that the discount rates carry over without a
# country adjustment; the difference is noted rather than modelled.
SCENARIOS = [
    {"name": "보수", "growth": 0.02, "fade_to": 0.01, "incremental_roic": 0.08,
     "discount": 0.12, "terminal_growth": 0.015},
    {"name": "중립", "growth": 0.05, "fade_to": 0.025, "incremental_roic": 0.13,
     "discount": 0.10, "terminal_growth": 0.020},
    {"name": "낙관", "growth": 0.09, "fade_to": 0.04, "incremental_roic": 0.20,
     "discount": 0.08, "terminal_growth": 0.025},
]

TAX_FLOOR, TAX_CEIL, TAX_DEFAULT = 0.05, 0.40, 0.22   # 22%: Korea's headline rate


def div(a, b):
    return None if (a is None or not b) else a / b


def load():
    with open(RAW) as fh:
        return json.load(fh)


def effective_tax(row):
    tax, pretax = row.get("income_tax_expense"), row.get("pretax_income")
    if tax is None or pretax is None or pretax <= 0:
        return TAX_DEFAULT, "세전이익이 없거나 음수여서 법정세율 22% 적용"
    r = tax / pretax
    if r < TAX_FLOOR:
        return TAX_FLOOR, f"실효세율 {r:.1%}가 하한 미만이라 5%로 제한"
    if r > TAX_CEIL:
        return TAX_CEIL, f"실효세율 {r:.1%}가 상한 초과라 40%로 제한"
    return r, f"실효 {r:.1%}"


def build_years(company):
    rows = []
    prev = None
    for y in company["years"]:
        ebit = y.get("operating_income")
        tax, tax_note = effective_tax(y)
        nopat = None if ebit is None else ebit * (1 - tax)
        debt = None
        if y.get("short_term_debt") is not None or y.get("long_term_debt") is not None:
            debt = (y.get("short_term_debt") or 0) + (y.get("long_term_debt") or 0)
        eq, cash = y.get("total_equity"), y.get("cash_and_equivalents")
        ic = None if (eq is None or cash is None or debt is None) else eq + debt - cash
        ic_avg = ic if prev is None or prev.get("invested_capital") is None else (
            (ic + prev["invested_capital"]) / 2 if ic is not None else None)
        # Operating working capital, cash and short-term debt excluded, so a
        # company that piled up cash does not read as having consumed it.
        wc = None
        if y.get("current_assets") is not None and y.get("current_liabilities") is not None:
            wc = ((y["current_assets"] - (cash or 0))
                  - (y["current_liabilities"] - (y.get("short_term_debt") or 0)))
        d_wc = None
        if wc is not None and prev is not None and prev.get("working_capital") is not None:
            d_wc = wc - prev["working_capital"]
        oe = None
        if all(v is not None for v in (y.get("net_income"),
                                       y.get("depreciation_amortization"),
                                       y.get("capex"), d_wc)):
            oe = calc.owner_earnings(y["net_income"], y["depreciation_amortization"],
                                     y["capex"], d_wc)
        row = {
            "fiscal_year": y["fiscal_year"],
            "revenue": y.get("revenue"),
            "operating_income": ebit,
            "operating_margin": div(ebit, y.get("revenue")),
            "net_income": y.get("net_income"),
            "tax_rate": tax, "tax_note": tax_note,
            "nopat": nopat,
            "interest_bearing_debt": debt,
            "total_equity": eq,
            "cash_and_equivalents": cash,
            "invested_capital": ic,
            "invested_capital_avg": ic_avg,
            "roic": div(nopat, ic_avg),
            "roe": div(y.get("net_income"), eq),
            "capex": y.get("capex"),
            "depreciation_amortization": y.get("depreciation_amortization"),
            "capex_to_depreciation": div(y.get("capex"), y.get("depreciation_amortization")),
            "operating_cash_flow": y.get("operating_cash_flow"),
            "working_capital": wc,
            "change_in_working_capital": d_wc,
            "owner_earnings": oe,
            "capex_to_revenue": div(y.get("capex"), y.get("revenue")),
        }
        rows.append(row)
        prev = row
    return rows


def cycle_summary(rows):
    """Where the company sits in its cycle, and what a normal year looks like.

    A single-year margin is the wrong input for a memory company. The
    normalised margin is the median of the observed years, which treats the
    trough and the peak as equally informative - the mean would let one
    extraordinary year set the level.
    """
    usable = [r for r in rows if r["operating_margin"] is not None]
    margins = [r["operating_margin"] for r in usable]
    latest = usable[-1]
    med = statistics.median(margins)
    return {
        "years_observed": len(usable),
        "window": f"FY{usable[0]['fiscal_year']}..FY{usable[-1]['fiscal_year']}",
        "operating_margin_median": med,
        "operating_margin_min": min(margins),
        "operating_margin_min_year": usable[margins.index(min(margins))]["fiscal_year"],
        "operating_margin_max": max(margins),
        "operating_margin_max_year": usable[margins.index(max(margins))]["fiscal_year"],
        "operating_margin_latest": latest["operating_margin"],
        "latest_vs_median": div(latest["operating_margin"], med),
        "loss_years": [r["fiscal_year"] for r in usable if (r["operating_income"] or 0) < 0],
        "operating_margin_mean": statistics.fmean(margins),
        "mean_operating_income": statistics.fmean(margins) * latest["revenue"],
        "normalised_operating_income": med * latest["revenue"],
        "normalisation": (f"관측된 {len(usable)}개 연도 영업이익률의 중앙값 "
                          f"{med:.1%}를 최근 매출에 적용"),
    }


def returns_summary(rows):
    roics = [(r["fiscal_year"], r["roic"]) for r in rows if r["roic"] is not None]
    incr = []
    for i in range(3, len(rows)):
        a, b = rows[i - 3], rows[i]
        if a["nopat"] is None or b["nopat"] is None:
            continue
        if a["invested_capital"] is None or b["invested_capital"] is None:
            continue
        d_cap = b["invested_capital"] - a["invested_capital"]
        if d_cap <= 0:
            continue
        incr.append({"window": f"FY{a['fiscal_year']}→FY{b['fiscal_year']}",
                     "delta_nopat": b["nopat"] - a["nopat"],
                     "delta_invested_capital": d_cap,
                     "incremental_roic": (b["nopat"] - a["nopat"]) / d_cap})
    full = None
    firsts = [r for r in rows if r["nopat"] is not None and r["invested_capital"] is not None]
    if len(firsts) >= 2:
        a, b = firsts[0], firsts[-1]
        d_cap = b["invested_capital"] - a["invested_capital"]
        if d_cap > 0:
            full = {"window": f"FY{a['fiscal_year']}→FY{b['fiscal_year']}",
                    "delta_nopat": b["nopat"] - a["nopat"],
                    "delta_invested_capital": d_cap,
                    "incremental_roic": (b["nopat"] - a["nopat"]) / d_cap}
    return {
        "roic_by_year": [{"fiscal_year": f, "roic": v} for f, v in roics],
        "roic_median": statistics.median([v for _, v in roics]) if roics else None,
        "roic_latest": roics[-1][1] if roics else None,
        "roic_min": min([v for _, v in roics]) if roics else None,
        "roic_years_above_10pct": sum(1 for _, v in roics if v >= 0.10),
        "roic_years_observed": len(roics),
        "incremental_roic_rolling_3y": incr,
        "incremental_roic_full": full,
    }


def market_cap(ticker, rows):
    m = MARKET[ticker]
    if ticker == "005930.KS":
        cap = (m["shares_ordinary"] * m["price"]
               + m["shares_preferred"] * m["price_preferred"])
        shares = m["shares_ordinary"] + m["shares_preferred"]
    else:
        shares = m["shares_issued"] - m["treasury_shares"]
        cap = shares * m["price"]
    return cap / 1e6, shares       # to millions of won, matching the statements


def dcf(base_nopat, net_cash, cap, shares):
    out = []
    for s in SCENARIOS:
        rows, pv_sum, nopat = [], 0.0, base_nopat
        n = 10
        for t in range(1, n + 1):
            g = s["growth"] + (s["fade_to"] - s["growth"]) * (t - 1) / (n - 1)
            rr = g / s["incremental_roic"]
            nopat *= (1 + g)
            fcf = nopat * (1 - rr)
            pv = fcf / (1 + s["discount"]) ** t
            pv_sum += pv
            rows.append({"year": t, "growth": g, "nopat": nopat,
                         "reinvestment_rate": rr, "free_cash_flow": fcf,
                         "present_value": pv})
        tg = s["terminal_growth"]
        trr = tg / s["incremental_roic"]
        terminal = rows[-1]["nopat"] * (1 + tg) * (1 - trr) / (s["discount"] - tg)
        terminal_pv = terminal / (1 + s["discount"]) ** n
        ev = pv_sum + terminal_pv
        equity = ev + net_cash
        out.append({
            "scenario": s["name"],
            "assumptions": {k: s[k] for k in
                            ("growth", "fade_to", "incremental_roic",
                             "discount", "terminal_growth")},
            "first_year_reinvestment_rate": rows[0]["reinvestment_rate"],
            "projection": rows,
            "pv_of_forecast": pv_sum,
            "pv_of_terminal": terminal_pv,
            "terminal_share_of_value": div(terminal_pv, ev),
            "enterprise_value": ev,
            "equity_value": equity,
            "value_per_share": equity * 1e6 / shares,
            "upside_vs_market": div(equity - cap, cap),
            "margin_of_safety": div(equity - cap, equity),
        })
    return out


def implied(base_nopat, net_cash, cap):
    """The annual return today's price delivers on the neutral path."""
    s = SCENARIOS[1]

    def value(disc):
        pv_sum, nopat = 0.0, base_nopat
        n = 10
        for t in range(1, n + 1):
            g = s["growth"] + (s["fade_to"] - s["growth"]) * (t - 1) / (n - 1)
            nopat *= (1 + g)
            pv_sum += nopat * (1 - g / s["incremental_roic"]) / (1 + disc) ** t
        tg = s["terminal_growth"]
        term = nopat * (1 + tg) * (1 - tg / s["incremental_roic"]) / (disc - tg)
        return pv_sum + term / (1 + disc) ** n + net_cash

    lo, hi = 0.021, 0.50
    if value(lo) < cap:
        return None
    for _ in range(90):
        mid = (lo + hi) / 2
        if value(mid) > cap:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def implied_operating_income(net_cash, cap, tax):
    """The steady-state operating income today's price implies.

    For a cyclical this is the question worth asking. Instead of choosing which
    year is normal and defending it, invert the neutral scenario and read off
    the normal the market has already chosen.
    """
    s = SCENARIOS[1]

    def value(op):
        nopat, pv_sum = op * (1 - tax), 0.0
        n = 10
        for t in range(1, n + 1):
            g = s["growth"] + (s["fade_to"] - s["growth"]) * (t - 1) / (n - 1)
            nopat *= (1 + g)
            pv_sum += nopat * (1 - g / s["incremental_roic"]) / (1 + s["discount"]) ** t
        tg = s["terminal_growth"]
        term = nopat * (1 + tg) * (1 - tg / s["incremental_roic"]) / (s["discount"] - tg)
        return pv_sum + term / (1 + s["discount"]) ** n + net_cash

    lo, hi = 0.0, cap
    for _ in range(90):
        mid = (lo + hi) / 2
        if value(mid) < cap:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def analyse(ticker, company):
    rows = build_years(company)
    cyc = cycle_summary(rows)
    ret = returns_summary(rows)
    cap, shares = market_cap(ticker, rows)
    latest = rows[-1]
    net_cash = ((latest["cash_and_equivalents"] or 0)
                - (latest["interest_bearing_debt"] or 0))
    tax = latest["tax_rate"]

    bases = {
        "latest_year": {
            "label": f"최근년도 (FY{latest['fiscal_year']}) 기준",
            "operating_income": latest["operating_income"],
            "nopat": latest["nopat"],
            "caveat": "사이클 고점의 이익을 영구화하는 계산입니다",
        },
        "cycle_median": {
            "label": "사이클 정규화 — 중앙값",
            "operating_income": cyc["normalised_operating_income"],
            "nopat": cyc["normalised_operating_income"] * (1 - tax),
            "caveat": cyc["normalisation"],
        },
        "cycle_mean": {
            "label": "사이클 정규화 — 평균",
            "operating_income": cyc["mean_operating_income"],
            "nopat": cyc["mean_operating_income"] * (1 - tax),
            "caveat": (f"관측 연도 영업이익률의 산술평균 {cyc['operating_margin_mean']:.1%}를 "
                       "최근 매출에 적용. 적자 연도의 무게가 중앙값보다 크게 반영됩니다"),
        },
    }
    # A run-rate base only when the interim is far from the last full year -
    # for a memory company at a turn, the fiscal year can already be history.
    interim = company.get("interim")
    if interim and interim.get("half_operating_income"):
        ann_op = interim["half_operating_income"] * 2
        ann_rev = interim["half_revenue"] * 2
        bases["run_rate"] = {
            "label": f"현재 실적 연환산 ({interim['period']})",
            "operating_income": ann_op,
            "annualised_revenue": ann_rev,
            "operating_margin": div(interim["half_operating_income"],
                                    interim["half_revenue"]),
            "nopat": ann_op * (1 - tax),
            "caveat": ("2026년 상반기 실적을 두 배 한 값입니다. 지금의 메모리 가격이 "
                       "그대로 이어진다는 가정이며, 정상이익이 아니라 현재 국면의 "
                       "상한선입니다"),
        }

    valuations = {}
    for key, b in bases.items():
        valuations[key] = {
            "base": b,
            "scenarios": dcf(b["nopat"], net_cash, cap, shares),
            "implied_return_at_current_price": implied(b["nopat"], net_cash, cap),
        }

    # The inversion that matters for a cyclical. Rather than arguing about
    # which year is normal, solve for the normal the price is assuming.
    implied_op = implied_operating_income(net_cash, cap, tax)
    run = bases.get("run_rate")
    # For a cyclical the useful question is not "which year is normal" but
    # "what fraction of what it is earning right now does the price assume
    # survives". That ratio is the whole argument in one number.
    sustain = []
    if run:
        for frac in (0.25, 0.35, 0.50, 0.65, 0.75, 1.00):
            op = run["operating_income"] * frac
            v = dcf(op * (1 - tax), net_cash, cap, shares)[1]
            sustain.append({"fraction_of_run_rate": frac,
                            "operating_income": op,
                            "implied_margin_on_run_rate_revenue":
                                div(op, run["annualised_revenue"]),
                            "value_per_share": v["value_per_share"],
                            "vs_price": div(v["value_per_share"],
                                            MARKET[ticker]["price"])})
    sens = []
    for margin in sorted({round(m, 4) for m in
                          [cyc["operating_margin_min"], 0.05, 0.10, 0.15, 0.20, 0.25,
                           0.30, 0.35, 0.40, 0.50,
                           cyc["operating_margin_median"],
                           cyc["operating_margin_latest"]] if m is not None and m > 0}):
        op = margin * latest["revenue"]
        v = dcf(op * (1 - tax), net_cash, cap, shares)[1]      # neutral scenario
        sens.append({"operating_margin": margin,
                     "operating_income": op,
                     "value_per_share": v["value_per_share"],
                     "vs_price": div(v["value_per_share"], MARKET[ticker]["price"])})

    reinvest = div((latest["capex"] or 0) - (latest["depreciation_amortization"] or 0)
                   + (latest["change_in_working_capital"] or 0), latest["nopat"])
    return {
        "ticker": ticker,
        "company_name": company["company_name"],
        "listing": company["listing"],
        "source": company["source"],
        "source_url": company.get("source_url") or company.get("source_page"),
        "accession": company.get("accession"),
        "source_confidence": company["source_confidence"],
        "source_note": company["source_note"],
        "market": dict(MARKET[ticker], market_cap_krw_mn=cap,
                       shares_outstanding=shares,
                       market_cap_usd_bn=cap * 1e6 / FX["krw_per_usd"] / 1e9),
        "years": rows,
        "cycle": cyc,
        "returns": ret,
        "net_cash": net_cash,
        "reinvestment_rate_latest": reinvest,
        "valuations": valuations,
        "implied_normalised_operating_income": implied_op,
        "implied_normalised_margin_on_latest_revenue": div(implied_op, latest["revenue"]),
        "implied_vs_latest_year_operating_income": div(implied_op, latest["operating_income"]),
        "implied_vs_run_rate_operating_income": (
            div(implied_op, run["operating_income"]) if run else None),
        "run_rate_sustain_sensitivity": sustain,
        "margin_sensitivity": sens,
        "interim": company.get("interim"),
    }


def main():
    raw = load()
    out = {
        "generated_at_utc": raw["generated_at_utc"],
        "currency": "KRW, millions unless stated",
        "fx": FX,
        "risk_free_korea": RISK_FREE_KR,
        "method": ("잉여현금흐름 = NOPAT × (1 − 성장률 ÷ 신규 ROIC). 10년 예측 후 "
                   "영구가치, 순현금 가산. 알파벳 밸류에이션과 동일한 구조입니다."),
        "scenarios": SCENARIOS,
        "companies": {},
    }
    for ticker, company in raw["companies"].items():
        out["companies"][ticker] = analyse(ticker, company)

    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(f"korea_valuation -> {OUT}")

    for t, c in out["companies"].items():
        print(f"\n== {c['company_name']} ({t})  시총 "
              f"₩{c['market']['market_cap_krw_mn']/1e6:,.0f}조 "
              f"(${c['market']['market_cap_usd_bn']:,.0f}B)")
        print(f"   영업이익률 중앙값 {c['cycle']['operating_margin_median']:.1%} "
              f"({c['cycle']['window']}), 최근 {c['cycle']['operating_margin_latest']:.1%}, "
              f"최저 {c['cycle']['operating_margin_min']:.1%} "
              f"(FY{c['cycle']['operating_margin_min_year']})")
        print(f"   ROIC 중앙값 {c['returns']['roic_median']:.1%}, "
              f"최근 {c['returns']['roic_latest']:.1%}")
        for key, v in c["valuations"].items():
            line = "  ".join(
                f"{s['scenario']} ₩{s['value_per_share']:,.0f}" for s in v["scenarios"])
            ir = v["implied_return_at_current_price"]
            print(f"   [{v['base']['label']}] {line}  | 함축수익률 "
                  f"{('%.2f%%' % (ir * 100)) if ir else '주가가 상한 초과'}")
        print(f"   현재가 ₩{c['market']['price']:,.0f}")
        print(f"   → 현재가가 전제하는 정상 영업이익 "
              f"₩{c['implied_normalised_operating_income']/1e6:,.1f}조 "
              f"= FY{c['years'][-1]['fiscal_year']} 영업이익의 "
              f"{c['implied_vs_latest_year_operating_income']:.1f}배, "
              f"현재 연환산 실적의 "
              f"{c['implied_vs_run_rate_operating_income']:.0%}")


if __name__ == "__main__":
    main()
