"""
Alphabet - the second round of memo replies.

Thirteen memos, several of which ask for figures the first pass did not compute:
ROIC with assets-not-yet-in-service taken out, a year-by-year incremental
return series, the revenue backlog put into the numerator, depreciation-life
scenarios, the not-yet-commenced leases capitalised, and a three-scenario DCF
built from projected cash flows rather than a single normalised number.

Two of the memos also caught real errors in the first document. Both are fixed
here and flagged in the output: see CORRECTIONS.

Sources: work/analysis.json (verified against the filings by verify.py) plus
figures read from Alphabet's FY2023-FY2025 10-K documents, each carried with
the accession that contains it.

Writes work/alphabet_memo2.json.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

FILINGS = {
    2025: "0001652044-26-000018",
    2024: "0001652044-25-000014",
    2023: "0001652044-24-000022",
}

# ---------------------------------------------------------------------------
# CORRECTION 1
#
# The first document compared "technical infrastructure" across FY2022-FY2025.
# Those are not the same line. Alphabet re-cut its property categories in the
# FY2025 10-K: before that the equipment line was "technology equipment", which
# holds servers and network gear only, while "technical infrastructure" also
# holds data-centre land, buildings and leasehold improvements. Putting $66.3bn
# (FY2022, equipment only) next to $203.7bn (FY2025, equipment plus buildings)
# made the build-out look like a tripling and drove revenue-per-dollar from
# $4.27 down to $1.98. On one consistent basis the fall is $2.73 to $1.98.
#
# The FY2024 10-K restates FY2023 on the new categories, which is what makes a
# comparable series possible at all. It reaches back only to FY2023, so FY2022
# has no figure on this basis and is left out rather than guessed.
# ---------------------------------------------------------------------------
TECHNICAL_INFRASTRUCTURE = {
    2023: {"value": 112_504e6, "source": FILINGS[2024],
           "note": "FY2024 10-K, new categories"},
    2024: {"value": 141_852e6, "source": FILINGS[2025],
           "note": "FY2025 10-K, includes finance-lease right-of-use assets"},
    2025: {"value": 203_679e6, "source": FILINGS[2025],
           "note": "FY2025 10-K, includes finance-lease right-of-use assets"},
}

# ---------------------------------------------------------------------------
# CORRECTION 2
#
# The first document said "$79bn of FY2025 technical infrastructure is still
# under construction". It is not inside that line. The FY2025 property note
# reads: technical infrastructure 203,679 + office space 48,348 + corporate and
# other 14,463 = property and equipment IN SERVICE 266,490; less accumulated
# depreciation (98,485); ADD assets not yet in service 78,592 = net 246,597.
# Assets not yet in service sit outside the in-service categories. So the
# revenue-per-dollar ratio was already on an in-service basis, and the figure
# that actually carries capital which earns nothing yet is invested capital.
# ---------------------------------------------------------------------------
ASSETS_NOT_YET_IN_SERVICE = {
    2022: 27_657e6, 2023: 35_229e6, 2024: 50_597e6, 2025: 78_592e6,
}

PPE_IN_SERVICE_2025 = 266_490e6
ACCUM_DEPRECIATION_2025 = 98_485e6
SERVERS_SHARE_OF_TECHNICAL_INFRA = 0.60   # stated in the FY2025 property note

# Depreciation policy, quoted from the FY2025 10-K property note.
USEFUL_LIVES = {
    "servers_and_network_equipment": 6,
    "data_centre_and_office_buildings": (7, 40),
    "corporate_and_other": (2, 25),
}
SERVICE_LIFE_CHANGE_2023 = -3_900e6

# Revenue backlog note, FY2025 10-K.
BACKLOG = {2023: 74_100e6, 2024: 93_200e6, 2025: 242_800e6}
BACKLOG_NEAR_TERM_SHARE = 0.50      # "just over 50% ... over the next 24 months"
BACKLOG_NEAR_TERM_YEARS = 2

# Leases entered into but not yet commenced, FY2025 10-K liquidity section.
LEASES_NOT_COMMENCED_SHORT = 5_800e6
LEASES_NOT_COMMENCED_LONG = 52_700e6
LEASE_COMMENCE_RANGE = (2026, 2031)
LEASE_TERM_RANGE = (1, 25)
OPERATING_LEASE_DISCOUNT_RATE = 0.036
OPERATING_LEASE_LIABILITY = {2024: 14_578e6, 2025: 15_954e6}
FINANCE_LEASE_LIABILITY = {2024: 1_677e6, 2025: 2_500e6}
POWER_PURCHASE_AGREEMENT_2026 = 9_900e6

# Cash-flow statement, FY2025 10-K.
CASH_FLOW_2025 = {
    "operating": 164_713e6,
    "capex": -91_447e6,
    "purchases_of_marketable_securities": -103_773e6,
    "maturities_and_sales_of_marketable_securities": 83_240e6,
    "purchases_of_non_marketable": -5_716e6,
    "maturities_and_sales_of_non_marketable": 1_367e6,
    "acquisitions_and_intangibles": -1_592e6,
    "other_investing": -2_370e6,
    "investing_total": -120_291e6,
    "stock_award_net_payments": -14_167e6,
    "buybacks": -45_709e6,
    "dividends": -10_049e6,
    "debt_issued": 64_564e6,
    "debt_repaid": -32_427e6,
    "other_financing": 400e6,
    "financing_total": -37_388e6,
    "fx": 208e6,
    "net_change_in_cash": 7_242e6,
    "cash_end_of_period": 30_708e6,
}
CASH_AND_SHORT_TERM_SECURITIES_2025 = 126_843e6
INTEREST_INCOME_2025 = 4_337e6
INTEREST_EXPENSE_NET_2025 = 736e6
INTEREST_CAPITALISED_2025 = 447e6
PENDING_ACQUISITIONS = {
    "Wiz": {"price": 32_000e6, "expected_close": "2026",
            "note": "all-cash; joins the Google Cloud segment on closing"},
    "Intersect": {"price": 4_800e6, "expected_close": "2026 상반기",
                  "note": "데이터센터·에너지 인프라. 현금 대가에 부채 인수가 추가됩니다"},
}

SEGMENT_2025 = {
    "구글 서비스": {"revenue": 342_721e6, "operating_income": 139_404e6},
    "구글 클라우드": {"revenue": 58_705e6, "operating_income": 13_910e6},
    "기타 베팅": {"revenue": 1_537e6, "operating_income": -7_515e6},
    "Alphabet 전사 활동": {"revenue": None, "operating_income": -16_760e6},
}
SERVICES_REVENUE_LINES_2025 = {
    "Google 검색 및 기타": 224_532e6,
    "YouTube 광고": 40_367e6,
    "Google 네트워크": 29_792e6,
    "구독·플랫폼·기기": 48_030e6,
}


def load():
    with open(os.path.join(HERE, "analysis.json")) as fh:
        analysis = json.load(fh)
    goog = next(c for c in analysis["companies"] if c["ticker"] == "GOOG")
    return analysis, goog


def yr(goog, fy):
    return next(y for y in goog["years"] if y["fiscal_year"] == fy)


def div(a, b):
    return None if not b else a / b


# ---------------------------------------------------------------------------
# 메모 0 - 건설 중인 자산을 분모에서 빼면
# ---------------------------------------------------------------------------

def roic_excluding_construction(goog):
    """ROIC with capital that is not yet in service removed from the denominator.

    The argument in the memo is sound: assets not yet in service produce no
    revenue by construction - Alphabet says depreciation does not even begin
    until they are ready for their intended use - so charging them against this
    year's profit measures the wrong thing. Taking them out answers "what is the
    capital that is actually working earning?"

    It is a supplementary reading, not a replacement. The money is spent, and a
    build-out that never earns is a loss whatever the ratio says.
    """
    rows = []
    prev_ic_ex = None
    for fy in (2022, 2023, 2024, 2025):
        y = yr(goog, fy)
        cip = ASSETS_NOT_YET_IN_SERVICE[fy]
        ic_ex = y["invested_capital"] - cip
        ic_ex_avg = ic_ex if prev_ic_ex is None else (ic_ex + prev_ic_ex) / 2
        rows.append({
            "fiscal_year": fy,
            "invested_capital_reported": y["invested_capital"],
            "assets_not_yet_in_service": cip,
            "invested_capital_ex_construction": ic_ex,
            "invested_capital_ex_construction_avg": ic_ex_avg,
            "nopat": y["nopat"],
            "roic_reported": y["roic"],
            "roic_ex_construction": div(y["nopat"], ic_ex_avg),
            "construction_share_of_capital": div(cip, y["invested_capital"]),
        })
        prev_ic_ex = ic_ex
    # The first row has no prior year on this basis, so its average is a
    # year-end figure and is not comparable. Marked rather than dropped.
    rows[0]["roic_ex_construction_note"] = "전기 값이 없어 기말 잔고 기준 (비교 불가)"
    return rows


def infrastructure_corrected(goog):
    """Revenue per dollar of technical infrastructure, on one consistent basis."""
    rows = []
    for fy in sorted(TECHNICAL_INFRASTRUCTURE):
        y = yr(goog, fy)
        ti = TECHNICAL_INFRASTRUCTURE[fy]["value"]
        rows.append({
            "fiscal_year": fy,
            "technical_infrastructure": ti,
            "source_note": TECHNICAL_INFRASTRUCTURE[fy]["note"],
            "revenue": y["revenue"],
            "operating_income": y["ebit"],
            "revenue_per_dollar": div(y["revenue"], ti),
            "operating_income_per_dollar": div(y["ebit"], ti),
            "assets_not_yet_in_service": ASSETS_NOT_YET_IN_SERVICE[fy],
        })
    return rows


# ---------------------------------------------------------------------------
# 메모 5 - 연도별 증분 ROIC
# ---------------------------------------------------------------------------

def incremental_roic_by_year(goog):
    """Year-on-year incremental return, plus a three-year rolling version.

    The memo is right that a single FY2021-FY2025 window hides when the cloud
    business actually started earning. Year-on-year is the honest cut, but it is
    also violently noisy - a year where invested capital happens to shrink puts
    a negative number in the denominator and the ratio flips sign for reasons
    that have nothing to do with returns. Both are given, and the unusable
    years are labelled rather than dropped.
    """
    years = [y["fiscal_year"] for y in goog["years"]]
    rows = []
    for i in range(1, len(years)):
        a, b = yr(goog, years[i - 1]), yr(goog, years[i])
        d_nopat = b["nopat"] - a["nopat"]
        d_cap = b["invested_capital"] - a["invested_capital"]
        status = "OK"
        inc = div(d_nopat, d_cap)
        if d_cap <= 0:
            inc, status = None, "투하자본이 줄어 산출 불가 (자사주 매입·자산 감소)"
        elif d_cap < 0.02 * b["invested_capital"]:
            status = "분모가 매우 작아 값이 불안정"
        rows.append({
            "fiscal_year": years[i],
            "nopat": b["nopat"],
            "delta_nopat": d_nopat,
            "invested_capital": b["invested_capital"],
            "delta_invested_capital": d_cap,
            "incremental_roic": inc,
            "status": status,
            "capex": b["raw"]["capex"],
            "revenue_growth": div(b["revenue"] - a["revenue"], a["revenue"]),
        })
    # Three-year rolling, which is what the noise above calls for.
    rolling = []
    for i in range(3, len(years)):
        a, b = yr(goog, years[i - 3]), yr(goog, years[i])
        d_nopat = b["nopat"] - a["nopat"]
        d_cap = b["invested_capital"] - a["invested_capital"]
        rolling.append({
            "window": f"FY{years[i-3]}→FY{years[i]}",
            "delta_nopat": d_nopat,
            "delta_invested_capital": d_cap,
            "incremental_roic": div(d_nopat, d_cap) if d_cap > 0 else None,
        })
    return {"annual": rows, "rolling_3y": rolling}


# ---------------------------------------------------------------------------
# 메모 6 - 계약잔고를 분자에 넣는다면
# ---------------------------------------------------------------------------

def backlog_into_numerator(goog):
    """Scenarios that put the revenue backlog to work in the numerator.

    The memo's logic is symmetric and correct: if capital that has not started
    earning is taken out of the denominator, then revenue that is contracted but
    not yet delivered belongs somewhere too. The honest place is the numerator,
    as the profit the backlog will produce once delivered.

    Every row below is a constructed scenario. The only figures Alphabet
    published are the $242.8bn backlog, the "just over 50% within 24 months"
    timing, and Google Cloud's current revenue and operating income.
    """
    y = yr(goog, 2025)
    tax = y["tax_rate"]
    cloud_rev = SEGMENT_2025["구글 클라우드"]["revenue"]
    cloud_oi = SEGMENT_2025["구글 클라우드"]["operating_income"]
    cloud_margin = cloud_oi / cloud_rev
    cloud_nopat_now = cloud_oi * (1 - tax)

    near_term_annual = (BACKLOG[2025] * BACKLOG_NEAR_TERM_SHARE
                        / BACKLOG_NEAR_TERM_YEARS)

    scenarios = []
    for name, years_to_deliver, margin, note in [
        ("보수", 4.0, cloud_margin,
         "잔고 전체를 4년에 걸쳐 인식하고 마진은 현재 수준 유지"),
        ("중립", 3.0, 0.30,
         "3년에 걸쳐 인식하고, 규모 확대로 마진이 30%까지 개선"),
        ("낙관", 2.5, 0.35,
         "2.5년에 걸쳐 인식하고 마진 35% — 현재 구글 서비스 마진(40.7%)에 근접"),
    ]:
        annual_rev = BACKLOG[2025] / years_to_deliver
        oi = annual_rev * margin
        nopat = oi * (1 - tax)
        ic_ex = (yr(goog, 2025)["invested_capital"] - ASSETS_NOT_YET_IN_SERVICE[2025])
        ic_ex_prev = (yr(goog, 2024)["invested_capital"] - ASSETS_NOT_YET_IN_SERVICE[2024])
        ic_ex_avg = (ic_ex + ic_ex_prev) / 2
        # Replace the cloud profit already in the numerator with the backlog
        # run-rate; everything else in NOPAT stays as reported.
        nopat_total = y["nopat"] - cloud_nopat_now + nopat
        scenarios.append({
            "scenario": name,
            "years_to_deliver": years_to_deliver,
            "implied_annual_revenue": annual_rev,
            "assumed_operating_margin": margin,
            "backlog_operating_income": oi,
            "backlog_nopat": nopat,
            "uplift_over_current_cloud_nopat": nopat - cloud_nopat_now,
            "company_nopat_adjusted": nopat_total,
            "roic_ex_construction_with_backlog": div(nopat_total, ic_ex_avg),
            "note": note,
        })

    return {
        "backlog": BACKLOG[2025],
        "backlog_prior": BACKLOG[2024],
        "backlog_growth": div(BACKLOG[2025] - BACKLOG[2024], BACKLOG[2024]),
        "cloud_revenue_2025": cloud_rev,
        "cloud_operating_margin_2025": cloud_margin,
        "cloud_nopat_2025": cloud_nopat_now,
        "near_term_implied_annual_revenue": near_term_annual,
        "near_term_vs_current_cloud_revenue": div(near_term_annual, cloud_rev),
        "reading": ("계약잔고 중 24개월 내 인식분만 연 환산해도 "
                    f"${near_term_annual/1e9:.1f}B으로, 현재 클라우드 연매출 "
                    f"${cloud_rev/1e9:.1f}B을 이미 넘습니다. 신규 계약을 한 건도 "
                    "더 따내지 못한다고 가정해도 향후 2년 클라우드 매출은 지금 "
                    "수준 이상이 계약으로 확보돼 있다는 뜻입니다."),
        "scenarios": scenarios,
    }


# ---------------------------------------------------------------------------
# 메모 8 - 감가상각 내용연수
# ---------------------------------------------------------------------------

def depreciation_scenarios(goog):
    """ROIC under shorter and longer assumed lives for the server fleet.

    Alphabet depreciates servers and network equipment over six years and says
    ~60% of technical infrastructure is that equipment. Only that portion is
    varied here; data-centre buildings genuinely last decades and are left at
    the reported charge.
    """
    y = yr(goog, 2025)
    tax = y["tax_rate"]
    ic_avg = y["invested_capital_avg"]
    servers_gross = (TECHNICAL_INFRASTRUCTURE[2025]["value"]
                     * SERVERS_SHARE_OF_TECHNICAL_INFRA)
    base_life = USEFUL_LIVES["servers_and_network_equipment"]
    base_charge = servers_gross / base_life

    rows = []
    for name, life, note in [
        ("보수 (4년)", 4, "AI 가속기 세대교체 주기에 맞춤. 상각을 앞당김"),
        ("중립 (6년, 보고 기준)", 6, "알파벳이 실제로 적용 중인 내용연수"),
        ("낙관 (8년)", 8, "구형 가속기를 추론용으로 오래 쓴다고 가정"),
    ]:
        charge = servers_gross / life
        delta = charge - base_charge
        ebit = y["ebit"] - delta
        nopat = ebit * (1 - tax)
        rows.append({
            "scenario": name,
            "useful_life_years": life,
            "annual_server_depreciation": charge,
            "delta_vs_reported": delta,
            "adjusted_operating_income": ebit,
            "adjusted_nopat": nopat,
            "adjusted_roic": div(nopat, ic_avg),
            "adjusted_operating_margin": div(ebit, y["revenue"]),
            "note": note,
        })
    return {
        "policy": {
            "servers_and_network_equipment_years": base_life,
            "buildings_years": USEFUL_LIVES["data_centre_and_office_buildings"],
            "corporate_and_other_years": USEFUL_LIVES["corporate_and_other"],
            "servers_share_of_technical_infrastructure": SERVERS_SHARE_OF_TECHNICAL_INFRA,
            "source": "FY2025 10-K, Property and Equipment 회계정책 주석",
        },
        "servers_gross_2025": servers_gross,
        "reported_depreciation_2025": y["raw"]["depreciation_amortization"],
        "service_life_change_2023": SERVICE_LIFE_CHANGE_2023,
        "scenarios": rows,
    }


# ---------------------------------------------------------------------------
# 메모 9 - 미개시 임차 약정
# ---------------------------------------------------------------------------

def lease_capitalisation(goog):
    """What the not-yet-commenced leases are, and ROIC if they were capitalised.

    Under ASC 842 a lease goes on the balance sheet at commencement, not at
    signature. These commence between 2026 and 2031, so today there is no asset,
    no liability and no payment - which is also why capitalising them into this
    year's ROIC is the wrong operation: it would put capital in the denominator
    that, exactly like assets not yet in service, is producing nothing yet.

    The adjustment that IS defensible today is the leases already running:
    operating-lease liabilities sit outside interest-bearing debt in this model,
    so the capital they represent is currently invisible to the ratio.
    """
    y = yr(goog, 2025)
    total_undiscounted = LEASES_NOT_COMMENCED_SHORT + LEASES_NOT_COMMENCED_LONG

    # Present value under two shapes for the payment schedule. Both start in
    # 2028 (the midpoint of the stated 2026-2031 commencement window) and run
    # level; the term is the variable, since the filing gives a 1-25 year range.
    pvs = {}
    for term in (10, 15, 20):
        payment = total_undiscounted / term
        r = OPERATING_LEASE_DISCOUNT_RATE
        annuity = sum(payment / (1 + r) ** t for t in range(1, term + 1))
        pvs[term] = annuity / (1 + r) ** 2      # discounted back from 2028

    op_lease_avg = (OPERATING_LEASE_LIABILITY[2024] + OPERATING_LEASE_LIABILITY[2025]) / 2
    fin_lease_avg = (FINANCE_LEASE_LIABILITY[2024] + FINANCE_LEASE_LIABILITY[2025]) / 2
    ic_avg = y["invested_capital_avg"]

    rows = [{
        "basis": "보고 기준 (현행)",
        "added_capital": 0.0,
        "invested_capital_avg": ic_avg,
        "roic": y["roic"],
        "note": "이미 개시된 금융리스는 유형자산에 포함돼 투하자본에 들어가 있습니다",
    }, {
        "basis": "개시된 운용리스 부채를 자본으로 가산",
        "added_capital": op_lease_avg,
        "invested_capital_avg": ic_avg + op_lease_avg,
        "roic": div(y["nopat"], ic_avg + op_lease_avg),
        "note": ("이 모델은 운용리스 부채를 이자부부채로 보지 않아 자산·부채가 "
                 "상계돼 투하자본에서 사실상 빠져 있습니다. 이 조정만이 오늘 "
                 "시점에 정당합니다"),
    }]
    for term, pv in pvs.items():
        rows.append({
            "basis": f"미개시 임차약정까지 자본화 (평균 {term}년 계약 가정)",
            "added_capital": op_lease_avg + pv,
            "invested_capital_avg": ic_avg + op_lease_avg + pv,
            "roic": div(y["nopat"], ic_avg + op_lease_avg + pv),
            "note": "참고용. 아직 이익을 내지 않는 자본을 분모에만 넣는 계산입니다",
        })

    return {
        "what_they_are": (
            "FY2025 10-K 유동성 항목의 원문: '2025년 12월 31일 기준, 우리는 아직 "
            "개시되지 않은, 주로 데이터센터와 관련된 리스를 체결했으며 단기 58억 "
            "달러, 장기 527억 달러의 향후 리스료가 있다. 이 리스들은 2026년에서 "
            "2031년 사이에 개시되며 해지불능 계약기간은 주로 1년에서 25년이다.' "
            "즉 제3자 데이터센터 운영사로부터 빌려 쓰기로 이미 서명한 전산 설비 "
            "임차 계약입니다."),
        "short_term": LEASES_NOT_COMMENCED_SHORT,
        "long_term": LEASES_NOT_COMMENCED_LONG,
        "total_undiscounted": total_undiscounted,
        "commence_between": LEASE_COMMENCE_RANGE,
        "term_range_years": LEASE_TERM_RANGE,
        "power_purchase_agreement_2026": POWER_PURCHASE_AGREEMENT_2026,
        "why_not_on_balance_sheet": (
            "ASC 842는 리스 자산과 부채를 '개시일(commencement date)'에 인식하도록 "
            "합니다. 서명일이 아닙니다. 개시 전에는 사용할 자산을 넘겨받지도 "
            "않았고 지급 의무도 시작되지 않았으므로 자산도 부채도 없습니다. "
            "회계상의 누락이 아니라 정의상 아직 자본이 아닌 것이고, 그래서 10-K는 "
            "이를 주석의 약정사항으로 공시합니다."),
        "present_value_estimates": pvs,
        "already_commenced": {
            "operating_lease_right_of_use_asset": 15_221e6,
            "operating_lease_liability": OPERATING_LEASE_LIABILITY[2025],
            "finance_lease_right_of_use_asset": 4_797e6,
            "finance_lease_liability": FINANCE_LEASE_LIABILITY[2025],
        },
        "scenarios": rows,
    }


# ---------------------------------------------------------------------------
# 메모 7 - 현금은 정말 놀고 있는가
# ---------------------------------------------------------------------------

def cash_analysis(goog):
    """Where FY2025's cash actually went, against the "idle cash" claim.

    The memo is right to push back. The first document called the $78bn net cash
    "undeployed capital" and marked capital allocation down for it. The cash-flow
    statement does not support that as stated.
    """
    cf = CASH_FLOW_2025
    net_securities = (cf["purchases_of_marketable_securities"]
                      + cf["maturities_and_sales_of_marketable_securities"])
    net_debt = cf["debt_issued"] + cf["debt_repaid"]
    committed = sum(v["price"] for v in PENDING_ACQUISITIONS.values())
    y = yr(goog, 2025)
    avg_liquidity = (95_657e6 + CASH_AND_SHORT_TERM_SECURITIES_2025) / 2
    avg_debt = (yr(goog, 2024)["interest_bearing_debt"]
                + y["interest_bearing_debt"]) / 2
    return {
        "cash_flow": cf,
        "net_purchases_of_marketable_securities": net_securities,
        "net_debt_raised": net_debt,
        "cash_and_equivalents_only": cf["cash_end_of_period"],
        "cash_and_short_term_securities": CASH_AND_SHORT_TERM_SECURITIES_2025,
        "short_term_securities": (CASH_AND_SHORT_TERM_SECURITIES_2025
                                  - cf["cash_end_of_period"]),
        "interest_income": INTEREST_INCOME_2025,
        "interest_expense_net_of_capitalised": INTEREST_EXPENSE_NET_2025,
        "interest_capitalised": INTEREST_CAPITALISED_2025,
        "yield_on_liquidity": div(INTEREST_INCOME_2025, avg_liquidity),
        "cost_of_debt": div(INTEREST_EXPENSE_NET_2025 + INTEREST_CAPITALISED_2025,
                            avg_debt),
        "average_liquidity": avg_liquidity,
        "average_debt": avg_debt,
        "pending_acquisitions": PENDING_ACQUISITIONS,
        "committed_to_acquisitions": committed,
        "net_cash": y["cash"] - y["interest_bearing_debt"],
        "net_cash_after_commitments": (y["cash"] - y["interest_bearing_debt"]
                                       - committed),
        "capex_guidance": ("FY2025 10-K: '2026년에는 2025년 대비 기술 인프라 "
                           "투자를 상당히 늘릴 것으로 예상한다'"),
    }


# ---------------------------------------------------------------------------
# 메모 3·12 - 현금흐름 추정에서 출발하는 3시나리오 DCF
# ---------------------------------------------------------------------------

def dcf_scenarios(analysis, goog):
    """A DCF built from projected cash flows rather than one normalised number.

    Free cash flow here is NOPAT less net investment, where net investment is
    the reinvestment rate applied to NOPAT. That formulation is what lets the
    build-out be modelled honestly: Alphabet is currently reinvesting 61% of
    after-tax operating profit, which is why owner earnings look thin, and the
    question the valuation turns on is whether that rate comes down as the
    data centres finish. Each scenario names its own path.

    Net cash is added at the end because the DCF values the business, and the
    cash is a separate asset that already exists.
    """
    y = yr(goog, 2025)
    nopat0 = y["nopat"]
    capex = y["raw"]["capex"]
    da = y["raw"]["depreciation_amortization"]
    d_wc = y["raw"]["change_in_working_capital"] or 0
    reinvest_now = div(capex - da + d_wc, nopat0)
    net_cash = y["cash"] - y["interest_bearing_debt"]
    shares = goog["shares_outstanding_used"]
    market_cap = goog["market_cap_usd"]

    # The reinvestment rate is NOT a free assumption. Buffett's own identity
    # fixes it: growth costs capital, and how much depends on what that capital
    # earns. So each year's rate is derived, RR = g / incremental ROIC, and the
    # scenario's real assumption is the incremental return - the number the
    # memos have been asking about all along. Setting the two independently is
    # how a valuation ends up assuming a company grows without paying for it.
    specs = [
        {"name": "보수", "growth": 0.08, "fade_to": 0.03, "incremental_roic": 0.12,
         "discount": 0.12, "terminal_growth": 0.020,
         "story": ("검색 점유율이 생성형 AI에 잠식되기 시작하고, 데이터센터 투자는 "
                   "해자를 지키는 비용으로 계속 나갑니다. 신규 자본의 수익률이 "
                   "12%까지 내려가 자본비용을 겨우 넘습니다.")},
        {"name": "중립", "growth": 0.11, "fade_to": 0.04, "incremental_roic": 0.20,
         "discount": 0.10, "terminal_growth": 0.025,
         "story": ("클라우드가 계약잔고대로 인도되고 검색은 완만히 성장합니다. "
                   "신규 자본이 최근 4년의 실측치(19.7%)와 같은 수익률을 냅니다.")},
        {"name": "낙관", "growth": 0.15, "fade_to": 0.05, "incremental_roic": 0.30,
         "discount": 0.08, "terminal_growth": 0.030,
         "story": ("AI 인프라가 완공되며 수익을 내기 시작하고, 계약잔고가 마진 "
                   "개선과 함께 인식됩니다. 신규 자본의 수익률이 전체 기간 "
                   "실측치(31.9%)에 가까운 30%로 회복됩니다.")},
    ]

    out = []
    for s in specs:
        rows = []
        n = 10
        pv_sum = 0.0
        nopat = nopat0
        for t in range(1, n + 1):
            # Growth fades linearly from the starting rate to the fade target,
            # so no scenario assumes a decade at its opening pace.
            g = s["growth"] + (s["fade_to"] - s["growth"]) * (t - 1) / (n - 1)
            rr = g / s["incremental_roic"]
            nopat = nopat * (1 + g)
            fcf = nopat * (1 - rr)
            pv = fcf / (1 + s["discount"]) ** t
            pv_sum += pv
            rows.append({"year": t, "growth": g, "nopat": nopat,
                         "reinvestment_rate": rr, "free_cash_flow": fcf,
                         "present_value": pv})
        tg = s["terminal_growth"]
        terminal_rr = tg / s["incremental_roic"]
        terminal_fcf = rows[-1]["nopat"] * (1 + tg) * (1 - terminal_rr)
        terminal = terminal_fcf / (s["discount"] - tg)
        terminal_pv = terminal / (1 + s["discount"]) ** n
        ev = pv_sum + terminal_pv
        equity = ev + net_cash
        out.append({
            "scenario": s["name"],
            "story": s["story"],
            "assumptions": {k: s[k] for k in
                            ("growth", "fade_to", "incremental_roic",
                             "discount", "terminal_growth")},
            "first_year_reinvestment_rate": rows[0]["reinvestment_rate"],
            "terminal_reinvestment_rate": terminal_rr,
            "projection": rows,
            "pv_of_forecast": pv_sum,
            "terminal_value": terminal,
            "pv_of_terminal": terminal_pv,
            "terminal_share_of_value": div(terminal_pv, ev),
            "enterprise_value": ev,
            "equity_value": equity,
            "value_per_share": div(equity, shares),
            "upside_vs_market": div(equity - market_cap, market_cap),
            "margin_of_safety": div(equity - market_cap, equity),
        })

    def value(growth, fade_to, inc_roic, disc, tg):
        pv_sum, nopat = 0.0, nopat0
        n = 10
        for t in range(1, n + 1):
            g = growth + (fade_to - growth) * (t - 1) / (n - 1)
            nopat *= (1 + g)
            pv_sum += nopat * (1 - g / inc_roic) / (1 + disc) ** t
        terminal_pv = ((nopat * (1 + tg) * (1 - tg / inc_roic) / (disc - tg))
                       / (1 + disc) ** n)
        return pv_sum + terminal_pv + net_cash

    # What the market is paying for, inverted three ways.
    #
    # First the ceiling: what the neutral growth path is worth if growth were
    # free - infinite return on new capital, nothing reinvested, every dollar of
    # NOPAT paid out. Nothing about the growth path can be worth more than this,
    # so it settles whether the price is reachable by better returns alone.
    free_growth_ceiling = value(0.11, 0.04, 1e9, 0.10, 0.025)

    # Then the growth today's price demands, at a 10% discount and an
    # incremental return as good as the full-period record (30%).
    lo, hi = 0.0, 0.29
    for _ in range(90):
        mid = (lo + hi) / 2
        if value(mid, mid / 3, 0.30, 0.10, 0.025) < market_cap:
            lo = mid
        else:
            hi = mid
    implied_growth = (lo + hi) / 2
    implied_growth_reachable = implied_growth < 0.2899

    lo, hi = 0.026, 0.40
    for _ in range(90):
        mid = (lo + hi) / 2
        if value(0.11, 0.04, 0.20, mid, 0.025) > market_cap:
            lo = mid
        else:
            hi = mid
    implied_discount = (lo + hi) / 2

    # The inversion that actually matters. Growth alone cannot justify the
    # price: as g approaches the incremental return, the capital growth
    # consumes swallows the cash it produces and value stops rising. So the
    # question is what return the new capital must earn.
    implied_inc_roic = {}
    for disc in (0.10, 0.08):
        ceiling = value(0.11, 0.04, 1e9, disc, 0.025)
        if ceiling < market_cap:
            implied_inc_roic[f"{disc:.0%}"] = {
                "value": None,
                "ceiling_at_free_growth": ceiling,
                "note": ("이 할인율에서는 신규 자본이 아무리 높은 수익률을 내도 "
                         "— 성장에 자본이 전혀 들지 않는다고 가정해도 — 현재 "
                         "시가총액에 닿지 않습니다"),
            }
            continue
        lo, hi = 0.05, 3.0
        for _ in range(90):
            mid = (lo + hi) / 2
            if value(0.11, 0.04, mid, disc, 0.025) < market_cap:
                lo = mid
            else:
                hi = mid
        implied_inc_roic[f"{disc:.0%}"] = {
            "value": (lo + hi) / 2, "ceiling_at_free_growth": ceiling, "note": None}

    # 메모 12: 중립에서 낙관으로 가는 길을, 가정 하나씩 바꿔가며.
    bridge = []
    base = dict(growth=0.11, fade_to=0.04, inc_roic=0.20, disc=0.10, tg=0.025)
    steps = [
        ("중립 시나리오", {}, "출발점"),
        ("+ 건설 중인 자본이 가동에 들어가 신규 ROIC 25%",
         {"inc_roic": 0.25},
         f"미사용 자산 ${ASSETS_NOT_YET_IN_SERVICE[2025]/1e9:.0f}B이 분모에만 들어가 "
         "있는 상태가 해소되면 측정되는 신규 수익률이 올라갑니다"),
        ("+ 계약잔고가 인식되며 성장률 13%", {"inc_roic": 0.25, "growth": 0.13},
         f"잔고 ${BACKLOG[2025]/1e9:.0f}B의 24개월 인식분만으로도 현재 클라우드 "
         "매출을 넘습니다"),
        ("+ 계약 확보로 현금흐름의 확실성이 높아져 할인율 8%",
         {"inc_roic": 0.25, "growth": 0.13, "disc": 0.08},
         "계약으로 확보된 매출은 광고 매출보다 예측 가능성이 높습니다"),
        ("+ 신규 ROIC가 전체 기간 실측치 수준(30%)까지 회복",
         {"inc_roic": 0.30, "growth": 0.13, "disc": 0.08},
         "= 낙관 시나리오에 준하는 가정"),
    ]
    for name, override, why in steps:
        p = dict(base); p.update(override)
        v = value(p["growth"], p["fade_to"], p["inc_roic"], p["disc"], p["tg"])
        bridge.append({
            "step": name, "why": why,
            "assumptions": p,
            "equity_value": v,
            "value_per_share": div(v, shares),
            "margin_of_safety": div(v - market_cap, v),
        })

    return {
        "starting_nopat": nopat0,
        "current_reinvestment_rate": reinvest_now,
        "implied_growth_at_current_price": implied_growth,
        "implied_growth_reachable": implied_growth_reachable,
        "implied_incremental_roic_at_current_price": implied_inc_roic,
        "free_growth_ceiling_at_neutral_path": free_growth_ceiling,
        "implied_discount_rate_at_current_price": implied_discount,
        "implied_note": ("첫 번째는 할인율 10%·재투자율 경로를 중립과 동일하게 두고 "
                         "현재 주가를 정당화하는 첫해 성장률을, 두 번째는 중립 성장 "
                         "경로가 맞다고 볼 때 현재 주가가 주는 연 수익률을 역산한 "
                         "값입니다."),
        "bridge_to_optimistic": bridge,
        "reinvestment_definition": "(설비투자 − 감가상각 + 운전자본증감) ÷ NOPAT",
        "net_cash": net_cash,
        "shares_outstanding": shares,
        "market_cap": market_cap,
        "price": goog["price"]["price"],
        "risk_free_rate": analysis["risk_free_rate"]["rate"],
        "wacc": goog["summary"]["wacc"],
        "scenarios": out,
    }


# ---------------------------------------------------------------------------
# 메모 10 - 15% 성장은 얼마나 그럴듯한가
# ---------------------------------------------------------------------------

def growth_feasibility(goog):
    """What sustaining 15% growth would demand, from the reinvestment identity.

    g = 재투자율 x 신규 ROIC. Both halves are observable, so the question
    "how likely is 15%?" becomes "what incremental return would 15% require,
    and has this company ever earned it?"
    """
    y = yr(goog, 2025)
    nopat = y["nopat"]
    reinvest = div(y["raw"]["capex"] - y["raw"]["depreciation_amortization"]
                   + (y["raw"]["change_in_working_capital"] or 0), nopat)
    s = goog["summary"]
    first, last = goog["years"][0], goog["years"][-1]
    n = last["fiscal_year"] - first["fiscal_year"]
    rev_cagr = (last["revenue"] / first["revenue"]) ** (1 / n) - 1
    rev_cagr_3y = (last["revenue"] / yr(goog, 2022)["revenue"]) ** (1 / 3) - 1

    targets = []
    for g in (0.08, 0.10, 0.12, 0.15, 0.18):
        targets.append({
            "growth_target": g,
            "required_incremental_roic": div(g, reinvest),
            "vs_full_period_incremental": div(g / reinvest, s["incremental_roic"]),
        })
    return {
        "reinvestment_rate": reinvest,
        "identity": "지속가능 성장률 g = 재투자율 × 신규 ROIC",
        "incremental_roic_full_period": s["incremental_roic"],
        "roic_median": s["roic_10y_median"],
        "implied_growth_at_full_period_incremental": reinvest * s["incremental_roic"],
        "revenue_cagr_since_2014": rev_cagr,
        "revenue_cagr_3y": rev_cagr_3y,
        "revenue_growth_latest": div(last["revenue"] - yr(goog, 2024)["revenue"],
                                     yr(goog, 2024)["revenue"]),
        "owner_earnings_cagr": s["owner_earnings_cagr"],
        "targets": targets,
        "base_effect": {
            "revenue_2014": first["revenue"],
            "revenue_2025": last["revenue"],
            "revenue_if_15pct_for_10y": last["revenue"] * 1.15 ** 10,
        },
    }


def main():
    analysis, goog = load()
    y25 = yr(goog, 2025)
    out = {
        "generated_at_utc": analysis["generated_at_utc"],
        "filings_read": FILINGS,
        "corrections": [
            {"id": 1,
             "what": "기술 인프라 시계열의 기준 불일치",
             "was": "FY2022 $66.3B → FY2025 $203.7B (3배), 인프라 $1당 매출 "
                    "$4.27 → $1.98",
             "now": "FY2023 $112.5B → FY2025 $203.7B (1.8배), 인프라 $1당 매출 "
                    "$2.73 → $1.98",
             "why": ("FY2024 10-K까지의 'technology equipment'는 서버·네트워크 "
                     "장비만이고, FY2025 10-K의 'technical infrastructure'는 "
                     "데이터센터 토지·건물·리스홀드까지 포함합니다. 서로 다른 "
                     "선을 이어 붙여 증가폭이 과장됐습니다. 새 기준으로 소급된 "
                     "가장 이른 해가 FY2023이라 FY2022는 뺐습니다.")},
            {"id": 2,
             "what": "건설 중인 자산의 위치",
             "was": "'FY2025 기술 인프라 $203.7B 중 $78.6B가 건설 중'",
             "now": "'건설 중인 자산 $78.6B는 기술 인프라와 별개 항목'",
             "why": ("FY2025 유형자산 주석: 기술 인프라 203,679 + 사무공간 48,348 "
                     "+ 기타 14,463 = 사용 중인 유형자산 266,490, 감가상각누계액 "
                     "(98,485), 여기에 미사용 자산 78,592를 더해 순액 246,597. "
                     "미사용 자산은 사용 중 자산 바깥에 있습니다. 따라서 인프라 "
                     "$1당 매출은 이미 가동 자산 기준이었고, 놀고 있는 자본이 "
                     "실제로 섞여 있던 곳은 투하자본입니다.")},
        ],
        "segments": {
            "detail_2025": SEGMENT_2025,
            "services_revenue_lines": SERVICES_REVENUE_LINES_2025,
            "total_revenue_2025": y25["revenue"],
        },
        "roic_ex_construction": roic_excluding_construction(goog),
        "infrastructure_corrected": infrastructure_corrected(goog),
        "incremental_roic_by_year": incremental_roic_by_year(goog),
        "backlog": backlog_into_numerator(goog),
        "depreciation": depreciation_scenarios(goog),
        "leases": lease_capitalisation(goog),
        "cash": cash_analysis(goog),
        "dcf": dcf_scenarios(analysis, goog),
        "growth": growth_feasibility(goog),
        "capital_intensity_series": [
            {"fiscal_year": z["fiscal_year"],
             "invested_capital": z["invested_capital"],
             "revenue": z["revenue"],
             "capital_intensity": z["capital_intensity"],
             "capex_to_revenue": div(z["raw"]["capex"], z["revenue"])}
            for z in goog["years"]
        ],
    }
    path = os.path.join(HERE, "alphabet_memo2.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(f"alphabet_memo2 -> {path}")

    r = out["roic_ex_construction"][-1]
    print(f"  ROIC ex-construction FY2025: {r['roic_ex_construction']:.1%} "
          f"(보고 {r['roic_reported']:.1%})")
    for s in out["dcf"]["scenarios"]:
        print(f"  DCF {s['scenario']}: 주당 ${s['value_per_share']:,.0f} "
              f"(현재 ${out['dcf']['price']:.2f}), 안전마진 {s['margin_of_safety']:+.1%}")
    print(f"  재투자율 {out['growth']['reinvestment_rate']:.1%}, 15% 성장에 필요한 "
          f"신규 ROIC {out['growth']['targets'][3]['required_incremental_roic']:.1%}")


if __name__ == "__main__":
    main()
