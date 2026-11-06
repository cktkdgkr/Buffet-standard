"""
성장률 재검증 보고서 산출물 검증 — 마크다운.

HTML 은 export_buffett_standard_html.py --verify 가 자기 페이지를
검사합니다. 여기서는 마크다운을 되읽어 엔진 값과 대조합니다.

표를 헤더로 특정하고 행을 완전일치로 찾습니다. 기업별 기록 표와 격자 표는
헤더가 같으므로 **구획(### 제목)을 먼저 자릅니다.**

    python3 verify_buffett_standard_exports.py
    python3 verify_buffett_standard_exports.py --mutate
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "fv", "buffett_standard.json")
MD = os.path.join(HERE, "성장률_재검증_버핏기준_적정주가.md")
MM, BN = 1e6, 1e9
DKEYS = ["bond30", "bond30_plus3", "project10", "project11"]


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def sg(x, nd=1):
    return "—" if x is None else f"{x * 100:+.{nd}f}%"


def bn(x, nd=1):
    return "—" if x is None else f"{x / BN:,.{nd}f}"


def usd(x, nd=0):
    return "—" if x is None else f"${x:,.{nd}f}"


class Checks:
    def __init__(self):
        self.passed = 0
        self.failures = []

    def eq(self, name, got, want):
        if got == want:
            self.passed += 1
        else:
            self.failures.append(f"{name}: 산출물 {got!r} != 엔진 {want!r}")

    def true(self, name, cond, detail=""):
        if cond:
            self.passed += 1
        else:
            self.failures.append(f"{name}: 거짓 {detail}")


def md_tables(text):
    out, cur = [], []
    for line in text.splitlines():
        if line.startswith("|"):
            cur.append([c.strip() for c in line.strip("|").split("|")])
        elif cur:
            if len(cur) >= 2:
                out.append((cur[0], cur[2:]))
            cur = []
    if len(cur) >= 2:
        out.append((cur[0], cur[2:]))
    return out


def md_table(text, header_has, exact=False, ncols=None):
    """
    표를 헤더로 특정합니다.

    ncols 는 헤더 이름이 겹칠 때 쓰는 두 번째 조건입니다 — 기초율 요약표와
    거시 기준표가 둘 다 "기준"으로 시작하는데 열 수가 4와 2로 다릅니다.
    """
    def match(h):
        if ncols is not None and len(h) != ncols:
            return False
        return any(x == header_has for x in h) if exact \
            else any(header_has in x for x in h)

    hits = [(h, r) for h, r in md_tables(text) if match(h)]
    if len(hits) != 1:
        raise SystemExit(f"표 특정 실패: {header_has!r} 가 {len(hits)}개 "
                         f"(완전일치={exact}, 열수={ncols})")
    return hits[0]


def md_row(text, header_has, label, col=0, exact=True, header_exact=False,
           ncols=None):
    _, rows = md_table(text, header_has, header_exact, ncols)
    hit = [r for r in rows if len(r) > col
           and (r[col].strip("* ") == label if exact else label in r[col])]
    if len(hit) != 1:
        raise SystemExit(f"행 특정 실패: {header_has!r} 표에서 {label!r} 가 "
                         f"{len(hit)}개")
    return hit[0]


def md_section(text, prefix):
    i = text.find(f"### {prefix}")
    if i < 0:
        raise SystemExit(f"구획 특정 실패: ### {prefix}...")
    j = len(text)
    for tag in ("\n### ", "\n## "):
        k = text.find(tag, i + 4)
        if 0 <= k < j:
            j = k
    return text[i:j]


def check(text, d, c):
    macro, br, cos = d["macro"], d["base_rates"], d["companies"]
    infl = macro["breakeven_inflation_10y"]["rate"]
    dmap = {x["key"]: x for x in d["discount_options"]}
    ni, sl = br["net_income_10y"], br["sales_10y"]

    def nm(co):
        return f"{co['korean']}({co['ticker']})"

    c.true("MD 자료 기준일", d["generated"] in text)
    c.true("MD 0부 바로잡음", "## 0. 먼저 바로잡습니다" in text)
    c.true("MD 1부 10년 기록", "## 1. 세 기업의 지난 10년" in text)
    c.true("MD 2부 기초율", "## 2. 객관 기준 ①" in text)
    c.true("MD 3부 거시", "## 3. 객관 기준 ②" in text)
    c.true("MD 4부 버핏", "## 4. 객관 기준 ③" in text)
    c.true("MD 5부 격자", "## 5. 다시 계산한 적정주가" in text)
    c.true("MD 6부 안전마진", "## 6. 버핏이라면 살까" in text)
    c.true("MD 8부 반론", "## 8. 기초율이 반박하지 못하는 것" in text)

    # 0. 해명
    _, rows = md_table(text, "10년 평균 (NOPAT CAGR)")
    c.eq("MD 해명 행 수", len(rows), len(d["clarification"]["rows"]))
    for r in d["clarification"]["rows"]:
        hit = [x for x in rows
               if x[0] == r["korean"] and x[1] == r["scenario"]]
        c.true(f"MD 해명 {r['korean']} {r['scenario']} 행", len(hit) == 1)
        if len(hit) == 1:
            c.eq(f"MD 해명 {r['korean']} {r['scenario']} 1년차", hit[0][2],
                 pct(r["year1_growth"]))
            c.eq(f"MD 해명 {r['korean']} {r['scenario']} 10년차", hit[0][3],
                 pct(r["year10_growth"]))
            c.eq(f"MD 해명 {r['korean']} {r['scenario']} 10년 CAGR",
                 hit[0][4].strip("* "), pct(r["nopat_cagr_10y"], 2))

    # 1. 10년 기록 — 구획을 먼저 자릅니다.
    for co in cos:
        sec = md_section(text, nm(co))
        for h in co["history"]:
            r = md_row(sec, "ROIC", f"FY{h['fiscal_year']}")
            c.eq(f"MD {co['ticker']} FY{h['fiscal_year']} 매출", r[1],
                 bn(h["revenue"]))
            c.eq(f"MD {co['ticker']} FY{h['fiscal_year']} 영업이익", r[3],
                 bn(h["operating_income"]))
            c.eq(f"MD {co['ticker']} FY{h['fiscal_year']} ROIC",
                 r[5].strip("* "), pct(h["roic"]))
            if h["operating_income_growth"] is not None:
                c.eq(f"MD {co['ticker']} FY{h['fiscal_year']} 영업이익 증감",
                     r[4], sg(h["operating_income_growth"], 1))
            r2 = md_row(sec, "투하자본 (평균)", f"FY{h['fiscal_year']}")
            c.eq(f"MD {co['ticker']} FY{h['fiscal_year']} 투하자본", r2[1],
                 bn(h["invested_capital_avg"]))

    # 2. 기초율
    for lab, share in ni["bands"]:
        if share == 0:
            continue
        r = md_row(text, "성장률 구간", f"{lab}%")
        c.eq(f"MD 기초율 구간 {lab}", r[1], pct(share))
    r = md_row(text, "이 수준 이상이 나온 비율", "중위값")
    c.eq("MD 기초율 중위 실질", r[1], pct(ni["median"]))
    c.eq("MD 기초율 중위 명목", r[2].strip("* "), pct(ni["median"] + infl))
    r = md_row(text, "이 수준 이상이 나온 비율", "평균")
    c.eq("MD 기초율 평균 실질", r[1], pct(ni["mean"]))
    over10 = sum(s for l, s in ni["bands"]
                 if "~" in l and float(l.split("~")[0]) >= 10)
    r = md_row(text, "이 수준 이상이 나온 비율", "실질 10% 이상")
    c.eq("MD 실질 10% 이상 비율", r[3].strip("* "), pct(over10))
    c.true("MD 기초율 실질 명시", "실질(인플레이션 조정) 기준입니다" in text)
    c.true("MD 생존편향 명시", "생존" in text)
    c.true("MD 본문 중위 명목 환산",
           f"중위값 **{pct(ni['median'])}**(실질) = 명목 "
           f"**{pct(ni['median'] + infl)}**" in text)
    sl_over10 = sum(s for l, s in sl["bands"]
                    if "~" in l and float(l.split("~")[0]) >= 10)
    c.true("MD 매출 기초율 비교",
           f"중위 {pct(sl['median'])}(실질), 실질 10% 이상은 "
           f"{pct(sl_over10)}" in text)

    # 백분위 표. 성장률 라벨("기초율 중위 5.5%" 등)이 세 기업에 그대로
    # 반복되므로 라벨만으로는 특정되지 않습니다. 표가 "기업 실적 행 +
    # 가정 4행"을 기업 순서대로 쌓은 구조이므로 블록으로 순회합니다.
    _, prows = md_table(text, "기초율 백분위")
    c.eq("MD 백분위 표 행 수", len(prows), len(cos) * 5)
    for i, co in enumerate(cos):
        blk = prows[i * 5:(i + 1) * 5]
        c.eq(f"MD {co['ticker']} 백분위 블록 머리", blk[0][0].strip("* "),
             f"{nm(co)} 과거 10년 실적")
        c.eq(f"MD {co['ticker']} 과거 명목", blk[0][1],
             pct(co["own_cagr_nominal"]))
        c.eq(f"MD {co['ticker']} 과거 실질", blk[0][2],
             pct(co["own_cagr_real"]))
        c.eq(f"MD {co['ticker']} 과거 백분위", blk[0][3].strip("* "),
             f"상위 {pct(co['own_cagr_percentile_at_or_above'])}")
        for g, r in zip(co["grid"], blk[1:]):
            c.eq(f"MD {co['ticker']} {g['growth_key']} 라벨", r[0],
                 f"— {g['growth_label'][:30]}")
            c.eq(f"MD {co['ticker']} {g['growth_key']} 명목", r[1],
                 pct(g["growth"]))
            c.eq(f"MD {co['ticker']} {g['growth_key']} 실질", r[2],
                 pct(g["growth_real"]))
            c.eq(f"MD {co['ticker']} {g['growth_key']} 백분위", r[3],
                 f"상위 {pct(g['base_rate_percentile_at_or_above'])}")

    # 3. 거시
    c.eq("MD 장기 실질 GDP",
         md_row(text, "기준", "장기 실질 GDP 성장률 (1950–2015)",
                header_exact=True, ncols=2)[1], pct(br["gdp_real_1950_2015"]))
    c.eq("MD 기대인플레이션",
         md_row(text, "기준", "10년 기대인플레이션 (FRED T10YIE)",
                header_exact=True, ncols=2)[1], pct(infl, 2))
    c.eq("MD 명목 GDP 상한",
         md_row(text, "기준", "→ 장기 명목 GDP (상한)",
                header_exact=True, ncols=2)[1].strip("* "),
         pct(macro["nominal_gdp_long_run"]["rate"], 2))
    c.eq("MD 30년 국채",
         md_row(text, "기준", "30년 국채 수익률", header_exact=True,
                ncols=2)[1],
         pct(macro["treasury_30y"]["rate"], 3))

    # 4. 버핏 인용 — 전문
    for q in d["buffett"]:
        c.true(f"MD 버핏 {q['year']} 인용 전문", q["quote"] in text,
               q["quote"][:45])
        c.true(f"MD 버핏 {q['year']} 출처", q["url"] in text)
        c.true(f"MD 버핏 {q['year']} 주석", q["note"] in text)
    for x in d["discount_options"]:
        r = md_row(text, "할인율 후보", x["label"])
        c.eq(f"MD 할인율 {x['key']}", r[1].strip("* "), pct(x["rate"], 2))
        c.true(f"MD 할인율 {x['key']} 근거", x["basis"] in text)
    c.true("MD 3%p 해석 단서", "버핏의 규칙이 아닙니다" in text)
    c.true("MD 발산 논거", "가치가 무한" in text)

    # 5. 격자 — 구획을 먼저 자릅니다.
    for co in cos:
        sec = md_section(text, f"{nm(co)} — 현재가")
        for g in co["grid"]:
            r = md_row(sec, "1년차", g["growth_label"][:28].strip())
            c.eq(f"MD 격자 {co['ticker']} {g['growth_key']} 1년차", r[1],
                 pct(g["growth"]))
            for i, dk in enumerate(DKEYS, start=2):
                c_ = [x for x in g["cells"] if x["discount_key"] == dk][0]
                want = ("발산" if c_["diverges"]
                        else usd(c_["value_per_share"]))
                c.eq(f"MD 격자 {co['ticker']} {g['growth_key']} @{dk}",
                     r[i].strip("* "), want)
        r = md_row(sec, "1년차", "현재가")
        for i in range(2, 6):
            c.eq(f"MD 격자 {co['ticker']} 현재가 열{i}", r[i],
                 usd(co["price"], 2))

    # 6. 안전마진
    _, mrows = md_table(text, "안전마진 30% 상한")
    expected = [(co, g) for co in cos for g in co["grid"]
                if not [x for x in g["cells"]
                        if x["discount_key"] == "bond30_plus3"][0]["diverges"]]
    c.eq("MD 안전마진 행 수", len(mrows), len(expected))
    for co, g in expected:
        c_ = [x for x in g["cells"]
              if x["discount_key"] == "bond30_plus3"][0]
        # 잘린 라벨 끝에 공백이 남을 수 있고, 마크다운 셀은 공백을 지웁니다.
        hit = [r for r in mrows if r[0] == nm(co)
               and r[1] == g["growth_label"][:24].strip()]
        c.true(f"MD 안전마진 {co['ticker']} {g['growth_key']} 행",
               len(hit) == 1, str(len(hit)))
        if len(hit) != 1:
            continue
        r = hit[0]
        c.eq(f"MD 안전마진 {co['ticker']} {g['growth_key']} 가치", r[2],
             usd(c_["value_per_share"]))
        c.eq(f"MD 안전마진 {co['ticker']} {g['growth_key']} 현재가대비", r[3],
             sg(c_["upside_vs_price"], 0))
        c.eq(f"MD 안전마진 {co['ticker']} {g['growth_key']} 상한",
             r[4].strip("* "), usd(c_["buy_price_at_margin"]["30%"]))
        ok = c_["buy_price_at_margin"]["30%"] > co["price"]
        c.eq(f"MD 안전마진 {co['ticker']} {g['growth_key']} 판정",
             r[6].strip("* "), "합격" if ok else "불합격")

    # 7. 터미널 민감도 — 발산이 실제로 표기됐는지
    div = sum(1 for co in cos for x in co["terminal_sensitivity"]
              if x["diverges"])
    c.true("MD 발산 칸이 있음", div > 0, str(div))
    c.eq("MD 발산 표기 개수", text.count("| 발산 |"), div)

    # 결론 서술이 데이터와 어긋나지 않는지
    c.true("MD 결론: 가정이 낮지 않다", "제 가정이 너무 낮은 게 아니라" in text)
    nv = [x for x in cos if x["ticker"] == "NVDA"][0]
    c.true("MD 엔비디아 전례 없음 서술", "전례가 **없습니다**" in text
           or "전례가" in text)
    for co in cos:
        if co["ticker"] == "NVDA":
            continue
        c.true(f"MD {co['ticker']} 전부 불합격 (데이터)",
               all([x for x in g["cells"]
                    if x["discount_key"] == "bond30_plus3"][0]
                   ["buy_price_at_margin"]["30%"] < co["price"]
                   for g in co["grid"]))
    c.true("MD 엔비디아 일부 합격 (데이터)",
           any([x for x in g["cells"]
                if x["discount_key"] == "bond30_plus3"][0]
               ["buy_price_at_margin"]["30%"] > nv["price"]
               for g in nv["grid"]))


MUTATIONS = [
    ("MD 해명 10년 CAGR 훼손", lambda t: t.replace("**6.95%**", "**3.95%**")),
    ("MD 기록 ROIC 훼손", lambda t: t.replace("**117.1%**", "**17.1%**")),
    ("MD 기록 영업이익 훼손", lambda t: t.replace("| 155.2 |", "| 55.2 |")),
    ("MD 기록 투하자본 훼손", lambda t: t.replace("| 349.0 |", "| 249.0 |")),
    ("MD 기초율 구간 훼손", lambda t: t.replace("| 41.7% |", "| 21.7% |")),
    ("MD 기초율 중위 명목 훼손",
     lambda t: t.replace("명목 **5.5%**", "명목 **8.5%**")),
    ("MD 백분위 훼손", lambda t: t.replace("**상위 10.2%**", "**상위 40.2%**")),
    ("MD 30년 국채 훼손", lambda t: t.replace("| 5.251% |", "| 3.251% |")),
    ("MD 명목 GDP 상한 훼손", lambda t: t.replace("**5.44%**", "**8.44%**")),
    ("MD 버핏 인용문 훼손",
     lambda t: t.replace("discounted at an appropriate interest rate",
                         "discounted at the cost of capital")),
    ("MD 버핏 주석 훼손",
     lambda t: t.replace("할인 공식 자체는 우리 모형과 같습니다",
                         "할인 공식은 우리 모형과 다릅니다")),
    ("MD 격자 한 칸 훼손", lambda t: t.replace("**$556**", "**$956**")),
    ("MD 안전마진 상한 훼손", lambda t: t.replace("**$389**", "**$689**")),
    ("MD 안전마진 판정 뒤집기",
     lambda t: t.replace("| **불합격** |", "| **합격** |", 1)),
    ("MD 발산 표기 제거", lambda t: t.replace("| 발산 |", "| $999 |", 1)),
    ("MD 3%p 해석 단서 제거",
     lambda t: t.replace("버핏의 규칙이 아닙니다", "버핏의 규칙입니다")),
    ("MD 실질 명시 제거",
     lambda t: t.replace("실질(인플레이션 조정) 기준입니다", "명목 기준입니다")),
    ("MD 결론 서술 제거",
     lambda t: t.replace("제 가정이 너무 낮은 게 아니라", "제 가정이 낮아서")),
    ("MD 발산 논거 제거", lambda t: t.replace("가치가 무한", "가치가 커짐")),
    ("MD 1부 제목 제거",
     lambda t: t.replace("## 1. 세 기업의 지난 10년", "## 서론")),
]


def main():
    mutate = "--mutate" in sys.argv
    d = json.load(open(DATA, encoding="utf-8"))
    md = open(MD, encoding="utf-8").read()

    c = Checks()
    check(md, d, c)
    print(f"출력물 검사 {c.passed + len(c.failures)}건 — 통과 {c.passed}, "
          f"실패 {len(c.failures)}")
    for f in c.failures[:20]:
        print("  ✗", f)
    if c.failures:
        return 1

    if mutate:
        print(f"\n변이 검정 {len(MUTATIONS)}건")
        survived = []
        for name, mut in MUTATIONS:
            bad = mut(md)
            if bad == md:
                survived.append(f"{name} (대상 없음)")
                print(f"  ✗ {name}: 훼손 대상을 찾지 못했습니다")
                continue
            c2 = Checks()
            try:
                check(bad, d, c2)
            except SystemExit as exc:
                print(f"  ✓ {name}: 구조 검사에서 중단 — {exc}")
                continue
            if c2.failures:
                print(f"  ✓ {name}: {len(c2.failures)}건 실패 "
                      f"— {c2.failures[0][:78]}")
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
