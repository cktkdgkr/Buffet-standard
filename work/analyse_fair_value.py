"""
마이크로소프트·알파벳·엔비디아·스페이스X 적정주가 — 보수·중립·낙관 시나리오.

알파벳에 썼던 것과 같은 논리입니다. 10년 현금흐름을 성장 감쇠로 투영하고,
성장에 드는 재투자를 증분 ROIC로 깎고, 터미널을 붙여 할인한 뒤 순현금을
더해 주당 가치를 냅니다.

**시나리오를 손으로 고르지 않습니다.** 네 기업의 성장률이 (10년 영업이익
CAGR 기준) 19.5%에서 67.6%까지 벌어져 있어, 하나의 숫자를 네 기업에 똑같이
쓰면 아무 기업에도 맞지 않습니다. 그래서 각 기업의 **자기 기록에서 규칙으로
도출**하고, 상한만 명시해 둡니다. 상한이 이 모형에서 가장 중요한 판단입니다 —
지금의 비범한 수익률과 성장률을 영구히 연장하지 않겠다는 선언이고, 그것이
없으면 엔비디아의 10년 CAGR 67.6%가 영구 성장률이 되어 어떤 가격도
정당화됩니다.

기준일 기준으로 다시 수집하고, 모든 수치는 공시에서 옵니다. TTM은 분기
사실을 재구성해 만들고, 알파벳 TTM 영업이익이 별도 파이프라인
(analyse_goog_price.py)의 값과 일치하는지로 교차검증합니다.

스페이스X는 TTM 세후영업이익이 음수여서 이 모형을 **적용하지 않습니다.**
분모를 발명하지 않는다는 규칙과 같은 이유입니다. 대신 거꾸로 풀어
"현재 가격이 정당화되려면 정상상태 NOPAT이 얼마여야 하는가"를 냅니다.

    python3 analyse_fair_value.py
    python3 analyse_fair_value.py --refresh
"""

import argparse
import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import sec_cache  # noqa: E402
from collect_roic import CONCEPTS  # noqa: E402

CACHE = os.path.join(HERE, "roic", "cache")
ROIC = os.path.join(HERE, "roic", "roic.json")
PRICES = os.path.join(HERE, "roic", "prices.json")
GOOG = os.path.join(HERE, "goog", "goog_price.json")
SPX = os.path.join(HERE, "spx", "spx_tsla.json")
OUT = os.path.join(HERE, "fv", "fair_value.json")
MM, BN = 1e6, 1e9

TARGETS = [
    ("MSFT", "0000789019", "마이크로소프트"),
    ("GOOG", "0001652044", "알파벳"),
    ("NVDA", "0001045810", "엔비디아"),
]

# 시나리오의 시장 변수는 네 기업에 똑같이 적용합니다. 할인율과 터미널 성장률은
# 기업의 성질이 아니라 "내가 요구하는 수익률"과 "장기 명목 성장"이므로,
# 기업별로 다르게 두면 비교가 깨집니다. 알파벳 직전 보고서의 값을 그대로
# 가져와 두 분석이 비교 가능하게 했습니다.
MARKET = {
    "보수": {"discount": 0.11, "terminal_growth": 0.020, "fade_to": 0.025},
    "중립": {"discount": 0.10, "terminal_growth": 0.025, "fade_to": 0.035},
    "낙관": {"discount": 0.09, "terminal_growth": 0.030, "fade_to": 0.045},
}

# 기업별 변수를 자기 기록에서 뽑는 규칙. 분수는 "10년 CAGR의 몇 분의 몇",
# 상한은 "그래도 이것보다 높게는 가정하지 않는다".
#
# 알파벳에 적용하면 보수 7.0%/15%, 중립 10.4%/18.9%, 낙관 20.9%/35% 가 나와
# 직전 보고서에서 손으로 골랐던 6%/15%, 12%/22%, 20%/30% 와 거의 같습니다.
# 규칙이 과거의 판단을 재현하므로, 규칙으로 바꾼 것이 결론을 움직이지
# 않았다는 뜻입니다.
RULE = {
    "보수": {"growth_divisor": 3.0, "growth_cap": 0.10,
             "roic_source": "min", "roic_divisor": 1.0, "roic_cap": 0.15},
    "중립": {"growth_divisor": 2.0, "growth_cap": 0.15,
             "roic_source": "median", "roic_divisor": 2.0, "roic_cap": 0.25},
    "낙관": {"growth_divisor": 1.0, "growth_cap": 0.25,
             "roic_source": "median", "roic_divisor": 1.0, "roic_cap": 0.35},
}
ORDER = ["보수", "중립", "낙관"]
YEARS = 10
CAGR_YEARS = 10


# --------------------------------------------------------------- 공시 읽기
def duration_facts(cf, concept):
    """
    기간 사실을, 태그별로 전부.

    **데이터가 있는 첫 태그를 잡으면 안 됩니다.** collect_roic 의
    annual_series 가 같은 함정을 주석으로 남겨 두었는데, 여기서 그대로
    빠졌습니다: 엔비디아와 알파벳은 매출의 일부만
    RevenueFromContractWithCustomerExcludingAssessedTax 로 태깅하고 총액은
    다른 태그에 싣습니다. 첫 태그를 잡으니 엔비디아 분기 매출이 $96.2십억
    대신 $3.1십억으로 나왔습니다. 후보를 전부 돌려주고, 부르는 쪽에서
    타이아웃으로 고릅니다.
    """
    us = cf["facts"].get("us-gaap", {})
    out = []
    for tag in CONCEPTS[concept]:
        if tag not in us:
            continue
        rows = []
        for unit, items in us[tag]["units"].items():
            if unit != "USD":
                continue
            for f in items:
                if not f.get("start"):
                    continue
                rows.append((date.fromisoformat(f["start"]),
                             date.fromisoformat(f["end"]), f["val"]))
        if rows:
            out.append((tag, rows))
    return out


def single_quarters(rows):
    """
    기간 사실을 단일 분기로 환원합니다.

    분기 길이(80~100일)로 보고된 사실은 그대로 쓰고, 없는 분기는 **시작일이
    같은 두 누적 사실의 차**로 만듭니다 — 4분기는 거의 언제나 연간에서 9개월을
    뺀 값으로만 존재합니다. 같은 (시작,끝) 쌍이 여러 번 나오면(재작성·재제출)
    먼저 본 것을 씁니다.
    """
    by = {}
    for s, e, v in rows:
        by.setdefault((s, e), v)
    q = {}
    for (s, e), v in by.items():
        if 80 <= (e - s).days <= 100:
            q[e] = v
    starts = {}
    for (s, e), v in by.items():
        starts.setdefault(s, []).append((e, v))
    for s, lst in starts.items():
        lst.sort()
        for i in range(1, len(lst)):
            (e0, v0), (e1, v1) = lst[i - 1], lst[i]
            if 80 <= (e1 - e0).days <= 100 and e1 not in q:
                q[e1] = v1 - v0
    return dict(sorted(q.items()))


def ttm(cf, concept, label, min_value=None, min_note=""):
    """
    최근 4개 분기의 합.

    분기말 네 개가 실제로 연속인지 확인합니다(첫째와 넷째 분기말 간격이
    1년에서 한 분기 뺀 만큼, 즉 250~290일). 분기 하나가 비어 건너뛰면 간격이
    늘어나 여기서 걸립니다 — 그대로 더하면 다섯 분기 전 실적이 섞입니다.

    min_value 는 태그 선택의 타이아웃입니다. 후보 태그를 우선순위대로 돌며
    유효한 TTM 을 만들고, min_value 를 넘는 첫 후보를 씁니다. 매출에 쓰는데,
    일부만 담은 태그는 총액보다 반드시 작기 때문입니다 — 넘지 못하면
    "총액이 아니다"라는 뜻입니다.
    """
    cands = duration_facts(cf, concept)
    if not cands:
        raise SystemExit(f"{label}: {concept} 사실이 없습니다")
    tried = []
    for tag, rows in cands:
        q = single_quarters(rows)
        ends = sorted(q)
        if len(ends) < 4:
            tried.append(f"{tag}: 분기 {len(ends)}개")
            continue
        last4 = ends[-4:]
        span = (last4[-1] - last4[0]).days
        if not 250 <= span <= 290:
            tried.append(f"{tag}: 분기말 간격 {span}일")
            continue
        total = sum(q[e] for e in last4)
        if min_value is not None and total < min_value:
            tried.append(f"{tag}: TTM {total / BN:,.1f}십억 < 기준 "
                         f"{min_value / BN:,.1f}십억")
            continue
        return {"tag": tag, "value": total,
                "quarter_ends": [str(x) for x in last4],
                "quarters": [q[e] for e in last4],
                "span_days": span,
                "tag_candidates": [t for t, _ in cands],
                "tag_rejected": tried,
                "tie_out": min_note or None}
    raise SystemExit(f"{label}: {concept} 쓸 수 있는 태그가 없습니다 — "
                     + " / ".join(tried))


def instant_latest(cf, concept, label, required=True):
    """가장 최근 시점 사실. 같은 날짜에 여러 건이면 10-K/10-Q 구분 없이 첫 건."""
    us = cf["facts"].get("us-gaap", {})
    for tag in CONCEPTS[concept]:  # noqa: B007 — 우선순위대로
        if tag not in us:
            continue
        best = None
        for unit, items in us[tag]["units"].items():
            if unit != "USD":
                continue
            for f in items:
                if f.get("start"):
                    continue
                e = date.fromisoformat(f["end"])
                if best is None or e > best[0]:
                    best = (e, f["val"])
        if best:
            return {"tag": tag, "value": best[1], "as_of": str(best[0])}
    if required:
        raise SystemExit(f"{label}: {concept} 시점 사실이 없습니다")
    return None


def shares_outstanding(cf, label):
    dei = cf["facts"].get("dei", {})
    tag = "EntityCommonStockSharesOutstanding"
    if tag not in dei:
        return None
    items = [f for u, its in dei[tag]["units"].items() for f in its]
    if not items:
        return None
    last = max(f["end"] for f in items)
    same = [f for f in items if f["end"] == last]
    # 복수 종류의 주식이면 표지에 종류별로 실립니다. 합계가 발행주식수입니다.
    return {"value": sum(f["val"] for f in same), "as_of": last,
            "classes": len(same)}


# ------------------------------------------------------------- 시나리오 도출
def cagr(a, b, n):
    return (b / a) ** (1.0 / n) - 1 if (a and b and a > 0 and b > 0) else None


def record(roic_study, ticker):
    """50개사 조사에서 이 기업의 10년 창 기록."""
    me = next((c for c in roic_study["companies"]
               if c["ticker"] == ticker), None)
    if not me:
        raise SystemExit(f"{ticker}: 50개사 조사에 없습니다")
    # 조사의 window 는 모든 기업을 한 표에 담기 위한 격자 범위이고, 기업별
    # 창은 "그 기업의 가장 최근 10개 회계연도"입니다(roic.json 의 window_note).
    # 격자로 자르면 6월 결산인 마이크로소프트가 11년이 되어 중위값이
    # 70.3% 에서 77.0% 로 틀어집니다.
    lo, hi = roic_study["window"]
    n = roic_study["window_years"]
    fys = sorted({y["fiscal_year"] for y in me["years"]})[-n:]
    ys = [y for y in me["years"] if y["fiscal_year"] in set(fys)]
    by = {y["fiscal_year"]: y for y in ys}
    last = max(by)
    first = last - CAGR_YEARS
    src = {y["fiscal_year"]: y for y in me["years"]}
    growth = (cagr(src[first]["operating_income"],
                   src[last]["operating_income"], CAGR_YEARS)
              if first in src else None)
    if growth is None:
        raise SystemExit(f"{ticker}: FY{first} 자료가 없어 10년 CAGR을 낼 수 없습니다")
    return {
        "company_name": me["company_name"], "sic": me["sic"],
        "window": [min(fys), max(fys)], "grid_window": [lo, hi],
        "window_years": n, "summary": me["summary"],
        "years": [{"fiscal_year": y["fiscal_year"], "roic": y.get("roic"),
                   "operating_income": y["operating_income"],
                   "revenue": y.get("revenue"),
                   "invested_capital_avg": y.get("invested_capital_avg")}
                  for y in ys],
        "cagr_years": CAGR_YEARS,
        "cagr_from": first, "cagr_to": last,
        "operating_income_cagr": growth,
        "revenue_cagr": cagr(src[first].get("revenue"),
                             src[last].get("revenue"), CAGR_YEARS),
        "invested_capital_cagr": cagr(src[first].get("invested_capital_avg"),
                                      src[last].get("invested_capital_avg"),
                                      CAGR_YEARS),
    }


def scenarios_for(rec):
    """규칙을 기업의 기록에 적용해 세 시나리오를 만듭니다."""
    s = rec["summary"]
    base = {"min": s["roic_min"], "median": s["roic_median"]}
    out = []
    for name in ORDER:
        r, m = RULE[name], MARKET[name]
        g_raw = rec["operating_income_cagr"] / r["growth_divisor"]
        g = min(g_raw, r["growth_cap"])
        ri_raw = base[r["roic_source"]] / r["roic_divisor"]
        ri = min(ri_raw, r["roic_cap"])
        out.append({
            "name": name,
            "growth": g, "growth_uncapped": g_raw,
            "growth_capped": g_raw > r["growth_cap"],
            "incremental_roic": ri, "incremental_roic_uncapped": ri_raw,
            "incremental_roic_capped": ri_raw > r["roic_cap"],
            "fade_to": m["fade_to"], "discount": m["discount"],
            "terminal_growth": m["terminal_growth"],
            "rule": (f"초기 성장 = 10년 영업이익 CAGR "
                     f"{rec['operating_income_cagr']:.1%} ÷ "
                     f"{r['growth_divisor']:g}, 상한 {r['growth_cap']:.0%} · "
                     f"증분 ROIC = 10년 {'최저' if r['roic_source'] == 'min' else '중위'} "
                     f"{base[r['roic_source']]:.1%} ÷ {r['roic_divisor']:g}, "
                     f"상한 {r['roic_cap']:.0%}"),
        })
    return out


# ----------------------------------------------------------------- 가치평가
def dcf_one(base_nopat, net_cash, shares, market_cap, s, years=YEARS):
    """
    성장 감쇠 + 터미널. 알파벳 보고서와 같은 식입니다.

    FCF = NOPAT × (1 − 성장률 ÷ 증분ROIC). 성장에 드는 재투자를 빼고 남는 것이
    주주 몫이라는 뜻이고, 증분 ROIC이 할인율보다 낮으면 성장이 가치를 깎습니다.
    """
    proj, pv, nopat = [], 0.0, base_nopat
    for t in range(1, years + 1):
        g = s["growth"] + (s["fade_to"] - s["growth"]) * (t - 1) / (years - 1)
        rr = g / s["incremental_roic"]
        nopat *= (1 + g)
        fcf = nopat * (1 - rr)
        disc = fcf / (1 + s["discount"]) ** t
        pv += disc
        proj.append({"year": t, "growth": g, "nopat": nopat,
                     "reinvestment_rate": rr, "free_cash_flow": fcf,
                     "present_value": disc})
    tg = s["terminal_growth"]
    term = (proj[-1]["nopat"] * (1 + tg) * (1 - tg / s["incremental_roic"])
            / (s["discount"] - tg))
    term_pv = term / (1 + s["discount"]) ** years
    ev = pv + term_pv
    eq = ev + net_cash
    vps = eq / shares
    return {
        "scenario": s["name"],
        "assumptions": {k: s[k] for k in
                        ("growth", "fade_to", "incremental_roic",
                         "discount", "terminal_growth")},
        "rule": s["rule"],
        "growth_capped": s["growth_capped"],
        "incremental_roic_capped": s["incremental_roic_capped"],
        "projection": proj,
        "pv_of_forecast": pv, "pv_of_terminal": term_pv,
        "terminal_share": term_pv / ev if ev else None,
        "enterprise_value": ev, "equity_value": eq,
        "value_per_share": vps,
        "upside_vs_market": eq / market_cap - 1 if market_cap else None,
        "first_year_reinvestment_rate": proj[0]["reinvestment_rate"],
    }


def implied_growth(base_nopat, net_cash, shares, market_cap, s):
    """
    현재 시가총액이 나오게 하는 초기 성장률. 감쇠 목표도 함께 내립니다.

    **탐색 상한은 증분 ROIC 입니다.** 처음에 60% 로 두었는데, 그러면 재투자율
    (성장률 ÷ 증분 ROIC)이 100% 를 넘는 구간이 답으로 나옵니다 — 번 돈보다 더
    투자해야 하는 성장이고, 모형에는 그 외부자금 조달이 들어 있지 않습니다.
    그렇게 나온 "중립 시나리오 정당화 성장률 32%"는 증분 ROIC 25% 를 넘는
    값이어서 자기 현금으로는 불가능합니다. 상한을 증분 ROIC 로 두면 그 모순이
    사라지고, "천장(성장률을 최적으로 골라도 나오는 최대 가치)이 현재가보다
    낮다"는 사실과 정확히 일치합니다.

    **해가 없을 수 있습니다.** 증분 ROIC이 할인율보다 조금만 높으면 성장이
    가치를 거의 더하지 못하므로, 상한까지 올려도 현재 시가총액에 닿지
    않습니다. 그때 None 을 돌려줍니다 — "이 시나리오의 가정으로는 어떤
    성장률도 현재 가격을 설명하지 못한다"는 뜻입니다.
    """
    bound = s["incremental_roic"] * 0.9995
    at_bound = dcf_one(base_nopat, net_cash, shares, market_cap,
                       {**s, "growth": bound,
                        "fade_to": min(s["fade_to"], bound)})["equity_value"]
    if at_bound < market_cap:
        return None
    lo, hi = -0.20, bound
    for _ in range(100):
        mid = (lo + hi) / 2
        t = dict(s)
        t["growth"] = mid
        t["fade_to"] = min(s["fade_to"], mid)
        if dcf_one(base_nopat, net_cash, shares, market_cap, t)["equity_value"] \
                < market_cap:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def best_case_within_scenario(base_nopat, net_cash, shares, market_cap, s):
    """
    한 시나리오의 가정 안에서 성장률만 바꿔 얻을 수 있는 **최대** 주당가치.

    증분 ROIC이 할인율보다 조금만 높으면, 성장률을 올려도 재투자가 그만큼
    늘어 남는 현금이 줄어듭니다. 증분 ROIC 15% 에서는 성장률 15% 에 재투자율이
    100% 가 되어 잉여현금이 0 이 되고, 그 위는 음수입니다. 그래서 가치에는
    천장이 있습니다. 현재가가 그 천장보다 높으면 "성장률을 아무리 높게 잡아도
    이 시나리오의 가정으로는 현재가를 설명할 수 없다"는 뜻이고, 정당화 성장률이
    없는 이유가 바로 이것입니다.
    """
    # 탐색 상한은 증분 ROIC 입니다. 그 지점에서 재투자율이 100% 가 되어
    # 잉여현금이 0 이 되고, 그 위는 음수이므로 가치가 늘 수 없습니다. 상한을
    # 그보다 낮게 잡으면(처음에 14% 로 고정했습니다) 시나리오 자신의 성장률이
    # 탐색 범위 밖으로 나가 "천장이 시나리오 값보다 낮다"는 모순이 납니다.
    hi = s["incremental_roic"]
    best = None
    steps = 2000
    for i in range(0, steps + 1):
        g = hi * i / steps * 0.9995
        t = {**s, "growth": g, "fade_to": min(s["fade_to"], g)}
        v = dcf_one(base_nopat, net_cash, shares, market_cap, t)
        if best is None or v["value_per_share"] > best["value_per_share"]:
            best = {"growth": g, "value_per_share": v["value_per_share"],
                    "equity_value": v["equity_value"]}
    best["search_upper_bound"] = hi
    best["note"] = (f"성장률 0 ~ {hi:.0%}(증분 ROIC) 구간에서 얻을 수 있는 "
                    f"최대값. 그 위에서는 재투자가 잉여현금을 다 먹습니다.")
    return best


def required_nopat(net_cash, shares, market_cap, s):
    """
    거꾸로: 현재 가격이 정당화되려면 기준연도 NOPAT이 얼마여야 하는가.

    모형이 NOPAT에 선형이므로 한 번 계산해 비례로 되풀면 됩니다. 기준 이익이
    음수여서 모형을 쓸 수 없는 기업(스페이스X)에 쓰는 경로입니다.
    """
    probe = dcf_one(1.0, 0.0, shares, market_cap, s)["enterprise_value"]
    return (market_cap - net_cash) / probe if probe else None


# --------------------------------------------------------------------- 수집
def company(ticker, cik, korean, roic_study, prices, refresh):
    cf = sec_cache.companyfacts(cik, CACHE, refresh=refresh)
    if isinstance(cf, tuple):
        cf = cf[0]
    if isinstance(cf, str):
        cf = json.load(open(cf, encoding="utf-8"))
    label = f"{korean}({ticker})"
    rec = record(roic_study, ticker)
    rec_years = rec["years"]

    oi = ttm(cf, "operating_income", label)
    # 매출 태그 선택의 타이아웃. "영업이익보다 크다"만으로는 약합니다 —
    # 알파벳의 RevenueFromContract... 는 총액의 71% 만 담는데도 영업이익보다는
    # 크므로 그 벽을 넘었고, TTM 매출이 FY2025 연간 매출보다 작게 나왔습니다.
    # 성장하는 기업의 TTM 은 직전 연간치보다 작을 수 없으니, 50개사 조사의
    # (이미 검증된) 최신 연간 매출을 기준으로 삼습니다.
    annual_rev = max((y.get("revenue") or 0) for y in rec_years)
    floor = max(oi["value"], annual_rev * 0.95)
    rev = ttm(cf, "revenue", label, min_value=floor,
              min_note=(f"TTM 매출 ≥ 최신 연간 매출 {annual_rev / BN:,.1f}십억 "
                        f"× 0.95 (총액이 아닌 태그 배제)"))
    pre = ttm(cf, "pretax_income", label)
    tax = ttm(cf, "income_tax_expense", label)
    rate = tax["value"] / pre["value"] if pre["value"] else None
    # 실효세율은 공시대로 쓰되, 평가손익 등으로 터무니없는 값이 나오면
    # 결론이 세율에 끌려갑니다. 0~35% 밖이면 멈춥니다.
    if rate is None or not 0.0 <= rate <= 0.35:
        raise SystemExit(f"{label}: TTM 실효세율 {rate} — 범위를 벗어났습니다")
    nopat = oi["value"] * (1 - rate)

    # 기타수익이 세전이익에 크게 섞이면 실효세율이 영업과 무관한 비율이 됩니다.
    # 알파벳에서 9개월 평가이익 $127.5십억이 그렇게 했고, 엔비디아도 같은
    # 모양입니다. 규칙상 수치를 쓰되 법정세율 대안을 나란히 둡니다.
    other = ttm(cf, "nonoperating_income", label)
    nopat_statutory = oi["value"] * (1 - 0.21)

    eq = instant_latest(cf, "total_equity", label)
    debt_parts = []
    for c in ("long_term_debt_noncurrent", "long_term_debt_current",
              "short_term_borrowings"):
        if c in CONCEPTS:
            got = instant_latest(cf, c, label, required=False)
            if got:
                debt_parts.append({"concept": c, **got})
    debt = sum(p["value"] for p in debt_parts)
    cash = instant_latest(cf, "cash_and_sti_combined", label, required=False)
    cash_note = "CashCashEquivalentsAndShortTermInvestments (결합 태그)"
    if not cash:
        ce = instant_latest(cf, "cash_and_equivalents", label)
        sti = instant_latest(cf, "short_term_investments", label,
                             required=False)
        cash = {"tag": f"{ce['tag']} + {sti['tag'] if sti else '—'}",
                "value": ce["value"] + (sti["value"] if sti else 0),
                "as_of": ce["as_of"]}
        cash_note = "현금 + 단기투자 (별도 태그 합산)"

    sh = shares_outstanding(cf, label)
    if ticker == "GOOG":
        # 알파벳은 표지 주식수를 dei 에 싣지 않습니다. 이미 282건으로 검증된
        # 전용 파이프라인의 값을 씁니다 (10-Q 표지, 3종 합계).
        g = json.load(open(GOOG, encoding="utf-8"))
        sh = {"value": g["analysis"]["shares_outstanding"],
              "as_of": g["filings"]["10-Q"]["period_end"], "classes": 3,
              "source": "goog_price.json (10-Q 표지, Class A+B+C)"}
    if not sh:
        raise SystemExit(f"{label}: 발행주식수를 찾지 못했습니다")

    px = prices["prices"][ticker]
    mc = px["price"] * sh["value"]
    net_cash = cash["value"] - debt
    scen = scenarios_for(rec)
    # ROIC 추세: 고점 이후 자본이 이익보다 빨리 늘었는지. 네 기업 모두 같은
    # 모양이고, 가격 판정보다 이 추세가 더 중요할 수 있습니다.
    peak = max(rec["years"], key=lambda y: y["roic"] or 0)
    last = max(rec["years"], key=lambda y: y["fiscal_year"])
    rec["trend"] = {
        "peak_fiscal_year": peak["fiscal_year"], "peak_roic": peak["roic"],
        "last_fiscal_year": last["fiscal_year"], "last_roic": last["roic"],
        "operating_income_multiple":
            last["operating_income"] / peak["operating_income"],
        "invested_capital_multiple":
            last["invested_capital_avg"] / peak["invested_capital_avg"],
        "note": ("고점 이후 투하자본 배수가 영업이익 배수보다 크면 ROIC 은 "
                 "떨어집니다. 이익이 멈춴 게 아니라 자본이 더 빨리 늘어서입니다."),
    }

    vals = [dcf_one(nopat, net_cash, sh["value"], mc, s) for s in scen]
    for v, s in zip(vals, scen):
        v["implied_growth_at_price"] = implied_growth(
            nopat, net_cash, sh["value"], mc, s)
        v["implied_growth_note"] = (
            None if v["implied_growth_at_price"] is not None else
            f"이 시나리오의 가정(증분 ROIC {s['incremental_roic']:.0%}, 할인율 "
            f"{s['discount']:.0%})으로는 초기 성장률을 증분 ROIC "
            f"{s['incremental_roic']:.0%}까지 올려도 현재 시가총액에 닿지 "
            f"않습니다. 그 위의 성장률은 재투자율이 100% 를 넘어 자기 "
            f"현금으로 조달할 수 없습니다.")
        v["required_nopat_at_price"] = required_nopat(
            net_cash, sh["value"], mc, s)
        v["required_nopat_multiple"] = (v["required_nopat_at_price"] / nopat
                                        if nopat else None)
        v["price_to_value"] = px["price"] / v["value_per_share"]
        best = best_case_within_scenario(nopat, net_cash, sh["value"], mc, s)
        v["best_case_in_scenario"] = best
        v["price_vs_best_case"] = px["price"] / best["value_per_share"]

    as_of = oi["quarter_ends"][-1]
    return {
        "ticker": ticker, "korean": korean, "cik": cik,
        "data_as_of": as_of,
        "data_as_of_note": (f"TTM 은 {oi['quarter_ends'][0]} 직전 분기부터 "
                            f"{as_of} 까지 4개 분기입니다. 기업마다 결산월이 "
                            f"달라 기준 분기말이 다릅니다."),
        "company_name": rec["company_name"], "sic": rec["sic"],
        "price": px["price"], "price_as_of": px["as_of_utc"],
        "fifty_two_week_high": px.get("fifty_two_week_high"),
        "fifty_two_week_low": px.get("fifty_two_week_low"),
        "shares_outstanding": sh, "market_cap": mc,
        "ttm": {"operating_income": oi, "revenue": rev,
                "pretax_income": pre, "income_tax_expense": tax,
                "nonoperating_income": other,
                "effective_tax_rate": rate, "nopat": nopat,
                "nopat_at_statutory_21": nopat_statutory,
                "nonoperating_share_of_pretax":
                    other["value"] / pre["value"] if pre["value"] else None,
                "tax_note": (f"TTM 법인세 {tax['value'] / BN:,.1f}십억 ÷ TTM "
                             f"세전이익 {pre['value'] / BN:,.1f}십억 = "
                             f"{rate:.1%}. 세전이익 중 영업 외 수익이 "
                             f"{other['value'] / pre['value']:.0%}. 법정세율 "
                             f"21% 적용 시 NOPAT "
                             f"{nopat_statutory / BN:,.1f}십억 "
                             f"({nopat_statutory / nopat - 1:+.1%})."),
                "operating_margin": oi["value"] / rev["value"]},
        "balance_sheet": {"total_equity": eq, "debt_parts": debt_parts,
                          "debt": debt, "cash_and_short_term": cash,
                          "cash_note": cash_note, "net_cash": net_cash,
                          "invested_capital": eq["value"] + debt
                          - cash["value"]},
        "record": rec, "scenario_inputs": scen, "valuations": vals,
        "model": "applied",
    }


def spacex(prices, refresh):
    """
    스페이스X는 기준이익이 성립하지 않아 **적정주가를 한 값으로 내지 않습니다.**

    처음에 "세후영업이익이 음수여서"라고 적었는데 그건 틀렸습니다. 9개월을
    연율화한 NOPAT 은 +$0.74십억으로 양수입니다. 다만 그 안이 상반기
    −$1.65십억과 3분기 +$2.20십억으로 갈려 있습니다. 즉 **흑자 전환 첫
    분기에 있는 회사**이고, 어느 분기를 기준으로 잡느냐가 가치를 수십 배
    바꿉니다. 10-K 가 없어 10년 ROIC 기록도 없으므로 기업별 규칙도 쓸 수
    없습니다.

    그래서 두 가지를 같이 냅니다. 기준이익 후보마다 세 시나리오를 돌린 값과,
    거꾸로 푼 "현재 가격이 요구하는 정상상태 NOPAT". 뒤쪽이 더 정직한
    답입니다 — 기준을 고르지 않아도 되기 때문입니다.
    """
    d = json.load(open(SPX, encoding="utf-8"))
    s = d["SPCX"]
    r = s["ratios"]
    q = s["quarterly"]
    sh = s["shares_outstanding"]
    px = prices["prices"]["SPCX"]
    mc = px["price"] * sh
    bs = s["balance_sheets"]
    latest_key = sorted(bs)[-1]
    latest = bs[latest_key]
    # 키 이름을 짐작해 .get(...) or 0 으로 받으면, 키가 바뀐 줄 모르고 0 이
    # 들어갑니다. 실제로 그렇게 현금을 0 으로 읽어 순현금이 +$51.0십억 대신
    # −$38.8십억이 되고, 주당 가치가 $90 가까이 깎였습니다. 없으면 멈춥니다.
    for key in ("cash_and_securities", "debt"):
        if key not in latest:
            raise SystemExit(
                f"스페이스X {latest_key} 재무상태표에 {key!r} 가 없습니다 "
                f"(있는 키: {sorted(latest)})")
    cash = latest["cash_and_securities"]
    debt = latest["debt"]
    net_cash = cash - debt

    bases = [
        {"key": "nine_months", "name": "9개월 연율화",
         "nopat": r.get("nopat_annualised"),
         "note": ("2026년 9개월 영업이익을 연율화한 뒤 세후. 상반기 적자와 "
                  "3분기 흑자가 상쇄돼 거의 0 입니다.")},
        {"key": "q3_run_rate", "name": "3분기 연율화",
         "nopat": (q["nopat_q3"] * 4) if q.get("nopat_q3") is not None
         else None,
         "note": ("3분기만 네 배. 흑자 전환한 첫 분기이고, 한 분기를 네 배 "
                  "하는 것은 계절성과 일회성을 무시합니다. 위쪽 경계로 "
                  "읽으십시오.")},
    ]

    scen = []
    for name in ORDER:
        m = MARKET[name]
        rr = RULE[name]
        scen.append({"name": name, "growth": rr["growth_cap"],
                     "incremental_roic": rr["roic_cap"],
                     "fade_to": m["fade_to"], "discount": m["discount"],
                     "terminal_growth": m["terminal_growth"],
                     "rule": (f"10년 ROIC 기록이 없어(10-K 미제출) 기업별 "
                              f"규칙을 쓸 수 없습니다. 상한값(성장 "
                              f"{rr['growth_cap']:.0%}, 증분 ROIC "
                              f"{rr['roic_cap']:.0%})을 그대로 적용 — 세 "
                              f"기업에 쓴 가정 중 가장 관대한 쪽입니다."),
                     "growth_capped": True,
                     "incremental_roic_capped": True})

    for b in bases:
        if b["nopat"] is None or b["nopat"] <= 0:
            b["valuations"] = None
            b["why_no_valuation"] = ("기준 NOPAT 이 0 이하입니다. 성장률을 "
                                     "곱해도 커지지 않으므로 모형을 돌리지 "
                                     "않습니다.")
            continue
        vals = []
        for sc in scen:
            v = dcf_one(b["nopat"], net_cash, sh, mc, sc)
            v["implied_growth_at_price"] = implied_growth(
                b["nopat"], net_cash, sh, mc, sc)
            v["implied_growth_note"] = (
                None if v["implied_growth_at_price"] is not None else
                f"초기 성장률을 증분 ROIC {sc['incremental_roic']:.0%}까지 "
                f"올려도 현재 시가총액에 닿지 않습니다.")
            vals.append(v)
        b["valuations"] = vals

    # 요구 이익을 "지금 매출의 몇 %" 로 바꿔 두면 규모가 와닿습니다. 사업부
    # 매출이 공시되므로 합계를 쓸 수 있습니다.
    seg = s.get("segments_9m") or {}
    rev_9m = sum(v["revenue"]["9m_2026"] for v in seg.values()
                 if isinstance(v, dict) and v.get("revenue", {}).get("9m_2026"))
    rev_q3 = sum(v["revenue"]["q3_2026"] for v in seg.values()
                 if isinstance(v, dict) and v.get("revenue", {}).get("q3_2026"))
    revenue = {"nine_months_2026": rev_9m,
               "nine_months_annualised": rev_9m * 4 / 3,
               "q3_2026": rev_q3, "q3_annualised": rev_q3 * 4,
               "market_cap_to_q3_annualised_revenue":
                   mc / (rev_q3 * 4) if rev_q3 else None,
               "note": "사업부별 공시 매출의 합. 연결 매출과 같습니다."}

    reverse = []
    q3_annual = (q["nopat_q3"] * 4) if q.get("nopat_q3") is not None else None
    for sc in scen:
        need = required_nopat(net_cash, sh, mc, sc)
        reverse.append({
            "scenario": sc["name"],
            "assumptions": {k: sc[k] for k in
                            ("growth", "fade_to", "incremental_roic",
                             "discount", "terminal_growth")},
            "rule": sc["rule"],
            "required_nopat_at_price": need,
            "required_nopat_per_share": need / sh if need else None,
            "vs_q3_annualised": (need / q3_annual) if q3_annual else None,
            "vs_nine_months_annualised":
                (need / r["nopat_annualised"])
                if r.get("nopat_annualised") else None,
            "as_share_of_q3_annualised_revenue":
                (need / (rev_q3 * 4)) if rev_q3 else None,
        })
    return {
        "ticker": "SPCX", "korean": "스페이스X", "cik": s["meta"].get("cik"),
        "company_name": s["meta"].get("entity"),
        "price": px["price"], "price_as_of": px["as_of_utc"],
        "fifty_two_week_high": px.get("fifty_two_week_high"),
        "fifty_two_week_low": px.get("fifty_two_week_low"),
        "shares_outstanding": {"value": sh, "as_of": latest_key,
                               "source": "10-Q 표지"},
        "market_cap": mc,
        "balance_sheet": {"balance_sheet_date": latest_key,
                          "cash_and_securities": cash, "debt": debt,
                          "net_cash": net_cash,
                          "equity": latest.get("equity"),
                          "goodwill": latest.get("goodwill"),
                          "construction_in_progress":
                              latest.get("construction_in_progress")},
        "earnings_bases": bases,
        "nopat_nine_months_annualised": r.get("nopat_annualised"),
        "nopat_q3_annualised": q3_annual,
        "nopat_first_half": q.get("nopat_first_half"),
        "nopat_q3": q.get("nopat_q3"),
        "segments_9m": s.get("segments_9m"),
        "revenue": revenue,
        "quarterly": q,
        "scenario_inputs": scen,
        "reverse": reverse,
        "model": "base_not_established",
        "why_not": ("기준이익이 성립하지 않습니다. 9개월 연율화 NOPAT 은 "
                    "+$0.7십억으로 양수이지만, 상반기 −$1.6십억과 3분기 "
                    "+$2.2십억이 상쇄된 결과입니다 — 흑자 전환 첫 분기에 "
                    "있는 회사이고, 어느 분기를 기준으로 잡느냐가 가치를 "
                    "수십 배 바꿉니다. 10-K 가 없어 10년 ROIC 기록도 "
                    "없습니다. 그래서 적정주가를 한 값으로 내지 않고, "
                    "기준이익 후보별 값과 현재 가격이 요구하는 정상상태 "
                    "이익을 나란히 냅니다."),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    print(f"오늘 {date.today().isoformat()} 기준")
    roic_study = json.load(open(ROIC, encoding="utf-8"))
    prices = json.load(open(PRICES, encoding="utf-8"))
    print(f"  50개사 조사 생성 {roic_study['generated']} · "
          f"시세 수집 {prices['fetched_utc'][:19]}")

    out = {"generated": date.today().isoformat(),
           "roic_study_generated": roic_study["generated"],
           "roic_study_window": roic_study["window"],
           "prices_fetched_utc": prices["fetched_utc"],
           "wacc_for_roic_hurdle": roic_study["wacc"],
           "market_assumptions": MARKET, "rule": RULE,
           "projection_years": YEARS, "cagr_years": CAGR_YEARS,
           "companies": []}
    for t, cik, ko in TARGETS:
        print(f"\n== {ko}({t}) ==")
        c = company(t, cik, ko, roic_study, prices, args.refresh)
        out["companies"].append(c)
        print(f"  TTM 영업이익 {c['ttm']['operating_income']['value'] / BN:,.1f}십억 "
              f"(분기말 {c['ttm']['operating_income']['quarter_ends'][-1]}) · "
              f"실효세율 {c['ttm']['effective_tax_rate']:.1%} · "
              f"NOPAT {c['ttm']['nopat'] / BN:,.1f}십억")
        print(f"  {c['ttm']['tax_note']}")
        print(f"  주가 ${c['price']:,.2f} · 시가총액 {c['market_cap'] / BN:,.0f}십억 · "
              f"순현금 {c['balance_sheet']['net_cash'] / BN:+,.1f}십억")
        print(f"  10년 CAGR 영업이익 {c['record']['operating_income_cagr']:.1%} · "
              f"ROIC 중위 {c['record']['summary']['roic_median']:.1%} "
              f"(최저 {c['record']['summary']['roic_min']:.1%})")
        tr = c["record"]["trend"]
        print(f"  ROIC 추세: FY{tr['peak_fiscal_year']} {tr['peak_roic']:.1%} "
              f"(고점) → FY{tr['last_fiscal_year']} {tr['last_roic']:.1%} · "
              f"투하자본 {tr['invested_capital_multiple']:.2f}배 vs "
              f"영업이익 {tr['operating_income_multiple']:.2f}배")
        for v in c["valuations"]:
            print(f"    {v['scenario']}  성장 {v['assumptions']['growth']:>5.1%}"
                  f"{'(상한)' if v['growth_capped'] else '     '} · "
                  f"증분ROIC {v['assumptions']['incremental_roic']:>5.1%}"
                  f"{'(상한)' if v['incremental_roic_capped'] else '     '} · "
                  f"할인 {v['assumptions']['discount']:.0%}  →  "
                  f"주당 ${v['value_per_share']:>8,.0f}  "
                  f"({v['upside_vs_market']:+6.0%}) · "
                  + (f"현재가 정당화 성장률 "
                     f"{v['implied_growth_at_price']:>6.1%}"
                     if v["implied_growth_at_price"] is not None
                     else "현재가를 설명하는 성장률 없음"))

    print("\n== 스페이스X(SPCX) ==")
    sx = spacex(prices, args.refresh)
    out["companies"].append(sx)
    print(f"  주가 ${sx['price']:,.2f} · 시가총액 {sx['market_cap'] / BN:,.0f}십억")
    print(f"  기준이익: 9개월 연율화 "
          f"{sx['nopat_nine_months_annualised'] / BN:+,.1f}십억 "
          f"(상반기 {sx['nopat_first_half'] / BN:+,.1f} + 3분기 "
          f"{sx['nopat_q3'] / BN:+,.1f}) · 3분기 연율화 "
          f"{sx['nopat_q3_annualised'] / BN:+,.1f}십억")
    for b in sx["earnings_bases"]:
        if not b.get("valuations"):
            print(f"    [{b['name']}] {b.get('why_no_valuation', '')}")
            continue
        line = " · ".join(f"{v['scenario']} ${v['value_per_share']:,.0f}"
                          f"({v['upside_vs_market']:+.0%})"
                          for v in b["valuations"])
        print(f"    [{b['name']}] {line}")
    for r in sx["reverse"]:
        print(f"    {r['scenario']}  요구 NOPAT "
              f"{r['required_nopat_at_price'] / BN:>7,.1f}십억"
              + (f" (3분기 연율화의 {r['vs_q3_annualised']:,.1f}배)"
                 if r.get("vs_q3_annualised") else ""))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
