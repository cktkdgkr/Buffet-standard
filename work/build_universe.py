"""
Universe builder - the 52-company analysis set.

Selection rule (US 50): the 50 largest US-listed operating companies by market
capitalisation. Ranking for *selection* comes from a third-party market-cap
screen, which is recorded here as selection provenance only. No figure taken
from that screen is ever reported in the analysis: once a company is in the set,
every number about it is recomputed from SEC filings and exchange prices. Mixing
those two roles is what the brief's sourcing standard forbids, so they are kept
apart explicitly.

Korea 2 (005930 Samsung Electronics, 000660 SK hynix) are appended by mandate,
not by ranking, and are marked qualitative-only: OpenDART requires an API key
that this environment does not hold, so their quantitative line items cannot be
sourced to an audited filing.

Writes work/universe.json.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

UA = "Buffett52Analysis research cktkdgkr@gmail.com"
WORK = os.path.dirname(os.path.abspath(__file__))
SCREEN_URL = "https://companiesmarketcap.com/usa/largest-companies-in-the-usa-by-market-cap/"
TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
US_COUNT = 50

# Entities that appear on a market-cap screen but cannot be analysed under this
# framework, with the reason recorded so the exclusion is auditable rather than
# silent. Each exclusion promotes the next eligible company on the screen.
EXCLUDE = {
    "SPCX": "private company - SEC registrant with no 10-K/20-F ever filed, so no "
            "audited annual series exists (screen values private secondaries)",
}

# The SEC ticker file maps a ticker to whichever registrant currently claims it,
# which after a holding-company reorganisation is a shell with no filing history.
# These overrides point at the registrant that actually files the 10-K, verified
# against the submissions endpoint.
CIK_OVERRIDE = {
    "XOM": {
        "cik": 34088,
        "reason": "ticker XOM now resolves to ExxonMobil Holdings Corp (CIK 2115436), "
                  "a 2026 reorganisation holdco with zero 10-K filings. The operating "
                  "registrant with the audited annual history is EXXON MOBIL CORP.",
    },
}

KOREA = [
    {
        "ticker": "005930.KS",
        "local_code": "005930",
        "company_name": "Samsung Electronics Co., Ltd.",
        "exchange_country": "KR",
        "analysis_mode": "QUALITATIVE_ONLY",
        "reason": (
            "Not an SEC registrant. Audited financials are filed with DART, whose "
            "API requires a key not available in this environment, so no line item "
            "can be sourced to a primary filing at the standard applied to the US 50."
        ),
    },
    {
        "ticker": "000660.KS",
        "local_code": "000660",
        "company_name": "SK hynix Inc.",
        "exchange_country": "KR",
        "analysis_mode": "QUALITATIVE_ONLY",
        "reason": (
            "Not an SEC registrant. Audited financials are filed with DART, whose "
            "API requires a key not available in this environment, so no line item "
            "can be sourced to a primary filing at the standard applied to the US 50."
        ),
    },
]


def fetch_bytes(url: str, retries: int = 5) -> bytes:
    """GET with backoff. SEC answers bursts with 429, which is worth waiting out."""
    delay = 3
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 407):
                raise RuntimeError(f"EGRESS DENIED ({e.code}) for {url}") from e
            if e.code != 429 or attempt == retries - 1:
                raise
        except Exception:
            if attempt == retries - 1:
                raise
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"unreachable: {url}")


def parse_screen(html: str):
    """Pull (rank, name, ticker, screen_market_cap_usd) out of the screen table."""
    out = []
    for row in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        rank = re.search(r'class="rank-td td-right" data-sort="(\d+)"', row)
        name = re.search(r'class="company-name">([^<]*)<', row)
        code = re.search(r'class="company-code">(?:<span[^>]*></span>)?([^<]*)<', row)
        mcap = re.search(r'<td class="td-right" data-sort="(\d+)"><span class="currency-symbol-left">', row)
        if not (rank and name and code):
            continue
        out.append({
            "screen_rank": int(rank.group(1)),
            "screen_name": name.group(1).strip(),
            "ticker": code.group(1).strip().upper(),
            "screen_market_cap_usd": int(mcap.group(1)) if mcap else None,
        })
    out.sort(key=lambda r: r["screen_rank"])
    return out


def load_ticker_map():
    data = json.loads(fetch_bytes(TICKER_URL))
    return {v["ticker"].upper(): (v["cik_str"], v["title"]) for v in data.values()}


def main():
    html = fetch_bytes(SCREEN_URL).decode("utf-8", "replace")
    screen = parse_screen(html)
    if len(screen) < US_COUNT:
        print(f"screen returned only {len(screen)} rows - too few to pick {US_COUNT}",
              file=sys.stderr)
        return 1

    tmap = load_ticker_map()
    companies, skipped = [], []

    for row in screen:
        if len(companies) >= US_COUNT:
            break
        t = row["ticker"]
        if t in EXCLUDE:
            skipped.append({**row, "skip_reason": EXCLUDE[t]})
            continue
        # SEC lists dual-class tickers with a dash (BRK-B); the screen may use
        # either form, so try both before giving up.
        cik_entry = tmap.get(t) or tmap.get(t.replace(".", "-"))
        if not cik_entry:
            skipped.append({**row, "skip_reason": "no CIK in SEC ticker map (not an SEC registrant)"})
            continue
        cik, sec_name = cik_entry
        entry = {
            "ticker": t,
            "cik": cik,
            "company_name": sec_name,
            "exchange_country": "US",
            "analysis_mode": "QUANTITATIVE",
            "selection": {
                "criterion": f"top {US_COUNT} US-listed companies by market capitalisation",
                "screen_rank": row["screen_rank"],
                "screen_market_cap_usd": row["screen_market_cap_usd"],
                "screen_source": SCREEN_URL,
                "screen_role": (
                    "SELECTION ONLY - this market cap decides set membership and is "
                    "never reported as an analysis figure. Reported market cap is "
                    "recomputed as SEC share count x exchange close."
                ),
            },
        }
        if t in CIK_OVERRIDE:
            ov = CIK_OVERRIDE[t]
            entry["cik_override"] = {"ticker_map_cik": cik, "reason": ov["reason"]}
            entry["cik"] = ov["cik"]
        companies.append(entry)

    universe = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "us_count": len(companies),
        "kr_count": len(KOREA),
        "total": len(companies) + len(KOREA),
        "selection_rule": {
            "us": f"top {US_COUNT} US-listed companies by market capitalisation, "
                  f"screened {datetime.now(timezone.utc).date().isoformat()}",
            "kr": "mandated by the brief, not by ranking",
        },
        "skipped_from_screen": skipped,
        "companies": companies + KOREA,
    }

    path = os.path.join(WORK, "universe.json")
    with open(path, "w") as f:
        json.dump(universe, f, indent=2, ensure_ascii=False)

    print(f"universe: {len(companies)} US + {len(KOREA)} KR = {universe['total']} -> {path}")
    if skipped:
        print(f"skipped {len(skipped)} screen rows:")
        for s in skipped:
            print(f"  #{s['screen_rank']:>3} {s['ticker']:<8} {s['skip_reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
