"""
Correct the first study where the re-derivation showed it wrong.

What it changes, and why each change is a correction rather than a preference:

1. ROIC and its three inputs, for every non-financial company-year in
   FY2016-FY2025. The re-derivation's figures carry 9,867 passing checks,
   including anchors read off the face of the filings and tripwires that bound
   debt by total liabilities and cash by current assets. The first study's
   figures carry none. Where they disagree, the checked ones stand.

2. Long-term debt, which the first study recorded as nil in 27 company-years
   where the 10-K filed a long-term debt tag - all ten of Oracle's years, seven
   of Coca-Cola's, four of Broadcom's, three of Visa's. This is the single
   largest source of error: Oracle's invested capital came out at $12.6bn
   against $86.9bn of filed debt, and its FY2024 ROIC at 761%.

3. method_notes.ebit, which described the numerator as "pretax income +
   interest expense where both are tagged, else the reported operating-income
   subtotal". The per-year records show the opposite order - 340 years on the
   reported subtotal and 124 on pretax plus interest - so the note had the
   priority backwards and contradicted the implementation it documented.

What it does NOT change: prices, market caps, owner earnings, the DCFs and the
valuation verdicts. Those are a separate chain, and the net-cash figures behind
them were computed from different fields that are mostly right. The one that is
not - Oracle, where the study carries +$24.7bn of net cash against $81.3bn of
net debt - is recorded in the changelog rather than silently repaired, because
re-running a valuation is not a correction, it is a new analysis.

The original is kept at analysis.json.pre-roic-correction.
"""

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OLD = os.path.join(HERE, "analysis.json")
BACKUP = OLD + ".pre-roic-correction"
NEW = os.path.join(HERE, "roic", "roic.json")
LOG = os.path.join(HERE, "roic", "corrections.json")

FIELD_MAP = [
    ("roic", "roic"),
    ("ebit", "operating_income"),
    ("tax_rate", "effective_tax_rate"),
    ("nopat", "nopat"),
    ("invested_capital", "invested_capital"),
    ("invested_capital_avg", "invested_capital_avg"),
]


def main():
    with open(OLD) as fh:
        old = json.load(fh)
    with open(NEW) as fh:
        new = json.load(fh)

    if not os.path.exists(BACKUP):
        shutil.copy2(OLD, BACKUP)

    new_by = {c["ticker"]: c for c in new["companies"]}
    changes, untouched, net_debt_notes = [], [], []

    for oc in old["companies"]:
        nc = new_by.get(oc["ticker"])
        if nc is None:
            untouched.append(f"{oc['ticker']}: 재산출 대상 아님")
            continue
        if nc["is_financial"]:
            untouched.append(f"{oc['ticker']}: 금융업 — 양쪽 모두 ROIC 비산출")
            continue

        n_years = {y["period_end"]: y for y in nc["years"]}
        for oy in oc["years"]:
            pe = oy.get("period_end")
            if not pe or pe not in n_years:
                continue
            ny = n_years[pe]
            if not 2016 <= ny["fiscal_year"] <= 2025:
                continue

            before = {k: oy.get(k) for k, _ in FIELD_MAP}
            for ok, nk in FIELD_MAP:
                oy[ok] = ny.get(nk)
            oy["ebit_method"] = ny["operating_income_route"]
            oy["roic_status"] = ny["roic_status"]
            oy["roic_confidence"] = ny["confidence"]
            oy["corrected_by"] = "analyse_roic.py (독립 재산출)"

            moved = [k for k, _ in FIELD_MAP
                     if _differs(before[k], oy.get(k))]
            if moved:
                changes.append({
                    "ticker": oc["ticker"], "fiscal_year": ny["fiscal_year"],
                    "period_end": pe, "fields": moved,
                    "roic_before": before["roic"], "roic_after": oy["roic"],
                    "ebit_before": before["ebit"], "ebit_after": oy["ebit"],
                    "capital_before": before["invested_capital_avg"],
                    "capital_after": oy["invested_capital_avg"],
                })

        # Summary fields that are pure restatements of the corrected series
        s, ns = oc["summary"], nc["summary"]
        s["roic_10y_median"] = ns["roic_median"]
        s["roic_years_observed"] = ns["years_usable"]
        s["roic_above_10pct_years"] = ns["years_above_wacc"]
        s["roic_stdev"] = ns["roic_stdev"]
        s["roic_wacc_spread_vs_10pct"] = ns["spread_median"]
        s["roic_verdict_vs_10pct"] = ns["verdict"]
        s["roic_corrected"] = True
        s["roic_correction_note"] = (
            "FY2016~FY2025 ROIC는 analyse_roic.py의 독립 재산출값으로 교체. "
            "구 조사의 차입금·현금 누락을 정정한 결과.")

        # The valuation chain is left alone, but where its net-cash input is
        # materially wrong the gap is recorded.
        latest = max((y for y in nc["years"] if y["fiscal_year"] <= 2025),
                     key=lambda y: y["fiscal_year"], default=None)
        if latest and None not in (latest["cash_and_short_term_investments"],
                                   latest["interest_bearing_debt"]):
            corrected = (latest["cash_and_short_term_investments"]
                         - latest["interest_bearing_debt"])
            stated = s.get("net_cash")
            if isinstance(stated, (int, float)) and \
                    abs(stated - corrected) > max(0.03 * abs(corrected), 5e9):
                note = {
                    "ticker": oc["ticker"], "fiscal_year": latest["fiscal_year"],
                    "net_cash_in_study": stated,
                    "net_cash_recomputed": corrected,
                    "error": stated - corrected,
                    "market_cap": oc.get("market_cap_usd"),
                    "error_vs_market_cap": (
                        (stated - corrected) / oc["market_cap_usd"]
                        if oc.get("market_cap_usd") else None),
                }
                net_debt_notes.append(note)
                s["net_cash_recomputed"] = corrected
                s["net_cash_error_flagged"] = stated - corrected
                s["valuation_note"] = (
                    (s.get("valuation_note") or "") +
                    " [정정 필요] 순현금 입력값이 재산출값과 "
                    f"{(stated - corrected)/1e9:,.1f}십억 달러 차이. "
                    "DCF 결과는 이 보고서에서 재계산하지 않았음.")

    old["method_notes"]["ebit"] = (
        "보고된 영업이익 소계를 우선 사용하고, 소계를 보고하지 않는 기업에 "
        "한해 손익계산서 항목을 쌓아 세전이익으로 역검증한 값(경로 V) 또는 "
        "세전이익 기반 추정값을 사용. 연도별로 ebit_method에 기록. "
        "(구 설명은 우선순위를 반대로 적고 있었음 — 실제 구현은 보고 소계 "
        "340건, 세전이익+이자 124건)")
    old["method_notes"]["roic_correction"] = (
        "FY2016~FY2025 ROIC는 work/analyse_roic.py로 독립 재산출한 값. "
        "원본은 analysis.json.pre-roic-correction 에 보존.")
    old["method_notes"]["returns_denominator"] = (
        "기초·기말 투하자본의 평균. 단, 어느 한쪽이 0 이하인 해는 평균이 "
        "0 근처로 내려가 비율이 폭발하므로 기말값을 단독 사용.")
    old["method_notes"]["wacc_for_roic_comparison"] = (
        "ROIC 비교용 문턱은 전 종목 10% 고정 (사용자 지정).")

    with open(OLD, "w") as fh:
        json.dump(old, fh, indent=1, ensure_ascii=False)

    log = {
        "backup": os.path.basename(BACKUP),
        "company_years_changed": len(changes),
        "changes": changes,
        "untouched": untouched,
        "net_cash_errors_flagged": net_debt_notes,
    }
    with open(LOG, "w") as fh:
        json.dump(log, fh, indent=1, ensure_ascii=False)

    big = sorted((c for c in changes
                  if None not in (c["roic_before"], c["roic_after"])),
                 key=lambda c: -abs(c["roic_after"] - c["roic_before"]))

    print(f"정정한 기업-연도 {len(changes)}건, 원본 백업 "
          f"{os.path.basename(BACKUP)}\n")
    print(f"ROIC 변화가 큰 상위 15건")
    print(f"  {'기업':<7}{'연도':<8}{'구 ROIC':>11}{'정정 ROIC':>11}"
          f"{'변화':>10}  바뀐 항목")
    for c in big[:15]:
        print(f"  {c['ticker']:<7}FY{c['fiscal_year']:<6}"
              f"{c['roic_before']:>11.1%}{c['roic_after']:>11.1%}"
              f"{c['roic_after'] - c['roic_before']:>+10.1%}  "
              f"{', '.join(c['fields'])[:44]}")

    if net_debt_notes:
        print(f"\n가치평가 쪽으로 번진 입력 오류 {len(net_debt_notes)}건 "
              f"(이 보고서에서 DCF는 재계산하지 않음)")
        print(f"  {'기업':<7}{'구 순현금':>14}{'재산출':>14}{'오차':>14}"
              f"{'시가총액 대비':>12}")
        for n in sorted(net_debt_notes, key=lambda n: -abs(n["error"])):
            print(f"  {n['ticker']:<7}{n['net_cash_in_study']/1e9:>13,.1f}"
                  f"{n['net_cash_recomputed']/1e9:>14,.1f}"
                  f"{n['error']/1e9:>14,.1f}"
                  f"{(n['error_vs_market_cap'] or 0):>12.1%}")
        print("  (단위 10억 달러)")

    print(f"\nwrote {OLD}\nwrote {LOG}")
    return 0


def _differs(a, b):
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) > max(abs(b) * 1e-6, 1e-9)
    return a != b


if __name__ == "__main__":
    sys.exit(main())
