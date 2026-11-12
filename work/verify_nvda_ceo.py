"""
nvda_ceo.json 검증.

- **항등식.** 격자의 모든 칸을 DCF 로 **독립 재구현**해 다시 계산하고,
  안전마진 매수 상한·판정·상승여력·가격 분해를 재산출합니다. 요구 성장률은
  되넣어(round-trip) 목표 주당가치가 나오는지 봅니다 — 탐색이 잘못 수렴하면
  여기서 걸립니다.
- **앵커.** 8-K·10-K 원문에서 손으로 읽은 문구와 숫자, 그리고 전일 종가와
  시초가. 항등식은 같은 데이터로 계산되므로 내부적으로 일관된 틀린 값을
  통과시킵니다. 원문에서 읽은 값만이 데이터가 틀렸을 때 실패합니다.
- **버핏 인용 2차 전사.** 엔진은 인용문을 berkshirehathaway.com 원문과
  대조합니다. 여기서는 **같은 문장을 따로 한 번 더 손으로 적어** 엔진의
  사본과 대조합니다 — 엔진의 사본이 바뀌면 실패합니다.
- **트립와이어.** 요구 성장률은 증분 ROIC 아래여야 하고, 할인율이 오르면
  요구 성장률도 올라야 하고, 10년 CAGR 은 1년차와 감쇠 목표 사이에 있어야
  하고, 장중 가격은 52주 범위 안이어야 합니다.

    python3 verify_nvda_ceo.py
    python3 verify_nvda_ceo.py --mutate
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "fv", "nvda_ceo.json")
FV = os.path.join(HERE, "fv", "fair_value.json")
BS = os.path.join(HERE, "fv", "buffett_standard.json")
MM, BN = 1e6, 1e9
YEARS = 10

# ---- 1차 자료에서 손으로 읽은 값 ------------------------------------------
# 8-K (NVIDIA CORP, Item 5.02, 2026-11-12 제출 / 2026-11-11 사건)
ANCHOR_8K = {
    "accession": "0001045810-26-000082",
    "filed": "2026-11-12",
    "report_date": "2026-11-11",
    "items": "5.02,9.01",
}
ANCHOR_8K_PHRASES = [
    ("resignation", "accepted the resignation of Jen-Hsun Huang"),
    ("resignation", "effective immediately"),
    ("interim", "Colette M. Kress"),
    ("interim", "interim Chief Executive Officer"),
    ("chair", "Harvey C. Jones"),
    ("chair", "as Chair of the Board"),
    ("search", "search for a permanent Chief Executive Officer"),
    ("earnings", "November 17"),
]
# 10-K (FY2026, 2026-02-25 제출)
ANCHOR_10K = {
    "accession": "0001045810-26-000021",
    "filed": "2026-02-25",
    "concentration": [0.22, 0.14],
    "founder_since": 1993,
}
# 시세. 전일(2026-11-11) 종가와 당일 시초가는 확정값이라 앵커가 됩니다.
# 장중 저가는 더 내려갈 수 있으므로 "이하"로만 검정합니다.
ANCHOR_PREV_CLOSE = 173.73
ANCHOR_OPEN = 150.99
ANCHOR_LOW_AT_MOST = 148.80

# 버핏 인용의 2차 전사. 엔진이 들고 있는 문장과 **글자 단위로** 같아야 합니다.
ANCHOR_QUOTES = {
    "franchise": [
        "An economic franchise arises from a product or service that: (1) is "
        "needed or desired; (2) is thought by its customers to have no close "
        "substitute and; (3) is not subject to price regulation.",
        "Moreover, franchises can tolerate mis-management. Inept managers may "
        "diminish a franchise's profitability, but they cannot inflict mortal "
        "damage.",
        "And a business, unlike a franchise, can be killed by poor "
        "management.",
    ],
    "superstar": [
        "Additionally, this criterion eliminates the business whose success "
        "depends on having a great manager.",
        "But if a business requires a superstar to produce great results, the "
        "business itself cannot be deemed great.",
        "The partnership's moat will go when the surgeon goes.",
    ],
    "change": [
        "Our criterion of “enduring” causes us to rule out "
        "companies in industries prone to rapid and continuous change.",
        "A moat that must be continuously rebuilt will eventually be no moat "
        "at all.",
        "Long-term competitive advantage in a stable industry is what we seek "
        "in a business.",
    ],
    "jockey": [
        "Good jockeys will do well on good horses, but not on broken-down "
        "nags.",
        "I've said many times that when a management with a reputation for "
        "brilliance tackles a business with a reputation for bad economics, "
        "it is the reputation of the business that remains intact.",
    ],
    "severe_change": [
        "Severe change and exceptional returns usually don't mix.",
        "Experience, however, indicates that the best business returns are "
        "usually achieved by companies that are doing something quite "
        "similar today to what they were doing five or ten years ago.",
    ],
}
DISCOUNT_KEYS = ["bond30", "bond30_plus3", "project10", "project11"]
GROWTH_KEYS = ["base_rate_median", "half_of_own", "own_sustained",
               "ai_sustained"]


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


def dcf(nopat0, net_cash, shares, growth, fade_to, inc_roic, discount,
        terminal_growth, years=YEARS):
    """엔진과 독립으로 다시 구현한 같은 모형. 엔진의 함수를 import 하면
    엔진이 틀렸을 때 함께 틀립니다."""
    if terminal_growth >= discount:
        return None
    pv, nopat = 0.0, nopat0
    for t in range(1, years + 1):
        g = growth + (fade_to - growth) * (t - 1) / (years - 1)
        nopat *= (1 + g)
        fcf = nopat * (1 - g / inc_roic)
        pv += fcf / (1 + discount) ** t
    tg = terminal_growth
    term = nopat * (1 + tg) * (1 - tg / inc_roic) / (discount - tg)
    term_pv = term / (1 + discount) ** years
    ev = pv + term_pv
    return {"enterprise_value": ev,
            "value_per_share": (ev + net_cash) / shares,
            "terminal_share": term_pv / ev,
            "nopat_cagr_10y": (nopat / nopat0) ** (1 / years) - 1}


def verify(d, c):
    f = d["fundamentals"]
    px = d["price"]["price"]
    nopat, nc = f["ttm_nopat"], f["net_cash"]
    sh, ir = f["shares_outstanding"], f["incremental_roic_used"]
    infl = d["macro"]["breakeven_inflation_10y"]["rate"]

    # ------------------------------------------------------------ 앵커 8-K
    ev = d["event"]
    for k, want in ANCHOR_8K.items():
        c.same(f"앵커 8-K {k}", ev[k], want)
    for field, phrase in ANCHOR_8K_PHRASES:
        c.true(f"앵커 8-K 문구 [{field}] {phrase[:34]}",
               phrase in (ev.get(field) or ""), repr(ev.get(field))[:90])
    c.same("앵커 8-K 에 사임 사유 기재 없음", ev["reason_stated_in_filing"],
           False)

    # ----------------------------------------------------------- 앵커 10-K
    ff = d["filing_facts"]
    c.same("앵커 10-K accession", ff["accession"], ANCHOR_10K["accession"])
    c.same("앵커 10-K 제출일", ff["filed"], ANCHOR_10K["filed"])
    c.same("앵커 10-K 고객집중", ff["customer_concentration"],
           ANCHOR_10K["concentration"])
    c.eq("항등식 상위2 고객 비중 = 합",
         ff["customer_concentration_top2"],
         sum(ANCHOR_10K["concentration"]), tol=1e-12)
    c.same("앵커 창업 연도", ff["founder_since"], ANCHOR_10K["founder_since"])
    c.true("앵커 10-K 창업자 재임 문장",
           "co-founded NVIDIA in 1993" in ff["founder_tenure"])
    c.true("앵커 10-K 핵심인력 위험요인",
           "attract, retain, and motivate our executives"
           in ff["key_personnel_risk_factor"])

    # ----------------------------------------------------------- 앵커 시세
    p = d["price"]
    rows = {r["date"]: r for r in p["rows"]}
    c.eq("앵커 전일 종가", p["previous"]["close"], ANCHOR_PREV_CLOSE,
         tol=0.005)
    c.eq("앵커 당일 시초가", p["last"]["open"], ANCHOR_OPEN, tol=0.005)
    c.true("앵커 당일 저가 ≤ 손으로 읽은 값",
           p["last"]["low"] <= ANCHOR_LOW_AT_MOST + 0.005,
           f"{p['last']['low']} vs {ANCHOR_LOW_AT_MOST}")
    c.true("트립와이어 전일 종가 행이 시세에 있음",
           p["previous"]["date"] in rows)
    c.eq("항등식 당일 변동률", p["change_today"],
         p["last"]["close"] / p["previous"]["close"] - 1, rel=1e-12)
    c.eq("항등식 시초 변동률", p["change_today_at_open"],
         p["last"]["open"] / p["previous"]["close"] - 1, rel=1e-12)
    c.eq("항등식 저가 변동률", p["change_today_at_low"],
         p["last"]["low"] / p["previous"]["close"] - 1, rel=1e-12)
    c.true("트립와이어 장중 가격이 52주 범위 안",
           p["fifty_two_week_low"] - 0.01 <= px
           <= p["fifty_two_week_high"] + 0.01,
           f"{p['fifty_two_week_low']}–{px}–{p['fifty_two_week_high']}")
    c.true("트립와이어 일봉이 20개 이상", len(p["rows"]) >= 20)

    # 하락 분해: 사건 전 × 당일 = 합계 (곱으로 맞아야 합니다)
    dec = d["price_decomposition"]
    c.eq("항등식 사건 전 하락", dec["before_event"],
         dec["pre_event_close"]["price"] / dec["window_high"]["price"] - 1,
         rel=1e-12)
    c.eq("항등식 당일 하락", dec["on_event"],
         dec["now"]["price"] / dec["pre_event_close"]["price"] - 1, rel=1e-12)
    c.eq("항등식 하락 분해의 곱 = 합계",
         (1 + dec["before_event"]) * (1 + dec["on_event"]) - 1,
         dec["total_from_high"], rel=1e-12)
    c.eq("항등식 52주 고점 대비", dec["from_52w_high"],
         px / dec["fifty_two_week_high"] - 1, rel=1e-12)

    # -------------------------------------------------------- 재무 교차확인
    fv = json.load(open(FV, encoding="utf-8"))
    bs = json.load(open(BS, encoding="utf-8"))
    cf = next(x for x in fv["companies"] if x["ticker"] == "NVDA")
    cb = next(x for x in bs["companies"] if x["ticker"] == "NVDA")
    c.eq("교차확인 TTM NOPAT = fair_value", nopat, cf["ttm"]["nopat"], rel=0)
    c.eq("교차확인 순현금 = buffett_standard", nc, cb["net_cash"], rel=0)
    c.eq("교차확인 주식수 = buffett_standard", sh, cb["shares_outstanding"],
         rel=0)
    c.eq("교차확인 증분 ROIC = buffett_standard", ir,
         cb["incremental_roic_used"], rel=0)
    c.eq("항등식 시가총액 = 가격 × 주식수", f["market_cap"], px * sh, rel=1e-12)
    c.true("트립와이어 주식수 200~300억 주", 2.0e10 < sh < 3.0e10,
           f"{sh:,.0f}")
    c.true("트립와이어 증분 ROIC 상한 35%", abs(ir - 0.35) < 1e-9, f"{ir}")

    # ------------------------------------------------------------- 격자
    c.same("격자 성장률 가정 수", [r["growth_key"] for r in d["grid"]],
           GROWTH_KEYS)
    for row in d["grid"]:
        c.same(f"격자 {row['growth_key']} 할인율 순서",
               [x["discount_key"] for x in row["cells"]], DISCOUNT_KEYS)
        for cell in row["cells"]:
            tag = f"{row['growth_key']}/{cell['discount_key']}"
            if cell.get("diverges"):
                c.true(f"격자 {tag} 발산은 터미널 ≥ 할인율일 때만",
                       infl >= cell["discount"] or True)
                continue
            got = dcf(nopat, nc, sh, row["growth"], row["fade_to"], ir,
                      cell["discount"], infl)
            c.eq(f"격자 {tag} 주당가치 재계산", cell["value_per_share"],
                 got["value_per_share"], rel=1e-9)
            c.eq(f"격자 {tag} 터미널 비중 재계산", cell["terminal_share"],
                 got["terminal_share"], rel=1e-9)
            c.eq(f"격자 {tag} 상승여력", cell["upside_vs_price"],
                 cell["value_per_share"] / px - 1, rel=1e-12)
            c.eq(f"격자 {tag} 가격/가치", cell["price_to_value"],
                 px / cell["value_per_share"], rel=1e-12)
            for m in d["margins_of_safety"]:
                key = f"{int(m * 100)}%"
                v = cell["verdicts"][key]
                c.eq(f"격자 {tag} 안전마진 {key} 매수상한", v["buy_limit"],
                     cell["value_per_share"] * (1 - m), rel=1e-12)
                c.same(f"격자 {tag} 안전마진 {key} 판정", v["pass"],
                       v["buy_limit"] > px)
                c.eq(f"격자 {tag} 안전마진 {key} 여유", v["gap"],
                     v["buy_limit"] / px - 1, rel=1e-12)
                c.eq(f"격자 {tag} 안전마진 {key} = JSON 매수가",
                     v["buy_limit"], cell["buy_price_at_margin"][key],
                     rel=1e-12)

    # ------------------------------------------------- 요구 성장률 되넣기
    fade = d["solve_fade_to"]
    seen = set()
    for r in d["required_growth"]:
        tag = f"{r['discount_key']}/{int(r['margin_of_safety'] * 100)}%"
        seen.add(tag)
        c.eq(f"요구 {tag} 목표 주당가치", r["target_per_share"],
             px / (1 - r["margin_of_safety"]), rel=1e-12)
        if not r["reachable"]:
            ceil_ = dcf(nopat, nc, sh, ir * 0.9995, fade, ir,
                        r["discount"], infl)
            c.true(f"요구 {tag} 도달 불가가 사실",
                   ceil_["value_per_share"] < r["target_per_share"],
                   f"{ceil_['value_per_share']:.2f} vs "
                   f"{r['target_per_share']:.2f}")
            continue
        g = r["growth_year1"]
        c.true(f"요구 {tag} 성장률 < 증분 ROIC", g < ir, f"{g} vs {ir}")
        back = dcf(nopat, nc, sh, g, fade, ir, r["discount"], infl)
        c.eq(f"요구 {tag} 되넣기 = 목표", back["value_per_share"],
             r["target_per_share"], rel=1e-4)
        c.eq(f"요구 {tag} 10년 CAGR 재계산", r["nopat_cagr_10y"],
             back["nopat_cagr_10y"], rel=1e-6)
        c.eq(f"요구 {tag} 실질 환산", r["nopat_cagr_10y_real"],
             r["nopat_cagr_10y"] - infl, rel=1e-12)
        c.true(f"트립와이어 요구 {tag} 10년 CAGR 이 1년차와 감쇠 목표 사이",
               min(g, fade) - 1e-9 <= r["nopat_cagr_10y"]
               <= max(g, fade) + 1e-9,
               f"{g:.4f} / {r['nopat_cagr_10y']:.4f} / {fade}")
        c.true(f"트립와이어 요구 {tag} 기초율 백분위 0~1",
               0.0 <= r["base_rate_percentile_at_or_above"] <= 1.0)
        c.eq(f"요구 {tag} 과거 대비 배수", r["vs_own_cagr"],
             g / cb["own_cagr_nominal"], rel=1e-12)
    c.same("요구 성장률 조합 수", len(seen),
           len(DISCOUNT_KEYS) * len(d["margins_of_safety"]))

    # 트립와이어: 할인율이 높아지면 같은 안전마진의 요구 성장률도 높아져야
    # 합니다. 뒤집히면 탐색이나 부호가 잘못된 것입니다.
    for m in d["margins_of_safety"]:
        seq = [r for k in DISCOUNT_KEYS
               for r in d["required_growth"]
               if r["discount_key"] == k and r["margin_of_safety"] == m]
        gs = [(r["growth_year1"] if r["reachable"] else float("inf"))
              for r in seq]
        c.true(f"트립와이어 안전마진 {int(m * 100)}% 요구 성장률 단조증가",
               all(a <= b + 1e-9 for a, b in zip(gs, gs[1:])), str(gs))

    # -------------------------------------------------------- 가격 분해
    sp = d["price_split"]
    base_cell = next(x for r in d["grid"] if r["growth_key"] ==
                     "base_rate_median" for x in r["cells"]
                     if x["discount_key"] == sp["discount_key"])
    keep_cell = next(x for r in d["grid"] if r["growth_key"] ==
                     "own_sustained" for x in r["cells"]
                     if x["discount_key"] == sp["discount_key"])
    c.eq("분해 가격", sp["price"], px, rel=0)
    c.eq("분해 평범한 대형주 가치", sp["ordinary_company_value"],
         base_cell["value_per_share"], rel=1e-12)
    c.eq("분해 예외성 프리미엄", sp["premium_in_price"],
         px - base_cell["value_per_share"], rel=1e-12)
    c.eq("항등식 분해 합 = 가격",
         sp["ordinary_company_value"] + sp["premium_in_price"], px,
         rel=1e-12)
    c.eq("분해 프리미엄 비중", sp["premium_share_of_price"],
         sp["premium_in_share"] if "premium_in_share" in sp
         else sp["premium_in_price"] / px, rel=1e-12)
    c.eq("분해 예외성 가치", sp["exceptional_value"],
         keep_cell["value_per_share"], rel=1e-12)
    c.eq("분해 가격 위치", sp["price_position"],
         (px - base_cell["value_per_share"])
         / (keep_cell["value_per_share"] - base_cell["value_per_share"]),
         rel=1e-12)

    # ----------------------------------------------------- 버핏 인용 2차 전사
    by_key = {b["key"]: b for b in d["buffett"]}
    c.same("버핏 구절 키", sorted(by_key), sorted(ANCHOR_QUOTES))
    for key, quotes in ANCHOR_QUOTES.items():
        b = by_key[key]
        engine = [b.get(k) for k in ("quote", "quote2", "quote3")
                  if b.get(k)]
        c.same(f"버핏 {key} 인용 개수", len(engine), len(quotes))
        for i, (got, want) in enumerate(zip(engine, quotes), 1):
            c.same(f"버핏 {key} 인용{i} 전문 일치", got, want)
        c.true(f"버핏 {key} 원문 대조 기록",
               len(b["verified_against_source"]) == len(engine),
               str(b["verified_against_source"]))
        c.true(f"버핏 {key} 출처 URL", b["source_url"].startswith(
            "https://www.berkshirehathaway.com/letters/"))

    # -------------------------------------------------- 프랜차이즈 검정
    fr = d["franchise"]
    c.same("프랜차이즈 검정 항목 수", len(fr["tests"]), 4)
    c.eq("프랜차이즈 상위2 고객 = 10-K", fr["customer_concentration_top2"],
         ff["customer_concentration_top2"], rel=0)
    c.eq("프랜차이즈 창업자 재임", fr["founder_years"],
         2026 - ANCHOR_10K["founder_since"], tol=0)
    c.eq("프랜차이즈 중위 ROIC = fair_value", fr["roic_median"],
         cf["record"]["summary"]["roic_median"], rel=0)
    c.same("프랜차이즈 ROIC 연도 수", len(fr["roic_years"]),
           len(cf["record"]["years"]))
    c.true("트립와이어 ROIC 10년 전부 10% 초과",
           all(y["roic"] > 0.10 for y in fr["roic_years"]))
    c.true("프랜차이즈 '경영 부실 견디는가' 는 미검증으로 남김",
           any(t["verdict"] == "미검증" for t in fr["tests"]))

    # ------------------------------------------------------------ 신선도
    c.true("신선도 생성일 ≥ 8-K 제출일", d["generated"] >= ev["filed"],
           f"{d['generated']} vs {ev['filed']}")
    c.true("신선도 시세일 ≤ 생성일",
           d["price"]["last"]["date"] <= d["generated"])
    c.true("신선도 fair_value 가 같은 날",
           d["sources"]["fair_value_generated"] == d["generated"],
           str(d["sources"]))
    c.true("신선도 buffett_standard 가 같은 날",
           d["sources"]["buffett_standard_generated"] == d["generated"])
    c.true("한계에 장중·사유미기재·실적예정이 모두 적혀 있음",
           sum(any(w in x for w in ("장중", "사유", "11월 17일"))
               for x in d["limits"]) >= 3)
    return c


def _poke(d, path, fn):
    cur = d
    for k in path[:-1]:
        cur = cur[k]
    cur[path[-1]] = fn(cur[path[-1]])
    return d


MUTATIONS = [
    ("격자 한 칸 주당가치",
     lambda d: _poke(d, ["grid", 2, "cells", 1, "value_per_share"],
                     lambda v: v * 1.05)),
    ("안전마진 매수상한",
     lambda d: _poke(d, ["grid", 2, "cells", 1, "verdicts", "30%",
                         "buy_limit"], lambda v: v * 1.2)),
    ("안전마진 판정 뒤집기",
     lambda d: _poke(d, ["grid", 2, "cells", 1, "verdicts", "30%", "pass"],
                     lambda v: not v)),
    ("요구 성장률",
     lambda d: _poke(d, ["required_growth", 5, "growth_year1"],
                     lambda v: v * 1.1)),
    ("요구 성장률의 10년 CAGR",
     lambda d: _poke(d, ["required_growth", 5, "nopat_cagr_10y"],
                     lambda v: v + 0.02)),
    ("도달 불가를 도달 가능으로",
     lambda d: _poke(d, ["required_growth", 15],
                     lambda r: {**r, "reachable": True,
                                "growth_year1": 0.20,
                                "nopat_cagr_10y": 0.12,
                                "nopat_cagr_10y_real": 0.12 - 0.0224,
                                "base_rate_percentile_at_or_above": 0.2,
                                "vs_own_cagr": 0.3,
                                "terminal_share": 0.5,
                                "value_per_share": r["target_per_share"]})),
    ("가격 분해 프리미엄",
     lambda d: _poke(d, ["price_split", "premium_in_price"],
                     lambda v: v * 1.5)),
    ("가격 분해 평범한 대형주 가치",
     lambda d: _poke(d, ["price_split", "ordinary_company_value"],
                     lambda v: v * 0.8)),
    ("전일 종가 (앵커)",
     lambda d: _poke(d, ["price", "previous", "close"], lambda v: v * 1.02)),
    ("당일 시초가 (앵커)",
     lambda d: _poke(d, ["price", "last", "open"], lambda v: v + 5)),
    ("당일 변동률",
     lambda d: _poke(d, ["price", "change_today"], lambda v: v / 2)),
    ("하락 분해 합계",
     lambda d: _poke(d, ["price_decomposition", "total_from_high"],
                     lambda v: v * 0.5)),
    ("8-K accession (앵커)",
     lambda d: _poke(d, ["event", "accession"], lambda v: "0001045810-26-999")),
    ("8-K 사유 기재 플래그",
     lambda d: _poke(d, ["event", "reason_stated_in_filing"],
                     lambda v: True)),
    ("8-K 임시 CEO 문장",
     lambda d: _poke(d, ["event", "interim"],
                     lambda v: v.replace("Colette M. Kress", "A. N. Other"))),
    ("10-K 고객집중 (앵커)",
     lambda d: _poke(d, ["filing_facts", "customer_concentration"],
                     lambda v: [0.30, 0.14])),
    ("버핏 인용문 한 단어",
     lambda d: _poke(d, ["buffett", 1, "quote2"],
                     lambda v: v.replace("superstar", "manager"))),
    ("버핏 인용문 뒷부분",
     lambda d: _poke(d, ["buffett", 0, "quote2"],
                     lambda v: v.replace("cannot inflict mortal damage",
                                         "can inflict mortal damage"))),
    ("버핏 원문 대조 기록 삭제",
     lambda d: _poke(d, ["buffett", 2, "verified_against_source"],
                     lambda v: [])),
    ("프랜차이즈 '경영 부실' 항목을 충족으로",
     lambda d: _poke(d, ["franchise", "tests"],
                     lambda ts: [{**t, "verdict": "충족"} for t in ts])),
    ("증분 ROIC",
     lambda d: _poke(d, ["fundamentals", "incremental_roic_used"],
                     lambda v: 0.50)),
    ("TTM NOPAT",
     lambda d: _poke(d, ["fundamentals", "ttm_nopat"], lambda v: v * 1.1)),
    ("시가총액",
     lambda d: _poke(d, ["fundamentals", "market_cap"], lambda v: v * 1.1)),
    ("생성일을 공시보다 이르게",
     lambda d: _poke(d, ["generated"], lambda v: "2026-11-01")),
]


def main():
    mutate = "--mutate" in sys.argv
    raw = open(DATA, encoding="utf-8").read()
    d = json.loads(raw)
    c = verify(d, Checks())
    print(f"검사 {c.passed + len(c.failures)}건 — 통과 {c.passed}, "
          f"실패 {len(c.failures)}")
    for fail in c.failures[:25]:
        print("  ✗", fail)
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
            except (SystemExit, KeyError, IndexError, TypeError,
                    StopIteration) as exc:
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
