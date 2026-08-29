"""
Alphabet deep dive - the numbers behind the memo answers and the case study.

Everything here is computed from primary sources already in the repository:
work/analysis.json (which is verified against the filings by verify.py), plus
the segment, property and backlog disclosures read straight out of Alphabet's
own 10-K inline XBRL. Nothing is estimated where the filing declines to say.

Writes work/alphabet.json.
"""

import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Read from Alphabet's 10-K inline XBRL.
#
# companyfacts drops any fact that carries a dimension, which is every segment
# and every property category. They exist only inside the filing document, so
# they are transcribed here with the accession that carries them. verify.py
# re-reads the same documents for the undimensioned figures; these were pulled
# by the same routine.
# ---------------------------------------------------------------------------

FILINGS = {
    2025: "0001652044-26-000018",
    2024: "0001652044-25-000014",
    2023: "0001652044-24-000022",
}

# us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax and
# us-gaap:OperatingIncomeLoss, dimensioned on StatementBusinessSegmentsAxis.
SEGMENTS = {
    2023: {
        "구글 서비스": {"revenue": 272_543e6, "operating_income": 95_858e6},
        "구글 클라우드": {"revenue": 33_088e6, "operating_income": 1_716e6},
        "기타 베팅": {"revenue": 1_527e6, "operating_income": -4_095e6},
        "전사 공통비용": {"revenue": None, "operating_income": -9_186e6},
    },
    2024: {
        "구글 서비스": {"revenue": 304_930e6, "operating_income": 121_263e6},
        "구글 클라우드": {"revenue": 43_229e6, "operating_income": 6_112e6},
        "기타 베팅": {"revenue": 1_648e6, "operating_income": -4_444e6},
        "전사 공통비용": {"revenue": None, "operating_income": -10_541e6},
    },
    2025: {
        "구글 서비스": {"revenue": 342_721e6, "operating_income": 139_404e6},
        "구글 클라우드": {"revenue": 58_705e6, "operating_income": 13_910e6},
        "기타 베팅": {"revenue": 1_537e6, "operating_income": -7_515e6},
        "전사 공통비용": {"revenue": None, "operating_income": -16_760e6},
    },
}

# us-gaap:PropertyPlantAndEquipment...BeforeAccumulatedDepreciationAndAmortization,
# dimensioned on PropertyPlantAndEquipmentByTypeAxis. FY2022/23 come from the
# FY2023 filing, which used the pre-2025 category labels; the technical
# infrastructure line is "technology equipment" there.
PPE_GROSS = {
    2022: {"technical_infrastructure": 66_267e6, "under_construction": 27_657e6,
           "total": 171_710e6, "label_note": "FY2023 10-K categories (technology equipment)"},
    2023: {"technical_infrastructure": 80_594e6, "under_construction": 35_229e6,
           "total": 201_803e6, "label_note": "FY2023 10-K categories (technology equipment)"},
    2024: {"technical_infrastructure": 141_852e6, "under_construction": 50_597e6,
           "total": 250_426e6, "label_note": "FY2025 10-K categories, incl. finance-lease ROU"},
    2025: {"technical_infrastructure": 203_679e6, "under_construction": 78_592e6,
           "total": 345_082e6, "label_note": "FY2025 10-K categories, incl. finance-lease ROU"},
}

# us-gaap:RevenueRemainingPerformanceObligation. Alphabet says roughly half is
# expected to be recognised within 24 months.
BACKLOG = {2023: 74_100e6, 2024: 93_200e6, 2025: 242_800e6}

# What the segment note does NOT carry. Established by enumerating every fact
# in the FY2025 10-K that has a StatementBusinessSegmentsAxis dimension: the
# axis appears on revenue, operating income, costs and expenses, labour and
# goodwill, and on nothing else.
SEGMENT_DISCLOSURE_ABSENT = [
    "자산 (us-gaap:Assets)", "설비투자", "감가상각", "유형자산",
]

DEPRECIATION = {2021: 10_273e6, 2022: 13_475e6, 2023: 11_946e6,
                2024: 15_311e6, 2025: 21_136e6}
CAPEX = {2021: 24_640e6, 2022: 31_485e6, 2023: 32_251e6,
         2024: 52_535e6, 2025: 91_447e6}
# us-gaap:Depreciation dimensioned on ChangeInAccountingEstimateByTypeAxis =
# ServiceLifeMember: the FY2023 reduction from extending server lives.
SERVICE_LIFE_CHANGE_2023 = -3_900e6
LEASES_NOT_YET_COMMENCED = 5_800e6 + 52_700e6
SBC_2025 = 27_100e6
BUYBACK_2025 = 45_709e6
RND_2025 = 61_087e6


def load():
    with open(os.path.join(HERE, "analysis.json")) as fh:
        analysis = json.load(fh)
    goog = next(c for c in analysis["companies"] if c["ticker"] == "GOOG")
    return analysis, goog


def year(goog, fy):
    return next(y for y in goog["years"] if y["fiscal_year"] == fy)


def pct(a, b):
    return None if not b else a / b


def segment_view(goog):
    """Margins by segment, and the capital question the filing will not answer."""
    out = []
    for fy in sorted(SEGMENTS):
        row = {"fiscal_year": fy, "segments": {}}
        for name, s in SEGMENTS[fy].items():
            row["segments"][name] = {
                "revenue": s["revenue"],
                "operating_income": s["operating_income"],
                "operating_margin": pct(s["operating_income"], s["revenue"]),
            }
        out.append(row)
    # Cloud's own trajectory: revenue and profit are disclosed, so the income
    # half of a segment return is knowable even though the capital half is not.
    cloud = {fy: SEGMENTS[fy]["구글 클라우드"] for fy in SEGMENTS}
    return {
        "by_year": out,
        "cloud_operating_income_growth": {
            "2023": cloud[2023]["operating_income"],
            "2024": cloud[2024]["operating_income"],
            "2025": cloud[2025]["operating_income"],
            "margin_2023": pct(cloud[2023]["operating_income"], cloud[2023]["revenue"]),
            "margin_2025": pct(cloud[2025]["operating_income"], cloud[2025]["revenue"]),
        },
        "segment_assets_disclosed": False,
        "segment_capex_disclosed": False,
        "absent_from_segment_note": SEGMENT_DISCLOSURE_ABSENT,
        "why": ("Alphabet's chief operating decision maker is not given assets by "
                "segment, so ASC 280 does not require the disclosure and Alphabet "
                "does not make it. Enumerating every dimensioned fact in the "
                "FY2025 10-K confirms it: the segment axis appears on revenue, "
                "operating income, costs, labour and goodwill, and on nothing "
                "else. A directly computed Google Cloud ROIC is therefore not "
                "derivable from the filings, and any figure presented as one is "
                "an allocation the analyst chose, not a number Alphabet reported."),
        "source_accession": FILINGS[2025],
    }


def cloud_roic_band(goog):
    """What Cloud's ROIC would be across the plausible allocation range.

    The allocation is the assumption, so it is exposed as a band rather than a
    point, and the basis of each bound is named.
    """
    y25 = year(goog, 2025)
    tax = y25["tax_rate"]
    cloud_oi = SEGMENTS[2025]["구글 클라우드"]["operating_income"]
    cloud_nopat = cloud_oi * (1 - tax)
    cloud_rev_share = SEGMENTS[2025]["구글 클라우드"]["revenue"] / (
        sum(s["revenue"] for s in SEGMENTS[2025].values() if s["revenue"]))
    ti_net_est = PPE_GROSS[2025]["technical_infrastructure"] * (
        1 - 98_485e6 / 345_082e6)  # accumulated D&A applied pro rata
    bands = []
    for share, basis in [
        (cloud_rev_share, "매출 비중과 동일하게 배분 — 하한. 클라우드가 매출 대비 "
                          "연산 자원을 많이 쓰므로 과소배분입니다"),
        (0.25, "기술 인프라의 4분의 1을 배분"),
        (0.40, "기술 인프라의 5분의 2를 배분 — 상한. 이 수준이면 클라우드가 검색보다 "
               "인프라를 더 많이 쓴다는 뜻이 됩니다"),
    ]:
        cap = ti_net_est * share + SEGMENTS[2025]["구글 클라우드"]["revenue"] * 0.0
        bands.append({
            "infrastructure_share": share,
            "basis": basis,
            "allocated_capital": cap,
            "roic": pct(cloud_nopat, cap),
        })
    return {
        "cloud_operating_income_2025": cloud_oi,
        "effective_tax_rate": tax,
        "cloud_nopat_2025": cloud_nopat,
        "technical_infrastructure_gross_2025": PPE_GROSS[2025]["technical_infrastructure"],
        "technical_infrastructure_net_estimate": ti_net_est,
        "net_estimate_method": ("gross technical infrastructure scaled by the "
                                "consolidated ratio of net to gross PP&E "
                                "(1 - 98,485/345,082); Alphabet does not publish "
                                "accumulated depreciation by category"),
        "bands": bands,
        "caveat": ("Every row is an allocation. The one figure here that is "
                   "Alphabet's own is the $13.9bn operating income; the capital "
                   "denominators are constructed."),
    }


def infrastructure_returns(goog):
    """The consolidated read on the build-out, which needs no allocation."""
    rows = []
    prev = None
    for fy in sorted(PPE_GROSS):
        ti = PPE_GROSS[fy]["technical_infrastructure"]
        cip = PPE_GROSS[fy]["under_construction"]
        y = year(goog, fy)
        rows.append({
            "fiscal_year": fy,
            "technical_infrastructure_gross": ti,
            "under_construction": cip,
            "revenue_per_dollar_of_infrastructure": pct(y["revenue"], ti),
            "operating_income_per_dollar_of_infrastructure": pct(y["ebit"], ti),
            "capex": CAPEX[fy],
            "depreciation": DEPRECIATION[fy],
            "capex_to_depreciation": pct(CAPEX[fy], DEPRECIATION[fy]),
            "infrastructure_added": None if prev is None else ti - prev,
        })
        prev = ti
    return rows


def capex_era_incremental(goog):
    """Incremental return over the build-out window, the way Buffett frames it.

    "The best business to own is one that over an extended period can employ
    large amounts of incremental capital at very high rates of return" (1992).
    That is a question about the change in earnings against the change in
    capital, and it needs no segment data at all.
    """
    out = {}
    for start, end, label in [(2021, 2025, "FY2021→FY2025 (AI 설비투자 구간)"),
                              (2022, 2025, "FY2022→FY2025"),
                              (2014, 2025, "FY2014→FY2025 (전체 기간)")]:
        a, b = year(goog, start), year(goog, end)
        d_nopat = b["nopat"] - a["nopat"]
        d_cap = b["invested_capital"] - a["invested_capital"]
        cum_capex = sum(CAPEX[f] for f in range(max(start + 1, 2021), end + 1)) \
            if start >= 2020 else None
        out[label] = {
            "nopat_start": a["nopat"], "nopat_end": b["nopat"],
            "invested_capital_start": a["invested_capital"],
            "invested_capital_end": b["invested_capital"],
            "delta_nopat": d_nopat, "delta_invested_capital": d_cap,
            "incremental_roic": pct(d_nopat, d_cap),
            "cumulative_capex": cum_capex,
        }
    return out


def roe_trap(goog):
    """Whether Alphabet's ROE is the flattering kind or the flattered-against kind."""
    y = year(goog, 2025)
    eq = y["total_equity"]
    debt = y["interest_bearing_debt"]
    cash = y["cash"]
    ni_op = y["net_income_operating"]
    ic = y["invested_capital"]
    # Equity carrying no operating role: the net cash pile. Strip it from both
    # the numerator's yield and the denominator to see the operating business.
    net_cash = cash - debt
    eq_avg = y["raw"]["total_equity_prior"]
    eq_avg = (eq + eq_avg) / 2 if eq_avg else eq
    return {
        "roe_latest": y["roe"],
        "roe_on_operating_earnings": pct(ni_op, eq_avg),
        "roic_latest": y["roic"],
        "spread_roe_minus_roic": y["roe_roic_spread"],
        "total_equity": eq,
        "total_equity_average": eq_avg,
        "interest_bearing_debt": debt,
        "cash_and_short_term_investments": cash,
        "net_cash": net_cash,
        "invested_capital": ic,
        "identity": ("자기자본 − 순현금 = 자기자본 + 이자부부채 − 현금 = 투하자본. "
                     f"${eq/1e9:.0f}B − ${net_cash/1e9:.0f}B = ${ic/1e9:.0f}B. "
                     "알파벳에서 ROE와 ROIC를 갈라놓는 것은 부채가 아니라 이 순현금입니다."),
        "debt_to_equity": pct(debt, eq),
        "net_income_operating": ni_op,
        "reading": ("ROE below ROIC is the opposite of the trap. The trap is a "
                    "company whose ROE is propped up by borrowed money, so the "
                    "return on equity flatters a business that earns less on the "
                    "whole capital it uses. Alphabet's ROE is dragged DOWN "
                    "instead, by equity that is parked in cash and securities "
                    "rather than working."),
        "roe_10y_median": goog["summary"]["roe_10y_median"],
        "roic_10y_median": goog["summary"]["roic_10y_median"],
    }


def owner_earnings_ladder(goog):
    """Every rung between operating cash flow and the figure used for value."""
    y = year(goog, 2025)
    r = y["raw"]
    ocf, capex, da = r["operating_cash_flow"], r["capex"], r["depreciation_amortization"]
    inv_at = y["investment_gains_after_tax"]
    return [
        {"step": "① 보고 순이익", "value": r["net_income"],
         "note": "10-K 손익계산서. 주주이익의 출발점이 되는 '보고 이익'"},
        {"step": "② − 투자평가손익 (세후)", "value": y["net_income_operating"],
         "note": f"세전 ${(y['investment_gains'] or 0)/1e9:.1f}B를 실효세율 "
                 f"{y['tax_rate']*100:.1f}%로 조정한 ${(inv_at or 0)/1e9:.1f}B 차감. "
                 f"사업이 번 돈이 아니라 보유 지분의 평가이익"},
        {"step": "③ + 감가상각", "value": y["net_income_operating"] + da,
         "note": f"비현금 비용 ${da/1e9:.1f}B 가산 (버핏 정의의 (b)항)"},
        {"step": "④ − 운전자본 증감",
         "value": y["net_income_operating"] + da - (r["change_in_working_capital"] or 0),
         "note": f"영업 운전자본이 흡수한 현금 "
                 f"{'−' if (r['change_in_working_capital'] or 0) < 0 else ''}"
                 f"${abs(r['change_in_working_capital'] or 0)/1e9:.1f}B "
                 f"(현금·단기차입금 제외 기준)"},
        {"step": "⑤ − 설비투자 전액 = 주주이익 (하한)", "value": y["owner_earnings"],
         "note": f"자본예산 ${capex/1e9:.1f}B 전부를 차감. 성장투자까지 비용으로 보므로 "
                 f"가장 보수적인 값"},
        {"step": "⑤′ − 유지 설비투자만 = 주주이익 (상한)",
         "value": y["owner_earnings_maintenance_capex"],
         "note": f"버핏 정의의 (c)항은 '경쟁 지위와 판매량을 유지하는 데 필요한' "
                 f"설비투자입니다. 그 대용치로 감가상각 ${da/1e9:.1f}B만 차감"},
        {"step": "[참고] 영업현금흐름 − 설비투자", "value": ocf - capex,
         "note": f"흔히 쓰이는 잉여현금흐름. 영업현금흐름 ${ocf/1e9:.1f}B에서 설비투자를 "
                 f"뺀 값이며, 평가이익은 이미 제외되어 있으나 주식보상비용이 "
                 f"비현금항목으로 되더해져 있어 주주이익보다 큽니다"},
    ]


def valuation_state(analysis, goog):
    s = goog["summary"]
    mc = goog["market_cap_usd"]
    return {
        "market_cap": mc,
        "price": goog["price"]["price"],
        "price_as_of": goog["price"]["as_of_utc"],
        "shares_outstanding": goog["shares_outstanding_used"],
        "risk_free_rate": analysis["risk_free_rate"],
        "wacc": s["wacc"],
        "dcf": s["dcf"],
        "dcf_maintenance_capex": s["dcf_maintenance_capex"],
        "band": s["intrinsic_value_band_base"],
        "implied_return_total_capex": s["implied_return_total_capex"],
        "implied_return_maintenance_capex": s["implied_return_maintenance_capex"],
        "per": s["per"],
        "per_on_operating_earnings": pct(mc, year(goog, 2025)["net_income_operating"]),
        "price_to_owner_earnings": s["price_to_owner_earnings"],
        "net_cash": s["net_cash"],
        "verdict_base": s["verdict_base"],
    }


def main():
    analysis, goog = load()
    out = {
        "generated_at_utc": analysis["generated_at_utc"],
        "company": goog["company_name"],
        "cik": goog["cik"],
        "filings_read": FILINGS,
        "segment": segment_view(goog),
        "cloud_roic_band": cloud_roic_band(goog),
        "infrastructure": infrastructure_returns(goog),
        "backlog_remaining_performance_obligation": BACKLOG,
        "backlog_note": ("us-gaap:RevenueRemainingPerformanceObligation. 알파벳은 이 중 "
                         "절반가량이 24개월 내 매출로 인식될 것으로 봅니다. 계약은 "
                         "체결됐지만 아직 인도되지 않은 매출이며, 설비투자가 수요를 "
                         "앞질렀는지 따라가고 있는지를 가르는 가장 직접적인 증거입니다."),
        "capex_era_incremental_roic": capex_era_incremental(goog),
        "roe_trap": roe_trap(goog),
        "owner_earnings_ladder": owner_earnings_ladder(goog),
        "valuation": valuation_state(analysis, goog),
        "accounting_watch_items": {
            "service_life_change_2023": SERVICE_LIFE_CHANGE_2023,
            "service_life_note": ("Extending server useful lives cut FY2023 "
                                  "depreciation by $3.9bn. Depreciation is the "
                                  "proxy for maintenance capex in the upper "
                                  "bound of the value band, so a longer assumed "
                                  "life raises that bound directly."),
            "leases_not_yet_commenced": LEASES_NOT_YET_COMMENCED,
            "leases_note": ("Data-centre leases signed but not yet started. Off "
                            "the balance sheet today, capital committed all the "
                            "same."),
            "share_based_compensation_2025": SBC_2025,
            "buyback_2025": BUYBACK_2025,
            "share_count_cagr": goog["summary"]["share_count_cagr"],
            "research_and_development_2025": RND_2025,
        },
        "quality": {
            "roic_10y_median": goog["summary"]["roic_10y_median"],
            "roic_latest": goog["summary"]["roic_latest"],
            "roic_years_observed": goog["summary"]["roic_years_observed"],
            "roic_above_10pct_years": goog["summary"]["roic_above_10pct_years"],
            "incremental_roic": goog["summary"]["incremental_roic"],
            "roic_wacc_spread": goog["summary"]["roic_wacc_spread"],
            "capital_intensity_latest": goog["summary"]["capital_intensity_latest"],
            "roic_tangible_10y_median": goog["summary"]["roic_tangible_10y_median"],
            "operating_margin_latest": goog["summary"]["operating_margin_latest"],
            "owner_earnings_cagr": goog["summary"]["owner_earnings_cagr"],
        },
    }
    path = os.path.join(HERE, "alphabet.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(f"alphabet -> {path}")

    b = out["cloud_roic_band"]
    print(f"  Cloud NOPAT FY2025 ${b['cloud_nopat_2025']/1e9:.1f}B; "
          f"allocated ROIC band "
          f"{b['bands'][2]['roic']:.1%}..{b['bands'][0]['roic']:.1%}")
    for label, v in out["capex_era_incremental_roic"].items():
        print(f"  incremental ROIC {label}: {v['incremental_roic']:.1%}")
    print(f"  backlog 2023->2025: ${BACKLOG[2023]/1e9:.0f}B -> ${BACKLOG[2025]/1e9:.0f}B")


if __name__ == "__main__":
    main()
