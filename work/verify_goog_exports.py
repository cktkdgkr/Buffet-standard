"""
알파벳 보고서 출력물 검증 — 마크다운과 엑셀.

세 포맷이 한 원본(goog_price.json)을 읽게 만들어 두었어도, 읽는 과정에서
틀릴 수 있습니다. 그래서 완성된 산출물을 **되읽어** 엔진 값과 대조합니다.
HTML 은 export_goog_price_html.py --verify 가 자기 페이지를 검사하므로 여기서
다루지 않습니다.

- 마크다운: 표의 숫자를 파싱해 엔진 값과 비교. 행 이름만으로 찾지 않고
  표를 헤더로 먼저 특정합니다 — 여러 표에 같은 행 이름이 있습니다.
- 엑셀: 수식 셀에 심긴 계산값을 읽어 엔진 값과 비교하고, 워크북 안의 검산
  셀("일치"/"불일치")이 실제로 "일치"인지 확인합니다. 행 번호를 적지 않고
  라벨로 찾습니다 — 레이아웃이 한 줄 움직이면 조용히 엉뚱한 셀을 가리키기
  때문입니다.

    python3 verify_goog_exports.py
    python3 verify_goog_exports.py --mutate
"""

import json
import os
import re
import sys

from openpyxl import load_workbook

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "goog", "goog_price.json")
MD = os.path.join(HERE, "알파벳_주가하락_투자기준판정.md")
XLSX = os.path.join(HERE, "알파벳_주가하락_투자기준판정.xlsx")
MM, BN = 1e6, 1e9
WACC = 0.10


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def sg(x, nd=1):
    return "—" if x is None else f"{x * 100:+.{nd}f}%"


def bn(x, nd=1):
    return "—" if x is None else f"{x / BN:,.{nd}f}"


def usd(x, nd=2):
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
    """(헤더, 행들) 목록. 연속한 파이프 줄을 하나의 표로 봅니다."""
    out, cur = [], []
    for line in text.splitlines():
        if line.startswith("|"):
            cur.append([c.strip() for c in line.strip("|").split("|")])
        elif cur:
            if len(cur) >= 2:
                out.append((cur[0], [r for r in cur[2:]]))
            cur = []
    if len(cur) >= 2:
        out.append((cur[0], cur[2:]))
    return out


def md_table(text, header_has, header_exact=False):
    """
    표를 헤더로 특정합니다.

    부분일치로는 모자랍니다 — "판정" 은 결론 요약표와 감시 지표표("판정이
    바뀌는 지점")에 둘 다 걸리고, "ROIC" 는 두 표에 걸립니다. 그럴 때
    header_exact 로 열 이름 완전일치를 씁니다.
    """
    def match(h):
        return any(x == header_has for x in h) if header_exact \
            else any(header_has in x for x in h)

    hits = [(h, r) for h, r in md_tables(text) if match(h)]
    if len(hits) != 1:
        raise SystemExit(f"마크다운 표 특정 실패: 헤더에 {header_has!r} 를 "
                         f"가진 표가 {len(hits)}개 (완전일치={header_exact})")
    return hits[0]


def md_row(text, header_has, label, exact=True, header_exact=False):
    _, rows = md_table(text, header_has, header_exact)
    hit = [r for r in rows if r
           and (r[0].strip("* ") == label if exact else label in r[0])]
    if len(hit) != 1:
        raise SystemExit(f"마크다운 행 특정 실패: {header_has!r} 표에서 "
                         f"{label!r} 가 {len(hit)}개")
    return hit[0]


def check_md(text, d, c):
    a = d["analysis"]
    V, rec, sgm = a["views"], a["ten_year_record"], a["segments"]
    rel = d["release"]

    c.true("마크다운 자료 기준일 표기", d["generated"] in text)
    c.true("마크다운 10-Q accession 표기",
           d["filings"]["10-Q"]["accession"] in text)
    c.true("마크다운 주가 표기", usd(a["price"]) in text)
    c.true("마크다운 티커·한글명 함께", "알파벳" in text and "GOOG" in text)

    # 사업부
    r = md_row(text, "Q3'26 영업이익", "구글 클라우드")
    c.eq("MD 클라우드 Q3'26 매출", r[2],
         bn(sgm["revenue"]["cloud"]["q3_2026"]))
    c.eq("MD 클라우드 Q3'26 영업이익", r[4],
         bn(sgm["operating_income"]["cloud"]["q3_2026"]))

    # 현금흐름 — 다섯 기간 전부
    for p in rel["cash_flow"]:
        r = md_row(text, "잉여현금흐름", p["period"])
        c.eq(f"MD {p['period']} 영업현금", r[1], bn(p["operating_cash_flow"]))
        c.eq(f"MD {p['period']} capex", r[2], bn(p["capex"]))
        c.eq(f"MD {p['period']} FCF", r[3], bn(p["free_cash_flow"]))

    # ROIC 네 관점
    for k, label in (("reported", "보고 기준"),
                     ("operating", "영업(−영업권·무형)"),
                     ("in_service", "가동(−미가동설비)"),
                     ("in_service_ex_stakes", "가동−투자지분")):
        r = md_row(text, "스프레드", label)
        c.eq(f"MD ROIC {k}", r[4], pct(V[k]["roic_ttm"]))
        c.eq(f"MD 평균자본 {k}", r[3], bn(V[k]["average"], 0))

    # 10년 기록
    for y in rec["years"]:
        r = md_row(text, "투하자본(평균)", f"FY{y['fiscal_year']}")
        c.eq(f"MD 10년 ROIC FY{y['fiscal_year']}", r[1], pct(y["roic"]))
        c.eq(f"MD 10년 영업이익 FY{y['fiscal_year']}", r[2],
             bn(y["operating_income"]))

    # 성장률 민감도와 가격별 요구 성장률
    for e in a["growth_sensitivity"]:
        r = md_row(text, "주당 가치", pct(e["growth"], 0))
        c.eq(f"MD 민감도 주당 g={e['growth']:.0%}", r[2],
             usd(e["value_per_share"], 0))
    for e in a["implied_growth_by_price"]:
        r = md_row(text, "함의 영구성장률", usd(e["price"]))
        c.eq(f"MD 요구 성장률 {usd(e['price'])}", r[2],
             pct(e["implied_growth"]))

    # 재무활동 — 자사주 매입이 0 이라는 사실이 보고서에 남아 있는지
    r = md_row(text, "재무활동 (9개월 누적)", "자사주 매입")
    c.eq("MD 자사주매입 2026", r[2],
         bn(a["financing"]["repurchases"]["nine_months_2026"]))
    c.eq("MD 자사주매입 2025", r[1],
         bn(a["financing"]["repurchases"]["nine_months_2025"]))

    # 판정 요약
    r = md_row(text, "판정", "가격(함의 영구성장률)", header_exact=True)
    c.eq("MD 요약 요구 성장률", r[1], pct(a["implied_growth_at_10pct"]))
    c.eq("MD 요약 가격 판정", r[2], "불합격")
    # 요약표는 판정만이 아니라 수치 열도 읽습니다. 판정만 보면 요약의 숫자가
    # 틀려도 통과합니다 — 변이 검정에서 실제로 빠져나갔습니다.
    for label, want in (
            ("ROIC(보고) vs 자본비용 10%", pct(V["reported"]["roic_ttm"])),
            ("ROIC(가동자본)", pct(V["in_service"]["roic_ttm"])),
            ("증분 ROIC(가동−지분)",
             pct(a["incremental"]["incremental_roic_in_service_ex_stakes"])),
            ("가격(주주이익 수익률)",
             f"{pct(a['implied_return_lower'])}~"
             f"{pct(a['implied_return_upper'])}")):
        r = md_row(text, "판정", label, header_exact=True)
        c.eq(f"MD 요약 수치 — {label}", r[1], want)
        c.eq(f"MD 요약 판정 — {label}", r[2],
             "불합격" if "가격" in label else "합격")
    c.true("MD 결론이 사업 합격·가격 불합격",
           "사업은 합격, 가격은 불합격" in text)


# ---------------------------------------------------------------------- 엑셀
def find(ws, label, col=1, limit=90):
    """라벨로 행을 찾습니다. 행 번호를 적어두면 레이아웃과 함께 썩습니다."""
    hits = [r for r in range(1, limit + 1)
            if str(ws.cell(row=r, column=col).value or "").strip() == label]
    if len(hits) != 1:
        raise SystemExit(f"엑셀 행 특정 실패: {ws.title}!{label!r} "
                         f"가 {len(hits)}개")
    return hits[0]


def check_xlsx(wb, d, c):
    a = d["analysis"]
    V, rec = a["views"], a["ten_year_record"]
    rel = d["release"]

    c.true("엑셀 시트 구성",
           [s.title for s in wb.worksheets]
           == ["가정", "공시원자료", "ROIC", "가격", "10년ROIC"],
           str([s.title for s in wb.worksheets]))

    ws = wb["ROIC"]
    c.near("XLSX TTM 영업이익", ws.cell(row=find(ws, "TTM 영업이익 "
                                             "(= FY2025 − 9M2025 + 9M2026)"),
                                    column=2).value,
           a["operating_income_ttm"] / MM, 0.5)
    c.near("XLSX NOPAT",
           ws.cell(row=find(ws, "NOPAT = 영업이익 × (1 − 실효세율)"),
                   column=2).value, a["nopat_ttm"] / MM, 0.5)
    c.near("XLSX NOPAT(법정 21%)",
           ws.cell(row=find(ws, "NOPAT (법정세율 21% 적용 시)"),
                   column=2).value, a["nopat_at_statutory_21"] / MM, 0.5)
    for k, label in (("reported", "보고 기준"),
                     ("operating", "영업 (−영업권·무형)"),
                     ("in_service", "가동 (−미가동 설비)"),
                     ("in_service_ex_stakes", "가동 − 투자지분")):
        row = find(ws, label)
        c.near(f"XLSX ROIC {k}", ws.cell(row=row, column=2).value,
               V[k]["roic_ttm"], 1e-9)
        c.near(f"XLSX 기초 {k}", ws.cell(row=row, column=3).value,
               V[k]["opening"] / MM, 0.5)
        c.near(f"XLSX 기말 {k}", ws.cell(row=row, column=4).value,
               V[k]["closing"] / MM, 0.5)
        c.near(f"XLSX 평균 {k}", ws.cell(row=row, column=5).value,
               V[k]["average"] / MM, 0.5)
        c.near(f"XLSX 스프레드 {k}", ws.cell(row=row, column=6).value,
               V[k]["roic_ttm"] - WACC, 1e-9)
    row = find(ws, "증분 ROIC")
    c.near("XLSX 증분 ROIC(보고)", ws.cell(row=row, column=2).value,
           a["incremental"]["incremental_roic_reported"], 1e-9)
    c.near("XLSX 증분 ROIC(가동−지분)", ws.cell(row=row, column=3).value,
           a["incremental"]["incremental_roic_in_service_ex_stakes"], 1e-9)

    ws = wb["공시원자료"]
    for p in rel["cash_flow"]:
        row = find(ws, p["period"])
        c.near(f"XLSX {p['period']} 영업현금", ws.cell(row=row, column=2).value,
               p["operating_cash_flow"] / MM, 0.5)
        c.near(f"XLSX {p['period']} capex", ws.cell(row=row, column=3).value,
               p["capex"] / MM, 0.5)
        # 잉여현금흐름 열은 수식입니다. 심긴 값이 회사 발표치와 같아야 합니다.
        c.near(f"XLSX {p['period']} FCF(수식)",
               ws.cell(row=row, column=4).value, p["free_cash_flow"] / MM, 0.5)
    row = find(ws, "검산: 네 분기 합 = TTM")
    c.eq("XLSX 분기합 검산 셀", ws.cell(row=row, column=4).value, "일치")
    row = find(ws, "외부자금 조달 합계 (수식)")
    c.near("XLSX 외부조달 합계", ws.cell(row=row, column=2).value,
           a["financing"]["external_capital_raised_9m_2026"] / MM, 0.5)
    row = find(ws, "자사주 매입")
    c.near("XLSX 자사주매입 2026", ws.cell(row=row, column=2).value, 0.0, 1e-9)
    c.near("XLSX 자사주매입 2025", ws.cell(row=row, column=3).value,
           a["financing"]["repurchases"]["nine_months_2025"] / MM, 0.5)

    ws = wb["가격"]
    c.near("XLSX 시가총액", ws.cell(row=find(ws, "시가총액 (백만 달러)"),
                                column=2).value, a["market_cap"] / MM, 1.0)
    c.near("XLSX NOPAT 수익률", ws.cell(row=find(ws, "NOPAT 수익률"),
                                    column=2).value, a["nopat_yield"], 1e-9)
    c.near("XLSX 주가÷NOPAT", ws.cell(row=find(ws, "주가 ÷ NOPAT"),
                                    column=2).value, a["price_to_nopat"], 1e-6)
    c.near("XLSX 주가÷FCF", ws.cell(row=find(ws, "주가 ÷ 잉여현금흐름"),
                                  column=2).value, a["price_to_fcf_ttm"], 1e-4)
    c.near("XLSX 필요배수", ws.cell(row=find(ws, "현재 NOPAT의 몇 배"),
                                column=2).value,
           a["multiple_of_current_nopat"], 1e-6)
    row = find(ws, "하단 — capex 전액을 비용으로")
    c.near("XLSX 주주이익 하단", ws.cell(row=row, column=2).value,
           a["owner_earnings_lower"] / MM, 0.5)
    c.near("XLSX 주주이익 하단 수익률", ws.cell(row=row, column=3).value,
           a["implied_return_lower"], 1e-9)
    row = find(ws, "상단 — 감가상각만 비용으로")
    c.near("XLSX 주주이익 상단", ws.cell(row=row, column=2).value,
           a["owner_earnings_upper"] / MM, 0.5)
    c.near("XLSX 주주이익 상단 수익률", ws.cell(row=row, column=3).value,
           a["implied_return_upper"], 1e-9)
    # 요구 성장률은 엑셀에서 닫힌 해로 풉니다. 엔진은 이분법으로 풉니다.
    # 두 방법이 같은 답을 내야 합니다 — 서로 독립적인 산출 경로입니다.
    row = find(ws, "요구 영구성장률 (역산)")
    c.near("XLSX 요구 성장률 (닫힌 해 = 엔진 이분법)",
           ws.cell(row=row, column=2).value, a["implied_growth_at_10pct"],
           1e-7)
    row = find(ws, "검산: g 를 모형에 되넣으면 시가총액")
    c.near("XLSX 모형 되넣기", ws.cell(row=row, column=2).value,
           a["market_cap"] / MM, 1.0)
    c.eq("XLSX 모형 검산 셀", ws.cell(row=row, column=3).value, "일치")
    for e in a["growth_sensitivity"]:
        hits = [r for r in range(1, 90)
                if isinstance(ws.cell(row=r, column=1).value, (int, float))
                and not isinstance(ws.cell(row=r, column=1).value, bool)
                and abs(ws.cell(row=r, column=1).value - e["growth"]) < 1e-9]
        c.true(f"XLSX 민감도 행 g={e['growth']:.0%}", len(hits) == 1,
               str(hits))
        if len(hits) == 1:
            c.near(f"XLSX 민감도 가치 g={e['growth']:.0%}",
                   ws.cell(row=hits[0], column=2).value, e["value"] / MM, 1.0)
            c.near(f"XLSX 민감도 주당 g={e['growth']:.0%}",
                   ws.cell(row=hits[0], column=3).value,
                   e["value_per_share"], 1e-4)
    for e in a["implied_growth_by_price"]:
        # 200.0 은 엑셀에 "200" 으로 저장되고 int 로 돌아옵니다. float 만
        # 받으면 반올림된 가격 행이 전부 안 보입니다.
        hits = [r for r in range(1, 90)
                if isinstance(ws.cell(row=r, column=1).value, (int, float))
                and not isinstance(ws.cell(row=r, column=1).value, bool)
                and abs(ws.cell(row=r, column=1).value - e["price"]) < 1e-6]
        c.true(f"XLSX 가격 행 {usd(e['price'])}", len(hits) == 1, str(hits))
        if len(hits) == 1:
            c.near(f"XLSX 요구 성장률 {usd(e['price'])}",
                   ws.cell(row=hits[0], column=3).value, e["implied_growth"],
                   1e-7)

    ws = wb["10년ROIC"]
    for y in rec["years"]:
        row = find(ws, f"FY{y['fiscal_year']}")
        c.near(f"XLSX 10년 ROIC FY{y['fiscal_year']}",
               ws.cell(row=row, column=2).value, y["roic"], 1e-12)
        c.near(f"XLSX 10년 문턱초과 FY{y['fiscal_year']}",
               ws.cell(row=row, column=6).value,
               1.0 if y["roic"] > WACC else 0.0, 1e-12)
    c.near("XLSX 문턱 초과 연수", ws.cell(row=find(ws, "문턱 초과 연수"),
                                   column=2).value, 10.0, 1e-9)
    c.near("XLSX 중위 ROIC", ws.cell(row=find(ws, "중위 ROIC (10년)"),
                                  column=2).value,
           rec["summary"]["roic_median"], 1e-9)
    c.near("XLSX 최고 ROIC", ws.cell(row=find(ws, "최고"), column=2).value,
           rec["summary"]["roic_max"], 1e-9)
    c.near("XLSX TTM 행", ws.cell(row=find(ws, "TTM 2026-09"),
                                column=2).value, V["reported"]["roic_ttm"],
           1e-9)

    ws = wb["가정"]
    c.near("XLSX 가정 자본비용", ws.cell(row=find(ws, "자본비용 (WACC)"),
                                   column=2).value, d["wacc"], 1e-12)
    c.near("XLSX 가정 주가", ws.cell(row=find(ws, "주가"), column=2).value,
           a["price"], 1e-9)
    c.near("XLSX 가정 주식수", ws.cell(row=find(ws, "발행주식수"),
                                  column=2).value, a["shares_outstanding"],
           1.0)
    row = find(ws, "ROIC (보고 기준)")
    c.near("XLSX 요약 ROIC(보고)", ws.cell(row=row, column=2).value,
           V["reported"]["roic_ttm"], 1e-9)
    c.eq("XLSX 요약 ROIC 판정", ws.cell(row=row, column=3).value, "합격")
    row = find(ws, "NOPAT 수익률")
    c.eq("XLSX 요약 NOPAT 수익률 판정", ws.cell(row=row, column=3).value,
         "불합격")
    row = find(ws, "요구 영구성장률")
    c.eq("XLSX 요약 요구 성장률 판정", ws.cell(row=row, column=3).value,
         "요구 조건")
    # 수식 셀이 빈칸이면 폰·웹 뷰어에서 전부 비어 보입니다.
    blanks = []
    for sheet in wb.worksheets:
        for rr in sheet.iter_rows():
            for cc in rr:
                if isinstance(cc.value, str) and cc.value.startswith("="):
                    blanks.append(f"{sheet.title}!{cc.coordinate}")
    c.true("XLSX 계산값이 심겨 있음 (수식만 남은 셀 없음)",
           not blanks, str(blanks[:5]))


MUTATIONS_MD = [
    ("MD 클라우드 영업이익 훼손", lambda t: t.replace("| 11.1 |", "| 12.1 |", 1)),
    ("MD Q3 FCF 훼손", lambda t: t.replace("| -9.1 |", "| -4.1 |", 1)),
    ("MD ROIC 가동 훼손", lambda t: t.replace("| 46.5% |", "| 44.5% |", 1)),
    ("MD 요구 성장률 훼손", lambda t: t.replace("| 6.9% |", "| 5.9% |")),
    ("MD 10년 ROIC 훼손", lambda t: t.replace("| 58.0% |", "| 38.0% |", 1)),
    ("MD 자사주매입 훼손", lambda t: t.replace("| 0.0 |", "| -9.0 |", 1)),
    ("MD 가격 판정을 합격으로 훼손",
     lambda t: t.replace("| 가격(함의 영구성장률) | 6.9% | 불합격 |",
                         "| 가격(함의 영구성장률) | 6.9% | 합격 |")),
    ("MD 결론 문장 제거",
     lambda t: t.replace("사업은 합격, 가격은 불합격", "모두 합격")),
    ("MD 자료 기준일 제거", lambda t: t.replace("2026-10-30", "")),
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
                survived.append(f"{name} (훼손 대상 없음)")
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
                      f"— {c2.failures[0][:80]}")
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
