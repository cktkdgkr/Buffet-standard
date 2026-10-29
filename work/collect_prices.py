"""
Today's closing price for a ticker, with the date it belongs to.

The earlier study stored a price and no refresh path, so the Tesla figure in
analysis.json is still the 10 August close - eighty days stale by the time
anyone read the valuation built on it. A price is the one input that is stale
the moment it is written, so this always refetches and always reports as-of.

    python3 collect_prices.py TSLA SPCX
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "roic", "prices.json")
# A neutral User-Agent, deliberately. The SEC asks filers' tools to identify
# themselves with contact details and sec_cache.py does that, but a market-data
# host is an unrelated service and has no business receiving the account
# holder's email address. (It also rejects that header: the request returns an
# error, which is how this was noticed.)
UA = "Mozilla/5.0 (compatible; portfolio-research/1.0)"
CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/"
         "{t}?range=5d&interval=1d")


def quote(ticker):
    url = CHART.format(t=ticker)
    raw = subprocess.run(["curl", "-sS", "--fail", "-A", UA, url],
                         capture_output=True, check=True).stdout
    d = json.loads(raw)
    res = d["chart"]["result"][0]
    meta = res["meta"]
    stamps = res.get("timestamp") or []
    closes = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") \
        or []
    # The last stamp with a close; an in-progress session can carry a null.
    last = None
    for ts, close in zip(stamps, closes):
        if close is not None:
            last = (ts, close)
    if last is None:
        raise SystemExit(f"{ticker}: 종가 없음")
    ts, close = last
    as_of = datetime.fromtimestamp(ts, tz=timezone.utc)
    return {
        "ticker": ticker,
        "price": close,
        "currency": meta.get("currency"),
        "exchange": meta.get("fullExchangeName"),
        "as_of_utc": as_of.isoformat(),
        "regular_market_price": meta.get("regularMarketPrice"),
        "fifty_two_week_high": meta.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": meta.get("fiftyTwoWeekLow"),
        "source_url": url,
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
    }


def main():
    tickers = sys.argv[1:] or ["TSLA", "SPCX"]
    existing = {}
    if os.path.exists(OUT):
        with open(OUT) as fh:
            existing = json.load(fh).get("prices", {})

    for t in tickers:
        try:
            q = quote(t)
        except Exception as exc:                               # noqa: BLE001
            print(f"  {t:<6}실패: {exc}")
            continue
        existing[t] = q
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(q["as_of_utc"])).total_seconds() / 3600
        print(f"  {t:<6}{q['price']:>10,.2f} {q['currency']}  "
              f"{q['exchange']}  종가 {q['as_of_utc'][:10]} "
              f"({age:.0f}시간 전)  52주 {q['fifty_two_week_low']:,.0f}"
              f"~{q['fifty_two_week_high']:,.0f}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump({"fetched_utc": datetime.now(timezone.utc).isoformat(),
                   "prices": existing}, fh, indent=1, ensure_ascii=False)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
