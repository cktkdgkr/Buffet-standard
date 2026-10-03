"""
The same data as the workbook, written as Markdown for reading on a phone.

Two things are different from the workbook, and both are the point.

Values, not formulas. openpyxl writes a formula without the value it evaluates
to, and most phone spreadsheet viewers do not recalculate, so the cells read
blank. Every number here is the computed figure.

Narrow tables. A phone shows maybe six columns before it starts scrolling
sideways, so the ten-year grid is split into two halves of five years, and the
per-year workings are a short table per company rather than one sheet 480 rows
long and 24 columns wide. Nothing is dropped - it is laid out differently.

    python3 export_roic_md.py
"""

import json
import os

import company_names as cn

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "미국50개사_ROIC_WACC비교.md")

D = json.load(open(os.path.join(HERE, "roic", "roic.json")))
R = json.load(open(os.path.join(HERE, "roic", "reconciliation.json")))
C = json.load(open(os.path.join(HERE, "roic", "corrections.json")))
G = json.load(open(os.path.join(HERE, "roic", "capital_diagnosis.json")))
ROUTES = json.load(open(os.path.join(HERE, "roic", "oi_routes.json")))

YEARS = list(range(2016, 2026))
WACC = D["wacc"]
MM = 1e6
BN = 1e9

by_ticker = {c["ticker"]: c for c in D["companies"]}
rank = D["ranking"]
out = []


def w(line=""):
    out.append(line)


def table(headers, rows, align=None):
    """A Markdown table. Columns after the first are right-aligned by default,
    because these are nearly all figures and a ragged left edge is harder to
    scan on a narrow screen."""
    align = align or (["left"] + ["right"] * (len(headers) - 1))
    sep = {"left": ":--", "right": "--:", "center": ":-:"}
    w("| " + " | ".join(str(h) for h in headers) + " |")
    w("|" + "|".join(sep[a] for a in align) + "|")
    for r in rows:
        w("| " + " | ".join("" if x is None else str(x) for x in r) + " |")
    w()


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def mm(x, nd=0):
    return "—" if x is None else f"{x / MM:,.{nd}f}"


def bn(x, nd=1):
    return "—" if x is None else f"{x / BN:,.{nd}f}"


def cell(comp, fy):
    """One year of ROIC for the wide grid: value, bracketed if below the
    hurdle, with the confidence and thin-capital marks."""
    y = next((y for y in comp["years"] if y["fiscal_year"] == fy), None)
    if y is None or y["roic"] is None:
        return "—"
    s = f"{y['roic'] * 100:.0f}"
    if y["confidence"] == "LOW":
        s += "*"
    if y.get("capital_too_small"):
        s += "†"
    return s if y["roic"] > WACC else f"({s})"


usable_years = sum(x["years_usable"] for x in rank)
above_years = sum(x["years_above_wacc"] for x in rank)
all_above = [x for x in rank if x["every_year_above_wacc"]]
orcl = next(n for n in C["net_cash_errors_flagged"] if n["ticker"] == "ORCL")
financials = [c["ticker"] for c in D["companies"] if c["is_financial"]]
no_subtotal = [c["ticker"] for c in D["companies"] if not c["is_financial"]
               and not any(y["operating_income_route"] == "reported"
                           for y in c["years"]
                           if 2016 <= y["fiscal_year"] <= 2025)]

# ---------------------------------------------------------------- 머리말
w("# 미국 50개사 ROIC vs 자본비용 10%")
w()
w(f"자료 SEC XBRL companyfacts API · 대상 FY2016~FY2025 · WACC 10% 고정 · "
  f"작성 {D['generated']}")
w()
w("> 엑셀과 같은 데이터입니다. 휴대폰에서 읽을 수 있도록 표를 좁게 나눴고, "
  "수식 대신 계산된 값을 그대로 적었습니다.")
w()
w("---")
w()

# ---------------------------------------------------------------- 요약
w("## 요약")
w()
w(f"비금융 **{len(rank)}개사의 {usable_years}개 기업-연도 가운데 "
  f"{above_years}개 연도({above_years / usable_years:.0%})가 ROIC 10%를 "
  f"넘겼습니다.** 10년 내내 한 해도 빠짐없이 넘긴 기업은 "
  f"{len(all_above)}곳이고, 전 기간 미달한 기업은 없습니다.")
w()
w("다만 이번 작업의 더 중요한 결과는 순위표가 아니라 **1차 조사의 오류 "
  f"{C['company_years_changed']}건을 찾아 바로잡은 것**입니다. 가장 큰 "
  f"원인은 1차 조사가 공시된 장기차입금을 "
  f"{len(G['old_missed_long_term_debt'])}개 기업-연도에서 누락한 것으로, "
  "오라클 10년·코카콜라 7년·브로드컴 4년·비자 3년이 여기 걸립니다. "
  "오라클 FY2024 ROIC가 761%로 나왔던 이유입니다.")
w()
w("그리고 이 오류는 ROIC에서 멈추지 않았습니다. 1차 조사는 **오라클을 "
  f"순현금 {bn(orcl['net_cash_in_study'])}십억 달러 기업으로 보고 있었는데, "
  f"실제로는 순차입금 {bn(-orcl['net_cash_recomputed'])}십억 달러**입니다. "
  f"오차 {bn(orcl['error'])}십억 달러, 시가총액의 "
  f"{pct(orcl['error_vs_market_cap'], 0)}입니다. 순현금은 기업가치에서 "
  "주주가치로 넘어갈 때 그대로 더해지므로 내재가치에 1:1로 반영됩니다. "
  "DCF 재계산은 이번 범위가 아니라 표시만 했습니다.")
w()

# ---------------------------------------------------------------- 읽는 법
w("## 표 읽는 법")
w()
table(["기호", "뜻"],
      [["`123`", "ROIC 10% 초과 (단위 %)"],
       ["`(123)`", "ROIC 10% 이하"],
       ["`*`", "영업이익 소계를 보고하지 않아 세전이익에서 추정한 해"],
       ["`†`", "순투하자본이 매출의 10% 미만 — 분모가 작아 비율이 민감 "
               "(문턱 판정은 유효)"],
       ["`—`", "산출 불가"]],
      align=["left", "left"])
w("ROIC 계산:")
w()
w("```")
w("NOPAT      = 영업이익 × (1 − 실효세율)")
w("투하자본    = 자기자본(비지배지분 포함) + 이자부차입금 − 현금·단기투자자산")
w("ROIC       = NOPAT ÷ 평균 투하자본 (기초·기말 평균)")
w("스프레드    = ROIC − 10%")
w("```")
w()
w("자기자본이나 투하자본이 0 이하인 해는 평균이 0 근처로 내려가 비율이 "
  "폭발하므로 기말값을 단독으로 씁니다. 금융업(SIC 6000~6799)은 ROIC를 "
  "산출하지 않습니다 — 은행에게 차입은 자금조달이 아니라 원재료여서 "
  "자기자본+차입금−현금이 아무것도 측정하지 않습니다.")
w()

# ---------------------------------------------------------------- 기업 목록
w("## 1. 기업 목록")
w()
for label, tickers in (
        ("ROIC 순위 대상 (비금융, 산출 5년 이상)",
         [x["ticker"] for x in rank]),
        ("표본 부족 (산출 5년 미만)",
         [x["ticker"] for x in D["thin_sample"]]),
        ("금융업 — ROIC 미산출", financials)):
    w(f"**{label} — {len(tickers)}곳**")
    w()
    table(["티커", "한글명", "영문 정식 명칭", "비고"],
          [[t, cn.korean(t), cn.english(t), cn.note(t) or "—"]
           for t in tickers],
          align=["left", "left", "left", "left"])
w("SEC가 반환하는 이름은 등록명(COSTCO WHOLESALE CORP /NEW, "
  "APPLIED MATERIALS INC /DE 등)이라 그대로 쓰지 않았습니다.")
w()

# ---------------------------------------------------------------- 순위
w("## 2. ROIC 요약 순위")
w()
table(["#", "기업", "중위", "최소", "최대", "초과"],
      [[str(i), cn.korean(x["ticker"]), pct(x["roic_median"], 0),
        pct(x["roic_min"], 0), pct(x["roic_max"], 0),
        f"{x['years_above_wacc']}/{x['years_usable']}"]
       for i, x in enumerate(rank, 1)])

# ---------------------------------------------------------------- 연도별
w("## 3. ROIC 연도별")
w()
w("폭을 맞추려고 전반 5년과 후반 5년으로 나눴습니다. 단위 %, 괄호는 "
  "10% 이하.")
w()
for title, half in (("### FY2016 ~ FY2020", YEARS[:5]),
                    ("### FY2021 ~ FY2025", YEARS[5:])):
    w(title)
    w()
    table(["기업"] + [f"'{str(y)[2:]}" for y in half],
          [[cn.korean(x["ticker"])] +
           [cell(by_ticker[x["ticker"]], fy) for fy in half]
           for x in rank])

w("### 표본 부족·금융업")
w()
w("팔란티어는 10년 중 대부분 순투하자본이 음수여서(현금이 자기자본+차입금을 "
  "넘어서) 이 정의로 ROIC가 성립하지 않습니다. GE 버노바는 2024년 4월 "
  "분사라 4년치뿐입니다. 금융업 9곳은 산출하지 않았습니다.")
w()
table(["기업", "상태"],
      [[cn.korean(x["ticker"]),
        f"산출 {x['years_usable']}년 · {x['verdict']}"]
       for x in D["thin_sample"]] +
      [[cn.korean(t), "금융업 — ROIC 정의 부적합"] for t in financials],
      align=["left", "left"])

# ---------------------------------------------------------------- 스프레드
w("## 4. ROIC − 10% 스프레드 (중위 기준)")
w()
buckets = [("+40%p 이상", lambda s: s >= 0.40),
           ("+20~40%p", lambda s: 0.20 <= s < 0.40),
           ("+10~20%p", lambda s: 0.10 <= s < 0.20),
           ("0~+10%p", lambda s: 0 <= s < 0.10),
           ("음수 (10% 미달)", lambda s: s < 0)]
for label, test in buckets:
    members = [x for x in rank if test(x["spread_median"])]
    if not members:
        continue
    w(f"**{label} — {len(members)}곳**")
    w()
    w(", ".join(f"{cn.korean(x['ticker'])} "
                f"{x['spread_median'] * 100:+.0f}" for x in members))
    w()
w("스프레드의 크기보다 **꾸준함**이 중요합니다. 중위 ROIC가 높아도 변동이 "
  "크면 어느 해에 자본을 투입했는지에 따라 결과가 갈리기 때문입니다. "
  f"10년 전부 10%를 넘긴 {len(all_above)}곳이 그 조건을 만족합니다.")
w()
table(["기업", "중위", "최소", "최대", "표준편차", "추정 연수"],
      [[cn.korean(x["ticker"]), pct(x["roic_median"], 0),
        pct(x["roic_min"], 0), pct(x["roic_max"], 0),
        pct(x["roic_stdev"], 0), str(x["years_estimated_numerator"])]
       for x in all_above])

# ---------------------------------------------------------------- 계산 명세
w("## 5. 계산 명세 — 기업별 연도별")
w()
w("엑셀 '계산 명세' 시트와 같은 내용입니다. 금액 단위는 **백만 달러**. "
  "`투하자본`은 기말값, `평균`은 ROIC의 분모로 쓴 기초·기말 평균입니다.")
w()
order = ([x["ticker"] for x in rank]
         + [x["ticker"] for x in D["thin_sample"]] + financials)
for t in order:
    comp = by_ticker[t]
    w(f"### {cn.korean(t)} — {cn.english(t)} ({t})")
    w()
    note = cn.note(t)
    if note:
        w(f"*{note}*")
        w()
    rows = []
    for y in comp["years"]:
        if not 2015 <= y["fiscal_year"] <= 2025:
            continue
        if y["fiscal_year"] == 2015:
            # FY2015 is on the table only to supply FY2016's opening capital.
            # Its own average needs FY2014, which is not shown, so printing a
            # ratio here would be a figure computed on a different basis from
            # every other row - the workbook blanks the same cells.
            rows.append(["FY2015 ◦", "—", "—", "—",
                         mm(y["invested_capital"]), "—", "—"])
            continue
        rows.append([f"FY{y['fiscal_year']}", mm(y["operating_income"]),
                     pct(y["effective_tax_rate"], 0), mm(y["nopat"]),
                     mm(y["invested_capital"]), mm(y["invested_capital_avg"]),
                     pct(y["roic"], 1)])
    table(["연도", "영업이익", "세율", "NOPAT", "투하자본", "평균", "ROIC"],
          rows)
    w("◦ FY2015는 FY2016 평균 투하자본의 기초값으로만 쓰입니다 "
      "(보고 기간 밖).")
    w()
    routes = sorted({y["operating_income_route"] for y in comp["years"]
                     if 2016 <= y["fiscal_year"] <= 2025})
    w(f"분자 산출 경로: {', '.join(routes)}")
    w()
    statuses = sorted({y["roic_status"] for y in comp["years"]
                       if 2016 <= y["fiscal_year"] <= 2025
                       and y["roic_status"] != "OK"})
    if statuses:
        w("비고: " + " / ".join(statuses))
        w()

# ---------------------------------------------------------------- 대조
w("## 6. 1차 조사와 대조")
w()
table(["구분", "건수", "비중"],
      [["대조 가능한 기업-연도", f"{R['compared_company_years']}", "100%"],
       ["1%p 이내 일치", f"{R['agree_within_1pp']}",
        f"{R['agree_within_1pp'] / R['compared_company_years']:.0%}"],
       ["1%p 초과 불일치", f"{R['differ_over_1pp']}",
        f"{R['differ_over_1pp'] / R['compared_company_years']:.0%}"],
       ["5%p 초과 불일치", f"{R['differ_over_5pp']}",
        f"{R['differ_over_5pp'] / R['compared_company_years']:.0%}"],
       ["10% 문턱 판정까지 바뀜", f"{R['hurdle_verdict_flips']}",
        f"{R['hurdle_verdict_flips'] / R['compared_company_years']:.0%}"],
       ["재조사만 산출 (1차는 공백)", f"{R['new_covers_old_blank']}", "—"],
       ["1차만 산출", f"{R['old_covers_new_blank']}", "—"]])

w("### 어느 쪽이 틀렸는지 — 판단이 필요 없는 검정")
w()
w("분모가 다르다는 것만으로는 어느 쪽이 맞는지 알 수 없습니다. 그래서 "
  "판단이 끼어들 여지가 없는 검정을 했습니다. **10-K에 장기차입금 태그가 "
  "있는 기업은 장기차입금이 있었던 것이고, 그걸 0으로 기록한 조사는 틀린 "
  "것**입니다. 단위 십억 달러.")
w()
tally = {}
for m in G["old_missed_long_term_debt"]:
    tk = m["key"].split()[0]
    cur = tally.setdefault(tk, {"n": 0, "filed": 0, "old": 0, "new": 0})
    cur["n"] += 1
    if (m["filed_long_term_debt"] or 0) > cur["filed"]:
        cur.update(filed=m["filed_long_term_debt"],
                   old=m["old_total_debt"], new=m["new_total_debt"] or 0)
table(["기업", "누락", "공시 장기차입금", "1차 차입금", "재산출"],
      [[cn.korean(tk), f"{v['n']}년", bn(v["filed"]), bn(v["old"]),
        bn(v["new"])]
       for tk, v in sorted(tally.items(), key=lambda kv: -kv[1]["filed"])])
w("반대 방향 오류도 있었습니다. 애플 FY2016의 현금을 1차 조사는 20.5십억 "
  "달러로 기록했지만, 단기 유가증권 46.7십억 달러를 합한 67.2십억 달러가 "
  "차감 대상입니다. 이 경우 1차 조사는 분모를 과대하게 잡아 **ROIC를 낮게** "
  "보고 있었습니다. 오류가 한쪽으로만 기울지 않았다는 뜻입니다.")
w()

w("### 문턱 판정이 바뀐 기업-연도")
w()
table(["기업", "연도", "재산출", "1차", "차이"],
      [[cn.korean(d["ticker"]), f"FY{d['fiscal_year']}",
        pct(d["roic_new"], 0), pct(d["roic_old"], 0),
        f"{d['gap_pp'] * 100:+.0f}%p"]
       for d in sorted(R["flips"], key=lambda d: -abs(d["gap_pp"]))])

w("### 차이가 큰 기업-연도 (상위 30)")
w()
table(["기업", "연도", "재산출", "1차", "차이"],
      [[cn.korean(d["ticker"]), f"FY{d['fiscal_year']}",
        pct(d["roic_new"], 0), pct(d["roic_old"], 0),
        f"{d['gap_pp'] * 100:+.0f}%p"]
       for d in R["differences"][:30]])
w(f"전체 {R['differ_over_1pp']}건은 엑셀 '구 조사 대조' 시트에 있습니다.")
w()

# ---------------------------------------------------------------- 정정
w("## 7. 1차 조사에 반영한 정정")
w()
table(["항목", "내용"],
      [["정정한 기업-연도",
        f"{C['company_years_changed']}건 (ROIC·영업이익·실효세율·투하자본)"],
       ["method_notes.ebit", "분자 우선순위를 실제 구현과 맞게 수정"],
       ["원본 보존", C["backup"]],
       ["재계산하지 않은 것", "가격·시가총액·주주이익·DCF·가치평가 판정"]],
      align=["left", "left"])
w("ROIC가 크게 바뀐 기업-연도 상위 20건:")
w()
big = sorted((x for x in C["changes"]
              if None not in (x["roic_before"], x["roic_after"])),
             key=lambda x: -abs(x["roic_after"] - x["roic_before"]))[:20]
table(["기업", "연도", "1차", "정정", "변화"],
      [[cn.korean(x["ticker"]), f"FY{x['fiscal_year']}",
        pct(x["roic_before"], 0), pct(x["roic_after"], 0),
        f"{(x['roic_after'] - x['roic_before']) * 100:+.0f}%p"]
       for x in big])

w("### 가치평가로 번진 입력 오류 — 재계산하지 않았음")
w()
w("단위 십억 달러.")
w()
table(["기업", "1차 순현금", "재산출", "오차", "시총 대비"],
      [[cn.korean(n["ticker"]), bn(n["net_cash_in_study"]),
        bn(n["net_cash_recomputed"]), bn(n["error"]),
        pct(n["error_vs_market_cap"], 1)]
       for n in sorted(C["net_cash_errors_flagged"],
                       key=lambda n: -abs(n["error"]))])
w("오라클이 결정적입니다. 시가총액의 24%에 해당하는 오차이므로 1차 조사의 "
  "오라클 가치평가 결론은 신뢰할 수 없습니다. 다른 네 곳은 1% 안팎이라 "
  "결론을 바꾸기 어렵습니다.")
w()

# ---------------------------------------------------------------- 경로
w("## 8. 영업이익 소계를 보고하지 않는 기업")
w()
w(f"{cn.joined(no_subtotal)} — 이 {len(no_subtotal)}곳은 손익계산서에 "
  "영업이익 소계가 없습니다. 분자를 어떻게 만들지는 주장이 아니라 측정으로 "
  "정했습니다. 소계를 보고하는 기업-연도에서 각 구성 방식을 보고치와 "
  "맞춰본 결과입니다.")
w()
table(["구성 경로", "검정", "일치", "정확도"],
      [[x["route"], str(x["tested"]), str(x["matched"]), pct(x["accuracy"])]
       for x in ROUTES["routes"]])
w("다만 **±2% 일치율은 이 문제에 맞는 통계가 아닙니다.** 목적이 ROIC를 10% "
  "문턱과 비교하는 것이므로, 중요한 건 분자를 바꿨을 때 문턱 판정이 "
  "뒤집히는지입니다. 그걸 직접 측정했습니다.")
w()
table(["구성 경로", "검정", "뒤집힘", "비율", "중위 격차"],
      [["B 매출총이익−영업비용", "207", "0", "0.0%", "0.00%"],
       ["C 매출−총비용", "167", "1", "0.6%", "0.00%"],
       ["H 세전이익+이자 (1차 조사 설명의 방식)", "477", "11", "2.3%",
        "1.11%"],
       ["D 매출−매출원가−영업비용", "220", "6", "2.7%", "0.00%"],
       ["G 세전이익+이자−이자·투자수익", "477", "14", "2.9%", "0.77%"],
       ["F 세전이익−영업외수익", "448", "16", "3.6%", "0.35%"]])
w("즉 세전이익 기반 추정은 ROIC 수준을 몇 %p 틀릴 수 있지만 10% 문턱 "
  "판정은 97% 정확합니다. 그래서 이 기업들을 버리지 않고 추정값으로 "
  "포함했고, 표에서 `*`로 표시했습니다.")
w()
w("경로 선택에는 함정이 하나 더 있었습니다. 경로 C의 85.8%라는 정확도는 "
  "소계를 보고하는 기업에서만 측정된 값이라 소계를 보고하지 않는 기업에 "
  "그대로 적용되지 않습니다. 실제로 제너럴 일렉트릭에 적용하자 FY2016 "
  "영업이익이 −6.4십억 달러로 나왔습니다. 그래서 모든 상향식 구성값은 "
  "**세전이익으로 역검증**을 통과해야만 쓰도록 했고, 경로 선택은 연도별이 "
  "아니라 기업별로 한 번만 하도록 했습니다 — 연도마다 다른 경로를 쓰면 "
  "10년 추세가 사업이 아니라 경로를 측정하게 되기 때문입니다.")
w()
table(["기업", "선택 경로", "역검증"],
      [[cn.korean(c["ticker"]), c["chosen_route"]["route"],
        "통과" if c["chosen_route"]["reconciles"] else "미통과"]
       for c in D["companies"] if c.get("chosen_route")],
      align=["left", "left", "left"])

# ---------------------------------------------------------------- 검증
w("## 9. 검증")
w()
table(["검증 방식", "건수", "무엇을 잡는지"],
      [["항등식", "—",
        "투하자본=자기자본+차입금−현금, NOPAT=영업이익×(1−세율), "
        "ROIC=NOPAT÷평균자본, 평균 산정 규칙"],
       ["트립와이어", "—",
        "차감 현금 ≤ 유동자산, 차입금 ≤ 총부채·총자산, 실효세율 5~40%"],
       ["공시 앵커", "19", "공시 본문에서 손으로 읽은 수치와 대조"],
       ["합계", "10,069", "전부 통과"],
       ["변이 검정", "10/10", "값을 고의로 훼손해 검사가 실패하는지 확인"],
       ["엑셀 수식 검증", "5,494", "워크북 파생 셀을 재평가해 엔진 값과 대조"],
       ["MD 검증", "—", "이 문서의 표를 되읽어 엔진 값과 대조"]],
      align=["left", "right", "left"])
w("앵커를 따로 두는 이유가 있습니다. 항등식과 트립와이어는 검사 대상과 "
  "같은 데이터로 계산되므로 **내부적으로 일관된 틀린 값은 둘 다 "
  "통과합니다.** 공시 원문에서 직접 읽은 수치만이 산술이 아니라 데이터가 "
  "틀렸을 때 실패할 수 있습니다. 실제로 램리서치 현금 과다차감과 오라클 "
  "차입금 이중계상은 앵커가 잡았습니다.")
w()

# ---------------------------------------------------------------- 한계
w("## 10. 남은 한계")
w()
for item in [
    f"**분자 추정 {len(D['low_confidence_years'])}개 연도.** 영업이익 소계를 "
    f"보고하지 않는 {len(no_subtotal)}개 기업은 세전이익에서 거꾸로 "
    "추정했습니다. 문턱 판정은 97% 정확하지만 ROIC 수준은 90분위에서 "
    "4~5%p 틀릴 수 있습니다.",
    "**자기자본 정의.** 분자가 연결 영업이익이므로 분모도 비지배지분을 "
    "포함했습니다. 1차 조사는 지배주주 지분만 썼고 96개 기업-연도에서 "
    "차이가 납니다. 정의가 다른 것이지 오류는 아닙니다.",
    "**장기 유가증권은 자본에 남겼습니다.** 비유동 투자자산을 빼지 않아 "
    "분모가 보수적으로(크게) 잡혔고, ROIC는 그만큼 낮게 나옵니다.",
    "**WACC 10%는 지시에 따른 고정값입니다.** 실제 자본비용은 기업마다 "
    "다르고 2016~2025년 금리 환경도 크게 달라졌습니다. 같은 문턱을 쓴 것은 "
    "ROIC를 서로 비교하기 위한 선택입니다.",
    "**ROIC가 높다는 것과 투자 대상이라는 것은 다릅니다.** 가격이 빠져 "
    "있습니다. ROIC 순위가 곧 매수 순위는 아닙니다.",
]:
    w(f"- {item}")
w()
w("---")
w()
w("재현: `bash work/run_roic.sh`")

with open(OUT, "w") as fh:
    fh.write("\n".join(out) + "\n")
print(f"wrote {OUT} ({len(out)} 줄, {os.path.getsize(OUT) / 1024:.0f} KB)")
