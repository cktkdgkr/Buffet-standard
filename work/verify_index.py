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
    # Yahoo Finance, 2026-11-23 종가 (chart API 일봉을 따로 받아 확인)
    "spx_close": (7237.17, "2026-11-23"),
    "ndx_close": (26746.10, "2026-11-23"),
    # multpl.com — EPS 는 실질(2026년 9월 달러), 장부가치는 명목
    "multpl_eps_real_2026_06": 298.03,
    "multpl_cpi_2026_09": 336.94,
    "multpl_bv_2025_09": 1270.32,
    # 실러 ie_data.xls
    "shiller_e_2024_06": 196.76,
    "shiller_cape_2024_09": 35.2288,
    # iShares 펀드 페이지 (2026-11-20 기준)
    "ishares_ivv_pe": 26.86, "ishares_cndx_pe": 30.54,
    # SEC 공시 (companyfacts)
    "mu_ttm_net_income": 84.969e9,           # FY2026 10-K, 2026-09-03 결산
    "nvda_ttm_operating_income": 197.579e9,  # 2025-10-26~2026-07-26 4개 분기
    "nvda_tax_rate": 36.865 / 229.744,       # 법인세 ÷ 세전이익, 같은 4개 분기
    "sndk_split": 8.0,                       # 2026-11-20 8:1 분할
    "pdd_ads_ratio": 4,                      # 20-F: ADS 1주 = 보통주 4주
    "ndx_members": 101,
    # 널리 공표된 역사적 종가(일봉) — 순환의 고점·저점이 제대로 읽혔는지.
    "spx_daily": {"2026-11-20": 6910.39, "2000-03-24": 1527.46, "2007-10-09": 1565.15,
                  "2009-03-09": 676.53, "2020-03-23": 2237.40,
                  "2022-01-03": 4796.56},
    "ndx_daily": {"2026-11-20": 25028.98, "2000-03-27": 4704.73, "2002-10-07": 804.64,
                  "2008-11-20": 1036.51},
    # worldperatio 페이지의 차트 데이터(detailPE_data)에서 손으로 읽은 값
    # — Date.UTC 의 달은 0부터 셉니다(Date.UTC(2000, 2, 1) = 2000년 3월).
    "wpr_pe": {"2000-03": 71.8672, "2008-11": 14.2200, "2021-11": 29.6900},
    "wpr_current": (26.37, "2026-11-20"),
    # Siblis Research 나스닥100 페이지의 연말 표
    "siblis_pe": {"2021-12": 38.00, "2026-10": 32.76},
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
                c.eq(f"{nm} 매수선 지금 대비 {k}", cell["buy_vs_level"][k],
                     cell["buy_level"][k] / lvl - 1, rel=1e-9)
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
        # 가치·매수선에 샀을 때의 기대수익률: 되넣으면 그 가격이 나와야 하고,
        # 가치에 산 경우는 정의상 버핏 기준 할인율과 같아야 합니다.
        ra = row.get("returns_at")
        bc = next(x for x in row["cells"]
                  if x["discount_key"] == "bond30_plus3")
        if c.true(f"{tag} {row['key']} 가치·매수선 기대수익률 있음",
                  bool(ra) and ra.get("value") is not None
                  and ra.get("buy30") is not None):
            c.eq(f"{tag} {row['key']} 가치 가격 = 격자", ra["value_price"],
                 bc["value"], rel=1e-12)
            c.eq(f"{tag} {row['key']} 매수선 가격 = 격자", ra["buy30_price"],
                 bc["buy_level"]["30%"], rel=1e-12)
            c.eq(f"{tag} {row['key']} 가치에 사면 = 할인율", ra["value"],
                 bc["discount"], tol=1e-6)
            for k_, price in (("value", ra["value_price"]),
                              ("buy30", ra["buy30_price"])):
                back = dcf(base, row["growth"], row["fade_to"], inc,
                           ra[k_], tg)
                c.eq(f"{tag} {row['key']} {k_} 기대수익률 되넣기",
                     back["value"], price, rel=1e-6)
            c.true(f"{tag} {row['key']} 지금 < 가치 < 매수선 수익률 순서",
                   ir is None or ir < ra["value"] < ra["buy30"],
                   f"{ir} / {ra['value']} / {ra['buy30']}")
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
    off = [r["symbol"] for r in cs if r.get("price_date") != n["level"]["date"]]
    c.true("트립와이어 구성종목 시세일 = 지수 종가일", not off, str(off))
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
    # 두 판(버핏 기준·10% 고정)을 같은 방식으로. 가치는 그 달의 EPS·성장률·
    # 할인율로 **독립 재계산**합니다 — 판정 플래그만 보면 가치 자체가 틀려도
    # 플래그와 서로 맞기만 하면 통과합니다.
    for btk, label, fixed in (("backtest", "백테스트", None),
                              ("backtest_fixed10", "백테스트(10% 고정)", 0.10)):
        b = s[btk]
        c.true(f"{label} 30년(360개월 이상)", b["months"] >= 360)
        c.same(f"{label} 고정 할인율 표기", b["fixed_discount"], fixed)
        if fixed is not None:
            c.true(f"{label} 할인율이 전부 {fixed:.0%}",
                   all(abs(r["discount"] - fixed) < 1e-12 for r in b["rows"]))
        for r in b["rows"][::30]:
            if r["value_own30"] is None:
                continue
            got = dcf(r["eps"], min(r["own30"], d["cap_growth"]), 0.045,
                      b["roe"], r["discount"], b["terminal"])
            c.eq(f"{label} {r['month']} 가치 재계산", r["value_own30"],
                 got["value"], rel=1e-9)
            c.same(f"{label} {r['month']} 매수선 판정", r["below_buy30"],
                   r["price"] <= r["buy30_own30"])
            c.eq(f"{label} {r['month']} 매수선 = 가치×0.7",
                 r["buy30_own30"], r["value_own30"] * 0.7, rel=1e-12)
        c.same(f"{label} 매수선 아래 개월 수", b["below_buy30"]["months"],
               sum(1 for r in b["rows"] if r["below_buy30"]))
        c.same(f"{label} 가치 아래 개월 수", b["below_value"]["months"],
               sum(1 for r in b["rows"] if r["below_value"]))
    # 앵커: 2009년 3월의 12개월 EPS (multpl 실질 → 명목)
    by_b = {r["month"]: r for r in s["backtest"]["rows"]}
    sh09 = {r["date"]: r for r in raw["shiller"]["rows"]}.get("2009-03")
    c.eq("앵커 2009-03 EPS = 실러", by_b["2009-03"]["eps"],
         sh09["earnings"], rel=0.01)
    c.true("2009-03 의 30년 성장률이 음수(끝점 이익 붕괴)",
           by_b["2009-03"]["own30"] < 0)

    check_ndx_history(c, d, raw)
    check_cycles(c, d, raw)

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


def _months(m, k):
    i = int(m[:4]) * 12 + int(m[5:7]) - 1 + k
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def check_ndx_history(c, d, raw):
    """나스닥100 의 30년 이익(2차 출처)과 그 위의 백테스트."""
    n, s = d["ndx"], d["spx"]
    h = n["history"]
    wpr = {r["month"]: r["pe"] for r in raw["ndx_pe_history"]["rows"]}
    for m, v in ANCHOR["wpr_pe"].items():
        c.eq(f"앵커 worldperatio P/E {m}", wpr.get(m), v, tol=0.00005)
    cur = raw["ndx_pe_history"]["current"]
    c.eq("앵커 worldperatio 현재 P/E", cur["pe"], ANCHOR["wpr_current"][0],
         tol=0.005)
    c.same("앵커 worldperatio 계산일", cur["date"], ANCHOR["wpr_current"][1])
    sib = {p["month"]: p["pe"] for p in raw["siblis_ndx"]["points"]}
    for m, v in ANCHOR["siblis_pe"].items():
        c.eq(f"앵커 Siblis P/E {m}", sib.get(m), v, tol=0.005)

    # 1포인트당 이익 = 그 달 말 지수 ÷ P/E — 원자료에서 다시.
    px = {r["date"][:7]: r["close"]
          for r in raw["prices"]["NDX"]["monthly"]["rows"]}
    ser = {r["month"]: r for r in h["series"]}
    for m in ("2000-03", "2008-11", "2021-11", "2015-06"):
        c.eq(f"나스닥 {m} 1포인트당 이익", ser[m]["eps"], px[m] / wpr[m],
             rel=1e-12)
    chk = h["checks"]
    dday = {r["date"]: r["close"]
            for r in raw["prices"]["NDX"]["daily"]["rows"]}
    live_m = (raw["ndx_pe_history"]["rows"][-1]["month"]
              if raw["ndx_pe_history"]["last_point_is_current"] else None)
    c.true("나스닥 마지막 점은 계산일 종가로 나눔",
           live_m is None or abs(ser[live_m]["eps"] * wpr[live_m]
                                 - dday[cur["date"]]) < 1e-6)
    c.eq("대조 worldperatio ↔ 우리 순이익 P/E", chk["today"]["rel"],
         cur["pe"] / n["aggregate"]["pe_net_income"] - 1, rel=1e-12)
    c.true("대조 worldperatio 현재값이 우리 순이익 집계와 ±10% 안",
           abs(chk["today"]["rel"]) < 0.10, f"{chk['today']['rel']:+.3f}")
    rels = sorted(abs(wpr[m] / v - 1) for m, v in sib.items()
                  if m in wpr and m != raw["ndx_pe_history"]["rows"][-1]
                  ["month"])
    med = (rels[len(rels) // 2] if len(rels) % 2 else
           (rels[len(rels) // 2 - 1] + rels[len(rels) // 2]) / 2)
    c.eq("대조 Siblis 중위 오차 재계산", chk["siblis"]["median_abs_rel"], med,
         rel=1e-12)
    c.eq("대조 Siblis 최대 오차 재계산", chk["siblis"]["max_abs_rel"],
         rels[-1], rel=1e-12)
    mv = chk["siblis_moved_to_today"]
    c.eq("대조 Siblis 를 오늘 가격으로", mv["pe_at_today_price"],
         sib[mv["month"]] * n["level"]["price"] / px[mv["month"]], rel=1e-12)
    c.true("대조 Siblis(정상화) 를 오늘로 옮기면 우리 P/NOPAT 와 ±10% 안",
           abs(mv["pe_at_today_price"] / n["aggregate"]["pe_nopat"] - 1)
           < 0.10, f"{mv['pe_at_today_price']:.2f} vs "
           f"{n['aggregate']['pe_nopat']:.2f}")
    cv = chk["convention"]
    c.true("날짜 해석: 그 달 말 종가로 나눈 이익이 더 매끄러움",
           cv["same_month_end"]["median_abs_change"]
           < cv["previous_month_end"]["median_abs_change"] / 2)
    c.true("트립와이어 나스닥 P/E 기록 5~200배",
           all(5 <= r["pe"] <= 200 for r in h["series"]))
    c.eq("나스닥 백테스트 ROE = 순이익 ÷ 자기자본(상한)", h["roe"],
         min(n["aggregate"]["roe_net_income"], d["cap_return"]), rel=0)

    # S&P 500 의 30년 EPS 기록 — multpl 원자료에서 직접(실질 → 명목).
    cpi = {r["date"][:7]: r["value"] for r in raw["spx"]["cpi"]["rows"]}
    er = {r["date"][:7]: r["value"] for r in raw["spx"]["eps"]["rows"]}
    base = cpi[max(cpi)]
    sp_last = max(m for m in er if m in cpi)

    def own30(m):
        m = min(m, sp_last)
        m0 = f"{int(m[:4]) - 30:04d}{m[4:]}"
        e1, e0 = er[m] * cpi[m] / base, er[m0] * cpi[m0] / base
        return (e1 / e0) ** (1 / 30) - 1

    for btk, label, fixed in (("backtest", "나스닥 백테스트", None),
                              ("backtest_fixed10", "나스닥 백테스트(10% 고정)",
                               0.10)):
        b = n[btk]
        c.true(f"{label} 30년(360개월 이상)", b["months"] >= 360)
        c.same(f"{label} 고정 할인율 표기", b["fixed_discount"], fixed)
        c.eq(f"{label} ROE", b["roe"], h["roe"], rel=0)
        tyx = {r["date"][:7]: r["close"] / 100
               for r in raw["prices"]["TYX"]["monthly"]["rows"]}
        for r in b["rows"][::25] + b["rows"][-1:]:
            m = r["month"]
            ref = (dday[cur["date"]] if m == live_m else px[m])
            c.eq(f"{label} {m} 이익 = 원자료", r["eps"], ref / wpr[m],
                 rel=1e-12)
            c.eq(f"{label} {m} 성장률 = S&P 30년", r["own30"], own30(m),
                 rel=1e-9)
            c.eq(f"{label} {m} 할인율", r["discount"],
                 fixed if fixed is not None else tyx[m] + 0.03, rel=1e-12)
            if r["value_own30"] is None:
                continue
            got = dcf(r["eps"], min(r["own30"], d["cap_growth"]), 0.045,
                      b["roe"], r["discount"], b["terminal"])
            c.eq(f"{label} {m} 가치 재계산", r["value_own30"], got["value"],
                 rel=1e-9)
            c.same(f"{label} {m} 가치 판정", r["below_value"],
                   r["price"] <= r["value_own30"])
        c.same(f"{label} 매수선 아래 개월 수", b["below_buy30"]["months"],
               sum(1 for r in b["rows"] if r["below_buy30"]))
        c.same(f"{label} 가치 아래 개월 수", b["below_value"]["months"],
               sum(1 for r in b["rows"] if r["below_value"]))


def zigzag_indep(daily, down, up):
    """
    엔진(find_cycles)과 따로 쓴 고점·저점 찾기. 인덱스로 걸으며, 확정된
    저점마다 그 앞 구간의 최고가를 **다시 찾아** 고점으로 삼습니다.
    """
    cl = [r["close"] for r in daily]
    dt = [r["date"] for r in daily]
    out, i0, n_ = [], 0, len(cl)
    while i0 < n_:
        # 고점 후보: i0 부터 걷다가 최고가 대비 down 이상 빠지는 첫 날.
        hi_i, j = i0, i0
        while j < n_ and cl[j] > cl[hi_i] * (1 - down):
            if cl[j] > cl[hi_i]:
                hi_i = j
            j += 1
        if j >= n_:
            break
        lo_i, k = j, j
        while k < n_ and cl[k] < cl[lo_i] * (1 + up):
            if cl[k] < cl[lo_i]:
                lo_i = k
            k += 1
        out.append((dt[hi_i], cl[hi_i], dt[lo_i], cl[lo_i],
                    dt[k] if k < n_ else None))
        i0 = k
    return out


def merge_indep(raw_c, tol):
    """연속된 하락 묶기 — 엔진과 따로, 묶음의 시작 인덱스로 걸으며."""
    out, i = [], 0
    while i < len(raw_c):
        p0, pk, t0, tr, _ = raw_c[i]
        low, low_d, legs, j = tr, t0, [], i + 1
        while (j < len(raw_c) and raw_c[j][1] < pk
               and raw_c[j][3] <= low * (1 + tol)):
            legs.append(raw_c[j][0])
            if raw_c[j][3] < low:
                low, low_d = raw_c[j][3], raw_c[j][2]
            j += 1
        out.append((p0, low_d, legs))
        i = j
    return out


def check_cycles(c, d, raw):
    for key, X in (("spx", d["spx"]), ("ndx", d["ndx"])):
        tag = "S&P" if key == "spx" else "나스닥"
        daily = raw["prices"][key.upper()]["daily"]["rows"]
        dmap = {r["date"]: r["close"] for r in daily}
        for dte, v in ANCHOR[f"{key}_daily"].items():
            c.eq(f"앵커 {tag} 일봉 {dte}", dmap.get(dte), v, tol=0.006)
        # 일봉 ↔ 월봉(같은 Yahoo 의 다른 계열): 월의 마지막 일봉 = 월말 종가.
        last_of = {}
        for r in daily:
            last_of[r["date"][:7]] = r["close"]
        mon = [r for r in raw["prices"][key.upper()]["monthly"]["rows"]
               if "1996-01" <= r["date"][:7]][:-1]
        bad = [r["date"][:7] for r in mon
               if abs(last_of.get(r["date"][:7], 0) / r["close"] - 1) > 1e-4]
        c.true(f"{tag} 일봉의 월말 = 월봉 종가 ({len(mon)}개월)", not bad,
               str(bad[:5]))

        rule = X["cycles"]["rule"]
        zz = zigzag_indep(daily, rule["down"], rule["up"])
        c.same(f"{tag} 묶기 전 순환 수", rule["raw_cycles"], len(zz))
        ind = merge_indep(zz, rule["merge_tol"])
        # 허용폭 범위: 양 끝에서는 같은 결과, 바로 바깥에서는 다른 결과.
        lo_t, hi_t = rule["merge_tol_band"]
        c.true(f"{tag} 묶기 허용폭 {rule['merge_tol']:.0%} 이 범위 안",
               lo_t <= rule["merge_tol"] <= hi_t)
        for t_ in (lo_t, hi_t):
            c.same(f"{tag} 허용폭 {t_:.3f} 에서도 같은 결과",
                   merge_indep(zz, t_), ind)
        for t_ in (round(lo_t - 0.001, 3), round(hi_t + 0.001, 3)):
            if 0 <= t_ <= 0.3:
                c.true(f"{tag} 허용폭 {t_:.3f} 에서는 다른 결과",
                       merge_indep(zz, t_) != ind)
        for k in ("bond", "fixed10"):
            cv = X["cycles"][k]
            b = X["backtest" if k == "bond" else "backtest_fixed10"]
            by = {r["month"]: r for r in b["rows"]}
            got = [(r["peak_date"], r["trough_date"],
                    [g_["peak_date"] for g_ in r["legs"]])
                   for r in cv["cycles"]]
            want = [(p, t, lg) for p, t, lg in ind if p[:7] >= b["from"]]
            c.same(f"{tag}[{k}] 고점·저점 = 독립 구현", got, want)
            for r in cv["cycles"]:
                nm = f"{tag}[{k}] {r['peak_date']}"
                c.eq(f"{nm} 고점 종가", r["peak"], dmap[r["peak_date"]],
                     rel=0)
                c.eq(f"{nm} 저점 종가", r["trough"], dmap[r["trough_date"]],
                     rel=0)
                c.true(f"{nm} 낙폭 ≥ {rule['down']:.0%}",
                       r["drawdown"] <= -rule["down"] + 1e-12)
                c.eq(f"{nm} 낙폭 = 저점÷고점−1", r["drawdown"],
                     r["trough"] / r["peak"] - 1, rel=1e-12)
                c.true(f"{nm} 중간 반등의 고점이 하락 시작 고점보다 낮음",
                       all(g_["peak"] < r["peak"] for g_ in r["legs"]))
                c.eq(f"{nm} 저점 = 중간 반등 포함 최저", r["trough"],
                     min([dmap[r["trough_date"]]]
                         + [g_["trough"] for g_ in r["legs"]]), rel=0)
                c.true(f"{nm} 미확정은 마지막 하나뿐",
                       not r["open"] or r is cv["cycles"][-1])
                row = by[r["value_month"]]
                c.true(f"{nm} 가치의 달 = 고점의 달(또는 마지막 달)",
                       r["value_month"] == r["peak_date"][:7]
                       or (r["peak_date"][:7] > b["to"]
                           and r["value_month"] == b["to"]))
                g = dcf(row["eps"], min(row["own30"], d["cap_growth"]), 0.045,
                        b["roe"], row["discount"], b["terminal"])
                c.eq(f"{nm} 그때 가치 재계산", r["value_at_peak"], g["value"],
                     rel=1e-9)
                c.eq(f"{nm} 그때 매수선", r["buy30_at_peak"],
                     g["value"] * 0.7, rel=1e-9)
                c.same(f"{nm} 저점이 가치 아래", r["reached_value"],
                       r["trough"] <= g["value"])
                c.same(f"{nm} 저점이 매수선 아래", r["reached_buy30"],
                       r["trough"] <= g["value"] * 0.7)
                c.eq(f"{nm} 저점 ÷ 가치", r["trough_vs_value"],
                     r["trough"] / g["value"] - 1, rel=1e-9)
                if "lag_month" in r:
                    c.same(f"{nm} 시차 달", r["lag_month"],
                           _months(r["value_month"], -cv["lag_months"]))
                    kk = by[r["lag_month"]]["eps"] / row["eps"]
                    c.eq(f"{nm} 시차 반영 가치", r["value_at_peak_lag"],
                         g["value"] * kk, rel=1e-9)
            closed = [r for r in cv["cycles"] if not r["open"]]
            c.same(f"{tag}[{k}] 확정 순환 수", cv["closed"], len(closed))
            c.same(f"{tag}[{k}] 가치 아래 도달 수", cv["reached_value"],
                   sum(r["trough"] <= r["value_at_peak"] for r in closed))
            c.same(f"{tag}[{k}] 매수선 아래 도달 수", cv["reached_buy30"],
                   sum(r["trough"] <= r["buy30_at_peak"] for r in closed))
            c.same(f"{tag}[{k}] 시차로 뒤집히는 순환", cv["flips_with_lag"],
                   [r["peak_date"] for r in cv["cycles"]
                    if "lag_month" in r and (
                        (r["trough"] <= r["value_at_peak_lag"])
                        != (r["trough"] <= r["value_at_peak"])
                        or (r["trough"] <= r["buy30_at_peak_lag"])
                        != (r["trough"] <= r["buy30_at_peak"]))])
        # '지금' 줄: 같은 잣대를 오늘에 — 독립 재계산.
        for k, disc in (("bond", d["macro"]["treasury_30y"]["rate"] + 0.03),
                        ("fixed10", 0.10)):
            nw = X["cycles"][k]["now"]
            b = X["backtest" if k == "bond" else "backtest_fixed10"]
            c.eq(f"{tag}[{k}] 지금 할인율", nw["discount"], disc, rel=1e-12)
            c.eq(f"{tag}[{k}] 지금 지수", nw["level"], X["level"]["price"],
                 rel=0)
            c.eq(f"{tag}[{k}] 지금 ROE = 그래프 ROE", nw["roe"], b["roe"],
                 rel=0)
            g = dcf(nw["eps"], min(nw["own30"], d["cap_growth"]), 0.045,
                    nw["roe"], disc, d["terminal"])
            c.eq(f"{tag}[{k}] 지금 가치 재계산", nw["value"], g["value"],
                 rel=1e-9)
            c.eq(f"{tag}[{k}] 지금 매수선", nw["buy30"], g["value"] * 0.7,
                 rel=1e-9)
            closed = [r for r in X["cycles"][k]["cycles"] if not r["open"]]
            prem = nw["level"] / g["value"] - 1
            hc = [r for r in closed if r["peak_vs_value"] >= prem]
            c.same(f"{tag}[{k}] 지금보다 프리미엄 높던 순환", 
                   nw["higher_premium_cycles"], len(hc))
            c.same(f"{tag}[{k}] 그중 가치 도달",
                   nw["higher_premium_reached_value"],
                   sum(r["trough"] <= r["value_at_peak"] for r in hc))
        if key == "spx":
            # S&P 500 의 '지금' 가치는 판정 격자의 '30년 EPS 기록 유지' 칸과
            # 같은 값이어야 합니다(같은 이익·성장률·ROE·할인율).
            row = next(r for r in X["grid"] if r["key"] == "own_sustained")
            for k, dk in (("bond", "bond30_plus3"), ("fixed10", "project10")):
                cell = next(x for x in row["cells"] if x["discount_key"] == dk)
                c.eq(f"S&P[{k}] 지금 가치 = 격자 칸", X["cycles"][k]["now"]
                     ["value"], cell["value"], rel=1e-9)
        else:
            c.eq("나스닥 지금 이익 = 계산일 종가 ÷ P/E",
                 X["cycles"]["bond"]["now"]["eps"],
                 dmap[raw["ndx_pe_history"]["current"]["date"]]
                 / raw["ndx_pe_history"]["current"]["pe"], rel=1e-3)
        c.true(f"{tag} 두 판의 순환이 같음",
               [r["peak_date"] for r in X["cycles"]["bond"]["cycles"]]
               == [r["peak_date"] for r in X["cycles"]["fixed10"]["cycles"]])
    # 나스닥 이익 출처 오차: Siblis 중위 오차를 그대로 씀.
    e = d["ndx"]["history"]["checks"]["siblis"]["median_abs_rel"]
    for k in ("bond", "fixed10"):
        cv = d["ndx"]["cycles"][k]
        c.eq(f"나스닥[{k}] 출처 오차 = Siblis 중위 오차", cv["source_error"], e,
             rel=0)
        c.same(f"나스닥[{k}] 출처 오차에 민감한 순환", cv["not_robust_to_source"],
               [r["peak_date"] for r in cv["cycles"] if (
                   (r["trough"] <= r["value_at_peak"] * (1 - e))
                   != (r["trough"] <= r["value_at_peak"] * (1 + e))
                   or (r["trough"] <= r["buy30_at_peak"] * (1 - e))
                   != (r["trough"] <= r["buy30_at_peak"] * (1 + e)))])


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
    ("10% 고정 가치", lambda d: _poke(
        d, ["spx", "backtest_fixed10", "rows", 30, "value_own30"],
        lambda v: v * 1.3)),
    ("10% 고정 할인율 바꾸기", lambda d: _poke(
        d, ["spx", "backtest_fixed10", "rows", 5, "discount"],
        lambda v: 0.08)),
    ("백테스트 판정 뒤집기", lambda d: _poke(
        d, ["spx", "backtest", "rows", 0, "below_buy30"], lambda v: not v)),
    ("백테스트 매수선 개월 수", lambda d: _poke(
        d, ["spx", "backtest", "below_buy30", "months"], lambda v: v + 5)),
    ("S&P 매수선 지금 대비", lambda d: _poke(
        d, ["spx", "grid", 1, "cells", 1, "buy_vs_level", "30%"],
        lambda v: v + 0.05)),
    ("S&P 매수선 기대수익률", lambda d: _poke(
        d, ["spx", "grid", 2, "returns_at", "buy30"], lambda v: v + 0.01)),
    ("나스닥 가치 기대수익률", lambda d: _poke(
        d, ["ndx", "grid", 0, "returns_at", "value"], lambda v: v + 0.005)),
    ("버핏 원문 대조 수", lambda d: _poke(
        d, ["index_passages", 0, "verified"], lambda v: 0)),
    ("버핏 인용문 훼손", lambda d: _poke(
        d, ["index_passages", 0, "quotes", 0],
        lambda v: v.replace("space out", "concentrate"))),
    ("나스닥 백테스트 가치", lambda d: _poke(
        d, ["ndx", "backtest", "rows", 50, "value_own30"], lambda v: v * 1.2)),
    ("나스닥 백테스트 이익", lambda d: _poke(
        d, ["ndx", "backtest_fixed10", "rows", 75, "eps"], lambda v: v * 1.1)),
    ("나스닥 이익 계열 한 달", lambda d: _poke(
        d, ["ndx", "history", "series"],
        lambda ss: [({**r, "eps": r["eps"] * 1.3} if r["month"] == "2008-11"
                     else r) for r in ss])),
    ("worldperatio 대조 오차", lambda d: _poke(
        d, ["ndx", "history", "checks", "today", "rel"], lambda v: 0.0)),
    ("Siblis 중위 오차", lambda d: _poke(
        d, ["ndx", "history", "checks", "siblis", "median_abs_rel"],
        lambda v: v / 2)),
    ("날짜 해석 근거 뒤집기", lambda d: _poke(
        d, ["ndx", "history", "checks", "convention", "same_month_end",
            "median_abs_change"], lambda v: 0.2)),
    ("나스닥 ROE 바꾸기", lambda d: _poke(
        d, ["ndx", "history", "roe"], lambda v: 0.139)),
    ("나스닥 마지막 점을 월봉 종가로", lambda d: _poke(
        d, ["ndx", "history", "series"],
        lambda ss: ss[:-1] + [{**ss[-1], "eps": ss[-1]["price"]
                               / ss[-1]["pe"]}])),
    ("지금 가치", lambda d: _poke(
        d, ["spx", "cycles", "bond", "now", "value"], lambda v: v * 1.1)),
    ("지금 할인율", lambda d: _poke(
        d, ["ndx", "cycles", "fixed10", "now", "discount"], lambda v: 0.09)),
    ("지금보다 프리미엄 높던 순환 수", lambda d: _poke(
        d, ["ndx", "cycles", "bond", "now", "higher_premium_cycles"],
        lambda v: v + 2)),
    ("나스닥 지금 이익", lambda d: _poke(
        d, ["ndx", "cycles", "bond", "now", "eps"], lambda v: v * 1.07)),
    ("묶기 허용폭 범위", lambda d: _poke(
        d, ["ndx", "cycles", "rule", "merge_tol_band"], lambda v: [0.0, 0.3])),
    ("중간 반등 하나 빼기", lambda d: _poke(
        d, ["spx", "cycles", "bond", "cycles", 1, "legs"], lambda v: v[1:])),
    ("묶인 하락의 저점을 첫 구간 저점으로", lambda d: _poke(
        d, ["spx", "cycles", "fixed10", "cycles", 1],
        lambda r: {**r, "trough_date": "2001-09-21", "trough": 965.80})),
    ("순환 고점 날짜 하루 밀기", lambda d: _poke(
        d, ["spx", "cycles", "bond", "cycles", 2, "peak_date"],
        lambda v: "2007-10-10")),
    ("순환 저점 수준", lambda d: _poke(
        d, ["ndx", "cycles", "fixed10", "cycles", 7, "trough"],
        lambda v: v * 0.9)),
    ("순환 하나 빼기", lambda d: _poke(
        d, ["spx", "cycles", "fixed10", "cycles"], lambda v: v[:5] + v[6:])),
    ("순환 그때 가치", lambda d: _poke(
        d, ["ndx", "cycles", "bond", "cycles", 14, "value_at_peak"],
        lambda v: v * 0.8)),
    ("순환 매수선 도달 뒤집기", lambda d: _poke(
        d, ["spx", "cycles", "bond", "cycles", 4, "reached_buy30"],
        lambda v: not v)),
    ("순환 도달 수", lambda d: _poke(
        d, ["ndx", "cycles", "bond", "reached_value"], lambda v: v + 1)),
    ("순환 시차 반전 목록", lambda d: _poke(
        d, ["spx", "cycles", "bond", "flips_with_lag"], lambda v: [])),
    ("출처 오차 민감 목록", lambda d: _poke(
        d, ["ndx", "cycles", "bond", "not_robust_to_source"], lambda v: [])),
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
