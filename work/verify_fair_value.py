"""
fair_value.json 검증.

- **항등식.** TTM = 4개 분기 합, NOPAT = 영업이익 × (1−세율), 순현금 = 현금 −
  차입, 시가총액 = 주가 × 주식수, 그리고 DCF 전체를 한 해씩 다시 계산해
  현금흐름·현재가치·터미널·기업가치·주당가치를 대조합니다. 모형이 선형이라
  거꾸로 푼 "요구 NOPAT"도 되넣어 시가총액이 복원되는지 봅니다.

- **앵커.** 10-Q 손익계산서 렌더링에서 손으로 읽은 분기 수치. companyfacts 로
  재구성한 분기가 공시 원문과 같은지 봅니다 — 두 경로가 독립이므로, 재구성이
  틀리면 여기서만 걸립니다. 알파벳은 별도 파이프라인
  (analyse_goog_price.py, 282건 검증)의 TTM 영업이익과도 대조합니다.

- **규칙 재현.** 시나리오 입력값을 50개사 조사의 기록과 RULE 에서 다시
  계산합니다. 손으로 고친 가정이 섞이면 걸립니다.

- **트립와이어.** 시나리오 순서(낙관 > 중립 > 보수), 상한 준수, 할인율 >
  터미널 성장률, 증분 ROIC > 터미널 성장률, 1년차 재투자율 < 100%.

    python3 verify_fair_value.py
    python3 verify_fair_value.py --mutate
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DATA = os.path.join(HERE, "fv", "fair_value.json")
GOOG = os.path.join(HERE, "goog", "goog_price.json")
MM, BN = 1e6, 1e9
YEARS = 10

# 10-Q 손익계산서 렌더링(R2.htm)에서 손으로 읽은 분기 수치. 단위 백만 달러.
# companyfacts 와는 다른 문서이므로, 분기 재구성이 틀리면 여기서 걸립니다.
ANCHORS = {
    "MSFT": {
        "accession": "0001193125-26-436133",
        "quarter_end": "2026-09-30",
        "revenue": 92_279, "operating_income": 45_915,
        "other_income": 38, "pretax": 45_953, "tax": 9_324,
        "net_income": 36_629, "eps_diluted": 4.92,
        "shares_diluted": 7_446,
    },
    "NVDA": {
        "accession": "0001045810-26-000075",
        "quarter_end": "2026-07-26",
        "revenue": 96_221, "operating_income": 63_734,
        "other_income": 7_773, "pretax": 71_507, "tax": 11_819,
        "net_income": 59_688, "eps_diluted": 2.46,
        "shares_diluted": 24_285,
        # 반년 누적도 읽어 둡니다. 분기 재구성이 누적분의 차로 만들어지므로,
        # 누적값이 맞는지가 분기값이 맞는지와 별개의 확인입니다.
        "six_month_revenue": 177_837, "six_month_operating_income": 117_270,
    },
}

# 시장 가정과 규칙은 보고서의 결론을 좌우하므로 값으로 박아 둡니다.
# 엔진에서 바꾸면 여기서 걸리고, 그때는 의도한 변경인지 확인해야 합니다.
MARKET_EXPECTED = {
    "보수": {"discount": 0.11, "terminal_growth": 0.020, "fade_to": 0.025},
    "중립": {"discount": 0.10, "terminal_growth": 0.025, "fade_to": 0.035},
    "낙관": {"discount": 0.09, "terminal_growth": 0.030, "fade_to": 0.045},
}
RULE_EXPECTED = {
    "보수": {"growth_divisor": 3.0, "growth_cap": 0.10,
             "roic_source": "min", "roic_divisor": 1.0, "roic_cap": 0.15},
    "중립": {"growth_divisor": 2.0, "growth_cap": 0.15,
             "roic_source": "median", "roic_divisor": 2.0, "roic_cap": 0.25},
    "낙관": {"growth_divisor": 1.0, "growth_cap": 0.25,
             "roic_source": "median", "roic_divisor": 1.0, "roic_cap": 0.35},
}
ORDER = ["보수", "중립", "낙관"]


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


def dcf_recompute(base_nopat, net_cash, shares, s, years=YEARS):
    """엔진과 독립적으로 DCF 를 다시 계산합니다."""
    proj, pv, nopat = [], 0.0, base_nopat
    for t in range(1, years + 1):
        g = s["growth"] + (s["fade_to"] - s["growth"]) * (t - 1) / (years - 1)
        rr = g / s["incremental_roic"]
        nopat *= (1 + g)
        fcf = nopat * (1 - rr)
        disc = fcf / (1 + s["discount"]) ** t
        pv += disc
        proj.append({"growth": g, "nopat": nopat, "reinvestment_rate": rr,
                     "free_cash_flow": fcf, "present_value": disc})
    tg = s["terminal_growth"]
    term = (proj[-1]["nopat"] * (1 + tg) * (1 - tg / s["incremental_roic"])
            / (s["discount"] - tg))
    term_pv = term / (1 + s["discount"]) ** years
    ev = pv + term_pv
    eq = ev + net_cash
    return {"projection": proj, "pv_of_forecast": pv, "pv_of_terminal": term_pv,
            "enterprise_value": ev, "equity_value": eq,
            "value_per_share": eq / shares}


def verify(d, c):
    c.true("생성일 존재", bool(d.get("generated")))
    c.true("50개사 조사 생성일이 산출일 이하",
           d["roic_study_generated"] <= d["generated"],
           f"{d['roic_study_generated']} vs {d['generated']}")
    c.same("투영 연수", d["projection_years"], YEARS)
    for name in ORDER:
        for k, v in MARKET_EXPECTED[name].items():
            c.eq(f"시장가정 {name}.{k}", d["market_assumptions"][name][k], v,
                 rel=0)
        for k, v in RULE_EXPECTED[name].items():
            if isinstance(v, str):
                c.same(f"규칙 {name}.{k}", d["rule"][name][k], v)
            else:
                c.eq(f"규칙 {name}.{k}", d["rule"][name][k], v, rel=0)

    applied = [x for x in d["companies"] if x["model"] == "applied"]
    c.same("모형 적용 기업 수", len(applied), 3)
    c.same("기준이익 미성립 기업 수",
           len([x for x in d["companies"]
                if x["model"] == "base_not_established"]), 1)

    for co in applied:
        t = co["ticker"]
        ttm, bs, rec = co["ttm"], co["balance_sheet"], co["record"]

        # ---- TTM 항등식 -------------------------------------------------
        for key in ("operating_income", "revenue", "pretax_income",
                    "income_tax_expense", "nonoperating_income"):
            blk = ttm[key]
            c.same(f"{t} {key} 분기 4개", len(blk["quarters"]), 4)
            c.same(f"{t} {key} 분기말 4개", len(blk["quarter_ends"]), 4)
            c.eq(f"{t} {key} TTM = 분기 합", blk["value"],
                 sum(blk["quarters"]), tol=1.0, rel=1e-9)
            c.true(f"{t} {key} 분기말 간격 250~290일",
                   250 <= blk["span_days"] <= 290, str(blk["span_days"]))
        c.same(f"{t} 자료 기준일 = 영업이익 최종 분기말", co["data_as_of"],
               ttm["operating_income"]["quarter_ends"][-1])
        c.eq(f"{t} 실효세율 = 법인세/세전", ttm["effective_tax_rate"],
             ttm["income_tax_expense"]["value"] / ttm["pretax_income"]["value"],
             rel=1e-12)
        c.eq(f"{t} NOPAT = 영업이익×(1−세율)", ttm["nopat"],
             ttm["operating_income"]["value"]
             * (1 - ttm["effective_tax_rate"]), rel=1e-12)
        c.eq(f"{t} 법정세율 21% NOPAT", ttm["nopat_at_statutory_21"],
             ttm["operating_income"]["value"] * 0.79, rel=1e-12)
        c.eq(f"{t} 영업이익률", ttm["operating_margin"],
             ttm["operating_income"]["value"] / ttm["revenue"]["value"],
             rel=1e-12)
        c.eq(f"{t} 영업외 비중", ttm["nonoperating_share_of_pretax"],
             ttm["nonoperating_income"]["value"]
             / ttm["pretax_income"]["value"], rel=1e-12)
        c.true(f"{t} 실효세율 0~35%", 0 <= ttm["effective_tax_rate"] <= 0.35,
               f"{ttm['effective_tax_rate']:.4f}")
        c.true(f"{t} TTM 영업이익 양수", ttm["operating_income"]["value"] > 0)

        # ---- 재무상태 ---------------------------------------------------
        c.eq(f"{t} 차입 = 구성항목 합", bs["debt"],
             sum(p["value"] for p in bs["debt_parts"]), tol=1.0, rel=1e-9)
        c.eq(f"{t} 순현금 = 현금 − 차입", bs["net_cash"],
             bs["cash_and_short_term"]["value"] - bs["debt"], rel=1e-12)
        c.eq(f"{t} 투하자본 = 자본 + 차입 − 현금", bs["invested_capital"],
             bs["total_equity"]["value"] + bs["debt"]
             - bs["cash_and_short_term"]["value"], rel=1e-12)
        c.true(f"{t} 자기자본 양수", bs["total_equity"]["value"] > 0)
        c.true(f"{t} 차입 0 이상", bs["debt"] >= 0, f"{bs['debt']:,.0f}")

        # ---- 시가총액 ---------------------------------------------------
        c.eq(f"{t} 시가총액 = 주가 × 주식수", co["market_cap"],
             co["price"] * co["shares_outstanding"]["value"], rel=1e-12)
        c.true(f"{t} 주가가 52주 범위 안",
               co["fifty_two_week_low"] <= co["price"]
               <= co["fifty_two_week_high"],
               f"{co['fifty_two_week_low']}–{co['price']}–"
               f"{co['fifty_two_week_high']}")

        # ---- 기록과 규칙 재현 -------------------------------------------
        c.same(f"{t} 10년 창 연수", len(rec["years"]), 10)
        rs = [y["roic"] for y in rec["years"] if y.get("roic")]
        c.same(f"{t} ROIC 사용가능 연수", len(rs), 10)
        import statistics
        c.eq(f"{t} 요약 중위 ROIC 재산출", rec["summary"]["roic_median"],
             statistics.median(rs), rel=1e-9)
        c.eq(f"{t} 요약 최저 ROIC 재산출", rec["summary"]["roic_min"],
             min(rs), rel=1e-9)
        c.true(f"{t} 10년 전 기간 문턱 초과",
               all(r > d["wacc_for_roic_hurdle"] for r in rs),
               str([round(r, 3) for r in rs]))
        by = {y["fiscal_year"]: y for y in rec["years"]}
        if rec["cagr_from"] in by:
            c.eq(f"{t} 10년 영업이익 CAGR 재산출",
                 rec["operating_income_cagr"],
                 (by[rec["cagr_to"]]["operating_income"]
                  / by[rec["cagr_from"]]["operating_income"])
                 ** (1 / rec["cagr_years"]) - 1, rel=1e-9)
        base = {"min": rec["summary"]["roic_min"],
                "median": rec["summary"]["roic_median"]}
        for s in co["scenario_inputs"]:
            r = RULE_EXPECTED[s["name"]]
            g_raw = rec["operating_income_cagr"] / r["growth_divisor"]
            ri_raw = base[r["roic_source"]] / r["roic_divisor"]
            c.eq(f"{t} {s['name']} 성장률 규칙 재현", s["growth"],
                 min(g_raw, r["growth_cap"]), rel=1e-12)
            c.eq(f"{t} {s['name']} 증분ROIC 규칙 재현", s["incremental_roic"],
                 min(ri_raw, r["roic_cap"]), rel=1e-12)
            c.same(f"{t} {s['name']} 성장 상한 표기", s["growth_capped"],
                   g_raw > r["growth_cap"])
            c.same(f"{t} {s['name']} ROIC 상한 표기",
                   s["incremental_roic_capped"], ri_raw > r["roic_cap"])
            c.true(f"{t} {s['name']} 성장률 상한 이내",
                   s["growth"] <= r["growth_cap"] + 1e-12)
            c.true(f"{t} {s['name']} 증분ROIC 상한 이내",
                   s["incremental_roic"] <= r["roic_cap"] + 1e-12)

        # ---- DCF 재계산 --------------------------------------------------
        for v in co["valuations"]:
            a = v["assumptions"]
            re_ = dcf_recompute(ttm["nopat"], bs["net_cash"],
                                co["shares_outstanding"]["value"], a)
            n = f"{t} {v['scenario']}"
            c.same(f"{n} 투영 연수", len(v["projection"]), YEARS)
            c.eq(f"{n} 예측기간 현재가치", v["pv_of_forecast"],
                 re_["pv_of_forecast"], rel=1e-9)
            c.eq(f"{n} 예측기간 현재가치 = 연도별 합", v["pv_of_forecast"],
                 sum(p["present_value"] for p in v["projection"]),
                 tol=1.0, rel=1e-9)
            c.eq(f"{n} 터미널 현재가치", v["pv_of_terminal"],
                 re_["pv_of_terminal"], rel=1e-9)
            c.eq(f"{n} 기업가치 = 예측 + 터미널", v["enterprise_value"],
                 v["pv_of_forecast"] + v["pv_of_terminal"], tol=1.0, rel=1e-9)
            c.eq(f"{n} 기업가치 재계산", v["enterprise_value"],
                 re_["enterprise_value"], rel=1e-9)
            c.eq(f"{n} 자기자본가치 = 기업가치 + 순현금", v["equity_value"],
                 v["enterprise_value"] + bs["net_cash"], tol=1.0, rel=1e-9)
            c.eq(f"{n} 주당가치 = 자기자본가치 / 주식수", v["value_per_share"],
                 v["equity_value"] / co["shares_outstanding"]["value"],
                 rel=1e-12)
            c.eq(f"{n} 주당가치 재계산", v["value_per_share"],
                 re_["value_per_share"], rel=1e-9)
            c.eq(f"{n} 시장 대비", v["upside_vs_market"],
                 v["equity_value"] / co["market_cap"] - 1, rel=1e-12)
            c.eq(f"{n} 터미널 비중", v["terminal_share"],
                 v["pv_of_terminal"] / v["enterprise_value"], rel=1e-12)
            # 성장 경로: 1년차는 초기 성장률, 10년차는 감쇠 목표, 선형.
            c.eq(f"{n} 1년차 성장률", v["projection"][0]["growth"],
                 a["growth"], rel=1e-12)
            c.eq(f"{n} 10년차 성장률", v["projection"][-1]["growth"],
                 a["fade_to"], rel=1e-12)
            for i, p in enumerate(v["projection"], start=1):
                g = a["growth"] + (a["fade_to"] - a["growth"]) \
                    * (i - 1) / (YEARS - 1)
                c.eq(f"{n} {i}년차 성장률", p["growth"], g, rel=1e-12)
                c.eq(f"{n} {i}년차 재투자율 = 성장÷증분ROIC",
                     p["reinvestment_rate"], g / a["incremental_roic"],
                     rel=1e-12)
                c.eq(f"{n} {i}년차 FCF = NOPAT×(1−재투자율)",
                     p["free_cash_flow"],
                     p["nopat"] * (1 - p["reinvestment_rate"]), rel=1e-9)
                c.eq(f"{n} {i}년차 현재가치", p["present_value"],
                     p["free_cash_flow"] / (1 + a["discount"]) ** i, rel=1e-9)
                prev = ttm["nopat"] if i == 1 else v["projection"][i - 2]["nopat"]
                c.eq(f"{n} {i}년차 NOPAT = 전년 × (1+성장)", p["nopat"],
                     prev * (1 + g), rel=1e-9)
            c.eq(f"{n} 1년차 재투자율 필드",
                 v["first_year_reinvestment_rate"],
                 a["growth"] / a["incremental_roic"], rel=1e-12)
            # 트립와이어
            c.true(f"{n} 할인율 > 터미널 성장률",
                   a["discount"] > a["terminal_growth"])
            c.true(f"{n} 증분ROIC > 터미널 성장률",
                   a["incremental_roic"] > a["terminal_growth"])
            c.true(f"{n} 1년차 재투자율 < 100%",
                   v["first_year_reinvestment_rate"] < 1.0,
                   f"{v['first_year_reinvestment_rate']:.3f}")
            c.true(f"{n} 터미널 비중 0~100%",
                   0 < v["terminal_share"] < 1.0,
                   f"{v['terminal_share']:.3f}")
            c.true(f"{n} 주당가치 양수", v["value_per_share"] > 0)
            # 거꾸로 푼 요구 NOPAT 을 되넣으면 시가총액이 복원됩니다.
            need = v["required_nopat_at_price"]
            back = dcf_recompute(need, bs["net_cash"],
                                 co["shares_outstanding"]["value"], a)
            c.eq(f"{n} 요구 NOPAT 되넣기 = 시가총액", back["equity_value"],
                 co["market_cap"], tol=1.0, rel=1e-7)
            c.eq(f"{n} 요구 NOPAT 배수", v["required_nopat_multiple"],
                 need / ttm["nopat"], rel=1e-12)
            # 정당화 성장률도 되넣어 확인합니다. 해가 없으면 상한에서도
            # 시가총액에 닿지 않아야 합니다.
            ig = v["implied_growth_at_price"]
            if ig is None:
                bound = a["incremental_roic"] * 0.9995
                c.true(f"{n} 정당화 성장률 없음 — 증분ROIC 상한에서도 미달",
                       dcf_recompute(ttm["nopat"], bs["net_cash"],
                                     co["shares_outstanding"]["value"],
                                     {**a, "growth": bound,
                                      "fade_to": min(a["fade_to"], bound)}
                                     )["equity_value"] < co["market_cap"])
                c.true(f"{n} 정당화 성장률 없음 — 설명 문구 있음",
                       bool(v.get("implied_growth_note")))
            else:
                c.true(f"{n} 정당화 성장률 ≤ 증분ROIC (자기 현금으로 조달 가능)",
                       ig <= a["incremental_roic"] + 1e-9,
                       f"{ig:.4f} vs {a['incremental_roic']:.4f}")
                back2 = dcf_recompute(
                    ttm["nopat"], bs["net_cash"],
                    co["shares_outstanding"]["value"],
                    {**a, "growth": ig, "fade_to": min(a["fade_to"], ig)})
                c.eq(f"{n} 정당화 성장률 되넣기 = 시가총액",
                     back2["equity_value"], co["market_cap"],
                     tol=1.0, rel=1e-6)
                c.true(f"{n} 정당화 성장률 설명 문구 없음",
                       v.get("implied_growth_note") is None)

        # ---- 시나리오 천장과 추세 ---------------------------------------
        for v in co["valuations"]:
            a, n = v["assumptions"], f"{t} {v['scenario']}"
            c.eq(f"{n} 현재가/평가치", v["price_to_value"],
                 co["price"] / v["value_per_share"], rel=1e-12)
            best = v["best_case_in_scenario"]
            re_ = dcf_recompute(ttm["nopat"], bs["net_cash"],
                                co["shares_outstanding"]["value"],
                                {**a, "growth": best["growth"],
                                 "fade_to": min(a["fade_to"],
                                                best["growth"])})
            c.eq(f"{n} 천장 주당가치 재계산", best["value_per_share"],
                 re_["value_per_share"], rel=1e-9)
            c.true(f"{n} 천장 ≥ 시나리오 자체 값",
                   best["value_per_share"] >= v["value_per_share"] - 1e-6,
                   f"{best['value_per_share']:,.2f} vs "
                   f"{v['value_per_share']:,.2f}")
            c.eq(f"{n} 현재가/천장", v["price_vs_best_case"],
                 co["price"] / best["value_per_share"], rel=1e-12)
            # 정당화 성장률이 없다는 것과 천장이 현재가보다 낮다는 것은 같은
            # 사실의 두 표현입니다. 어긋나면 한쪽이 틀렸습니다.
            if v["implied_growth_at_price"] is None:
                c.true(f"{n} 정당화 성장률 없음 ⇔ 천장 < 현재가",
                       best["value_per_share"] < co["price"],
                       f"천장 {best['value_per_share']:,.2f} vs "
                       f"현재가 {co['price']:,.2f}")
            else:
                c.true(f"{n} 정당화 성장률 있음 ⇔ 천장 ≥ 현재가",
                       best["value_per_share"] >= co["price"] - 1e-6,
                       f"천장 {best['value_per_share']:,.2f} vs "
                       f"현재가 {co['price']:,.2f}")
        tr = rec["trend"]
        peak = max(rec["years"], key=lambda y: y["roic"] or 0)
        last = max(rec["years"], key=lambda y: y["fiscal_year"])
        c.same(f"{t} 추세 고점 연도", tr["peak_fiscal_year"],
               peak["fiscal_year"])
        c.eq(f"{t} 추세 고점 ROIC", tr["peak_roic"], peak["roic"], rel=0)
        c.same(f"{t} 추세 최근 연도", tr["last_fiscal_year"],
               last["fiscal_year"])
        c.eq(f"{t} 추세 영업이익 배수", tr["operating_income_multiple"],
             last["operating_income"] / peak["operating_income"], rel=1e-12)
        c.eq(f"{t} 추세 투하자본 배수", tr["invested_capital_multiple"],
             last["invested_capital_avg"] / peak["invested_capital_avg"],
             rel=1e-12)
        c.true(f"{t} 고점이 최근 연도가 아님 (ROIC 하락 추세)",
               tr["peak_fiscal_year"] < tr["last_fiscal_year"],
               f"고점 FY{tr['peak_fiscal_year']} vs 최근 "
               f"FY{tr['last_fiscal_year']}")
        c.true(f"{t} 투하자본 배수 > 영업이익 배수 (자본이 더 빨리 늘었음)",
               tr["invested_capital_multiple"]
               > tr["operating_income_multiple"],
               f"{tr['invested_capital_multiple']:.2f} vs "
               f"{tr['operating_income_multiple']:.2f}")

        # ---- 시나리오 순서 ----------------------------------------------
        vals = {v["scenario"]: v["value_per_share"] for v in co["valuations"]}
        c.same(f"{t} 시나리오 3개", sorted(vals), sorted(ORDER))
        c.true(f"{t} 낙관 > 중립 > 보수",
               vals["낙관"] > vals["중립"] > vals["보수"],
               str({k: round(x, 1) for k, x in vals.items()}))
        order_in_file = [v["scenario"] for v in co["valuations"]]
        c.same(f"{t} 시나리오 순서 보존", order_in_file, ORDER)

        # ---- 앵커 (10-Q 원문에서 손으로 읽음) ----------------------------
        if t in ANCHORS:
            A = ANCHORS[t]
            qe = A["quarter_end"]
            oi = ttm["operating_income"]
            c.true(f"{t} 앵커 분기말이 TTM 안에 있음", qe in oi["quarter_ends"],
                   f"{qe} vs {oi['quarter_ends']}")
            if qe in oi["quarter_ends"]:
                i = oi["quarter_ends"].index(qe)
                c.eq(f"{t} 앵커 분기 영업이익 {qe}", oi["quarters"][i],
                     A["operating_income"] * MM, rel=0)
                c.eq(f"{t} 앵커 분기 매출 {qe}",
                     ttm["revenue"]["quarters"][i], A["revenue"] * MM, rel=0)
                c.eq(f"{t} 앵커 분기 세전이익 {qe}",
                     ttm["pretax_income"]["quarters"][i], A["pretax"] * MM,
                     rel=0)
                c.eq(f"{t} 앵커 분기 법인세 {qe}",
                     ttm["income_tax_expense"]["quarters"][i], A["tax"] * MM,
                     rel=0)
                c.eq(f"{t} 앵커 분기 영업외수익 {qe}",
                     ttm["nonoperating_income"]["quarters"][i],
                     A["other_income"] * MM, rel=0)
                # 공시 안에서도 맞아야 합니다: 영업이익 + 영업외 = 세전.
                c.eq(f"{t} 앵커 항등식 영업이익+영업외=세전",
                     A["operating_income"] + A["other_income"], A["pretax"],
                     rel=0)
                c.eq(f"{t} 앵커 항등식 세전−법인세=순이익",
                     A["pretax"] - A["tax"], A["net_income"], rel=0)
                c.eq(f"{t} 앵커 항등식 EPS×주식수≈순이익",
                     A["eps_diluted"] * A["shares_diluted"], A["net_income"],
                     rel=0.005)

    # ---- 알파벳: 별도 파이프라인과 교차검증 -----------------------------
    goog = [x for x in applied if x["ticker"] == "GOOG"][0]
    if os.path.exists(GOOG):
        g = json.load(open(GOOG, encoding="utf-8"))
        c.eq("교차검증 알파벳 TTM 영업이익 = goog 파이프라인",
             goog["ttm"]["operating_income"]["value"],
             g["analysis"]["operating_income_ttm"], tol=1.0, rel=1e-9)
        c.eq("교차검증 알파벳 주식수 = goog 파이프라인",
             goog["shares_outstanding"]["value"],
             g["analysis"]["shares_outstanding"], rel=0)
        # 세율은 창이 달라(9개월 vs 4개 분기) 값이 다릅니다. 2%p 안이어야
        # 합니다 — 더 벌어지면 한쪽이 잘못된 기간을 읽고 있습니다.
        c.true("교차검증 알파벳 세율 차이 2%p 이내",
               abs(goog["ttm"]["effective_tax_rate"]
                   - g["analysis"]["tax_rate_ttm"]) < 0.02,
               f"{goog['ttm']['effective_tax_rate']:.3f} vs "
               f"{g['analysis']['tax_rate_ttm']:.3f}")
        c.true("교차검증 알파벳 NOPAT 차이 5% 이내",
               abs(goog["ttm"]["nopat"] / g["analysis"]["nopat_ttm"] - 1) < 0.05,
               f"{goog['ttm']['nopat'] / BN:,.1f} vs "
               f"{g['analysis']['nopat_ttm'] / BN:,.1f}")

    # ---- 스페이스X: 모형 미적용 ------------------------------------------
    sx = [x for x in d["companies"] if x["model"] == "base_not_established"][0]
    c.same("스페이스X 티커", sx["ticker"], "SPCX")
    c.true("스페이스X 미적용 사유 기재", bool(sx.get("why_not")))
    c.same("스페이스X 모형 상태", sx["model"], "base_not_established")
    c.true("스페이스X 단일 적정주가 없음", "valuations" not in sx)
    c.same("스페이스X 기준이익 후보 2개", len(sx["earnings_bases"]), 2)
    c.eq("스페이스X 시가총액 = 주가 × 주식수", sx["market_cap"],
         sx["price"] * sx["shares_outstanding"]["value"], rel=1e-12)
    c.eq("스페이스X 순현금 = 현금 − 차입", sx["balance_sheet"]["net_cash"],
         sx["balance_sheet"]["cash_and_securities"]
         - sx["balance_sheet"]["debt"], rel=1e-12)
    # 현금을 0 으로 읽어 순현금이 음수가 된 적이 있습니다. 10-Q 표지의 현금이
    # 수백억 달러인 회사이므로, 0 이나 음수는 읽기 실패로 봅니다.
    c.true("스페이스X 현금 > 0", sx["balance_sheet"]["cash_and_securities"] > 0,
           f"{sx['balance_sheet']['cash_and_securities']:,.0f}")
    c.true("스페이스X 순현금 양수", sx["balance_sheet"]["net_cash"] > 0,
           f"{sx['balance_sheet']['net_cash']:,.0f}")
    c.same("스페이스X 역산 3개", len(sx["reverse"]), 3)
    c.same("스페이스X 역산 순서", [r["scenario"] for r in sx["reverse"]], ORDER)
    # 기준이익 후보 중 9개월 연율화는 음수여야 합니다 — 그것이 모형을 쓰지
    # 않는 이유이고, 양수가 되면 사유 자체가 성립하지 않습니다.
    # 기준이익이 성립하지 않는 이유는 "음수"가 아니라 "얇고 갈려 있음"입니다.
    # 처음에 음수라고 적었다가 틀렸으므로, 그 사실관계를 검사로 박아 둡니다.
    nine = [b for b in sx["earnings_bases"] if "9개월" in b["name"]][0]
    c.eq("스페이스X 9개월 연율화 = 저장값", nine["nopat"],
         sx["nopat_nine_months_annualised"], rel=1e-12)
    c.true("스페이스X 9개월 연율화 NOPAT 양수 (음수가 아님)",
           nine["nopat"] > 0, f"{nine['nopat'] / BN:,.2f}")
    c.true("스페이스X 상반기 NOPAT 음수", sx["nopat_first_half"] < 0,
           f"{sx['nopat_first_half'] / BN:,.2f}")
    c.true("스페이스X 3분기 NOPAT 양수", sx["nopat_q3"] > 0,
           f"{sx['nopat_q3'] / BN:,.2f}")
    c.eq("스페이스X 3분기 연율화 = 3분기 × 4", sx["nopat_q3_annualised"],
         sx["nopat_q3"] * 4, rel=1e-12)
    c.true("스페이스X 9개월 연율화 < 3분기 연율화의 1/5 (기준이 갈려 있음)",
           nine["nopat"] < sx["nopat_q3_annualised"] / 5,
           f"{nine['nopat'] / BN:,.2f} vs "
           f"{sx['nopat_q3_annualised'] / BN:,.2f}")
    q3b = [b for b in sx["earnings_bases"] if "3분기" in b["name"]][0]
    c.eq("스페이스X 3분기 기준 = 3분기 × 4", q3b["nopat"],
         sx["nopat_q3"] * 4, rel=1e-12)
    for b in sx["earnings_bases"]:
        if not b.get("valuations"):
            continue
        c.same(f"스페이스X [{b['name']}] 시나리오 3개",
               [v["scenario"] for v in b["valuations"]], ORDER)
        for v in b["valuations"]:
            a = v["assumptions"]
            re_ = dcf_recompute(b["nopat"], sx["balance_sheet"]["net_cash"],
                                sx["shares_outstanding"]["value"], a)
            c.eq(f"스페이스X [{b['name']}] {v['scenario']} 주당가치 재계산",
                 v["value_per_share"], re_["value_per_share"], rel=1e-9)
            c.eq(f"스페이스X [{b['name']}] {v['scenario']} 시장 대비",
                 v["upside_vs_market"],
                 v["equity_value"] / sx["market_cap"] - 1, rel=1e-12)
        vals = {v["scenario"]: v["value_per_share"] for v in b["valuations"]}
        c.true(f"스페이스X [{b['name']}] 낙관 > 중립 > 보수",
               vals["낙관"] > vals["중립"] > vals["보수"],
               str({k: round(x, 2) for k, x in vals.items()}))
    for r in sx["reverse"]:
        a = r["assumptions"]
        back = dcf_recompute(r["required_nopat_at_price"],
                             sx["balance_sheet"]["net_cash"],
                             sx["shares_outstanding"]["value"], a)
        c.eq(f"스페이스X {r['scenario']} 요구 NOPAT 되넣기 = 시가총액",
             back["equity_value"], sx["market_cap"], tol=1.0, rel=1e-7)
        c.eq(f"스페이스X {r['scenario']} 주당 요구 NOPAT",
             r["required_nopat_per_share"],
             r["required_nopat_at_price"] / sx["shares_outstanding"]["value"],
             rel=1e-12)
        c.true(f"스페이스X {r['scenario']} 요구 NOPAT 양수",
               r["required_nopat_at_price"] > 0)
    # 가정이 관대해질수록 요구 이익은 줄어야 합니다.
    rv = sx["revenue"]
    seg = sx["segments_9m"]
    c.eq("스페이스X 9개월 매출 = 사업부 합", rv["nine_months_2026"],
         sum(v["revenue"]["9m_2026"] for v in seg.values()
             if isinstance(v, dict)), tol=1.0, rel=1e-9)
    c.eq("스페이스X 3분기 매출 = 사업부 합", rv["q3_2026"],
         sum(v["revenue"]["q3_2026"] for v in seg.values()
             if isinstance(v, dict)), tol=1.0, rel=1e-9)
    c.eq("스페이스X 9개월 연율화 매출", rv["nine_months_annualised"],
         rv["nine_months_2026"] * 4 / 3, rel=1e-12)
    c.eq("스페이스X 3분기 연율화 매출", rv["q3_annualised"],
         rv["q3_2026"] * 4, rel=1e-12)
    c.eq("스페이스X 시총/연율화매출", rv["market_cap_to_q3_annualised_revenue"],
         sx["market_cap"] / rv["q3_annualised"], rel=1e-12)
    c.true("스페이스X 3분기 연율화 매출 > 9개월 연율화 (가속 중)",
           rv["q3_annualised"] > rv["nine_months_annualised"],
           f"{rv['q3_annualised'] / BN:,.1f} vs "
           f"{rv['nine_months_annualised'] / BN:,.1f}")
    for r in sx["reverse"]:
        c.eq(f"스페이스X {r['scenario']} 요구이익/연율화매출",
             r["as_share_of_q3_annualised_revenue"],
             r["required_nopat_at_price"] / rv["q3_annualised"], rel=1e-12)
    needs = [r["required_nopat_at_price"] for r in sx["reverse"]]
    c.true("스페이스X 보수 > 중립 > 낙관 (요구 이익)",
           needs[0] > needs[1] > needs[2],
           str([round(x / BN, 1) for x in needs]))
    return c


MUTATIONS = [
    ("MSFT 분기 영업이익 하나 훼손", lambda d: _q(d, "MSFT", "operating_income",
                                            3, 50_000 * MM)),
    ("NVDA 분기 매출 하나 훼손", lambda d: _q(d, "NVDA", "revenue", 3,
                                        90_000 * MM)),
    ("GOOG TTM 영업이익 훼손", lambda d: _ttm(d, "GOOG", "operating_income",
                                         150e9)),
    ("MSFT 실효세율 훼손", lambda d: _set(d, "MSFT", ("ttm",
                                                "effective_tax_rate"), 0.25)),
    ("NVDA NOPAT 훼손", lambda d: _set(d, "NVDA", ("ttm", "nopat"), 200e9)),
    ("MSFT 순현금 훼손", lambda d: _set(d, "MSFT",
                                   ("balance_sheet", "net_cash"), 100e9)),
    ("GOOG 주식수 훼손", lambda d: _set(d, "GOOG",
                                   ("shares_outstanding", "value"), 11e9)),
    ("NVDA 주가 훼손", lambda d: _set(d, "NVDA", ("price",), 250.0)),
    ("MSFT 낙관 주당가치 훼손", lambda d: _val(d, "MSFT", "낙관",
                                        "value_per_share", 600.0)),
    ("GOOG 중립 기업가치 훼손", lambda d: _val(d, "GOOG", "중립",
                                        "enterprise_value", 3e12)),
    ("NVDA 보수 터미널 현재가치 훼손", lambda d: _val(d, "NVDA", "보수",
                                            "pv_of_terminal", 2e12)),
    ("MSFT 중립 1년차 FCF 훼손", lambda d: _proj(d, "MSFT", "중립", 0,
                                          "free_cash_flow", 99e9)),
    ("GOOG 낙관 성장 경로 훼손", lambda d: _proj(d, "GOOG", "낙관", 5,
                                         "growth", 0.30)),
    ("NVDA 낙관 증분ROIC를 상한 위로 훼손",
     lambda d: _assume(d, "NVDA", "낙관", "incremental_roic", 0.50)),
    ("MSFT 보수 할인율을 터미널 아래로 훼손",
     lambda d: _assume(d, "MSFT", "보수", "discount", 0.01)),
    ("GOOG 중립 성장률 규칙 위반", lambda d: _assume(d, "GOOG", "중립",
                                             "growth", 0.14)),
    ("시장가정 할인율 훼손", lambda d: d["market_assumptions"]["중립"]
     .__setitem__("discount", 0.08)),
    ("규칙 상한 훼손", lambda d: d["rule"]["낙관"].__setitem__("growth_cap",
                                                        0.40)),
    ("MSFT 10년 CAGR 훼손", lambda d: _set(d, "MSFT",
                                       ("record", "operating_income_cagr"),
                                       0.30)),
    ("NVDA 10년 중 한 해를 문턱 아래로",
     lambda d: _rec_year(d, "NVDA", 3, 0.05)),
    ("GOOG 요구 NOPAT 훼손", lambda d: _val(d, "GOOG", "보수",
                                       "required_nopat_at_price", 90e9)),
    ("NVDA 정당화 성장률 훼손", lambda d: _val(d, "NVDA", "중립",
                                       "implied_growth_at_price", 0.10)),
    ("스페이스X 요구 NOPAT 훼손", lambda d: _sx(d, 1,
                                        "required_nopat_at_price", 60e9)),
    ("스페이스X 9개월 NOPAT을 양수로", lambda d: _sx_base(d, "9개월", 5e9)),
    ("스페이스X에 적정주가를 넣음", lambda d: _sx_add_valuations(d)),
    ("MSFT 보수 천장을 현재가 위로 훼손", lambda d: _best(d, "MSFT", "보수",
                                                   600.0)),
    ("NVDA 낙관 천장을 현재가 아래로 훼손", lambda d: _best(d, "NVDA", "낙관",
                                                   100.0)),
    ("GOOG 추세 고점 연도 훼손", lambda d: _set(d, "GOOG",
                                          ("record", "trend",
                                           "peak_fiscal_year"), 2025)),
    ("MSFT 추세 투하자본 배수 훼손", lambda d: _set(
        d, "MSFT", ("record", "trend", "invested_capital_multiple"), 1.5)),
    ("스페이스X 3분기 매출 훼손", lambda d: _set_sx_rev(d, "q3_2026", 5e9)),
    ("GOOG 현재가/평가치 훼손", lambda d: _val(d, "GOOG", "중립",
                                        "price_to_value", 1.0)),
]


def _co(d, t):
    return [x for x in d["companies"] if x["ticker"] == t][0]


def _q(d, t, key, i, val):
    _co(d, t)["ttm"][key]["quarters"][i] = val


def _ttm(d, t, key, val):
    _co(d, t)["ttm"][key]["value"] = val


def _set(d, t, path, val):
    o = _co(d, t)
    for k in path[:-1]:
        o = o[k]
    o[path[-1]] = val


def _val(d, t, scen, key, val):
    v = [x for x in _co(d, t)["valuations"] if x["scenario"] == scen][0]
    v[key] = val


def _proj(d, t, scen, i, key, val):
    v = [x for x in _co(d, t)["valuations"] if x["scenario"] == scen][0]
    v["projection"][i][key] = val


def _assume(d, t, scen, key, val):
    co = _co(d, t)
    for v in co["valuations"]:
        if v["scenario"] == scen:
            v["assumptions"][key] = val
    for s in co["scenario_inputs"]:
        if s["name"] == scen:
            s[key] = val


def _rec_year(d, t, i, val):
    _co(d, t)["record"]["years"][i]["roic"] = val


def _sx(d, i, key, val):
    sx = [x for x in d["companies"] if x["model"] == "base_not_established"][0]
    sx["reverse"][i][key] = val


def _sx_base(d, name_has, val):
    sx = [x for x in d["companies"] if x["model"] == "base_not_established"][0]
    for b in sx["earnings_bases"]:
        if name_has in b["name"]:
            b["nopat"] = val


def _best(d, t, scen, val):
    v = [x for x in _co(d, t)["valuations"] if x["scenario"] == scen][0]
    v["best_case_in_scenario"]["value_per_share"] = val


def _set_sx_rev(d, key, val):
    sx = [x for x in d["companies"]
          if x["model"] == "base_not_established"][0]
    sx["revenue"][key] = val


def _sx_add_valuations(d):
    sx = [x for x in d["companies"] if x["model"] == "base_not_established"][0]
    sx["valuations"] = [{"scenario": "낙관", "value_per_share": 200.0}]


def main():
    mutate = "--mutate" in sys.argv
    verbose = "--verbose" in sys.argv
    with open(DATA, encoding="utf-8") as fh:
        raw = fh.read()
    d = json.loads(raw)

    c = verify(d, Checks())
    print(f"검사 {c.passed + len(c.failures)}건 — 통과 {c.passed}, "
          f"실패 {len(c.failures)}")
    for f in c.failures:
        print("  ✗", f)
    if verbose and not c.failures:
        for co in d["companies"]:
            if co["model"] != "applied":
                continue
            vs = {v["scenario"]: v["value_per_share"] for v in co["valuations"]}
            print(f"  {co['korean']}({co['ticker']}) ${co['price']:,.2f} → "
                  f"보수 ${vs['보수']:,.0f} · 중립 ${vs['중립']:,.0f} · "
                  f"낙관 ${vs['낙관']:,.0f}")
    if c.failures:
        return 1

    if mutate:
        print(f"\n변이 검정 {len(MUTATIONS)}건 — 값을 훼손해 검사가 실제로 "
              f"실패하는지 확인")
        survived = []
        for name, mut in MUTATIONS:
            m = json.loads(raw)
            mut(m)
            mc = Checks()
            try:
                verify(m, mc)
            except (SystemExit, KeyError, IndexError, TypeError) as exc:
                print(f"  ✓ {name}: 구조 검사에서 중단 — {type(exc).__name__} {exc}")
                continue
            if mc.failures:
                print(f"  ✓ {name}: {len(mc.failures)}건 실패 "
                      f"— {mc.failures[0][:84]}")
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
