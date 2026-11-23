"""
index.json 검증 — S&P 500·나스닥100 판정.

- **항등식.** 격자·요구 성장률·기대수익률을 DCF 를 **독립 재구현**해 다시
  계산하고, 나스닥100 집계(Σ시가총액·Σ이익·P/E·지수 1포인트당 이익)를
  구성종목 행에서 다시 더합니다. 실질→명목 환산도 표본 달에서 재계산합니다.
- **두 출처 대조(트립와이어).** multpl 을 명목으로 되돌린 EPS 가 실러의
  명목 EPS 와 맞는지, 우리 P/E 가 multpl 이 공표한 P/E 와 맞는지, 우리 CAPE
  가 실러의 마지막 CAPE 와 이어지는지, 나스닥100 집계 P/E 가 iShares 공표치와
  같은 자릿수인지.
- **앵커.** 원 출처에서 손으로 읽은 값 — 지수 종가, multpl 의 EPS·CPI·장부
  가치, 실러의 EPS·CAPE, iShares P/E, 그리고 SEC 공시의 구성종목 수치
  (마이크론 12개월 순이익, 엔비디아 영업이익·세율, 샌디스크 분할, PDD ADS
  비율). 항등식은 같은 데이터로 계산되므로 틀린 데이터를 통과시킵니다.

    python3 verify_index.py
    python3 verify_index.py --mutate
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "idx", "index.json")
RAW = os.path.join(HERE, "idx", "index_raw.json")
BN = 1e9
YEARS = 10

# ---- 원 출처에서 손으로 읽은 값 -------------------------------------------
ANCHOR = {
    # Yahoo Finance, 2026-11-20 종가
    "spx_close": (6910.39, "2026-11-20"),
    "ndx_close": (25028.98, "2026-11-20"),
    # multpl.com — EPS 는 실질(2026년 9월 달러), 장부가치는 명목
    "multpl_eps_real_2026_06": 298.03,
    "multpl_cpi_2026_09": 336.94,
    "multpl_bv_2025_09": 1270.32,
    # 실러 ie_data.xls
    "shiller_e_2024_06": 196.76,
    "shiller_cape_2024_09": 35.2288,
    # iShares 펀드 페이지 (2026-11-19 기준)
    "ishares_ivv_pe": 27.49, "ishares_cndx_pe": 31.10,
    # SEC 공시 (companyfacts)
    "mu_ttm_net_income": 84.969e9,           # FY2026 10-K, 2026-09-03 결산
    "nvda_ttm_operating_income": 197.579e9,  # 2025-10-26~2026-07-26 4개 분기
    "nvda_tax_rate": 36.865 / 229.744,       # 법인세 ÷ 세전이익, 같은 4개 분기
    "sndk_split": 8.0,                       # 2026-11-20 8:1 분할
    "pdd_ads_ratio": 4,                      # 20-F: ADS 1주 = 보통주 4주
    "ndx_members": 101,
}
GROWTH_KEYS = ["base_rate_median", "half_of_own", "own_sustained",
               "recent_10y"]
DISCOUNT_KEYS = ["bond30", "bond30_plus3", "project10", "project11"]


class Checks:
    def __init__(self):
        self.passed, self.failures = 0, []

    def eq(self, name, got, want, tol=0.0, rel=None):
        if got is None or want is None:
            self.failures.append(f"{name}: 값 없음 ({got!r} / {want!r})")
            return False
        lim = tol if rel is None else max(tol, abs(want) * rel)
        if abs(got - want) <= lim:
            self.passed += 1
            return True
        self.failures.append(f"{name}: {got:,.6g} != {want:,.6g} "
                             f"(허용 {lim:,.4g})")
        return False

    def same(self, name, got, want):
        if got == want:
            self.passed += 1
            return True
        self.failures.append(f"{name}: {got!r} != {want!r}")
        return False

    def true(self, name, cond, detail=""):
        if cond:
            self.passed += 1
            return True
        self.failures.append(f"{name}: 거짓 {detail}")
        return False


def dcf(e0, growth, fade_to, inc, k, tg, years=YEARS):
    """엔진과 독립으로 다시 쓴 같은 모형(지수: 순현금 0, 주식수 1)."""
    if tg >= k:
        return None
    pv, e = 0.0, e0
    for t in range(1, years + 1):
        g = growth + (fade_to - growth) * (t - 1) / (years - 1)
        e *= (1 + g)
        pv += e * (1 - g / inc) / (1 + k) ** t
    term = e * (1 + tg) * (1 - tg / inc) / (k - tg)
    tpv = term / (1 + k) ** years
    return {"value": pv + tpv, "terminal_share": tpv / (pv + tpv),
            "cagr": (e / e0) ** (1 / years) - 1}


def check_grid(c, tag, X, d):
    lvl = X["level"]["price"]
    base = (X["earnings"]["eps_nominal"] if "eps_nominal" in X["earnings"]
            else X["earnings"]["per_point_nopat"])
    inc, tg = X["incremental_return"], d["terminal"]
    c.same(f"{tag} 성장률 가정 순서", [r["key"] for r in X["grid"]],
           GROWTH_KEYS)
    c.true(f"{tag} 증분 수익률 ≤ 상한", inc <= d["cap_return"] + 1e-12)
    prev_vals = None
    for row in X["grid"]:
        c.true(f"{tag} {row['key']} 성장률 ≤ 상한",
               row["growth"] <= d["cap_growth"] + 1e-12)
        c.same(f"{tag} {row['key']} 할인율 순서",
               [x["discount_key"] for x in row["cells"]], DISCOUNT_KEYS)
        vals = []
        for cell in row["cells"]:
            nm = f"{tag} {row['key']}/{cell['discount_key']}"
            if cell.get("diverges"):
                c.true(f"{nm} 발산은 터미널≥할인율일 때만",
                       tg >= cell["discount"])
                vals.append(None)
                continue
            got = dcf(base, row["growth"], row["fade_to"], inc,
                      cell["discount"], tg)
            c.eq(f"{nm} 가치 재계산", cell["value"], got["value"], rel=1e-9)
            c.eq(f"{nm} 터미널 비중", cell["terminal_share"],
                 got["terminal_share"], rel=1e-9)
            c.eq(f"{nm} 상승여력", cell["upside_vs_level"],
                 cell["value"] / lvl - 1, rel=1e-12)
            for m in d["margins"]:
                k = f"{int(m * 100)}%"
                c.eq(f"{nm} 매수선 {k}", cell["buy_level"][k],
                     cell["value"] * (1 - m), rel=1e-12)
                c.same(f"{nm} 판정 {k}", cell["pass"][k],
                       cell["value"] * (1 - m) > lvl)
            vals.append(cell["value"])
        # 할인율이 오르면 가치는 내려가야 합니다.
        clean = [v for v in vals if v is not None]
        c.true(f"{tag} {row['key']} 할인율↑ → 가치↓",
               all(a > b for a, b in zip(clean, clean[1:])), str(clean))
        # 기대수익률 되넣기
        ir = row["implied_return"]
        if ir is not None:
            back = dcf(base, row["growth"], row["fade_to"], inc, ir, tg)
            c.eq(f"{tag} {row['key']} 기대수익률 되넣기 = 지수",
                 back["value"], lvl, rel=1e-6)
            c.true(f"{tag} {row['key']} 기대수익률 > 터미널", ir > tg)
        prev_vals = vals
    # 요구 성장률
    seen = 0
    for r in X["required"]:
        seen += 1
        nm = f"{tag} 요구 {r['discount_key']}/{int(r['margin'] * 100)}%"
        c.eq(f"{nm} 목표", r["target_level"], lvl / (1 - r["margin"]),
             rel=1e-12)
        if not r["reachable"]:
            if "ceiling_level" in r:
                ceil_ = dcf(base, inc * 0.9995, d["solve_fade_to"], inc,
                            r["discount"], tg)
                c.true(f"{nm} 도달 불가가 사실",
                       ceil_["value"] < r["target_level"])
                c.eq(f"{nm} 천장", r["ceiling_level"], ceil_["value"],
                     rel=1e-9)
            continue
        c.true(f"{nm} 성장률 < 증분 수익률", r["growth_year1"] < inc)
        back = dcf(base, r["growth_year1"], d["solve_fade_to"], inc,
                   r["discount"], tg)
        c.eq(f"{nm} 되넣기 = 목표", back["value"], r["target_level"],
             rel=1e-4)
        c.eq(f"{nm} 10년 CAGR", r["nopat_cagr_10y"], back["cagr"], rel=1e-6)
        c.true(f"{nm} 백분위 0~1", 0 <= r["base_rate_percentile"] <= 1)
    c.same(f"{tag} 요구 성장률 조합 수", seen,
           len(DISCOUNT_KEYS) * len(d["margins"]))


def verify(d, c):
    raw = json.load(open(RAW, encoding="utf-8"))
    s, n = d["spx"], d["ndx"]

    # ------------------------------------------------------------- 앵커
    c.eq("앵커 S&P 500 종가", s["level"]["price"], ANCHOR["spx_close"][0],
         tol=0.005)
    c.same("앵커 S&P 500 종가일", s["level"]["date"], ANCHOR["spx_close"][1])
    c.eq("앵커 나스닥100 종가", n["level"]["price"], ANCHOR["ndx_close"][0],
         tol=0.005)
    c.same("앵커 나스닥100 종가일", n["level"]["date"], ANCHOR["ndx_close"][1])
    c.true("앵커 종가 (장중 아님)",
           not s["level"]["is_intraday"] and not n["level"]["is_intraday"])
    c.eq("앵커 multpl 실질 EPS 2026-06", s["earnings"]["eps_real"],
         ANCHOR["multpl_eps_real_2026_06"], tol=0.005)
    c.same("앵커 EPS 기준 달", s["earnings"]["as_of"], "2026-06")
    c.eq("앵커 multpl CPI 기준(2026-09)", s["earnings"]["cpi_base"],
         ANCHOR["multpl_cpi_2026_09"], tol=0.005)
    c.same("앵커 CPI 기준 달 = 페이지 문구의 2026년 9월",
           s["earnings"]["cpi_base_month"], "2026-09")
    bv = {r["date"][:7]: r["value"]
          for r in raw["spx"]["book_value"]["rows"]}
    c.eq("앵커 multpl 장부가치 2025-09", bv.get("2025-09"),
         ANCHOR["multpl_bv_2025_09"], tol=0.005)
    sh = {r["date"]: r for r in raw["shiller"]["rows"]}
    c.eq("앵커 실러 EPS 2024-06", sh["2024-06"]["earnings"],
         ANCHOR["shiller_e_2024_06"], tol=0.005)
    c.eq("앵커 실러 CAPE 2024-09", s["cape"]["seam"]["shiller"],
         ANCHOR["shiller_cape_2024_09"], tol=0.0005)
    c.eq("앵커 iShares IVV P/E", d["ishares_spx"]["pe"],
         ANCHOR["ishares_ivv_pe"], tol=0.005)
    c.eq("앵커 iShares CNDX P/E", n["ishares"]["pe"],
         ANCHOR["ishares_cndx_pe"], tol=0.005)
    c.same("앵커 나스닥100 구성종목 수",
           len(raw["ndx_members"]["members"]), ANCHOR["ndx_members"])
    rows = {r["symbol"]: r for r in raw["ndx_constituents"]}
    c.eq("앵커 마이크론 12개월 순이익", rows["MU"]["net_income_usd"],
         ANCHOR["mu_ttm_net_income"], rel=1e-6)
    c.eq("앵커 엔비디아 12개월 영업이익", rows["NVDA"]["operating_income_usd"],
         ANCHOR["nvda_ttm_operating_income"], rel=1e-6)
    c.eq("앵커 엔비디아 실효세율", rows["NVDA"]["effective_tax_rate"],
         ANCHOR["nvda_tax_rate"], rel=1e-6)
    c.eq("앵커 샌디스크 분할 배수", rows["SNDK"]["split_multiplier"],
         ANCHOR["sndk_split"], tol=0)
    c.same("앵커 PDD ADS 비율", rows["PDD"]["ads_ratio"],
           ANCHOR["pdd_ads_ratio"])
    c.true("앵커 PDD ADS 문구가 20-F 에 있음",
           "four Class A ordinary shares" in rows["PDD"]["ads"]["evidence"])
    c.same("알파벳 두 종목은 한 번만", rows["GOOGL"].get("duplicate_of"),
           "GOOG")

    # ----------------------------------------------- 두 출처 대조 (S&P 500)
    xc = s["crosschecks"]
    c.true("대조 multpl 명목 EPS ↔ 실러: 중위 오차 < 0.5%",
           xc["eps_vs_shiller"]["median_abs_rel"] < 0.005,
           f"{xc['eps_vs_shiller']['median_abs_rel']:.4f}")
    c.true("대조 multpl 명목 EPS ↔ 실러: 최대 오차 < 2%",
           abs(xc["eps_vs_shiller"]["worst"]["rel"]) < 0.02,
           str(xc["eps_vs_shiller"]["worst"]))
    c.true("대조 겹치는 달 300개 이상", xc["eps_vs_shiller"]["months"] >= 300)
    c.true("대조 우리 P/E ↔ multpl 공표 P/E: 중위 오차 < 4%",
           xc["pe_vs_multpl"]["median_abs_rel"] < 0.04,
           f"{xc['pe_vs_multpl']['median_abs_rel']:.4f}")
    c.true("대조 CAPE 이음새 < 3%", abs(s["cape"]["seam"]["rel"]) < 0.03,
           str(s["cape"]["seam"]))

    # 실질→명목 환산을 표본 달에서 직접 재계산
    cpi = {r["date"][:7]: r["value"] for r in raw["spx"]["cpi"]["rows"]}
    er = {r["date"][:7]: r["value"] for r in raw["spx"]["eps"]["rows"]}
    base = cpi[max(cpi)]
    for r in s["series"][::60]:
        c.eq(f"환산 {r['month']} 명목 EPS",
             r["eps_nominal"], er[r["month"]] * cpi[r["month"]] / base,
             rel=1e-12)
        if r.get("pe") and r.get("price"):
            c.eq(f"환산 {r['month']} P/E", r["pe"],
                 r["price"] / r["eps_nominal"], rel=1e-12)
    c.eq("S&P 500 지금 P/E", s["earnings"]["pe_now"],
         s["level"]["price"] / s["earnings"]["eps_nominal"], rel=1e-12)

    # 30년 기록 재계산
    for k, w in s["record"]["windows"].items():
        n_ = int(k)
        c.eq(f"S&P 500 {k}년 명목 EPS CAGR", w["eps_cagr_nominal"],
             (w["eps_nominal_to"] / w["eps_nominal_from"]) ** (1 / n_) - 1,
             rel=1e-12)
    c.true("S&P 500 30년 창이 실제 30년",
           int(s["record"]["windows"]["30"]["to"][:4])
           - int(s["record"]["windows"]["30"]["from"][:4]) == 30)
    c.true("트립와이어 ROE 중위 5~40%",
           0.05 <= s["record"]["roe"]["median"] <= 0.40)
    c.eq("S&P 500 증분 수익률 = ROE 중위(상한 적용)",
         s["incremental_return"],
         min(s["record"]["roe"]["median"], d["cap_return"]), rel=0)

    # -------------------------------------------------- 나스닥100 집계
    agg = n["aggregate"]
    cs = [r for r in raw["ndx_constituents"] if "market_cap" in r
          and not r.get("error") and not r.get("duplicate_of")]
    M = sum(r["market_cap"] for r in cs)
    NI = sum(r["net_income_usd"] for r in cs)
    NP = sum(r["nopat_usd"] for r in cs)
    c.same("나스닥100 집계 종목 수", agg["constituents"], len(cs))
    c.eq("나스닥100 Σ시가총액", agg["market_cap"], M, rel=1e-12)
    c.eq("나스닥100 Σ순이익", agg["net_income"], NI, rel=1e-12)
    c.eq("나스닥100 ΣNOPAT", agg["nopat"], NP, rel=1e-12)
    c.eq("나스닥100 P/NOPAT", agg["pe_nopat"], M / NP, rel=1e-12)
    c.eq("나스닥100 P/E(순이익)", agg["pe_net_income"], M / NI, rel=1e-12)
    c.eq("나스닥100 1포인트당 NOPAT", n["earnings"]["per_point_nopat"],
         n["level"]["price"] * NP / M, rel=1e-12)
    c.eq("나스닥100 비중 합 = 1",
         sum(r["weight"] for r in agg["constituent_rows"]), 1.0, tol=1e-9)
    c.true("나스닥100 집계 범위 ≥ 99개", agg["constituents"] >= 99)
    c.true("트립와이어 의심 종목 없음",
           not [r["symbol"] for r in cs if r.get("suspect")],
           str([r["symbol"] for r in cs if r.get("suspect")]))
    c.true("트립와이어 구성종목 시가총액 ≥ 50억 달러",
           all(r["market_cap"] >= 5e9 for r in cs),
           str([r["symbol"] for r in cs if r["market_cap"] < 5e9]))
    c.true("트립와이어 이익 자료 460일 이내",
           all(r["earnings_age_days"] <= 460 for r in cs))
    c.true("대조 P/NOPAT 가 iShares 와 ±20% 안",
           abs(agg["pe_nopat"] / n["ishares"]["pe"] - 1) < 0.20,
           f"{agg['pe_nopat']:.2f} vs {n['ishares']['pe']}")
    c.true("NOPAT 이 순이익보다 작음 (평가이익이 순이익에 섞임)",
           agg["nopat"] < agg["net_income"])
    c.eq("나스닥100 평가이익 격차", agg["mtm_gap_total"], NI - NP,
         rel=1e-12)
    c.true("트립와이어 나스닥100 ROE 5~60%",
           0.05 <= agg["roe_nopat"] <= 0.60, f"{agg['roe_nopat']:.3f}")

    # --------------------------------------------------------- 격자·요구
    check_grid(c, "S&P 500", s, d)
    check_grid(c, "나스닥100", n, d)

    # ------------------------------------------------------------ 백테스트
    b = s["backtest"]
    c.true("백테스트 30년(360개월 이상)", b["months"] >= 360)
    for r in b["rows"][::45]:
        if r["value_own30"] is None:
            continue
        c.same(f"백테스트 {r['month']} 매수선 판정", r["below_buy30"],
               r["price"] <= r["buy30_own30"])
        c.eq(f"백테스트 {r['month']} 매수선 = 가치×0.7", r["buy30_own30"],
             r["value_own30"] * 0.7, rel=1e-12)
    c.same("백테스트 매수선 아래 개월 수", b["below_buy30"]["months"],
           sum(1 for r in b["rows"] if r["below_buy30"]))
    c.same("백테스트 가치 아래 개월 수", b["below_value"]["months"],
           sum(1 for r in b["rows"] if r["below_value"]))

    # ------------------------------------------------------------ CAPE 구간
    fw = s["forward_returns"]
    c.same("CAPE 5분위", [x["quintile"] for x in fw["buckets"]],
           [1, 2, 3, 4, 5])
    c.true("CAPE 5분위 경계가 오름차순",
           all(a["cape_to"] <= b_["cape_from"] + 1e-9
               for a, b_ in zip(fw["buckets"], fw["buckets"][1:])))

    # ------------------------------------------------------------ 인용문
    c.same("버핏 지수 구절 수", len(d["index_passages"]), 3)
    for p in d["index_passages"]:
        c.same(f"버핏 {p['key']} 원문 대조 수", p["verified"],
               len(p["quotes"]))
    keys = {p["key"]: p for p in d["index_passages"]}
    c.true("1993 '나눠 사라' 문장",
           "space out his purchases" in keys["space_out"]["quotes"][0])
    c.true("2013 '들뜬 시점' 문장",
           "extreme exuberance" in keys["exuberance"]["quotes"][0])

    # ------------------------------------------------------------ 신선도
    c.true("신선도 수집일 = 생성일", d["collected"] == d["generated"])
    c.true("신선도 지수 종가가 7일 이내",
           (__import__("datetime").date.fromisoformat(d["generated"])
            - __import__("datetime").date.fromisoformat(
                s["level"]["date"])).days <= 7)
    return c


def _poke(d, path, fn):
    cur = d
    for k in path[:-1]:
        cur = cur[k]
    cur[path[-1]] = fn(cur[path[-1]])
    return d


MUTATIONS = [
    ("S&P 격자 한 칸", lambda d: _poke(
        d, ["spx", "grid", 2, "cells", 1, "value"], lambda v: v * 1.05)),
    ("S&P 매수선", lambda d: _poke(
        d, ["spx", "grid", 2, "cells", 1, "buy_level", "30%"],
        lambda v: v * 1.2)),
    ("S&P 판정 뒤집기", lambda d: _poke(
        d, ["spx", "grid", 0, "cells", 1, "pass", "0%"], lambda v: not v)),
    ("S&P 기대수익률", lambda d: _poke(
        d, ["spx", "grid", 2, "implied_return"], lambda v: v + 0.01)),
    ("S&P 도달 불가를 가능으로", lambda d: _poke(
        d, ["spx", "required", 6],
        lambda r: {**r, "reachable": True, "growth_year1": 0.1,
                   "nopat_cagr_10y": 0.07, "cagr_real": 0.05,
                   "base_rate_percentile": 0.3})),
    ("S&P EPS (앵커)", lambda d: _poke(
        d, ["spx", "earnings", "eps_real"], lambda v: v * 1.03)),
    ("S&P 명목 EPS 환산", lambda d: _poke(
        d, ["spx", "series", 0, "eps_nominal"], lambda v: v * 1.5)),
    ("S&P 30년 EPS CAGR", lambda d: _poke(
        d, ["spx", "record", "windows", "30", "eps_cagr_nominal"],
        lambda v: v + 0.02)),
    ("S&P 증분 수익률", lambda d: _poke(
        d, ["spx", "incremental_return"], lambda v: 0.30)),
    ("S&P 종가 (앵커)", lambda d: _poke(
        d, ["spx", "level", "price"], lambda v: v * 1.01)),
    ("대조 실러 오차 부풀리기", lambda d: _poke(
        d, ["spx", "crosschecks", "eps_vs_shiller", "median_abs_rel"],
        lambda v: 0.08)),
    ("CAPE 이음새 깨기", lambda d: _poke(
        d, ["spx", "cape", "seam", "rel"], lambda v: 0.12)),
    ("나스닥 ΣNOPAT", lambda d: _poke(
        d, ["ndx", "aggregate", "nopat"], lambda v: v * 1.1)),
    ("나스닥 P/NOPAT", lambda d: _poke(
        d, ["ndx", "aggregate", "pe_nopat"], lambda v: v * 0.9)),
    ("나스닥 1포인트당 이익", lambda d: _poke(
        d, ["ndx", "earnings", "per_point_nopat"], lambda v: v * 1.2)),
    ("나스닥 격자 한 칸", lambda d: _poke(
        d, ["ndx", "grid", 1, "cells", 1, "value"], lambda v: v * 0.9)),
    ("나스닥 요구 성장률", lambda d: _poke(
        d, ["ndx", "required", 4], lambda r: {**r, "growth_year1":
                                              r["growth_year1"] * 1.1}
        if r.get("reachable") else r)),
    ("나스닥 종가 (앵커)", lambda d: _poke(
        d, ["ndx", "level", "price"], lambda v: v + 100)),
    ("iShares P/E (앵커)", lambda d: _poke(
        d, ["ndx", "ishares", "pe"], lambda v: 40.0)),
    ("백테스트 판정 뒤집기", lambda d: _poke(
        d, ["spx", "backtest", "rows", 0, "below_buy30"], lambda v: not v)),
    ("백테스트 매수선 개월 수", lambda d: _poke(
        d, ["spx", "backtest", "below_buy30", "months"], lambda v: v + 5)),
    ("버핏 원문 대조 수", lambda d: _poke(
        d, ["index_passages", 0, "verified"], lambda v: 0)),
    ("버핏 인용문 훼손", lambda d: _poke(
        d, ["index_passages", 0, "quotes", 0],
        lambda v: v.replace("space out", "concentrate"))),
    ("생성일을 다른 날로", lambda d: _poke(
        d, ["generated"], lambda v: "2026-12-31")),
]


def main():
    mutate = "--mutate" in sys.argv
    raw = open(DATA, encoding="utf-8").read()
    c = verify(json.loads(raw), Checks())
    print(f"검사 {c.passed + len(c.failures)}건 — 통과 {c.passed}, "
          f"실패 {len(c.failures)}")
    for f in c.failures[:25]:
        print("  ✗", f)
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
            except (KeyError, IndexError, TypeError) as exc:
                print(f"  ✗ {name}: 훼손 자체가 실패 — {exc}")
                survived.append(f"{name} (훼손 실패)")
                continue
            mc = Checks()
            try:
                verify(m, mc)
            except (KeyError, IndexError, TypeError, StopIteration) as exc:
                print(f"  ✓ {name}: 구조 검사에서 중단 — "
                      f"{type(exc).__name__}")
                continue
            if mc.failures:
                print(f"  ✓ {name}: {len(mc.failures)}건 실패 — "
                      f"{mc.failures[0][:78]}")
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
