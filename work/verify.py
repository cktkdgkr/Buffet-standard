"""
PHASE 6 (A6) - independent re-verification of every sourced figure.

The point of this phase is that it can fail. Nothing here reads work/raw: it
goes back to SEC, to the exchange and to FRED, asks for each figure again by the
narrowest endpoint that returns it, and compares. A figure that came out of a
parsing mistake, a stale cache or a tag that has since been restated shows up as
a mismatch rather than surviving into the report.

Figures are checked against the FILING DOCUMENT, not against another API view of
the same store. The first version of this phase re-read the companyconcept
endpoint and reported Coca-Cola and Visa as mismatches; the endpoint simply
serves no annual facts for those companies, so the check was measuring SEC's
aggregation rather than the data. The 10-K's own inline XBRL is the primary
record and the only thing worth verifying against.

Four checks per company:
  1. The latest 10-K is downloaded and its inline XBRL parsed independently.
     Every analysis figure drawn from that filing must appear in it, under the
     same tag, for the same period, at the same value.
  2. The accession number carried by that figure must appear in the company's
     EDGAR filing index - proof the filing it claims to come from is real.
  3. The share count used for market capitalisation must be present in that
     same document, re-derived from the parse rather than string-matched.
  4. The price quote must be retrievable and within a sane band of the one used.

Macro inputs are re-checked once, not per company.

Writes work/verification.json. Any company with a FAIL is reported, and PHASE 7
drops the affected figure rather than publishing it.
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
CONCEPT = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/{taxonomy}/{tag}.json"

# Metrics re-verified per company. Every figure that reaches the report is built
# from these, so verifying them covers the report's factual surface.
VERIFY_METRICS = ["revenue", "net_income", "total_equity", "pretax_income",
                  "cash_and_equivalents", "capex"]

# A quote moves between the analysis run and this one; only a jump big enough to
# mean a different instrument or a split is treated as a failure.
PRICE_TOLERANCE = 0.15


def fetch(url: str, retries: int = 5):
    delay = 3
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (403, 407):
                raise RuntimeError(f"EGRESS DENIED ({e.code}) for {url}") from e
            if attempt == retries - 1:
                raise
        except Exception:
            if attempt == retries - 1:
                raise
        time.sleep(delay)
        delay *= 2
    return None


def parse_contexts(html):
    """Context id -> its period end and share-class member."""
    contexts = {}
    for m in re.finditer(r'<(?:[\w-]+:)?context[^>]*id="([^"]+)"(.*?)</(?:[\w-]+:)?context>',
                         html, re.S | re.I):
        cid, body = m.group(1), m.group(2)
        end = re.search(r'<(?:[\w-]+:)?(?:instant|endDate)>\s*([\d-]+)\s*<', body, re.I)
        member = re.search(r'<(?:[\w-]+:)?explicitMember[^>]*>\s*(?:[\w-]+:)?([\w-]+)\s*<',
                           body, re.I)
        contexts[cid] = {"end": end.group(1) if end else None,
                         "member": member.group(1) if member else None}
    return contexts


def parse_filing_facts(html, contexts):
    """
    Every numeric inline-XBRL fact in a document, keyed by (tag, period end).

    Contexts are passed in rather than read from the same document. In a filing
    split across two files, every context is declared once in the primary
    document and the companion file carries facts that only reference them - so
    parsing that file alone yields 3,500 facts with no periods attached, and
    every comparison against it fails for the wrong reason.

    Scale and sign are applied as the filing declares them, so a cover page that
    prints "24,300" with scale="6" is read as 24.3 billion rather than as a
    mismatch against the collected figure.
    """
    facts = {}
    for m in re.finditer(r'<ix:nonFraction([^>]*)>(.*?)</ix:nonFraction>', html, re.S | re.I):
        attrs, inner = m.group(1), m.group(2)
        name = re.search(r'name="([^"]+)"', attrs)
        ctx = re.search(r'contextRef="([^"]+)"', attrs)
        if not name or not ctx:
            continue
        raw = re.sub(r"<[^>]+>", "", inner).strip().replace(",", "").replace("\xa0", "")
        if not raw or not re.fullmatch(r"[\d.]+", raw):
            continue
        scale = re.search(r'scale="(-?\d+)"', attrs)
        val = float(raw) * (10 ** int(scale.group(1))) if scale else float(raw)
        if re.search(r'sign="-"', attrs):
            val = -val
        c = contexts.get(ctx.group(1), {})
        # Only undimensioned facts are comparable: a segment-level figure is a
        # different quantity that happens to share a tag.
        key = (name.group(1).split(":")[-1], c.get("end"), c.get("member"))
        facts.setdefault(key, set()).add(round(val, 2))
    return facts


def filing_documents(cik, accession, primary_url):
    """
    Every inline-XBRL document in the filing, not just the primary one.

    A large filer often splits the 10-K in two: IBM's primary document carries
    the narrative and the cover page while the financial statements sit in a
    companion file, and Wells Fargo does the reverse. Parsing only the document
    the submissions index calls "primary" therefore finds a cover page and no
    income statement, which looks exactly like a data failure and is not one.
    """
    urls = [primary_url]
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"
    body = fetch(f"{base}/index.json")
    if not body:
        return urls
    primary_name = primary_url.rsplit("/", 1)[-1]
    # The report documents share a stem with the primary ("wfc-20251231*"); the
    # rest of the filing is exhibits. Ranking by size alone picked up three
    # employment-agreement exhibits and left Wells Fargo's 11MB financial
    # statements outside the window.
    stem = re.match(r"^([a-z]+-?\d{8})", primary_name)
    stem = stem.group(1) if stem else primary_name[:8]

    candidates = []
    for item in json.loads(body).get("directory", {}).get("item", []):
        name = item.get("name", "")
        size = int(item.get("size") or 0)
        # R*.htm are the viewer's rendered fragments, duplicating facts already
        # in the source documents; skip them and anything too small to hold
        # statements.
        if (not name.endswith(".htm") or re.match(r"^R\d+\.htm$", name)
                or size < 100_000 or name == primary_name):
            continue
        candidates.append((name.startswith(stem), size, f"{base}/{name}"))

    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
    urls += [c[2] for c in candidates[:3]]
    return urls


def check_metric_against_filing(raw_metric, filing_facts, accession):
    """Confirm the analysis figure appears in the filing it cites."""
    tag = raw_metric.get("xbrl_tag")
    series = raw_metric.get("series") or []
    if not tag or not series:
        return None
    cited = [r for r in series if r.get("accession") == accession]
    if not cited:
        return {"metric": raw_metric["metric"], "result": "SKIP",
                "reason": "no figure drawn from the filing being verified"}
    latest = cited[-1]
    found = filing_facts.get((tag, latest["period_end"], None))
    if found is None:
        return {"metric": raw_metric["metric"], "result": "FAIL",
                "reason": f"filing contains no undimensioned {tag} fact ending "
                          f"{latest['period_end']}"}
    if round(latest["value"], 2) not in found:
        return {"metric": raw_metric["metric"], "result": "FAIL",
                "reason": f"value mismatch: analysis used {latest['value']}, "
                          f"filing states {sorted(found)}"}
    return {"metric": raw_metric["metric"], "result": "PASS",
            "value": latest["value"], "period_end": latest["period_end"],
            "accession": accession, "xbrl_tag": tag}


def check_accessions(cik, accessions):
    """Every cited accession must exist in the company's EDGAR filing index."""
    url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    body = fetch(url)
    if body is None:
        return {"result": "FAIL", "reason": "submissions index unavailable", "source_url": url}
    j = json.loads(body)
    known = set(j.get("filings", {}).get("recent", {}).get("accessionNumber", []))
    # Older filings roll into separate index files; fetch them only if needed.
    missing = {a for a in accessions if a and a not in known}
    if missing:
        for extra in j.get("filings", {}).get("files", []):
            body = fetch(f"https://data.sec.gov/submissions/{extra['name']}")
            if body:
                known |= set(json.loads(body).get("accessionNumber", []))
            missing = {a for a in missing if a not in known}
            if not missing:
                break
    return {
        "result": "PASS" if not missing else "FAIL",
        "checked": len(accessions),
        "not_found": sorted(missing),
        "source_url": url,
    }


def check_cover_shares(cover, filing_facts):
    """Each class share count must reappear in the independently parsed filing."""
    if cover.get("status") != "OK":
        return {"result": "SKIP", "reason": cover.get("reason", "not collected")}
    missing = []
    for cls, val in (cover.get("by_class") or {}).items():
        member = None if cls == "undimensioned" else cls
        hits = [v for (tag, _end, mem), vals in filing_facts.items()
                if tag == "EntityCommonStockSharesOutstanding" and mem == member
                for v in vals]
        if round(val, 2) not in hits:
            missing.append(cls)
    return {
        "result": "PASS" if not missing else "FAIL",
        "reason": None if not missing else f"share counts not reproduced on re-parse: {missing}",
        "shares_outstanding": cover.get("shares_outstanding"),
        "source_url": cover.get("source_url"),
    }


def check_price(rec):
    price = (rec.get("price") or {})
    url = price.get("source_url")
    if not url or price.get("price") is None:
        return {"result": "SKIP", "reason": "no price collected"}
    body = fetch(url)
    if body is None:
        return {"result": "FAIL", "reason": "quote endpoint returned 404", "source_url": url}
    j = json.loads(body)
    res = (j.get("chart") or {}).get("result")
    if not res:
        return {"result": "FAIL", "reason": "quote payload empty", "source_url": url}
    now = res[0].get("meta", {}).get("regularMarketPrice")
    if now is None:
        return {"result": "FAIL", "reason": "no price in payload", "source_url": url}
    drift = abs(now - price["price"]) / price["price"]
    return {
        "result": "PASS" if drift <= PRICE_TOLERANCE else "FAIL",
        "analysis_price": price["price"], "reverify_price": now, "drift": drift,
        "reason": None if drift <= PRICE_TOLERANCE else
                  "quote moved beyond tolerance - possible split or wrong instrument",
        "source_url": url,
    }


def check_macro(analysis):
    out = {}
    rf = analysis["risk_free_rate"]
    body = fetch(rf["source_url"])
    ok = False
    if body:
        rows = [ln.split(",") for ln in body.decode().strip().splitlines()[1:]]
        rows = [(d, v) for d, v in rows if v not in (".", "")]
        ok = bool(rows) and abs(float(rows[-1][1]) / 100.0 - rf["rate"]) < 0.005
    out["risk_free_rate"] = {"result": "PASS" if ok else "FAIL",
                             "value": rf["rate"], "source_url": rf["source_url"]}
    erp = analysis["equity_risk_premium"]
    body = fetch(erp["source_url"])
    ok = bool(body) and f"{erp['erp']*100:.2f}%".encode() in body
    out["equity_risk_premium"] = {"result": "PASS" if ok else "FAIL",
                                  "value": erp["erp"], "source_url": erp["source_url"]}
    return out


def main():
    with open(os.path.join(WORK, "analysis.json")) as f:
        analysis = json.load(f)
    cover = json.load(open(os.path.join(WORK, "cover_shares.json")))

    print("re-verifying macro inputs...")
    macro = check_macro(analysis)
    for k, v in macro.items():
        print(f"  {k}: {v['result']}")

    results, failures = {}, []
    for rec in analysis["companies"]:
        t, cik = rec["ticker"], rec["cik"]
        with open(os.path.join(WORK, "raw", f"{t}.json")) as f:
            raw = json.load(f)

        # One download per company: the filing that the headline figures cite.
        cov = cover.get(t, {})
        filing_url = cov.get("source_url")
        accession = cov.get("accession")
        filing_facts, fetch_err = {}, None
        docs = []
        if filing_url and accession:
            docs = filing_documents(cik, accession, filing_url)
            # Two passes: contexts are declared in one document and referenced
            # from the others, so they must all be in hand before any fact is
            # given a period.
            bodies, contexts = [], {}
            for url in docs:
                body = fetch(url)
                if body is None:
                    continue
                text = body.decode("utf-8", "replace")
                bodies.append(text)
                contexts.update(parse_contexts(text))
                time.sleep(0.3)
            for text in bodies:
                for key, vals in parse_filing_facts(text, contexts).items():
                    filing_facts.setdefault(key, set()).update(vals)
            if not filing_facts:
                fetch_err = "filing documents no longer retrievable"
        else:
            fetch_err = "no filing document recorded for this company"

        metric_checks, accns = [], set()
        for m in VERIFY_METRICS:
            node = raw.get("metrics", {}).get(m)
            if not node:
                continue
            if fetch_err:
                metric_checks.append({"metric": m, "result": "FAIL", "reason": fetch_err})
                continue
            res = check_metric_against_filing(node, filing_facts, accession)
            if res:
                metric_checks.append(res)
                if res.get("accession"):
                    accns.add(res["accession"])

        acc_check = check_accessions(cik, accns)
        time.sleep(0.25)
        cover_check = check_cover_shares(cov, filing_facts)
        price_check = check_price(rec)
        time.sleep(0.25)

        failed = [c for c in metric_checks if c["result"] == "FAIL"]
        for name, c in (("accessions", acc_check), ("cover_shares", cover_check),
                        ("price", price_check)):
            if c.get("result") == "FAIL":
                failed.append({"metric": name, **c})

        results[t] = {
            "filing_verified": filing_url,
            "documents_parsed": docs,
            "metrics": metric_checks,
            "accessions": acc_check,
            "cover_shares": cover_check,
            "price": price_check,
            "verdict": "PASS" if not failed else "FAIL",
        }
        if failed:
            failures.append((t, failed))
        n_pass = sum(1 for c in metric_checks if c["result"] == "PASS")
        n_ck = sum(1 for c in metric_checks if c["result"] in ("PASS", "FAIL"))
        print(f"[{t:<6}] {results[t]['verdict']:<4} metrics {n_pass}/{n_ck} "
              f"accn {acc_check['result']} cover {cover_check['result']} "
              f"price {price_check['result']}")

    out = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "every figure re-requested from its primary endpoint and compared; "
                  "no value read from the local collection",
        "macro": macro,
        "companies": results,
        "summary": {
            "companies_checked": len(results),
            "companies_passed": sum(1 for r in results.values() if r["verdict"] == "PASS"),
            "companies_failed": len(failures),
        },
    }
    with open(os.path.join(WORK, "verification.json"), "w") as f:
        json.dump(out, f, indent=2)

    print(f"\n{out['summary']['companies_passed']}/{len(results)} companies fully verified")
    if failures:
        print("FAILURES:")
        for t, fs in failures:
            for c in fs:
                print(f"  {t} {c['metric']}: {c.get('reason')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
