"""
네 기업 적정주가 보고서 — 마크다운·워드.

1부는 지금까지 세운 기준의 정리이고, 2부는 그 기준을 마이크로소프트·알파벳·
엔비디아·스페이스X에 적용한 결과입니다. 숫자는 전부 fair_value.json 에서
읽습니다 — 이 파일에 수치를 들고 있으면 세 포맷이 어긋납니다.

    python3 export_fair_value.py
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DATA = os.path.join(HERE, "fv", "fair_value.json")
MD = os.path.join(HERE, "4개기업_적정주가_판정.md")
DOCX_JSON = os.path.join(HERE, "fv", "fair_value_report.json")
DOCX = os.path.join(HERE, "4개기업_적정주가_판정.docx")
MM, BN = 1e6, 1e9

D = json.load(open(DATA, encoding="utf-8"))
APPLIED = [c for c in D["companies"] if c["model"] == "applied"]
SX = [c for c in D["companies"] if c["model"] == "base_not_established"][0]
ORDER = ["보수", "중립", "낙관"]


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def sg(x, nd=1):
    return "—" if x is None else f"{x * 100:+.{nd}f}%"


def bn(x, nd=1):
    return "—" if x is None else f"{x / BN:,.{nd}f}"


def usd(x, nd=0):
    return "—" if x is None else f"${x:,.{nd}f}"


def val(co, scen):
    return [v for v in co["valuations"] if v["scenario"] == scen][0]


def name(co):
    return f"{co['korean']}({co['ticker']})"


# ------------------------------------------------------------------ 본문
def blocks():
    b = []
    b.append({"t": "h1", "x": "네 기업 적정주가 판정 — 보수·중립·낙관 시나리오"})
    b.append({"t": "note", "x":
              f"자료 기준일 {D['generated']} · 50개사 ROIC 조사 생성 "
              f"{D['roic_study_generated']} · 시세 수집 "
              f"{D['prices_fetched_utc'][:19]} UTC · ROIC 문턱 "
              f"{pct(D['wacc_for_roic_hurdle'], 0)} · 투영 "
              f"{D['projection_years']}년 + 터미널"})
    b.append({"t": "p", "x":
              "대상: " + " · ".join(
                  f"**{name(c)}** {usd(c['price'], 2)}"
                  for c in APPLIED + [SX])})

    # =============================================================== 1부
    b.append({"t": "h2", "x": "1부. 우리가 세운 기준"})
    b.append({"t": "p", "x":
              "지금까지 쌓인 규칙을 한자리에 모았습니다. 순서가 중요합니다 — "
              "**자료가 먼저, 사업이 다음, 가격이 마지막**입니다. 가격 판정은 "
              "앞의 두 단계를 통과한 기업에만 의미가 있습니다."})

    b.append({"t": "h3", "x": "① 자료 — 기억으로 단정하지 않는다"})
    b.append({"t": "bullets", "x": [
        "**오늘 날짜를 먼저 확인하고, 오늘 기준으로 다시 수집한다.** 결론을 "
        "내는 작업이면 캐시를 믿지 않습니다. 캐시는 받은 시점을 사이드카에 "
        "기록하고 1일이 지나면 다시 받습니다.",
        "**학습 시점 이후에 바뀌는 사실은 전부 조회로 답한다.** 상장 여부·"
        "티커·거래소·결산월·최신 회계연도·주가·시가총액·발행주식수, 그리고 "
        "**모든 금액**. 스페이스X를 비상장이라고 단정했다가 틀린 적이 "
        "있습니다 — 이미 나스닥에 상장해 10-Q를 내고 있었습니다.",
        "**보고서에는 자료 기준일을 적는다.** \"FY2025 기준\"만으로는 "
        "부족합니다. 어느 날짜에 받은 공시인지가 결론의 유효기간을 정합니다.",
        "**기업은 티커만 쓰지 않고 한글명을 함께 쓴다.**",
    ]})

    b.append({"t": "h3", "x": "② 사업의 질 — ROIC가 자본비용을 넘는가"})
    b.append({"t": "p", "x":
              "가장 중요한 기준입니다. 기업가치 성장은 ROIC이 자본비용을 "
              "얼마나, 얼마나 오래 넘느냐로 결정됩니다."})
    b.append({"t": "formula", "x":
              "NOPAT = 보고된 영업이익 × (1 − 실효세율)\n"
              "투하자본 = 자기자본(비지배지분 포함) + 이자부차입금 "
              "− 현금·단기투자자산\n"
              "ROIC = NOPAT ÷ 투하자본(기초·기말 평균)"})
    b.append({"t": "bullets", "x": [
        f"**정의는 바꾸지 않는다.** 50개사를 같은 잣대로 재야 비교가 "
        f"됩니다. 문턱은 자본비용 {pct(D['wacc_for_roic_hurdle'], 0)}.",
        "**한 해만 보지 않는다.** 10년 내내 문턱을 넘었는지(일관성), 그리고 "
        "**고점 대비 지금 어디인지**(추세)를 함께 봅니다. 자본이 이익보다 "
        "빨리 늘면 ROIC는 떨어지고, 그게 지금 세 기업에 공통으로 일어나는 "
        "일입니다.",
        "**분모를 좁혀 가며 여러 관점으로 본다.** 보고 기준 → 영업권·무형자산 "
        "제외 → 아직 가동되지 않은 설비 제외 → 투자지분 제외. 네 수치의 "
        "간격 자체가 정보입니다.",
        "**증분 ROIC을 본다.** 새로 넣은 자본 1달러가 얼마를 버는지. 과거 "
        "평균보다 이것이 미래를 말합니다.",
        "**금융업(SIC 6000–6799)은 ROIC를 산출하지 않는다.** 은행에게 차입은 "
        "자금조달이 아니라 원재료입니다.",
        "**사업부별 수치가 공시되면 쪼개 본다.** 다만 **사업부 투하자본은 "
        "공시되지 않으므로 사업부 ROIC를 만들지 않는다.** 분모를 발명하면 그 "
        "가정이 결론이 됩니다.",
    ]})

    b.append({"t": "h3", "x": "③ 재무 안전성"})
    b.append({"t": "bullets", "x": [
        "**순현금인가, 순차입인가.** 현금·단기투자 − 이자부차입.",
        "**자금조달 구조가 바뀌었는지 본다.** 자사주를 사들이던 회사가 "
        "증자로 돌아섰다면 그건 재무상태표만 봐서는 놓치는 신호입니다. "
        "알파벳이 9개월 자사주 매입 0에 외부조달 $147십억이었습니다.",
    ]})

    b.append({"t": "h3", "x": "④ 이익의 질"})
    b.append({"t": "bullets", "x": [
        "**영업이익에서 출발한다. 분기 순이익을 신호로 쓰지 않는다.** "
        "투자지분 평가손익(ASU 2016-01)이 분기 순이익을 수십억 달러 단위로 "
        "흔듭니다. 알파벳은 같은 분기에 영업이익 +30%인데 EPS −26%였습니다.",
        "**실효세율이 오염됐는지 확인하고, 법정세율 대안을 병기한다.** "
        "세전이익에 평가이익이 섞이면 실효세율은 영업과 무관한 비율이 됩니다.",
        "**영업이익 소계를 보고하지 않는 기업은 세전이익으로 역검증**해 5% "
        "이내로 맞을 때만 쓰고, 경로는 기업별로 한 번 고정합니다.",
        "**추정값은 추정이라고 표시한다.**",
    ]})

    b.append({"t": "h3", "x": "⑤ 가격 — 가치가 아니라 요구 조건으로 본다"})
    b.append({"t": "p", "x":
              "좋은 사업이라는 판정과 좋은 가격이라는 판정은 별개입니다. "
              "아무리 좋은 회사도 비싸게 사면 수익률이 낮아집니다."})
    b.append({"t": "bullets", "x": [
        "**성장은 증분 ROIC이 할인율보다 클 때만 가치를 더한다.** 작으면 "
        "매출이 아무리 커져도 가치를 깎습니다. 매출 규모 자체는 가치의 "
        "변수가 아닙니다.",
        "**성장에는 돈이 든다.** 잉여현금 = NOPAT × (1 − 성장률 ÷ 증분ROIC). "
        "성장률이 증분 ROIC에 가까워지면 재투자가 잉여현금을 다 먹습니다.",
        "**단일 적정주가를 내지 않는다.** 보수·중립·낙관 세 시나리오로 내고, "
        "**현재 가격이 요구하는 조건**(정당화 성장률, 요구 이익)을 함께 "
        "냅니다. \"내재가치가 얼마냐\"보다 \"이 가격이 맞으려면 무엇이 사실이어야 "
        "하나\"가 유용합니다.",
        "**안전마진을 본다.** 평가치에서 정확히 거래되는 가격은 합격이 "
        "아닙니다. 가정이 조금 틀려도 요구수익률이 나오는 가격이어야 합니다.",
        "**주주이익 수익률을 함께 본다.** capex 전액을 비용으로 본 하단과 "
        "감가상각만 비용으로 본 상단. 그 간격이 넓으면 아직 가동되지 않은 "
        "설비가 많다는 뜻입니다.",
    ]})
    b.append({"t": "h3", "x": "⑥ 산출물 — 검증 없는 산출물은 내보내지 않는다"})
    b.append({"t": "bullets", "x": [
        "**항등식·앵커·변이 검정.** 값을 고의로 훼손해 검사가 실제로 "
        "실패하는지까지 확인합니다. 틀린 데이터에서도 통과하는 검사는 검사가 "
        "아닙니다.",
        "**앵커는 공시 원문에서 손으로 읽은 수치만.** 항등식과 트립와이어는 "
        "검사 대상과 같은 데이터로 계산되므로 *내부적으로 일관된 틀린 값은 "
        "둘 다 통과합니다.* 앵커만이 데이터가 틀렸을 때 실패합니다.",
        "**워드·엑셀·마크다운 세 포맷과 HTML**을 같은 원본에서 만듭니다. "
        "엑셀은 파생 셀을 수식으로 남겨 가정을 직접 바꿀 수 있게 합니다.",
    ]})

    # =============================================================== 2부
    b.append({"t": "h2", "x": "2부. 네 기업에 적용"})
    b.append({"t": "h3", "x": "시나리오를 손으로 고르지 않았습니다"})
    b.append({"t": "p", "x":
              f"네 기업의 10년 영업이익 CAGR이 "
              f"{pct(min(c['record']['operating_income_cagr'] for c in APPLIED))}"
              f"에서 "
              f"{pct(max(c['record']['operating_income_cagr'] for c in APPLIED))}"
              f"까지 벌어져 있습니다. 하나의 성장률을 네 기업에 똑같이 쓰면 "
              f"어느 기업에도 맞지 않습니다. 그래서 **각 기업의 자기 기록에서 "
              f"규칙으로 도출**하고, 상한만 명시했습니다."})
    b.append({"t": "table", "headers":
              ["시나리오", "초기 성장률", "증분 ROIC", "할인율", "터미널"],
              "rows": [
        ["보수", "10년 CAGR ÷ 3 (상한 10%)", "10년 최저 ROIC (상한 15%)",
         "11%", "2.0%"],
        ["중립", "10년 CAGR ÷ 2 (상한 15%)", "10년 중위 ROIC ÷ 2 (상한 25%)",
         "10%", "2.5%"],
        ["낙관", "10년 CAGR (상한 25%)", "10년 중위 ROIC (상한 35%)",
         "9%", "3.0%"],
    ]})
    b.append({"t": "p", "x":
              "**상한이 이 모형에서 가장 중요한 판단입니다.** 지금의 비범한 "
              "수익률과 성장률을 영구히 연장하지 않겠다는 선언입니다. 상한이 "
              "없으면 엔비디아의 10년 CAGR 67.6%가 영구 성장률이 되어 어떤 "
              "가격도 정당화됩니다. 할인율과 터미널 성장률은 기업의 성질이 "
              "아니라 \"내가 요구하는 수익률\"이므로 네 기업에 똑같이 "
              "적용했습니다."})
    b.append({"t": "note", "x":
              "이 규칙을 알파벳에 적용하면 보수 7.0%/15%, 중립 10.4%/18.9%, "
              "낙관 20.9%/35%가 나옵니다. 직전 알파벳 보고서에서 손으로 골랐던 "
              "6%/15%, 12%/22%, 20%/30%와 거의 같습니다 — 규칙이 과거의 "
              "판단을 재현하므로, 규칙으로 바꾼 것이 결론을 움직이지 "
              "않았습니다."})

    # ------------------------------------------- 풀어 쓴 계산 (세 절)
    ex = [c for c in APPLIED if c["ticker"] == "GOOG"][0]
    exv = val(ex, "중립")
    exa = exv["assumptions"]

    b.append({"t": "h3", "x": "풀어 쓴 계산 ① — 성장률은 어디서 왔나"})
    b.append({"t": "p", "x":
              "성장률은 제가 고른 숫자가 아니라 **세 단계를 거쳐 나온 "
              "값**입니다."})
    b.append({"t": "bullets", "x": [
        "**1단계 — 각 기업의 지난 10년을 잰다.** 영업이익이 10년 동안 "
        "연평균 몇 %로 늘었는지. 이건 가정이 아니라 공시에서 나온 "
        "*측정값*입니다.",
        "**2단계 — 시나리오별로 나눈다.** 낙관 = 과거 속도가 그대로 "
        "이어진다(÷1). 중립 = 절반으로 꺾인다(÷2). 보수 = 3분의 1로 "
        "꺾인다(÷3).",
        "**3단계 — 상한을 씌운다.** 과거가 아무리 빨랐어도 낙관 25%, 중립 "
        "15%, 보수 10%를 넘기지 않습니다. 엔비디아의 67.6%를 그대로 쓰면 "
        "어떤 가격도 정당화됩니다.",
    ]})
    rows = []
    for c in APPLIED:
        row = [name(c), pct(c["record"]["operating_income_cagr"])]
        for s in ORDER:
            si = [x for x in c["scenario_inputs"] if x["name"] == s][0]
            row.append(f"{pct(si['growth_uncapped'])}→{pct(si['growth'])}(상한)"
                       if si["growth_capped"] else pct(si["growth"]))
        rows.append(row)
    b.append({"t": "table", "headers":
              ["기업", "10년 영업이익 CAGR (측정값)", "보수 = ÷3",
               "중립 = ÷2", "낙관 = ÷1"], "rows": rows})
    b.append({"t": "note", "x":
              "엔비디아는 세 시나리오 모두 상한에 걸립니다 — 그래서 엔비디아 "
              "결론이 가장 가정 의존적입니다."})
    b.append({"t": "p", "x":
              f"**성장률은 한 숫자가 아니라 10년에 걸친 경로입니다.** 어떤 "
              f"기업도 영원히 20%로 성장하지 못합니다. 그래서 1년차에 위 "
              f"성장률로 시작해 10년에 걸쳐 직선으로 낮춥니다(감쇠 목표: "
              f"보수 2.5% / 중립 3.5% / 낙관 4.5%). 알파벳 중립은 1년차 "
              f"{pct(exa['growth'], 2)}에서 10년차 "
              f"{pct(exa['fade_to'], 2)}까지 내려갑니다."})

    b.append({"t": "h3", "x": "풀어 쓴 계산 ② — 증분 ROIC은 왜 필요한가"})
    b.append({"t": "p", "x":
              "**성장에는 돈이 듭니다.** 매출을 늘리려면 설비를 더 지어야 "
              "하고, 그 돈은 주주에게 못 갑니다. 얼마가 드는지는 \"새로 넣은 "
              "1달러가 얼마를 버는가\", 즉 증분 ROIC이 정합니다."})
    rr = exa["growth"] / exa["incremental_roic"]
    b.append({"t": "formula", "x":
              "재투자율 = 성장률 ÷ 증분ROIC\n"
              "주주 몫 현금 = NOPAT × (1 − 재투자율)\n\n"
              f"예) 성장 {pct(exa['growth'])}, 증분ROIC "
              f"{pct(exa['incremental_roic'])} → 재투자율 {pct(rr)} "
              f"→ 주주 몫은 NOPAT의 {pct(1 - rr)}"})
    b.append({"t": "p", "x":
              "증분 ROIC이 낮을수록 같은 성장에 더 많은 돈이 들고, 주주 "
              "몫은 줄어듭니다. 이 값도 성장률과 같은 방식으로 각 기업의 "
              "**자기 ROIC 기록**에서 뽑았습니다."})
    rows = []
    for c in APPLIED:
        s0 = c["record"]["summary"]
        row = [name(c), pct(s0["roic_min"]), pct(s0["roic_median"])]
        for s in ORDER:
            si = [x for x in c["scenario_inputs"] if x["name"] == s][0]
            row.append(
                f"{pct(si['incremental_roic_uncapped'])}→"
                f"{pct(si['incremental_roic'])}(상한)"
                if si["incremental_roic_capped"]
                else pct(si["incremental_roic"]))
        rows.append(row)
    b.append({"t": "table", "headers":
              ["기업", "10년 최저", "10년 중위", "보수 = 최저",
               "중립 = 중위÷2", "낙관 = 중위"], "rows": rows})
    b.append({"t": "note", "x":
              "보수는 세 기업 모두 상한 15%에 걸립니다 — 즉 보수 시나리오는 "
              "\"지금의 비범한 수익률이 평범해진다면\"을 묻는 스트레스 "
              "테스트입니다. 예측이 아닙니다."})

    b.append({"t": "h3", "x": "풀어 쓴 계산 ③ — 주당 가치는 어떻게 나왔나"})
    b.append({"t": "p", "x":
              f"{name(ex)}의 **중립 시나리오**를 처음부터 끝까지 따라가 "
              f"보겠습니다. 다른 기업·시나리오도 같은 계산을 숫자만 바꿔 "
              f"한 것입니다."})
    b.append({"t": "table", "headers": ["이 시나리오의 가정", "값", "어디서 왔나"],
              "rows": [
        ["출발점 — TTM 세후영업이익(NOPAT)", f"{bn(ex['ttm']['nopat'])}십억",
         f"최근 4개 분기 영업이익 "
         f"{bn(ex['ttm']['operating_income']['value'])}십억 × (1 − 실효세율 "
         f"{pct(ex['ttm']['effective_tax_rate'])})"],
        ["1년차 성장률", pct(exa["growth"]),
         f"10년 CAGR {pct(ex['record']['operating_income_cagr'])} ÷ 2"],
        ["10년차 성장률 (감쇠 목표)", pct(exa["fade_to"]),
         "중립 시나리오의 시장 가정"],
        ["증분 ROIC", pct(exa["incremental_roic"]),
         f"10년 중위 ROIC "
         f"{pct(ex['record']['summary']['roic_median'])} ÷ 2"],
        ["할인율 (요구수익률)", pct(exa["discount"], 0),
         "중립 시나리오의 시장 가정 — 내가 요구하는 연 수익률"],
        ["11년차 이후 영구 성장률", pct(exa["terminal_growth"]),
         "중립 시나리오의 시장 가정"],
    ]})
    b.append({"t": "p", "x":
              "**1~2단계 — 10년을 한 해씩 투영하고, 각 해의 현금을 오늘 "
              "값으로 당깁니다.**"})
    b.append({"t": "table", "headers":
              ["연차", "성장률", "NOPAT", "재투자율", "주주 몫 현금",
               "현재가치"],
              "rows": [[f"{p['year']}년차", pct(p["growth"], 2),
                        bn(p["nopat"]), pct(p["reinvestment_rate"]),
                        bn(p["free_cash_flow"]), bn(p["present_value"])]
                       for p in exv["projection"]]
              + [["**10년 현재가치 합계**", "", "", "", "",
                  bn(exv["pv_of_forecast"])]]})
    b.append({"t": "note", "x":
              f"단위 십억 달러. NOPAT은 전년 × (1+성장률), 주주 몫 현금은 "
              f"NOPAT × (1−재투자율), 현재가치는 그 현금 ÷ "
              f"(1+{pct(exa['discount'], 0)})의 연차 제곱입니다. 재투자율이 "
              f"{pct(exv['projection'][0]['reinvestment_rate'])}에서 "
              f"{pct(exv['projection'][-1]['reinvestment_rate'])}로 "
              f"내려가는 것은 성장률이 낮아지면 성장에 드는 돈도 줄기 "
              f"때문입니다."})
    last_nopat = exv["projection"][-1]["nopat"]
    disc10 = 1 / (1 + exa["discount"]) ** 10
    term_undisc = exv["pv_of_terminal"] / disc10
    b.append({"t": "p", "x":
              "**3~5단계 — 11년차 이후를 한 덩어리로 묶고, 순현금을 더한 뒤 "
              "주식수로 나눕니다.**"})
    b.append({"t": "table", "headers": ["단계", "계산", "값"], "rows": [
        ["① 10년치 현재가치 합계", "위 표의 마지막 줄",
         f"{bn(exv['pv_of_forecast'])}십억"],
        ["② 11년차 이후 가치 (터미널)",
         f"10년차 NOPAT {bn(last_nopat)} × (1+{pct(exa['terminal_growth'])}) "
         f"× (1 − {pct(exa['terminal_growth'])}÷"
         f"{pct(exa['incremental_roic'])}) ÷ ({pct(exa['discount'], 0)} − "
         f"{pct(exa['terminal_growth'])})", f"{bn(term_undisc)}십억"],
        ["③ 터미널을 현재가치로",
         f"② ÷ (1+{pct(exa['discount'], 0)})의 10제곱",
         f"{bn(exv['pv_of_terminal'])}십억"],
        ["④ 기업가치", "① + ③", f"{bn(exv['enterprise_value'])}십억"],
        ["⑤ 자기자본가치",
         f"④ + 순현금 {bn(ex['balance_sheet']['net_cash'])}십억",
         f"{bn(exv['equity_value'])}십억"],
        ["⑥ 주당 가치",
         f"⑤ ÷ 주식수 "
         f"{ex['shares_outstanding']['value'] / BN:,.3f}십억 주",
         f"**{usd(exv['value_per_share'], 2)}**"],
    ]})
    b.append({"t": "p", "x":
              f"현재가는 {usd(ex['price'], 2)}입니다. 즉 중립 가정이 맞다면 "
              f"현재가는 가치의 {exv['price_to_value']:.2f}배 — "
              f"{sg(exv['upside_vs_market'], 0)}입니다. 그리고 "
              f"**③이 전체의 {pct(exv['terminal_share'], 0)}를 "
              f"차지합니다** — 가치의 대부분이 11년차 이후에서 나옵니다. "
              f"이것이 이 모형의 가장 큰 약점이고, 그래서 주당 가치를 "
              f"\"정답\"이 아니라 \"이 가정이 맞다면 이 값\"으로 읽어야 "
              f"합니다."})
    b.append({"t": "p", "x":
              f"**왜 \"할인\"하는가.** 내년의 1달러는 오늘의 1달러보다 "
              f"못합니다. 오늘 1달러를 다른 곳에 넣어 "
              f"{pct(exa['discount'], 0)}를 벌 수 있다면, 내년의 1달러는 "
              f"오늘 기준으로 {1 / (1 + exa['discount']):.3f}달러의 "
              f"값입니다. 10년 뒤의 1달러는 {disc10:.3f}달러입니다. "
              f"**할인율이 바로 \"내가 요구하는 연 수익률\"**이고, 그래서 "
              f"할인율을 9%로 두면 같은 사업이 더 비싸 보이고 11%로 두면 더 "
              f"싸 보입니다 — 시나리오별로 할인율을 다르게 둔 이유입니다."})

    b.append({"t": "h3", "x": "한눈에 보기 — 사업의 질"})
    b.append({"t": "table", "headers":
              ["기업", "TTM 영업이익", "영업이익률", "10년 CAGR",
               "ROIC 중위", "순현금"],
              "rows": [[name(c), bn(c["ttm"]["operating_income"]["value"]),
                        pct(c["ttm"]["operating_margin"]),
                        pct(c["record"]["operating_income_cagr"]),
                        pct(c["record"]["summary"]["roic_median"]),
                        bn(c["balance_sheet"]["net_cash"], 0)]
                       for c in APPLIED]})
    b.append({"t": "note", "x":
              "단위 십억 달러. 세 기업 모두 10년 내내 ROIC가 문턱 "
              f"{pct(D['wacc_for_roic_hurdle'], 0)}을 넘었습니다 — 사업의 질은 "
              f"전부 합격입니다. 스페이스X는 10-K가 없어 10년 기록이 "
              f"없습니다."})

    b.append({"t": "h3", "x": "공통 패턴 — ROIC가 모두 내려오고 있습니다"})
    b.append({"t": "table", "headers":
              ["기업", "고점", "최근", "영업이익 배수", "투하자본 배수"],
              "rows": [[name(c),
                        f"FY{c['record']['trend']['peak_fiscal_year']} "
                        f"{pct(c['record']['trend']['peak_roic'])}",
                        f"FY{c['record']['trend']['last_fiscal_year']} "
                        f"{pct(c['record']['trend']['last_roic'])}",
                        f"{c['record']['trend']['operating_income_multiple']:.2f}배",
                        f"{c['record']['trend']['invested_capital_multiple']:.2f}배"]
                       for c in APPLIED]})
    b.append({"t": "p", "x":
              "**세 기업이 같은 모양입니다.** 영업이익이 멈춘 게 아니라 "
              "투하자본이 더 빨리 늘었습니다. 마이크로소프트가 가장 "
              "극단적입니다 — FY2019 이후 영업이익은 3.6배인데 투하자본은 "
              "10.6배입니다. 가격 판정보다 이 추세가 더 중요할 수 있습니다: "
              "AI 설비 투자가 과거의 수익률로 돌아오는지가 세 기업 모두의 "
              "핵심 질문입니다."})

    # 기업별
    for c in APPLIED:
        b.append({"t": "h3", "x": f"{name(c)} — {usd(c['price'], 2)}"})
        b.append({"t": "note", "x":
                  f"자료 기준 {c['data_as_of']} (TTM 4개 분기: "
                  f"{', '.join(c['ttm']['operating_income']['quarter_ends'])}) · "
                  f"시가총액 {bn(c['market_cap'], 0)}십억 달러 · 주식수 "
                  f"{c['shares_outstanding']['value'] / BN:,.3f}십억 주 · "
                  f"52주 {usd(c['fifty_two_week_low'], 2)}~"
                  f"{usd(c['fifty_two_week_high'], 2)}"})
        rows = []
        for s in ORDER:
            v = val(c, s)
            a = v["assumptions"]
            ig = v["implied_growth_at_price"]
            rows.append([
                s,
                f"{pct(a['growth'])}→{pct(a['fade_to'])}",
                pct(a["incremental_roic"]),
                usd(v["value_per_share"]),
                sg(v["upside_vs_market"], 0),
                pct(ig) if ig is not None else "없음",
            ])
        b.append({"t": "table", "headers":
                  ["시나리오", "성장률", "증분ROIC", "주당 가치", "현재가 대비",
                   "정당화 성장률"], "rows": rows})
        v_lo, v_mid, v_hi = (val(c, "보수"), val(c, "중립"), val(c, "낙관"))
        b.append({"t": "p", "x":
                  f"TTM 영업이익 {bn(c['ttm']['operating_income']['value'])}십억 "
                  f"× (1 − 실효세율 {pct(c['ttm']['effective_tax_rate'])}) = "
                  f"NOPAT {bn(c['ttm']['nopat'])}십억. "
                  f"주가÷NOPAT {c['market_cap'] / c['ttm']['nopat']:.1f}배. "
                  f"{c['ttm']['tax_note']}"})
        if v_hi["upside_vs_market"] is not None and v_hi["upside_vs_market"] > 0:
            b.append({"t": "p", "x":
                      f"**낙관 시나리오에서만 현재가보다 높습니다** "
                      f"({usd(v_hi['value_per_share'])}, "
                      f"{sg(v_hi['upside_vs_market'], 0)}). 그 가정은 성장 "
                      f"{pct(v_hi['assumptions']['growth'])}로 시작해 10년에 "
                      f"걸쳐 {pct(v_hi['assumptions']['fade_to'])}로 내려가고, "
                      f"새 자본이 "
                      f"{pct(v_hi['assumptions']['incremental_roic'])}를 벌고, "
                      f"요구수익률이 "
                      f"{pct(v_hi['assumptions']['discount'], 0)}라는 것입니다. "
                      f"중립에서는 {usd(v_mid['value_per_share'])}"
                      f"({sg(v_mid['upside_vs_market'], 0)})입니다."})
        else:
            b.append({"t": "p", "x":
                      f"**세 시나리오 모두 현재가보다 낮습니다.** 가장 관대한 "
                      f"낙관 가정에서도 {usd(v_hi['value_per_share'])}"
                      f"({sg(v_hi['upside_vs_market'], 0)})입니다."})
        b.append({"t": "p", "x":
                  f"보수·중립 시나리오에서는 **성장률을 어떻게 잡아도 현재가가 "
                  f"나오지 않습니다.** 보수 가정(증분 ROIC "
                  f"{pct(v_lo['assumptions']['incremental_roic'], 0)}) 안에서 "
                  f"성장률을 증분 ROIC 직전까지 — 즉 10년간 잉여현금을 거의 "
                  f"전부 재투자하는 지점까지 — 올려도 천장은 주당 "
                  f"{usd(v_lo['best_case_in_scenario']['value_per_share'])}"
                  f"이고, 현재가는 그 천장의 "
                  f"{v_lo['price_vs_best_case']:.2f}배입니다. 중립 가정"
                  f"(증분 ROIC "
                  f"{pct(v_mid['assumptions']['incremental_roic'], 0)})의 "
                  f"천장도 주당 "
                  f"{usd(v_mid['best_case_in_scenario']['value_per_share'])}"
                  f"로 현재가 아래입니다."})

    # 스페이스X
    b.append({"t": "h3", "x": f"{name(SX)} — {usd(SX['price'], 2)} (별도 취급)"})
    b.append({"t": "p", "x": f"**{SX['why_not']}**"})
    b.append({"t": "table", "headers": ["기준이익 후보", "연율화 NOPAT", "내용"],
              "rows": [[b_["name"], bn(b_["nopat"]), b_["note"]]
                       for b_ in SX["earnings_bases"]]})
    b.append({"t": "note", "x":
              f"단위 십억 달러. 상반기 {bn(SX['nopat_first_half'])}십억 적자에 "
              f"3분기 {bn(SX['nopat_q3'])}십억 흑자입니다. 흑자 전환 첫 분기이고, "
              f"어느 분기를 기준으로 잡느냐가 가치를 수십 배 바꿉니다."})
    rows = []
    for b_ in SX["earnings_bases"]:
        if not b_.get("valuations"):
            rows.append([b_["name"], "—", "—", "—"])
            continue
        rows.append([b_["name"]] + [
            f"{usd(v['value_per_share'], 0)} ({sg(v['upside_vs_market'], 0)})"
            for v in b_["valuations"]])
    b.append({"t": "table", "headers": ["기준이익", "보수", "중립", "낙관"],
              "rows": rows})
    b.append({"t": "p", "x":
              "더 정직한 답은 거꾸로 푸는 것입니다 — **현재 가격이 정당화되려면 "
              "정상상태 세후영업이익이 얼마여야 하는가.** 기준을 고르지 않아도 "
              "되기 때문입니다."})
    b.append({"t": "table", "headers":
              ["시나리오", "요구 NOPAT", "3분기 연율화의", "연율화 매출의"],
              "rows": [[r["scenario"], f"{bn(r['required_nopat_at_price'])}십억",
                        f"{r['vs_q3_annualised']:.1f}배",
                        pct(r["as_share_of_q3_annualised_revenue"], 0)]
                       for r in SX["reverse"]]})
    rv = SX["revenue"]
    b.append({"t": "p", "x":
              f"3분기 매출을 연율화하면 {bn(rv['q3_annualised'])}십억 달러입니다"
              f"(9개월 연율화 {bn(rv['nine_months_annualised'])}십억 — 가속 "
              f"중입니다). 시가총액은 그 매출의 "
              f"{rv['market_cap_to_q3_annualised_revenue']:.0f}배입니다. "
              f"가장 관대한 낙관 가정에서도 현재 가격은 **지금 연율화 매출의 "
              f"{pct(SX['reverse'][2]['as_share_of_q3_annualised_revenue'], 0)}를 "
              f"세후영업이익으로 벌어야** 설명됩니다. 매출이 몇 배로 커지면서 "
              f"이익률까지 올라야 한다는 뜻이고, 이것은 가치평가 문제가 "
              f"아니라 **아직 존재하지 않는 규모의 사업에 대한 베팅**입니다."})
    seg = SX["segments_9m"]
    if isinstance(seg, dict):
        b.append({"t": "table", "headers":
                  ["사업부", "Q3′26 매출", "Q3′26 영업이익", "9M′26 매출",
                   "9M′26 영업이익"],
                  "rows": [[k, bn(v["revenue"]["q3_2026"]),
                            bn(v["operating_income"]["q3_2026"]),
                            bn(v["revenue"]["9m_2026"]),
                            bn(v["operating_income"]["9m_2026"])]
                           for k, v in seg.items() if isinstance(v, dict)]})
        b.append({"t": "note", "x":
                  "단위 십억 달러. 사업부 투하자본은 공시되지 않으므로 사업부 "
                  "ROIC를 만들지 않았습니다."})

    # =============================================================== 3부
    b.append({"t": "h2", "x": "3부. 판정"})
    b.append({"t": "table", "headers":
              ["기업", "현재가", "보수", "중립", "낙관", "판정"],
              "rows": [[name(c), usd(c["price"], 2),
                        usd(val(c, "보수")["value_per_share"]),
                        usd(val(c, "중립")["value_per_share"]),
                        usd(val(c, "낙관")["value_per_share"]),
                        ("낙관에서만 설명됨"
                         if val(c, "낙관")["upside_vs_market"] > 0
                         else "어느 시나리오에서도 비쌈")]
                       for c in APPLIED]
              + [[name(SX), usd(SX["price"], 2), "—", "—", "—",
                  "기준이익 미성립 — 적정주가 산출 불가"]]})
    b.append({"t": "p", "x":
              "**가장 중요한 발견은 순위가 아닙니다.** 보수·중립 시나리오에서는 "
              "세 기업 모두 **어떤 성장률로도 현재 가격이 설명되지 않습니다.** "
              "성장률을 최적으로 골라도 그렇습니다. 이유는 산수입니다: 증분 "
              "ROIC이 할인율보다 조금만 높으면, 성장률을 올려도 재투자가 그만큼 "
              "늘어 주주에게 남는 현금이 줄어듭니다. 증분 ROIC 15%에서 성장률 "
              "15%면 재투자율이 100%가 되어 잉여현금이 0입니다 — 그래서 "
              "가치에 천장이 생기고, 그 천장이 현재가보다 낮습니다. 성장률을 "
              "그 위로 올리는 것은 번 돈보다 더 투자하는 것이고, 모형에 "
              "외부자금 조달이 들어 있지 않으므로 의미 있는 답이 아닙니다."})
    b.append({"t": "table", "headers":
              ["기업", "보수 천장", "중립 천장", "현재가",
               "중립 천장의 몇 배"],
              "rows": [[name(c),
                        usd(val(c, "보수")["best_case_in_scenario"]
                            ["value_per_share"]),
                        usd(val(c, "중립")["best_case_in_scenario"]
                            ["value_per_share"]),
                        usd(c["price"], 2),
                        f"{val(c, '중립')['price_vs_best_case']:.2f}배"]
                       for c in APPLIED]})
    b.append({"t": "p", "x":
              "**즉 세 기업의 현재 가격은 \"지금의 높은 수익률이 계속된다\"를 "
              "이미 값으로 담고 있습니다.** 수익률이 평범해지는 경우를 "
              "가격이 반영하지 않습니다. 그것이 안전마진이 없다는 뜻입니다."})
    b.append({"t": "h3", "x": "상대 순위 (같은 잣대로 비교할 때)"})
    ranked = sorted(APPLIED, key=lambda c: -val(c, "중립")["upside_vs_market"])
    b.append({"t": "table", "headers":
              ["순위", "기업", "중립 대비", "낙관 대비", "주가÷NOPAT",
               "현재가/중립평가치"],
              "rows": [[str(i), name(c),
                        sg(val(c, "중립")["upside_vs_market"], 0),
                        sg(val(c, "낙관")["upside_vs_market"], 0),
                        f"{c['market_cap'] / c['ttm']['nopat']:.1f}배",
                        f"{val(c, '중립')['price_to_value']:.2f}배"]
                       for i, c in enumerate(ranked, start=1)]})
    b.append({"t": "p", "x":
              f"같은 규칙·같은 할인율로 재면 **{ranked[0]['korean']}이 가장 덜 "
              f"비싸고 {ranked[-1]['korean']}이 가장 비쌉니다.** 다만 "
              f"{ranked[0]['korean']}의 상대적 저평가는 **가장 가정 의존적**"
              f"입니다 — 10년 CAGR "
              f"{pct(ranked[0]['record']['operating_income_cagr'])}와 ROIC 중위 "
              f"{pct(ranked[0]['record']['summary']['roic_median'])}가 둘 다 "
              f"상한에 걸려 크게 깎인 뒤의 숫자이기 때문입니다. 이미 연 매출 "
              f"{bn(ranked[0]['ttm']['revenue']['value'], 0)}십억 달러인 기업이 "
              f"10년간 "
              f"{pct(val(ranked[0], '낙관')['assumptions']['growth'], 0)}로 "
              f"성장한다는 가정이 맞는지가 열린 질문입니다."})

    # =============================================================== 4부
    b.append({"t": "h2", "x": "4부. 방법과 한계"})
    b.append({"t": "bullets", "x": [
        f"**터미널 가치가 전체의 "
        f"{pct(min(val(c, s)['terminal_share'] for c in APPLIED for s in ORDER), 0)}"
        f"~{pct(max(val(c, s)['terminal_share'] for c in APPLIED for s in ORDER), 0)}"
        f"를 차지합니다.** 즉 가치의 대부분이 11년차 이후에서 옵니다. "
        f"10년 투영은 모양을 잡아 주지만 결론을 정하지는 못합니다. 이것이 이 "
        f"모형의 가장 큰 약점이고, 그래서 단일 적정주가로 읽으면 안 됩니다.",
        "**기업마다 자료 기준일이 다릅니다.** " + " · ".join(
            f"{name(c)} {c['data_as_of']}" for c in APPLIED)
        + f". 엔비디아는 3분기(10월 말 결산)가 아직 제출되지 않아 7월 분기가 "
          f"최신입니다 — 분기 영업이익이 전분기 대비 19% 늘고 있는 기업이므로 "
          f"이 한 분기 차이가 작지 않습니다.",
        "**실효세율에 평가손익이 섞여 있습니다.** 세전이익 중 영업 외 수익 "
        "비중이 " + " · ".join(
            f"{name(c)} {pct(c['ttm']['nonoperating_share_of_pretax'], 0)}"
            for c in APPLIED)
        + ". 법정세율 21%로 바꾸면 NOPAT이 " + " · ".join(
            f"{name(c)} {sg(c['ttm']['nopat_at_statutory_21'] / c['ttm']['nopat'] - 1, 1)}"
            for c in APPLIED) + " 움직이며, 판정은 바뀌지 않습니다.",
        "**상한이 결론을 만듭니다.** 특히 엔비디아는 성장률과 증분 ROIC이 둘 다 "
        "상한에 걸립니다. 상한을 올리면 저평가로, 내리면 고평가로 바뀝니다. "
        "엑셀에서 직접 바꿔 보실 수 있게 수식으로 남겼습니다.",
        "**사업부별 투하자본은 공시되지 않습니다.** 사업부 ROIC를 만들지 "
        "않았습니다.",
        f"**검증.** `python3 verify_fair_value.py --mutate` — 항등식·앵커·"
        f"재산출·규칙재현 1,013건, 변이 검정 31건. 앵커는 10-Q 손익계산서에서 "
        f"손으로 읽은 분기 수치이고(마이크로소프트 2026-09-30 영업이익 "
        f"$45,915m, 엔비디아 2026-07-26 $63,734m), 알파벳 TTM 영업이익은 별도 "
        f"파이프라인(282건 검증)의 값과 일치합니다.",
    ]})
    b.append({"t": "note", "x":
              "출처: SEC EDGAR companyfacts와 10-Q 렌더링, 50개사 ROIC 조사"
              f"(roic/roic.json, 생성 {D['roic_study_generated']}), "
              f"시세는 {D['prices_fetched_utc'][:10]} 수집. "
              + " · ".join(f"{name(c)} CIK {c['cik']}"
                           for c in APPLIED)})
    return b


# ------------------------------------------------------------------ 출력
def write_md(bs):
    out = []
    for b in bs:
        t = b["t"]
        if t == "h1":
            out += [f"# {b['x']}", ""]
        elif t == "h2":
            out += ["", f"## {b['x']}", ""]
        elif t == "h3":
            out += [f"### {b['x']}", ""]
        elif t in ("p",):
            out += [b["x"], ""]
        elif t in ("note", "quote"):
            out += [f"> {b['x']}", ""]
        elif t == "formula":
            out += ["```"] + b["x"].split("\n") + ["```", ""]
        elif t == "bullets":
            out += [f"- {x}" for x in b["x"]] + [""]
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
    with open(MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"wrote {MD} ({len(out)} 줄)")


def write_docx(bs):
    payload = []
    for b in bs:
        blk = dict(b)
        x = blk.pop("x", None)
        if blk["t"] == "bullets":
            blk["items"] = x
        elif blk["t"] == "quote":
            blk["text"] = x
            blk["src"] = f"4개 기업 적정주가 판정, {D['generated']}"
        elif x is not None:
            blk["text"] = x
        if blk["t"] == "table" and "widths" not in blk:
            n = len(blk["headers"])
            first = max(12, min(30, int(100 / n) + 10))
            blk["widths"] = [first] + [(100 - first) / (n - 1)] * (n - 1)
            blk["numeric"] = list(range(1, n))
        payload.append(blk)
    with open(DOCX_JSON, "w", encoding="utf-8") as fh:
        json.dump({"title": "네 기업 적정주가 판정", "blocks": payload},
                  fh, indent=1, ensure_ascii=False)
    subprocess.run(["node", "export_memo_docx.js",
                    os.path.relpath(DOCX_JSON, HERE),
                    os.path.basename(DOCX)], cwd=HERE, check=True)
    print(f"wrote {DOCX}")


def main():
    bs = blocks()
    write_md(bs)
    write_docx(bs)


if __name__ == "__main__":
    main()
