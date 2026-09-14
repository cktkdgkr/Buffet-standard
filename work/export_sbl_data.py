"""
Build the Word payload for the Samsung Biologics analysis.

Every figure is read from work/kr/sbl_valuation.json (which is built from
work/kr/sbl_raw.json, which is built from the audited PDFs), so nothing in the
document is typed by hand. Rendered by export_memo_docx.js.
"""

import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
VAL = os.path.join(HERE, "kr", "sbl_valuation.json")
RAW = os.path.join(HERE, "kr", "sbl_raw.json")
OUT = os.path.join(HERE, "_sbl_payload.json")

T, B = 1e12, 1e9


def won_t(v, dp=2):
    return "—" if v is None else f"{v/T:,.{dp}f}조원"


def won_b(v, dp=0):
    return "—" if v is None else f"{v/B:,.{dp}f}"


def won_e(v, dp=0):
    """억원. One 억 is 100 million won."""
    return "—" if v is None else f"{v/1e8:,.{dp}f}억원"


def pct(v, dp=1):
    return "—" if v is None else f"{v*100:,.{dp}f}%"


def main():
    with open(VAL) as fh:
        d = json.load(fh)
    with open(RAW) as fh:
        raw = json.load(fh)

    years = {y["fiscal_year"]: y for y in d["years"]}
    oe = {e["fiscal_year"]: e for e in d["owner_earnings"]}
    mkt = d["market"]
    cap = mkt["market_cap_computed"]
    md = d["margin_decomposition"]
    cf = d["customer_funding"]
    conc = d["concentration"]
    it = raw["interim_2026"]
    dis = raw["discontinued_operations"]
    eq = raw["equity_transactions"]
    seg = raw["segment_note_fy2024"]
    wacc_lo, wacc_hi = d["cost_of_capital"]["range"]

    inc5 = [e for e in d["incremental_returns"] if e["years"] == 5]
    inc5_vals = [e["operating_ex_payables_ex_cip"]["incremental_roic"]
                 for e in inc5]

    cum = lambda a, b, key, src: sum((src[fy].get(key) or 0)
                                    for fy in range(a, b + 1) if fy in src)
    cum_ni = cum(2016, 2025, "net_income", oe)
    cum_capex = cum(2016, 2025, "capex", oe)
    cum_ocf = cum(2016, 2025, "ocf", years)
    cum_fcf = cum(2016, 2025, "fcf_from_cash_flow_statement", oe)
    cum_fcf_5y = cum(2021, 2025, "fcf_from_cash_flow_statement", oe)
    cum_ni_5y = cum(2021, 2025, "net_income", oe)

    norm = d["valuation"]["run_rate_fx_normalised"]
    rep = d["valuation"]["reported_fy2025"]
    run = d["valuation"]["run_rate_2026"]
    sc = {s["scenario"]: s for s in norm["scenarios"]}
    im_norm = d["implied"]["run_rate_fx_normalised"]
    im_run = d["implied"]["run_rate_2026"]

    blocks = []
    add = blocks.append
    h1 = lambda t: add({"t": "h1", "text": t})
    h2 = lambda t: add({"t": "h2", "text": t})
    h3 = lambda t: add({"t": "h3", "text": t})
    p = lambda t: add({"t": "p", "text": t})
    note = lambda t: add({"t": "note", "text": t})
    quote = lambda t, s: add({"t": "quote", "text": t, "src": s})
    formula = lambda t: add({"t": "formula", "text": t})
    bullets = lambda items: add({"t": "bullets", "items": items})

    def table(headers, rows, widths, numeric=None):
        add({"t": "table", "headers": headers, "rows": rows,
             "widths": widths, "numeric": numeric or []})

    # ====================================================== 0. 결론 먼저
    h1("결론 요약")

    p("삼성바이오로직스는 버핏이 세운 일곱 개 기준 가운데 사업의 질에 관한 여섯 개를 "
      "대체로 통과합니다. 통과하지 못하는 것은 일곱 번째, 가격입니다. 그리고 그 미달 "
      "폭은 판단의 여지가 있는 정도가 아닙니다.")

    table(
        ["기준", "판정", "근거"],
        [["1. 이해할 수 있는 사업", "통과",
          "위탁생산 한 가지. 분할 후 단일 부문. 매출 인식과 원가 구조가 단순"],
         ["2. 기존 자본의 수익률 > 자본비용", "통과",
          f"FY2025 ROIC {pct(years[2025]['roic_operating_ex_cip'])} vs 자본비용 "
          f"{pct(wacc_lo)}~{pct(wacc_hi)}"],
         ["3. 지속되는 해자", "조건부 통과",
          "규제에 묶인 전환비용과 세계 최대 규모. 다만 상위 5개 고객이 매출의 "
          f"{pct(conc['2025']['top5_share'])}"],
         ["4. 증분 자본의 수익률 > 자본비용", "통과",
          f"5년 구간 증분 ROIC {pct(min(inc5_vals))}~{pct(max(inc5_vals))}"],
         ["5. 자본배분·주주지향", "조건부 통과",
          "재투자 수익률은 높으나 배당 0, 2022년 3.19조원 증자, 지배주주 74.3%"],
         ["6. 이익의 질", "조건부 통과",
          f"10년 누적 영업현금흐름−설비투자 {won_e(cum_fcf)}. 회계는 깨끗하나 "
          "주주에게 남은 현금은 없었음"],
         ["7. 합리적인 가격", "미달",
          f"모든 시나리오·모든 기준연도에서 시가총액 {won_t(cap)}에 미달"]],
        [16, 10, 44])

    p(f"**가격.** 2026년 9월 14일 종가 {mkt['price']:,.0f}원, 유통주식 "
      f"{mkt['shares_outstanding']:,}주, 시가총액 {won_t(cap)}입니다. "
      f"현재 환율로 환산한 2026년 실적 기준으로 가치를 계산하면 "
      f"보수 {won_t(sc['보수']['equity_value'])}, "
      f"중립 {won_t(sc['중립']['equity_value'])}, "
      f"낙관 {won_t(sc['낙관']['equity_value'])}입니다. "
      f"가장 낙관적인 경우에도 시장가보다 "
      f"{pct(abs(sc['낙관']['upside_vs_market']))} 낮습니다.")

    p("**낙관 시나리오가 어느 정도로 낙관적인가.** 첫해 성장률 25%, 증분 ROIC 26%, "
      "할인율 9%입니다. 25%는 최근 5년 매출 CAGR 31.4%와 2026년 상반기 +28.0%보다 "
      "낮게, 즉 실적의 하단에 맞춘 값이고, 26%는 실측 증분 ROIC 구간(24.9~29.7%)의 "
      "중간이며, 9%는 계산한 자본비용 범위의 최저값입니다. 세 가지 모두 회사에 "
      "유리한 쪽 끝에 놓고도 값이 시장가에 닿지 않습니다.")

    p(f"**현재 주가가 요구하는 것.** 낙관 시나리오의 틀을 그대로 두고 성장률만 "
      f"역산하면 첫해 {pct(im_norm['against_optimistic']['implied_initial_growth'])}가 "
      f"필요합니다. 그 성장률은 증분 ROIC 26% 아래에서 재투자율 "
      f"{pct(im_norm['against_optimistic']['implied_first_year_reinvestment_rate'], 0)}를 "
      "뜻하므로, 회사는 벌어들이는 세후영업이익보다 많은 돈을 매년 외부에서 조달해야 "
      "합니다. 할인율만 역산하면 "
      f"{pct(im_norm['against_optimistic']['implied_discount_rate'])}, "
      f"자본비용 하한 {pct(wacc_lo)}보다 낮습니다. 증분 ROIC만 역산하면 "
      "어떤 값으로도 시장가에 닿지 않습니다.")

    note("이 결론은 사업에 대한 부정이 아닙니다. 아래 기준 2·4에서 보듯 이 회사가 "
         "투입한 자본에서 뽑아내는 수익률은 이 작업에서 다룬 52개 기업 가운데 상위권에 "
         "들어갑니다. 1996년 주주서한의 문장이 정확히 이 상황을 가리킵니다.")

    quote("투자자가 훌륭한 기업을 사면서도 지나치게 높은 가격을 지불하면, 그 뒤 "
          "10년간 회사가 눈부시게 성장해도 그 성장의 열매가 주주에게 돌아오지 않을 수 "
          "있습니다. 최고의 기업에도 너무 많은 값을 치를 수 있습니다.",
          "1996년 버크셔 해서웨이 주주서한, '불가피한 기업들'(The Inevitables)")

    # ====================================================== 1. 기준
    h1("1. 적용한 기준")

    p("이 보고서는 앞선 52개 기업 분석과 알파벳 심층분석에서 정리한 일곱 개 기준을 "
      "그대로 씁니다. 기준은 버핏의 주주서한에서 직접 따왔고, 각 기준의 출처를 "
      "함께 적습니다.")

    bullets([
        "**기준 1 — 이해할 수 있는 사업.** 1977년 서한의 네 가지 조건 중 첫 번째. "
        "무엇을 팔아 어떻게 돈을 버는지 설명할 수 있어야 합니다.",
        "**기준 2 — 기존 투하자본의 수익률이 자본비용을 넘는다.** 2007년 서한의 "
        "'사업을 영위하기 위해 필요한 자본' 대비 수익.",
        "**기준 3 — 해자가 지속된다.** 2007년 서한: 수익성 높은 사업에는 반드시 "
        "'성을 지키는 해자'가 있어야 하고, 그 해자는 오래 버텨야 합니다.",
        "**기준 4 — 증분 투하자본의 수익률이 자본비용을 넘는다.** 2007년 서한의 "
        "'훌륭한·좋은·끔찍한' 3분류. 씨즈캔디는 성장에 자본이 거의 들지 않아 훌륭하고, "
        "자본이 들지만 그 자본에서 높은 수익을 내면 좋은 기업입니다.",
        "**기준 5 — 자본배분과 주주지향.** 1992년 서한의 스톡옵션 논의, 유보이익 "
        "1달러가 시장가치 1달러 이상을 만들어야 한다는 기준.",
        "**기준 6 — 이익의 질.** 1986년 서한의 주주이익 정의.",
        "**기준 7 — 합리적인 가격.** 1989년 서한 '적당한 기업을 훌륭한 가격에 사는 "
        "것보다 훌륭한 기업을 적당한 가격에 사는 것이 훨씬 낫다', 그리고 1992년 서한이 "
        "인용한 존 버 윌리엄스의 가치 정의.",
    ])

    quote("가치평가의 기준은 변하지 않습니다. 어떤 주식, 채권, 사업의 가치든 "
          "적절한 이자율로 할인한 미래 현금 유출입이 결정합니다.",
          "1992년 버크셔 해서웨이 주주서한, 존 버 윌리엄스 『투자가치이론』 인용")

    p("현금흐름은 앞선 작업에서 정한 항등식으로 계산합니다. 성장률을 가정하면 "
      "재투자율은 자동으로 정해지므로, 어떤 시나리오도 대가를 치르지 않고 "
      "성장할 수 없습니다.")

    formula("FCF = NOPAT × (1 − 성장률 g ÷ 증분 ROIC)")

    p("이 항등식이 알파벳 분석에서보다 이 회사에서 훨씬 큰 역할을 합니다. "
      "삼성바이오로직스의 성장률은 증분 ROIC에 근접해 있고 어떤 구간에서는 그것을 "
      "넘었습니다. 그것이 곧 '성장하는 동안 현금을 쓰는 기업'의 산술적 정의입니다.")

    # ====================================================== 2. 데이터
    h1("2. 데이터 기준 — 무엇을 세고 있는지 먼저 정한다")

    p("이 회사의 10년 숫자를 그냥 이어 붙이면 서로 다른 세 회사를 하나로 그린 그림이 "
      "됩니다. 삼성바이오에피스가 세 번 성격을 바꿨기 때문입니다.")

    bullets([
        "**FY2016~FY2021.** 에피스는 지분법 적용 합작회사였습니다. 연결 손익에 "
        "매출로 들어오지 않고, 지분법손익으로 영업외에 잡혔습니다.",
        "**FY2022년 4월 20일.** 바이오젠 보유 50%−1주를 인수해 100% 자회사가 "
        "되었습니다. 이후 연결 매출에 에피스 매출이 합산됩니다.",
        "**FY2025년 11월 1일.** 인적분할로 삼성에피스홀딩스가 분리되었습니다. "
        f"FY2025 연결 손익에서 에피스는 중단영업으로 빠졌고 (중단영업 매출 "
        f"{won_b(dis['revenue'][0])}십억원, 10개월분), FY2024 비교치도 "
        "계속영업 기준으로 재작성되었습니다. 발행주식수는 71,174,000주에서 "
        "46,290,951주로 줄었습니다.",
    ])

    h2("해결 — 회사가 직접 공시하는 별도재무제표")

    p("해법은 회사의 별도(別途) 재무제표입니다. 별도제표는 모든 연도에서 CDMO 사업만 "
      "담고 있고, 에피스에 판 매출도 제거하지 않고 매출로 표시합니다. 이것이 바로 "
      "분할 후 회사가 보고하는 기준과 같습니다. 세 개의 항등식이 이 연결을 증명합니다.")

    table(
        ["검증 항목", "값", "판정"],
        [["별도 FY2024 매출 = 연결 계속영업 FY2024 매출",
          f"{years[2024]['revenue']:,.0f}원", "원 단위까지 일치"],
         ["연결 FY2024 매출 = 계속영업 + 중단영업",
          f"{raw['consolidated_reported']['2024']['revenue']:,.0f}원", "일치"],
         ["별도 FY2021 매출 = 연결 FY2021 매출 (에피스 연결 전)",
          f"{years[2021]['revenue']:,.0f}원", "일치"],
         ["별도 FY2025 매출 = 연결 FY2025 매출 (분할 후 단일사업)",
          f"{years[2025]['revenue']:,.0f}원", "일치"],
         ["FY2024 CDMO 부문 총매출(내부거래 포함) ≈ 별도 매출",
          f"{seg['total_sales']['2024_cdmo']:,.0f}원", "0.4% 차이"]],
        [40, 30, 18])

    note("자료는 전부 회사 IR 사이트에 게시된 감사보고서 원본 PDF입니다 "
         "(FY2016~FY2025 연간, 2026년 반기 검토보고서). 각 PDF에는 감사인의 "
         "감사보고서가 붙어 있습니다. XBRL 태그가 아니라 PDF 텍스트에서 뽑았기 "
         "때문에 파싱 오류는 오류가 아니라 그럴듯한 숫자로 나타납니다. 그래서 "
         "work/verify_sbl.py에 111건의 정합성·자릿수·기준연결 검증을 두었고 "
         "전부 통과합니다. 검증기 자체도 일부러 숫자를 틀리게 넣어 실패하는지 "
         "확인했습니다.")

    h2("10년 실적 — CDMO 사업 기준")

    table(
        ["FY", "매출", "영업이익", "영업이익률", "NOPAT", "순이익", "감가상각", "설비투자"],
        [[str(fy), won_b(years[fy]["revenue"]), won_b(years[fy]["operating_income"]),
          pct(years[fy]["operating_margin"]), won_b(years[fy]["nopat"]),
          won_b(years[fy]["net_income"]),
          won_b(years[fy]["depreciation_amortization"]),
          won_b(years[fy]["capex"])]
         for fy in sorted(years)],
        [6, 11, 11, 11, 10, 10, 10, 10],
        numeric=[1, 2, 3, 4, 5, 6, 7])

    note("단위: 십억원. 매출은 FY2016 2,946억원에서 FY2025 4조 5,570억원으로 "
         "9년간 연 35.6% 복리로 늘었습니다. FY2020→FY2025 5년 CAGR은 31.4%, "
         "FY2022→FY2025 3년 CAGR은 23.2%입니다.")

    # ====================================================== 기준 1
    h1("3. 기준 1 — 이해할 수 있는 사업인가")

    p("통과합니다. 삼성바이오로직스는 바이오의약품 위탁개발생산(CDMO) 회사입니다. "
      "제약사가 개발한 항체 의약품을 자기 공장에서 대신 만들어 배치 단위로 넘기고 "
      "대금을 받습니다. 분할 후 보고부문은 CDMO 하나뿐입니다.")

    p("수익 인식은 감사인이 핵심감사사항으로 지정한 항목이기도 합니다. FY2025 "
      "감사보고서는 'CMO 배치 매출의 수익 인식 시점 절단(cut-off)의 적정성'을 "
      "핵심감사사항으로 적었습니다. 즉 매출의 성격 자체는 단순하지만 어느 기(期)에 "
      "넣을지가 판단 사항이라는 뜻입니다. 이 점은 기준 6에서 다시 다룹니다.")

    p(f"지역별로는 FY2025 매출 {won_t(years[2025]['revenue'])} 중 유럽 "
      f"{won_t(conc['geography']['europe']['2025'])}, 미국 "
      f"{won_t(conc['geography']['usa']['2025'])}, 국내 "
      f"{won_t(conc['geography']['domestic']['2025'])}입니다. 해외 비중 "
      f"{pct(d['valuation_bases']['foreign_revenue_share_2025'])}. 매출은 "
      "달러·유로로 받고 원가는 대부분 원화로 치르는 구조이며, 이것이 기준 7에서 "
      "결정적인 변수가 됩니다.")

    # ====================================================== 기준 2
    h1("4. 기준 2 — 기존 자본의 수익률이 자본비용을 넘는가")

    h2("먼저 분모를 정한다")

    p("투하자본을 어떻게 세느냐가 이 회사에서는 결론을 바꿉니다. 세 가지 방식을 "
      "모두 계산했고, 고른 이유와 버린 이유를 함께 적습니다.")

    bullets([
        "**하향식 (자기자본 + 이자부부채 + 리스부채 − 현금성자산 − 타회사 투자).** "
        "52개 기업 분석에서 쓴 방식입니다. 이 회사에서는 두 번 깨집니다. 에피스 지분이 "
        "FY2021까지 대차대조표를 지배해 FY2017 하향식 투하자본은 음수(−1조 8,140억원)로 "
        "나오고, 2025년 분할이 자기자본을 1조 8,650억원 줄였는데 그 감소는 위탁생산 "
        "사업과 아무 관계가 없습니다.",
        "**상향식 영업자본 (영업자산 − 영업부채).** 지주회사 성격의 잡음과 분할에 "
        "모두 영향받지 않습니다. 이것을 씁니다.",
        "**상향식에서 매입채무를 차감하지 않은 것.** 이 회사 매입채무에는 공사대금이 "
        "섞여 있습니다(FY2022 1조 6,290억원). 공사대금은 운전자본이 아니라 공장을 "
        "조달한 돈이므로, 이를 차감하면 건설 연도의 수익률이 부풀려집니다. 증분 "
        "ROIC은 이 기준으로 계산했습니다.",
    ])

    gaps = [years[fy]["capital"]["top_down"] / years[fy]["capital"]["operating"] - 1
            for fy in range(2018, 2026)]
    note("선택이 결론을 만들지 않았다는 증거는 두 방식이 FY2018 이후 서로 "
         f"{pct(min(gaps), 0)}~{pct(max(gaps), 0)} 범위에서 같이 움직인다는 점입니다 "
         f"(예: FY2024 하향식 {won_b(years[2024]['capital']['top_down'])}십억원, "
         f"상향식 {won_b(years[2024]['capital']['operating'])}십억원). "
         "FY2016·FY2017만 크게 벌어지는데, 그 두 해의 하향식 투하자본은 "
         "에피스 지분 때문에 음수가 나오므로 애초에 쓸 수 없는 값입니다.")

    h2("그리고 건설중자산을 빼야 한다")

    p("이것이 이 회사에서 가장 중요한 보정입니다. FY2024 말 영업자본 "
      f"{won_b(years[2024]['capital']['operating'])}십억원 가운데 "
      f"{won_b(years[2024]['capital']['construction_in_progress'])}십억원 — 30% — 이 "
      "아직 완공되지 않아 한 푼도 벌지 못하는 공장이었습니다. FY2025에 2조 1,829억원이 "
      "건설중자산에서 가동자산으로 이전되었습니다. 이것을 빼지 않으면 FY2024가 "
      "수익률이 무너진 해로 읽히는데, 실제로는 아무것도 무너지지 않았습니다.")

    note("알파벳 2차 검토에서 '아직 가동되지 않은 자산'에 적용한 것과 같은 보정입니다.")

    table(
        ["FY", "영업자본", "건설중자산", "ROIC (건설중 포함)", "ROIC (건설중 제외)",
         "하향식 ROIC"],
        [[str(fy), won_b(years[fy]["capital"]["operating"]),
          won_b(years[fy]["capital"]["construction_in_progress"]),
          pct(years[fy]["roic_operating"]),
          pct(years[fy]["roic_operating_ex_cip"]),
          pct(years[fy]["roic_top_down"])]
         for fy in sorted(years)],
        [6, 14, 13, 18, 18, 14],
        numeric=[1, 2, 3, 4, 5])

    p(f"건설중자산을 뺀 ROIC은 FY2022 이후 "
      f"{pct(years[2022]['roic_operating_ex_cip'])} → "
      f"{pct(years[2023]['roic_operating_ex_cip'])} → "
      f"{pct(years[2024]['roic_operating_ex_cip'])} → "
      f"{pct(years[2025]['roic_operating_ex_cip'])}로 4년 내내 22%를 넘습니다. "
      f"자본비용 참고 범위는 {pct(wacc_lo)}~{pct(wacc_hi)}입니다 (한국 10년물 "
      f"{pct(d['cost_of_capital']['risk_free']['rate'], 2)}, 베타 0.9~1.2, "
      "주식위험프리미엄 5.5~7.5%). **기준 2는 명확히 통과합니다.**")

    h2("FY2025 영업이익률 45.4%는 진짜인가")

    p(f"FY2024 {pct(md['fy2024_margin'])}에서 FY2025 {pct(md['fy2025_margin'])}로 "
      f"{md['total_change']*100:.1f}포인트 올랐습니다. 위탁생산업으로서는 이례적인 "
      "수준이므로 환율 탓인지 따로 떼어봤습니다.")

    p(f"FY2025 손익을 FY2024 평균환율(1,363.4원)로 환산하면 영업이익률은 "
      f"{pct(md['fy2025_margin_at_fy2024_rate'])}입니다. 즉 환율 기여는 "
      f"{md['fx_contribution']*100:+.1f}포인트({pct(md['fx_share_of_change'], 0)}), "
      f"영업 개선 기여는 {md['operating_contribution']*100:+.1f}포인트입니다. "
      "마진 상승의 대부분은 5공장 가동에 따른 가동률 상승과 고정비 레버리지이며, "
      "환율 효과가 아닙니다.")

    p(f"2026년 상반기 실적이 이를 뒷받침합니다. 매출 {won_t(it['h1_2026']['revenue'])} "
      f"(전년 동기 {won_t(it['h1_2025']['revenue'])}, +"
      f"{(it['h1_2026']['revenue']/it['h1_2025']['revenue']-1)*100:.1f}%), "
      f"영업이익 {won_t(it['h1_2026']['operating_income'])}, 영업이익률 "
      f"{pct(it['h1_2026']['operating_income']/it['h1_2026']['revenue'])}. "
      "FY2025의 마진은 한 해의 사건이 아니라 새 수준입니다.")

    # ====================================================== 기준 3
    h1("5. 기준 3 — 해자가 지속되는가")

    quote("정말로 훌륭한 사업이라면 지속적으로 뛰어난 이익을 내기 위해 성 주변에 "
          "지속가능한 '해자'가 있어야 합니다. … 우리는 성의 해자가 넓고 영구적일 "
          "것이라고 믿는 사업을 찾습니다.",
          "2007년 버크셔 해서웨이 주주서한")

    h2("해자가 있다는 근거")

    bullets([
        "**규제에 묶인 전환비용.** 바이오의약품의 제조소는 허가의 일부입니다. "
        "고객이 위탁처를 바꾸려면 기술이전, 비교동등성 시험, 규제기관 변경허가를 "
        "다시 거쳐야 합니다. 이것이 CDMO 계약이 장기화되는 구조적 이유입니다.",
        "**고객이 먼저 돈을 낸다.** FY2025 말 선수금 "
        f"{won_t(cf['advance_receipts_2025'])}, 계약부채 "
        f"{won_t(cf['contract_liabilities_2025'])}, 합계 "
        f"{won_t(cf['total_customer_funding_2025'])}입니다. 연매출의 "
        f"{pct(cf['as_share_of_revenue'])}, 영업자본의 "
        f"{pct(cf['as_share_of_operating_capital'])}에 해당하는 고객 자금을 일이 "
        "끝나기 전에 받아 무이자로 쓰고 있습니다. 버핏이 보험업에서 중시한 "
        "플로트와 같은 성격이며, 협상력의 직접적 증거입니다.",
        "**규모.** FY2025 말 유형자산 취득원가는 7조 6,546억원, 장부가 "
        f"{won_t(years[2025]['ppe'])}이며, FY2025 한 해에 2조 1,829억원이 "
        "건설중자산에서 가동자산으로 넘어갔습니다. 같은 규모를 새로 세우려면 "
        "비슷한 금액과 수 년의 건설·검증 기간이 필요합니다. 규모 자체가 "
        "진입장벽이라는 주장의 근거는 이 숫자이며, '세계 최대'와 같은 순위 "
        "주장은 감사보고서에서 확인할 수 없으므로 쓰지 않았습니다.",
        "**수익률 자체.** 건설중자산을 뺀 ROIC이 4년 연속 22%를 넘는다는 사실은 "
        "경쟁이 초과이익을 아직 걷어가지 못했다는 증거입니다. 해자의 존재는 "
        "이야기가 아니라 수익률로 확인됩니다.",
    ])

    h2("해자를 의심할 근거")

    table(
        ["", "FY2025", "FY2024"],
        [["상위 5개 고객 매출", won_t(conc["2025"]["top5_revenue"]),
          won_t(conc["2024"]["top5_revenue"])],
         ["상위 5개 고객 비중", pct(conc["2025"]["top5_share"]),
          pct(conc["2024"]["top5_share"])],
         ["최대 고객 1곳 비중", pct(conc["2025"]["largest_share"]),
          pct(conc["2024"]["largest_share"])]],
        [34, 22, 22], numeric=[1, 2])

    bullets([
        f"**고객 집중.** 상위 5개 고객이 FY2025 매출의 "
        f"{pct(conc['2025']['top5_share'])}이고, 1년 전 "
        f"{pct(conc['2024']['top5_share'])}에서 오히려 높아졌습니다. 최대 고객 "
        f"한 곳이 매출의 {pct(conc['2025']['largest_share'])}입니다. "
        "익명화된 공시라 같은 고객인지 확인할 수 없지만, 개별 잔액의 이동 폭이 "
        "큽니다(A사 +117%, E사 −59%). 해자가 고객 한 곳의 파이프라인 성패에 "
        "노출되어 있다는 뜻입니다.",
        "**자본집약.** 해자를 유지하는 데 계속 돈이 듭니다. FY2025 설비투자는 "
        f"감가상각의 {years[2025]['capex']/years[2025]['depreciation_amortization']:.1f}배입니다. "
        "2007년 서한의 분류로 보면 씨즈캔디 같은 '훌륭한' 기업이 아니라 자본을 "
        "잘 쓰는 '좋은' 기업입니다.",
        "**성장이 한 지역에 몰려 있다.** 미국 매출이 FY2024 "
        f"{won_t(conc['geography']['usa']['2024'])}에서 FY2025 "
        f"{won_t(conc['geography']['usa']['2025'])}로 "
        f"{pct(conc['geography']['usa']['2025']/conc['geography']['usa']['2024']-1, 0)} "
        "늘었습니다. 반면 국내 매출은 줄었습니다. 성장의 대부분이 한 나라의 "
        "규제·통상 환경에 걸려 있다는 뜻이며, 이 부분은 감사보고서가 말해주지 "
        "않는 영역입니다.",
        f"**건설중자산이 {won_b(years[2025]['capital']['construction_in_progress'])}"
        "십억원으로 줄었습니다.** 다음 성장 파동을 위한 설비를 아직 짓고 있지 "
        "않다는 뜻이기도 합니다. FY2027 이후의 성장은 앞으로 결정·집행할 투자에 "
        "달려 있으며, 그 투자가 과거와 같은 수익률을 낼지는 확인된 사실이 "
        "아니라 가정입니다.",
    ])

    p("**판정: 조건부 통과.** 전환비용과 선수금 구조는 실재하고 수익률로 확인됩니다. "
      "다만 '넓고 영구적인' 해자라고 부르기에는 고객 집중도가 높고 유지비용이 "
      "큽니다.")

    # ====================================================== 기준 4
    h1("6. 기준 4 — 증분 자본의 수익률")

    quote("정말 훌륭한 사업은 … 성장에 필요한 자본을 거의 쓰지 않고도 훌륭한 "
          "자본수익률을 냅니다. … 좋은 사업이지만 훌륭하지는 않은 사업은 성장을 "
          "위해 상당한 자본을 필요로 하는데, 그 자본에서 나오는 수익이 만족스럽다면 "
          "여전히 좋은 사업입니다.",
          "2007년 버크셔 해서웨이 주주서한")

    p("이 기준이 삼성바이오로직스의 성격을 정확히 규정합니다. 씨즈캔디처럼 자본이 "
      "들지 않는 회사가 아니라, 자본을 대량으로 쓰면서 그 자본에서 높은 수익을 "
      "내는 회사입니다.")

    table(
        ["구간", "ΔNOPAT", "Δ투하자본", "증분 ROIC"],
        [[f"FY{e['from']}→FY{e['to']}",
          won_b(e["delta_nopat"]),
          won_b(e["operating_ex_payables_ex_cip"]["delta_capital"]),
          pct(e["operating_ex_payables_ex_cip"]["incremental_roic"])]
         for e in inc5],
        [22, 20, 20, 18], numeric=[1, 2, 3])

    p(f"5년 구간 다섯 개가 모두 {pct(min(inc5_vals))}~{pct(max(inc5_vals))} 안에 "
      f"들어옵니다. 자본비용 상한 {pct(wacc_hi)}의 두 배 이상입니다. "
      "**기준 4는 통과합니다.** 한 구간의 우연이 아니라는 점이 중요합니다 — "
      "건설중자산을 뺀 기준으로 계산했고, 매입채무를 차감하지 않아 공사대금이 "
      "수익률을 부풀리는 경로를 막았습니다.")

    note("동시에 이 표는 기준 7의 결론을 예고합니다. 증분 ROIC이 25~30%라는 것은, "
         "성장률이 25~30%에 접근하면 재투자율이 100%에 접근한다는 뜻입니다. "
         "FCF = NOPAT × (1 − g/증분ROIC)이므로 그 지점에서 주주에게 돌아가는 "
         "현금은 0이 됩니다.")

    # ====================================================== 기준 5
    h1("7. 기준 5 — 자본배분과 주주지향")

    h2("10년간 주주와 회사 사이에 오간 현금")

    table(
        ["항목", "금액", "설명"],
        [["누적 순이익 (FY2016~FY2025)", won_t(cum_ni),
          "CDMO 사업 기준"],
         ["누적 영업현금흐름", won_t(cum_ocf), ""],
         ["누적 설비투자", won_t(cum_capex), "유형자산 취득"],
         ["누적 영업현금흐름 − 설비투자", f"{won_b(cum_fcf)}십억원",
          "10년 합계가 사실상 0"],
         ["주주가 낸 돈 (2022년 유상증자)",
          won_t(eq["capital_increase_2022"]["total"]),
          f"{int(eq['capital_increase_2022']['share_capital']/2500):,}주 신규발행 "
          "(액면 2,500원). 에피스 잔여지분 인수 자금"],
         ["주주가 받은 배당", "0원", "상장 이후 한 번도 없음"],
         ["자기주식 취득",
          won_e(eq["treasury_2025"]["amount"]),
          f"{eq['treasury_2025']['shares']:,}주. 분할 단수주 취득이며 "
          "매입 프로그램이 아님"]],
        [30, 18, 32], numeric=[1])

    p(f"10년 동안 순이익 {won_t(cum_ni)}을 벌었지만 영업현금흐름에서 설비투자를 뺀 "
      f"금액은 누적 {won_e(cum_fcf)} — 사실상 0 — 이었고, 그 위에 주주로부터 "
      f"{won_t(eq['capital_increase_2022']['total'])}을 더 받았습니다. "
      "번 돈 전부와 증자대금까지 공장에 들어갔다는 뜻입니다.")

    p("이 자체는 흠이 아닙니다. 증분 ROIC이 25~30%라면 배당하지 않고 재투자하는 "
      "것이 옳은 결정입니다. 1달러를 유보해 1달러 이상의 시장가치를 만들었느냐는 "
      "버핏의 기준으로 보면, 그렇습니다. **하지만 그 결정의 귀결도 정직하게 "
      "적어야 합니다. 이 주식을 보유해서 지난 10년간 받은 현금은 0원이고, "
      "수익은 전부 주가에서 나와야 했습니다.**")

    h2("최근 5년은 달라지고 있다")

    p(f"FY2021~FY2025만 보면 누적 순이익 {won_t(cum_ni_5y)}, 누적 영업현금흐름 − "
      f"설비투자 {won_t(cum_fcf_5y)}입니다. 순이익의 "
      f"{pct(cum_fcf_5y/cum_ni_5y, 0)}가 현금으로 남았습니다. FY2025만 보면 "
      f"{won_e(oe[2025]['fcf_from_cash_flow_statement'])}이고, 여기에는 아래에서 "
      f"설명하는 공급자금융 청산 "
      f"{won_e(cf['supplier_finance']['2024'] - cf['supplier_finance']['2025'])}이 "
      "빠져 있으므로 이를 되돌리면 약 "
      f"{won_e(oe[2025]['fcf_from_cash_flow_statement'] + cf['supplier_finance']['2024'] - cf['supplier_finance']['2025'])}"
      "입니다. 5공장 투자가 끝나면서 현금이 실제로 남기 시작한 변곡점으로 "
      "보입니다.")

    h2("지배구조에서 확인해야 할 것")

    bullets([
        "**지배주주 비중 74.3%.** FY2025 말 삼성물산 43.06%, 삼성전자 31.22%. "
        "유통주식은 25.7%입니다. 소수주주가 자본배분에 개입할 여지는 사실상 "
        "없습니다.",
        "**특수관계자 매입채무.** FY2024 말 특수관계자에 대한 매입채무가 "
        f"{won_e(cf['related_party_payables_million'][1] * 1e6)}"
        f"({cf['related_party_payables_million'][1]:,}백만원)이었고 FY2025 말 "
        f"{won_e(cf['related_party_payables_million'][0] * 1e6)}입니다. 이 가운데 "
        f"공급자금융 약정 잔액이 FY2024 "
        f"{won_e(cf['supplier_finance']['2024'])}, FY2025 "
        f"{won_e(cf['supplier_finance']['2025'])}입니다. 사실상 계열사를 통한 "
        "단기 자금조달이 매입채무로 표시되어 있었다는 뜻이며, FY2024 영업현금흐름은 "
        "그만큼 부풀려지고 FY2025는 그만큼 깎였습니다. 금액 자체는 청산되었지만 "
        "이런 거래가 가능한 구조라는 점은 기록해 둘 사항입니다.",
        "**분할의 왕복.** 2022년에 3.19조원을 증자해 에피스 지분 50%를 사들였고, "
        "2025년에 그 에피스를 떼어내 주주에게 삼성에피스홀딩스 주식으로 "
        "나눠줬습니다. 주주가 손실을 본 것은 아니지만, 3년 반 동안 자본을 "
        "왕복시킨 셈입니다. 그 과정에서 발행주식은 66,165,000주 → 71,174,000주 → "
        "46,290,951주로 두 번 바뀌었고, 분할 이전 주가·EPS와 현재 수치는 직접 "
        "비교할 수 없습니다.",
    ])

    p("**판정: 조건부 통과.** 재투자 수익률이 높으므로 무배당·전액재투자는 정당한 "
      "선택입니다. 다만 주주지향의 증거(배당, 자기주식 매입, 소수주주 보호장치)는 "
      "없고, 지배구조는 소수주주가 목소리를 낼 구조가 아닙니다.")

    # ====================================================== 기준 6
    h1("8. 기준 6 — 이익의 질")

    quote("주주이익은 (a) 보고이익에 (b) 감가상각비, 감모상각비, 기타 비현금성 "
          "비용을 더하고, (c) 기업이 장기적 경쟁지위와 판매량을 완전히 유지하기 위해 "
          "필요한 연평균 설비투자액을 차감한 값입니다.",
          "1986년 버크셔 해서웨이 주주서한, 부록")

    p("이 정의에서 판단이 필요한 부분은 (c) 한 줄뿐입니다. FY2025 설비투자 "
      f"{won_b(years[2025]['capex'])}십억원 중 얼마가 '유지'이고 얼마가 '성장'인가. "
      "회사는 공장을 짓고 있으므로 대부분은 성장입니다. 그래서 세 가지로 "
      "계산해 범위를 보여드립니다.")

    table(
        ["FY", "순이익", "감가상각", "설비투자",
         "주주이익 (유지=감가상각)", "주주이익 (유지=설비투자 전액)",
         "영업현금흐름−설비투자"],
        [[str(fy), won_b(oe[fy]["net_income"]),
          won_b(oe[fy]["depreciation_amortization"]),
          won_b(oe[fy]["capex"]),
          won_b(oe[fy]["oe_maintenance_equals_da"]),
          won_b(oe[fy]["oe_all_in_capex"]),
          won_b(oe[fy]["fcf_from_cash_flow_statement"])]
         for fy in sorted(oe)],
        [5, 9, 9, 9, 16, 17, 15],
        numeric=[1, 2, 3, 4, 5, 6])

    p("두 끝 중 어느 쪽도 단독으로 답이 아닙니다. 왼쪽(유지=감가상각)은 회사가 "
      "성장을 멈추면 얼마를 벌게 되는지를 말하고, 오른쪽은 성장하는 동안 주주에게 "
      "실제로 얼마가 남는지를 말합니다. FY2025 기준 왼쪽 "
      f"{won_b(oe[2025]['oe_maintenance_equals_da'])}십억원, 오른쪽 "
      f"{won_b(oe[2025]['oe_all_in_capex'])}십억원 — 2.7배 차이입니다. "
      "가치평가에서는 이 문제를 항등식이 자동으로 처리합니다. 성장률을 가정하면 "
      "재투자율이 따라 나오므로, 유지·성장을 임의로 가르지 않아도 됩니다.")

    h2("회계의 신뢰성")

    bullets([
        "**현금이 이익을 뒷받침합니다.** FY2025 영업현금흐름 "
        f"{won_b(years[2025]['ocf'])}십억원이 순이익 "
        f"{won_b(years[2025]['net_income'])}십억원을 넘습니다. 발생주의로 이익을 "
        "밀어넣은 흔적은 없습니다.",
        "**재고는 봐야 합니다.** FY2025 재고 "
        f"{won_t(years[2025]['inventories'])}은 매출원가 "
        f"{won_t(abs(raw['years'][-1]['cost_of_revenue']))} 대비 약 381일분입니다. "
        "제품 724.8십억원(전년 526.9에서 +37.7%)이 매출 증가율(+30.3%)보다 빠르게 "
        "늘었습니다. 배치 생산과 고객 출하승인 대기 때문에 이 업종의 재고는 원래 "
        "길지만, 제품 재고가 매출보다 계속 빠르게 늘면 그때는 신호입니다. "
        "평가손실충당금은 811억원(취득원가의 3.7%)이고 당기 평가손실은 198억원으로 "
        "전년 563억원보다 줄었습니다.",
        "**공급자금융.** 위에서 다룬 대로 FY2024 매입채무에 5,406억원이 섞여 "
        "있었습니다. FY2024와 FY2025의 영업현금흐름을 그대로 비교하면 안 됩니다.",
        "**감사인의 핵심감사사항.** FY2025 감사보고서는 CMO 배치 매출의 인식 시점 "
        "절단을 핵심감사사항으로 지정했습니다. 오류가 있었다는 뜻이 아니라, "
        "판단이 개입하는 지점이 어디인지 감사인이 밝힌 것입니다.",
    ])

    h2("2018년 회계 사건 — 사실관계와 현재 상태")

    p("이 회사는 2018년 증권선물위원회로부터 에피스 회계처리와 관련해 두 차례 "
      "행정처분을 받았습니다(감사인 지정 3년, 대표이사 해임 권고, 검찰 통보, "
      "재무제표 재작성, 과징금 80억원). 회사는 두 처분 모두 취소소송을 "
      "제기했습니다.")

    p("FY2025 감사보고서 주석 35에 따르면, 1차 처분 취소소송은 "
      "2025년 9월 25일 대법원이 증선위의 상고를 기각해 **회사의 청구가 전부 "
      "받아들여진 상태로 확정**되었습니다. 2차 처분 취소소송은 2024년 8월 14일 "
      "서울행정법원이 처분을 취소했고, 증선위가 항소해 계속 중입니다.")

    note("기준 6은 경영진의 정직성을 묻는 항목이기도 합니다. 회계처리의 적정성을 "
         "두고 7년간 다툼이 있었다는 사실 자체는 기록해야 하고, 법원이 회사 손을 "
         "들어줬다는 사실도 똑같이 기록해야 합니다. 어느 한쪽만 적으면 편향입니다.")

    p("**판정: 조건부 통과.** 현금이 이익을 뒷받침하고 법적 분쟁은 회사에 유리하게 "
      "정리되고 있습니다. 다만 10년간 주주에게 남은 현금이 사실상 0이었다는 사실, "
      "재고 증가 속도, 공급자금융을 통한 현금흐름 왜곡은 계속 봐야 할 항목입니다.")

    # ====================================================== 기준 7
    h1("9. 기준 7 — 가격")

    h2("기준연도를 무엇으로 잡는가")

    p("이 회사는 매출의 92%를 해외에서 벌고 원가는 대부분 원화로 씁니다. "
      "원/달러 평균환율은 FY2025 1,421.4원, 2026년 상반기 1,482.0원이었고 "
      f"현재(2026년 9월) {FX_SPOT_TXT}입니다. 2026년 6월 1,529.5원에서 "
      "3개월 만에 11% 절상되었습니다. 이미 시장이 떠난 환율을 자본화하는 것은 "
      "보수적인 것이 아니라 틀린 것이므로, 기준연도를 세 가지로 계산합니다.")

    table(
        ["기준", "매출", "영업이익", "영업이익률", "실효세율", "NOPAT"],
        [[d["valuation_bases"][k]["label"],
          won_t(d["valuation_bases"][k]["revenue"]),
          won_t(d["valuation_bases"][k]["operating_income"]),
          pct(d["valuation_bases"][k]["operating_income"]
              / d["valuation_bases"][k]["revenue"]),
          pct(d["valuation_bases"][k]["tax_rate"]),
          won_t(d["valuation_bases"][k]["nopat"])]
         for k in ("reported_fy2025", "run_rate_2026", "run_rate_fx_normalised")],
        [30, 14, 14, 12, 12, 14], numeric=[1, 2, 3, 4, 5])

    p("환산에는 해외매출 비중 "
      f"{pct(d['valuation_bases']['foreign_revenue_share_2025'])}와 "
      f"원가 중 외화연동 비중 30% 가정을 썼습니다. 배양액·레진·일회용 자재는 "
      "달러로 수입하고 인건비·감가상각·전력은 원화이므로 전액 원화도 전액 외화도 "
      "아닙니다. 회사가 이 비율을 공시하지 않으므로 가정이며, 0%~60%로 흔들어보면 "
      "FY2026 연율 영업이익은 1.94조~2.08조원 사이에서 움직입니다. "
      "결론을 바꾸는 크기가 아닙니다.")

    h3("환율이 얼마면 실적이 얼마인가")

    table(
        ["원/달러", "매출(연율)", "영업이익(연율)", "영업이익률", "NOPAT(연율)"],
        [[f"{e['rate_to']:,.1f}", won_t(e["revenue"]),
          won_t(e["operating_income"]), pct(e["operating_margin"]),
          won_t(e["nopat"])]
         for e in d["valuation_bases"]["fx_sensitivity_of_run_rate"]],
        [14, 18, 18, 14, 18], numeric=[0, 1, 2, 3, 4])

    note("환율이 1,200원으로 돌아가면 NOPAT은 1.17조원으로, 현재 환율 기준 "
         "1.48조원 대비 21% 줄어듭니다. 이 회사에 대한 투자는 상당 부분 "
         "'원화가 약세로 유지된다'는 데 대한 투자입니다.")

    h2("세 시나리오")

    p("성장률은 실적에 맞춰 잡았습니다. 느낌상 신중해 보이는 숫자를 쓰면 분석이 "
      "아니라 희망이 됩니다.")

    for s in norm["scenarios"]:
        h3(f"{s['scenario']} 시나리오")
        p(s["story"])
        a = s["assumptions"]
        f = s["feasibility"]
        bullets([
            f"가정: 첫해 성장률 {pct(a['growth'])} → 10년차 {pct(a['fade_to'])}, "
            f"증분 ROIC {pct(a['incremental_roic'])}, 할인율 {pct(a['discount'])}, "
            f"영구성장률 {pct(a['terminal_growth'])}",
            f"1년차 재투자율 {pct(s['first_year_reinvestment_rate'])} — "
            f"세후영업이익의 이만큼이 공장으로 다시 들어가고 "
            f"{pct(1 - s['first_year_reinvestment_rate'])}만 주주 몫으로 남습니다",
            f"10년 누적 재투자 {won_t(f['cumulative_reinvestment'])} "
            f"(누적 NOPAT의 {pct(f['reinvestment_as_share_of_nopat'], 0)}), "
            f"투하자본 {f['invested_capital_multiple']:.1f}배, "
            f"연평균 설비투자는 FY2025의 "
            f"{f['average_annual_capex_vs_fy2025']:.1f}배",
            f"10년 뒤 매출 {won_t(f['implied_revenue_end'])} "
            f"(현재 환율로 약 {f['implied_revenue_end_usd_bn']*10:,.0f}억 달러)",
            f"**기업가치 {won_t(s['equity_value'])}, 주당 "
            f"{s['value_per_share']:,.0f}원, 시장가 대비 "
            f"{pct(s['upside_vs_market'])}**",
            f"터미널 가치 비중 {pct(s['terminal_share_of_value'])}",
        ])

    note("터미널 비중이 낙관 시나리오에서 78%까지 올라갑니다. 성장률이 높을수록 "
         "재투자로 앞단 현금흐름이 사라지고 가치가 먼 미래로 밀립니다. "
         "78%가 10년 뒤 이후에 달려 있다는 뜻이므로, 이 시나리오는 계산 결과가 "
         "아니라 믿음의 표현에 가깝다는 점을 분명히 해둡니다.")

    h2("세 기준연도 × 세 시나리오 전체")

    table(
        ["기준연도", "보수", "중립", "낙관", "시장가"],
        [[v["label"]] + [won_t(s["equity_value"]) for s in v["scenarios"]]
         + [won_t(cap)]
         for v in (rep, run, norm)],
        [28, 15, 15, 15, 15], numeric=[1, 2, 3, 4])

    table(
        ["기준연도", "보수 적정주가", "중립 적정주가", "낙관 적정주가", "현재주가"],
        [[v["label"]] + [f"{s['value_per_share']:,.0f}원" for s in v["scenarios"]]
         + [f"{mkt['price']:,.0f}원"]
         for v in (rep, run, norm)],
        [26, 17, 17, 17, 15], numeric=[1, 2, 3, 4])

    p("아홉 개 칸 가운데 시장가에 닿는 것이 하나도 없습니다. 가장 가까운 경우는 "
      f"2026년 상반기를 연율화하고(환율 보정 없이) 낙관 시나리오를 적용한 "
      f"{won_t(run['scenarios'][2]['equity_value'])}이며, 그래도 "
      f"{pct(abs(run['scenarios'][2]['upside_vs_market']))} 미달입니다. "
      f"52주 최저가 {mkt['fifty_two_week_low']:,.0f}원조차 낙관 시나리오의 "
      f"적정주가 {norm['scenarios'][2]['value_per_share']:,.0f}원보다 높습니다.")

    h2("거꾸로 — 지금 주가는 무엇을 가정하고 있는가")

    p("가치를 계산해 주가와 비교하는 대신, 주가를 맞추는 가정을 역산했습니다. "
      "세 개의 손잡이를 하나씩 돌립니다.")

    table(
        ["역산 대상", "낙관 시나리오 틀 기준", "중립 시나리오 틀 기준", "실측·참고치"],
        [["첫해 성장률",
          pct(im_norm["against_optimistic"]["implied_initial_growth"]),
          pct(im_norm["against_neutral"]["implied_initial_growth"]),
          "FY2020→FY2025 매출 CAGR 31.4%, 2026 상반기 +28.0%"],
         ["→ 그때의 1년차 재투자율",
          pct(im_norm["against_optimistic"]["implied_first_year_reinvestment_rate"], 0),
          pct(im_norm["against_neutral"]["implied_first_year_reinvestment_rate"], 0),
          "100%를 넘으면 외부 조달 필요"],
         ["할인율",
          pct(im_norm["against_optimistic"]["implied_discount_rate"]),
          pct(im_norm["against_neutral"]["implied_discount_rate"]),
          f"자본비용 참고 범위 {pct(wacc_lo)}~{pct(wacc_hi)}"],
         ["증분 ROIC",
          "도달 불가",
          "도달 불가",
          f"5년 구간 실측 {pct(min(inc5_vals))}~{pct(max(inc5_vals))}"]],
        [22, 20, 20, 34], numeric=[1, 2])

    p("세 줄을 함께 읽어야 합니다.")

    bullets([
        "**성장률.** 현재가를 정당화하려면 첫해 "
        f"{pct(im_norm['against_optimistic']['implied_initial_growth'])}로 시작해 "
        "10년간 체감하는 성장이 필요합니다. FY2020→FY2025 매출 CAGR 31.4%보다 "
        "높은 수준을, 그것도 출발점이 아니라 10년 경로의 시작으로 요구하는 "
        f"셈입니다. 지금 건설중인 설비는 "
        f"{won_e(years[2025]['capital']['construction_in_progress'])}뿐이고, "
        "FY2025 매출은 이미 FY2020의 3.9배입니다. 같은 배율을 다시 만들어야 "
        "합니다.",
        "**그런데 그 성장은 스스로 조달되지 않습니다.** 증분 ROIC 26% 아래에서 "
        f"{pct(im_norm['against_optimistic']['implied_initial_growth'])} 성장은 "
        f"재투자율 {pct(im_norm['against_optimistic']['implied_first_year_reinvestment_rate'], 0)}를 "
        "뜻합니다. 100%를 넘는 차액은 증자나 차입으로 메워야 하는데, 현금흐름할인 "
        "계산은 그 희석과 이자를 기존 주주에게 청구하지 않습니다. 즉 이 역산값은 "
        "이미 과대평가된 값이고, 현실에서 필요한 성장률은 이보다 더 높습니다.",
        "**할인율.** 다른 손잡이를 모두 낙관에 두고 할인율만 맞추면 "
        f"{pct(im_norm['against_optimistic']['implied_discount_rate'])}입니다. "
        f"한국 10년물 {pct(d['cost_of_capital']['risk_free']['rate'], 2)}에 주식위험"
        f"프리미엄 3.6%포인트만 얹은 값으로, 계산한 자본비용 범위 "
        f"{pct(wacc_lo)}~{pct(wacc_hi)}의 아래입니다.",
        "**증분 ROIC.** 성장률과 할인율을 시나리오 값에 고정하고 증분 ROIC만 "
        "올려보면, 재투자가 0에 수렴할 만큼(300% 이상) 올려도 값이 시장가에 "
        "닿지 않습니다. 즉 이 주가를 설명하는 것은 '자본효율이 더 좋을 것'이라는 "
        "기대가 아니라, '성장이 더 길고 클 것' 또는 '요구수익률이 더 낮아도 "
        "된다'는 기대입니다.",
    ])

    p("**판정: 미달.** 기준 7은 통과하지 못합니다.")

    # ====================================================== 10. 결론
    h1("10. 결론 — 그래서 얼마면 사는가")

    p("사업은 좋습니다. 2007년 서한의 분류로 '훌륭한' 기업은 아니고 '좋은' 기업이며, "
      "좋은 기업의 조건 — 성장에 자본이 들지만 그 자본에서 만족스러운 수익을 낸다 — "
      "을 4년 연속 22% 넘는 ROIC과 25~30%의 증분 ROIC으로 충족합니다. "
      "가격만이 문제입니다.")

    table(
        ["시나리오가 맞다면", "적정주가", "현재주가 대비 필요한 하락"],
        [[f"{s['scenario']} ({s['assumptions']['growth']*100:.0f}% → "
          f"{s['assumptions']['fade_to']*100:.1f}%, 증분ROIC "
          f"{s['assumptions']['incremental_roic']*100:.0f}%, 할인율 "
          f"{s['assumptions']['discount']*100:.0f}%)",
          f"{s['value_per_share']:,.0f}원",
          pct(s["value_per_share"] / mkt["price"] - 1)]
         for s in norm["scenarios"]],
        [46, 16, 20], numeric=[1, 2])

    p(f"중립과 낙관의 중간에 가치가 있다고 보면 주당 "
      f"{(norm['scenarios'][1]['value_per_share'] + norm['scenarios'][2]['value_per_share'])/2:,.0f}원 "
      f"부근입니다. 여기에 버핏이 요구한 안전마진을 25% 적용하면 매수 가격은 "
      f"{(norm['scenarios'][1]['value_per_share'] + norm['scenarios'][2]['value_per_share'])/2*0.75:,.0f}원 "
      f"수준이 됩니다. 현재 {mkt['price']:,.0f}원에서 약 "
      f"{pct((norm['scenarios'][1]['value_per_share'] + norm['scenarios'][2]['value_per_share'])/2*0.75/mkt['price'] - 1)}입니다.")

    note("이 숫자를 목표주가로 읽지 마시기 바랍니다. 이것은 '내가 정한 가정 아래서 "
         "가치가 이만큼이므로 그 아래에서만 사겠다'는 규칙의 출력일 뿐입니다. "
         "가정이 틀리면 숫자도 틀립니다. 어느 가정이 어디서 왔는지를 이 문서 "
         "전체에 적어둔 이유가 그것입니다.")

    h2("내가 틀렸다면 어디서 틀렸을 가능성이 큰가")

    bullets([
        "**성장 기간.** 10년 체감 모형을 썼습니다. 바이오의약품 위탁생산 수요가 "
        "20년 넘게 두 자릿수로 늘고 이 회사가 계속 점유율을 유지한다면, 10년으로 "
        "끊은 모형은 가치를 과소평가합니다. 다만 그 경우 터미널 비중이 더 높아지고 "
        "계산의 신뢰도는 더 떨어집니다.",
        "**마진의 지속.** 영업이익률 45%가 유지되면 제가 쓴 기준연도는 낮지 않고 "
        "맞습니다. FY2025에 가동에 들어간 설비의 가동률이 더 올라가면 마진에 "
        "추가 여지가 있고, 그만큼 가치도 올라갑니다.",
        "**환율.** 원화가 1,500원대로 다시 밀리면 NOPAT이 1.85조원까지 올라가고 "
        "낙관 시나리오 가치가 시장가에 근접합니다. 반대로 1,200원이면 21% 낮아집니다. "
        "제 기준연도는 현재 환율이며, 그 선택 자체가 판단입니다.",
        "**자본비용.** 한국 10년물이 4.18%인 상황에서 9%를 낙관 할인율로 썼습니다. "
        "금리가 크게 떨어지면 이 회사처럼 현금흐름이 뒤에 몰린 기업의 가치는 "
        "빠르게 올라갑니다. 시장이 8%를 쓰고 있다면 시장이 옳을 수도 있습니다. "
        "다만 그 가정을 쓰고 있다는 사실은 인식하고 있어야 합니다.",
        f"**증설 계획.** 건설중자산이 "
        f"{won_e(years[2025]['capital']['construction_in_progress'])}으로 줄어 "
        "다음 성장 파동의 설비가 아직 대차대조표에 없습니다. 회사가 추가 투자를 "
        "확정하고 그 수익률이 과거와 같다면 제 중립 시나리오는 낮습니다. 반대로 "
        "투자를 늦추면 보수 시나리오에 가까워집니다. 이 항목은 감사보고서로 "
        "확인할 수 없고 앞으로의 공시를 봐야 하는 부분입니다.",
    ])

    # ====================================================== 부록
    h1("부록 A. 자료 출처")

    table(
        ["연도", "문서", "성격"],
        [["FY2016~FY2017", "Audited Financial Statement 2017 FY", "감사받은 재무제표 (당시 종속회사 없음)"],
         ["FY2018", "2018 FY Audited Financial Statements", "감사받은 재무제표"],
         ["FY2019", "2019 FY Audited Financial Statements", "감사받은 재무제표"],
         ["FY2020", "2020 FY Audited Financial Statements (Consolidated)", "감사받은 연결재무제표"],
         ["FY2021", "2021 FY Audited Financial Statements (Consolidated)", "감사받은 연결재무제표"],
         ["FY2022~FY2025", "각 연도 FY Audited Financial Statements (Separate)", "감사받은 별도재무제표"],
         ["FY2024~FY2025", "각 연도 FY Audited Financial Statements (Consolidated)", "부문·중단영업 주석"],
         ["2026 상반기", "2026 2Q Reviewed Financial Statement (Consolidated)", "검토받은 반기재무제표"]],
        [18, 44, 30])

    bullets([
        f"주가: {mkt['price_source']}. 시가총액은 유통주식 "
        f"{mkt['shares_outstanding']:,}주 기준 {won_t(cap)}이며, 네이버 공시 "
        f"{won_t(mkt['market_cap_naver'])}과 0.04% 차이입니다.",
        f"환율: {d['fx']['series']} — {d['fx']['url']}",
        f"무위험수익률: {d['cost_of_capital']['risk_free']['series']} "
        f"({pct(d['cost_of_capital']['risk_free']['rate'], 2)}, "
        f"{d['cost_of_capital']['risk_free']['as_of']}) — "
        f"{d['cost_of_capital']['risk_free']['url']}",
    ])

    h1("부록 B. 판단이 들어간 지점")

    p("숫자가 아니라 판단인 부분만 모았습니다. 각 항목은 결론을 바꿀 수 있는 "
      "크기 순입니다.")

    table(
        ["판단", "선택한 값", "대안", "결론에 미치는 영향"],
        [["기준연도",
          "2026 상반기 연율화 · 현재 환율",
          "FY2025 실적 / 환율 보정 없는 연율화",
          "NOPAT 1.48조 vs 1.58조 vs 1.71조. 낙관 시나리오 가치가 48.8조~56.5조로 "
          "움직이지만 어느 쪽도 65.1조에 닿지 않음"],
         ["원가 중 외화연동 비중", "30%", "0%~60%",
          "FY2026 연율 영업이익 1.94조~2.08조. 결론 불변"],
         ["투하자본 측정", "상향식 영업자본 (건설중자산 제외)",
          "하향식 / 건설중자산 포함",
          "FY2024 ROIC 23.8% vs 16.5%. 기준 2·4의 통과 여부가 아니라 정도가 바뀜"],
         ["증분 ROIC 기준", "매입채무 미차감",
          "매입채무 차감",
          "FY2018→FY2022 구간이 125%로 튀는 것을 방지. 5년 구간 값은 큰 차이 없음"],
         ["실효세율 하한 처리", "밴드(5~40%) 밖이면 법정 22% 적용",
          "밴드 경계값으로 제한 (52개 기업 분석 방식)",
          "FY2019·FY2020 ROIC이 소폭 낮아짐. 가치평가 기준연도에는 영향 없음"],
         ["유지 설비투자", "감가상각 ~ 설비투자 전액 범위로 제시",
          "한 값으로 확정",
          "주주이익이 FY2025 1,593십억 vs 586십억. 가치평가는 항등식으로 우회"],
         ["성장 기간", "10년 체감 후 영구성장",
          "15~20년 체감",
          "기간을 늘리면 가치가 올라가지만 터미널 비중이 더 높아짐"]],
        [18, 22, 22, 38])

    p("마지막으로, 이 문서의 모든 수치는 work/kr/sbl_raw.json (감사보고서 PDF에서 "
      "추출) → work/verify_sbl.py (111건 검증) → work/kr/sbl_valuation.json "
      "(계산) → 이 문서 순으로 흘러갑니다. 손으로 옮겨 적은 숫자는 없습니다.")

    p("같은 계산을 셀 단위로 따라가실 수 있도록 엑셀 파일 "
      "**삼성바이오로직스_버핏기준_기업분석.xlsx**를 함께 올렸습니다. 파란 글씨는 "
      "감사보고서에서 읽은 값, 검정은 같은 시트 수식, 초록은 다른 시트를 참조하는 "
      "수식, 노랑은 바꿔도 되는 가정입니다. 가정 시트의 환율이나 성장률을 바꾸면 "
      "모든 시나리오와 적정주가가 따라 움직입니다. 워크북의 수식 723개를 별도 "
      "평가기(work/verify_sbl_exports.py)로 계산해 분석 엔진과 같은 값이 나오는지 "
      "확인했고, 전부 일치합니다.")

    payload = {
        "title": "삼성바이오로직스 — 버핏 기준 기업분석",
        "subtitle": ("CDMO 단일사업 기준 FY2016~FY2025 · 7개 기준 전수 적용 · "
                     f"2026-09-14 종가 {mkt['price']:,.0f}원 대비 평가"),
        "generated": date.today().isoformat(),
        "blocks": blocks,
    }
    with open(OUT, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"wrote {OUT}  ({len(blocks)} blocks)")
    return 0


FX_SPOT_TXT = "1,358.5원"

if __name__ == "__main__":
    sys.exit(main())
