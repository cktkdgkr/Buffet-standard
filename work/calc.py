"""
Buffett framework quantitative engine.

Implements the metrics defined in the analysis brief (principles 1-6) as pure
functions over explicit inputs. No data is embedded here: every function takes
figures supplied by the caller and returns a computed result plus the inputs it
used, so results stay reproducible and auditable.

Design rule carried through the whole module: a missing input yields None
(propagated as DATA_UNAVAILABLE downstream), never a silently substituted
default. A figure that cannot be sourced must not become a number here.

Run `python3 calc.py` to execute the self-tests.
"""

from dataclasses import dataclass, field
from typing import Optional, Sequence

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _missing(*vals) -> bool:
    """True if any required input is absent."""
    return any(v is None for v in vals)


def _safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if _missing(num, den) or den == 0:
        return None
    return num / den


def cagr(begin: Optional[float], end: Optional[float], years: float) -> Optional[float]:
    """Compound annual growth rate. Undefined for non-positive endpoints."""
    if _missing(begin, end) or years <= 0 or begin <= 0 or end <= 0:
        return None
    return (end / begin) ** (1.0 / years) - 1.0


# ---------------------------------------------------------------------------
# Principle 1 - ROIC (existing and incremental) vs WACC
# ---------------------------------------------------------------------------

def nopat(operating_income: Optional[float], tax_rate: Optional[float]) -> Optional[float]:
    """Net operating profit after tax."""
    if _missing(operating_income, tax_rate):
        return None
    return operating_income * (1.0 - tax_rate)


def invested_capital(
    total_equity: Optional[float],
    interest_bearing_debt: Optional[float],
    cash_and_equivalents: Optional[float],
) -> Optional[float]:
    """
    Invested capital = equity + interest-bearing debt - excess cash.

    Cash is deducted because idle cash is not capital put to work in the
    operating business; leaving it in understates ROIC for the cash-rich
    balance sheets common among mega-caps.
    """
    if _missing(total_equity, interest_bearing_debt, cash_and_equivalents):
        return None
    return total_equity + interest_bearing_debt - cash_and_equivalents


def roic(
    operating_income: Optional[float],
    tax_rate: Optional[float],
    invested_capital_value: Optional[float],
) -> Optional[float]:
    return _safe_div(nopat(operating_income, tax_rate), invested_capital_value)


def incremental_roic(
    nopat_begin: Optional[float],
    nopat_end: Optional[float],
    ic_begin: Optional[float],
    ic_end: Optional[float],
) -> Optional[float]:
    """
    Incremental ROIC = change in NOPAT / change in invested capital.

    This is the brief's '신규 ROIC': the return management earned on capital it
    actually deployed over the window, which is the read on current management
    rather than on a franchise inherited from the past. Undefined when invested
    capital shrank (the ratio has no economic meaning there).
    """
    if _missing(nopat_begin, nopat_end, ic_begin, ic_end):
        return None
    d_ic = ic_end - ic_begin
    if d_ic <= 0:
        return None
    return (nopat_end - nopat_begin) / d_ic


def wacc(
    equity_value: Optional[float],
    debt_value: Optional[float],
    cost_of_equity: Optional[float],
    cost_of_debt: Optional[float],
    tax_rate: Optional[float],
) -> Optional[float]:
    if _missing(equity_value, debt_value, cost_of_equity, cost_of_debt, tax_rate):
        return None
    total = equity_value + debt_value
    if total <= 0:
        return None
    we, wd = equity_value / total, debt_value / total
    return we * cost_of_equity + wd * cost_of_debt * (1.0 - tax_rate)


def cost_of_equity_capm(
    risk_free: Optional[float], beta: Optional[float], erp: Optional[float]
) -> Optional[float]:
    if _missing(risk_free, beta, erp):
        return None
    return risk_free + beta * erp


def roic_wacc_spread(roic_value: Optional[float], wacc_value: Optional[float]) -> Optional[float]:
    """The brief's final decision line. Negative spread => growth destroys value."""
    if _missing(roic_value, wacc_value):
        return None
    return roic_value - wacc_value


# ---------------------------------------------------------------------------
# Principle 2 - the ROE trap (leverage check)
# ---------------------------------------------------------------------------

def roe(net_income: Optional[float], total_equity: Optional[float]) -> Optional[float]:
    return _safe_div(net_income, total_equity)


def roe_roic_spread(roe_value: Optional[float], roic_value: Optional[float]) -> Optional[float]:
    """
    ROE minus ROIC. A wide positive gap means reported ROE is being manufactured
    by leverage rather than by operating returns; narrow is higher quality.
    """
    if _missing(roe_value, roic_value):
        return None
    return roe_value - roic_value


def net_debt_to_ebitda(
    interest_bearing_debt: Optional[float],
    cash_and_equivalents: Optional[float],
    ebitda: Optional[float],
) -> Optional[float]:
    if _missing(interest_bearing_debt, cash_and_equivalents, ebitda):
        return None
    return _safe_div(interest_bearing_debt - cash_and_equivalents, ebitda)


def interest_coverage(
    operating_income: Optional[float], interest_expense: Optional[float]
) -> Optional[float]:
    return _safe_div(operating_income, interest_expense)


# ---------------------------------------------------------------------------
# Principle 3 - Owner Earnings
# ---------------------------------------------------------------------------

def owner_earnings(
    net_income: Optional[float],
    depreciation_amortization: Optional[float],
    capex: Optional[float],
    change_in_working_capital: Optional[float],
) -> Optional[float]:
    """
    Owner earnings = net income + D&A - CapEx - incremental working capital.

    `capex` and `change_in_working_capital` are passed as positive magnitudes of
    cash consumed. All four inputs must cover the SAME fiscal period; mixing a
    fiscal-year net income with a trailing-twelve-month D&A from a different
    period end is the standard way this figure gets quietly corrupted.
    """
    if _missing(net_income, depreciation_amortization, capex, change_in_working_capital):
        return None
    return net_income + depreciation_amortization - capex - change_in_working_capital


def owner_earnings_margin(oe: Optional[float], revenue: Optional[float]) -> Optional[float]:
    return _safe_div(oe, revenue)


# ---------------------------------------------------------------------------
# Principle 5 (stage 1) - current multiples
# ---------------------------------------------------------------------------

def per(market_cap: Optional[float], net_income: Optional[float]) -> Optional[float]:
    if _missing(net_income) or (net_income is not None and net_income <= 0):
        return None  # PER is meaningless on losses
    return _safe_div(market_cap, net_income)


def pbr(market_cap: Optional[float], total_equity: Optional[float]) -> Optional[float]:
    return _safe_div(market_cap, total_equity)


def psr(market_cap: Optional[float], revenue: Optional[float]) -> Optional[float]:
    return _safe_div(market_cap, revenue)


# ---------------------------------------------------------------------------
# Principle 6 - intrinsic value and margin of safety
# ---------------------------------------------------------------------------

@dataclass
class DCFScenario:
    name: str                    # 'conservative' | 'base' | 'optimistic'
    growth_rate: float           # owner-earnings growth during the forecast window
    discount_rate: float         # brief: 10% base, 8%/12% for sensitivity
    terminal_growth: float
    years: int = 10


@dataclass
class DCFResult:
    scenario: str
    intrinsic_value: Optional[float]
    pv_forecast: Optional[float] = None
    pv_terminal: Optional[float] = None
    assumptions: dict = field(default_factory=dict)


def dcf_intrinsic_value(base_owner_earnings: Optional[float], s: DCFScenario) -> DCFResult:
    """
    Two-stage DCF on owner earnings (not EPS, not EBITDA - per principle 3).

    Returns a single scenario's present value. The brief requires that these are
    only ever presented as a three-scenario RANGE and used to answer 'is this
    inside an investable band', never as a point estimate of worth.
    """
    assumptions = {
        "growth_rate": s.growth_rate,
        "discount_rate": s.discount_rate,
        "terminal_growth": s.terminal_growth,
        "forecast_years": s.years,
        "basis": "owner earnings",
    }
    if base_owner_earnings is None:
        return DCFResult(s.name, None, assumptions=assumptions)
    if s.discount_rate <= s.terminal_growth:
        # Terminal value diverges; refuse rather than emit a nonsense number.
        return DCFResult(s.name, None, assumptions=assumptions)

    pv_forecast, cf = 0.0, base_owner_earnings
    for year in range(1, s.years + 1):
        cf = cf * (1.0 + s.growth_rate)
        pv_forecast += cf / ((1.0 + s.discount_rate) ** year)

    terminal = cf * (1.0 + s.terminal_growth) / (s.discount_rate - s.terminal_growth)
    pv_terminal = terminal / ((1.0 + s.discount_rate) ** s.years)

    return DCFResult(s.name, pv_forecast + pv_terminal, pv_forecast, pv_terminal, assumptions)


def margin_of_safety(
    intrinsic_value: Optional[float], market_cap: Optional[float]
) -> Optional[float]:
    """(intrinsic value - market cap) / intrinsic value. Positive => discount."""
    if _missing(intrinsic_value, market_cap) or intrinsic_value == 0:
        return None
    return (intrinsic_value - market_cap) / intrinsic_value


def verdict_from_margin(mos: Optional[float]) -> str:
    """
    The brief's three-way call. Deliberately not a price target.
    """
    if mos is None:
        return "DATA_UNAVAILABLE"
    if mos >= 0.30:
        return "INVESTABLE_RANGE"
    if mos >= 0.0:
        return "BORDERLINE"
    return "OUTSIDE_RANGE"


def share_count_cagr(
    shares_begin: Optional[float], shares_end: Optional[float], years: float
) -> Optional[float]:
    """
    Negative result = net buyback = rising per-share intrinsic value, which the
    brief flags as the thing that actually matters in capital allocation.
    """
    return cagr(shares_begin, shares_end, years)


# ---------------------------------------------------------------------------
# Self-tests
# ---------------------------------------------------------------------------

def _tests() -> None:
    ok = 0

    def check(label, got, want, tol=1e-6):
        nonlocal ok
        if want is None:
            assert got is None, f"{label}: expected None, got {got}"
        else:
            assert got is not None and abs(got - want) < tol, f"{label}: {got} != {want}"
        ok += 1

    # Principle 1
    check("nopat", nopat(1000.0, 0.21), 790.0)
    check("invested_capital", invested_capital(5000.0, 2000.0, 1000.0), 6000.0)
    check("roic", roic(1000.0, 0.21, 6000.0), 790.0 / 6000.0)
    check("incremental_roic", incremental_roic(500.0, 800.0, 4000.0, 5000.0), 0.30)
    check("incremental_roic shrinking IC -> None",
          incremental_roic(500.0, 800.0, 5000.0, 4000.0), None)
    check("cost_of_equity_capm", cost_of_equity_capm(0.04, 1.2, 0.05), 0.10)
    # 60/40 equity/debt, Ke 10%, Kd 5%, tax 21%
    check("wacc", wacc(6000.0, 4000.0, 0.10, 0.05, 0.21), 0.6 * 0.10 + 0.4 * 0.05 * 0.79)
    check("spread", roic_wacc_spread(0.15, 0.09), 0.06)

    # Principle 2
    check("roe", roe(800.0, 4000.0), 0.20)
    check("roe_roic_spread", roe_roic_spread(0.20, 0.13), 0.07)
    check("net_debt_to_ebitda", net_debt_to_ebitda(3000.0, 1000.0, 1000.0), 2.0)
    check("interest_coverage", interest_coverage(1000.0, 50.0), 20.0)

    # Principle 3
    check("owner_earnings", owner_earnings(1000.0, 300.0, 250.0, 50.0), 1000.0)
    check("oe_margin", owner_earnings_margin(1000.0, 8000.0), 0.125)
    check("owner_earnings missing input propagates",
          owner_earnings(1000.0, None, 250.0, 50.0), None)

    # Principle 5 stage 1
    check("per", per(20000.0, 1000.0), 20.0)
    check("per on loss -> None", per(20000.0, -50.0), None)
    check("pbr", pbr(20000.0, 5000.0), 4.0)
    check("psr", psr(20000.0, 10000.0), 2.0)

    # Principle 6 - hand-checkable DCF: zero growth, 10% discount, 0% terminal.
    # Each year's CF = 100; PV of 10 years + terminal (100/0.10 discounted).
    flat = DCFScenario("base", 0.0, 0.10, 0.0, 10)
    r = dcf_intrinsic_value(100.0, flat)
    expect_forecast = sum(100.0 / (1.10 ** y) for y in range(1, 11))
    expect_terminal = (100.0 / 0.10) / (1.10 ** 10)
    check("dcf forecast leg", r.pv_forecast, expect_forecast)
    check("dcf terminal leg", r.pv_terminal, expect_terminal)
    check("dcf total", r.intrinsic_value, expect_forecast + expect_terminal)

    # Divergent terminal must refuse, not emit a negative/absurd value
    check("dcf refuses g >= r",
          dcf_intrinsic_value(100.0, DCFScenario("bad", 0.05, 0.04, 0.06)).intrinsic_value, None)
    check("dcf propagates missing OE",
          dcf_intrinsic_value(None, flat).intrinsic_value, None)

    check("margin_of_safety", margin_of_safety(1000.0, 700.0), 0.30)
    assert verdict_from_margin(0.35) == "INVESTABLE_RANGE"
    assert verdict_from_margin(0.10) == "BORDERLINE"
    assert verdict_from_margin(-0.20) == "OUTSIDE_RANGE"
    assert verdict_from_margin(None) == "DATA_UNAVAILABLE"
    ok += 4

    # Buybacks reduce share count -> negative CAGR
    sc = share_count_cagr(1000.0, 900.0, 5.0)
    assert sc is not None and sc < 0, "buyback should give negative share-count CAGR"
    ok += 1

    check("cagr", cagr(100.0, 200.0, 10.0), 2 ** 0.1 - 1)

    print(f"calc.py self-tests passed: {ok} assertions")


if __name__ == "__main__":
    _tests()
