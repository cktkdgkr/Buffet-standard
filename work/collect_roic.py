"""
Return on invested capital for the fifty US companies, rebuilt from scratch.

This is deliberately a second, independent path to the same number. The earlier
study read the figures out of each 10-K's inline XBRL in work/collect_sec.py;
this one reads them from the SEC's companyfacts API, which serves the same
filings' tagged facts through a different endpoint and a different code path.
Two independent derivations that agree are evidence the number is right. Where
they disagree, the disagreement locates a bug in one of them - which is the
point of doing it twice.

The definition is the one the earlier audit settled on, and it is not changed
here, because changing the definition and the data path at the same time would
make any difference impossible to attribute:

    NOPAT            = reported operating income x (1 - effective tax rate)
    invested capital = total equity + interest-bearing debt - cash and
                       marketable securities
    ROIC             = NOPAT / average invested capital

Two points about that definition are worth restating, since both were
corrections rather than defaults. The numerator is the *reported operating
income* subtotal, not pretax income plus interest expense: the latter pulls
interest income and investment gains into the numerator while the denominator
subtracts the cash that produced them, which overstated Alphabet's FY2025 ROIC
by a quarter and flipped Intel's FY2024 sign. And cash is cash plus marketable
securities, because the 2007 letter's test is the capital "required to conduct
the business", and a Treasury portfolio is not.

Financial companies (SIC 6000-6799) are carried but flagged: for a bank, debt
is raw material rather than financing, so invested capital does not mean the
same thing.

Writes work/roic/roic_raw.json. Nothing in the file is derived - that is
analyse_roic.py's job.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "roic")
OUT = os.path.join(OUT_DIR, "roic_raw.json")
CACHE = os.path.join(OUT_DIR, "cache")

UA = "Buffett-standard research cktkdgkr@gmail.com"

# Tag priority per concept. The first tag that yields a value for a fiscal year
# wins, and which one won is recorded so a reader can see what was used.
CONCEPTS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
    ],
    # Several companies - notably pharma and oil - present an income statement
    # with no operating-income subtotal at all. These are the pieces one can be
    # built from; build_operating_income() in analyse_roic.py says how, and
    # records which route each company-year took.
    "costs_and_expenses": ["CostsAndExpenses"],
    "gross_profit": ["GrossProfit"],
    "operating_expenses": ["OperatingExpenses"],
    "cost_of_revenue": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
    ],
    "research_and_development": [
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
    ],
    # The remaining operating lines, needed to rebuild the subtotal for the
    # five non-financial companies that file no operating income at all. The
    # list is not a guess: it is what Lilly, Merck, J&J, IBM and KLA actually
    # tag, and build_operating_income()'s route V proves the list is complete
    # for a given year by adding the non-operating items back and checking the
    # result against the pretax income those companies do file.
    "acquired_iprd": [
        "ResearchAndDevelopmentInProcess",
        "AcquiredInProcessResearchAndDevelopment",
        "BusinessCombinationAcquiredInProcessResearchAndDevelopment",
    ],
    "restructuring": [
        "RestructuringCharges",
        "RestructuringSettlementAndImpairmentProvisions",
    ],
    "amortization_intangibles": ["AmortizationOfIntangibleAssets"],
    "impairment": [
        "GoodwillAndIntangibleAssetImpairment",
        "AssetImpairmentCharges",
    ],
    "litigation": ["LitigationSettlementExpense"],
    "other_nonoperating_detail": ["OtherNonoperatingIncomeExpense"],
    "equity_method_income": ["IncomeLossFromEquityMethodInvestments"],
    "gain_on_sale_of_business": ["GainLossOnSaleOfBusiness"],
    "selling_general_admin": [
        "SellingGeneralAndAdministrativeExpense",
        "GeneralAndAdministrativeExpense",
    ],
    "selling_and_marketing": [
        "SellingAndMarketingExpense",
        "MarketingExpense",
    ],
    "nonoperating_income": [
        "NonoperatingIncomeExpense",
        "OtherNonoperatingIncomeExpense",
    ],
    "investment_income_interest": [
        "InvestmentIncomeInterest",
        "InvestmentIncomeInterestAndDividend",
    ],
    # Only totals here. "...BeforeIncomeTaxesDomestic" and "...Foreign" are the
    # geographic split of the same line and reading either as the total would
    # understate the company by whatever the other region earned.
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "income_tax_expense": [
        "IncomeTaxExpenseBenefit",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    "interest_expense": [
        "InterestExpense",
        "InterestExpenseDebt",
        "InterestIncomeExpenseNet",
        "InterestExpenseNonoperating",
    ],
    # Balance sheet, instant.
    # Operating income is consolidated, so the capital it earns on should be
    # consolidated too - the including-NCI figure. Both are collected and
    # analyse_roic.py reports the gap, which is immaterial for all but a few.
    "total_equity": [
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "StockholdersEquity",
    ],
    "equity_parent_only": [
        "StockholdersEquity",
    ],
    "cash_and_equivalents": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    # One tag gives cash and short-term investments already added up, and where
    # a company files it it is the most reliable source for the subtraction.
    # It is kept as its own concept so build_cash() can prefer it.
    "cash_and_sti_combined": [
        "CashCashEquivalentsAndShortTermInvestments",
    ],
    # Otherwise the current investments line has to be found, and the tag for
    # it moves: Alphabet used AvailableForSaleSecuritiesCurrent through FY2017
    # and MarketableSecuritiesCurrent after it.
    #
    # Every tag here is a balance-sheet line. The maturity schedule's
    # within-one-year column looks like a substitute and is not one: it covers
    # the whole available-for-sale portfolio, including the part classified as
    # non-current and the restricted part. For Lam Research FY2019 it reads
    # $4,844m against $1,106m of current investments actually on the balance
    # sheet, and subtracting it left $327m of average invested capital and a
    # ROIC of 675% instead of roughly 44%. It was in this list as a last resort
    # because it happened to match Nvidia; it is now out.
    "short_term_investments": [
        "ShortTermInvestments",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
        "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesCurrent",
        "OtherShortTermInvestments",
        # Lam Research labels its current securities line plainly as
        # "Investments" ($1,773.0m at June 2019). The tag is last because at
        # some filers it carries a total that includes non-current holdings;
        # the cash-cannot-exceed-current-assets tripwire in verify_roic.py is
        # what stands behind it.
        "Investments",
    ],
    "long_term_investments": [
        "LongTermInvestments",
        "MarketableSecuritiesNoncurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent",
    ],
    "long_term_debt_noncurrent": [
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermNotesAndLoans",
        "LongTermNotesPayable",
        "SeniorNotesNoncurrent",
    ],
    "long_term_debt_current": [
        "LongTermDebtCurrent",
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
    ],
    "short_term_debt": [
        "ShortTermBorrowings",
        "CommercialPaper",
        "OtherShortTermBorrowings",
        "NotesPayableCurrent",
    ],
    "long_term_debt_total": [
        "LongTermDebt",
    ],
    # Named for what it is: the whole of it, current portion included. Kept
    # apart from LongTermDebt so build_debt() can use it on its own and add
    # nothing. Oracle files this at $86,869m for May 2024 alongside a current
    # notes payable line of $10,605m that is already inside it; adding the two
    # put $10.6bn of debt into Oracle's capital twice.
    "debt_combined_total": [
        "DebtLongtermAndShorttermCombinedAmount",
    ],
    "debt_current_total": [
        "DebtCurrent",
    ],
    "goodwill": ["Goodwill"],
    "intangibles": [
        "IntangibleAssetsNetExcludingGoodwill",
        "FiniteLivedIntangibleAssetsNet",
    ],
    "total_assets": ["Assets"],
    # Not used in the ratio, but cash subtracted from capital cannot exceed
    # current assets - verify_roic.py uses it as a tripwire on the cash tags.
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "total_liabilities": ["Liabilities"],
}

DURATION = {"revenue", "operating_income", "pretax_income",
            "income_tax_expense", "net_income", "interest_expense",
            "costs_and_expenses", "gross_profit", "operating_expenses",
            "nonoperating_income", "investment_income_interest",
            "cost_of_revenue", "research_and_development",
            "selling_general_admin", "selling_and_marketing"}


def fetch_facts(cik):
    """companyfacts for one CIK, cached on disk so a rerun costs nothing."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"CIK{cik:010d}.json")
    if not (os.path.exists(path) and os.path.getsize(path) > 2000):
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
        subprocess.run(["curl", "-sS", "--compressed", "-A", UA, url,
                        "-o", path], check=True)
        time.sleep(0.15)           # stay well inside the SEC's rate limit
    with open(path) as fh:
        return json.load(fh)


def annual_series(facts, tags, duration):
    """
    One value per fiscal year, filled tag by tag in priority order.

    The fallback is per year, not per tag. An earlier version took the first tag
    that had any values at all, which meant a tag covering six of ten years
    blocked the remaining four from ever being filled - Visa and UnitedHealth
    came back with no equity on that logic, because they switch between
    StockholdersEquity and the including-noncontrolling-interests variant.

    Income-statement facts must come from a 10-K and span a real year (330-400
    days), so a quarter mis-tagged as FY cannot slip in. Balance-sheet facts
    accept a 10-Q as well, since a year-end instant is the same figure wherever
    it is filed; 10-K wins where both carry it. Where a period has been reported
    twice - an original filing and a later restatement - the latest filing wins,
    because that is the figure the company now stands behind.
    """
    us = facts.get("facts", {}).get("us-gaap", {})
    values, sources = {}, {}
    for tag in tags:
        node = us.get(tag)
        if not node:
            continue
        best = {}
        for unit, entries in node.get("units", {}).items():
            if unit != "USD":
                continue
            for e in entries:
                form = e.get("form")
                end = e.get("end")
                if not end:
                    continue
                if duration:
                    if form not in ("10-K", "10-K/A") or e.get("fp") != "FY":
                        continue
                    start = e.get("start")
                    if not start:
                        continue
                    days = (datetime.fromisoformat(end)
                            - datetime.fromisoformat(start)).days
                    if not 330 <= days <= 400:
                        continue
                    rank = 0
                else:
                    # A balance sheet date is a balance sheet date. The same
                    # audited year-end figures appear as comparatives in the
                    # following year's quarterly filings, and sometimes only
                    # there: Mastercard's FY2017 long-term debt is absent from
                    # every 10-K fact, so a 10-K-only rule returned zero debt
                    # for 2017 and a ROIC of 243% against the 113% and 256% on
                    # either side. 10-K still wins where both exist, and the
                    # extra quarter-end dates this admits are dropped later,
                    # because a period only becomes a fiscal year if an income
                    # statement came with it.
                    if form not in ("10-K", "10-K/A", "10-Q"):
                        continue
                    rank = 0 if form in ("10-K", "10-K/A") else 1
                prior = best.get(end)
                if (prior is None or rank < prior["rank"]
                        or (rank == prior["rank"]
                            and e.get("filed", "") > prior["filed"])):
                    best[end] = {"value": e["val"], "filed": e.get("filed", ""),
                                 "accn": e.get("accn"), "fy": e.get("fy"),
                                 "rank": rank, "form": form}
        for end, rec in best.items():
            if end not in values:          # earlier tags win, per year
                values[end] = rec
                sources[end] = tag
    return sources, values


def collect_company(ticker, cik, name):
    facts = fetch_facts(cik)
    series, tags_used = {}, {}
    for concept, tags in CONCEPTS.items():
        sources, values = annual_series(facts, tags, concept in DURATION)
        used = sorted(set(sources.values()))
        tags_used[concept] = used[0] if len(used) == 1 else used
        for end, rec in values.items():
            series.setdefault(end, {})[concept] = rec["value"]
            series[end].setdefault("_tag_" + concept, sources[end])
            series[end].setdefault("_accn", rec["accn"])
            series[end].setdefault("_filed", rec["filed"])
            series[end].setdefault("_sec_fy", rec["fy"])

    # A period end only counts as a fiscal year if the income statement is
    # there; balance-sheet-only dates are comparatives from a neighbouring
    # filing, not years of their own.
    years = []
    for end in sorted(series):
        row = series[end]
        if row.get("revenue") is None and row.get("operating_income") is None:
            continue
        row["period_end"] = end
        row["fiscal_year_label"] = fiscal_label(end)
        years.append(row)

    return {
        "ticker": ticker, "cik": cik, "company_name": name,
        "entity_name": facts.get("entityName"),
        "tags_used": tags_used,
        "years": years,
    }


def fiscal_label(end):
    """
    The calendar year a fiscal year is named for.

    A year ending in January through May is overwhelmingly named for the prior
    calendar year by the companies in this set (Nvidia's year to January 2026
    is its fiscal 2026 by its own naming, but Apple's to September 2025 is
    fiscal 2025). Rather than guess, the label here is simply the calendar year
    of the period end, with January and February pulled back a year so that a
    31 January close lands with the year it mostly covers. The comparison in
    verify_roic.py matches on period end, not on this label, so nothing
    downstream depends on the convention.
    """
    y, m = int(end[:4]), int(end[5:7])
    return y - 1 if m <= 2 else y


def main():
    with open(os.path.join(HERE, "analysis.json")) as fh:
        prior = json.load(fh)
    companies = [{"ticker": c["ticker"], "cik": c["cik"],
                  "name": c["company_name"],
                  "sic": c.get("sic"), "sic_description": c.get("sic_description")}
                 for c in prior["companies"]]

    out, failures = [], []
    for i, c in enumerate(companies, 1):
        try:
            rec = collect_company(c["ticker"], c["cik"], c["name"])
            rec["sic"] = c["sic"]
            rec["sic_description"] = c["sic_description"]
            rec["is_financial"] = bool(
                c["sic"] and 6000 <= int(c["sic"]) <= 6799)
            out.append(rec)
            print(f"  [{i:>2}/{len(companies)}] {c['ticker']:<6} "
                  f"{len(rec['years']):>2} 개 회계연도")
        except Exception as exc:                        # noqa: BLE001
            failures.append({"ticker": c["ticker"], "error": str(exc)})
            print(f"  [{i:>2}/{len(companies)}] {c['ticker']:<6} FAILED: {exc}")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump({
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "source": "SEC XBRL companyfacts API "
                      "(https://data.sec.gov/api/xbrl/companyfacts/)",
            "independent_of": "work/collect_sec.py, which reads the same "
                              "filings' inline XBRL directly",
            "concepts": CONCEPTS,
            "companies": out,
            "failures": failures,
        }, fh)
    print(f"\nwrote {OUT}  ({len(out)} 사, 실패 {len(failures)})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
