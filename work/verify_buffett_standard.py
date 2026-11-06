"""
buffett_standard.json 검증.

- **기초율 전사 검증.** 1차 자료(Base Rate Book Exhibit 4)에서 옮긴 분포가
  맞는지, 분포 자체로 되짚습니다. 구간 비중의 합이 1 이어야 하고, **구간
  분포에서 계산한 중위값이 문서가 따로 인쇄한 중위값과 같아야** 합니다.
  이 두 검사는 제가 숫자를 잘못 옮기면 반드시 실패합니다 — 분포와 요약값은
  문서의 서로 다른 행에서 왔으므로 독립입니다.
- **항등식.** 격자의 모든 칸을 DCF 로 다시 계산해 대조하고, 안전마진 가격·
  상승여력·성장 경로·재투자율·터미널 공식을 전부 재산출합니다.
- **앵커.** 거시 수치(국채·기대인플레이션)와 버핏 인용의 존재, 그리고
  fair_value.json 의 투영과 일치하는지(해명 표).
- **트립와이어.** 할인율이 오르면 가치는 내려가야 하고, 성장률이 오르면
  가치는 올라가야 하고, 발산은 터미널 ≥ 할인율일 때만 일어나야 합니다.

    python3 verify_buffett_standard.py
    python3 verify_buffett_standard.py --mutate
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DATA = os.path.join(HERE, "fv", "buffett_standard.json")
FV = os.path.join(HERE, "fv", "fair_value.json")
MM, BN = 1e6, 1e9
YEARS = 10
CAP = 0.25

# 1차 자료에서 손으로 읽은 값. Base Rate Book 2016-09-26 Exhibit 4,
# "Sales: >$50,000 Mn" 칸의 10-Yr 열. 실질 기준.
ANCHOR_NET_INCOME = {
    "median": 0.033, "mean": 0.038, "stdev": 0.112,
    "band_0_10": 0.417, "band_10_20": 0.141, "band_20_30": 0.061,
    "band_m10_0": 0.276, "band_over_90": 0.000,
}
ANCHOR_SALES = {
    "median": 0.011, "mean": 0.008, "stdev": 0.058,
    "band_0_5": 0.378, "band_5_10": 0.172, "band_10_15": 0.030,
    "band_15_20": 0.009, "band_20_25": 0.000,
}
ANCHOR_GDP_REAL = 0.032          # "U.S. GDP grew at 3.2 percent per year"
ANCHOR_BEI = 0.0224             # FRED T10YIE, 2026-11-05
ORDER_KEYS = ["base_rate_median", "half_of_own", "own_sustained",
              "ai_sustained"]
DISCOUNT_KEYS = ["bond30", "bond30_plus3", "project10", "project11"]


class Checks:
    def __init__(self):
        self.passed = 0
        self.failures = []

    def eq(self, name, got, want, tol=0.0, rel=None):
        if got is None or want is None:
            self.failures.append(f"{name}: 값 없음 (got={got!r} want={want!r})")
            return
        limit = tol if rel is None else max(tol, abs(want) * rel)
        if abs(got - want) <= limit:
            self.passed += 1
        else:
            self.failures.append(
                f"{name}: {got:,.6g} != {want:,.6g} (허용 {limit:,.6g})")

    def same(self, name, got, want):
        if got == want:
            self.passed += 1
        else:
            self.failures.append(f"{name}: {got!r} != {want!r}")

    def true(self, name, cond, detail=""):
        if cond:
            self.passed += 1
        else:
            self.failures.append(f"{name}: 거짓 {detail}")


def bounds(lab):
    if lab.startswith("<"):
        return (-999.0, float(lab[1:]) / 100.0)
    if lab.startswith(">"):
        return (float(lab[1:]) / 100.0, 999.0)
    lo, hi = lab.split("~")
    return (float(lo) / 100.0, float(hi) / 100.0)


def share_at_or_above(bands, value):
    out = 0.0
    for lab, share in bands:
        lo, hi = bounds(lab)
        if value <= lo:
            out += share
        elif value < hi:
            out += share * (hi - value) / (hi - lo)
    return out


def median_from_bands(bands):
    """구간 분포에서 중위값을 선형보간으로 찾습니다."""
    lo, hi = -1.0, 1.5
    for _ in range(200):
        mid = (lo + hi) / 2
        if share_at_or_above(bands, mid) > 0.5:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def dcf(base_nopat, net_cash, shares, growth, fade_to, inc_roic,
        discount, terminal_growth, years=YEARS):
    if terminal_growth >= discount:
        return None
    proj, pv, nopat = [], 0.0, base_nopat
    for t in range(1, years + 1):
        g = growth + (fade_to - growth) * (t - 1) / (years - 1)
        rr = g / inc_roic
        nopat *= (1 + g)
        fcf = nopat * (1 - rr)
        disc = fcf / (1 + discount) ** t
        pv += disc
        proj.append({"year": t, "growth": g, "nopat": nopat,
                     "reinvestment_rate": rr, "free_cash_flow": fcf,
                     "present_value": disc})
    tg = terminal_growth
    term = (proj[-1]["nopat"] * (1 + tg) * (1 - tg / inc_roic)
            / (discount - tg))
    term_pv = term / (1 + discount) ** years
    ev = pv + term_pv
    eq = ev + net_cash
    return {"projection": proj, "pv_of_forecast": pv,
            "pv_of_terminal": term_pv,
            "terminal_share": term_pv / ev if ev else None,
            "enterprise_value": ev, "equity_value": eq,
            "value_per_share": eq / shares,
            "nopat_cagr_10y": (proj[-1]["nopat"] / base_nopat)
            ** (1 / years) - 1}


def verify(d, c):
    br = d["base_rates"]
    macro = d["macro"]
    infl = macro["breakeven_inflation_10y"]["rate"]

    # ---- 기초율 전사 검증 ------------------------------------------------
    c.true("기초율이 실질 기준임을 명시", br["real_terms"] is True)
    c.true("기초율 생존편향 주의 기재", bool(br.get("survivorship_note")))
    c.true("기초율 출처 기재", "Base Rate Book" in br["source"])
    c.same("기초율 기간", br["period"], "1950-2015")
    c.true("기초율 참조군이 $50십억 초과", "$50,000" in br["reference_class"])
    for key, anchor in (("net_income_10y", ANCHOR_NET_INCOME),
                        ("sales_10y", ANCHOR_SALES)):
        blk = br[key]
        total = sum(s for _, s in blk["bands"])
        c.eq(f"기초율 {key} 구간 비중 합 = 1", total, 1.0, tol=0.002)
        c.eq(f"앵커 {key} 중위", blk["median"], anchor["median"], rel=0)
        c.eq(f"앵커 {key} 평균", blk["mean"], anchor["mean"], rel=0)
        c.eq(f"앵커 {key} 표준편차", blk["stdev"], anchor["stdev"], rel=0)
        # 독립 검사: 구간 분포에서 계산한 중위값이 문서가 따로 인쇄한
        # 중위값과 일치해야 합니다. 전사 오류가 있으면 여기서 깨집니다.
        c.eq(f"교차검증 {key} 구간분포의 중위 = 인쇄된 중위",
             median_from_bands(blk["bands"]), blk["median"], tol=0.006)
        c.eq(f"교차검증 {key} 중위 지점의 누적비중 = 50%",
             share_at_or_above(blk["bands"], blk["median"]), 0.5, tol=0.01)
        c.true(f"기초율 {key} 모든 비중 0 이상",
               all(s >= 0 for _, s in blk["bands"]))
    bands = br["net_income_10y"]["bands"]
    c.eq("앵커 순이익 0~10% 구간", dict(bands)["0~10"],
         ANCHOR_NET_INCOME["band_0_10"], rel=0)
    c.eq("앵커 순이익 10~20% 구간", dict(bands)["10~20"],
         ANCHOR_NET_INCOME["band_10_20"], rel=0)
    c.eq("앵커 순이익 20~30% 구간", dict(bands)["20~30"],
         ANCHOR_NET_INCOME["band_20_30"], rel=0)
    c.eq("앵커 순이익 −10~0% 구간", dict(bands)["-10~0"],
         ANCHOR_NET_INCOME["band_m10_0"], rel=0)
    sb = dict(br["sales_10y"]["bands"])
    for lab, key in (("0~5", "band_0_5"), ("5~10", "band_5_10"),
                     ("10~15", "band_10_15"), ("15~20", "band_15_20"),
                     ("20~25", "band_20_25")):
        c.eq(f"앵커 매출 {lab}% 구간", sb[lab], ANCHOR_SALES[key], rel=0)
    c.eq("앵커 장기 실질 GDP 성장률", br["gdp_real_1950_2015"],
         ANCHOR_GDP_REAL, rel=0)
    # 매출 성장 분포가 순이익 분포보다 꼬리가 얇아야 합니다 — 마진이
    # 움직이지 않는 쪽이 분산이 작습니다. 뒤집히면 두 표를 바꿔 넣은 것입니다.
    c.true("트립와이어 매출 분포가 순이익 분포보다 꼬리가 얇음",
           br["sales_10y"]["stdev"] < br["net_income_10y"]["stdev"],
           f"{br['sales_10y']['stdev']} vs {br['net_income_10y']['stdev']}")
    # 누적 비중은 값이 커지면 단조 감소해야 합니다.
    prev = 1.1
    for v in (-0.2, -0.1, 0.0, 0.05, 0.1, 0.2, 0.3, 0.5):
        got = share_at_or_above(bands, v)
        c.true(f"트립와이어 누적비중 단조감소 {v:+.0%}", got <= prev + 1e-12,
               f"{got:.4f} > {prev:.4f}")
        prev = got

    # ---- 거시 앵커 -------------------------------------------------------
    c.eq("앵커 기대인플레이션", infl, ANCHOR_BEI, rel=0)
    c.same("기대인플레이션 출처", macro["breakeven_inflation_10y"]["series"],
           "FRED T10YIE")
    for key in ("treasury_30y", "treasury_10y"):
        y = macro[key]
        c.eq(f"{key} 비율 = 퍼센트/100", y["rate"], y["percent"] / 100.0,
             rel=1e-12)
        c.true(f"트립와이어 {key} 0~25%", 0 < y["rate"] < 0.25,
               f"{y['rate']}")
        c.true(f"{key} 출처 URL", y["source_url"].startswith("https://"))
    c.true("트립와이어 30년 국채 > 10년 국채 (정상 수익률곡선)",
           macro["treasury_30y"]["rate"] > macro["treasury_10y"]["rate"],
           f"{macro['treasury_30y']['rate']:.4f} vs "
           f"{macro['treasury_10y']['rate']:.4f}")
    c.eq("항등식 장기 명목 GDP = 실질 + 기대인플레",
         macro["nominal_gdp_long_run"]["rate"],
         br["gdp_real_1950_2015"] + infl, rel=1e-12)

    # ---- 할인율·터미널 후보 ----------------------------------------------
    dmap = {x["key"]: x for x in d["discount_options"]}
    c.same("할인율 후보 구성", [x["key"] for x in d["discount_options"]],
           DISCOUNT_KEYS)
    c.eq("항등식 국채30 할인율", dmap["bond30"]["rate"],
         macro["treasury_30y"]["rate"], rel=1e-12)
    c.eq("항등식 국채30+3%p 할인율", dmap["bond30_plus3"]["rate"],
         macro["treasury_30y"]["rate"] + 0.03, rel=1e-12)
    c.eq("프로젝트 기준 10%", dmap["project10"]["rate"], 0.10, rel=0)
    c.eq("프로젝트 보수 11%", dmap["project11"]["rate"], 0.11, rel=0)
    rates = [x["rate"] for x in d["discount_options"]]
    c.true("트립와이어 할인율 오름차순", rates == sorted(rates), str(rates))
    c.true("국채+3%p 근거에 해석임이 명시",
           "해석" in dmap["bond30_plus3"]["basis"])
    tmap = {x["key"]: x for x in d["terminal_options"]}
    c.eq("터미널 인플레이션", tmap["inflation"]["rate"], infl, rel=1e-12)
    c.eq("터미널 명목GDP", tmap["nominal_gdp"]["rate"],
         macro["nominal_gdp_long_run"]["rate"], rel=1e-12)
    c.true("트립와이어 터미널 오름차순",
           [x["rate"] for x in d["terminal_options"]]
           == sorted(x["rate"] for x in d["terminal_options"]))

    # ---- 버핏 인용 -------------------------------------------------------
    c.true("버핏 인용 5건 이상", len(d["buffett"]) >= 5, str(len(d["buffett"])))
    years_cited = {q["year"] for q in d["buffett"]}
    for y in (1992, 1994, 2007):
        c.true(f"버핏 {y}년 인용 있음", y in years_cited)
    for q in d["buffett"]:
        c.true(f"버핏 {q['year']} 인용에 출처 URL",
               q["url"].startswith("https://"))
        c.true(f"버핏 {q['year']} 인용문 비어 있지 않음", len(q["quote"]) > 20)
        c.true(f"버핏 {q['year']} 1차/2차 구분 기재",
               "1차" in q["kind"] or "2차" in q["kind"], q["kind"])
    prim = [q for q in d["buffett"] if "1차" in q["kind"]]
    c.true("1차 출처가 berkshirehathaway.com",
           all("berkshirehathaway.com" in q["url"] for q in prim))
    c.true("증분 수익률 조건 인용 포함",
           any("incremental returns" in q["quote"] for q in d["buffett"]))
    c.true("안전마진 인용 포함",
           any("cents on the dollar" in q["quote"] for q in d["buffett"]))

    # ---- 해명 표: fair_value.json 과 일치 --------------------------------
    fv = json.load(open(FV, encoding="utf-8"))
    applied = [x for x in fv["companies"] if x["model"] == "applied"]
    rows = {(r["ticker"], r["scenario"]): r
            for r in d["clarification"]["rows"]}
    c.same("해명 표 행 수", len(d["clarification"]["rows"]),
           len(applied) * 3)
    for co in applied:
        for v in co["valuations"]:
            r = rows.get((co["ticker"], v["scenario"]))
            c.true(f"해명 {co['ticker']} {v['scenario']} 존재", r is not None)
            if not r:
                continue
            c.eq(f"해명 {co['ticker']} {v['scenario']} 1년차 성장률",
                 r["year1_growth"], v["assumptions"]["growth"], rel=0)
            c.eq(f"해명 {co['ticker']} {v['scenario']} 10년차 성장률",
                 r["year10_growth"], v["assumptions"]["fade_to"], rel=0)
            c.eq(f"재산출 해명 {co['ticker']} {v['scenario']} 10년 CAGR",
                 r["nopat_cagr_10y"],
                 (v["projection"][-1]["nopat"] / co["ttm"]["nopat"])
                 ** (1 / 10) - 1, rel=1e-12)
            # 요점: 10년 CAGR 이 10년차 성장률보다 높아야 합니다. 그래야
            # "3.5%는 10년간 성장률이 아니다"라는 해명이 성립합니다.
            c.true(f"트립와이어 해명 {co['ticker']} {v['scenario']}: "
                   f"10년 CAGR > 10년차 성장률",
                   r["nopat_cagr_10y"] > r["year10_growth"],
                   f"{r['nopat_cagr_10y']:.4f} vs {r['year10_growth']:.4f}")

    # ---- 기업별 격자 -----------------------------------------------------
    by_ticker = {x["ticker"]: x for x in applied}
    c.same("기업 수", len(d["companies"]), len(applied))
    for co in d["companies"]:
        t = co["ticker"]
        src = by_ticker[t]
        c.eq(f"{t} TTM NOPAT = fair_value", co["ttm_nopat"],
             src["ttm"]["nopat"], rel=0)
        c.eq(f"{t} 순현금 = fair_value", co["net_cash"],
             src["balance_sheet"]["net_cash"], rel=0)
        c.eq(f"{t} 주식수 = fair_value", co["shares_outstanding"],
             src["shares_outstanding"]["value"], rel=0)
        c.eq(f"{t} 주가 = fair_value", co["price"], src["price"], rel=0)
        c.eq(f"{t} 10년 CAGR = fair_value", co["own_cagr_nominal"],
             src["record"]["operating_income_cagr"], rel=0)
        c.eq(f"{t} 실질 CAGR = 명목 − 기대인플레", co["own_cagr_real"],
             co["own_cagr_nominal"] - infl, rel=1e-12)
        c.eq(f"{t} 증분ROIC = min(10년 중위, 35%)",
             co["incremental_roic_used"],
             min(src["record"]["summary"]["roic_median"], 0.35), rel=1e-12)
        c.true(f"{t} 참조군에 속함 (매출 > $50십억)",
               co["in_reference_class"] is True
               and co["ttm_revenue"] > 50 * BN,
               f"{co['ttm_revenue'] / BN:,.0f}십억")
        c.eq(f"재산출 {t} 과거 CAGR 백분위",
             co["own_cagr_percentile_at_or_above"],
             share_at_or_above(bands, co["own_cagr_real"]), rel=1e-9)

        # 10년 기록 표
        hist = co["history"]
        c.same(f"{t} 기록 10년", len(hist), 10)
        src_years = {y["fiscal_year"]: y for y in src["record"]["years"]}
        for i, h in enumerate(hist):
            y = src_years[h["fiscal_year"]]
            c.eq(f"{t} FY{h['fiscal_year']} 영업이익",
                 h["operating_income"], y["operating_income"], rel=0)
            c.eq(f"{t} FY{h['fiscal_year']} ROIC", h["roic"], y["roic"],
                 rel=0)
            if i:
                p = hist[i - 1]
                c.eq(f"재산출 {t} FY{h['fiscal_year']} 영업이익 증가율",
                     h["operating_income_growth"],
                     h["operating_income"] / p["operating_income"] - 1,
                     rel=1e-12)
                if h.get("revenue") and p.get("revenue"):
                    c.eq(f"재산출 {t} FY{h['fiscal_year']} 매출 증가율",
                         h["revenue_growth"],
                         h["revenue"] / p["revenue"] - 1, rel=1e-12)
            else:
                c.true(f"{t} 첫 해 증가율 없음",
                       h["operating_income_growth"] is None)
        c.true(f"트립와이어 {t} 기록이 연속된 연도",
               [h["fiscal_year"] for h in hist]
               == list(range(hist[0]["fiscal_year"],
                             hist[0]["fiscal_year"] + 10)),
               str([h["fiscal_year"] for h in hist]))
        # 기록에서 다시 계산한 10년 CAGR 이 저장값과 맞는지. 창이 10개
        # 회계연도이므로 구간은 9년입니다 — CAGR 은 첫 해 이전을 기준으로
        # 하므로 fair_value 가 쓰는 기준연도와 다릅니다. 방향만 봅니다.
        c.true(f"트립와이어 {t} 기록 기간 영업이익 증가",
               hist[-1]["operating_income"] > hist[0]["operating_income"])

        own = co["own_cagr_nominal"]
        c.same(f"{t} 성장률 후보 구성",
               [g["growth_key"] for g in co["grid"]], ORDER_KEYS)
        gmap = {g["growth_key"]: g for g in co["grid"]}
        c.eq(f"{t} 기초율 중위 성장률 = 실질 중위 + 기대인플레",
             gmap["base_rate_median"]["growth"],
             br["net_income_10y"]["median"] + infl, rel=1e-12)
        c.eq(f"{t} 과거의 절반 = min(CAGR/2, 상한)",
             gmap["half_of_own"]["growth"], min(own / 2, CAP), rel=1e-12)
        c.eq(f"{t} 과거 유지 = min(CAGR, 상한)",
             gmap["own_sustained"]["growth"], min(own, CAP), rel=1e-12)
        c.eq(f"{t} AI 가속 성장률 = 과거 유지와 같음",
             gmap["ai_sustained"]["growth"], min(own, CAP), rel=1e-12)
        c.true(f"트립와이어 {t} AI 가속의 감쇠 목표가 가장 높음",
               gmap["ai_sustained"]["fade_to"]
               > max(gmap[k]["fade_to"] for k in ORDER_KEYS
                     if k != "ai_sustained"))
        for g in co["grid"]:
            c.true(f"{t} {g['growth_key']} 성장률 상한 이내",
                   g["growth"] <= CAP + 1e-12, f"{g['growth']}")
            c.eq(f"{t} {g['growth_key']} 실질 성장률",
                 g["growth_real"], g["growth"] - infl, rel=1e-12)
            c.eq(f"재산출 {t} {g['growth_key']} 기초율 백분위",
                 g["base_rate_percentile_at_or_above"],
                 share_at_or_above(bands, g["growth"] - infl), rel=1e-9)
            c.same(f"{t} {g['growth_key']} 할인율 4개",
                   [x["discount_key"] for x in g["cells"]], DISCOUNT_KEYS)
            for cell in g["cells"]:
                n = f"{t} {g['growth_key']} @{cell['discount_key']}"
                re_ = dcf(co["ttm_nopat"], co["net_cash"],
                          co["shares_outstanding"], g["growth"],
                          g["fade_to"], co["incremental_roic_used"],
                          cell["discount"], tmap["inflation"]["rate"])
                c.eq(f"{n} 할인율", cell["discount"],
                     dmap[cell["discount_key"]]["rate"], rel=1e-12)
                if re_ is None:
                    c.true(f"{n} 발산 표기", cell["diverges"] is True)
                    c.true(f"{n} 발산 사유 기재", bool(cell.get("why")))
                    continue
                c.true(f"{n} 발산 아님", cell["diverges"] is False)
                c.eq(f"재산출 {n} 주당가치", cell["value_per_share"],
                     re_["value_per_share"], rel=1e-9)
                c.eq(f"항등식 {n} 상승여력", cell["upside_vs_price"],
                     cell["value_per_share"] / co["price"] - 1, rel=1e-12)
                c.eq(f"재산출 {n} 터미널 비중", cell["terminal_share"],
                     re_["terminal_share"], rel=1e-9)
                c.eq(f"재산출 {n} 10년 NOPAT CAGR", cell["nopat_cagr_10y"],
                     re_["nopat_cagr_10y"], rel=1e-9)
                c.true(f"트립와이어 {n} 터미널 비중 0~100%",
                       0 < cell["terminal_share"] < 1,
                       f"{cell['terminal_share']:.3f}")
                for m in d["margin_of_safety"]:
                    k = f"{int(m * 100)}%"
                    c.eq(f"항등식 {n} 안전마진 {k} 매수가",
                         cell["buy_price_at_margin"][k],
                         cell["value_per_share"] * (1 - m), rel=1e-12)
                c.eq(f"항등식 {n} 안전마진 0% = 주당가치",
                     cell["buy_price_at_margin"]["0%"],
                     cell["value_per_share"], rel=1e-12)
            # 할인율이 오르면 가치는 내려가야 합니다.
            vals = [x["value_per_share"] for x in g["cells"]
                    if not x["diverges"]]
            c.true(f"트립와이어 {t} {g['growth_key']} 할인율↑ ⇒ 가치↓",
                   vals == sorted(vals, reverse=True),
                   str([round(v, 1) for v in vals]))
        # 성장률이 오르면 가치는 올라가야 합니다 (같은 할인율에서).
        for dk in DISCOUNT_KEYS:
            seq = []
            for g in co["grid"]:
                cell = [x for x in g["cells"] if x["discount_key"] == dk][0]
                if not cell["diverges"]:
                    seq.append((g["growth"], g["fade_to"],
                                cell["value_per_share"]))
            # 성장률과 감쇠목표가 둘 다 같거나 높으면 가치도 높아야 합니다.
            for i in range(len(seq)):
                for j in range(len(seq)):
                    gi, fi, vi = seq[i]
                    gj, fj, vj = seq[j]
                    if gi >= gj and fi >= fj and (gi > gj or fi > fj):
                        c.true(f"트립와이어 {t} @{dk} 성장↑ ⇒ 가치↑",
                               vi >= vj - 1e-6,
                               f"({gi:.3f},{fi:.3f})={vi:.1f} vs "
                               f"({gj:.3f},{fj:.3f})={vj:.1f}")

        # 터미널 민감도 — 두 할인율 × 세 터미널.
        ts = co["terminal_sensitivity"]
        c.same(f"{t} 터미널 민감도 6개", len(ts), 6)
        c.same(f"{t} 터미널 민감도 성장률 기준",
               co["terminal_sensitivity_growth_key"], "half_of_own")
        c.same(f"{t} 터미널 민감도 구성",
               [(x["discount_key"], x["terminal_key"]) for x in ts],
               [(dk, tk) for dk in ("bond30_plus3", "bond30")
                for tk in [o["key"] for o in d["terminal_options"]]])
        for x in ts:
            tr = tmap[x["terminal_key"]]["rate"]
            dr = dmap[x["discount_key"]]["rate"]
            n = f"{t} 터미널 {x['terminal_key']}@{x['discount_key']}"
            c.eq(f"{n} 비율", x["rate"], tr, rel=1e-12)
            c.eq(f"{n} 할인율", x["discount"], dr, rel=1e-12)
            re_ = dcf(co["ttm_nopat"], co["net_cash"],
                      co["shares_outstanding"],
                      gmap["half_of_own"]["growth"],
                      gmap["half_of_own"]["fade_to"],
                      co["incremental_roic_used"], dr, tr)
            # 발산은 터미널 ≥ 할인율일 때만, 그때는 반드시.
            c.same(f"트립와이어 {n} 발산 조건", x["diverges"], tr >= dr)
            if re_ is None:
                c.true(f"{n} 발산 표기", x["diverges"] is True)
                c.true(f"{n} 발산 사유 기재", bool(x.get("why")))
                c.true(f"{n} 발산 시 가치 없음",
                       x["value_per_share"] is None)
            else:
                c.true(f"{n} 발산 아님", x["diverges"] is False)
                c.eq(f"재산출 {n} 주당가치", x["value_per_share"],
                     re_["value_per_share"], rel=1e-9)
                c.eq(f"항등식 {n} 상승여력", x["upside_vs_price"],
                     x["value_per_share"] / co["price"] - 1, rel=1e-12)
        for dk in ("bond30_plus3", "bond30"):
            live = [x["value_per_share"] for x in ts
                    if x["discount_key"] == dk and not x["diverges"]]
            c.true(f"트립와이어 {t} @{dk} 터미널↑ ⇒ 가치↑",
                   live == sorted(live), str([round(v, 1) for v in live]))
        # 순수 국채에서는 명목 GDP 터미널이 반드시 발산해야 합니다 — 그게
        # '국채 + 얼마'가 필요한 이유이고, 보고서가 그 논거를 씁니다.
        gdp_at_bond = [x for x in ts if x["discount_key"] == "bond30"
                       and x["terminal_key"] == "nominal_gdp"][0]
        c.true(f"트립와이어 {t} 순수 국채 + 명목GDP 터미널은 발산",
               gdp_at_bond["diverges"] is True)
    return c


MUTATIONS = [
    ("기초율 중위를 훼손", lambda d: d["base_rates"]["net_income_10y"]
     .__setitem__("median", 0.10)),
    ("기초율 구간 하나를 훼손", lambda d: _band(d, "net_income_10y",
                                        "0~10", 0.20)),
    ("기초율 구간 합을 1에서 벗어나게", lambda d: _band(d, "sales_10y",
                                              "0~5", 0.50)),
    ("기초율이 실질임을 숨김", lambda d: d["base_rates"]
     .__setitem__("real_terms", False)),
    ("생존편향 주의를 제거", lambda d: d["base_rates"]
     .__setitem__("survivorship_note", "")),
    ("매출·순이익 분포를 맞바꿈", lambda d: _swap_dists(d)),
    ("기대인플레이션 훼손", lambda d: d["macro"]["breakeven_inflation_10y"]
     .__setitem__("rate", 0.04)),
    ("30년 국채를 10년보다 낮게", lambda d: d["macro"]["treasury_30y"]
     .__setitem__("rate", 0.03)),
    ("국채+3%p 할인율 훼손", lambda d: _disc(d, "bond30_plus3", 0.07)),
    ("할인율 순서를 뒤섞음", lambda d: _disc(d, "project10", 0.04)),
    ("국채+3%p 근거에서 '해석' 제거",
     lambda d: _disc_basis(d, "bond30_plus3", "버핏의 규칙입니다.")),
    ("버핏 1992 인용 제거", lambda d: d.__setitem__(
        "buffett", [q for q in d["buffett"] if q["year"] != 1992])),
    ("버핏 인용 출처를 비표준 도메인으로",
     lambda d: d["buffett"][0].__setitem__("url", "http://example.com")),
    ("MSFT 격자 한 칸 주당가치 훼손",
     lambda d: _cell(d, "MSFT", "own_sustained", "bond30_plus3",
                     "value_per_share", 900.0)),
    ("GOOG 안전마진 매수가 훼손",
     lambda d: _margin(d, "GOOG", "half_of_own", "project10", "30%", 999.0)),
    ("NVDA 성장률을 상한 위로", lambda d: _growth(d, "NVDA",
                                          "own_sustained", 0.40)),
    ("MSFT 증분ROIC 훼손", lambda d: _co(d, "MSFT").__setitem__(
        "incremental_roic_used", 0.50)),
    ("GOOG 기초율 백분위 훼손", lambda d: _co(d, "GOOG").__setitem__(
        "own_cagr_percentile_at_or_above", 0.60)),
    ("NVDA 기록에서 한 해를 빼기", lambda d: _co(d, "NVDA")["history"].pop(3)),
    ("MSFT 기록 ROIC 한 해 훼손",
     lambda d: _co(d, "MSFT")["history"][5].__setitem__("roic", 0.05)),
    ("MSFT 기록 증가율 훼손",
     lambda d: _co(d, "MSFT")["history"][5].__setitem__(
         "operating_income_growth", 0.90)),
    ("해명 표의 10년 CAGR 훼손",
     lambda d: d["clarification"]["rows"][1].__setitem__(
         "nopat_cagr_10y", 0.02)),
    ("발산해야 하는 칸을 발산 아님으로 훼손", lambda d: _tsens(
        d, "GOOG", "bond30", "nominal_gdp", "diverges", False)),
    ("발산 아닌 칸을 발산으로 훼손", lambda d: _tsens(
        d, "MSFT", "bond30_plus3", "inflation", "diverges", True)),
    ("터미널 민감도 주당가치 훼손", lambda d: _tsens(
        d, "NVDA", "bond30_plus3", "half_gdp", "value_per_share", 999.0)),
    ("GOOG 터미널 비중 훼손",
     lambda d: _cell(d, "GOOG", "half_of_own", "project10",
                     "terminal_share", 1.4)),
    ("명목 GDP 항등식 훼손", lambda d: d["macro"]["nominal_gdp_long_run"]
     .__setitem__("rate", 0.09)),
]


def _co(d, t):
    return [x for x in d["companies"] if x["ticker"] == t][0]


def _band(d, key, lab, val):
    bs = d["base_rates"][key]["bands"]
    for i, (l, _) in enumerate(bs):
        if l == lab:
            bs[i] = [lab, val]
            return
    raise SystemExit(f"변이 대상 구간 없음: {key} {lab}")


def _swap_dists(d):
    br = d["base_rates"]
    br["sales_10y"], br["net_income_10y"] = (br["net_income_10y"],
                                             br["sales_10y"])


def _disc(d, key, val):
    for x in d["discount_options"]:
        if x["key"] == key:
            x["rate"] = val
            return
    raise SystemExit(f"변이 대상 할인율 없음: {key}")


def _disc_basis(d, key, val):
    for x in d["discount_options"]:
        if x["key"] == key:
            x["basis"] = val
            return


def _grid(d, t, gkey):
    return [g for g in _co(d, t)["grid"] if g["growth_key"] == gkey][0]


def _cell(d, t, gkey, dkey, field, val):
    g = _grid(d, t, gkey)
    [x for x in g["cells"] if x["discount_key"] == dkey][0][field] = val


def _margin(d, t, gkey, dkey, m, val):
    g = _grid(d, t, gkey)
    cell = [x for x in g["cells"] if x["discount_key"] == dkey][0]
    cell["buy_price_at_margin"][m] = val


def _tsens(d, t, dkey, tkey, field, val):
    for x in _co(d, t)["terminal_sensitivity"]:
        if x["discount_key"] == dkey and x["terminal_key"] == tkey:
            x[field] = val
            return
    raise SystemExit(f"변이 대상 민감도 칸 없음: {t} {dkey} {tkey}")


def _growth(d, t, gkey, val):
    _grid(d, t, gkey)["growth"] = val


def main():
    mutate = "--mutate" in sys.argv
    with open(DATA, encoding="utf-8") as fh:
        raw = fh.read()
    d = json.loads(raw)

    c = verify(d, Checks())
    print(f"검사 {c.passed + len(c.failures)}건 — 통과 {c.passed}, "
          f"실패 {len(c.failures)}")
    for f in c.failures[:25]:
        print("  ✗", f)
    if len(c.failures) > 25:
        print(f"  … 외 {len(c.failures) - 25}건")
    if c.failures:
        return 1

    if mutate:
        print(f"\n변이 검정 {len(MUTATIONS)}건 — 값을 훼손해 검사가 실제로 "
              f"실패하는지 확인")
        survived = []
        for name, mut in MUTATIONS:
            m = json.loads(raw)
            try:
                mut(m)
            except (SystemExit, KeyError, IndexError) as exc:
                print(f"  ✗ {name}: 훼손 자체가 실패 — {exc}")
                survived.append(f"{name} (훼손 실패)")
                continue
            mc = Checks()
            try:
                verify(m, mc)
            except (SystemExit, KeyError, IndexError, TypeError) as exc:
                print(f"  ✓ {name}: 구조 검사에서 중단 — "
                      f"{type(exc).__name__} {exc}")
                continue
            if mc.failures:
                print(f"  ✓ {name}: {len(mc.failures)}건 실패 "
                      f"— {mc.failures[0][:80]}")
            else:
                survived.append(name)
                print(f"  ✗ {name}: 아무 검사도 실패하지 않음 — 검사 구멍")
        if survived:
            print(f"\n변이 {len(survived)}건이 통과했습니다: {survived}")
            return 1
        print(f"  변이 {len(MUTATIONS)}/{len(MUTATIONS)}건 모두 포착")
    return 0


if __name__ == "__main__":
    sys.exit(main())
