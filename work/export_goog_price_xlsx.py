"""
알파벳 주가 판정 워크북.

파생 셀은 전부 같은 워크북 안의 셀을 참조하는 수식입니다. 공시에서 읽은
원자료만 값으로 넣고, NOPAT·투하자본·ROIC·요구성장률은 엑셀이 계산합니다.
그래서 어떤 숫자든 수식 바를 따라가면 공시 원문 수치까지 내려갈 수 있고,
가정을 바꾸면 아래가 전부 따라 움직입니다 — 특히 자본비용과 성장률을
바꿔 보려면 이 파일이 세 포맷 중 유일한 수단입니다.

openpyxl 은 수식 셀의 값을 비워 두므로, 끝에서 embed_xlsx_values.py 로
계산값을 수식 옆에 심습니다. 그러지 않으면 폰·웹 뷰어에서 전부 빈칸입니다.

    python3 export_goog_price_xlsx.py
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import company_names  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

DATA = os.path.join(HERE, "goog", "goog_price.json")
OUT = os.path.join(HERE, "알파벳_주가하락_투자기준판정.xlsx")

H = Font(bold=True, color="FFFFFF", size=10)
HFILL = PatternFill("solid", fgColor="2F4F6F")
SUB = Font(bold=True, size=10)
SUBFILL = PatternFill("solid", fgColor="DCE6F1")
IN = PatternFill("solid", fgColor="FFF8E1")      # 공시에서 읽은 입력값
OVER = PatternFill("solid", fgColor="E2EFDA")    # 10% 문턱 초과
UNDER = PatternFill("solid", fgColor="FCE4E4")   # 10% 문턱 미달
FLAG = PatternFill("solid", fgColor="FFF2CC")    # 주목
NOTE = Font(italic=True, size=9, color="555555")
TITLE = Font(bold=True, size=13, color="2F4F6F")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
PCT, PCT2, NUM, NUM1, USD = "0.0%", "0.00%", "#,##0", "#,##0.0", '"$"#,##0.00'
MM, BN = 1e6, 1e9


def head(ws, row, labels, widths=None):
    for i, t in enumerate(labels, start=1):
        c = ws.cell(row=row, column=i, value=t)
        c.font, c.fill, c.border = H, HFILL, BOX
        c.alignment = Alignment(horizontal="center", vertical="center",
                                wrap_text=True)
    if widths:
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def band(ws, row, text, span=6):
    c = ws.cell(row=row, column=1, value=text)
    c.font, c.fill = SUB, SUBFILL
    for i in range(1, span + 1):
        ws.cell(row=row, column=i).fill = SUBFILL
        ws.cell(row=row, column=i).border = BOX
    return row + 1


def put(ws, row, col, value, fmt=None, fill=None, font=None, bold=False):
    c = ws.cell(row=row, column=col, value=value)
    c.border = BOX
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    if font:
        c.font = font
    elif bold:
        c.font = Font(bold=True, size=10)
    return c


def note(ws, row, text, span=6):
    c = ws.cell(row=row, column=1, value=text)
    c.font = NOTE
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=row, start_column=1,
                   end_row=row, end_column=span)
    ws.row_dimensions[row].height = 30
    return row + 1


def build(d):
    a = d["analysis"]
    V, rec, sgm = a["views"], a["ten_year_record"], a["segments"]
    rel, fin = d["release"], a["financing"]
    s26 = a["balance_sheets"]["2026-09-30"]
    s25 = a["balance_sheets"]["2025-12-31"]
    name = company_names.label("GOOG", "short")
    wb = Workbook()

    # ------------------------------------------------------- 1. 가정 시트
    ws = wb.active
    ws.title = "가정"
    ws["A1"] = f"{name} — 주가 하락 원인과 투자기준 판정"
    ws["A1"].font = TITLE
    ws["A2"] = (f"자료 기준일 {d['generated']} · 10-Q "
                f"{d['filings']['10-Q']['accession']} "
                f"({d['filings']['10-Q']['filed']} 제출) · 8-K "
                f"{d['filings']['8-K']['accession']} "
                f"({d['filings']['8-K']['filed']} 제출)")
    ws["A2"].font = NOTE
    r = 4
    r = band(ws, r, "바꿔 볼 수 있는 가정 (노란 칸을 고치면 전부 다시 계산됩니다)")
    head(ws, r, ["항목", "값", "단위", "출처"], [34, 18, 12, 46])
    r += 1
    rows = [
        ("자본비용 (WACC)", d["wacc"], "비율",
         "프로젝트 기준. 50개사 조사와 같은 10%."),
        ("주가", a["price"], "달러",
         f"{d['price_history']['last']['date']} 종가. "
         f"{d['price_history']['source_url']}"),
        ("발행주식수", a["shares_outstanding"], "주",
         "10-Q 표지 보통주 합계 (Class A+B+C)"),
        ("TTM 실효세율", a["tax_rate_ttm"], "비율",
         "9개월 법인세 ÷ 9개월 세전이익. 평가이익이 섞여 있음"),
        ("법정세율 (대안)", 0.21, "비율",
         "연방 법정세율. 바꿔 보기용"),
    ]
    ASSUMP = {}
    for label, val, unit, src in rows:
        put(ws, r, 1, label, bold=True)
        fmt = PCT2 if unit == "비율" else (USD if unit == "달러" else NUM)
        put(ws, r, 2, val, fmt, IN)
        put(ws, r, 3, unit)
        put(ws, r, 4, src, font=NOTE)
        ASSUMP[label] = f"가정!$B${r}"
        r += 1
    r = note(ws, r, "노란 칸은 공시·시세에서 그대로 읽은 입력값입니다. 나머지 "
                    "시트의 모든 수치는 이 칸들과 '공시원자료' 시트를 "
                    "참조하는 수식이며, 값을 붙여넣은 셀은 없습니다.", 4)

    # 결론 요약은 다른 시트의 좌표를 참조합니다. 행 번호를 추측해 적으면
    # 레이아웃이 한 줄만 움직여도 조용히 엉뚱한 셀을 가리킵니다 — 실제로
    # 문자열 셀을 참조해 수식이 깨졌습니다. 그래서 자리만 잡아 두고, 아래
    # 시트들을 다 만든 뒤 수집한 실제 좌표로 채웁니다.
    r += 1
    summary_at = r
    r += 2 + 7 + 1
    assum_ws = ws

    # -------------------------------------------------- 2. 공시 원자료 시트
    ws = wb.create_sheet("공시원자료")
    ws["A1"] = "공시에서 읽은 원자료 — 값만 들어 있고 수식은 없습니다"
    ws["A1"].font = TITLE
    r = 3
    r = band(ws, r, "손익계산서 (10-Q, 백만 달러)", 5)
    head(ws, r, ["항목", "Q3 2026", "Q3 2025", "9M 2026", "9M 2025"],
         [34, 16, 16, 16, 16])
    r += 1
    REF = {}
    h = rel["headline"]
    inc_rows = [
        ("매출", sgm["revenue"]["total"]["q3_2026"],
         sgm["revenue"]["total"]["q3_2025"], a["revenue_9m_2026"],
         a["revenue_9m_2025"]),
        ("영업이익", h["operating_income_q3_2026"],
         h["operating_income_q3_2025"], a["operating_income_9m_2026"],
         a["operating_income_9m_2025"]),
        ("기타수익 (평가손익)", h["other_income_q3_2026"],
         h["other_income_q3_2025"], a["other_income_9m_2026"],
         a["other_income_9m_2025"]),
        ("세전이익", None, None, a["pretax_9m_2026"], a["pretax_9m_2025"]),
        ("법인세", None, None, a["tax_9m_2026"], None),
        ("순이익", h["net_income_q3_2026"], h["net_income_q3_2025"],
         a["net_income_9m_2026"], a["net_income_9m_2025"]),
    ]
    for label, *vals in inc_rows:
        put(ws, r, 1, label, bold=True)
        for i, v in enumerate(vals, start=2):
            put(ws, r, i, None if v is None else v / MM, NUM, IN)
        REF[label] = r
        r += 1
    put(ws, r, 1, "희석 EPS (달러)", bold=True)
    for i, v in enumerate((h["eps_q3_2026"], h["eps_q3_2025"],
                           a["eps_diluted_9m_2026"],
                           a["eps_diluted_9m_2025"]), start=2):
        put(ws, r, i, v, USD, IN)
    REF["희석 EPS"] = r
    r += 2

    r = band(ws, r, "FY2025 10-K (백만 달러)", 5)
    head(ws, r, ["항목", "FY2025"], [34, 16])
    r += 1
    fy = d["fy2025_from_engine"]
    for label, v in (("영업이익", fy["operating_income"]),
                     ("실효세율", fy["effective_tax_rate"]),
                     ("감가상각비", fy["depreciation"])):
        put(ws, r, 1, label, bold=True)
        put(ws, r, 2, v if label == "실효세율" else v / MM,
            PCT2 if label == "실효세율" else NUM, IN)
        REF[f"FY2025 {label}"] = r
        r += 1
    r += 1

    r = band(ws, r, "대차대조표 (10-Q, 백만 달러)", 5)
    head(ws, r, ["항목", "2026-09-30", "2025-12-31"], [34, 16, 16])
    r += 1
    for key, label in (("equity", "자기자본"),
                       ("debt", "이자부 장기차입금"),
                       ("cash_and_securities", "현금·단기투자"),
                       ("goodwill", "영업권"),
                       ("intangibles", "무형자산"),
                       ("non_marketable_securities", "비시장성 투자지분"),
                       ("assets_not_yet_in_service", "미가동 설비"),
                       ("total_assets", "총자산")):
        put(ws, r, 1, label, bold=True)
        put(ws, r, 2, s26[key] / MM, NUM, IN)
        put(ws, r, 3, s25[key] / MM, NUM, IN)
        REF[label] = r
        r += 1
    r += 1

    r = band(ws, r, "현금흐름 (8-K 발표문 조정표, 백만 달러)", 5)
    head(ws, r, ["기간", "영업현금흐름", "capex", "잉여현금흐름 (수식)"],
         [20, 18, 18, 22])
    r += 1
    CF = {}
    for p in rel["cash_flow"]:
        put(ws, r, 1, p["period"], bold=True)
        put(ws, r, 2, p["operating_cash_flow"] / MM, NUM, IN)
        put(ws, r, 3, p["capex"] / MM, NUM, IN)
        # 회사 정의 그대로: 영업현금흐름 + capex(음수).
        put(ws, r, 4, f"=B{r}+C{r}", NUM)
        CF[p["period"]] = r
        r += 1
    put(ws, r, 1, "검산: 네 분기 합 = TTM", bold=True)
    q = [CF[k] for k in ("Q4 2025", "Q1 2026", "Q2 2026", "Q3 2026")]
    put(ws, r, 2, "=" + "+".join(f"B{x}" for x in q), NUM)
    put(ws, r, 3, "=" + "+".join(f"C{x}" for x in q), NUM)
    put(ws, r, 4,
        f'=IF(ROUND(B{r}-B{CF["TTM Q3 2026"]},0)=0,"일치","불일치")')
    r += 1
    r = note(ws, r, "잉여현금흐름 열은 수식입니다. 회사 자신의 정의"
                    "(영업현금흐름 − capex)이고, capex 는 음수로 입력돼 "
                    "있으므로 더합니다. 마지막 줄은 네 분기 합이 TTM 과 "
                    "맞는지 엑셀 안에서 다시 검산합니다.", 4)
    r += 1

    r = band(ws, r, "재무활동 9개월 누적 (10-Q, 백만 달러)", 5)
    head(ws, r, ["항목", "2026", "2025"], [34, 16, 16])
    r += 1
    FINR = {}
    for key, label in (("repurchases", "자사주 매입"),
                       ("debt_issued", "차입 조달"),
                       ("common_issued", "보통주 발행 (ATM)"),
                       ("preferred_issued", "우선주 발행"),
                       ("dividends", "배당")):
        put(ws, r, 1, label, bold=True)
        put(ws, r, 2, fin[key]["nine_months_2026"] / MM, NUM, IN)
        put(ws, r, 3, fin[key]["nine_months_2025"] / MM, NUM, IN)
        FINR[key] = r
        r += 1
    put(ws, r, 1, "외부자금 조달 합계 (수식)", bold=True)
    put(ws, r, 2, f"=B{FINR['debt_issued']}+B{FINR['common_issued']}"
                  f"+B{FINR['preferred_issued']}", NUM, FLAG)
    put(ws, r, 3, f"=C{FINR['debt_issued']}+C{FINR['common_issued']}"
                  f"+C{FINR['preferred_issued']}", NUM)
    r += 1

    # --------------------------------------------------------- 3. ROIC 시트
    ws = wb.create_sheet("ROIC")
    ws["A1"] = "투하자본이익률 — 네 가지 분모"
    ws["A1"].font = TITLE
    E = "공시원자료"
    r = 3
    put(ws, r, 1, "TTM 영업이익 (= FY2025 − 9M2025 + 9M2026)", bold=True)
    put(ws, r, 2, f"={E}!B{REF['FY2025 영업이익']}"
                  f"-{E}!E{REF['영업이익']}+{E}!D{REF['영업이익']}", NUM)
    OI = f"$B${r}"
    r += 1
    put(ws, r, 1, "실효세율 (가정 시트)", bold=True)
    put(ws, r, 2, f"={ASSUMP['TTM 실효세율']}", PCT2)
    TAX = f"$B${r}"
    r += 1
    put(ws, r, 1, "NOPAT = 영업이익 × (1 − 실효세율)", bold=True)
    put(ws, r, 2, f"={OI}*(1-{TAX})", NUM)
    NOPAT = f"$B${r}"
    r += 1
    put(ws, r, 1, "NOPAT (법정세율 21% 적용 시)", bold=True)
    put(ws, r, 2, f"={OI}*(1-{ASSUMP['법정세율 (대안)']})", NUM)
    r += 2

    r = band(ws, r, "분모 네 가지와 ROIC", 6)
    head(ws, r, ["투하자본 기준", "ROIC (TTM)", "기초", "기말", "평균 (수식)",
                 "스프레드 (수식)"], [30, 14, 14, 14, 16, 16])
    r += 1
    eq_, dt, csh = REF["자기자본"], REF["이자부 장기차입금"], REF["현금·단기투자"]
    gw, it = REF["영업권"], REF["무형자산"]
    nm, nis = REF["비시장성 투자지분"], REF["미가동 설비"]
    stacks = [
        ("보고 기준", "자기자본 + 차입 − 현금",
         lambda c: f"{E}!{c}{eq_}+{E}!{c}{dt}-{E}!{c}{csh}"),
        ("영업 (−영업권·무형)", "보고 − 영업권 − 무형자산",
         lambda c: f"{E}!{c}{eq_}+{E}!{c}{dt}-{E}!{c}{csh}"
                   f"-{E}!{c}{gw}-{E}!{c}{it}"),
        ("가동 (−미가동 설비)", "영업 − 미가동 설비",
         lambda c: f"{E}!{c}{eq_}+{E}!{c}{dt}-{E}!{c}{csh}"
                   f"-{E}!{c}{gw}-{E}!{c}{it}-{E}!{c}{nis}"),
        ("가동 − 투자지분", "가동 − 비시장성 투자지분",
         lambda c: f"{E}!{c}{eq_}+{E}!{c}{dt}-{E}!{c}{csh}"
                   f"-{E}!{c}{gw}-{E}!{c}{it}-{E}!{c}{nis}-{E}!{c}{nm}"),
    ]
    roic_rows = {}
    for key, (label, how, f) in zip(
            ("reported", "operating", "in_service", "in_service_ex_stakes"),
            stacks):
        put(ws, r, 1, label, bold=True)
        put(ws, r, 3, "=" + f("C"), NUM)      # 기초 = 2025-12-31
        put(ws, r, 4, "=" + f("B"), NUM)      # 기말 = 2026-09-30
        put(ws, r, 5, f"=AVERAGE(C{r}:D{r})", NUM)
        put(ws, r, 2, f"={NOPAT}/E{r}", PCT,
            OVER if V[key]["roic_ttm"] > d["wacc"] else UNDER)
        put(ws, r, 6, f"=B{r}-{ASSUMP['자본비용 (WACC)']}", PCT)
        roic_rows[key] = r
        r += 1
    r = note(ws, r, "분모는 기초·기말 평균입니다(프로젝트 기준). 각 분모가 "
                    "어떻게 쌓였는지는 수식 바에서 바로 보입니다: "
                    + " / ".join(f"{lb} = {hw}" for lb, hw, _ in stacks), 6)
    r += 1

    r = band(ws, r, "증분 수익성 (FY2025 → TTM)", 6)
    head(ws, r, ["항목", "보고 기준", "가동 − 지분 기준"], [30, 18, 20])
    r += 1
    put(ws, r, 1, "FY2025 NOPAT", bold=True)
    put(ws, r, 2, f"={E}!B{REF['FY2025 영업이익']}"
                  f"*(1-{E}!B{REF['FY2025 실효세율']})", NUM)
    fy_nopat = f"$B${r}"
    r += 1
    put(ws, r, 1, "ΔNOPAT", bold=True)
    put(ws, r, 2, f"={NOPAT}-{fy_nopat}", NUM)
    put(ws, r, 3, f"=B{r}", NUM)
    dn = r
    r += 1
    put(ws, r, 1, "Δ투하자본 (기말 − 기초)", bold=True)
    put(ws, r, 2, f"=D{roic_rows['reported']}-C{roic_rows['reported']}", NUM)
    put(ws, r, 3, f"=D{roic_rows['in_service_ex_stakes']}"
                  f"-C{roic_rows['in_service_ex_stakes']}", NUM)
    dc = r
    r += 1
    put(ws, r, 1, "증분 ROIC", bold=True)
    put(ws, r, 2, f"=B{dn}/B{dc}", PCT, FLAG)
    put(ws, r, 3, f"=C{dn}/C{dc}", PCT, OVER)
    inc_roic_row = r
    r += 1
    r = note(ws, r, a["incremental"]["note"], 6)

    # --------------------------------------------------------- 4. 가격 시트
    ws = wb.create_sheet("가격")
    ws["A1"] = "가격이 요구하는 것"
    ws["A1"].font = TITLE
    r = 3
    head(ws, r, ["항목", "값", "수식 / 근거"], [32, 18, 56])
    r += 1
    put(ws, r, 1, "주가", bold=True)
    put(ws, r, 2, f"={ASSUMP['주가']}", USD)
    put(ws, r, 3, f"{d['price_history']['last']['date']} 종가", font=NOTE)
    r += 1
    put(ws, r, 1, "발행주식수", bold=True)
    put(ws, r, 2, f"={ASSUMP['발행주식수']}", NUM)
    put(ws, r, 3, "10-Q 표지", font=NOTE)
    SH = f"$B${r}"
    r += 1
    put(ws, r, 1, "시가총액 (백만 달러)", bold=True)
    put(ws, r, 2, f"={ASSUMP['주가']}*{SH}/1000000", NUM)
    MC = f"$B${r}"
    r += 1
    put(ws, r, 1, "TTM NOPAT (백만 달러)", bold=True)
    put(ws, r, 2, "=ROIC!$B$5", NUM)
    NP = f"$B${r}"
    r += 1
    put(ws, r, 1, "TTM 잉여현금흐름 (백만 달러)", bold=True)
    put(ws, r, 2, f"=공시원자료!D{CF['TTM Q3 2026']}", NUM)
    FCF = f"$B${r}"
    r += 1
    put(ws, r, 1, "TTM 영업현금흐름 (백만 달러)", bold=True)
    put(ws, r, 2, f"=공시원자료!B{CF['TTM Q3 2026']}", NUM)
    OCF = f"$B${r}"
    r += 1
    put(ws, r, 1, "TTM 감가상각비 (백만 달러)", bold=True)
    put(ws, r, 2, f"=공시원자료!B{REF['FY2025 감가상각비']}"
                  f"-{a['depreciation_9m_2025'] / MM:.0f}"
                  f"+{a['depreciation_9m_2026'] / MM:.0f}", NUM)
    DEP = f"$B${r}"
    r += 1
    put(ws, r, 1, "NOPAT 수익률", bold=True)
    yield_row = r
    put(ws, r, 2, f"={NP}/{MC}", PCT, UNDER)
    put(ws, r, 3, "TTM NOPAT ÷ 시가총액. 성장이 없다고 볼 때의 수익률",
        font=NOTE)
    r += 1
    put(ws, r, 1, "주가 ÷ NOPAT", bold=True)
    put(ws, r, 2, f"={MC}/{NP}", NUM1)
    r += 1
    put(ws, r, 1, "주가 ÷ 잉여현금흐름", bold=True)
    put(ws, r, 2, f"={MC}/{FCF}", NUM1)
    r += 1
    put(ws, r, 1, "10% 수익에 필요한 NOPAT", bold=True)
    put(ws, r, 2, f"={MC}*{ASSUMP['자본비용 (WACC)']}", NUM)
    r += 1
    put(ws, r, 1, "현재 NOPAT의 몇 배", bold=True)
    put(ws, r, 2, f"=B{r - 1}/{NP}", NUM1, UNDER)
    r += 2

    r = band(ws, r, "주주이익 밴드", 3)
    head(ws, r, ["기준", "금액 (백만)", "함의 수익률"], [32, 18, 18])
    r += 1
    put(ws, r, 1, "하단 — capex 전액을 비용으로", bold=True)
    put(ws, r, 2, f"={FCF}", NUM)
    put(ws, r, 3, f"=B{r}/{MC}", PCT, UNDER)
    oe_lo_row = r
    r += 1
    put(ws, r, 1, "상단 — 감가상각만 비용으로", bold=True)
    put(ws, r, 2, f"={OCF}-{DEP}", NUM)
    put(ws, r, 3, f"=B{r}/{MC}", PCT, UNDER)
    oe_hi_row = r
    r += 1
    r = note(ws, r, "진실은 둘 사이에 있습니다. 지금 간격이 비정상적으로 넓은 "
                    "것은 이미 쓴 미가동 설비가 감가상각에 아직 반영되지 "
                    "않았기 때문입니다.", 3)
    r += 1

    r = band(ws, r, "영구성장 모형 — 가격이 요구하는 성장률", 4)
    put(ws, r, 1, "기업가치 = NOPAT × (1 − g ÷ 증분ROIC) ÷ (WACC − g)",
        font=Font(bold=True, size=10, color="2F4F6F"))
    r += 1
    put(ws, r, 1, "증분 ROIC (가동 기준 ROIC 적용)", bold=True)
    put(ws, r, 2, f"=ROIC!$B${roic_rows['in_service']}", PCT)
    IR = f"$B${r}"
    r += 1
    put(ws, r, 1, "요구 영구성장률 (역산)", bold=True)
    # 모형을 g 에 대해 풀면 닫힌 해가 나옵니다. 반복 없이 수식 하나로:
    #   V = N(1 − g/r)/(k − g)  ⇒  g = (V·k − N) / (V − N/r)
    put(ws, r, 2, f"=({MC}*{ASSUMP['자본비용 (WACC)']}-{NP})"
                  f"/({MC}-{NP}/{IR})", PCT, UNDER)
    G = f"$B${r}"
    g_row = r
    r += 1
    put(ws, r, 1, "검산: g 를 모형에 되넣으면 시가총액", bold=True)
    put(ws, r, 2, f"={NP}*(1-{G}/{IR})/({ASSUMP['자본비용 (WACC)']}-{G})", NUM)
    put(ws, r, 3, f'=IF(ROUND(B{r}-{MC},0)=0,"일치","불일치")')
    r += 1
    r = note(ws, r, "요구 성장률은 반복 계산이 아니라 닫힌 해입니다: "
                    "g = (V·k − N) ÷ (V − N÷증분ROIC). 바로 아래 줄에서 그 g 를 "
                    "모형에 되넣어 시가총액이 복원되는지 엑셀 안에서 "
                    "검산합니다.", 4)
    r += 1

    r = band(ws, r, "성장률 민감도 (할인율은 가정 시트 값)", 4)
    head(ws, r, ["영구 성장률", "기업가치 (백만)", "주당 가치", "현재가 대비"],
         [18, 20, 16, 16])
    r += 1
    for e in a["growth_sensitivity"]:
        put(ws, r, 1, e["growth"], PCT, IN)
        put(ws, r, 2, f"={NP}*(1-A{r}/{IR})"
                      f"/({ASSUMP['자본비용 (WACC)']}-A{r})", NUM)
        put(ws, r, 3, f"=B{r}*1000000/{SH}", USD)
        put(ws, r, 4, f"=C{r}/{ASSUMP['주가']}-1", PCT,
            OVER if e["vs_price"] > 0 else UNDER)
        r += 1
    r = note(ws, r, "성장률 칸(노란색)을 고치면 세 열이 따라 움직입니다. 3%p "
                    "차이로 가치가 2배 넘게 벌어지는 것이 이 표의 요점입니다 — "
                    "성장률이 할인율에 가까워질수록 분모가 0 으로 가기 "
                    "때문입니다. '적정주가'로 읽으면 안 됩니다.", 4)
    r += 1

    r = band(ws, r, "가격별 요구 성장률 (같은 모형을 거꾸로)", 3)
    head(ws, r, ["주가", "시가총액 (백만)", "요구 영구성장률"], [18, 20, 20])
    r += 1
    for e in a["implied_growth_by_price"]:
        here = abs(e["price"] - a["price"]) < 0.01
        put(ws, r, 1, e["price"], USD, FLAG if here else IN)
        put(ws, r, 2, f"=A{r}*{SH}/1000000", NUM)
        put(ws, r, 3, f"=(B{r}*{ASSUMP['자본비용 (WACC)']}-{NP})"
                      f"/(B{r}-{NP}/{IR})", PCT, UNDER)
        r += 1
    r = note(ws, r, "주황색 줄이 현재가입니다. 주가 칸을 바꾸면 그 가격이 "
                    "요구하는 영구성장률이 나옵니다.", 3)

    # ------------------------------------------------------- 5. 10년 ROIC
    ws = wb.create_sheet("10년ROIC")
    ws["A1"] = f"10년 ROIC 기록 — 50개사 조사 (생성 {rec['generated']})"
    ws["A1"].font = TITLE
    r = 3
    head(ws, r, ["회계연도", "ROIC", "영업이익 (백만)", "투하자본 평균 (백만)",
                 "스프레드 (수식)", "문턱 초과?"], [14, 12, 18, 22, 16, 12])
    r += 1
    first = r
    for y in rec["years"]:
        put(ws, r, 1, f"FY{y['fiscal_year']}", bold=True)
        put(ws, r, 2, y["roic"], PCT, IN)
        put(ws, r, 3, y["operating_income"] / MM, NUM, IN)
        put(ws, r, 4, y["invested_capital_avg"] / MM, NUM, IN)
        put(ws, r, 5, f"=B{r}-{ASSUMP['자본비용 (WACC)']}", PCT,
            OVER if y["roic"] > d["wacc"] else UNDER)
        # 문턱 초과를 1/0 으로 세는 보조 열. COUNTIF 는 리터럴 기준만 받으므로
        # 자본비용 칸을 바꿔도 따라 움직이게 하려면 이 방식이 필요합니다.
        put(ws, r, 6, f"=IF(B{r}>{ASSUMP['자본비용 (WACC)']},1,0)", NUM)
        r += 1
    put(ws, r, 1, "TTM 2026-09", bold=True)
    put(ws, r, 2, f"=ROIC!B{roic_rows['reported']}", PCT, FLAG)
    put(ws, r, 3, "=ROIC!$B$3", NUM)
    put(ws, r, 4, f"=ROIC!E{roic_rows['reported']}", NUM)
    put(ws, r, 5, f"=B{r}-{ASSUMP['자본비용 (WACC)']}", PCT)
    ttm_row = r
    r += 2
    for label, formula, fmt in (
            ("중위 ROIC (10년)", f"=MEDIAN(B{first}:B{first + 9})", PCT),
            ("최고", f"=MAX(B{first}:B{first + 9})", PCT),
            ("최저", f"=MIN(B{first}:B{first + 9})", PCT),
            ("문턱 초과 연수", f"=SUM(F{first}:F{first + 9})", NUM),
            ("고점 대비 현재 (TTM ÷ 최고)",
             f"=B{ttm_row}/MAX(B{first}:B{first + 9})", PCT),
            ("영업이익 배수 (최근 ÷ 고점연도)",
             f"=C{first + 9}/C{first + 5}", NUM1),
            ("투하자본 배수 (최근 ÷ 고점연도)",
             f"=D{first + 9}/D{first + 5}", NUM1)):
        put(ws, r, 1, label, bold=True)
        put(ws, r, 2, formula, fmt)
        r += 1
    r = note(ws, r, "마지막 두 줄이 ROIC 하락의 원인입니다. 영업이익은 늘었는데 "
                    "투하자본이 더 많이 늘면 ROIC 는 떨어집니다. 고점연도는 "
                    f"FY{max(rec['years'], key=lambda y: y['roic'])['fiscal_year']}"
                    f"입니다.", 5)

    # ---------------------------------- 가정 시트의 결론 요약 (실제 좌표로)
    ws = assum_ws
    r = summary_at
    r = band(ws, r, "결론 요약", 4)
    head(ws, r, ["기준", "수치", "판정", "근거"], [34, 18, 12, 46])
    r += 1
    WACC = ASSUMP["자본비용 (WACC)"]
    for label, ref, fmt, why in [
        ("ROIC (보고 기준)", f"ROIC!$B${roic_rows['reported']}", PCT,
         "자기자본 + 차입 − 현금, 기초·기말 평균"),
        ("ROIC (가동자본)", f"ROIC!$B${roic_rows['in_service']}", PCT,
         "미가동 설비를 분모에서 제외"),
        ("증분 ROIC (가동−지분)", f"ROIC!$C${inc_roic_row}", PCT,
         "FY2025 → TTM 의 ΔNOPAT ÷ Δ투하자본"),
        ("NOPAT 수익률", f"가격!$B${yield_row}", PCT,
         "성장이 없다고 볼 때의 수익률"),
        ("주주이익 수익률 (하단)", f"가격!$C${oe_lo_row}", PCT,
         "capex 전액을 비용으로 (= 잉여현금흐름)"),
        ("주주이익 수익률 (상단)", f"가격!$C${oe_hi_row}", PCT,
         "감가상각만 비용으로"),
    ]:
        put(ws, r, 1, label, bold=True)
        put(ws, r, 2, f"={ref}", fmt)
        put(ws, r, 3, f'=IF(B{r}>{WACC},"합격","불합격")')
        put(ws, r, 4, why, font=NOTE)
        r += 1
    # 요구 성장률은 뜻이 반대입니다 — 자본비용보다 *낮아야* 가격이 설명됩니다.
    put(ws, r, 1, "요구 영구성장률", bold=True)
    put(ws, r, 2, f"=가격!$B${g_row}", PCT)
    put(ws, r, 3, f'=IF(B{r}<{WACC},"요구 조건","설명 불가")')
    put(ws, r, 4, "이 칸만 뜻이 반대입니다: 자본비용보다 낮아야 가격이 "
                  "설명되며, 낮다는 것이 합격을 뜻하지는 않습니다",
        font=NOTE)
    r += 1
    note(ws, r, "판정 열은 수식입니다 — 자본비용 칸을 8%나 12%로 바꾸면 "
                "합격·불합격이 그 자리에서 다시 계산됩니다.", 4)
    return wb


def main():
    d = json.load(open(DATA, encoding="utf-8"))
    wb = build(d)
    wb.save(OUT)
    print(f"wrote {OUT}")
    # openpyxl 은 수식 셀에 값을 남기지 않습니다. 폰·웹 뷰어는 재계산을 하지
    # 않으므로, 계산값을 수식 옆에 심지 않으면 전부 빈칸으로 보입니다.
    subprocess.run([sys.executable, "embed_xlsx_values.py",
                    os.path.basename(OUT)], cwd=HERE, check=True)


if __name__ == "__main__":
    main()
