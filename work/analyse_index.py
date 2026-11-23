"""
S&P 500 과 나스닥100 을 이 프로젝트의 버핏 기준으로 판정합니다.

질문: 30년 기록으로 보면 적절한 매수 가격(지수 수준)은 얼마이고, 지금의
실적 기준으로 버핏이 말하는 안전마진이 확보되는 수준은 얼마인가.

방법은 개별 기업에 쓴 것과 같습니다. 단일 적정가를 내지 않고,
  1. 30년 기록에서 성장률 가정을 **규칙으로** 도출하고(손으로 고르지 않음),
  2. 성장률 가정 × 할인율 **격자**로 지수 1포인트당 가치를 내고,
  3. 안전마진 0·20·30·40% 를 적용한 **매수 상한 지수 수준**을 내고,
  4. 거꾸로 **지금 지수 수준이 요구하는 성장률**을 풉니다.

지수에 맞게 바꾼 것은 둘입니다.
  - **분자.** 개별 기업의 NOPAT 자리에 지수의 12개월 이익을 씁니다. S&P 500 은
    S&P 가 공표하는 보고 기준 EPS(30년 일관된 계열). 나스닥100 은 지수 단위
    이익이 공표되지 않아 구성종목 100개의 이익을 SEC 공시에서 모아 만들고,
    순이익과 NOPAT 를 **함께** 냅니다 — 순이익에는 보유 지분 평가이익이
    섞여 있어(알파벳·아마존) NOPAT 가 프로젝트의 기본 분자입니다.
  - **재투자 수익률.** 개별 기업의 증분 ROIC 자리에 지수의 ROE 를 씁니다.
    재투자율 = 성장률 ÷ ROE — 지속가능 성장의 항등식(g = ROE × 유보율)을
    거꾸로 쓴 것이고, 1992 서한의 "incremental returns that are enticing"
    조건과 같은 항입니다.

    python3 analyse_index.py
"""

import json
import os
import statistics as st
import sys
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from analyse_buffett_standard import dcf, percentile_of      # noqa: E402

RAW = os.path.join(HERE, "idx", "index_raw.json")
BS = os.path.join(HERE, "fv", "buffett_standard.json")
OUT = os.path.join(HERE, "idx", "index.json")
BN = 1e9
YEARS = 10
MARGINS = [0.0, 0.20, 0.30, 0.40]
CAP_GROWTH = 0.25          # 개별 기업 격자와 같은 상한
CAP_RETURN = 0.35          # 증분 수익률 상한 — 개별 기업과 같음
SOLVE_FADE_TO = 0.035      # 요구 성장률을 풀 때의 감쇠 모양(중립 시나리오)
WINDOWS = (10, 20, 30)


def ym(d):
    return d[:7]


def shift(m, years):
    y, mo = int(m[:4]), m[5:7]
    return f"{y + years:04d}-{mo}"


def cagr(a, b, n):
    return (b / a) ** (1 / n) - 1 if a and b and a > 0 and b > 0 else None


def pct_rank(values, x):
    """x 보다 낮았던 비율(0~1)."""
    return sum(v < x for v in values) / len(values) if values else None


# ---------------------------------------------------------------- S&P 500
def spx_series(raw):
    """
    월별 표: 가격(명목)·EPS(명목·실질)·배당(명목)·장부가치·ROE.

    multpl 의 EPS·배당은 **실질(2026년 9월 불변 달러)** 이라 같은 사이트의
    CPI 로 명목으로 되돌립니다: 명목 = 실질 × CPI(그 달) ÷ CPI(기준 달).
    기준 달은 CPI 표의 마지막 달이고, 페이지 문구("constant September,
    2026 dollars")와 일치하는지 확인합니다.
    """
    cpi = {ym(r["date"]): r["value"] for r in raw["spx"]["cpi"]["rows"]}
    base_m = max(cpi)
    base = cpi[base_m]
    eps_r = {ym(r["date"]): r["value"] for r in raw["spx"]["eps"]["rows"]}
    dps_r = {ym(r["date"]): r["value"] for r in raw["spx"]["dividend"]["rows"]}
    bv = {ym(r["date"]): r["value"] for r in raw["spx"]["book_value"]["rows"]}
    pe_m = {ym(r["date"]): r["value"] for r in raw["spx"]["pe"]["rows"]}
    px = {ym(r["date"]): r["close"]
          for r in raw["prices"]["SPX"]["monthly"]["rows"]}
    rows = []
    for m in sorted(eps_r):
        if m not in cpi:
            continue
        k = cpi[m] / base
        rec = {"month": m, "cpi": cpi[m],
               "eps_real": eps_r[m], "eps_nominal": eps_r[m] * k,
               "dps_nominal": dps_r[m] * k if m in dps_r else None,
               "price": px.get(m), "pe_multpl": pe_m.get(m),
               "book_value": bv.get(m)}
        if rec["price"] and rec["eps_nominal"] > 0:
            rec["pe"] = rec["price"] / rec["eps_nominal"]
        if rec["book_value"]:
            rec["roe"] = rec["eps_nominal"] / rec["book_value"]
        rows.append(rec)
    return rows, base_m, base


def spx_crosschecks(raw, rows):
    """
    두 독립 사본의 대조.
    (1) multpl 을 명목으로 되돌린 EPS ↔ 실러의 명목 EPS (겹치는 1996~2024).
    (2) 우리가 계산한 P/E ↔ multpl 이 공표한 P/E (최근 5년, 같은 달).
    둘 다 맞아야 CPI 환산과 가격 매칭이 옳은 것입니다.
    """
    sh = {r["date"]: r for r in raw["shiller"]["rows"]}
    a = []
    for r in rows:
        s = sh.get(r["month"])
        if s and s["earnings"] and r["month"] >= "1996-01":
            a.append({"month": r["month"], "ours": r["eps_nominal"],
                      "shiller": s["earnings"],
                      "rel": r["eps_nominal"] / s["earnings"] - 1})
    b = []
    for r in rows:
        if r["month"] >= "2021-07" and r.get("pe") and r.get("pe_multpl"):
            b.append({"month": r["month"], "ours": r["pe"],
                      "multpl": r["pe_multpl"],
                      "rel": r["pe"] / r["pe_multpl"] - 1})
    return {
        "eps_vs_shiller": {
            "months": len(a),
            "median_abs_rel": st.median(abs(x["rel"]) for x in a),
            "p90_abs_rel": sorted(abs(x["rel"]) for x in a)[int(len(a) * .9)],
            "worst": max(a, key=lambda x: abs(x["rel"])),
            "last": a[-1]},
        "pe_vs_multpl": {
            "months": len(b),
            "median_abs_rel": st.median(abs(x["rel"]) for x in b),
            "worst": max(b, key=lambda x: abs(x["rel"])),
            "note": ("multpl 의 P/E 는 그 달 첫날 가격, 우리는 월말 가격이라 "
                     "한 달 안의 움직임만큼 다를 수 있습니다.")},
    }


def spx_record(raw, rows):
    by = {r["month"]: r for r in rows}
    last_e = max(m for m in by)
    lvl = raw["prices"]["SPX"]["latest"]
    out = {"eps_as_of": last_e, "windows": {}}
    for n in WINDOWS:
        m0 = shift(last_e, -n)
        r0, r1 = by.get(m0), by[last_e]
        if not r0:
            continue
        out["windows"][str(n)] = {
            "from": m0, "to": last_e,
            "eps_nominal_from": r0["eps_nominal"],
            "eps_nominal_to": r1["eps_nominal"],
            "eps_cagr_nominal": cagr(r0["eps_nominal"], r1["eps_nominal"], n),
            "eps_cagr_real": cagr(r0["eps_real"], r1["eps_real"], n),
        }
    # 가격 CAGR — 월말 종가, 최신 월까지.
    px = raw["prices"]["SPX"]["monthly"]["rows"]
    pm = {ym(r["date"]): r["close"] for r in px}
    last_p = max(pm)
    out["price"] = {}
    for n in WINDOWS:
        m0 = shift(last_p, -n)
        if m0 in pm:
            out["price"][str(n)] = {"from": m0, "to": last_p,
                                    "cagr": cagr(pm[m0], pm[last_p], n)}
    # 30년 P/E 분포와 지금의 위치.
    start = shift(last_e, -30)
    pes = [(r["month"], r["pe"]) for r in rows
           if r["month"] >= start and r.get("pe")]
    cur_pe = lvl["price"] / by[last_e]["eps_nominal"]
    vals = [p for _, p in pes]
    out["pe_30y"] = {
        "months": len(vals), "median": st.median(vals),
        "min": min(pes, key=lambda x: x[1]),
        "max": max(pes, key=lambda x: x[1]),
        "current": cur_pe, "share_below_current": pct_rank(vals, cur_pe),
        "note": ("2008~2009 년에는 이익이 급감해 P/E 가 일시적으로 100배를 "
                 "넘었습니다. 중위값은 그 영향을 받지 않습니다."),
    }
    roes = [(r["month"], r["roe"]) for r in rows if r.get("roe")]
    out["roe"] = {"from": roes[0][0], "to": roes[-1][0], "quarters": len(roes),
                  "median": st.median(v for _, v in roes),
                  "min": min(roes, key=lambda x: x[1]),
                  "max": max(roes, key=lambda x: x[1]),
                  "latest": roes[-1]}
    payout = [r["dps_nominal"] / r["eps_nominal"] for r in rows
              if r["month"] >= start and r.get("dps_nominal")
              and r["eps_nominal"] > 0]
    out["payout_median_30y"] = st.median(payout)
    return out


def spx_cape(raw, rows):
    """
    지금의 CAPE(10년 평균 실질이익 대비 가격)와 실러 계열과의 이음새 확인.

    multpl 실질 EPS 는 2026년 9월 달러이므로, 가격도 같은 달러로 맞춰
    나눕니다. 실러가 공표한 마지막 CAPE(2024-09) 시점에서 같은 방식으로
    계산한 값이 실러 값과 맞는지가 이 방법의 검정입니다.
    """
    by = {r["month"]: r for r in rows}
    cpi = {r["month"]: r["cpi"] for r in rows}
    cpi_all = {ym(r["date"]): r["value"] for r in raw["spx"]["cpi"]["rows"]}
    base = cpi_all[max(cpi_all)]

    def cape_at(m, price_nominal):
        ms = sorted(x for x in by if x <= m)[-120:]
        if len(ms) < 120:
            return None
        avg = st.mean(by[x]["eps_real"] for x in ms)
        k = base / cpi_all[m] if m in cpi_all else 1.0
        return price_nominal * k / avg

    lvl = raw["prices"]["SPX"]["latest"]
    last_e = max(by)
    now = cape_at(last_e, lvl["price"])
    sh = [r for r in raw["shiller"]["rows"] if r["cape"]]
    sh_last = sh[-1]
    ours_then = cape_at(sh_last["date"], sh_last["price"])
    hist = [(r["date"], r["cape"]) for r in sh if r["date"] >= "1950-01"]
    vals = [v for _, v in hist]
    v30 = [v for d_, v in hist if d_ >= shift(sh_last["date"], -30)]
    return {
        "current": now, "eps_window_end": last_e,
        "seam": {"month": sh_last["date"], "shiller": sh_last["cape"],
                 "ours": ours_then,
                 "rel": ours_then / sh_last["cape"] - 1 if ours_then else None},
        "share_below_current_since_1950": pct_rank(vals, now),
        "share_below_current_30y": pct_rank(v30, now),
        "median_since_1950": st.median(vals),
        "median_30y": st.median(v30),
        "max_since_1950": max(hist, key=lambda x: x[1]),
    }


def forward_returns(raw):
    """
    시작 시점의 CAPE 와 그 뒤 10년 실질 총수익률 — 실러 자료만으로.

    모형이 아니라 기록입니다. 1950~2014년의 매달을 시작점으로 잡고, 실러의
    실질 총수익 가격으로 10년 연환산 수익률을 셉니다. 시작점이 겹치므로
    표본 수만큼 독립적인 관측이 아닙니다 — 실제로는 약 6~7개 10년 구간의
    정보입니다.
    """
    rows = [r for r in raw["shiller"]["rows"]
            if r["real_tr_price"] and r["date"] >= "1950-01"]
    idx = {r["date"]: r for r in rows}
    obs = []
    for r in rows:
        m1 = shift(r["date"], 10)
        if r["cape"] and m1 in idx:
            obs.append({"month": r["date"], "cape": r["cape"],
                        "fwd10_real": (idx[m1]["real_tr_price"]
                                       / r["real_tr_price"]) ** 0.1 - 1})
    obs.sort(key=lambda x: x["cape"])
    n = len(obs)
    buckets = []
    for i, (lo, hi) in enumerate(((0, .2), (.2, .4), (.4, .6), (.6, .8),
                                  (.8, 1.0))):
        part = obs[int(n * lo):int(n * hi)]
        fr = [x["fwd10_real"] for x in part]
        buckets.append({
            "quintile": i + 1,
            "cape_from": part[0]["cape"], "cape_to": part[-1]["cape"],
            "months": len(part),
            "fwd10_real_median": st.median(fr),
            "fwd10_real_min": min(fr), "fwd10_real_max": max(fr),
            "share_negative": sum(x < 0 for x in fr) / len(fr),
        })
    top = [x for x in obs if x["cape"] >= 30]
    return {"from": obs and min(x["month"] for x in obs),
            "to": obs and max(x["month"] for x in obs),
            "months": n, "buckets": buckets,
            "cape_30_plus": {
                "months": len(top),
                "fwd10_real_median": st.median(x["fwd10_real"] for x in top)
                if top else None,
                "fwd10_real_max": max((x["fwd10_real"] for x in top),
                                      default=None),
                "periods": sorted({x["month"][:4] for x in top})}}


# ---------------------------------------------------------------- 나스닥100
def ndx_aggregate(raw):
    cs = [c for c in raw["ndx_constituents"]
          if "market_cap" in c and not c.get("error")
          and not c.get("duplicate_of")]
    excluded = [c for c in raw["ndx_constituents"]
                if c.get("error") and not c.get("duplicate_of")]
    M = sum(c["market_cap"] for c in cs)
    NI = sum(c["net_income_usd"] for c in cs)
    NP = sum(c["nopat_usd"] for c in cs)
    EQ = sum(c["equity_usd"] for c in cs if c.get("equity_usd"))
    NI_eq = sum(c["net_income_usd"] for c in cs if c.get("equity_usd"))
    NP_eq = sum(c["nopat_usd"] for c in cs if c.get("equity_usd"))
    lvl = raw["prices"]["NDX"]["latest"]["price"]
    for c in cs:
        c["weight"] = c["market_cap"] / M
        c["mtm_gap"] = c["net_income_usd"] - c["nopat_usd"]
    annualised = [c for c in cs if "연율화" in c["earnings_method"]]
    M_ann = sum(c["market_cap"] for c in annualised)
    NP_ann = sum(c["nopat_usd"] for c in annualised)
    losers = [c for c in cs if c["net_income_usd"] < 0]
    top = sorted(cs, key=lambda c: -c["market_cap"])
    gaps = sorted(cs, key=lambda c: -abs(c["mtm_gap"]))
    return {
        "constituents": len(cs), "excluded": [
            {"symbol": c["symbol"], "why": c["error"]} for c in excluded],
        "market_cap": M, "net_income": NI, "nopat": NP, "equity": EQ,
        "pe_net_income": M / NI, "pe_nopat": M / NP,
        "earnings_yield_nopat": NP / M,
        "roe_net_income": NI_eq / EQ, "roe_nopat": NP_eq / EQ,
        "earnings_per_point_net_income": lvl * NI / M,
        "earnings_per_point_nopat": lvl * NP / M,
        "mtm_gap_total": NI - NP,
        "annualised": [{"symbol": c["symbol"], "weight": c["weight"],
                        "method": c["earnings_method"]} for c in annualised],
        "pe_nopat_excluding_annualised": (M - M_ann) / (NP - NP_ann),
        "loss_makers": [{"symbol": c["symbol"], "weight": c["weight"],
                         "net_income": c["net_income_usd"]} for c in losers],
        "pe_nopat_profitable_only": (
            sum(c["market_cap"] for c in cs if c["nopat_usd"] > 0)
            / sum(c["nopat_usd"] for c in cs if c["nopat_usd"] > 0)),
        "top": [{"symbol": c["symbol"], "name": c["name"],
                 "weight": c["weight"], "market_cap": c["market_cap"],
                 "net_income": c["net_income_usd"], "nopat": c["nopat_usd"],
                 "pe_nopat": (c["market_cap"] / c["nopat_usd"]
                              if c["nopat_usd"] > 0 else None),
                 "method": c["earnings_method"],
                 "period_end": c["earnings_period_end"]} for c in top[:15]],
        "top10_weight": sum(c["weight"] for c in top[:10]),
        "largest_mtm_gaps": [{"symbol": c["symbol"],
                              "net_income": c["net_income_usd"],
                              "nopat": c["nopat_usd"],
                              "gap": c["mtm_gap"]} for c in gaps[:6]],
        "foreign_currency": [{"symbol": c["symbol"],
                              "currency": c["currency"],
                              "fx_usd": c["fx_usd"]}
                             for c in cs if c["currency"] != "USD"],
        "ads": [{"symbol": c["symbol"], "ratio": c["ads_ratio"],
                 "evidence": c["ads"]["evidence"]}
                for c in cs if c.get("ads")],
        "splits": [{"symbol": c["symbol"], "splits": c["splits"],
                    "multiplier": c["split_multiplier"]}
                   for c in cs if c.get("splits")],
        "constituent_rows": [
            {k: c.get(k) for k in (
                "symbol", "name", "weight", "market_cap", "net_income_usd",
                "nopat_usd", "equity_usd", "earnings_method",
                "earnings_period_end", "nopat_basis", "currency",
                "shares_source", "split_multiplier", "ads_ratio", "pe")}
            for c in top],
    }


def price_record(raw, key):
    pm = {ym(r["date"]): r["close"] for r in raw["prices"][key]["monthly"]["rows"]}
    last = max(pm)
    out = {}
    for n in WINDOWS:
        m0 = shift(last, -n)
        if m0 in pm:
            out[str(n)] = {"from": m0, "to": last, "from_level": pm[m0],
                           "to_level": pm[last],
                           "cagr": cagr(pm[m0], pm[last], n)}
    # 최대 낙폭(월말 기준, 30년)
    start = shift(last, -30)
    peak, worst = None, (0.0, None, None)
    for m in sorted(pm):
        if m < start:
            continue
        if peak is None or pm[m] > peak[1]:
            peak = (m, pm[m])
        dd = pm[m] / peak[1] - 1
        if dd < worst[0]:
            worst = (dd, peak[0], m)
    out["max_drawdown_30y"] = {"drawdown": worst[0], "peak": worst[1],
                               "trough": worst[2]}
    return out


def implied_return(base_earn, level, inc_return, g, fade_to, terminal):
    """
    지금 지수 수준에서 사면 그 성장률이 실현될 때 연 몇 %를 버는가 — 가치가
    지수와 같아지는 할인율. 성장률 쪽으로 푸는 '요구 성장률'의 짝입니다.
    터미널 성장률보다 높은 범위에서만 찾습니다(그 아래는 발산).
    """
    lo, hi = terminal + 1e-4, 0.40

    def v(r):
        return dcf(base_earn, 0.0, 1.0, g, fade_to, inc_return, r,
                   terminal)["value_per_share"]
    if v(hi) > level or v(lo) < level:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if v(mid) > level:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def spx_backtest(raw, rows, roe, terminal, base_rate_real, infl):
    """
    같은 규칙을 지난 30년의 매달에 적용했다면 언제가 매수 구간이었나.

    그 달의 12개월 EPS, 그 달의 30년 국채 + 3%p, 그 달까지의 30년 EPS 기록
    (성장률 가정)으로 가치를 내고, 안전마진 30% 매수 상한과 그 달 지수를
    비교합니다. 단순화가 둘 있습니다 — ROE 는 전 기간 중위값 하나, 터미널
    성장률은 지금의 기대인플레이션 하나로 고정했습니다(1990년대의 기대
    인플레이션 기록이 이 환경에서 닿지 않습니다). 그래서 이 표는 '그때의
    판단'이 아니라 '지금의 잣대를 그때에 댄 결과'입니다.

    매수 구간에 샀을 때와 아닐 때의 뒤 10년 실질 총수익률은 실러 자료로
    셉니다(2024-09 까지라 시작점은 2014년까지).
    """
    by = {r["month"]: r for r in rows}
    tyx = {ym(r["date"]): r["close"] / 100
           for r in raw["prices"]["TYX"]["monthly"]["rows"]}
    sh = {r["date"]: r for r in raw["shiller"]["rows"] if r["real_tr_price"]}
    last = max(m for m in by if by[m].get("price"))
    start = shift(last, -30)
    out = []
    for m in sorted(by):
        r = by[m]
        if m < start or not r.get("price") or m not in tyx:
            continue
        m30 = shift(m, -30)
        if m30 not in by or r["eps_nominal"] <= 0:
            continue
        own = cagr(by[m30]["eps_nominal"], r["eps_nominal"], 30)
        k = tyx[m] + 0.03
        rec = {"month": m, "price": r["price"], "eps": r["eps_nominal"],
               "discount": k, "own30": own}
        for key, g, fade in (("base", base_rate_real + infl, infl),
                             ("own30", min(own, CAP_GROWTH), 0.045)):
            v = dcf(r["eps_nominal"], 0.0, 1.0, g, fade, roe, k, terminal)
            rec[f"value_{key}"] = (None if v["diverges"]
                                   else v["value_per_share"])
        rec["buy30_own30"] = (rec["value_own30"] * 0.7
                              if rec["value_own30"] else None)
        rec["below_buy30"] = bool(rec["buy30_own30"]
                                  and r["price"] <= rec["buy30_own30"])
        rec["below_value"] = bool(rec["value_own30"]
                                  and r["price"] <= rec["value_own30"])
        m10 = shift(m, 10)
        if m in sh and m10 in sh:
            rec["fwd10_real"] = (sh[m10]["real_tr_price"]
                                 / sh[m]["real_tr_price"]) ** 0.1 - 1
        out.append(rec)

    def summary(sel):
        fr = [x["fwd10_real"] for x in sel if "fwd10_real" in x]
        return {"months": len(sel),
                "with_forward": len(fr),
                "fwd10_real_median": st.median(fr) if fr else None}
    below = [x for x in out if x["below_buy30"]]
    below_v = [x for x in out if x["below_value"]]
    above = [x for x in out if not x["below_value"]]
    runs, cur = [], None
    for x in out:
        if x["below_value"]:
            if cur and shift(cur["to"], 0) and _next(cur["to"]) == x["month"]:
                cur["to"] = x["month"]
                cur["months"] += 1
                cur["min_ratio"] = min(cur["min_ratio"],
                                       x["price"] / x["value_own30"])
            else:
                cur = {"from": x["month"], "to": x["month"], "months": 1,
                       "min_ratio": x["price"] / x["value_own30"]}
                runs.append(cur)
    return {"from": out[0]["month"] if out else None,
            "to": out[-1]["month"] if out else None,
            "months": len(out),
            "roe": roe, "terminal": terminal,
            "below_buy30": summary(below),
            "below_value": summary(below_v),
            "above_value": summary(above),
            "runs_below_value": runs,
            "rows": [{k: x.get(k) for k in (
                "month", "price", "value_base", "value_own30",
                "buy30_own30", "discount", "below_buy30", "below_value",
                "fwd10_real")} for x in out]}


def _next(m):
    y, mo = int(m[:4]), int(m[5:7])
    return f"{y + (mo == 12):04d}-{(mo % 12) + 1:02d}"


# 버핏이 '지수'에 대해 직접 쓴 문장. 받은 원문과 **대조해 통과해야** 씁니다.
# 이 보고서의 숫자(안전마진 매수선)와 그의 처방(나눠 사기)이 다르다는 점을
# 함께 보여 주는 것이 이 구절들의 역할입니다.
INDEX_LETTERS = {
    1993: "https://www.berkshirehathaway.com/letters/1993.html",
    2013: "https://www.berkshirehathaway.com/letters/2013ltr.pdf",
}
INDEX_PASSAGES = [
    {"key": "space_out", "year": 1993, "kind": "1차 (주주서한)",
     "title": "지수는 나눠서 산다",
     "quotes": [
         "That investor should both own a large number of equities and "
         "space out his purchases.",
         "By periodically investing in an index fund, for example, the "
         "know-nothing investor can actually out-perform most investment "
         "professionals."],
     "why": ("기업을 분석하지 않는 투자자에게 버핏의 처방은 '안전마진이 생길 "
             "때까지 기다려라'가 아니라 **나눠서 사라**입니다. 지수에는 한 "
             "번의 진입 가격보다 진입 시점의 분산이 먼저입니다.")},
    {"key": "exuberance", "year": 2013, "kind": "1차 (주주서한)",
     "title": "가장 큰 위험은 들뜬 시점에 들어가는 것",
     "quotes": [
         "The main danger is that the timid or beginning investor will "
         "enter the market at a time of extreme exuberance and then become "
         "disillusioned when paper losses occur.",
         "The antidote to that kind of mistiming is for an investor to "
         "accumulate shares over a long period and never to sell when the "
         "news is bad and stocks are well off their highs."],
     "why": ("같은 처방을 20년 뒤에 다시 적었습니다. 그리고 위험을 명시합니다 — "
             "'극단적 들뜸'의 시점에 들어가는 것. 그 시점을 재는 잣대가 이 "
             "보고서의 CAPE·P/E 위치와 요구 성장률입니다.")},
    {"key": "will", "year": 2013, "kind": "1차 (주주서한)",
     "title": "자기 유언장의 지시",
     "quotes": [
         "Put 10% of the cash in short-term government bonds and 90% in a "
         "very low-cost S&P 500 index fund."],
     "why": ("버핏 자신의 유언 지시입니다. 지수를 '언젠가 싸지면'이 아니라 "
             "기본 자산으로 둡니다. 다만 이건 상속 자금의 장기 배분이고, "
             "가격과 무관하게 한 번에 사라는 말은 아닙니다 — 같은 서한이 "
             "바로 앞에서 나눠 사라고 적습니다.")},
]


def verify_passages(refresh=False):
    """원문을 받아 각 인용문이 **문장 전체로** 들어 있는지 확인합니다."""
    import html as _html
    import re
    import subprocess
    import sec_cache
    texts = {}
    for year, url in INDEX_LETTERS.items():
        pdf = url.endswith(".pdf")
        p, _, _ = sec_cache.fetch(
            url, os.path.join(HERE, "idx", "cache", f"brk_{year}"
                              + (".pdf" if pdf else ".html")),
            max_age_days=365, refresh=refresh, min_bytes=20000, binary=pdf)
        if pdf:
            t = subprocess.run(["pdftotext", "-layout", p, "-"],
                               capture_output=True, check=True,
                               text=True).stdout
        else:
            t = _html.unescape(re.sub(r"<[^>]+>", " ",
                                      open(p, errors="ignore").read()))
        t = (t.replace("\u201c", '"').replace("\u201d", '"')
             .replace("\u2019", "'").replace("\u2018", "'"))
        texts[year] = re.sub(r"\s+", " ", t)
    out = []
    for ps in INDEX_PASSAGES:
        for q in ps["quotes"]:
            # 서한은 줄 끝에서 하이픈 뒤에 공백을 남깁니다("know- nothing").
            # 공백과 하이픈 뒤 공백만 느슨하게 보고, 단어는 그대로 대조합니다.
            pat = (re.escape(q).replace(r"\ ", r"[\s-]*")
                   .replace(r"\-", r"-\s*"))
            if not re.search(pat, texts[ps["year"]]):
                raise SystemExit(f"{ps['year']} 서한에서 인용문을 찾지 "
                                 f"못했습니다: {q[:70]}…")
        out.append({**ps, "source_url": INDEX_LETTERS[ps["year"]],
                    "verified": len(ps["quotes"])})
    return out


# ---------------------------------------------------------------- 공통
def growth_options(own30, own10, infl, base_rate_median, label_own, kind):
    med_nom = base_rate_median + infl
    opts = [
        {"key": "base_rate_median", "growth": med_nom, "fade_to": infl,
         "label": f"기초율 중위 {med_nom:.1%}",
         "basis": (f"매출 $50십억 초과 기업의 10년 순이익 CAGR 중위 "
                   f"{base_rate_median:.1%}(실질) + 기대인플레이션 "
                   f"{infl:.2%}. 지수가 '평범한 대형 기업'처럼 성장한다는 가정.")},
        {"key": "half_of_own", "growth": min(own30 / 2, CAP_GROWTH),
         "fade_to": 0.035,
         "label": f"{label_own}의 절반 {min(own30 / 2, CAP_GROWTH):.1%}",
         "basis": f"{label_own} {own30:.1%}의 절반 — 중립 시나리오의 규칙."},
        {"key": "own_sustained", "growth": min(own30, CAP_GROWTH),
         "fade_to": 0.045,
         "label": f"{label_own} 유지 {min(own30, CAP_GROWTH):.1%}",
         "basis": f"{label_own} {own30:.1%}가 그대로 이어진다는 가정."},
        {"key": "recent_10y", "growth": min(own10, CAP_GROWTH),
         "fade_to": 0.045,
         "label": f"최근 10년 유지 {min(own10, CAP_GROWTH):.1%}",
         "basis": (f"최근 10년 속도 {own10:.1%}가 이어진다는 가정 — "
                   f"가장 관대한 경우." + (" 나스닥100 은 이익 기록이 없어 "
                                         "가격 상승률을 씁니다 — 이익 성장 "
                                         "+ 밸류에이션 변화가 섞인 값입니다."
                                         if kind == "price" else ""))},
    ]
    return opts


def grid_for(base_earn, level, inc_return, options, discounts, terminal):
    """
    지수 1포인트당 가치. 지수에는 순현금 항이 없고(이익이 이미 자기자본
    주주의 몫이므로), '주식수'는 1(지수 1포인트)입니다.
    """
    rows = []
    for g in options:
        row = {**g, "cells": [],
               "implied_return": implied_return(base_earn, level, inc_return,
                                                g["growth"], g["fade_to"],
                                                terminal)}
        for d in discounts:
            r = dcf(base_earn, 0.0, 1.0, g["growth"], g["fade_to"],
                    inc_return, d["rate"], terminal)
            cell = {"discount_key": d["key"], "discount": d["rate"]}
            if r["diverges"]:
                cell.update({"diverges": True, "why": r["why"]})
            else:
                v = r["value_per_share"]
                cell.update({
                    "diverges": False, "value": v,
                    "upside_vs_level": v / level - 1,
                    "terminal_share": r["terminal_share"],
                    "nopat_cagr_10y": r["nopat_cagr_10y"],
                    "buy_level": {f"{int(m * 100)}%": v * (1 - m)
                                  for m in MARGINS},
                    "pass": {f"{int(m * 100)}%": v * (1 - m) > level
                             for m in MARGINS},
                    # 매수선이 지금 지수보다 몇 % 아래(위)인가 — 거기까지
                    # 얼마나 내려와야 하는지.
                    "buy_vs_level": {f"{int(m * 100)}%":
                                     v * (1 - m) / level - 1
                                     for m in MARGINS}})
            row["cells"].append(cell)
        # 그 가격에 샀을 때의 기대수익률 — 지금 지수뿐 아니라 버핏 기준 가치와
        # 안전마진 30% 매수선에 샀을 때도. 가치에 산 경우는 정의상 할인율과
        # 같아야 하지만, 하드코딩하지 않고 같은 풀이로 계산해 그 사실을
        # 검산합니다(검증기가 할인율과 대조).
        bc = next((c for c in row["cells"]
                   if c["discount_key"] == "bond30_plus3"
                   and not c.get("diverges")), None)
        if bc:
            row["returns_at"] = {
                "discount_key": "bond30_plus3",
                "value_price": bc["value"],
                "buy30_price": bc["buy_level"]["30%"],
                "value": implied_return(base_earn, bc["value"], inc_return,
                                        g["growth"], g["fade_to"], terminal),
                "buy30": implied_return(base_earn, bc["buy_level"]["30%"],
                                        inc_return, g["growth"],
                                        g["fade_to"], terminal),
            }
        rows.append(row)
    return rows


def required_growth(base_earn, level, inc_return, discounts, terminal,
                    br_bands, infl):
    out = []
    for d in discounts:
        for m in MARGINS:
            target = level / (1 - m)

            def val(g):
                r = dcf(base_earn, 0.0, 1.0, g, SOLVE_FADE_TO, inc_return,
                        d["rate"], terminal)
                return None if r["diverges"] else r
            rec = {"discount_key": d["key"], "discount": d["rate"],
                   "margin": m, "target_level": target}
            hi = inc_return * 0.9995
            v_hi = val(hi)
            if v_hi is None:
                rec.update({"reachable": False, "why": "발산"})
                out.append(rec)
                continue
            if v_hi["value_per_share"] < target:
                rec.update({"reachable": False,
                            "ceiling_level": v_hi["value_per_share"]})
                out.append(rec)
                continue
            lo = -0.5
            for _ in range(200):
                mid = (lo + hi) / 2
                v = val(mid)
                if v is None or v["value_per_share"] < target:
                    lo = mid
                else:
                    hi = mid
            v = val(hi)
            rec.update({
                "reachable": True, "growth_year1": hi,
                "nopat_cagr_10y": v["nopat_cagr_10y"],
                "cagr_real": v["nopat_cagr_10y"] - infl,
                "base_rate_percentile": percentile_of(
                    br_bands, v["nopat_cagr_10y"] - infl),
                "value_check": v["value_per_share"]})
            out.append(rec)
    return out


def main():
    raw = json.load(open(RAW, encoding="utf-8"))
    bs = json.load(open(BS, encoding="utf-8"))
    print(f"오늘 {date.today().isoformat()} 기준 · 수집 {raw['generated']}")
    infl = raw["macro"]["breakeven_inflation_10y"]["rate"]
    br = bs["base_rates"]
    r30 = raw["macro"]["treasury_30y"]["rate"]
    discounts = [
        {"key": "bond30", "rate": r30, "label": f"30년 국채 {r30:.2%}"},
        {"key": "bond30_plus3", "rate": r30 + 0.03,
         "label": f"30년 국채 + 3%p = {r30 + 0.03:.2%}"},
        {"key": "project10", "rate": 0.10, "label": "프로젝트 기준 10%"},
        {"key": "project11", "rate": 0.11, "label": "프로젝트 보수 11%"},
    ]
    terminal = infl

    # --------------------------------------------------------- S&P 500
    rows, base_m, base_cpi = spx_series(raw)
    xc = spx_crosschecks(raw, rows)
    rec = spx_record(raw, rows)
    cape = spx_cape(raw, rows)
    fwd = forward_returns(raw)
    lvl = raw["prices"]["SPX"]["latest"]
    by = {r["month"]: r for r in rows}
    eps_now = by[rec["eps_as_of"]]["eps_nominal"]
    roe = min(rec["roe"]["median"], CAP_RETURN)
    w30, w10 = rec["windows"]["30"], rec["windows"]["10"]
    spx_opts = growth_options(w30["eps_cagr_nominal"],
                              w10["eps_cagr_nominal"], infl, br["net_income_10y"]["median"],
                              "30년 EPS 기록", "eps")
    spx = {
        "label": "S&P 500", "level": lvl,
        "earnings": {"basis": "S&P 보고 기준 EPS (12개월 누적, 명목)",
                     "eps_nominal": eps_now, "as_of": rec["eps_as_of"],
                     "eps_real": by[rec["eps_as_of"]]["eps_real"],
                     "cpi_base_month": base_m, "cpi_base": base_cpi,
                     "pe_now": lvl["price"] / eps_now,
                     "earnings_yield": eps_now / lvl["price"]},
        "incremental_return": roe,
        "incremental_return_basis": (
            f"ROE(EPS ÷ 주당장부가치) {rec['roe']['from']}~{rec['roe']['to']} "
            f"분기 {rec['roe']['quarters']}개의 중위값"),
        "record": rec, "crosschecks": xc, "cape": cape,
        "forward_returns": fwd,
        "series": [{k: r.get(k) for k in ("month", "price", "eps_nominal",
                                          "eps_real", "pe", "roe")}
                   for r in rows if r["month"] >= shift(rec["eps_as_of"], -31)],
    }
    spx["grid"] = grid_for(eps_now, lvl["price"], roe, spx_opts, discounts,
                           terminal)
    # ROE 를 바꿔도 판정이 바뀌는가 — 전 기간 중위, 최근 10년 중위, 최신,
    # 그리고 상한. 버핏 기준 할인율에서 봅니다.
    roe_hist = [(r["month"], r["roe"]) for r in rows if r.get("roe")]
    last_roe_m = roe_hist[-1][0]
    roe10 = st.median(v for m_, v in roe_hist
                      if m_ >= shift(last_roe_m, -10))
    bd = next(x for x in discounts if x["key"] == "bond30_plus3")
    sens = []
    for lab, rv in (("전 기간 중위", roe), ("최근 10년 중위", roe10),
                    ("최신 분기", roe_hist[-1][1]), ("상한", CAP_RETURN)):
        rv = min(rv, CAP_RETURN)
        cells = []
        for g in spx_opts:
            v = dcf(eps_now, 0.0, 1.0, g["growth"], g["fade_to"], rv,
                    bd["rate"], terminal)["value_per_share"]
            cells.append({"growth_key": g["key"], "value": v,
                          "buy30": v * 0.7, "pass0": v > lvl["price"]})
        sens.append({"label": lab, "roe": rv, "cells": cells})
    spx["roe_sensitivity"] = sens
    spx["backtest"] = spx_backtest(raw, rows, roe, terminal,
                                   br["net_income_10y"]["median"], infl)
    spx["required"] = required_growth(eps_now, lvl["price"], roe, discounts,
                                      terminal, br["net_income_10y"]["bands"],
                                      infl)
    print(f"  S&P 500 {lvl['price']:,.2f} · EPS {eps_now:,.2f} "
          f"({rec['eps_as_of']}) · P/E {lvl['price'] / eps_now:.1f} · ROE "
          f"{roe:.1%} · 30년 EPS CAGR {w30['eps_cagr_nominal']:.2%}")

    # ------------------------------------------------------- 나스닥100
    agg = ndx_aggregate(raw)
    nlvl = raw["prices"]["NDX"]["latest"]
    prc = price_record(raw, "NDX")
    nroe = min(agg["roe_nopat"], CAP_RETURN)
    p30 = prc["30"]["cagr"]
    p10 = prc["10"]["cagr"]
    # 나스닥100 에는 30년 이익 기록이 없습니다. 성장률 가정의 '자기 기록'
    # 자리에 S&P 500 의 30년 EPS 기록을 쓰되(미국 대형주 참조군), 가장 관대한
    # 가정 하나는 나스닥100 의 10년 가격 상승률로 둡니다 — 이익 성장과
    # 밸류에이션 변화가 섞인 값이라는 것을 표에 적습니다.
    ndx_opts = growth_options(w30["eps_cagr_nominal"], p10, infl,
                              br["net_income_10y"]["median"],
                              "S&P 500 30년 EPS 기록", "price")
    base_n = agg["earnings_per_point_nopat"]
    ndx = {
        "label": "나스닥100", "level": nlvl,
        "earnings": {"basis": ("구성종목 NOPAT 합 ÷ 시가총액 합 × 지수 "
                               "(SEC 공시에서 직접 집계)"),
                     "per_point_nopat": base_n,
                     "per_point_net_income": agg["earnings_per_point_net_income"],
                     "pe_now": agg["pe_nopat"],
                     "pe_net_income": agg["pe_net_income"]},
        "incremental_return": nroe,
        "incremental_return_basis": (
            f"구성종목 NOPAT 합 ÷ 자기자본 합 = {agg['roe_nopat']:.1%}"
            + (f" (상한 {CAP_RETURN:.0%} 적용)"
               if agg["roe_nopat"] > CAP_RETURN else "")),
        "aggregate": agg, "price_record": prc,
        "ishares": raw["ishares"]["NDX"],
    }
    ndx["grid"] = grid_for(base_n, nlvl["price"], nroe, ndx_opts, discounts,
                           terminal)
    bd = next(x for x in discounts if x["key"] == "bond30_plus3")
    sens = []
    for lab, rv in (("구성종목 집계 (NOPAT÷자본)", nroe),
                    ("S&P 500 전 기간 중위", roe), ("상한", CAP_RETURN)):
        rv = min(rv, CAP_RETURN)
        cells = []
        for g in ndx_opts:
            v = dcf(base_n, 0.0, 1.0, g["growth"], g["fade_to"], rv,
                    bd["rate"], terminal)["value_per_share"]
            cells.append({"growth_key": g["key"], "value": v,
                          "buy30": v * 0.7, "pass0": v > nlvl["price"]})
        sens.append({"label": lab, "roe": rv, "cells": cells})
    ndx["roe_sensitivity"] = sens
    ndx["required"] = required_growth(base_n, nlvl["price"], nroe, discounts,
                                      terminal,
                                      br["net_income_10y"]["bands"], infl)
    # 순이익 기준으로 바꾸면 무엇이 달라지는가(민감도).
    ndx["grid_net_income"] = grid_for(
        agg["earnings_per_point_net_income"], nlvl["price"],
        min(agg["roe_net_income"], CAP_RETURN), ndx_opts, discounts,
        terminal)
    print(f"  나스닥100 {nlvl['price']:,.2f} · P/NOPAT {agg['pe_nopat']:.1f} "
          f"· P/E(순이익) {agg['pe_net_income']:.1f} · iShares "
          f"{raw['ishares']['NDX']['pe']} · ROE {nroe:.1%}")
    spx["price_record"] = price_record(raw, "SPX")

    out = {
        "generated": date.today().isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "collected": raw["generated"],
        "macro": raw["macro"], "discounts": discounts, "terminal": terminal,
        "margins": MARGINS, "solve_fade_to": SOLVE_FADE_TO,
        "cap_growth": CAP_GROWTH, "cap_return": CAP_RETURN,
        "base_rates": br, "buffett": bs["buffett"],
        "index_passages": verify_passages(),
        "spx": spx, "ndx": ndx,
        "sources": {
            "multpl": "https://www.multpl.com/",
            "shiller": raw["shiller"]["source_url"],
            "ishares_spx": raw["ishares"]["SPX"]["source_url"],
            "ishares_ndx": raw["ishares"]["NDX"]["source_url"],
            "ndx_members": raw["ndx_members"]["source_page"],
            "sec": "https://www.sec.gov/edgar/sec-api-documentation",
        },
        "ishares_spx": raw["ishares"]["SPX"],
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(f"wrote {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
