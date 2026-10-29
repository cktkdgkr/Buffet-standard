"""
What today's date means for the data this project has already collected.

Run at the start of every session by .claude/hooks/session-start.sh, and
runnable by hand. It answers one question: is there anything filed since we
last looked?

For each company in the study it reads the SEC filing index - small, one
request each - and compares the newest annual or quarterly filing against the
newest period the analysis actually covers. A company that has filed since is
listed as stale, with the form and the date, so the gap is a line of output
rather than something to notice later in a number.

This exists because the opposite happened. The companyfacts cache had no
expiry, so a rerun on 29 October silently reused a copy taken on 3 October and
four weeks of filings never entered the analysis. Nothing failed.

    python3 check_freshness.py              # 요약
    python3 check_freshness.py --verbose    # 기업별 전체
    python3 check_freshness.py --quick      # 캐시 나이만 (네트워크 없음)
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sec_cache                                               # noqa: E402

CACHE = os.path.join(HERE, "roic", "cache")
DATASETS = [
    # (label, json file, how to pull out {ticker: (cik, latest period end)})
    ("미국 50개사 ROIC", os.path.join(HERE, "roic", "roic.json"), "roic"),
]
ANNUAL = ("10-K", "10-K/A", "20-F", "40-F")
QUARTERLY = ("10-Q", "10-Q/A")


def load_roic(path):
    with open(path) as fh:
        d = json.load(fh)
    out = {}
    for c in d["companies"]:
        ends = [y["period_end"] for y in c["years"] if y.get("period_end")]
        out[c["ticker"]] = {"cik": int(c["cik"]),
                            "covered_to": max(ends) if ends else None,
                            "name": c["company_name"]}
    return out, d.get("generated")


def latest_filings(cik, refresh, max_age_days):
    """The newest annual and quarterly filing the SEC has for this CIK."""
    sub, from_net, before = sec_cache.submissions(
        cik, CACHE, refresh=refresh, max_age_days=max_age_days)
    recent = sub["filings"]["recent"]
    newest = {}
    for form, filed, end, acc in zip(recent["form"], recent["filingDate"],
                                     recent.get("reportDate",
                                                [""] * len(recent["form"])),
                                     recent["accessionNumber"]):
        group = ("annual" if form in ANNUAL
                 else "quarterly" if form in QUARTERLY else None)
        if group is None:
            continue
        cur = newest.get(group)
        if cur is None or filed > cur["filed"]:
            newest[group] = {"form": form, "filed": filed,
                             "period_end": end, "accession": acc}
    return newest, sec_cache.describe(before, from_net), sub.get("name")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--quick", action="store_true",
                    help="네트워크 없이 캐시 나이만 보고")
    ap.add_argument("--refresh", action="store_true",
                    help="제출 색인을 강제로 다시 받음")
    ap.add_argument("--max-age-days", type=float, default=1.0)
    a = ap.parse_args()

    today = date.today()
    print(f"오늘 {today.isoformat()} ({today:%A})")

    if not os.path.isdir(CACHE):
        print("  수집 캐시가 없습니다 — collect_roic.py 를 먼저 실행하세요.")
        return 0

    # Cache age first: it needs no network and it is the fastest way to see
    # whether the collected data is anywhere near today.
    facts = [f for f in os.listdir(CACHE) if f.startswith("CIK")]
    if facts:
        ages = sorted(sec_cache.age_days(os.path.join(CACHE, f)) or 0
                      for f in facts)
        print(f"  companyfacts 캐시 {len(facts)}개 · 최신 {ages[0]:.1f}일 전 "
              f"· 중위 {ages[len(ages) // 2]:.1f}일 전 "
              f"· 최고 {ages[-1]:.1f}일 전")

    stale_datasets = []
    for label, path, kind in DATASETS:
        if not os.path.exists(path):
            print(f"  {label}: 산출물 없음 ({os.path.basename(path)})")
            continue
        generated = None
        if kind == "roic":
            companies, generated = load_roic(path)
        if generated:
            gen = datetime.fromisoformat(generated).date()
            print(f"  {label}: 분석 생성일 {generated} "
                  f"({(today - gen).days}일 전), {len(companies)}개사")
            if (today - gen).days > 7:
                stale_datasets.append(label)

        if a.quick:
            continue

        rows, errors = [], []
        for ticker, info in companies.items():
            try:
                newest, note, _ = latest_filings(
                    info["cik"], a.refresh, a.max_age_days)
            except Exception as exc:                           # noqa: BLE001
                errors.append(f"{ticker}: {exc}")
                continue
            covered = info["covered_to"]
            newer = []
            for group in ("annual", "quarterly"):
                f = newest.get(group)
                if not f:
                    continue
                end = f.get("period_end") or ""
                if covered and end and end > covered:
                    newer.append(f)
            rows.append({"ticker": ticker, "covered_to": covered,
                         "newer": newer, "newest": newest, "note": note})

        stale = [r for r in rows if r["newer"]]
        print(f"    제출 색인 확인 {len(rows)}개사 — "
              f"분석 이후 신규 공시 있는 기업 {len(stale)}개")
        if stale:
            print(f"    {'기업':<8}{'분석 반영 기말':<14}"
                  f"{'신규 공시':<10}{'제출일':<12}{'기말'}")
            for r in sorted(stale, key=lambda r: r["ticker"]):
                for f in r["newer"]:
                    print(f"    {r['ticker']:<8}{str(r['covered_to']):<14}"
                          f"{f['form']:<10}{f['filed']:<12}"
                          f"{f.get('period_end') or '—'}")
            print()
            print("    → 분석을 다시 돌리기 전에:")
            print("       python3 collect_roic.py --refresh && "
                  "bash run_roic.sh")
        if errors:
            print(f"    조회 실패 {len(errors)}건: {', '.join(errors[:5])}")

        if a.verbose:
            print(f"\n    {'기업':<8}{'반영 기말':<13}{'최신 연간':<24}"
                  f"{'최신 분기':<24}{'색인'}")
            for r in sorted(rows, key=lambda r: r["ticker"]):
                ann = r["newest"].get("annual") or {}
                qtr = r["newest"].get("quarterly") or {}
                fmt = (lambda f: f"{f.get('form','—')} {f.get('filed','')}"
                       f" ({f.get('period_end') or '—'})" if f else "—")
                print(f"    {r['ticker']:<8}{str(r['covered_to']):<13}"
                      f"{fmt(ann):<24}{fmt(qtr):<24}{r['note']}")

    if stale_datasets:
        print(f"\n주의: {', '.join(stale_datasets)} 의 분석 결과가 일주일 "
              f"넘게 지났습니다. 오늘 기준으로 결론을 내려면 다시 "
              f"수집하십시오.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
