"""
Read the Markdown report back and check every figure against roic.json.

The workbook's numbers are formulas, so verify_roic_exports.py can re-evaluate
them. Markdown has no formulas - the figures are rendered text, and a rendering
mistake (a column shifted, a company's row paired with another's numbers, a
percentage printed as a fraction) leaves no trace that reading the file would
reveal. So the tables are parsed back into numbers and compared to the engine,
which is the only way to know the document says what it claims.

Rounding is accounted for rather than ignored: a cell printed to the nearest
whole percent is checked against the engine's value rounded the same way, so a
genuine mismatch of 1pp still fails.

    python3 verify_roic_md.py
    python3 verify_roic_md.py --mutate
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

import company_names as cn

HERE = os.path.dirname(os.path.abspath(__file__))
MD = os.path.join(HERE, "미국50개사_ROIC_WACC비교.md")
ROIC = os.path.join(HERE, "roic", "roic.json")
WACC = 0.10
MM = 1e6


def parse_tables(text):
    """Every Markdown table in the document, each as (heading path, header
    row, data rows)."""
    tables, heads = [], []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            heads = heads[:level - 1] + [m.group(2).strip()]
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and \
                re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            header = [c.strip() for c in line.strip("|").split("|")]
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            tables.append((list(heads), header, rows))
            continue
        i += 1
    return tables


def num(s):
    """A rendered cell back to a number, or None for a dash."""
    s = s.strip().strip("*")
    if s in ("—", "", "-"):
        return None
    neg_brackets = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "").replace("†", "").replace("*", "")
    s = s.replace("%p", "").replace("%", "").replace("+", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return v


# Each entry corrupts one rendered figure or mark. The point is not that the
# document is currently right - it is that these checks fail when it is wrong.
MUTATIONS = [
    ("연도별 수치", "| 아리스타 네트웍스 | 109 |",
     "| 아리스타 네트웍스 | 119 |"),
    ("괄호 표기 (문턱 판정)", "| RTX | 14 | 11 | (3) |",
     "| RTX | 14 | 11 | 3 |"),
    ("추정 표시 제거", "| 셰브론 | (-1*) |", "| 셰브론 | (-1) |"),
    ("순위표 중위값", "| 1 | 아리스타 네트웍스 | 165% |",
     "| 1 | 아리스타 네트웍스 | 175% |"),
    ("순위표 기업명 교체", "| 2 | 엔비디아 |", "| 2 | 애플 |"),
    ("계산 명세 금액", "| FY2025 | 129,039 |", "| FY2025 | 129,999 |"),
    ("기업 목록 영문명", "| AAPL | 애플 | Apple |",
     "| AAPL | 애플 | Orange |"),
    ("기초 참조 행에 값", "| FY2015 ◦ | — | — | — | 101 | — | — |",
     "| FY2015 ◦ | 149 | — | — | 101 | — | — |"),
]


def mutate():
    """Corrupt the document one figure at a time and confirm main() fails."""
    original = open(MD).read()
    backup = MD + ".mutation-backup"
    shutil.copy2(MD, backup)
    caught, skipped = 0, 0
    print("\n변이 검정 — 수치를 고의로 훼손했을 때 검사가 실패해야 정상")
    try:
        for label, before, after in MUTATIONS:
            if before not in original:
                skipped += 1
                print(f"  {'대상없음':<6}{label}")
                continue
            with open(MD, "w") as fh:
                fh.write(original.replace(before, after, 1))
            run = subprocess.run([sys.executable, __file__],
                                 capture_output=True, text=True)
            hit = run.returncode != 0
            caught += hit
            line = next((l.strip() for l in run.stdout.split("\n")
                         if "실패:" in l), "")
            print(f"  {'탐지' if hit else '놓침':<6}{label:<24}{line[:70]}")
    finally:
        with open(MD, "w") as fh:
            fh.write(original)
        os.remove(backup)
    total = len(MUTATIONS) - skipped
    print(f"\n변이 {total}건 중 {caught}건 탐지")
    return 0 if caught == total and total else 1


def main():
    text = open(MD).read()
    data = json.load(open(ROIC))
    tables = parse_tables(text)

    by = {c["ticker"]: {y["fiscal_year"]: y for y in c["years"]}
          for c in data["companies"]}
    summ = {c["ticker"]: c["summary"] for c in data["companies"]}
    ko2tk = {cn.korean(t): t for t in by}

    checks, fails = 0, []

    def expect(got, want, label, nd):
        """Compare a rendered figure to the engine's, at the precision it was
        rendered to."""
        nonlocal checks
        checks += 1
        if want is None:
            if got is not None:
                fails.append(f"{label}: 값이 없어야 하는데 {got}")
            return
        if got is None:
            fails.append(f"{label}: 값이 비어 있음 (기대 {want})")
            return
        if round(got, nd) != round(want, nd):
            fails.append(f"{label}: {got} != {round(want, nd)}")

    seen_sections = set()

    for heads, header, rows in tables:
        path = " / ".join(heads)

        # --- 기업 목록 --------------------------------------------------
        if header[:3] == ["티커", "한글명", "영문 정식 명칭"]:
            seen_sections.add("roster")
            for r in rows:
                tk, ko, en = r[0], r[1], r[2]
                checks += 3
                if tk not in by:
                    fails.append(f"기업 목록: 알 수 없는 티커 {tk}")
                if ko != cn.korean(tk):
                    fails.append(f"기업 목록 {tk}: 한글명 {ko}")
                if en != cn.english(tk):
                    fails.append(f"기업 목록 {tk}: 영문명 {en}")

        # --- 요약 순위 --------------------------------------------------
        elif header == ["#", "기업", "중위", "최소", "최대", "초과"]:
            seen_sections.add("rank")
            checks += 1
            if len(rows) != len(data["ranking"]):
                fails.append(f"순위표 행 수 {len(rows)} != "
                             f"{len(data['ranking'])}")
            for i, r in enumerate(rows):
                want_tk = data["ranking"][i]["ticker"]
                checks += 2
                if r[1] != cn.korean(want_tk):
                    fails.append(f"순위 {i+1}: {r[1]} != "
                                 f"{cn.korean(want_tk)}")
                if r[0] != str(i + 1):
                    fails.append(f"순위 번호 {r[0]} != {i+1}")
                s = summ[want_tk]
                for col, key in ((2, "roic_median"), (3, "roic_min"),
                                 (4, "roic_max")):
                    expect(num(r[col]), s[key] * 100,
                           f"순위 {cn.korean(want_tk)} {header[col]}", 0)
                checks += 1
                want_cnt = f"{s['years_above_wacc']}/{s['years_usable']}"
                if r[5] != want_cnt:
                    fails.append(f"순위 {cn.korean(want_tk)} 초과: "
                                 f"{r[5]} != {want_cnt}")

        # --- 연도별 그리드 ----------------------------------------------
        elif header[0] == "기업" and all(h.startswith("'")
                                       for h in header[1:]):
            seen_sections.add("grid")
            years = [2000 + int(h.strip("'")) for h in header[1:]]
            for r in rows:
                tk = ko2tk.get(r[0])
                checks += 1
                if tk is None:
                    fails.append(f"연도별 그리드: 모르는 기업 {r[0]}")
                    continue
                for col, fy in enumerate(years, start=1):
                    raw = r[col]
                    y = by[tk].get(fy)
                    want = None if (y is None or y["roic"] is None) \
                        else y["roic"] * 100
                    label = f"연도별 {r[0]} FY{fy}"
                    expect(num(raw), want, label, 0)

                    # The brackets and marks carry meaning, so they are checked
                    # too - a figure printed without its estimate mark reads as
                    # firmer than it is.
                    if want is None:
                        continue
                    checks += 3
                    bracketed = raw.startswith("(")
                    if bracketed != (y["roic"] <= WACC):
                        fails.append(f"{label}: 괄호 표기 오류 ({raw})")
                    if ("*" in raw) != (y["confidence"] == "LOW"):
                        fails.append(f"{label}: 추정 표시(*) 오류 ({raw})")
                    if ("†" in raw) != bool(y.get("capital_too_small")):
                        fails.append(f"{label}: 자본 표시(†) 오류 ({raw})")

        # --- 기업별 계산 명세 -------------------------------------------
        elif header == ["연도", "영업이익", "세율", "NOPAT", "투하자본",
                        "평균", "ROIC"]:
            seen_sections.add("detail")
            m = re.match(r"^(.*?) — .* \((.+)\)$", heads[-1])
            checks += 1
            if not m:
                fails.append(f"계산 명세 제목 해석 불가: {heads[-1]}")
                continue
            tk = m.group(2)
            if tk not in by:
                fails.append(f"계산 명세: 모르는 티커 {tk}")
                continue
            for r in rows:
                fy = int(r[0].replace("FY", "").replace("◦", "").strip())
                y = by[tk].get(fy)
                checks += 1
                if y is None:
                    fails.append(f"계산 명세 {tk} FY{fy}: 엔진에 없는 연도")
                    continue
                label = f"계산 명세 {tk} FY{fy}"
                if fy == 2015:
                    expect(num(r[4]),
                           None if y["invested_capital"] is None
                           else y["invested_capital"] / MM,
                           f"{label} 투하자본", 0)
                    for col in (1, 2, 3, 5, 6):
                        checks += 1
                        if r[col] != "—":
                            fails.append(f"{label}: 기초 참조 행인데 "
                                         f"{header[col]}에 값 {r[col]}")
                    continue
                for col, key, scale, nd in (
                        (1, "operating_income", MM, 0),
                        (3, "nopat", MM, 0),
                        (4, "invested_capital", MM, 0),
                        (5, "invested_capital_avg", MM, 0)):
                    v = y[key]
                    expect(num(r[col]), None if v is None else v / scale,
                           f"{label} {header[col]}", nd)
                expect(num(r[2]), y["effective_tax_rate"] * 100,
                       f"{label} 세율", 0)
                expect(num(r[6]),
                       None if y["roic"] is None else y["roic"] * 100,
                       f"{label} ROIC", 1)

    # Every company must have a detail table and a row in both grid halves.
    detail_tickers = set()
    grid_rows = {}
    for heads, header, rows in tables:
        if header == ["연도", "영업이익", "세율", "NOPAT", "투하자본",
                      "평균", "ROIC"]:
            m = re.match(r"^.*\((.+)\)$", heads[-1])
            if m:
                detail_tickers.add(m.group(1))
        elif header[0] == "기업" and all(h.startswith("'")
                                       for h in header[1:]):
            grid_rows[header[1]] = {r[0] for r in rows}

    checks += 1
    missing = set(by) - detail_tickers
    if missing:
        fails.append(f"계산 명세가 없는 기업: {sorted(missing)}")

    ranked_names = {cn.korean(x["ticker"]) for x in data["ranking"]}
    for half, names in grid_rows.items():
        checks += 1
        if names != ranked_names:
            fails.append(f"연도별 그리드 {half}: 기업 집합 불일치 — "
                         f"누락 {sorted(ranked_names - names)}")

    for want in ("roster", "rank", "grid", "detail"):
        checks += 1
        if want not in seen_sections:
            fails.append(f"필수 섹션 누락: {want}")

    print(f"MD 검사 {checks}건 중 통과 {checks - len(fails)}건, "
          f"실패 {len(fails)}건")
    for f in fails[:30]:
        print(f"  실패: {f}")
    if len(fails) > 30:
        print(f"  … 외 {len(fails) - 30}건")
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutate", action="store_true",
                    help="수치를 고의로 훼손해 검사가 실제로 실패하는지 확인")
    args = ap.parse_args()
    code = main()
    if args.mutate:
        code = mutate() or code
    sys.exit(code)
