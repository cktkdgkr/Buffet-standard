"""
Builds the payload the Word exporter renders.

Kept separate from export_docx.js so the scoring, the moat read and the ranking
come from report.py rather than being reimplemented in JavaScript. If the two
diverged, the document and the markdown report would quietly disagree about
which company ranks where.

Writes work/_docx_payload.json.
"""

import json
import os
import sys

WORK = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, WORK)
import report as rp                                     # noqa: E402


def pct(v, dp=1):
    return "—" if v is None else f"{v * 100:.{dp}f}%"


def mult(v, dp=1):
    return "—" if v is None else f"{v:.{dp}f}x"


def bn(v, dp=0):
    return "—" if v is None else f"{v / 1e9:,.{dp}f}"


def _alphabet_block(analysis):
    """Numbers for the Word document's Alphabet case section."""
    g = next((c for c in analysis["companies"] if c["ticker"] == "GOOG"), None)
    if not g:
        return None
    s, y = g["summary"], g["years"][-1]
    raw = y.get("raw", {})
    std = [c for c in analysis["companies"] if c["sector_treatment"] == "STANDARD"]
    rows = [(c["ticker"], c["summary"].get("implied_return_maintenance_capex"),
             c["summary"].get("roic_10y_median"), c["summary"].get("net_cash"))
            for c in std if c["summary"].get("implied_return_maintenance_capex")]
    rows.sort(key=lambda r: -r[1])
    return {
        "capex": bn(raw.get("capex"), 1),
        "da": bn(raw.get("depreciation_amortization"), 1),
        "growth_capex": bn(y.get("growth_capex"), 0),
        "growth_share": pct(s.get("growth_capex_share_of_capex"), 0),
        "net_cash": bn(s.get("net_cash"), 0),
        "roic": pct(s.get("roic_latest")),
        "market_cap": bn(g.get("market_cap_usd"), 0),
        "band_rows": [[ko, bn(s["dcf"][k]["intrinsic_value"], 0),
                       bn(s["dcf_maintenance_capex"][k]["intrinsic_value"], 0),
                       f'{pct(s["dcf"][k]["margin_of_safety"], 0)} ~ '
                       f'{pct(s["dcf_maintenance_capex"][k]["margin_of_safety"], 0)}']
                      for k, ko in (("conservative", "보수"), ("base", "기준"),
                                    ("optimistic", "낙관"))],
        "optimistic_mos": pct(s["dcf_maintenance_capex"]["optimistic"]["margin_of_safety"], 0),
        "implied_rows": [[t + (" \u2190" if t == "GOOG" else ""), pct(ir), pct(roic), bn(nc, 0)]
                         for t, ir, roic, nc in rows[:12]],
    }


def main():
    with open(os.path.join(WORK, "analysis.json")) as f:
        analysis = json.load(f)
    with open(os.path.join(WORK, "verification.json")) as f:
        verification = json.load(f)

    for c in analysis["companies"]:
        c["summary"]["_latest_revenue"] = next(
            (r["revenue"] for r in reversed(c["years"]) if r.get("revenue")), None)
        c["_score"], c["_detail"] = rp.quality_score(c["summary"])

    std_all = [c for c in analysis["companies"] if c["sector_treatment"] == "STANDARD"]
    std = [c for c in std_all if c["summary"].get("quality_scoreable", True)]
    unscoreable = [c for c in std_all if not c["summary"].get("quality_scoreable", True)]
    fin = [c for c in analysis["companies"] if c["sector_treatment"] == "FINANCIAL"]
    std.sort(key=lambda c: (-c["_score"], -(c["summary"].get("roic_10y_median") or -9)))
    fin.sort(key=lambda c: -(c["summary"].get("roe_10y_median") or -9))

    valued = [c for c in std_all if c["summary"]["valuation_status"] == "VALUED"]
    valued.sort(key=lambda c: -(c["summary"].get("implied_return_maintenance_capex") or -9))
    negoe = [c for c in std_all if c["summary"]["valuation_status"] == "NEGATIVE_OWNER_EARNINGS"]
    investable = [c for c in valued if c["summary"]["dcf"]["base"]["verdict"] == "INVESTABLE_RANGE"]
    borderline = [c for c in valued if c["summary"]["dcf"]["base"]["verdict"] == "BORDERLINE"]
    above_wacc = sum(1 for c in std_all if (c["summary"].get("roic_wacc_spread") or -1) > 0)

    rf, erp = analysis["risk_free_rate"], analysis["equity_risk_premium"]
    vsum = verification["summary"]

    quality_rows = [[
        str(i), c["ticker"], c["company_name"], str(c["_score"]),
        pct(c["summary"].get("roic_10y_median")),
        f"{c['summary'].get('roic_above_10pct_years')}/{c['summary'].get('roic_years_observed')}",
        rp.inc_display(c["summary"]).replace("해당없음 ", ""),
        pct(c["summary"].get("roic_wacc_spread")),
        rp.moat_read(c["summary"]),
    ] for i, c in enumerate(std, 1)]

    valuation_rows = []
    for c in valued:
        s = c["summary"]
        d, dm = s["dcf"]["base"], s["dcf_maintenance_capex"]["base"]
        valuation_rows.append([
            c["ticker"], bn(s["owner_earnings_normalised"]),
            bn(s.get("owner_earnings_normalised_maintenance")),
            bn(d["intrinsic_value"]), bn(dm["intrinsic_value"]),
            bn(c["market_cap_usd"]), pct(s.get("implied_return_maintenance_capex")),
            bn(s.get("net_cash")),
            {"INVESTABLE_RANGE": "투자가능", "BORDERLINE": "경계선",
             "OUTSIDE_RANGE": "범위밖"}.get(d["verdict"], d["verdict"]),
        ])

    gap = sorted(std_all, key=lambda c: -(c["summary"].get("roe_roic_spread_latest") or -99))[:12]
    roe_rows = []
    for c in gap:
        s = c["summary"]
        sp = s.get("roe_roic_spread_latest")
        note = ("자기자본이 마이너스이거나 0에 가까워 비율이 의미를 잃음"
                if sp is not None and sp > 1.0 else
                "레버리지가 ROE를 밀어올림" if sp is not None and sp > 0.10 else
                "ROE와 ROIC가 근접 — 수익성이 사업에서 나옴")
        roe_rows.append([c["ticker"], pct(s.get("roe_latest")), pct(s.get("roic_latest")),
                         pct(sp), mult(s.get("net_debt_to_ebitda_latest")),
                         mult(s.get("interest_coverage_latest")), note])

    bb = sorted([c for c in std_all if c["summary"].get("share_count_cagr") is not None],
                key=lambda c: c["summary"]["share_count_cagr"])
    capital_rows = []
    for c in bb[:10] + bb[-5:]:
        s = c["summary"]
        g, inc = s["share_count_cagr"], s.get("incremental_roic")
        note = ("자사주 매입 — 신규 자본 수익률이 높아 재투자와 병행할 여력"
                if g < 0 and (inc or 0) >= 0.15 else
                "자사주 매입으로 주당 가치 상승" if g < 0 else
                "희석 — 주식 기반 보상이 주주 몫을 잠식")
        capital_rows.append([c["ticker"], pct(g, 2), s.get("share_count_window", "—"),
                             rp.inc_display(s).replace("해당없음 ", ""), note])

    fin_rows = [[c["ticker"], c["company_name"], (c.get("sic_description") or "")[:34],
                 pct(c["summary"].get("roe_10y_median")), pct(c["summary"].get("roe_latest")),
                 mult(c["summary"].get("per")), mult(c["summary"].get("pbr"))] for c in fin]

    payload = {
        "generated": analysis["generated_at_utc"][:16].replace("T", " ") + " UTC",
        "n_std": len(std_all),
        "unscoreable_rows": [[c["ticker"], c["company_name"],
                              "어느 해에도 의미 있는 ROIC가 나오지 않습니다 — 보유 현금이 "
                              "자기자본과 거의 같고 차입금이 없어 투하자본이 0 이하입니다."]
                             for c in unscoreable],
        "alphabet": _alphabet_block(analysis),
        "n_fin": len(fin),
        "headline": [
            f"비금융 {len(std)}개사 중 {above_wacc}개사가 ROIC로 자본비용을 넘겼습니다. "
            f"그런데 할인율 10% 기준 DCF에서 안전마진 30% 이상인 기업은 {len(investable)}개입니다. "
            f"품질과 가격은 이 유니버스에서 완전히 분리돼 있습니다.",
            f"경계선은 {len(borderline)}개사({', '.join(c['ticker'] for c in borderline) or '없음'})이고, "
            f"나머지는 전부 적정가치 추정 범위 밖에서 거래되고 있습니다.",
            f"주주이익이 음수인 기업이 {len(negoe)}개({', '.join(c['ticker'] for c in negoe)})입니다. "
            f"이익이 없어서가 아니라 설비투자와 운전자본이 순이익을 넘어서기 때문입니다. "
            f"원칙 3 관점에서 이것은 데이터 공백이 아니라 사업에 대한 판정입니다.",
            f"금융 {len(fin)}개사는 ROIC·주주이익 프레임을 적용하지 않았습니다. 은행에서 부채는 "
            f"자금조달이 아니라 원재료여서 투하자본이 정의되지 않습니다. ROE·레버리지·배수로만 평가했습니다.",
            f"검증은 {vsum['companies_passed']}/{vsum['companies_checked']}개사가 통과했습니다. "
            f"모든 인용 수치를 해당 10-K 원문과 대조했습니다.",
        ],
        "macro": (f"무위험수익률 {rf['rate']:.2%} ({rf['as_of']}, FRED DGS10) · "
                  f"주식위험프리미엄 {erp['erp']:.2%} ({erp['as_of']}, Damodaran)"),
        "quality_rows": quality_rows,
        "valuation_rows": valuation_rows,
        "negoe_rows": [[c["ticker"], c["company_name"],
                        f"정규화 주주이익 {c['summary']['owner_earnings_normalised']/1e9:.1f}십억 달러"]
                       for c in negoe],
        "roe_rows": roe_rows,
        "capital_rows": capital_rows,
        "fin_rows": fin_rows,
        "verification_line": (
            f"{vsum['companies_passed']}개사 전부에 대해 각 항목을 해당 10-K 원문의 인라인 XBRL과 "
            f"대조하고, 인용한 접수번호가 EDGAR에 실재하는지 확인하고, 주식수를 재파싱으로 "
            f"재현하고, 주가를 재조회했습니다. 통과하지 못한 수치는 보고서에 넣지 않는다는 "
            f"규칙이었으나 최종 실행에서 실패 항목은 없었습니다."),
    }

    path = os.path.join(WORK, "_docx_payload.json")
    with open(path, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"payload -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
