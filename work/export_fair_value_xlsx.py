"""
네 기업 적정주가 워크북 — 가정을 직접 바꿔 볼 수 있게.

이 보고서의 결론은 상한값(성장률 25%, 증분 ROIC 35%)과 할인율에 크게
의존합니다. 그래서 세 포맷 중 엑셀만이 할 수 있는 일을 합니다: **가정을
노란 칸에 두고 10년 투영 전체를 수식으로 남깁니다.** 상한을 올리거나 할인율을
바꾸면 현금흐름·현재가치·터미널·주당가치가 그 자리에서 다시 계산됩니다.

openpyxl 은 수식 셀의 값을 비워 두므로 embed_xlsx_values.py 로 계산값을
심습니다. 그러지 않으면 폰·웹 뷰어에서 전부 빈칸입니다.

    python3 export_fair_value_xlsx.py
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

DATA = os.path.join(HERE, "fv", "fair_value.json")
OUT = os.path.join(HERE, "4개기업_적정주가_판정.xlsx")
MM, BN = 1e6, 1e9
ORDER = ["보수", "중립", "낙관"]

H = Font(bold=True, color="FFFFFF", size=10)
HFILL = PatternFill("solid", fgColor="2F4F6F")
SUB = Font(bold=True, size=10)
SUBFILL = PatternFill("solid", fgColor="DCE6F1")
IN = PatternFill("solid", fgColor="FFF8E1")      # 바꿔 볼 수 있는 가정
SRC = PatternFill("solid", fgColor="EDEDED")     # 공시에서 읽은 값
CHEAP = PatternFill("solid", fgColor="E2EFDA")
RICH = PatternFill("solid", fgColor="FCE4E4")
FLAG = PatternFill("solid", fgColor="FFF2CC")
NOTE = Font(italic=True, size=9, color="555555")
TITLE = Font(bold=True, size=13, color="2F4F6F")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
PCT, PCT2, NUM, NUM1, NUM2, USD = ("0.0%", "0.00%", "#,##0", "#,##0.0",
                                   "#,##0.00", '"$"#,##0.00')
USD0 = '"$"#,##0'


def head(ws, row, labels, widths=None, freeze=True):
    for i, t in enumerate(labels, start=1):
        c = ws.cell(row=row, column=i, value=t)
        c.font, c.fill, c.border = H, HFILL, BOX
        c.alignment = Alignment(horizontal="center", vertical="center",
                                wrap_text=True)
    if widths:
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
    if freeze:
        ws.freeze_panes = ws.cell(row=row + 1, column=1)


def band(ws, row, text, span=8):
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


def note(ws, row, text, span=8, height=32):
    c = ws.cell(row=row, column=1, value=text)
    c.font = NOTE
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=row, start_column=1, end_row=row,
                   end_column=span)
    ws.row_dimensions[row].height = height
    return row + 1


def build(d):
    applied = [c for c in d["companies"] if c["model"] == "applied"]
    sx = [c for c in d["companies"]
          if c["model"] == "base_not_established"][0]
    wb = Workbook()

    # ------------------------------------------------------- 1. 가정 시트
    ws = wb.active
    ws.title = "가정"
    ws["A1"] = "네 기업 적정주가 — 가정"
    ws["A1"].font = TITLE
    ws["A2"] = (f"자료 기준일 {d['generated']} · 50개사 조사 "
                f"{d['roic_study_generated']} · 시세 "
                f"{d['prices_fetched_utc'][:19]} UTC")
    ws["A2"].font = NOTE
    r = 4
    r = band(ws, r, "시장 가정 — 네 기업에 똑같이 적용 (노란 칸을 바꾸면 "
                    "전부 다시 계산됩니다)", 5)
    head(ws, r, ["시나리오", "할인율", "터미널 성장률", "10년차 성장률(감쇠 목표)"],
         [16, 14, 16, 24], freeze=False)
    r += 1
    MK = {}
    for s in ORDER:
        m = d["market_assumptions"][s]
        put(ws, r, 1, s, bold=True)
        put(ws, r, 2, m["discount"], PCT2, IN)
        put(ws, r, 3, m["terminal_growth"], PCT2, IN)
        put(ws, r, 4, m["fade_to"], PCT2, IN)
        MK[s] = {"discount": f"가정!$B${r}", "terminal": f"가정!$C${r}",
                 "fade": f"가정!$D${r}"}
        r += 1
    r = note(ws, r, "할인율과 터미널 성장률은 기업의 성질이 아니라 “내가 "
                    "요구하는 수익률”과 “장기 명목 성장”이므로 네 기업에 "
                    "똑같이 적용합니다. 기업별로 다르게 두면 비교가 "
                    "깨집니다.", 5)
    r += 1

    r = band(ws, r, "기업별 가정을 뽑는 규칙 — 상한이 가장 중요한 판단입니다", 6)
    head(ws, r, ["시나리오", "성장률 = 10년 CAGR ÷", "성장률 상한",
                 "증분ROIC 출처", "증분ROIC ÷", "증분ROIC 상한"],
         [16, 20, 14, 16, 14, 16], freeze=False)
    r += 1
    RL = {}
    for s in ORDER:
        rr = d["rule"][s]
        put(ws, r, 1, s, bold=True)
        put(ws, r, 2, rr["growth_divisor"], NUM1, IN)
        put(ws, r, 3, rr["growth_cap"], PCT2, IN)
        put(ws, r, 4, "10년 최저" if rr["roic_source"] == "min" else "10년 중위")
        put(ws, r, 5, rr["roic_divisor"], NUM1, IN)
        put(ws, r, 6, rr["roic_cap"], PCT2, IN)
        RL[s] = {"gdiv": f"가정!$B${r}", "gcap": f"가정!$C${r}",
                 "rdiv": f"가정!$E${r}", "rcap": f"가정!$F${r}",
                 "rsrc": rr["roic_source"]}
        r += 1
    r = note(ws, r, "상한을 올리면 저평가로, 내리면 고평가로 바뀝니다. 상한이 "
                    "없으면 엔비디아의 10년 CAGR 67.6%가 영구 성장률이 되어 "
                    "어떤 가격도 정당화됩니다. 이 칸들이 결론을 만듭니다.", 6)
    r += 1

    r = band(ws, r, "공시에서 읽은 값 (회색 — 바꾸지 마십시오)", 8)
    head(ws, r, ["기업", "주가", "주식수(십억)", "TTM 영업이익(백만)",
                 "실효세율", "순현금(백만)", "10년 CAGR", "ROIC 중위",
                 "ROIC 최저"],
         [18, 12, 14, 18, 12, 16, 12, 12, 12], freeze=False)
    r += 1
    CO = {}
    for c in applied:
        put(ws, r, 1, f"{c['korean']}({c['ticker']})", bold=True)
        put(ws, r, 2, c["price"], USD, SRC)
        put(ws, r, 3, c["shares_outstanding"]["value"] / BN, NUM2, SRC)
        put(ws, r, 4, c["ttm"]["operating_income"]["value"] / MM, NUM, SRC)
        put(ws, r, 5, c["ttm"]["effective_tax_rate"], PCT2, SRC)
        put(ws, r, 6, c["balance_sheet"]["net_cash"] / MM, NUM, SRC)
        put(ws, r, 7, c["record"]["operating_income_cagr"], PCT2, SRC)
        put(ws, r, 8, c["record"]["summary"]["roic_median"], PCT2, SRC)
        put(ws, r, 9, c["record"]["summary"]["roic_min"], PCT2, SRC)
        CO[c["ticker"]] = {
            "price": f"가정!$B${r}", "shares": f"가정!$C${r}",
            "oi": f"가정!$D${r}", "tax": f"가정!$E${r}",
            "netcash": f"가정!$F${r}", "cagr": f"가정!$G${r}",
            "median": f"가정!$H${r}", "min": f"가정!$I${r}",
            "korean": c["korean"], "data_as_of": c["data_as_of"]}
        r += 1
    r = note(ws, r, "주식수와 순현금은 십억·백만 단위입니다. 자료 기준일: "
             + " · ".join(f"{c['korean']} {c['data_as_of']}"
                          for c in applied)
             + ". 엔비디아는 3분기가 아직 제출되지 않아 7월 분기가 "
               "최신입니다.", 9)

    # ------------------------------------------------- 2. 기업별 투영 시트
    SUMMARY = {}
    for c in applied:
        t = c["ticker"]
        ref = CO[t]
        ws = wb.create_sheet(f"{t} 투영")
        ws["A1"] = (f"{c['korean']}({t}) — 10년 투영 + 터미널 "
                    f"(자료 기준 {c['data_as_of']})")
        ws["A1"].font = TITLE
        r = 3
        put(ws, r, 1, "TTM NOPAT = 영업이익 × (1 − 실효세율)", bold=True)
        put(ws, r, 2, f"={ref['oi']}*(1-{ref['tax']})", NUM)
        NP = f"$B${r}"
        r += 1
        put(ws, r, 1, "순현금", bold=True)
        put(ws, r, 2, f"={ref['netcash']}", NUM)
        NC = f"$B${r}"
        r += 1
        put(ws, r, 1, "주식수 (백만 주)", bold=True)
        put(ws, r, 2, f"={ref['shares']}*1000", NUM)
        SH = f"$B${r}"
        r += 1
        put(ws, r, 1, "시가총액 (백만)", bold=True)
        put(ws, r, 2, f"={ref['price']}*{SH}", NUM)
        MC = f"$B${r}"
        r += 2

        SUMMARY[t] = {}
        for s in ORDER:
            rl, mk = RL[s], MK[s]
            r = band(ws, r, f"{s} 시나리오", 8)
            put(ws, r, 1, "초기 성장률 = MIN(10년 CAGR ÷ 나눔수, 상한)",
                bold=True)
            put(ws, r, 2, f"=MIN({ref['cagr']}/{rl['gdiv']},{rl['gcap']})",
                PCT2)
            G0 = f"$B${r}"
            r += 1
            put(ws, r, 1, "증분 ROIC = MIN(출처 ÷ 나눔수, 상한)", bold=True)
            src = ref["median"] if rl["rsrc"] == "median" else ref["min"]
            put(ws, r, 2, f"=MIN({src}/{rl['rdiv']},{rl['rcap']})", PCT2)
            RI = f"$B${r}"
            r += 1
            put(ws, r, 1, "10년차 성장률 (감쇠 목표)", bold=True)
            put(ws, r, 2, f"={mk['fade']}", PCT2)
            GF = f"$B${r}"
            r += 1
            put(ws, r, 1, "할인율 / 터미널 성장률", bold=True)
            put(ws, r, 2, f"={mk['discount']}", PCT2)
            put(ws, r, 3, f"={mk['terminal']}", PCT2)
            DR, TG = f"$B${r}", f"$C${r}"
            r += 2

            head(ws, r, ["연차", "성장률", "NOPAT", "재투자율", "잉여현금",
                         "할인계수", "현재가치"],
                 [10, 12, 16, 12, 16, 12, 16], freeze=False)
            r += 1
            first = r
            for yidx in range(1, d["projection_years"] + 1):
                put(ws, r, 1, yidx, NUM)
                # 선형 감쇠: 1년차 = 초기, 10년차 = 감쇠 목표.
                put(ws, r, 2,
                    f"={G0}+({GF}-{G0})*({yidx}-1)/"
                    f"({d['projection_years']}-1)", PCT2)
                prev = NP if yidx == 1 else f"$C${r - 1}"
                put(ws, r, 3, f"={prev}*(1+B{r})", NUM)
                put(ws, r, 4, f"=B{r}/{RI}", PCT)
                put(ws, r, 5, f"=C{r}*(1-D{r})", NUM)
                put(ws, r, 6, f"=1/(1+{DR})^{yidx}", NUM2)
                put(ws, r, 7, f"=E{r}*F{r}", NUM)
                r += 1
            last = r - 1
            put(ws, r, 1, "예측기간 합", bold=True)
            put(ws, r, 7, f"=SUM(G{first}:G{last})", NUM)
            PV = f"$G${r}"
            r += 1
            put(ws, r, 1, "터미널 가치 (11년차 이후)", bold=True)
            put(ws, r, 5,
                f"=$C${last}*(1+{TG})*(1-{TG}/{RI})/({DR}-{TG})", NUM)
            put(ws, r, 6, f"=1/(1+{DR})^{d['projection_years']}", NUM2)
            put(ws, r, 7, f"=E{r}*F{r}", NUM)
            TPV = f"$G${r}"
            r += 1
            put(ws, r, 1, "기업가치 = 예측 + 터미널", bold=True)
            put(ws, r, 7, f"={PV}+{TPV}", NUM)
            EV = f"$G${r}"
            r += 1
            put(ws, r, 1, "터미널 비중", bold=True)
            put(ws, r, 7, f"={TPV}/{EV}", PCT, FLAG)
            r += 1
            put(ws, r, 1, "자기자본가치 = 기업가치 + 순현금", bold=True)
            put(ws, r, 7, f"={EV}+{NC}", NUM)
            EQ = f"$G${r}"
            r += 1
            put(ws, r, 1, "주당 가치", bold=True)
            vps = [v for v in c["valuations"] if v["scenario"] == s][0]
            put(ws, r, 7, f"={EQ}/{SH}", USD,
                CHEAP if vps["value_per_share"] > c["price"] else RICH)
            VPS = f"$G${r}"
            r += 1
            put(ws, r, 1, "현재가 대비", bold=True)
            put(ws, r, 7, f"={EQ}/{MC}-1", PCT,
                CHEAP if vps["value_per_share"] > c["price"] else RICH)
            r += 1
            put(ws, r, 1, "현재가 ÷ 주당 가치", bold=True)
            put(ws, r, 7, f"={ref['price']}/{VPS}", NUM2)
            r += 2
            SUMMARY[t][s] = {"vps": f"'{ws.title}'!{VPS}",
                             "eq": f"'{ws.title}'!{EQ}"}

        r = note(ws, r, "노란 칸은 '가정' 시트에 있습니다. 여기 모든 셀은 그 "
                        "칸들을 참조하는 수식이고, 값을 붙여넣은 셀은 "
                        "없습니다. 성장률 상한이나 할인율을 바꾸면 이 표 "
                        "전체가 다시 계산됩니다.", 7)

    # --------------------------------------------------------- 3. 요약 시트
    ws = wb.create_sheet("요약", 1)
    ws["A1"] = "판정 요약"
    ws["A1"].font = TITLE
    r = 3
    head(ws, r, ["기업", "현재가", "보수", "중립", "낙관",
                 "중립 대비", "낙관 대비", "판정"],
         [18, 12, 12, 12, 12, 12, 12, 24])
    r += 1
    for c in applied:
        t = c["ticker"]
        put(ws, r, 1, f"{c['korean']}({t})", bold=True)
        put(ws, r, 2, f"={CO[t]['price']}", USD)
        for i, s in enumerate(ORDER, start=3):
            vps = [v for v in c["valuations"] if v["scenario"] == s][0]
            put(ws, r, i, f"={SUMMARY[t][s]['vps']}", USD,
                CHEAP if vps["value_per_share"] > c["price"] else RICH)
        put(ws, r, 6, f"=D{r}/B{r}-1", PCT)
        put(ws, r, 7, f"=E{r}/B{r}-1", PCT)
        put(ws, r, 8, f'=IF(E{r}>B{r},"낙관에서만 설명됨",'
                      f'"어느 시나리오에서도 비쌈")')
        r += 1
    put(ws, r, 1, f"{sx['korean']}({sx['ticker']})", bold=True)
    put(ws, r, 2, sx["price"], USD, SRC)
    for i in range(3, 8):
        put(ws, r, i, "—")
    put(ws, r, 8, "기준이익 미성립 — 산출 불가", fill=FLAG)
    r += 2
    r = note(ws, r, "판정 열은 수식입니다 — '가정' 시트의 상한이나 할인율을 "
                    "바꾸면 그 자리에서 다시 계산됩니다. 녹색은 평가치가 "
                    "현재가보다 높다는 뜻이고, 이 색은 이 뜻으로만 "
                    "씁니다.", 8)
    r += 1

    r = band(ws, r, "스페이스X — 거꾸로 푼 요구 이익", 5)
    head(ws, r, ["시나리오", "요구 NOPAT(백만)", "3분기 연율화의",
                 "연율화 매출의"], [16, 20, 16, 16], freeze=False)
    r += 1
    for rr in sx["reverse"]:
        put(ws, r, 1, rr["scenario"], bold=True)
        put(ws, r, 2, rr["required_nopat_at_price"] / MM, NUM, RICH)
        put(ws, r, 3, rr["vs_q3_annualised"], NUM1)
        put(ws, r, 4, rr["as_share_of_q3_annualised_revenue"], PCT, RICH)
        r += 1
    r = note(ws, r, sx["why_not"], 5, height=60)
    return wb


def main():
    d = json.load(open(DATA, encoding="utf-8"))
    wb = build(d)
    wb.save(OUT)
    print(f"wrote {OUT}")
    subprocess.run([sys.executable, "embed_xlsx_values.py",
                    os.path.basename(OUT)], cwd=HERE, check=True)


if __name__ == "__main__":
    main()
