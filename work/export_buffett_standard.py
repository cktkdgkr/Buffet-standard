"""
성장률 가정 재검증 + 버핏 기준 적정주가 — 마크다운·워드.

buffett_standard.json 에서 생성합니다. HTML 판과 같은 원본을 읽으므로 세
포맷이 어긋날 수 없습니다.

    python3 export_buffett_standard.py
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DATA = os.path.join(HERE, "fv", "buffett_standard.json")
MD = os.path.join(HERE, "성장률_재검증_버핏기준_적정주가.md")
DOCX_JSON = os.path.join(HERE, "fv", "buffett_standard_report.json")
DOCX = os.path.join(HERE, "성장률_재검증_버핏기준_적정주가.docx")
MM, BN = 1e6, 1e9

D = json.load(open(DATA, encoding="utf-8"))
MACRO, BR, COS = D["macro"], D["base_rates"], D["companies"]
INFL = MACRO["breakeven_inflation_10y"]["rate"]
DMAP = {x["key"]: x for x in D["discount_options"]}
TMAP = {x["key"]: x for x in D["terminal_options"]}
NI, SL = BR["net_income_10y"], BR["sales_10y"]
DKEYS = ["bond30", "bond30_plus3", "project10", "project11"]


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def sg(x, nd=1):
    return "—" if x is None else f"{x * 100:+.{nd}f}%"


def bn(x, nd=1):
    return "—" if x is None else f"{x / BN:,.{nd}f}"


def usd(x, nd=0):
    return "—" if x is None else f"${x:,.{nd}f}"


def nm(co):
    return f"{co['korean']}({co['ticker']})"


def gcell(co, gkey, dkey):
    g = [x for x in co["grid"] if x["growth_key"] == gkey][0]
    return g, [x for x in g["cells"] if x["discount_key"] == dkey][0]


def band_share_at_or_above(bands, v):
    out = 0.0
    for lab, share in bands:
        if lab.startswith("<"):
            lo, hi = -999.0, float(lab[1:]) / 100.0
        elif lab.startswith(">"):
            lo, hi = float(lab[1:]) / 100.0, 999.0
        else:
            a, b = lab.split("~")
            lo, hi = float(a) / 100.0, float(b) / 100.0
        if v <= lo:
            out += share
        elif v < hi:
            out += share * (hi - v) / (hi - lo)
    return out


def blocks():
    b = []
    b.append({"t": "h1",
              "x": "성장률 가정 재검증 — 그리고 버핏 기준으로 다시 계산한 적정주가"})
    b.append({"t": "note", "x":
              f"자료 기준일 {D['generated']} · 본문 보고서 "
              f"{D['fair_value_generated']} 생성 · 30년 국채 "
              f"{pct(MACRO['treasury_30y']['rate'], 3)} · 10년 국채 "
              f"{pct(MACRO['treasury_10y']['rate'], 3)} · 10년 "
              f"기대인플레이션 {pct(INFL, 2)} (FRED T10YIE, "
              f"{MACRO['breakeven_inflation_10y']['as_of']}) · 기초율 "
              f"{BR['source']} · {BR['period']} · 참조군 "
              f"{BR['reference_class']}"})
    b.append({"t": "p", "x":
              "제기된 의문은 **\"AI 발 성장이 예상되는 업계인데 10년차 "
              "성장률 3.5%는 너무 낮지 않은가. 세 기업은 지난 10년간 10% 넘게 "
              "성장해 왔다\"**입니다. 먼저 제 보고서가 오해를 유발한 부분을 "
              "바로잡고, 성장률 가정을 외부 자료 세 가지로 재검증한 뒤, "
              "버핏의 실제 기준으로 적정주가를 다시 냈습니다."})

    # ---------------------------------------------------------- 0. 바로잡음
    b.append({"t": "h2", "x": "0. 먼저 바로잡습니다 — 3.5%는 10년간 성장률이 아닙니다"})
    b.append({"t": "p", "x":
              "**제 보고서의 표현이 오해를 유발했습니다.** 3.5%는 *10년차 한 "
              "해*의 성장률(감쇠 목표)이고 10년 전체의 평균이 아닙니다. 중립 "
              "시나리오는 1년차에 약 10%로 시작해 10년에 걸쳐 3.5%까지 직선으로 "
              "내려갑니다. 그 10년을 평균하면 아래와 같습니다."})
    b.append({"t": "table", "headers":
              ["기업", "시나리오", "1년차", "10년차", "10년 평균 (NOPAT CAGR)"],
              "rows": [[r["korean"], r["scenario"], pct(r["year1_growth"]),
                        pct(r["year10_growth"]),
                        f"**{pct(r['nopat_cagr_10y'], 2)}**"]
                       for r in D["clarification"]["rows"]]})
    b.append({"t": "note", "x":
              "즉 중립은 10년 평균 6.6~9.2%, 낙관은 11.9~14.6%를 가정하고 "
              "있었습니다. 3.5%로 10년을 가정한 시나리오는 하나도 없습니다."})

    # --------------------------------------------------------- 1. 10년 기록
    b.append({"t": "h2", "x": "1. 세 기업의 지난 10년 — 성장률과 ROIC"})
    b.append({"t": "p", "x":
              "요청하신 표입니다. 전부 SEC 공시에서 뽑은 값이고, 50개사 "
              "조사와 같은 ROIC 정의를 씁니다. 단위는 십억 달러입니다."})
    for co in COS:
        b.append({"t": "h3", "x": f"{nm(co)}"})
        b.append({"t": "table", "headers":
                  ["회계연도", "매출", "증감", "영업이익", "증감", "ROIC"],
                  "rows": [[f"FY{h['fiscal_year']}", bn(h["revenue"]),
                            sg(h["revenue_growth"], 1)
                            if h["revenue_growth"] is not None else "—",
                            bn(h["operating_income"]),
                            sg(h["operating_income_growth"], 1)
                            if h["operating_income_growth"] is not None
                            else "—",
                            f"**{pct(h['roic'])}**"]
                           for h in co["history"]]})
        b.append({"t": "table", "headers":
                  ["회계연도", "투하자본 (평균)", "증감"],
                  "rows": [[f"FY{h['fiscal_year']}",
                            bn(h["invested_capital_avg"]),
                            sg(h["invested_capital_growth"], 1)
                            if h["invested_capital_growth"] is not None
                            else "—"]
                           for h in co["history"]]})
        b.append({"t": "note", "x":
                  f"10년 CAGR: 영업이익 {pct(co['own_cagr_nominal'])} · 매출 "
                  f"{pct(co['own_revenue_cagr_nominal'])}. 자료 기준 "
                  f"{co['data_as_of']}. TTM 매출 "
                  f"{bn(co['ttm_revenue'], 0)}십억 달러."})

    # --------------------------------------------------------- 2. 기초율
    b.append({"t": "h2", "x": "2. 객관 기준 ① — 기초율: 이 규모 기업이 실제로 "
                              "얼마나 성장했는가"})
    b.append({"t": "p", "x":
              f"가장 직접적인 외부 검증은 **같은 규모의 기업들이 과거 10년 "
              f"동안 실제로 얼마나 성장했는지**를 보는 것입니다. "
              f"{BR['source']}이 {BR['period']}년을 규모별로 집계해 "
              f"두었습니다. 우리 세 기업의 TTM 매출은 "
              + " · ".join(f"{co['korean']} {bn(co['ttm_revenue'], 0)}십억"
                           for co in COS)
              + f" 달러로 전부 **{BR['reference_class']}** 참조군에 "
                f"들어갑니다."})
    b.append({"t": "note", "x":
              f"**이 수치는 전부 실질(인플레이션 조정) 기준입니다.** "
              f"{BR['real_terms_note']} 아래에는 명목 환산값(실질 + "
              f"기대인플레이션 {pct(INFL, 2)})을 함께 적었습니다."})
    b.append({"t": "h3", "x": "10년 순이익 성장률 분포 (매출 $50십억 초과, "
                              "1950–2015, 실질)"})
    b.append({"t": "table", "headers": ["성장률 구간", "비중"],
              "rows": [[f"{lab}%", pct(share)]
                       for lab, share in NI["bands"] if share > 0]})
    neg = sum(s for l, s in NI["bands"]
              if l.startswith("-") or l.startswith("<"))
    b.append({"t": "p", "x":
              f"중위값 **{pct(NI['median'])}**(실질) = 명목 "
              f"**{pct(NI['median'] + INFL)}**, 평균 {pct(NI['mean'])}(실질) "
              f"= 명목 {pct(NI['mean'] + INFL)}. 음수였던 경우가 "
              f"{pct(neg)}입니다 — 이 규모의 기업이 10년에 걸쳐 이익을 못 "
              f"늘린 경우가 셋 중 하나가 넘습니다."})
    over10 = sum(s for l, s in NI["bands"]
                 if "~" in l and float(l.split("~")[0]) >= 10)
    over20 = sum(s for l, s in NI["bands"]
                 if "~" in l and float(l.split("~")[0]) >= 20)
    sl_over10 = sum(s for l, s in SL["bands"]
                    if "~" in l and float(l.split("~")[0]) >= 10)
    b.append({"t": "table", "headers":
              ["기준", "실질", "명목 환산", "이 수준 이상이 나온 비율"],
              "rows": [
        ["중위값", pct(NI["median"]), f"**{pct(NI['median'] + INFL)}**", "50%"],
        ["평균", pct(NI["mean"]), pct(NI["mean"] + INFL), "—"],
        ["실질 10% 이상", "10.0%", pct(0.10 + INFL), f"**{pct(over10)}**"],
        ["실질 20% 이상", "20.0%", pct(0.20 + INFL), pct(over20)],
    ]})
    b.append({"t": "note", "x":
              f"표준편차 {pct(NI['stdev'])}. 매출 성장률 분포는 더 얇습니다 — "
              f"중위 {pct(SL['median'])}(실질), 실질 10% 이상은 "
              f"{pct(sl_over10)}에 불과합니다. 이익 쪽 꼬리가 두꺼운 것은 "
              f"마진이 움직이기 때문입니다. 그리고 **이 기초율은 위쪽으로 "
              f"치우쳐 있습니다**: {BR['survivorship_note']}"})

    b.append({"t": "h3", "x": "그 분포 안에서 우리 세 기업과 제 가정은 어디인가"})
    rows = []
    for co in COS:
        rows.append([f"**{nm(co)} 과거 10년 실적**",
                     pct(co["own_cagr_nominal"]), pct(co["own_cagr_real"]),
                     f"**상위 {pct(co['own_cagr_percentile_at_or_above'])}**"])
        for g in co["grid"]:
            rows.append([f"— {g['growth_label'][:30]}", pct(g["growth"]),
                         pct(g["growth_real"]),
                         f"상위 {pct(g['base_rate_percentile_at_or_above'])}"])
    b.append({"t": "table", "headers": ["가정 / 실적", "명목", "실질",
                                        "기초율 백분위"], "rows": rows})
    nv = [c for c in COS if c["ticker"] == "NVDA"][0]
    b.append({"t": "p", "x":
              f"**여기서 결론이 뒤집힙니다.** 제 가정이 너무 낮은 게 아니라, "
              f"**세 기업의 지난 10년이 이미 분포의 꼬리**였습니다. "
              f"마이크로소프트와 알파벳의 실질 성장률은 상위 10~12%, 엔비디아의 "
              f"{pct(nv['own_cagr_real'])}는 **이 규모 기업 중 전례가 "
              f"없습니다**(상위 {pct(nv['own_cagr_percentile_at_or_above'])}). "
              f"다만 엔비디아는 10년 전에 매출 $5십억짜리 회사였으므로, "
              f"**다음 10년에 적용되는 참조군은 지금 규모의 것**입니다 — 그게 "
              f"규모별로 나눠 보는 이유입니다."})
    b.append({"t": "p", "x":
              "반대로 제 가정을 이 분포에 얹어 보면 중립(실질 4.4~7.0%)은 "
              "중위값보다 위이고 낙관(실질 9.7~12.3%)은 상위 20% 안쪽입니다. "
              "**즉 제 가정은 보수적이라기보다 이미 낙관적인 쪽**입니다. 다만 "
              "기초율이 2015년까지의 자료라는 점, 그리고 AI 가 과거와 다른 "
              "국면이라는 주장은 기초율이 반박할 수 없는 영역입니다 — 기초율은 "
              "\"그게 얼마나 드문 일인지\"만 말해 줍니다."})

    # ------------------------------------------------------- 3. 거시 상한
    b.append({"t": "h2", "x": "3. 객관 기준 ② — 영구성장률의 상한은 경제성장률입니다"})
    b.append({"t": "p", "x":
              "10년 이후의 영구성장률은 취향의 문제가 아닙니다. 어떤 기업도 "
              "경제보다 빠르게 *영구히* 성장할 수 없습니다 — 그러면 결국 경제 "
              "전체가 됩니다. 그래서 상한이 명목 GDP 성장률입니다."})
    b.append({"t": "table", "headers": ["기준", "값"], "rows": [
        ["장기 실질 GDP 성장률 (1950–2015)", pct(BR["gdp_real_1950_2015"])],
        ["10년 기대인플레이션 (FRED T10YIE)", pct(INFL, 2)],
        ["→ 장기 명목 GDP (상한)",
         f"**{pct(MACRO['nominal_gdp_long_run']['rate'], 2)}**"],
        ["30년 국채 수익률", pct(MACRO["treasury_30y"]["rate"], 3)],
        ["10년 국채 수익률", pct(MACRO["treasury_10y"]["rate"], 3)],
    ]})
    b.append({"t": "note", "x":
              f"{BR['gdp_note']} 기대인플레이션은 시장가격에서 유도된 "
              f"값이며 제 전망이 아닙니다. 2007년 주주총회에서 버핏이 국채를 "
              f"\"4 and 3/4%\"라고 말한 수준이 오늘 10년 국채와 거의 "
              f"같습니다."})
    b.append({"t": "p", "x":
              f"본문 보고서가 쓴 터미널 2.0~3.0%는 이 상한"
              f"({pct(MACRO['nominal_gdp_long_run']['rate'], 2)})의 절반 "
              f"이하입니다. 보수적인 쪽이 맞고, 그래서 아래에서 명목 GDP까지 "
              f"올려 본 민감도를 함께 냈습니다."})

    # ------------------------------------------------------- 4. 버핏 기준
    b.append({"t": "h2", "x": "4. 객관 기준 ③ — 버핏은 실제로 어떻게 계산했는가"})
    b.append({"t": "p", "x":
              "찾아보니 핵심은 성장률이 아니라 **할인율**에 있었습니다."})
    for q in D["buffett"]:
        b.append({"t": "quote", "x": q["quote"],
                  "src": f"{q['year']}년 · {q['kind']} · {q['url']}"})
        b.append({"t": "note", "x": q["note"]})
    b.append({"t": "p", "x":
              "**정리하면 버핏의 방식은 이렇습니다.** ① 장기 국채 수익률을 "
              "할인율의 *기준*으로 삼고, ② 위험 프리미엄을 얹는 대신 "
              "**안전마진**으로 위험을 처리하고, ③ 성장은 **증분 수익률이 "
              "매력적일 때만** 가치가 된다고 봅니다. ③은 우리 모형이 이미 쓰고 "
              "있는 식 그대로입니다."})
    b.append({"t": "formula", "x":
              "잉여현금 = NOPAT × (1 − 성장률 ÷ 증분ROIC)\n"
              "           ↑ 1992년 서한의 \"incremental returns that are "
              "enticing\" 이 바로 이 항입니다"})
    b.append({"t": "table", "headers": ["할인율 후보", "값"],
              "rows": [[x["label"],
                        (f"**{pct(x['rate'], 2)}**"
                         if x["key"] == "bond30_plus3" else pct(x["rate"], 2))]
                       for x in D["discount_options"]]})
    for x in D["discount_options"]:
        b.append({"t": "note", "x": f"**{x['label']}** — {x['basis']}"})
    b.append({"t": "p", "x":
              f"**순수 국채 수익률만으로 주식을 할인하면 모순이 생깁니다.** "
              f"30년 국채 {pct(MACRO['treasury_30y']['rate'], 2)}로 할인하면서 "
              f"영구성장률을 명목 GDP "
              f"{pct(MACRO['nominal_gdp_long_run']['rate'], 2)}로 두면 분모가 "
              f"음수가 되어 **가치가 무한**이 됩니다(아래 민감도 표에서 실제로 "
              f"발산합니다). 이것이 버핏의 \"국채보다 significantly higher\"가 "
              f"필요한 이유이고, 국채 + 3%포인트를 기준으로 삼은 근거입니다."})

    # ------------------------------------------------------------- 5. 격자
    b.append({"t": "h2", "x": "5. 다시 계산한 적정주가 — 성장률 × 할인율 격자"})
    b.append({"t": "p", "x":
              f"어느 칸이 맞는지는 가정의 문제이므로 하나의 답을 내지 않고 "
              f"격자로 냈습니다. 증분 ROIC은 네 칸 전부에 같은 값(각 기업의 "
              f"10년 중위 ROIC, 상한 35%)을 써서 **성장률과 할인율의 효과만** "
              f"보이게 했고, 터미널은 {pct(TMAP['inflation']['rate'], 2)}"
              f"(실질 영구성장 0%)로 고정했습니다."})
    for co in COS:
        b.append({"t": "h3", "x": f"{nm(co)} — 현재가 {usd(co['price'], 2)}"})
        rows = []
        for g in co["grid"]:
            row = [g["growth_label"][:28], pct(g["growth"])]
            for dk in DKEYS:
                c_ = [x for x in g["cells"] if x["discount_key"] == dk][0]
                row.append("발산" if c_["diverges"]
                           else f"**{usd(c_['value_per_share'])}**")
            rows.append(row)
        rows.append(["현재가", "—"] + [usd(co["price"], 2)] * 4)
        b.append({"t": "table", "headers":
                  ["성장률 가정", "1년차",
                   f"국채 {pct(DMAP['bond30']['rate'], 2)}",
                   f"버핏 {pct(DMAP['bond30_plus3']['rate'], 2)}",
                   "프로젝트 10%", "보수 11%"], "rows": rows})
        b.append({"t": "note", "x":
                  f"증분 ROIC {pct(co['incremental_roic_used'])} 고정. "
                  f"{co['incremental_roic_basis']}"})

    # -------------------------------------------------------- 6. 안전마진
    b.append({"t": "h2", "x": "6. 버핏이라면 살까 — 안전마진을 적용한 판정"})
    b.append({"t": "p", "x":
              f"버핏 기준으로 계산한 가치는 **살 가격이 아닙니다.** 그는 "
              f"위험을 할인율에 얹지 않고 안전마진으로 처리하므로, 그 가치보다 "
              f"충분히 싸야 삽니다. 아래는 버핏 할인율"
              f"({pct(DMAP['bond30_plus3']['rate'], 2)})에서 계산한 가치에 "
              f"안전마진 30%를 적용한 매수 상한입니다."})
    rows = []
    for co in COS:
        for g in co["grid"]:
            _, c_ = gcell(co, g["growth_key"], "bond30_plus3")
            if c_["diverges"]:
                continue
            buy = c_["buy_price_at_margin"]["30%"]
            ok = buy > co["price"]
            rows.append([nm(co), g["growth_label"][:24],
                         usd(c_["value_per_share"]),
                         sg(c_["upside_vs_price"], 0), f"**{usd(buy)}**",
                         usd(co["price"], 2),
                         f"**{'합격' if ok else '불합격'}**"])
    b.append({"t": "table", "headers":
              ["기업", "성장률 가정", "가치", "현재가 대비",
               "안전마진 30% 상한", "현재가", "판정"], "rows": rows})
    goog = [c for c in COS if c["ticker"] == "GOOG"][0]
    _, g_ai = gcell(goog, "ai_sustained", "bond30_plus3")
    b.append({"t": "p", "x":
              f"**결론: 버핏 기준으로 바꿔도 판정은 거의 그대로입니다.** "
              f"할인율을 10%에서 {pct(DMAP['bond30_plus3']['rate'], 2)}로 "
              f"낮추면 가치는 크게 오르지만, 버핏이 함께 요구하는 안전마진 "
              f"30%를 적용하면 **마이크로소프트와 알파벳은 네 가정 모두 "
              f"불합격**입니다. 알파벳의 AI 가속 가정이 매수 상한 "
              f"{usd(g_ai['buy_price_at_margin']['30%'])}로 현재가 "
              f"{usd(goog['price'], 2)}에 가장 가깝게 닿습니다. **엔비디아만 "
              f"과거 성장 유지 또는 AI 가속을 가정할 때 합격**하고, 그 가정이 "
              f"바로 기초율에서 상위 "
              f"{pct(nv['grid'][2]['base_rate_percentile_at_or_above'])} "
              f"안쪽인 경우입니다."})

    # ---------------------------------------------------- 7. 터미널 민감도
    b.append({"t": "h2", "x": "7. 영구성장률을 올리면 — 그리고 모형이 깨지는 지점"})
    b.append({"t": "p", "x":
              "\"AI 로 성장이 오래 간다\"는 주장을 영구성장률로 반영하면 "
              "어떻게 되는지 봅니다. 성장률 가정은 \"과거의 절반\"으로 "
              "고정했습니다."})
    for co in COS:
        b.append({"t": "table", "headers":
                  ["할인율", "영구성장률", "주당 가치", "현재가 대비"],
                  "rows": [[f"{'버핏 기준' if x['discount_key'] == 'bond30_plus3' else '순수 국채'} "
                            f"{pct(x['discount'], 2)}",
                            f"{x['label']} ({pct(x['rate'], 2)})",
                            "발산" if x["diverges"]
                            else f"**{usd(x['value_per_share'])}**",
                            "—" if x["diverges"]
                            else sg(x["upside_vs_price"], 0)]
                           for x in co["terminal_sensitivity"]]})
        b.append({"t": "note", "x":
                  f"{nm(co)} · 현재가 {usd(co['price'], 2)}. 순수 국채 "
                  f"할인율에서 명목 GDP 영구성장을 가정하면 분모가 음수가 되어 "
                  f"발산합니다 — 그 조합은 쓸 수 없습니다."})

    # ------------------------------------------------------- 8. 남는 반론
    b.append({"t": "h2", "x": "8. 기초율이 반박하지 못하는 것"})
    b.append({"t": "bullets", "x": [
        f"**기초율은 2015년까지의 자료입니다.** {BR['period']}년을 집계한 "
        f"것이므로 지금의 AI 설비 투자 국면은 들어 있지 않습니다. \"이번은 "
        f"다르다\"는 주장을 기초율은 반박할 수 없고, 다만 그것이 얼마나 드문 "
        f"일인지를 말해 줍니다.",
        "**참조군의 구성이 다릅니다.** 1950~2015년에 매출 $50십억을 넘었던 "
        "기업들은 상당수가 정유·자동차·통신 같은 성숙 산업입니다. "
        "영업이익률 33~65%인 오늘의 소프트웨어·반도체 기업이 그 분포에 잘 "
        "대표되어 있다고 보기 어렵습니다.",
        "**매출이 아니라 이익을 모형화합니다.** 마진이 오르면 이익은 매출보다 "
        "빨리 자랍니다. 그래서 순이익 기초율(꼬리가 더 두꺼운 쪽)을 썼지만, "
        "이미 마진이 높은 세 기업에 남은 마진 여지는 제한적입니다.",
        "**생존편향이 기초율을 올립니다.** 사라진 기업은 표본에서 빠졌으므로 "
        "실제 기대값은 표에 적힌 것보다 낮습니다 — 즉 제 가정은 더 낙관적인 "
        "쪽입니다.",
        "**3%포인트 스프레드는 버핏의 규칙이 아닙니다.** 1994년 발언(국채 7% "
        "→ 최소 10%)에서 인용자가 유도한 해석입니다. 버핏은 2007년에 \"we "
        "don't formally have discount rates\"라고 말했습니다.",
    ]})
    b.append({"t": "p", "x":
              "**그래서 가장 정직한 답은 이것입니다.** 제기하신 의문의 "
              "전제(\"10년차 3.5%는 10년간 성장률\")는 사실이 아니었고, 실제 "
              "가정(중립 10년 평균 6.6~9.2%, 낙관 11.9~14.6%)은 이 규모 기업의 "
              "역사적 분포에서 **중위값 위, 상위 20% 안쪽**입니다. 할인율을 "
              "버핏 기준으로 낮추면 가치는 크게 오르지만, 버핏이 함께 요구하는 "
              "안전마진을 적용하면 마이크로소프트와 알파벳은 여전히 불합격이고 "
              "엔비디아만 — 과거 성장이 유지된다는 전제에서 — 합격합니다."})
    b.append({"t": "note", "x":
              f"출처: 기초율 {BR['source']} ({BR['source_url']}) · "
              f"거시 FRED T10YIE, 국채 수익률 · 버핏 1차 출처 "
              f"https://www.berkshirehathaway.com/letters/1992.html · "
              f"검증 1,132건 통과, 변이 27건 포착."})
    return b


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
        elif t == "p":
            out += [b["x"], ""]
        elif t == "note":
            out += [f"> {b['x']}", ""]
        elif t == "quote":
            out += [f"> “{b['x']}”", ">",
                    f"> — {b.get('src', '')}", ""]
        elif t == "formula":
            out += ["```"] + b["x"].split("\n") + ["```", ""]
        elif t == "bullets":
            out += [f"- {x}" for x in b["x"]] + [""]
        elif t == "table":
            h = b["headers"]
            align = ["left"] + ["right"] * (len(h) - 1)
            if len(h) <= 2:
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
            blk["src"] = b.get("src", "")
        elif x is not None:
            blk["text"] = x
        if blk["t"] == "table" and "widths" not in blk:
            n = len(blk["headers"])
            first = max(12, min(34, int(100 / n) + 12))
            blk["widths"] = [first] + [(100 - first) / (n - 1)] * (n - 1)
            blk["numeric"] = list(range(1, n))
        payload.append(blk)
    with open(DOCX_JSON, "w", encoding="utf-8") as fh:
        json.dump({"title": "성장률 재검증 · 버핏 기준 적정주가",
                   "blocks": payload}, fh, indent=1, ensure_ascii=False)
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
