"""
SpaceX and Tesla on the Alphabet template: what the capital earns, and how
much of it is not earning yet.

The Alphabet work turned on one distinction. A company pouring money into
infrastructure shows a falling ROIC whether or not the business is getting
worse, because the denominator grows the moment cash is spent while the
numerator waits for the asset to be switched on. Separating capital in service
from capital under construction took Alphabet's incremental ROIC from 25% to
51% - same filings, same definition, one line of the PP&E note.

Both companies here are in that position, and SpaceX is in it to a degree
Alphabet never was: $23.7bn of its $110.0bn gross PP&E was construction in
progress at 30 September 2026, against $4.6bn nine months earlier.

Three views of ROIC, therefore:

  reported          NOPAT / (equity + debt - cash)
  operating         ... less goodwill and intangibles, so an acquisition does
                    not flatter or punish the operating return
  in service        ... less construction in progress, which is the return on
                    the capital actually running

And for SpaceX a fourth thing the consolidated figures hide completely: the
segments. Starlink, the launch business and the AI business have different
economics, and the filings give revenue, operating income and capital
expenditure for each.

Writes work/spx/spx_tsla.json.
"""

import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from collect_spx_tsla import find_row                          # noqa: E402

RAW = os.path.join(HERE, "spx", "spx_tsla_raw.json")
ROIC = os.path.join(HERE, "roic", "roic.json")
PRICES = os.path.join(HERE, "roic", "prices.json")
OUT = os.path.join(HERE, "spx", "spx_tsla.json")

MM = 1e6
TAX_DEFAULT = 0.21          # US federal statutory, for a loss-making year
WACC = 0.10                 # the project's hurdle, per instruction


def col_index(report, want):
    """Which column of a rendering a period label belongs to."""
    if not report:
        return None
    for i, c in enumerate(report.get("columns", [])):
        if want in c.replace("\n", " "):
            return i
    return None


def val(row, i):
    if not row or i is None or i >= len(row["values"]):
        return None
    return row["values"][i]


# --------------------------------------------------------------------- SpaceX
def spacex(raw):
    co = raw["companies"]["SPCX"]
    q = co["filings"]["10-Q_2026-09-30"]
    pro = co["prospectus"]

    seg, bs, ppe, back = (q["segments"], q["balance_sheet"],
                          q["ppe_schedule"], q["backlog"])

    # The segment note's four columns are Q3 2026, Q3 2025, 9M 2026, 9M 2025.
    # Nine months is the comparable pair; a single quarter of a business like
    # this says very little.
    i26, i25 = 2, 3

    def seg_rows(context):
        """Revenue, operating income and capex for one segment."""
        out = {}
        for key, element in (("revenue",
                              "RevenueFromContractWithCustomerExcludingAssessedTax"),
                             ("operating_income", "OperatingIncomeLoss"),
                             # Segment capex is tagged as an addition to
                             # long-lived assets, not as the cash-flow
                             # payment line.
                             ("capex",
                              "SegmentExpenditureAdditionToLongLivedAssets"),
                             ("depreciation_amortisation",
                              "DepreciationDepletionAndAmortization")):
            r = find_row(q["segments"], element=element, context=context)
            out[key] = {"9m_2026": val(r, i26), "9m_2025": val(r, i25)}
        return out

    segments = {
        "Space": seg_rows("Operating Segments | Space"),
        "Connectivity": seg_rows("Operating Segments | Connectivity"),
        "SI": seg_rows("Operating Segments | SI"),
    }
    consolidated = seg_rows("Operating Segments")

    # Balance sheet: September 2026 and December 2025.
    b26, b25 = 0, 1

    def bs_val(element, i, *labels):
        r = find_row(bs, *labels, element=element)
        return val(r, i)

    def ppe_val(context, i):
        r = find_row(ppe, element="PropertyPlantAndEquipmentGross",
                     context=context)
        return val(r, i)

    def balance(i):
        equity = bs_val("StockholdersEquity", i, "total shareholders")
        pref = bs_val("TemporaryEquityCarryingAmountAttributableToParent", i,
                      "redeemable convertible preferred")
        cash = bs_val("CashAndCashEquivalentsAtCarryingValue", i,
                      "cash and cash equivalents")
        securities = bs_val("MarketableSecuritiesCurrent", i,
                            "marketable securities")
        debt_cur = bs_val("LongTermDebtAndCapitalLeaseObligationsCurrent", i)
        debt_nc = bs_val("LongTermDebtAndCapitalLeaseObligations", i)
        goodwill = bs_val("Goodwill", i, "goodwill")
        intangibles = bs_val("IntangibleAssetsNetExcludingGoodwill", i,
                             "intangible assets")
        cip = ppe_val("Construction-in-progress", i)
        return {
            "equity": equity,
            "redeemable_preferred": pref,
            "cash_and_securities": (cash or 0) + (securities or 0),
            "debt": (debt_cur or 0) + (debt_nc or 0),
            "goodwill": goodwill, "intangibles": intangibles,
            "construction_in_progress": cip,
            "ppe_gross": ppe_val(None, i),
            "ppe_net": bs_val("PropertyPlantAndEquipmentNet", i,
                              "property, plant, and equipment, net"),
            "total_assets": bs_val("Assets", i, "total assets"),
        }

    sheets = {"2026-09-30": balance(b26), "2025-12-31": balance(b25)}

    # Annual history, which exists only in the prospectus.
    def pro_row(table, *needles, exact=False):
        if not pro or not pro.get(table):
            return None
        for label, values, _raw in pro[table]:
            low = label.lower().strip()
            if exact:
                if low == needles[0].lower():
                    return values
            elif all(n.lower() in low for n in needles):
                return values
        return None

    # Summary operations columns: Q1 2026, Q1 2025, FY2025, FY2024, FY2023.
    # Exact labels: "revenue" alone also matches the per-share block's
    # headings, and "net income" matches the per-share lines beneath it.
    ops = {"revenue": pro_row("summary_operations", "revenue", exact=True),
           "costs": pro_row("summary_operations", "total costs and expenses",
                            exact=True),
           "operating_income": pro_row("summary_operations",
                                       "income (loss) from operations",
                                       exact=True),
           "net_income": pro_row("summary_operations", "net income (loss)",
                                 exact=True)}
    annual = {}
    for n, idx in (("FY2025", 2), ("FY2024", 3), ("FY2023", 4)):
        annual[n] = {k: (v[idx] * MM if v and idx < len(v)
                         and v[idx] is not None else None)
                     for k, v in ops.items()}

    bs_pro = {"cash": pro_row("summary_balance_sheet", "cash and cash"),
              "ppe_net": pro_row("summary_balance_sheet", "property, plant"),
              "total_assets": pro_row("summary_balance_sheet", "total assets"),
              "total_liabilities": pro_row("summary_balance_sheet",
                                           "total liabilities"),
              "preferred": pro_row("summary_balance_sheet",
                                   "redeemable convertible"),
              "equity": pro_row("summary_balance_sheet",
                                "total shareholders")}
    # Summary balance-sheet columns: March 2026, December 2025, December 2024.
    annual_bs = {}
    for n, idx in (("2026-03-31", 0), ("2025-12-31", 1), ("2024-12-31", 2)):
        annual_bs[n] = {k: (v[idx] * MM if v and idx < len(v)
                            and v[idx] is not None else None)
                        for k, v in bs_pro.items()}

    segrev = {}
    for name in ("Space", "Connectivity", "AI", "Total revenues"):
        v = pro_row("segment_revenue", name)
        if v:
            segrev[name] = {"FY2025": v[0] * MM if v[0] else None,
                            "FY2024": v[1] * MM if len(v) > 1 and v[1]
                            else None,
                            "FY2023": v[2] * MM if len(v) > 2 and v[2]
                            else None}

    # Shares outstanding by class from the balance sheet parenthetical. There
    # is no dei:EntityCommonStockSharesOutstanding in companyfacts for this
    # filer, and the equity-activity note states the same totals, so the two
    # agree independently: Class A 8,240m + Class B 5,339m + Class C nil.
    par = co["filings"]["10-Q_2026-09-30"].get("shares_parenthetical")
    shares_out = None
    if par:
        total = 0.0
        for cls in ("Class A Common Stock", "Class B Common Stock",
                    "Class C Common Stock"):
            r = find_row(par, "shares outstanding", context=cls)
            if r and r["values"] and r["values"][0] is not None:
                total += r["values"][0]
        shares_out = total or None

    backlog = {
        "remaining_performance_obligation":
            val(find_row(back, "backlog revenue"), 0),
        "deferred_revenue": val(find_row(back, "deferred revenue"), 0),
        "deferred_revenue_prior": val(find_row(back, "deferred revenue"), 2),
    }

    return {"segments_9m": segments, "consolidated_9m": consolidated,
            "balance_sheets": sheets, "annual_from_prospectus": annual,
            "balance_from_prospectus": annual_bs,
            "segment_revenue_annual": segrev, "backlog": backlog,
            "shares_outstanding": shares_out,
            "meta": co["meta"],
            "prospectus_source": pro.get("source_url") if pro else None,
            "quarterly_source": q["balance_sheet"]["source_url"]}


# ---------------------------------------------------------------------- Tesla
def tesla(raw, roic):
    co = raw["companies"]["TSLA"]
    k = co["filings"]["10-K_2025-12-31"]
    q = co["filings"]["10-Q_2026-09-30"]

    series = next(c for c in roic["companies"] if c["ticker"] == "TSLA")

    def ppe_block(f, i):
        """
        Tesla's PP&E components by label, not by element.

        Every row in its schedule carries the same defref - the rendering
        points at the axis rather than the line item - so matching on the
        element name returns the first row for all of them. The labels are
        distinct and the dimension headings carry the component names.

        The AI-infrastructure line is the same asset class under two names:
        the FY2025 10-K calls it "AI infrastructure" and the Q3 2026 10-Q
        "SI infrastructure", so both are tried.
        """
        ppe = f["ppe_schedule"]
        g = lambda ctx: val(find_row(ppe, context=ctx, patterns_required=False), i)
        ai = g("SI infrastructure")
        if ai is None:
            ai = g("AI infrastructure")
        return {
            # The gross line comes first in the schedule and the net line
            # after the accumulated-depreciation row, so an exact label is
            # needed to tell them apart.
            "gross": val(find_row(ppe, "property, plant and equipment",
                                  exact=True), i),
            "net": val(find_row(ppe, "property, plant and equipment, net",
                                exact=True), i),
            "accumulated_depreciation":
                val(find_row(ppe, "accumulated depreciation"), i),
            "construction_in_progress": g("Construction in progress"),
            "ai_infrastructure": ai,
            "machinery": g("Machinery, equipment"),
            "land_and_buildings": g("Land and buildings"),
        }

    def bs_block(f, i):
        bs = f["balance_sheet"]
        v = lambda el, *lbl: val(find_row(bs, *lbl, element=el), i)
        return {
            "equity": v("StockholdersEquity", "total stockholders"),
            "cash": v("CashAndCashEquivalentsAtCarryingValue",
                      "cash and cash equivalents"),
            "short_term_investments": v("ShortTermInvestments",
                                        "short-term investments"),
            "debt_current": v(None, "current portion of debt"),
            "debt_noncurrent": v(None, "debt and finance leases, net of"),
            "deferred_revenue_current": v(None, "deferred revenue, current"),
            "deferred_revenue_noncurrent":
                v(None, "deferred revenue, net of current"),
            "goodwill": v("Goodwill", "goodwill"),
            "total_assets": v("Assets", "total assets"),
        }

    return {
        "annual_roic": [
            {k2: y.get(k2) for k2 in
             ("fiscal_year", "period_end", "revenue", "operating_income",
              "effective_tax_rate", "nopat", "total_equity",
              "interest_bearing_debt", "cash_and_short_term_investments",
              "invested_capital", "invested_capital_avg", "roic",
              "operating_margin", "confidence", "roic_status")}
            for y in series["years"] if y["fiscal_year"] >= 2015],
        "summary": series["summary"],
        "ppe": {"2025-12-31": ppe_block(k, 0), "2024-12-31": ppe_block(k, 1),
                "2026-09-30": ppe_block(q, 0)},
        "balance": {"2025-12-31": bs_block(k, 0),
                    "2026-09-30": bs_block(q, 0)},
        "deferred_revenue_activity": [
            [r["label"], r["values"]] for r in k["backlog"]["rows"]
        ] if k.get("backlog") else None,
        "shares_outstanding": tesla_shares(),
        "meta": co["meta"],
        "source": k["balance_sheet"]["source_url"],
    }


def tesla_shares():
    """
    The latest cover-page share count, from the company's own filing.

    The earlier study used the FY2025 10-K figure of 3,752m, which was already
    nine months and 200 million shares out of date by the time this ran.
    """
    import sec_cache
    facts, _, _ = sec_cache.companyfacts(1318605,
                                         os.path.join(HERE, "roic", "cache"))
    node = facts["facts"].get("dei", {}).get(
        "EntityCommonStockSharesOutstanding")
    if not node:
        return None
    best = None
    for unit, entries in node["units"].items():
        for e in entries:
            if best is None or e["end"] > best["end"]:
                best = e
    return best["val"] if best else None


# ---------------------------------------------------------------- the ratios
#
# Three denominators, from the widest to the narrowest, and the gap between
# them is the point.
#
#   reported     equity + redeemable preferred + debt - cash and securities
#   operating    ... less goodwill and acquired intangibles
#   in service   ... less construction in progress
#
# Redeemable preferred belongs in capital even though US GAAP parks it outside
# equity: SpaceX carried $38.8bn of it at December 2025 and none at September
# 2026, because the IPO converted it. Leaving it out would show the capital
# base shrinking by $38.8bn in a year when the company raised money.
#
# Goodwill is separated because of the Cursor merger - $42.7bn of stock for a
# business with an implied equity value of $60bn, which put $36.6bn of new
# goodwill on the balance sheet in one quarter. Including it answers "what does
# the return look like to a shareholder who paid for the acquisition"; excluding
# it answers "what do the operating assets earn". Both are worth knowing and
# they are not the same question.
#
# Construction in progress is the Alphabet adjustment: capital already spent on
# assets that are not yet running and cannot yet earn.


def roic_views(nopat, opening, closing):
    """ROIC on each denominator, averaging opening and closing capital."""
    out = {}
    for view in ("reported", "operating", "in_service"):
        o, c = opening.get(view), closing.get(view)
        if None in (o, c) or nopat is None:
            out[view] = None
            continue
        avg = (o + c) / 2.0
        out[view] = {"opening": o, "closing": c, "average": avg,
                     "roic": (nopat / avg) if avg > 0 else None,
                     "spread_vs_wacc": ((nopat / avg) - WACC)
                     if avg > 0 else None}
    return out


def capital_stack(b):
    """The three denominators from one balance sheet."""
    base = ((b.get("equity") or 0) + (b.get("redeemable_preferred") or 0)
            + (b.get("debt") or 0) - (b.get("cash_and_securities") or 0))
    operating = base - (b.get("goodwill") or 0) - (b.get("intangibles") or 0)
    return {"reported": base, "operating": operating,
            "in_service": operating - (b.get("construction_in_progress") or 0)}


def spacex_ratios(s, price):
    sep, dec = s["balance_sheets"]["2026-09-30"], \
        s["balance_sheets"]["2025-12-31"]
    c = s["consolidated_9m"]
    oi_9m = c["operating_income"]["9m_2026"]

    # Annualised from nine months. Crude, and stated as such: the fourth
    # quarter of a business adding $20bn of plant a quarter is not three months
    # of the first nine. It is here because a nine-month numerator against an
    # average annual denominator would understate the return by a third, which
    # would be a worse error than this one.
    oi_annualised = oi_9m * 4.0 / 3.0
    nopat = oi_annualised * (1 - TAX_DEFAULT)

    views = roic_views(nopat, capital_stack(dec), capital_stack(sep))
    shares = s.get("shares_outstanding")
    market_cap = (shares * price) if (shares and price) else None

    segs = {}
    for name, d in s["segments_9m"].items():
        rev = d["revenue"]["9m_2026"]
        oi = d["operating_income"]["9m_2026"]
        cx = d["capex"]["9m_2026"]
        segs[name] = {
            "revenue_9m": rev, "operating_income_9m": oi, "capex_9m": cx,
            "operating_margin": (oi / rev) if rev else None,
            "capex_to_revenue": (cx / rev) if rev else None,
            # Operating income less the capital it absorbed in the same
            # period. Invested capital is not disclosed by segment, so this is
            # the honest substitute: a business whose own cash generation
            # covers its own build is a different proposition from one that
            # does not, and no invented denominator is needed to see it.
            "operating_income_less_capex": (oi - cx)
            if None not in (oi, cx) else None,
            "revenue_growth_9m": ((rev / d["revenue"]["9m_2025"] - 1)
                                  if d["revenue"]["9m_2025"] else None),
        }

    return {
        "operating_income_9m_2026": oi_9m,
        "operating_income_annualised": oi_annualised,
        "nopat_annualised": nopat,
        "tax_note": f"세전 적자이므로 법정세율 {TAX_DEFAULT:.0%} 적용",
        "views": views,
        "segments": segs,
        "shares_outstanding": shares,
        "price": price,
        "market_cap": market_cap,
        "capital_not_in_service_share":
            sep["construction_in_progress"] / sep["ppe_gross"],
        "goodwill_share_of_capital":
            (sep["goodwill"] or 0) / capital_stack(sep)["reported"],
        "backlog_to_revenue_annualised":
            s["backlog"]["remaining_performance_obligation"]
            / (c["revenue"]["9m_2026"] * 4.0 / 3.0),
    }


def tesla_ratios(t, price):
    years = {y["fiscal_year"]: y for y in t["annual_roic"]}
    ppe = t["ppe"]

    # The in-service view on the last three year-ends, which is as far back as
    # the PP&E note goes in the filings collected here.
    in_service = {}
    for when, fy in (("2025-12-31", 2025), ("2024-12-31", 2024)):
        y = years.get(fy)
        if not y or y["invested_capital"] is None:
            continue
        cip = ppe[when]["construction_in_progress"]
        in_service[fy] = {
            "invested_capital": y["invested_capital"],
            "construction_in_progress": cip,
            "capital_in_service": y["invested_capital"] - cip,
            "cip_share": cip / y["invested_capital"],
        }
    for fy in sorted(in_service):
        prior = in_service.get(fy - 1)
        y = years[fy]
        if prior and y["nopat"] is not None:
            avg = (in_service[fy]["capital_in_service"]
                   + prior["capital_in_service"]) / 2.0
            in_service[fy]["roic_in_service"] = y["nopat"] / avg
            in_service[fy]["roic_reported"] = y["roic"]

    # Incremental return: the change in NOPAT against the change in capital.
    # This is the number that says what the recent spending is earning, as
    # opposed to what the whole history earned.
    incremental = {}
    for label, a, b in (("FY2020→FY2025", 2020, 2025),
                        ("FY2022→FY2025", 2022, 2025),
                        ("FY2023→FY2025", 2023, 2025)):
        ya, yb = years.get(a), years.get(b)
        if not ya or not yb or None in (ya["nopat"], yb["nopat"],
                                        ya["invested_capital"],
                                        yb["invested_capital"]):
            continue
        d_nopat = yb["nopat"] - ya["nopat"]
        d_cap = yb["invested_capital"] - ya["invested_capital"]
        incremental[label] = {
            "delta_nopat": d_nopat, "delta_capital": d_cap,
            "incremental_roic": (d_nopat / d_cap) if d_cap else None,
        }

    shares = t.get("shares_outstanding")
    market_cap = (shares * price) if (shares and price) else None
    latest = years.get(2025)
    return {
        "in_service": in_service,
        "incremental": incremental,
        "shares_outstanding": shares, "price": price,
        "market_cap": market_cap,
        "latest_fiscal_year": 2025,
        "roic_latest": latest["roic"] if latest else None,
        "roic_peak": max((y["roic"] for y in t["annual_roic"]
                          if y["roic"] is not None), default=None),
        "roic_median_10y": t["summary"]["roic_median"],
        "years_above_wacc": t["summary"]["years_above_wacc"],
        "years_usable": t["summary"]["years_usable"],
        "price_to_nopat": (market_cap / latest["nopat"])
        if market_cap and latest and latest["nopat"] else None,
    }


def main():
    raw = json.load(open(RAW))
    roic = json.load(open(ROIC))
    prices = json.load(open(PRICES))["prices"]

    out = {"generated": date.today().isoformat(), "wacc": WACC,
           "prices": {t: prices[t] for t in ("SPCX", "TSLA") if t in prices},
           "SPCX": spacex(raw), "TSLA": tesla(raw, roic)}

    out["SPCX"]["ratios"] = spacex_ratios(
        out["SPCX"], out["prices"].get("SPCX", {}).get("price"))
    out["TSLA"]["ratios"] = tesla_ratios(
        out["TSLA"], out["prices"].get("TSLA", {}).get("price"))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)

    s = out["SPCX"]
    print(f"오늘 {out['generated']} · WACC {WACC:.0%}\n")
    print("스페이스X — 9개월 사업부별 (백만 달러)")
    print(f"  {'사업부':<16}{'매출 9M26':>11}{'영업이익':>11}{'마진':>8}"
          f"{'capex':>11}{'capex/매출':>11}")
    for name, d in s["segments_9m"].items():
        rev = d["revenue"]["9m_2026"]
        oi = d["operating_income"]["9m_2026"]
        cx = d["capex"]["9m_2026"]
        print(f"  {name:<16}{rev/MM:>11,.0f}{oi/MM:>11,.0f}"
              f"{oi/rev:>8.0%}{cx/MM:>11,.0f}{cx/rev:>11.1f}x")
    c = s["consolidated_9m"]
    print(f"  {'합계':<16}{c['revenue']['9m_2026']/MM:>11,.0f}"
          f"{c['operating_income']['9m_2026']/MM:>11,.0f}"
          f"{c['operating_income']['9m_2026']/c['revenue']['9m_2026']:>8.0%}"
          f"{c['capex']['9m_2026']/MM:>11,.0f}"
          f"{c['capex']['9m_2026']/c['revenue']['9m_2026']:>11.1f}x")

    print("\n스페이스X — 연간 (등록신고서, 백만 달러)")
    print(f"  {'연도':<10}{'매출':>11}{'영업이익':>11}{'순이익':>11}")
    for n in ("FY2023", "FY2024", "FY2025"):
        a = s["annual_from_prospectus"][n]
        f = lambda x: "—" if x is None else f"{x/MM:,.0f}"
        print(f"  {n:<10}{f(a['revenue']):>11}"
              f"{f(a['operating_income']):>11}{f(a['net_income']):>11}")

    print("\n스페이스X — 투하자본 구성 (백만 달러)")
    for when, b in s["balance_sheets"].items():
        print(f"  {when}: 자기자본 {b['equity']/MM:,.0f} · 우선주 "
              f"{(b['redeemable_preferred'] or 0)/MM:,.0f} · 차입금 "
              f"{b['debt']/MM:,.0f} · 현금·유가증권 "
              f"{b['cash_and_securities']/MM:,.0f}")
        print(f"              PP&E 총액 {b['ppe_gross']/MM:,.0f} · "
              f"건설중 {b['construction_in_progress']/MM:,.0f} "
              f"({b['construction_in_progress']/b['ppe_gross']:.0%}) · "
              f"영업권 {(b['goodwill'] or 0)/MM:,.0f}")
    bk = s["backlog"]
    print(f"  계약잔고(RPO) {bk['remaining_performance_obligation']/MM:,.0f} · "
          f"선수금 {bk['deferred_revenue']/MM:,.0f}")

    t = out["TSLA"]
    print("\n테슬라 — 연간 ROIC")
    print(f"  {'연도':<9}{'매출':>11}{'영업이익':>11}{'ROIC':>9}")
    for y in t["annual_roic"]:
        if y["fiscal_year"] < 2016:
            continue
        print(f"  FY{y['fiscal_year']:<7}{y['revenue']/MM:>11,.0f}"
              f"{(y['operating_income'] or 0)/MM:>11,.0f}"
              f"{(y['roic'] or 0):>9.1%}")
    for when, p in t["ppe"].items():
        print(f"  {when}: PP&E 총액 {p['gross']/MM:>8,.0f} · 건설중 "
              f"{p['construction_in_progress']/MM:>8,.0f} "
              f"({p['construction_in_progress']/p['gross']:>4.0%}) · "
              f"AI·SI 인프라 {(p['ai_infrastructure'] or 0)/MM:>8,.0f}")

    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
