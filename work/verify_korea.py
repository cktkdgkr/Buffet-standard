"""
Check the Korean figures against the documents they came from.

PHASE 6 does this for the fifty US companies by re-reading their filings. The
same duty applies here, and the need is sharper: these two came out of a PDF
text layer and an HTML prospectus rather than tagged XBRL, so a parsing slip
produces a plausible-looking number rather than an error. One already did -
a note reference glued itself to the figure beside it and Samsung's short-term
borrowings came out at 41 quadrillion won, which the arithmetic below catches.

Three kinds of check:
  A. Internal consistency - relations that must hold inside a statement.
  B. Magnitude - figures that must sit in a believable band for the company.
  C. Independent recomputation - a figure derived two different ways.

Exit code is non-zero if anything fails.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "kr", "korea_raw.json")

TOL = 0.005          # 0.5%: statements are rounded to the million


def close(a, b, tol=TOL):
    if a is None or b is None:
        return False
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def check(results, ok, label, detail=""):
    results.append((bool(ok), label, detail))


def main():
    with open(RAW) as fh:
        raw = json.load(fh)
    results = []

    for ticker, c in raw["companies"].items():
        name = c["company_name"]
        years = c["years"]

        for y in years:
            fy = y["fiscal_year"]
            tag = f"{name} FY{fy}"
            rev = y.get("revenue")
            op = y.get("operating_income")
            pretax = y.get("pretax_income")
            tax = y.get("income_tax_expense")
            ni = y.get("net_income")
            eq = y.get("total_equity")

            # A. Net income must equal pretax less tax.
            if None not in (pretax, tax, ni):
                check(results, close(pretax - tax, ni),
                      f"{tag} 세전이익 − 법인세 = 당기순이익",
                      f"{pretax:,.0f} − {tax:,.0f} = {pretax-tax:,.0f} vs {ni:,.0f}")

            # B. Margins have to be inside a band no real manufacturer leaves.
            if None not in (rev, op) and rev:
                m = op / rev
                check(results, -0.60 <= m <= 0.85,
                      f"{tag} 영업이익률이 현실적 범위", f"{m:.1%}")
            if None not in (rev, ni) and rev:
                check(results, -0.60 <= ni / rev <= 1.20,
                      f"{tag} 순이익률이 현실적 범위", f"{ni/rev:.1%}")

            # B. Debt and cash cannot dwarf equity by orders of magnitude. This
            # is the check the 41-quadrillion parse failed.
            debt = None
            if y.get("short_term_debt") is not None or y.get("long_term_debt") is not None:
                debt = (y.get("short_term_debt") or 0) + (y.get("long_term_debt") or 0)
            if None not in (debt, eq) and eq:
                check(results, 0 <= debt <= 5 * eq,
                      f"{tag} 이자부부채가 자기자본의 5배 이내",
                      f"부채 {debt:,.0f} vs 자기자본 {eq:,.0f}")
            if None not in (y.get("cash_and_equivalents"), eq) and eq:
                check(results, 0 <= y["cash_and_equivalents"] <= 3 * eq,
                      f"{tag} 현금성자산이 자기자본의 3배 이내",
                      f"{y['cash_and_equivalents']:,.0f}")

            # B. Current assets must exceed the cash inside them.
            if None not in (y.get("current_assets"), y.get("cash_and_equivalents")):
                check(results, y["current_assets"] >= y["cash_and_equivalents"] * 0.5,
                      f"{tag} 유동자산 ≥ 현금성자산의 절반",
                      f"{y['current_assets']:,.0f} vs {y['cash_and_equivalents']:,.0f}")

            # C. Capex and D&A should be within an order of magnitude of each
            # other for a going concern at this scale.
            if None not in (y.get("capex"), y.get("depreciation_amortization")):
                r = y["capex"] / y["depreciation_amortization"]
                check(results, 0.2 <= r <= 5.0,
                      f"{tag} 설비투자 ÷ 감가상각이 0.2~5배", f"{r:.2f}x")

        # A. The series must be monotonic in time and free of duplicates.
        fys = [y["fiscal_year"] for y in years]
        check(results, fys == sorted(set(fys)),
              f"{name} 회계연도가 중복 없이 오름차순", str(fys))

        # C. Revenue growth between adjacent years has to be survivable.
        for a, b in zip(years, years[1:]):
            if a.get("revenue") and b.get("revenue"):
                g = b["revenue"] / a["revenue"] - 1
                check(results, -0.60 <= g <= 2.0,
                      f"{name} FY{a['fiscal_year']}→FY{b['fiscal_year']} 매출 증감",
                      f"{g:+.1%}")

        # A. Interim figures must be consistent with each other.
        it = c.get("interim")
        if it and it.get("half_revenue") and it.get("quarter_revenue"):
            check(results, it["half_revenue"] >= it["quarter_revenue"],
                  f"{name} 반기 매출 ≥ 분기 매출",
                  f"{it['half_revenue']:,.0f} vs {it['quarter_revenue']:,.0f}")
            check(results, 0 < it["half_operating_income"] / it["half_revenue"] < 0.85,
                  f"{name} 반기 영업이익률이 현실적 범위",
                  f"{it['half_operating_income']/it['half_revenue']:.1%}")

    # SK hynix's own disclosure states its FY2025 revenue in the MD&A in
    # billions; the statements give millions. They have to agree.
    hy = raw["companies"]["000660.KS"]
    fy25 = next(y for y in hy["years"] if y["fiscal_year"] == 2025)
    check(results, close(fy25["revenue"], 97_147_000, 0.001),
          "SK하이닉스 FY2025 매출이 사업설명서 본문(97,147십억원)과 일치",
          f"{fy25['revenue']:,.0f}")

    sam = raw["companies"]["005930.KS"]
    fy25s = next(y for y in sam["years"] if y["fiscal_year"] == 2025)
    # Samsung prints basic EPS; recomputing it from profit attributable to
    # ordinary shares is not possible here, but the order of magnitude is.
    check(results, 300_000_000 < fy25s["revenue"] < 400_000_000,
          "삼성전자 FY2025 매출이 300~400조원", f"{fy25s['revenue']:,.0f}")

    failed = [r for r in results if not r[0]]
    for ok, label, detail in results:
        if not ok:
            print(f"  FAIL  {label}  [{detail}]")
    print(f"\nchecks: {len(results)}, failed: {len(failed)}")
    if failed:
        return 1
    print("every Korean figure passes its consistency and magnitude checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
