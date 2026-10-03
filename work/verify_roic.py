"""
Checks on the independent ROIC re-derivation.

Three kinds of check, and they catch different things.

Identities re-compute every published number from its inputs. They catch a
broken formula but say nothing about whether the inputs are the right ones.

Tripwires are constraints the real world imposes that a tagging mistake tends
to violate: cash subtracted from capital cannot exceed current assets, because
cash and short-term investments are both current assets; debt cannot exceed
total assets; an effective tax rate outside its clamp means the clamp did not
run. Each of these has already caught something. The cash tripwire is why the
within-one-year maturity column is no longer in the short-term-investments tag
list - it put $4,844m of Lam Research's portfolio into the subtraction against
$1,106m actually on the balance sheet.

Anchors are figures read off the face of the filings by hand. Identities and
tripwires are both self-referential: they are computed from the same data they
are checking, so a wrong figure that is internally consistent passes both. An
anchor is the only check here that can fail because the data is wrong rather
than because the arithmetic is.

Mutation tests close the loop by corrupting values on purpose and confirming
the checks fail. A test suite that passes on bad data is not a test suite.

    python3 verify_roic.py
    python3 verify_roic.py --mutate
"""

import argparse
import copy
import json
import os
import sys

import company_names as cn

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "roic", "roic_raw.json")
RES = os.path.join(HERE, "roic", "roic.json")

TOL = 1e-6          # relative, for identities
LOW_CONF_ROUTES = {"pretax_less_nonoperating",
                   "pretax_plus_interest_less_investment_income"}
WACC = 0.10

# Read off the face of the filings. Dollar figures are as reported, in millions
# where the filing reports millions and dollars where it reports thousands -
# every one is scaled to dollars here.
ANCHORS = [
    # (ticker, fiscal year, field, value, source)
    ("GOOG", 2025, "revenue", 402_836e6, "Alphabet FY2025 10-K 손익계산서"),
    ("GOOG", 2025, "operating_income", 129_039e6, "Alphabet FY2025 10-K"),
    ("GOOG", 2025, "total_equity", 415_265e6, "Alphabet FY2025 10-K 재무상태표"),
    ("GOOG", 2024, "operating_income", 112_390e6, "Alphabet FY2024 10-K"),
    ("GOOG", 2016, "operating_income", 23_716e6, "Alphabet FY2016 10-K"),
    ("NVDA", 2025, "revenue", 215_938e6, "NVIDIA FY2026(1월결산) 10-K"),
    ("NVDA", 2025, "operating_income", 130_387e6, "NVIDIA FY2026 10-K"),
    ("NVDA", 2025, "total_equity", 157_293e6, "NVIDIA FY2026 10-K"),
    ("MSFT", 2016, "operating_income", 26_078e6, "Microsoft FY2016 10-K"),
    ("MSFT", 2016, "total_equity", 83_090e6, "Microsoft FY2016 10-K"),
    ("AAPL", 2025, "revenue", 416_161e6, "Apple FY2025 10-K"),
    ("KO", 2017, "operating_income", 7_755e6, "Coca-Cola FY2017 10-K"),
    ("ANET", 2025, "operating_income", 3_856e6, "Arista FY2025 10-K"),
    ("ANET", 2025, "interest_bearing_debt", 0.0, "Arista 무차입 — 차입금 라인 없음"),
    ("LRCX", 2019, "cash_and_short_term_investments",
     (3_658.219 + 1_772.984) * 1e6,
     "Lam FY2019 10-K: 현금 3,658.2 + 유동투자자산 1,773.0"),
    ("ORCL", 2024, "total_equity", 9_239e6, "Oracle FY2024 10-K (NCI 포함)"),
    ("ORCL", 2024, "interest_bearing_debt", 86_869e6,
     "Oracle FY2024 10-K: 비유동 76,264 + 유동 10,605"),
    ("ORCL", 2025, "interest_bearing_debt", 92_568e6,
     "Oracle FY2025 10-K: 비유동 85,297 + 유동 7,271"),
    ("AAPL", 2016, "interest_bearing_debt", 87_032e6,
     "Apple FY2016 10-K: 장기 75,427 + 유동 3,500 + CP 8,105"),
]


class Checks:
    def __init__(self):
        self.passed = 0
        self.failures = []

    def ok(self, cond, label):
        if cond:
            self.passed += 1
        else:
            self.failures.append(label)
        return bool(cond)

    def close(self, got, want, label, tol=TOL):
        if got is None or want is None:
            return self.ok(False, f"{label}: 값 없음 (got={got}, want={want})")
        scale = max(abs(want), 1.0)
        return self.ok(abs(got - want) / scale <= tol,
                       f"{label}: {got!r} != {want!r}")


def run(raw, res, c):
    raw_by = {x["ticker"]: {y["period_end"]: y for y in x["years"]}
              for x in raw["companies"]}

    c.ok(len(res["companies"]) == 50, f"기업 수 50 != {len(res['companies'])}")
    c.ok(res["wacc"] == WACC, "WACC 10% 아님")
    c.ok(res["window"] == [2016, 2025], "창이 FY2016~FY2025 아님")

    tickers = [x["ticker"] for x in res["companies"]]
    c.ok(len(set(tickers)) == len(tickers), "티커 중복")

    # A ticker with no readable name would print blank in the reports rather
    # than failing, so it fails here instead.
    missing, orphan = cn.check(tickers)
    c.ok(not missing, f"company_names.py에 이름 없는 티커: {missing}")
    c.ok(not orphan, f"company_names.py에만 있는 티커: {orphan}")
    edgar = {x["ticker"]: x["company_name"] for x in res["companies"]}
    for t in tickers:
        c.ok(bool(cn.korean(t)), f"{t}: 한글명 없음")
        c.ok(bool(cn.english(t)), f"{t}: 영문명 없음")
        # A name left as the registrant name means it was never written: the
        # whole point of the module is not to print COSTCO WHOLESALE CORP /NEW
        # at a reader. IBM, AMD and RTX are genuinely their own names and are
        # not caught by this, because the registrant names are INTERNATIONAL
        # BUSINESS MACHINES CORP, ADVANCED MICRO DEVICES INC and RTX Corp.
        c.ok(cn.korean(t) != edgar[t] and cn.english(t) != edgar[t],
             f"{t}: 이름이 SEC 등록명 그대로 ({edgar[t]})")
        c.ok(cn.label(t).count("(") == cn.label(t).count(")"),
             f"{t}: 라벨 괄호 불균형 ({cn.label(t)})")

    for comp in res["companies"]:
        tk = comp["ticker"]
        rows = raw_by.get(tk, {})
        ends = [y["period_end"] for y in comp["years"]]
        c.ok(len(set(ends)) == len(ends), f"{tk}: 기말일 중복")
        c.ok(ends == sorted(ends), f"{tk}: 기말일 정렬 안 됨")

        prev_ic = None
        for i, y in enumerate(comp["years"]):
            fy, tag = y["fiscal_year"], f"{tk} FY{y['fiscal_year']}"
            src = rows.get(y["period_end"], {})

            # Identity: invested capital
            eq, debt = y["total_equity"], y["interest_bearing_debt"]
            cash = y["cash_and_short_term_investments"]
            if None not in (eq, debt, cash):
                c.close(y["invested_capital"], eq + debt - cash,
                        f"{tag}: 투하자본 = 자기자본+차입금-현금")
            else:
                c.ok(y["invested_capital"] is None,
                     f"{tag}: 구성요소가 없는데 투하자본이 있음")

            # Identity: NOPAT
            if y["operating_income"] is not None:
                c.close(y["nopat"],
                        y["operating_income"] * (1 - y["effective_tax_rate"]),
                        f"{tag}: NOPAT = 영업이익x(1-세율)")

            # Identity: the averaging rule, including its exceptions
            ic = y["invested_capital"]
            if ic is not None:
                if i == 0 or prev_ic is None or \
                        comp["years"][i - 1]["fiscal_year"] != fy - 1:
                    c.close(y["invested_capital_avg"], ic,
                            f"{tag}: 직전연도 없으면 기말 사용")
                elif prev_ic <= 0 or ic <= 0:
                    c.close(y["invested_capital_avg"], ic,
                            f"{tag}: 부호 전환 시 기말 단독 사용")
                else:
                    c.close(y["invested_capital_avg"], (ic + prev_ic) / 2.0,
                            f"{tag}: 기초·기말 평균")

            # Identity: ROIC
            avg = y["invested_capital_avg"]
            if y["roic"] is not None:
                c.ok(avg is not None and avg > 0,
                     f"{tag}: ROIC가 있는데 평균투하자본이 0 이하")
                c.ok(not y["cash_hole_suspected"],
                     f"{tag}: 현금 공백으로 표시됐는데 ROIC가 있음")
                if avg:
                    c.close(y["roic"], y["nopat"] / avg, f"{tag}: ROIC 식")
            else:
                c.ok(y["roic_status"] != "OK",
                     f"{tag}: ROIC가 없는데 상태가 OK")

            in_window = 2016 <= fy <= 2025

            # Tripwire: cash cannot exceed current assets
            ca = src.get("current_assets")
            if in_window and cash is not None and ca:
                c.ok(cash <= ca * 1.001,
                     f"{tag}: 차감 현금 {cash:,.0f} > 유동자산 {ca:,.0f}")

            # Tripwire: debt cannot exceed total assets, nor total
            # liabilities. The liabilities bound is the tighter of the two and
            # is what catches a double count: Oracle's May-2024 debt came out
            # at $97.5bn because the combined total and the current portion
            # inside it were added together.
            ta = src.get("total_assets")
            if in_window and debt is not None and ta:
                c.ok(debt <= ta * 1.001,
                     f"{tag}: 차입금 {debt:,.0f} > 총자산 {ta:,.0f}")
            tl = src.get("total_liabilities")
            if in_window and debt is not None and tl:
                c.ok(debt <= tl * 1.001,
                     f"{tag}: 차입금 {debt:,.0f} > 총부채 {tl:,.0f}")

            # Tripwire: the tax clamp ran
            c.ok(0.05 - 1e-9 <= y["effective_tax_rate"] <= 0.40 + 1e-9,
                 f"{tag}: 실효세율 {y['effective_tax_rate']} 범위 밖")

            # Tripwire: debt is never negative
            if debt is not None:
                c.ok(debt >= 0, f"{tag}: 차입금 음수 {debt}")

            # Every reconstructed year must carry a reconciliation inside the
            # 5% gate, and the route must be the one chosen for the company
            # unless that route could not be built that year.
            route = y["operating_income_route"]
            d = y.get("route_detail") or {}
            if route not in ("reported", "unavailable") \
                    and not route.endswith("_unreconciled") \
                    and route not in LOW_CONF_ROUTES:
                err = d.get("chosen_tie_out_error")
                c.ok(err is not None and err <= 0.05,
                     f"{tag}: {route} 역검증 미통과 (오차 {err})")
            if route not in ("reported", "unavailable"):
                pref = ((d.get("company_route") or {}).get("preference")
                        or [route])
                c.ok(route in pref or route.endswith("_unreconciled"),
                     f"{tag}: 경로 {route}가 회사 우선순위 {pref}에 없음")

            # Confidence must follow the route, not be set independently
            want = ("HIGH" if route in ("reported", "verified_line_build")
                    else "LOW" if route in LOW_CONF_ROUTES
                    or route.endswith("_unreconciled") else "MEDIUM")
            if not y["cash_hole_suspected"]:
                c.ok(y["confidence"] == want,
                     f"{tag}: 신뢰도 {y['confidence']} != {want} (경로 {route})")

            # The fiscal label must sit on its period end
            yr = int(y["period_end"][:4])
            mo = int(y["period_end"][5:7])
            c.ok(fy == (yr - 1 if mo <= 2 else yr),
                 f"{tag}: 회계연도 라벨이 기말({y['period_end']})과 불일치")

            prev_ic = ic

        # Summary consistency
        s = comp["summary"]
        win = [y for y in comp["years"] if 2016 <= y["fiscal_year"] <= 2025]
        usable = [y["roic"] for y in win if y["roic"] is not None]
        c.ok(s["years_usable"] == len(usable),
             f"{tk}: 산출 연도 수 {s['years_usable']} != {len(usable)}")
        if usable:
            c.close(s["roic_min"], min(usable), f"{tk}: 최소 ROIC")
            c.close(s["roic_max"], max(usable), f"{tk}: 최대 ROIC")
            c.ok(s["years_above_wacc"] == sum(1 for r in usable if r > WACC),
                 f"{tk}: 문턱 초과 연수")
            c.ok(s["years_above_wacc"] + s["years_below_wacc"] == len(usable),
                 f"{tk}: 초과+미달 != 산출 연수")
            c.close(s["spread_median"], s["roic_median"] - WACC,
                    f"{tk}: 스프레드 = 중위 ROIC - WACC")
        c.ok(comp["is_financial"] == (s["verdict"].startswith("금융업")),
             f"{tk}: 금융업 표시와 판정 불일치")

    # Financials carry no ROIC at all
    for comp in res["companies"]:
        if comp["is_financial"]:
            c.ok(all(y["roic"] is None for y in comp["years"]),
                 f"{comp['ticker']}: 금융업인데 ROIC가 산출됨")

    # Ranking is sorted and holds only companies that clear the sample floor
    rank = res["ranking"]
    meds = [r["roic_median"] for r in rank]
    c.ok(meds == sorted(meds, reverse=True), "순위가 중위 ROIC 내림차순 아님")
    c.ok(all(r["years_usable"] >= res["min_years_for_ranking"] for r in rank),
         "순위에 표본 부족 기업이 포함됨")

    # Anchors
    res_by = {x["ticker"]: {y["fiscal_year"]: y for y in x["years"]}
              for x in res["companies"]}
    for tk, fy, field, want, source in ANCHORS:
        y = res_by.get(tk, {}).get(fy)
        if not c.ok(y is not None, f"앵커 {tk} FY{fy} 연도 없음 ({source})"):
            continue
        c.close(y.get(field), want, f"앵커 {tk} FY{fy} {field} ({source})",
                tol=2e-4)


MUTATIONS = [
    ("투하자본 항등식", lambda r: _poke(r, "GOOG", 2025, "invested_capital",
                                   lambda v: v * 1.05)),
    ("NOPAT 항등식", lambda r: _poke(r, "MSFT", 2024, "nopat",
                                   lambda v: v + 1e9)),
    ("ROIC 식", lambda r: _poke(r, "AAPL", 2023, "roic",
                               lambda v: v + 0.02)),
    ("평균투하자본 규칙", lambda r: _poke(r, "KO", 2020, "invested_capital_avg",
                                   lambda v: v * 0.9)),
    ("세율 클램프", lambda r: _poke(r, "XOM", 2020, "effective_tax_rate",
                                lambda v: 0.95)),
    ("차입금 음수", lambda r: _poke(r, "WMT", 2022, "interest_bearing_debt",
                                lambda v: -v)),
    ("앵커 (알파벳 영업이익)",
     lambda r: _poke(r, "GOOG", 2025, "operating_income",
                     lambda v: v * 1.01)),
    ("금융업 ROIC 미산출", lambda r: _poke(r, "JPM", 2023, "roic",
                                     lambda v: 0.15)),
    ("순위 정렬", lambda r: r["ranking"].reverse() or r),
    ("요약 최대값", lambda r: _poke_summary(r, "HD", "roic_max",
                                        lambda v: v * 1.5)),
]


def _poke(res, ticker, fy, field, fn):
    for comp in res["companies"]:
        if comp["ticker"] != ticker:
            continue
        for y in comp["years"]:
            if y["fiscal_year"] == fy:
                if y.get(field) is None:
                    y[field] = 1.0
                else:
                    y[field] = fn(y[field])
                return res
    raise SystemExit(f"변이 대상 없음: {ticker} FY{fy} {field}")


def _poke_summary(res, ticker, field, fn):
    for comp in res["companies"]:
        if comp["ticker"] == ticker:
            comp["summary"][field] = fn(comp["summary"][field])
            return res
    raise SystemExit(f"변이 대상 없음: {ticker} {field}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutate", action="store_true",
                    help="값을 고의로 훼손해 검사가 실제로 실패하는지 확인")
    a = ap.parse_args()

    with open(RAW) as fh:
        raw = json.load(fh)
    with open(RES) as fh:
        res = json.load(fh)

    c = Checks()
    run(raw, res, c)
    total = c.passed + len(c.failures)
    print(f"검사 {total}건 중 통과 {c.passed}건, 실패 {len(c.failures)}건")
    for f in c.failures[:40]:
        print(f"  실패: {f}")
    if len(c.failures) > 40:
        print(f"  … 외 {len(c.failures) - 40}건")

    if not a.mutate:
        return 0 if not c.failures else 1

    print("\n변이 검정 — 각 항목을 훼손했을 때 검사가 실패해야 정상")
    caught = 0
    for label, mutate in MUTATIONS:
        trial = mutate(copy.deepcopy(res))
        cc = Checks()
        try:
            run(raw, trial, cc)
        except Exception as exc:                       # noqa: BLE001
            cc.failures.append(f"예외: {exc}")
        hit = bool(cc.failures)
        caught += hit
        print(f"  {'탐지' if hit else '놓침':<5} {label:<28}"
              f"실패 {len(cc.failures)}건")
    print(f"\n변이 {len(MUTATIONS)}건 중 {caught}건 탐지")
    return 0 if (not c.failures and caught == len(MUTATIONS)) else 1


if __name__ == "__main__":
    sys.exit(main())
