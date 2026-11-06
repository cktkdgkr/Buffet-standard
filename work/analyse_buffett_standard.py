"""
성장률 가정을 객관 자료로 검증하고, 버핏의 실제 기준으로 적정주가를 다시 냅니다.

제기된 의문: "AI 발 성장이 예상되는 업계인데 10년차 성장률 3.5%는 너무 낮지
않은가. 세 기업은 지난 10년간 10% 넘게 성장해 왔다."

**먼저 제 보고서의 오해를 유발한 표현을 바로잡습니다.** 3.5%는 "10년간
성장률"이 아니라 10년차 한 해의 성장률이고, 중립 시나리오가 실제로 가정한
10년 평균(NOPAT CAGR)은 6.6~9.2%, 낙관은 11.9~14.6%입니다. 그래도 "이 가정이
객관적인가"는 유효한 질문이므로 세 가지 외부 기준으로 재검증합니다.

1. **기초율** — Credit Suisse HOLT 의 Base Rate Book (Mauboussin·Callahan·
   Majd, 2016-09-26) Exhibit 4. 1950~2015년, 규모별로 1·3·5·10년 성장률 분포.
   매출 $50십억 초과 기업의 10년 성장률이 우리 세 기업의 참조군입니다.
   **이 수치는 전부 인플레이션 조정(실질)입니다** — 문서가 두 곳에서 명시하고
   있고, 명목 가정과 비교하려면 인플레이션을 더해야 합니다.
2. **거시 기준** — 30년·10년 국채 수익률과 시장이 기대하는 10년 인플레이션
   (10년 BEI). 영구성장률의 상한이 여기서 나옵니다.
3. **버핏의 실제 기준** — 1992년 주주서한(할인 공식과 "증분 수익률" 조건),
   1994년 주주총회 발언(국채 7%일 때 최소 10%로 할인), 2007년 주주총회
   (형식적 할인율을 쓰지 않으며 국채보다 "significantly higher"를 요구,
   안전마진으로 위험을 처리).

그 위에서 **성장률 가정 × 할인율**의 격자로 주당 가치를 냅니다. 하나의
"정답"을 내지 않는 이유는 어느 칸이 맞는지가 가정의 문제이기 때문이고,
격자는 각 가정이 결론을 얼마나 움직이는지를 보여 줍니다.

    python3 analyse_buffett_standard.py
    python3 analyse_buffett_standard.py --refresh
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FV = os.path.join(HERE, "fv", "fair_value.json")
OUT = os.path.join(HERE, "fv", "buffett_standard.json")
MACRO_CACHE = os.path.join(HERE, "fv", "macro")
MM, BN = 1e6, 1e9
YEARS = 10

UA = {"User-Agent": "Mozilla/5.0 (compatible; portfolio-research/1.0)"}
YIELD_SERIES = {
    "treasury_30y": ("%5ETYX", "30년 미국 국채 수익률"),
    "treasury_10y": ("%5ETNX", "10년 미국 국채 수익률"),
}

# Credit Suisse HOLT, Base Rate Book (Mauboussin, Callahan, Majd),
# 2016-09-26, Exhibit 4. 1950~2015년. 참조군은 "매출 $50,000백만 초과"이고,
# 우리 세 기업의 TTM 매출(마이크로소프트 346·알파벳 471·엔비디아 303십억
# 달러)이 모두 그 위이므로 이 칸이 맞는 참조군입니다.
#
# **실질 기준입니다.** 문서: "Bear in mind that these data are adjusted for
# inflation and that most forecasts reflect inflation expectations."
# 그래서 명목 가정과 비교할 때는 인플레이션 기대치를 더합니다.
BASE_RATES = {
    "source": ("Credit Suisse HOLT, \"The Base Rate Book\" "
               "(Mauboussin·Callahan·Majd), 2016-09-26, Exhibit 4"),
    "source_url": ("https://sorfis.com/wp-content/uploads/2021/09/"
                   "The-Base-Rate-Book-Integrating-the-Past-to-Better-"
                   "Anticipate-the-Future-September-2016.pdf"),
    "period": "1950-2015",
    "reference_class": "매출 $50,000백만 초과 (Mega)",
    "real_terms": True,
    "real_terms_note": ("문서 명시: \"these data are adjusted for inflation\". "
                        "명목 가정과 비교하려면 인플레이션 기대치를 더해야 "
                        "합니다."),
    "survivorship_note": ("문서 명시: 각 표본은 그 기간을 생존한 기업만 "
                          "포함합니다(10년 표본은 10년 생존). 상장 기업의 약 "
                          "절반이 10년 안에 사라집니다 — 즉 이 기초율은 "
                          "위쪽으로 치우쳐 있습니다."),
    # 10년 순이익 CAGR 분포 (실질). 구간은 10%포인트 폭.
    "net_income_10y": {
        "bands": [("<-50", 0.000), ("-50~-40", 0.000), ("-40~-30", 0.002),
                  ("-30~-20", 0.019), ("-20~-10", 0.062), ("-10~0", 0.276),
                  ("0~10", 0.417), ("10~20", 0.141), ("20~30", 0.061),
                  ("30~40", 0.019), ("40~50", 0.002), ("50~60", 0.001),
                  ("60~70", 0.000), ("70~80", 0.000), ("80~90", 0.000),
                  (">90", 0.000)],
        "mean": 0.038, "median": 0.033, "stdev": 0.112,
    },
    # 10년 매출 CAGR 분포 (실질). 구간은 5%포인트 폭.
    "sales_10y": {
        "bands": [("<-25", 0.000), ("-25~-20", 0.003), ("-20~-15", 0.010),
                  ("-15~-10", 0.031), ("-10~-5", 0.098), ("-5~0", 0.269),
                  ("0~5", 0.378), ("5~10", 0.172), ("10~15", 0.030),
                  ("15~20", 0.009), ("20~25", 0.000), ("25~30", 0.000),
                  ("30~35", 0.000), ("35~40", 0.000), ("40~45", 0.000),
                  (">45", 0.000)],
        "mean": 0.008, "median": 0.011, "stdev": 0.058,
    },
    "gdp_real_1950_2015": 0.032,
    "gdp_note": ("문서: \"From 1950-2015, U.S. GDP grew at 3.2 percent per "
                 "year, adjusted for inflation\". 매출 성장률과 GDP 성장률의 "
                 "상관계수는 0.66."),
}

# 버핏의 기준. 전부 1차 또는 1차에 가까운 출처이고, 해석이 섞인 곳은
# 해석이라고 적어 둡니다.
BUFFETT = [
    {"year": 1992, "kind": "주주서한 (1차)",
     "url": "https://www.berkshirehathaway.com/letters/1992.html",
     "quote": ("The value of any stock, bond or business today is determined "
               "by the cash inflows and outflows — discounted at an "
               "appropriate interest rate — that can be expected to occur "
               "during the remaining life of the asset."),
     "note": ("할인 공식 자체는 우리 모형과 같습니다. 다만 \"appropriate "
              "interest rate\"가 무엇인지는 이 서한에 없습니다.")},
    {"year": 1992, "kind": "주주서한 (1차)",
     "url": "https://www.berkshirehathaway.com/letters/1992.html",
     "quote": ("Growth benefits investors only when the business in point "
               "can invest at incremental returns that are enticing — in "
               "other words, only when each dollar used to finance the "
               "growth creates over a dollar of long-term market value."),
     "note": ("우리 모형의 잉여현금 = NOPAT × (1 − 성장률 ÷ 증분ROIC) 가 "
              "바로 이 문장의 수식입니다. 증분 ROIC을 넣는 것이 버핏 "
              "기준에서 벗어난 장치가 아니라, 그 기준 자체입니다.")},
    {"year": 1994, "kind": "주주총회 발언 (2차 인용)",
     "url": ("https://finance.yahoo.com/news/"
             "warren-buffetts-3-discount-rate-152235624.html"),
     "quote": ("I would say that in a world of 7% long-term bond rates we "
               "would certainly want to think we were discounting future "
               "after-tax streams of cash at least a 10% rate. But that "
               "will depend on the certainty we feel about the business."),
     "note": ("국채 7%일 때 최소 10% — 스프레드 3%포인트. **3%포인트라는 "
              "규칙은 버핏이 말한 것이 아니라 인용자(GuruFocus/Hargreaves)의 "
              "해석입니다.** 다만 '국채 + 얼마'라는 구조는 버핏의 말 "
              "자체입니다.")},
    {"year": 2007, "kind": "주주총회 발언 (2차 전사)",
     "url": ("https://www.good-investing.net/berkshire-hathaway-"
             "annual-meeting/transcripts/2007-transcript/"),
     "quote": ("If government bond rates were 2 percent, we're not going to "
               "buy a business to earn 3 or 3 ½ percent expectancy over the "
               "years. … we don't formally have discount rates."),
     "note": ("형식적 할인율을 쓰지 않고, 국채보다 \"significantly higher\"를 "
              "요구합니다. 같은 자리에서 국채가 \"4 and 3/4%\"라고 말했는데, "
              "오늘 10년 국채가 그와 거의 같은 수준입니다.")},
    {"year": 2007, "kind": "주주총회 발언 (2차 전사)",
     "url": ("https://www.good-investing.net/berkshire-hathaway-"
             "annual-meeting/transcripts/2007-transcript/"),
     "quote": ("we'd love to find them when they're selling at 40 cents on "
               "the dollar … [but we usually pay] much closer to a dollar "
               "on the dollar."),
     "note": ("위험을 할인율에 얹지 않고 **안전마진**으로 처리합니다. 그래서 "
              "버핏 기준으로 계산한 가치는 '살 가격'이 아니라 '그보다 얼마나 "
              "싸게 사야 하는가'의 출발점입니다.")},
]

MARGIN_OF_SAFETY = [0.0, 0.20, 0.30, 0.40]
# 성장률 상한. 모형이 폭발하지 않게 하기 위한 장치이고, 네 가정 전부에
# 똑같이 적용합니다. 본문 보고서의 낙관 시나리오 상한과 같은 값입니다.
CAP = 0.25


def fetch_yield(symbol, label, refresh):
    """국채 수익률. FRED 가 프록시를 통과하지 못해 시세 경로를 씁니다."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?range=5d&interval=1d")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as fh:
        d = json.load(fh)
    m = d["chart"]["result"][0]["meta"]
    v = m.get("regularMarketPrice")
    if v is None or not 0 < v < 25:
        raise SystemExit(f"{label}: 수익률 {v!r} — 범위를 벗어났습니다")
    return {"label": label, "symbol": m.get("symbol"), "percent": v,
            "rate": v / 100.0,
            "as_of_utc": datetime.fromtimestamp(
                m["regularMarketTime"], tz=timezone.utc).isoformat()
            if m.get("regularMarketTime") else None,
            "source_url": url}


def dcf(base_nopat, net_cash, shares, growth, fade_to, inc_roic,
        discount, terminal_growth, years=YEARS):
    """
    보고서 본문과 똑같은 모형입니다. 가정만 바꿔 끼웁니다.

    성장률이 할인율을 넘어도 폭발하지 않습니다 — 명시 기간은 유한하고,
    터미널은 터미널 성장률(할인율보다 낮음)을 씁니다. 다만 **터미널 성장률이
    할인율 이상이면 발산**하므로 그때는 계산하지 않고 그 사실을 돌려줍니다.
    """
    if terminal_growth >= discount:
        return {"diverges": True,
                "why": (f"터미널 성장률 {terminal_growth:.2%} ≥ 할인율 "
                        f"{discount:.2%} — 영구가치가 무한이 되어 계산할 수 "
                        f"없습니다. 이것 자체가 정보입니다: 국채 수익률만으로 "
                        f"주식을 할인하면서 명목 GDP 속도의 영구성장을 "
                        f"가정하면 어떤 가격도 정당화됩니다.")}
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
    return {"diverges": False, "projection": proj,
            "pv_of_forecast": pv, "pv_of_terminal": term_pv,
            "terminal_share": term_pv / ev if ev else None,
            "enterprise_value": ev, "equity_value": eq,
            "value_per_share": eq / shares,
            "nopat_cagr_10y": (proj[-1]["nopat"] / base_nopat)
            ** (1 / years) - 1}


def percentile_of(bands, value):
    """
    기초율 분포에서 value 이상이 나올 확률.

    구간 경계는 라벨에서 읽습니다. value 가 구간 안에 걸치면 그 구간을
    선형으로 나눕니다 — 구간 폭이 10%포인트나 되므로 경계로만 세면
    오차가 큽니다.
    """
    def bounds(lab):
        if lab.startswith("<"):
            return (-999.0, float(lab[1:]) / 100.0)
        if lab.startswith(">"):
            return (float(lab[1:]) / 100.0, 999.0)
        lo, hi = lab.split("~")
        return (float(lo) / 100.0, float(hi) / 100.0)

    above = 0.0
    for lab, share in bands:
        lo, hi = bounds(lab)
        if value <= lo:
            above += share
        elif value < hi:
            # 구간 안: 위쪽 부분만 센다.
            above += share * (hi - value) / (hi - lo)
    return above


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.parse_args()
    print(f"오늘 {date.today().isoformat()} 기준")
    os.makedirs(MACRO_CACHE, exist_ok=True)
    fv = json.load(open(FV, encoding="utf-8"))
    applied = [c for c in fv["companies"] if c["model"] == "applied"]

    # ------------------------------------------------------------ 거시 기준
    macro = {}
    for key, (sym, label) in YIELD_SERIES.items():
        macro[key] = fetch_yield(sym, label, True)
        print(f"  {label}: {macro[key]['percent']:.3f}%")
    # 시장이 기대하는 10년 인플레이션. FRED 페이지에서 읽은 값을 고정해
    # 두고 출처와 날짜를 함께 적습니다 — 프록시가 FRED CSV 를 막습니다.
    macro["breakeven_inflation_10y"] = {
        "label": "10년 기대인플레이션 (10-Year Breakeven Inflation Rate)",
        "series": "FRED T10YIE", "percent": 2.24, "rate": 0.0224,
        "as_of": "2026-11-05",
        "source_url": "https://fred.stlouisfed.org/series/T10YIE",
        "note": "시장가격에서 유도된 기대치입니다 — 제 전망이 아닙니다.",
    }
    infl = macro["breakeven_inflation_10y"]["rate"]
    macro["nominal_gdp_long_run"] = {
        "label": "장기 명목 GDP 성장률 (추정)",
        "rate": BASE_RATES["gdp_real_1950_2015"] + infl,
        "note": (f"실질 {BASE_RATES['gdp_real_1950_2015']:.1%}"
                 f"(1950–2015, Base Rate Book) + 기대인플레이션 "
                 f"{infl:.2%}. 영구성장률의 상한입니다 — 어떤 기업도 "
                 f"경제보다 빠르게 영구히 성장할 수 없습니다."),
    }
    print(f"  10년 기대인플레이션: {infl:.2%} (FRED T10YIE, 2026-11-05)")
    print(f"  장기 명목 GDP(추정): "
          f"{macro['nominal_gdp_long_run']['rate']:.2%}")

    # --------------------------------------------------------- 할인율 후보
    r30 = macro["treasury_30y"]["rate"]
    r10 = macro["treasury_10y"]["rate"]
    DISCOUNTS = [
        {"key": "bond30", "rate": r30,
         "label": f"30년 국채 {r30:.2%}",
         "basis": ("버핏을 문자 그대로 — 장기 국채 수익률로 할인하고 위험은 "
                   "안전마진으로 처리. 1996년 \"국채에 큰 프리미엄을 "
                   "얹는 것은 말이 안 된다\"는 취지의 발언에 해당합니다.")},
        {"key": "bond30_plus3", "rate": r30 + 0.03,
         "label": f"30년 국채 + 3%p = {r30 + 0.03:.2%}",
         "basis": ("1994년 발언(국채 7% → 최소 10%)에서 유도한 스프레드. "
                   "**3%포인트는 인용자의 해석이고 버핏의 규칙이 "
                   "아닙니다.** 다만 2007년에 국채가 4¾%일 때 "
                   "\"significantly higher\"를 요구했다는 발언과 방향이 "
                   "같습니다.")},
        {"key": "project10", "rate": 0.10,
         "label": "프로젝트 기준 10%",
         "basis": ("50개사 ROIC 문턱과 같은 값. 기업 간 비교를 위해 고정한 "
                   "요구수익률입니다.")},
        {"key": "project11", "rate": 0.11,
         "label": "프로젝트 보수 11%",
         "basis": "보수 시나리오에 쓴 할인율."},
    ]

    # --------------------------------------------- 성장률 가정 후보 (기업별)
    def growth_options(co):
        own = co["record"]["operating_income_cagr"]
        med_nom = BASE_RATES["net_income_10y"]["median"] + infl
        return [
            {"key": "base_rate_median", "growth": med_nom,
             "fade_to": infl,
             "label": f"기초율 중위 {med_nom:.1%}",
             "basis": (f"매출 $50십억 초과 기업의 10년 순이익 CAGR 중위값 "
                       f"{BASE_RATES['net_income_10y']['median']:.1%}(실질) + "
                       f"기대인플레이션 {infl:.2%}. 즉 \"이 규모 기업의 "
                       f"역사적 중앙값만큼\" 성장한다는 가정.")},
            # 상한 25%는 네 가정 전부에 똑같이 적용합니다. 한쪽만 씌우면
            # 엔비디아에서 "과거의 절반"(33.8%)이 "과거 유지"(25%)보다
            # 높아져 라벨과 값이 어긋납니다 — 실제로 그렇게 나왔습니다.
            {"key": "half_of_own", "growth": min(own / 2, CAP),
             "fade_to": 0.035,
             "label": (f"과거의 절반 {min(own / 2, CAP):.1%}"
                       + (f" (원값 {own / 2:.1%}, 상한 {CAP:.0%})"
                          if own / 2 > CAP else "")),
             "basis": (f"자기 10년 영업이익 CAGR {own:.1%}의 절반"
                       + (f" = {own / 2:.1%}이지만 상한 {CAP:.0%}을 "
                          f"적용했습니다."
                          if own / 2 > CAP
                          else ". 본문 중립 시나리오와 같은 규칙입니다."))},
            {"key": "own_sustained", "growth": min(own, CAP),
             "fade_to": 0.045,
             "label": (f"과거 유지 {min(own, CAP):.1%}"
                       + (f" (원값 {own:.1%}, 상한 {CAP:.0%})"
                          if own > CAP else "")),
             "basis": (f"자기 10년 CAGR {own:.1%}이 그대로 이어진다는 가정 — "
                       f"제기된 의문이 정확히 이것입니다."
                       + (f" 원값 {own:.1%}은 상한 {CAP:.0%}으로 깎였습니다. "
                          f"상한 없이 돌리면 1년차 영업이익이 "
                          f"{(1 + own):.2f}배가 되어 10년 뒤 전 세계 "
                          f"이익보다 커집니다." if own > CAP else ""))},
            {"key": "ai_sustained", "growth": min(own, CAP),
             "fade_to": 0.08,
             "label": f"AI 가속 {min(own, CAP):.1%} → 10년차 8%",
             "basis": ("과거 속도로 시작하되 **감쇠를 거의 하지 않는** 가정. "
                       "10년차에도 8%로 성장합니다. AI 로 성장이 장기화된다는 "
                       "주장을 가장 후하게 반영한 경우입니다.")},
        ]

    TERMINALS = [
        {"key": "inflation", "rate": infl,
         "label": f"기대인플레이션 {infl:.2%}",
         "basis": "실질 영구성장 0%. 표준적인 보수 가정입니다."},
        {"key": "half_gdp", "rate": infl + BASE_RATES["gdp_real_1950_2015"] / 2,
         "label": f"인플레 + 실질 1.6% = "
                  f"{infl + BASE_RATES['gdp_real_1950_2015'] / 2:.2%}",
         "basis": "경제의 절반 속도로 영구히 성장."},
        {"key": "nominal_gdp", "rate": macro["nominal_gdp_long_run"]["rate"],
         "label": f"명목 GDP {macro['nominal_gdp_long_run']['rate']:.2%}",
         "basis": ("경제와 같은 속도로 영구히. 이보다 높게 두면 기업이 "
                   "결국 경제 전체가 됩니다 — 상한입니다.")},
    ]

    out = {"generated": date.today().isoformat(),
           "question": ("10년차 성장률 3.5%가 너무 낮은가. 세 기업은 지난 "
                        "10년간 10% 넘게 성장해 왔다."),
           "clarification": None,  # 아래에서 채웁니다
           "macro": macro, "base_rates": BASE_RATES, "buffett": BUFFETT,
           "discount_options": DISCOUNTS, "terminal_options": TERMINALS,
           "margin_of_safety": MARGIN_OF_SAFETY,
           "fair_value_generated": fv["generated"],
           "companies": []}

    # 먼저 오해를 바로잡습니다: 기존 시나리오가 실제로 가정한 10년 CAGR.
    clar = []
    for c in applied:
        for v in c["valuations"]:
            n10 = v["projection"][-1]["nopat"]
            clar.append({
                "ticker": c["ticker"], "korean": c["korean"],
                "scenario": v["scenario"],
                "year1_growth": v["assumptions"]["growth"],
                "year10_growth": v["assumptions"]["fade_to"],
                "nopat_cagr_10y": (n10 / c["ttm"]["nopat"]) ** (1 / 10) - 1,
            })
    out["clarification"] = {
        "note": ("3.5%는 \"10년간 성장률\"이 아니라 10년차 한 해의 "
                 "성장률입니다. 각 시나리오가 실제로 가정한 10년 평균은 "
                 "아래와 같습니다."),
        "rows": clar,
    }
    print("\n기존 시나리오가 실제로 가정한 10년 NOPAT CAGR")
    for r in clar:
        print(f"  {r['korean']:<8}{r['scenario']:<5}"
              f"1년차 {r['year1_growth']:>6.1%} → 10년차 "
              f"{r['year10_growth']:>5.1%} · 10년 CAGR "
              f"{r['nopat_cagr_10y']:>6.2%}")

    # ------------------------------------------------------------ 기업별
    for c in applied:
        own = c["record"]["operating_income_cagr"]
        rev_cagr = c["record"].get("revenue_cagr")
        # 참조군 안에서 이 기업의 과거 실적이 어디인가. 기초율은 실질이므로
        # 명목 실적에서 인플레이션을 뺀 뒤 비교합니다.
        own_real = own - infl
        rev_real = (rev_cagr - infl) if rev_cagr else None
        inc_roic = min(c["record"]["summary"]["roic_median"], 0.35)
        nopat = c["ttm"]["nopat"]
        nc = c["balance_sheet"]["net_cash"]
        sh = c["shares_outstanding"]["value"]
        px = c["price"]

        grid = []
        for g in growth_options(c):
            row = {"growth_key": g["key"], "growth_label": g["label"],
                   "growth": g["growth"], "fade_to": g["fade_to"],
                   "basis": g["basis"],
                   "growth_real": g["growth"] - infl,
                   "base_rate_percentile_at_or_above":
                       percentile_of(BASE_RATES["net_income_10y"]["bands"],
                                     g["growth"] - infl),
                   "cells": []}
            for dsc in DISCOUNTS:
                r_ = dcf(nopat, nc, sh, g["growth"], g["fade_to"], inc_roic,
                         dsc["rate"], TERMINALS[0]["rate"])
                cell = {"discount_key": dsc["key"], "discount": dsc["rate"]}
                if r_["diverges"]:
                    cell.update({"diverges": True, "why": r_["why"]})
                else:
                    cell.update({
                        "diverges": False,
                        "value_per_share": r_["value_per_share"],
                        "upside_vs_price": r_["value_per_share"] / px - 1,
                        "terminal_share": r_["terminal_share"],
                        "nopat_cagr_10y": r_["nopat_cagr_10y"],
                        "buy_price_at_margin": {
                            f"{int(m * 100)}%": r_["value_per_share"] * (1 - m)
                            for m in MARGIN_OF_SAFETY},
                    })
                row["cells"].append(cell)
            grid.append(row)

        # 터미널 성장률 민감도. 두 할인율에서 봅니다 — 버핏 기준(국채+3%p)과
        # 순수 국채. 순수 국채(5.25%)에서 명목 GDP 영구성장(5.44%)을
        # 가정하면 **발산합니다**. 그것 자체가 결론입니다: 주식을 국채
        # 수익률만으로 할인하면서 경제 속도의 영구성장을 가정하면 어떤
        # 가격도 정당화됩니다. 그래서 버핏의 '국채 + 얼마'가 필요합니다.
        tsens = []
        g = [x for x in growth_options(c) if x["key"] == "half_of_own"][0]
        for dk in ("bond30_plus3", "bond30"):
            dsc = [x for x in DISCOUNTS if x["key"] == dk][0]
            for t in TERMINALS:
                r_ = dcf(nopat, nc, sh, g["growth"], g["fade_to"], inc_roic,
                         dsc["rate"], t["rate"])
                tsens.append({
                    "discount_key": dk, "discount": dsc["rate"],
                    "terminal_key": t["key"], "label": t["label"],
                    "rate": t["rate"], "basis": t["basis"],
                    "diverges": r_["diverges"],
                    "value_per_share": r_.get("value_per_share"),
                    "upside_vs_price": (r_["value_per_share"] / px - 1)
                    if not r_["diverges"] else None,
                    "why": r_.get("why")})

        # 10년 성장률·ROIC 기록 표 (요청 항목)
        ys = sorted(c["record"]["years"], key=lambda y: y["fiscal_year"])
        history = []
        for i, y in enumerate(ys):
            prev = ys[i - 1] if i else None
            history.append({
                "fiscal_year": y["fiscal_year"],
                "revenue": y.get("revenue"),
                "operating_income": y["operating_income"],
                "invested_capital_avg": y.get("invested_capital_avg"),
                "roic": y.get("roic"),
                "revenue_growth": (y["revenue"] / prev["revenue"] - 1)
                if prev and prev.get("revenue") and y.get("revenue") else None,
                "operating_income_growth":
                    (y["operating_income"] / prev["operating_income"] - 1)
                    if prev and prev.get("operating_income") else None,
                "invested_capital_growth":
                    (y["invested_capital_avg"] / prev["invested_capital_avg"]
                     - 1) if prev and prev.get("invested_capital_avg") else None,
            })

        out["companies"].append({
            "ticker": c["ticker"], "korean": c["korean"],
            "price": px, "market_cap": c["market_cap"],
            "data_as_of": c["data_as_of"],
            "ttm_nopat": nopat, "ttm_revenue": c["ttm"]["revenue"]["value"],
            "net_cash": nc, "shares_outstanding": sh,
            "incremental_roic_used": inc_roic,
            "incremental_roic_basis":
                (f"10년 중위 ROIC "
                 f"{c['record']['summary']['roic_median']:.1%}에 상한 35% "
                 f"적용. 네 할인율·네 성장률 전부에 같은 값을 써서 격자가 "
                 f"성장률과 할인율의 효과만 보이게 했습니다."),
            "own_cagr_nominal": own, "own_cagr_real": own_real,
            "own_revenue_cagr_nominal": rev_cagr,
            "own_revenue_cagr_real": rev_real,
            "own_cagr_percentile_at_or_above":
                percentile_of(BASE_RATES["net_income_10y"]["bands"], own_real),
            "own_revenue_percentile_at_or_above":
                percentile_of(BASE_RATES["sales_10y"]["bands"], rev_real)
                if rev_real is not None else None,
            "in_reference_class":
                c["ttm"]["revenue"]["value"] > 50 * BN,
            "history": history,
            "grid": grid,
            "terminal_sensitivity": tsens,
            "terminal_sensitivity_growth_key": g["key"],
        })

        print(f"\n== {c['korean']}({c['ticker']}) ${px:,.2f} ==")
        print(f"  10년 영업이익 CAGR {own:.1%} (명목) = 실질 {own_real:.1%} → "
              f"이 규모 기업 중 상위 "
              f"{percentile_of(BASE_RATES['net_income_10y']['bands'], own_real):.1%}")
        print(f"  증분 ROIC {inc_roic:.1%} · 터미널 "
              f"{TERMINALS[0]['rate']:.2%} 고정")
        hdr = "".join(f"{d['rate']:>11.2%}" for d in DISCOUNTS)
        print(f"  {'성장률 가정':<26}{hdr}")
        for row in grid:
            cells = ""
            for cell in row["cells"]:
                cells += ("      발산" if cell["diverges"]
                          else f"{cell['value_per_share']:>11,.0f}")
            print(f"  {row['growth_label']:<26}{cells}")
        print(f"  {'(현재가)':<26}" + "".join(f"{px:>11,.0f}"
                                            for _ in DISCOUNTS))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
