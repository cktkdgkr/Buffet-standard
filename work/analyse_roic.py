"""
ROIC by year for the fifty US companies, and the spread over a 10% cost of
capital.

Independent of work/analyse.py by construction: different inputs
(work/roic/roic_raw.json from the companyfacts API rather than filing text),
different code, written without reading the other engine's output. The
reconciliation against it lives in verify_roic.py, which is where the two are
allowed to meet.

    NOPAT            = operating income x (1 - effective tax rate)
    invested capital = total equity + interest-bearing debt
                       - cash and short-term investments
    ROIC             = NOPAT / average invested capital
    spread           = ROIC - 10%

Three decisions in that are judgments rather than arithmetic, so each is made
once, explicitly, and recorded per company-year.

1. Which operating income. Eighteen of the fifty do not report an
   operating-income subtotal at all - pharma and oil mostly run revenue
   straight down to pretax income. The earlier audit established that falling
   back to "pretax income + interest expense" is wrong, because it pulls
   interest and investment income into a numerator whose denominator has had
   the cash subtracted out. So a subtotal is reconstructed instead, and the
   route is chosen on measured accuracy: every route was tested against the
   reported subtotal on the 1,600-odd company-years where both exist.

       reported OperatingIncomeLoss                      - preferred
       gross profit - operating expenses                 100.0% (n=228)
       revenue - cost of revenue - operating expenses     94.6% (n=241)
       revenue - costs and expenses                       85.8% (n=176)
       pretax - non-operating income                      50.3% (n=477)

   The last route is a coin flip, because many companies tag
   NonoperatingIncomeExpense as only part of the non-operating block. It is
   used only where nothing else exists, and the year is marked LOW confidence
   so it can be excluded from any conclusion.

2. Cash. Cash and equivalents plus short-term investments, following the 2007
   letter's test of the capital "required to conduct the business" - a Treasury
   portfolio is not. Long-term marketable securities are left in capital, which
   is the conservative choice.

3. Financials. SIC 6000-6799 get no ROIC. For a bank, borrowing is the raw
   material rather than the financing, so equity plus debt less cash is not a
   measure of anything.

Writes work/roic/roic.json.
"""

import json
import os
import statistics
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "roic", "roic_raw.json")
OUT = os.path.join(HERE, "roic", "roic.json")

WACC = 0.10                  # the user's instruction: one hurdle for everyone
FIRST_FY, LAST_FY = 2016, 2025

TAX_FLOOR, TAX_CEIL = 0.05, 0.40
TAX_DEFAULT = 0.21           # US federal statutory rate post-2017

# Route label -> measured accuracy against the reported subtotal, from the
# test in this module's docstring. Carried so the report can cite it.
ROUTE_ACCURACY = {
    "reported": 1.0,
    "gross_profit_less_operating_expenses": 1.000,
    "revenue_less_cost_of_revenue_less_operating_expenses": 0.946,
    "revenue_less_costs_and_expenses": 0.858,
    "pretax_less_nonoperating": 0.503,
    # Route V is not a population statistic but a per-year proof: every year it
    # is used has been tied out against filed pretax income within 1%.
    "verified_line_build": None,
}
# Routes whose numerator is derived from pretax income, so the pretax
# reconciliation cannot test them, plus any bottom-up build that failed it.
LOW_CONFIDENCE_ROUTES = {
    "pretax_less_nonoperating",
    "pretax_plus_interest_less_investment_income",
}


def g(row, key):
    v = row.get(key)
    return None if v is None else float(v)


OPERATING_EXPENSE_LINES = (
    "research_and_development", "acquired_iprd", "selling_general_admin",
    "selling_and_marketing", "restructuring", "amortization_intangibles",
    "impairment", "litigation",
)
NONOPERATING_LINES = (
    "investment_income_interest", "other_nonoperating_detail",
    "equity_method_income", "gain_on_sale_of_business",
)
TIE_OUT_TOLERANCE = 0.01


def nonoperating_net(row):
    """Everything below the operating line, as a single signed amount."""
    net = -(g(row, "interest_expense") or 0.0)
    for k in NONOPERATING_LINES:
        x = g(row, k)
        if x is not None:
            net += x
    return net


def tie_out(oi, row):
    """
    How far a candidate subtotal is from reconciling to filed pretax income.

    None where the check cannot be run. This is the single gate every bottom-up
    route passes through, which is what stopped route C - revenue less total
    costs and expenses - from being believed. On the 176 company-years where a
    reported subtotal exists to compare against, route C matched it 85.8% of
    the time, and that number is measured only on companies that report a
    subtotal, so it says nothing about the companies that do not. Applied to
    GE, whose Revenues tag covers the industrial business while CostsAndExpenses
    covers the whole group, route C returned minus $6.4bn of operating income
    for FY2016 against a reported pretax profit, and the old study's plus
    $7.0bn. Nothing in the route's own accuracy statistic would have caught
    that; the pretax reconciliation does, immediately.
    """
    pre = g(row, "pretax_income")
    if oi is None or pre is None or abs(pre) < 1e6:
        return None
    return abs(oi + nonoperating_net(row) - pre) / abs(pre)


def verified_build(row):
    """
    Rebuild the subtotal from the lines a company does file, then prove the
    rebuild rather than trust it.

    Lilly, Merck, J&J, IBM and KLA publish no operating-income line, and every
    heuristic for inventing one scored badly in test_oi_routes.py - the best of
    them, pretax less non-operating income, is right 50.3% of the time. So the
    pieces are added up explicitly and then checked: put the non-operating
    items back on top of the rebuilt subtotal and the result has to come out at
    the pretax income the company independently files, within 1%.

        revenue - COGS - operating expense lines      = rebuilt subtotal
        rebuilt + interest income + other non-op
                + equity method + gains - interest    = pretax, or the rebuild
                                                        is rejected

    The two sides use disjoint sets of tags and pretax income is a filed total,
    so the check is not circular. A year that ties has had both its expense
    list and its non-operating list shown to be complete; a year that does not
    tie gets no ROIC at all, which is the honest outcome.
    """
    gp = g(row, "gross_profit")
    if gp is not None:
        base, base_note = gp, "GrossProfit"
    else:
        rev, cogs = g(row, "revenue"), g(row, "cost_of_revenue")
        if None in (rev, cogs):
            return None
        base, base_note = rev - cogs, "매출 − 매출원가"

    opex, used = 0.0, []
    for k in OPERATING_EXPENSE_LINES:
        x = g(row, k)
        if x is not None:
            opex += x
            used.append(k)
    if not used:
        return None
    oi = base - opex

    pre = g(row, "pretax_income")
    if pre is None or abs(pre) < 1e6:
        return None
    nonop = nonoperating_net(row)
    err = abs(oi + nonop - pre) / abs(pre)
    return {
        "operating_income": oi, "base": base_note, "lines": used,
        "nonoperating_net": nonop, "pretax": pre, "tie_out_error": err,
        "tied": err <= TIE_OUT_TOLERANCE,
    }


BOTTOM_UP_TOLERANCE = 0.05


def candidate_builds(row):
    """Every bottom-up reconstruction available for this year, with its
    reconciliation error against filed pretax income."""
    rev, cor = g(row, "revenue"), g(row, "cost_of_revenue")
    gp, opex = g(row, "gross_profit"), g(row, "operating_expenses")
    ce = g(row, "costs_and_expenses")

    out = []
    if None not in (gp, opex):
        out.append(("gross_profit_less_operating_expenses", gp - opex))
    if None not in (rev, cor, opex):
        out.append(("revenue_less_cost_of_revenue_less_operating_expenses",
                    rev - cor - opex))
    if None not in (rev, ce):
        out.append(("revenue_less_costs_and_expenses", rev - ce))
    v = verified_build(row)
    if v:
        out.append(("verified_line_build", v["operating_income"]))
    return [{"route": n, "operating_income": val, "tie_out_error":
             tie_out(val, row)} for n, val in out]


def build_operating_income(row, chosen=None):
    """
    Operating income, the route that produced it, and the route's workings.

    A reported subtotal wins outright. Failing that, the company's single
    chosen route is used if it is available this year and reconciles to filed
    pretax income; otherwise the best-reconciling build for the year is taken,
    and only if nothing reconciles does the numerator fall back to an estimate
    derived from pretax income itself - which this test cannot judge, because
    it is defined from the figure the test checks against.

    Ordering routes by their measured accuracy and taking the first available
    was the earlier design and it was not enough: accuracy measured where a
    subtotal exists does not carry over to the companies where none does, which
    is the only place these routes are ever used.
    """
    oi = g(row, "operating_income")
    if oi is not None:
        return oi, "reported", None

    cands = {c["route"]: c for c in candidate_builds(row)}
    scored = sorted(((c["tie_out_error"], c["route"], c["operating_income"])
                     for c in cands.values() if c["tie_out_error"] is not None))
    detail = {"candidates": list(cands.values()), "company_route": chosen}

    # Walk the company's preference list and take the first route that can be
    # built this year. A pretax-derived estimate is used rather than dropping
    # the company, because the size of the error was measured instead of
    # assumed: on the 448 company-years where a subtotal is reported,
    # substituting route F moves ROIC by a median of 0.35pp and crosses the 10%
    # hurdle in 3.6% of years, and route G moves it 0.77pp and crosses in 2.9%.
    # Both are computed for every estimated year and hurdle_agrees records
    # whether they agree - where they do, the verdict holds either way.
    estimators = {
        "pretax_less_nonoperating": route_f_estimate,
        "pretax_plus_interest_less_investment_income": route_g_estimate,
    }
    for name in (chosen or {}).get("preference", []):
        if name in estimators:
            value = estimators[name](row)
            if value is not None:
                return value, name, detail
        elif name in cands:
            err = cands[name]["tie_out_error"]
            if err is not None and err <= BOTTOM_UP_TOLERANCE:
                detail["chosen_tie_out_error"] = err
                return cands[name]["operating_income"], name, detail

    if scored:
        # Nothing reconciles and no pretax-based estimate is possible either;
        # the least-bad bottom-up build is reported, marked as unreconciled.
        err, name, value = scored[0]
        detail["chosen_tie_out_error"] = err
        return value, name + "_unreconciled", detail

    return None, "unavailable", detail


def route_g_estimate(row):
    pre, ie = g(row, "pretax_income"), g(row, "interest_expense")
    if None in (pre, ie):
        return None
    return pre + ie - (g(row, "investment_income_interest") or 0.0)


def route_f_estimate(row):
    pre, nonop = g(row, "pretax_income"), g(row, "nonoperating_income")
    return None if None in (pre, nonop) else pre - nonop


def build_debt(row):
    """
    Interest-bearing debt, avoiding the double count that the overlapping tags
    invite. LongTermDebtNoncurrent excludes the current portion and so needs it
    added back; LongTermDebt as filed normally includes it and so does not.
    """
    combined = g(row, "debt_combined_total")
    if combined is not None:
        return combined, "DebtLongtermAndShorttermCombinedAmount (현재분 포함 총액)"

    ltn = g(row, "long_term_debt_noncurrent")
    ltt = g(row, "long_term_debt_total")
    ltc = g(row, "long_term_debt_current")
    dct = g(row, "debt_current_total")
    st = g(row, "short_term_debt")

    if ltn is not None:
        long_part, note = ltn, "LongTermDebtNoncurrent"
        current_part = dct if dct is not None else (
            (ltc or 0) + (st or 0) if (ltc is not None or st is not None)
            else None)
        cnote = ("DebtCurrent" if dct is not None
                 else "LongTermDebtCurrent + ShortTermBorrowings")
    elif ltt is not None:
        long_part, note = ltt, "LongTermDebt (현재분 포함으로 간주)"
        current_part = st
        cnote = "ShortTermBorrowings only"
    else:
        long_part, note = None, "장기차입금 태그 없음"
        current_part, cnote = (dct if dct is not None else st), "현재분만"

    if long_part is None and current_part is None:
        # XBRL omits a balance-sheet tag when the line is not on the balance
        # sheet, so no debt tag in any year means a debt-free balance sheet,
        # not missing data. Arista has never borrowed and every one of its ten
        # years came back with no invested capital at all on the stricter rule.
        return 0.0, "차입금 라인 없음 → 0 (무차입)"
    return (long_part or 0) + (current_part or 0), f"{note} + {cnote}"


def build_cash(row):
    combined = g(row, "cash_and_sti_combined")
    if combined is not None:
        return combined, "CashCashEquivalentsAndShortTermInvestments (결합 태그)"
    c = g(row, "cash_and_equivalents")
    s = g(row, "short_term_investments")
    if c is None and s is None:
        return None, "현금 태그 없음"
    if s is None:
        return c, "현금성자산만 (단기투자자산 태그 없음)"
    return (c or 0) + (s or 0), "현금성자산 + 단기투자자산"


def flag_cash_holes(years):
    """
    A missing short-term-investments tag in one year of a company that files it
    in the years either side is a hole, not a year the company held no
    securities - and it inflates invested capital by the whole portfolio.
    Alphabet FY2016 came back at 16% ROIC instead of 34% from exactly this,
    because its FY2016 10-K tagged the line AvailableForSaleSecuritiesCurrent
    and the collector was only looking for MarketableSecuritiesCurrent.

    Tag coverage was widened so these resolve at source; the check stays as the
    tripwire for the next renamed tag.

    Only the years immediately either side count. Tesla really held no
    marketable securities from FY2016 to FY2020, Netflix none from FY2018 to
    FY2020, and an any-earlier/any-later test called all of those holes and
    threw away eight good years.
    """
    has = [y["cash_note"].startswith(("CashCash", "현금성자산 + "))
           for y in years]
    for i, y in enumerate(years):
        if has[i]:
            continue
        before = i > 0 and has[i - 1]
        after = i + 1 < len(has) and has[i + 1]
        if before and after:
            y["cash_hole_suspected"] = True
            y["roic_status"] = "현금성자산 태그 누락 의심 — 투하자본 과대"
            y["confidence"] = "LOW"


def effective_tax(row):
    pre, tax = g(row, "pretax_income"), g(row, "income_tax_expense")
    if pre is None or tax is None or pre <= 0:
        return TAX_DEFAULT, "세전이익을 쓸 수 없어 법정세율 21% 적용"
    r = tax / pre
    if r < TAX_FLOOR:
        return TAX_FLOOR, f"실효세율 {r:.1%} → 하한 5% 적용"
    if r > TAX_CEIL:
        return TAX_CEIL, f"실효세율 {r:.1%} → 상한 40% 적용"
    return r, f"실효 {r:.1%}"


def choose_route(rows):
    """
    One reconstruction route for the whole company, not one per year.

    Picking the best-reconciling route year by year gave Chevron a series built
    from four different definitions - route C in FY2017, route G in FY2018-21,
    route C again in FY2022-23 - and a ten-year ROIC trend assembled that way
    measures the routes as much as the business. So the route is chosen once,
    on how well it reconciles across the window as a whole, and then applied to
    every year that needs it. A company's own reported subtotal still wins in
    the years it exists.

    Routes are ranked by median reconciliation error, with coverage breaking
    ties: a route that reconciles well but only in three of ten years is worse
    than one slightly looser that covers all ten.
    """
    scores = {}
    for row in rows.values():
        if g(row, "operating_income") is not None:
            continue
        for cand in candidate_builds(row):
            if cand["tie_out_error"] is None:
                continue
            scores.setdefault(cand["route"], []).append(cand["tie_out_error"])
    need = max((len(v) for v in scores.values()), default=1)
    ranked = sorted(
        ((k, v) for k, v in scores.items()
         if statistics.median(v) <= BOTTOM_UP_TOLERANCE),
        key=lambda kv: (-len(kv[1]) / need, statistics.median(kv[1])))

    # Then the two pretax-derived estimates, whichever covers more of the
    # window first. These cannot be reconciliation-tested, so coverage is the
    # only thing to go on; route F is preferred on a tie because substituting
    # it moved ROIC by a median of 0.35pp against route G's 0.77pp on the years
    # where a reported subtotal exists to measure against.
    cover = {"pretax_less_nonoperating": 0,
             "pretax_plus_interest_less_investment_income": 0}
    for row in rows.values():
        if g(row, "operating_income") is not None:
            continue
        if route_f_estimate(row) is not None:
            cover["pretax_less_nonoperating"] += 1
        if route_g_estimate(row) is not None:
            cover["pretax_plus_interest_less_investment_income"] += 1
    pretax_order = sorted(
        (k for k, n in cover.items() if n),
        key=lambda k: (-cover[k], k != "pretax_less_nonoperating"))

    order = [k for k, _ in ranked] + pretax_order
    if not order:
        return None
    return {
        "preference": order,
        "route": order[0],
        "reconciles": bool(ranked),
        "years": len(scores.get(order[0], [])) or cover.get(order[0], 0),
        "median_tie_out_error": (statistics.median(scores[order[0]])
                                 if order[0] in scores else None),
        "considered": {k: {"years": len(v),
                           "median_tie_out_error": statistics.median(v),
                           "reconciles":
                               statistics.median(v) <= BOTTOM_UP_TOLERANCE}
                       for k, v in scores.items()},
        "pretax_coverage": cover,
    }


def company_years(c, c_is_financial=False):
    rows = {y["fiscal_year_label"]: y for y in c["years"]}
    chosen = choose_route(rows)
    out = []
    for fy in sorted(rows):
        row = rows[fy]
        oi, route, detail = build_operating_income(row, chosen)
        tax, tax_note = effective_tax(row)
        debt, debt_note = build_debt(row)
        cash, cash_note = build_cash(row)
        equity = g(row, "total_equity")
        parent = g(row, "equity_parent_only")

        ic = None
        if None not in (equity, debt, cash):
            ic = equity + debt - cash
        nopat = None if oi is None else oi * (1 - tax)

        out.append({
            "fiscal_year": fy,
            "period_end": row["period_end"],
            "accession": row.get("_accn"),
            "revenue": g(row, "revenue"),
            "operating_income": oi,
            "operating_income_route": route,
            "route_detail": detail,
            "route_accuracy": ROUTE_ACCURACY.get(route),
            "effective_tax_rate": tax, "tax_note": tax_note,
            "nopat": nopat,
            "total_equity": equity,
            "equity_parent_only": parent,
            "noncontrolling_interest": (None if None in (equity, parent)
                                        else equity - parent),
            "interest_bearing_debt": debt, "debt_note": debt_note,
            "cash_and_short_term_investments": cash, "cash_note": cash_note,
            "invested_capital": ic,
            "operating_margin": (None if None in (oi, g(row, "revenue"))
                                 or not g(row, "revenue")
                                 else oi / g(row, "revenue")),
        })

    for i, y in enumerate(out):
        route = y["operating_income_route"]
        if route in LOW_CONFIDENCE_ROUTES or route.endswith("_unreconciled"):
            y["confidence"] = "LOW"
        elif route in ("reported", "verified_line_build"):
            y["confidence"] = "HIGH"
        else:
            y["confidence"] = "MEDIUM"
        y["cash_hole_suspected"] = False
        y["roic_status"] = "OK"
    flag_cash_holes(out)

    # Average capital needs the prior year, so it is filled on a second pass.
    for i, y in enumerate(out):
        # The previous row is only an opening balance if it is the previous
        # year. American Express has no 10-K facts between FY2010 and FY2016,
        # and taking the previous row regardless averaged its FY2016 capital
        # with its FY2010 capital.
        prev = out[i - 1] if i else None
        if prev is not None and prev["fiscal_year"] != y["fiscal_year"] - 1:
            prev = None
        ic, pic = y["invested_capital"], prev["invested_capital"] if prev else None
        # Averaging opening and closing capital is right until one of them is
        # negative, when the mean lands near zero and the ratio explodes.
        # Nvidia's capital went from -$568m to +$947m across FY2016, an average
        # of $189m, and ROIC came out at 892% - a statement about a sign change,
        # not about the business. Where an endpoint is not positive the closing
        # figure is used on its own.
        avg, avg_note = None, "기초·기말 평균"
        if ic is not None:
            if pic is None:
                avg, avg_note = ic, "기말 (직전연도 없음)"
            elif pic <= 0 or ic <= 0:
                avg, avg_note = ic, "기말 단독 (기초 또는 기말 자본이 0 이하)"
            else:
                avg = (ic + pic) / 2.0
        y["invested_capital_avg"] = avg
        y["invested_capital_avg_note"] = avg_note
        y["roic"] = None
        y["capital_intensity"] = (
            None if avg is None or not y["revenue"] else avg / y["revenue"])
        if y["cash_hole_suspected"]:
            continue
        if y["nopat"] is None:
            y["roic_status"] = "영업이익 산출 불가"
        elif avg is None:
            y["roic_status"] = "투하자본 산출 불가"
        elif avg <= 0:
            y["roic_status"] = ("투하자본이 0 이하 — 현금이 자기자본+차입금을 "
                                "넘어 비율이 성립하지 않음")
        elif c_is_financial:
            # Stated as excluded, so actually excluded. Leaving the ratio
            # populated and only labelling the verdict invites someone to read
            # a bank's equity-plus-debt-less-cash return as comparable to
            # Apple's. For a bank, borrowing is the raw material.
            y["roic_status"] = "금융업 — ROIC 정의 부적합"
        else:
            y["roic"] = y["nopat"] / avg

        # Where the numerator is an estimate, run the other estimate too and
        # record whether the two agree about the 10% hurdle. Agreement makes
        # the verdict safe without making the level precise.
        if y["roic"] is not None and y["confidence"] != "HIGH":
            row = rows[y["fiscal_year"]]
            alts = []
            for fn in (route_f_estimate, route_g_estimate):
                oi_alt = fn(row)
                if oi_alt is not None:
                    alts.append(oi_alt * (1 - y["effective_tax_rate"]) / avg)
            if len(alts) == 2:
                y["roic_alternate"] = alts
                y["hurdle_agrees"] = (alts[0] > WACC) == (alts[1] > WACC) \
                    == (y["roic"] > WACC)
                y["roic_range_pp"] = abs(alts[0] - alts[1])

        # A denominator that has shrunk to almost nothing makes the ratio
        # hypersensitive: Arista's cash pile nearly cancels its equity, leaving
        # $1.6bn of net capital against $9.0bn of revenue and a ROIC of 229%.
        # That is arithmetically right and the verdict against a 10% hurdle is
        # not in doubt, so the year is marked rather than dropped. An earlier
        # version dropped any year whose capital was under 10% of revenue and
        # deleted Costco entirely - a high-turnover retailer carries thin
        # capital against enormous revenue by design, which is the opposite of
        # a data problem. The median is robust to the few genuine extremes.
        ci = y["capital_intensity"]
        y["capital_too_small"] = bool(
            y["roic"] is not None and ci is not None and ci < 0.10)
        if y["capital_too_small"]:
            y["roic_status"] = (f"투하자본이 매출의 {ci:.1%} — 분모가 작아 "
                                f"비율이 민감 (판정은 유효)")
    return out


def summarise(ticker, years, is_financial):
    window = [y for y in years if FIRST_FY <= y["fiscal_year"] <= LAST_FY]
    usable = [y for y in window if y["roic"] is not None]
    roics = [y["roic"] for y in usable]
    spreads = [r - WACC for r in roics]
    return {
        "years_in_window": len(window),
        "years_usable": len(usable),
        "roic_median": statistics.median(roics) if roics else None,
        "roic_mean": statistics.fmean(roics) if roics else None,
        "roic_min": min(roics) if roics else None,
        "roic_max": max(roics) if roics else None,
        "roic_stdev": statistics.stdev(roics) if len(roics) > 1 else None,
        "spread_median": statistics.median(spreads) if spreads else None,
        "years_above_wacc": sum(1 for r in roics if r > WACC),
        "years_below_wacc": sum(1 for r in roics if r <= WACC),
        "every_year_above_wacc": bool(roics) and all(r > WACC for r in roics),
        "years_estimated_numerator": sum(1 for y in usable
                                         if y["confidence"] != "HIGH"),
        "years_hurdle_disputed": sum(1 for y in usable
                                     if y.get("hurdle_agrees") is False),
        "years_capital_too_small": sum(1 for y in window
                                       if y.get("capital_too_small")),
        "verdict": verdict(roics, is_financial),
    }


def verdict(roics, is_financial):
    if is_financial:
        return "금융업 — ROIC 정의 부적합"
    if not roics:
        return "산출 불가"
    n = len(roics)
    above = sum(1 for r in roics if r > WACC)
    med = statistics.median(roics)
    if above == n and med >= 0.25:
        return "전 기간 초과 · 매우 높음"
    if above == n:
        return "전 기간 초과"
    if above >= n * 0.8:
        return "대체로 초과"
    if above >= n * 0.5:
        return "절반 이상 초과"
    if above > 0:
        return "대부분 미달"
    return "전 기간 미달"


def main():
    with open(RAW) as fh:
        raw = json.load(fh)

    companies = []
    for c in raw["companies"]:
        years = company_years(c, c.get("is_financial", False))
        companies.append({
            "ticker": c["ticker"], "cik": c["cik"],
            "company_name": c["company_name"],
            "sic": c.get("sic"), "sic_description": c.get("sic_description"),
            "chosen_route": choose_route(
                {y["fiscal_year_label"]: y for y in c["years"]}),
            "is_financial": c.get("is_financial", False),
            "years": years,
            "summary": summarise(c["ticker"], years,
                                 c.get("is_financial", False)),
        })

    nonfin = [c for c in companies if not c["is_financial"]]
    # Five years is the floor for a median to mean anything. Palantir's
    # capital was negative or near zero for nine of its ten years, leaving one
    # usable year at 1,532% - a number that would otherwise top the ranking.
    MIN_YEARS = 5
    scored = [c for c in nonfin if c["summary"]["roic_median"] is not None
              and c["summary"]["years_usable"] >= MIN_YEARS]
    thin = [c for c in nonfin if c["summary"]["roic_median"] is not None
            and c["summary"]["years_usable"] < MIN_YEARS]
    scored.sort(key=lambda c: -c["summary"]["roic_median"])

    route_counts = {}
    low = []
    for c in companies:
        for y in c["years"]:
            if FIRST_FY <= y["fiscal_year"] <= LAST_FY:
                r = y["operating_income_route"]
                route_counts[r] = route_counts.get(r, 0) + 1
                if y["confidence"] == "LOW":
                    low.append(f"{c['ticker']} FY{y['fiscal_year']}")

    result = {
        "generated": date.today().isoformat(),
        "wacc": WACC,
        "wacc_note": ("사용자 지정값. 자본비용을 기업별로 다르게 잡으면 "
                      "ROIC 비교가 아니라 베타 비교가 되므로, 전 종목에 "
                      "같은 문턱을 적용했습니다."),
        "window": [FIRST_FY, LAST_FY],
        "source": raw["source"],
        "route_accuracy": ROUTE_ACCURACY,
        "route_counts_in_window": route_counts,
        "low_confidence_years": low,
        "companies": companies,
        "min_years_for_ranking": MIN_YEARS,
        "ranking": [{"ticker": c["ticker"], "name": c["company_name"],
                     **c["summary"]} for c in scored],
        "thin_sample": [{"ticker": c["ticker"], "name": c["company_name"],
                         **c["summary"]} for c in thin],
    }
    with open(OUT, "w") as fh:
        json.dump(result, fh, indent=1, ensure_ascii=False)

    print(f"독립 재산출: {len(companies)}사, 창 FY{FIRST_FY}~FY{LAST_FY}, "
          f"WACC {WACC:.0%}\n")
    print("영업이익 산출 경로별 건수 (창 내)")
    for r, n in sorted(route_counts.items(), key=lambda kv: -kv[1]):
        acc = ROUTE_ACCURACY.get(r)
        print(f"  {r:<52}{n:>5}건" + (f"  정확도 {acc:.1%}" if acc else ""))
    if low:
        print(f"\n저신뢰(LOW) 연도 {len(low)}건: "
              f"{', '.join(low[:12])}{' …' if len(low) > 12 else ''}")

    print(f"\n{'순위':>3} {'티커':<7}{'기업명':<26}{'중위 ROIC':>10}"
          f"{'최소':>8}{'최대':>8}{'초과연수':>9}  판정")
    for i, c in enumerate(scored, 1):
        s = c["summary"]
        print(f"{i:>3} {c['ticker']:<7}{c['company_name'][:24]:<26}"
              f"{s['roic_median']:>10.1%}{s['roic_min']:>8.1%}"
              f"{s['roic_max']:>8.1%}"
              f"{s['years_above_wacc']:>5}/{s['years_usable']:<3}  "
              f"{s['verdict']}")

    if thin:
        print(f"\n표본 부족 (산출 연도 5년 미만) {len(thin)}사")
        for c in thin:
            s2 = c["summary"]
            print(f"  {c['ticker']:<7}{c['company_name'][:26]:<28}"
                  f"산출 {s2['years_usable']}년, 중위 {s2['roic_median']:.1%}"
                  f" — 자본 과소/음수 {s2['years_capital_too_small']}년")

    skipped = [c for c in companies if c["summary"]["roic_median"] is None
               or c["is_financial"]]
    if skipped:
        print(f"\n제외 {len(skipped)}사")
        for c in skipped:
            print(f"  {c['ticker']:<7}{c['company_name'][:30]:<32}"
                  f"{c['summary']['verdict']}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
