"""
Alphabet valued as two businesses rather than one.

The memo asks for the existing business and the AI business to be projected
separately, and the segment disclosures make that possible: Google Services and
Google Cloud each publish revenue and operating income, five years of them.
They are not the same business. Services grew revenue 9.6% a year over that
window at a 40.7% operating margin. Cloud grew 32.2% a year and went from a
11.9% operating LOSS to a 23.7% margin. Averaging them into one growth rate,
which is what the single-company model did, hides the entire question.

What the segments still do not give is capital. Alphabet does not disclose
segment assets, so the reinvestment each segment needs is an assumption, not a
measurement - stated per scenario and varied, never presented as a fact.

A second memo challenges the growth rates the earlier model used. It is right:
against a five-year revenue CAGR of 17.2% and a NOPAT CAGR of 25.5%, calling
15% "optimistic" was a miscalibration. Both are addressed here - see
GROWTH_AUDIT.

Writes work/alphabet_sotp.json.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "alphabet_sotp.json")

FILINGS = {2025: "0001652044-26-000018", 2023: "0001652044-24-000022"}

# Segment revenue and operating income, read from the inline XBRL of the FY2023
# and FY2025 10-Ks (companyfacts drops dimensioned facts, so these come from the
# filing documents). In millions of dollars.
SEGMENTS = {
    "services": {
        "label": "구글 서비스 (기존 사업)",
        "what": "검색·유튜브 광고, 구독·플랫폼·기기",
        "revenue": {2021: 237_529, 2022: 253_528, 2023: 272_543,
                    2024: 304_930, 2025: 342_721},
        "operating_income": {2021: 88_132, 2022: 82_699, 2023: 95_858,
                             2024: 121_263, 2025: 139_404},
    },
    "cloud": {
        "label": "구글 클라우드 (AI 사업)",
        "what": "AI 인프라·플랫폼(TPU/GPU, Vertex AI, Gemini Enterprise), Workspace",
        "revenue": {2021: 19_206, 2022: 26_280, 2023: 33_088,
                    2024: 43_229, 2025: 58_705},
        "operating_income": {2021: -2_282, 2022: -1_922, 2023: 1_716,
                             2024: 6_112, 2025: 13_910},
    },
    "other": {
        "label": "기타 베팅 + 전사 AI 연구",
        "what": "웨이모·아이소모픽 등, 그리고 중앙 집중화된 프론티어 모델 연구개발",
        "revenue": {2021: 753, 2022: 1_068, 2023: 1_527,
                    2024: 1_648, 2025: 1_537},
        "operating_income": {2021: -4_051 - 3_085, 2022: -4_636 - 1_299,
                             2023: -4_095 - 9_186, 2024: -4_444 - 10_541,
                             2025: -7_515 - 16_760},
    },
}

CONSOLIDATED = {
    "revenue_2025": 402_836,
    "operating_income_2025": 129_039,
    "tax_rate_2025": 0.168,
    "net_cash": 77_758,
    "shares_outstanding": 12_097.0,        # millions
    "price": 355.84,
    "market_cap": 4_304_596,
    "risk_free": 0.0465,
    "cost_of_equity": 0.1006,
    "wacc": 0.0996,
    "backlog_2025": 242_800,
}

# The company-wide history the growth challenge turns on.
GROWTH_AUDIT = {
    "revenue": {2014: 66_001, 2015: 74_989, 2020: 182_527, 2022: 282_836, 2025: 402_836},
    "nopat": {2014: 13_018, 2015: 16_114, 2020: 34_524, 2022: 62_926, 2025: 107_382},
    "operating_income": {2014: 16_496, 2015: 19_360, 2020: 41_224,
                         2022: 74_842, 2025: 129_039},
    "previous_scenario_growth": {"보수": 0.08, "중립": 0.11, "낙관": 0.15},
    "previous_scenario_incremental_roic": {"보수": 0.12, "중립": 0.20, "낙관": 0.30},
}

# Per-scenario paths. Growth and margin are given per segment; the incremental
# return on new capital is the assumption that converts growth into a cash cost.
SCENARIOS = [
    {
        "name": "보수",
        "discount": 0.12, "terminal_growth": 0.020,
        "story": ("생성형 AI가 검색 질의를 잠식하기 시작하고 광고 단가가 눌립니다. "
                  "클라우드는 계속 크지만 경쟁으로 마진 개선이 멈춥니다."),
        "services": {"g0": 0.05, "g10": 0.02, "margin_end": 0.36, "inc_roic": 0.30},
        "cloud": {"g0": 0.18, "g10": 0.05, "margin_end": 0.24, "inc_roic": 0.12},
        "other_growth": 0.05,
    },
    {
        "name": "중립",
        "discount": 0.10, "terminal_growth": 0.025,
        "story": ("검색이 최근 5년 실적(연 9.6%)에 가까운 속도로 계속 크고, "
                  "클라우드가 계약잔고대로 인도되며 마진이 소프트웨어 사업 수준으로 "
                  "올라갑니다."),
        "services": {"g0": 0.09, "g10": 0.035, "margin_end": 0.41, "inc_roic": 0.40},
        "cloud": {"g0": 0.28, "g10": 0.08, "margin_end": 0.32, "inc_roic": 0.18},
        "other_growth": 0.03,
    },
    {
        "name": "낙관",
        "discount": 0.08, "terminal_growth": 0.030,
        "story": ("AI가 검색을 잠식하는 대신 확장시키고, 클라우드가 최근 5년 실적"
                  "(연 32.2%)에 가까운 속도를 유지하며 마진이 구글 서비스 수준에 "
                  "근접합니다."),
        "services": {"g0": 0.11, "g10": 0.045, "margin_end": 0.44, "inc_roic": 0.50},
        "cloud": {"g0": 0.34, "g10": 0.10, "margin_end": 0.40, "inc_roic": 0.25},
        "other_growth": 0.00,
    },
]

YEARS = 10


def div(a, b):
    return None if (a is None or not b) else a / b


def cagr(a, b, n):
    return (b / a) ** (1 / n) - 1


def segment_history():
    out = {}
    for key, s in SEGMENTS.items():
        rev, op = s["revenue"], s["operating_income"]
        yrs = sorted(rev)
        rows = [{"fiscal_year": y, "revenue": rev[y], "operating_income": op[y],
                 "operating_margin": div(op[y], rev[y])} for y in yrs]
        out[key] = {
            "label": s["label"], "what": s["what"], "rows": rows,
            "revenue_cagr": cagr(rev[yrs[0]], rev[yrs[-1]], len(yrs) - 1),
            "operating_income_cagr": (cagr(op[yrs[0]], op[yrs[-1]], len(yrs) - 1)
                                      if op[yrs[0]] > 0 and op[yrs[-1]] > 0 else None),
            "margin_start": div(op[yrs[0]], rev[yrs[0]]),
            "margin_end": div(op[yrs[-1]], rev[yrs[-1]]),
            "share_of_revenue_2025": div(rev[yrs[-1]], CONSOLIDATED["revenue_2025"]),
            "share_of_operating_income_2025": div(op[yrs[-1]],
                                                  CONSOLIDATED["operating_income_2025"]),
        }
    return out


def project_segment(rev0, margin0, spec, tax, discount, terminal_growth,
                    positive_only=True):
    """One segment's cash flows.

    Revenue growth fades linearly; the operating margin moves linearly from
    today's to the scenario's endpoint. Reinvestment is derived from growth and
    the segment's assumed incremental return, the same identity the
    single-company model uses - so a segment cannot grow without paying for it.
    """
    rows, pv, rev, margin = [], 0.0, rev0, margin0
    inc = spec["inc_roic"]
    for t in range(1, YEARS + 1):
        g = spec["g0"] + (spec["g10"] - spec["g0"]) * (t - 1) / (YEARS - 1)
        margin = margin0 + (spec["margin_end"] - margin0) * t / YEARS
        rev *= (1 + g)
        op = rev * margin
        nopat = op * (1 - tax)
        rr = max(0.0, g / inc) if inc else 0.0
        fcf = nopat * (1 - rr)
        if positive_only:
            fcf = fcf
        d = fcf / (1 + discount) ** t
        pv += d
        rows.append({"year": t, "growth": g, "revenue": rev,
                     "operating_margin": margin, "operating_income": op,
                     "nopat": nopat, "reinvestment_rate": rr,
                     "free_cash_flow": fcf, "present_value": d})
    tg = terminal_growth
    trr = tg / inc if inc else 0.0
    term_fcf = rows[-1]["nopat"] * (1 + tg) * (1 - trr)
    terminal = term_fcf / (discount - tg)
    terminal_pv = terminal / (1 + discount) ** YEARS
    return {
        "projection": rows,
        "pv_of_forecast": pv,
        "pv_of_terminal": terminal_pv,
        "value": pv + terminal_pv,
        "terminal_share": div(terminal_pv, pv + terminal_pv),
        "final_year_revenue": rows[-1]["revenue"],
        "final_year_operating_income": rows[-1]["operating_income"],
        "first_year_reinvestment_rate": rows[0]["reinvestment_rate"],
    }


def project_cost_centre(op0, growth, tax, discount, terminal_growth):
    """Other Bets plus central AI research: a cost, projected as a cost.

    The tax shield is applied because these losses reduce the group's tax bill.
    """
    rows, pv, op = [], 0.0, op0
    for t in range(1, YEARS + 1):
        op *= (1 + growth)
        after_tax = op * (1 - tax)
        d = after_tax / (1 + discount) ** t
        pv += d
        rows.append({"year": t, "operating_income": op,
                     "after_tax": after_tax, "present_value": d})
    tg = terminal_growth
    terminal = rows[-1]["after_tax"] * (1 + tg) / (discount - tg)
    terminal_pv = terminal / (1 + discount) ** YEARS
    return {"projection": rows, "pv_of_forecast": pv,
            "pv_of_terminal": terminal_pv, "value": pv + terminal_pv}


def run_scenario(s, tax):
    svc = SEGMENTS["services"]
    cld = SEGMENTS["cloud"]
    oth = SEGMENTS["other"]
    services = project_segment(svc["revenue"][2025],
                               div(svc["operating_income"][2025], svc["revenue"][2025]),
                               s["services"], tax, s["discount"], s["terminal_growth"])
    cloud = project_segment(cld["revenue"][2025],
                            div(cld["operating_income"][2025], cld["revenue"][2025]),
                            s["cloud"], tax, s["discount"], s["terminal_growth"])
    other = project_cost_centre(oth["operating_income"][2025], s["other_growth"],
                                tax, s["discount"], s["terminal_growth"])
    ev = services["value"] + cloud["value"] + other["value"]
    equity = ev + CONSOLIDATED["net_cash"]
    # The blended company growth each scenario implies, which is what makes it
    # comparable with the single-company model and with the historical CAGR.
    rev0 = svc["revenue"][2025] + cld["revenue"][2025] + oth["revenue"][2025]
    rev10 = (services["final_year_revenue"] + cloud["final_year_revenue"]
             + oth["revenue"][2025])
    return {
        "scenario": s["name"],
        "story": s["story"],
        "assumptions": {
            "discount": s["discount"], "terminal_growth": s["terminal_growth"],
            "services": s["services"], "cloud": s["cloud"],
            "other_growth": s["other_growth"],
        },
        "services": services,
        "cloud": cloud,
        "other": other,
        "enterprise_value": ev,
        "net_cash": CONSOLIDATED["net_cash"],
        "equity_value": equity,
        "value_per_share": equity / CONSOLIDATED["shares_outstanding"],
        "upside_vs_market": div(equity - CONSOLIDATED["market_cap"],
                                CONSOLIDATED["market_cap"]),
        "margin_of_safety": div(equity - CONSOLIDATED["market_cap"], equity),
        "implied_company_revenue_cagr": cagr(rev0, rev10, YEARS),
        "cloud_share_of_value": div(cloud["value"], ev),
        "services_share_of_value": div(services["value"], ev),
        "year10_revenue": rev10,
        "year10_cloud_share_of_revenue": div(cloud["final_year_revenue"], rev10),
    }


def implied_discount_rate(tax):
    """The annual return today's price delivers on the neutral segment paths."""
    s = dict(SCENARIOS[1])

    def value(disc):
        t = dict(s); t["discount"] = disc
        return run_scenario(t, tax)["equity_value"]

    lo, hi = s["terminal_growth"] + 0.001, 0.40
    if value(lo) < CONSOLIDATED["market_cap"]:
        return None
    for _ in range(90):
        mid = (lo + hi) / 2
        if value(mid) > CONSOLIDATED["market_cap"]:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def cloud_growth_needed(tax):
    """What Cloud must do for the whole company to compound at 15%.

    Services is 85% of revenue, so the blended rate is dominated by it. This
    turns "is 15% plausible?" into a question about two observable businesses
    rather than one abstract number.
    """
    svc_rev = SEGMENTS["services"]["revenue"][2025]
    cld_rev = SEGMENTS["cloud"]["revenue"][2025]
    oth_rev = SEGMENTS["other"]["revenue"][2025]
    total = svc_rev + cld_rev + oth_rev
    out = []
    for target in (0.10, 0.12, 0.15, 0.17, 0.20):
        rows = []
        for svc_g in (0.05, 0.08, 0.09, 0.11):
            need = (total * (1 + target) - svc_rev * (1 + svc_g) - oth_rev) / cld_rev - 1
            rows.append({"services_growth": svc_g, "cloud_growth_needed": need})
        out.append({"company_growth_target": target, "combinations": rows})
    return {
        "revenue_mix_2025": {"services": div(svc_rev, total), "cloud": div(cld_rev, total),
                             "other": div(oth_rev, total)},
        "targets": out,
        "cloud_actual_cagr": cagr(SEGMENTS["cloud"]["revenue"][2021],
                                  SEGMENTS["cloud"]["revenue"][2025], 4),
        "services_actual_cagr": cagr(SEGMENTS["services"]["revenue"][2021],
                                     SEGMENTS["services"]["revenue"][2025], 4),
    }


def growth_audit():
    r, n, o = (GROWTH_AUDIT["revenue"], GROWTH_AUDIT["nopat"],
               GROWTH_AUDIT["operating_income"])
    windows = []
    for label, start, span in (("3년 (FY2022→FY2025)", 2022, 3),
                               ("5년 (FY2020→FY2025)", 2020, 5),
                               ("10년 (FY2015→FY2025)", 2015, 10),
                               ("11년 (FY2014→FY2025)", 2014, 11)):
        windows.append({
            "window": label,
            "revenue_cagr": cagr(r[start], r[2025], span),
            "operating_income_cagr": cagr(o[start], o[2025], span),
            "nopat_cagr": cagr(n[start], n[2025], span),
        })
    return {
        "windows": windows,
        "previous_assumptions": GROWTH_AUDIT["previous_scenario_growth"],
        "verdict": ("이전 모형의 낙관 시나리오 성장률 15%는 5년 실적 매출 CAGR "
                    "17.2%, NOPAT CAGR 25.5%보다 낮습니다. '낙관'이라는 이름이 "
                    "실적보다 보수적인 가정에 붙어 있었습니다."),
        "counterpoints": [
            ("5년 창은 FY2021 한 해의 반등(매출 +41.2%)을 안고 있습니다. 그 해를 "
             "제외한 최근 3년 매출 CAGR은 12.5%입니다."),
            ("NOPAT이 매출보다 빨리 자란 것은 영업이익률이 FY2020 22.6%에서 FY2025 "
             "32.0%로 9.4%포인트 확대된 결과입니다. 마진 확대는 무한히 이어질 수 "
             "없으므로 NOPAT CAGR을 그대로 미래에 옮기면 이중으로 낙관하게 됩니다."),
            ("성장은 공짜가 아닙니다. g = 재투자율 × 신규 ROIC이므로, 성장률을 "
             "올리면 재투자율이 따라 올라갑니다. 다만 그 대가가 가치를 깎을지 "
             "키울지는 신규 ROIC와 할인율의 차이에 달려 있습니다 — 구글 서비스처럼 "
             "신규 ROIC가 할인율을 크게 웃도는 사업에서는 성장이 가치를 키우고"
             "(아래 민감도 참조), 클라우드의 보수 시나리오처럼 신규 ROIC가 12%로 "
             "할인율에 근접하면 성장해도 남는 것이 거의 없습니다."),
        ],
    }


def cost_centre_sensitivity(tax):
    """How much the perpetual-loss treatment of Other Bets and central R&D costs.

    Charging FY2025's combined $24.3bn loss forever is defensible - the research
    is what produces the models both segments sell - but it is an assumption
    worth sizing, because it removes a seventh of the neutral equity value.
    """
    out = []
    for label, growth, note in (
        ("영구히 현 수준 유지 (성장 3%)", 0.03, "기준 가정"),
        ("성장 0% — 명목 기준 고정", 0.00, "연구비가 더 늘지 않는 경우"),
        ("연 5%씩 축소", -0.05, "웨이모 등이 손익분기에 접근하는 경우"),
        ("연 10%씩 확대", 0.10, "프론티어 모델 경쟁이 심화되는 경우"),
    ):
        s = json.loads(json.dumps(SCENARIOS[1]))
        s["other_growth"] = growth
        r = run_scenario(s, tax)
        out.append({"treatment": label, "growth": growth, "note": note,
                    "cost_centre_value": r["other"]["value"],
                    "equity_value": r["equity_value"],
                    "value_per_share": r["value_per_share"]})
    return out


def growth_value_tradeoff(tax):
    """Value as a function of growth alone, holding the return on capital fixed.

    The counter-intuitive result the memo needs: past a point, more growth
    lowers value, because the capital it consumes rises faster than the profit
    it produces. This is Buffett's 1992 point stated as arithmetic.
    """
    base = SCENARIOS[1]
    out = []
    for g in (0.05, 0.08, 0.09, 0.11, 0.13, 0.15, 0.17, 0.20):
        s = json.loads(json.dumps(base))
        s["services"]["g0"] = g
        s["services"]["g10"] = min(g, 0.035 + max(0.0, (g - 0.09) * 0.3))
        r = run_scenario(s, tax)
        out.append({"services_growth": g,
                    "first_year_reinvestment_rate":
                        r["services"]["first_year_reinvestment_rate"],
                    "value_per_share": r["value_per_share"],
                    "implied_company_revenue_cagr": r["implied_company_revenue_cagr"]})
    return out


def main():
    tax = CONSOLIDATED["tax_rate_2025"]
    hist = segment_history()
    scenarios = [run_scenario(s, tax) for s in SCENARIOS]
    out = {
        "generated_note": "FY2025 10-K 및 FY2023 10-K 부문 주석 기준",
        "filings_read": FILINGS,
        "consolidated": CONSOLIDATED,
        "segment_history": hist,
        "scenarios": scenarios,
        "implied_discount_rate_at_current_price": implied_discount_rate(tax),
        "growth_audit": growth_audit(),
        "cloud_growth_needed_for_company_growth": cloud_growth_needed(tax),
        "growth_value_tradeoff": growth_value_tradeoff(tax),
        "cost_centre_sensitivity": cost_centre_sensitivity(tax),
        "caveat": ("부문별 자본이 공시되지 않으므로 각 부문의 신규 ROIC는 측정치가 "
                   "아니라 시나리오별 가정입니다. 부문 매출과 영업이익만이 알파벳이 "
                   "보고한 값입니다."),
    }
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(f"alphabet_sotp -> {OUT}")

    for k, h in hist.items():
        print(f"  {h['label']}: 매출 CAGR {h['revenue_cagr']:.1%}, "
              f"마진 {h['margin_start']:.1%} → {h['margin_end']:.1%}, "
              f"매출비중 {h['share_of_revenue_2025']:.1%}")
    print()
    for s in scenarios:
        print(f"  {s['scenario']}: 서비스 ${s['services']['value']/1e3:,.0f}B + "
              f"클라우드 ${s['cloud']['value']/1e3:,.0f}B + 기타 "
              f"${s['other']['value']/1e3:,.0f}B + 순현금 "
              f"${s['net_cash']/1e3:,.0f}B = ${s['equity_value']/1e3:,.0f}B, "
              f"주당 ${s['value_per_share']:,.0f} (현재 "
              f"${CONSOLIDATED['price']:,.2f}), 전사 성장률 "
              f"{s['implied_company_revenue_cagr']:.1%}")
    ir = out["implied_discount_rate_at_current_price"]
    print(f"\n  함축수익률(중립 부문 경로): "
          f"{('%.2f%%' % (ir * 100)) if ir else '주가가 상한 초과'}")


if __name__ == "__main__":
    main()
