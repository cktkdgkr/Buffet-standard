"""
Samsung Biologics (207940.KS) - audited financial data from the company's own
statements.

Two things make this company harder to put in a ten-year series than the fifty
US names, and both are structural rather than cosmetic:

  1. Samsung Bioepis. It was an equity-accounted joint venture through 2021,
     became a wholly-owned subsidiary in April 2022, and was spun off into
     Samsung Epis Holdings with an effective date of 1 November 2025. The
     reported consolidated numbers therefore describe three different companies
     over ten years.

  2. The spin-off reduced the share count from 71,174,000 to 46,290,951, so
     per-share history is not comparable either.

The fix for (1) is the company's own separate (별도) statements. They carry the
CDMO business alone in every year, with sales to Bioepis shown as revenue
rather than eliminated - which is exactly the basis the post-spin-off group
reports on. The identity checks in verify_sbl.py confirm the join: separate
FY2024 revenue equals the restated continuing-operations FY2024 revenue to the
won, and separate FY2021 revenue equals consolidated FY2021 revenue to the won.

Sources, all from https://samsungbiologics.com IR (audited, with the auditor's
report attached to each PDF):

  FY2016-FY2019   audited financial statements (the company had no consolidated
                  subsidiaries; these are already separate-basis)
  FY2020-FY2021   audited consolidated statements (one immaterial subsidiary)
  FY2022-FY2025   audited separate statements, plus the consolidated set for
                  the discontinued-operations and segment notes
  2026 1H         reviewed consolidated statements

Everything is kept in Korean won. Writes work/kr/sbl_raw.json.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
TXT = os.path.join(HERE, "kr", "txt")
OUT = os.path.join(HERE, "kr", "sbl_raw.json")

# A figure in these statements always carries at least one thousands group, so
# requiring one keeps note references ("5,9,31,33") out of the match. The same
# rule caught the 41-quadrillion parse in the Samsung Electronics collector.
# Parentheses must balance, or a share count printed as "46,290,951)" at the end
# of a wrapped caption is read as a negative.
FIGURE = re.compile(r"\(\d{1,3}(?:,\d{3})+\)|\d{1,3}(?:,\d{3})+")


def numbers(line):
    """Every won figure on a line, parentheses read as negative."""
    out = []
    for m in FIGURE.finditer(line):
        s = m.group(0)
        neg = s.startswith("(")
        out.append(-int(s.strip("()").replace(",", "")) if neg
                   else int(s.replace(",", "")))
    return out


def load(name):
    with open(os.path.join(TXT, f"{name}.txt")) as fh:
        return fh.read()


def section(text, start_pat, end_pat, occurrence=1):
    """The slice between the n-th match of start_pat and the next end_pat."""
    starts = [m.end() for m in re.finditer(start_pat, text)]
    if len(starts) <= occurrence:
        raise KeyError(f"section start {start_pat!r} #{occurrence} not found")
    s = starts[occurrence]
    m = re.search(end_pat, text[s:])
    return text[s: s + (m.start() if m else 200_000)]


def pick(sec, label_pat, index=0, lookahead=6, required=True):
    """
    First figure on the line carrying label_pat.

    Labels sometimes wrap across lines with the figures left on a later line
    (the PDF text layer breaks long captions), so look ahead a few lines for
    the first line that actually carries numbers.
    """
    lines = sec.split("\n")
    for i, line in enumerate(lines):
        if not re.search(label_pat, line, re.I):
            continue
        for j in range(i, min(i + lookahead + 1, len(lines))):
            ns = numbers(lines[j])
            if ns:
                if len(ns) <= index:
                    break
                return ns[index]
    if required:
        raise KeyError(f"label {label_pat!r} not found in section")
    return None


def opt(sec, label_pat, index=0, lookahead=6):
    try:
        return pick(sec, label_pat, index, lookahead, required=False)
    except KeyError:
        return None


# --------------------------------------------------------------------------
# Per-year extraction.
#
# Each entry says which text file to read, which multiple of a won the figures
# are printed in, and where the three statements start. The older filings print
# thousands of won and use slightly different captions, so the layout is data
# rather than code.
# --------------------------------------------------------------------------

BS_END = r"Statements? of (?:Comprehensive|Profit)"
IS_END = r"Statements? of Changes in Equity"
CF_END = r"Notes to the (?:Separate |Consolidated )?(?:Financial|Separate)"

YEARS = {
    2016: dict(doc="sbl_2017", unit=1_000, col=1,
               bs=(r"Statements of Financial Position", 1),
               is_=(r"Statements of Comprehensive Loss", 1)),
    2017: dict(doc="sbl_2017", unit=1_000, col=0,
               bs=(r"Statements of Financial Position", 1),
               is_=(r"Statements of Comprehensive Loss", 1)),
    2018: dict(doc="sbl_2018", unit=1_000, col=0,
               bs=(r"Statements of Financial Position", 1),
               is_=(r"Statements of Comprehensive Income", 1)),
    2019: dict(doc="sbl_2019", unit=1, col=0,
               bs=(r"Statements of Financial Position", 1),
               is_=(r"Statements of Comprehensive Income", 1)),
    2020: dict(doc="sbl_2020", unit=1, col=0,
               bs=(r"Statements of Financial Position", 1),
               is_=(r"Statements of Comprehensive Income", 1)),
    2021: dict(doc="sbl_2021", unit=1, col=0,
               bs=(r"Statements of Financial Position", 1),
               is_=(r"Statements of Comprehensive Income", 1)),
    2022: dict(doc="sblsep_2022", unit=1, col=0,
               bs=(r"Statements of Financial Position", 1),
               is_=(r"Statements of Comprehensive Income", 1)),
    2023: dict(doc="sblsep_2023", unit=1, col=0,
               bs=(r"Statements of Financial Position", 1),
               is_=(r"Statements of Comprehensive Income", 1)),
    2024: dict(doc="sblsep_2024", unit=1, col=0,
               bs=(r"Statements of Financial Position", 1),
               is_=(r"Statements of Comprehensive Income", 1)),
    2025: dict(doc="sblsep_2025", unit=1, col=0,
               bs=(r"Statements of Financial Position", 1),
               is_=(r"Statements of Comprehensive Income", 0)),
}


def income_statement(sec, col, unit):
    g = lambda pat, req=True, i=None: (
        pick(sec, pat, col if i is None else i, required=req))
    o = lambda pat: opt(sec, pat, col)
    out = {
        "revenue": g(r"^\s*Revenue\b"),
        "cost_of_revenue": g(r"Cost of (?:revenue|sales)"),
        "gross_profit": g(r"Gross profit"),
        "sga": g(r"Selling, general and administrative"),
        "operating_income": g(r"Operating (?:profit|income|loss)"),
        "other_income": o(r"^\s*Other income"),
        "other_expenses": o(r"^\s*Other expenses"),
        "finance_income": o(r"^\s*Finance income"),
        "finance_costs": o(r"^\s*Finance costs"),
        "equity_method_income": o(r"(?:Share of profit|Equity loss) .*associates"),
        "pretax_income": g(r"(?:Profit|Loss)\s*(?:\(loss\))?\s*before income tax"),
        "income_tax_expense": g(r"Income tax (?:expense|benefit)"),
        "net_income": g(r"(?:Net (?:profit|loss)|Profit|Loss)\s*(?:\(loss\))?\s*for the (?:year|period)"),
    }
    return {k: (None if v is None else v * unit) for k, v in out.items()}


def balance_sheet(sec, col, unit):
    o = lambda pat, la=6: opt(sec, pat, col, la)
    out = {
        "cash_and_equivalents": o(r"Cash and cash equivalents"),
        "short_term_financial_instruments": o(r"Short-term financial instruments"),
        "inventories": o(r"^\s*Inventories"),
        # Receivables, payables and contract assets are needed for the
        # bottom-up operating-capital measure. Both receivables and payables
        # appear under current and non-current headings; the current figure
        # comes first and carries essentially all of the balance.
        "trade_receivables": o(r"Trade and other receivables"),
        "trade_payables": o(r"Trade and other payables"),
        "contract_assets": o(r"^\s*Contract assets"),
        "other_current_liabilities": o(r"Other current liabilities"),
        "current_assets": o(r"(?:^\s*Current assets|^\s*Total current assets)"),
        "ppe": o(r"Property, plant and equipment"),
        "intangibles": o(r"^\s*Intangible assets"),
        "right_of_use": o(r"Right-of-use asset"),
        "investments_in_subs": o(r"Investments in (?:subsidiar(?:y|ies)|associates?)"),
        "total_assets": o(r"Total assets"),
        "contract_liabilities_current": None,
        "total_liabilities": o(r"Total liabilities(?!\s+and equity)"),
        "total_equity": o(r"Total equity"),
    }
    del out["contract_liabilities_current"]
    return {k: (None if v is None else v * unit) for k, v in out.items()}


def debt_and_contract_liabilities(sec, col, unit):
    """
    Interest-bearing debt and contract liabilities both appear twice - once
    under current liabilities, once under non-current - so take them in order
    of appearance rather than by label alone.
    """
    lines = sec.split("\n")

    def all_hits(pat):
        hits = []
        for i, line in enumerate(lines):
            if re.search(pat, line, re.I):
                for j in range(i, min(i + 4, len(lines))):
                    ns = numbers(lines[j])
                    if ns:
                        if len(ns) > col:
                            hits.append(ns[col])
                        break
        return hits

    debt = all_hits(r"(?:Debentures|Bonds)(?: and borrowings)?|^\s*Borrowings")
    lease = all_hits(r"Lease liabilities")
    contract = all_hits(r"Contract liabilities")
    c_assets = all_hits(r"^\s*Contract assets")
    return {
        "debt_total": (sum(debt) * unit) if debt else None,
        "debt_parts": [d * unit for d in debt],
        "lease_liabilities": (sum(lease) * unit) if lease else None,
        "contract_liabilities": (sum(contract) * unit) if contract else None,
        "contract_assets_total": (sum(c_assets) * unit) if c_assets else None,
    }


def cash_flow(text, col, unit):
    sec = section(text, r"Statements of Cash Flows", CF_END, occurrence=1)
    o = lambda pat, la=6: opt(sec, pat, col, la)
    # Outflows are printed in parentheses in some years and bare in others, so
    # capex is taken as a magnitude and the direction is supplied here.
    capex = o(r"(?:Acquisition|Purchase|Payments? for|Additions?) "
              r"(?:of |for )?property, plant and equipment")
    intan = o(r"(?:Acquisition|Purchase) of intangible assets")
    out = {
        "ocf": o(r"Net cash (?:inflow|provided|from|flows?)[^\n]*operating"),
        "capex": None if capex is None else abs(capex),
        "intangible_capex": None if intan is None else abs(intan),
        "interest_paid": o(r"Interest paid"),
        "tax_paid": o(r"Income tax(?:es)? paid"),
        "dividends_paid": o(r"Dividends? paid"),
    }
    return {k: (None if v is None else v * unit) for k, v in out.items()}


def dna(text, col, unit):
    """
    Depreciation, amortisation of intangibles and depreciation of right-of-use
    assets, from the indirect-method reconciliation of operating cash flow.

    The reconciliation sits on the face of the cash flow statement through
    FY2024 and moves into a note (Note 32) in the FY2025 statements, so the
    block is located by its own contents - a line for intangible amortisation
    with a line for straight depreciation within a few lines of it - rather
    than by page position.
    """
    lines = text.split("\n")
    amort_at = [i for i, l in enumerate(lines)
                if re.match(r"\s*Amortization of intangible assets\s", l)
                and numbers(l)]
    for i in amort_at:
        window = lines[max(0, i - 8): i + 8]
        # The same two captions also appear in the selling-and-administrative
        # expenses note, where they cover only the SG&A share - FY2024's SG&A
        # depreciation is 18.5bn against 276.1bn for the company. "Adjustments
        # for:" heads the reconciliation and nothing else.
        if not any(re.search(r"Adjustments for", l) for l in window):
            continue
        dep = rou = None
        for l in window:
            if dep is None and re.match(r"\s*Depreciation\s+[\d,\\W]", l) \
                    and numbers(l):
                dep = numbers(l)
            if rou is None and re.search(r"Depreciation of right-of-use", l) \
                    and numbers(l):
                rou = numbers(l)
        am = numbers(lines[i])
        if dep is None or len(dep) <= col or len(am) <= col:
            continue
        total = dep[col] + am[col] + (rou[col] if rou and len(rou) > col else 0)
        return {
            "depreciation": dep[col] * unit,
            "amortization": am[col] * unit,
            "rou_depreciation": (rou[col] * unit) if rou and len(rou) > col
                                else None,
            "depreciation_amortization": total * unit,
        }
    return {"depreciation": None, "amortization": None,
            "rou_depreciation": None, "depreciation_amortization": None}


def collect_year(fy, cfg):
    text = load(cfg["doc"])
    unit, col = cfg["unit"], cfg["col"]
    bs_pat, bs_occ = cfg["bs"]
    is_pat, is_occ = cfg["is_"]
    bs = section(text, bs_pat, BS_END, occurrence=bs_occ)
    is_ = section(text, is_pat, IS_END, occurrence=is_occ)

    row = {"fiscal_year": fy, "source_document": cfg["doc"] + ".pdf"}
    row.update(income_statement(is_, col, unit))
    row.update(balance_sheet(bs, col, unit))
    row.update(debt_and_contract_liabilities(bs, col, unit))
    row.update(cash_flow(text, col, unit))
    row.update(dna(text, col, unit))
    normalise_tax_sign(row)
    return row


def normalise_tax_sign(row):
    """
    The statements alternate between printing the tax line as an expense
    (positive, or in parentheses when the whole column is shown as a charge) and
    as "income tax benefit (expense)" with the sign reversed. Pin it to the one
    convention the arithmetic has to satisfy: pretax - tax = net income.
    """
    p, t, n = (row.get("pretax_income"), row.get("income_tax_expense"),
               row.get("net_income"))
    if None in (p, t, n):
        return
    if abs((p - t) - n) <= abs((p + t) - n):
        return                      # already an expense-positive figure
    row["income_tax_expense"] = -t
    row["tax_sign_flipped"] = True


# --------------------------------------------------------------------------
# Context the valuation needs but the three statements do not carry: the
# reported consolidated series (so the basis change is visible rather than
# hidden), the CDMO segment split for the two years Bioepis was consolidated,
# the discontinued-operations note that pins the FY2024 restatement, the 2026
# half-year, the share count either side of the spin-off, and the customer and
# geographic concentration.
# --------------------------------------------------------------------------

def despace(text):
    """
    The 2026 interim's text layer breaks figures with a stray space
    ("621, 049,157,764"). Close the gap around commas only - the same fix the
    Samsung Electronics collector needed, and for the same reason: widening it
    to all whitespace merges two adjacent figures into one.
    """
    return re.sub(r",\s+(?=\d)", ",", text)


def consolidated_series():
    """Reported consolidated revenue, operating profit and net income."""
    out = {}
    plan = [("sbl_2020", 2020, 2019), ("sbl_2021", 2021, 2020),
            ("sbl_2022", 2022, 2021), ("sbl_2023", 2023, 2022),
            ("sbl_2024", 2024, 2023), ("sbl_2025", 2025, 2024)]
    for doc, cur, prev in plan:
        text = load(doc)
        occ = 0 if doc == "sbl_2025" else 1
        sec = section(text, r"Statements of Comprehensive Income", IS_END, occ)
        for col, fy in ((0, cur), (1, prev)):
            row = {
                "revenue": opt(sec, r"^\s*Revenue\b", col),
                "operating_income": opt(sec, r"Operating (?:profit|income)", col),
                "net_income": opt(sec, r"Profit for the year", col),
                "source_document": doc + ".pdf",
            }
            # The FY2025 statements restate FY2024 to continuing operations, so
            # the later filing is not always the right answer for an earlier
            # year. Keep the first (as-originally-reported) reading.
            out.setdefault(fy, row)
    return out


def segment_note():
    """CDMO vs biosimilar split, FY2023 and FY2024 (from the FY2024 filing)."""
    text = load("sbl_2024")
    i = text.index("4. Operating Segments")
    sec = text[i: i + 6000]
    lines = sec.split("\n")

    def row(pat):
        for l in lines:
            if re.search(pat, l):
                n = numbers(l)
                if len(n) >= 6:
                    return {"2024_cdmo": n[0], "2024_bio": n[1],
                            "2024_total": n[2], "2023_cdmo": n[3],
                            "2023_bio": n[4], "2023_total": n[5]}
        return None

    return {
        "total_sales": row(r"^Total sales"),
        "net_sales": row(r"^Net sales"),
        "operating_profit": row(r"^Operating profit"),
    }


def discontinued_note():
    """Note 34 of the FY2025 consolidated statements: the spun-off business."""
    text = load("sbl_2025")
    i = text.index("(c) Overview of Discontinued Operations")
    sec = text[i: i + 1500]
    g = lambda pat: [n for n in (opt(sec, pat, 0), opt(sec, pat, 1))]
    return {
        "revenue": g(r"^\s*Revenue"),
        "operating_income": g(r"^\s*Operating profit"),
        "profit": g(r"Profit from discontinued operations"),
        "years": [2025, 2024],
        "note": "FY2025 covers ten months to the 1 November 2025 spin-off date",
        "source_document": "sbl_2025.pdf",
    }


def interim_2026():
    """
    2026 half-year, reviewed consolidated. Four columns: Q2 2026, 1H 2026,
    Q2 2025, 1H 2025.
    """
    text = despace(load("sbl_2026q2"))
    sec = section(text, r"Statements of Comprehensive Income", IS_END, 1)
    cols = ("q2_2026", "h1_2026", "q2_2025", "h1_2025")
    out = {}
    for label, pat in (("revenue", r"^Revenue\b"),
                       ("operating_income", r"^Operating profit"),
                       ("pretax_income", r"^Profit before income tax"),
                       ("income_tax_expense", r"^Income tax expense"),
                       ("profit_continuing", r"Profit from continuing operations")):
        for i, c in enumerate(cols):
            out.setdefault(c, {})[label] = opt(sec, pat, i)
    out["source_document"] = "sbl_2026q2.pdf"
    return out


def share_counts():
    text = load("sblsep_2025")
    i = text.index("Number of  \nIssued")
    sec = text[i: i + 900]
    ending = None
    for l in sec.split("\n"):
        if l.strip().startswith("Ending Balance"):
            ending = numbers(l)
    wa = opt(text[text.index("Weighted-average number of ordinary shares"):]
             [:400], r"Weighted-average number of ordinary shares", 0)
    return {
        "issued_2025": ending[0] if ending else None,
        "outstanding_2025": ending[1] if ending else None,
        "issued_2024": ending[2] if ending else None,
        "weighted_average_2025": wa,
        "source_document": "sblsep_2025.pdf",
    }


def concentration():
    text = load("sblsep_2025")
    i = text.index("Details of customers")
    sec = text[i: i + 1800]
    cust = {}
    for tag in "ABCDE":
        v = opt(sec, rf"^Client {tag}\b", 0), opt(sec, rf"^Client {tag}\b", 1)
        cust[f"client_{tag.lower()}"] = {"2025": v[0], "2024": v[1]}
    geo = {}
    for name, pat in (("domestic", r"^Domestic"), ("europe", r"^Europe"),
                      ("usa", r"^USA"), ("other", r"^Other\b")):
        geo[name] = {"2025": opt(sec, pat, 0), "2024": opt(sec, pat, 1)}
    return {"customers": cust, "geography": geo,
            "source_document": "sblsep_2025.pdf"}


def construction_in_progress():
    """
    Construction-in-progress out of the property note, which is the company's
    own statement of how much capital is on the balance sheet but not yet
    earning anything.

    It matters here more than in most companies. At the end of FY2024 W1,823bn
    of the W5,991bn operating capital - 30% of it - was an unfinished plant, and
    W2,183bn was transferred into service during FY2025. A return on capital
    computed without taking that out reads FY2024 as a year of deteriorating
    returns when nothing had deteriorated.

    The property note is printed in thousands of won through FY2023 and in won
    from FY2024, so the unit travels with the document.
    """
    # doc, unit, and how many years that document's cost table shows first.
    plan = [("sbl_2018", 1_000, [2018, 2017]),
            ("sbl_2017", 1_000, [2017, 2016]),
            ("sbl_2020", 1_000, [2020, 2019]),
            ("sblsep_2022", 1_000, [2022, 2021]),
            ("sblsep_2023", 1_000, [2023, 2022]),
            ("sblsep_2025", 1, [2025, 2024])]
    out = {}
    for doc, unit, fys in plan:
        text = load(doc)
        m = re.search(r"\d+\. Property, Plant and Equipment", text)
        # Stop at the next numbered note. The note that follows also has a
        # construction-in-progress row, at a different scope.
        rest = text[m.end():]
        nxt = re.search(r"\n\s*\d+\.\s+[A-Z]", rest)
        lines = rest[: nxt.start() if nxt else 8000].split("\n")
        rows = []

        # The note holds two kinds of table and both carry a
        # Construction-in-progress row with four figures on it, so they cannot
        # be told apart by shape. The cost table is headed by "Accumulated
        # depreciation"; the movement table by "Beginning balance". Only the
        # cost table gives a carrying amount per year.
        for i, line in enumerate(lines):
            if not re.search(r"Construction-in", line):
                continue
            header = " ".join(lines[max(0, i - 25): i])
            if "Beginning balance" in header or "Accumulated" not in header:
                continue
            for j in range(i, min(i + 4, len(lines))):
                if numbers(lines[j]):
                    rows.append(numbers(lines[j]))
                    break

        # Some notes put both years in one table, others print one table per
        # year in reverse-chronological order. Accumulated depreciation on this
        # row is always nil and prints as a dash, so a two-year table arrives
        # as cost, carrying amount, cost, carrying amount.
        if len(rows) >= len(fys):
            chosen = [(fy, rows[k], len(rows[k]) - 1)
                      for k, fy in enumerate(fys)]
        elif len(rows) == 1 and len(rows[0]) >= 2 * len(fys):
            per = len(rows[0]) // len(fys)
            chosen = [(fy, rows[0], k * per + per - 1)
                      for k, fy in enumerate(fys)]
        else:
            continue
        for fy, row, idx in chosen:
            out.setdefault(fy, {"carrying_amount": row[idx] * unit,
                                "figures_on_row": row,
                                "source_document": doc + ".pdf"})
    return out


def equity_transactions():
    """
    What shareholders put in and took out. The answer matters for the capital
    allocation criterion and it is not on the face of any statement: the FY2022
    statement of changes in equity carries a W3,188bn capital increase, and no
    year carries a dividend.
    """
    text = load("sblsep_2022")
    sec = section(text, r"Statements of Changes in Equity", r"above separate", 1)
    line = [l for l in sec.split("\n") if "Capital increase" in l]
    row = numbers(line[0]) if line else []
    dividends = {}
    for fy, doc in ((2019, "sbl_2019"), (2021, "sbl_2021"),
                    (2023, "sblsep_2023"), (2025, "sblsep_2025")):
        t = load(doc)
        dividends[fy] = bool(re.search(r"Dividends? (?:paid|of)\s*[\\W]?\s*\d",
                                       t, re.I))
    return {
        "capital_increase_2022": {"share_capital": row[0] if row else None,
                                  "share_premium": row[1] if len(row) > 1 else None,
                                  "total": row[2] if len(row) > 2 else None,
                                  "source_document": "sblsep_2022.pdf"},
        "dividend_line_found": dividends,
        "treasury_2025": {"amount": 92_012_513_657, "shares": 51_433,
                          "note": "분할에 따른 단수주 취득 (자기주식 매입 프로그램이 아님)",
                          "source_document": "sblsep_2025.pdf"},
    }


def float_and_supplier_finance():
    """
    Two items the face of the balance sheet does not name, both material.

    Advance receipts and contract liabilities are customer money held before
    the work is done - float, in the sense the insurance letters use. Supplier
    finance arrangements are the opposite: the FY2024 payables balance carried
    W540.6bn of them, almost all owed to a related party, and the FY2025
    unwinding of that balance is why FY2025 operating cash flow looks worse
    relative to profit than it is.
    """
    text = load("sblsep_2025")
    note20 = text[text.index("20. Other Liabilities"):][:900]
    note17 = text[text.index("17. Trade and Other Payables"):][:1400]
    adv = numbers([l for l in note20.split("\n") if "Advance receipts" in l][0])
    # The supplier-finance caption wraps over three lines with the figures on a
    # fourth, so let pick() walk forward to them.
    sup = [pick(note17, r"Liabilities under", i) for i in (0, 1)]
    rel = re.search(r"related parties as of December 31, 2025 and December 31, "
                    r"2024 are \\?\s*([\d,]+)[^\d]+([\d,]+)", text.replace("\n", " "))
    return {
        "advance_receipts": {"2025_current": adv[0], "2025_non_current": adv[1],
                             "2024_current": adv[2], "2024_non_current": adv[3]},
        "supplier_finance": {"2025": sup[0], "2024": sup[1]},
        "related_party_payables_million": (
            [int(rel.group(1).replace(",", "")), int(rel.group(2).replace(",", ""))]
            if rel else None),
        "source_document": "sblsep_2025.pdf",
    }


def main():
    years = []
    for fy in sorted(YEARS):
        try:
            years.append(collect_year(fy, YEARS[fy]))
            print(f"  FY{fy}  ok")
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"  FY{fy}  FAILED: {exc}")
            years.append({"fiscal_year": fy, "error": str(exc)})

    payload = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "company_name": "Samsung Biologics Co., Ltd.",
        "ticker": "207940.KS",
        "currency": "KRW",
        "basis": "separate (CDMO) statements; see module docstring",
        "years": years,
    }
    for name, fn in (("consolidated_reported", consolidated_series),
                     ("segment_note_fy2024", segment_note),
                     ("discontinued_operations", discontinued_note),
                     ("interim_2026", interim_2026),
                     ("shares", share_counts),
                     ("concentration", concentration),
                     ("float_and_supplier_finance", float_and_supplier_finance),
                     ("construction_in_progress", construction_in_progress),
                     ("equity_transactions", equity_transactions)):
        try:
            payload[name] = fn()
            print(f"  {name}  ok")
        except Exception as exc:  # noqa: BLE001
            print(f"  {name}  FAILED: {exc}")
            payload[name] = {"error": str(exc)}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
