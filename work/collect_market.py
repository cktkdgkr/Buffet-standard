"""
A1 (market leg) - the inputs valuation needs that a 10-K does not carry.

Three things: the share price that turns an audited share count into a market
capitalisation, the equity beta that prices risk in CAPM, and the two
macro constants (risk-free rate, equity risk premium) that the whole discount
rate is built on.

Beta is regressed here rather than copied from a data vendor, because a quoted
beta carries an undisclosed window and benchmark and cannot be reconciled to
anything. This one is monthly returns against the S&P 500 over five years, and
the window, observation count and R-squared are written out with it.

Writes work/market.json.
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
CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={iv}"
BENCHMARK = "^GSPC"
FRED_DGS10 = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
ERP_URL = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html"
MIN_BETA_OBS = 24          # under two years of monthly data, a beta is noise


def fetch(url: str, retries: int = 5) -> bytes:
    delay = 2
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 407):
                raise RuntimeError(f"EGRESS DENIED ({e.code}) for {url}") from e
            if e.code == 404 or attempt == retries - 1:
                raise
        except Exception:
            if attempt == retries - 1:
                raise
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"unreachable: {url}")


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------

def chart(sym: str, rng: str, iv: str):
    url = CHART.format(sym=urllib.request.quote(sym), rng=rng, iv=iv)
    j = json.loads(fetch(url))
    res = (j.get("chart") or {}).get("result")
    if not res:
        return None, url
    return res[0], url


def latest_price(sym: str):
    """Most recent close, with the timestamp it belongs to."""
    r, url = chart(sym, "5d", "1d")
    if not r:
        return {"status": "DATA_UNAVAILABLE", "source_url": url}
    meta = r.get("meta", {})
    px = meta.get("regularMarketPrice")
    ts = meta.get("regularMarketTime")
    return {
        "price": px,
        "currency": meta.get("currency"),
        "exchange": meta.get("fullExchangeName"),
        "as_of_utc": datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None,
        "source_url": url,
        "confidence": "HIGH" if px is not None else "LOW",
    }


def splits(sym: str):
    """
    Split history, needed to put a share-count series on one basis.

    A company's share count for a given year comes from the 10-K filed that
    year, in the units of that year. A 10-K restates only two prior years, so
    anything older keeps its pre-split count, and a series spanning a split
    reads as explosive share issuance: NVIDIA's 4:1 and 10:1 splits make it look
    like 41% annual dilution when it has in fact been buying stock back. That
    inverts the capital-allocation judgment entirely.
    """
    url = CHART.format(sym=urllib.request.quote(sym), rng="25y", iv="1mo") + "&events=split"
    try:
        j = json.loads(fetch(url))
    except Exception:                                   # noqa: BLE001
        return {"status": "DATA_UNAVAILABLE", "source_url": url}
    res = (j.get("chart") or {}).get("result")
    if not res:
        return {"status": "DATA_UNAVAILABLE", "source_url": url}
    events = (res[0].get("events") or {}).get("splits") or {}
    out = []
    for ts, ev in events.items():
        num, den = ev.get("numerator"), ev.get("denominator")
        if not num or not den:
            continue
        out.append({
            "date": datetime.fromtimestamp(int(ts), timezone.utc).date().isoformat(),
            "ratio": num / den,
            "as_stated": ev.get("splitRatio"),
        })
    out.sort(key=lambda s: s["date"])
    return {"status": "OK", "splits": out, "source_url": url}


def monthly_closes(sym: str):
    r, url = chart(sym, "5y", "1mo")
    if not r:
        return None, url
    ts = r.get("timestamp") or []
    quote = (r.get("indicators", {}).get("quote") or [{}])[0]
    adj = (r.get("indicators", {}).get("adjclose") or [{}])
    closes = (adj[0].get("adjclose") if adj and adj[0].get("adjclose") else quote.get("close")) or []
    out = [(t, c) for t, c in zip(ts, closes) if c is not None]
    return out, url


def returns(series):
    return {series[i][0]: series[i][1] / series[i - 1][1] - 1.0
            for i in range(1, len(series)) if series[i - 1][1]}


def regress_beta(stock, market):
    """OLS slope of stock returns on market returns, on their common months."""
    rs, rm = returns(stock), returns(market)
    # Yahoo stamps monthly bars at the exchange's month start, so align on the
    # calendar month rather than the raw epoch.
    key = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m")
    ms = {key(t): v for t, v in rs.items()}
    mm = {key(t): v for t, v in rm.items()}
    months = sorted(set(ms) & set(mm))
    n = len(months)
    if n < MIN_BETA_OBS:
        return {"beta": None, "observations": n, "status": "INSUFFICIENT_HISTORY",
                "note": f"{n} common monthly returns, need {MIN_BETA_OBS}"}
    xs = [mm[m] for m in months]
    ys = [ms[m] for m in months]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return {"beta": None, "observations": n, "status": "DEGENERATE"}
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    beta = sxy / sxx
    syy = sum((y - my) ** 2 for y in ys)
    r2 = (sxy ** 2) / (sxx * syy) if syy else None
    return {
        "beta": beta,
        "observations": n,
        "r_squared": r2,
        "window": f"{months[0]}..{months[-1]}",
        "method": "OLS of monthly total returns on S&P 500 monthly total returns",
        "benchmark": BENCHMARK,
        "status": "OK",
    }


# ---------------------------------------------------------------------------
# Macro constants
# ---------------------------------------------------------------------------

def risk_free_rate():
    """10-year Treasury constant maturity - the standard long-horizon risk-free."""
    csv = fetch(FRED_DGS10).decode()
    rows = [ln.split(",") for ln in csv.strip().splitlines()[1:]]
    rows = [(d, v) for d, v in rows if v not in (".", "")]
    if not rows:
        return {"status": "DATA_UNAVAILABLE", "source_url": FRED_DGS10}
    d, v = rows[-1]
    return {
        "rate": float(v) / 100.0,
        "as_of": d,
        "series": "DGS10 (10-Year Treasury Constant Maturity Rate)",
        "source_url": FRED_DGS10,
        "confidence": "HIGH",
    }


def equity_risk_premium():
    html = fetch(ERP_URL).decode("utf-8", "replace")
    updated = re.search(r"Last updated:\s*([A-Za-z]+ \d+, \d{4})", re.sub(r"<[^>]+>", " ", html))
    hdr, us = None, None
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).replace("\xa0", " ").strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if cells and cells[0] == "Country":
            hdr = cells
        if cells and cells[0] == "United States":
            us = cells
    if not (hdr and us) or "Equity Risk Premium" not in hdr:
        return {"status": "DATA_UNAVAILABLE", "source_url": ERP_URL,
                "reason": "US row or ERP column not found; page layout changed"}
    erp = us[hdr.index("Equity Risk Premium")]
    return {
        "erp": float(erp.rstrip("%")) / 100.0,
        "country": "United States",
        "as_of": updated.group(1) if updated else None,
        "source_url": ERP_URL,
        "source_note": "Damodaran (NYU Stern) implied equity risk premium",
        "confidence": "HIGH",
    }


# ---------------------------------------------------------------------------

def main():
    with open(os.path.join(WORK, "universe.json")) as f:
        uni = json.load(f)

    print("macro inputs...")
    rf = risk_free_rate()
    erp = equity_risk_premium()
    print(f"  risk-free: {rf.get('rate')} ({rf.get('as_of')})")
    print(f"  ERP:       {erp.get('erp')} ({erp.get('as_of')})")

    print(f"benchmark {BENCHMARK}...")
    bench, bench_url = monthly_closes(BENCHMARK)
    if not bench:
        print("  benchmark unavailable - betas cannot be regressed", file=sys.stderr)

    companies = {}
    for c in uni["companies"]:
        sym = c["ticker"]
        # SEC writes dual-class tickers with a dash, Yahoo with a hyphen too,
        # but the screen may hand us a dot form.
        ysym = sym.replace(".", "-") if c["exchange_country"] == "US" else sym
        print(f"[{sym}] price + beta...")
        rec = {"ticker": sym, "yahoo_symbol": ysym, "price": latest_price(ysym),
               "splits": splits(ysym)}
        if bench:
            stock, surl = monthly_closes(ysym)
            rec["beta"] = regress_beta(stock, bench) if stock else {
                "beta": None, "status": "DATA_UNAVAILABLE"}
            rec["beta"]["source_url"] = surl
            rec["beta"]["benchmark_source_url"] = bench_url
        companies[sym] = rec
        time.sleep(0.3)

    out = {
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "risk_free_rate": rf,
        "equity_risk_premium": erp,
        "companies": companies,
    }
    path = os.path.join(WORK, "market.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    ns = sum(1 for r in companies.values() if (r.get("splits") or {}).get("splits"))
    print(f"companies with split history: {ns}")
    ok = sum(1 for r in companies.values() if r["price"].get("price") is not None)
    nb = sum(1 for r in companies.values() if (r.get("beta") or {}).get("beta") is not None)
    print(f"\nprices {ok}/{len(companies)}, betas {nb}/{len(companies)} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
