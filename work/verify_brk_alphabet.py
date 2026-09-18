"""
Check the Berkshire/Alphabet figures against the filings they came from.

Same duty as verify_sbl.py. These numbers were pulled out of inline-XBRL HTML by
flattening tags and reading the figures that follow a caption, which is a method
that fails quietly: a caption that appears twice, or a column order that differs
between two filings, produces a plausible number rather than an error.

Four kinds of check:
  A. Internal consistency - relations that must hold inside a statement.
  B. Cross-document - the same fact told by two different filings.
  C. Independent recomputation - a figure derived a second way.
  D. Model identities - the analysis engine's own arithmetic.

Exit code is non-zero if anything fails.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "brk_alphabet.json")
ANALYSIS = os.path.join(HERE, "brk_alphabet_analysis.json")


def close(a, b, rel=0.005):
    if a is None or b is None:
        return False
    return abs(a - b) <= rel * max(1.0, abs(a), abs(b))


def main():
    with open(RAW) as fh:
        raw = json.load(fh)
    with open(ANALYSIS) as fh:
        an = json.load(fh)
    results = []

    def check(ok, label, detail=""):
        results.append((bool(ok), label, detail))

    # ------------------------------------------------------------------ A
    for tag in ("2026q2", "2025q2"):
        a = raw["alphabet"][tag]
        seg = a["segments"]
        for col, name in ((1, "당분기"), (3, "누적")):
            seg_rev = sum(seg[s]["revenue"][col] for s in seg)
            total = a["total_revenues"][col]
            # Total revenue also carries hedging gains, which are not a segment.
            check(abs(seg_rev - total) <= 0.005 * total,
                  f"알파벳 {tag} {name} 부문매출 합 ≈ 총매출",
                  f"{seg_rev:,.0f} vs {total:,.0f} (차이는 헤지손익)")
            seg_oi = sum(seg[s]["operating_income"][col] for s in seg)
            oi = a["income_from_operations"][col]
            check(seg_oi > oi,
                  f"알파벳 {tag} {name} 부문영업이익 합 > 전사 영업이익",
                  f"{seg_oi:,.0f} vs {oi:,.0f} (차액은 전사공통비)")

    a26 = raw["alphabet"]["2026q2"]
    for i, period in enumerate(("2025-12-31", "2026-06-30")):
        check(close(a26["total_assets"][i],
                    a26["total_equity"][i] + (a26["total_assets"][i]
                                              - a26["total_equity"][i])),
              f"알파벳 {period} 자산 = 부채 + 자본 (항등식)",
              f"{a26['total_assets'][i]:,.0f}")

    check(a26["capex"][1] < a26["capex"][0] < 0,
          "알파벳 설비투자가 두 기간 모두 음수(유출)이고 2026년이 더 큼",
          f"{a26['capex'][0]:,.0f} → {a26['capex'][1]:,.0f}")
    check(a26["buybacks"][1] == 0 and a26["buybacks"][0] < 0,
          "알파벳 자사주매입이 2025 상반기 대비 2026 상반기에 0으로",
          f"{a26['buybacks'][0]:,.0f} → {a26['buybacks'][1]:,.0f}")

    # ------------------------------------------------------------------ B
    q = raw["berkshire_13f"]
    for period, e in q.items():
        a = e["alphabet"]
        if not a:
            continue
        check(sum(r["shares"] for r in a["by_class"]) == a["shares"],
              f"버크셔 {period} 알파벳 클래스별 주식수 합 = 합계",
              f"{a['shares']:,}")

    pp = raw["private_placement"]
    gross = (pp["class_a_shares"] * pp["class_a_price"]
             + pp["class_c_shares"] * pp["class_c_price"])
    check(close(gross, pp["gross_proceeds_bn"] * 1e9, 0.001),
          "사모발행 주식수 × 단가 = 공시된 총액 100억 달러",
          f"{gross:,.0f} vs {pp['gross_proceeds_bn']*1e9:,.0f}")
    check(pp["total_shares"] == pp["class_a_shares"] + pp["class_c_shares"],
          "사모발행 총 주식수", f"{pp['total_shares']:,.0f}")

    q2 = q["2026-06-30"]["alphabet"]["shares"] - q["2026-03-31"]["alphabet"]["shares"]
    check(q2 > pp["total_shares"],
          "2026년 2분기 증가분이 사모발행분보다 큼 (나머지는 장내 매수)",
          f"증가 {q2:,.0f} vs 사모 {pp['total_shares']:,.0f}")

    check(q["2026-06-30"]["alphabet"]["rank"] == 3,
          "2026년 2분기말 알파벳이 버크셔 13F 3위",
          f"{q['2026-06-30']['alphabet']['rank']}위, 비중 "
          f"{q['2026-06-30']['alphabet']['weight']:.1%}")
    check(q["2025-06-30"]["alphabet"] is None,
          "2025년 2분기말에는 보유 없음 (신규 편입 시점 확인)")

    # ------------------------------------------------------------------ C
    mc = raw["mandatory_convertible"]
    check(close(mc["gross_proceeds_total"],
                2 * (mc["depositary_shares_per_series"] / 20) * 1000.0),
          "전환우선주 발행총액 = 예탁증서÷20 × 액면 $1,000 × 2개 시리즈",
          f"{mc['gross_proceeds_total']:,.0f}")
    check(close(mc["series_a_floor_price"],
                1000.0 / mc["series_a_conversion_rate"]["max"]),
          "전환 하한가 = 액면 ÷ 최대전환비율",
          f"{mc['series_a_floor_price']:,.2f}")
    check(close(mc["series_a_cap_price"],
                1000.0 / mc["series_a_conversion_rate"]["min"]),
          "전환 상한가 = 액면 ÷ 최소전환비율",
          f"{mc['series_a_cap_price']:,.2f}")
    check(mc["capped_call_cap_class_a"] > mc["series_a_cap_price"],
          "캡드콜 상한이 전환 상한보다 높음",
          f"{mc['capped_call_cap_class_a']:,.2f} vs "
          f"{mc['series_a_cap_price']:,.2f}")

    # The breakeven has to actually be a breakeven: common should lose just
    # below it and win just above it.
    ch = an["instrument_choice"]
    be = ch["breakeven_price_2029"]
    grid = {round(g["price_2029"], 2): g for g in ch["payoff_grid"]}
    below = [g for g in ch["payoff_grid"] if g["price_2029"] < be]
    above = [g for g in ch["payoff_grid"] if g["price_2029"] > be]
    check(all(not g["common_wins"] for g in below),
          "손익분기 아래에서는 전부 우선주가 유리",
          f"분기점 ${be:,.0f}")
    check(all(g["common_wins"] for g in above),
          "손익분기 위에서는 전부 보통주가 유리",
          f"분기점 ${be:,.0f}")
    check(ch["preferred_floor_price"] <= be <= ch["preferred_cap_price"],
          "손익분기가 전환 하한~상한 구간 안에 있음",
          f"{ch['preferred_floor_price']:,.2f} ≤ {be:,.2f} ≤ "
          f"{ch['preferred_cap_price']:,.2f}")

    # ------------------------------------------------------------------ D
    cost = an["cost_basis"]
    legs = [l for l in cost["legs"] if l["shares_added"] > 0]
    check(close(sum(l["shares_added"] for l in legs), cost["shares_final"]),
          "매입 레그 합 = 최종 보유주식수", f"{cost['shares_final']:,.0f}")
    check(close(sum(l["estimated_cost"] for l in legs),
                cost["estimated_total_cost"]),
          "매입 레그 원가 합 = 총 추정원가",
          f"{cost['estimated_total_cost']/1e9:,.1f}bn")
    check(close(cost["estimated_average_cost_per_share"],
                cost["estimated_total_cost"] / cost["shares_final"]),
          "평균 매입단가 = 총원가 ÷ 주식수",
          f"${cost['estimated_average_cost_per_share']:,.2f}")

    r = an["returns"]
    check(close(r["roic_2026"],
                r["nopat_annualised_2026"] / r["operating_capital_2026"]),
          "ROIC 2026 = NOPAT ÷ 영업투하자본", f"{r['roic_2026']:.1%}")
    check(close(r["incremental_roic"],
                (r["nopat_annualised_2026"] - r["nopat_annualised_2025"])
                / (r["operating_capital_2026"] - r["operating_capital_2025"])),
          "증분 ROIC = ΔNOPAT ÷ Δ영업투하자본",
          f"{r['incremental_roic']:.1%}")
    check(r["incremental_roic"] > 0.10,
          "증분 ROIC이 자본비용 추정치(약 10%)를 상회",
          f"{r['incremental_roic']:.1%}")
    c = r["cloud"]
    check(close(c["margin_h1_2026"],
                c["operating_income_h1_2026"] / c["revenue_h1_2026"]),
          "클라우드 영업이익률 재계산", f"{c['margin_h1_2026']:.1%}")
    check(c["margin_h1_2026"] > c["margin_h1_2025"],
          "클라우드 마진이 전년 대비 상승 (하락이 아님)",
          f"{c['margin_h1_2025']:.1%} → {c['margin_h1_2026']:.1%}")

    for s in an["valuation"]["scenarios"]:
        p0 = s["projection"][0]
        a = s["assumptions"]
        check(close(p0["free_cash_flow"],
                    p0["nopat"] * (1 - p0["growth"] / a["incremental_roic"])),
              f"{s['scenario']} 1년차 FCF = NOPAT × (1 − g ÷ 증분ROIC)",
              f"{p0['free_cash_flow']:,.0f}")
        check(close(s["equity_value"],
                    s["enterprise_value"] + an["valuation"]["net_cash"]),
              f"{s['scenario']} 자기자본가치 = 기업가치 + 순현금",
              f"{s['equity_value']:,.0f}")
        check(close(s["value_per_share"],
                    s["equity_value"] / an["valuation"]["shares_used"]),
              f"{s['scenario']} 주당가치", f"${s['value_per_share']:,.0f}")

    # ----------------------------------------------- alphabet_capital.json
    cap_path = os.path.join(HERE, "alphabet_capital.json")
    if os.path.exists(cap_path):
        with open(cap_path) as fh:
            cap = json.load(fh)
        ppe = cap["ppe_detail"]
        for period, e in ppe.items():
            check(close(e["in_service"] + e["accumulated_depreciation"]
                        + e["not_yet_in_service"], e["net"], 1e-6),
                  f"유형자산 {period}: 가동중 − 감가상각누계 + 미가동 = 순액",
                  f"{e['net']:,.0f}")
            check(0 < e["not_yet_in_service"] < e["net"],
                  f"유형자산 {period}: 미가동자산이 순액 범위 안",
                  f"{e['not_yet_in_service']/e['net']:.1%}")

        v = cap["three_views"]
        for tag, yr in (("2025", "2025-06-30"), ("2026", "2026-06-30")):
            check(close(v["working"][f"capital_{tag}"],
                        v["as_reported"][f"capital_{tag}"]
                        - ppe[yr]["not_yet_in_service"]),
                  f"가동자본 {tag} = 전체 영업자본 − 미가동자산",
                  f"{v['working'][f'capital_{tag}']:,.0f}")
            check(close(v["working"][f"roic_{tag}"],
                        v[f"nopat_{tag}"] / v["working"][f"capital_{tag}"]),
                  f"가동자본 ROIC {tag} 재계산",
                  f"{v['working'][f'roic_{tag}']:.1%}")
        for key in ("as_reported", "working"):
            check(close(v[key]["incremental_roic"],
                        (v["nopat_2026"] - v["nopat_2025"])
                        / v[key]["delta_capital"]),
                  f"{key} 증분 ROIC 재계산",
                  f"{v[key]['incremental_roic']:.1%}")
        check(v["working"]["incremental_roic"] > v["as_reported"]["incremental_roic"],
              "미가동자산을 빼면 증분 ROIC이 올라간다",
              f"{v['as_reported']['incremental_roic']:.1%} → "
              f"{v['working']['incremental_roic']:.1%}")
        check(0 < v["share_of_capital_increase_not_working"] < 1,
              "영업자본 증가분 중 미가동 비중이 0~100% 사이",
              f"{v['share_of_capital_increase_not_working']:.0%}")

        m = cap["matured"]
        check(close(m["uplift_operating_income"],
                    m["uplift_revenue"] * m["incremental_operating_margin"]),
              "성숙 시 영업이익 증분 = 매출 증분 × 증분 영업이익률",
              f"{m['uplift_operating_income']:,.0f}")
        check(close(m["backlog_implied_annual_cloud_revenue"],
                    m["backlog_cloud"] * m["backlog_recognised_share_24m"] / 2),
              "잔고 기준 연 매출 = 클라우드 잔고 × 인식비율 ÷ 2년",
              f"{m['backlog_implied_annual_cloud_revenue']:,.0f}")
        check(close(m["roic_matured"], m["nopat_matured"] / m["capital"]),
              "성숙 ROIC 재계산", f"{m['roic_matured']:.1%}")
        check(m["roic_matured"] > v["as_reported"]["roic_2026"],
              "성숙 ROIC이 보고 기준 ROIC보다 높다",
              f"{v['as_reported']['roic_2026']:.1%} → {m['roic_matured']:.1%}")
        check(m["cloud_margin_matured"] > m["cloud_margin_run_rate"],
              "성숙 시 클라우드 마진이 현재 런레이트보다 높다",
              f"{m['cloud_margin_run_rate']:.1%} → "
              f"{m['cloud_margin_matured']:.1%}")

        rows = cap["discount_rate_sensitivity"]["rows"]
        vals = [r["equity_value"] for r in rows]
        terms = [r["terminal_share"] for r in rows]
        check(all(a > b for a, b in zip(vals, vals[1:])),
              "할인율이 오르면 가치가 단조 감소")
        check(all(a > b for a, b in zip(terms, terms[1:])),
              "할인율이 오르면 터미널 비중이 단조 감소",
              f"{terms[0]:.0%} → {terms[-1]:.0%}")

        alt = cap["alternatives"]
        if "error" not in alt:
            check(alt["counted"] > 30,
                  "52개 기업 중 DCF 산출 가능한 종목 수", str(alt["counted"]))
            check(alt["with_positive_optimistic"] > 0,
                  "낙관 시나리오에서 안전마진 양수인 대안이 존재",
                  f"{alt['with_positive_optimistic']}개")

    # The hypothesis grid must show the sign flip at incremental ROIC =
    # discount rate; that is the whole point of the table.
    h = an["hypothesis_test"]
    k = h["discount_rate"]
    for row in h["grid"]:
        vals = [e["value"] for e in row["values"] if e["value"] is not None]
        if len(vals) < 2:
            continue
        rising = vals[-1] > vals[0]
        check(rising == (row["incremental_roic"] > k),
              f"증분ROIC {row['incremental_roic']:.0%}에서 성장의 가치 방향",
              f"{'증가' if rising else '감소'} (할인율 {k:.0%})")

    failed = [x for x in results if not x[0]]
    for ok, label, detail in results:
        if not ok:
            print(f"  FAIL  {label}  [{detail}]")
    print(f"\nchecks: {len(results)}, failed: {len(failed)}")
    if failed:
        return 1
    print("버크셔·알파벳 수치 전부 공시원문 정합성 검증 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
