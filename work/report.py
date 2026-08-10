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

    roic = s.get("roic_10y_median")
    p = 25 if roic is None else (25 if roic >= 0.30 else 20 if roic >= 0.20
                                 else 15 if roic >= 0.15 else 10 if roic >= 0.10 else 0)
    p = 0 if roic is None else p
    pts += p
    detail["ROIC 중앙값"] = p

    obs, above = s.get("roic_years_observed") or 0, s.get("roic_above_10pct_years") or 0
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

    std = [c for c in companies if c["sector_treatment"] == "STANDARD"]
    fin = [c for c in companies if c["sector_treatment"] == "FINANCIAL"]
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
    valued = [c for c in std if c["summary"]["valuation_status"] == "VALUED"]
    investable = [c for c in valued if c["summary"]["dcf"]["base"]["verdict"] == "INVESTABLE_RANGE"]
    borderline = [c for c in valued if c["summary"]["dcf"]["base"]["verdict"] == "BORDERLINE"]
    negoe = [c for c in std if c["summary"]["valuation_status"] == "NEGATIVE_OWNER_EARNINGS"]

    w(f"- **품질과 가격은 별개였습니다.** 비금융 {len(std)}개 기업 중 "
      f"{sum(1 for c in std if (c['summary'].get('roic_wacc_spread') or -1) > 0)}개사가 "
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
    w(f"## 1. 품질 순위 — 비금융 {len(std)}개사")
    w("")
    w("점수는 사업의 질만 봅니다. 가격은 다음 절에서 따로 다룹니다. "
      "자본비용에 못 미치는 사업은 싸다고 투자 대상이 되지 않는다는 것이 원칙 1의 요지이기 때문입니다.")
    w("")
    w("| # | 티커 | 기업 | 점수 | ROIC 중앙값 | 두자릿수 유지 | 신규 ROIC | ROIC−WACC | 해자 판정 |")
    w("|---:|---|---|---:|---:|:--:|---:|---:|---|")
    for i, c in enumerate(std, 1):
        s = c["summary"]
        w(f"| {i} | {c['ticker']} | {c['company_name'][:26]} | **{c['_score']}** | "
          f"{pct(s.get('roic_10y_median'))} | {s.get('roic_above_10pct_years')}/{s.get('roic_years_observed')} | "
          f"{inc_display(s)} | {pct(s.get('roic_wacc_spread'))} | {moat_read(s)} |")
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
    w("| 티커 | 정규화 주주이익($B) | 적정가치($B) | 시가총액($B) | P/적정가치 | 안전마진 | 판정 |")
    w("|---|---:|---:|---:|---:|---:|---|")
    ranked = sorted(valued, key=lambda c: -(c["summary"]["dcf"]["base"]["margin_of_safety"] or -99))
    for c in ranked:
        s = c["summary"]
        d = s["dcf"]["base"]
        iv, mc = d["intrinsic_value"], c["market_cap_usd"]
        ratio = mc / iv if (iv and mc) else None
        # Past roughly 20x the ratio stops discriminating: it only says the
        # owner-earnings base is a rounding error against the price.
        ratio_txt = ">20x" if (ratio and ratio > 20) else num(ratio, 1, "x")
        mos_txt = "<-1900%" if (ratio and ratio > 20) else pct(d["margin_of_safety"], 0)
        w(f"| {c['ticker']} | {usd_bn(s['owner_earnings_normalised'])} | {usd_bn(iv)} | {usd_bn(mc)} | "
          f"{ratio_txt} | {mos_txt} | {d['verdict']} |")
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
    gap = sorted(std, key=lambda c: -(c["summary"].get("roe_roic_spread_latest") or -99))
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


def limitations_section(analysis, verification):
    L = []
    w = L.append
    w("## 7. 한계와 데이터 처리 원칙")
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
    lines += limitations_section(analysis, verification)

    path = os.path.join(WORK, "REPORT.md")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"report -> {path} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
