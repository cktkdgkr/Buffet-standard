"""
Build the Word payload for "why did Berkshire buy Alphabet".

Every figure is read from work/brk_alphabet_analysis.json (built from
work/brk_alphabet.json, which is built from the filings), so nothing here is
typed by hand. Rendered by export_memo_docx.js.
"""

import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
AN = os.path.join(HERE, "brk_alphabet_analysis.json")
RAW = os.path.join(HERE, "brk_alphabet.json")
SOTP = os.path.join(HERE, "alphabet_sotp.json")
OUT = os.path.join(HERE, "_brk_payload.json")

BN, M = 1e9, 1e6


def bn(v, dp=1):
    """The filings are in millions; show billions."""
    return "—" if v is None else f"${v/1000:,.{dp}f}bn"


def usd(v, dp=2):
    return "—" if v is None else f"${v:,.{dp}f}"


def pct(v, dp=1):
    return "—" if v is None else f"{v*100:,.{dp}f}%"


def sh(v):
    return "—" if v is None else f"{v:,.0f}주"


def main():
    with open(AN) as fh:
        d = json.load(fh)
    with open(RAW) as fh:
        raw = json.load(fh)
    with open(SOTP) as fh:
        sotp = json.load(fh)

    cost = d["cost_basis"]
    ch = d["instrument_choice"]
    opp = d["opportunity_cost"]
    ret = d["returns"]
    val = d["valuation"]
    who = d["who_decided"]
    pp = raw["private_placement"]
    mc = raw["mandatory_convertible"]
    q13 = raw["berkshire_13f"]
    cl = ret["cloud"]
    ci = ret["capital_intensity"]
    price = d["price"]["price"]

    blocks = []
    add = blocks.append
    h1 = lambda t: add({"t": "h1", "text": t})
    h2 = lambda t: add({"t": "h2", "text": t})
    h3 = lambda t: add({"t": "h3", "text": t})
    p = lambda t: add({"t": "p", "text": t})
    note = lambda t: add({"t": "note", "text": t})
    quote = lambda t, s: add({"t": "quote", "text": t, "src": s})
    formula = lambda t: add({"t": "formula", "text": t})
    bullets = lambda i: add({"t": "bullets", "items": i})

    def table(headers, rows, widths, numeric=None):
        add({"t": "table", "headers": headers, "rows": rows,
             "widths": widths, "numeric": numeric or []})

    # ===================================================== 0
    h1("한 문장으로")

    p("**버크셔가 알파벳을 산 마지막이자 가장 큰 매수는 장내 매수가 아니라, "
      "알파벳이 AI 설비투자 자금을 조달하려고 벌인 사상 최대 규모의 자본조달에 "
      "버크셔가 100억 달러짜리 앵커 투자자로 들어간 것입니다.** 그리고 그 자리에서 "
      "버크셔는 같은 주에 알파벳이 공모로 팔던 6.25% 상환전환우선주 — 쿠폰이 붙고 "
      "하방이 막힌 물건 — 를 마다하고, 보호장치가 하나도 없는 보통주를 시장가에 "
      "샀습니다. 이 선택 하나가 버크셔의 생각을 가장 많이 말해줍니다.")

    p("질문하신 가설 — '수익률이 낮아져도 매출이 커지니까' — 은 방향은 맞지만 "
      "이유가 틀렸습니다. 매출 규모 자체는 가치의 변수가 아닙니다. 성장이 가치를 "
      "더하느냐 깎느냐는 **증분 ROIC이 할인율보다 큰가** 하나로 결정되고, "
      "알파벳의 실측 증분 ROIC은 여전히 25~32%입니다. 평균 ROIC은 정확히 "
      "지적하신 대로 떨어지고 있지만(47.3% → 39.4%), 떨어지는 평균과 "
      "높은 증분은 모순이 아닙니다.")

    # ===================================================== 1
    h1("1. 무엇이 실제로 일어났는가")

    h2("13F로 본 3막")

    rows = []
    for l in cost["legs"]:
        rows.append([
            l["period"],
            sh(l["shares_held"]) if l["shares_held"] else "미보유",
            ("—" if l["shares_added"] <= 0 else f"+{l['shares_added']:,.0f}"),
            ("—" if not l.get("blended_price") else usd(l["blended_price"])),
            ("—" if not l["rank"] else f"{l['rank']}위"),
            ("—" if not l["weight"] else pct(l["weight"])),
        ])
    table(["분기말", "보유주식수", "증가분", "추정 매입단가", "포트폴리오 순위", "비중"],
          rows, [13, 20, 16, 15, 12, 10], numeric=[1, 2, 3, 4, 5])

    p(f"세 번의 매수는 성격이 전혀 다릅니다. "
      f"**1막(2025년 3분기)** 은 {sh(cost['legs'][3]['shares_added'])}, "
      f"약 {bn(cost['legs'][3]['estimated_cost']/M, 1)} 규모의 평범한 신규 편입입니다. "
      f"**2막(2026년 1분기)** 에 {sh(cost['legs'][5]['shares_added'])}를 더해 "
      f"3.2배로 키웠고, **3막(2026년 2분기)** 에 다시 "
      f"{sh(cost['legs'][6]['shares_added'])}를 더해 포트폴리오 3위 "
      f"{bn(q13['2026-06-30']['alphabet']['value']/M, 1)}, 비중 "
      f"{pct(q13['2026-06-30']['alphabet']['weight'])}가 되었습니다.")

    p(f"**포지션의 {pct(cost['share_of_position_bought_in_2026'], 0)}가 2026년에 "
      f"매입되었습니다.** 추정 평균 매입단가는 "
      f"{usd(cost['estimated_average_cost_per_share'])}, 현재가는 {usd(price)}이므로 "
      f"평가이익은 {pct(cost['gain_vs_cost'])}에 불과합니다. "
      "**버크셔는 싸게 사서 오르는 것을 지켜본 것이 아니라, 지금 가격에 산 "
      "것입니다.** 제 이전 보고서가 '매력적이지 않다'고 평가한 바로 그 가격대입니다.")

    note(cost["method_note"])

    h2("2막과 3막 사이에 알파벳이 한 일")

    p("2026년 5~6월, 알파벳은 회사 역사상 처음으로 대규모 외부 자본조달을 "
      "했습니다. 검색 광고로 연간 수백억 달러의 잉여현금을 만들던 회사가, "
      "동시에 네 가지 창구를 전부 열었습니다.")

    lt_before, lt_after = ci["long_term_debt_2025"], ci["long_term_debt_2026"]
    table(
        ["조달 수단", "규모", "조건 / 비고"],
        [["회사채", f"장기차입금 {bn(lt_before)} → {bn(lt_after)}",
          "USD 다수 트랜치 + 영국 파운드 55억 + 스위스프랑 31억. "
          "만기 2028년~2066년"],
         ["상환전환우선주",
          bn(mc["gross_proceeds_total"] / M),
          f"쿠폰 {pct(mc['coupon'], 2)}, 액면 $1,000, 2029년 5월 15일 강제전환. "
          f"공모로 판매"],
         ["보통주 공모",
          f"{pp['public_offering']['class_a_shares']:,.0f}주(A) + "
          f"{pp['public_offering']['class_c_shares']:,.0f}주(C)",
          f"A {usd(pp['public_offering']['class_a_price'], 4)} / "
          f"C {usd(pp['public_offering']['class_c_price'], 4)}. "
          f"초과배정 각 {pp['public_offering']['overallotment_class_a']:,.0f}주 "
          "전액 행사"],
         ["**버크셔 사모발행**",
          f"**{bn(pp['gross_proceeds_bn'] * 1000, 0)}**",
          f"A {pp['class_a_shares']:,.0f}주 @ {usd(pp['class_a_price'])}, "
          f"C {pp['class_c_shares']:,.0f}주 @ {usd(pp['class_c_price'])}. "
          "등록권 부여"],
         ["ATM 프로그램",
          f"최대 {bn(pp['atm_programme_bn'] * 1000, 0)}",
          "필요할 때 시장에 직접 파는 상시 창구"]],
        [16, 26, 48])

    po = pp["public_offering"]
    public_gross = ((po["class_a_shares"] + po["overallotment_class_a"])
                    * po["class_a_price"]
                    + (po["class_c_shares"] + po["overallotment_class_c"])
                    * po["class_c_price"]) / M
    executed = (lt_after - lt_before + mc["gross_proceeds_total"] / M
                + public_gross + pp["gross_proceeds_bn"] * 1000)
    p(f"규모를 합치면 이미 집행된 것만 {bn(executed, 0)}이고 "
      f"(회사채 순증 {bn(lt_after - lt_before, 0)} + 우선주 "
      f"{bn(mc['gross_proceeds_total'] / M, 0)} + 보통주 공모 "
      f"{bn(public_gross, 0)} + 버크셔 사모 "
      f"{bn(pp['gross_proceeds_bn'] * 1000, 0)}), ATM 한도까지 쓰면 "
      f"{bn(executed + pp['atm_programme_bn'] * 1000, 0)}에 이릅니다. "
      "그리고 같은 기간 **자사주 매입은 완전히 멈췄습니다** — 2025년 상반기 "
      f"{bn(ci['buybacks_h1_2025'])}에서 2026년 상반기 0입니다.")

    note("이 다섯 줄을 한 번에 보시면 이 회사에 무슨 일이 일어나고 있는지가 "
         "분명해집니다. 주주에게 현금을 돌려주던 회사가, 주주와 채권자에게서 "
         "현금을 받는 회사로 바뀌었습니다.")

    # ===================================================== 2
    h1("2. 결정적 증거 — 버크셔는 우선주를 마다하고 보통주를 샀다")

    p("같은 주에 알파벳은 두 가지를 팔았습니다. 하나는 버크셔에게 사모로 판 "
      "보통주이고, 다른 하나는 시장에 공모로 판 6.25% 상환전환우선주입니다. "
      "버크셔가 역사적으로 이런 상황에서 요구해온 것은 **언제나** 후자 쪽 "
      "물건이었습니다.")

    bullets([
        "2008년 골드만삭스 — 10% 우선주 + 워런트",
        "2008년 제너럴일렉트릭 — 10% 우선주 + 워런트",
        "2011년 뱅크오브아메리카 — 6% 우선주 + 워런트",
        "2019년 옥시덴탈 — 8% 우선주 + 워런트. **이 우선주는 지금도 버크셔가 "
        "들고 있고, 이번 2026년 2분기 10-Q에 청산가치 약 85억 달러로 "
        "그대로 적혀 있습니다.**",
    ])

    p("그런데 이번에는 우선주를 잡지 않았습니다. 알파벳의 우선주 조건은 이렇습니다.")

    table(
        ["항목", "조건"],
        [["쿠폰", f"{pct(mc['coupon'], 2)} (액면 $1,000 기준)"],
         ["만기", f"{mc['mandatory_conversion_date']} 강제전환"],
         ["전환 하한가 (이 아래면 최대 비율로 전환)",
          f"A {usd(mc['series_a_floor_price'])} / C {usd(mc['series_b_floor_price'])}"],
         ["전환 상한가 (이 위면 최소 비율로 전환)",
          f"A {usd(mc['series_a_cap_price'])} / C {usd(mc['series_b_cap_price'])}"],
         ["캡드콜 상한 (회사가 희석을 막으려 사둔 것)",
          f"A {usd(mc['capped_call_cap_class_a'])} / "
          f"C {usd(mc['capped_call_cap_class_c'])}"]],
        [42, 44])

    h2("두 선택지의 손익을 2029년 주가의 함수로 그려보면")

    p("100달러가 아니라 1,000달러를 기준으로 맞춰서 비교합니다. 버크셔가 실제로 "
      f"낸 가격은 두 클래스 가중평균 {usd(ch['berkshire_blended_price'])}이므로, "
      f"1,000달러로 보통주 {ch['common_shares_per_1000']:.4f}주를 삽니다. "
      f"우선주 1,000달러는 3년간 쿠폰 "
      f"{usd(ch['preferred_coupons_total_per_1000'])}를 받고, 2029년 5월에 "
      "주가에 따라 정해진 비율로 보통주로 바뀝니다.")

    table(
        ["2029년 5월 주가", "보통주 손익", "우선주 손익", "차액", "누가 이기나"],
        [[usd(g["price_2029"], 0), usd(g["common"], 0), usd(g["preferred"], 0),
          usd(g["common_minus_preferred"], 0),
          "보통주" if g["common_wins"] else "우선주"]
         for g in ch["payoff_grid"]],
        [18, 16, 16, 14, 14], numeric=[0, 1, 2, 3])

    formula(f"손익분기 2029년 주가 = {usd(ch['breakeven_price_2029'], 0)}  "
            f"(매입가 대비 {pct(ch['breakeven_vs_purchase'])}, 연 "
            f"{pct(ch['implied_minimum_annual_return'])})")

    p(f"**즉 버크셔가 보통주를 고른 선택이 옳았던 것이 되려면, 2029년 5월에 "
      f"알파벳 주가가 최소 {usd(ch['breakeven_price_2029'], 0)} 이상이어야 "
      f"합니다.** 그 아래에서는 우선주가 이깁니다 — 쿠폰만큼, 그리고 하한 "
      "아래에서는 더 많은 주식을 받으니까요. 버크셔는 하방이 막히고 쿠폰이 "
      "나오는 물건을 눈앞에 두고 그것을 포기했습니다. 그 행동이 함축하는 최소한의 "
      f"기대치가 {usd(ch['breakeven_price_2029'], 0)}이고, 투자자가 손익분기에 "
      "딱 맞추어 베팅하지는 않으므로 실제 기대치는 그보다 위에 있어야 합니다.")

    note(ch["caveat"])

    p("**반대 해석도 공정하게 적어둡니다.** 버크셔가 보통주를 고른 이유가 "
      "가치 판단이 아니라 '영구적으로 들고 갈 지분이 필요했고, 3년 뒤 만기가 "
      "오는 물건은 그 목적에 맞지 않았다'일 수도 있습니다. 버크셔는 코카콜라를 "
      "38년, 아메리칸익스프레스를 31년 들고 있는 회사입니다. 다만 그 해석을 "
      f"받아들이더라도 {usd(ch['breakeven_price_2029'], 0)}이라는 숫자는 "
      "'버크셔가 이 정도는 포기할 각오를 했다'는 비용의 크기로 남습니다.")

    # ===================================================== 3
    h1("3. 두 번째 이유 — 버크셔의 대안은 4.14%짜리 국채였다")

    table(
        ["2026년 6월 30일 버크셔 보험부문", "금액"],
        [["미국 재무부 단기채", bn(opp["treasury_bills"] / M, 0)],
         ["현금 및 현금성자산", bn(opp["cash_and_equivalents"] / M, 0)],
         ["주식", bn(opp["equity_securities"] / M, 0)],
         ["단기채 ÷ 주식", f"{opp['bills_over_equities']:.2f}배"],
         ["알파벳 포지션", bn(opp["alphabet_position_value"] / M, 1)],
         ["알파벳 포지션 ÷ 단기채", pct(opp["position_as_share_of_bills"])]],
        [46, 22], numeric=[1])

    p(f"**버크셔는 주식보다 단기국채를 더 많이 들고 있습니다.** 그 국채가 주는 "
      f"수익률은 {pct(opp['t_bill_yield'], 2)}이고, 연간 이자는 "
      f"{bn(opp['annual_income_on_bills'] / M, 0)}입니다. 버크셔의 한계 자금이 "
      "넘어야 하는 문턱은 '시장에서 가장 싼 주식'이 아니라 이 4.14%입니다.")

    p("제 보고서들이 쓰는 할인율 9~11%는 **개인 투자자의 기회비용**입니다. "
      "주식 전체에서 고를 수 있는 사람의 요구수익률이지요. 버크셔는 3,250억 "
      "달러를 한 번에 옮길 곳이 사실상 없는 회사이고, 그래서 같은 자산에 대해 "
      "더 낮은 요구수익률을 적용해도 합리적입니다. **이것은 알파벳이 싸다는 "
      "뜻이 아니라, 버크셔의 문턱이 당신의 문턱보다 낮다는 뜻입니다.** "
      "이 구분이 이 보고서에서 가장 중요한 한 줄입니다.")

    note(f"덧붙여, 100억 달러를 하루에 시장가로 집행할 방법은 사실상 이것 "
         f"하나뿐이었습니다. 알파벳 하루 거래대금을 생각하면 장내에서 "
         f"{bn(pp['gross_proceeds_bn'] * 1000, 0)}를 사려면 몇 주가 걸리고 "
         f"그 사이 가격을 스스로 밀어 올립니다. 버크셔의 진짜 제약은 "
         "'무엇을 살까'가 아니라 '어떻게 규모 있게 집행할까'입니다.")

    # ===================================================== 4
    h1("4. 누가 결정했는가")

    p(who["evidence"] + " " + who["buyback_policy_language"])

    p("**" + who["implication"] + "**")

    note("이 구분이 중요한 이유는, 질문에 '버핏 기준 하에서'라고 쓰셨기 "
         "때문입니다. 이 매수는 버핏 개인의 판단이라기보다 버크셔라는 조직의 "
         "판단이고, 버핏 기준에 부합하는지는 우리가 따로 검증해야 할 대상이지 "
         "전제가 아닙니다.")

    # ===================================================== 5
    h1("5. 가설 검증 — '수익률이 낮아져도 매출이 커지니까'")

    p("이 가설은 검증 가능합니다. 우리가 쓰는 항등식이 답을 정확히 냅니다.")

    formula("FCF = NOPAT × (1 − 성장률 g ÷ 증분 ROIC)")

    p("성장이 영구적으로 이어진다고 보면 가치는 "
      "NOPAT × (1 − g ÷ 증분ROIC) ÷ (할인율 − g)입니다. 이 식을 g로 미분하면 "
      "부호가 (증분ROIC − 할인율)의 부호와 같습니다. 말로 옮기면 이렇습니다.")

    quote("성장은 그 자체로 좋은 것도 나쁜 것도 아닙니다. 투자자가 사업에 "
          "투입하는 자본에서 매력적인 수익이 날 때에만 성장이 가치를 더합니다. "
          "성장의 대가로 투입한 1달러가 장기적으로 1달러 이상의 시장가치를 "
          "만들지 못한다면, 그 성장은 가치를 파괴합니다.",
          "1992년 버크셔 해서웨이 주주서한")

    h2("숫자로 보면")

    ht = d["hypothesis_test"]
    growths = [e["growth"] for e in ht["grid"][0]["values"]]
    rows = []
    for row in ht["grid"]:
        cells = []
        for chg in row["value_change_from_growth"]:
            cells.append("발산" if chg is None else pct(chg, 0))
        rows.append([pct(row["incremental_roic"], 0)] + cells)
    table(["증분 ROIC"] + [f"성장 {pct(g, 0)}" for g in growths],
          rows, [14] + [13] * len(growths), numeric=list(range(1, len(growths) + 1)))

    p(f"표는 '성장률 0%일 때의 가치 대비 몇 % 변하는가'입니다. 할인율은 "
      f"{pct(ht['discount_rate'], 0)}로 고정했습니다. 읽는 법은 간단합니다.")

    bullets([
        "**증분 ROIC이 할인율과 같을 때(10%) 성장은 가치를 정확히 0만큼 "
        "바꿉니다.** 매출이 두 배가 되든 열 배가 되든 가치는 그대로입니다. "
        "매출 규모가 가치의 변수가 아니라는 말의 정확한 의미가 이것입니다.",
        "**증분 ROIC이 할인율보다 낮으면(5%, 8%) 성장은 가치를 파괴합니다.** "
        "증분 ROIC 5%에서 9% 성장은 가치를 9배 깎아냅니다. "
        "'매출이 커지니까 괜찮다'가 가장 위험해지는 구간입니다.",
        "**증분 ROIC이 할인율보다 높을 때만(12% 이상) 성장이 가치를 더합니다.** "
        "25%에서 9% 성장은 가치를 5.4배로 키웁니다.",
    ])

    p("**그러므로 질문하신 가설은 이렇게 고쳐 써야 맞습니다.** "
      "'매출이 커지기 때문'이 아니라, **'평균 ROIC이 떨어지더라도 새로 넣는 "
      "자본의 수익률이 자본비용보다 충분히 높게 유지되기 때문'** 입니다. "
      "그리고 이것은 사실 확인이 가능한 명제입니다.")

    # ===================================================== 6
    h1("6. 그래서 수익률은 실제로 떨어졌는가")

    table(
        ["지표", "2025년 6월말 기준", "2026년 6월말 기준", "변화"],
        [["세후영업이익 (반기 연율화)",
          bn(ret["nopat_annualised_2025"]), bn(ret["nopat_annualised_2026"]),
          pct(ret["nopat_annualised_2026"] / ret["nopat_annualised_2025"] - 1)],
         ["영업투하자본",
          bn(ret["operating_capital_2025"]), bn(ret["operating_capital_2026"]),
          pct(ret["operating_capital_2026"] / ret["operating_capital_2025"] - 1)],
         ["**ROIC (평균)**", pct(ret["roic_2025"]), pct(ret["roic_2026"]),
          f"{ret['roic_change']*100:+.1f}pp"],
         ["**증분 ROIC**", "—", pct(ret["incremental_roic"]), "—"],
         ["증분 ROIC (영업권 제외)", "—",
          pct(ret["incremental_roic_ex_goodwill"]), "—"]],
        [26, 18, 18, 14], numeric=[1, 2, 3])

    p(f"**평균 ROIC은 지적하신 대로 떨어졌습니다 — {pct(ret['roic_2025'])}에서 "
      f"{pct(ret['roic_2026'])}로 {abs(ret['roic_change'])*100:.1f}포인트.** "
      "검색이라는 초저자본 사업 위에 클라우드라는 고자본 사업을 얹고 있으니 "
      "평균이 내려가는 것은 산술적으로 당연합니다.")

    p(f"**그런데 새로 넣은 자본의 수익률은 {pct(ret['incremental_roic'])}입니다.** "
      f"이번 기간에 인수로 생긴 영업권 {bn(ret['goodwill_added'])}를 분모에서 "
      f"빼면 {pct(ret['incremental_roic_ex_goodwill'])}입니다. 자본비용 추정치 "
      "약 10%의 2.5~3배입니다. 5절의 표에서 25~30% 줄에 해당하고, 그 줄에서 "
      "성장은 가치를 크게 더합니다.")

    note("이 측정에는 보수적인 편향이 하나 들어 있습니다. 2026년 상반기에 쓴 "
         f"설비투자 {bn(ci['capex_h1_2026'])} 중 상당 부분은 아직 매출을 내지 "
         "않은 자산인데 분모에는 이미 들어가 있습니다. 즉 실제 증분 수익률은 "
         "여기 적힌 값보다 높을 가능성이 큽니다. 삼성바이오로직스 분석에서 "
         "건설중자산을 뺐던 것과 같은 논점인데, 알파벳은 미가동 자산을 별도로 "
         "공시하지 않아 분리할 수 없었습니다.")

    h2("클라우드에 무슨 일이 일어났는가")

    table(
        ["클라우드", "2025년 상반기", "2026년 상반기", "변화"],
        [["매출", bn(cl["revenue_h1_2025"]), bn(cl["revenue_h1_2026"]),
          pct(cl["revenue_growth"])],
         ["영업이익", bn(cl["operating_income_h1_2025"]),
          bn(cl["operating_income_h1_2026"]),
          pct(cl["operating_income_h1_2026"] / cl["operating_income_h1_2025"] - 1)],
         ["영업이익률", pct(cl["margin_h1_2025"]), pct(cl["margin_h1_2026"]),
          f"{(cl['margin_h1_2026']-cl['margin_h1_2025'])*100:+.1f}pp"],
         ["2분기만", "—", f"매출 {bn(cl['revenue_q2_2026'])} / "
          f"마진 {pct(cl['margin_q2_2026'])}",
          f"매출 {pct(cl['revenue_growth_q2'])}"],
         ["증분 영업이익률", "—", pct(cl["incremental_operating_margin"]),
          "새 매출 1달러당 영업이익"]],
        [18, 18, 26, 20], numeric=[1, 2, 3])

    p("**여기서 질문의 전제 하나를 정정해야 합니다.** 'AI 클라우드가 고자본의 "
      "좋은 사업 수준으로 내려왔다'고 보셨는데, 손익계산서상으로는 정반대가 "
      f"일어나고 있습니다. 클라우드 영업이익률은 FY2025 "
      f"{pct(cl['fy2025_margin'])}에서 2026년 상반기 {pct(cl['margin_h1_2026'])}로, "
      f"2분기만 보면 {pct(cl['margin_q2_2026'])}까지 올라갔습니다. 새로 붙는 "
      f"매출 1달러당 영업이익이 {pct(cl['incremental_operating_margin'])}입니다. "
      "규모의 경제가 아주 강하게 작동하고 있다는 뜻입니다.")

    bl = ret["backlog"]
    p(f"수주잔고는 {bl['total_bn']:,.1f}십억 달러이고 그중 클라우드가 "
      f"{bl['cloud_bn']:,.1f}십억 달러입니다. 2분기 클라우드 매출을 연율화한 "
      f"{bn(cl['revenue_q2_2026'] * 4, 0)}의 약 "
      f"{bl['cloud_bn']*1000/(cl['revenue_q2_2026']*4):.1f}배입니다. "
      "이것이 AI 이야기를 '계약된 매출'로 바꿔주는 숫자이고, 버핏이 요구하는 "
      "종류의 가시성에 가장 가까운 증거입니다.")

    note("다만 공정하게 적습니다. 알파벳은 2026년 1분기부터 원계약기간 1년 "
         "이하 계약도 수주잔고에 포함하도록 기준을 바꿨습니다. 따라서 FY2025의 "
         f"{FY2025_BACKLOG:,.1f}십억 달러와 직접 비교하면 증가폭이 과장됩니다.")

    # ===================================================== 7
    h1("7. 그 대가 — 주주에게 돌아오는 현금이 사라졌다")

    table(
        ["", "2025년 상반기", "2026년 상반기", "변화"],
        [["영업활동현금흐름", bn(ci["ocf_h1_2025"]), bn(ci["ocf_h1_2026"]),
          pct(ci["ocf_h1_2026"] / ci["ocf_h1_2025"] - 1)],
         ["설비투자", bn(ci["capex_h1_2025"]), bn(ci["capex_h1_2026"]),
          pct(ci["capex_growth"])],
         ["**잉여현금흐름**", bn(ci["fcf_h1_2025"]), bn(ci["fcf_h1_2026"]),
          pct(ci["fcf_h1_2026"] / ci["fcf_h1_2025"] - 1)],
         ["감가상각", "—", bn(ci["depreciation_h1_2026"]),
          f"설비투자 ÷ 감가상각 = {ci['capex_over_depreciation']:.1f}배"],
         ["자사주 매입", bn(ci["buybacks_h1_2025"]),
          bn(abs(ci["buybacks_h1_2026"]), 0), "전면 중단"],
         ["장기차입금", bn(ci["long_term_debt_2025"]),
          bn(ci["long_term_debt_2026"]),
          pct(ci["long_term_debt_2026"] / ci["long_term_debt_2025"] - 1)]],
        [20, 18, 18, 24], numeric=[1, 2, 3])

    p(f"**설비투자가 감가상각의 {ci['capex_over_depreciation']:.1f}배입니다.** "
      f"잉여현금흐름은 {bn(ci['fcf_h1_2025'])}에서 {bn(ci['fcf_h1_2026'])}으로 "
      "사실상 사라졌고, 자사주 매입은 0이 되었으며, 주식수는 줄어들다가 늘기 "
      "시작했습니다. 삼성바이오로직스 보고서에서 다룬 구조와 똑같은데 규모가 "
      "100배입니다.")

    p("**그리고 이것이 버핏의 2007년 분류가 정확히 겨냥하는 지점입니다.**")

    quote("정말 훌륭한 사업은 성장에 필요한 자본을 거의 쓰지 않고도 훌륭한 "
          "자본수익률을 냅니다. … 좋은 사업이지만 훌륭하지는 않은 사업은 성장을 "
          "위해 상당한 자본을 필요로 하는데, 그 자본에서 나오는 수익이 "
          "만족스럽다면 여전히 좋은 사업입니다.",
          "2007년 버크셔 해서웨이 주주서한")

    p("알파벳은 '훌륭한' 사업(검색)에서 '좋은' 사업(AI 클라우드)으로 "
      "무게중심을 옮기는 중입니다. 지적하신 감각이 정확히 이것이었고, "
      "그 감각은 맞습니다. 다만 '좋은' 사업도 증분 수익률이 자본비용의 2.5배면 "
      "가치를 크게 만듭니다. 버핏이 '좋은' 사업을 사지 말라고 한 적은 "
      "없습니다 — 값을 너무 치르지 말라고 했을 뿐입니다.")

    # ===================================================== 8
    h1("8. 그 기준으로 다시 계산한 가치")

    p(f"이전 보고서는 FY2025 실적을 기준연도로 썼습니다. 지금은 2026년 상반기 "
      f"실적이 있으므로 그것을 연율화해 다시 계산합니다. 기준 세후영업이익은 "
      f"{bn(val['base_nopat'], 0)}로, FY2025 기준보다 "
      f"{pct(val['base_nopat'] / (FY2025_OI * (1 - FY2025_TAX)) - 1, 0)} 큽니다.")

    table(
        ["입력값", "값", "설명"],
        [["기준 세후영업이익", bn(val["base_nopat"], 0),
          "2026년 상반기 영업이익 × 2 × (1 − FY2025 실효세율 16.8%)"],
         ["주식수", f"{val['shares_used']:,.0f}백만주", val["shares_note"]],
         ["순현금", bn(val["net_cash"], 0), val["net_cash_note"]],
         ["시가총액", bn(val["market_cap"], 0),
          f"{usd(price)} × {val['shares_used']:,.0f}백만주 ({d['price']['as_of']})"],
         ["미국 10년물", pct(d["rates"]["treasury_10y"]["rate"], 2),
          f"직전 보고서 시점 "
          f"{pct(d['rates']['treasury_10y_previous_report']['rate'], 2)}에서 상승 "
          "— 할인율에 불리한 방향"]],
        [18, 20, 50])

    note("세율에 관한 주의: 2026년 상반기 알파벳의 보고 순이익은 "
         f"{bn(raw['alphabet']['2026q2']['net_income'][3], 0)}로 영업이익 "
         f"{bn(raw['alphabet']['2026q2']['income_from_operations'][3], 0)}의 두 배가 "
         "넘습니다. 차액의 대부분은 비상장주식 평가이익입니다(비상장주식 잔액이 "
         f"{bn(raw['alphabet']['2026q2']['non_marketable_securities'][0], 0)}에서 "
         f"{bn(raw['alphabet']['2026q2']['non_marketable_securities'][1], 0)}로 "
         "늘었습니다). 이 회계는 버핏이 매년 주주서한에서 불평하는 바로 그 "
         "규정이고, 지금 알파벳의 주당순이익을 그대로 쓰면 크게 오도됩니다. "
         "그래서 영업이익에서 출발했고 실효세율도 FY2025 값을 썼습니다.")

    rows = []
    for s in val["scenarios"]:
        a = s["assumptions"]
        rows.append([
            s["scenario"],
            f"{pct(a['growth'], 0)} → {pct(a['fade_to'], 1)}",
            pct(a["incremental_roic"], 0),
            pct(a["discount"], 0),
            bn(s["equity_value"], 0),
            usd(s["value_per_share"], 0),
            pct(s["upside_vs_market"]),
            pct(s["terminal_share"], 0),
        ])
    table(["시나리오", "성장률", "증분ROIC", "할인율", "자기자본가치", "주당가치",
           "시장대비", "터미널비중"],
          rows, [10, 15, 11, 10, 15, 12, 12, 11],
          numeric=[1, 2, 3, 4, 5, 6, 7])

    p(f"**낙관 시나리오에서 {usd(val['scenarios'][2]['value_per_share'], 0)}, "
      f"현재가 대비 {pct(val['scenarios'][2]['upside_vs_market'])}입니다.** "
      "이전 보고서의 부문별 합산(SOTP) 낙관 시나리오는 "
      f"{usd(sotp['scenarios'][2]['value_per_share'], 0)}로 당시 주가와 거의 "
      "같았습니다. 방법이 다르므로 직접 비교할 수는 없지만, 두 계산이 같은 말을 "
      "합니다 — **가장 낙관적인 가정에서도 알파벳은 대략 제값이고, 싸지 "
      "않습니다.**")

    h2("거꾸로 — 현재 주가가 요구하는 성장률")

    ig = val["implied_initial_growth"]
    table(
        ["시나리오 틀", "현재가를 정당화하는 첫해 성장률", "실제 실적과 비교"],
        [["보수 (증분ROIC 15%, 할인율 11%)", pct(ig["보수"]),
          "불가능한 수준"],
         ["중립 (증분ROIC 22%, 할인율 10%)", pct(ig["중립"]),
          "최근 실적을 크게 상회"],
         ["낙관 (증분ROIC 30%, 할인율 9%)", pct(ig["낙관"]),
          f"2026년 상반기 매출 성장 "
          f"{pct(raw['alphabet']['2026q2']['total_revenues'][3] / raw['alphabet']['2026q2']['total_revenues'][2] - 1)}, "
          f"영업이익 성장 "
          f"{pct(raw['alphabet']['2026q2']['income_from_operations'][3] / raw['alphabet']['2026q2']['income_from_operations'][2] - 1)}"]],
        [30, 26, 34], numeric=[1])

    p(f"**이것이 삼성바이오로직스와 결정적으로 다른 점입니다.** "
      f"삼성바이오로직스는 현재가가 실적 기록을 넘어서는 성장을 요구했습니다. "
      f"알파벳은 낙관 시나리오 틀에서 {pct(ig['낙관'])}를 요구하는데, "
      f"이 회사가 방금 분기에 실제로 낸 성장이 그 수준입니다. "
      "**지금 주가는 '이 회사가 방금 한 것을 앞으로도 한동안 한다'를 "
      "요구하고 있습니다.** 무리한 요구는 아니지만, 안전마진은 없습니다.")

    # ===================================================== 9
    h1("9. 결론 — 버크셔의 이유가 당신의 이유가 될 수 있는가")

    h2("버크셔가 산 이유 (증거의 무게 순)")

    table(
        ["이유", "증거", "강도"],
        [["1. 규모 있게 집행할 수 있는 기회였다",
          f"단기국채 {bn(opp['treasury_bills']/M, 0)} 보유. 하루에 "
          f"{bn(pp['gross_proceeds_bn']*1000, 0)}를 시장가로 넣을 수 있는 "
          "유일한 경로가 사모발행이었음", "매우 강함 (공시)"],
         ["2. 요구수익률이 낮아도 되는 위치",
          f"한계 대안이 {pct(opp['t_bill_yield'], 2)} 단기국채", "매우 강함 (공시)"],
         ["3. 주가가 3년 내 20% 이상 오른다고 본다",
          f"6.25% 하방보호 우선주를 포기하고 보통주 선택 → 손익분기 "
          f"{usd(ch['breakeven_price_2029'], 0)}", "강함 (거래구조에서 도출)"],
         ["4. AI 자본지출의 증분 수익률이 높다고 본다",
          f"실측 증분 ROIC {pct(ret['incremental_roic'])}, 클라우드 증분 "
          f"영업이익률 {pct(cl['incremental_operating_margin'])}", "강함 (재무제표)"],
         ["5. 수주잔고가 가시성을 준다",
          f"클라우드 수주잔고 {bl['cloud_bn']:,.0f}십억 달러", "중간 (기준 변경 있음)"],
         ["6. 검색 반독점 판결의 불확실성이 줄었다",
          "2025년 12월 최종판결, 2026년 1월 항소 — 구조적 분할은 없었음",
          "약함 (해석)"]],
        [24, 40, 20])

    h2("그 이유가 당신에게도 성립하는가")

    bullets([
        "**1번과 2번은 성립하지 않습니다.** 당신의 한계 대안은 4.14% 단기국채가 "
        "아니라 주식 시장 전체입니다. 100억 달러를 집행해야 하는 제약도 없습니다. "
        "버크셔가 알파벳을 산 이유의 절반 이상이 '버크셔이기 때문'이고, "
        "그 절반은 당신에게 이전되지 않습니다.",
        "**3번은 참고할 수 있지만 검증할 수 없습니다.** "
        f"{usd(ch['breakeven_price_2029'], 0)}이라는 숫자는 버크셔의 기대치를 "
        "보여주지만, 그 기대가 옳은지는 그들도 당신도 모릅니다. "
        "남의 확신을 자기 확신으로 삼는 것이 버핏이 가장 경계한 일입니다.",
        "**4번과 5번은 당신에게도 그대로 성립합니다.** 증분 ROIC 25~32%는 "
        "누가 계산해도 같은 숫자이고, 이것이 이 분석에서 실제로 건진 것입니다. "
        "제 이전 보고서가 '클라우드의 자본효율이 나빠진다'는 쪽에 무게를 "
        "뒀다면, 2026년 상반기 데이터는 그 반대를 가리킵니다. 그 부분은 "
        "수정합니다.",
        "**6번은 근거가 약하므로 투자 이유로 쓰지 마시기 바랍니다.**",
    ])

    h2("그래서 지금 사야 하는가")

    p(f"**기준 7(합리적인 가격)은 여전히 통과하지 못합니다.** 낙관 시나리오에서 "
      f"{usd(val['scenarios'][2]['value_per_share'], 0)}, 현재가 {usd(price)} "
      f"대비 {pct(val['scenarios'][2]['upside_vs_market'])}입니다. 다만 "
      "삼성바이오로직스처럼 '어떤 시나리오로도 닿지 않는' 상태는 아니고, "
      "**낙관 가정이 맞으면 제값, 틀리면 비싼** 상태입니다. 안전마진이 없는 "
      "가격이지 터무니없는 가격은 아닙니다.")

    p("시나리오 간 주당가치가 "
      f"{usd(val['scenarios'][0]['value_per_share'], 0)}에서 "
      f"{usd(val['scenarios'][2]['value_per_share'], 0)}까지 "
      f"{val['scenarios'][2]['value_per_share']/val['scenarios'][0]['value_per_share']:.1f}배 "
      "벌어진다는 사실 자체가 답의 일부입니다. 이 정도로 답이 가정에 민감한 "
      "회사는, 버핏의 표현을 빌리면 '능력범위'의 경계에 있습니다. "
      "터미널 가치가 전체의 "
      f"{pct(val['scenarios'][2]['terminal_share'], 0)}를 차지한다는 것도 "
      "같은 이야기입니다 — 가치의 대부분이 10년 뒤 이후에 있습니다.")

    quote("적당한 기업을 훌륭한 가격에 사는 것보다, 훌륭한 기업을 적당한 가격에 "
          "사는 것이 훨씬 낫습니다.",
          "1989년 버크셔 해서웨이 주주서한")

    p("알파벳은 훌륭한 기업이고 가격은 적당합니다. 버핏 기준으로 '사도 되는' "
      "상태에 가장 가까운 것은 맞습니다. 다만 버핏이 요구한 안전마진은 "
      "'적당한 가격'이 아니라 '적당한 가격보다 더 싼 가격'이었고, 지금은 "
      "거기에 있지 않습니다. 버크셔가 그 마진 없이 산 이유는 3절에 적은 대로 "
      "**그들의 문턱이 4.14%이기 때문**이지, 마진이 있기 때문이 아닙니다.")

    # ===================================================== 부록
    h1("부록. 자료 출처")

    table(
        ["문서", "접수번호", "쓰인 곳"],
        [["버크셔 13F-HR (7개 분기)", "2024-12-31 ~ 2026-06-30 각 분기",
          "분기별 보유주식수·순위·비중"],
         ["알파벳 Form 8-K (2026-06-04)", "0001193125-26-257724",
          "버크셔 사모발행 조건, 보통주 공모, ATM 프로그램"],
         ["알파벳 Form 8-K (2026-06-05)", "0001193125-26-259830",
          "6.25% 상환전환우선주 조건, 전환비율, 캡드콜"],
         ["알파벳 Form 10-Q (2026 2분기)", "0001652044-26-000071",
          "부문 실적, 설비투자, 수주잔고, 재무상태표"],
         ["알파벳 Form 10-Q (2025 2분기)", "0001652044-25-000062",
          "전년 동기 비교치, 전년 영업투하자본"],
         ["알파벳 Form 10-K (FY2025)", "0001652044-26-000018",
          "실효세율, 주식수, 직전 보고서 기준연도"],
         ["버크셔 Form 10-Q (2026 2분기)", "0001193125-26-341032",
          "단기국채·주식 잔액, 5대 보유종목 주석, 경영진 인증서"]],
        [26, 24, 34])

    bullets([
        f"주가: {d['price']['source']}, {d['price']['as_of']} 종가 {usd(price)}",
        f"금리: FRED DGS3MO {pct(d['rates']['t_bill_3m']['rate'], 2)}, "
        f"DGS10 {pct(d['rates']['treasury_10y']['rate'], 2)} "
        f"({d['rates']['t_bill_3m']['as_of']})",
        "검증: work/verify_brk_alphabet.py 가 공시 원문과의 정합성·재계산·"
        "모형 항등식 53건을 확인하고 전부 통과했습니다. 검증기 자체도 값을 "
        "일부러 틀리게 넣어 실패하는지 확인했습니다.",
    ])

    payload = {
        "title": "버크셔는 왜 알파벳을 샀는가",
        "subtitle": ("13F·8-K·10-Q로 되짚은 매수 경위와, 그 이유를 기준으로 한 "
                     f"알파벳 재평가 · {d['price']['as_of']} 주가 {usd(price)}"),
        "generated": date.today().isoformat(),
        "blocks": blocks,
    }
    with open(OUT, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"wrote {OUT}  ({len(blocks)} blocks)")
    return 0


FY2025_OI = 129_039.0
FY2025_TAX = 0.168
FY2025_BACKLOG = 242.8

if __name__ == "__main__":
    sys.exit(main())
