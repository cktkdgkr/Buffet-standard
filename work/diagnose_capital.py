"""
Which study got invested capital right.

The reconciliation says the denominator is responsible for 154 of the 179
disagreements, which is an observation, not a verdict. This settles it by
taking the three inputs apart - equity, debt, cash - and asking of each
disagreement whether the figure is checkable against something neither study
produced.

Debt is checkable. A company that filed a long-term debt tag in its 10-K had
long-term debt; if a study recorded none, the study is wrong, and no judgment
call is involved. That one test turns out to explain most of the gap.

Writes work/roic/capital_diagnosis.json.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "roic", "roic_raw.json")
NEW = os.path.join(HERE, "roic", "roic.json")
OLD = os.path.join(HERE, "analysis.json")
OUT = os.path.join(HERE, "roic", "capital_diagnosis.json")

DEBT_TAGS = ("long_term_debt_noncurrent", "long_term_debt_total",
             "long_term_debt_current", "debt_current_total",
             "short_term_debt")


def main():
    raw = {c["ticker"]: {y["period_end"]: y for y in c["years"]}
           for c in json.load(open(RAW))["companies"]}
    new = json.load(open(NEW))
    old = {c["ticker"]: c for c in json.load(open(OLD))["companies"]}

    findings = {"old_missed_long_term_debt": [], "old_missed_all_debt": [],
                "new_debt_larger_other": [], "cash_differs": [],
                "equity_differs": [], "agree": []}

    for comp in new["companies"]:
        tk = comp["ticker"]
        oc = old.get(tk)
        if oc is None:
            continue
        o_years = {y["period_end"]: y for y in oc["years"]
                   if y.get("period_end")}
        for y in comp["years"]:
            if not 2016 <= y["fiscal_year"] <= 2025:
                continue
            o = o_years.get(y["period_end"])
            if o is None:
                continue
            r = o["raw"]
            src = raw[tk].get(y["period_end"], {})
            label = f"{tk} FY{y['fiscal_year']}"

            old_debt = (r.get("long_term_debt") or 0) + \
                       (r.get("short_term_debt") or 0)
            new_debt = y["interest_bearing_debt"]

            # Is there a filed long-term debt fact for this balance sheet date?
            filed_lt = next((src.get(t) for t in ("long_term_debt_noncurrent",
                                                  "long_term_debt_total")
                             if src.get(t)), None)

            if filed_lt and not r.get("long_term_debt"):
                findings["old_missed_long_term_debt"].append({
                    "key": label,
                    "filed_long_term_debt": filed_lt,
                    "old_long_term_debt": r.get("long_term_debt"),
                    "old_total_debt": old_debt, "new_total_debt": new_debt,
                    "tag": src.get("_tag_long_term_debt_noncurrent")
                           or src.get("_tag_long_term_debt_total"),
                    "roic_old": o.get("roic"), "roic_new": y.get("roic"),
                })
                if old_debt == 0:
                    findings["old_missed_all_debt"].append(label)
            elif new_debt is not None and abs(new_debt - old_debt) > \
                    max(0.02 * max(abs(new_debt), abs(old_debt)), 1e8):
                findings["new_debt_larger_other"].append({
                    "key": label, "old": old_debt, "new": new_debt,
                    "note": y["debt_note"],
                })

            nc, oc_ = y["cash_and_short_term_investments"], r.get("cash")
            if None not in (nc, oc_) and abs(nc - oc_) > \
                    max(0.02 * max(abs(nc), abs(oc_)), 1e8):
                findings["cash_differs"].append({
                    "key": label, "old": oc_, "new": nc,
                    "note": y["cash_note"],
                    "short_term_investments":
                        src.get("short_term_investments"),
                })

            ne, oe = y["total_equity"], r.get("total_equity")
            if None not in (ne, oe) and abs(ne - oe) > \
                    max(0.02 * max(abs(ne), abs(oe)), 1e8):
                findings["equity_differs"].append({
                    "key": label, "old": oe, "new": ne,
                    "noncontrolling_interest": y.get(
                        "noncontrolling_interest"),
                })

    with open(OUT, "w") as fh:
        json.dump(findings, fh, indent=1, ensure_ascii=False)

    md = findings["old_missed_long_term_debt"]
    print("구 조사가 공시된 장기차입금을 누락한 기업-연도: "
          f"{len(md)}건")
    print(f"  그중 차입금을 전액 0으로 본 경우: "
          f"{len(findings['old_missed_all_debt'])}건\n")
    tally = {}
    for m in md:
        tally[m["key"].split()[0]] = tally.get(m["key"].split()[0], 0) + 1
    print("  기업별 누락 연수")
    for tk, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"    {tk:<7}{n:>3}년")

    print(f"\n  누락 규모 상위 12건")
    print(f"    {'기업-연도':<14}{'공시 장기차입금':>16}{'구 차입금':>12}"
          f"{'신규 차입금':>13}{'구 ROIC':>9}{'신규':>9}")
    for m in sorted(md, key=lambda m: -(m["filed_long_term_debt"] or 0))[:12]:
        print(f"    {m['key']:<14}{m['filed_long_term_debt']/1e6:>16,.0f}"
              f"{m['old_total_debt']/1e6:>12,.0f}"
              f"{(m['new_total_debt'] or 0)/1e6:>13,.0f}"
              f"{(m['roic_old'] or 0):>9.1%}{(m['roic_new'] or 0):>9.1%}")

    for key, title in (("cash_differs", "현금 차이"),
                       ("equity_differs", "자기자본 차이"),
                       ("new_debt_larger_other", "기타 차입금 차이")):
        rows = findings[key]
        print(f"\n{title}: {len(rows)}건")
        for m in rows[:8]:
            print(f"    {m['key']:<14}구 {m['old']/1e6:>12,.0f}  "
                  f"신규 {m['new']/1e6:>12,.0f}   "
                  f"{m.get('note') or m.get('noncontrolling_interest') or ''}")

    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
