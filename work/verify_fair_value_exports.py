"""
네 기업 적정주가 산출물 검증 — 마크다운과 엑셀.

세 포맷이 한 원본(fair_value.json)을 읽게 만들어 두었어도 읽는 과정에서
틀릴 수 있습니다. 완성된 산출물을 **되읽어** 엔진 값과 대조합니다. HTML 은
export_fair_value_html.py --verify 가 자기 페이지를 검사합니다.

- 마크다운: 표를 헤더로 특정하고 행을 완전일치로 찾습니다. 세 기업의
  시나리오 표가 헤더를 공유하므로 **구획(### 제목)을 먼저 자릅니다.**
- 엑셀: 수식 셀에 심긴 계산값을 읽어 엔진 값과 비교합니다. 행 번호를 적지
  않고 라벨로 찾습니다 — 레이아웃이 한 줄 움직이면 같이 썩습니다.

    python3 verify_fair_value_exports.py
    python3 verify_fair_value_exports.py --mutate
"""

import json
import os
import sys

from openpyxl import load_workbook

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "fv", "fair_value.json")
MD = os.path.join(HERE, "4개기업_적정주가_판정.md")
XLSX = os.path.join(HERE, "4개기업_적정주가_판정.xlsx")
MM, BN = 1e6, 1e9
ORDER = ["보수", "중립", "낙관"]


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

    def near(self, name, got, want, tol):
        if got is not None and not isinstance(got, str) \
                and abs(got - want) <= tol:
            self.passed += 1
        else:
            self.failures.append(
                f"{name}: 산출물 {got!r} != 엔진 {want:,.6g} (허용 {tol:,.6g})")

    def true(self, name, cond, detail=""):
        if cond:
            self.passed += 1
        else:
            self.failures.append(f"{name}: 거짓 {detail}")


# ------------------------------------------------------------------ 마크다운
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


def md_table(text, header_has, exact=False):
    def match(h):
        return any(x == header_has for x in h) if exact \
            else any(header_has in x for x in h)

    hits = [(h, r) for h, r in md_tables(text) if match(h)]
    if len(hits) != 1:
        raise SystemExit(f"마크다운 표 특정 실패: {header_has!r} 가 "
                         f"{len(hits)}개 (완전일치={exact})")
    return hits[0]


def md_row(text, header_has, label, col=0, exact=True, header_exact=False):
    _, rows = md_table(text, header_has, header_exact)
    hit = [r for r in rows if len(r) > col
           and (r[col].strip("* ") == label if exact else label in r[col])]
    if len(hit) != 1:
        raise SystemExit(f"마크다운 행 특정 실패: {header_has!r} 표에서 "
                         f"{label!r} 가 {len(hit)}개")
    return hit[0]


def md_section(text, heading_prefix):
    """### 제목으로 시작하는 구획. 세 기업 표가 헤더를 공유하므로 필요합니다."""
    i = text.find(f"### {heading_prefix}")
    if i < 0:
        raise SystemExit(f"마크다운 구획 특정 실패: ### {heading_prefix}...")
    j = len(text)
    for tag in ("\n### ", "\n## "):
        k = text.find(tag, i + 4)
        if 0 <= k < j:
            j = k
    return text[i:j]


def check_md(text, d, c):
    applied = [x for x in d["companies"] if x["model"] == "applied"]
    sx = [x for x in d["companies"]
          if x["model"] == "base_not_established"][0]

    def val(co, s):
        return [v for v in co["valuations"] if v["scenario"] == s][0]

    def nm(co):
        return f"{co['korean']}({co['ticker']})"

    c.true("MD 자료 기준일 표기", d["generated"] in text)
    c.true("MD 50개사 조사 생성일 표기", d["roic_study_generated"] in text)
    c.true("MD 1부 기준 정리 있음", "## 1부. 우리가 세운 기준" in text)
    c.true("MD 2부 적용 있음", "## 2부. 네 기업에 적용" in text)
    c.true("MD 3부 판정 있음", "## 3부. 판정" in text)
    c.true("MD 4부 한계 있음", "## 4부. 방법과 한계" in text)
    c.true("MD ROIC 정의 명시", "NOPAT = 보고된 영업이익 × (1 − 실효세율)"
           in text)
    c.true("MD 한글명과 티커 병기",
           all(nm(x) in text for x in applied + [sx]))

    for co in applied:
        sec = md_section(text, f"{nm(co)} — ")
        for s in ORDER:
            v, a = val(co, s), val(co, s)["assumptions"]
            r = md_row(sec, "정당화 성장률", s)
            c.eq(f"MD {co['ticker']} {s} 성장률", r[1],
                 f"{pct(a['growth'])}→{pct(a['fade_to'])}")
            c.eq(f"MD {co['ticker']} {s} 증분ROIC", r[2],
                 pct(a["incremental_roic"]))
            c.eq(f"MD {co['ticker']} {s} 주당가치", r[3],
                 usd(v["value_per_share"]))
            c.eq(f"MD {co['ticker']} {s} 현재가 대비", r[4],
                 sg(v["upside_vs_market"], 0))
            ig = v["implied_growth_at_price"]
            c.eq(f"MD {co['ticker']} {s} 정당화 성장률", r[5],
                 pct(ig) if ig is not None else "없음")
        # 사업의 질 · 추세 · 판정 · 천장 · 순위
        r = md_row(text, "ROIC 중위", nm(co))
        c.eq(f"MD {co['ticker']} TTM 영업이익", r[1],
             bn(co["ttm"]["operating_income"]["value"]))
        c.eq(f"MD {co['ticker']} 10년 CAGR", r[3],
             pct(co["record"]["operating_income_cagr"]))
        c.eq(f"MD {co['ticker']} ROIC 중위", r[4],
             pct(co["record"]["summary"]["roic_median"]))
        tr = co["record"]["trend"]
        r = md_row(text, "투하자본 배수", nm(co))
        c.eq(f"MD {co['ticker']} 추세 고점", r[1],
             f"FY{tr['peak_fiscal_year']} {pct(tr['peak_roic'])}")
        c.eq(f"MD {co['ticker']} 추세 투하자본 배수", r[4],
             f"{tr['invested_capital_multiple']:.2f}배")
        r = md_row(text, "판정", nm(co), header_exact=True)
        c.eq(f"MD {co['ticker']} 판정 보수", r[2],
             usd(val(co, "보수")["value_per_share"]))
        c.eq(f"MD {co['ticker']} 판정 중립", r[3],
             usd(val(co, "중립")["value_per_share"]))
        c.eq(f"MD {co['ticker']} 판정 낙관", r[4],
             usd(val(co, "낙관")["value_per_share"]))
        c.eq(f"MD {co['ticker']} 판정 문구", r[5],
             "낙관에서만 설명됨" if val(co, "낙관")["upside_vs_market"] > 0
             else "어느 시나리오에서도 비쌈")
        r = md_row(text, "중립 천장의 몇 배", nm(co))
        c.eq(f"MD {co['ticker']} 보수 천장", r[1],
             usd(val(co, "보수")["best_case_in_scenario"]["value_per_share"]))
        c.eq(f"MD {co['ticker']} 중립 천장", r[2],
             usd(val(co, "중립")["best_case_in_scenario"]["value_per_share"]))
        r = md_row(text, "현재가/중립평가치", nm(co), col=1)
        c.eq(f"MD {co['ticker']} 순위 중립 대비", r[2],
             sg(val(co, "중립")["upside_vs_market"], 0))

    # ---- 풀어 쓴 계산 절 -------------------------------------------------
    ex = [c for c in applied if c["ticker"] == "GOOG"][0]
    exv = [v for v in ex["valuations"] if v["scenario"] == "중립"][0]
    exa = exv["assumptions"]

    for co in applied:
        r = md_row(text, "10년 영업이익 CAGR (측정값)", nm(co))
        c.eq(f"MD 풀이① {co['ticker']} 10년 CAGR", r[1],
             pct(co["record"]["operating_income_cagr"]))
        for i, s in enumerate(ORDER, start=2):
            si = [x for x in co["scenario_inputs"] if x["name"] == s][0]
            want = (f"{pct(si['growth_uncapped'])}→{pct(si['growth'])}(상한)"
                    if si["growth_capped"] else pct(si["growth"]))
            c.eq(f"MD 풀이① {co['ticker']} {s} 성장률", r[i], want)
        r = md_row(text, "10년 중위", nm(co))
        c.eq(f"MD 풀이② {co['ticker']} 10년 최저 ROIC", r[1],
             pct(co["record"]["summary"]["roic_min"]))
        c.eq(f"MD 풀이② {co['ticker']} 10년 중위 ROIC", r[2],
             pct(co["record"]["summary"]["roic_median"]))
        for i, s in enumerate(ORDER, start=3):
            si = [x for x in co["scenario_inputs"] if x["name"] == s][0]
            want = (f"{pct(si['incremental_roic_uncapped'])}→"
                    f"{pct(si['incremental_roic'])}(상한)"
                    if si["incremental_roic_capped"]
                    else pct(si["incremental_roic"]))
            c.eq(f"MD 풀이② {co['ticker']} {s} 증분ROIC", r[i], want)

    for p_ in exv["projection"]:
        r = md_row(text, "주주 몫 현금", f"{p_['year']}년차")
        c.eq(f"MD 풀이③ {p_['year']}년차 성장률", r[1],
             pct(p_["growth"], 2))
        c.eq(f"MD 풀이③ {p_['year']}년차 NOPAT", r[2], bn(p_["nopat"]))
        c.eq(f"MD 풀이③ {p_['year']}년차 재투자율", r[3],
             pct(p_["reinvestment_rate"]))
        c.eq(f"MD 풀이③ {p_['year']}년차 주주몫현금", r[4],
             bn(p_["free_cash_flow"]))
        c.eq(f"MD 풀이③ {p_['year']}년차 현재가치", r[5],
             bn(p_["present_value"]))
    r = md_row(text, "주주 몫 현금", "10년 현재가치 합계")
    c.eq("MD 풀이③ 10년 현재가치 합계", r[5], bn(exv["pv_of_forecast"]))

    for lab, want in (
            ("출발점 — TTM 세후영업이익(NOPAT)",
             f"{bn(ex['ttm']['nopat'])}십억"),
            ("1년차 성장률", pct(exa["growth"])),
            ("10년차 성장률 (감쇠 목표)", pct(exa["fade_to"])),
            ("증분 ROIC", pct(exa["incremental_roic"])),
            ("할인율 (요구수익률)", pct(exa["discount"], 0)),
            ("11년차 이후 영구 성장률", pct(exa["terminal_growth"]))):
        r = md_row(text, "어디서 왔나", lab)
        c.eq(f"MD 풀이③ 가정 {lab}", r[1], want)

    for lab, want in (
            ("① 10년치 현재가치 합계", f"{bn(exv['pv_of_forecast'])}십억"),
            ("③ 터미널을 현재가치로", f"{bn(exv['pv_of_terminal'])}십억"),
            ("④ 기업가치", f"{bn(exv['enterprise_value'])}십억"),
            ("⑤ 자기자본가치", f"{bn(exv['equity_value'])}십억"),
            ("⑥ 주당 가치", usd(exv["value_per_share"], 2))):
        r = md_row(text, "단계", lab, header_exact=True)
        # 마크다운의 ⑥ 행은 강조(**)가 붙습니다 — 강조를 벗겨 비교합니다.
        c.eq(f"MD 풀이③ 단계 {lab}", r[2].strip("*"), want)
    c.true("MD 풀이③ 터미널 비중 서술",
           f"{pct(exv['terminal_share'], 0)}를 차지합니다" in text)
    c.true("MD 풀이① 3단계 설명 있음",
           "1단계" in text and "2단계" in text and "3단계" in text)
    c.true("MD 풀이② 재투자율 식 있음", "재투자율 = 성장률 ÷ 증분ROIC" in text)
    c.true("MD 풀이③ 할인 설명 있음", "내가 요구하는 연 수익률" in text)

    # 스페이스X
    for b in sx["earnings_bases"]:
        r = md_row(text, "연율화 NOPAT", b["name"])
        c.eq(f"MD 스페이스X {b['name']} NOPAT", r[1], bn(b["nopat"]))
    for rr in sx["reverse"]:
        r = md_row(text, "연율화 매출의", rr["scenario"])
        c.eq(f"MD 스페이스X {rr['scenario']} 요구 NOPAT", r[1],
             f"{bn(rr['required_nopat_at_price'])}십억")
        c.eq(f"MD 스페이스X {rr['scenario']} 매출 비중", r[3],
             pct(rr["as_share_of_q3_annualised_revenue"], 0))
    for k, v in sx["segments_9m"].items():
        if not isinstance(v, dict):
            continue
        r = md_row(text, "9M′26 영업이익", k)
        c.eq(f"MD 스페이스X 사업부 {k} Q3 매출", r[1],
             bn(v["revenue"]["q3_2026"]))

    # 결론이 표와 어긋나지 않는지
    c.true("MD 결론: 낙관에서만 설명", "낙관 시나리오에서만" in text)
    c.true("MD 결론: 보수·중립에 해 없음", "어떤 성장률로도" in text)
    c.true("MD 스페이스X 산출 불가 명시",
           "기준이익 미성립" in text or "기준이익이 성립하지 않습니다" in text)


# ---------------------------------------------------------------------- 엑셀
def find(ws, label, col=1, limit=140, after=None, until=None, nth=None):
    """
    라벨로 행을 찾습니다. 행 번호를 적어 두면 레이아웃과 함께 썩습니다.

    after 는 '가정' 시트 때문에 필요합니다 — 시장가정 블록과 규칙 블록에
    '보수'·'중립'·'낙관' 라벨이 각각 한 번씩 나오므로, 어느 블록인지를 먼저
    정해야 특정됩니다. nth 는 같은 라벨이 여러 번 나오는 것이 정상인 경우에
    씁니다.
    """
    start = 1
    if after is not None:
        anchors = [r for r in range(1, limit + 1)
                   if after in str(ws.cell(row=r, column=1).value or "")]
        if len(anchors) != 1:
            raise SystemExit(f"엑셀 블록 특정 실패: {ws.title}!{after!r} 가 "
                             f"{len(anchors)}개")
        start = anchors[0]
    end = limit
    if until is not None:
        stops = [r for r in range(start + 1, limit + 1)
                 if until in str(ws.cell(row=r, column=1).value or "")]
        if not stops:
            raise SystemExit(f"엑셀 블록 끝 특정 실패: {ws.title}!{until!r}")
        end = stops[0] - 1
    hits = [r for r in range(start, end + 1)
            if str(ws.cell(row=r, column=col).value or "").strip() == label]
    if nth is not None:
        if len(hits) <= nth:
            raise SystemExit(f"엑셀 행 특정 실패: {ws.title}!{label!r} 가 "
                             f"{len(hits)}개 (nth={nth})")
        return hits[nth]
    if len(hits) != 1:
        raise SystemExit(f"엑셀 행 특정 실패: {ws.title}!{label!r} 가 "
                         f"{len(hits)}개")
    return hits[0]


def check_xlsx(wb, d, c):
    applied = [x for x in d["companies"] if x["model"] == "applied"]
    sx = [x for x in d["companies"]
          if x["model"] == "base_not_established"][0]

    def val(co, s):
        return [v for v in co["valuations"] if v["scenario"] == s][0]

    want_sheets = (["가정", "요약"]
                   + [f"{co['ticker']} 투영" for co in applied])
    c.eq("엑셀 시트 구성", wb.sheetnames, want_sheets)

    # 가정 시트의 시장 가정과 규칙
    ws = wb["가정"]
    for s in ORDER:
        row = find(ws, s, after="시장 가정", until="기업별 가정")
        m = d["market_assumptions"][s]
        c.near(f"XLSX 가정 {s} 할인율", ws.cell(row=row, column=2).value,
               m["discount"], 1e-12)
        c.near(f"XLSX 가정 {s} 터미널", ws.cell(row=row, column=3).value,
               m["terminal_growth"], 1e-12)
        c.near(f"XLSX 가정 {s} 감쇠목표", ws.cell(row=row, column=4).value,
               m["fade_to"], 1e-12)
    for co in applied:
        row = find(ws, f"{co['korean']}({co['ticker']})")
        c.near(f"XLSX 가정 {co['ticker']} 주가",
               ws.cell(row=row, column=2).value, co["price"], 1e-6)
        c.near(f"XLSX 가정 {co['ticker']} 주식수(십억)",
               ws.cell(row=row, column=3).value,
               co["shares_outstanding"]["value"] / BN, 1e-6)
        c.near(f"XLSX 가정 {co['ticker']} TTM 영업이익(백만)",
               ws.cell(row=row, column=4).value,
               co["ttm"]["operating_income"]["value"] / MM, 0.5)
        c.near(f"XLSX 가정 {co['ticker']} 실효세율",
               ws.cell(row=row, column=5).value,
               co["ttm"]["effective_tax_rate"], 1e-12)
        c.near(f"XLSX 가정 {co['ticker']} 순현금(백만)",
               ws.cell(row=row, column=6).value,
               co["balance_sheet"]["net_cash"] / MM, 0.5)
        c.near(f"XLSX 가정 {co['ticker']} 10년 CAGR",
               ws.cell(row=row, column=7).value,
               co["record"]["operating_income_cagr"], 1e-12)

    # 기업별 투영 시트
    for co in applied:
        ws = wb[f"{co['ticker']} 투영"]
        c.near(f"XLSX {co['ticker']} TTM NOPAT",
               ws.cell(row=find(ws, "TTM NOPAT = 영업이익 × (1 − 실효세율)"),
                       column=2).value, co["ttm"]["nopat"] / MM, 0.5)
        c.near(f"XLSX {co['ticker']} 시가총액",
               ws.cell(row=find(ws, "시가총액 (백만)"), column=2).value,
               co["market_cap"] / MM, 1.0)
        # 시나리오 블록은 "주당 가치" 라벨이 세 번 나옵니다. 블록 순서대로
        # 집어 시나리오에 대응시킵니다 — 라벨만으로는 특정되지 않습니다.
        vps_rows = [r for r in range(1, 140)
                    if str(ws.cell(row=r, column=1).value or "").strip()
                    == "주당 가치"]
        c.eq(f"XLSX {co['ticker']} 주당가치 행 3개", len(vps_rows), 3)
        for s, row in zip(ORDER, vps_rows):
            v = val(co, s)
            c.near(f"XLSX {co['ticker']} {s} 주당가치",
                   ws.cell(row=row, column=7).value, v["value_per_share"],
                   0.01)
            c.near(f"XLSX {co['ticker']} {s} 현재가 대비",
                   ws.cell(row=row + 1, column=7).value,
                   v["upside_vs_market"], 1e-6)
            c.near(f"XLSX {co['ticker']} {s} 현재가÷평가치",
                   ws.cell(row=row + 2, column=7).value,
                   v["price_to_value"], 1e-6)
        ev_rows = [r for r in range(1, 140)
                   if str(ws.cell(row=r, column=1).value or "").strip()
                   == "기업가치 = 예측 + 터미널"]
        c.eq(f"XLSX {co['ticker']} 기업가치 행 3개", len(ev_rows), 3)
        for s, row in zip(ORDER, ev_rows):
            v = val(co, s)
            c.near(f"XLSX {co['ticker']} {s} 기업가치",
                   ws.cell(row=row, column=7).value,
                   v["enterprise_value"] / MM, 1.0)
            c.near(f"XLSX {co['ticker']} {s} 터미널 비중",
                   ws.cell(row=row + 1, column=7).value,
                   v["terminal_share"], 1e-6)
        # 10년 투영의 마지막 해 NOPAT 과 1년차 재투자율
        for s, row in zip(ORDER, ev_rows):
            v = val(co, s)
            c.near(f"XLSX {co['ticker']} {s} 10년차 NOPAT",
                   ws.cell(row=row - 3, column=3).value,
                   v["projection"][-1]["nopat"] / MM, 1.0)

    # 요약 시트
    ws = wb["요약"]
    for co in applied:
        row = find(ws, f"{co['korean']}({co['ticker']})")
        c.near(f"XLSX 요약 {co['ticker']} 현재가",
               ws.cell(row=row, column=2).value, co["price"], 1e-6)
        for i, s in enumerate(ORDER, start=3):
            c.near(f"XLSX 요약 {co['ticker']} {s}",
                   ws.cell(row=row, column=i).value,
                   val(co, s)["value_per_share"], 0.01)
        c.near(f"XLSX 요약 {co['ticker']} 중립 대비",
               ws.cell(row=row, column=6).value,
               val(co, "중립")["upside_vs_market"], 1e-6)
        c.eq(f"XLSX 요약 {co['ticker']} 판정",
             ws.cell(row=row, column=8).value,
             "낙관에서만 설명됨" if val(co, "낙관")["upside_vs_market"] > 0
             else "어느 시나리오에서도 비쌈")
    row = find(ws, f"{sx['korean']}({sx['ticker']})")
    c.near("XLSX 요약 스페이스X 현재가", ws.cell(row=row, column=2).value,
           sx["price"], 1e-6)
    c.eq("XLSX 요약 스페이스X 판정", ws.cell(row=row, column=8).value,
         "기준이익 미성립 — 산출 불가")
    for rr in sx["reverse"]:
        row = find(ws, rr["scenario"])
        c.near(f"XLSX 스페이스X {rr['scenario']} 요구 NOPAT",
               ws.cell(row=row, column=2).value,
               rr["required_nopat_at_price"] / MM, 0.5)
        c.near(f"XLSX 스페이스X {rr['scenario']} 매출 비중",
               ws.cell(row=row, column=4).value,
               rr["as_share_of_q3_annualised_revenue"], 1e-6)

    # 수식 셀이 빈칸이면 폰·웹 뷰어에서 전부 비어 보입니다.
    blanks = [f"{s.title}!{cc.coordinate}" for s in wb.worksheets
              for rr in s.iter_rows() for cc in rr
              if isinstance(cc.value, str) and cc.value.startswith("=")]
    c.true("XLSX 계산값이 심겨 있음 (수식만 남은 셀 없음)", not blanks,
           str(blanks[:5]))


MUTATIONS_MD = [
    ("MD MSFT 중립 주당가치 훼손", lambda t: t.replace("| $277 |", "| $377 |")),
    ("MD GOOG 낙관 주당가치 훼손", lambda t: t.replace("| $331 |", "| $431 |")),
    ("MD NVDA 정당화 성장률 훼손", lambda t: t.replace("| 16.4% |",
                                                "| 26.4% |")),
    ("MD 보수에 정당화 성장률을 넣음",
     lambda t: t.replace("| 15.0% | $78 | -57% | 없음 |",
                         "| 15.0% | $78 | -57% | 12.0% |")),
    ("MD ROIC 중위 훼손", lambda t: t.replace("| 70.3% |", "| 60.3% |")),
    ("MD 추세 투하자본 배수 훼손", lambda t: t.replace("| 10.59배 |",
                                              "| 1.59배 |")),
    ("MD 천장 훼손", lambda t: t.replace("| $214 |", "| $414 |")),
    ("MD 판정을 뒤집음",
     lambda t: t.replace("| 어느 시나리오에서도 비쌈 |",
                         "| 낙관에서만 설명됨 |", 1)),
    ("MD 스페이스X 요구 NOPAT 훼손", lambda t: t.replace("| 146.9십억 |",
                                                  "| 46.9십억 |")),
    ("MD 스페이스X 사업부 매출 훼손", lambda t: t.replace("| 5.2 |", "| 7.2 |",
                                                 1)),
    ("MD 결론 문장 제거", lambda t: t.replace("낙관 시나리오에서만", "모든 경우에")),
    ("MD 1부 기준 정리 제거",
     lambda t: t.replace("## 1부. 우리가 세운 기준", "## 서론")),
    ("MD ROIC 정의 제거",
     lambda t: t.replace("NOPAT = 보고된 영업이익 × (1 − 실효세율)", "NOPAT")),
    ("MD 자료 기준일 제거", lambda t: t.replace("2026-11-06", "")),
    ("MD 풀이① 10년 CAGR 훼손", lambda t: t.replace("| 20.9% |", "| 30.9% |")),
    ("MD 풀이① 상한 표기 제거",
     lambda t: t.replace("| 67.6%→25.0%(상한) |", "| 25.0% |")),
    ("MD 풀이② 10년 최저 ROIC 훼손",
     lambda t: t.replace("| 22.2% | 113.2% |", "| 32.2% | 113.2% |")),
    ("MD 풀이③ 5년차 NOPAT 훼손", lambda t: t.replace("| 197.0 |",
                                                 "| 297.0 |")),
    ("MD 풀이③ 1년차 재투자율 훼손", lambda t: t.replace("| 55.2% |",
                                                  "| 45.2% |")),
    ("MD 풀이③ 10년 합계 훼손", lambda t: t.replace("| 729.5 |", "| 629.5 |")),
    ("MD 풀이③ 주당가치 훼손", lambda t: t.replace("**$164.31**",
                                             "**$194.31**")),
    ("MD 풀이③ 터미널 비중 서술 훼손", lambda t: t.replace("61%를 차지합니다",
                                                  "41%를 차지합니다")),
    ("MD 풀이② 재투자율 식 제거",
     lambda t: t.replace("재투자율 = 성장률 ÷ 증분ROIC", "재투자율 계산")),
]


def main():
    mutate = "--mutate" in sys.argv
    d = json.load(open(DATA, encoding="utf-8"))
    md = open(MD, encoding="utf-8").read()
    wb = load_workbook(XLSX, data_only=True)

    c = Checks()
    check_md(md, d, c)
    n_md = c.passed + len(c.failures)
    check_xlsx(wb, d, c)
    total = c.passed + len(c.failures)
    print(f"출력물 검사 {total}건 (마크다운 {n_md} · 엑셀 {total - n_md}) — "
          f"통과 {c.passed}, 실패 {len(c.failures)}")
    for f in c.failures:
        print("  ✗", f)
    if c.failures:
        return 1

    if mutate:
        print(f"\n변이 검정 {len(MUTATIONS_MD)}건 — 마크다운을 훼손해 검사가 "
              f"실제로 실패하는지 확인")
        survived = []
        for name, mut in MUTATIONS_MD:
            bad = mut(md)
            if bad == md:
                survived.append(f"{name} (대상 없음)")
                print(f"  ✗ {name}: 훼손 대상을 찾지 못했습니다")
                continue
            c2 = Checks()
            try:
                check_md(bad, d, c2)
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
        print(f"  변이 {len(MUTATIONS_MD)}/{len(MUTATIONS_MD)}건 모두 포착")
    return 0


if __name__ == "__main__":
    sys.exit(main())
