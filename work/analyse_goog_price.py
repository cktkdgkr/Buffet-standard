"""
Alphabet at the price it fell to, measured against this project's criteria.

On 28 October 2026 Alphabet released its third quarter and the shares fell
12.6% the next day, from $321.89 to $281.23 - the largest single-day move in six
months and a new 52-week low. The quarter itself looks strong on the lines a
headline quotes: revenue up 25%, Cloud up 103%, operating income up 30%,
operating margin 32%. Two other lines explain the reaction, and both are in the
release.

Reported net income fell to $26.2bn from $35.0bn and EPS to $2.12 from $2.87,
because other income swung from a $12.8bn gain to an $8.2bn loss. That is
mark-to-market on equity investments under ASU 2016-01, which this project's
earlier audit already established has to come out of owner earnings - it is not
the operating business getting worse.

Free cash flow is the one that matters. Capital expenditure reached $51.4bn in
the quarter against $42.3bn of operating cash flow, so free cash flow was
negative $9.1bn, after negative $5.9bn the quarter before. Two consecutive
quarters of negative free cash flow at a company that earned $24.6bn of it as
recently as Q4 2025.

That is precisely what the ROIC framework here measures: capital going in
faster than earnings are coming out. So the question is not whether the price
fell but whether, at this price, the business clears the 10% hurdle and the
Buffett criteria.

Writes work/goog/goog_price.json.

    python3 analyse_goog_price.py
    python3 analyse_goog_price.py --refresh
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sec_cache                                               # noqa: E402
from collect_spx_tsla import (find_row, get_report, pick,      # noqa: E402
                              report_map)

CIK = 1652044
CACHE = os.path.join(HERE, "goog", "cache")
OUT = os.path.join(HERE, "goog", "goog_price.json")
MM, BN = 1e6, 1e9
WACC = 0.10
UA_WEB = "Mozilla/5.0 (compatible; portfolio-research/1.0)"


def latest(forms, refresh):
    sub, _, _ = sec_cache.submissions(CIK, CACHE, refresh=refresh,
                                      max_age_days=1.0)
    r = sub["filings"]["recent"]
    out = []
    for f, d, rd, acc, doc in zip(
            r["form"], r["filingDate"],
            r.get("reportDate", [""] * len(r["form"])),
            r["accessionNumber"],
            r.get("primaryDocument", [""] * len(r["form"]))):
        if f in forms:
            out.append({"form": f, "filed": d, "period_end": rd,
                        "accession": acc, "primary_document": doc})
    return sub, out


def price_history(ticker, rng="6mo"):
    """Closes for the last six months, so the fall can be dated rather than
    described."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?range={rng}&interval=1d")
    raw = subprocess.run(["curl", "-sS", "--fail", "-A", UA_WEB, url],
                         capture_output=True, check=True).stdout
    d = json.loads(raw)["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    rows = [{"date": datetime.fromtimestamp(t, tz=timezone.utc)
             .date().isoformat(), "close": c, "volume": v}
            for t, c, v in zip(d["timestamp"], q["close"], q["volume"]) if c]
    closes = [r["close"] for r in rows]
    hi = max(rows, key=lambda r: r["close"])
    lo = min(rows, key=lambda r: r["close"])
    moves = []
    for i in range(1, len(rows)):
        ch = rows[i]["close"] / rows[i - 1]["close"] - 1
        if abs(ch) >= 0.04:
            moves.append({"date": rows[i]["date"], "change": ch,
                          "from": rows[i - 1]["close"],
                          "to": rows[i]["close"],
                          "volume": rows[i]["volume"]})
    meta = d["meta"]
    return {
        "ticker": ticker, "first": rows[0], "last": rows[-1],
        "high": hi, "low": lo,
        "from_high": rows[-1]["close"] / hi["close"] - 1,
        "fifty_two_week_high": meta.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": meta.get("fiftyTwoWeekLow"),
        "big_moves": moves,
        "recent": rows[-12:],
        "source_url": url,
    }


def release_numbers(acc, refresh):
    """
    The quarterly free-cash-flow table out of the earnings release.

    It is in the 8-K's exhibit as running prose and a table, not as tagged
    XBRL, so the figures are read out of the text. Every one of them is
    checked against the quarterly cash-flow statement in the 10-Q, which is
    tagged - so a misread here fails rather than propagates.
    """
    base = (f"https://www.sec.gov/Archives/edgar/data/{CIK}/"
            f"{acc.replace('-', '')}")
    d, _, _ = sec_cache.fetch_json(
        base + "/index.json", os.path.join(CACHE, f"{acc}_index.json"),
        max_age_days=365, refresh=refresh)
    exhibit = next((x["name"] for x in d["directory"]["item"]
                    if "exhibit" in x["name"].lower()
                    and x["name"].endswith(".htm")), None)
    if not exhibit:
        return None
    p, _, _ = sec_cache.fetch(f"{base}/{exhibit}",
                              os.path.join(CACHE, f"{acc}_ex99.htm"),
                              max_age_days=365, refresh=refresh,
                              min_bytes=10000)
    import html as _h
    txt = re.sub(r"\s+", " ", _h.unescape(
        re.sub(r"<[^>]+>", " ", open(p, errors="ignore").read())))

    # Parse inside the reconciliation table only. Searching the whole document
    # for "Net cash provided by operating activities" found the phrase in the
    # cash-flow statement further down and returned that section's figures, so
    # the row disagreed with the capex and free-cash-flow rows beside it. The
    # tie-out below is what caught it.
    # The heading appears twice: once in prose near the top as a forward
    # reference ("...included at the end of this release") and once over the
    # table itself. Taking the first match put the window 10,000 characters
    # early, over the balance sheet, and the row labels were not in it. The
    # right occurrence is the one the data rows follow.
    header = ("Reconciliation from GAAP Net Cash Provided by "
              "Operating Activities")
    window = None
    for m in re.finditer(re.escape(header), txt):
        candidate = txt[m.start():m.start() + 1600]
        if "Less: purchases of property and equipment" in candidate:
            window = candidate
            break
    if window is None:
        window = txt

    def grab(label, count):
        m = re.search(re.escape(label)
                      + r"((?:\s*\$?\s*\(?-?[\d,]+\)?){%d})" % count,
                      window)
        if not m:
            return None
        nums = re.findall(r"\(?-?[\d,]+\)?", m.group(1))
        out = []
        for n in nums[:count]:
            neg = n.startswith("(")
            v = float(n.strip("()").replace(",", "")) * MM
            out.append(-v if neg else v)
        return out

    ocf = grab("Net cash provided by operating activities", 5)
    capex = grab("Less: purchases of property and equipment", 5)
    fcf = grab("Free cash flow", 5)

    # Free cash flow is operating cash flow less capital expenditure, by the
    # company's own definition printed beneath the table. If the three rows do
    # not satisfy that, at least one of them was read from the wrong place.
    if ocf and capex and fcf:
        for i, (o, k, f) in enumerate(zip(ocf, capex, fcf)):
            if abs((o + k) - f) > max(abs(f) * 1e-6, 1e6):
                raise SystemExit(
                    f"발표문 현금흐름 표 파싱 오류: {i}번째 열에서 "
                    f"{o/MM:,.0f} + {k/MM:,.0f} != {f/MM:,.0f}")
    # Segment revenue and operating income, from the supplemental tables. Each
    # row carries the prior-year quarter then the current one, so two numbers
    # per label.
    #
    # Each table needs its own window. "Google Cloud" is a row in both, and
    # only the first row of each block prints the "$", so a document-wide
    # search for the segment's operating income returned its revenue instead -
    # $30,709m of Cloud revenue reported as Cloud operating income. The two
    # sums below are what makes that fail rather than pass: the components of
    # each table have to add up to the consolidated total already anchored
    # against the 10-Q.
    def window_between(start, end, tail=60):
        """
        The slice from `start` through `end`, plus a tail.

        The tail matters: the window has to reach past the closing label to
        the figures that follow it, or the total row parses as missing and the
        sum check below cannot run.
        """
        a = txt.find(start)
        if a < 0:
            return None
        b = txt.find(end, a + len(start))
        return txt[a:b + len(end) + tail] if b > 0 else txt[a:]

    def pair(where, label, scale=MM):
        if where is None:
            return None
        m = re.search(re.escape(label)
                      + r"\s*\$?\s*(\(?-?[\d,]+\)?)\s*\$?\s*(\(?-?[\d,]+\)?)",
                      where)
        if not m:
            return None
        out = []
        for n in m.group(1, 2):
            neg = n.startswith("(")
            v = float(n.strip("()").replace(",", "")) * scale
            out.append(-v if neg else v)
        return {"q3_2025": out[0], "q3_2026": out[1]}

    rev_win = window_between("Google Search & other", "Number of employees")
    oi_win = window_between("Operating income (loss):",
                            "Total income from operations")

    seg_revenue = {k: pair(rev_win, lbl) for k, lbl in (
        ("search", "Google Search & other"),
        ("youtube_ads", "YouTube ads"),
        ("network", "Google Network"),
        ("advertising", "Google advertising"),
        ("subscriptions_devices",
         "Google subscriptions, platforms, and devices"),
        ("services_total", "Google Services total"),
        ("cloud", "Google Cloud"),
        ("other_bets", "Other Bets"),
        ("hedging", "Hedging gains (losses)"),
        ("total", "Total revenues"),
    )}
    seg_income = {k: pair(oi_win, lbl) for k, lbl in (
        ("services", "Google Services"),
        ("cloud", "Google Cloud"),
        ("other_bets", "Other Bets"),
        ("alphabet_level", "Alphabet-level activities (1)"),
        ("total", "Total income from operations"),
    )}
    # Employees are people, not dollars. The table is headed "$ in millions"
    # like everything else here, and multiplying 204,757 staff by a million is
    # exactly the class of error that turned 13.6bn shares into 1.4e16 once.
    employees = pair(rev_win, "Number of employees", scale=1)

    for name, block, parts in (
            ("매출", seg_revenue,
             ("services_total", "cloud", "other_bets", "hedging")),
            ("영업이익", seg_income,
             ("services", "cloud", "other_bets", "alphabet_level"))):
        total = block.get("total")
        if not total or any(block.get(k) is None for k in parts):
            raise SystemExit(
                f"발표문 사업부 {name} 표 파싱 오류: 누락 "
                f"{[k for k in parts + ('total',) if not block.get(k)]}")
        for q in ("q3_2025", "q3_2026"):
            got = sum(block[k][q] for k in parts)
            if abs(got - total[q]) > 1e6:
                raise SystemExit(
                    f"발표문 사업부 {name} 합계 불일치 {q}: "
                    f"{got / MM:,.0f} != {total[q] / MM:,.0f}")

    segments = {"revenue": seg_revenue, "operating_income": seg_income,
                "employees": employees}

    cols = ["Q4 2025", "Q1 2026", "Q2 2026", "Q3 2026", "TTM Q3 2026"]
    table = None
    if ocf and capex and fcf:
        table = [{"period": c, "operating_cash_flow": o,
                  "capex": k, "free_cash_flow": f}
                 for c, o, k, f in zip(cols, ocf, capex, fcf)]
    return {"exhibit_url": f"{base}/{exhibit}", "cash_flow": table,
            "segments": segments,
            "headline": {
                "revenue_q3_2026": 127_577 * MM,
                "revenue_q3_2025": 102_346 * MM,
                "operating_income_q3_2026": 40_576 * MM,
                "operating_income_q3_2025": 31_228 * MM,
                "other_income_q3_2026": -8_221 * MM,
                "other_income_q3_2025": 12_759 * MM,
                "net_income_q3_2026": 26_170 * MM,
                "net_income_q3_2025": 34_979 * MM,
                "eps_q3_2026": 2.12, "eps_q3_2025": 2.87,
                "cloud_revenue_q3_2026": 30_700 * MM,
            }}


def quarter_financials(acc, refresh):
    """Balance sheet, income statement and the PP&E note from the 10-Q."""
    base, reports = report_map(CIK, acc, refresh)
    got = {}
    for key, keywords in (
            ("balance_sheet", ("Consolidated Balance Sheets",)),
            ("operations", ("Consolidated Statements of Income",)),
            ("cash_flows", ("Consolidated Statements of Cash Flows",)),
            ("ppe", ("Property", "Details")),
            ("revenue", ("Disaggregat", "Details")),
            ("segments", ("Segment", "Details")),
    ):
        short, fn = pick(reports, *keywords)
        got[key] = get_report(base, CIK, acc, fn, refresh) if fn else None
        if got[key]:
            got[key]["short_name"] = short
            got[key]["source_url"] = f"{base}/{fn}"
    return got


def ten_year_record():
    """
    Alphabet's own ten years of ROIC, out of the fifty-company study.

    The price question is "is 29% on reported capital good enough at this
    price", and that cannot be judged against one trailing figure. The record
    also carries the fact that matters most here: ROIC peaked at 58.0% in
    FY2021 and has fallen every period since, not because operating income
    stopped growing but because invested capital grew faster.
    """
    path = os.path.join(HERE, "roic", "roic.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        study = json.load(fh)
    me = next((c for c in study["companies"]
               if c["ticker"] in ("GOOG", "GOOGL")), None)
    if not me:
        return None
    lo, hi = study["window"]
    years = [{"fiscal_year": y["fiscal_year"], "roic": y.get("roic"),
              "operating_income": y.get("operating_income"),
              "invested_capital_avg": y.get("invested_capital_avg")}
             for y in me["years"] if lo <= y["fiscal_year"] <= hi]
    return {"source": "roic/roic.json (미국 50개사 조사)",
            "generated": study["generated"], "window": study["window"],
            "wacc": study["wacc"], "summary": me["summary"],
            "ticker": me["ticker"], "company_name": me["company_name"],
            "years": years}


def ratios(fin, release, price, shares, fy2025, record=None):
    """
    ROIC on the three denominators, and what the price implies.

    Trailing twelve months, because a quarter of a business adding $50bn of
    plant is not a quarter of a year. TTM operating income is the last full
    year plus the nine months to September less the same nine months a year
    earlier.

    The tax rate is the issue here. Alphabet's nine-month pretax income carries
    $127.5bn of other income - mark-to-market on its non-marketable securities
    under ASU 2016-01 - so the effective rate computed from it is a rate on
    investment gains as much as on operations. Both are reported: the TTM rate
    as the engine's rule produces it, and FY2025's rate, which is the last one
    struck on a year whose pretax income was mostly operating.
    """
    bs, ops, ppe = fin["balance_sheet"], fin["operations"], fin["ppe"]

    def b(element, i):
        r = find_row(bs, element=element)
        return r["values"][i] if r else None

    def o(element, i):
        r = find_row(ops, element=element)
        return r["values"][i] if r else None

    def pp(context, i):
        r = find_row(ppe, context=context, patterns_required=False)
        return r["values"][i] if r else None

    SEP, DEC = 0, 1
    Q3_26, Q3_25, NM_26, NM_25 = 0, 1, 2, 3

    oi_9m_26 = o("OperatingIncomeLoss", NM_26)
    oi_9m_25 = o("OperatingIncomeLoss", NM_25)
    oi_ttm = fy2025["operating_income"] - oi_9m_25 + oi_9m_26

    # The name cf is reused further down for the release's cash-flow table, so
    # the 10-Q statement keeps its own name. Shadowing it once cost an hour.
    cf_table = fin.get("cash_flows")

    def c(element, i):
        r = find_row(cf_table, element=element)
        return r["values"][i] if r else None

    tax_9m_26 = o("IncomeTaxExpenseBenefit", NM_26)
    pre_9m_26 = o("IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
                  "ExtraordinaryItemsNoncontrollingInterest", NM_26)
    tax_ttm_rate = (tax_9m_26 / pre_9m_26) if pre_9m_26 else None

    sheets = {}
    for label, i in (("2026-09-30", SEP), ("2025-12-31", DEC)):
        equity = b("StockholdersEquity", i)
        debt = b("LongTermDebtNoncurrent", i)
        cash = b("CashCashEquivalentsAndShortTermInvestments", i)
        goodwill = b("Goodwill", i)
        intangibles = b("IntangibleAssetsNetExcludingGoodwill", i)
        not_in_service = pp("Assets not yet in service", i)
        # Non-marketable securities are Alphabet's stakes in other companies.
        # The project's standard definition subtracts cash and marketable
        # securities only, so these stay in the denominator - conservative,
        # and the same rule every other company is measured on. They matter
        # more here than anywhere else: $135bn at September 2026, a quarter of
        # invested capital, and they produce no operating income. Reported as
        # a fourth view rather than folded into the headline.
        non_marketable = b("OtherLongTermInvestments", i)
        base = equity + debt - cash
        operating = base - goodwill - intangibles
        sheets[label] = {
            "non_marketable_securities": non_marketable,
            "equity": equity, "debt": debt, "cash_and_securities": cash,
            "goodwill": goodwill, "intangibles": intangibles,
            "assets_not_yet_in_service": not_in_service,
            "ppe_net": b("PropertyPlantAndEquipmentAndFinanceLease"
                         "ArrangementsBeforeAccumulatedDepreciationAnd"
                         "AmortizationNet", i) or pp(None, i),
            "total_assets": b("Assets", i),
            "reported": base, "operating": operating,
            "in_service": operating - not_in_service,
            "in_service_ex_stakes": operating - not_in_service
            - (non_marketable or 0),
        }

    views = {}
    for name in ("reported", "operating", "in_service",
                 "in_service_ex_stakes"):
        o_, c_ = sheets["2025-12-31"][name], sheets["2026-09-30"][name]
        avg = (o_ + c_) / 2.0
        views[name] = {"opening": o_, "closing": c_, "average": avg}

    out = {"operating_income_ttm": oi_ttm,
           "depreciation_9m_2026": c("Depreciation", 0),
           "depreciation_9m_2025": c("Depreciation", 1),
           "share_based_comp_9m_2026": c("ShareBasedCompensation", 0),
           "securities_gain_9m_2026": c(
               "GainLossOnInvestments", 0),
           "operating_income_9m_2026": oi_9m_26,
           "operating_income_9m_2025": oi_9m_25,
           "revenue_9m_2026": o("Revenues", NM_26),
           "revenue_9m_2025": o("Revenues", NM_25),
           "other_income_9m_2026": o("NonoperatingIncomeExpense", NM_26),
           "other_income_9m_2025": o("NonoperatingIncomeExpense", NM_25),
           # The nine-month lines, so the report never carries a figure of its
           # own. Quarterly net income is a mark-to-market number here, and the
           # nine-month view is what shows that: the same company reads as a
           # 26% fall for the quarter and a doubling for the nine months.
           "pretax_9m_2026": pre_9m_26,
           "pretax_9m_2025": o("IncomeLossFromContinuingOperationsBefore"
                               "IncomeTaxesExtraordinaryItems"
                               "NoncontrollingInterest", NM_25),
           "tax_9m_2026": tax_9m_26,
           "net_income_9m_2026": o("NetIncomeLoss", NM_26),
           "net_income_9m_2025": o("NetIncomeLoss", NM_25),
           "eps_diluted_9m_2026": o("EarningsPerShareDiluted", NM_26),
           "eps_diluted_9m_2025": o("EarningsPerShareDiluted", NM_25),
           "preferred_dividends_9m_2026": o(
               "PreferredStockDividendsIncomeStatementImpact", NM_26),
           "tax_rate_ttm": tax_ttm_rate,
           "tax_rate_fy2025": fy2025["effective_tax_rate"],
           "balance_sheets": sheets, "views": views,
           "shares_outstanding": shares, "price": price,
           "market_cap": price * shares}

    for key, rate in (("ttm", tax_ttm_rate),
                      ("fy2025", fy2025["effective_tax_rate"])):
        nopat = oi_ttm * (1 - rate)
        out[f"nopat_{key}"] = nopat
        for name, v in views.items():
            v[f"roic_{key}"] = nopat / v["average"]
            v[f"spread_{key}"] = nopat / v["average"] - WACC

    # Free cash flow, from the release, and what it is once the capital that
    # is not yet earning is set aside.
    by_period = {r["period"]: r for r in (release["cash_flow"] or [])}
    ttm = by_period.get("TTM Q3 2026")
    if ttm:
        out["free_cash_flow_ttm"] = ttm["free_cash_flow"]
        out["operating_cash_flow_ttm"] = ttm["operating_cash_flow"]
        out["capex_ttm"] = ttm["capex"]
        growth_in_capital = (sheets["2026-09-30"]["assets_not_yet_in_service"]
                             - sheets["2025-12-31"]["assets_not_yet_in_service"])
        out["increase_in_assets_not_yet_in_service"] = growth_in_capital
        # Capital expenditure that went into assets still under construction is
        # not a cost of this year's earnings - it is next year's capacity.
        out["free_cash_flow_before_new_construction"] = (
            ttm["free_cash_flow"] + growth_in_capital)

    # What the price needs. Two readings, neither a forecast: the return on
    # today's earnings with no growth, and the growth a 10% return would
    # require given how much of each incremental dollar has to be reinvested.
    nopat = out["nopat_ttm"]
    mc = out["market_cap"]
    out["nopat_yield"] = nopat / mc
    out["nopat_required_for_10pct"] = mc * WACC
    out["multiple_of_current_nopat"] = (mc * WACC) / nopat
    out["price_to_nopat"] = mc / nopat
    out["price_to_fcf_ttm"] = (mc / out["free_cash_flow_ttm"]
                               if out.get("free_cash_flow_ttm") else None)

    # Owner earnings, as a band rather than a point, exactly as the earlier
    # study framed it: the lower bound charges the whole capital budget
    # against this year's earnings, the upper bound charges only depreciation,
    # and the truth is between them. The gap is unusually wide right now
    # because $145bn of plant is not yet in service - capital already spent
    # that cannot yet earn, and that depreciation does not yet reflect.
    dep_ttm = (fy2025["depreciation"] - out["depreciation_9m_2025"]
               + out["depreciation_9m_2026"]) if fy2025.get("depreciation") \
        else None
    if dep_ttm and out.get("operating_cash_flow_ttm"):
        ocf = out["operating_cash_flow_ttm"]
        out["depreciation_ttm"] = dep_ttm
        out["owner_earnings_lower"] = out["free_cash_flow_ttm"]
        out["owner_earnings_upper"] = ocf - dep_ttm
        out["implied_return_lower"] = out["free_cash_flow_ttm"] / mc
        out["implied_return_upper"] = (ocf - dep_ttm) / mc

    # Solve for the growth rate that makes a 10% discount rate give today's
    # price, with reinvestment set by the return on capital in service.
    inc_roic = views["in_service"]["roic_ttm"]
    lo, hi = 0.0, WACC - 1e-6
    for _ in range(200):
        g = (lo + hi) / 2
        value = nopat * (1 - g / inc_roic) / (WACC - g)
        if value < mc:
            lo = g
        else:
            hi = g
    out["implied_growth_at_10pct"] = (lo + hi) / 2
    out["implied_growth_note"] = (
        f"영구성장 모형 V = NOPAT×(1−g/증분ROIC)÷(k−g), k=10%, "
        f"증분ROIC는 가동자본 기준 {inc_roic:.1%} 적용")
    # What the model gives at a range of growth rates, and what price each
    # implies. The spread is the point: a perpetuity discounted at 10% is
    # violently sensitive as growth approaches the discount rate, so the band
    # from 4% to 8% growth is wider than any reasonable person's confidence
    # about Alphabet's next decade. Presented as a sensitivity rather than a
    # valuation.
    grid = []
    for g in (0.03, 0.04, 0.05, 0.06, 0.07, 0.08):
        v = nopat * (1 - g / inc_roic) / (WACC - g)
        grid.append({"growth": g, "value": v,
                     "value_per_share": v / shares,
                     "vs_price": v / shares / price - 1})
    out["growth_sensitivity"] = grid

    # And the mirror: at a few prices, what perpetual growth a 10% return
    # would require.
    prices = []
    for px in (200.0, 250.0, price, 300.0, 355.84, 400.0):
        cap = px * shares
        lo_, hi_ = 0.0, WACC - 1e-6
        for _ in range(200):
            g = (lo_ + hi_) / 2
            if nopat * (1 - g / inc_roic) / (WACC - g) < cap:
                lo_ = g
            else:
                hi_ = g
        prices.append({"price": px, "market_cap": cap,
                       "implied_growth": (lo_ + hi_) / 2})
    out["implied_growth_by_price"] = prices

    out["actual_growth_operating_income_9m"] = oi_9m_26 / oi_9m_25 - 1
    out["actual_growth_revenue_9m"] = (out["revenue_9m_2026"]
                                       / out["revenue_9m_2025"] - 1)

    # Incremental return, FY2025 to the trailing twelve months. It comes out
    # low and the reason is worth stating rather than reporting the ratio
    # bare: invested capital rose $203bn in nine months, but $263bn of that
    # was equity, and most of the equity increase is the $127bn of
    # mark-to-market gains on securities running through net income. Capital
    # that arrived as an investment revaluation never had a chance to earn
    # operating income, so the denominator is inflated by something the
    # numerator excludes by construction.
    d_nopat = out["nopat_ttm"] - fy2025["nopat"]
    d_cap = (sheets["2026-09-30"]["reported"]
             - sheets["2025-12-31"]["reported"])
    d_cap_ex = (sheets["2026-09-30"]["in_service_ex_stakes"]
                - sheets["2025-12-31"]["in_service_ex_stakes"])
    out["incremental"] = {
        "delta_nopat": d_nopat,
        "delta_capital_reported": d_cap,
        "incremental_roic_reported": d_nopat / d_cap if d_cap else None,
        "delta_capital_in_service_ex_stakes": d_cap_ex,
        "incremental_roic_in_service_ex_stakes":
            d_nopat / d_cap_ex if d_cap_ex else None,
        "note": "FY2025 → TTM 2026-09. 보고 기준 분모에는 투자자산 평가이익이 "
                "자기자본으로 들어와 있어, 영업이익을 낼 수 없는 자본이 "
                "포함됩니다.",
    }

    # The tax rate is the one input the project's rule fixes but the filing
    # makes awkward, so the alternative is carried rather than argued about.
    # 19.0% is the rule's number, struck on a pretax income that holds
    # $127.5bn of securities revaluation; 21% is the federal statutory rate.
    # The verdict does not move between them, which is the point of showing it.
    out["nopat_at_statutory_21"] = oi_ttm * (1 - 0.21)
    out["nopat_sensitivity_note"] = (
        f"규칙상 실효세율 {out['tax_rate_ttm']:.1%} 적용 시 NOPAT "
        f"{out['nopat_ttm'] / 1e9:,.1f}십억, 법정세율 21% 적용 시 "
        f"{out['nopat_at_statutory_21'] / 1e9:,.1f}십억 "
        f"({out['nopat_at_statutory_21'] / out['nopat_ttm'] - 1:+.1%})")

    # Where the operating income comes from, and where it does not. Reported
    # by segment in the release, so no denominator has to be invented.
    out["segments"] = release.get("segments")

    # The financing switch. Nine months to September: not one dollar of stock
    # repurchased, against $39.8bn in the same nine months of 2025, while
    # $147bn came in from debt, common stock and preferred. A company that
    # returned capital now raises it, and that is a fact about the price of
    # the shares as much as about the balance sheet.
    fin_rows = {
        "repurchases": "Repurchases of stock",
        "debt_issued": "Proceeds from issuance of debt",
        "debt_repaid": "Repayments of debt",
        "common_issued": "Proceeds from issuance of common stock",
        "preferred_issued": "mandatory convertible preferred",
        "dividends": "Dividend payments on preferred and common",
        "sbc_settlement": "Net payments related to stock-based award",
    }
    financing = {}
    for key, label in fin_rows.items():
        r = find_row(cf_table, label)
        if r:
            financing[key] = {"nine_months_2026": r["values"][0],
                              "nine_months_2025": r["values"][1]}
    raised = sum(financing[k]["nine_months_2026"] for k in
                 ("debt_issued", "common_issued", "preferred_issued")
                 if k in financing)
    financing["external_capital_raised_9m_2026"] = raised
    financing["note"] = (
        "9개월 누적. 자사주 매입은 0, 외부자금 조달은 차입·보통주·우선주 합계.")
    out["financing"] = financing

    # Ten years of ROIC from the fifty-company study, so the price question is
    # asked against the company's own record rather than one trailing figure.
    out["ten_year_record"] = record
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)
    print(f"오늘 {date.today().isoformat()} 기준")

    sub, filings = latest(("10-Q", "10-K", "8-K"), a.refresh)
    tenq = next(f for f in filings if f["form"] == "10-Q")
    eightk = next(f for f in filings if f["form"] == "8-K")
    print(f"  최신 10-Q {tenq['filed']} (기말 {tenq['period_end']}) "
          f"{tenq['accession']}")
    print(f"  최신 8-K  {eightk['filed']} {eightk['accession']}")

    hist = price_history("GOOG")
    print(f"\n  주가 {hist['last']['close']:,.2f} ({hist['last']['date']}) · "
          f"6개월 고점 {hist['high']['close']:,.2f} "
          f"({hist['high']['date']}) · 고점 대비 {hist['from_high']:+.1%}")
    for m in hist["big_moves"][-3:]:
        print(f"    {m['date']}  {m['from']:,.2f} → {m['to']:,.2f}  "
              f"{m['change']:+.1%}")

    rel = release_numbers(eightk["accession"], a.refresh)
    if rel and rel["cash_flow"]:
        print(f"\n  잉여현금흐름 (백만 달러)")
        print(f"    {'기간':<14}{'영업CF':>12}{'capex':>12}{'FCF':>12}")
        for r in rel["cash_flow"]:
            print(f"    {r['period']:<14}{r['operating_cash_flow']/MM:>12,.0f}"
                  f"{r['capex']/MM:>12,.0f}"
                  f"{r['free_cash_flow']/MM:>12,.0f}")

    fin = quarter_financials(tenq["accession"], a.refresh)
    for k, v in fin.items():
        print(f"  {k:<16}{'확보' if v else '없음':<6}"
              f"{(v or {}).get('short_name','')[:60]}")

    # FY2025 from the fifty-company engine, so the definition is the same one
    # every other company in this project is measured on.
    roic = json.load(open(os.path.join(HERE, "roic", "roic.json")))
    goog = next(c for c in roic["companies"] if c["ticker"] == "GOOG")
    fy2025 = next(y for y in goog["years"] if y["fiscal_year"] == 2025)
    # Depreciation is not in the ROIC engine's record, so it is read from the
    # same companyfacts source the engine uses.
    facts, _, _ = sec_cache.companyfacts(CIK, CACHE)
    dep = None
    for unit, entries in facts["facts"]["us-gaap"]["Depreciation"]["units"] \
            .items():
        if unit != "USD":
            continue
        for e in entries:
            if (e.get("form", "").startswith("10-K") and e.get("fp") == "FY"
                    and e.get("start")
                    and e["end"].startswith("2025")):
                dep = e["val"]
    fy2025 = dict(fy2025, depreciation=dep)

    shares = 12_294_000_000.0
    price = hist["last"]["close"]
    calc = ratios(fin, rel, price, shares, fy2025, ten_year_record())

    out = {
        "generated": date.today().isoformat(),
        "wacc": WACC,
        "entity": sub["name"], "cik": sub["cik"],
        "tickers": sub.get("tickers"), "exchanges": sub.get("exchanges"),
        "filings": {"10-Q": tenq, "8-K": eightk},
        "price_history": hist,
        "release": rel,
        "financials": {k: v for k, v in fin.items()},
        "fy2025_from_engine": fy2025,
        "analysis": calc,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
