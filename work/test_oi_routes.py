"""
Which reconstruction of operating income to trust, settled by measurement.

Eighteen of the fifty companies file an income statement with no
operating-income subtotal - Lilly, Merck, J&J, IBM, Exxon, Chevron, GE, KLA and
the banks. ROIC still needs a numerator for them, so the subtotal has to be
built from the lines they do file. There are several ways to build it and they
do not agree, so rather than pick one on plausibility, each is tested against
the reported subtotal on the company-years where both exist.

A route counts as matching when it lands within 2% of the reported figure.
Run it with --tolerance to see how the ranking moves; the ordering is stable
from 0.5% to 5%.

    python3 test_oi_routes.py
"""

import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "roic", "roic_raw.json")
OUT = os.path.join(HERE, "roic", "oi_routes.json")


def v(row, key):
    x = row.get(key)
    return None if x is None else float(x)


def route_b(r):
    gp, ox = v(r, "gross_profit"), v(r, "operating_expenses")
    return None if None in (gp, ox) else gp - ox


def route_d(r):
    rev, cor, ox = v(r, "revenue"), v(r, "cost_of_revenue"), v(r, "operating_expenses")
    return None if None in (rev, cor, ox) else rev - cor - ox


def route_c(r):
    rev, ce = v(r, "revenue"), v(r, "costs_and_expenses")
    return None if None in (rev, ce) else rev - ce


def route_e(r):
    gp = v(r, "gross_profit")
    rd, sga, sm = (v(r, "research_and_development"),
                   v(r, "selling_general_admin"), v(r, "selling_and_marketing"))
    if gp is None or (rd is None and sga is None and sm is None):
        return None
    return gp - (rd or 0) - (sga or 0) - (sm or 0)


def route_f(r):
    pre, non = v(r, "pretax_income"), v(r, "nonoperating_income")
    return None if None in (pre, non) else pre - non


def route_g(r):
    """
    Bottom-up EBIT: pretax income, add back the cost of debt, take out the
    income the cash pile earned. The earlier audit rejected pretax + interest
    expense on its own, because leaving investment income in the numerator
    while the denominator subtracts the cash that produced it counts the same
    cash twice. Route H below is that rejected version, kept so the size of
    the error is on the record rather than asserted.
    """
    pre, ie, ii = (v(r, "pretax_income"), v(r, "interest_expense"),
                   v(r, "investment_income_interest"))
    if pre is None or ie is None:
        return None
    return pre + ie - (ii or 0)


def route_h(r):
    pre, ie = v(r, "pretax_income"), v(r, "interest_expense")
    return None if None in (pre, ie) else pre + ie


ROUTES = [
    ("B  매출총이익 − 영업비용", route_b),
    ("D  매출 − 매출원가 − 영업비용", route_d),
    ("C  매출 − 총비용", route_c),
    ("E  매출총이익 − R&D − 판관비", route_e),
    ("G  세전이익 + 이자비용 − 이자·투자수익", route_g),
    ("H  세전이익 + 이자비용 (감사에서 기각된 방식)", route_h),
    ("F  세전이익 − 영업외수익", route_f),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tolerance", type=float, default=0.02)
    a = ap.parse_args()
    tol = a.tolerance

    with open(RAW) as fh:
        raw = json.load(fh)

    results = []
    for label, fn in ROUTES:
        tested = hit = 0
        errs = []
        for c in raw["companies"]:
            for y in c["years"]:
                rep = v(y, "operating_income")
                if rep is None or abs(rep) < 1e6:
                    continue
                got = fn(y)
                if got is None:
                    continue
                tested += 1
                err = abs(got - rep) / abs(rep)
                errs.append(err)
                if err <= tol:
                    hit += 1
        errs.sort()
        results.append({
            "route": label, "tested": tested, "matched": hit,
            "accuracy": hit / tested if tested else None,
            "median_error": errs[len(errs) // 2] if errs else None,
        })

    results.sort(key=lambda r: (-(r["accuracy"] or 0), -r["tested"]))
    with open(OUT, "w") as fh:
        json.dump({"tolerance": tol, "routes": results}, fh,
                  indent=1, ensure_ascii=False)

    print(f"보고된 영업이익 소계와의 일치율 (허용오차 ±{tol:.1%})\n")
    print(f"{'구성 경로':<44}{'검정':>7}{'일치':>7}{'정확도':>9}{'중위오차':>10}")
    for r in results:
        print(f"{r['route']:<44}{r['tested']:>7}{r['matched']:>7}"
              f"{(r['accuracy'] or 0):>9.1%}"
              f"{(r['median_error'] or 0):>10.2%}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()


def verdict_impact():
    """
    The ±2% pass rate is not the statistic this decision needs.

    ROIC here is compared against a single 10% hurdle, so what matters is not
    whether a reconstructed numerator reproduces the reported one exactly, but
    whether it ever moves a company-year across that line. A route with a 3%
    median error on the numerator moves ROIC by 3% of itself - 15.0% becomes
    15.5% - which changes no verdict at all. A route that is usually close but
    occasionally off by half is a different matter.

    So: on every company-year where operating income IS reported, compute ROIC
    both ways and count the flips.
    """
    import statistics

    with open(RAW) as fh:
        raw = json.load(fh)

    from analyse_roic import build_debt, build_cash, effective_tax, WACC

    stats = {label: {"n": 0, "flips": 0, "gaps": [], "rel": []}
             for label, _ in ROUTES}

    for c in raw["companies"]:
        rows = sorted(c["years"], key=lambda y: y["period_end"])
        caps = []
        for r in rows:
            eq = v(r, "total_equity")
            debt, _ = build_debt(r)
            cash, _ = build_cash(r)
            caps.append(None if None in (eq, debt, cash) else eq + debt - cash)
        for i, r in enumerate(rows):
            rep = v(r, "operating_income")
            if rep is None or abs(rep) < 1e6:
                continue
            ic = caps[i]
            if ic is None:
                continue
            avg = ic if i == 0 or caps[i - 1] is None else (ic + caps[i - 1]) / 2
            if avg is None or avg <= 0:
                continue
            tax, _ = effective_tax(r)
            true_roic = rep * (1 - tax) / avg
            for label, fn in ROUTES:
                got = fn(r)
                if got is None:
                    continue
                alt = got * (1 - tax) / avg
                s = stats[label]
                s["n"] += 1
                s["gaps"].append(abs(alt - true_roic))
                s["rel"].append(abs(alt - true_roic) / max(abs(true_roic), 1e-9))
                if (true_roic > WACC) != (alt > WACC):
                    s["flips"] += 1

    rows_out = []
    for label, _ in ROUTES:
        s = stats[label]
        if not s["n"]:
            continue
        gaps = sorted(s["gaps"])
        rows_out.append({
            "route": label, "n": s["n"], "flips": s["flips"],
            "flip_rate": s["flips"] / s["n"],
            "roic_gap_median": statistics.median(gaps),
            "roic_gap_p90": gaps[int(len(gaps) * 0.9)],
        })
    rows_out.sort(key=lambda r: r["flip_rate"])

    print("\n\n10% 문턱 판정이 뒤집히는 빈도 "
          "(영업이익이 보고된 연도에서, 보고치 기준 ROIC와 비교)\n")
    print(f"{'구성 경로':<44}{'검정':>7}{'판정뒤집힘':>11}{'비율':>8}"
          f"{'ROIC 중위격차':>13}{'90분위':>9}")
    for r in rows_out:
        print(f"{r['route']:<44}{r['n']:>7}{r['flips']:>11}"
              f"{r['flip_rate']:>8.1%}{r['roic_gap_median']:>13.2%}"
              f"{r['roic_gap_p90']:>9.2%}")
    return rows_out
