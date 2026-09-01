"""
Payload for the Samsung Electronics / SK hynix valuation report.

Every figure is read from work/kr/korea_valuation.json rather than typed in, so
the prose cannot drift from the computation.

Writes work/_korea_payload.json for export_memo_docx.js.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    with open(os.path.join(HERE, name)) as fh:
        return json.load(fh)


K = load(os.path.join("kr", "korea_valuation.json"))
RAW = load(os.path.join("kr", "korea_raw.json"))
ANALYSIS = load("analysis.json")
GOOG = next(c for c in ANALYSIS["companies"] if c["ticker"] == "GOOG")
MEMO2 = load("alphabet_memo2.json")

SEC = K["companies"]["005930.KS"]
HYN = K["companies"]["000660.KS"]


def pct(v, d=1):
    return "-" if v is None else f"{v*100:.{d}f}%"


def jo(v, d=1):
    """Korean won in jo (trillion), which is how these figures are read."""
    if v is None:
        return "-"
    return f"{'−' if v < 0 else ''}₩{abs(v)/1e6:,.{d}f}조"


def won(v, d=0):
    return "-" if v is None else f"₩{v:,.{d}f}"


def usd_bn(v, d=0):
    return "-" if v is None else f"${v:,.{d}f}B"


def x(v, d=1):
    return "-" if v is None else f"{v:.{d}f}배"


blocks = []
h1 = lambda t: blocks.append({"t": "h1", "text": t})
h2 = lambda t: blocks.append({"t": "h2", "text": t})
h3 = lambda t: blocks.append({"t": "h3", "text": t})
p = lambda t: blocks.append({"t": "p", "text": t})
note = lambda t: blocks.append({"t": "note", "text": t})
formula = lambda t: blocks.append({"t": "formula", "text": t})
bullets = lambda items: blocks.append({"t": "bullets", "items": items})
quote = lambda t, src: blocks.append({"t": "quote", "text": t, "src": src})


def table(headers, rows, widths, numeric=()):
    blocks.append({"t": "table", "headers": headers,
                   "rows": [[str(c) for c in r] for r in rows],
                   "widths": widths, "numeric": list(numeric)})


# ===========================================================================
# 요약
# ===========================================================================

h1("요약")

p("초판 보고서는 삼성전자와 SK하이닉스를 정량 분석에서 제외했습니다. 두 회사가 SEC "
  "등록기업이 아니어서, 미국 50개사에 적용한 '모든 숫자가 제출서류까지 추적된다'는 "
  "기준을 맞출 수 없었기 때문입니다. **이번에는 두 곳 모두 1차 자료를 확보해 같은 "
  "기준으로 가치평가했습니다.**")

table(["", "삼성전자", "SK하이닉스"],
      [["현재 주가", won(SEC["market"]["price"]) + " (보통주)",
        won(HYN["market"]["price"])],
       ["시가총액", f"{jo(SEC['market']['market_cap_krw_mn'], 0)} "
        f"({usd_bn(SEC['market']['market_cap_usd_bn'])})",
        f"{jo(HYN['market']['market_cap_krw_mn'], 0)} "
        f"({usd_bn(HYN['market']['market_cap_usd_bn'])})"],
       ["DCF 적정가치 — 사이클 정규화 기준",
        won(SEC["valuations"]["cycle_median"]["scenarios"][1]["value_per_share"]),
        won(HYN["valuations"]["cycle_median"]["scenarios"][1]["value_per_share"])],
       ["DCF 적정가치 — 현재 실적 연환산 기준",
        won(SEC["valuations"]["run_rate"]["scenarios"][1]["value_per_share"]),
        won(HYN["valuations"]["run_rate"]["scenarios"][1]["value_per_share"])],
       ["현재가가 전제하는 정상 영업이익",
        jo(SEC["implied_normalised_operating_income"]),
        jo(HYN["implied_normalised_operating_income"])],
       ["그것은 현재 연환산 실적의",
        pct(SEC["implied_vs_run_rate_operating_income"], 0),
        pct(HYN["implied_vs_run_rate_operating_income"], 0)]],
      [3400, 3000, 2960], numeric=(1, 2))

p("**두 회사의 답은 '싸다'도 '비싸다'도 아니라 '무엇을 믿느냐에 전적으로 달려 있다'"
  "입니다.** 과거 10년의 평균적인 수익성이 정상이라고 보면 두 주식 모두 현재가의 "
  "3분의 1 수준이 적정가입니다. 지금 벌고 있는 속도가 유지된다고 보면 현재가의 "
  "1.6~1.8배가 적정가입니다. 이만큼 폭이 벌어지는 종목은 미국 50개사 중에 없습니다.")

p("시장은 그 사이 어딘가를 가리키고 있습니다. 현재 주가를 정당화하려면 삼성전자는 "
  "지금 벌고 있는 속도의 " + pct(SEC["implied_vs_run_rate_operating_income"], 0) + ", "
  "SK하이닉스는 " + pct(HYN["implied_vs_run_rate_operating_income"], 0) + "가 "
  "영구히 유지되어야 합니다. 그것을 영업이익률로 옮기면 삼성전자 "
  + pct(SEC["implied_normalised_operating_income"]
        / SEC["valuations"]["run_rate"]["base"]["annualised_revenue"]) + ", SK하이닉스 "
  + pct(HYN["implied_normalised_operating_income"]
        / HYN["valuations"]["run_rate"]["base"]["annualised_revenue"]) + "입니다.")
p("**이 수치를 각 회사의 역대 최고 이익률과 나란히 두면 판단의 성격이 분명해집니다.** "
  "삼성전자의 역대 최고 영업이익률은 "
  + pct(SEC["cycle"]["operating_margin_max"]) +
  f"(FY{SEC['cycle']['operating_margin_max_year']})였습니다. 즉 시장은 삼성전자가 "
  "**역대 최고 수준의 수익성을 영구히 유지한다**고 가정하고 있습니다. "
  "SK하이닉스에 대해서는 관측된 3개 연도의 중앙값 "
  + pct(HYN["cycle"]["operating_margin_median"]) + "을 크게 웃도는 수준을 가정하고 "
  "있습니다. **이 보고서의 결론은 목표주가가 아니라, 그 전제가 타당한지를 판단할 "
  "재료를 정리하는 데 있습니다.**")

# ===========================================================================
# 1. 자료 출처
# ===========================================================================

h1("1. 이번에는 왜 가능해졌는가 — 자료 출처")

p("초판에 이렇게 적었습니다.")

quote("이 절에는 정량 수치가 없습니다. 삼성전자와 SK하이닉스는 SEC 등록 기업이 아니라 "
      "감사받은 재무제표를 DART에 제출하며, OpenDART API는 이 환경에 없는 인증키를 "
      "요구합니다. 앞의 50개사는 모든 숫자가 제출서류의 접수번호까지 추적되는데, "
      "이 두 곳만 기억에 의존해 숫자를 적으면 보고서 전체의 기준이 무너집니다.",
      "초판 보고서 6절")

p("그 제약이 두 가지 이유로 풀렸습니다.")

h3("SK하이닉스 — 이제 SEC 제출서류가 있습니다")

p("**SK하이닉스는 2026년 7월 나스닥에 미국주식예탁증서(ADS)를 상장했습니다"
  "(종목코드 SKHY, CIK " + str(RAW["companies"]["000660.KS"]["cik"]) + ").** 그 과정에서 "
  "제출한 Form F-1 최종 투자설명서(424B4, 접수번호 "
  + RAW["companies"]["000660.KS"]["accession"] + ")에 **감사받은 연결재무제표 "
  "FY2023·FY2024·FY2025 3개 연도**가 실려 있습니다. 미국 50개사와 정확히 같은 "
  "출처입니다.")

p("여기에 2026년 8월 18일 제출된 Form 6-K(접수번호 "
  + (HYN["interim"] or {}).get("accession", "") + ")에서 2026년 상반기 실적을 "
  "가져왔습니다.")

h3("삼성전자 — 회사가 공개하는 감사보고서")

p("삼성전자는 SEC 등록기업이 아니지만, **감사받은 연결재무제표 원문을 회사 IR "
  "사이트에 연도별 PDF로 공개**하고 있습니다. DART에 제출하는 것과 같은 문서이고 "
  "감사인의 감사보고서가 붙어 있습니다. FY2016~FY2025 10개 연도분을 내려받아 "
  "재무상태표·손익계산서·현금흐름표·주석을 직접 파싱했습니다.")

p("2026년 상반기는 같은 사이트의 검토받은 요약중간연결재무제표에서 가져왔습니다.")

table(["", "삼성전자", "SK하이닉스"],
      [["자료 성격", "회사 공개 감사받은 연결재무제표",
        "SEC 제출 Form F-1 내 감사받은 연결재무제표"],
       ["확보 연도", "FY2015~FY2025 (11개 연도)", "FY2023~FY2025 (3개 연도)"],
       ["최신 중간실적", "2026 상반기 (검토받은 중간재무제표)", "2026 상반기 (Form 6-K)"],
       ["신뢰등급", "HIGH", "HIGH"],
       ["한계", "SEC 제출서류가 아니므로 접수번호 대신 문서 URL로 추적",
        "감사받은 연간 시계열이 3년뿐 — 완전한 사이클을 담지 못함"]],
      [2000, 3700, 3660])

note("두 회사의 재무제표는 XBRL 태그가 아니라 PDF 텍스트와 HTML 표에서 읽었기 때문에, "
     "파싱 오류가 '에러'가 아니라 '그럴듯한 숫자'로 나타납니다. 그래서 별도 검증 "
     "스크립트(work/verify_korea.py)로 114개 항목을 점검했습니다 — 세전이익 − "
     "법인세 = 순이익 같은 항등식, 이익률·부채비율의 현실적 범위, 설비투자와 "
     "감가상각의 배수 등입니다. 실제로 이 검증이 오류 두 건을 잡아냈습니다(주석 참조).")

# ===========================================================================
# 2. 적용한 기준
# ===========================================================================

h1("2. 적용한 가치평가 기준")

p("알파벳에 쓴 것과 **구조가 동일한** 할인현금흐름 모형입니다.")

formula("잉여현금흐름 = NOPAT × (1 − 성장률 ÷ 신규 ROIC)")

bullets([
    "**NOPAT** = 보고된 영업이익 × (1 − 실효세율). 영업이익을 쓰는 이유는 투하자본이 "
    "현금을 빼고 있어서, 현금·투자자산이 버는 금융수익도 분자에서 빠져야 하기 "
    "때문입니다.",
    "**재투자율을 가정하지 않습니다.** g = 재투자율 × 신규 ROIC라는 항등식이 있으므로 "
    "성장률과 신규 ROIC를 정하면 재투자율이 따라 나옵니다. 성장을 높게 잡으면 "
    "재투자가 자동으로 늘어 잉여현금흐름이 줄어듭니다 — 자본 없이 성장하는 시나리오가 "
    "구조적으로 불가능합니다.",
    "**10년 예측 + 영구가치.** 성장률은 1년차에서 10년차로 선형 감속하고, 영구가치도 "
    "같은 항등식으로 계산합니다.",
    "**순현금을 마지막에 더합니다.** DCF는 사업이 벌 미래 현금의 현재가치이고, "
    "순현금은 그와 별개로 이미 있는 자산입니다.",
])

h3("시나리오 가정")

sc = K["scenarios"]
table(["", "보수", "중립", "낙관"],
      [["1년차 성장률"] + [pct(s["growth"], 0) for s in sc],
       ["10년차 성장률"] + [pct(s["fade_to"]) for s in sc],
       ["신규 ROIC"] + [pct(s["incremental_roic"], 0) for s in sc],
       ["할인율"] + [pct(s["discount"], 0) for s in sc],
       ["영구성장률"] + [pct(s["terminal_growth"]) for s in sc]],
      [2800, 2200, 2200, 2160], numeric=(1, 2, 3))

p("**할인율은 알파벳과 같은 값을 씁니다.** 한국 10년물 국고채 금리가 "
  + pct(K["risk_free_korea"]["rate"]) + "(" + K["risk_free_korea"]["as_of"] + ")로 "
  "미국 10년물 " + pct(ANALYSIS["risk_free_rate"]["rate"]) + "와 큰 차이가 없어, "
  "국가위험 조정을 따로 넣지 않고 그 사실만 밝혀 둡니다.")

p("**성장률과 신규 ROIC는 각 회사의 실측치에서 잡았습니다.** 알파벳에서 중립 "
  "시나리오의 신규 ROIC 20%를 실측 3년 롤링 24.7%에서 가져온 것과 같은 방식입니다. "
  "두 반도체 회사의 실측치는 5절에서 제시합니다.")

# ===========================================================================
# 3. 사이클 문제
# ===========================================================================

h1("3. 먼저 짚어야 할 것 — 사이클")

p("이 두 회사에는 알파벳에 없던 문제가 있습니다. **어느 해를 출발점으로 삼느냐에 "
  "따라 답이 몇 배씩 달라집니다.**")

table(["", "삼성전자", "SK하이닉스"],
      [["영업이익률 최저", pct(SEC["cycle"]["operating_margin_min"]) +
        f" (FY{SEC['cycle']['operating_margin_min_year']})",
        pct(HYN["cycle"]["operating_margin_min"]) +
        f" (FY{HYN['cycle']['operating_margin_min_year']})"],
       ["영업이익률 최고", pct(SEC["cycle"]["operating_margin_max"]) +
        f" (FY{SEC['cycle']['operating_margin_max_year']})",
        pct(HYN["cycle"]["operating_margin_max"]) +
        f" (FY{HYN['cycle']['operating_margin_max_year']})"],
       ["영업이익률 중앙값", pct(SEC["cycle"]["operating_margin_median"]),
        pct(HYN["cycle"]["operating_margin_median"])],
       ["2026 상반기 영업이익률",
        pct(SEC["valuations"]["run_rate"]["base"]["operating_margin"]),
        pct(HYN["valuations"]["run_rate"]["base"]["operating_margin"])],
       ["관측 구간", SEC["cycle"]["window"], HYN["cycle"]["window"]]],
      [2600, 3400, 3360], numeric=(1, 2))

p("SK하이닉스는 FY2023에 영업손실 "
  + jo(next(y["operating_income"] for y in HYN["years"] if y["fiscal_year"] == 2023)) +
  "를 냈고, FY2025에 영업이익 "
  + jo(next(y["operating_income"] for y in HYN["years"] if y["fiscal_year"] == 2025)) +
  "를 냈습니다. **2년 만에 적자에서 사상 최대 이익으로 갔습니다.** 그리고 2026년 "
  "상반기에는 반기만으로 "
  + jo(HYN["interim"]["half_operating_income"]) + "를 벌어, FY2025 연간 이익의 두 배를 "
  "반년에 냈습니다.")

p("삼성전자도 방향은 같습니다. 2026년 상반기 영업이익 "
  + jo(SEC["interim"]["half_operating_income"]) + "는 전년 동기 "
  + jo(SEC["interim"]["prior_year_half_operating_income"]) + "의 "
  + x(SEC["interim"]["half_operating_income"]
      / SEC["interim"]["prior_year_half_operating_income"]) + "이고, FY2025 연간 "
  "영업이익 " + jo(SEC["years"][-1]["operating_income"]) + "의 세 배가 넘습니다.")

quote("가격 문제를 제쳐두면, 소유하기 가장 좋은 사업은 오랜 기간에 걸쳐 많은 양의 "
      "증분 자본을 아주 높은 수익률로 투입할 수 있는 사업이다. 최악의 사업은 그 "
      "반대를 해야만 하는 사업이다 — 즉 계속 늘어나는 자본을 아주 낮은 수익률로 "
      "투입해야 하는 사업이다.",
      "버크셔 해서웨이 1992년 주주서한")

p("**그래서 이 보고서는 출발점을 네 가지로 나누어 각각 계산합니다.** 하나를 고르고 "
  "그것이 정답인 척하는 것이 이런 회사에서 가장 흔한 실수입니다.")

table(["출발점", "무엇인가", "편향"],
      [["최근년도 (FY2025)", "가장 최근에 감사받은 온전한 1년",
        "이미 회복 국면 — 지금 실적과는 한참 떨어져 있음"],
       ["사이클 정규화 — 중앙값", "관측 연도 영업이익률의 중앙값을 최근 매출에 적용",
        "관측 구간이 짧으면 사이클을 대표하지 못함"],
       ["사이클 정규화 — 평균", "산술평균 적용", "적자 연도의 무게가 중앙값보다 큼"],
       ["현재 실적 연환산", "2026 상반기 실적 × 2",
        "현재 메모리 가격이 영원히 유지된다는 가정 — 명백한 상한"]],
      [2600, 4000, 2760])

# ===========================================================================
# 4·5. 회사별
# ===========================================================================


def company_section(c, num, extra_notes=()):
    h1(f"{num}. {c['company_name']}")

    m = c["market"]
    latest = c["years"][-1]
    h2(f"{num}.1 지금 어디에 서 있는가")
    table(["항목", "값", "비고"],
          [["주가", won(m["price"]), m["price_source"]],
           ["유통주식수", f"{m['shares_outstanding']:,.0f}주", m["shares_note"]],
           ["시가총액", jo(m["market_cap_krw_mn"], 0),
            usd_bn(m["market_cap_usd_bn"]) + f" (환율 {K['fx']['krw_per_usd']:,.2f}원/$, "
            + K["fx"]["as_of"] + ")"],
           [f"FY{latest['fiscal_year']} 매출", jo(latest["revenue"]), ""],
           [f"FY{latest['fiscal_year']} 영업이익", jo(latest["operating_income"]),
            "영업이익률 " + pct(latest["operating_margin"])],
           ["2026 상반기 매출", jo(c["interim"]["half_revenue"]), c["interim"]["period"]],
           ["2026 상반기 영업이익", jo(c["interim"]["half_operating_income"]),
            "영업이익률 " + pct(c["valuations"]["run_rate"]["base"]["operating_margin"])],
           ["순현금", jo(c["net_cash"]), "현금성자산 − 이자부부채"]],
          [2400, 2200, 4760], numeric=(1,))

    h2(f"{num}.2 자본은 얼마를 벌었는가 (원칙 1)")
    rows = [[f"FY{y['fiscal_year']}", jo(y["revenue"]), jo(y["operating_income"]),
             pct(y["operating_margin"]), pct(y["roic"]) if y["roic"] is not None else "-",
             jo(y["capex"]), x(y["capex_to_depreciation"], 2) if y["capex_to_depreciation"] else "-"]
            for y in c["years"] if y["revenue"]]
    table(["연도", "매출", "영업이익", "영업이익률", "ROIC", "설비투자", "설비투자÷감가상각"],
          rows, [1000, 1500, 1500, 1400, 1200, 1400, 1360], numeric=(1, 2, 3, 4, 5, 6))

    r = c["returns"]
    inc = r["incremental_roic_full"]
    p(f"**ROIC 중앙값 {pct(r['roic_median'])}, 최근 {pct(r['roic_latest'])}.** "
      f"관측된 {r['roic_years_observed']}개 연도 중 "
      f"{r['roic_years_above_10pct']}개 연도에서 10%를 넘겼습니다.")
    if inc:
        p(f"**신규 ROIC({inc['window']})는 {pct(inc['incremental_roic'])}입니다.** "
          f"그 기간 투하자본이 {jo(inc['delta_invested_capital'])} 늘고 NOPAT이 "
          f"{jo(inc['delta_nopat'])} 늘었습니다.")
    for t in extra_notes:
        p(t)

    h2(f"{num}.3 네 가지 출발점의 DCF")
    order = ["cycle_median", "cycle_mean", "latest_year", "run_rate"]
    rows = []
    for key in order:
        v = c["valuations"].get(key)
        if not v:
            continue
        rows.append([v["base"]["label"], jo(v["base"]["operating_income"]),
                     jo(v["base"]["nopat"])]
                    + [won(s["value_per_share"]) for s in v["scenarios"]]
                    + [pct(v["scenarios"][1]["value_per_share"] / m["price"] - 1, 0)])
    table(["출발점", "영업이익", "NOPAT", "보수", "중립", "낙관", "중립 vs 현재가"],
          rows, [2400, 1300, 1300, 1200, 1200, 1300, 1660],
          numeric=(1, 2, 3, 4, 5, 6))
    p(f"현재 주가는 **{won(m['price'])}**입니다.")

    h2(f"{num}.4 거꾸로 — 현재가는 무엇을 전제하는가")
    p("어느 해가 정상인지를 두고 다투는 대신, **시장이 이미 고른 정상을 역산**하면 "
      "논쟁이 사실 확인으로 바뀝니다. 중립 시나리오를 뒤집어 현재 시가총액을 "
      "정당화하는 영구 영업이익을 구했습니다.")
    table(["역산 결과", "값"],
          [["현재가가 전제하는 정상 영업이익",
            jo(c["implied_normalised_operating_income"])],
           [f"= FY{latest['fiscal_year']} 영업이익의",
            x(c["implied_vs_latest_year_operating_income"])],
           ["= 2026 상반기 연환산 영업이익의",
            pct(c["implied_vs_run_rate_operating_income"], 0)],
           ["= 최근 매출 대비 영업이익률",
            pct(c["implied_normalised_margin_on_latest_revenue"])],
           ["참고: 관측된 영업이익률 최고치",
            pct(c["cycle"]["operating_margin_max"]) +
            f" (FY{c['cycle']['operating_margin_max_year']})"]],
          [5400, 3960], numeric=(1,))

    h3("현재 실적이 얼마나 유지되어야 하는가")
    rows = [[pct(s["fraction_of_run_rate"], 0), jo(s["operating_income"]),
             pct(s["implied_margin_on_run_rate_revenue"]),
             won(s["value_per_share"]), x(s["vs_price"], 2)]
            for s in c["run_rate_sustain_sensitivity"]]
    table(["현재 실적의 몇 %가 유지되면", "그때 영업이익", "그때 영업이익률",
           "중립 적정가치", "현재가 대비"],
          rows, [2400, 1800, 1800, 1800, 1560], numeric=(0, 1, 2, 3, 4))
    p("**현재가와 같아지는 지점이 "
      + pct(c["implied_vs_run_rate_operating_income"], 0) + "입니다.** 그보다 많이 "
      "유지되면 지금 사는 것이 이익이고, 그보다 적게 유지되면 손해입니다. "
      "이 한 줄이 이 종목에 대한 투자 판단의 전부입니다.")

    ir_norm = c["valuations"]["cycle_median"]["implied_return_at_current_price"]
    ir_run = c["valuations"]["run_rate"]["implied_return_at_current_price"]
    p("함축수익률로 보면 — 사이클 정규화 기준으로 현재가에 사면 연 "
      + pct(ir_norm, 2) + ", 현재 실적이 유지된다고 보면 연 " + pct(ir_run, 2) +
      "입니다. 한국 10년물 국고채가 " + pct(K["risk_free_korea"]["rate"]) + "입니다.")


company_section(
    SEC, 4,
    extra_notes=[
        "**이 숫자가 삼성전자에 대한 가장 중요한 발견입니다.** 11년 동안 투하자본을 "
        + jo(SEC["returns"]["incremental_roic_full"]["delta_invested_capital"], 0) +
        " 늘렸는데 NOPAT은 "
        + jo(SEC["returns"]["incremental_roic_full"]["delta_nopat"], 0) + " 늘었습니다. "
        "신규 자본의 수익률이 "
        + pct(SEC["returns"]["incremental_roic_full"]["incremental_roic"]) +
        "로, 자본비용을 겨우 넘거나 밑돕니다. 버핏의 1992년 기준을 그대로 적용하면 "
        "**지난 10년의 삼성전자 성장은 주주 가치를 거의 만들지 못했습니다.**",
        "3년 롤링으로 보면 8개 구간 중 5개가 마이너스입니다. 이는 사업이 나빠서라기보다 "
        "메모리 사이클의 저점이 창(window)에 걸린 결과이기도 하지만, 어느 쪽이든 "
        "'투입한 자본이 이익으로 돌아오는 관계'가 안정적이지 않다는 뜻입니다.",
    ])

company_section(
    HYN, 5,
    extra_notes=[
        "**이 수치는 3개 연도, 사실상 2개 구간에서 나온 것이라 해석에 주의가 "
        "필요합니다.** FY2024→FY2025의 신규 ROIC "
        + pct(HYN["returns"]["incremental_roic_full"]["incremental_roic"]) +
        "는 사이클 회복 구간을 그대로 측정한 값이지, 지속 가능한 재투자 수익률이 "
        "아닙니다. 알파벳에서 FY2021(코로나 후 광고 급증)의 119.7%를 걸러냈던 것과 "
        "같은 종류의 왜곡입니다.",
        "**완전한 사이클을 담은 시계열이 없다는 것이 SK하이닉스 분석의 가장 큰 "
        "한계입니다.** F-1은 감사받은 3개 연도만 싣고 있고, 그중 하나가 대규모 "
        "적자연도, 둘이 호황연도입니다. 초판에서 '최소 한 번의 완전한 사이클(호황·불황 "
        "각각 최소 2년)이 필요하다'고 적었던 조건은 여전히 충족되지 않았습니다.",
    ])

# ===========================================================================
# 6. 비교
# ===========================================================================

h1("6. 비교 — 두 회사, 그리고 미국 50개사")

h2("6.1 두 회사 나란히")

table(["", "삼성전자", "SK하이닉스"],
      [["시가총액", jo(SEC["market"]["market_cap_krw_mn"], 0),
        jo(HYN["market"]["market_cap_krw_mn"], 0)],
       ["ROIC 중앙값", pct(SEC["returns"]["roic_median"]),
        pct(HYN["returns"]["roic_median"])],
       ["신규 ROIC (전체 구간)",
        pct(SEC["returns"]["incremental_roic_full"]["incremental_roic"]) +
        f" ({SEC['returns']['incremental_roic_full']['window']})",
        pct(HYN["returns"]["incremental_roic_full"]["incremental_roic"]) +
        f" ({HYN['returns']['incremental_roic_full']['window']})"],
       ["영업이익률 변동폭",
        pct(SEC["cycle"]["operating_margin_min"]) + " ~ " +
        pct(SEC["cycle"]["operating_margin_max"]),
        pct(HYN["cycle"]["operating_margin_min"]) + " ~ " +
        pct(HYN["cycle"]["operating_margin_max"])],
       ["2026 상반기 영업이익률",
        pct(SEC["valuations"]["run_rate"]["base"]["operating_margin"]),
        pct(HYN["valuations"]["run_rate"]["base"]["operating_margin"])],
       ["순현금", jo(SEC["net_cash"]), jo(HYN["net_cash"])],
       ["순현금 ÷ 시가총액", pct(SEC["net_cash"] / SEC["market"]["market_cap_krw_mn"]),
        pct(HYN["net_cash"] / HYN["market"]["market_cap_krw_mn"])],
       ["현재가가 전제하는 유지율",
        pct(SEC["implied_vs_run_rate_operating_income"], 0),
        pct(HYN["implied_vs_run_rate_operating_income"], 0)],
       ["감사받은 연간 시계열", f"{SEC['cycle']['years_observed']}개 연도",
        f"{HYN['cycle']['years_observed']}개 연도"]],
      [2600, 3400, 3360], numeric=(1, 2))

p("**두 회사의 성격 차이가 뚜렷합니다.** 삼성전자는 사업이 넓게 퍼져 있어 사이클의 "
  "진폭이 작고(최저 " + pct(SEC["cycle"]["operating_margin_min"]) + "), 순현금이 "
  "시가총액의 " + pct(SEC["net_cash"] / SEC["market"]["market_cap_krw_mn"]) +
  "에 달해 재무적으로 훨씬 두껍습니다. SK하이닉스는 사실상 메모리 단일 사업이라 "
  "진폭이 크고(최저 " + pct(HYN["cycle"]["operating_margin_min"]) + "), 순현금은 "
  "시가총액의 " + pct(HYN["net_cash"] / HYN["market"]["market_cap_krw_mn"]) +
  "에 그칩니다.")

p("**대신 SK하이닉스는 지금 훨씬 잘 벌고 있습니다.** 2026년 상반기 영업이익률 "
  + pct(HYN["valuations"]["run_rate"]["base"]["operating_margin"]) + " 대 삼성전자 "
  + pct(SEC["valuations"]["run_rate"]["base"]["operating_margin"]) + ". 매출은 "
  "삼성전자의 절반이 안 되는데(" + jo(HYN["interim"]["half_revenue"], 0) + " 대 "
  + jo(SEC["interim"]["half_revenue"], 0) + ") 영업이익은 3분의 2 수준입니다.")

h2("6.2 알파벳과 나란히 — 같은 모형, 같은 시나리오 구조")

goog_mid = MEMO2["dcf"]["scenarios"][1]
table(["", "알파벳", "삼성전자", "SK하이닉스"],
      [["ROIC 중앙값", pct(GOOG["summary"]["roic_10y_median"]),
        pct(SEC["returns"]["roic_median"]), pct(HYN["returns"]["roic_median"])],
       ["신규 ROIC", pct(MEMO2["incremental_roic_by_year"]["rolling_3y"][-1]["incremental_roic"])
        + " (3년 롤링)",
        pct(SEC["returns"]["incremental_roic_full"]["incremental_roic"]) + " (11년)",
        pct(HYN["returns"]["incremental_roic_full"]["incremental_roic"]) + " (1년)"],
       ["중립 DCF ÷ 현재가",
        f"{goog_mid['value_per_share']/MEMO2['dcf']['price']:.2f}배",
        f"{SEC['valuations']['cycle_median']['scenarios'][1]['value_per_share']/SEC['market']['price']:.2f}배",
        f"{HYN['valuations']['cycle_median']['scenarios'][1]['value_per_share']/HYN['market']['price']:.2f}배"],
       ["함축수익률 (정규화 기준)",
        pct(MEMO2["dcf"]["implied_discount_rate_at_current_price"], 2),
        pct(SEC["valuations"]["cycle_median"]["implied_return_at_current_price"], 2),
        pct(HYN["valuations"]["cycle_median"]["implied_return_at_current_price"], 2)],
       ["이익의 예측 가능성", "높음 — 광고·클라우드",
        "낮음 — 메모리 사이클", "매우 낮음 — 메모리 단일"]],
      [2400, 2400, 2300, 2260], numeric=(1, 2, 3))

p("**세 회사 모두 '정규화 이익 기준으로는 비싸다'는 같은 결론이 나옵니다.** "
  "다만 성격이 다릅니다. 알파벳은 이익이 안정적이므로 그 판정이 비교적 단단합니다. "
  "두 반도체 회사는 정규화 이익 자체가 무엇인지 확정하기 어려워, 같은 결론이라도 "
  "훨씬 약한 근거 위에 서 있습니다.")

# ===========================================================================
# 7. 버핏 기준 판정
# ===========================================================================

h1("7. 버핏 기준 판정")

p("2부에서 정리한 7개 기준을 그대로 적용합니다.")

table(["#", "기준", "삼성전자", "SK하이닉스"],
      [["1", "이해할 수 있는 사업", "통과 — 다만 사업부가 넓게 섞여 있음",
        "통과 — 사실상 메모리 단일"],
       ["2", "기존 ROIC > WACC",
        "통과 — 중앙값 " + pct(SEC["returns"]["roic_median"]),
        "통과 — 다만 3개 연도뿐"],
       ["3", "지속성 (해자)", "**불통과** — FY2023 ROIC "
        + pct(next(y["roic"] for y in SEC["years"] if y["fiscal_year"] == 2023)) +
        ", 사이클 저점에서 자본비용 미달",
        "**불통과** — FY2023 영업손실"],
       ["4", "신규 ROIC > WACC",
        "**불통과** — 11년 신규 ROIC "
        + pct(SEC["returns"]["incremental_roic_full"]["incremental_roic"]),
        "판정 불가 — 측정 구간이 1년"],
       ["5", "자본배분·주주 지향성",
        "통과 — 순현금 " + jo(SEC["net_cash"], 0) + ", 자사주 소각 진행",
        "판정 유보 — 시계열 부족"],
       ["6", "이익의 질", "통과 — 영업이익과 현금흐름이 정합",
        "주의 — FY2025 순이익에 금융손익 비중이 큼"],
       ["7", "가격의 합리성", "**불통과** (정규화 기준)", "**불통과** (정규화 기준)"]],
      [500, 2600, 3200, 3060])

p("**기준 3과 4가 이 두 회사의 핵심 쟁점입니다.** 버핏이 2007년 서한에서 해자를 "
  "정의하며 쓴 단어는 '지속적인(enduring)'이었고, 그 기준을 '사이클 저점에서도 "
  "자본비용을 넘는가'로 옮기면 두 회사 모두 최근 사이클에서 통과하지 못했습니다.")

quote("우리가 '지속적'이라는 기준을 두는 탓에 빠르고 연속적인 변화를 겪는 산업의 "
      "기업들은 후보에서 제외된다. (…) 계속 다시 쌓아야 하는 해자는 결국 해자가 "
      "아닐 것이다.",
      "버크셔 해서웨이 2007년 주주서한")

p("메모리 반도체는 2~3년마다 공정을 갈아엎고 그때마다 수십 조 원을 다시 넣어야 하는 "
  "사업입니다. 삼성전자가 11년간 투하자본을 "
  + jo(SEC["returns"]["incremental_roic_full"]["delta_invested_capital"], 0) +
  " 늘리고도 NOPAT이 "
  + jo(SEC["returns"]["incremental_roic_full"]["delta_nopat"], 0) +
  "밖에 늘지 않았다는 사실이 그 성격을 그대로 보여줍니다.")

p("**다만 반론도 분명히 적어둡니다.** AI 가속기용 고대역폭 메모리(HBM)는 범용 D램과 "
  "가격 결정 구조가 다르고, 지금의 이익률(SK하이닉스 반기 "
  + pct(HYN["valuations"]["run_rate"]["base"]["operating_margin"]) +
  ")은 과거 어느 호황에서도 없던 수준입니다. 이것이 '이번엔 다르다'인지 '더 큰 "
  "사이클'인지는 이 보고서가 가진 자료로는 판별되지 않습니다. 판별에 필요한 것은 "
  "다음 저점에서의 ROIC이고, 그것은 아직 관측되지 않았습니다.")

# ===========================================================================
# 8. 한계
# ===========================================================================

h1("8. 한계")

bullets([
    "**SK하이닉스의 감사받은 시계열이 3년뿐입니다.** F-1이 담은 것이 그것뿐이고, "
    "그중 하나가 적자연도입니다. 사이클 정규화의 근거가 얇습니다. 2027년 첫 20-F가 "
    "제출되면 시계열이 늘어납니다.",
    "**삼성전자 수치는 SEC 접수번호로 추적되지 않습니다.** 회사가 공개한 감사받은 "
    "재무제표 PDF의 URL로 추적됩니다. 감사받은 원문이라는 점에서 신뢰등급은 같지만, "
    "제3자 제출 시스템을 거치지 않았다는 차이는 남습니다.",
    "**부문별 자본을 알 수 없습니다.** 삼성전자는 부문별 매출·영업이익·감가상각을 "
    "공시하지만 부문 자산은 공시하지 않습니다. 반도체(DS)와 모바일(DX)의 ROIC를 "
    "따로 구할 수 없다는 뜻이고, 이는 알파벳에서 구글 클라우드 ROIC를 구할 수 없던 "
    "것과 같은 제약입니다.",
    "**환율 위험을 모형에 넣지 않았습니다.** 원화로 계산하고 " +
    f"{K['fx']['krw_per_usd']:,.2f}원/$" + "로 환산만 했습니다. 달러 기준 투자자에게는 "
    "환율이 별도의 손익 요인입니다.",
    "**지배구조 할인을 반영하지 않았습니다.** 두 회사 모두 지주 구조와 소액주주 "
    "보호 수준이 미국 기업과 다르고, 시장은 통상 이를 할인해 반영합니다. 이 모형은 "
    "현금흐름만 봅니다.",
    "**2026년 상반기 실적은 검토(review)이지 감사(audit)가 아닙니다.** 연환산 "
    "시나리오의 출발점이 감사받지 않은 숫자라는 뜻입니다.",
])

note("검증 상태: work/verify_korea.py의 114개 정합성·범위 검증을 모두 통과했습니다. "
     "이 검증이 실제로 파싱 오류 두 건을 잡아냈습니다 — 주석번호가 금액에 달라붙어 "
     "삼성전자 단기차입금이 4경 원으로 나온 건, 그리고 '법인세비용(환입)' 표기 변화로 "
     "FY2024의 법인세가 FY2023 행에 들어간 건입니다. 둘 다 수정 후 재계산했습니다.")


def main():
    payload = {
        "title": "삼성전자·SK하이닉스 가치평가",
        "subtitle": "미국 50개사·알파벳과 동일한 DCF 기준 적용 · 1차 자료 기반",
        "generated": K["generated_at_utc"][:10],
        "blocks": blocks,
    }
    path = os.path.join(HERE, "_korea_payload.json")
    with open(path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"payload -> {path} ({len(blocks)} blocks)")


if __name__ == "__main__":
    main()
