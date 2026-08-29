"""
A1 Filing Collector - SEC EDGAR XBRL.

Pulls audited financial data straight from the XBRL facts that companies file
with their 10-K/10-Q, so every figure carries the accession number of the filing
it came from. That provenance is what lets a figure qualify for the top
confidence grade; a number without it cannot.

Writes work/raw/{ticker}.json.

Usage:
    python3 collect_sec.py --probe                 # check access, exit
    python3 collect_sec.py --tickers AAPL MSFT     # collect named tickers
    python3 collect_sec.py --universe work/universe.json

Requires the egress allowlist to include data.sec.gov and www.sec.gov.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

UA = "Buffett52Analysis research cktkdgkr@gmail.com"
RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

# Concepts we need, with fallbacks. Filers tag the same economic line
# differently (and change tags between years), so each metric lists candidate
# us-gaap tags in priority order and we take the first that yields data.
CONCEPTS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "RevenuesNetOfInterestExpense",
        "SalesRevenueNet",
    ],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquireOtherPropertyPlantAndEquipment",
    ],
    # Lets owner earnings be cross-checked as (operating cash flow - capex),
    # which already embeds D&A and the working-capital swing. Useful where the
    # current-asset/liability split needed for the direct formula is absent,
    # as it is for banks.
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "total_assets": ["Assets"],
    "total_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    # Cash alone is the wrong measure of a company's liquid position. Alphabet
    # holds $30.7bn as "cash and equivalents" and another $96bn in current
    # marketable securities; treating only the first as cash overstates its
    # invested capital by roughly a hundred billion dollars and understates its
    # ROIC to match. The combined tag is preferred where a filer publishes it,
    # and short-term investments are collected separately so the analysis can
    # add them where it does not.
    "cash_and_equivalents": [
        "CashCashEquivalentsAndShortTermInvestments",
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "short_term_investments": [
        "MarketableSecuritiesCurrent",
        "ShortTermInvestments",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
        "OtherShortTermInvestments",
    ],
    # Ordered most-inclusive first. Filers split borrowings across several tags
    # (Coca-Cola carries commercial paper separately from the current portion of
    # long-term debt), and only one tag is taken, so the broadest wins. Note
    # that tags naming "debt securities" are investments the company HOLDS, not
    # money it owes, and are deliberately absent from both lists.
    "short_term_debt": [
        "DebtCurrent",
        "ShortTermBorrowings",
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "LongTermDebtCurrent",
        "ConvertibleDebtCurrent",
        "OtherShortTermBorrowings",
        "CommercialPaper",
        "NotesPayableCurrent",
    ],
    "long_term_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebt",
        "ConvertibleDebtNoncurrent",
    ],
    # Buffett's stated denominator is "net tangible assets" - the 2007 letter
    # prices See's on "the capital required to conduct the business" and
    # contrasts $82m earned "on $400 million of net tangible assets". Goodwill
    # and acquired intangibles are collected so that basis can be built.
    "goodwill": ["Goodwill"],
    "intangible_assets": [
        "IntangibleAssetsNetExcludingGoodwill",
        "FiniteLivedIntangibleAssetsNet",
    ],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "interest_expense": [
        "InterestExpense",
        "InterestExpenseDebt",
        "InterestAndDebtExpense",
        "InterestExpenseNonoperating",
        "InterestExpenseOther",
        "InterestIncomeExpenseNet",
    ],
    # Needed to turn pretax income into EBIT for the filers that publish no
    # operating-income subtotal at all (see EBIT handling in analyse.py).
    "nonoperating_income": ["NonoperatingIncomeExpense", "OtherNonoperatingIncomeExpense"],
    # Operating cash flow adds stock compensation back as a non-cash charge.
    # Buffett does not: "If options aren't a form of compensation, what are they?
    # If compensation isn't an expense, what is it?" (1992 letter). Collected so
    # owner earnings can charge it rather than inherit the add-back.
    "share_based_compensation": [
        "ShareBasedCompensation",
        "AllocatedShareBasedCompensationExpense",
        "ShareBasedCompensationArrangementByShareBasedPaymentAwardCompensationCost",
    ],
    # Mark-to-market on investment portfolios runs through net income under
    # ASU 2016-01 and can swamp the operating result: Alphabet's FY2025 net
    # income carries $24.6bn of it. Buffett spends a paragraph of nearly every
    # recent letter telling shareholders to ignore exactly this line. Collected
    # so owner earnings can start from the business rather than the portfolio.
    "investment_gains": [
        "DebtAndEquitySecuritiesGainLoss",
        "EquitySecuritiesFvNiGainLoss",
        "GainLossOnInvestments",
        "MarketableSecuritiesGainLoss",
        "GainLossOnSaleOfInvestments",
        "RealizedInvestmentGainsLosses",
    ],
    "income_tax_expense": ["IncomeTaxExpenseBenefit"],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    # Oracle stops tagging a consolidated pretax total after FY2018 and publishes
    # only the domestic and foreign halves. Collected separately so the analysis
    # can add them back rather than silently falling through to a statutory tax
    # rate for a company that reports its actual one.
    "pretax_income_domestic": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic"],
    "pretax_income_foreign": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign"],
    "shares_outstanding": [
        "CommonStockSharesOutstanding",
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ],
}

# Flow concepts are period totals (annual duration); stock concepts are
# point-in-time balances. They are filtered differently below.
FLOW_METRICS = {
    "revenue", "operating_income", "net_income", "depreciation_amortization",
    "capex", "interest_expense", "income_tax_expense", "pretax_income",
    "operating_cash_flow", "nonoperating_income", "share_based_compensation",
    "investment_gains", "pretax_income_domestic", "pretax_income_foreign",
}

# Share counts are a cover-page disclosure, so some filers tag them only in the
# `dei` taxonomy and never in us-gaap. Metrics listed here fall back to dei.
DEI_FALLBACK = {"shares_outstanding": ["EntityCommonStockSharesOutstanding"]}


def fetch(url: str, retries: int = 4):
    """GET with backoff. Distinguishes policy denial from transient failure."""
    delay = 2
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept-Encoding": "gzip, deflate"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    data = gzip.decompress(data)
                return json.loads(data)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (403, 407):
                # Egress policy denial - retrying will not help.
                raise RuntimeError(
                    f"EGRESS DENIED ({e.code}) for {url}. "
                    "Add data.sec.gov and www.sec.gov to the environment allowlist."
                ) from e
            if e.code == 404:
                return None
        except Exception as e:                       # noqa: BLE001
            last = repr(e)
            # A policy denial surfaces as a failed CONNECT tunnel rather than an
            # HTTPError. Retrying it is pointless and the proxy asks us not to.
            if "Tunnel connection failed" in last and ("403" in last or "407" in last):
                raise RuntimeError(
                    f"EGRESS DENIED at proxy CONNECT for {url}. "
                    "Add data.sec.gov and www.sec.gov to the environment allowlist."
                ) from e
        if attempt < retries - 1:
            time.sleep(delay)
            delay *= 2
    print(f"    fetch failed after {retries} attempts: {url} ({last})", file=sys.stderr)
    return None


def load_ticker_map():
    data = fetch(TICKER_URL)
    if not data:
        raise RuntimeError("Could not load SEC ticker->CIK map.")
    return {v["ticker"].upper(): (v["cik_str"], v["title"]) for v in data.values()}


def _fiscal_year(end: str) -> int:
    """
    Label a period by the calendar year it mostly covers, from its own end date.

    NOT the `fy` field on the fact: that is the fiscal year of the *filing* the
    fact appeared in, and a 10-K restates two prior years, so three different
    fiscal years arrive carrying an identical `fy`. Keying on it collapses them
    into one bucket and silently drops two real years.

    A period ending in Jan-May is dated to the prior calendar year, so a
    retailer's year ending 2026-01-31 lines up with a calendar-year filer's
    2025 rather than being compared against 2026.
    """
    d = datetime.fromisoformat(end)
    return d.year if d.month >= 6 else d.year - 1


def _pick_annual(units, is_flow):
    """
    Reduce raw XBRL unit entries to one clean value per fiscal year.

    Keeps only annual-report figures so series are audited and internally
    consistent, takes ~365-day durations for flows (never a summed quarter),
    and for restated periods prefers the most recently filed value.
    """
    rows = []
    for u in units:
        if u.get("form") not in ("10-K", "20-F", "40-F"):
            continue
        end, val = u.get("end"), u.get("val")
        if not end or val is None:
            continue
        if is_flow:
            start = u.get("start")
            if not start:
                continue
            days = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days
            if not (330 <= days <= 400):      # annual duration only
                continue
        rows.append({
            "fiscal_year": _fiscal_year(end), "period_end": end, "value": val,
            "form": u.get("form"), "accession": u.get("accn"), "filed": u.get("filed"),
        })

    # Same period restated across filings -> keep the latest filed value.
    by_period = {}
    for r in rows:
        cur = by_period.get(r["period_end"])
        if cur is None or (r.get("filed") or "") > (cur.get("filed") or ""):
            by_period[r["period_end"]] = r

    # A 52/53-week calendar can put two period ends in one fiscal year; keep the
    # later one so the year is represented once.
    best = {}
    for r in by_period.values():
        cur = best.get(r["fiscal_year"])
        if cur is None or r["period_end"] > cur["period_end"]:
            best[r["fiscal_year"]] = r
    return [best[k] for k in sorted(best)]


def extract(facts, metric, tags):
    """
    Pick the candidate tag that best covers recent history, with provenance.

    Not simply the first tag that returns anything. Filers abandon tags: Tesla's
    LongTermDebtCurrent stops in 2012, Visa's StockholdersEquity in 2011, GE's
    CashAndCashEquivalentsAtCarryingValue in 2017, each superseded by a later
    tag. Taking the first non-empty hit locks onto the dead one and reports a
    decade-old balance sheet as current, so candidates are scored on how recent
    and how complete their series is, with the priority order breaking ties.
    """
    all_facts = facts.get("facts", {})
    candidates = [("us-gaap", t) for t in tags]
    candidates += [("dei", t) for t in DEI_FALLBACK.get(metric, [])]

    found = []
    for priority, (taxonomy, tag) in enumerate(candidates):
        node = all_facts.get(taxonomy, {}).get(tag)
        if not node:
            continue
        for unit_key in ("USD", "shares", "USD/shares"):
            if unit_key not in node.get("units", {}):
                continue
            series = _pick_annual(node["units"][unit_key], metric in FLOW_METRICS)
            if series:
                found.append({"taxonomy": taxonomy, "tag": tag, "unit": unit_key,
                              "series": series, "priority": priority,
                              "latest": series[-1]["fiscal_year"]})
                break

    if not found:
        return {
            "metric": metric, "xbrl_tag": None, "series": [],
            "status": "DATA_UNAVAILABLE",
            "confidence": "LOW",
            "confidence_reason": f"No usable tag found among {[c[1] for c in candidates]}.",
        }

    newest = max(f["latest"] for f in found)
    # Reaching the newest year matters most - a stale series is worse than a
    # short one. Then take the longest run, then the caller's stated priority.
    def score(f):
        recent = sum(1 for r in f["series"] if r["fiscal_year"] > newest - 10)
        return (f["latest"] == newest, recent, -f["priority"])

    best = max(found, key=score)
    rejected = [{"tag": f["tag"], "latest_fiscal_year": f["latest"], "years": len(f["series"])}
                for f in found if f is not best]

    # A filer that switches tags mid-history can leave the winner with a hole:
    # Alphabet reports revenue under Revenues through 2021 and again from 2023,
    # and under RevenueFromContractWithCustomer for 2022, so neither tag alone
    # covers the decade. A missing year is filled from another candidate only
    # when the two agree exactly on every year they share - if they track each
    # other everywhere they overlap they are the same series, and if they do not
    # the gap stays a gap rather than being papered over with a different
    # concept.
    filled = []
    by_year = {r["fiscal_year"]: r for r in best["series"]}
    for alt in found:
        if alt is best:
            continue
        alt_by_year = {r["fiscal_year"]: r for r in alt["series"]}
        shared = set(by_year) & set(alt_by_year)
        if len(shared) < 2:
            continue
        if any(by_year[y]["value"] != alt_by_year[y]["value"] for y in shared):
            continue
        for y in sorted(set(alt_by_year) - set(by_year)):
            if best["series"][0]["fiscal_year"] <= y <= best["latest"]:
                row = dict(alt_by_year[y])
                row["filled_from_tag"] = alt["tag"]
                by_year[y] = row
                filled.append({"fiscal_year": y, "from_tag": alt["tag"],
                               "agreed_on_years": sorted(shared)})
    if filled:
        best["series"] = [by_year[y] for y in sorted(by_year)]
    return {
        "metric": metric,
        "xbrl_tag": best["tag"],
        "taxonomy": best["taxonomy"],
        "unit": best["unit"],
        "series": best["series"],
        "source_url": None,          # filled by caller (company-level)
        "confidence": "HIGH",
        "confidence_reason": (
            f"Audited XBRL tag {best['taxonomy']}:{best['tag']} from the company's own "
            f"annual filing; each year carries its accession number."
        ),
        "tag_selection": {
            "chosen_because": "best coverage of recent fiscal years among candidates",
            "latest_fiscal_year": best["latest"],
            "years": len(best["series"]),
            "alternatives_rejected": rejected,
            "gaps_filled": filled,
        },
    }


def collect(ticker, cik, name):
    url = FACTS_URL.format(cik=cik)
    facts = fetch(url)
    if not facts:
        return {
            "ticker": ticker, "cik": cik, "company_name": name,
            "status": "DATA_UNAVAILABLE",
            "reason": "companyfacts returned no data after retries",
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    metrics = {}
    for metric, tags in CONCEPTS.items():
        m = extract(facts, metric, tags)
        m["source_url"] = url
        metrics[metric] = m

    found = sum(1 for m in metrics.values() if m.get("series"))
    return {
        "ticker": ticker,
        "cik": cik,
        "company_name": facts.get("entityName", name),
        "source_url": url,
        "source_document": "SEC EDGAR XBRL company facts (10-K derived)",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "metrics_found": f"{found}/{len(CONCEPTS)}",
        "metrics": metrics,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", default=[])
    ap.add_argument("--universe")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--refresh", action="store_true",
                    help="re-pull companies already present in work/raw")
    args = ap.parse_args()

    if args.probe:
        try:
            m = load_ticker_map()
            print(f"ACCESS OK - SEC ticker map loaded ({len(m)} tickers). "
                  f"AAPL -> CIK {m.get('AAPL')}")
            return 0
        except Exception as e:                        # noqa: BLE001
            print(f"ACCESS BLOCKED - {e}")
            return 1

    # (ticker, cik, name) triples. The universe file already carries a verified
    # CIK per company, including overrides where a ticker now resolves to a
    # reorganisation holdco with no filing history, so it wins over the ticker
    # map. Bare --tickers still fall back to the map.
    targets = []
    if args.universe:
        with open(args.universe) as f:
            uni = json.load(f)
        targets += [(c["ticker"], c["cik"], c["company_name"])
                    for c in uni.get("companies", [])
                    if c.get("exchange_country") == "US"
                    and c.get("analysis_mode") == "QUANTITATIVE"]

    if args.tickers:
        tmap = load_ticker_map()
        for t in args.tickers:
            t = t.upper()
            if t not in tmap:
                print(f"[{t}] not in SEC ticker map - skipping (non-US listing?)")
                continue
            cik, name = tmap[t]
            targets.append((t, cik, name))

    os.makedirs(RAW_DIR, exist_ok=True)
    failures = []

    for t, cik, name in targets:
        out = os.path.join(RAW_DIR, f"{t}.json")
        if os.path.exists(out) and not args.refresh:
            print(f"[{t}] cached - skipping (use --refresh to re-pull)")
            continue
        print(f"[{t}] CIK {cik} - collecting...")
        rec = collect(t, cik, name)
        with open(out, "w") as f:
            json.dump(rec, f, indent=2)
        found = rec.get("metrics_found", "FAILED")
        print(f"[{t}] {found} -> work/raw/{t}.json")
        if rec.get("status") == "DATA_UNAVAILABLE":
            failures.append(t)
        time.sleep(0.4)          # stay well inside SEC's fair-use rate limit

    if failures:
        print(f"\n{len(failures)} companies returned no data: {', '.join(failures)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
