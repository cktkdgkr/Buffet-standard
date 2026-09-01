"""
Korea 2 - audited financial data for Samsung Electronics and SK hynix.

The first report left these two blank on purpose: every US figure traces to a
filing accession, and filling two rows from memory would have broken that. Two
primary sources close the gap without lowering the standard.

  Samsung Electronics - the audited consolidated financial statements the
  company publishes on its own IR site, one PDF per fiscal year, each carrying
  the auditor's report. Not an SEC filing, but the company's own audited
  statements, which is the same document DART receives.

  SK hynix - an SEC filing after all. The company listed ADSs on Nasdaq in
  July 2026 (ticker SKHY, CIK 2120882) and its Form F-1 prospectus, filed as
  424B4 on 2026-07-10, carries audited consolidated statements for FY2023,
  FY2024 and FY2025 plus reviewed Q1 2026 interims.

Both report in millions of Korean won under IFRS. Amounts are kept in won here
and converted once, at a dated rate, where the report needs dollars.

Writes work/kr/{ticker}.json.

Usage:
    python3 collect_korea.py                 # use cached documents
    python3 collect_korea.py --refresh       # re-download first
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
KR_DIR = os.path.join(HERE, "kr")
DOC_DIR = os.path.join(KR_DIR, "docs")

sys.path.insert(0, HERE)
import pdfstub  # noqa: F401,E402  - must precede pypdf
import pypdf  # noqa: E402
import htab  # noqa: E402

UA_SAMSUNG = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
UA_SEC = "Buffett52Analysis research cktkdgkr@gmail.com"

SAMSUNG_PDF = ("https://images.samsung.com/is/content/samsung/assets/global/ir/"
               "docs/{year}_con_quarter04_all.pdf")
SAMSUNG_YEARS = list(range(2016, 2026))
SAMSUNG_SOURCE_PAGE = ("https://www.samsung.com/global/ir/financial-information/"
                       "audited-financial-statements/")

HYNIX_424B4 = ("https://www.sec.gov/Archives/edgar/data/2120882/"
               "000119312526299963/d32785d424b4.htm")
HYNIX_ACCESSION = "0001193125-26-299963"
HYNIX_CIK = 2120882

# The half-year results, filed on Form 6-K. Both companies are mid-cycle-turn,
# so the last full fiscal year is already stale: SK hynix earned more operating
# profit in the second quarter of 2026 than in the whole of FY2025.
HYNIX_6K = ("https://www.sec.gov/Archives/edgar/data/2120882/"
            "000119312526354777/d147827d6k.htm")
HYNIX_6K_ACCESSION = "0001193125-26-354777"
SAMSUNG_INTERIM_PDF = ("https://images.samsung.com/is/content/samsung/assets/global/"
                       "ir/docs/2026_con_quarter02_soi.pdf")


def fetch(url, path, ua):
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


# ---------------------------------------------------------------------------
# Samsung: read the audited statements out of the PDF
# ---------------------------------------------------------------------------

# The PDF text layer puts stray spaces inside figures - "57, 856,378",
# "32,707 ,431", "18, 840,559" and "20 ,012,416" all appear in the FY2025
# statements. Every one of them sits next to a comma, and separate columns are
# never comma-separated, so closing up whitespace around commas repairs the
# figures without merging two columns into one. Letting the number pattern
# itself span spaces does merge them: "333,605,938 300,870,903" then reads as a
# single 24-digit number, which is how the first pass silently lost every
# Samsung figure.
NUM = r"\(?-?\d[\d,]*\)?"

# Every amount in these statements is at least four digits and so carries a
# thousands comma, while a note reference never does. Requiring the comma is
# what keeps "Income tax expense (benefit) 25 3,078,383 (4,480,835)" from
# reading the note number 25 as the tax charge - which it did, and which put
# FY2024's tax into the FY2023 row.
FIGURE = r"\(?-?\d{1,3}(?:,\d{3})+\)?"


def _split_group(m):
    """Rejoin a thousands group the PDF text layer broke in half.

    The interim statements contain "50,322,0 27" and "20,820,6 94": a space
    dropped inside the final group. Two conditions together tell that apart
    from the space between two columns - the fragments must add up to exactly
    three digits, and the right fragment must END the number rather than start
    a new one. Without the second condition a note reference glues itself to
    the figure beside it: "4,12,13,29 1,177,508" became "4,12,13,291,177,508",
    which is how Samsung's short-term borrowings came out at 41 quadrillion won.
    """
    left, right = m.group(2), m.group(3)
    if len(left) + len(right) == 3:
        return f",{left}{right}"
    return m.group(0)


def _tidy(line):
    line = re.sub(r"\s*,\s*", ",", line)
    return re.sub(r"(,)(\d{1,2}) (\d{1,2})(?=\s|$)", _split_group, line)


def _num(s):
    s = s.strip()
    neg = s.startswith("(") or s.endswith(")")
    s = re.sub(r"[(),\s]", "", s)
    if not s or not re.fullmatch(r"-?\d+", s):
        return None
    v = float(s)
    return -v if neg else v


STATEMENT_HEADS = [
    ("position", "CONSOLIDATED STATEMENTS OF FINANCIAL POSITION"),
    ("income", "CONSOLIDATED STATEMENTS OF PROFIT OR LOSS"),
    ("comprehensive", "CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME"),
    ("equity", "CONSOLIDATED STATEMENTS OF CHANGES IN EQUITY"),
    ("cashflow", "CONSOLIDATED STATEMENTS OF CASH FLOWS"),
]


def samsung_sections(text):
    """Split the document into the primary statements and the notes.

    Searching the whole PDF for "Revenue" finds the segment note before the
    income statement and returns four segment figures run together. Every line
    has to be read inside the statement it belongs to.
    """
    marks = []
    for key, head in STATEMENT_HEADS:
        for m in re.finditer(re.escape(head), text):
            marks.append((m.start(), key))
    marks.sort()
    sections, seen = {}, set()
    for i, (pos, key) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        sections.setdefault(key, "")
        sections[key] += text[pos:end]
        seen.add(key)
    notes_at = max((p for p, _ in marks), default=0)
    sections["notes"] = text[notes_at:]
    return sections


def samsung_find(text, label, want=2):
    """Numbers following a label on its own line, tolerating note references."""
    if text is None:
        return None
    for line in text.splitlines():
        s = line.strip()
        if not s.lower().startswith(label.lower()):
            continue
        # Tidy only the numeric remainder: the label itself may contain a
        # comma ("property, plant and equipment") that closing up would break.
        rest = _tidy(s[len(label):])
        if rest[:1].isalpha():          # "Revenue" must not match "Revenues from"
            continue
        nums = [_num(x) for x in re.findall(FIGURE, rest)]
        nums = [n for n in nums if n is not None and n != 0]
        if len(nums) >= want:
            return nums[:want]
    return None


def samsung_largest(text, label, want=2):
    """The occurrence of `label` carrying the largest figures.

    Depreciation appears in the segment note per segment, in the expense-by-
    nature note, and in the cash-flow adjustments note. All but the segment
    rows give the consolidated total, which is the largest.
    """
    best = None
    for line in (text or "").splitlines():
        s = line.strip()
        if not s.lower().startswith(label.lower()):
            continue
        rest = _tidy(s[len(label):])
        if rest[:1].isalpha():
            continue
        nums = [_num(x) for x in re.findall(FIGURE, rest)]
        nums = [n for n in nums if n is not None and n != 0]
        if len(nums) >= want and (best is None or abs(nums[0]) > abs(best[0])):
            best = nums[:want]
    return best


def samsung_subtotal(text, after_label):
    """The unlabelled subtotal row that closes a balance-sheet section."""
    if not text:
        return None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().lower().startswith(after_label.lower()):
            for nxt in lines[i + 1:i + 4]:
                s = _tidy(nxt.strip())
                if re.match(r"^[\d(]", s):
                    nums = [_num(x) for x in re.findall(FIGURE, s)]
                    nums = [n for n in nums if n is not None and n != 0]
                    if len(nums) >= 2:
                        return nums[:2]
    return None


def samsung_year(path, year):
    reader = pypdf.PdfReader(path)
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    text = text.replace("–", "-").replace("’", "'")
    sec = samsung_sections(text)

    def g(labels, where, want=2):
        """First label that hits. Samsung renamed several lines over the decade -
        "Profit for the period" became "Profit for the year", "Net cash inflow
        from operating activities" became "Net cash provided by ...", and
        "Purchases of property, plant and equipment" became "Acquisition of ...".
        """
        for label in ([labels] if isinstance(labels, str) else labels):
            got = samsung_find(sec.get(where), label, want)
            if got:
                return got
        return None

    rev = g("Revenue", "income")
    op = g("Operating profit", "income")
    pretax = g("Profit before income tax", "income")
    tax = g(["Income tax expense", "Income tax benefit"], "income")
    ni = g(["Profit for the year", "Profit for the period"], "income")
    fin_inc = g("Financial income", "income")
    fin_exp = g("Financial expense", "income")
    cash = g("Cash and cash equivalents", "position")
    stfi = g("Short-term financial instruments", "position")
    stb = g("Short-term borrowings", "position")
    cur_lt = g("Current portion of long-term liabilities", "position")
    deb = g("Debentures", "position")
    ltb = g("Long-term borrowings", "position")
    eq = g("Total equity", "position")
    ca = (g("Total current assets", "position")
          or samsung_subtotal(sec.get("position"), "Other current assets"))
    cl = (g("Total current liabilities", "position")
          or samsung_subtotal(sec.get("position"), "Other current liabilities")
          or samsung_subtotal(sec.get("position"), "Provisions"))
    ocf = g(["Net cash provided by operating activities",
             "Net cash inflow from operating activities",
             "Net cash from operating activities"], "cashflow")
    capex = g(["Acquisition of property, plant and equipment",
               "Purchases of property, plant and equipment"], "cashflow")
    dep = samsung_largest(sec.get("notes"), "Depreciation")
    amo = samsung_largest(sec.get("notes"), "Amortization")

    def one(v, idx=0):
        return None if v is None else v[idx]

    def da(idx):
        d, a = one(dep, idx), one(amo, idx)
        if d is None:
            return None
        return d + (a or 0)

    out = {}
    for idx, fy in ((0, year), (1, year - 1)):
        row = {
            "fiscal_year": fy,
            "revenue": one(rev, idx),
            "operating_income": one(op, idx),
            "pretax_income": one(pretax, idx),
            "income_tax_expense": one(tax, idx),
            "net_income": one(ni, idx),
            "cash_and_equivalents": (None if one(cash, idx) is None else
                                     one(cash, idx) + (one(stfi, idx) or 0)),
            "short_term_debt": (None if one(stb, idx) is None else
                                one(stb, idx) + (one(cur_lt, idx) or 0)),
            "long_term_debt": (None if (one(deb, idx) is None and one(ltb, idx) is None)
                               else (one(deb, idx) or 0) + (one(ltb, idx) or 0)),
            "total_equity": one(eq, idx),
            "operating_cash_flow": one(ocf, idx),
            "capex": (None if one(capex, idx) is None else abs(one(capex, idx))),
            "depreciation_amortization": da(idx),
            "financial_income": one(fin_inc, idx),
            "financial_expense": one(fin_exp, idx),
            "current_assets": one(ca, idx),
            "current_liabilities": one(cl, idx),
        }
        out[fy] = row
    return out, text


def collect_samsung_interim(refresh=False):
    """Samsung's half-year 2026 profit or loss, from the interim statements."""
    path = os.path.join(DOC_DIR, "samsung_2026q2_soi.pdf")
    if refresh and os.path.exists(path):
        os.remove(path)
    fetch(SAMSUNG_INTERIM_PDF, path, UA_SAMSUNG)
    text = "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(path).pages)
    # Columns run: 3M current, 3M prior, USD, USD, 6M current, 6M prior, USD, USD.
    rev = samsung_find(text, "Revenue", 6)
    op = samsung_find(text, "Operating profit", 6)
    if not rev or not op:
        return None
    return {
        "period": "2026 상반기 (검토받은 요약중간연결재무제표)",
        "quarter_revenue": rev[0],
        "quarter_operating_income": op[0],
        "half_revenue": rev[4],
        "half_operating_income": op[4],
        "prior_year_half_revenue": rev[5],
        "prior_year_half_operating_income": op[5],
        "source": SAMSUNG_INTERIM_PDF,
    }


def collect_hynix_interim(refresh=False):
    """SK hynix's half-year 2026 results, from the Form 6-K."""
    path = os.path.join(DOC_DIR, "skhynix_6k_2026q2.htm")
    if refresh and os.path.exists(path):
        os.remove(path)
    fetch(HYNIX_6K, path, UA_SEC)
    import html as _html
    raw = open(path, encoding="utf-8", errors="replace").read()
    t = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", raw)))
    i = t.find("Category Second quarter of 2026")
    if i < 0:
        return None
    seg = t[i:i + 900]

    def after(label):
        m = re.search(re.escape(label) + r"\s+([\d,]+)", seg)
        return float(m.group(1).replace(",", "")) if m else None

    return {
        "period": "2026 상반기 (Form 6-K, K-IFRS 연결)",
        "quarter_revenue": after("Revenue"),
        "quarter_operating_income": after("Operating profit"),
        "half_revenue": after("Cumulative revenue"),
        "half_operating_income": after("Cumulative operating profit"),
        "half_net_income": after("Cumulative profit"),
        "source": HYNIX_6K,
        "accession": HYNIX_6K_ACCESSION,
    }


def collect_samsung(refresh=False):
    years = {}
    sources = {}
    for y in SAMSUNG_YEARS:
        path = os.path.join(DOC_DIR, f"samsung_{y}_all.pdf")
        if refresh and os.path.exists(path):
            os.remove(path)
        fetch(SAMSUNG_PDF.format(year=y), path, UA_SAMSUNG)
        parsed, _ = samsung_year(path, y)
        # The filing for year Y restates Y-1, so a later filing wins: it is the
        # figure as most recently audited.
        for fy, row in parsed.items():
            if fy < SAMSUNG_YEARS[0] - 1:
                continue
            # The later filing wins on any line it carries, but a line it omits
            # keeps the earlier filing's figure rather than going blank.
            merged = dict(years.get(fy, {}))
            for k, v in row.items():
                if v is not None or k not in merged:
                    merged[k] = v
            years[fy] = merged
            sources.setdefault(fy, {})
            sources[fy] = {"filed_for_year": max(y, sources[fy].get("filed_for_year", 0)),
                           "document": SAMSUNG_PDF.format(year=y)}
        print(f"  [005930] FY{y} parsed "
              f"revenue={parsed[y]['revenue']} op={parsed[y]['operating_income']}")
    return years, sources


# ---------------------------------------------------------------------------
# SK hynix: read the audited statements out of the 424B4
# ---------------------------------------------------------------------------

def _last(nums, n):
    """The final n numbers on a row.

    Statement rows carry the note reference first ("4,24,31" arrives as 42431),
    then one column per year. Taking from the right drops the reference without
    having to model how the note numbers were run together.
    """
    return nums[-n:] if len(nums) >= n else None


def hynix_rows(tables, idx, n):
    out = {}
    for r in tables[idx]["rows"]:
        lbl, nums = htab.label_and_numbers(r)
        if not lbl:
            continue
        got = _last(nums, n)
        if got:
            out.setdefault(lbl, got)
    return out


def collect_hynix(refresh=False):
    path = os.path.join(DOC_DIR, "skhynix_424b4.htm")
    if refresh and os.path.exists(path):
        os.remove(path)
    fetch(HYNIX_424B4, path, UA_SEC)
    T = htab.tables(path)

    def find(pred, lo=0, hi=10 ** 9):
        for i, t in enumerate(T):
            if lo <= t["start"] <= hi and pred(t):
                return i
        return None

    def has(t, *words):
        flat = " ".join(" ".join(r) for r in t["rows"])
        return all(w.lower() in flat.lower() for w in words)

    # Restrict to the audited statements. The MD&A earlier in the prospectus
    # repeats the same line names in a table denominated in BILLIONS of won,
    # and picking that one up silently divides every figure by a thousand.
    FS = 2_000_000

    def millions(t):
        flat = " ".join(" ".join(r) for r in t["rows"][:4]).lower()
        return "in millions of korean won" in flat

    i_assets = find(lambda t: millions(t) and has(t, "Cash and cash equivalents",
                                                  "Total assets"), lo=FS)
    i_liab = find(lambda t: millions(t) and has(t, "Total liabilities",
                                                "Total equity"), lo=FS)
    i_is = find(lambda t: millions(t) and has(t, "Revenue", "Cost of sales",
                                              "Income tax expense (benefits)"), lo=FS)
    i_cf = find(lambda t: millions(t) and has(t, "Cash flows from operating activities"),
                lo=FS)
    i_adj = find(lambda t: millions(t) and has(t, "Depreciation", "Amortization",
                                               "Income tax expense (benefit)"),
                 lo=4_200_000)
    for name, i in (("balance sheet (assets)", i_assets), ("balance sheet (liabilities)", i_liab),
                    ("income statement", i_is), ("cash flow", i_cf),
                    ("cash-flow adjustments note", i_adj)):
        if i is None:
            raise SystemExit(f"SK hynix: could not locate the {name} table")

    assets = hynix_rows(T, i_assets, 2)
    liab = hynix_rows(T, i_liab, 2)
    inc = hynix_rows(T, i_is, 3)
    cf = hynix_rows(T, i_cf, 3)
    adj = hynix_rows(T, i_adj, 3)

    def a(k, i):
        v = assets.get(k) or liab.get(k)
        return None if v is None else v[i]

    def s(d, k, i):
        v = d.get(k)
        return None if v is None else v[i]

    years = {}
    # Income statement and cash flow carry 2025/2024/2023; the balance sheet
    # only 2025/2024. FY2023 balance-sheet items that the prospectus does give
    # are picked up individually below.
    for i, fy in ((0, 2025), (1, 2024), (2, 2023)):
        gross = s(inc, "Gross profit (loss)", i)
        sga = s(inc, "Selling and administrative expenses", i)
        rnd = s(inc, "Research and development expenses", i)
        op = None if gross is None else gross - (sga or 0) - (rnd or 0)
        row = {
            "fiscal_year": fy,
            "revenue": s(inc, "Revenue", i),
            "operating_income": op,
            "operating_income_method": "매출총이익 − 판매관리비 − 연구개발비",
            "pretax_income": s(inc, "Profit (loss) before income tax", i),
            "income_tax_expense": s(inc, "Income tax expense (benefits)", i),
            "net_income": s(inc, "Profit (loss) for the year", i),
            "operating_cash_flow": s(cf, "Net cash provided by operating activities", i),
            "capex": abs(s(cf, "Acquisitions of property, plant and equipment", i) or 0) or None,
            "depreciation_amortization": (
                (s(adj, "Depreciation", i) or 0) + (s(adj, "Amortization", i) or 0)) or None,
            "interest_expense": s(adj, "Interest expense", i),
            "interest_income": s(adj, "Interest income", i),
            "cash_end_of_year": s(cf, "Cash and cash equivalents at the end of the year", i),
        }
        if i < 2:
            row.update({
                "cash_and_equivalents": sum(
                    x for x in (a("Cash and cash equivalents", i),
                                a("Short-term financial instruments", i),
                                a("Short-term investment assets", i)) if x),
                "short_term_debt": a("Borrowings", i),
                "long_term_debt": None,   # filled below from the second occurrence
                "total_equity": a("Total equity", i),
                "total_assets": a("Total assets", i),
            })
        years[fy] = row

    # "Borrowings" appears once under current liabilities and once under
    # non-current. htab keeps the first, so the second is read directly.
    bor = [n for r in T[i_liab]["rows"]
           for lbl, n in [htab.label_and_numbers(r)] if lbl == "Borrowings"]
    if len(bor) >= 2:
        for i, fy in ((0, 2025), (1, 2024)):
            years[fy]["short_term_debt"] = _last(bor[0], 2)[i]
            years[fy]["long_term_debt"] = _last(bor[1], 2)[i]

    # Current-asset and current-liability subtotals are unlabelled rows that
    # follow the last named line of each section.
    def subtotal(idx, after_label):
        rows = T[idx]["rows"]
        seen = False
        for r in rows:
            lbl, nums = htab.label_and_numbers(r)
            if lbl == after_label:
                seen = True
                continue
            if seen and lbl is None and len(nums) >= 2:
                return _last(nums, 2)
        return None

    ca = subtotal(i_assets, "Other current assets")
    cl = subtotal(i_liab, "Other current liabilities")
    for i, fy in ((0, 2025), (1, 2024)):
        if ca:
            years[fy]["current_assets"] = ca[i]
        if cl:
            years[fy]["current_liabilities"] = cl[i]

    # FY2023 closing equity comes from the statement of changes in equity.
    for t in T:
        for r in t["rows"]:
            lbl, nums = htab.label_and_numbers(r)
            if lbl == "Balance at December 31, 2023" and len(nums) >= 2:
                years[2023]["total_equity"] = nums[-1]
    years[2023]["cash_and_equivalents"] = years[2023].get("cash_end_of_year")
    years[2023]["balance_sheet_note"] = (
        "FY2023 대차대조표는 F-1에 2025·2024만 실려 있어 자기자본은 자본변동표, "
        "현금은 현금흐름표 기말잔액에서 가져왔고 차입금·유동항목은 공란입니다")

    # Q1 2026 interim, which matters because the cycle turned hard after FY2025.
    i_q = find(lambda t: has(t, "Revenue", "Cost of sales"), lo=4400000)
    q = hynix_rows(T, i_q, 2) if i_q else {}
    interim = None
    if q:
        # The interim statement drops the "(loss)" from the gross-profit label
        # that the annual one carries.
        gross = s(q, "Gross profit (loss)", 0)
        if gross is None:
            gross = s(q, "Gross profit", 0)
        prior_gross = s(q, "Gross profit (loss)", 1)
        if prior_gross is None:
            prior_gross = s(q, "Gross profit", 1)

        def op_from(g, i):
            if g is None:
                return None
            return (g - (s(q, "Selling and administrative expenses", i) or 0)
                    - (s(q, "Research and development expenses", i) or 0))

        interim = {
            "period": "2026 1분기 (검토받은 요약중간재무제표)",
            "revenue": s(q, "Revenue", 0),
            "operating_income": op_from(gross, 0),
            "pretax_income": s(q, "Profit (loss) before income tax", 0)
                             or s(q, "Profit before income tax", 0),
            "prior_year_revenue": s(q, "Revenue", 1),
            "prior_year_operating_income": op_from(prior_gross, 1),
        }

    shares = None
    for t in T:
        for r in t["rows"]:
            lbl, nums = htab.label_and_numbers(r)
            if lbl == "SK Square Co., Ltd." and nums:
                shares = None  # ownership table; total picked up below
    for t in T:
        flat = " ".join(" ".join(r) for r in t["rows"][:3])
        if "Shareholder" in flat and "Number of shares" in flat:
            for r in t["rows"]:
                lbl, nums = htab.label_and_numbers(r)
                if lbl is None and nums and nums[0] > 5e8:
                    shares = nums[0]
    return years, interim, shares


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    os.makedirs(KR_DIR, exist_ok=True)

    print("[005930.KS] Samsung Electronics - audited statements from the IR site")
    sam_years, sam_sources = collect_samsung(args.refresh)
    sam_interim = collect_samsung_interim(args.refresh)
    print(f"  [005930] 2026 상반기 매출={sam_interim and sam_interim['half_revenue']} "
          f"영업이익={sam_interim and sam_interim['half_operating_income']}")

    print("[000660.KS] SK hynix - audited statements from the SEC 424B4")
    hy_years, hy_interim, hy_shares = collect_hynix(args.refresh)
    hy_interim_6k = collect_hynix_interim(args.refresh)
    print(f"  [000660] 2026 상반기 매출={hy_interim_6k and hy_interim_6k['half_revenue']} "
          f"영업이익={hy_interim_6k and hy_interim_6k['half_operating_income']}")
    print(f"  [000660] FY2025 revenue={hy_years[2025]['revenue']} "
          f"op={hy_years[2025]['operating_income']}")

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "currency": "KRW, millions",
        "companies": {
            "005930.KS": {
                "company_name": "삼성전자",
                "company_name_en": "Samsung Electronics Co., Ltd.",
                "listing": "KRX KOSPI 005930",
                "source": "회사가 IR 사이트에 공개하는 감사받은 연결재무제표 (연도별 PDF)",
                "source_page": SAMSUNG_SOURCE_PAGE,
                "source_confidence": "HIGH",
                "source_note": ("SEC 제출서류는 아니지만 회사의 감사받은 연결재무제표 "
                                "원문이며, DART에 제출되는 것과 같은 문서입니다."),
                "documents": sam_sources,
                "interim": sam_interim,
                "years": [sam_years[k] for k in sorted(sam_years)],
            },
            "000660.KS": {
                "company_name": "SK하이닉스",
                "company_name_en": "SK hynix Inc.",
                "listing": "KRX KOSPI 000660 / Nasdaq SKHY (ADS, 2026년 7월 상장)",
                "source": "SEC 424B4 (Form F-1 최종 투자설명서) 내 감사받은 연결재무제표",
                "source_url": HYNIX_424B4,
                "accession": HYNIX_ACCESSION,
                "cik": HYNIX_CIK,
                "source_confidence": "HIGH",
                "source_note": ("2026년 7월 나스닥 ADS 상장으로 SEC 제출서류가 생겼습니다. "
                                "감사받은 연간 재무제표는 FY2023~FY2025 3개 연도뿐입니다."),
                "shares_outstanding": hy_shares,
                "shares_issued": 728_002_365,
                "treasury_shares": 26_310_845,
                "interim": hy_interim_6k or hy_interim,
                "interim_q1_from_f1": hy_interim,
                "years": [hy_years[k] for k in sorted(hy_years)],
            },
        },
    }
    path = os.path.join(KR_DIR, "korea_raw.json")
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False)
    print(f"korea_raw -> {path}")


if __name__ == "__main__":
    main()
