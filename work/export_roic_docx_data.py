"""
Build the block list for the ROIC-versus-WACC Word report.

Renders through export_memo_docx.js:

    python3 export_roic_docx_data.py
    node export_memo_docx.js roic/roic_report.json 미국50개사_ROIC_WACC비교.docx
"""

import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "roic", "roic_report.json")

D = json.load(open(os.path.join(HERE, "roic", "roic.json")))
R = json.load(open(os.path.join(HERE, "roic", "reconciliation.json")))
C = json.load(open(os.path.join(HERE, "roic", "corrections.json")))
G = json.load(open(os.path.join(HERE, "roic", "capital_diagnosis.json")))
ROUTES = json.load(open(os.path.join(HERE, "roic", "oi_routes.json")))

YEARS = list(range(2016, 2026))
WACC = D["wacc"]
BN = 1e9


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def bn(x, nd=1):
    return "—" if x is None else f"{x / BN:,.{nd}f}"


def roic_of(comp, fy):
    y = next((y for y in comp["years"] if y["fiscal_year"] == fy), None)
    return None if y is None else y["roic"]


def flag(comp, fy):
    y = next((y for y in comp["years"] if y["fiscal_year"] == fy), None)
    if y is None or y["roic"] is None:
        return ""
    s = ""
    if y["confidence"] == "LOW":
        s += "*"
    if y.get("capital_too_small"):
        s += "†"
    return s


by_ticker = {c["ticker"]: c for c in D["companies"]}
rank = D["ranking"]
usable_years = sum(x["years_usable"] for x in rank)
above_years = sum(x["years_above_wacc"] for x in rank)
all_above = [x for x in rank if x["every_year_above_wacc"]]
some_below = [x for x in rank if not x["every_year_above_wacc"]]
median_of_medians = statistics.median(x["roic_median"] for x in rank)
low_years = len(D["low_confidence_years"])
thin_capital = sum(x["years_capital_too_small"] for x in rank)
orcl = next(n for n in C["net_cash_errors_flagged"] if n["ticker"] == "ORCL")

blocks = []
add = blocks.append

add({"t": "h1", "text": "미국 50개사 ROIC vs 자본비용 10% — 재조사"})
add({"t": "note",
     "text": "자료 SEC XBRL companyfacts API · 대상 FY2016~FY2025 · "
             "WACC 10% 고정 · 산출 engine work/analyse_roic.py · "
             "검증 9,867건 통과, 변이 10/10 탐지 · "
             f"작성 {D['generated']}"})

add({"t": "h2", "text": "요약"})
add({"t": "p",
     "text": f"**비금융 {len(rank)}개사의 {usable_years}개 기업-연도 가운데 "
             f"{above_years}개 연도({above_years / usable_years:.0%})가 "
             f"ROIC 10%를 넘겼습니다.** 중위 ROIC의 중앙값은 "
             f"{pct(median_of_medians)}로, 문턱의 두 배를 웃돕니다. "
             f"10년 내내 한 해도 빠짐없이 10%를 넘긴 기업은 "
             f"{len(all_above)}곳이고, 한 해라도 미달한 기업이 "
             f"{len(some_below)}곳입니다. 전 기간 미달한 기업은 없습니다."})
add({"t": "p",
     "text": "다만 이번 작업의 더 중요한 결과는 순위표가 아니라 **1차 조사의 "
             f"오류 {C['company_years_changed']}건을 찾아 바로잡은 것**입니다. "
             f"가장 큰 원인은 1차 조사가 공시된 장기차입금을 "
             f"{len(G['old_missed_long_term_debt'])}개 기업-연도에서 누락한 "
             "것으로, 오라클 10년, 코카콜라 7년, 브로드컴 4년, 비자 3년이 "
             "여기에 걸립니다. 오라클 FY2024 ROIC가 761%로 나왔던 이유입니다."})
add({"t": "p",
     "text": "그리고 이 오류는 ROIC에서 멈추지 않았습니다. 1차 조사는 "
             f"**오라클을 순현금 {bn(orcl['net_cash_in_study'])}십억 달러 "
             f"기업으로 보고 있었는데, 실제로는 순차입금 "
             f"{bn(-orcl['net_cash_recomputed'])}십억 달러**입니다. "
             f"차이가 {bn(orcl['error'])}십억 달러, 시가총액의 "
             f"{pct(orcl['error_vs_market_cap'], 0)}에 해당합니다. "
             "DCF 재계산은 이번 범위가 아니므로 표시만 해두었습니다."})

add({"t": "h2", "text": "1. 왜 별도로 다시 조사했는지"})
add({"t": "p",
     "text": "ROIC가 WACC를 넘는지가 기업가치 성장의 핵심이라는 판단에 "
             "동의합니다. 그렇다면 ROIC 숫자 자체가 맞는지가 결론 전체를 "
             "좌우합니다. 그래서 1차 조사 결과를 보지 않은 상태에서, "
             "정의만 같게 두고 경로를 완전히 바꿔 다시 산출했습니다."})
add({"t": "table",
     "headers": ["", "1차 조사", "이번 재조사"],
     "rows": [
         ["자료 경로", "공시 본문(10-K)을 파싱", "XBRL companyfacts API"],
         ["코드", "work/analyse.py", "work/collect_roic.py + analyse_roic.py"],
         ["정의", "자기자본+이자부차입금−현금", "동일"],
         ["분모 평균", "기초·기말 평균", "동일 (부호 전환 해는 기말 단독)"],
         ["자기자본", "지배주주 지분", "비지배지분 포함 (분자가 연결이므로)"],
         ["검증", "없음", "항등식·트립와이어·앵커 9,867건 + 변이 10건"],
     ]})
add({"t": "p",
     "text": "정의가 같고 경로만 다르면, 두 결과가 어긋날 때 **어느 한쪽이 "
             "틀렸다**는 뜻이 됩니다. 그 점이 이번 조사의 목적이었습니다."})

add({"t": "h2", "text": "2. 두 조사를 맞춰본 결과"})
add({"t": "table",
     "headers": ["구분", "건수", "비중"],
     "rows": [
         ["대조 가능한 기업-연도", f"{R['compared_company_years']}",
          "100%"],
         ["1%p 이내 일치", f"{R['agree_within_1pp']}",
          f"{R['agree_within_1pp'] / R['compared_company_years']:.0%}"],
         ["1%p 초과 불일치", f"{R['differ_over_1pp']}",
          f"{R['differ_over_1pp'] / R['compared_company_years']:.0%}"],
         ["5%p 초과 불일치", f"{R['differ_over_5pp']}",
          f"{R['differ_over_5pp'] / R['compared_company_years']:.0%}"],
         ["10% 문턱 판정까지 바뀜", f"{R['hurdle_verdict_flips']}",
          f"{R['hurdle_verdict_flips'] / R['compared_company_years']:.0%}"],
         ["재조사만 산출 (1차는 공백)", f"{R['new_covers_old_blank']}", "—"],
         ["1차만 산출", f"{R['old_covers_new_blank']}", "—"],
     ]})
add({"t": "p",
     "text": f"절반 가까이가 어긋났고, 원인은 한쪽으로 몰렸습니다. "
             f"불일치 {R['differ_over_1pp']}건 중 "
             f"{R['cause_tally'].get('투하자본(분모)', 0)}건이 분모 문제였고, "
             f"분자 문제는 {R['cause_tally'].get('영업이익(분자)', 0)}건입니다."})

add({"t": "h2", "text": "3. 어느 쪽이 틀렸는지 — 판단이 필요 없는 검정"})
add({"t": "p",
     "text": "분모가 다르다는 것만으로는 어느 쪽이 맞는지 알 수 없습니다. "
             "그래서 판단이 끼어들 여지가 없는 검정을 했습니다. "
             "**10-K에 장기차입금 태그가 있는 기업은 장기차입금이 있었던 "
             "것이고, 그걸 0으로 기록한 조사는 틀린 것**입니다."})
add({"t": "table",
     "headers": ["기업", "누락 연수", "공시 장기차입금(최대, 십억$)",
                 "1차 조사 총차입금", "재산출 총차입금"],
     "rows": []})
tally = {}
for m in G["old_missed_long_term_debt"]:
    tk = m["key"].split()[0]
    cur = tally.setdefault(tk, {"n": 0, "filed": 0, "old": 0, "new": 0})
    cur["n"] += 1
    if (m["filed_long_term_debt"] or 0) > cur["filed"]:
        cur["filed"] = m["filed_long_term_debt"]
        cur["old"] = m["old_total_debt"]
        cur["new"] = m["new_total_debt"] or 0
for tk, v in sorted(tally.items(), key=lambda kv: -kv[1]["filed"]):
    blocks[-1]["rows"].append([tk, f"{v['n']}년", bn(v["filed"]),
                               bn(v["old"]), bn(v["new"])])
add({"t": "p",
     "text": "오라클은 10년 전부가 여기에 해당합니다. 1차 조사는 오라클의 "
             "투하자본을 12.6십억 달러로 잡았는데, 그 해 공시된 차입금만 "
             "86.9십억 달러였습니다. ROIC 761%는 그 결과입니다."})
add({"t": "p",
     "text": "반대 방향 오류도 있었습니다. 애플 FY2016의 현금을 1차 조사는 "
             "20.5십억 달러로 기록했지만, 단기 유가증권 46.7십억 달러를 "
             "합한 67.2십억 달러가 차감 대상입니다. 이 경우 1차 조사는 "
             "분모를 과대하게 잡아 **ROIC를 낮게** 보고 있었습니다. "
             "오류가 한쪽으로만 기울지 않았다는 뜻입니다."})

add({"t": "h2", "text": "4. 재조사 쪽에서도 발견된 오류"})
add({"t": "p",
     "text": "재조사가 1차 조사보다 낫다는 결론은 검증을 거친 뒤에야 "
             "말할 수 있습니다. 실제로 재조사 과정에서 제 쪽 오류를 여섯 건 "
             "찾아 고쳤고, 전부 검증 장치가 잡아낸 것입니다."})
add({"t": "table",
     "headers": ["무엇이 틀렸는지", "증상", "어떻게 잡았는지"],
     "rows": [
         ["알파벳 FY2016 단기투자자산 누락 — FY2017 이후 태그만 찾고 있었음",
          "ROIC 16% (실제 34%)",
          "연도 간 현금 연속성 점검"],
         ["램리서치 현금 과다차감 — 만기표의 1년 이내 컬럼($4,844m)을 "
          "유동 투자자산($1,773m)으로 오인",
          "ROIC 675%",
          "차감 현금 ≤ 유동자산 트립와이어 + 공시 앵커"],
         ["오라클 차입금 이중계상 — 현재분 포함 총액에 현재분을 또 더함",
          "차입금 $97.5bn (실제 $86.9bn)",
          "차입금 ≤ 총부채 트립와이어 + 공시 앵커"],
         ["마스터카드 FY2017 차입금 0 — 10-K에만 의존해 10-Q 비교수치를 "
          "못 봄",
          "ROIC 243%",
          "연도 간 차입금 연속성"],
         ["엔비디아 FY2016 — 기초자본이 음수인데 평균을 냄",
          "ROIC 892%",
          "부호 전환 시 기말 단독 사용 규칙"],
         ["아멕스 — FY2010과 FY2016 자본의 평균. 직전 '행'을 썼기 때문",
          "평균 투하자본 43% 과대",
          "엑셀 수식 검증(직전 연도 참조 확인)"],
     ]})
add({"t": "p",
     "text": "코스트코를 한 번 통째로 날린 적도 있습니다. 순투하자본이 "
             "매출의 10% 미만인 해를 '분모가 너무 작다'며 제외하는 규칙을 "
             "넣었더니, 회전율이 높은 유통업이 전부 걸렸습니다. 유통업이 "
             "거대한 매출에 얇은 자본을 쓰는 건 자료 문제가 아니라 사업의 "
             "성격이므로, 제외가 아니라 표시로 바꿨습니다."})

add({"t": "h2", "text": "5. 영업이익 소계를 보고하지 않는 기업"})
add({"t": "p",
     "text": "일라이릴리·머크·J&J·IBM·KLA·엑슨·셰브론·GE는 손익계산서에 "
             "영업이익 소계가 없습니다. 분자를 만들어야 하는데, 어떻게 "
             "만들지는 주장이 아니라 측정으로 정했습니다. 소계를 보고하는 "
             "기업-연도에서 각 구성 방식을 보고치와 맞춰봤습니다."})
add({"t": "table",
     "headers": ["구성 경로", "검정", "±2% 일치", "정확도", "중위 오차"],
     "rows": [[x["route"], str(x["tested"]), str(x["matched"]),
               pct(x["accuracy"]), pct(x["median_error"], 2)]
              for x in ROUTES["routes"]]})
add({"t": "p",
     "text": "이 표는 1차 조사의 방법 기술에 대한 답도 됩니다. 1차 조사의 "
             "method_notes는 분자를 '세전이익+이자비용을 우선 사용'한다고 "
             "적어두었는데, 실제 기록은 보고 소계 340건 대 세전이익+이자 "
             "124건으로 우선순위가 반대였습니다. 설명이 구현과 어긋나 "
             "있었던 것이고, 설명을 고쳤습니다. 그리고 그 방식(경로 H)은 "
             "측정해보니 정확도 32.7%로 전 경로 중 최하위였습니다 — "
             "이자·투자수익을 빼주면(경로 G) 42.1%로 올라갑니다."})
add({"t": "p",
     "text": "다만 **±2% 일치율은 이 문제에 맞는 통계가 아닙니다.** 목적이 "
             "ROIC를 10% 문턱과 비교하는 것이므로, 중요한 건 분자를 바꿨을 "
             "때 문턱 판정이 뒤집히는지입니다. 그걸 직접 측정했습니다."})
add({"t": "table",
     "headers": ["구성 경로", "검정", "판정 뒤집힘", "비율",
                 "ROIC 중위 격차", "90분위"],
     "rows": [
         ["B 매출총이익−영업비용", "207", "0", "0.0%", "0.00%", "0.00%"],
         ["C 매출−총비용", "167", "1", "0.6%", "0.00%", "0.35%"],
         ["H 세전이익+이자 (1차 조사 설명의 방식)", "477", "11", "2.3%",
          "1.11%", "5.59%"],
         ["D 매출−매출원가−영업비용", "220", "6", "2.7%", "0.00%", "0.00%"],
         ["G 세전이익+이자−이자·투자수익", "477", "14", "2.9%", "0.77%",
          "5.19%"],
         ["F 세전이익−영업외수익", "448", "16", "3.6%", "0.35%", "3.98%"],
     ]})
add({"t": "p",
     "text": "즉 세전이익 기반 추정은 ROIC 수준을 몇 %p 틀릴 수 있지만 "
             "10% 문턱 판정은 97% 정확합니다. 그래서 이 여덟 기업을 "
             "버리지 않고 추정값으로 포함했고, 두 가지 추정 방식을 모두 "
             "계산해 판정이 일치하는지 기업-연도마다 기록했습니다. "
             f"해당 연도는 {low_years}건이며 표에서 별표(*)로 "
             "표시했습니다."})
add({"t": "p",
     "text": "다만 경로 선택에는 함정이 하나 더 있었습니다. 경로 C의 "
             "85.8%라는 정확도는 소계를 보고하는 기업에서만 측정된 값이라, "
             "소계를 보고하지 않는 기업에 그대로 적용되지 않습니다. 실제로 "
             "GE에 적용하자 FY2016 영업이익이 −6.4십억 달러로 나왔습니다 "
             "(Revenues 태그는 산업부문만, CostsAndExpenses는 그룹 전체를 "
             "담고 있었습니다). 그래서 모든 상향식 구성값은 **세전이익으로 "
             "역검증**을 통과해야만 쓰도록 했고, 경로 선택은 연도별이 아니라 "
             "기업별로 한 번만 하도록 바꿨습니다 — 연도마다 다른 경로를 쓰면 "
             "10년 추세가 사업이 아니라 경로를 측정하게 되기 때문입니다."})

add({"t": "h2", "text": "6. ROIC 연도별 — vs WACC 10%"})
add({"t": "note",
     "text": "굵은 음영 없음 = 10% 초과. 괄호는 10% 이하. "
             "* = 영업이익을 세전이익에서 추정한 해. "
             "† = 순투하자본이 매출의 10% 미만이어서 비율이 민감한 해 "
             "(문턱 판정 자체는 유효). 단위 %."})
rows = []
for i, entry in enumerate(rank, 1):
    comp = by_ticker[entry["ticker"]]
    cells = []
    for fy in YEARS:
        v = roic_of(comp, fy)
        if v is None:
            cells.append("—")
        else:
            s = f"{v * 100:.0f}{flag(comp, fy)}"
            cells.append(s if v > WACC else f"({s})")
    rows.append([str(i), entry["ticker"]] + cells +
                [f"{entry['roic_median'] * 100:.0f}",
                 f"{entry['years_above_wacc']}/{entry['years_usable']}"])
add({"t": "table",
     "headers": ["순위", "티커"] + [str(y)[2:] for y in YEARS] +
                ["중위", "초과"],
     "rows": rows})

add({"t": "h2", "text": "7. ROIC − 10% 스프레드 (중위 기준)"})
add({"t": "table",
     "headers": ["구간", "기업", "기업 수"],
     "rows": [
         ["+40%p 이상", ", ".join(x["ticker"] for x in rank
                               if x["spread_median"] >= 0.40),
          str(sum(1 for x in rank if x["spread_median"] >= 0.40))],
         ["+20~40%p", ", ".join(x["ticker"] for x in rank
                                if 0.20 <= x["spread_median"] < 0.40),
          str(sum(1 for x in rank if 0.20 <= x["spread_median"] < 0.40))],
         ["+10~20%p", ", ".join(x["ticker"] for x in rank
                                if 0.10 <= x["spread_median"] < 0.20),
          str(sum(1 for x in rank if 0.10 <= x["spread_median"] < 0.20))],
         ["0~+10%p", ", ".join(x["ticker"] for x in rank
                               if 0 <= x["spread_median"] < 0.10),
          str(sum(1 for x in rank if 0 <= x["spread_median"] < 0.10))],
         ["음수 (10% 미달)", ", ".join(x["ticker"] for x in rank
                                  if x["spread_median"] < 0),
          str(sum(1 for x in rank if x["spread_median"] < 0))],
     ]})
add({"t": "p",
     "text": "스프레드의 크기보다 **꾸준함**이 중요합니다. 중위 ROIC가 "
             "높아도 변동이 크면 어느 해에 자본을 투입했는지에 따라 결과가 "
             "갈리기 때문입니다. 10년 전부 10%를 넘긴 "
             f"{len(all_above)}곳이 그 조건을 만족합니다: "
             f"{', '.join(x['ticker'] for x in all_above)}."})
add({"t": "table",
     "headers": ["기업", "중위 ROIC", "최소", "최대", "표준편차",
                 "분자 추정 연수"],
     "rows": [[x["ticker"], pct(x["roic_median"], 0), pct(x["roic_min"], 0),
               pct(x["roic_max"], 0), pct(x["roic_stdev"], 0),
               str(x["years_estimated_numerator"])]
              for x in all_above]})

add({"t": "h2", "text": "8. 비율로 읽으면 안 되는 기업"})
add({"t": "p",
     "text": "아리스타·램리서치·마스터카드처럼 현금이 자기자본을 거의 "
             "상계하는 기업은 순투하자본이 0에 가까워, ROIC가 100%를 "
             "넘더라도 그 숫자를 다른 기업과 나란히 놓을 수 없습니다. "
             "아리스타의 FY2025 자기자본 12.4십억 달러 중 10.7십억 달러가 "
             "현금이어서 순투하자본은 1.6십억 달러, 매출 9.0십억 달러의 "
             "18%입니다. ROIC 192%는 산술적으로 맞지만 '이 사업은 자본이 "
             "거의 필요 없다'는 뜻이지 '수익률이 192%'라는 뜻이 아닙니다. "
             f"창 안에서 이런 해가 {thin_capital}건이며 표에 †로 "
             "표시했습니다. 10% 문턱 판정은 영향받지 않습니다."})
add({"t": "p",
     "text": "팔란티어와 GE버노바는 산출 연도가 5년 미만이어서 순위에서 "
             "뺐습니다. 팔란티어는 10년 중 대부분 순투하자본이 음수여서 "
             "(현금이 자기자본+차입금을 넘어서) 이 정의로는 ROIC가 성립하지 "
             "않습니다. 금융업 9곳(버크셔·JP모건·BoA·씨티·웰스파고·"
             "골드만·모건스탠리·아멕스·유나이티드헬스)은 ROIC를 산출하지 "
             "않았습니다 — 은행에게 차입은 자금조달이 아니라 원재료여서 "
             "자기자본+차입금−현금이 아무것도 측정하지 않습니다."})

add({"t": "h2", "text": "9. 1차 조사에 반영한 정정"})
add({"t": "table",
     "headers": ["항목", "내용"],
     "rows": [
         ["정정한 기업-연도", f"{C['company_years_changed']}건 "
                        "(ROIC·영업이익·실효세율·투하자본)"],
         ["method_notes.ebit", "분자 우선순위를 실제 구현과 맞게 수정"],
         ["method_notes.returns_denominator", "부호 전환 해의 예외 명시"],
         ["원본 보존", C["backup"]],
         ["재계산하지 않은 것", "가격·시가총액·주주이익·DCF·가치평가 판정"],
     ]})
add({"t": "p",
     "text": "ROIC가 바뀐 폭이 큰 기업-연도입니다."})
big = sorted((x for x in C["changes"]
              if None not in (x["roic_before"], x["roic_after"])),
             key=lambda x: -abs(x["roic_after"] - x["roic_before"]))[:12]
add({"t": "table",
     "headers": ["기업", "연도", "1차 ROIC", "정정 ROIC", "변화"],
     "rows": [[x["ticker"], f"FY{x['fiscal_year']}", pct(x["roic_before"], 0),
               pct(x["roic_after"], 0),
               f"{(x['roic_after'] - x['roic_before']) * 100:+.0f}%p"]
              for x in big]})

add({"t": "h3", "text": "가치평가로 번진 입력 오류 — 재계산하지 않았음"})
add({"t": "p",
     "text": "ROIC와 별개로, 1차 조사가 쓴 순현금 입력값이 재산출값과 "
             f"크게 어긋난 기업이 {len(C['net_cash_errors_flagged'])}곳 "
             "있습니다. 순현금은 기업가치에서 주주가치로 넘어가는 과정에 "
             "그대로 더해지므로, 이 오차는 내재가치에 1:1로 반영됩니다."})
add({"t": "table",
     "headers": ["기업", "1차 조사 순현금", "재산출", "오차", "시가총액 대비"],
     "rows": [[n["ticker"], bn(n["net_cash_in_study"]),
               bn(n["net_cash_recomputed"]), bn(n["error"]),
               pct(n["error_vs_market_cap"], 1)]
              for n in sorted(C["net_cash_errors_flagged"],
                              key=lambda n: -abs(n["error"]))]})
add({"t": "p",
     "text": "오라클이 결정적입니다. 시가총액의 24%에 해당하는 오차이므로 "
             "1차 조사의 오라클 가치평가 결론은 신뢰할 수 없습니다. "
             "다른 네 곳은 1% 안팎이라 결론을 바꾸기 어렵습니다. "
             "**가치평가 재계산은 정정이 아니라 새로운 분석이므로 "
             "이번 작업에서 하지 않았습니다** — 필요하시면 오라클만 따로 "
             "다시 돌리겠습니다."})

add({"t": "h2", "text": "10. 검증"})
add({"t": "table",
     "headers": ["검증 방식", "건수", "무엇을 잡는지"],
     "rows": [
         ["항등식", "—",
          "투하자본=자기자본+차입금−현금, NOPAT=영업이익×(1−세율), "
          "ROIC=NOPAT÷평균자본, 평균 산정 규칙"],
         ["트립와이어", "—",
          "차감 현금 ≤ 유동자산, 차입금 ≤ 총부채 및 총자산, "
          "실효세율 5~40% 범위"],
         ["공시 앵커", "19",
          "공시 본문에서 손으로 읽은 수치와 대조. 자기참조가 아닌 "
          "유일한 검사"],
         ["합계", "9,867", "전부 통과"],
         ["변이 검정", "10/10",
          "값을 고의로 훼손해 검사가 실제로 실패하는지 확인"],
         ["엑셀 수식 검증", "5,494",
          "워크북의 모든 파생 셀을 재평가해 산출 엔진 값과 대조"],
     ]})
add({"t": "p",
     "text": "앵커를 따로 두는 이유가 있습니다. 항등식과 트립와이어는 "
             "검사 대상과 같은 데이터로 계산되므로, **내부적으로 일관된 "
             "틀린 값은 둘 다 통과합니다.** 공시 원문에서 직접 읽은 수치만이 "
             "산술이 아니라 데이터가 틀렸을 때 실패할 수 있습니다. "
             "실제로 램리서치 현금 과다차감과 오라클 차입금 이중계상은 "
             "앵커가 잡았습니다."})
add({"t": "p",
     "text": "앵커 자체가 틀린 적도 있습니다. 램리서치 FY2019의 유동 "
             "투자자산을 1,106백만 달러로 적었는데 실제 공시는 "
             "1,772.984백만 달러였습니다 — 기억으로 쓴 값이어서 틀렸고, "
             "공시 데이터를 다시 확인해 고쳤습니다."})

add({"t": "h2", "text": "11. 남은 한계"})
add({"t": "bullets",
     "items": [
         f"**분자 추정 {low_years}개 연도.** 영업이익 소계를 보고하지 않는 "
         "여덟 기업은 세전이익에서 거꾸로 추정했습니다. 문턱 판정은 97% "
         "정확하지만 ROIC 수준은 90분위에서 4~5%p 틀릴 수 있습니다. "
         "릴리·J&J·IBM·KLA·셰브론은 두 추정 방식의 판정이 모두 일치했고, "
         "머크 FY2020 한 해만 불일치입니다.",
         "**자기자본 정의.** 분자가 연결 영업이익이므로 분모도 비지배지분을 "
         "포함했습니다. 1차 조사는 지배주주 지분만 썼고, 96개 기업-연도에서 "
         "차이가 납니다. 대부분 1~5% 수준이지만 정의가 다른 것이지 "
         "오류는 아닙니다.",
         "**장기 유가증권은 자본에 남겼습니다.** 비유동 투자자산을 빼지 "
         "않았으므로 분모가 보수적으로(크게) 잡혔고, ROIC는 그만큼 "
         "낮게 나옵니다.",
         "**WACC 10%는 지시에 따른 고정값입니다.** 실제 자본비용은 기업마다 "
         "다르고, 2016~2025년 사이 금리 환경도 크게 달라졌습니다. 같은 "
         "문턱을 쓴 것은 ROIC를 서로 비교하기 위한 선택입니다.",
         "**ROIC가 높다는 것과 투자 대상이라는 것은 다릅니다.** 가격이 "
         "빠져 있습니다. 1차 조사의 가치평가는 오라클을 제외하면 "
         "이번 정정으로 결론이 바뀌지 않지만, ROIC 순위가 곧 매수 "
         "순위는 아닙니다.",
     ]})

add({"t": "h2", "text": "12. 재현 방법"})
add({"t": "p",
     "text": "`bash work/run_roic.sh` 한 번으로 수집부터 워드·엑셀 작성까지 "
             "전부 다시 돌아갑니다. 순서에 한 곳 의존성이 있습니다: 대조와 "
             "원인 규명은 1차 조사 원본을 읽어야 하므로 정정 적용보다 먼저 "
             "실행되어야 하고, 스크립트가 백업에서 원본을 복원한 뒤 "
             "시작합니다."})
add({"t": "table",
     "headers": ["파일", "역할"],
     "rows": [
         ["collect_roic.py", "companyfacts에서 50개사 재무 태그 수집"],
         ["test_oi_routes.py", "분자 구성 경로의 정확도·판정 뒤집힘 측정"],
         ["analyse_roic.py", "ROIC 산출 (정의·경로 선택·역검증)"],
         ["verify_roic.py", "항등식·트립와이어·앵커 + 변이 검정"],
         ["reconcile_roic.py", "1차 조사와 기업-연도별 대조"],
         ["diagnose_capital.py", "투하자본 차이의 원인 규명"],
         ["apply_corrections.py", "1차 조사 정정 및 원본 백업"],
         ["export_roic_xlsx.py", "엑셀 (전 파생 셀이 수식)"],
         ["verify_roic_exports.py", "엑셀 수식 5,494건 재평가 검증"],
     ]})

# The renderer needs a width per column. Rather than hand-tune every table,
# the first column gets more room (it carries names and labels) and the rest
# share what is left; a two-column table is a label/prose pair, so it leans
# much further.
for b in blocks:
    if b["t"] != "table" or b.get("widths"):
        continue
    n = len(b["headers"])
    if n == 2:
        b["widths"] = [26, 74]
    elif n == 3:
        b["widths"] = [22, 56, 22]
    else:
        first = max(10, min(20, int(100 / n) + 6))
        rest = (100 - first) / (n - 1)
        b["widths"] = [first] + [rest] * (n - 1)
    # Columns that hold figures read better right-aligned.
    b["numeric"] = [i for i, h in enumerate(b["headers"])
                    if i > 0 and any(k in str(h) for k in
                                     ("%", "건수", "연수", "십억", "ROIC",
                                      "차입금", "오차", "검정", "비중",
                                      "최소", "최대", "중위", "초과",
                                      "편차", "일치", "정확도", "뒤집힘",
                                      "분위", "변화"))
                    or (i > 1 and str(h).isdigit())]

json.dump({"title": "미국 50개사 ROIC vs WACC 10% 재조사", "blocks": blocks},
          open(OUT, "w"), indent=1, ensure_ascii=False)
print(f"wrote {OUT} ({len(blocks)} blocks)")
