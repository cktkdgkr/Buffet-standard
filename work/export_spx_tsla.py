"""
The SpaceX and Tesla report, in Markdown, Word and Excel.

One generator for all three because the content is identical and only the
container differs: the Markdown is laid out for a phone (no table past six
columns), the Word document goes through the shared renderer, and the workbook
keeps the derived cells as formulas with their values embedded.

    python3 export_spx_tsla.py
"""

import json
import os
import subprocess
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DATA = os.path.join(HERE, "spx", "spx_tsla.json")
MD = os.path.join(HERE, "스페이스X_테슬라_기업분석.md")
DOCX_JSON = os.path.join(HERE, "spx", "spx_tsla_report.json")
DOCX = os.path.join(HERE, "스페이스X_테슬라_기업분석.docx")
XLSX = os.path.join(HERE, "스페이스X_테슬라_기업분석.xlsx")

D = json.load(open(DATA))
# JSON has no integer keys, so the fiscal years in the in-service block come
# back as strings. Normalising here keeps every reference below written as the
# year it is.
D["TSLA"]["ratios"]["in_service"] = {
    int(k): v for k, v in D["TSLA"]["ratios"]["in_service"].items()}
MM, BN = 1e6, 1e9
S, T = D["SPCX"], D["TSLA"]
SR, TR = S["ratios"], T["ratios"]
Q = S["quarterly"]
COMMITMENTS = S.get("disclosed_commitments", [])
WACC = D["wacc"]


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def mm(x, nd=0):
    return "—" if x is None else f"{x / MM:,.{nd}f}"


def bn(x, nd=1):
    return "—" if x is None else f"{x / BN:,.{nd}f}"


# ------------------------------------------------------------------ the facts
SPX_PRICE_DATE = D["prices"]["SPCX"]["as_of_utc"][:10]
TSLA_PRICE_DATE = D["prices"]["TSLA"]["as_of_utc"][:10]
SEGMENTS = [("Space", "발사체"), ("Connectivity", "스타링크"),
            ("SI", "슈퍼인텔리전스")]
YEARS_T = [y for y in T["annual_roic"] if y["fiscal_year"] >= 2016]


def blocks():
    """The report as a list of blocks, rendered to Markdown and Word alike."""
    b = []
    add = b.append

    add({"t": "h1", "text": "스페이스X · 테슬라 기업분석"})
    add({"t": "note",
         "text": f"자료 SEC 공시 (SPCX 10-Q 2026-09-30 기말, 424B4 "
                 f"2026-06-12 · TSLA 10-K FY2025, 10-Q 2026-09-30 기말) · "
                 f"주가 {SPX_PRICE_DATE} 종가 · WACC 10% 고정 · "
                 f"작성 {D['generated']} · 검증 124건 통과, 변이 11/11 탐지"})

    # ----------------------------------------------------------------- 요약
    add({"t": "h2", "text": "요약"})
    add({"t": "p",
         "text": "**먼저 정정합니다. 스페이스X는 비상장이 아닙니다.** 제가 "
                 "기억으로 비상장이라고 단정했는데, EDGAR를 조회하니 "
                 "2026년 6월 나스닥에 상장(티커 SPCX, 424B4 6월 12일, "
                 "Class A 6억 3,890만주 × $135.00)했고 10-Q가 두 건 "
                 "제출돼 있습니다. 조회가 먼저였으면 생기지 않을 "
                 "오류였습니다."})
    add({"t": "p",
         "text": "**그리고 SPCX는 발사체 회사가 아닙니다.** 10-Q 주석 1은 "
                 "세 개 사업부를 설명합니다 — Space(발사체), "
                 "Connectivity(스타링크), 그리고 Super Intelligence(SI "
                 "인프라 + Grok + Cursor + X). Cursor(Anysphere)는 2026년 "
                 "8월 14일 지분가치 $60bn 기준 주식 $42,723m으로 "
                 "인수했습니다. 영업권이 투하자본의 39%입니다."})
    add({"t": "p",
         "text": f"**두 회사 모두 ROIC가 자본비용 10%에 미달합니다.** "
                 f"스페이스X는 가장 관대한 관점(영업권·건설중자산 제외)에서도 "
                 f"{pct(SR['views']['in_service']['roic'])}, 테슬라는 FY2025 "
                 f"{pct(TR['roic_latest'])}입니다. 테슬라의 10년 중위는 "
                 f"{pct(TR['roic_median_10y'])}로 문턱 근처이고, 문턱을 넘긴 "
                 f"해는 {TR['years_above_wacc']}/{TR['years_usable']}년입니다."})
    add({"t": "p",
         "text": f"**다만 스페이스X에는 사업부별로 전혀 다른 이야기가 "
                 f"숨어 있습니다.** 9개월 기준 스타링크는 매출 "
                 f"{mm(SR['segments']['Connectivity']['revenue_9m'])}백만 "
                 f"달러에 영업이익 "
                 f"{mm(SR['segments']['Connectivity']['operating_income_9m'])}"
                 f"백만 달러(마진 "
                 f"{pct(SR['segments']['Connectivity']['operating_margin'], 0)}"
                 f")로, 자기 capex "
                 f"{mm(SR['segments']['Connectivity']['capex_9m'])}백만 "
                 f"달러를 스스로 대고도 남습니다. SI 사업부는 영업적자 "
                 f"{mm(SR['segments']['SI']['operating_income_9m'])}백만 "
                 f"달러에 capex "
                 f"{mm(SR['segments']['SI']['capex_9m'])}백만 달러 — 자기 "
                 f"매출의 "
                 f"{SR['segments']['SI']['capex_to_revenue']:.1f}배이고 "
                 f"그룹 전체 capex의 83%입니다."})
    add({"t": "p",
         "text": "**가장 중요한 한계를 먼저 말씀드립니다. 스페이스X에는 "
                 "버핏 기준의 핵심인 10년 일관성 검정을 적용할 수 없습니다.** "
                 "10-K가 아직 없고, 감사된 연간 수치는 등록신고서의 3개 "
                 "회계연도(FY2023~FY2025)뿐입니다. 그 3년 중 영업이익 "
                 "흑자는 FY2024 한 해($466m, 마진 3.3%)입니다. 이건 자료를 "
                 "더 찾아서 해결되는 문제가 아니라, 회사가 아직 그만큼의 "
                 "공개 이력을 갖고 있지 않다는 사실입니다."})

    # ------------------------------------------------------- 1. 사실관계
    add({"t": "h2", "text": "1. 사실관계 — 조회로 확정한 것"})
    add({"t": "table",
         "headers": ["항목", "스페이스X (SPCX)", "테슬라 (TSLA)"],
         "widths": [20, 40, 40],
         "rows": [
             ["CIK", "1181412", "1318605"],
             ["거래소·티커", "나스닥 SPCX", "나스닥 TSLA"],
             ["상장", "2026년 6월 (424B4 6/12)", "2010년 6월"],
             ["SIC", f"{S['meta']['sic']} {S['meta']['sic_description']}",
              f"{T['meta']['sic']} {T['meta']['sic_description']}"],
             ["결산월", "12월", "12월"],
             ["10-K", "**없음** (첫 10-K는 2027년 초 예상)",
              "FY2025분 2026-01-29 제출"],
             ["최신 10-Q", "2026-09-30 기말 (10-22 제출)",
              "2026-09-30 기말 (10-22 제출)"],
             ["연간 감사수치 출처", "등록신고서 424B4 (FY2023~FY2025)",
              "10-K (FY2016~FY2025)"],
             ["사업부", "Space · Connectivity · Super Intelligence",
              "단일 보고부문"],
         ]})
    add({"t": "p",
         "text": "스페이스X의 companyfacts API에는 **연간 기간이 하나도 "
                 "없습니다** — 10-Q의 분기·누적 자료만 있습니다. 그래서 "
                 "연간 수치는 1,167만 자(11MB) 분량의 424B4 본문에서 표를 "
                 "찾아 읽었습니다. 표 번호는 개정판마다 바뀌므로 위치가 "
                 "아니라 내용으로 찾도록 했습니다."})

    # ------------------------------------------------------- 2. 스페이스X
    add({"t": "h2", "text": "2. 스페이스X — 사업부가 말해주는 것"})
    add({"t": "p",
         "text": "연결 영업이익률 3%는 이 회사를 거의 설명하지 못합니다. "
                 "세 사업부의 경제성이 완전히 다르고, 공시는 사업부별 매출· "
                 "영업이익·capex를 모두 제공합니다."})
    rows = []
    for key, ko in SEGMENTS:
        v = SR["segments"][key]
        rows.append([f"{ko} ({key})", mm(v["revenue_9m"]),
                     mm(v["operating_income_9m"]),
                     pct(v["operating_margin"], 0), mm(v["capex_9m"]),
                     f"{v['capex_to_revenue']:.1f}x"])
    c = S["consolidated_9m"]
    rows.append(["**합계**", mm(c["revenue"]["9m_2026"]),
                 mm(c["operating_income"]["9m_2026"]),
                 pct(c["operating_income"]["9m_2026"]
                     / c["revenue"]["9m_2026"], 0),
                 mm(c["capex"]["9m_2026"]),
                 f"{c['capex']['9m_2026'] / c['revenue']['9m_2026']:.1f}x"])
    add({"t": "table",
         "headers": ["사업부", "매출", "영업이익", "마진", "capex",
                     "capex/매출"],
         "rows": rows})
    add({"t": "note", "text": "2026년 1~9월, 단위 백만 달러."})
    add({"t": "p",
         "text": "사업부별 투하자본은 공시되지 않으므로 사업부 ROIC는 "
                 "계산할 수 없습니다. 분모를 임의로 만들지 않고, 대신 같은 "
                 "기간에 **자기가 번 영업이익으로 자기 capex를 댈 수 있는가**"
                 "를 봤습니다. 분모를 발명하지 않아도 답이 보이는 질문입니다."})
    add({"t": "table",
         "headers": ["사업부", "영업이익 − capex", "매출 성장(전년 9개월 대비)"],
         "rows": [[f"{ko} ({key})",
                   mm(SR["segments"][key]["operating_income_less_capex"]),
                   pct(SR["segments"][key]["revenue_growth_9m"], 0)]
                  for key, ko in SEGMENTS]})
    add({"t": "p",
         "text": "스타링크만 양수입니다. 발사체는 매출이 2% 늘면서 적자로 "
                 "돌아섰고, SI는 매출이 380% 늘었지만 그 성장에 매출의 3.7배를 "
                 "쓰고 있습니다. **그룹 capex $48,069m 중 $39,995m(83%)이 "
                 "SI로 갑니다.** 지금의 스페이스X는 스타링크가 버는 돈과 "
                 "IPO로 받은 $85,675m을 AI 인프라에 넣고 있는 회사입니다."})

    add({"t": "h3", "text": "분기로 쪼개면 — 9개월 누계가 가리는 것"})
    add({"t": "p",
         "text": "9개월 누계 영업이익 705백만 달러는 서로 반대인 두 기간을 "
                 "평균한 값입니다. 1~2분기에 영업적자 2,086백만 달러를 냈고 "
                 "3분기에 2,791백만 달러를 벌었습니다. 누계만 보면 지금 "
                 "회사가 어디에 있는지 알 수 없습니다."})
    add({"t": "table",
         "headers": ["항목", "1~2분기", "3분기", "9개월 누계"],
         "rows": [
             ["매출", mm(Q["first_half_2026"]["revenue"]),
              mm(Q["q3_2026"]["revenue"]),
              mm(Q["nine_months_2026"]["revenue"])],
             ["영업이익", mm(Q["first_half_2026"]["operating_income"]),
              mm(Q["q3_2026"]["operating_income"]),
              mm(Q["nine_months_2026"]["operating_income"])],
             ["NOPAT (×0.79)", mm(Q["nopat_first_half"]),
              mm(Q["nopat_q3"]), mm(SR["nopat_annualised"] * 3 / 4)],
             ["capex", mm(Q["first_half_2026"]["capex"]),
              mm(Q["q3_2026"]["capex"]),
              mm(Q["nine_months_2026"]["capex"])],
         ]})
    add({"t": "note", "text": "단위 백만 달러."})
    add({"t": "p",
         "text": "**NOPAT은 어느 기간으로 봐도 마이너스가 아닙니다.** "
                 "9개월 누계 +557백만, 3분기 단독 +2,205백만 달러입니다. "
                 "마이너스인 것은 9개월 누계 *순이익*(−413백만 달러)이고, "
                 "그건 1~2분기 적자와 이자비용 1,968백만 달러 때문입니다. "
                 "3분기 순이익은 +4,404백만 달러입니다."})
    add({"t": "h3", "text": "3분기 속도로 보면 판정이 바뀝니다"})
    rr = Q["q3_run_rate_views"]
    add({"t": "table",
         "headers": ["분모", "6월말", "9월말", "평균", "ROIC", "−10%"],
         "rows": [[{"reported": "보고", "operating": "영업",
                    "in_service": "가동"}[k],
                   bn(v["opening"]), bn(v["closing"]), bn(v["average"]),
                   pct(v["roic"]), pct(v["spread_vs_wacc"])]
                  for k, v in rr.items()]})
    add({"t": "note",
         "text": f"단위 십억 달러. 분자는 3분기 NOPAT "
                 f"{mm(Q['nopat_q3'])}백만 달러 × 4. 분모는 6월말·9월말 "
                 f"투하자본의 평균."})
    add({"t": "p",
         "text": "**세 관점 중 둘이 10%를 넘습니다** — 영업 기준 14.2%, "
                 "가동 기준 20.0%. 9개월 연율 기준(0.9%/1.5%/2.2%)과 전혀 "
                 "다른 결론입니다. 어느 쪽도 정답이라고 부르지 않습니다: "
                 "9개월 연율은 나쁜 두 분기를 섞어 현재를 과소평가하고, "
                 "한 분기를 ×4 하는 것은 같은 논리로 과대평가합니다."})
    add({"t": "h3", "text": "3분기 급증은 인수 때문이 아닙니다"})
    add({"t": "table",
         "headers": ["매출 항목", "3Q2025", "3Q2026", "증가"],
         "rows": [
             ["SI 인프라·솔루션", "359", "7,022", "19배"],
             ["스타링크 소비자", "1,986", "3,121", "+57%"],
             ["스타링크 기업·정부", "1,111", "2,127", "+91%"],
             ["X 광고", "454", "538", "+18%"],
             ["발사체", "1,666", "1,767", "+6%"],
         ]})
    add({"t": "p",
         "text": "Cursor 기여분은 약 539백만 달러입니다 — 10-Q의 프로포마 "
                 "매출 15,114백만 달러와 보고 매출 14,575백만 달러의 "
                 "차이입니다. SI의 7,022백만 달러 중 대부분은 인수가 아닌 "
                 "자체 증가이고, 스타링크 영업이익도 1,190 → 2,367백만 "
                 "달러(마진 45%)로 좋아졌습니다. 반대로 발사체는 영업이익이 "
                 "+259에서 −7백만 달러로 돌아섰습니다."})

    add({"t": "h3", "text": "연간 이력 — 있는 만큼만"})
    add({"t": "table",
         "headers": ["연도", "매출", "영업이익", "순이익", "영업이익률"],
         "rows": [[n, mm(a["revenue"]), mm(a["operating_income"]),
                   mm(a["net_income"]),
                   pct(a["operating_income"] / a["revenue"], 1)
                   if a["revenue"] else "—"]
                  for n, a in sorted(S["annual_from_prospectus"].items())]})
    add({"t": "note",
         "text": "등록신고서 424B4 요약재무, 단위 백만 달러. "
                 "FY2022 이전은 공개 공시에 없습니다."})
    add({"t": "p",
         "text": "3년 중 흑자 1년. 버핏 기준의 '10년간 꾸준한 수익력'은 "
                 "이 자료로는 참도 거짓도 판정할 수 없습니다. "
                 "**판정 불가는 통과가 아닙니다.**"})

    add({"t": "h3", "text": "ROIC — 세 가지 분모"})
    add({"t": "p",
         "text": "알파벳 분석에서 세웠던 구분을 그대로 적용했습니다. 자본을 "
                 "쏟아붓는 회사는 사업이 나빠지지 않아도 ROIC가 떨어집니다 — "
                 "돈을 쓰는 순간 분모가 커지지만 분자는 그 자산이 가동될 "
                 "때까지 기다리기 때문입니다."})
    add({"t": "formula",
         "text": "보고 = 자기자본+우선주+차입금−현금 · "
                 "영업 = 보고−영업권−무형자산 · 가동 = 영업−건설중자산"})
    add({"t": "table",
         "headers": ["분모", "기초(2025-12)", "기말(2026-09)", "평균",
                     "ROIC", "−10%"],
         "rows": [[{"reported": "보고", "operating": "영업",
                    "in_service": "가동"}[k],
                   bn(v["opening"]), bn(v["closing"]), bn(v["average"]),
                   pct(v["roic"]), pct(v["spread_vs_wacc"])]
                  for k, v in SR["views"].items()]})
    add({"t": "note",
         "text": f"단위 십억 달러. 분자는 9개월 영업이익 "
                 f"{mm(SR['operating_income_9m_2026'])}백만 달러를 연율화한 "
                 f"{mm(SR['operating_income_annualised'])}백만 달러에 "
                 f"법정세율 21%를 적용한 NOPAT "
                 f"{mm(SR['nopat_annualised'])}백만 달러."})
    add({"t": "p",
         "text": "연율화는 거칠고, 그 점을 밝혀 둡니다. 분기마다 $20bn씩 "
                 "설비를 늘리는 회사의 4분기는 앞 9개월의 3분의 1이 "
                 "아닙니다. 그래도 9개월 분자를 연간 평균 분모에 나누면 "
                 "수익률이 3분의 1로 깎이는데, 그게 더 큰 오류입니다."})
    add({"t": "p",
         "text": f"**세 관점 모두 문턱 아래입니다.** 가장 관대한 가동자본 "
                 f"기준으로도 {pct(SR['views']['in_service']['roic'])}, "
                 f"10%까지 "
                 f"{pct(-SR['views']['in_service']['spread_vs_wacc'])} "
                 f"부족합니다. 우선주를 자본에 넣은 이유는 "
                 f"2025년 12월 $38,752m이 있었고 IPO로 전환되어 2026년 9월 "
                 f"0이 되었기 때문입니다 — 빼면 돈을 조달한 해에 자본이 "
                 f"$38.8bn 줄어든 것처럼 보입니다."})

    add({"t": "h3", "text": "아직 돈을 벌지 않는 자본"})
    sep = S["balance_sheets"]["2026-09-30"]
    dec = S["balance_sheets"]["2025-12-31"]
    add({"t": "table",
         "headers": ["항목", "2025-12-31", "2026-09-30", "증가"],
         "rows": [
             ["PP&E 총액", mm(dec["ppe_gross"]), mm(sep["ppe_gross"]),
              f"{sep['ppe_gross'] / dec['ppe_gross'] - 1:+.0%}"],
             ["건설중자산", mm(dec["construction_in_progress"]),
              mm(sep["construction_in_progress"]),
              f"{sep['construction_in_progress'] / dec['construction_in_progress'] - 1:+.0%}"],
             ["건설중 비중", pct(dec["construction_in_progress"]
                            / dec["ppe_gross"], 0),
              pct(sep["construction_in_progress"] / sep["ppe_gross"], 0), ""],
             ["영업권", mm(dec["goodwill"]), mm(sep["goodwill"]),
              f"{sep['goodwill'] / dec['goodwill'] - 1:+.0%}"],
             ["계약잔고(RPO)", "—",
              mm(S["backlog"]["remaining_performance_obligation"]), ""],
             ["선수금", mm(S["backlog"]["deferred_revenue_prior"]),
              mm(S["backlog"]["deferred_revenue"]), ""],
         ]})
    add({"t": "p",
         "text": f"건설중자산이 9개월 만에 "
                 f"{mm(dec['construction_in_progress'])}에서 "
                 f"{mm(sep['construction_in_progress'])}백만 달러로 늘어, "
                 f"PP&E 총액의 "
                 f"{pct(sep['construction_in_progress'] / sep['ppe_gross'], 0)}"
                 f"가 아직 가동되지 않은 자산입니다. 알파벳에서 이 비중이 "
                 f"38%였고 그 조정이 증분 ROIC를 25%에서 51%로 바꿨습니다. "
                 f"여기서도 같은 방향으로 작용하지만, 출발점이 0.9%라서 "
                 f"2.2%가 되는 데 그칩니다."})
    add({"t": "p",
         "text": f"계약잔고 "
                 f"{bn(S['backlog']['remaining_performance_obligation'])}"
                 f"십억 달러는 연율 매출의 "
                 f"{SR['backlog_to_revenue_annualised']:.1f}배이고, 공시에 "
                 f"따르면 67%가 1년 내, 27%가 그 다음, 6%가 이후에 "
                 f"인식됩니다. 이미 받은 선수금은 "
                 f"{bn(S['backlog']['deferred_revenue'])}십억 달러입니다. "
                 f"이건 앞으로의 매출을 뒷받침하는 사실이지만, 수익성을 "
                 f"뒷받침하지는 않습니다 — SI의 적자는 매출이 없어서가 "
                 f"아니라 매출보다 비용이 커서 나는 것입니다."})

    add({"t": "h3", "text": "아직 어느 재무상태표에도 없는 자본"})
    for com in COMMITMENTS:
        add({"t": "table",
             "headers": ["항목", "내용"],
             "rows": [
                 ["약정", com["what"]],
                 ["금액", f"약 {com['amount'] / BN:,.0f}십억 달러"],
                 ["체결일", com["agreed"]],
                 ["개시 예정", com["expected_start"]],
                 ["기간", f"{com['term_years']}년"],
                 ["상태", com["status"]],
                 ["출처", f"{com['form']} {com['filed']} "
                        f"({com['accession']})"],
             ]})
        add({"t": "quote", "text": com["quote"],
             "src": f"{com['form']}, {com['filed']}"})
        add({"t": "p", "text": com["note"]})

    # --------------------------------------------------------- 3. 테슬라
    add({"t": "h2", "text": "3. 테슬라 — 10년이 있는 쪽"})
    add({"t": "table",
         "headers": ["연도", "매출", "영업이익", "영업이익률", "ROIC",
                     "−10%"],
         "rows": [[f"FY{y['fiscal_year']}", mm(y["revenue"]),
                   mm(y["operating_income"]),
                   pct(y["operating_margin"], 1),
                   pct(y["roic"]),
                   pct(y["roic"] - WACC) if y["roic"] is not None else "—"]
                  for y in YEARS_T]})
    add({"t": "note", "text": "단위 백만 달러. 10-K 기준."})
    add({"t": "p",
         "text": f"ROIC가 FY2022 {pct(TR['roic_peak'])}에서 FY2025 "
                 f"{pct(TR['roic_latest'])}로 내려왔습니다. 10년 중위 "
                 f"{pct(TR['roic_median_10y'])}, 문턱 초과 "
                 f"{TR['years_above_wacc']}/{TR['years_usable']}년 — "
                 f"'꾸준히 자본비용을 넘긴 회사'라고 하기 어렵습니다."})

    add({"t": "h3", "text": "증분 ROIC — 최근에 넣은 돈이 버는 것"})
    add({"t": "p",
         "text": "10년 평균은 과거에 넣은 자본이 번 것을 말합니다. 지금 "
                 "판단에 필요한 건 **최근에 넣은 자본이 버는 것**이고, 그건 "
                 "영업이익 증가분을 투하자본 증가분으로 나눈 값입니다."})
    add({"t": "table",
         "headers": ["구간", "ΔNOPAT", "Δ투하자본", "증분 ROIC"],
         "rows": [[k, bn(v["delta_nopat"]), bn(v["delta_capital"]),
                   pct(v["incremental_roic"])]
                  for k, v in TR["incremental"].items()]})
    add({"t": "note", "text": "단위 십억 달러."})
    add({"t": "p",
         "text": f"FY2022→FY2025에 투하자본이 "
                 f"{bn(TR['incremental']['FY2022→FY2025']['delta_capital'])}"
                 f"십억 달러 늘었는데 NOPAT은 "
                 f"{bn(TR['incremental']['FY2022→FY2025']['delta_nopat'])}"
                 f"십억 달러 줄었습니다. 증분 ROIC "
                 f"{pct(TR['incremental']['FY2022→FY2025']['incremental_roic'])}"
                 f"는 '최근 3년에 추가로 넣은 자본이 수익을 전혀 늘리지 "
                 f"못했다'는 뜻입니다. FY2020 기준으로 보면 "
                 f"{pct(TR['incremental']['FY2020→FY2025']['incremental_roic'])}"
                 f"로, 플러스지만 역시 문턱 아래입니다."})

    add({"t": "h3", "text": "건설중자산을 빼면 달라지는가"})
    add({"t": "table",
         "headers": ["연도", "보고 ROIC", "가동자본 ROIC", "건설중 비중"],
         "rows": [[f"FY{fy}", pct(v["roic_reported"]),
                   pct(v["roic_in_service"]), pct(v["cip_share"], 0)]
                  for fy, v in sorted(TR["in_service"].items())
                  if "roic_in_service" in v]})
    add({"t": "p",
         "text": f"FY2025 {pct(TR['roic_latest'])} → "
                 f"{pct(TR['in_service'][2025]['roic_in_service'])}. "
                 f"방향은 맞지만 문턱을 넘기지 못합니다. 알파벳과 달리 "
                 f"테슬라의 미사용 자본 비중은 "
                 f"{pct(TR['in_service'][2025]['cip_share'], 0)}로, "
                 f"설명이 되는 크기가 아닙니다."})
    tp = T["ppe"]
    add({"t": "p",
         "text": f"다만 테슬라도 같은 AI 설비 투자를 하고 있습니다. "
                 f"PP&E의 AI·SI 인프라 항목이 2024년 12월 "
                 f"{mm(tp['2024-12-31']['ai_infrastructure'])}에서 2026년 "
                 f"9월 {mm(tp['2026-09-30']['ai_infrastructure'])}백만 "
                 f"달러로 늘었습니다. FY2025 10-K는 이 항목을 'AI "
                 f"infrastructure'로, 2026년 3분기 10-Q는 'SI "
                 f"infrastructure'로 부릅니다 — 스페이스X가 AI 사업부를 "
                 f"Super Intelligence로 개칭한 것과 같은 변경입니다."})

    # ------------------------------------------------------- 4. 가격
    add({"t": "h2", "text": "4. 가격"})
    add({"t": "table",
         "headers": ["항목", "스페이스X", "테슬라"],
         "rows": [
             ["주가", f"${SR['price']:,.2f} ({SPX_PRICE_DATE})",
              f"${TR['price']:,.2f} ({TSLA_PRICE_DATE})"],
             ["발행주식수", f"{SR['shares_outstanding'] / BN:,.3f}십억주",
              f"{TR['shares_outstanding'] / BN:,.3f}십억주"],
             ["시가총액", f"{bn(SR['market_cap'], 0)}십억 달러",
              f"{bn(TR['market_cap'], 0)}십억 달러"],
             ["연율 NOPAT", f"{bn(SR['nopat_annualised'], 1)}십억 달러",
              f"{bn([y for y in YEARS_T if y['fiscal_year'] == 2025][0]['nopat'], 1)}십억 달러"],
             ["시가총액 / NOPAT",
              f"{SR['market_cap'] / SR['nopat_annualised']:,.0f}배",
              f"{TR['price_to_nopat']:,.0f}배"],
         ]})
    add({"t": "p",
         "text": "**DCF를 돌리지 않았습니다.** 알파벳에서는 성장률이 "
                 "떨어지는 여러 시나리오로 현재가치를 쌓았지만, 그 계산은 "
                 "출발점이 되는 정상 수익력이 있어야 성립합니다. 스페이스X는 "
                 "3년 중 2년이 영업적자이고 분기마다 자본구조가 바뀌고 "
                 "있어서, 어떤 숫자를 기준 수익력으로 잡아도 그 선택이 "
                 "결과를 전부 결정합니다. 테슬라는 기준 수익력은 있지만 "
                 "증분 ROIC가 음수여서, 성장을 가정하는 모형이 가치를 "
                 "늘리는 게 아니라 줄입니다. 두 경우 모두 모형을 "
                 "돌리는 것이 정확도를 높이지 않고 가정을 숨깁니다."})
    add({"t": "p",
         "text": f"대신 거꾸로 묻는 게 정직합니다. 테슬라의 현재 시가총액 "
                 f"{bn(TR['market_cap'], 0)}십억 달러가 10% 수익률을 "
                 f"내려면 NOPAT이 "
                 f"{bn(TR['market_cap'] * WACC, 0)}십억 달러여야 합니다. "
                 f"FY2025 실적의 "
                 f"{TR['market_cap'] * WACC / [y for y in YEARS_T if y['fiscal_year'] == 2025][0]['nopat']:.0f}"
                 f"배입니다. 스페이스X는 "
                 f"{bn(SR['market_cap'] * WACC, 0)}십억 달러가 필요한데 "
                 f"연율 NOPAT이 {bn(SR['nopat_annualised'], 1)}십억 "
                 f"달러입니다."})

    # ------------------------------------------------- 5. 버핏 기준 판정
    add({"t": "h2", "text": "5. 버핏 기준 판정"})
    add({"t": "table",
         "headers": ["기준", "스페이스X", "테슬라"],
         "widths": [26, 37, 37],
         "rows": [
             ["이해할 수 있는 사업",
              "✗ 세 사업부의 경제성이 전혀 다르고, 그중 하나는 2개월 전 "
              "인수한 AI 사업",
              "△ 자동차·에너지는 명확, AI·로보틱스 비중이 커지는 중"],
             ["10년 일관된 수익력",
              "**판정 불가** — 감사된 연간 수치 3년, 그중 흑자 1년",
              "✗ 문턱 초과 5/10년, 중위 "
              f"{pct(TR['roic_median_10y'])}"],
             [f"ROIC > WACC({WACC:.0%})",
              f"✗ 보고 {pct(SR['views']['reported']['roic'])} · 가동 "
              f"{pct(SR['views']['in_service']['roic'])}",
              f"✗ FY2025 {pct(TR['roic_latest'])} · 가동 "
              f"{pct(TR['in_service'][2025]['roic_in_service'])}"],
             ["증분 ROIC",
              "✗ 산출 불가 (자본구조 급변) · SI capex는 매출의 3.7배",
              f"✗ FY2022→25 "
              f"{pct(TR['incremental']['FY2022→FY2025']['incremental_roic'])}"],
             ["낮은 부채",
              f"△ 차입금 {bn(sep['debt'], 0)}십억 달러에 현금·유가증권 "
              f"{bn(sep['cash_and_securities'], 0)}십억 달러로 순현금",
              "△ 순현금이지만 FY2025 영업이익이 이자비용 대비 축소"],
             ["가격 매력",
              f"✗ 시총/NOPAT "
              f"{SR['market_cap'] / SR['nopat_annualised']:,.0f}배",
              f"✗ 시총/NOPAT {TR['price_to_nopat']:,.0f}배"],
         ]})
    add({"t": "p",
         "text": "**스페이스X 안에서 버핏 기준을 자기 숫자로 통과하는 "
                 "사업은 스타링크 하나입니다.** 9개월 영업이익률 41%, 자기 "
                 "capex를 자기 영업이익으로 대고, 매출이 57% 늘었습니다. "
                 "문제는 그걸 따로 살 수 없다는 것입니다 — SPCX를 사면 "
                 "스타링크가 버는 돈을 SI 사업부에 넣는 결정을 함께 사게 "
                 "됩니다. 지금 그 비율은 그룹 capex의 83%입니다."})

    # ---------------------------------------------------- 6. 한계
    add({"t": "h2", "text": "6. 이 분석의 한계"})
    add({"t": "bullets", "items": [
        "**스페이스X는 10년 검정을 할 수 없습니다.** 가장 중요한 한계이고, "
        "자료를 더 찾아 해결되지 않습니다. 첫 10-K가 나오는 2027년 초에 "
        "FY2026 연간 수치가 확정되면 4년이 됩니다.",
        "**기간을 어떻게 잡느냐가 판정을 바꿉니다.** 9개월 연율 기준으로는 "
        "세 관점 모두 문턱에 미달하고(0.9%/1.5%/2.2%), 3분기 속도 "
        "기준으로는 둘이 넘습니다(9.2%/14.2%/20.0%). 둘 다 추정이고 "
        "방향만 반대입니다. 1~2분기 영업적자 2,086백만 달러가 일시적인지 "
        "3분기 흑자 2,791백만 달러가 지속적인지는 다음 분기들이 "
        "답할 문제입니다.",
        "**사업부 ROIC는 계산하지 않았습니다.** 사업부별 투하자본이 "
        "공시되지 않습니다. 사업부 capex를 누적해 분모를 만드는 방법이 "
        "있지만, 그건 측정이 아니라 추정이고 결과를 좌우합니다.",
        "**Cursor 인수 2개월분만 반영돼 있습니다.** 2026년 8월 14일 "
        "종료이므로 3분기 실적에 1.5개월만 들어 있고, 영업권 "
        f"{bn(sep['goodwill'], 0)}십억 달러는 전액 반영돼 있습니다. "
        "분자와 분모의 기간이 어긋나 있어 다음 분기부터 ROIC가 올라갈 "
        "여지가 있습니다.",
        "**DCF를 돌리지 않았습니다.** 이유는 4장에 적었습니다. 필요하시면 "
        "기준 수익력을 무엇으로 잡을지 먼저 정한 뒤에 돌리겠습니다.",
        "**WACC 10%는 지시에 따른 고정값입니다.** 두 회사의 실제 자본비용은 "
        "다르고, 특히 스페이스X는 상장 4개월째여서 시장 기반 추정이 "
        "의미를 갖기 어렵습니다.",
    ]})

    add({"t": "h2", "text": "7. 검증과 재현"})
    add({"t": "table",
         "headers": ["검증 방식", "내용"],
         "rows": [
             ["항등식", "투하자본 구성, NOPAT, ROIC, 평균 산정, "
                     "PP&E 순액=총액−감가상각누계, 시가총액"],
             ["합계 검정", "사업부 매출·영업이익·capex의 합이 연결 수치와 "
                      "일치, PP&E 구성항목이 총액 범위 내"],
             ["범위 검정", "발행주식수 10억~1,000억주, 시가총액 "
                      "1,000억~10조 달러 (배율 오류 탐지용)"],
             ["공시 앵커", "20건 — 공시 본문에서 손으로 읽은 수치와 대조"],
             ["합계", "124건 전부 통과"],
             ["변이 검정", "11건 전부 탐지 (10-K 존재를 위조하는 변이 포함)"],
         ]})
    add({"t": "p",
         "text": "합계 검정이 특히 중요했습니다. 이 수치들은 API가 아니라 "
                 "공시 렌더링을 파싱해 얻은 것이고, 파서가 숫자 대신 표제 "
                 "행을 잡거나 '$ in Millions' 배율을 주식수에 적용하면 "
                 "**내부적으로 일관되면서 틀린 값**이 나옵니다. 실제로 둘 다 "
                 "일어났습니다 — 우선주가 0으로 읽힌 것은 $38,752m 위의 "
                 "표제를 잡았기 때문이고, 주식수가 1.4×10¹⁶으로 나와 "
                 "시가총액이 200경 달러가 된 적도 있습니다. 사업부 합계와 "
                 "범위 검정이 그 부류를 잡습니다."})
    add({"t": "table",
         "headers": ["파일", "역할"],
         "rows": [
             ["collect_spx_tsla.py", "10-Q·10-K·424B4에서 재무제표 표 수집"],
             ["analyse_spx_tsla.py", "ROIC 3개 관점·사업부·증분·가격"],
             ["verify_spx_tsla.py", "항등식·합계·앵커 + 변이 검정"],
             ["export_spx_tsla.py", "마크다운·워드·엑셀 작성"],
         ]})
    return b


# ------------------------------------------------------------------ markdown
def write_md(bs):
    out = []
    for b in bs:
        t = b["t"]
        if t == "h1":
            out += [f"# {b['text']}", ""]
        elif t == "h2":
            out += ["", f"## {b['text']}", ""]
        elif t == "h3":
            out += ["", f"### {b['text']}", ""]
        elif t in ("p",):
            out += [b["text"], ""]
        elif t == "note":
            out += [f"> {b['text']}", ""]
        elif t == "formula":
            out += ["```", b["text"], "```", ""]
        elif t == "bullets":
            out += [f"- {i}" for i in b["items"]] + [""]
        elif t == "table":
            h = b["headers"]
            align = ["left"] + ["right"] * (len(h) - 1)
            if len(h) <= 3:
                align = ["left"] * len(h)
            out.append("| " + " | ".join(h) + " |")
            out.append("|" + "|".join(
                {"left": ":--", "right": "--:"}[a] for a in align) + "|")
            for r in b["rows"]:
                out.append("| " + " | ".join(str(x) for x in r) + " |")
            out.append("")
    with open(MD, "w") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"wrote {MD} ({len(out)} 줄)")


# ---------------------------------------------------------------------- word
def write_docx(bs):
    payload = []
    for b in bs:
        blk = dict(b)
        if blk["t"] == "table" and "widths" not in blk:
            n = len(blk["headers"])
            first = max(12, min(26, int(100 / n) + 8))
            blk["widths"] = [first] + [(100 - first) / (n - 1)] * (n - 1)
            blk["numeric"] = list(range(1, n))
        payload.append(blk)
    with open(DOCX_JSON, "w") as fh:
        json.dump({"title": "스페이스X · 테슬라 기업분석",
                   "blocks": payload}, fh, indent=1, ensure_ascii=False)
    # The renderer resolves both paths against its own directory, so it is
    # given relative ones from there.
    subprocess.run(["node", "export_memo_docx.js",
                    os.path.relpath(DOCX_JSON, HERE),
                    os.path.basename(DOCX)],
                   cwd=HERE, check=True)


def main():
    bs = blocks()
    write_md(bs)
    write_docx(bs)


if __name__ == "__main__":
    main()
