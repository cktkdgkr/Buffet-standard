"""
Two objections to the Alphabet valuation, tested rather than argued.

Objection 1. The optimistic scenario fades growth from 20% to 4.5% over ten
years, but Alphabet has compounded revenue at more than 11% for a decade and
more than 16% over five years. Is the fade too severe?

Objection 2. Capital spending will eventually taper while the revenue it bought
keeps arriving, so the return on capital should rise structurally - build once,
collect for years. Does the model capture that, and is it right about it?

The second one turns on a fact rather than an opinion, and the fact is in the
accounting policy note: Alphabet depreciates data centre and office buildings
over seven to 40 years, but "servers and network equipment generally over a
period of six years", and the property note says roughly 60% of technical
infrastructure is servers and network equipment. So 60% of the AI build is on a
six-year replacement clock. "Capex stops and revenue continues" is the right
model for the buildings and the wrong one for the machines inside them.

The first one is partly a convention. No company can outgrow the economy
forever, so a terminal rate has to sit near nominal GDP. But the endpoint of the
fade and the terminal rate are assumptions, they are powerful, and they should be
swept rather than asserted - which is what this file does.

It also repairs an omission. The earlier "matured" calculation added the revenue
the backlog will bring but not the depreciation that arrives when $122.8bn of
not-yet-in-service assets switch on. Both belong in that calculation.

Writes work/alphabet_fade.json.
"""

import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "brk_alphabet.json")
AN = os.path.join(HERE, "brk_alphabet_analysis.json")
CAP = os.path.join(HERE, "alphabet_capital.json")
OUT = os.path.join(HERE, "alphabet_fade.json")

PRICE = 347.33
TAX = 0.168

# Revenue, as filed. FY2016-FY2024 from the XBRL company facts; FY2025 from the
# 10-K already collected.
REVENUE = {2016: 90_272.0, 2017: 110_855.0, 2018: 136_819.0, 2019: 161_857.0,
           2020: 182_527.0, 2021: 257_637.0, 2022: 282_836.0, 2023: 307_394.0,
           2024: 350_018.0, 2025: 402_836.0}
OPERATING_INCOME = {2020: 41_224.0, 2021: 78_714.0, 2022: 74_842.0,
                    2023: 84_293.0, 2024: 112_390.0, 2025: 129_039.0}

# Accounting policy note, FY2025 10-K.
USEFUL_LIVES = {
    "servers_and_network": 6.0,
    "data_centre_and_office_buildings": (7.0, 40.0),
    "corporate_and_other": (2.0, 25.0),
    "servers_share_of_technical_infrastructure": 0.60,
    "source": "FY2025 Form 10-K, Summary of Significant Accounting Policies "
              "and Property and Equipment note",
}
BUILDING_LIFE = 20.0      # midpoint of the 7-40 year range actually used
OFFICE_LIFE = 25.0
CORPORATE_LIFE = 10.0


def div(a, b):
    return None if (a is None or not b) else a / b


def cagr(a, b, n):
    return (b / a) ** (1.0 / n) - 1.0


def growth_record():
    ys = sorted(REVENUE)
    last = ys[-1]
    out = {"revenue_by_year": REVENUE, "windows": []}
    for n in (9, 5, 3, 1):
        if last - n in REVENUE:
            out["windows"].append({
                "years": n, "from": last - n, "to": last,
                "revenue_cagr": cagr(REVENUE[last - n], REVENUE[last], n),
            })
    for w in out["windows"]:
        if w["from"] in OPERATING_INCOME:
            w["operating_income_cagr"] = cagr(OPERATING_INCOME[w["from"]],
                                              OPERATING_INCOME[2025],
                                              w["years"])
    return out


def scenario_path(g0, g10, n=10):
    return [g0 + (g10 - g0) * (t - 1) / (n - 1) for t in range(1, n + 1)]


def dcf(base_nopat, net_cash, shares, market_cap, g0, g10, inc_roic, k, tg,
        n=10):
    pv, nopat, rows = 0.0, base_nopat, []
    for t, g in enumerate(scenario_path(g0, g10, n), 1):
        rr = g / inc_roic
        nopat *= (1 + g)
        fcf = nopat * (1 - rr)
        d = fcf / (1 + k) ** t
        pv += d
        rows.append({"year": t, "growth": g, "reinvestment_rate": rr,
                     "nopat": nopat, "free_cash_flow": fcf,
                     "present_value": d})
    term = (nopat * (1 + tg) * (1 - tg / inc_roic) / (k - tg) / (1 + k) ** n)
    eq = pv + term + net_cash
    cum = nopat / base_nopat
    return {
        "assumptions": {"growth": g0, "fade_to": g10,
                        "incremental_roic": inc_roic, "discount": k,
                        "terminal_growth": tg},
        "average_growth": (cum ** (1 / n)) - 1,
        "nopat_multiple_after_10y": cum,
        "pv_of_forecast": pv, "pv_of_terminal": term,
        "terminal_share": div(term, pv + term),
        "equity_value": eq, "value_per_share": eq / shares,
        "vs_market": div(eq - market_cap, market_cap),
        "projection": rows,
    }


def fade_grid(base_nopat, net_cash, shares, market_cap, inc_roic=0.50,
              k=0.09):
    """Value as the fade endpoint and the perpetual rate are varied."""
    out = []
    for g10 in (0.045, 0.06, 0.08, 0.10):
        row = {"fade_to": g10, "cells": []}
        for tg in (0.025, 0.030, 0.035, 0.040):
            if tg >= k:
                continue
            r = dcf(base_nopat, net_cash, shares, market_cap, 0.20, g10,
                    inc_roic, k, tg)
            row["cells"].append({
                "terminal_growth": tg,
                "value_per_share": r["value_per_share"],
                "vs_market": r["vs_market"],
                "terminal_share": r["terminal_share"],
                "average_growth": r["average_growth"],
            })
        out.append(row)
    return {"incremental_roic": inc_roic, "discount": k, "rows": out}


def steady_state_capital(raw):
    """
    What it costs to stand still.

    With 60% of technical infrastructure on a six-year life, a fleet of a given
    size needs a sixth of that 60% replaced every year forever. That is the
    floor under capital spending, and it is the number the "capex stops"
    argument has to clear.
    """
    ppe = raw["ppe_detail"]["2026-06-30"]
    tech = ppe["technical_infrastructure"]
    office = ppe["office_space"]
    corp = ppe["corporate_and_other"]
    nis = ppe["not_yet_in_service"]
    s = USEFUL_LIVES["servers_share_of_technical_infrastructure"]

    def annual(gross_tech, gross_office=0.0, gross_corp=0.0):
        return (gross_tech * s / USEFUL_LIVES["servers_and_network"]
                + gross_tech * (1 - s) / BUILDING_LIFE
                + gross_office / OFFICE_LIFE
                + gross_corp / CORPORATE_LIFE)

    in_service = annual(tech, office, corp)
    # Assets not yet in service are overwhelmingly technical infrastructure.
    from_nis = annual(nis)
    actual = raw["alphabet"]["2026q2"]["depreciation"][1] * 2
    capex_run_rate = -raw["alphabet"]["2026q2"]["capex"][1] * 2

    return {
        "gross_technical_infrastructure": tech,
        "gross_office": office,
        "gross_corporate": corp,
        "not_yet_in_service": nis,
        "implied_annual_depreciation_in_service": in_service,
        "implied_annual_depreciation_from_not_yet_in_service": from_nis,
        "implied_annual_depreciation_all": in_service + from_nis,
        "reported_depreciation_run_rate": actual,
        "depreciation_still_to_come": in_service + from_nis - actual,
        "capex_run_rate": capex_run_rate,
        "steady_state_capex_as_share_of_current": div(in_service + from_nis,
                                                      capex_run_rate),
        "note": ("정상상태 설비투자는 감가상각과 같아집니다. 서버·네트워크 장비가 "
                 "기술인프라의 60%이고 내용연수가 6년이므로, 성장이 0이어도 "
                 "매년 그만큼을 갈아끼워야 합니다. '설비투자가 멈춘다'가 아니라 "
                 "'설비투자가 이 수준으로 내려앉는다'가 맞습니다."),
    }


def matured_corrected(raw, cap, steady):
    """
    The earlier matured calculation, with the depreciation that arrives when the
    not-yet-in-service assets switch on.
    """
    m = cap["matured"]
    extra_dep = steady["implied_annual_depreciation_from_not_yet_in_service"]
    oi_now = m["company_operating_income_now"]
    oi_before = m["company_operating_income_matured"]
    oi_after = oi_before - extra_dep
    capital = m["capital"]
    return {
        "operating_income_run_rate": oi_now,
        "backlog_uplift": m["uplift_operating_income"],
        "depreciation_from_assets_switching_on": extra_dep,
        "operating_income_matured_before": oi_before,
        "operating_income_matured_after": oi_after,
        "nopat_matured_after": oi_after * (1 - TAX),
        "roic_matured_before": m["roic_matured"],
        "roic_matured_after": div(oi_after * (1 - TAX), capital),
        "revenue_needed_to_offset_depreciation": div(
            extra_dep, m["incremental_operating_margin"]),
        "backlog_revenue_uplift": m["uplift_revenue"],
        "note": ("직전 계산은 수주잔고가 가져올 매출은 더했지만, 미가동 자산 "
                 "1,228억 달러가 가동에 들어갈 때 함께 오는 감가상각은 빼지 "
                 "않았습니다. 둘 다 넣어야 맞습니다."),
    }


def main():
    with open(RAW) as fh:
        raw = json.load(fh)
    with open(AN) as fh:
        an = json.load(fh)
    with open(CAP) as fh:
        cap = json.load(fh)

    v = an["valuation"]
    base, net_cash = v["base_nopat"], v["net_cash"]
    shares, mcap = v["shares_used"], v["market_cap"]

    growth = growth_record()
    steady = steady_state_capital(raw)
    mat = matured_corrected(raw, cap, steady)

    named = {
        "기존 낙관 (증분ROIC 30%)": dict(g0=0.20, g10=0.045, inc_roic=0.30,
                                        k=0.09, tg=0.030),
        "미가동자산 반영 (증분ROIC 50%)": dict(g0=0.20, g10=0.045,
                                              inc_roic=0.50, k=0.09, tg=0.030),
        "완만한 감속 (10년차 8%)": dict(g0=0.20, g10=0.08, inc_roic=0.50,
                                       k=0.09, tg=0.030),
        "완만한 감속 + 영구성장 4%": dict(g0=0.20, g10=0.08, inc_roic=0.50,
                                         k=0.09, tg=0.040),
        "위와 같되 할인율 10%": dict(g0=0.20, g10=0.08, inc_roic=0.50,
                                    k=0.10, tg=0.040),
        "위와 같되 할인율 11%": dict(g0=0.20, g10=0.08, inc_roic=0.50,
                                    k=0.11, tg=0.040),
    }
    scenarios = {n: dcf(base, net_cash, shares, mcap, **kw)
                 for n, kw in named.items()}

    result = {
        "generated": date.today().isoformat(),
        "price": PRICE,
        "growth_record": growth,
        "useful_lives": USEFUL_LIVES,
        "steady_state": steady,
        "matured_corrected": mat,
        "scenarios": scenarios,
        "fade_grid": fade_grid(base, net_cash, shares, mcap),
    }
    with open(OUT, "w") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)

    print("■ 알파벳의 실제 성장 기록")
    for w in growth["windows"]:
        oi = w.get("operating_income_cagr")
        print(f"  {w['years']:>2}년 ({w['from']}→{w['to']})  매출 CAGR "
              f"{w['revenue_cagr']:>6.1%}" +
              (f"   영업이익 CAGR {oi:>6.1%}" if oi else ""))

    print("\n■ 정상상태 설비투자 — '설비투자가 멈춘다'가 맞는가")
    print(f"  기술인프라(가동 중, 취득원가) "
          f"${steady['gross_technical_infrastructure']/1000:,.0f}bn, "
          f"그중 60%가 내용연수 6년짜리 서버·네트워크")
    print(f"  가동 중 자산의 연간 감가상각 "
          f"${steady['implied_annual_depreciation_in_service']/1000:,.0f}bn")
    print(f"  미가동 자산 "
          f"${steady['not_yet_in_service']/1000:,.0f}bn이 가동되면 추가 "
          f"${steady['implied_annual_depreciation_from_not_yet_in_service']/1000:,.0f}bn")
    print(f"  → 정상상태 유지 설비투자 "
          f"${steady['implied_annual_depreciation_all']/1000:,.0f}bn "
          f"(현재 설비투자 ${steady['capex_run_rate']/1000:,.0f}bn의 "
          f"{steady['steady_state_capex_as_share_of_current']:.0%})")
    print(f"  현재 감가상각 계상액 "
          f"${steady['reported_depreciation_run_rate']/1000:,.0f}bn → 아직 "
          f"${steady['depreciation_still_to_come']/1000:,.0f}bn이 더 올 예정")

    print("\n■ 성숙 상태 재계산 (감가상각 빠진 것 보정)")
    print(f"  현재 영업이익 연율 "
          f"${mat['operating_income_run_rate']/1000:,.0f}bn")
    print(f"  + 수주잔고 전환 효과 ${mat['backlog_uplift']/1000:,.0f}bn")
    print(f"  − 미가동 자산 가동 시 감가상각 "
          f"${mat['depreciation_from_assets_switching_on']/1000:,.0f}bn")
    print(f"  = ${mat['operating_income_matured_after']/1000:,.0f}bn  "
          f"(보정 전 ${mat['operating_income_matured_before']/1000:,.0f}bn)")
    print(f"  성숙 ROIC {mat['roic_matured_before']:.1%} → "
          f"{mat['roic_matured_after']:.1%}")

    print("\n■ 시나리오별 가치")
    print(f"{'시나리오':<30}{'10년차':>8}{'평균성장':>9}{'영구':>6}"
          f"{'할인율':>7}{'주당가치':>10}{'시장대비':>10}{'터미널':>8}")
    for n, s in scenarios.items():
        a = s["assumptions"]
        print(f"{n:<30}{a['fade_to']:>8.1%}{s['average_growth']:>9.1%}"
              f"{a['terminal_growth']:>6.1%}{a['discount']:>7.0%}"
              f"${s['value_per_share']:>9,.0f}{s['vs_market']:>+10.1%}"
              f"{s['terminal_share']:>8.0%}")

    print(f"\n■ 감속 정도 × 영구성장률 (증분ROIC 50%, 할인율 9%) — 주당가치")
    fg = result["fade_grid"]
    tgs = [c["terminal_growth"] for c in fg["rows"][0]["cells"]]
    print(f"{'10년차 성장률':>14}" + "".join(f"{t:>12.1%}" for t in tgs))
    for row in fg["rows"]:
        print(f"{row['fade_to']:>14.1%}"
              + "".join(f"${c['value_per_share']:>11,.0f}"
                        for c in row["cells"]))
    print(f"{'현재가':>14}" + f"${PRICE:>11,.0f}")

    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
