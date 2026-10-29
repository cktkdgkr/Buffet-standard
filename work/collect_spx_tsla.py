"""
Primary financial data for SpaceX (SPCX) and Tesla (TSLA), as of the day it
runs.

The two are collected together because the question is the same for both -
what does the capital earn, and how much of it is not earning yet - but the
data has to come from different places, and the difference is the first
finding of the analysis.

Tesla has filed annual reports for a decade, so its history comes from the
companyfacts API like the other fifty companies, with the latest 10-Q for the
current capital position.

SpaceX has filed two. It listed on Nasdaq in June 2026 (638.9 million Class A
shares at $135.00; 424B4 filed 12 June 2026), so there is no 10-K yet and
companyfacts carries no annual period for it at all - only quarterly and
year-to-date figures from the two 10-Qs. Everything annual has to come out of
the registration statement.

What the filings also settle, and what no amount of recollection would have:
SPCX is not a launch company with a satellite business attached. Note 1 of the
September 2026 10-Q describes three segments - Space (launch), Connectivity
(Starlink) and Super Intelligence, the last holding SI infrastructure, the Grok
model, Cursor and X. Cursor (Anysphere, Inc.) was acquired on 14 August 2026
for $42,723m in stock against an implied equity value of $60bn. Segment figures
are filed, so the segments can be looked at separately, which is the only way
the question "what does the capital earn" has an answer here.

Data comes from the Financial Report renderings (the R*.htm files) rather than
the main document, because those are one statement per file as a plain table.

    python3 collect_spx_tsla.py
    python3 collect_spx_tsla.py --refresh
"""

import argparse
import html
import json
import os
import re
import sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sec_cache                                               # noqa: E402

CACHE = os.path.join(HERE, "spx", "cache")
OUT = os.path.join(HERE, "spx", "spx_tsla_raw.json")

SPCX_CIK = 1181412
TSLA_CIK = 1318605

ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}"


# --------------------------------------------------------------- R-file tables
def strip_tags(x):
    return html.unescape(re.sub(r"<[^>]+>", " ", x)).strip()


NUM = re.compile(r"^\(?\$?\s*-?[\d,]+(?:\.\d+)?\)?%?$")


def parse_number(cell):
    """
    One rendered cell to a number.

    The renderings use brackets for negatives, commas for thousands, and an
    em-dash for nil. A cell that is not a number at all comes back as None
    rather than zero, because a missing line and a zero line mean different
    things on a balance sheet.
    """
    t = strip_tags(cell).replace("\xa0", " ").strip()
    if t in ("", "—", "–", "-", "$", "$ —"):
        return None
    t = t.replace("$", "").replace(",", "").replace("%", "").strip()
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").strip()
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", t):
        return None
    v = float(t)
    return -v if neg else v


def parse_report(path):
    """
    An R*.htm rendering as {"title", "scale", "columns", "rows"}.

    Each row carries the XBRL element name alongside its label, pulled out of
    the onclick the rendering attaches to every line
    ("defref_us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax").
    That is what the row actually is, and matching on it instead of on the
    printed label removes the guesswork: "Revenue" appears a dozen times in a
    segment note under different dimensions, and two companies label the same
    element differently.

    Units are per row, not per table. The heading says "$ in Millions" but the
    same table carries "Number of operating segments | segment" = 3, and
    multiplying that by a million would be nonsense - so the scale is recorded
    and applied only where the row is a monetary one, which the element name
    and the rendered "$" together establish.
    """
    raw = open(path, errors="ignore").read()
    m = re.search(r'<table class="report".*?</table>', raw, re.S)
    if not m:
        return None
    table = m.group(0)
    rows_html = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)

    title, scale, columns, rows = "", 1.0, [], []
    for i, tr in enumerate(rows_html):
        cells = re.findall(r"<t([hd])[^>]*>(.*?)</t[hd]>", tr, re.S)
        if not cells:
            continue
        kinds = {k for k, _ in cells}
        texts = [strip_tags(c) for _, c in cells]
        if kinds == {"h"}:
            if not title and texts[0]:
                title = texts[0]
                if "in Millions" in title:
                    scale = 1e6
                elif "in Thousands" in title:
                    scale = 1e3
                elif "in Billions" in title:
                    scale = 1e9
            # The column headers are the period labels; a row of them that
            # contains a date is the one to keep.
            dated = [t for t in texts if re.search(r"[A-Z][a-z]{2}\.? ?\d", t)]
            if dated:
                columns = dated
            continue
        label = texts[0]
        raw_cells = [c for _, c in cells[1:]]
        values = [parse_number(c) for c in raw_cells]
        element = None
        # The hyphen in "us-gaap" has to be in the class, or the name is
        # truncated to "us" and every element match silently fails.
        m_el = re.search(r"defref_([A-Za-z0-9-]+)_([A-Za-z0-9_]+)",
                         cells[0][1])
        if m_el:
            element = f"{m_el.group(1)}:{m_el.group(2)}"
        # A share count is not an amount of money, however the table is
        # headed. The balance sheet is titled "$ in Millions" and carries
        # "Common stock, shares outstanding (in shares) 8,240,000,000" - and
        # multiplying that by a million turned 13.6bn shares into 1.4e16 and a
        # $2tn market capitalisation into nonsense.
        is_shares = ("in shares" in label.lower()
                     or "(in shares)" in label.lower()
                     or (element or "").lower().endswith("shares")
                     or "shares" in (element or "").lower()
                     and "value" not in (element or "").lower())
        monetary = (not is_shares) and any("$" in c for c in raw_cells)
        if label:
            rows.append({"label": label, "element": element,
                         "values": values, "monetary": monetary})
    # A block's first row shows the "$"; the rows beneath it do not, so
    # monetary-ness is inherited from the nearest row above that had one.
    seen_money = False
    for r in rows:
        if r["monetary"]:
            seen_money = True
        elif seen_money and any(v is not None for v in r["values"]) \
                and r["element"] and ":" in r["element"] \
                and "in shares" not in r["label"].lower() \
                and "shares" not in (r["element"] or "").lower():
            r["monetary"] = True

    # The dimension a figure belongs to sits on its own row above it, with no
    # values - "Construction in progress", then the amount tagged plainly as
    # PropertyPlantAndEquipmentGross. Tesla's whole PP&E breakdown is eight
    # consecutive rows labelled "Property, plant and equipment", so without
    # carrying that heading down each row the components are indistinguishable.
    # Renderings carry spacer columns that are empty in every row: the balance
    # sheet has one at the front and the prospectus one between each pair of
    # years. Leaving them in puts every column index one or two places out,
    # which then reads as missing data rather than as an error - the balance
    # sheet lookups all came back None from exactly this.
    width = max((len(r["values"]) for r in rows), default=0)
    keep = [i for i in range(width)
            if any(i < len(r["values"]) and r["values"][i] is not None
                   for r in rows)]
    if len(keep) < width:
        for r in rows:
            r["values"] = [r["values"][i] if i < len(r["values"]) else None
                           for i in keep]

    # Two levels, because a segment block has sub-headings inside it:
    #
    #   Operating Segments | Space      <- the dimension
    #     Segment Reporting [Line Items]
    #       Revenue
    #     Costs and expenses            <- a sub-heading, not a dimension
    #       Cost of revenue
    #
    # Keeping one context meant "Cost of revenue" came back under "Costs and
    # expenses" with the segment lost. The dimension is the heading that is
    # not one of the statement's own sub-headings.
    SUBHEADINGS = ("costs and expenses", "supplemental segment information",
                   "assets", "liabilities", "current assets",
                   "current liabilities", "long-term liabilities",
                   "shareholders' equity", "stockholders' equity",
                   "revenues", "operating expenses")
    dimension = None
    subheading = None
    for r in rows:
        blank = all(v is None for v in r["values"])
        if blank:
            label = r["label"]
            if label.endswith(("[Abstract]", "[Line Items]", "[Member]")):
                pass
            elif label.lower().rstrip(":") in SUBHEADINGS:
                subheading = label
            else:
                dimension, subheading = label, None
            r["context"] = None
            r["subheading"] = None
        else:
            r["context"] = dimension
            r["subheading"] = subheading
    return {"title": title, "scale": scale, "columns": columns, "rows": rows}


def find_row(report, *patterns, element=None, context=None, exact=False,
             patterns_required=True):
    """
    The first matching row, with monetary values scaled to dollars.

    Matching on `element` (the XBRL name) is preferred; the label patterns are
    the fallback for the handful of rows a filer tags with a custom element.
    """
    if not report:
        return None
    for r in report["rows"]:
        # A heading row carries the label but no figures: the balance sheet's
        # "Redeemable convertible preferred stock" sits above the line that
        # holds the $38,752m, and matching the heading returned no value while
        # looking like a successful lookup.
        if all(v is None for v in r["values"]):
            continue
        if (r.get("element") or "").endswith(("Abstract", "LineItems")):
            continue
        if context is not None:
            ctx = (r.get("context") or "").lower()
            if context.lower() not in ctx:
                continue
            if not patterns_required and not patterns and not element:
                # A context-only lookup: the dimension heading identifies the
                # row on its own, which is how Tesla's PP&E components have to
                # be read.
                mult = report["scale"] if r["monetary"] else 1.0
                return {"label": r["label"], "element": r.get("element"),
                        "context": r.get("context"),
                        "subheading": r.get("subheading"),
                        "monetary": r["monetary"],
                        "values": [None if v is None else v * mult
                                   for v in r["values"]],
                        "columns": report["columns"]}
        if element and r.get("element") and \
                r["element"].split(":")[-1] == element:
            hit = True
        else:
            low = r["label"].lower()
            hit = any((low == p.lower()) if exact else (p.lower() in low)
                      for p in patterns) if patterns else False
        if not hit:
            continue
        mult = report["scale"] if r["monetary"] else 1.0
        return {"label": r["label"], "element": r.get("element"),
                "context": r.get("context"),
                "subheading": r.get("subheading"),
                "monetary": r["monetary"],
                "values": [None if v is None else v * mult
                           for v in r["values"]],
                "columns": report["columns"]}
    return None


# ------------------------------------------------------------------- filings
def filing_index(cik, accession, refresh):
    acc = accession.replace("-", "")
    base = ARCHIVE.format(cik=cik, acc=acc)
    d, _, _ = sec_cache.fetch_json(
        base + "/index.json",
        os.path.join(CACHE, f"{cik}_{acc}_index.json"),
        max_age_days=365, refresh=refresh)
    return base, [x["name"] for x in d["directory"]["item"]]


def report_map(cik, accession, refresh):
    """ShortName to R-file, from the filing's own summary."""
    acc = accession.replace("-", "")
    base = ARCHIVE.format(cik=cik, acc=acc)
    p, _, _ = sec_cache.fetch(
        base + "/FilingSummary.xml",
        os.path.join(CACHE, f"{cik}_{acc}_summary.xml"),
        max_age_days=365, refresh=refresh, min_bytes=400)
    x = open(p, errors="ignore").read()
    out = []
    for m in re.finditer(r"<Report[^>]*>(.*?)</Report>", x, re.S):
        b = m.group(1)
        g = lambda t: (re.search(rf"<{t}>(.*?)</{t}>", b, re.S)
                       or [None, ""])[1].strip()
        fn, short = g("HtmlFileName"), g("ShortName")
        if fn:
            out.append((short, fn))
    return base, out


def get_report(base, cik, accession, filename, refresh):
    acc = accession.replace("-", "")
    p, _, _ = sec_cache.fetch(
        f"{base}/{filename}",
        os.path.join(CACHE, f"{cik}_{acc}_{filename}"),
        max_age_days=365, refresh=refresh, min_bytes=200)
    return parse_report(p)


def pick(reports, *keywords):
    """The R-file whose ShortName contains all the keywords."""
    for short, fn in reports:
        low = short.lower()
        if all(k.lower() in low for k in keywords):
            return short, fn
    return None, None


def latest_filings(cik, forms, refresh, limit=12):
    sub, _, _ = sec_cache.submissions(cik, CACHE, refresh=refresh,
                                      max_age_days=1.0)
    r = sub["filings"]["recent"]
    out = []
    for form, filed, end, acc, doc in zip(
            r["form"], r["filingDate"],
            r.get("reportDate", [""] * len(r["form"])),
            r["accessionNumber"], r.get("primaryDocument",
                                        [""] * len(r["form"]))):
        if form in forms:
            out.append({"form": form, "filed": filed, "period_end": end,
                        "accession": acc, "primary_document": doc})
    return {"entity": sub["name"], "cik": sub["cik"],
            "tickers": sub.get("tickers"), "exchanges": sub.get("exchanges"),
            "sic": sub.get("sic"), "sic_description": sub.get("sicDescription"),
            "fiscal_year_end": sub.get("fiscalYearEnd"),
            "filings": out[:limit]}


# ------------------------------------------------------------ per-company pull
# Each entry is a list of keyword sets tried in order, because the two
# companies name the same statement differently: SpaceX files "Property, Plant,
# and Equipment, Net - Narrative (Details)" and Tesla "Property, Plant and
# Equipment, Net - Additional Information (Details)", and Tesla has no backlog
# note at all - its unearned revenue sits in a deferred-revenue schedule.
WANT = [
    ("balance_sheet", [("Consolidated Balance Sheets",)]),
    ("operations", [("Consolidated Statements of Operations",)]),
    ("cash_flows", [("Consolidated Statements of Cash Flows",)]),
    ("segments", [("Segment", "Details")]),
    ("ppe_schedule", [("Property", "Schedule", "Details")]),
    ("ppe_narrative", [("Property", "Narrative"),
                       ("Property", "Additional Information")]),
    ("revenue_disaggregation", [("Disaggregation", "Details")]),
    ("backlog", [("Backlog",), ("Deferred Revenue", "Details")]),
    ("debt_schedule", [("Debt", "Schedule of Debt"),
                       ("Debt", "Schedule of Recourse"),
                       ("Debt", "Details")]),
    ("acquisition_consideration", [("Purchase Consideration",)]),
    ("acquisition_assets", [("Assets Acquired",)]),
    ("shares_outstanding", [("Common Stock", "Details"),
                            ("Equity", "Details")]),
    # The share count by class. The equity-activity note states the same
    # totals, which is a useful second reading of a figure the whole valuation
    # rests on.
    ("shares_parenthetical", [("Balance Sheets", "Parenthetical")]),
]


def collect_filing(cik, accession, refresh):
    base, reports = report_map(cik, accession, refresh)
    got = {"accession": accession,
           "report_count": len(reports),
           "reports_available": [s for s, _ in reports]}
    for key, keyword_sets in WANT:
        short = fn = None
        for keywords in keyword_sets:
            short, fn = pick(reports, *keywords)
            if fn:
                break
        if not fn:
            got[key] = None
            continue
        rep = get_report(base, cik, accession, fn, refresh)
        got[key] = {"short_name": short, "file": fn,
                    "title": rep["title"] if rep else None,
                    "columns": rep["columns"] if rep else [],
                    "rows": rep["rows"] if rep else [],
                    "scale": rep["scale"] if rep else None,
                    "source_url": f"{base}/{fn}"}
    return got


# ------------------------------------------------- prospectus (no XBRL tables)
def prospectus_tables(cik, accession, document, refresh):
    """
    The annual statements out of a prospectus, which carries no XBRL
    rendering.

    SpaceX has filed no 10-K - it listed in June 2026 - so FY2023 to FY2025
    exist only here. The 424B4 is an 11MB document with 148 tables and no
    machine-readable index, so each table is located by what it contains
    rather than by position: tables are numbered differently in every
    amendment, and an index would silently point at the wrong one.
    """
    base = ARCHIVE.format(cik=cik, acc=accession.replace("-", ""))
    path = os.path.join(CACHE, f"{cik}_{accession.replace('-', '')}_doc.htm")
    p, _, _ = sec_cache.fetch(f"{base}/{document}", path,
                              max_age_days=365, refresh=refresh,
                              min_bytes=100000)
    raw = open(p, errors="ignore").read()

    def rows_of(t):
        out = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
            cells = [re.sub(r"\s+", " ",
                            html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                     for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr,
                                         re.S)]
            if any(cells):
                out.append(cells)
        return out

    tables = [rows_of(t) for t in
              re.findall(r"<table[^>]*>.*?</table>", raw, re.S)]

    def locate(*required, max_rows=60):
        """The smallest table containing every required phrase."""
        best = None
        for rows in tables:
            flat = " ".join(" ".join(r) for r in rows).lower()
            if len(rows) > max_rows:
                continue
            if all(k.lower() in flat for k in required):
                if best is None or len(rows) < len(best):
                    best = rows
        return best

    def tidy(rows):
        if rows is None:
            return None
        out = []
        for r in rows:
            label = re.sub(r"[.\s]+$", "", r[0]).strip()
            vals = [parse_number(c) for c in r[1:]]
            out.append([label, vals, [c for c in r[1:]]])
        # Drop the spacer columns, which sit between every pair of years in
        # the prospectus tables and otherwise shift each year one place.
        width = max((len(v) for _, v, _ in out), default=0)
        keep = [i for i in range(width)
                if any(i < len(v) and v[i] is not None for _, v, _ in out)]
        if len(keep) < width:
            out = [[lbl,
                    [v[i] if i < len(v) else None for i in keep],
                    [rc[i] if i < len(rc) else "" for i in keep]]
                   for lbl, v, rc in out]
        return out

    return {
        "source_url": f"{base}/{document}",
        "accession": accession,
        # The summary tables carry the three audited years side by side, which
        # is what a ten-year test would use if ten years existed.
        # "Income (loss) from operations" alone also matches the operating
        # metrics table, which carries "Segment income (loss) from
        # operations" beside launch counts and is smaller - so it won. The
        # revenue and net income lines are what distinguish the statement.
        "summary_operations": tidy(locate("Total costs and expenses",
                                          "Net income (loss)",
                                          "Year Ended December 31")),
        "summary_balance_sheet": tidy(locate("Total shareholders",
                                             "Property, plant, and equipment",
                                             "December 31")),
        "segment_revenue": tidy(locate("Total revenues", "Connectivity",
                                       "Year Ended December 31")),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)

    print(f"오늘 {date.today().isoformat()} 기준 수집"
          + (" (--refresh)" if a.refresh else ""))

    out = {"generated": date.today().isoformat(), "companies": {}}

    for label, cik, forms in (("SPCX", SPCX_CIK, ("10-Q", "10-K", "424B4",
                                                  "S-1/A", "S-1")),
                              ("TSLA", TSLA_CIK, ("10-K", "10-Q"))):
        meta = latest_filings(cik, forms, a.refresh)
        print(f"\n{label}: {meta['entity']}")
        print(f"  티커 {meta['tickers']} · 거래소 {meta['exchanges']} · "
              f"SIC {meta['sic']} · 결산 {meta['fiscal_year_end']}")
        annual = [f for f in meta["filings"] if f["form"] == "10-K"]
        quarterly = [f for f in meta["filings"] if f["form"] == "10-Q"]
        reg = [f for f in meta["filings"]
               if f["form"] in ("424B4", "S-1/A", "S-1")]
        print(f"  10-K {len(annual)}건 · 10-Q {len(quarterly)}건 · "
              f"등록신고서 {len(reg)}건")
        if not annual:
            print("  ** 10-K 없음 — 연간 감사수치는 등록신고서에서만 "
                  "확인 가능 **")

        pulls = {}
        targets = ([quarterly[0]] if quarterly else []) + \
                  ([annual[0]] if annual else [])
        if not annual:
            # A 424B4 prospectus is filed without XBRL renderings, so the
            # annual statements have to come from the S-1 (or its amendment),
            # which is tagged. Every registration filing is tried until one
            # yields a FilingSummary.
            targets += [f for f in reg]
        for f in targets:
            print(f"  수집 {f['form']} {f['filed']} (기말 "
                  f"{f['period_end'] or '—'}) {f['accession']}")
            try:
                got = collect_filing(cik, f["accession"], a.refresh)
            except Exception as exc:                           # noqa: BLE001
                print(f"    실패: {exc}")
                continue
            have = [k for k, _ in WANT if got.get(k)]
            missing = [k for k, _ in WANT if not got.get(k)]
            print(f"    표 {got['report_count']}개 중 확보 "
                  f"{len(have)}/{len(WANT)}"
                  + (f" · 없음: {', '.join(missing)}" if missing else ""))
            got.update({"form": f["form"], "filed": f["filed"],
                        "period_end": f["period_end"]})
            pulls[f"{f['form']}_{f['period_end'] or f['filed']}"] = got

        prospectus = None
        if not annual:
            # The 424B4 is the final, priced prospectus, so its figures are the
            # ones the market was sold on.
            final = next((f for f in meta["filings"]
                          if f["form"] == "424B4"), None)
            if final:
                try:
                    prospectus = prospectus_tables(
                        cik, final["accession"], final["primary_document"],
                        a.refresh)
                    found = [k for k in ("summary_operations",
                                         "summary_balance_sheet",
                                         "segment_revenue")
                             if prospectus.get(k)]
                    print(f"  등록신고서 {final['form']} "
                          f"{final['filed']}: 표 확보 {', '.join(found)}")
                except Exception as exc:                       # noqa: BLE001
                    print(f"  등록신고서 파싱 실패: {exc}")

        out["companies"][label] = {"meta": meta, "filings": pulls,
                                   "prospectus": prospectus}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
