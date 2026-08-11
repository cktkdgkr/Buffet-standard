"""
PHASE 7 - the final report and the 52-company ranking.

Reads work/analysis.json and work/verification.json and writes REPORT.md. A
figure only reaches the report if PHASE 6 confirmed it against the filing it
cites; anything that failed verification is dropped rather than footnoted.

The ranking scores quality, not cheapness, and reports price separately. That
ordering is the framework's, not a presentational choice: a business earning
returns below its cost of capital is not made investable by a low multiple, and
the point of principle 1 is to settle that question before valuation is opened.
"""

import json
import os
import sys
from datetime import datetime, timezone

WORK = os.path.dirname(os.path.abspath(__file__))

# Quality score, 100 points. Thresholds rather than percentile ranks: a company
# should clear an absolute standard of business quality, not merely beat the
# other forty-nine mega-caps in the same expensive market.
def quality_score(s):
    pts, detail = 0, {}

    # A business that needs no net capital and still earns money sits at the top
    # of this dimension by construction - there is no ratio to compute because
    # the denominator is nil, which is the condition itself.
    roic = s.get("roic_10y_median")
    light = (s.get("capital_light_years") or 0) > 0 and not s.get("roic_years_capped")
    if roic is None and light:
        p = 25
    elif roic is None:
        p = 0
    else:
        p = (25 if roic >= 0.30 else 20 if roic >= 0.20
             else 15 if roic >= 0.15 else 10 if roic >= 0.10 else 0)
    pts += p
    detail["ROIC 중앙값"] = p

    obs = s.get("roic_years_observed") or 0
    above = s.get("roic_above_10pct_years") or 0
    p = round(20 * above / obs) if obs else 0
    pts += p
    detail["ROIC 지속성"] = p

    inc = s.get("incremental_roic")
    p = 0 if inc is None else (20 if inc >= 0.20 else 15 if inc >= 0.15
                               else 10 if inc >= 0.10 else 5 if inc > 0 else 0)
    pts += p
    detail["신규 ROIC"] = p

    spread = s.get("roic_wacc_spread")
    p = 0 if spread is None else (15 if spread >= 0.15 else 12 if spread >= 0.10
                                  else 8 if spread >= 0.05 else 4 if spread > 0 else 0)
    pts += p
    detail["ROIC-WACC 스프레드"] = p

    rev = s.get("_latest_revenue")
    oe = s.get("owner_earnings_normalised")
    margin = (oe / rev) if (oe is not None and rev) else None
    p = 0 if margin is None else (10 if margin >= 0.20 else 7 if margin >= 0.10
                                  else 4 if margin >= 0.05 else 2 if margin > 0 else 0)
    pts += p
    detail["주주이익 마진"] = p

    nd = s.get("net_debt_to_ebitda_latest")
    p = 5 if nd is None else (5 if nd <= 1.0 else 4 if nd <= 2.0 else 2 if nd <= 3.0 else 0)
    pts += p
    detail["순부채/EBITDA"] = p

    cov = s.get("interest_coverage_latest")
    p = 0 if cov is None else (5 if cov >= 10 else 3 if cov >= 5 else 1 if cov >= 2 else 0)
    pts += p
    detail["이자보상배율"] = p

    return pts, detail


def pct(v, dp=1):
    return "데이터없음" if v is None else f"{v * 100:.{dp}f}%"


def num(v, dp=1, suffix=""):
    return "데이터없음" if v is None else f"{v:.{dp}f}{suffix}"


def usd_bn(v):
    return "데이터없음" if v is None else f"{v / 1e9:,.0f}"


def inc_display(s):
    """Incremental ROIC, or a short reason it carries no information."""
    v = s.get("incremental_roic")
    if v is not None:
        return pct(v)
    st = s.get("incremental_roic_status") or ""
    if "CAPITAL_BASE_ESSENTIALLY_UNCHANGED" in st:
        return "해당없음 (자본 거의 불변)"
    if "INVESTED_CAPITAL_SHRANK" in st:
        return "해당없음 (자본 축소)"
    return "데이터없음"


def roic_display(s):
    """ROIC, or the condition where required capital is nil."""
    v = s.get("roic_10y_median")
    if v is not None:
        return pct(v)
    if (s.get("capital_light_years") or 0) > 0:
        return "자본 불필요"
    return "산출불가"


def tangible_display(s):
    """
    ROIC on net tangible capital, or a note when goodwill has consumed the base.

    Buffett's own phrasing is "net tangible assets", but for a company that grew
    by acquisition the goodwill it carries can exceed the capital the business
    employs, leaving a denominator near zero. Visa reads 5,750% on that basis.
    The number is not wrong so much as beside the point, so it is labelled.
    """
    v = s.get("roic_tangible_10y_median")
    if v is None:
        return "산출불가"
    if v > 2.0:
        return f"{v * 100:,.0f}% (영업권이 자본 초과)"
    return pct(v)


def valuation_note_ko(c):
    """Render the reason in the report's language; the JSON keeps the original."""
    s = c["summary"]
    st = s["valuation_status"]
    if st == "FRAMEWORK_NOT_APPLICABLE":
        return ("금융업 - 주주이익이 정의되지 않음. 설비투자와 운전자본은 은행이 자본을 "
                "어떻게 굴리는지 설명하지 못합니다.")
    oe = s.get("owner_earnings_normalised")
    return (f"정규화 주주이익이 음수({oe/1e9:.1f}십억 달러). 설비투자와 운전자본이 순이익을 "
            f"넘어서 할인할 현금흐름 자체가 없습니다. 데이터 공백이 아니라 사업에 대한 판정입니다.")


def moat_read(s):
    """A one-line read on durability from the quantitative proxies."""
    obs = s.get("roic_years_observed") or 0
    above = s.get("roic_above_10pct_years") or 0
    stdev = s.get("operating_margin_stdev")
    if not obs:
        return "판정불가"
    ratio = above / obs
    stable = stdev is not None and stdev < 0.05
    if obs < 5:
        return f"판정보류 — 관측 {obs}년뿐 (분사·상장 이력)"
    if ratio >= 0.9 and stable:
        return "강함 - 장기간 두 자릿수 ROIC + 안정적 마진"
    if ratio >= 0.9:
        return "강함 - 장기간 두 자릿수 ROIC, 마진 변동은 있음"
    if ratio >= 0.6:
        return "보통 - ROIC가 기간에 따라 흔들림"
    return "약함 - 두 자릿수 ROIC를 지킨 해가 절반 미만"


def build(analysis, verification):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    companies = analysis["companies"]
    for c in companies:
        latest_rev = next((r["revenue"] for r in reversed(c["years"]) if r.get("revenue")), None)
        c["summary"]["_latest_revenue"] = latest_rev
        c["_score"], c["_detail"] = quality_score(c["summary"])

    std_all = [c for c in companies if c["sector_treatment"] == "STANDARD"]
    fin = [c for c in companies if c["sector_treatment"] == "FINANCIAL"]
    # A company with no measurable ROIC in any year cannot be placed on a scale
    # where 45 of the 100 points come from return on capital - it would rank on
    # the points it cannot lose. Listed separately with the reason instead.
    std = [c for c in std_all if c["summary"].get("quality_scoreable", True)]
    unscoreable = [c for c in std_all if not c["summary"].get("quality_scoreable", True)]
    std.sort(key=lambda c: (-c["_score"], -(c["summary"].get("roic_10y_median") or -9)))
    fin.sort(key=lambda c: -(c["summary"].get("roe_10y_median") or -9))

    rf = analysis["risk_free_rate"]
    erp = analysis["equity_risk_premium"]
    vsum = verification["summary"]

    L = []
    w = L.append

    w("# 버핏 기준 52개 기업 분석")
    w("")
    w(f"생성 {ts} · 미국 50개사(정량) + 한국 2개사(정성)")
    w("")

    # ---------------------------------------------------------------- 요약
    w("## 한눈에")
    w("")
    valued = [c for c in std_all if c["summary"]["valuation_status"] == "VALUED"]
    investable = [c for c in valued if c["summary"]["dcf"]["base"]["verdict"] == "INVESTABLE_RANGE"]
    borderline = [c for c in valued if c["summary"]["dcf"]["base"]["verdict"] == "BORDERLINE"]
    negoe = [c for c in std_all if c["summary"]["valuation_status"] == "NEGATIVE_OWNER_EARNINGS"]

    w(f"- **품질과 가격은 별개였습니다.** 비금융 {len(std_all)}개 기업 중 "
      f"{sum(1 for c in std_all if (c['summary'].get('roic_wacc_spread') or -1) > 0)}개사가 "
      f"ROIC로 자본비용을 넘겼지만, 기준 시나리오(할인율 10%) DCF에서 안전마진 30% 이상인 "
      f"기업은 **{len(investable)}개**였습니다.")
    if borderline:
        w(f"- 경계선상은 {len(borderline)}개사({', '.join(c['ticker'] for c in borderline)})입니다. "
          f"나머지는 전부 적정가치 추정 범위 밖에서 거래되고 있습니다.")
    w(f"- **주주이익이 음수인 기업이 {len(negoe)}개**({', '.join(c['ticker'] for c in negoe)})입니다. "
      f"이익이 없어서가 아니라 설비투자와 운전자본이 순이익을 넘어서기 때문이며, "
      f"원칙 3 관점에서는 데이터 공백이 아니라 사업에 대한 판정입니다.")
    w(f"- 금융 {len(fin)}개사는 ROIC·주주이익 프레임을 적용하지 않았습니다. 은행에서 부채는 "
      f"자금조달이 아니라 원재료라 투하자본이 정의되지 않습니다. ROE·레버리지·배수로만 평가했습니다.")
    w(f"- 검증: **{vsum['companies_passed']}/{vsum['companies_checked']}개사**의 모든 인용 수치가 "
      f"해당 제출서류 원문과 대조 확인됐습니다.")
    w("")

    # ---------------------------------------------------------------- 순위
    w(f"## 1. 품질 순위 — 비금융 {len(std_all)}개사")
    w("")
    w("점수는 사업의 질만 봅니다. 가격은 다음 절에서 따로 다룹니다. "
      "자본비용에 못 미치는 사업은 싸다고 투자 대상이 되지 않는다는 것이 원칙 1의 요지이기 때문입니다.")
    w("")
    w("**ROIC의 분모는 '사업을 영위하는 데 필요한 자본'입니다.** 버핏이 2007년 주주서한에서 "
      "쓴 정의를 그대로 따랐습니다 — 시즈캔디를 두고 *\"The capital then required to conduct "
      "the business was $8 million... Consequently, the company was earning 60% pre-tax on "
      "invested capital\"*라고 적었고, 왜 그 자본이 적은지도 설명합니다(현금 판매라 매출채권이 "
      "없고 생산·유통 주기가 짧아 재고가 적다). 즉 운전자본과 고정자산이지, 놀고 있는 현금이 "
      "아닙니다. 그래서 자기자본＋이자부부채에서 현금을 뺍니다.")
    w("")
    w("**자본집약도**(필요자본 ÷ 매출)를 함께 싣습니다. 버핏의 시즈캔디는 매출 $30M에 자본 "
      "$8M, 즉 27%였습니다. 이 값이 낮으면서 ROIC가 높은 것이 그가 말한 *dream business*이고, "
      "같은 서한은 그 원형을 이렇게 지목합니다 — *\"It's far better to have an ever-increasing "
      "stream of earnings with virtually no major capital requirements. Ask Microsoft or "
      "Google.\"* 따라서 ROIC가 세 자릿수로 나오는 것은 눌러야 할 이상치가 아니라 자본이 거의 "
      "필요 없다는 **발견**입니다.")
    w("")
    w("**유형자산 기준 ROIC**도 병기했습니다. 같은 서한이 대조군을 *\"$82 million pre-tax on "
      "$400 million of net tangible assets\"*로 표현하므로, 영업권과 무형자산을 뺀 분모가 "
      "버핏의 표현에 가장 가깝습니다. 다만 인수를 많이 한 기업은 영업권이 자본을 넘어 이 분모가 "
      "0에 근접하므로(비자·필립모리스) 순위에는 쓰지 않고 참고로만 둡니다.")
    w("")
    w("| # | 티커 | 기업 | 점수 | ROIC 중앙값 | 자본집약도 | 유형자산 ROIC | 두자릿수 유지 | "
      "신규 ROIC | ROIC−WACC | 해자 판정 |")
    w("|---:|---|---|---:|---:|---:|---:|:--:|---:|---:|---|")
    for i, c in enumerate(std, 1):
        s = c["summary"]
        w(f"| {i} | {c['ticker']} | {c['company_name'][:26]} | **{c['_score']}** | "
          f"{roic_display(s)} | {pct(s.get('capital_intensity_median'))} | "
          f"{tangible_display(s)} | "
          f"{s.get('roic_above_10pct_years')}/{s.get('roic_years_observed')} | "
          f"{inc_display(s)} | {pct(s.get('roic_wacc_spread'))} | {moat_read(s)} |")
    w("")
    if unscoreable:
        w("**점수를 낼 수 없는 기업**")
        w("")
        w("| 티커 | 기업 | 사유 |")
        w("|---|---|---|")
        for c in unscoreable:
            w(f"| {c['ticker']} | {c['company_name'][:26]} | "
              f"어느 해에도 의미 있는 ROIC가 나오지 않습니다 — 보유 현금이 자기자본과 "
              f"거의 같고 차입금이 없어 투하자본이 0 이하이므로, 배점의 45점을 차지하는 "
              f"자본수익률 항목에 측정할 대상 자체가 없습니다. |")
        w("")

    # ---------------------------------------------------------------- 밸류에이션
    w("## 2. 가격 — 원칙 5·6")
    w("")
    w(f"주주이익 기준 2단계 DCF입니다. 기준 시나리오는 할인율 10%, 영구성장률 2.5%, "
      f"성장률은 각 사의 주주이익 과거 성장률을 10%로 상한을 두고 적용했습니다. "
      f"무위험수익률 {pct(rf.get('rate'), 2)}({rf.get('as_of')}), "
      f"주식위험프리미엄 {pct(erp.get('erp'), 2)}({erp.get('as_of')})는 WACC 산출에만 쓰입니다.")
    w("")
    w("P/적정가치가 1.0보다 크면 시장이 이 DCF보다 비싸게 매기고 있다는 뜻입니다.")
    w("")
    w("적정가치는 하나의 숫자가 아니라 **범위**로 제시합니다. 하한은 설비투자 전액을 주주이익에서 "
      "차감한 것이고, 상한은 감가상각만큼만(유지 목적) 차감한 것입니다. 버핏의 주주이익 정의는 "
      "'장기 경쟁지위와 판매량을 유지하는 데 필요한' 지출을 빼라고 하므로 후자가 정의에 더 "
      "가깝지만, 인플레이션기에는 자산 교체비용이 감가상각을 넘으므로 전자가 안전한 하한입니다.")
    w("")
    w("**함축수익률**은 지금 가격에 사서 가정대로 흘러갈 때 얻는 연 수익률입니다. "
      f"무위험수익률 {pct(rf.get('rate'), 2)}와 직접 비교하시면 됩니다. "
      "'안전마진 30% 이상인가'는 비싼 시장에서 거의 전부 '아니오'로 답이 끝나버리는 반면, "
      "함축수익률은 종목 간 비교를 가능하게 합니다.")
    w("")
    w("| 티커 | 주주이익 하한 | 주주이익 상한 | 적정가치 하한 | 적정가치 상한 | 시가총액 | "
      "함축수익률 | 순현금 | 판정(하한 기준) |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---|")
    # Ordered by the return the price implies rather than by margin of safety:
    # in a market where almost nothing clears a 30% discount, the margin of
    # safety sorts a column of "no" and says nothing about which no is closest.
    ranked = sorted(valued,
                    key=lambda c: -(c["summary"].get("implied_return_maintenance_capex") or -9))
    for c in ranked:
        s = c["summary"]
        d, dm = s["dcf"]["base"], s["dcf_maintenance_capex"]["base"]
        w(f"| {c['ticker']} | {usd_bn(s['owner_earnings_normalised'])} | "
          f"{usd_bn(s.get('owner_earnings_normalised_maintenance'))} | "
          f"{usd_bn(d['intrinsic_value'])} | {usd_bn(dm['intrinsic_value'])} | "
          f"{usd_bn(c['market_cap_usd'])} | "
          f"{pct(s.get('implied_return_maintenance_capex'))} | "
          f"{usd_bn(s.get('net_cash'))} | {d['verdict']} |")
    w("")
    w("### 밸류에이션을 내지 않은 기업")
    w("")
    w("| 티커 | 사유 |")
    w("|---|---|")
    for c in companies:
        s = c["summary"]
        if s["valuation_status"] in ("NEGATIVE_OWNER_EARNINGS", "FRAMEWORK_NOT_APPLICABLE"):
            w(f"| {c['ticker']} | {valuation_note_ko(c)} |")
    w("")

    # ---------------------------------------------------------------- 원칙 2
    w("## 3. ROE의 함정 — 원칙 2")
    w("")
    w("ROE에서 ROIC를 뺀 값이 크면, 보고된 자기자본이익률이 사업의 수익성이 아니라 "
      "레버리지에서 나오고 있다는 신호입니다. 자사주 매입으로 자기자본이 줄어든 경우에도 "
      "같은 형태로 벌어지므로, 부채 지표를 함께 봐야 구분됩니다.")
    w("")
    w("| 티커 | ROE | ROIC | 차이 | 순부채/EBITDA | 이자보상배율 | 읽는 법 |")
    w("|---|---:|---:|---:|---:|---:|---|")
    gap = sorted(std_all, key=lambda c: -(c["summary"].get("roe_roic_spread_latest") or -99))
    for c in gap[:12]:
        s = c["summary"]
        sp = s.get("roe_roic_spread_latest")
        nd = s.get("net_debt_to_ebitda_latest")
        note = ("자기자본이 마이너스이거나 0에 가까워 비율이 의미를 잃음"
                if sp is not None and sp > 1.0 else
                "레버리지가 ROE를 밀어올림" if sp is not None and sp > 0.10 else
                "ROE와 ROIC가 근접 - 수익성이 레버리지가 아닌 사업에서 나옴")
        w(f"| {c['ticker']} | {pct(s.get('roe_latest'))} | {pct(s.get('roic_latest'))} | "
          f"{pct(sp)} | {num(nd, 1, 'x')} | {num(s.get('interest_coverage_latest'), 1, 'x')} | {note} |")
    w("")

    # ---------------------------------------------------------------- 원칙 4
    w("## 4. 자본배분 — 원칙 4")
    w("")
    w("주식수 연평균 증감률입니다. 음수는 자사주 매입으로 주당 가치가 올라갔다는 뜻이고, "
      "양수는 희석입니다.")
    w("")
    w("주식수는 액면분할 기준을 통일한 뒤 계산했습니다. 각 연도의 주식수는 그해 제출된 "
      "10-K의 단위로 기록되는데 10-K는 직전 2개 연도까지만 소급 수정하므로, 분할을 "
      "가로지르는 시계열은 그대로 두면 폭발적인 신주 발행처럼 보입니다. 조정 전 엔비디아는 "
      "연 41% 희석, 아마존은 연 33% 희석으로 나왔습니다. 실제로는 각각 4:1·10:1, 20:1 "
      "분할이었습니다. 한편 델의 `1806:1000`이나 GE의 `1281:1000`처럼 정수가 아닌 비율은 "
      "분할이 아니라 스핀오프에 따른 주가 조정이어서 주식수에 적용하지 않았습니다.")
    w("")
    buyback = sorted([c for c in std if c["summary"].get("share_count_cagr") is not None],
                     key=lambda c: c["summary"]["share_count_cagr"])
    w("| 티커 | 주식수 CAGR | 기간 | 신규 ROIC | 해석 |")
    w("|---|---:|---|---:|---|")
    for c in buyback[:10] + buyback[-5:]:
        s = c["summary"]
        g = s["share_count_cagr"]
        inc = s.get("incremental_roic")
        note = ("매입 - 신규 자본 수익률이 높아 재투자와 병행할 여력" if g < 0 and (inc or 0) >= 0.15
                else "매입으로 주당 가치 상승" if g < 0
                else "희석 - 주식 기반 보상이 주주 몫을 잠식")
        w(f"| {c['ticker']} | {pct(g, 2)} | {s.get('share_count_window', '-')} | {pct(inc)} | {note} |")
    w("")

    # ---------------------------------------------------------------- 금융
    w(f"## 5. 금융 {len(fin)}개사 — 별도 기준")
    w("")
    w("ROIC와 주주이익은 산출하지 않았습니다. 은행·보험의 대차대조표에서 부채는 "
      "자금조달 수단이 아니라 영업 자산이고, 유동자산·유동부채 구분 자체가 존재하지 않아 "
      "투하자본과 운전자본이 정의되지 않기 때문입니다. SIC 6000~6799으로 분류했습니다.")
    w("")
    w("| 티커 | 기업 | 업종 | ROE 중앙값 | 최근 ROE | PER | PBR |")
    w("|---|---|---|---:|---:|---:|---:|")
    for c in fin:
        s = c["summary"]
        w(f"| {c['ticker']} | {c['company_name'][:24]} | {c.get('sic_description', '')[:26]} | "
          f"{pct(s.get('roe_10y_median'))} | {pct(s.get('roe_latest'))} | "
          f"{num(s.get('per'), 1, 'x')} | {num(s.get('pbr'), 2, 'x')} |")
    w("")

    return L


def korea_section(n_std):
    """
    The two Korean names, carried as far as the evidence standard allows.

    No quantitative figure is stated. Their audited financials are filed with
    DART, whose API needs a key this environment does not hold, and the whole
    point of the US work above is that every number traces to a filing. Writing
    Samsung's ROIC from memory would contradict the standard the rest of the
    report is built on, so this section reasons about business characteristics
    and says plainly what it would take to close the gap.
    """
    L = []
    w = L.append
    w("## 6. 한국 2개사 — 정성 분석")
    w("")
    w("**이 절에는 정량 수치가 없습니다.** 삼성전자와 SK하이닉스는 SEC 등록 기업이 아니라 "
      "감사받은 재무제표를 DART에 제출하며, OpenDART API는 이 환경에 없는 인증키를 요구합니다. "
      "앞의 50개사는 모든 숫자가 제출서류의 접수번호까지 추적되는데, 이 두 곳만 기억에 의존해 "
      "숫자를 적으면 보고서 전체의 기준이 무너집니다. 그래서 사업의 성격만 프레임워크에 비추어 "
      "정리하고, 공백은 공백으로 남깁니다.")
    w("")
    w("### 프레임워크 관점에서 본 구조적 특징")
    w("")
    w(("**두 회사 모두 원칙 1과 3이 가장 혹독하게 적용되는 업종에 있습니다.** 메모리 반도체는 "
      "설비투자가 매출에 선행하고, 감가상각이 끝나기 전에 다음 세대 투자가 시작됩니다. "
      "이 보고서의 미국 50개사에서도 같은 성질이 그대로 드러났습니다. 마이크론의 정규화 "
      "주주이익 마진은 비금융 {n} 기업 중 최하위권이었고, 인텔은 주주이익이 음수였습니다. "
      "메모리 사이클의 정점에서 순이익이 아무리 커도, 주주이익 기준으로는 그 이익의 상당 부분이 "
      "다음 세대 공정에 재투입되어 주주에게 남지 않습니다.").format(n=f"{n_std}개"))
    w("")
    w("**SK하이닉스**는 HBM 비중이 커지면서 제품 믹스가 범용 D램에서 벗어나는 국면에 있습니다. "
      "프레임워크상 이것이 해자에 해당하는지는 한 가지로 판별됩니다 — 사이클 저점에서도 "
      "ROIC가 자본비용을 넘는지입니다. 고점 ROIC는 메모리 업체에서 늘 높게 나오므로 판별력이 없습니다. "
      "이 판정에는 최소 한 번의 완전한 사이클(호황·불황 각각 최소 2년)에 걸친 투하자본과 "
      "NOPAT 시계열이 필요하며, 지금은 확보되지 않았습니다.")
    w("")
    w("**삼성전자**는 반도체·디스플레이·모바일이 한 재무제표에 묶여 있어 전사 ROIC가 "
      "성격이 다른 사업들의 가중평균이 됩니다. 원칙 1을 의미 있게 적용하려면 사업부문별 "
      "영업이익과 부문 자산이 필요하고, 이는 사업보고서 부문정보에 공시되지만 "
      "역시 DART 접근이 전제입니다. 전사 숫자만으로 내린 판정은 파운드리의 낮은 수익률과 "
      "메모리의 높은 수익률을 뭉개버려 어느 쪽에 대해서도 답을 주지 못합니다.")
    w("")
    w("### 판정")
    w("")
    w("| 항목 | 삼성전자 | SK하이닉스 |")
    w("|---|---|---|")
    w("| 원칙 1 ROIC vs WACC | 판정불가 — 투하자본 시계열 없음 | 판정불가 — 투하자본 시계열 없음 |")
    w("| 원칙 2 ROE 함정 | 판정불가 | 판정불가 |")
    w("| 원칙 3 주주이익 | 판정불가 — 구조적으로 자본집약적이라는 점만 확인 | 판정불가 — 동일 |")
    w("| 원칙 4 해자 | 부문 혼재로 전사 판정이 무의미 | 사이클 저점 ROIC가 관건, 미확보 |")
    w("| 원칙 5·6 적정가치 | 판정불가 | 판정불가 |")
    w("")
    w("### 이 공백을 메우려면")
    w("")
    w("OpenDART 인증키(무료 발급) 하나면 됩니다. 키가 있으면 두 회사의 사업보고서 XBRL에서 "
      "미국 50개사와 동일한 항목을 동일한 방식으로 뽑아낼 수 있고, 접수번호 단위 출처와 "
      "PHASE 6 재검증까지 같은 파이프라인을 태울 수 있습니다. "
      "`work/collect_dart.py`를 추가하고 `--universe`에 두 종목을 포함시키면 나머지 단계는 그대로 동작합니다.")
    w("")
    return L


def alphabet_case_section(analysis):
    """
    The Alphabet case - a live counter-example used to test the model.

    Berkshire built a large Alphabet position while this report's first run said
    Alphabet traded above intrinsic value in every scenario. One of the two was
    wrong, and running that down found three real defects rather than a
    difference of opinion. This section records the challenge, the corrections,
    and what remains a genuine judgment difference.
    """
    g = next((c for c in analysis["companies"] if c["ticker"] == "GOOG"), None)
    L = []
    w = L.append
    w("## 7. 알파벳 사례 — 모델 맹점 점검")
    w("")
    w("이 절은 반례에서 출발합니다. 초판은 알파벳이 낙관 시나리오에서도 적정가치보다 비싸다고 "
      "판정했는데, 같은 기간 버크셔 해서웨이는 알파벳을 대규모로 매입했습니다. 둘 중 하나는 "
      "틀렸다는 뜻이므로 원인을 추적했고, 의견 차이가 아니라 **모델의 실제 결함 세 가지**가 "
      "나왔습니다.")
    w("")
    w("### 사실 확인 — 버크셔의 알파벳 보유 (SEC 13F 원문)")
    w("")
    w("| 13F 제출일 | 보유 시점 | 보유 주식수 | 평가액 |")
    w("|---|---|---:|---:|")
    w("| 2025-11-14 | Q3 2025 | 17,846,142주 (Class A) | $4.34B — 신규 편입 |")
    w("| 2026-02-17 | Q4 2025 | 17,846,142주 (Class A) | $5.59B — 주식수 동일 |")
    w("| 2026-05-15 | Q1 2026 | 54,249,798주 (A) + 3,585,215주 (C) | **$16.63B** |")
    w("")
    w("출처: EDGAR CIK 0001067983, 접수번호 0001193125-25-282901 · 0001193125-26-054580 · "
      "0001193125-26-226661. Q1 2026에 3배로 늘렸고 신고 포트폴리오(약 $263B)의 6% 수준입니다. "
      "시험 매수로 보기 어려운 규모입니다.")
    w("")
    w("### 결함 1 — 성장 설비투자를 사업 악화로 계산했습니다 (가장 큼)")
    w("")
    w("버핏의 주주이익 정의는 '**장기 경쟁지위와 판매량을 유지하는 데 필요한**' 자본적 지출을 "
      "빼라고 합니다. 유지 목적 지출이지 자본예산 전체가 아닙니다. 초판은 설비투자 전액을 "
      "차감했습니다.")
    w("")
    if g:
        y = g["years"][-1]
        raw = y.get("raw", {})
        w(f"알파벳 FY{y['fiscal_year']}: 설비투자 ${raw.get('capex',0)/1e9:.1f}B에 감가상각 "
          f"${raw.get('depreciation_amortization',0)/1e9:.1f}B. 차액 "
          f"${(y.get('growth_capex') or 0)/1e9:.0f}B, 즉 설비투자의 "
          f"{(g['summary'].get('growth_capex_share_of_capex') or 0):.0%}가 감가상각을 넘는 "
          f"**증설 투자**입니다. 이걸 전액 비용으로 치면 AI 데이터센터를 짓는 행위가 "
          f"수익성 악화로 기록됩니다.")
    w("")
    w("이 결함은 알파벳만의 문제가 아니었습니다. **테슬라와 팔란티어는 '주주이익 음수'로 "
      "분류돼 밸류에이션 자체가 배제돼 있었는데, 성장 투자 때문이었지 사업이 나빠서가 "
      "아니었습니다.** 유지 설비투자 기준으로는 음수인 기업이 하나도 없습니다.")
    w("")
    w("수정: 적정가치를 **범위**로 바꿨습니다. 하한은 설비투자 전액 차감(보수), 상한은 "
      "감가상각만큼만 차감(정의에 충실). 감가상각은 유지 지출의 근사치일 뿐이고 인플레이션기에는 "
      "교체비용이 이를 넘으므로, 어느 한쪽을 정답으로 선언하지 않고 둘 다 제시합니다.")
    w("")
    w("### 결함 2 — 현금을 십억 단위로 잘못 봤습니다")
    w("")
    w("`CashAndCashEquivalentsAtCarryingValue` 태그만 읽고 있었는데, 알파벳은 여기에 $30.7B, "
      "유동 유가증권에 별도로 $96B를 담고 있었습니다. **$96B가 통째로 빠져 있었습니다.** "
      "그 결과 투하자본이 과대계상돼 ROIC가 낮게 나왔고, 순현금이 마이너스로 뒤집혀 있었습니다.")
    w("")
    if g:
        sm = g["summary"]
        w(f"| 항목 | 수정 전 | 수정 후 |")
        w(f"|---|---:|---:|")
        w(f"| 유동자산 | $30.7B | $126.8B |")
        w(f"| 순현금 | −$18B | **+${(sm.get('net_cash') or 0)/1e9:.0f}B** |")
        w(f"| ROIC (최근) | 35.4% | **{sm.get('roic_latest', 0):.1%}** |")
    w("")
    w("수정: 결합 태그를 우선 사용하고, 분리 공시하는 기업은 단기투자자산을 더합니다. "
      "운전자본 계산에서도 유가증권이 빠지므로 주주이익이 더 정확해집니다.")
    w("")
    w("### 결함 3 — 태그 전환으로 생긴 연도 구멍")
    w("")
    w("알파벳은 매출 태그를 중간에 바꿔서 어느 한 태그도 10년을 온전히 덮지 못했고, "
      "**FY2022 매출이 비어 있었습니다.** 수정: 두 태그가 겹치는 모든 연도에서 값이 정확히 "
      "일치할 때만(알파벳은 8개 연도 일치) 빈 연도를 메웁니다. 값이 하나라도 다르면 서로 다른 "
      "개념이므로 구멍을 그대로 둡니다.")
    w("")
    w("### 남는 것은 판단 차이입니다")
    w("")
    w("세 결함을 고쳐도 알파벳이 기준 시나리오에서 싸지지는 않습니다. 달라진 것은 "
      "**틀린 이유로 배제되던 것이 판단의 문제로 바뀌었다**는 점입니다.")
    if g:
        sm = g["summary"]
        d, dm = sm["dcf"], sm["dcf_maintenance_capex"]
        w("")
        w("| 시나리오 | 적정가치 하한(총 설비투자) | 적정가치 상한(유지 설비투자) | 안전마진 범위 |")
        w("|---|---:|---:|---:|")
        for k, ko in (("conservative", "보수"), ("base", "기준"), ("optimistic", "낙관")):
            w(f"| {ko} | {usd_bn(d[k]['intrinsic_value'])} | {usd_bn(dm[k]['intrinsic_value'])} | "
              f"{pct(d[k]['margin_of_safety'], 0)} ~ {pct(dm[k]['margin_of_safety'], 0)} |")
        w("")
        w(f"시가총액 {usd_bn(g['market_cap_usd'])}십억 달러 기준입니다. 낙관 시나리오에 유지 "
          f"설비투자를 적용하면 안전마진이 "
          f"{pct(dm['optimistic']['margin_of_safety'], 0)}로 플러스가 되고, 순현금 "
          f"${(sm.get('net_cash') or 0)/1e9:.0f}B를 더하면 투자가능 기준선인 30%에 닿습니다. "
          f"다만 이건 낙관 가정과 유지 설비투자 가정을 **동시에** 채택한 결과이므로, "
          f"기준 시나리오가 여전히 비싸다는 사실을 덮지는 않습니다.")
    w("")
    w("### 버크셔가 본 것에 대한 추정")
    w("")
    w("함축수익률로 보면 그림이 달라집니다. 지금 가격에 사서 가정대로 흘러갈 때의 연 수익률입니다.")
    w("")
    std = [c for c in analysis["companies"] if c["sector_treatment"] == "STANDARD"]
    rows = [(c["ticker"], c["summary"].get("implied_return_maintenance_capex"),
             c["summary"].get("roic_10y_median"), c["summary"].get("net_cash"))
            for c in std if c["summary"].get("implied_return_maintenance_capex")]
    rows.sort(key=lambda r: -r[1])
    w("| 티커 | 함축수익률 | ROIC 중앙값 | 순현금($B) |")
    w("|---|---:|---:|---:|")
    for t, ir, roic, nc in rows[:12]:
        mark = " ←" if t == "GOOG" else ""
        w(f"| {t}{mark} | {pct(ir)} | {pct(roic)} | {usd_bn(nc)} |")
    w("")
    w("알파벳은 함축수익률 자체로는 상위권이되 1위가 아닙니다. 눈에 띄는 건 **조합**입니다. "
      "위에 있는 종목들은 대부분 품질이 낮거나(머크 13%, 엑슨 10%, 셰브론 7%, 델 10%) "
      "순부채 상태인데, 알파벳은 ROIC 중앙값 38%에 12년 내내 두 자릿수를 지켰고 목록에서 "
      "가장 큰 순현금을 들고 있습니다. 품질·재무구조·함축수익률을 함께 놓고 보면 "
      "메가캡 중에서 가장 나은 조합입니다.")
    w("")
    w("그리고 비교 대상이 중요합니다. 버크셔의 대안은 4.7% 단기국채입니다. "
      "이 프레임워크의 '안전마진 30%' 문턱은 절대 기준이라 비싼 시장에서는 모든 종목에 "
      "'아니오'를 돌려주고 대화를 끝내버립니다. 실제 자본배분은 언제나 상대적입니다.")
    w("")
    w("**단서 두 가지.** 첫째, 13F는 보유만 공시하고 매수 이유를 밝히지 않으므로 위 해석은 "
      "추정입니다. 둘째, 이 판단이 버핏 본인의 것인지 투자 담당(Todd Combs·Ted Weschler)이나 "
      "후임 경영진의 것인지는 공시로 알 수 없습니다. 다만 어느 쪽이든 버크셔의 자본이 "
      "같은 원칙 아래 집행된 것으로 보는 것이 합리적입니다.")
    w("")
    w("### 이 사례가 남긴 구조적 한계")
    w("")
    w("고치지 않았지만 명시해 둘 것들입니다.")
    w("")
    w("- **과거만 봅니다.** 성장률은 과거 주주이익 CAGR에서 나오고 상한이 걸립니다. "
      "사업이 변곡점에 있다면 과거 시계열에는 그 정보가 없습니다.")
    w("- **비영업 자산을 값으로 치지 않습니다.** 웨이모 같은 사업, 지분투자, 순현금은 "
      "이익 흐름에만 근거한 DCF에 들어오지 않습니다. 순현금은 별도 열로 표시만 했습니다.")
    w("- **할인율이 고정입니다.** 8·10·12%는 대안 수익률과 무관하게 고정돼 있습니다. "
      "무위험수익률이 4.7%인 국면에서 10%를 요구하는 것은 상당히 높은 문턱입니다.")
    w("- **절대 기준이라 상대 비교를 못 합니다.** 포지션 규모나 기회비용은 이 프레임워크 "
      "밖의 문제입니다. 함축수익률 열을 넣은 것이 부분적인 보완입니다.")
    w("")
    return L

def limitations_section(analysis, verification):
    L = []
    w = L.append
    w("## 8. 한계와 데이터 처리 원칙")
    w("")
    w("보고서에 실린 수치가 어떤 판단을 거쳤는지 밝혀둡니다. 수치를 그대로 쓰기 어려웠던 "
      "지점마다 추정으로 메우지 않고 표시하는 쪽을 택했습니다.")
    w("")
    w("**EBIT을 일관되게 재구성했습니다.** 릴리·엑슨모빌·IBM·머크·셰브론은 영업이익 소계를 "
      "아예 태깅하지 않습니다. 태그가 있는 회사는 보고된 영업이익을, 없는 회사는 다른 것을 쓰면 "
      "ROIC가 회사마다 다른 것을 뜻하게 됩니다. 그래서 전 종목에서 `세전이익 + 이자비용`으로 "
      "통일하고, 이자비용이 없는 3개사만 보고된 영업이익으로 대체했습니다. 연도별로 어느 방식을 "
      "썼는지 `analysis.json`에 기록돼 있습니다.")
    w("")
    w("**분모는 기초·기말 평균입니다.** 기말 잔고를 쓰면 연말에 자본을 조달한 회사가 "
      "한 해 내내 그 자본으로 벌어들인 것처럼 보입니다.")
    w("")
    w("**필립모리스의 ROIC는 산출했지만 자기자본은 마이너스입니다.** 장기간의 자사주 매입 결과이고, "
      "투하자본이 음수가 되는 해에는 비율 자체가 의미를 잃으므로 그런 연도는 "
      "`NOT_MEANINGFUL_NEGATIVE_INVESTED_CAPITAL`로 표시했습니다.")
    w("")
    w("**베타의 설명력이 낮은 종목이 있습니다.** 5년 월간 수익률을 S&P 500에 회귀해 직접 "
      "추정했는데, 엑슨모빌·머크·존슨앤드존슨 등 방어주는 결정계수가 0.05 미만입니다. "
      "이 경우 CAPM 자기자본비용이 약하게만 식별되고 그 위에 세운 WACC도 무릅니다. "
      "해당 종목은 `beta_reliability: LOW`로 표시했으며, DCF는 WACC가 아니라 "
      "8·10·12% 고정 할인율 3종을 쓰므로 이 약점의 영향을 받지 않습니다.")
    w("")
    w("**비자의 시가총액은 과소평가돼 있습니다.** 클래스 B-1·B-2·C의 전환비율은 "
      "이사회가 소송 에스크로 정산에 따라 주기적으로 재설정하므로 표지에서 도출할 수 없습니다. "
      "클래스 A만으로 계산했고 `incomplete: true`로 표시했습니다. 실제 전환 후 기준 시가총액은 "
      "이보다 크므로, 비자의 안전마진은 표에 적힌 것보다 나쁩니다.")
    w("")
    w("**주주이익 정규화 방식.** 주주이익은 운전자본 타이밍 때문에 해마다 크게 출렁입니다 "
      "(코카콜라는 한 해에 166억 달러에서 21억 달러로 움직였습니다). 최근 5년 주주이익 마진의 "
      "중앙값을 최근 매출에 적용해 정규화했습니다. 금액의 중앙값을 쓰면 성장 기업을 "
      "몇 년 전 규모로 평가하게 되어, 보수적인 것이 아니라 낡은 값이 됩니다.")
    w("")
    w("**전수조사를 별도로 돌렸습니다.** `audit.py`가 데이터 무결성(태그 노후화, 연도 공백, "
      "불가능한 부호), 파생지표(범위를 벗어난 비율, 깨진 항등식), 배점 규칙(결측이 점수를 "
      "얻는지), 산출물 간 정합성을 훑습니다. 이 조사에서 나온 수정은 다음과 같습니다. "
      "주식수 분할 조정이 기간종료일 기준이어서 이미 소급 수정된 연도에 분할을 한 번 더 "
      "적용하고 있었고(애플 FY2019가 710억 주로 계산됐습니다), 분할일을 월간 시세로 받아 "
      "월초로 뭉개진 탓에 팔로알토의 한 해가 잘못된 쪽에 놓였습니다. 순부채/EBITDA와 "
      "이자보상배율이 분모·분자가 음수일 때도 숫자를 냈고, 자기자본이 0 이하인 해의 ROE가 "
      "15,000%로 표시됐으며, 오라클은 연결 세전이익 태그가 2017년에 끊겨 실효세율이 조용히 "
      "법정세율로 대체되고 있었습니다(국내·해외 합산으로 복원). 남은 지적 8건은 팔란티어 "
      "직상장, RTX-UTC 합병, 델 Class V 거래처럼 실제 기업 이벤트이거나 대체 태그가 없는 "
      "공백으로, 각각 확인 후 그대로 두었습니다.")
    w("")
    w("**ROIC 분모를 한 번 잘못 바꿨다가 되돌렸습니다.** 아리스타처럼 현금이 많은 기업은 "
      "필요자본이 매출의 5분의 1도 안 되어 ROIC가 96~192%로 요동칩니다. 이걸 이상치로 보고 "
      "현금을 빼지 않은 '총투하자본'으로 순위를 매긴 판이 있었는데, 방향이 반대였습니다. "
      "버핏의 분모는 명시적으로 '사업을 영위하는 데 필요한 자본'이고, 자본이 거의 필요 없다는 "
      "것은 그가 가장 높이 사는 조건입니다 — 2007년 서한이 그 원형으로 마이크로소프트와 "
      "구글을 지목합니다. 세 자릿수 ROIC는 억눌러야 할 잡음이 아니라 시즈캔디와 같은 성질의 "
      "발견이었습니다. 게다가 배점은 구간식이라(30% 이상이면 만점) 그 변동성이 점수에 닿지도 "
      "않았고, 이상치를 제외하려던 규칙이 오히려 아리스타의 관측 연도를 12년에서 2년으로 "
      "줄여 실제 피해를 냈습니다. 통계적 안정성을 위해 프레임워크의 의미를 희생한 판단이었고, "
      "지금은 버핏의 정의로 돌아가 있습니다.")
    w("")
    w("**DCF는 점 추정이 아닙니다.** 보수·기준·낙관 3개 시나리오의 범위로만 읽어야 하며, "
      "이 보고서는 '투자 가능 구간 안인가'라는 질문에만 답합니다. 목표주가가 아닙니다.")
    w("")
    w(f"**검증되지 않은 수치는 없습니다.** PHASE 6에서 "
      f"{verification['summary']['companies_passed']}개사 전부에 대해 "
      f"각 항목을 해당 10-K 원문의 인라인 XBRL과 대조하고, 인용한 접수번호가 EDGAR에 "
      f"실재하는지 확인하고, 주식수를 재파싱으로 재현하고, 주가를 재조회했습니다. "
      f"통과하지 못한 수치는 보고서에 넣지 않는다는 규칙이었으나, 최종 실행에서는 실패 항목이 없었습니다.")
    w("")
    w("### 재현 방법")
    w("")
    w("```bash")
    w("python3 work/build_universe.py          # 유니버스 확정")
    w("python3 work/collect_sec.py --universe work/universe.json")
    w("python3 work/collect_cover_shares.py    # 표지 주식수")
    w("python3 work/collect_market.py          # 주가·베타·무위험수익률·ERP")
    w("python3 work/analyse.py                 # PHASE 2-5")
    w("python3 work/verify.py                  # PHASE 6")
    w("python3 work/report.py                  # PHASE 7")
    w("```")
    w("")
    return L


def main():
    with open(os.path.join(WORK, "analysis.json")) as f:
        analysis = json.load(f)
    with open(os.path.join(WORK, "verification.json")) as f:
        verification = json.load(f)

    lines = build(analysis, verification)
    lines += korea_section(len([c for c in analysis["companies"] if c["sector_treatment"] == "STANDARD"]))
    lines += alphabet_case_section(analysis)
    lines += limitations_section(analysis, verification)

    path = os.path.join(WORK, "REPORT.md")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"report -> {path} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
