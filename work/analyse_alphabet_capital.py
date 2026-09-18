"""
Alphabet's return on capital, separating the capital that is working from the
capital that is not, and testing what the contracted backlog implies.

This exists because the previous round got one thing wrong and one thing
incomplete.

Wrong: it said Alphabet does not disclose assets that are built but not yet
earning, so they could not be stripped out of the denominator. Alphabet does
disclose them, on the face of the property note, in the 10-Q as well as the
10-K. At 30 June 2026 the balance is $122.8bn - 38.2% of net property and
equipment, and more than half of the year's increase. Charging the business for
plant that is not yet switched on understates the return on the plant that is.

Incomplete: it reported the backlog as evidence of visibility but never used it.
The backlog cannot be added to today's operating income - that is a stock added
to a flow, and the costs of serving it have not been incurred either - but it
can be used for the calculation that question actually asks: freeze the balance
sheet where it is, let what has been built come into service and what has been
contracted turn into revenue, and see what the return settles at.

Three views of the same business result:

  as_reported   income from the plant that is running, over all the capital,
                working or not. The most conservative, and mismatched in time.
  working       income from the plant that is running, over the capital that is
                running. Matched in time; the honest read of today.
  matured       income after the backlog converts, over all the capital. Where
                the business is heading if it stopped investing today.

Writes work/alphabet_capital.json.
"""

import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "brk_alphabet.json")
AN = os.path.join(HERE, "brk_alphabet_analysis.json")
OUT = os.path.join(HERE, "alphabet_capital.json")

TAX = 0.168          # FY2025 effective rate; see note in analyse_brk_alphabet
PRICE = 347.33


def div(a, b):
    return None if (a is None or not b) else a / b


def operating_capital(a, idx, ppe_not_in_service=None):
    """
    Bottom-up operating capital. Cash, marketable and non-marketable securities
    are excluded - at June 2026 Alphabet held $131.5bn of non-marketable
    securities whose mark-ups drove reported net income to more than twice
    operating income, and none of it is capital employed in search or cloud.

    Pass ppe_not_in_service to remove plant that is built but not switched on.
    """
    g = lambda k: a[k][idx]
    total = (g("ppe_net") + g("operating_lease_assets") + g("goodwill")
             + g("accounts_receivable") - g("total_current_liabilities"))
    return total - (ppe_not_in_service or 0)


def three_views(raw):
    a26, a25 = raw["alphabet"]["2026q2"], raw["alphabet"]["2025q2"]
    ppe = raw["ppe_detail"]
    nis25 = ppe["2025-06-30"]["not_yet_in_service"]
    nis26 = ppe["2026-06-30"]["not_yet_in_service"]

    # Half-year operating income annualised, on both sides of the comparison.
    oi25 = a26["income_from_operations"][2] * 2
    oi26 = a26["income_from_operations"][3] * 2
    nopat25, nopat26 = oi25 * (1 - TAX), oi26 * (1 - TAX)

    ic25_all = operating_capital(a25, 1)
    ic26_all = operating_capital(a26, 1)
    ic25_work = operating_capital(a25, 1, nis25)
    ic26_work = operating_capital(a26, 1, nis26)

    return {
        "nopat_2025": nopat25, "nopat_2026": nopat26,
        "not_yet_in_service_2025": nis25, "not_yet_in_service_2026": nis26,
        "not_yet_in_service_increase": nis26 - nis25,
        "as_reported": {
            "capital_2025": ic25_all, "capital_2026": ic26_all,
            "roic_2025": div(nopat25, ic25_all),
            "roic_2026": div(nopat26, ic26_all),
            "delta_capital": ic26_all - ic25_all,
            "incremental_roic": div(nopat26 - nopat25, ic26_all - ic25_all),
        },
        "working": {
            "capital_2025": ic25_work, "capital_2026": ic26_work,
            "roic_2025": div(nopat25, ic25_work),
            "roic_2026": div(nopat26, ic26_work),
            "delta_capital": ic26_work - ic25_work,
            "incremental_roic": div(nopat26 - nopat25, ic26_work - ic25_work),
        },
        "share_of_capital_increase_not_working": div(
            nis26 - nis25, ic26_all - ic25_all),
    }


def matured(raw, views):
    """
    Freeze the balance sheet and let the contracted backlog arrive.

    The company says just over 50% of the backlog is recognised as revenue over
    the next 24 months. Applying that to the cloud backlog gives an annual cloud
    revenue level that the existing contracts alone support, and the observed
    incremental operating margin turns that into operating income. Everything
    else - services, other bets, the corporate cost centre - is held flat, which
    is conservative for services and generous for other bets.
    """
    a26 = raw["alphabet"]["2026q2"]
    bl = raw["alphabet"]["backlog_2026q2"]
    cloud = a26["segments"]["Google Cloud"]

    cloud_q2_rev = cloud["revenue"][1] * 4          # Q2 annualised
    cloud_q2_oi = cloud["operating_income"][1] * 4
    # Incremental operating margin measured on the half-year year-over-year
    # change, which is the cleanest read of what a new revenue dollar earns.
    inc_margin = div(
        cloud["operating_income"][3] - raw["alphabet"]["2025q2"]
        ["segments"]["Google Cloud"]["operating_income"][3],
        cloud["revenue"][3] - raw["alphabet"]["2025q2"]
        ["segments"]["Google Cloud"]["revenue"][3])

    backlog_annual = bl["cloud_bn"] * 1000 * 0.50 / 2.0   # half over two years
    uplift_rev = max(0.0, backlog_annual - cloud_q2_rev)
    uplift_oi = uplift_rev * inc_margin

    company_oi_now = a26["income_from_operations"][1] * 4
    company_oi_matured = company_oi_now + uplift_oi
    nopat_matured = company_oi_matured * (1 - TAX)
    capital_all = views["as_reported"]["capital_2026"]

    return {
        "cloud_revenue_run_rate": cloud_q2_rev,
        "cloud_operating_income_run_rate": cloud_q2_oi,
        "cloud_margin_run_rate": div(cloud_q2_oi, cloud_q2_rev),
        "incremental_operating_margin": inc_margin,
        "backlog_cloud": bl["cloud_bn"] * 1000,
        "backlog_recognised_share_24m": 0.50,
        "backlog_implied_annual_cloud_revenue": backlog_annual,
        "uplift_revenue": uplift_rev,
        "uplift_operating_income": uplift_oi,
        "cloud_revenue_matured": cloud_q2_rev + uplift_rev,
        "cloud_operating_income_matured": cloud_q2_oi + uplift_oi,
        "cloud_margin_matured": div(cloud_q2_oi + uplift_oi,
                                    cloud_q2_rev + uplift_rev),
        "company_operating_income_now": company_oi_now,
        "company_operating_income_matured": company_oi_matured,
        "nopat_matured": nopat_matured,
        "capital": capital_all,
        "roic_matured": div(nopat_matured, capital_all),
        "cross_check": ("2분기 클라우드 매출이 전년 대비 81.8% 늘고 있으므로, "
                        "수주잔고만으로 계산한 이 매출 수준은 성장 추세보다 "
                        "오히려 보수적입니다. 즉 이 계산은 상한이 아니라 하한에 "
                        "가깝습니다."),
        "why_not_add_backlog_to_income": (
            "수주잔고를 오늘의 영업이익에 그냥 더하면 두 가지가 틀립니다. "
            "첫째, 잔고는 미래 매출의 '잔액'이고 영업이익은 한 해의 '흐름'이라 "
            "단위가 다릅니다. 둘째, 그 매출을 내려면 앞으로 원가도 들어가는데 "
            "그 원가에는 지금 분모에 들어 있는 바로 그 설비의 감가상각이 "
            "포함됩니다. 그래서 잔고는 분자에 더하는 것이 아니라, 이미 지은 "
            "자본이 언제 얼마를 벌게 되는지를 가늠하는 데 씁니다."),
    }


def discount_rate_sensitivity(base_nopat, net_cash, shares, market_cap):
    """
    What happens to the valuation as the discount rate falls.

    This is the arithmetic behind the warning that lowering your hurdle because
    you cannot find an alternative is not a free move: as the rate approaches
    the growth rate the value runs away, and the share of it sitting beyond the
    forecast horizon rises until the answer is almost entirely an assumption
    about a decade from now.
    """
    g0, g10, inc_roic, tg = 0.20, 0.045, 0.30, 0.030
    rows = []
    for k in (0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12):
        if k <= tg:
            continue
        pv, nopat = 0.0, base_nopat
        for t in range(1, 11):
            g = g0 + (g10 - g0) * (t - 1) / 9
            nopat *= (1 + g)
            pv += nopat * (1 - g / inc_roic) / (1 + k) ** t
        term = (nopat * (1 + tg) * (1 - tg / inc_roic) / (k - tg)
                / (1 + k) ** 10)
        eq = pv + term + net_cash
        rows.append({
            "discount_rate": k,
            "equity_value": eq,
            "value_per_share": eq / shares,
            "vs_market": div(eq - market_cap, market_cap),
            "terminal_share": div(term, pv + term),
        })
    return {"assumptions": {"growth": g0, "fade_to": g10,
                            "incremental_roic": inc_roic,
                            "terminal_growth": tg},
            "rows": rows}


def alternatives_available():
    """
    Whether an investor really has no alternative is checkable: the 52-company
    study already ranked every name by margin of safety on the same engine.
    """
    path = os.path.join(HERE, "analysis.json")
    if not os.path.exists(path):
        return {"error": "analysis.json not found"}
    with open(path) as fh:
        a = json.load(fh)
    out = []
    for c in a.get("companies", []):
        s = c.get("summary") or {}
        dcf = s.get("dcf") or {}
        base = dcf.get("base") or {}
        mos = base.get("margin_of_safety")
        if not isinstance(mos, (int, float)):
            continue
        out.append({"ticker": c.get("ticker"), "name": c.get("company_name"),
                    "margin_of_safety": mos,
                    "verdict": base.get("verdict"),
                    "optimistic_margin_of_safety":
                        (dcf.get("optimistic") or {}).get("margin_of_safety")})
    out.sort(key=lambda r: -(r["margin_of_safety"] or -9))
    return {
        "counted": len(out),
        "with_positive_margin": sum(1 for r in out
                                    if (r["margin_of_safety"] or 0) > 0),
        "with_positive_optimistic": sum(
            1 for r in out
            if isinstance(r["optimistic_margin_of_safety"], (int, float))
            and r["optimistic_margin_of_safety"] > 0),
        "top": out[:12],
        "basis": ("52개 기업 분석의 기준(중립) 시나리오 안전마진. "
                  "주주이익 기준이고 성장률 10%·할인율 10%·영구성장 2.5%로 "
                  "전 종목에 같은 틀을 적용한 값입니다."),
    }


def main():
    with open(RAW) as fh:
        raw = json.load(fh)
    with open(AN) as fh:
        an = json.load(fh)

    views = three_views(raw)
    mat = matured(raw, views)
    val = an["valuation"]
    sens = discount_rate_sensitivity(val["base_nopat"], val["net_cash"],
                                     val["shares_used"], val["market_cap"])

    result = {
        "generated": date.today().isoformat(),
        "correction": ("직전 보고서는 '알파벳이 미가동 자산을 별도 공시하지 않아 "
                       "분리할 수 없다'고 적었습니다. 이는 사실과 다릅니다. "
                       "유형자산 주석에 'assets not yet in service'가 별도 "
                       "줄로 공시되어 있고, 10-K뿐 아니라 10-Q에도 있습니다. "
                       "이 파일이 그 정정입니다."),
        "ppe_detail": raw["ppe_detail"],
        "three_views": views,
        "matured": mat,
        "discount_rate_sensitivity": sens,
        "alternatives": alternatives_available(),
    }
    with open(OUT, "w") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)

    # --------------------------------------------------------------- console
    print("■ 유형자산: 가동 중인 것과 아직 아닌 것 (백만 달러)")
    ppe = raw["ppe_detail"]
    print(f"{'':<22}" + "".join(f"{k:>14}" for k in sorted(ppe)))
    for lbl, key in (("가동 중 (취득원가)", "in_service"),
                     ("감가상각누계", "accumulated_depreciation"),
                     ("미가동 자산", "not_yet_in_service"),
                     ("순 유형자산", "net")):
        print(f"{lbl:<22}" + "".join(f"{ppe[k][key]:>14,.0f}"
                                     for k in sorted(ppe)))
    print(f"{'미가동 비중':<22}"
          + "".join(f"{ppe[k]['not_yet_in_service']/ppe[k]['net']:>14.1%}"
                    for k in sorted(ppe)))

    print("\n■ 같은 사업, 세 가지 ROIC")
    ar, wk = views["as_reported"], views["working"]
    print(f"{'':<26}{'2025-06':>12}{'2026-06':>12}{'증분 ROIC':>12}")
    print(f"{'보고 기준 (전체 자본)':<26}{ar['roic_2025']:>12.1%}"
          f"{ar['roic_2026']:>12.1%}{ar['incremental_roic']:>12.1%}")
    print(f"{'가동자본 기준':<26}{wk['roic_2025']:>12.1%}"
          f"{wk['roic_2026']:>12.1%}{wk['incremental_roic']:>12.1%}")
    print(f"  미가동 자산 {views['not_yet_in_service_2025']:,.0f} → "
          f"{views['not_yet_in_service_2026']:,.0f} "
          f"(증가 {views['not_yet_in_service_increase']:,.0f}, "
          f"영업자본 증가분의 "
          f"{views['share_of_capital_increase_not_working']:.0%})")

    print("\n■ 수주잔고가 매출로 바뀌면 (자본은 오늘 수준에서 동결)")
    print(f"  클라우드 현재 연율 매출 {mat['cloud_revenue_run_rate']:,.0f} "
          f"→ 잔고 기준 {mat['cloud_revenue_matured']:,.0f} "
          f"(+{mat['uplift_revenue']:,.0f})")
    print(f"  증분 영업이익률 {mat['incremental_operating_margin']:.1%} 적용 → "
          f"영업이익 +{mat['uplift_operating_income']:,.0f}")
    print(f"  클라우드 영업이익률 {mat['cloud_margin_run_rate']:.1%} → "
          f"{mat['cloud_margin_matured']:.1%}")
    print(f"  전사 영업이익 {mat['company_operating_income_now']:,.0f} → "
          f"{mat['company_operating_income_matured']:,.0f}")
    print(f"  성숙 ROIC (전체 자본 기준) {mat['roic_matured']:.1%}")

    print("\n■ 할인율을 낮추면 어떻게 되는가 (낙관 가정 고정)")
    print(f"{'할인율':>8}{'자기자본가치':>16}{'주당':>10}{'시장대비':>10}"
          f"{'터미널 비중':>12}")
    for r in sens["rows"]:
        print(f"{r['discount_rate']:>8.0%}{r['equity_value']/1000:>14,.0f}bn"
              f"{r['value_per_share']:>10,.0f}{r['vs_market']:>+10.1%}"
              f"{r['terminal_share']:>12.0%}")

    alt = result["alternatives"]
    if "error" not in alt:
        print(f"\n■ '대안이 없다'는 검증 가능한가 — 52개 기업 중 안전마진 "
              f"양수 {alt['with_positive_margin']}개 / {alt['counted']}개")
        for r in alt["top"][:6]:
            print(f"    {r['name'][:34]:<36}{r['margin_of_safety']:>8.1%}")

    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
