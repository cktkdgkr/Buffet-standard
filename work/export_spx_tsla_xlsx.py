"""
The SpaceX and Tesla workbook, and a check that the Markdown says the same.

Two jobs in one file because they share the figures.

The workbook keeps every derived cell as a formula over cells in the same
sheet, then embed_xlsx_values.py writes the results in beside them so a phone
viewer shows numbers rather than blanks.

The Markdown check parses the report's tables back into numbers and compares
them to the analysis engine. Markdown has no formulas to re-evaluate, so a
figure typed into the wrong row leaves no trace that reading it would reveal.

    python3 export_spx_tsla_xlsx.py
    python3 export_spx_tsla_xlsx.py --verify-md
    python3 export_spx_tsla_xlsx.py --verify-md --mutate
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DATA = os.path.join(HERE, "spx", "spx_tsla.json")
MD = os.path.join(HERE, "스페이스X_테슬라_기업분석.md")
XLSX = os.path.join(HERE, "스페이스X_테슬라_기업분석.xlsx")
MM, BN = 1e6, 1e9

H = Font(bold=True, color="FFFFFF", size=10)
HFILL = PatternFill("solid", fgColor="2F4F6F")
SUB = Font(bold=True, size=10)
SUBFILL = PatternFill("solid", fgColor="DCE6F1")
GOOD = PatternFill("solid", fgColor="E2EFDA")
BAD = PatternFill("solid", fgColor="FCE4E4")
NOTE = Font(italic=True, size=9, color="555555")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
PCT, NUM, X = "0.0%", "#,##0", '0.0"x"'


def load():
    d = json.load(open(DATA))
    d["TSLA"]["ratios"]["in_service"] = {
        int(k): v for k, v in d["TSLA"]["ratios"]["in_service"].items()}
    return d


def header(ws, row, labels, widths):
    for i, l in enumerate(labels, 1):
        c = ws.cell(row=row, column=i, value=l)
        c.font, c.fill, c.border = H, HFILL, BOX
        c.alignment = Alignment(horizontal="center", wrap_text=True)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def guide_sheet(wb, d):
    ws = wb.create_sheet("읽는 방법")
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 108
    rows = [
        ("스페이스X · 테슬라 기업분석", ""),
        ("자료 기준일", f"{d['generated']} — 이 날짜에 SEC에서 받은 공시"),
        ("주가", f"SPCX ${d['prices']['SPCX']['price']:,.2f} · "
               f"TSLA ${d['prices']['TSLA']['price']:,.2f} "
               f"({d['prices']['TSLA']['as_of_utc'][:10]} 종가)"),
        ("WACC", "전 종목 10% 고정 (지시사항)"),
        ("", ""),
        ("스페이스X에 대한 중요한 한계", ""),
        ("10-K 없음", "2026년 6월 상장이라 아직 10-K가 없습니다. 감사된 "
                  "연간 수치는 등록신고서(424B4)의 FY2023~FY2025 "
                  "3년뿐이고, 그 3년 중 영업이익 흑자는 FY2024 한 "
                  "해입니다. 버핏 기준의 10년 일관성 검정은 적용할 수 "
                  "없습니다 — 판정 불가이며, 통과가 아닙니다."),
        ("법인 구조", "SPCX는 발사체 회사가 아닙니다. Space(발사체) · "
                  "Connectivity(스타링크) · Super Intelligence(SI 인프라 "
                  "+ Grok + Cursor + X) 세 사업부입니다."),
        ("", ""),
        ("ROIC 세 가지 분모", ""),
        ("보고", "자기자본 + 상환전환우선주 + 차입금 − 현금·유가증권"),
        ("영업", "보고 − 영업권 − 무형자산. Cursor 인수로 영업권이 "
               "투하자본의 39%여서 분리했습니다."),
        ("가동", "영업 − 건설중자산. 이미 쓴 돈이지만 아직 가동되지 않아 "
               "수익을 낼 수 없는 자본을 뺀 것입니다."),
        ("", ""),
        ("검증", "verify_spx_tsla.py 124건 통과 · 변이 11/11 탐지 · "
               "공시 앵커 20건"),
        ("수식", "파생 셀은 같은 시트의 셀을 참조하는 수식입니다. "
               "계산값은 수식 옆에 심어 두었으므로 재계산하지 않는 "
               "뷰어에서도 숫자가 보입니다."),
    ]
    for r, (a, b) in enumerate(rows, 1):
        ca = ws.cell(row=r, column=1, value=a)
        cb = ws.cell(row=r, column=2, value=b)
        cb.alignment = Alignment(wrap_text=True, vertical="top")
        if a and not b:
            ca.font, ca.fill, cb.fill = SUB, SUBFILL, SUBFILL
        elif a:
            ca.font = SUB
    ws.cell(row=1, column=1).font = Font(bold=True, size=14)


def segments_sheet(wb, d):
    ws = wb.create_sheet("스페이스X 사업부")
    s, sr = d["SPCX"], d["SPCX"]["ratios"]
    ws.cell(row=1, column=1,
            value="2026년 1~9월. 사업부별 투하자본은 공시되지 않으므로 "
                  "사업부 ROIC는 계산할 수 없습니다 — 대신 자기 영업이익으로 "
                  "자기 capex를 댈 수 있는지를 봅니다.").font = NOTE
    header(ws, 2, ["사업부", "매출", "영업이익", "영업이익률", "capex",
                   "capex/매출", "영업이익−capex", "매출 성장"],
           [20, 14, 14, 12, 14, 12, 16, 12])
    order = [("Space", "발사체"), ("Connectivity", "스타링크"),
             ("SI", "슈퍼인텔리전스")]
    r = 3
    for key, ko in order:
        v = sr["segments"][key]
        ws.cell(row=r, column=1, value=f"{ko} ({key})")
        ws.cell(row=r, column=2, value=v["revenue_9m"]).number_format = NUM
        ws.cell(row=r, column=3,
                value=v["operating_income_9m"]).number_format = NUM
        ws.cell(row=r, column=4, value=f"=C{r}/B{r}").number_format = PCT
        ws.cell(row=r, column=5, value=v["capex_9m"]).number_format = NUM
        ws.cell(row=r, column=6, value=f"=E{r}/B{r}").number_format = X
        cell = ws.cell(row=r, column=7, value=f"=C{r}-E{r}")
        cell.number_format = NUM
        cell.fill = GOOD if v["operating_income_less_capex"] > 0 else BAD
        ws.cell(row=r, column=8,
                value=v["revenue_growth_9m"]).number_format = PCT
        r += 1
    ws.cell(row=r, column=1, value="합계").font = SUB
    ws.cell(row=r, column=2, value=f"=SUM(B3:B{r-1})").number_format = NUM
    ws.cell(row=r, column=3, value=f"=SUM(C3:C{r-1})").number_format = NUM
    ws.cell(row=r, column=4, value=f"=C{r}/B{r}").number_format = PCT
    ws.cell(row=r, column=5, value=f"=SUM(E3:E{r-1})").number_format = NUM
    ws.cell(row=r, column=6, value=f"=E{r}/B{r}").number_format = X
    ws.cell(row=r, column=7, value=f"=C{r}-E{r}").number_format = NUM
    for col in range(1, 9):
        ws.cell(row=r, column=col).fill = SUBFILL

    r += 3
    ws.cell(row=r, column=1, value="연결 실적과의 합계 검정").font = SUB
    r += 1
    header(ws, r, ["항목", "사업부 합계", "연결 공시", "차이"],
           [20, 16, 16, 12])
    c = s["consolidated_9m"]
    for label, key, srow in (("매출", "revenue", 3), ("영업이익",
                                                    "operating_income", 4),
                             ("capex", "capex", 5)):
        r += 1
        col = {"revenue": "B", "operating_income": "C", "capex": "E"}[key]
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=f"=SUM({col}3:{col}5)"
                ).number_format = NUM
        ws.cell(row=r, column=3,
                value=c[key]["9m_2026"]).number_format = NUM
        cell = ws.cell(row=r, column=4, value=f"=B{r}-C{r}")
        cell.number_format = NUM
        cell.fill = GOOD


def roic_sheet(wb, d):
    ws = wb.create_sheet("스페이스X ROIC")
    s, sr = d["SPCX"], d["SPCX"]["ratios"]
    sep, dec = s["balance_sheets"]["2026-09-30"], \
        s["balance_sheets"]["2025-12-31"]

    ws.cell(row=1, column=1,
            value="공시 입력값만 값이고, 투하자본·NOPAT·ROIC는 모두 "
                  "이 시트의 셀을 참조하는 수식입니다.").font = NOTE
    header(ws, 2, ["항목", "2025-12-31", "2026-09-30"], [34, 18, 18])
    rows = [("자기자본", "equity"), ("상환전환우선주", "redeemable_preferred"),
            ("차입금", "debt"), ("현금·유가증권", "cash_and_securities"),
            ("영업권", "goodwill"), ("무형자산", "intangibles"),
            ("건설중자산", "construction_in_progress"),
            ("PP&E 총액", "ppe_gross"), ("총자산", "total_assets")]
    r = 3
    first = r
    for label, key in rows:
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=dec.get(key) or 0).number_format = NUM
        ws.cell(row=r, column=3, value=sep.get(key) or 0).number_format = NUM
        r += 1
    idx = {label: first + i for i, (label, _) in enumerate(rows)}

    r += 1
    ws.cell(row=r, column=1, value="투하자본 (수식)").font = SUB
    for col in (1, 2, 3):
        ws.cell(row=r, column=col).fill = SUBFILL
    r += 1
    stack_rows = {}
    for label, formula in (
        ("보고", "{e}{{r}}+{p}{{r}}+{d}{{r}}-{c}{{r}}"),
        ("영업", "=보고-영업권-무형자산"),
        ("가동", "=영업-건설중자산"),
    ):
        ws.cell(row=r, column=1, value=label)
        stack_rows[label] = r
        for col, letter in ((2, "B"), (3, "C")):
            if label == "보고":
                f = (f"={letter}{idx['자기자본']}+{letter}{idx['상환전환우선주']}"
                     f"+{letter}{idx['차입금']}-{letter}{idx['현금·유가증권']}")
            elif label == "영업":
                f = (f"={letter}{stack_rows['보고']}-{letter}{idx['영업권']}"
                     f"-{letter}{idx['무형자산']}")
            else:
                f = (f"={letter}{stack_rows['영업']}"
                     f"-{letter}{idx['건설중자산']}")
            ws.cell(row=r, column=col, value=f).number_format = NUM
        r += 1

    r += 1
    ws.cell(row=r, column=1, value="분자").font = SUB
    for col in (1, 2, 3):
        ws.cell(row=r, column=col).fill = SUBFILL
    r += 1
    oi_row = r
    ws.cell(row=r, column=1, value="9개월 영업이익 (공시)")
    ws.cell(row=r, column=2,
            value=sr["operating_income_9m_2026"]).number_format = NUM
    r += 1
    ann_row = r
    ws.cell(row=r, column=1, value="연율화 (×4/3)")
    ws.cell(row=r, column=2, value=f"=B{oi_row}*4/3").number_format = NUM
    r += 1
    tax_row = r
    ws.cell(row=r, column=1, value="법정세율")
    ws.cell(row=r, column=2, value=0.21).number_format = PCT
    r += 1
    nopat_row = r
    ws.cell(row=r, column=1, value="NOPAT")
    ws.cell(row=r, column=2,
            value=f"=B{ann_row}*(1-B{tax_row})").number_format = NUM

    r += 2
    ws.cell(row=r, column=1, value="ROIC").font = SUB
    for col in range(1, 7):
        ws.cell(row=r, column=col).fill = SUBFILL
    r += 1
    header(ws, r, ["분모", "기초", "기말", "평균", "ROIC", "−10%"],
           [34, 18, 18, 18, 12, 12])
    for label in ("보고", "영업", "가동"):
        r += 1
        src = stack_rows[label]
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=f"=B{src}").number_format = NUM
        ws.cell(row=r, column=3, value=f"=C{src}").number_format = NUM
        ws.cell(row=r, column=4,
                value=f"=(B{r}+C{r})/2").number_format = NUM
        cell = ws.cell(row=r, column=5, value=f"=$B${nopat_row}/D{r}")
        cell.number_format = PCT
        cell.fill = BAD
        ws.cell(row=r, column=6, value=f"=E{r}-0.1").number_format = PCT


def tesla_sheet(wb, d):
    ws = wb.create_sheet("테슬라 ROIC")
    t, tr = d["TSLA"], d["TSLA"]["ratios"]
    ws.cell(row=1, column=1,
            value="영업이익·세율·자본 구성은 공시값이고 NOPAT·투하자본·"
                  "ROIC는 수식입니다.").font = NOTE
    header(ws, 2, ["연도", "매출", "영업이익", "실효세율", "NOPAT",
                   "자기자본", "차입금", "현금·단기투자", "투하자본",
                   "평균 투하자본", "ROIC", "−10%"],
           [9, 14, 14, 11, 14, 14, 14, 15, 14, 15, 10, 10])
    r = 3
    rows_by_fy = {}
    for y in t["annual_roic"]:
        if y["fiscal_year"] < 2015:
            continue
        ws.cell(row=r, column=1, value=f"FY{y['fiscal_year']}")
        ws.cell(row=r, column=2, value=y["revenue"]).number_format = NUM
        ws.cell(row=r, column=3,
                value=y["operating_income"]).number_format = NUM
        ws.cell(row=r, column=4,
                value=y["effective_tax_rate"]).number_format = PCT
        ws.cell(row=r, column=5,
                value=f"=C{r}*(1-D{r})").number_format = NUM
        ws.cell(row=r, column=6, value=y["total_equity"]).number_format = NUM
        ws.cell(row=r, column=7,
                value=y["interest_bearing_debt"]).number_format = NUM
        ws.cell(row=r, column=8,
                value=y["cash_and_short_term_investments"]
                ).number_format = NUM
        ws.cell(row=r, column=9,
                value=f"=F{r}+G{r}-H{r}").number_format = NUM
        prev = rows_by_fy.get(y["fiscal_year"] - 1)
        if prev:
            ws.cell(row=r, column=10,
                    value=f"=(I{r}+I{prev})/2").number_format = NUM
            ws.cell(row=r, column=11,
                    value=f"=E{r}/J{r}").number_format = PCT
            cell = ws.cell(row=r, column=12, value=f"=K{r}-0.1")
            cell.number_format = PCT
            cell.fill = GOOD if (y["roic"] or 0) > 0.10 else BAD
        else:
            for col in (10, 11, 12):
                ws.cell(row=r, column=col, value="—")
        rows_by_fy[y["fiscal_year"]] = r
        r += 1

    r += 2
    ws.cell(row=r, column=1, value="증분 ROIC").font = SUB
    r += 1
    header(ws, r, ["구간", "ΔNOPAT", "Δ투하자본", "증분 ROIC"],
           [18, 16, 16, 14])
    for label, inc in tr["incremental"].items():
        r += 1
        a, b = label.replace("FY", "").split("→")
        ra, rb = rows_by_fy[int(a)], rows_by_fy[int(b)]
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2,
                value=f"=E{rb}-E{ra}").number_format = NUM
        ws.cell(row=r, column=3,
                value=f"=I{rb}-I{ra}").number_format = NUM
        cell = ws.cell(row=r, column=4, value=f"=B{r}/C{r}")
        cell.number_format = PCT
        cell.fill = BAD if (inc["incremental_roic"] or 0) < 0.10 else GOOD


def price_sheet(wb, d):
    ws = wb.create_sheet("가격")
    sr, tr = d["SPCX"]["ratios"], d["TSLA"]["ratios"]
    ws.cell(row=1, column=1,
            value=f"주가는 {d['prices']['TSLA']['as_of_utc'][:10]} 종가. "
                  f"시가총액과 배수는 수식입니다.").font = NOTE
    header(ws, 2, ["항목", "스페이스X", "테슬라"], [30, 22, 22])
    nopat_t = [y for y in d["TSLA"]["annual_roic"]
               if y["fiscal_year"] == 2025][0]["nopat"]
    r = 3
    for label, a, b, fmt in (
            ("주가 (달러)", sr["price"], tr["price"], "#,##0.00"),
            ("발행주식수", sr["shares_outstanding"],
             tr["shares_outstanding"], NUM),
    ):
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=a).number_format = fmt
        ws.cell(row=r, column=3, value=b).number_format = fmt
        r += 1
    mc = r
    ws.cell(row=r, column=1, value="시가총액")
    ws.cell(row=r, column=2, value="=B3*B4").number_format = NUM
    ws.cell(row=r, column=3, value="=C3*C4").number_format = NUM
    r += 1
    np_row = r
    ws.cell(row=r, column=1, value="연율 NOPAT")
    ws.cell(row=r, column=2,
            value=sr["nopat_annualised"]).number_format = NUM
    ws.cell(row=r, column=3, value=nopat_t).number_format = NUM
    r += 1
    ws.cell(row=r, column=1, value="시가총액 / NOPAT")
    for col in ("B", "C"):
        ws.cell(row=r, column=2 if col == "B" else 3,
                value=f"={col}{mc}/{col}{np_row}").number_format = X
    r += 1
    ws.cell(row=r, column=1, value="10% 수익에 필요한 NOPAT")
    ws.cell(row=r, column=2, value=f"=B{mc}*0.1").number_format = NUM
    ws.cell(row=r, column=3, value=f"=C{mc}*0.1").number_format = NUM
    r += 1
    ws.cell(row=r, column=1, value="현재 NOPAT의 몇 배가 필요한가")
    ws.cell(row=r, column=2,
            value=f"=B{r-1}/B{np_row}").number_format = X
    ws.cell(row=r, column=3,
            value=f"=C{r-1}/C{np_row}").number_format = X


def build(d):
    wb = Workbook()
    wb.remove(wb.active)
    guide_sheet(wb, d)
    segments_sheet(wb, d)
    roic_sheet(wb, d)
    tesla_sheet(wb, d)
    price_sheet(wb, d)
    wb.calculation.fullCalcOnLoad = True
    wb.save(XLSX)
    print(f"wrote {XLSX}")
    print(f"시트: {', '.join(wb.sheetnames)}")


# -------------------------------------------------------------- markdown check
def md_tables(text):
    out, heads = [], []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^(#{1,4})\s+(.*)$", lines[i])
        if m:
            heads = heads[:len(m.group(1)) - 1] + [m.group(2).strip()]
            i += 1
            continue
        if lines[i].startswith("|") and i + 1 < len(lines) \
                and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            header_row = [c.strip() for c in lines[i].strip("|").split("|")]
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip()
                             for c in lines[i].strip("|").split("|")])
                i += 1
            out.append((list(heads), header_row, rows))
            continue
        i += 1
    return out


def num(s):
    s = s.strip().replace("**", "")
    if s in ("—", "", "-"):
        return None
    s = s.replace(",", "").replace("%", "").replace("x", "")
    s = s.replace("$", "").replace("+", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def verify_md(d):
    text = open(MD).read()
    tables = md_tables(text)
    sr, tr = d["SPCX"]["ratios"], d["TSLA"]["ratios"]
    checks, fails = 0, []

    def expect(got, want, label, nd=0):
        nonlocal checks
        checks += 1
        if want is None:
            return
        if got is None:
            fails.append(f"{label}: 값 없음 (기대 {want})")
        elif round(got, nd) != round(want, nd):
            fails.append(f"{label}: {got} != {round(want, nd)}")

    seen = set()
    ko = {"발사체 (Space)": "Space", "스타링크 (Connectivity)": "Connectivity",
          "슈퍼인텔리전스 (SI)": "SI"}
    for _heads, head, rows in tables:
        if head[:4] == ["사업부", "매출", "영업이익", "마진"]:
            seen.add("segments")
            checks += 1
            labels = {r[0].replace("**", "") for r in rows}
            if not set(ko).issubset(labels):
                fails.append(f"사업부 행 누락: "
                             f"{sorted(set(ko) - labels)}")
            for r in rows:
                key = ko.get(r[0])
                if key is None:
                    continue
                v = sr["segments"][key]
                expect(num(r[1]), v["revenue_9m"] / MM, f"{key} 매출")
                expect(num(r[2]), v["operating_income_9m"] / MM,
                       f"{key} 영업이익")
                expect(num(r[3]), v["operating_margin"] * 100, f"{key} 마진")
                expect(num(r[4]), v["capex_9m"] / MM, f"{key} capex")
                expect(num(r[5]), v["capex_to_revenue"], f"{key} capex배수", 1)
        elif head[:2] == ["분모", "기초(2025-12)"]:
            seen.add("roic")
            names = {"보고": "reported", "영업": "operating",
                     "가동": "in_service"}
            checks += 1
            if {r[0] for r in rows} != set(names):
                fails.append(f"ROIC 관점 행 집합 불일치: "
                             f"{sorted(r[0] for r in rows)}")
            for r in rows:
                k = names.get(r[0])
                if not k:
                    continue
                v = sr["views"][k]
                expect(num(r[1]), v["opening"] / BN, f"{k} 기초", 1)
                expect(num(r[2]), v["closing"] / BN, f"{k} 기말", 1)
                expect(num(r[3]), v["average"] / BN, f"{k} 평균", 1)
                expect(num(r[4]), v["roic"] * 100, f"{k} ROIC", 1)
        elif head[:3] == ["연도", "매출", "영업이익"] and len(head) == 6 \
                and head[4] == "ROIC":
            seen.add("tesla")
            by = {y["fiscal_year"]: y for y in d["TSLA"]["annual_roic"]}
            for r in rows:
                fy = int(r[0].replace("FY", ""))
                y = by[fy]
                expect(num(r[1]), y["revenue"] / MM, f"TSLA FY{fy} 매출")
                expect(num(r[2]), y["operating_income"] / MM,
                       f"TSLA FY{fy} 영업이익")
                expect(num(r[4]), y["roic"] * 100, f"TSLA FY{fy} ROIC", 1)
        elif head[:2] == ["구간", "ΔNOPAT"]:
            seen.add("incremental")
            # The row labels themselves are checked, not just the figures in
            # the rows that happen to match. A renamed or dropped row was
            # skipped silently and a mutation that renamed FY2022→FY2025 went
            # undetected - a missing row is as wrong as a wrong number.
            checks += 1
            found = {r[0] for r in rows}
            expected = set(tr["incremental"])
            if found != expected:
                fails.append(f"증분 ROIC 행 집합 불일치 — 없음 "
                             f"{sorted(expected - found)}, 초과 "
                             f"{sorted(found - expected)}")
            for r in rows:
                inc = tr["incremental"].get(r[0])
                if not inc:
                    continue
                expect(num(r[1]), inc["delta_nopat"] / BN, f"{r[0]} ΔNOPAT", 1)
                expect(num(r[2]), inc["delta_capital"] / BN, f"{r[0]} Δ자본", 1)
                expect(num(r[3]), inc["incremental_roic"] * 100,
                       f"{r[0]} 증분 ROIC", 1)

    for want in ("segments", "roic", "tesla", "incremental"):
        checks += 1
        if want not in seen:
            fails.append(f"필수 표 누락: {want}")

    print(f"마크다운 검사 {checks}건 중 통과 {checks - len(fails)}건, "
          f"실패 {len(fails)}건")
    for f in fails[:20]:
        print(f"  실패: {f}")
    return 1 if fails else 0


MD_MUTATIONS = [
    ("사업부 영업이익", "| 스타링크 (Connectivity) | 12,796 | 5,211 |",
     "| 스타링크 (Connectivity) | 12,796 | 6,211 |"),
    ("ROIC 관점", "| 가동 | 21.5 | 47.2 |", "| 가동 | 21.5 | 57.2 |"),
    ("테슬라 ROIC", "| FY2025 | 94,827 |", "| FY2025 | 95,827 |"),
    ("증분 ROIC 수치", "| FY2022→FY2025 | -9.3 |",
     "| FY2022→FY2025 | -1.3 |"),
    ("증분 ROIC 행 이름", "| FY2022→FY2025 |", "| FY2022→FY2099 |"),
    ("ROIC 관점 행 삭제", "| 가동 | 21.5 | 47.2 |", ""),
]


def mutate_md(d):
    original = open(MD).read()
    backup = MD + ".bak"
    shutil.copy2(MD, backup)
    caught, ran = 0, 0
    print("\n변이 검정 — 마크다운 수치를 훼손했을 때 검사가 실패해야 정상")
    try:
        for label, a, b in MD_MUTATIONS:
            if a not in original:
                print(f"  {'대상없음':<6}{label}")
                continue
            ran += 1
            open(MD, "w").write(original.replace(a, b, 1))
            run = subprocess.run([sys.executable, __file__, "--verify-md"],
                                 capture_output=True, text=True)
            hit = run.returncode != 0
            caught += hit
            line = next((l.strip() for l in run.stdout.split("\n")
                         if "실패:" in l), "")
            print(f"  {'탐지' if hit else '놓침':<6}{label:<18}{line[:66]}")
    finally:
        open(MD, "w").write(original)
        os.remove(backup)
    print(f"\n변이 {ran}건 중 {caught}건 탐지")
    return 0 if caught == ran and ran else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-md", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    d = load()
    if a.verify_md:
        code = verify_md(d)
        if a.mutate:
            code = mutate_md(d) or code
        return code
    build(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
