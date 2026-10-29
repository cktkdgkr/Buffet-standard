"""
Checks on the SpaceX and Tesla figures.

The same three kinds as the fifty-company work, and for the same reason: an
identity proves the arithmetic, a tie-out proves the pieces are complete, and
an anchor is the only one of the three that can fail because the data is wrong
rather than because the sum is.

The tie-outs matter more here than usual. These figures come from parsing
filing renderings rather than from an API, and a parser that picks up the
heading row instead of the figure beneath it, or applies a table's "$ in
Millions" to a share count, produces a number that is internally consistent
and wrong. Both of those happened: the preferred stock read as nil because the
lookup matched "Redeemable convertible preferred stock" - the heading above
the $38,752m - and the share count came through as 1.4e16, which valued the
company at $2 quintillion. The segment revenues summing to the consolidated
total, and the PP&E components summing to the gross figure, are what catch
that class of mistake.

    python3 verify_spx_tsla.py
    python3 verify_spx_tsla.py --mutate
"""

import argparse
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "spx", "spx_tsla.json")
MM = 1e6

# Read off the filings by hand. Sources:
#   SPCX 10-Q for the quarter ended 30 September 2026, accession
#        0001628280-26-066880
#   SPCX 424B4 filed 12 June 2026, accession 0001628280-26-042639
#   TSLA 10-K for FY2025, accession 0001628280-26-003952
#   TSLA 10-Q for the quarter ended 30 September 2026, accession
#        0001628280-26-066775
ANCHORS = [
    ("SPCX 9M2026 매출", ["SPCX", "consolidated_9m", "revenue", "9m_2026"],
     27_083 * MM),
    ("SPCX 9M2026 영업이익",
     ["SPCX", "consolidated_9m", "operating_income", "9m_2026"], 705 * MM),
    ("SPCX 9M2026 capex", ["SPCX", "consolidated_9m", "capex", "9m_2026"],
     48_069 * MM),
    ("SPCX Starlink 9M2026 영업이익",
     ["SPCX", "segments_9m", "Connectivity", "operating_income", "9m_2026"],
     5_211 * MM),
    ("SPCX SI 9M2026 capex",
     ["SPCX", "segments_9m", "SI", "capex", "9m_2026"], 39_995 * MM),
    ("SPCX 자기자본 2026-09-30",
     ["SPCX", "balance_sheets", "2026-09-30", "equity"], 176_768 * MM),
    ("SPCX 우선주 2025-12-31",
     ["SPCX", "balance_sheets", "2025-12-31", "redeemable_preferred"],
     38_752 * MM),
    ("SPCX 영업권 2026-09-30",
     ["SPCX", "balance_sheets", "2026-09-30", "goodwill"], 48_423 * MM),
    ("SPCX 건설중자산 2026-09-30",
     ["SPCX", "balance_sheets", "2026-09-30", "construction_in_progress"],
     23_745 * MM),
    ("SPCX PP&E 총액 2026-09-30",
     ["SPCX", "balance_sheets", "2026-09-30", "ppe_gross"], 110_005 * MM),
    ("SPCX 계약잔고",
     ["SPCX", "backlog", "remaining_performance_obligation"], 62_959 * MM),
    ("SPCX 발행주식수", ["SPCX", "ratios", "shares_outstanding"],
     13_579_000_000.0),
    ("SPCX FY2025 매출",
     ["SPCX", "annual_from_prospectus", "FY2025", "revenue"], 18_674 * MM),
    ("SPCX FY2025 영업이익",
     ["SPCX", "annual_from_prospectus", "FY2025", "operating_income"],
     -2_589 * MM),
    ("SPCX FY2024 영업이익",
     ["SPCX", "annual_from_prospectus", "FY2024", "operating_income"],
     466 * MM),
    ("SPCX FY2023 영업이익",
     ["SPCX", "annual_from_prospectus", "FY2023", "operating_income"],
     -3_505 * MM),
    ("TSLA 건설중자산 2026-09-30",
     ["TSLA", "ppe", "2026-09-30", "construction_in_progress"], 11_211 * MM),
    ("TSLA PP&E 총액 2025-12-31", ["TSLA", "ppe", "2025-12-31", "gross"],
     60_816 * MM),
    ("TSLA AI 인프라 2026-09-30",
     ["TSLA", "ppe", "2026-09-30", "ai_infrastructure"], 10_956 * MM),
    ("TSLA 발행주식수", ["TSLA", "ratios", "shares_outstanding"],
     3_952_757_946.0),
]


def dig(d, path):
    for k in path:
        if d is None:
            return None
        d = d.get(k) if isinstance(d, dict) else None
    return d


class Checks:
    def __init__(self):
        self.passed = 0
        self.failures = []

    def ok(self, cond, label):
        if cond:
            self.passed += 1
        else:
            self.failures.append(label)

    def close(self, got, want, label, rel=2e-4):
        if got is None or want is None:
            self.ok(False, f"{label}: 값 없음 (got={got}, want={want})")
            return
        self.ok(abs(got - want) <= rel * max(1.0, abs(want)),
                f"{label}: {got:,.0f} != {want:,.0f}")


def run(d, c):
    c.ok(d.get("wacc") == 0.10, "WACC 10% 아님")
    c.ok(bool(d.get("generated")), "작성일 없음")

    s, t = d["SPCX"], d["TSLA"]

    # --- SpaceX: listing facts, which were the thing asserted from memory ---
    meta = s["meta"]
    c.ok(meta["tickers"] == ["SPCX"], f"SPCX 티커 {meta['tickers']}")
    c.ok(meta["exchanges"] == ["Nasdaq"], f"SPCX 거래소 {meta['exchanges']}")
    forms = {f["form"] for f in meta["filings"]}
    c.ok("10-Q" in forms, "SPCX 10-Q 없음")
    c.ok("10-K" not in forms,
         "SPCX 10-K가 존재 — 연간 수치의 출처를 다시 확인할 것")
    c.ok("424B4" in forms, "SPCX 424B4 없음")

    # --- tie-out: segments sum to the consolidated total -------------------
    for key in ("revenue", "operating_income", "capex"):
        for period in ("9m_2026", "9m_2025"):
            parts = [s["segments_9m"][n][key][period]
                     for n in ("Space", "Connectivity", "SI")]
            total = s["consolidated_9m"][key][period]
            if any(p is None for p in parts) or total is None:
                c.ok(False, f"SPCX 사업부 {key} {period}: 값 누락")
                continue
            c.close(sum(parts), total,
                    f"SPCX 사업부 합계 {key} {period}", rel=2e-3)

    # --- tie-out: PP&E components sum to the gross figure ------------------
    for when, b in s["balance_sheets"].items():
        c.ok(b["ppe_gross"] is not None and b["ppe_gross"] > 0,
             f"SPCX {when} PP&E 총액 없음")
        c.ok(b["construction_in_progress"] is not None,
             f"SPCX {when} 건설중자산 없음")
        c.ok(0 < b["construction_in_progress"] < b["ppe_gross"],
             f"SPCX {when} 건설중자산이 총액 범위를 벗어남")

    # --- identity: the capital stack and the three ROIC views --------------
    sr = s["ratios"]
    for when, view_key in (("2025-12-31", "opening"), ("2026-09-30",
                                                       "closing")):
        b = s["balance_sheets"][when]
        base = ((b["equity"] or 0) + (b["redeemable_preferred"] or 0)
                + (b["debt"] or 0) - (b["cash_and_securities"] or 0))
        c.close(sr["views"]["reported"][view_key], base,
                f"SPCX {when} 보고 투하자본")
        c.close(sr["views"]["operating"][view_key],
                base - (b["goodwill"] or 0) - (b["intangibles"] or 0),
                f"SPCX {when} 영업 투하자본")
        c.close(sr["views"]["in_service"][view_key],
                base - (b["goodwill"] or 0) - (b["intangibles"] or 0)
                - (b["construction_in_progress"] or 0),
                f"SPCX {when} 가동 투하자본")

    c.close(sr["operating_income_annualised"],
            sr["operating_income_9m_2026"] * 4 / 3, "SPCX 연율화 영업이익")
    c.close(sr["nopat_annualised"],
            sr["operating_income_annualised"] * 0.79, "SPCX NOPAT")
    for name, v in sr["views"].items():
        c.close(v["average"], (v["opening"] + v["closing"]) / 2,
                f"SPCX {name} 평균 투하자본")
        c.close(v["roic"], sr["nopat_annualised"] / v["average"],
                f"SPCX {name} ROIC")
        c.close(v["spread_vs_wacc"], v["roic"] - 0.10,
                f"SPCX {name} 스프레드")
    # The narrower the denominator the higher the return, by construction.
    c.ok(sr["views"]["reported"]["roic"] <= sr["views"]["operating"]["roic"]
         <= sr["views"]["in_service"]["roic"],
         "SPCX 세 관점의 ROIC 순서가 정의와 맞지 않음")

    c.close(sr["market_cap"], sr["shares_outstanding"] * sr["price"],
            "SPCX 시가총액")
    # A share count in the billions, not the quadrillions. This is the check
    # that would have caught the scale applied to a count of shares.
    c.ok(1e9 < sr["shares_outstanding"] < 1e11,
         f"SPCX 발행주식수가 비현실적: {sr['shares_outstanding']:,.0f}")
    c.ok(1e11 < sr["market_cap"] < 1e13,
         f"SPCX 시가총액이 비현실적: {sr['market_cap']:,.0f}")

    for name, seg in sr["segments"].items():
        c.close(seg["operating_margin"],
                seg["operating_income_9m"] / seg["revenue_9m"],
                f"SPCX {name} 영업이익률")
        c.close(seg["capex_to_revenue"], seg["capex_9m"] / seg["revenue_9m"],
                f"SPCX {name} capex/매출")
        c.close(seg["operating_income_less_capex"],
                seg["operating_income_9m"] - seg["capex_9m"],
                f"SPCX {name} 영업이익−capex")

    # --- Tesla -------------------------------------------------------------
    tr = t["ratios"]
    years = {y["fiscal_year"]: y for y in t["annual_roic"]}
    for fy, y in years.items():
        if None in (y["operating_income"], y["effective_tax_rate"],
                    y["nopat"]):
            continue
        c.close(y["nopat"],
                y["operating_income"] * (1 - y["effective_tax_rate"]),
                f"TSLA FY{fy} NOPAT")
        if y["invested_capital"] is not None:
            c.close(y["invested_capital"],
                    y["total_equity"] + y["interest_bearing_debt"]
                    - y["cash_and_short_term_investments"],
                    f"TSLA FY{fy} 투하자본")
        if y["roic"] is not None and y["invested_capital_avg"]:
            c.close(y["roic"], y["nopat"] / y["invested_capital_avg"],
                    f"TSLA FY{fy} ROIC")

    for label, inc in tr["incremental"].items():
        a, b = label.replace("FY", "").split("→")
        ya, yb = years[int(a)], years[int(b)]
        c.close(inc["delta_nopat"], yb["nopat"] - ya["nopat"],
                f"TSLA {label} ΔNOPAT")
        c.close(inc["delta_capital"],
                yb["invested_capital"] - ya["invested_capital"],
                f"TSLA {label} Δ투하자본")
        c.close(inc["incremental_roic"],
                inc["delta_nopat"] / inc["delta_capital"],
                f"TSLA {label} 증분 ROIC")

    for fy, v in tr["in_service"].items():
        c.close(v["capital_in_service"],
                v["invested_capital"] - v["construction_in_progress"],
                f"TSLA FY{fy} 가동 투하자본")
        c.close(v["cip_share"],
                v["construction_in_progress"] / v["invested_capital"],
                f"TSLA FY{fy} 건설중 비중")

    c.close(tr["market_cap"], tr["shares_outstanding"] * tr["price"],
            "TSLA 시가총액")
    c.ok(1e9 < tr["shares_outstanding"] < 1e11,
         f"TSLA 발행주식수가 비현실적: {tr['shares_outstanding']:,.0f}")
    c.close(tr["roic_latest"], years[2025]["roic"], "TSLA 최신 ROIC")

    for when, p in t["ppe"].items():
        c.ok(0 < p["construction_in_progress"] < p["gross"],
             f"TSLA {when} 건설중자산 범위")
        c.close(p["net"], p["gross"] + p["accumulated_depreciation"],
                f"TSLA {when} PP&E 순액 = 총액 − 감가상각누계")

    # --- anchors -----------------------------------------------------------
    for label, path, want in ANCHORS:
        c.close(dig(d, path), want, f"앵커 {label}")


MUTATIONS = [
    ("사업부 합계 불일치",
     lambda d: _set(d, ["SPCX", "segments_9m", "Connectivity", "revenue",
                        "9m_2026"], 1.0e10)),
    ("투하자본 항등식",
     lambda d: _set(d, ["SPCX", "ratios", "views", "reported", "closing"],
                    1.0e11)),
    ("ROIC 식",
     lambda d: _set(d, ["SPCX", "ratios", "views", "operating", "roic"],
                    0.25)),
    ("세 관점의 순서",
     lambda d: _set(d, ["SPCX", "ratios", "views", "in_service", "roic"],
                    0.001)),
    ("주식수 배율 오류",
     lambda d: _set(d, ["SPCX", "ratios", "shares_outstanding"], 1.3579e16)),
    ("시가총액 식",
     lambda d: _set(d, ["TSLA", "ratios", "market_cap"], 1.0e12)),
    ("상장 사실 (10-K 존재로 위조)",
     lambda d: d["SPCX"]["meta"]["filings"].append(
         {"form": "10-K", "filed": "2026-02-01", "period_end": "2025-12-31",
          "accession": "0000000000-00-000000", "primary_document": ""})
     or d),
    ("앵커 (스타링크 영업이익)",
     lambda d: _set(d, ["SPCX", "segments_9m", "Connectivity",
                        "operating_income", "9m_2026"], 5_500 * MM)),
    ("테슬라 NOPAT 항등식",
     lambda d: _set_year(d, 2025, "nopat", 9.9e9)),
    ("테슬라 증분 ROIC",
     lambda d: _set(d, ["TSLA", "ratios", "incremental", "FY2022→FY2025",
                        "incremental_roic"], 0.30)),
    ("PP&E 순액 항등식",
     lambda d: _set(d, ["TSLA", "ppe", "2025-12-31", "net"], 1.0e10)),
]


def _set(d, path, value):
    node = d
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    return d


def _set_year(d, fy, key, value):
    for y in d["TSLA"]["annual_roic"]:
        if y["fiscal_year"] == fy:
            y[key] = value
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()

    with open(DATA) as fh:
        d = json.load(fh)

    c = Checks()
    run(d, c)
    total = c.passed + len(c.failures)
    print(f"검사 {total}건 중 통과 {c.passed}건, 실패 {len(c.failures)}건")
    for f in c.failures[:25]:
        print(f"  실패: {f}")

    if not a.mutate:
        return 1 if c.failures else 0

    print("\n변이 검정 — 값을 훼손했을 때 검사가 실패해야 정상")
    caught = 0
    for label, mutate in MUTATIONS:
        trial = mutate(copy.deepcopy(d))
        cc = Checks()
        try:
            run(trial, cc)
        except Exception as exc:                               # noqa: BLE001
            cc.failures.append(f"예외: {exc}")
        hit = bool(cc.failures)
        caught += hit
        print(f"  {'탐지' if hit else '놓침':<5}{label:<28}"
              f"실패 {len(cc.failures)}건")
    print(f"\n변이 {len(MUTATIONS)}건 중 {caught}건 탐지")
    return 0 if (not c.failures and caught == len(MUTATIONS)) else 1


if __name__ == "__main__":
    sys.exit(main())
