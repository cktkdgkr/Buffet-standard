"""
A1 (share-count leg) - current shares outstanding from the 10-K cover page.

The companyfacts API drops any fact carrying a dimension, so a filer that tags
its share count per share class - Visa, Berkshire, and others - appears to have
no share count at all, or worse, a leftover undimensioned figure from years ago.
Visa's companyfacts share count is from 2009. Multiplying a live price by that
is how a market cap ends up wrong by a factor of four.

The cover page of the 10-K itself carries the number, tagged as inline XBRL with
an explicit class member, and it is dated later than the fiscal year end. This
reads it straight out of the filing document: the facts, the contexts they point
at, and the share class each context names.

Class shares are summed at their economic conversion ratio. For almost every
filer that ratio is 1 - Alphabet's A/B/C and Meta's A/B are all one share of
economic interest. Berkshire is the exception: a Class A share is 1,500 Class B
shares, so the total is expressed in B-equivalents to match a B quote. Ratios
that are neither 1 nor a disclosed constant (Visa's B-1, B-2 and C convert at
rates set periodically by its board) are not guessed; those classes are left out
and the shortfall is recorded on the record.

Writes work/cover_shares.json.
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
SHARE_TAG = "dei:EntityCommonStockSharesOutstanding"

# Conversion into the quoted share's units, keyed by ticker then XBRL class
# member. Absent tickers use ratio 1 for every class, which is right whenever
# the classes differ only in voting rights.
CLASS_RATIO = {
    "BRK-B": {
        # Berkshire's charter fixes Class A at 1,500 Class B shares. The quote
        # used for market cap is the B share, so A converts up.
        "CommonClassAMember": 1500.0,
        "CommonClassBMember": 1.0,
        "_note": "expressed in Class B equivalents (A = 1,500 B, per the charter)",
    },
    "V": {
        # Visa's B-1, B-2 and C convert at ratios its board resets as litigation
        # escrow is settled, so they are not a constant this script can source.
        "CommonClassAMember": 1.0,
        "_note": "Class A only; B-1/B-2/C excluded because their conversion rates "
                 "are periodically reset and not derivable from the cover page, so "
                 "the resulting market cap understates the as-converted total",
        "_incomplete": True,
    },
}


def fetch(url: str, retries: int = 6) -> bytes:
    delay = 4
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    data = gzip.decompress(data)
                return data
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


def latest_annual_report(cik: int):
    j = json.loads(fetch(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    rec = j["filings"]["recent"]
    for i, form in enumerate(rec["form"]):
        if form in ("10-K", "20-F", "40-F"):
            accn = rec["accessionNumber"][i].replace("-", "")
            doc = rec["primaryDocument"][i]
            return {
                "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/{doc}",
                "accession": rec["accessionNumber"][i],
                "form": form,
                "filed": rec["filingDate"][i],
            }
    return None


def parse_contexts(html: str):
    """context id -> the share-class member it names, if any."""
    out = {}
    for m in re.finditer(r'<(?:\w+:)?context[^>]*id="([^"]+)"(.*?)</(?:\w+:)?context>',
                         html, re.S | re.I):
        cid, body = m.group(1), m.group(2)
        # The member's namespace prefix can contain a hyphen (us-gaap:), which
        # \w does not cover, so both prefix and local name allow one.
        member = re.search(r'<(?:[\w-]+:)?explicitMember[^>]*>\s*(?:[\w-]+:)?([\w-]+)\s*<',
                           body, re.I)
        out[cid] = member.group(1) if member else None
    return out


def parse_share_facts(html: str):
    """Every cover-page share-count fact, with its scale and context applied."""
    facts = []
    pattern = (r'<ix:nonFraction([^>]*name="' + re.escape(SHARE_TAG) + r'"[^>]*)>(.*?)</ix:nonFraction>')
    for m in re.finditer(pattern, html, re.S | re.I):
        attrs, inner = m.group(1), m.group(2)
        raw = re.sub(r"<[^>]+>", "", inner).strip().replace(",", "").replace("\xa0", "")
        if not raw or not re.fullmatch(r"[\d.]+", raw):
            continue
        scale = re.search(r'scale="(-?\d+)"', attrs)
        ctx = re.search(r'contextRef="([^"]+)"', attrs)
        val = float(raw) * (10 ** int(scale.group(1))) if scale else float(raw)
        if re.search(r'sign="-"', attrs):
            val = -val
        facts.append({"value": val, "context": ctx.group(1) if ctx else None})
    return facts


def collect(ticker: str, cik: int):
    filing = latest_annual_report(cik)
    if not filing:
        return {"ticker": ticker, "status": "DATA_UNAVAILABLE",
                "reason": "no 10-K/20-F/40-F in recent filings"}
    html = fetch(filing["url"]).decode("utf-8", "replace")
    contexts = parse_contexts(html)
    facts = parse_share_facts(html)

    # A filing split across documents declares its contexts in only one of them.
    # Wells Fargo's cover page sits in the companion file and references a
    # context defined next door, so the share count arrives with no share class
    # attached. Pull the sibling documents in only when that actually happens.
    if facts and any(contexts.get(f["context"]) is None for f in facts):
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{filing['accession'].replace('-', '')}"
        try:
            index = json.loads(fetch(f"{base}/index.json"))
            primary_name = filing["url"].rsplit("/", 1)[-1]
            siblings = sorted(
                (i for i in index.get("directory", {}).get("item", [])
                 if i.get("name", "").endswith(".htm")
                 and not re.match(r"^R\d+\.htm$", i["name"])
                 and int(i.get("size") or 0) > 100_000
                 and i["name"] != primary_name),
                key=lambda i: int(i.get("size") or 0), reverse=True)
            siblings = [i["name"] for i in siblings]
            for name in siblings[:3]:
                time.sleep(0.5)
                contexts.update(parse_contexts(fetch(f"{base}/{name}").decode("utf-8", "replace")))
                if all(contexts.get(f["context"]) is not None for f in facts):
                    break
        except Exception:                               # noqa: BLE001
            pass                                        # keep the unresolved label
    if not facts:
        return {"ticker": ticker, "status": "DATA_UNAVAILABLE",
                "reason": f"no inline {SHARE_TAG} fact on the cover page",
                "source_url": filing["url"], **filing}

    ratios = CLASS_RATIO.get(ticker, {})
    by_class, total, skipped = {}, 0.0, []
    for f in facts:
        member = contexts.get(f["context"])
        if member:
            key = member
        elif f["context"] in contexts:
            key = "undimensioned"
        else:
            # Context did not resolve. Key by its id rather than pooling it with
            # everything else, so two unresolved classes cannot silently merge
            # and lose one of them.
            key = f"unresolved:{f['context']}"
        # The same class can be tagged twice at different precision; they are
        # the same figure, so keep one rather than double-counting.
        by_class[key] = max(by_class.get(key, 0.0), f["value"])

    for key, val in by_class.items():
        if key == "undimensioned":
            ratio = 1.0
        elif ratios:
            ratio = ratios.get(key)
            if ratio is None:
                skipped.append({"class": key, "shares": val,
                                "reason": "no sourced conversion ratio"})
                continue
        else:
            ratio = 1.0
        total += val * ratio

    # An undimensioned fact is already the whole company; do not add classes to it.
    if "undimensioned" in by_class and len(by_class) > 1:
        total = by_class["undimensioned"]

    as_of = re.search(r'name="dei:DocumentPeriodEndDate"[^>]*>([^<]+)<', html)
    return {
        "ticker": ticker,
        "status": "OK",
        "shares_outstanding": total,
        "by_class": by_class,
        "classes_excluded": skipped,
        "conversion_note": ratios.get("_note", "all classes summed at 1:1"),
        "incomplete": bool(ratios.get("_incomplete") or skipped),
        "document_period_end": as_of.group(1).strip() if as_of else None,
        "source_url": filing["url"],
        "accession": filing["accession"],
        "form": filing["form"],
        "filed": filing["filed"],
        "confidence": "HIGH",
        "confidence_reason": "read from the inline XBRL on the cover page of the "
                             "company's own annual report",
    }


def main():
    with open(os.path.join(WORK, "universe.json")) as f:
        uni = json.load(f)
    path = os.path.join(WORK, "cover_shares.json")
    out = json.load(open(path)) if os.path.exists(path) else {}

    targets = [c for c in uni["companies"] if c.get("analysis_mode") == "QUANTITATIVE"]
    for c in targets:
        t = c["ticker"]
        if t in out and out[t].get("status") == "OK" and "--refresh" not in sys.argv:
            continue
        try:
            rec = collect(t, c["cik"])
        except Exception as e:                          # noqa: BLE001
            rec = {"ticker": t, "status": "DATA_UNAVAILABLE", "reason": repr(e)}
        out[t] = rec
        n = rec.get("shares_outstanding")
        print(f"[{t:<6}] {rec['status']:<17} "
              f"{(f'{n/1e9:.3f}B shares' if n else rec.get('reason', '')[:50]):<20} "
              f"{'INCOMPLETE' if rec.get('incomplete') else ''}")
        with open(path, "w") as f:
            json.dump(out, f, indent=2)
        time.sleep(1.0)

    ok = sum(1 for r in out.values() if r.get("status") == "OK")
    print(f"\n{ok}/{len(targets)} cover-page share counts -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
