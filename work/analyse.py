"""
PHASE 2-5 - the framework applied to the collected data.

Turns work/raw/*.json plus work/market.json into one analysis record per
company, using calc.py for every metric. Nothing is computed inline here that
calc.py already defines; this module's job is to line the inputs up correctly
and to be explicit about which construction each number came from.

Three decisions here shape everything downstream, so they are stated rather
than buried:

1. EBIT is built as pretax income + interest expense for every company that has
   both, and only falls back to the reported operating-income subtotal
   otherwise. Five of the fifty (Lilly, Exxon, IBM, Merck, Chevron) publish no
   operating-income line at all. Taking the reported subtotal where it exists
   and something else where it does not would make the headline ROIC mean
   different things for different companies, which is worse than a uniform
   construction that is slightly unconventional.

2. Returns are measured against AVERAGE capital over the year, not the closing
   balance. A company that raised capital in December would otherwise look as
   though it earned a full year's profit on it.

3. Banks and insurers are excluded from ROIC and owner earnings by SIC code,
   not by a hand-written list. For a bank, debt is raw material rather than
   financing, so invested capital has no meaning and a ROIC computed from it
   would be a number with no interpretation. They are carried through the parts
   of the framework that do apply (ROE, leverage, multiples) and marked
   FRAMEWORK_NOT_APPLICABLE elsewhere.

Writes work/analysis.json.
"""

import json
import os
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timezone

import calc

UA = "Buffett52Analysis research cktkdgkr@gmail.com"
WORK = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(WORK, "raw")

# SIC ranges whose balance sheets the invested-capital model does not describe.
FINANCIAL_SIC = [(6000, 6799)]

# Effective tax rates outside this band are artefacts of one-off items (a
# settlement, a valuation-allowance release) rather than the rate a marginal
# dollar of profit will bear, so NOPAT uses a clamped rate and says so.
TAX_FLOOR, TAX_CAP = 0.05, 0.40
DEFAULT_TAX = 0.21          # US federal statutory, used only when unclamped rate is absent

# A market cap computed from filing-date share counts and a live price will drift
# from a live screen after a split or a large buyback. Beyond this the figure is
# not trusted for valuation.
MCAP_TOLERANCE = 0.25

SCENARIOS = [
    # (name, growth multiplier on history, discount rate, terminal growth)
    ("conservative", 0.5, 0.12, 0.020),
    ("base", 1.0, 0.10, 0.025),
    ("optimistic", 1.25, 0.08, 0.030),
]
GROWTH_CAP = 0.10           # no base case compounds faster than this for a decade
GROWTH_CAP_OPTIMISTIC = 0.15


# ---------------------------------------------------------------------------
# Loading and alignment
# ---------------------------------------------------------------------------

def load_sic(companies):
    """SIC code per CIK, cached, so the financial-sector split is sourced."""
    path = os.path.join(WORK, "sic.json")
    cache = json.load(open(path)) if os.path.exists(path) else {}
    dirty = False
    for c in companies:
        key = str(c["cik"])
        if key in cache:
            continue
        url = f"https://data.sec.gov/submissions/CIK{c['cik']:010d}.json"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            j = json.loads(r.read())
        cache[key] = {"sic": j.get("sic"), "sic_description": j.get("sicDescription"),
                      "name": j.get("name"), "source_url": url}
        dirty = True
        time.sleep(0.3)
    if dirty:
        with open(path, "w") as f:
            json.dump(cache, f, indent=2)
    return cache


def is_financial(sic) -> bool:
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return False
    return any(lo <= s <= hi for lo, hi in FINANCIAL_SIC)


def series_map(raw, metric):
    """{fiscal_year: value} for one metric."""
    node = raw.get("metrics", {}).get(metric, {})
    return {r["fiscal_year"]: r["value"] for r in node.get("series", [])}


def accession_map(raw, metric):
    node = raw.get("metrics", {}).get(metric, {})
    return {r["fiscal_year"]: r["accession"] for r in node.get("series", [])}


def split_adjust_shares(shares, filed_by_year, split_events):
    """
    Restate a share-count series into current, post-split units.

    Each year's count is reported in the units of the filing it came from, and a
    10-K only restates two prior years, so a decade-long series straddles every
    split the company has done since. Left alone, NVIDIA's 4:1 and 10:1 splits
    turn a buyback into 41% annual "dilution" and Amazon's 20:1 does the same,
    which reverses the capital-allocation reading for five of the fifty.

    The adjustment keys on the FILING date, not the fiscal period. A filing
    states share counts in the units current when it was filed, so a year whose
    figure was restated in a later 10-K is already post-split. Keying on the
    period end instead re-applies a split the filing had already applied:
    Apple's FY2019 count was restated in the FY2020 report, filed after the 4:1
    split, and was being multiplied by four a second time to 71bn shares.
    """
    # The quote feed files spin-offs in the same channel as splits, as a price
    # adjustment like "1806:1000" (Dell shedding VMware) or "1281:1000" (GE
    # spinning out HealthCare). Those change the price, not the share count, so
    # applying them here would invent shares that were never issued. A real
    # split is a small whole-number exchange - 2:1, 3:2, 10:1, 1:8 - so ratios
    # that are not are set aside and recorded.
    real, ignored = [], []
    for ev in split_events:
        parts = str(ev.get("as_stated") or "").split(":")
        try:
            num, den = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            ignored.append(ev)
            continue
        (real if (num <= 100 and den <= 100) else ignored).append(ev)

    ignored_note = ""
    if ignored:
        ignored_note = ("; ignored as price adjustments rather than share splits: "
                        + ", ".join(f"{e['as_stated']} on {e['date']}" for e in ignored))
    if not real:
        return dict(shares), ("no share splits on record; counts already comparable"
                              + ignored_note)
    split_events = real
    adjusted, applied = {}, []
    for year, val in shares.items():
        filed = filed_by_year.get(year)
        if not filed:
            adjusted[year] = val
            continue
        factor = 1.0
        for ev in split_events:
            if ev["date"] > filed:
                factor *= ev["ratio"]
        adjusted[year] = val * factor
        if factor != 1.0:
            applied.append(f"FY{year} x{factor:g}")
    note = ("restated into post-split units: " + ", ".join(applied)) if applied else \
           "splits on record but all predate the series; no adjustment needed"
    return adjusted, note + ignored_note


def avg2(prev, cur):
    """Average of opening and closing balance; falls back to whichever exists."""
    if prev is None:
        return cur
    if cur is None:
        return None
    return (prev + cur) / 2.0


# ---------------------------------------------------------------------------
# Derived inputs
# ---------------------------------------------------------------------------

def build_ebit(pretax, interest, reported_oi, year):
    """EBIT with its construction recorded, so mixed methods stay visible."""
    p, i = pretax.get(year), interest.get(year)
    if p is not None and i is not None:
        return p + i, "pretax_income + interest_expense"
    oi = reported_oi.get(year)
    if oi is not None:
        return oi, "reported OperatingIncomeLoss (no interest expense tagged)"
    if p is not None:
        return p, "pretax_income only (no interest expense tagged)"
    return None, "DATA_UNAVAILABLE"


def effective_tax(tax, pretax, year):
    """Effective rate, clamped, with a flag when the raw rate was unusable."""
    t, p = tax.get(year), pretax.get(year)
    if t is None or p is None or p <= 0:
        return DEFAULT_TAX, "statutory 21% (pretax income absent or non-positive)"
    raw = t / p
    if raw < TAX_FLOOR:
        return TAX_FLOOR, f"clamped up from {raw:.1%}"
    if raw > TAX_CAP:
        return TAX_CAP, f"clamped down from {raw:.1%}"
    return raw, f"effective {raw:.1%}"


def interest_bearing_debt(short_d, long_d, year):
    """
    Short- plus long-term interest-bearing debt.

    A missing component alongside a present one is read as nil rather than
    unknown: filers omit the tag when the balance is zero. If neither side is
    tagged the company's debt is genuinely unknown and stays None.
    """
    s, l = short_d.get(year), long_d.get(year)
    if s is None and l is None:
        return None, "DATA_UNAVAILABLE"
    if s is None:
        return l, "long-term only (no short-term debt tagged; read as nil)"
    if l is None:
        return s, "short-term only (no long-term debt tagged; read as nil)"
    return s + l, "short-term + long-term"


def working_capital_change(cur_a, cur_l, cash, short_debt, year, prev_year):
    """
    Cash absorbed by OPERATING working capital, positive = consumed.

    Cash and short-term debt are stripped out first. Total current assets
    include cash, so a company that banks a large cash pile would otherwise
    register as having consumed working capital and its owner earnings would be
    driven negative by its own success at generating cash - which is what
    happened to Intel, Oracle and Tesla on the unadjusted figure. Short-term
    debt is financing, not operations, and comes out of current liabilities for
    the same reason.
    """
    for y in (year, prev_year):
        if cur_a.get(y) is None or cur_l.get(y) is None:
            return None, "DATA_UNAVAILABLE"

    def owc(y):
        a = cur_a[y] - (cash.get(y) or 0.0)
        l = cur_l[y] - (short_debt.get(y) or 0.0)
        return a - l

    exact = all(cash.get(y) is not None for y in (year, prev_year))
    note = ("operating working capital (cash and short-term debt excluded)"
            if exact else
            "current assets less current liabilities; cash not tagged for both years, "
            "so the swing may still carry a cash movement")
    return owc(year) - owc(prev_year), note


# ---------------------------------------------------------------------------
# Per-company analysis
# ---------------------------------------------------------------------------

def analyse_company(entry, raw, mkt, sic_info, cover):
    t = entry["ticker"]
    fin = is_financial(sic_info.get("sic"))

    S = {m: series_map(raw, m) for m in raw.get("metrics", {})}
    accns = {m: accession_map(raw, m) for m in raw.get("metrics", {})}

    # A filer whose borrowing tags stopped years ago has repaid its debt, not
    # hidden it: the tag is dropped once the balance is nil. Without this,
    # genuinely unlevered companies (Arista, Palantir - their only "debt" tags
    # are debt SECURITIES they hold as investments) lose ROIC entirely.
    # The test is deliberately staleness, not absence, and it runs after the tag
    # list was widened: Coca-Cola looked debt-free too until the collector
    # learned LongTermDebtAndCapitalLeaseObligations, and reading that as nil
    # would have quietly erased $40bn of borrowings from its invested capital.
    # "Cash" for invested-capital purposes is the liquid pile, not just the
    # cash line. Where a filer publishes the combined tag it already includes
    # short-term investments; where it does not, they are added here.
    cash_tag = (raw.get("metrics", {}).get("cash_and_equivalents") or {}).get("xbrl_tag")
    combined = cash_tag == "CashCashEquivalentsAndShortTermInvestments"
    sti = S.get("short_term_investments", {})
    if not combined and sti:
        merged = dict(S.get("cash_and_equivalents", {}))
        for y, v in merged.items():
            if sti.get(y) is not None:
                merged[y] = v + sti[y]
        S["cash_and_equivalents"] = merged
    liquidity_note = ("cash tag already includes short-term investments" if combined
                      else ("cash + short-term investments" if sti else "cash only; no "
                            "short-term investment tag published"))

    # Fill a missing consolidated pretax total from the domestic and foreign
    # halves where a filer publishes only those. Without this the effective tax
    # rate falls back to the statutory 21% for a company that discloses its real
    # one, and EBIT loses its preferred construction.
    pt = dict(S.get("pretax_income", {}))
    dom, fgn = S.get("pretax_income_domestic", {}), S.get("pretax_income_foreign", {})
    pretax_filled = []
    for y in set(dom) & set(fgn):
        if pt.get(y) is None:
            pt[y] = dom[y] + fgn[y]
            pretax_filled.append(y)
    if pretax_filled:
        S["pretax_income"] = pt
    pretax_note = ("consolidated tag used" if not pretax_filled else
                   f"domestic + foreign summed for FY{sorted(pretax_filled)} "
                   f"(no consolidated tag published)")

    equity_years = S.get("total_equity", {})
    latest_bs_year = max(equity_years) if equity_years else None
    debt_years = set(S.get("short_term_debt", {})) | set(S.get("long_term_debt", {}))
    debt_read_as_nil = bool(
        latest_bs_year is not None
        and (not debt_years or max(debt_years) <= latest_bs_year - 3))
    if debt_read_as_nil:
        S["short_term_debt"] = dict(S.get("short_term_debt", {}))
        S["short_term_debt"].update({y: 0.0 for y in equity_years})

    years = sorted(set(S.get("net_income", {})) | set(S.get("revenue", {})))
    years = [y for y in years if y >= max(years) - 11] if years else []

    price = (mkt.get("price") or {}).get("price")
    # Share counts must be on one basis before any of them are compared.
    filed_dates = {r["fiscal_year"]: r.get("filed")
                   for r in raw.get("metrics", {}).get("shares_outstanding", {}).get("series", [])}
    shares_series, split_note = split_adjust_shares(
        S.get("shares_outstanding", {}), filed_dates,
        (mkt.get("splits") or {}).get("splits") or [])
    S["shares_outstanding"] = shares_series
    latest_share_year = max(shares_series) if shares_series else None

    # The cover page of the latest annual report is both more current than the
    # balance-sheet date and complete across share classes, so it wins whenever
    # it is available; the balance-sheet count is the fallback.
    shares, shares_src = shares_series.get(latest_share_year), (
        f"us-gaap share count, FY{latest_share_year}")
    if cover.get("status") == "OK" and cover.get("shares_outstanding"):
        shares = cover["shares_outstanding"]
        shares_src = (f"10-K cover page ({cover.get('document_period_end')}), "
                      f"{cover.get('conversion_note')}")
    market_cap = price * shares if (price is not None and shares) else None

    # Guard against a share count that predates a split or a big buyback.
    screen = (entry.get("selection") or {}).get("screen_market_cap_usd")
    mcap_check = {"status": "NOT_CHECKED"}
    if market_cap and screen:
        div = abs(market_cap - screen) / screen
        mcap_check = {
            "computed_usd": market_cap,
            "screen_usd": screen,
            "divergence": div,
            "status": "OK" if div <= MCAP_TOLERANCE else "DIVERGENT",
            "note": ("share count and price agree with an independent screen"
                     if div <= MCAP_TOLERANCE else
                     "computed market cap disagrees with an independent screen beyond "
                     "tolerance - likely a stock split or share-class effect between the "
                     "filing date and the quote; valuation multiples suppressed"),
        }
        if div > MCAP_TOLERANCE:
            market_cap = None

    rows = []
    for idx, y in enumerate(years):
        prev = years[idx - 1] if idx > 0 else None
        ebit, ebit_method = build_ebit(S.get("pretax_income", {}), S.get("interest_expense", {}),
                                       S.get("operating_income", {}), y)
        tax, tax_note = effective_tax(S.get("income_tax_expense", {}),
                                      S.get("pretax_income", {}), y)
        ibd, ibd_note = interest_bearing_debt(S.get("short_term_debt", {}),
                                              S.get("long_term_debt", {}), y)
        equity = S.get("total_equity", {}).get(y)
        cash = S.get("cash_and_equivalents", {}).get(y)
        ni = S.get("net_income", {}).get(y)
        rev = S.get("revenue", {}).get(y)
        da = S.get("depreciation_amortization", {}).get(y)
        capex = S.get("capex", {}).get(y)
        ocf = S.get("operating_cash_flow", {}).get(y)

        ic = None if fin else calc.invested_capital(equity, ibd, cash)
        ic_prev = None
        if prev is not None and not fin:
            ic_prev = calc.invested_capital(
                S.get("total_equity", {}).get(prev),
                interest_bearing_debt(S.get("short_term_debt", {}),
                                      S.get("long_term_debt", {}), prev)[0],
                S.get("cash_and_equivalents", {}).get(prev))
        ic_avg = avg2(ic_prev, ic)
        eq_avg = avg2(S.get("total_equity", {}).get(prev) if prev else None, equity)

        # Capital employed before deducting cash. Reported alongside the
        # cash-netted figure because years of buybacks can drive net invested
        # capital to nearly nothing, at which point the ratio explodes and stops
        # describing the business - Philip Morris and KLA both hit this.
        ic_gross = None if fin else calc.invested_capital(equity, ibd, 0.0)
        ic_gross_prev = None
        if prev is not None and not fin:
            ic_gross_prev = calc.invested_capital(
                S.get("total_equity", {}).get(prev),
                interest_bearing_debt(S.get("short_term_debt", {}),
                                      S.get("long_term_debt", {}), prev)[0], 0.0)
        ic_gross_avg = avg2(ic_gross_prev, ic_gross)

        # Buffett's own denominator, in his words: "net tangible assets". The
        # 2007 letter prices See's on "the capital required to conduct the
        # business" - $8m against $30m of sales - and contrasts $82m earned on
        # "$400 million of net tangible assets". Goodwill and acquired
        # intangibles are not capital the business needs to operate; they record
        # what was paid for someone else's earning power.
        gw = S.get("goodwill", {}).get(y)
        intang = S.get("intangible_assets", {}).get(y)
        ic_tang = None
        if ic is not None:
            ic_tang = ic - (gw or 0.0) - (intang or 0.0)
        ic_tang_prev = None
        if prev is not None and ic_prev is not None:
            ic_tang_prev = (ic_prev - (S.get("goodwill", {}).get(prev) or 0.0)
                            - (S.get("intangible_assets", {}).get(prev) or 0.0))
        ic_tang_avg = avg2(ic_tang_prev, ic_tang)
        roic_tangible = None if fin else calc.roic(ebit, tax, ic_tang_avg)
        if ic_tang_avg is not None and ic_tang_avg <= 0:
            roic_tangible = None
        capital_intensity = calc._safe_div(ic_avg, rev)

        nopat = calc.nopat(ebit, tax)
        roic_v = None if fin else calc.roic(ebit, tax, ic_avg)
        roic_status = "OK"
        if fin:
            roic_status = "FRAMEWORK_NOT_APPLICABLE"
        elif ic_avg is None:
            roic_status = "DATA_UNAVAILABLE"
        elif ic_avg <= 0:
            # Required capital at or below zero with profits coming out is not a
            # broken ratio - it is the far end of what Buffett prizes. See's
            # needed $8m against $30m of sales and he called it the prototype of
            # a dream business; a company that needs none at all while earning
            # money is that case taken further. The ratio is undefined, so the
            # condition is recorded instead of a number. With EBIT also at or
            # below zero there is nothing to say either way.
            if (ebit or 0) > 0:
                roic_v, roic_status = None, "CAPITAL_LIGHT_NO_NET_CAPITAL_REQUIRED"
            else:
                roic_v, roic_status = None, "NOT_MEANINGFUL_NEGATIVE_INVESTED_CAPITAL"
        elif rev and ic_avg < 0.10 * rev:
            roic_status = "UNSTABLE_MINIMAL_INVESTED_CAPITAL"
        # The gross basis degenerates too, just far less often: Oracle's FY2022
        # gross invested capital was $1.3bn against $42bn of revenue after years
        # of buybacks, and Palantir's straddles zero across its listing. Same
        # guard as the net basis.
        roic_gross_v = None if fin else calc.roic(ebit, tax, ic_gross_avg)
        roic_gross_status = "OK"
        if fin:
            roic_gross_status = "FRAMEWORK_NOT_APPLICABLE"
        elif ic_gross_avg is None:
            roic_gross_status = "DATA_UNAVAILABLE"
        elif ic_gross_avg <= 0:
            roic_gross_v, roic_gross_status = None, "NOT_MEANINGFUL_NEGATIVE_INVESTED_CAPITAL"
        elif rev and ic_gross_avg < 0.10 * rev:
            roic_gross_v, roic_gross_status = None, "NOT_MEANINGFUL_MINIMAL_INVESTED_CAPITAL"
        # ROE divided by an equity base at or below zero is not a return. Home
        # Depot's FY2020 came out at 14,061% and AbbVie's FY2025 at 15,367%,
        # both purely because buybacks had taken book equity to near nothing.
        roe_v = calc.roe(ni, eq_avg) if (eq_avg or 0) > 0 else None
        roe_status = "OK" if (eq_avg or 0) > 0 else "NOT_MEANINGFUL_EQUITY_AT_OR_BELOW_ZERO"
        if roe_v is not None and abs(roe_v) > 5.0:
            roe_status = "UNSTABLE_EQUITY_NEAR_ZERO"

        # Owner earnings: the direct definition first, the cash-flow route as a
        # fallback where the classified balance sheet needed for the working
        # capital swing does not exist.
        d_wc, wc_note = working_capital_change(
            S.get("current_assets", {}), S.get("current_liabilities", {}),
            S.get("cash_and_equivalents", {}), S.get("short_term_debt", {}),
            y, prev) if prev else (None, "no prior year")
        oe = calc.owner_earnings(ni, da, capex, d_wc)
        oe_method = f"net income + D&A - capex - change in {wc_note}"

        # Buffett's definition subtracts the capex "the business requires to
        # fully maintain its long-term competitive position and its unit
        # volume" - maintenance capex, not the whole capital budget. Charging
        # every dollar of a build-out against owner earnings makes growth
        # investment read as deterioration: Alphabet spent $91bn against $21bn
        # of depreciation in FY2025 and its owner earnings duly halved, which
        # describes the accounting, not the business.
        #
        # Depreciation is the standard proxy for the replacement half of that
        # spend. It is not exact - in an inflationary period replacing an asset
        # costs more than its historical depreciation, which Buffett himself
        # warned about - so the two figures are kept as a BAND rather than one
        # being declared correct. Total capex is the pessimistic bound,
        # maintenance-only the optimistic one.
        maint_capex = None if (capex is None or da is None) else min(capex, da)
        oe_maint = calc.owner_earnings(ni, da, maint_capex, d_wc)
        growth_capex = None if (capex is None or maint_capex is None) else capex - maint_capex
        if oe is None and ocf is not None and capex is not None:
            oe, oe_method = ocf - capex, "operating cash flow - capex (working-capital swing already embedded)"
        if fin:
            oe, oe_maint = None, None
            oe_method = "FRAMEWORK_NOT_APPLICABLE (financial sector)"

        ebitda = ebit + da if (ebit is not None and da is not None) else None

        rows.append({
            "fiscal_year": y,
            # Raw filing inputs are carried alongside the derived figures so a
            # reader can rebuild every ratio from the same numbers the engine
            # used, rather than having to take the result on trust.
            "raw": {
                "revenue": rev,
                "pretax_income": S.get("pretax_income", {}).get(y),
                "interest_expense": S.get("interest_expense", {}).get(y),
                "income_tax_expense": S.get("income_tax_expense", {}).get(y),
                "operating_income_reported": S.get("operating_income", {}).get(y),
                "net_income": ni,
                "depreciation_amortization": da,
                "capex": capex,
                "operating_cash_flow": ocf,
                "total_equity": equity,
                "total_equity_prior": S.get("total_equity", {}).get(prev) if prev else None,
                "cash": cash,
                "short_term_debt": S.get("short_term_debt", {}).get(y),
                "long_term_debt": S.get("long_term_debt", {}).get(y),
                "current_assets": S.get("current_assets", {}).get(y),
                "current_liabilities": S.get("current_liabilities", {}).get(y),
                "current_assets_prior": S.get("current_assets", {}).get(prev) if prev else None,
                "current_liabilities_prior": S.get("current_liabilities", {}).get(prev) if prev else None,
                "cash_prior": S.get("cash_and_equivalents", {}).get(prev) if prev else None,
                "short_term_debt_prior": S.get("short_term_debt", {}).get(prev) if prev else None,
                "invested_capital_prior": ic_prev,
                "change_in_working_capital": d_wc,
                "working_capital_note": wc_note,
            },
            "period_end": next((r["period_end"] for r in raw["metrics"]["net_income"]["series"]
                                if r["fiscal_year"] == y), None),
            "accession": accns.get("net_income", {}).get(y),
            "revenue": rev, "net_income": ni,
            "ebit": ebit, "ebit_method": ebit_method,
            "tax_rate": tax, "tax_note": tax_note,
            "nopat": nopat,
            "interest_bearing_debt": ibd, "debt_note": ibd_note,
            "total_equity": equity, "cash": cash,
            "invested_capital": ic, "invested_capital_avg": ic_avg,
            "invested_capital_gross_avg": ic_gross_avg,
            "invested_capital_tangible": ic_tang,
            "invested_capital_tangible_avg": ic_tang_avg,
            "roic_tangible": roic_tangible,
            "goodwill": gw, "intangible_assets": intang,
            "capital_intensity": capital_intensity,
            "roic": roic_v, "roic_status": roic_status, "roic_gross": roic_gross_v,
            "roic_gross_status": roic_gross_status,
            "roe": roe_v, "roe_status": roe_status,
            "roe_roic_spread": calc.roe_roic_spread(roe_v, roic_v),
            "ebitda": ebitda,
            # A leverage ratio divided by negative EBITDA produces a negative
            # number that reads like net cash. Intel's FY2024 came out at -124x
            # on EBITDA of -$0.2bn. There is no leverage reading to give when a
            # company is not generating EBITDA, so it stays blank.
            "net_debt_to_ebitda": (calc.net_debt_to_ebitda(ibd, cash, ebitda)
                                   if (ebitda or 0) > 0 else None),
            # Coverage is how many times operating profit covers interest. With
            # EBIT at or below zero it is not covered at all, and a negative
            # multiple reads like a number rather than that fact.
            "interest_coverage": (calc.interest_coverage(ebit, S.get("interest_expense", {}).get(y))
                                  if (ebit or 0) > 0 else None),
            "interest_coverage_status": ("OK" if (ebit or 0) > 0
                                         else "NOT_COVERED_EBIT_AT_OR_BELOW_ZERO"),
            "owner_earnings": oe, "owner_earnings_method": oe_method,
            "owner_earnings_maintenance_capex": oe_maint,
            "maintenance_capex": maint_capex, "growth_capex": growth_capex,
            "owner_earnings_margin_maintenance": calc.owner_earnings_margin(oe_maint, rev),
            "owner_earnings_margin": calc.owner_earnings_margin(oe, rev),
            "operating_margin": calc._safe_div(ebit, rev),
            "shares_outstanding": shares_series.get(y),
        })

    return {
        "ticker": t,
        # The XBRL entityName can name a financing subsidiary rather than the
        # registrant - Bank of America's facts come back as "BofA Finance LLC" -
        # so the filer index name wins, with entityName as the fallback.
        "company_name": (sic_info.get("name") or raw.get("company_name")
                         or entry.get("company_name")),
        "cik": entry["cik"],
        "sic": sic_info.get("sic"),
        "sic_description": sic_info.get("sic_description"),
        "sector_treatment": "FINANCIAL" if fin else "STANDARD",
        "source_url": raw.get("source_url"),
        "price": mkt.get("price"),
        "shares_outstanding_used": shares,
        "shares_source": shares_src,
        "share_series_split_adjustment": split_note,
        "shares_cover_page": cover,
        "shares_as_of_fiscal_year": latest_share_year,
        "market_cap_usd": market_cap,
        "market_cap_check": mcap_check,
        "market_cap_method": "SEC-filed share count x latest exchange close",
        "liquidity_definition": liquidity_note,
        "pretax_income_note": pretax_note,
        "debt_read_as_nil": debt_read_as_nil,
        "beta": mkt.get("beta"),
        "years": rows,
    }


# ---------------------------------------------------------------------------
# Summary metrics across the window
# ---------------------------------------------------------------------------

def summarise(rec, rf, erp):
    rows = [r for r in rec["years"]]
    fin = rec["sector_treatment"] == "FINANCIAL"
    out = {}

    def vals(key, n=None):
        v = [(r["fiscal_year"], r[key]) for r in rows if r.get(key) is not None]
        return v[-n:] if n else v

    latest_fy = rows[-1]["fiscal_year"] if rows else None
    out["latest_fiscal_year"] = latest_fy

    def latest_of(pairs, label):
        """
        Most recent observation, tagged with the year it is actually from.

        A metric can be absent for the newest year while present earlier; taking
        the last non-null and calling it current would silently date-shift the
        figure, so the year travels with the value and a stale one is marked.
        """
        if not pairs:
            return None, None, "DATA_UNAVAILABLE"
        fy, v = pairs[-1]
        return v, fy, ("OK" if fy == latest_fy else f"STALE - latest available is FY{fy}, "
                                                    f"company's newest filed year is FY{latest_fy}")

    # The ranking uses ROIC on the capital the business actually requires -
    # equity plus interest-bearing debt, less cash. That is Buffett's own
    # denominator. The 2007 letter: "The capital then required to conduct the
    # business was $8 million... Consequently, the company was earning 60%
    # pre-tax on invested capital", and later "$82 million pre-tax on $400
    # million of net tangible assets".
    #
    # An earlier build switched the ranking to GROSS invested capital, leaving
    # cash in, because the net figure explodes when a company's cash approaches
    # its whole capital base - Arista's net ROIC swings between 96% and 192%.
    # That was backwards. Needing almost no capital is the condition Buffett
    # prizes above all others, and the same letter names the archetypes: "It's
    # far better to have an ever-increasing stream of earnings with virtually no
    # major capital requirements. Ask Microsoft or Google." A 148% return on
    # required capital is the See's Candy finding, not an artefact to suppress.
    #
    # The instability never actually reached the score, which bands ROIC anyway:
    # 148% and 35% both land in the top band. It only distorted the displayed
    # median and the sort - and the exclusion rule introduced to fix it did real
    # damage, shrinking Arista's observation count to two.
    roics = vals("roic")
    roics_gross = vals("roic_gross")
    roics_tangible = vals("roic_tangible")
    out["roic_tangible_10y_median"] = (statistics.median([v for _, v in roics_tangible])
                                       if roics_tangible else None)
    out["roic_tangible_latest"] = roics_tangible[-1][1] if roics_tangible else None
    ci = vals("capital_intensity")
    out["capital_intensity_latest"] = ci[-1][1] if ci else None
    out["capital_intensity_median"] = (statistics.median([v for _, v in ci]) if ci else None)
    out["roic_basis"] = ("capital required to run the business "
                         "(equity + interest-bearing debt - cash), per the 2007 letter")
    out["roic_unstable_years"] = sum(
        1 for r in rows if (r.get("roic_status") or "").startswith(("UNSTABLE", "NOT_MEANINGFUL")))

    out["roic_latest"], out["roic_latest_year"], out["roic_latest_status"] = \
        latest_of(roics, "roic")
    out["roic_gross_latest"], out["roic_gross_latest_year"], _ = latest_of(roics_gross, "roic_gross")
    out["roic_gross_10y_median"] = (statistics.median([v for _, v in roics_gross])
                                    if roics_gross else None)
    out["roic_gross_years_observed"] = len(roics_gross)
    out["roic_gross_above_10pct_years"] = sum(1 for _, v in roics_gross if v >= 0.10)
    out["roic_gross_stdev"] = (statistics.pstdev([v for _, v in roics_gross])
                               if len(roics_gross) > 1 else None)
    out["roic_10y_median"] = statistics.median([v for _, v in roics]) if roics else None
    # Capital-light years count as observed and as clearing the bar: the
    # business earned a return on capital it did not need.
    capital_light_years = sum(
        1 for r in rows if r.get("roic_status") == "CAPITAL_LIGHT_NO_NET_CAPITAL_REQUIRED")
    out["capital_light_years"] = capital_light_years
    out["roic_years_observed"] = len(roics) + capital_light_years
    out["roic_above_10pct_years"] = sum(1 for _, v in roics if v >= 0.10) + capital_light_years
    # Consistency is the point of principle 1: a high average built out of two
    # good years is not a franchise.
    out["roic_stdev"] = statistics.pstdev([v for _, v in roics]) if len(roics) > 1 else None
    # Palantir funds itself entirely from a cash pile roughly equal to its
    # equity and carries no debt, so its invested capital is about zero and no
    # year yields a meaningful ROIC. Scoring it on a scale where 45 of the 100
    # points come from ROIC would rank it on the points it cannot lose rather
    # than on anything measured.
    out["quality_scoreable"] = len(roics) > 0 or len(roics_gross) > 0
    out["quality_not_scoreable_reason"] = None if (roics or roics_gross) else (
        "no year yields a meaningful ROIC - invested capital is at or below zero "
        "throughout, so the return-on-capital half of the framework has nothing "
        "to measure")

    # Incremental ROIC over the longest clean window available.
    inc = None
    # Measured on gross invested capital, matching the basis the score uses.
    # On the net basis Arista's incremental ROIC came out at 203% because the
    # denominator - the change in a capital base that is nearly all cash - is
    # noise rather than capital management actually deployed.
    nop = [(r["fiscal_year"], r["nopat"], r["invested_capital"]) for r in rows
           if r.get("nopat") is not None and r.get("invested_capital") is not None]
    inc_status = "DATA_UNAVAILABLE"
    if len(nop) >= 2 and not fin:
        (_, n0, i0), (_, n1, i1) = nop[0], nop[-1]
        inc = calc.incremental_roic(n0, n1, i0, i1)
        out["incremental_roic_window"] = f"FY{nop[0][0]}..FY{nop[-1][0]}"
        # The ratio needs a denominator worth dividing by. Apple's invested
        # capital is barely larger than it was a decade ago - it returns its
        # cash rather than redeploying it - so the change in capital is a
        # rounding error and the quotient reads in the hundreds of percent.
        # That says nothing about the returns on capital management actually
        # put to work, so a capital base that moved less than a quarter over
        # the window is treated as not having moved.
        if inc is None:
            inc_status = "NOT_MEANINGFUL_INVESTED_CAPITAL_SHRANK"
        elif i0 and abs(i1 - i0) < 0.25 * abs(i0):
            inc, inc_status = None, "NOT_MEANINGFUL_CAPITAL_BASE_ESSENTIALLY_UNCHANGED"
        else:
            inc_status = "OK"
    elif fin:
        inc_status = "FRAMEWORK_NOT_APPLICABLE"
    out["incremental_roic"] = inc
    out["incremental_roic_status"] = inc_status

    out["roic_status_latest"] = rows[-1].get("roic_status") if rows else None

    # Same treatment as ROIC: years where the equity base has collapsed stay
    # visible with their flag but are kept out of the multi-year aggregates.
    roes_all = vals("roe")
    ROE_CAP = 5.0
    roes = [(fy, max(-ROE_CAP, min(v, ROE_CAP))) for fy, v in roes_all]
    out["roe_years_capped_as_unstable"] = sum(1 for _, v in roes_all if abs(v) > ROE_CAP)
    out["roe_latest"], out["roe_latest_year"], _ = latest_of(roes, "roe")
    out["roe_10y_median"] = statistics.median([v for _, v in roes]) if roes else None
    spreads = vals("roe_roic_spread")
    out["roe_roic_spread_latest"] = spreads[-1][1] if spreads else None

    nd = vals("net_debt_to_ebitda")
    out["net_debt_to_ebitda_latest"] = nd[-1][1] if nd else None
    ic_ = vals("interest_coverage")
    out["interest_coverage_latest"] = ic_[-1][1] if ic_ else None

    oes = vals("owner_earnings")
    out["owner_earnings_latest"], out["owner_earnings_latest_year"], _ = \
        latest_of(oes, "owner_earnings")
    out["owner_earnings_years"] = len(oes)
    # The DCF runs off a normalised figure: a single year swings on one-off
    # capex or a working-capital snap, and compounding that for a decade is how
    # a DCF turns into fiction. Coca-Cola's owner earnings went $16.6bn ->
    # $2.1bn in one year on working-capital timing alone.
    #
    # Normalising the MARGIN and applying it to current revenue, rather than
    # taking a median of the levels, smooths that timing without discarding
    # growth. A median of levels values Arista off a year when it was a third
    # its current size, which is staleness dressed up as conservatism.
    margins_recent = [v for _, v in vals("owner_earnings_margin")][-5:]
    latest_rev = next((r["revenue"] for r in reversed(rows) if r.get("revenue")), None)
    recent_levels = [v for _, v in oes[-3:]]
    if margins_recent and latest_rev:
        out["owner_earnings_normalised"] = statistics.median(margins_recent) * latest_rev
        out["owner_earnings_normalisation"] = (
            f"median owner-earnings margin of the last {len(margins_recent)} years "
            f"({statistics.median(margins_recent):.1%}) applied to FY{latest_fy} revenue")
    elif recent_levels:
        out["owner_earnings_normalised"] = statistics.median(recent_levels)
        out["owner_earnings_normalisation"] = (
            f"median of the last {len(recent_levels)} years (no margin history)")
    else:
        out["owner_earnings_normalised"] = None
        out["owner_earnings_normalisation"] = "DATA_UNAVAILABLE"
    out["owner_earnings_median_level"] = (
        statistics.median(recent_levels) if recent_levels else None)

    # The same normalisation applied to the maintenance-capex figure, giving the
    # optimistic end of the owner-earnings band.
    m_margins = [v for _, v in vals("owner_earnings_margin_maintenance")][-5:]
    out["owner_earnings_normalised_maintenance"] = (
        statistics.median(m_margins) * latest_rev if (m_margins and latest_rev) else None)
    growth_capex = [v for _, v in vals("growth_capex")]
    out["growth_capex_latest"] = growth_capex[-1] if growth_capex else None
    out["growth_capex_share_of_capex"] = None
    latest_row = rows[-1] if rows else {}
    gc, cx = latest_row.get("growth_capex"), (latest_row.get("raw") or {}).get("capex")
    if gc is not None and cx:
        out["growth_capex_share_of_capex"] = gc / cx
    if len(oes) >= 4 and oes[0][1] and oes[-1][1] and oes[0][1] > 0 and oes[-1][1] > 0:
        out["owner_earnings_cagr"] = calc.cagr(oes[0][1], oes[-1][1], oes[-1][0] - oes[0][0])
        out["owner_earnings_cagr_window"] = f"FY{oes[0][0]}..FY{oes[-1][0]}"
    else:
        out["owner_earnings_cagr"] = None

    margins = vals("operating_margin")
    out["operating_margin_latest"] = margins[-1][1] if margins else None
    out["operating_margin_stdev"] = (statistics.pstdev([v for _, v in margins])
                                     if len(margins) > 1 else None)

    sh = vals("shares_outstanding")
    if len(sh) >= 2 and sh[-1][0] > sh[0][0]:
        out["share_count_cagr"] = calc.share_count_cagr(sh[0][1], sh[-1][1], sh[-1][0] - sh[0][0])
        out["share_count_window"] = f"FY{sh[0][0]}..FY{sh[-1][0]}"
    else:
        out["share_count_cagr"] = None

    # ---- WACC -------------------------------------------------------------
    beta = (rec.get("beta") or {}).get("beta")
    ke = calc.cost_of_equity_capm(rf, beta, erp)
    latest = rows[-1] if rows else {}
    debt = latest.get("interest_bearing_debt")
    int_exp = None
    for r in reversed(rows):
        if r.get("interest_coverage") is not None and r.get("ebit") is not None:
            int_exp = r["ebit"] / r["interest_coverage"] if r["interest_coverage"] else None
            break
    kd = calc._safe_div(int_exp, debt)
    kd_note = "interest expense / interest-bearing debt"
    if kd is not None and not (0.0 < kd < 0.25):
        kd, kd_note = None, f"implied rate {kd:.1%} outside a credible band; discarded"
    if kd is None and debt:
        # A large-cap with debt it does not break out still has a cost of debt.
        # An investment-grade spread over the risk-free rate is a stated
        # assumption; leaving WACC undefined for a third of the set is worse.
        kd = rf + 0.010
        kd_note = "ASSUMED risk-free + 100bp (investment-grade spread); interest expense not tagged"

    if not debt:
        # No interest-bearing debt tagged: the firm is equity-financed as far as
        # the filings show, so WACC collapses to the cost of equity.
        wacc_v = ke
        wacc_note = "no interest-bearing debt in the filings; WACC = cost of equity"
    else:
        wacc_v = calc.wacc(rec.get("market_cap_usd"), debt, ke, kd, latest.get("tax_rate"))
        wacc_note = "market-value weights: market cap for equity, book interest-bearing debt"

    out["cost_of_equity"] = ke
    out["cost_of_debt"] = kd
    out["cost_of_debt_note"] = kd_note
    out["wacc"] = wacc_v
    out["wacc_note"] = wacc_note
    # Spread on the gross basis too, so the score's three ROIC-derived
    # components all describe the same denominator.
    out["roic_wacc_spread"] = calc.roic_wacc_spread(out["roic_latest"], wacc_v)
    out["roic_wacc_spread_gross_basis"] = calc.roic_wacc_spread(out["roic_gross_latest"], wacc_v)
    r2 = (rec.get("beta") or {}).get("r_squared")
    out["beta_reliability"] = (
        "LOW - the market explains under 10% of this stock's variance, so its CAPM "
        "cost of equity is weakly identified and the WACC built on it is soft"
        if r2 is not None and r2 < 0.10 else "OK")

    # ---- Multiples --------------------------------------------------------
    mc = rec.get("market_cap_usd")
    out["per"] = calc.per(mc, latest.get("net_income"))
    out["pbr"] = calc.pbr(mc, latest.get("total_equity"))
    out["psr"] = calc.psr(mc, latest.get("revenue"))
    out["price_to_owner_earnings"] = calc._safe_div(mc, out["owner_earnings_normalised"])

    # ---- DCF --------------------------------------------------------------
    base_oe = out["owner_earnings_normalised"]
    hist_g = out.get("owner_earnings_cagr")
    dcf = {}
    for name, mult, disc, tg in SCENARIOS:
        cap = GROWTH_CAP_OPTIMISTIC if name == "optimistic" else GROWTH_CAP
        g = 0.03 if hist_g is None else max(0.0, min(hist_g * mult, cap))
        s = calc.DCFScenario(name, g, disc, tg, years=10)
        r = calc.dcf_intrinsic_value(base_oe if (base_oe or 0) > 0 else None, s)
        dcf[name] = {
            "intrinsic_value": r.intrinsic_value,
            "assumptions": r.assumptions,
            "margin_of_safety": calc.margin_of_safety(r.intrinsic_value, mc),
            "verdict": calc.verdict_from_margin(calc.margin_of_safety(r.intrinsic_value, mc)),
        }
    out["dcf"] = dcf

    # The same three scenarios run on maintenance-capex owner earnings. Reported
    # as the upper bound of a band, never on its own: it assumes every dollar of
    # capex above depreciation buys growth rather than standing still, which is
    # the most generous reading a Buffett framework permits.
    base_oe_m = out.get("owner_earnings_normalised_maintenance")
    dcf_m = {}
    for name, mult, disc, tg in SCENARIOS:
        cap = GROWTH_CAP_OPTIMISTIC if name == "optimistic" else GROWTH_CAP
        g = 0.03 if hist_g is None else max(0.0, min(hist_g * mult, cap))
        rr = calc.dcf_intrinsic_value(base_oe_m if (base_oe_m or 0) > 0 else None,
                                      calc.DCFScenario(name, g, disc, tg, years=10))
        dcf_m[name] = {
            "intrinsic_value": rr.intrinsic_value,
            "margin_of_safety": calc.margin_of_safety(rr.intrinsic_value, mc),
            "verdict": calc.verdict_from_margin(calc.margin_of_safety(rr.intrinsic_value, mc)),
        }
    out["dcf_maintenance_capex"] = dcf_m
    out["intrinsic_value_band_base"] = {
        "lower_total_capex": dcf["base"]["intrinsic_value"],
        "upper_maintenance_capex": dcf_m["base"]["intrinsic_value"],
        "market_cap": mc,
        "note": "lower bound charges the whole capital budget against owner earnings, "
                "upper bound charges only depreciation; the truth is between them",
    }
    # The discount rate at which today's price equals intrinsic value - i.e. the
    # annual return the market price implies, if the growth assumptions hold.
    # This inverts the usual question. Instead of "is this inside a 30% margin of
    # safety", which returns a verdict of no for almost every mega-cap in an
    # expensive market and stops the conversation, it asks what return you are
    # being offered, which can be compared against the risk-free rate and against
    # the other forty-nine names.
    def implied_return(base, growth, terminal):
        if not base or base <= 0 or not mc:
            return None
        lo, hi = terminal + 0.0005, 0.60
        for _ in range(120):
            mid = (lo + hi) / 2
            iv = calc.dcf_intrinsic_value(
                base, calc.DCFScenario("implied", growth, mid, terminal, 10)).intrinsic_value
            if iv is None:
                return None
            lo, hi = (mid, hi) if iv > mc else (lo, mid)
        return (lo + hi) / 2

    g_base = dcf["base"]["assumptions"]["growth_rate"]
    out["implied_return_total_capex"] = implied_return(base_oe, g_base, 0.025)
    out["implied_return_maintenance_capex"] = implied_return(base_oe_m, g_base, 0.025)
    out["implied_return_note"] = (
        f"annual return implied by the current price at {g_base:.1%} owner-earnings growth "
        f"for ten years then 2.5%; compare against the {rf:.2%} risk-free rate")

    # Net cash is reported rather than added to intrinsic value: owner earnings
    # already include the interest it earns, so adding the principal on top
    # would double-count part of it. A reader who thinks the pile is
    # redeployable can add it themselves.
    lat = rows[-1] if rows else {}
    if lat.get("cash") is not None and lat.get("interest_bearing_debt") is not None:
        out["net_cash"] = lat["cash"] - lat["interest_bearing_debt"]
    else:
        out["net_cash"] = None

    # Separate the three reasons a DCF produced nothing. A bank has no owner
    # earnings by construction, a company spending more on plant than it earns
    # has negative ones as a finding about the business, and only the third case
    # is a hole in the data. Reporting all three as DATA_UNAVAILABLE would hide
    # the most interesting of them.
    if fin:
        out["valuation_status"] = "FRAMEWORK_NOT_APPLICABLE"
        out["valuation_note"] = ("owner earnings are not defined for a financial: capex "
                                 "and working capital do not describe how it deploys capital")
    elif base_oe is not None and base_oe <= 0:
        out["valuation_status"] = "NEGATIVE_OWNER_EARNINGS"
        out["valuation_note"] = (
            f"normalised owner earnings are negative ({base_oe/1e9:.1f}bn): capital "
            f"spending plus working capital exceed reported profit, so there is no "
            f"positive stream to discount. A finding about the business, not a data gap.")
    elif base_oe is None:
        out["valuation_status"] = "DATA_UNAVAILABLE"
        out["valuation_note"] = "insufficient inputs to construct owner earnings"
    else:
        out["valuation_status"] = "VALUED"
        out["valuation_note"] = None
    out["dcf_growth_basis"] = (
        f"historical owner-earnings CAGR {hist_g:.1%} ({out.get('owner_earnings_cagr_window')}), "
        f"scaled per scenario and capped" if hist_g is not None else
        "no owner-earnings history; 3% placeholder growth used and the result should "
        "be read as indicative only")
    out["verdict_base"] = dcf["base"]["verdict"]
    return out


def main():
    with open(os.path.join(WORK, "universe.json")) as f:
        uni = json.load(f)
    with open(os.path.join(WORK, "market.json")) as f:
        market = json.load(f)

    cover_path = os.path.join(WORK, "cover_shares.json")
    cover = json.load(open(cover_path)) if os.path.exists(cover_path) else {}

    us = [c for c in uni["companies"] if c.get("analysis_mode") == "QUANTITATIVE"]
    sic = load_sic(us)

    rf = market["risk_free_rate"].get("rate")
    erp = market["equity_risk_premium"].get("erp")
    print(f"risk-free {rf:.2%}, ERP {erp:.2%}")

    results = []
    for c in us:
        path = os.path.join(RAW, f"{c['ticker']}.json")
        if not os.path.exists(path):
            print(f"[{c['ticker']}] no raw file - skipping", file=sys.stderr)
            continue
        with open(path) as f:
            raw = json.load(f)
        rec = analyse_company(c, raw, market["companies"].get(c["ticker"], {}),
                              sic.get(str(c["cik"]), {}), cover.get(c["ticker"], {}))
        rec["summary"] = summarise(rec, rf, erp)
        results.append(rec)
        s = rec["summary"]
        roic = f"{s['roic_latest']:.1%}" if s["roic_latest"] is not None else "n/a"
        wacc = f"{s['wacc']:.1%}" if s["wacc"] is not None else "n/a"
        print(f"[{c['ticker']:<6}] {rec['sector_treatment']:<9} ROIC {roic:>7} "
              f"WACC {wacc:>6}  {s['verdict_base']}")

    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "risk_free_rate": market["risk_free_rate"],
        "equity_risk_premium": market["equity_risk_premium"],
        "method_notes": {
            "ebit": "pretax income + interest expense where both are tagged, else the "
                    "reported operating-income subtotal; recorded per year",
            "returns_denominator": "average of opening and closing capital",
            "financials": "SIC 6000-6799 excluded from ROIC and owner earnings",
            "dcf_base": "median owner earnings of the last three years",
        },
        "companies": results,
    }
    with open(os.path.join(WORK, "analysis.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n{len(results)} companies -> work/analysis.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
