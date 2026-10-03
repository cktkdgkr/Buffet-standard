"""
Where the independent re-derivation disagrees with the first study, and which
one is right.

The two were built to disagree if either was wrong. The first study (analyse.py
-> analysis.json) reads figures out of filing text; this one (collect_roic.py ->
analyse_roic.py) pulls them from the XBRL companyfacts API and never looks at
the other's output. Same definition, independent paths. A gap between them is
therefore evidence about one of the two, and the point of this script is to
stop guessing which.

Each company-year is matched on period end, not on fiscal-year label, because
the two label a January year-end differently and matching on the label would
align Nvidia's FY2025 with its FY2026.

Disagreements are classified by where they come from - numerator, denominator,
tax rate - and the ones that cross the 10% hurdle are listed in full, because
those are the only ones that change an answer.

Writes work/roic/reconciliation.json.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
NEW = os.path.join(HERE, "roic", "roic.json")
OLD = os.path.join(HERE, "analysis.json")
OUT = os.path.join(HERE, "roic", "reconciliation.json")

WACC = 0.10
MATERIAL = 0.01          # 1pp of ROIC
BIG = 0.05               # 5pp of ROIC


def rel(a, b):
    if a is None or b is None:
        return None
    if abs(b) < 1e-9:
        return None if abs(a) < 1e-9 else 1.0
    return (a - b) / abs(b)


def classify(n, o):
    """Attribute a ROIC gap to the piece of the formula that moved."""
    causes = []
    for label, key_new, key_old in (
        ("영업이익(분자)", "operating_income", "ebit"),
        ("투하자본(분모)", "invested_capital_avg", "invested_capital_avg"),
        ("실효세율", "effective_tax_rate", "tax_rate"),
    ):
        r = rel(n.get(key_new), o.get(key_old))
        if r is not None and abs(r) > 0.02:
            causes.append(f"{label} {r:+.1%}")
    if n.get("operating_income_route") != "reported":
        causes.append(f"신규 분자 추정경로({n['operating_income_route']})")
    if o.get("ebit_method") and "pretax" in str(o.get("ebit_method")):
        causes.append("구 분자 = 세전이익+이자")
    return causes or ["원인 불명 — 개별 확인 필요"]


def main():
    with open(NEW) as fh:
        new = json.load(fh)
    with open(OLD) as fh:
        old = json.load(fh)

    old_by = {c["ticker"]: c for c in old["companies"]}

    rows, only_new, only_old, missing_company, unmatchable = [], [], [], [], []
    for c in new["companies"]:
        oc = old_by.get(c["ticker"])
        if oc is None:
            missing_company.append(c["ticker"])
            continue
        # A handful of the old study's rows carry no period end at all; those
        # cannot be matched on anything reliable and are counted separately
        # rather than guessed at by fiscal-year label.
        o_years = {y["period_end"]: y for y in oc["years"]
                   if y.get("period_end")}
        n_years = {y["period_end"]: y for y in c["years"]
                   if y.get("period_end")}
        unmatchable.extend(f"{c['ticker']} FY{y.get('fiscal_year')}"
                           for y in oc["years"] if not y.get("period_end"))
        for pe in sorted(set(n_years) | set(o_years)):
            n, o = n_years.get(pe), o_years.get(pe)
            if n is None:
                if 2016 <= int(pe[:4]) <= 2026 and o.get("roic") is not None:
                    only_old.append(f"{c['ticker']} {pe}")
                continue
            if not (2016 <= n["fiscal_year"] <= 2025):
                continue
            if o is None:
                if n.get("roic") is not None:
                    only_new.append(f"{c['ticker']} {pe}")
                continue
            nr, orr = n.get("roic"), o.get("roic")
            if nr is None and orr is None:
                continue
            gap = None if None in (nr, orr) else nr - orr
            flips = (None if None in (nr, orr)
                     else (nr > WACC) != (orr > WACC))
            rows.append({
                "ticker": c["ticker"], "name": c["company_name"],
                "period_end": pe, "fiscal_year": n["fiscal_year"],
                "roic_new": nr, "roic_old": orr, "gap_pp": gap,
                "hurdle_flips": flips,
                "oi_new": n.get("operating_income"),
                "oi_old": o.get("ebit"),
                "route_new": n.get("operating_income_route"),
                "method_old": o.get("ebit_method"),
                "cap_new": n.get("invested_capital_avg"),
                "cap_old": o.get("invested_capital_avg"),
                "tax_new": n.get("effective_tax_rate"),
                "tax_old": o.get("tax_rate"),
                "confidence_new": n.get("confidence"),
                "causes": (classify(n, o)
                           if gap is not None and abs(gap) > MATERIAL else []),
            })

    both = [r for r in rows if r["gap_pp"] is not None]
    agree = [r for r in both if abs(r["gap_pp"]) <= MATERIAL]
    differ = sorted((r for r in both if abs(r["gap_pp"]) > MATERIAL),
                    key=lambda r: -abs(r["gap_pp"]))
    flips = [r for r in both if r["hurdle_flips"]]
    new_only_rows = [r for r in rows if r["roic_old"] is None]
    old_only_rows = [r for r in rows if r["roic_new"] is None]

    cause_tally = {}
    for r in differ:
        for c in r["causes"]:
            key = c.split(" ")[0]
            cause_tally[key] = cause_tally.get(key, 0) + 1

    result = {
        "compared_company_years": len(both),
        "agree_within_1pp": len(agree),
        "differ_over_1pp": len(differ),
        "differ_over_5pp": sum(1 for r in differ if abs(r["gap_pp"]) > BIG),
        "hurdle_verdict_flips": len(flips),
        "new_covers_old_blank": len(new_only_rows),
        "old_covers_new_blank": len(old_only_rows),
        "cause_tally": cause_tally,
        "differences": differ,
        "flips": flips,
        "new_only": [f"{r['ticker']} FY{r['fiscal_year']}"
                     for r in new_only_rows],
        "old_only": [f"{r['ticker']} FY{r['fiscal_year']}"
                     for r in old_only_rows],
        "unmatchable_old_rows": unmatchable,
        "companies_absent_from_old_study": missing_company,
        "stale_method_note_in_analysis_json": old["method_notes"]["ebit"],
    }
    with open(OUT, "w") as fh:
        json.dump(result, fh, indent=1, ensure_ascii=False)

    print(f"대조 가능한 기업-연도 {len(both)}건\n")
    print(f"  1%p 이내 일치          {len(agree):>4}건  "
          f"({len(agree)/len(both):.1%})")
    print(f"  1%p 초과 불일치        {len(differ):>4}건")
    print(f"  5%p 초과 불일치        {result['differ_over_5pp']:>4}건")
    print(f"  10% 문턱 판정이 뒤집힘  {len(flips):>4}건")
    print(f"  신규만 산출 (구 공백)    {len(new_only_rows):>4}건")
    print(f"  구 조사만 산출          {len(old_only_rows):>4}건")

    if cause_tally:
        print("\n불일치 원인 (중복 집계)")
        for k, v in sorted(cause_tally.items(), key=lambda kv: -kv[1]):
            print(f"  {k:<24}{v:>4}건")

    if flips:
        print(f"\n문턱 판정이 바뀌는 {len(flips)}건 — 결론에 영향")
        print(f"  {'기업':<7}{'연도':<8}{'신규':>8}{'구':>8}{'차이':>8}  원인")
        for r in sorted(flips, key=lambda r: -abs(r["gap_pp"])):
            print(f"  {r['ticker']:<7}FY{r['fiscal_year']:<6}"
                  f"{r['roic_new']:>8.1%}{r['roic_old']:>8.1%}"
                  f"{r['gap_pp']:>+8.1%}  {', '.join(r['causes'])[:62]}")

    print(f"\n차이가 큰 상위 20건")
    print(f"  {'기업':<7}{'연도':<8}{'신규':>9}{'구':>9}{'차이':>9}  원인")
    for r in differ[:20]:
        print(f"  {r['ticker']:<7}FY{r['fiscal_year']:<6}"
              f"{r['roic_new']:>9.1%}{r['roic_old']:>9.1%}"
              f"{r['gap_pp']:>+9.1%}  {', '.join(r['causes'])[:58]}")

    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
