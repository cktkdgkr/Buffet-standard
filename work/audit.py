"""
Full audit - a battery of checks looking for anything still wrong.

PHASE 6 proves each figure matches the filing it cites. That is necessary and
not sufficient: a figure can be faithfully transcribed and still be the wrong
figure, or be combined into a ratio that means nothing, or be scored by a rule
that rewards its own absence. This looks for those.

Checks are grouped by what they can catch:
  A. data integrity   - stale tags, gaps, impossible values
  B. derived metrics  - ratios outside any plausible range, broken identities
  C. scoring          - rules that misbehave on missing or extreme inputs
  D. consistency      - the three deliverables disagreeing with each other

Every finding prints with enough context to judge it. Some are expected and
benign; the point is that nothing goes unexamined.
"""

import json
import os
import re
import sys

WORK = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, WORK)
import report as rp                                      # noqa: E402

findings = []


def flag(severity, area, ticker, message):
    findings.append((severity, area, ticker, message))


# ---------------------------------------------------------------------------
# A. Data integrity
# ---------------------------------------------------------------------------

KEY_METRICS = ["revenue", "net_income", "total_equity", "cash_and_equivalents",
               "capex", "depreciation_amortization", "operating_cash_flow",
               "pretax_income", "income_tax_expense"]


def audit_raw(analysis):
    for c in analysis["companies"]:
        t = c["ticker"]
        path = os.path.join(WORK, "raw", f"{t}.json")
        raw = json.load(open(path))
        latest_fy = max((y["fiscal_year"] for y in c["years"]), default=None)

        for m in KEY_METRICS:
            node = raw.get("metrics", {}).get(m, {})
            series = node.get("series") or []
            if not series:
                continue
            years = [r["fiscal_year"] for r in series]

            # A1 - a series that stops years before the company's latest year is
            # being read as current when it is not.
            filled_note = (c.get("pretax_income_note") or "")
            if m == "pretax_income" and "summed" in filled_note:
                continue     # analysis rebuilds it from the domestic/foreign halves
            if latest_fy and max(years) < latest_fy - 1:
                flag("HIGH", "A1 stale series", t,
                     f"{m} via {node.get('xbrl_tag')} ends FY{max(years)}, "
                     f"company's latest year is FY{latest_fy}")

            # A2 - holes inside the covered window
            window = [y for y in years if y >= latest_fy - 9] if latest_fy else years
            if window:
                missing = sorted(set(range(min(window), max(window) + 1)) - set(window))
                if missing:
                    flag("MED", "A2 gap in series", t,
                         f"{m} missing FY{missing} between FY{min(window)} and FY{max(window)}")

            # A3 - signs that cannot happen
            for r in series:
                v = r["value"]
                if m in ("revenue", "total_equity", "cash_and_equivalents") and m == "revenue" and v < 0:
                    flag("HIGH", "A3 impossible sign", t, f"revenue FY{r['fiscal_year']} = {v}")
                if m in ("capex", "depreciation_amortization") and v < 0:
                    flag("MED", "A3 impossible sign", t, f"{m} FY{r['fiscal_year']} = {v} (expected positive)")

        # A4 - net margin outside any plausible band
        for y in c["years"]:
            rev, ni = y.get("revenue"), y.get("net_income")
            if rev and ni is not None and rev > 0:
                margin = ni / rev
                if margin > 0.70:
                    flag("MED", "A4 implausible margin", t,
                         f"FY{y['fiscal_year']} net margin {margin:.0%} - check revenue tag")
                if margin < -1.0:
                    flag("MED", "A4 implausible margin", t,
                         f"FY{y['fiscal_year']} net margin {margin:.0%}")

        # A5 - a share count that jumps hard suggests a split not adjusted away
        sh = [(y["fiscal_year"], y.get("shares_outstanding")) for y in c["years"]
              if y.get("shares_outstanding")]
        for (y0, s0), (y1, s1) in zip(sh, sh[1:]):
            if s0 and s1 and (s1 / s0 > 1.35 or s1 / s0 < 0.74):
                flag("MED", "A5 share-count jump", t,
                     f"FY{y0}->{y1} shares {s0/1e6:,.0f}M -> {s1/1e6:,.0f}M "
                     f"({s1/s0:.2f}x) - split adjustment or issuance?")

        # A6 - owner earnings should sit near operating cash flow less capex
        for y in c["years"]:
            oe = y.get("owner_earnings")
            raw_y = y.get("raw") or {}
            ocf, cx = raw_y.get("operating_cash_flow"), raw_y.get("capex")
            if oe is None or ocf is None or cx is None:
                continue
            fcf = ocf - cx
            scale = max(abs(fcf), abs(oe), 1e9)
            if abs(oe - fcf) / scale > 1.0:
                flag("LOW", "A6 owner earnings vs FCF", t,
                     f"FY{y['fiscal_year']} owner earnings {oe/1e9:.1f}B vs "
                     f"OCF-capex {fcf/1e9:.1f}B - large divergence")


# ---------------------------------------------------------------------------
# B. Derived metrics
# ---------------------------------------------------------------------------

def audit_derived(analysis):
    for c in analysis["companies"]:
        t = c["ticker"]
        for y in c["years"]:
            fy = y["fiscal_year"]
            # The score is built on gross invested capital, so an extreme
            # net-of-cash ROIC is a reported detail rather than an input.
            roic = y.get("roic")
            if roic is not None and (roic > 2.0 or roic < -1.0):
                flag("LOW", "B1 net ROIC out of range", t,
                     f"FY{fy} net ROIC {roic:.0%} (score uses the gross basis)")
            rg = y.get("roic_gross")
            if rg is not None and (rg > 2.0 or rg < -1.0):
                flag("HIGH", "B1 gross ROIC out of range", t, f"FY{fy} gross ROIC {rg:.0%}")
            roe = y.get("roe")
            if roe is not None and (roe > 3.0 or roe < -3.0):
                excluded = (c["summary"].get("roe_years_capped_as_unstable") or 0) > 0
                flag("LOW" if excluded else "MED", "B2 ROE out of range", t,
                     f"FY{fy} ROE {roe:.0%} - equity near zero"
                     + (" (capped at the aggregate ceiling)" if excluded else ""))
            nd = y.get("net_debt_to_ebitda")
            eb = y.get("ebitda")
            if nd is not None and eb is not None and eb < 0:
                flag("HIGH", "B3 ratio on negative EBITDA", t,
                     f"FY{fy} net debt/EBITDA {nd:.1f}x computed on EBITDA {eb/1e9:.1f}B")
            ic = y.get("interest_coverage")
            if ic is not None and ic < 0:
                flag("MED", "B4 negative interest coverage", t, f"FY{fy} {ic:.1f}x")

        s = c["summary"]
        # B5 - the maintenance band must bracket, never invert
        for k in ("conservative", "base", "optimistic"):
            lo = (s.get("dcf") or {}).get(k, {}).get("intrinsic_value")
            hi = (s.get("dcf_maintenance_capex") or {}).get(k, {}).get("intrinsic_value")
            if lo is not None and hi is not None and hi < lo - 1:
                flag("HIGH", "B5 inverted band", t,
                     f"{k}: maintenance-capex IV {hi/1e9:.0f}B below total-capex IV {lo/1e9:.0f}B")
        # B6 - implied return should be finite and sane where a value exists
        for key in ("implied_return_total_capex", "implied_return_maintenance_capex"):
            v = s.get(key)
            if v is not None and (v > 0.5 or v <= 0.025):
                flag("MED", "B6 implied return extreme", t, f"{key} = {v:.1%}")
        # B7 - EBIT construction should not flip between years
        methods = {y.get("ebit_method") for y in c["years"] if y.get("ebit")}
        methods = {m for m in methods if m and m != "DATA_UNAVAILABLE"}
        if len(methods) > 1:
            flag("LOW", "B7 mixed EBIT method", t, f"{sorted(methods)}")
        # B8 - a clamped tax rate in most years means the clamp is doing the work
        clamped = sum(1 for y in c["years"] if "clamped" in (y.get("tax_note") or ""))
        if c["years"] and clamped / len(c["years"]) > 0.5:
            flag("LOW", "B8 tax mostly clamped", t,
                 f"{clamped}/{len(c['years'])} years clamped")


# ---------------------------------------------------------------------------
# C. Scoring
# ---------------------------------------------------------------------------

def audit_scoring(analysis):
    for c in analysis["companies"]:
        if c["sector_treatment"] != "STANDARD":
            continue
        t = c["ticker"]
        s = c["summary"]
        s["_latest_revenue"] = next((r["revenue"] for r in reversed(c["years"])
                                     if r.get("revenue")), None)
        score, detail = rp.quality_score(s)

        # C1 - a component that pays full marks for an absent input
        if s.get("net_debt_to_ebitda_latest") is None and detail["순부채/EBITDA"] > 0:
            flag("HIGH", "C1 missing data scores points", t,
                 f"net debt/EBITDA is absent yet scores {detail['순부채/EBITDA']}/5")

        # C2 - a company with very few observed years scored on the same scale
        obs = s.get("roic_gross_years_observed") or 0
        if 0 < obs < 5:
            flag("MED", "C2 thin history scored", t,
                 f"only {obs} observed ROIC years but scored on the full scale "
                 f"(총점 {score})")

        # C3 - scoring a company that has no ROIC at all
        if obs == 0 and score > 0 and s.get("quality_scoreable", True):
            flag("HIGH", "C3 scored without ROIC", t,
                 f"no measurable ROIC in any year yet 총점 {score}")


# ---------------------------------------------------------------------------
# D. Cross-deliverable consistency
# ---------------------------------------------------------------------------

def audit_consistency(analysis):
    md = open(os.path.join(WORK, "REPORT.md")).read()

    # D1 - the Word payload must carry the same sections the markdown has
    payload_path = os.path.join(WORK, "_docx_payload.json")
    if os.path.exists(payload_path):
        payload = json.load(open(payload_path))
        md_sections = set(re.findall(r"^## (\d+)\.", md, re.M))
        if "7" in md_sections and not payload.get("alphabet"):
            flag("HIGH", "D1 Word behind markdown", "-",
                 "REPORT.md has section 7 (Alphabet case) but the Word payload "
                 "carries no data for it - the .docx is missing a section the "
                 "markdown reports")
        if payload.get("valuation_rows") and len(payload["valuation_rows"][0]) != 9:
            flag("HIGH", "D1 Word behind markdown", "-",
                 f"Word valuation table has {len(payload.get('valuation_rows', [{}])[0])} "
                 f"columns; markdown now has 9 (band + implied return + net cash)")

    # D2 - headline counts in the markdown must match the data
    std = [c for c in analysis["companies"] if c["sector_treatment"] == "STANDARD"]
    fin = [c for c in analysis["companies"] if c["sector_treatment"] == "FINANCIAL"]
    for label, n in (("비금융", len(std)), ("금융", len(fin))):
        for m in re.finditer(rf"(?<!비){label} (\d+)개", md):
            if int(m.group(1)) != n:
                flag("HIGH", "D2 count mismatch", "-",
                     f"markdown says {label} {m.group(1)}개, data has {n}")

    # D3 - every ticker in the data appears in the markdown ranking
    listed = set(re.findall(r"^\| \d+ \| ([A-Z\-]+) \|", md, re.M))
    listed |= set(re.findall(r"^\| ([A-Z\-]+) \| [^|]+ \| 어느 해에도", md, re.M))
    missing = {c["ticker"] for c in std} - listed
    if missing:
        flag("HIGH", "D3 company missing from report", "-", f"{sorted(missing)}")


def main():
    with open(os.path.join(WORK, "analysis.json")) as f:
        analysis = json.load(f)

    audit_raw(analysis)
    audit_derived(analysis)
    audit_scoring(analysis)
    audit_consistency(analysis)

    order = {"HIGH": 0, "MED": 1, "LOW": 2}
    findings.sort(key=lambda f: (order[f[0]], f[1], f[2]))
    by_sev = {}
    for sev, area, t, msg in findings:
        by_sev.setdefault(sev, []).append((area, t, msg))

    print(f"audit findings: {len(findings)}")
    for sev in ("HIGH", "MED", "LOW"):
        rows = by_sev.get(sev, [])
        if not rows:
            continue
        print(f"\n=== {sev} ({len(rows)}) ===")
        for area, t, msg in rows:
            print(f"  [{area}] {t}: {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
