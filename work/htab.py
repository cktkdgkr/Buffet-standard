"""Pull tables out of an SEC HTML filing without a DOM library.

The text-extraction route loses column alignment, which is fatal for a
financial statement: every figure ends up in one long run with no way to tell
which year it belongs to. Splitting on <tr>/<td> keeps rows and columns.
"""
import re, html


def tables(path):
    h = open(path, encoding="utf-8", errors="replace").read()
    out = []
    for m in re.finditer(r"<table[^>]*>(.*?)</table>", h, re.S | re.I):
        rows = []
        for rm in re.finditer(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S | re.I):
            cells = []
            for cm in re.finditer(r"<t[dh][^>]*>(.*?)</t[dh]>", rm.group(1), re.S | re.I):
                c = re.sub(r"<[^>]+>", " ", cm.group(1))
                c = html.unescape(c)
                cells.append(re.sub(r"\s+", " ", c).strip())
            if cells:
                rows.append(cells)
        if rows:
            out.append({"start": m.start(), "rows": rows})
    return out


def num(s):
    """A financial-statement cell to a float. Parentheses are negative."""
    if s is None:
        return None
    s = s.strip().replace(",", "").replace("—", "").replace("—", "")
    s = s.replace("W", "").replace("₩", "").replace("$", "").strip()
    neg = s.startswith("(") or s.endswith(")")
    s = s.strip("()").strip()
    if not s or not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    v = float(s)
    return -v if neg else v


def label_and_numbers(row):
    """First non-empty text cell as the label, every parsable number after it."""
    label, nums = None, []
    for c in row:
        v = num(c)
        if v is not None:
            nums.append(v)
        elif c and label is None and not re.fullmatch(r"[\s\)\(%]*", c):
            label = c
    return label, nums
