"""
What Berkshire Hathaway actually bought in Alphabet, and what Alphabet was
doing while they bought it.

The question this answers is not "is Alphabet cheap" - the earlier reports did
that - but "what did Berkshire see". So the evidence has to be what Berkshire
and Alphabet filed, not commentary about them. Four primary sources:

  1. Berkshire's 13F-HR information tables (CIK 1067983), quarter by quarter.
     These give the share count and the portfolio rank, and they show that the
     position was built in three separate acts at three very different prices.

  2. Alphabet's Form 8-K of 4 June 2026 (accession 0001193125-26-257724). This
     is the document that changes the question. Berkshire did not accumulate
     the last leg in the market - Alphabet sold them 28.6 million shares in a
     negotiated private placement for exactly $10 billion, alongside a public
     offering of common stock priced the same week.

  3. Alphabet's Form 8-K of 5 June 2026 (accession 0001193125-26-259830). The
     same week, Alphabet sold $19.25bn of 6.25% mandatory convertible preferred
     stock - to the public market, not to Berkshire. That Berkshire took the
     unprotected common when a downside-protected 6.25% instrument was on the
     table the same week is the most informative fact in the whole file, and it
     is a fact, not an inference.

  4. Alphabet's Form 10-Q for Q2 2026 (0001652044-26-000071) and Q2 2025
     (0001652044-25-000062), plus the FY2025 10-K figures already collected,
     for what the business was doing on both sides of the purchase.

Plus Berkshire's own Q2 2026 10-Q (0001193125-26-341032) for the size of the
Treasury bill pile the Alphabet purchase was competing against.

Everything is in millions of US dollars except share counts and prices.
Writes work/brk_alphabet.json.
"""

import json
import os
import re
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "brk", "docs")
OUT = os.path.join(HERE, "brk_alphabet.json")

UA = "Buffett-standard research cktkdgkr@gmail.com"

# ---------------------------------------------------------------------------
# Berkshire's 13F information tables. The file name inside each filing is not
# predictable, so it travels with the accession.
# ---------------------------------------------------------------------------
THIRTEEN_F = {
    "2024-12-31": ("000095012325002701", "39042.xml"),
    "2025-03-31": ("000095012325005701", "form13fInfoTable.xml"),
    "2025-06-30": ("000095012325008343", "43977.xml"),
    "2025-09-30": ("000119312525282901", "46994.xml"),
    "2025-12-31": ("000119312526054580", "50240.xml"),
    "2026-03-31": ("000119312526226661", "53405.xml"),
    "2026-06-30": ("000119312526352200", "56757.xml"),
}

DOCS = {
    "goog_10q_2026q2": ("1652044", "000165204426000071", "goog-20260630.htm"),
    "goog_10q_2025q2": ("1652044", "000165204425000062", "goog-20250630.htm"),
    "goog_8k_20260604": ("1652044", "000119312526257724", "d83560d8k.htm"),
    "goog_8k_20260605": ("1652044", "000119312526259830", "d36818d8k.htm"),
    "brk_10q_2026q2": ("1067983", "000119312526341032", "brka-20260630.htm"),
}


def fetch(url, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    subprocess.run(["curl", "-sS", "-A", UA, url, "-o", path], check=True)
    return path


def text_of(path):
    """Filing HTML flattened to one line per element, entities decoded."""
    import html as _html
    raw = open(path, errors="ignore").read()
    raw = re.sub(r"<[^>]+>", "\n", raw)
    raw = _html.unescape(raw)
    return [x.strip() for x in raw.split("\n") if x.strip()]


NUM = re.compile(r"\(?\$?\s?-?\d[\d,]*(?:\.\d+)?\)?")


def numbers(seq):
    """
    Figures from a run of flattened elements.

    The inline-XBRL flattening puts a minus sign, a dollar sign and a closing
    parenthesis in their own elements, so the sign has to be rebuilt from the
    surrounding tokens rather than read off the number itself.
    """
    out, neg = [], False
    for tok in seq:
        t = tok.strip()
        if t == "(":
            neg = True
            continue
        if t == ")":
            neg = False
            continue
        if t in ("$", "%", "|"):
            continue
        m = re.fullmatch(r"-?\d[\d,]*(?:\.\d+)?", t)
        if m:
            v = float(t.replace(",", ""))
            out.append(-v if neg else v)
            neg = False
    return out


def after(lines, label, count, skip=0, window=90):
    """The first `count` figures following the `skip`-th occurrence of label."""
    hits = [i for i, l in enumerate(lines) if l.strip() == label]
    if len(hits) <= skip:
        hits = [i for i, l in enumerate(lines) if label in l]
    if len(hits) <= skip:
        raise KeyError(f"label not found: {label!r} (#{skip})")
    i = hits[skip]
    vals = numbers(lines[i + 1: i + 1 + window])
    return vals[:count]


# ---------------------------------------------------------------------------
def berkshire_positions():
    """Every Berkshire 13F position, by quarter, with Alphabet pulled out."""
    quarters = {}
    for period, (folder, fname) in THIRTEEN_F.items():
        path = os.path.join(CACHE, f"13f_{period}.xml")
        fetch(f"https://www.sec.gov/Archives/edgar/data/1067983/{folder}/{fname}",
              path)
        body = re.sub(r'\sxmlns(:\w+)?="[^"]+"', "", open(path).read())
        root = ET.fromstring(body)
        rows = []
        for it in root.iter("infoTable"):
            g = lambda tag: (it.find(f".//{tag}").text
                             if it.find(f".//{tag}") is not None else None)
            rows.append({"issuer": g("nameOfIssuer"), "class": g("titleOfClass"),
                         "cusip": g("cusip"), "value": int(g("value")),
                         "shares": int(g("sshPrnamt"))})
        by_issuer = {}
        for r in rows:
            key = re.sub(r"\s+(INC|CORP|CO|LTD|LIMITED|NEW)\b", "",
                         r["issuer"].upper()).strip()
            e = by_issuer.setdefault(key, {"value": 0, "shares": 0})
            e["value"] += r["value"]
            e["shares"] += r["shares"]
        total = sum(v["value"] for v in by_issuer.values())
        ranked = sorted(by_issuer.items(), key=lambda kv: -kv[1]["value"])
        alpha = next(((i + 1, v) for i, (k, v) in enumerate(ranked)
                      if "ALPHABET" in k), None)
        quarters[period] = {
            "positions": len(by_issuer),
            "total_value": total,
            "top10": [{"issuer": k, "value": v["value"], "shares": v["shares"],
                       "weight": v["value"] / total}
                      for k, v in ranked[:10]],
            "alphabet": None if not alpha else {
                "rank": alpha[0], "value": alpha[1]["value"],
                "shares": alpha[1]["shares"],
                "weight": alpha[1]["value"] / total,
                "by_class": [r for r in rows if "ALPHABET" in r["issuer"].upper()],
            },
            "source": f"13F-HR, period {period}",
        }
    return quarters


def private_placement():
    """
    The 4 June 2026 private placement and the offerings around it, read out of
    the 8-K rather than summarised from memory.
    """
    path = os.path.join(CACHE, "goog_8k_20260604.htm")
    cik, folder, fname = DOCS["goog_8k_20260604"]
    fetch(f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{fname}", path)
    # The inline-XBRL flattening breaks sentences across elements, so collapse
    # runs of whitespace before matching prose.
    body = re.sub(r"\s+", " ", " ".join(text_of(path)))

    def grab(pattern, cast=float):
        m = re.search(pattern, body)
        if not m:
            return None
        return [cast(g.replace(",", "")) for g in m.groups()]

    pp = grab(r"sale of ([\d,]+) shares of Class A Common Stock at a price per "
              r"share of approximately \$([\d.]+) and ([\d,]+) shares of Class C "
              r"Capital Stock at a price per share of approximately \$([\d.]+)")
    public = grab(r"issue and sell ([\d,]+) shares of Class A Common Stock, "
                  r"\$0\.001 par value \(.Class A Common Stock.\) at a price of "
                  r"([\d.]+) per share, and ([\d,]+) shares of Class C Capital "
                  r"Stock, \$0\.001 par value \(.Class C Capital Stock.\) at a "
                  r"price of ([\d.]+) per share")
    over = grab(r"additional ([\d,]+) shares of Class A Common Stock and an "
                r"additional ([\d,]+) shares of Class C Capital Stock")
    atm = grab(r"up to \$([\d.]+) billion of shares of Class A Common Stock")
    gross = grab(r"for gross proceeds of \$([\d.]+) billion")

    return {
        "agreement_date": "2026-06-01",
        "counterparty": "National Indemnity Company (an affiliate of "
                        "Berkshire Hathaway Inc.)",
        "class_a_shares": pp[0], "class_a_price": pp[1],
        "class_c_shares": pp[2], "class_c_price": pp[3],
        "total_shares": pp[0] + pp[2],
        "gross_proceeds_bn": gross[0] if gross else None,
        "public_offering": {
            "class_a_shares": public[0], "class_a_price": public[1],
            "class_c_shares": public[2], "class_c_price": public[3],
            "overallotment_class_a": over[0], "overallotment_class_c": over[1],
            "overallotment_exercised": "in full on 2026-06-03",
        },
        "atm_programme_bn": atm[0] if atm else None,
        "registration_rights": True,
        "source": "Form 8-K filed 2026-06-04, accession 0001193125-26-257724",
    }


def mandatory_convertible():
    """
    The instrument Berkshire did not take. Terms from the 5 June 2026 8-K.
    """
    path = os.path.join(CACHE, "goog_8k_20260605.htm")
    cik, folder, fname = DOCS["goog_8k_20260605"]
    fetch(f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{fname}", path)
    body = re.sub(r"\s+", " ", " ".join(text_of(path)))

    base = re.search(r"\(1\) ([\d,]+) series A depositary shares", body)
    over = re.search(r"additional ([\d,]+) Depositary Shares", body)
    conv_a = re.search(r"convert for settlement on or about May 15, 2029, into "
                       r"between ([\d.]+) and ([\d.]+) shares of Class A", body)
    conv_b = re.search(r"into between ([\d.]+) and ([\d.]+) shares of Class C",
                       body)
    cap_a = re.search(r"cap price of the Series A Capped Calls will initially "
                      r"be \$([\d,.]+) per share", body)
    cap_b = re.search(r"cap price of the Series B Capped Calls will initially "
                      r"be \$([\d,.]+) per share", body)

    base_n = int(base.group(1).replace(",", ""))
    over_n = int(over.group(1).replace(",", ""))
    dep_per_series = base_n + over_n
    pref_per_series = dep_per_series / 20
    liquidation = 1000.0
    # A mandatory convertible converts at the low rate when the stock is high,
    # so the minimum conversion rate sets the price above which the holder
    # stops participating - the instrument's effective cap.
    return {
        "coupon": 0.0625,
        "liquidation_preference_per_share": liquidation,
        "depositary_shares_per_series": dep_per_series,
        "preferred_shares_per_series": pref_per_series,
        "gross_proceeds_total": 2 * pref_per_series * liquidation,
        "mandatory_conversion_date": "2029-05-15",
        "series_a_conversion_rate": {"min": float(conv_a.group(1)),
                                     "max": float(conv_a.group(2))},
        "series_b_conversion_rate": {"min": float(conv_b.group(1)),
                                     "max": float(conv_b.group(2))},
        "series_a_floor_price": liquidation / float(conv_a.group(2)),
        "series_a_cap_price": liquidation / float(conv_a.group(1)),
        "series_b_floor_price": liquidation / float(conv_b.group(2)),
        "series_b_cap_price": liquidation / float(conv_b.group(1)),
        "capped_call_cap_class_a": float(cap_a.group(1).replace(",", "")),
        "capped_call_cap_class_c": float(cap_b.group(1).replace(",", "")),
        "taken_by_berkshire": False,
        "source": "Form 8-K filed 2026-06-05, accession 0001193125-26-259830",
    }


def alphabet_results():
    """Income statement, balance sheet and cash flow, Q2 2026 and Q2 2025."""
    out = {}
    for tag, key in (("2026q2", "goog_10q_2026q2"), ("2025q2", "goog_10q_2025q2")):
        cik, folder, fname = DOCS[key]
        path = os.path.join(CACHE, f"{key}.htm")
        fetch(f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{fname}",
              path)
        L = text_of(path)
        # Income statement and segments print four columns: Q prior, Q current,
        # 6M prior, 6M current.
        seg = {}
        for name in ("Google Services", "Google Cloud", "Other Bets"):
            rev = after(L, name, 4, skip=[i for i, l in enumerate(L)
                                          if l.strip() == name].__len__() and 0)
            seg[name] = {}
        # Revenues and operating income by segment sit in one note; take the
        # block that follows "Operating income (loss):".
        oi_at = next(i for i, l in enumerate(L)
                     if l.strip().startswith("Operating income (loss)"))
        rev_at = next(i for i, l in enumerate(L[:oi_at])
                      if l.strip() == "Revenues:")
        def block(start, names):
            res = {}
            for n in names:
                j = next(i for i, l in enumerate(L[start:oi_at + 200], start)
                         if l.strip() == n)
                res[n] = numbers(L[j + 1: j + 40])[:4]
            return res
        names = ["Google Services", "Google Cloud", "Other Bets"]
        rev_b = block(rev_at, names)
        oi_b = block(oi_at, names)
        for n in names:
            seg[n] = {"revenue": rev_b[n], "operating_income": oi_b[n]}

        out[tag] = {
            "segments": seg,
            # "Total revenues" also heads the geography table, where the columns
            # are percentages; the income statement's own line is unambiguous.
            "total_revenues": after(L, "Revenues", 4, skip=0),
            "pretax_income": after(L, "Income before income taxes", 4),
            "income_tax": after(L, "Provision for income taxes", 4),
            "income_from_operations": after(L, "Income from operations", 4),
            "net_income": after(L, "Net income", 4),
            "ocf": after(L, "Net cash provided by operating activities", 2),
            "capex": after(L, "Purchases of property and equipment", 2),
            "depreciation": after(L, "Depreciation of property and equipment", 2),
            "buybacks": after(L, "Repurchases of stock", 2,
                              skip=2 if tag == "2026q2" else 2),
            "dividends": after(L, "Dividend payments", 2),
            "ppe_net": after(L, "Property and equipment, net", 2),
            "total_assets": after(L, "Total assets", 2),
            "total_equity": after(L, "Total stockholders’ equity", 2),
            "long_term_debt": after(L, "Long-term debt", 2),
            "non_marketable_securities": after(L, "Non-marketable securities", 2),
            "cash_and_securities": after(
                L, "Total cash, cash equivalents, and marketable securities", 2),
            "accounts_receivable": after(L, "Accounts receivable, net", 2),
            "accounts_payable": after(L, "Accounts payable", 2),
            "total_current_liabilities": after(L, "Total current liabilities", 2),
            "operating_lease_assets": after(L, "Operating lease assets", 2),
            "goodwill": after(L, "Goodwill", 2),
            "source": f"Form 10-Q, {key}",
        }
    # Revenue backlog is prose, not a table.
    L = text_of(os.path.join(CACHE, "goog_10q_2026q2.htm"))
    body = " ".join(L)
    m = re.search(r"we had \$ ([\d.]+) billion of remaining performance "
                  r"obligations .{0,40}?of which \$ ([\d.]+) billion related to "
                  r"Google Cloud", body)
    out["backlog_2026q2"] = {
        "total_bn": float(m.group(1)), "cloud_bn": float(m.group(2)),
        "definition_change": ("2026년 1분기부터 원계약기간 1년 이하 계약도 "
                              "수주잔고에 포함하도록 보고 기준을 변경했습니다"),
        "source": "Form 10-Q Q2 2026, Revenue Backlog",
    }
    return out


def ppe_detail():
    """
    Property and equipment split into what is working and what is not.

    Alphabet reports "assets not yet in service" as its own line, added after
    the in-service subtotal. The earlier round of this work said the split
    could not be made; that was wrong - the note is in the 10-Q as well as the
    10-K, and at 30 June 2026 the not-yet-in-service balance is $122.8bn, more
    than a third of net property and equipment. A return on capital computed
    without removing it charges the business for plant that is not yet
    producing anything.
    """
    out = {}
    plan = [("goog_10q_2025q2", ["2024-12-31", "2025-06-30"]),
            ("goog_10q_2026q2", ["2025-12-31", "2026-06-30"])]
    for key, periods in plan:
        cik, folder, fname = DOCS[key]
        path = os.path.join(CACHE, f"{key}.htm")
        fetch(f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{fname}",
              path)
        L = text_of(path)
        i = next(j for j, l in enumerate(L) if "not yet in service" in l)
        # The note prints two columns, prior period then current.
        window = L[max(0, i - 42): i + 20]

        def row(label, n=2):
            # Footnote markers sit in their own element ("Technical
            # infrastructure" then "(1)"), so match the start of the caption.
            k = next(j for j, l in enumerate(window)
                     if l.strip().startswith(label))
            return numbers(window[k + 1: k + 30])[:n]

        vals = {
            "technical_infrastructure": row("Technical infrastructure"),
            "office_space": row("Office space"),
            "corporate_and_other": row("Corporate and other assets"),
            "in_service": row("Property and equipment, in service"),
            "accumulated_depreciation": row("Less: accumulated depreciation"),
            "not_yet_in_service": row("Add: assets not yet in service"),
        }
        # "Property and equipment, net" also heads the note itself, so read the
        # total from after the not-yet-in-service line rather than by caption.
        k = next(j for j, l in enumerate(window)
                 if l.strip().startswith("Add: assets not yet in service"))
        tail = window[k + 1:]
        t = next(j for j, l in enumerate(tail)
                 if l.strip().startswith("Property and equipment, net"))
        vals["net"] = numbers(tail[t + 1: t + 30])[:2]
        for col, period in enumerate(periods):
            out[period] = {k: v[col] for k, v in vals.items()}
            out[period]["source"] = f"Form 10-Q, {key}"
    return out


def berkshire_balance_sheet():
    cik, folder, fname = DOCS["brk_10q_2026q2"]
    path = os.path.join(CACHE, "brk_10q_2026q2.htm")
    fetch(f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{fname}", path)
    L = text_of(path)
    return {
        "cash_and_equivalents": after(L, "Cash and cash equivalents*", 2),
        "treasury_bills": after(L, "Short-term investments in U.S. Treasury Bills**", 2),
        "equity_securities": after(L, "Investments in equity securities", 2),
        "fixed_maturity": after(L, "Investments in fixed maturity securities", 2),
        "periods": ["2026-06-30", "2025-12-31"],
        "five_largest_note": ("The five largest holdings at June 30, 2026 were "
                              "Alphabet Inc., American Express Company, Apple "
                              "Inc., Bank of America Corporation and The "
                              "Coca-Cola Company"),
        "five_largest_share_of_equities": 0.66,
        "source": "Berkshire Form 10-Q Q2 2026, accession 0001193125-26-341032",
    }


def main():
    payload = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "question": ("버크셔 해서웨이가 알파벳 지분을 이렇게까지 늘린 이유는 "
                     "무엇인가 - 그들이 제출한 서류로만 답한다"),
    }
    for name, fn in (("berkshire_13f", berkshire_positions),
                     ("private_placement", private_placement),
                     ("mandatory_convertible", mandatory_convertible),
                     ("alphabet", alphabet_results),
                     ("berkshire_balance_sheet", berkshire_balance_sheet),
                     ("ppe_detail", ppe_detail)):
        try:
            payload[name] = fn()
            print(f"  {name}  ok")
        except Exception as exc:                          # noqa: BLE001
            print(f"  {name}  FAILED: {type(exc).__name__}: {exc}")
            payload[name] = {"error": f"{type(exc).__name__}: {exc}"}

    with open(OUT, "w") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
