"""
Check the Samsung Biologics figures against the documents they came from.

Same duty as verify_korea.py, and the same reason: these came out of a PDF text
layer, not tagged XBRL, so a parsing slip yields a plausible number rather than
an error. Three kinds of check, plus a fourth this company specifically needs:

  A. Internal consistency  - relations that must hold inside a statement.
  B. Magnitude             - figures that must sit in a believable band.
  C. Independent recomputation - a figure derived two different ways.
  D. Basis continuity      - the join between the separate (CDMO) series and
                             the consolidated statements. The whole ten-year
                             series rests on the claim that the separate
                             statements are the same business the post-spin-off
                             group reports, so that claim is tested, not
                             assumed.

Exit code is non-zero if anything fails.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "kr", "sbl_raw.json")

TOL = 0.005


def close(a, b, tol=TOL):
    if a is None or b is None:
        return False
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def main():
    with open(RAW) as fh:
        raw = json.load(fh)
    years = {y["fiscal_year"]: y for y in raw["years"]}
    results = []

    def check(ok, label, detail=""):
        results.append((bool(ok), label, detail))

    bn = lambda v: "n/a" if v is None else f"{v/1e9:,.1f}십억원"

    # ---------------------------------------------------------------- A, B, C
    for fy, y in sorted(years.items()):
        tag = f"FY{fy}"
        rev, cos, gp = y.get("revenue"), y.get("cost_of_revenue"), y.get("gross_profit")
        sga, op = y.get("sga"), y.get("operating_income")
        pre, tax, ni = (y.get("pretax_income"), y.get("income_tax_expense"),
                        y.get("net_income"))

        # A. The income statement has to add up. Cost and SG&A are printed in
        # parentheses, so they arrive negative.
        if None not in (rev, cos, gp):
            check(close(rev + cos, gp) or close(rev - cos, gp),
                  f"{tag} 매출 − 매출원가 = 매출총이익",
                  f"{bn(rev)} − {bn(abs(cos))} vs {bn(gp)}")
        if None not in (gp, sga, op):
            check(close(gp + sga, op) or close(gp - sga, op),
                  f"{tag} 매출총이익 − 판관비 = 영업이익",
                  f"{bn(gp)} − {bn(abs(sga))} vs {bn(op)}")
        if None not in (pre, tax, ni):
            check(close(pre - tax, ni),
                  f"{tag} 세전이익 − 법인세 = 당기순이익",
                  f"{bn(pre)} − {bn(tax)} vs {bn(ni)}")

        # A. The balance sheet has to balance.
        ta, tl, te = y.get("total_assets"), y.get("total_liabilities"), y.get("total_equity")
        if None not in (ta, tl, te):
            check(close(ta, tl + te), f"{tag} 자산 = 부채 + 자본",
                  f"{bn(ta)} vs {bn(tl+te)}")

        # B. A contract manufacturer's margin band. FY2016 was the first year of
        # Plant 2 at low utilisation and ran at a loss, so the floor is wide.
        if None not in (rev, op) and rev:
            check(-0.30 <= op / rev <= 0.60,
                  f"{tag} 영업이익률이 현실적 범위", f"{op/rev:.1%}")

        # B. Debt and cash against equity.
        debt, eq = y.get("debt_total"), y.get("total_equity")
        if None not in (debt, eq) and eq:
            check(0 <= debt <= 2 * eq, f"{tag} 이자부부채가 자기자본의 2배 이내",
                  f"{bn(debt)} vs {bn(eq)}")
        cash = (y.get("cash_and_equivalents") or 0) + \
               (y.get("short_term_financial_instruments") or 0)
        if eq:
            check(0 <= cash <= 1.5 * eq, f"{tag} 현금성자산이 자기자본의 1.5배 이내",
                  bn(cash))

        # C. Capex against depreciation. A company building plants runs well
        # above 1x; the band only has to exclude a mis-parse by an order of
        # magnitude.
        capex, da = y.get("capex"), y.get("depreciation_amortization")
        if None not in (capex, da) and da:
            check(0.3 <= capex / da <= 8.0,
                  f"{tag} 설비투자 ÷ 감가상각이 0.3~8배", f"{capex/da:.2f}배")

        # C. Property, plant and equipment cannot fall while capex exceeds
        # depreciation by a wide margin.
        prev = years.get(fy - 1)
        if prev and None not in (y.get("ppe"), prev.get("ppe"), capex, da):
            implied = prev["ppe"] + capex - (y.get("depreciation") or da)
            check(abs(implied - y["ppe"]) <= 0.25 * max(1.0, y["ppe"]),
                  f"{tag} 유형자산 기초 + 설비투자 − 감가상각 ≈ 기말",
                  f"추정 {bn(implied)} vs 실제 {bn(y['ppe'])}")

    # B. Revenue growth between adjacent years has to be survivable. FY2022 is
    # the exception the basis change creates and is checked separately.
    fys = sorted(years)
    for a, b in zip(fys, fys[1:]):
        ra, rb = years[a].get("revenue"), years[b].get("revenue")
        if ra and rb:
            g = rb / ra - 1
            check(-0.20 <= g <= 1.00, f"FY{a}→FY{b} 매출 증감", f"{g:+.1%}")

    # ------------------------------------------------------------------- D
    # The series is only usable if the separate statements really are the
    # continuing (CDMO) business. Three identities test that.
    con = {int(k): v for k, v in raw["consolidated_reported"].items()}
    dis = raw["discontinued_operations"]

    check(close(years[2024]["revenue"], 3_497_145_675_782, 0.0001),
          "별도 FY2024 매출 = 연결 계속영업 FY2024 매출 (FY2025 보고서 비교연도)",
          f"{years[2024]['revenue']:,.0f}")
    check(close(con[2024]["revenue"],
                years[2024]["revenue"] + dis["revenue"][1], 0.0001),
          "연결 FY2024 매출 = 계속영업(CDMO) + 중단영업(바이오에피스)",
          f"{con[2024]['revenue']:,.0f} vs "
          f"{years[2024]['revenue'] + dis['revenue'][1]:,.0f}")
    check(close(years[2021]["revenue"], con[2021]["revenue"], 0.0001),
          "별도 FY2021 매출 = 연결 FY2021 매출 (에피스 연결 전이므로 동일해야 함)",
          f"{years[2021]['revenue']:,.0f} vs {con[2021]['revenue']:,.0f}")
    check(close(years[2025]["revenue"], con[2025]["revenue"], 0.0001),
          "별도 FY2025 매출 = 연결 FY2025 매출 (분할 후 CDMO 단일사업)",
          f"{years[2025]['revenue']:,.0f} vs {con[2025]['revenue']:,.0f}")

    # The segment note is the third, independent read on the same split.
    seg = raw["segment_note_fy2024"]
    check(close(seg["net_sales"]["2024_cdmo"] + seg["net_sales"]["2024_bio"],
                seg["net_sales"]["2024_total"], 0.0001),
          "FY2024 부문 순매출 합 = 연결 매출",
          f"{seg['net_sales']['2024_total']:,.0f}")
    check(close(seg["total_sales"]["2024_cdmo"], years[2024]["revenue"], 0.01),
          "FY2024 CDMO 부문 총매출(내부거래 포함) ≈ 별도 매출",
          f"{seg['total_sales']['2024_cdmo']:,.0f} vs "
          f"{years[2024]['revenue']:,.0f}")

    # ------------------------------------------------------------------- C
    # Independent recomputations against figures the company prints itself.
    sh = raw["shares"]
    eps = years[2025]["net_income"] / sh["weighted_average_2025"]
    check(close(eps, 23_671, 0.001), "FY2025 기본주당이익 재계산 = 공시치 23,671원",
          f"{eps:,.0f}원")
    check(sh["issued_2025"] == 46_290_951 and sh["issued_2024"] == 71_174_000,
          "분할 전후 발행주식수 (71,174,000 → 46,290,951)",
          f"{sh['issued_2024']:,} → {sh['issued_2025']:,}")

    geo = raw["concentration"]["geography"]
    gsum = sum(geo[k]["2025"] for k in geo)
    check(close(gsum, years[2025]["revenue"], 0.0001),
          "FY2025 지역별 매출 합 = 총매출", f"{gsum:,.0f}")

    it = raw["interim_2026"]
    check(it["h1_2026"]["revenue"] > it["q2_2026"]["revenue"] > 0,
          "2026 상반기 매출 > 2분기 매출",
          f"{it['h1_2026']['revenue']:,.0f} vs {it['q2_2026']['revenue']:,.0f}")
    # Cross-document: the interim's own FY2025 half-year comparative has to sit
    # inside the annual figure at a plausible share. Anything outside this band
    # means the two documents are not describing the same entity - which is the
    # mistake the spin-off makes easy to commit.
    share = it["h1_2025"]["revenue"] / years[2025]["revenue"]
    check(0.38 <= share <= 0.52,
          "2026 반기보고서의 2025 상반기 비교치가 FY2025 연간의 38~52%",
          f"{share:.1%}")
    m26 = it["h1_2026"]["operating_income"] / it["h1_2026"]["revenue"]
    check(0.20 <= m26 <= 0.60, "2026 상반기 영업이익률이 현실적 범위", f"{m26:.1%}")

    # A. The FY2025 balance sheet is smaller than FY2024's because the spin-off
    # removed the Bioepis carrying value. That has to be the explanation, not a
    # parsing slip: the fall in total assets should be close to the fall in the
    # investment line plus the cash paid out.
    d_assets = years[2024]["total_assets"] - years[2025]["total_assets"]
    d_inv = (years[2024]["investments_in_subs"]
             - years[2025]["investments_in_subs"])
    check(0.5 * d_inv <= d_assets <= 1.6 * d_inv,
          "FY2025 총자산 감소가 종속·관계기업투자 감소로 설명됨",
          f"자산 −{bn(d_assets)} vs 투자 −{bn(d_inv)}")

    failed = [r for r in results if not r[0]]
    for ok, label, detail in results:
        if not ok:
            print(f"  FAIL  {label}  [{detail}]")
    print(f"\nchecks: {len(results)}, failed: {len(failed)}")
    if failed:
        return 1
    print("삼성바이오로직스 수치 전부 정합성·자릿수·기준연결 검증 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
