"""
idx/index.json 을 HTML 페이지로 냅니다. 보고서 포맷은 HTML 하나입니다.

엔진의 JSON 하나만 읽습니다. --verify 는 만든 페이지의 표·카드·막대·선
그래프·본문 숫자·인용문을 되읽어 엔진과 대조하고, --mutate 는 페이지를
훼손해 그 검사가 실제로 실패하는지 확인합니다.

    python3 export_index_html.py
    python3 export_index_html.py --verify --mutate
"""

import argparse
import html
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "idx", "index.json")
OUT = os.path.join(HERE, "idx", "index_report.html")
BN = 1e9
DISC = ["bond30", "bond30_plus3", "project10", "project11"]
MOS = ["0%", "20%", "30%", "40%"]


def esc(x):
    return html.escape(str(x))


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def sg(x, nd=1):
    return "—" if x is None else f"{x * 100:+.{nd}f}%"


def rng(vals, nd=1):
    """수익률 범위. 소수 첫째 자리까지 같으면 한 값만 씁니다."""
    lo, hi = pct(min(vals), nd), pct(max(vals), nd)
    return lo if lo == hi else f"{lo} ~ {hi}"


def pts(x):
    return "—" if x is None else f"{x:,.0f}"


def table(headers, rows, caption=None, align=None):
    align = align or (["l"] + ["r"] * (len(headers) - 1))
    o = ['<figure class="tw">', '<div class="scroll"><table>',
         "<thead><tr>" + "".join(f'<th class="{a}">{esc(h)}</th>'
                                 for h, a in zip(headers, align))
         + "</tr></thead><tbody>"]
    for r in rows:
        tds = []
        for v, a in zip(r, align):
            st = ""
            if isinstance(v, tuple):
                v, s_ = v
                st = f' data-state="{s_}"' if s_ else ""
            tds.append(f'<td class="{a}"{st}>{v}</td>')
        o.append("<tr>" + "".join(tds) + "</tr>")
    o.append("</tbody></table></div>")
    if caption:
        o.append(f"<figcaption>{caption}</figcaption>")
    o.append("</figure>")
    return "\n".join(o)


def cell_of(X, gkey, dkey):
    row = next(r for r in X["grid"] if r["key"] == gkey)
    return row, next(c for c in row["cells"] if c["discount_key"] == dkey)


def req_of(X, dkey, m):
    return next(r for r in X["required"] if r["discount_key"] == dkey
                and abs(r["margin"] - m) < 1e-9)


def ladder(X, prefix):
    """버핏 기준 할인율에서 성장률 가정별 가치와 안전마진별 매수선 — 범위 막대.

    축은 0 부터 (가장 큰 가치와 현재 지수 중 큰 쪽) × 1.05. 막대 길이와 표식
    위치가 값에 비례해야 하고, 검증기가 그것을 다시 잽니다.
    """
    lvl = X["level"]["price"]
    rows = []
    vmax = lvl
    for g in X["grid"]:
        _, c = cell_of(X, g["key"], "bond30_plus3")
        vmax = max(vmax, c["value"])
    axis = vmax * 1.05
    o = [f'<div class="ladder" data-axis="{axis:.4f}">']
    for g in X["grid"]:
        _, c = cell_of(X, g["key"], "bond30_plus3")
        v, b30 = c["value"], c["buy_level"]["30%"]
        o.append(
            f'<div class="lrow" data-g="{prefix}-{g["key"]}">'
            f'<span class="llab">{esc(g["label"])}</span>'
            f'<span class="ltrack">'
            f'<span class="lbuy" data-bar="{prefix}-{g["key"]}-buy30" '
            f'style="width:{b30 / axis * 100:.3f}%"></span>'
            f'<span class="lval" data-bar="{prefix}-{g["key"]}-value" '
            f'style="width:{(v - b30) / axis * 100:.3f}%;'
            f'left:{b30 / axis * 100:.3f}%"></span>'
            f'<span class="lnow" data-bar="{prefix}-now" '
            f'style="left:{lvl / axis * 100:.3f}%"></span>'
            f'</span>'
            f'<span class="lnum">{pts(b30)} · {pts(v)}</span></div>')
    o.append(f'<div class="laxis"><span>0</span><span>{pts(axis)}</span></div>')
    o.append(f'<p class="lkey">진한 막대 = 안전마진 30% 매수선까지 · 옅은 막대 = '
             f'가치까지 · 세로선 = 지금 {pts(lvl)} · 오른쪽 숫자 = 매수선 · '
             f'가치</p>')
    o.append("</div>")
    return "\n".join(o)


def backtest_svg(bt, key="bond", disc_text="30년 국채+3%p"):
    """지난 30년: 지수 · 버핏 기준 가치 · 안전마진 30% 매수선 (로그 축).

    key 는 그래프를 구분하는 표식입니다. 같은 페이지에 할인율만 다른 그래프가
    둘 있어서, 검증기가 표식으로 먼저 그래프를 특정한 뒤 좌표를 읽습니다.
    """
    rows = [r for r in bt["rows"] if r["value_own30"]]
    W, H, L, R, T, B = 720, 300, 52, 12, 12, 28
    vals = [r["price"] for r in rows] + [r["value_own30"] for r in rows] + \
        [r["buy30_own30"] for r in rows]
    lo, hi = math.log(min(vals) * 0.9), math.log(max(vals) * 1.1)

    def X(i):
        return L + (W - L - R) * i / (len(rows) - 1)

    def Y(v):
        return T + (H - T - B) * (1 - (math.log(v) - lo) / (hi - lo))

    def line(key):
        return " ".join(f"{X(i):.1f},{Y(r[key]):.1f}"
                        for i, r in enumerate(rows))
    ticks = []
    for v in (250, 500, 1000, 2000, 4000, 8000):
        if math.exp(lo) <= v <= math.exp(hi):
            ticks.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" '
                         f'y2="{Y(v):.1f}" class="grid"/>'
                         f'<text x="{L - 6}" y="{Y(v) + 4:.1f}" '
                         f'class="tick" text-anchor="end">{v:,}</text>')
    years = []
    for i, r in enumerate(rows):
        if r["month"].endswith("-06") and int(r["month"][:4]) % 5 == 1:
            years.append(f'<text x="{X(i):.1f}" y="{H - 8}" class="tick" '
                         f'text-anchor="middle">{r["month"][:4]}</text>')
    # 매수선 아래 구간을 음영으로
    shade = []
    for i, r in enumerate(rows):
        if r["below_buy30"]:
            x0 = X(max(i - 0.5, 0))
            x1 = X(min(i + 0.5, len(rows) - 1))
            shade.append(f'<rect x="{x0:.1f}" y="{T}" width="{x1 - x0:.1f}" '
                         f'height="{H - T - B}" class="zone"/>')
    return (
        f'<figure class="chart" data-chart="{key}">'
        f'<svg viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="지난 30년 S&amp;P 500 지수와 버핏 기준 가치, 안전마진 30% '
        f'매수선" data-n="{len(rows)}" data-lo="{lo:.6f}" '
        f'data-hi="{hi:.6f}">'
        + "".join(shade) + "".join(ticks) + "".join(years)
        + f'<polyline class="l-buy" data-line="buy30" points="{line("buy30_own30")}"/>'
        + f'<polyline class="l-val" data-line="value" points="{line("value_own30")}"/>'
        + f'<polyline class="l-px" data-line="price" points="{line("price")}"/>'
        + "</svg>"
        + '<div class="legend"><span><i class="sw px"></i>S&amp;P 500 (월말)</span>'
          '<span><i class="sw val"></i>버핏 기준 가치</span>'
          '<span><i class="sw buy"></i>안전마진 30% 매수선</span>'
          '<span><i class="sw zone"></i>매수선 아래였던 달</span></div>'
        + f"<figcaption>로그 축. 가치 = 그 달의 12개월 EPS·할인율 {disc_text}·"
          f"그 달까지의 30년 EPS 기록(성장률)·ROE {bt['roe'] * 100:.1f}% 로 "
          f"계산. 지금의 잣대를 과거에 댄 것이지 그때의 판단은 "
          f"아닙니다.</figcaption></figure>")


def build(d):
    s, n = d["spx"], d["ndx"]
    m = d["macro"]
    r30 = m["treasury_30y"]["rate"]
    bei = m["breakeven_inflation_10y"]
    dl = {x["key"]: x["label"] for x in d["discounts"]}
    bp = {p["key"]: p for p in d["index_passages"]}
    sv = [cell_of(s, g["key"], "bond30_plus3")[1] for g in s["grid"]]
    nv = [cell_of(n, g["key"], "bond30_plus3")[1] for g in n["grid"]]
    s_lo, s_hi = min(c["value"] for c in sv), max(c["value"] for c in sv)
    n_lo, n_hi = min(c["value"] for c in nv), max(c["value"] for c in nv)
    s_b_lo, s_b_hi = min(c["buy_level"]["30%"] for c in sv), \
        max(c["buy_level"]["30%"] for c in sv)
    n_b_lo, n_b_hi = min(c["buy_level"]["30%"] for c in nv), \
        max(c["buy_level"]["30%"] for c in nv)
    s_ir = [g["implied_return"] for g in s["grid"]]
    n_ir = [g["implied_return"] for g in n["grid"]]
    _, s_own = cell_of(s, "own_sustained", "bond30_plus3")
    _, n_own = cell_of(n, "own_sustained", "bond30_plus3")
    rec, cape, bt, fw = s["record"], s["cape"], s["backtest"], \
        s["forward_returns"]
    agg = n["aggregate"]
    o = []
    w = o.append

    w("<title>지수 매수선 판정</title>")
    w('<meta name="claude:viewport-fit-sides" content="cover">')
    w('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
      'family=Noto+Serif+KR:wght@500;700&family=Noto+Sans+KR:wght@400;500;700'
      '&family=IBM+Plex+Mono:wght@400;500&display=swap">')
    # ---- design plan ----------------------------------------------------
    # 장부(ledger) 같은 판정문: 짙은 병록색 하나로 구조를 잡고, 숫자는 등폭.
    # 의미색은 한 가지 뜻만 — over/under 는 매수선 판정, pos/neg 는 부호,
    # flag 는 주목. 범위 막대와 30년 선 그래프가 페이지의 두 시각 장치.
    w("""<style>
:root{
  --bg:#f7f7f4; --panel:#ffffff; --panel2:#eceee9;
  --fg:#1b1f1c; --dim:#4c5550; --dim2:#7a837e;
  --line:#d8dcd6; --line2:#c2c8c1;
  --accent:#24584a; --accent-soft:#e3ece8;
  --over:#2d6a4a; --over-soft:#e5efe8;
  --under:#9c3f2c; --under-soft:#f6e7e2;
  --pos:#2d6a4a; --neg:#9c3f2c;
  --flag:#8a6410; --flag-soft:#f5edd9;
  --buy:#2d6a4a; --val:#7fa89a; --now:#1b1f1c; --px:#1b1f1c;
  --zone:#e3efe7; --quote:#f1f1ec;
  --display:"Noto Serif KR",Georgia,"Times New Roman",serif;
  --body:"Noto Sans KR",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#121614; --panel:#1a1f1c; --panel2:#222925;
  --fg:#e9eeeb; --dim:#a7b2ac; --dim2:#7d8882;
  --line:#2d3530; --line2:#3c4640;
  --accent:#86c2ae; --accent-soft:#1c2a25;
  --over:#7fc39a; --over-soft:#15271d;
  --under:#e39a81; --under-soft:#2b1a15;
  --pos:#7fc39a; --neg:#e39a81;
  --flag:#d9b45c; --flag-soft:#2b2412;
  --buy:#7fc39a; --val:#3f6b5d; --now:#e9eeeb; --px:#e9eeeb;
  --zone:#17271f; --quote:#1d221f;
  color-scheme:dark;
}}
:root[data-theme="dark"]{
  --bg:#121614; --panel:#1a1f1c; --panel2:#222925;
  --fg:#e9eeeb; --dim:#a7b2ac; --dim2:#7d8882;
  --line:#2d3530; --line2:#3c4640;
  --accent:#86c2ae; --accent-soft:#1c2a25;
  --over:#7fc39a; --over-soft:#15271d;
  --under:#e39a81; --under-soft:#2b1a15;
  --pos:#7fc39a; --neg:#e39a81;
  --flag:#d9b45c; --flag-soft:#2b2412;
  --buy:#7fc39a; --val:#3f6b5d; --now:#e9eeeb; --px:#e9eeeb;
  --zone:#17271f; --quote:#1d221f;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:var(--body);
  font-size:16px;line-height:1.72;margin:0;-webkit-text-size-adjust:100%;
  /* 한국어 복합명사가 음절에서 끊기지 않게 — 없으면 "자/본비용" */
  word-break:keep-all;overflow-wrap:break-word}
.wrap{max-width:54rem;margin:0 auto;
  padding-left:max(16px,env(safe-area-inset-left,0px));
  padding-right:max(16px,env(safe-area-inset-right,0px));
  padding-block:0}
h1,h2,h3,h4{font-family:var(--display);text-wrap:balance;margin:0}
h1{font-size:clamp(1.75rem,5vw,2.5rem);line-height:1.22;font-weight:700;
  letter-spacing:-.015em}
h2{font-size:clamp(1.28rem,3.3vw,1.6rem);line-height:1.3;font-weight:700;
  margin-block:2.9rem .35rem;border-top:2px solid var(--fg);
  padding-block:.6rem 0}
h3{font-size:1.06rem;line-height:1.4;font-weight:700;margin-block:1.9rem .25rem}
p{margin:0 0 1rem}
a{color:var(--accent);text-underline-offset:.18em}
ul,ol{margin:0 0 1rem;padding-left:1.15rem}
li{margin-block:.42rem}
code{font-family:var(--mono);font-size:.86em;background:var(--panel2);
  padding:.08rem .3rem;border-radius:2px}
.eyebrow{font-family:var(--mono);font-size:.72rem;font-weight:500;
  letter-spacing:.1em;text-transform:uppercase;color:var(--accent);
  margin:0 0 .55rem}
.lede{font-size:1.06rem;color:var(--dim);margin-block:.9rem 0}
.meta{font-family:var(--mono);font-size:.75rem;line-height:1.9;
  color:var(--dim2);border-top:1px solid var(--line);
  margin-block:1.3rem 0;padding-block:.85rem 0}
.meta b{color:var(--dim);font-weight:500}
header.page{padding-block:2.5rem 0}
footer.page{border-top:1px solid var(--line);margin-block:3rem 0;
  padding-block:1.1rem 2.6rem;font-size:.84rem;color:var(--dim)}

.cards{display:grid;gap:1px;background:var(--line);
  border:1px solid var(--line);margin-block:1.5rem 0}
@media(min-width:640px){.cards{grid-template-columns:1fr 1fr}}
.card{background:var(--panel);padding:1.05rem 1.1rem 1.15rem;min-width:0}
.card h3{margin:0 0 .15rem;font-size:1.02rem}
.card .lvl{font-family:var(--display);font-size:2rem;font-weight:700;
  line-height:1.1;font-variant-numeric:tabular-nums}
.card .sub{font-size:.8rem;color:var(--dim2);margin:0 0 .65rem}
.card dl{display:grid;grid-template-columns:auto 1fr;gap:.3rem .9rem;
  margin:0;font-size:.9rem}
.card dt{color:var(--dim)}
.card dd{margin:0;text-align:right;font-family:var(--mono);
  font-variant-numeric:tabular-nums}
.card dd.strong{font-weight:500;color:var(--accent)}
.card .ctitle{font-size:.76rem;font-weight:700;letter-spacing:.04em;
  color:var(--dim2);margin:.8rem 0 .3rem;border-top:1px solid var(--line);
  padding-top:.6rem}
.cnote{font-size:.8rem;color:var(--dim);margin:.6rem 0 0}
.card dd[data-state="flag"]{color:var(--flag)}

.verdict{border:2px solid var(--fg);background:var(--panel);
  padding:1.05rem 1.1rem;margin-block:1.4rem}
.verdict h3{margin-top:0}
.callout{border:1px solid var(--line2);background:var(--panel2);
  padding:.95rem 1.05rem;margin-block:1.2rem;font-size:.93rem}

figure.tw{margin:1rem 0 1.4rem}
.scroll{overflow-x:auto;border:1px solid var(--line);background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{padding:.44rem .62rem;border-bottom:1px solid var(--line);
  white-space:nowrap}
thead th{background:var(--panel2);font-weight:700;font-size:.78rem;
  color:var(--dim);border-bottom:1px solid var(--line2)}
tbody tr:last-child td{border-bottom:0}
td{font-family:var(--mono);font-variant-numeric:tabular-nums}
td.l,th.l{text-align:left} td.r,th.r{text-align:right}
td.w,th.w{text-align:left;white-space:normal;min-width:13rem}
td.l,td.w{font-family:var(--body)}
td[data-state="over"]{color:var(--over);background:var(--over-soft)}
td[data-state="under"]{color:var(--under);background:var(--under-soft)}
td[data-state="pos"]{color:var(--pos)}
td[data-state="neg"]{color:var(--neg)}
td[data-state="flag"]{color:var(--flag);background:var(--flag-soft)}
figcaption{font-size:.78rem;color:var(--dim2);margin-block:.45rem 0}

/* 범위 막대: 안전마진 30% 매수선까지(진한색) + 가치까지(옅은색) + 현재 지수(선) */
.ladder{border:1px solid var(--line);background:var(--panel);
  padding:.9rem 1rem;margin-block:1rem 1.4rem}
.lrow{display:grid;grid-template-columns:1fr;gap:.2rem;margin-block:.55rem}
@media(min-width:640px){.lrow{grid-template-columns:13rem 1fr 7.5rem;
  align-items:center;gap:.7rem}}
.llab{font-size:.84rem;color:var(--dim);min-width:0}
.ltrack{position:relative;height:1.15rem;background:var(--panel2);
  border:1px solid var(--line)}
.lbuy{position:absolute;left:0;top:0;bottom:0;background:var(--buy);
  opacity:.85}
.lval{position:absolute;top:0;bottom:0;background:var(--val);opacity:.7}
.lnow{position:absolute;top:-.3rem;bottom:-.3rem;width:2px;
  background:var(--now)}
.lnum{font-family:var(--mono);font-size:.78rem;color:var(--dim);
  text-align:right}
.laxis{display:flex;justify-content:space-between;font-family:var(--mono);
  font-size:.72rem;color:var(--dim2);margin-top:.4rem}
.lkey{font-size:.76rem;color:var(--dim2);margin:.35rem 0 0}

.chart{margin:1rem 0 1.4rem;border:1px solid var(--line);
  background:var(--panel);padding:.6rem .6rem .8rem;overflow-x:auto}
.chart svg{display:block;width:100%;min-width:34rem;height:auto}
.chart .grid{stroke:var(--line);stroke-width:1}
.chart .tick{font-family:var(--mono);font-size:11px;fill:var(--dim2)}
.chart .zone{fill:var(--zone)}
.chart polyline{fill:none;stroke-linejoin:round}
.chart .l-px{stroke:var(--px);stroke-width:1.6}
.chart .l-val{stroke:var(--val);stroke-width:2}
.chart .l-buy{stroke:var(--buy);stroke-width:2;stroke-dasharray:5 4}
.legend{display:flex;flex-wrap:wrap;gap:.2rem 1rem;font-size:.78rem;
  color:var(--dim);margin-top:.5rem}
.sw{display:inline-block;width:.85rem;height:.2rem;margin-right:.35rem;
  vertical-align:middle}
.sw.px{background:var(--px)} .sw.val{background:var(--val);height:.25rem}
.sw.buy{background:var(--buy)} .sw.zone{background:var(--zone);height:.7rem}

blockquote{margin:0 0 1rem;background:var(--quote);
  border-left:3px solid var(--accent);padding:.85rem 1rem}
blockquote p{margin:0 0 .5rem;font-family:var(--mono);font-size:.84rem;
  line-height:1.75;color:var(--dim)}
blockquote .src{font-family:var(--mono);font-size:.74rem;color:var(--dim2);
  display:block;margin-top:.4rem}
</style>""")
    w('<div class="wrap">')

    # ------------------------------------------------------------ header
    w('<header class="page">')
    w(f'<p class="eyebrow">{esc(d["generated"])} · S&amp;P 500 · '
      f'Nasdaq-100</p>')
    w("<h1>S&amp;P 500·나스닥100, 버핏 기준으로 얼마에 사야 하나</h1>")
    w(f'<p class="lede">이 프로젝트가 개별 기업에 써 온 잣대 — 성장률 가정 × '
      f'할인율의 격자, 안전마진 매수선, 거꾸로 푼 요구 성장률 — 를 두 지수에 '
      f'그대로 댔습니다. 성장률은 S&amp;P 500 의 <b>30년 이익 기록</b>에서 '
      f'규칙으로 뽑았습니다.</p>')
    w(f'<p class="meta">자료 기준일 <b>{esc(d["generated"])}</b> · 지수 종가 '
      f'<b>{esc(s["level"]["date"])}</b><br>S&amp;P 500 이익 <b>12개월 누적 '
      f'{esc(s["earnings"]["as_of"])}</b> (S&amp;P 보고 기준) · 나스닥100 이익 '
      f'<b>구성종목 SEC 공시 집계</b><br>30년 국채 <b>{pct(r30, 2)}</b> · '
      f'기대인플레이션 <b>{pct(bei["rate"], 2)}</b> '
      f'(FRED {esc(bei["as_of"])})</p>')
    w("</header>")

    # ------------------------------------------------------------ cards
    w('<div class="cards">')
    for key, X, lo, hi, blo, bhi, irs, own in (
            ("spx", s, s_lo, s_hi, s_b_lo, s_b_hi, s_ir, s_own),
            ("ndx", n, n_lo, n_hi, n_b_lo, n_b_hi, n_ir, n_own)):
        pe = X["earnings"]["pe_now"]
        w(f'<div class="card" data-card="{key}">')
        w(f'<h3>{esc(X["label"])}</h3>')
        w(f'<div class="lvl" data-v="{key}-level">{pts(X["level"]["price"])}'
          f'</div>')
        w(f'<p class="sub">{esc(X["level"]["date"])} 종가 · '
          f'{"P/E" if key == "spx" else "P/NOPAT"} '
          f'<span data-v="{key}-pe">{pe:.1f}</span>배</p>')
        w("<dl>")
        w(f'<dt>버핏 기준 가치</dt><dd data-v="{key}-value">{pts(lo)} ~ '
          f'{pts(hi)}</dd>')
        # 매수선은 판정이 아니라 가격이라 의미색(under)을 쓰지 않습니다.
        w(f'<dt>안전마진 30% 매수선</dt><dd class="strong" '
          f'data-v="{key}-buy">{pts(blo)} ~ {pts(bhi)}</dd>')
        ra = [g["returns_at"] for g in X["grid"]]
        w('</dl><p class="ctitle">기대수익률 — 그 가격에 샀을 때</p><dl>')
        w(f'<dt>지금 지수에 사면</dt><dd data-state="flag" '
          f'data-v="{key}-ir">{rng([g["implied_return"] for g in X["grid"]])}'
          f'</dd>')
        w(f'<dt>버핏 기준 가치에 사면</dt><dd '
          f'data-v="{key}-ir-value">{rng([x["value"] for x in ra])}</dd>')
        w(f'<dt>안전마진 30% 매수선에 사면</dt><dd class="strong" '
          f'data-v="{key}-ir-buy">{rng([x["buy30"] for x in ra])}</dd>')
        w(f'<dt>비교: 30년 국채</dt><dd>{pct(r30, 2)}</dd>')
        w("</dl></div>")
    w("</div>")
    w(f'<p class="cnote">기대수익률 = 그 가격에 사서 각 성장률 가정(4개)이 '
      f'그대로 실현될 때의 연수익률, 범위는 가정 사이의 차이입니다. '
      f'<b>버핏 기준 가치에 사면 정의상 할인율 {pct(r30 + 0.03, 2)}와 '
      f'같습니다</b> — 가치란 그 수익률을 내는 가격이기 때문입니다. '
      f'30% 싸게 사도 연 수익률이 2%p 남짓만 오르는 것은, 이 수익률이 '
      f'<b>영원히 보유하며 현금흐름만 받는다</b>고 가정한 값이라 시장 '
      f'가격이 가치로 되돌아가며 생기는 차익은 넣지 않았기 때문입니다.</p>')

    # ------------------------------------------------------------ verdict
    rq_s0 = req_of(s, "bond30_plus3", 0.0)
    rq_n0 = req_of(n, "bond30_plus3", 0.0)
    w('<div class="verdict">')
    w("<h3>한 줄 판정</h3>")
    w(f'<p><b>두 지수 모두 버핏 기준으로는 안전마진이 없습니다.</b> 버핏의 '
      f'할인율(장기 국채 + 3%p = {pct(r30 + 0.03, 2)})로 계산한 가치가 '
      f'S&amp;P 500 은 <b data-v="v-spx">{pts(s_lo)}~{pts(s_hi)}</b>, '
      f'나스닥100 은 <b data-v="v-ndx">{pts(n_lo)}~{pts(n_hi)}</b>이고, '
      f'둘 다 지금 지수({pts(s["level"]["price"])}, '
      f'{pts(n["level"]["price"])})보다 낮습니다. 안전마진 30%를 적용한 '
      f'매수선은 S&amp;P 500 <b data-v="b-spx">{pts(s_b_lo)}~{pts(s_b_hi)}'
      f'</b>, 나스닥100 <b data-v="b-ndx">{pts(n_b_lo)}~{pts(n_b_hi)}</b>'
      f'입니다.</p>')
    w(f'<p>같은 사실을 수익률로 바꾸면 더 분명합니다. 지금 가격에 사서 각 '
      f'성장률 가정이 그대로 실현되면 기대수익률은 S&amp;P 500 '
      f'<b data-v="ir-spx">{pct(min(s_ir))}~{pct(max(s_ir))}</b>, 나스닥100 '
      f'<b data-v="ir-ndx">{pct(min(n_ir))}~{pct(max(n_ir))}</b>입니다. 30년 '
      f'국채 {pct(r30, 2)} 위의 몫은 <b>1~3%p</b> — 버핏이 국채보다 '
      f'"significantly higher"를 요구한다고 말한 것과 비교하면 얇습니다.</p>')
    w(f'<p>S&amp;P 500 은 <b>안전마진을 0으로 해도</b> 자기 돈으로 조달 '
      f'가능한 어떤 성장률로도 지금 가격이 설명되지 않습니다(성장률을 ROE '
      f'{pct(s["incremental_return"])} 직전까지 올려도 가치 천장이 '
      f'<b data-v="ceil-spx">{pts(rq_s0.get("ceiling_level"))}</b>). 나스닥100 '
      f'은 안전마진 0에서만 1년차 '
      f'<b data-v="rq-ndx">{pct(rq_n0.get("growth_year1"))}</b>(10년 평균 '
      f'{pct(rq_n0.get("nopat_cagr_10y"))}) 성장을 요구하고, 안전마진 20% '
      f'이상에서는 해가 없습니다.</p>')
    w(f'<p><b>다만 버핏이 지수 투자자에게 준 처방은 "매수선까지 기다려라"가 '
      f'아닙니다.</b> 그는 1993년과 2013년에 같은 말을 했습니다 — <b>나눠서 '
      f'사라</b>, 그리고 가장 큰 위험은 <b>극단적으로 들뜬 시점에 한꺼번에 '
      f'들어가는 것</b>이다. 지금 S&amp;P 500 의 CAPE 는 '
      f'<b data-v="cape">{cape["current"]:.1f}</b>로 1950년 이후 '
      f'<b data-v="cape-pct">{pct(cape["share_below_current_since_1950"], 0)}'
      f'</b>의 달보다 높습니다.</p>')
    w("</div>")

    # ------------------------------------------------------------ 잣대
    w("<h2>이 보고서가 쓰는 잣대</h2>")
    w(f'<p>개별 기업에 쓴 모형을 그대로 씁니다: 10년간 성장률이 감쇠하고, '
      f'성장에 필요한 재투자(= 성장률 ÷ 재투자 수익률)를 뺀 현금을 할인하고, '
      f'그 뒤는 영구가치로 둡니다. 영구성장률은 기대인플레이션 '
      f'{pct(d["terminal"], 2)}(실질 0%).</p>')
    w(table(["항목", "개별 기업", "지수에서"],
            [["분자", "NOPAT (영업이익 × (1 − 세율))",
              ("S&amp;P 500: S&amp;P 보고 기준 EPS. 나스닥100: 구성종목 NOPAT "
               "합 (순이익은 민감도로)", "")],
             ["재투자 수익률", "증분 ROIC",
              ("ROE. S&amp;P 500 은 1999~2025년 중위, 나스닥100 은 구성종목 "
               "NOPAT÷자기자본", "")],
             ["할인율", "국채 · 국채+3%p · 10% · 11%",
              ("같음. <b>국채+3%p 는 1994년 발언(국채 7% → 10%)에서 읽은 "
               "인용자의 해석이고 버핏의 규칙이 아닙니다</b>", "")],
             ["성장률 가정", "자기 10년 영업이익 기록에서 규칙으로",
              ("자기 <b>30년</b> EPS 기록에서 같은 규칙으로 (절반·유지) + "
               "기초율 중위 + 최근 10년", "")],
             ["안전마진", "0·20·30·40%", ("같음", "")]],
            align=["l", "l", "w"]))
    w('<div class="callout"><p><b>왜 순수 국채 할인율 칸은 판정에서 빼고 '
      ' 읽는가.</b> 30년 국채로 할인하면서 영구성장률을 명목 GDP 로 두면 분모가 '
      '음수가 되어 발산합니다 — 이 프로젝트가 앞선 보고서에서 확인한 사실입니다. '
      '그래서 국채 칸은 "할인율이 이 정도로 낮아야 지금 가격이 설명된다"는 '
      '참고로만 둡니다.</p></div>')

    # =========================================================== S&P 500
    w("<h2>S&amp;P 500</h2>")
    w("<h3>30년 기록 — 이익은 무엇을 해 왔나</h3>")
    rows = []
    for k in ("10", "20", "30"):
        wv, pv = rec["windows"][k], rec["price"][k]
        rows.append([f"{k}년", f'{esc(wv["from"])} → {esc(wv["to"])}',
                     pct(wv["eps_cagr_nominal"], 2), pct(wv["eps_cagr_real"], 2),
                     pct(pv["cagr"], 2)])
    w(table(["기간", "이익 창", "EPS 연평균 (명목)", "EPS 연평균 (실질)",
             "지수 연평균"], rows,
            caption="EPS 는 12개월 누적 보고 기준. 실질 = 2026년 9월 달러. "
                    "지수 연평균은 월말 종가, 배당 제외."))
    p30 = rec["pe_30y"]
    w(f'<p>30년 동안 이익은 연 <b data-v="eps30">'
      f'{pct(rec["windows"]["30"]["eps_cagr_nominal"], 2)}</b>(실질 '
      f'{pct(rec["windows"]["30"]["eps_cagr_real"], 2)}) 늘었고, 지수는 연 '
      f'{pct(rec["price"]["30"]["cagr"], 2)} 올랐습니다. 지수가 이익보다 '
      f'빨리 오른 만큼 배수가 올라갔습니다. <b>기간을 어떻게 자르느냐가 '
      f'답을 바꿉니다</b> — 20년 창은 고점(2006)에서, 10년 창은 회복기에서 '
      f'시작해 연 {pct(rec["windows"]["20"]["eps_cagr_nominal"])}와 '
      f'{pct(rec["windows"]["10"]["eps_cagr_nominal"])}로 벌어집니다. 그래서 '
      f'성장률 가정은 30년 창을 기준으로 두고, 최근 10년은 가장 관대한 '
      f'가정으로 따로 둡니다.</p>')
    w(table(["지표", "값", "의미"],
            [["지금 P/E (보고 기준)", f'<b>{s["earnings"]["pe_now"]:.1f}</b>',
              ("지수 ÷ 12개월 EPS", "")],
             ["30년 P/E 중위", f'{p30["median"]:.1f}',
              ("지금은 30년 중 아래쪽 " + pct(p30["share_below_current"], 0)
               + "의 달보다 높음", "")],
             ["CAPE (10년 평균 실질이익)", (f'<b>{cape["current"]:.1f}</b>',
                                          "flag"),
              (f'1950년 이후 {pct(cape["share_below_current_since_1950"], 0)}'
               f', 최근 30년 {pct(cape["share_below_current_30y"], 0)}의 달보다 '
               f'높음', "")],
             ["ROE 중위 (1999~2025)", pct(rec["roe"]["median"]),
              (f'재투자 수익률로 씀. 최신 분기 {pct(rec["roe"]["latest"][1])}',
               "")],
             ["배당성향 중위 (30년)", pct(rec["payout_median_30y"], 0),
              ("자사주 매입 제외", "")]],
            align=["l", "r", "w"]))
    xc = s["crosschecks"]
    w(f'<p class="meta" style="border:0;padding:0">교차확인: multpl 의 EPS '
      f'(실질)를 같은 사이트의 CPI 로 명목으로 되돌린 값이 실러의 명목 EPS 와 '
      f'겹치는 {xc["eps_vs_shiller"]["months"]}개월 동안 중위 '
      f'{pct(xc["eps_vs_shiller"]["median_abs_rel"], 2)}, 최대 '
      f'{pct(abs(xc["eps_vs_shiller"]["worst"]["rel"]), 2)} 차이. 우리 CAPE 를 '
      f'실러의 마지막 값({esc(cape["seam"]["month"])})에 이으면 '
      f'{sg(cape["seam"]["rel"], 1)}.</p>')

    w("<h3>버핏 기준 판정 — 성장률 × 할인율</h3>")
    rows = []
    for g in s["grid"]:
        for c in g["cells"]:
            rows.append([
                esc(g["label"]), esc(dl[c["discount_key"]]),
                f'<b>{pts(c["value"])}</b>',
                (sg(c["upside_vs_level"], 0),
                 "pos" if c["upside_vs_level"] > 0 else "neg"),
                f'<b>{pts(c["buy_level"]["30%"])}</b>',
                sg(c["buy_vs_level"]["30%"], 0),
                (f'<b>{"합격" if c["pass"]["30%"] else "불합격"}</b>',
                 "over" if c["pass"]["30%"] else "under")])
    w(table(["성장률 가정", "할인율", "가치", "지금 대비", "매수선 (안전마진 30%)",
             "매수선 지금 대비", "판정"], rows,
            caption=f"지수 포인트 단위. 재투자 수익률 ROE "
                    f"{pct(s['incremental_return'])}. 판정 = 매수선이 지금 "
                    f"지수 {pts(s['level']['price'])}보다 높은가. '매수선 지금 "
                    f"대비' = 지수가 그 매수선까지 내려오려면 몇 % 빠져야 "
                    f"하는가. 초록·빨강은 판정에만 씁니다.",
            align=["w", "l", "r", "r", "r", "r", "r"]))

    w("<h3>적절한 매수 가격 — 안전마진 사다리</h3>")
    w(f'<p>버핏 기준 할인율 {pct(r30 + 0.03, 2)}에서, 성장률 가정마다 가치와 '
      f'안전마진별 매수선입니다. 막대의 진한 부분이 안전마진 30% 매수선까지, '
      f'옅은 부분이 가치까지, 세로선이 지금 지수입니다.</p>')
    w(ladder(s, "spx"))
    rows = []
    for g in s["grid"]:
        _, c = cell_of(s, g["key"], "bond30_plus3")
        rows.append([esc(g["label"])] + [
            (f'<b>{pts(c["buy_level"][k])}</b>' if k == "30%"
             else pts(c["buy_level"][k]),
             "over" if c["pass"][k] else "under") for k in MOS])
    w(table(["성장률 가정", "가치 (0%)", "20%", "30%", "40%"], rows,
            caption="안전마진별 매수선. 초록 = 지금 지수가 그 아래(합격), "
                    "빨강 = 지금 지수가 그 위(불합격)."))
    rows = []
    for z in s["roe_sensitivity"]:
        rows.append([esc(z["label"]), pct(z["roe"])] + [
            (pts(c["value"]), "over" if c["pass0"] else "under")
            for c in z["cells"]])
    w(table(["ROE 가정", "ROE"] + [g["label"].split(" ")[0] + " …"
                                   for g in s["grid"]], rows,
            caption="ROE 를 바꿔도 판정이 바뀌는가 — 버핏 기준 할인율, 안전마진 "
                    "0% 의 가치. 열은 위 표의 성장률 가정 순서와 같습니다. "
                    "ROE 를 상한 35% 까지 올리고 최근 10년 성장률을 써야 "
                    "겨우 지금 지수에 닿습니다."))

    w("<h3>거꾸로 — 지금 가격이 요구하는 것</h3>")
    rows = []
    for g in s["grid"]:
        ir = g["implied_return"]
        rows.append([esc(g["label"]), f'<b>{pct(ir, 2)}</b>',
                     (sg(ir - r30, 2), "flag")])
    w(table(["성장률 가정", "기대수익률", "30년 국채 대비"], rows,
            caption="기대수익률 = 가치가 지금 지수와 같아지는 할인율. 이 "
                    "칸은 '높을수록 좋다'입니다."))
    rows = []
    for dk in DISC:
        for mm in d["margins"]:
            r = req_of(s, dk, mm)
            lab = f"안전마진 {int(mm * 100)}%"
            if r["reachable"]:
                rows.append([esc(dl[dk]), lab, pct(r["growth_year1"]),
                             pct(r["nopat_cagr_10y"]),
                             f'상위 {pct(r["base_rate_percentile"])}'])
            else:
                rows.append([esc(dl[dk]), lab, ("없음", "flag"),
                             "—", (f'천장 {pts(r.get("ceiling_level"))}',
                                   "flag")])
    w(table(["할인율", "요구 조건", "1년차 성장률", "10년 평균", "기초율 위치"],
            rows,
            caption="요구 성장률은 <b>낮을수록 가격이 설명되기 쉽다</b>는 뜻이라 "
                    "다른 판정 칸과 방향이 반대입니다. '없음' = 성장률을 재투자 "
                    "수익률(ROE) 직전까지 올려도 닿지 못함 — 그 위는 자기 돈으로 "
                    "조달할 수 없는 성장입니다."))

    w("<h3>30년을 같은 잣대로 되짚으면</h3>")
    w(backtest_svg(bt))
    w(table(["구간", "개월 수", "뒤 10년 실질 총수익률 (중위)"],
            [["매수선(안전마진 30%) 아래", f'{bt["below_buy30"]["months"]}',
              pct(bt["below_buy30"]["fwd10_real_median"])],
             ["가치 아래", f'{bt["below_value"]["months"]}',
              pct(bt["below_value"]["fwd10_real_median"])],
             ["가치 위", f'{bt["above_value"]["months"]}',
              pct(bt["above_value"]["fwd10_real_median"])]],
            caption=f"{esc(bt['from'])}~{esc(bt['to'])} 의 "
                    f"{bt['months']}개월. 뒤 10년 수익률은 실러 자료가 있는 "
                    f"2014년 시작분까지만 셉니다(그래서 개월 수보다 적음). "
                    f"시작점이 겹치므로 독립 관측 수는 훨씬 적습니다."))
    runs = [r for r in bt["runs_below_value"] if r["months"] >= 6]
    w(f'<p>지금의 잣대로는 지난 30년 중 <b data-v="bt-months">'
      f'{bt["below_value"]["months"]}개월</b>이 가치 아래였고, 그중 '
      f'{bt["below_buy30"]["months"]}개월이 안전마진 30% 매수선 아래였습니다. '
      f'가장 긴 구간은 '
      + ", ".join(f'{r["from"]}~{r["to"]}({r["months"]}개월)' for r in runs)
      + '. 이 구간 대부분은 <b>금리가 낮았던 시기</b>입니다 — 국채 2~3%에 '
        '3%p 를 더한 할인율에서는 같은 이익이 훨씬 비싸게 평가됩니다. '
        '그리고 <b>2009년 바닥은 이 잣대로 매수 구간이 아니었습니다</b>. '
        '12개월 보고이익이 상각으로 거의 0이 되어 가치도 함께 꺼졌기 '
        '때문입니다 — 직전 12개월 이익만 보는 방식의 약점이고, CAPE 가 10년 '
        '평균을 쓰는 이유입니다.</p>')

    # ---- 2008~09년에 가치가 지수보다 크게 꺼진 이유
    by_bt = {r["month"]: r for r in bt["rows"]}
    e07, e09 = by_bt["2007-06"], by_bt["2009-03"]
    w(f'<p><b>2008~09년에 가치선이 지수보다 훨씬 깊게 꺼진 이유.</b> 이 '
      f'가치는 직전 12개월 보고이익에 비례합니다. S&amp;P 500 의 12개월 EPS 가 '
      f'2007년 6월 <b data-v="e07">{e07["eps"]:,.2f}</b>에서 2009년 3월 '
      f'<b data-v="e09">{e09["eps"]:,.2f}</b>로 '
      f'{sg(e09["eps"] / e07["eps"] - 1, 0)} 줄었고 — 금융사 손실과 대규모 '
      f'상각이 보고이익에 그대로 들어갔습니다 — 같은 기간 지수는 '
      f'{sg(e09["price"] / e07["price"] - 1, 0)}였습니다. 게다가 성장률 '
      f'가정(그 달까지의 30년 EPS 기록)도 끝점 이익이 무너지면서 '
      f'{pct(e07["own30"])}에서 <b data-v="g09">{pct(e09["own30"])}</b>로 '
      f'내려가 두 번 깎였습니다. 시장은 이익이 회복할 것을 보고 그만큼 '
      f'떨어지지 않았고, 실제로 EPS 는 2009년 말 다시 '
      f'{by_bt["2009-12"]["eps"]:,.2f}로 돌아왔습니다.</p>')

    b10 = s["backtest_fixed10"]
    w("<h3>할인율을 10%로 고정하면</h3>")
    w('<p>금리 수준과 무관하게 매달 같은 10%로 할인한 판입니다. 저금리 시기에 '
      '할인율이 낮아져 가치가 부풀던 효과를 걷어 냅니다.</p>')
    w(backtest_svg(b10, "fixed10", "10% 고정"))
    w(table(["구간 (10% 고정)", "개월 수", "뒤 10년 실질 총수익률 (중위)"],
            [["매수선(안전마진 30%) 아래", f'{b10["below_buy30"]["months"]}',
              pct(b10["below_buy30"]["fwd10_real_median"])],
             ["가치 아래", f'{b10["below_value"]["months"]}',
              pct(b10["below_value"]["fwd10_real_median"])],
             ["가치 위", f'{b10["above_value"]["months"]}',
              pct(b10["above_value"]["fwd10_real_median"])]],
            caption="'—' = 해당하는 달이 없음."))
    near10 = min((r for r in b10["rows"] if r["value_own30"]),
                 key=lambda r: r["price"] / r["value_own30"])
    if b10["below_value"]["months"] == 0:
        w(f'<p><b>10% 고정으로는 지난 30년 동안 S&amp;P 500 이 가치 아래로 '
          f'내려온 달이 <span data-v="b10-months">한 번도</span> '
          f'없었습니다.</b> 가장 가까웠던 때가 '
          f'<span data-v="b10-near">{esc(near10["month"])}</span>로, 지수 '
          f'{pts(near10["price"])}가 가치 {pts(near10["value_own30"])}보다 '
          f'{sg(near10["price"] / near10["value_own30"] - 1, 0)} 높았습니다. '
          f'그런데 그 30년 동안 아무 때나 산 사람의 뒤 10년 실질 수익률 중위는 '
          f'<b data-v="b10-fwd">{pct(b10["above_value"]["fwd10_real_median"])}'
          f'</b>였습니다. 즉 이 잣대를 10% 로 고정해 지켰다면 30년 내내 '
          f'시장 밖에 있었을 것입니다.</p>')
    else:
        w(f'<p>10% 고정으로는 가치 아래였던 달이 '
          f'<span data-v="b10-months">{b10["below_value"]["months"]}개월'
          f'</span>입니다.</p>')
    w(f'<p><b>이건 모형이 보수적이라는 신호입니다.</b> 가장 유력한 원인은 '
      f'재투자 수익률로 쓴 ROE {pct(s["incremental_return"])}입니다. 이 값이면 '
      f'연 {pct(rec["windows"]["30"]["eps_cagr_nominal"])} 성장에 이익의 '
      f'{pct(rec["windows"]["30"]["eps_cagr_nominal"] / s["incremental_return"], 0)}'
      f'를 재투자해야 한다고 계산되는데, 실제 S&amp;P 500 은 배당만으로 이익의 '
      f'{pct(rec["payout_median_30y"], 0)}(30년 중위)를 내주고도 그만큼 '
      f'성장했습니다. 자사주 매입은 자료가 없어 더하지 못했지만, 더하면 '
      f'실제 재투자는 모형의 가정보다 적었을 가능성이 큽니다 — 장부상 ROE 가 '
      f'새로 투자한 돈의 수익률을 낮게 잡는다는 뜻입니다. 그래서 이 보고서의 '
      f'"비싸다" 판정은 방향으로 읽고, 매수선 숫자 자체는 엄격한 쪽으로 '
      f'읽으십시오.</p>')

    w("<h3>70년 기록 — 시작 시점의 CAPE 와 뒤 10년</h3>")
    rows = [[f'{b["quintile"]}분위', f'{b["cape_from"]:.1f} ~ {b["cape_to"]:.1f}',
             f'{b["months"]}', f'<b>{pct(b["fwd10_real_median"])}</b>',
             f'{pct(b["fwd10_real_min"])} ~ {pct(b["fwd10_real_max"])}',
             pct(b["share_negative"], 0)] for b in fw["buckets"]]
    w(table(["CAPE 5분위", "CAPE 범위", "개월", "뒤 10년 실질 (중위)", "범위",
             "손실 비율"], rows,
            caption=f"실러 자료, {esc(fw['from'])}~{esc(fw['to'])} 시작. "
                    f"실질 총수익률(배당 재투자). 모형 없이 기록만으로 센 "
                    f"것입니다."))
    c30 = fw["cape_30_plus"]
    w(f'<p>지금 CAPE {cape["current"]:.1f}는 5분위(가장 비싼 구간)의 위쪽입니다. '
      f'CAPE 가 30을 넘었던 달에서 시작한 뒤 10년 실질 수익률은 중위 '
      f'<b data-v="cape30">{pct(c30["fwd10_real_median"])}</b>, 가장 좋았던 '
      f'경우도 {pct(c30["fwd10_real_max"])}였습니다 — 다만 그 표본은 '
      f'{", ".join(c30["periods"])}년 한 번의 거품뿐이라 일반화하기에는 '
      f'얇습니다.</p>')

    # =========================================================== 나스닥100
    w("<h2>나스닥100</h2>")
    w("<h3>이익을 어떻게 만들었나</h3>")
    w(f'<p>나스닥100 의 지수 단위 이익은 무료로 공표되지 않습니다. 그래서 '
      f'구성종목 {agg["constituents"]}개(알파벳 두 종목은 하나로)의 12개월 '
      f'이익을 <b>SEC 공시에서 직접</b> 모아 '
      f'<code>지수 P/E = Σ시가총액 ÷ Σ이익</code>으로 만들었습니다. 시가총액 '
      f'가중 지수에서는 이것이 정의입니다. 나스닥100 은 상위 종목 비중을 깎는 '
      f'수정 가중이라 그만큼 다를 수 있습니다.</p>')
    w(table(["지표", "값", "비고"],
            [["P/NOPAT (기본)", f'<b>{agg["pe_nopat"]:.1f}</b>',
              ("영업이익 × (1 − 세율)의 합", "")],
             ["P/E (순이익)", f'{agg["pe_net_income"]:.1f}',
              ("보유 지분 평가이익이 섞여 낮게 나옴", "")],
             ["iShares 공표 P/E (CNDX)", f'{n["ishares"]["pe"]:.1f}',
              (f'{esc(n["ishares"]["as_of"])} · 보유종목 P/E 가중평균이라 '
               f'방식이 다름', "")],
             ["순이익 − NOPAT", f'{agg["mtm_gap_total"] / BN:,.0f}십억 달러',
              ("대부분 평가이익 (아래 표)", "flag")],
             ["ROE (NOPAT ÷ 자기자본)", pct(agg["roe_nopat"]),
              ("재투자 수익률로 씀", "")],
             ["상위 10개 비중", pct(agg["top10_weight"], 0),
              ("시가총액 기준", "")]],
            align=["l", "r", "w"]))
    rows = [[esc(g["symbol"]), f'{g["net_income"] / BN:,.1f}',
             f'{g["nopat"] / BN:,.1f}',
             (f'{g["gap"] / BN:+,.1f}', "pos" if g["gap"] > 0 else "neg")]
            for g in agg["largest_mtm_gaps"]]
    w(table(["종목", "순이익", "NOPAT", "차이"], rows,
            caption="단위 십억 달러, 12개월. 알파벳·아마존의 순이익에는 보유 "
                    "지분의 평가이익이 크게 들어 있습니다 — 이 프로젝트가 "
                    "영업이익에서 출발하는 이유이고, 같은 종목이 S&amp;P 500 "
                    "의 보고 기준 EPS 에도 들어 있습니다."))
    rows = [[esc(t["symbol"]), pct(t["weight"], 1),
             f'{t["market_cap"] / 1e12:,.2f}',
             (f'{t["pe_nopat"]:.1f}' if t["pe_nopat"] else "적자",
              "" if t["pe_nopat"] else "neg"),
             esc(t["method"])] for t in agg["top"][:12]]
    w(table(["종목", "비중", "시가총액 (조$)", "P/NOPAT", "이익 기간"], rows,
            caption="연율화 = 상장한 지 1년이 안 돼 연속 분기가 넷이 안 되는 "
                    "종목(스페이스X 등) — 있는 분기를 연율화했습니다."))
    w(f'<p class="meta" style="border:0;padding:0">검산에서 바로잡은 것: '
      f'샌디스크가 2026-11-20 에 8:1 로 분할해 공시 주식수(분할 전) × 시세(분할 '
      f'후)로 시가총액이 8분의 1로 나왔던 것, 종류주식이 여럿인 회사(알파벳·'
      f'메타·컴캐스트 …)의 표지 주식수가 비거나 2009년 값이 남아 있던 것, '
      f'몇 년 전에 쓰지 않게 된 순이익 태그를 집었던 것(브로드컴·부킹). '
      f'외화 보고 기업 {len(agg["foreign_currency"])}곳은 Yahoo 환율로, ADS 는 '
      f'20-F 원문에서 확인한 비율로 환산했습니다.</p>')

    w("<h3>30년 가격 기록</h3>")
    pr = n["price_record"]
    w(table(["기간", "출발 → 지금", "지수 연평균"],
            [[f"{k}년", f'{pts(pr[k]["from_level"])} → {pts(pr[k]["to_level"])}',
              pct(pr[k]["cagr"], 2)] for k in ("10", "20", "30")],
            caption=f'월말 종가. 30년 최대 낙폭 '
                    f'{pct(pr["max_drawdown_30y"]["drawdown"], 0)} '
                    f'({esc(pr["max_drawdown_30y"]["peak"])} 고점 → '
                    f'{esc(pr["max_drawdown_30y"]["trough"])} 바닥).'))
    w('<p><b>나스닥100 에는 30년 이익 기록이 없습니다.</b> 가격 기록은 30년이 '
      '있지만 가격 상승률은 이익 성장과 밸류에이션 변화가 섞인 값입니다. '
      '그래서 성장률 가정의 "자기 기록" 자리에 미국 대형주 참조군인 '
      'S&amp;P 500 의 30년 EPS 기록을 쓰고, 가장 관대한 가정 하나만 나스닥100 의 '
      '10년 가격 상승률로 두었습니다.</p>')

    w("<h3>버핏 기준 판정 — 성장률 × 할인율</h3>")
    rows = []
    for g in n["grid"]:
        for c in g["cells"]:
            rows.append([
                esc(g["label"]), esc(dl[c["discount_key"]]),
                f'<b>{pts(c["value"])}</b>',
                (sg(c["upside_vs_level"], 0),
                 "pos" if c["upside_vs_level"] > 0 else "neg"),
                f'<b>{pts(c["buy_level"]["30%"])}</b>',
                sg(c["buy_vs_level"]["30%"], 0),
                (f'<b>{"합격" if c["pass"]["30%"] else "불합격"}</b>',
                 "over" if c["pass"]["30%"] else "under")])
    w(table(["성장률 가정", "할인율", "가치", "지금 대비", "매수선 (안전마진 30%)",
             "매수선 지금 대비", "판정"], rows,
            caption=f"지수 포인트 단위. 1포인트당 NOPAT "
                    f"{n['earnings']['per_point_nopat']:,.1f}, 재투자 수익률 "
                    f"{pct(n['incremental_return'])}.",
            align=["w", "l", "r", "r", "r", "r", "r"]))
    w("<h3>적절한 매수 가격 — 안전마진 사다리</h3>")
    w(ladder(n, "ndx"))
    rows = []
    for g in n["grid"]:
        _, c = cell_of(n, g["key"], "bond30_plus3")
        rows.append([esc(g["label"])] + [
            (f'<b>{pts(c["buy_level"][k])}</b>' if k == "30%"
             else pts(c["buy_level"][k]),
             "over" if c["pass"][k] else "under") for k in MOS])
    w(table(["성장률 가정", "가치 (0%)", "20%", "30%", "40%"], rows,
            caption=f"버핏 기준 할인율 {pct(r30 + 0.03, 2)}."))
    rows = []
    for g in n["grid"]:
        ir = g["implied_return"]
        rows.append([esc(g["label"]), f'<b>{pct(ir, 2)}</b>',
                     (sg(ir - r30, 2), "flag")])
    w(table(["성장률 가정", "기대수익률", "30년 국채 대비"], rows))
    rows = []
    for dk in DISC:
        for mm in d["margins"]:
            r = req_of(n, dk, mm)
            lab = f"안전마진 {int(mm * 100)}%"
            if r["reachable"]:
                rows.append([esc(dl[dk]), lab, pct(r["growth_year1"]),
                             pct(r["nopat_cagr_10y"]),
                             f'상위 {pct(r["base_rate_percentile"])}'])
            else:
                rows.append([esc(dl[dk]), lab, ("없음", "flag"), "—",
                             (f'천장 {pts(r.get("ceiling_level"))}', "flag")])
    w(table(["할인율", "요구 조건", "1년차 성장률", "10년 평균", "기초율 위치"],
            rows, caption="방향 주의: 요구 성장률은 낮을수록 좋습니다."))
    rows = []
    for g, c in zip(n["grid_net_income"], n["grid"]):
        a = next(x for x in g["cells"] if x["discount_key"] == "bond30_plus3")
        b = next(x for x in c["cells"] if x["discount_key"] == "bond30_plus3")
        rows.append([esc(g["label"]), pts(b["value"]), pts(a["value"]),
                     ("합격" if a["pass"]["0%"] else "불합격",
                      "over" if a["pass"]["0%"] else "under")])
    w(table(["성장률 가정", "가치 (NOPAT)", "가치 (순이익)",
             "순이익으로도 안전마진 0% 판정"], rows,
            caption="평가이익이 섞인 순이익을 분자로 써도 판정이 바뀌는지. "
                    "순이익 쪽 재투자 수익률은 순이익 ÷ 자기자본."))

    # ======================================================== 버핏의 처방
    w("<h2>버핏이 지수에 대해 직접 한 말</h2>")
    for key in ("space_out", "exuberance", "will"):
        p = bp[key]
        w(f'<h3>{esc(p["title"])}</h3>')
        w(f'<blockquote data-bq="{key}">')
        for q in p["quotes"]:
            w(f"<p>&ldquo;{esc(q)}&rdquo;</p>")
        w(f'<span class="src"><a href="{esc(p["source_url"])}">'
          f'{p["year"]}년 주주서한</a> · 원문 대조 {p["verified"]}문장'
          f'</span></blockquote>')
        w(f'<p>{esc(p["why"])}</p>')

    # ============================================================ 결론
    w("<h2>결론</h2>")
    w("<ol>")
    w(f'<li><b>S&amp;P 500 의 버핏 기준 매수선(안전마진 30%)은 '
      f'{pts(s_b_lo)}~{pts(s_b_hi)}</b>입니다. 30년 EPS 기록(연 '
      f'{pct(rec["windows"]["30"]["eps_cagr_nominal"], 2)})이 이어진다고 '
      f'보면 가치 {pts(s_own["value"])}, 매수선 '
      f'{pts(s_own["buy_level"]["30%"])}. 지금 {pts(s["level"]["price"])}는 '
      f'그 가치보다 {sg(s["level"]["price"] / s_own["value"] - 1, 0)} '
      f'높습니다.</li>')
    w(f'<li><b>나스닥100 의 매수선은 {pts(n_b_lo)}~{pts(n_b_hi)}</b>입니다. '
      f'가장 관대한 가정(10년 가격 상승률 연 {pct(p10_of(n), 1)} 지속)에서도 '
      f'가치는 {pts(n_hi)}로 지금 {pts(n["level"]["price"])}보다 낮습니다.</li>')
    w(f'<li><b>판정을 가르는 것은 할인율입니다.</b> 국채 + 3%p 를 받아들이면 두 '
      f'지수 모두 비싸고, 순수 국채({pct(r30, 2)})로 할인하면 둘 다 싸 '
      f'보입니다. 지금 가격이 약속하는 수익률은 국채보다 1~3%p 높을 '
      f'뿐입니다.</li>')
    w(f'<li><b>지난 30년의 기록은 이 잣대를 지지합니다.</b> 가치 아래에서 산 '
      f'달의 뒤 10년 실질 수익률 중위는 '
      f'{pct(bt["below_value"]["fwd10_real_median"])}, 가치 위에서 산 달은 '
      f'{pct(bt["above_value"]["fwd10_real_median"])}였습니다. CAPE 5분위에서 '
      f'시작한 10년은 중위 {pct(fw["buckets"][-1]["fwd10_real_median"])}.</li>')
    w('<li><b>그래도 버핏의 처방은 "기다려라"가 아니라 "나눠 사라"입니다.</b> '
      '지수를 사려는 사람이 이 매수선까지 기다리면 몇 년, 혹은 다시 오지 '
      '않을 수 있습니다(위 그래프에서 매수선 아래였던 기간은 대부분 저금리 '
      '시기였습니다). 이 보고서가 말할 수 있는 것은 <b>지금은 버핏이 경고한 '
      '"들뜬 시점"에 가깝다</b>는 것이고, 그렇다면 한 번에 사지 말고 오래 '
      '나눠 사라는 것이 그의 문장이 가리키는 방향입니다.</li>')
    w("</ol>")

    # ============================================================ 한계
    w("<h2>이 분석의 한계</h2>")
    w("<ul>")
    for x in (
        f"<b>S&amp;P 500 의 이익은 {esc(s['earnings']['as_of'])} 까지입니다.</b> "
        "3분기 보고 기준 EPS 는 아직 multpl 에 실리지 않았고, S&amp;P 원본 "
        "스프레드시트는 이 환경에서 403 으로 막힙니다.",
        "<b>보고 기준 EPS 에는 2018년 이후 보유 지분 평가손익이 들어갑니다</b> "
        "(회계기준 변경). 그래서 최근 이익은 30년 전과 정의가 조금 다르고, "
        "알파벳·아마존 같은 평가이익이 지금의 EPS 를 높입니다 — 이 보고서의 "
        "S&amp;P 500 가치는 그만큼 후한 쪽입니다.",
        "<b>나스닥100 은 구성종목을 시가총액으로 가중했습니다.</b> 지수의 실제 "
        "수정 가중과 다르고, 외국 발행인 6곳은 연간 이익, 상장 1년 미만 2곳은 "
        "연율화 이익입니다.",
        "<b>기대인플레이션은 FRED 가 이 환경에서 닿지 않아 "
        f"{esc(bei['as_of'])} 값({pct(bei['rate'], 2)})을 그대로 썼습니다.</b> "
        "영구성장률과 기초율 명목 환산에 들어갑니다.",
        "<b>백테스트의 ROE 와 영구성장률은 고정값입니다.</b> 그때의 판단이 "
        "아니라 지금의 잣대를 그때에 댄 것입니다.",
        "<b>국채 + 3%p 는 해석입니다.</b> 1994년 발언에서 읽은 스프레드이고 "
        "버핏이 정한 규칙이 아닙니다. 2007년 그는 형식적인 할인율이 없다고 "
        "말했습니다.",
    ):
        w(f"<li>{x}</li>")
    w("</ul>")
    w('<footer class="page">')
    w(f'출처: <a href="https://www.multpl.com/s-p-500-earnings">multpl</a> '
      f'(S&amp;P 다우존스 공표치) · <a href="{esc(d["sources"]["shiller"])}">'
      f'실러 ie_data</a> · <a href="{esc(d["sources"]["ndx_members"])}">나스닥 '
      f'구성종목</a> · SEC EDGAR companyfacts · '
      f'<a href="{esc(d["sources"]["ishares_ndx"])}">iShares</a> · Yahoo '
      f'Finance · <a href="{esc(d["base_rates"]["source_url"])}">Base Rate '
      f'Book</a> · <a href="https://www.berkshirehathaway.com/letters/">버크셔 '
      f'주주서한</a>.<br>자료 기준일 {esc(d["generated"])}. 재현: '
      f'<code>bash work/run_index.sh</code>.<br>투자 판단은 읽는 분의 '
      f'몫입니다.')
    w("</footer>")
    w("</div>")
    return "\n".join(o)


def p10_of(n):
    return next(g for g in n["grid"] if g["key"] == "recent_10y")["growth"]


# ------------------------------------------------------------------- 검증
def tables_of(page):
    out = []
    for m in re.finditer(r"<table>(.*?)</table>", page, re.S):
        blob = m.group(1)
        heads = [html.unescape(re.sub(r"<[^>]+>", "", h)).strip()
                 for h in re.findall(r"<th[^>]*>(.*?)</th>", blob, re.S)]
        rows = [[html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
                 for t in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
                for tr in re.findall(r"<tr>(.*?)</tr>", blob, re.S)]
        out.append((heads, [r for r in rows if r]))
    return out


def section(page, start, end):
    a = page.find(start)
    if a < 0:
        raise SystemExit(f"구획 특정 실패: {start}")
    b = page.find(end, a + len(start))
    return page[a:b if b > 0 else len(page)]


def verify(page, d):
    s, n = d["spx"], d["ndx"]
    r30 = d["macro"]["treasury_30y"]["rate"]
    dl = {x["key"]: x["label"] for x in d["discounts"]}
    fails, passed = [], 0

    def eq(name, got, want):
        nonlocal passed
        if got == want:
            passed += 1
            return True
        fails.append(f"{name}: 페이지 {got!r} != 엔진 {want!r}")
        return False

    def true(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            return True
        fails.append(f"{name}: 거짓 {detail}")
        return False

    def near(name, got, want, tol):
        nonlocal passed
        if got is not None and abs(got - want) <= tol:
            passed += 1
            return True
        fails.append(f"{name}: 페이지 {got} vs 엔진 {want:.4f}")
        return False

    def v_of(key):
        m = re.search(rf'data-v="{re.escape(key)}"[^>]*>(.*?)</', page, re.S)
        return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() \
            if m else None

    # ------------------------------------------------------- 페이지 요건
    true("타이틀", "<title>" in page[:8192])
    m = re.search(r"<title>(.*?)</title>", page)
    true("타이틀 2~4 단어", bool(m) and 2 <= len(m.group(1).split()) <= 4,
         m.group(1) if m else "")
    true("doctype·html·head·body 없음",
         not re.search(r"<(?:!doctype|html|head|body)\b", page, re.I))
    true("viewport-fit", "claude:viewport-fit-sides" in page)
    flat = page.replace(" ", "")
    true("좌측 거터", "max(16px,env(safe-area-inset-left,0px))" in flat)
    true("우측 거터", "max(16px,env(safe-area-inset-right,0px))" in flat)
    true("keep-all", "word-break:keep-all" in flat)
    bare = re.search(r"^:root\{(.*?)\}", page, re.S | re.M)
    for tk in ("--bg", "--fg", "--accent", "--over", "--under", "--pos",
               "--neg", "--flag", "--buy", "--val", "--now", "--zone"):
        true(f"토큰 {tk} 맨 :root", bool(bare) and f"{tk}:" in bare.group(1))
    for g in (':root:not([data-theme="light"])', ':root[data-theme="dark"]'):
        true(f"다크 가드 {g[:24]}", g in page)
    true("다크 color-scheme", page.count("color-scheme:dark") >= 2)
    true("body 배경 토큰", "background:var(--bg)" in flat)
    true("표가 스크롤 안",
         page.count('<div class="scroll">') == page.count("<table>"))
    for host in set(re.findall(r'(?:src|href)="https?://([^/"]+)', page)):
        true(f"허용 호스트 {host}", host in (
            "fonts.googleapis.com", "www.multpl.com", "img1.wsimg.com",
            "indexes.nasdaqomx.com", "www.ishares.com", "sorfis.com",
            "www.berkshirehathaway.com"), host)

    # --------------------------------------------------------- 카드·본문
    for key, X in (("spx", s), ("ndx", n)):
        vals = [cell_of(X, g["key"], "bond30_plus3")[1] for g in X["grid"]]
        lo, hi = min(c["value"] for c in vals), max(c["value"] for c in vals)
        blo = min(c["buy_level"]["30%"] for c in vals)
        bhi = max(c["buy_level"]["30%"] for c in vals)
        irs = [g["implied_return"] for g in X["grid"]]
        eq(f"카드 {key} 지수", v_of(f"{key}-level"), pts(X["level"]["price"]))
        eq(f"카드 {key} 배수", v_of(f"{key}-pe"),
           f'{X["earnings"]["pe_now"]:.1f}')
        eq(f"카드 {key} 가치", v_of(f"{key}-value"), f"{pts(lo)} ~ {pts(hi)}")
        eq(f"카드 {key} 매수선", v_of(f"{key}-buy"),
           f"{pts(blo)} ~ {pts(bhi)}")
        eq(f"카드 {key} 기대수익률", v_of(f"{key}-ir"), rng(irs))
        ra = [g["returns_at"] for g in X["grid"]]
        eq(f"카드 {key} 가치에 사면", v_of(f"{key}-ir-value"),
           rng([x["value"] for x in ra]))
        eq(f"카드 {key} 매수선에 사면", v_of(f"{key}-ir-buy"),
           rng([x["buy30"] for x in ra]))
        eq(f"판정 {key} 가치", v_of(f"v-{key}"), f"{pts(lo)}~{pts(hi)}")
        eq(f"판정 {key} 매수선", v_of(f"b-{key}"), f"{pts(blo)}~{pts(bhi)}")
        eq(f"판정 {key} 기대수익률", v_of(f"ir-{key}"),
           f"{pct(min(irs))}~{pct(max(irs))}")
    eq("판정 S&P 천장", v_of("ceil-spx"),
       pts(req_of(s, "bond30_plus3", 0.0).get("ceiling_level")))
    eq("판정 나스닥 요구 성장률", v_of("rq-ndx"),
       pct(req_of(n, "bond30_plus3", 0.0).get("growth_year1")))
    eq("판정 CAPE", v_of("cape"), f'{s["cape"]["current"]:.1f}')
    eq("판정 CAPE 백분위", v_of("cape-pct"),
       pct(s["cape"]["share_below_current_since_1950"], 0))
    eq("본문 30년 EPS", v_of("eps30"),
       pct(s["record"]["windows"]["30"]["eps_cagr_nominal"], 2))
    eq("본문 백테스트 개월", v_of("bt-months"),
       f'{s["backtest"]["below_value"]["months"]}개월')
    eq("본문 CAPE30+ 수익률", v_of("cape30"),
       pct(s["forward_returns"]["cape_30_plus"]["fwd10_real_median"]))

    # ------------------------------------------------------------ 격자 표
    T = tables_of(page)
    grids = [t for t in T if t[0][:2] == ["성장률 가정", "할인율"]]
    eq("격자 표 수", len(grids), 2)
    for (heads, rows), X, tag in zip(grids, (s, n), ("S&P", "나스닥")):
        eq(f"{tag} 격자 행 수", len(rows), 16)
        for g in X["grid"]:
            for c in g["cells"]:
                hit = [r for r in rows if r[0] == g["label"]
                       and r[1] == dl[c["discount_key"]]]
                if not true(f"{tag} 격자 행 {g['key']}/{c['discount_key']}",
                            len(hit) == 1):
                    continue
                r = hit[0]
                eq(f"{tag} {g['key']}/{c['discount_key']} 가치", r[2],
                   pts(c["value"]))
                eq(f"{tag} {g['key']}/{c['discount_key']} 지금 대비", r[3],
                   sg(c["upside_vs_level"], 0))
                eq(f"{tag} {g['key']}/{c['discount_key']} 매수선", r[4],
                   pts(c["buy_level"]["30%"]))
                eq(f"{tag} {g['key']}/{c['discount_key']} 매수선 지금 대비",
                   r[5], sg(c["buy_vs_level"]["30%"], 0))
                eq(f"{tag} {g['key']}/{c['discount_key']} 판정", r[6],
                   "합격" if c["pass"]["30%"] else "불합격")
    bad = [m_.group(0) for m_ in re.finditer(
        r'data-state="(over|under)"><b>(합격|불합격)</b>', page)
        if (m_.group(1) == "over") != (m_.group(2) == "합격")]
    true("판정 색 = 판정", not bad, str(bad[:2]))

    # ------------------------------------------------------- 사다리 표
    ladders = [t for t in T if t[0] == ["성장률 가정", "가치 (0%)", "20%",
                                        "30%", "40%"]]
    eq("사다리 표 수", len(ladders), 2)
    for (heads, rows), X, tag in zip(ladders, (s, n), ("S&P", "나스닥")):
        for g in X["grid"]:
            _, c = cell_of(X, g["key"], "bond30_plus3")
            hit = [r for r in rows if r[0] == g["label"]]
            if not true(f"{tag} 사다리 행 {g['key']}", len(hit) == 1):
                continue
            for i, k in enumerate(MOS, 1):
                eq(f"{tag} 사다리 {g['key']} {k}", hit[0][i],
                   pts(c["buy_level"][k]))

    # -------------------------------------------- 범위 막대 (길이 = 값)
    bars = dict(re.findall(r'data-bar="([\w-]+)" style="width:([\d.]+)%',
                           page))
    lefts = re.findall(r'data-bar="(\w+)-now" style="left:([\d.]+)%', page)
    for X, prefix in ((s, "spx"), (n, "ndx")):
        m_ = re.search(rf'data-g="{prefix}-base_rate_median".*?', page)
        axis_m = re.findall(r'<div class="ladder" data-axis="([\d.]+)"', page)
        axis = float(axis_m[0 if prefix == "spx" else 1])
        for g in X["grid"]:
            _, c = cell_of(X, g["key"], "bond30_plus3")
            kb = f'{prefix}-{g["key"]}-buy30'
            kv = f'{prefix}-{g["key"]}-value'
            if true(f"막대 {kb}", kb in bars):
                near(f"막대 {kb} 길이", float(bars[kb]) / 100 * axis,
                     c["buy_level"]["30%"], axis * 0.0001)
            if true(f"막대 {kv}", kv in bars):
                near(f"막대 {kv} 길이", float(bars[kv]) / 100 * axis,
                     c["value"] - c["buy_level"]["30%"], axis * 0.0001)
        nows = [float(v) for k, v in lefts if k == prefix]
        true(f"막대 {prefix} 현재선 4개", len(nows) == 4)
        for x in nows:
            near(f"막대 {prefix} 현재선 위치", x / 100 * axis,
                 X["level"]["price"], axis * 0.0001)

    # -------------------------------------------- 30년 선 그래프 (좌표 = 값)
    # 할인율만 다른 그래프가 둘이라 표식으로 먼저 특정합니다 — 페이지 전체에서
    # 첫 그래프를 집으면 둘째 그래프가 틀려도 통과합니다.
    for ckey, btk in (("bond", "backtest"), ("fixed10", "backtest_fixed10")):
        btc = s[btk]
        rows_bt = [r for r in btc["rows"] if r["value_own30"]]
        mfig = re.search(rf'<figure class="chart" data-chart="{ckey}">'
                         r'(.*?)</figure>', page, re.S)
        if not true(f"그래프 {ckey} 존재", bool(mfig)):
            continue
        fig = mfig.group(1)
        msv = re.search(r'data-n="(\d+)" data-lo="([-\d.]+)" '
                        r'data-hi="([-\d.]+)"', fig)
        if not true(f"그래프 {ckey} 축 정보", bool(msv)):
            continue
        nn, lo, hi = int(msv.group(1)), float(msv.group(2)), \
            float(msv.group(3))
        eq(f"그래프 {ckey} 점 수", nn, len(rows_bt))
        H, T_, B = 300, 12, 28
        for key, line in (("price", "price"), ("value", "value_own30"),
                          ("buy30", "buy30_own30")):
            mm = re.search(rf'data-line="{key}" points="([^"]+)"', fig)
            if not true(f"그래프 {ckey} 선 {key}", bool(mm)):
                continue
            ptsl = [tuple(map(float, p.split(",")))
                    for p in mm.group(1).split()]
            eq(f"그래프 {ckey} 선 {key} 점 수", len(ptsl), len(rows_bt))
            for i in range(0, len(rows_bt), 40):
                want = T_ + (H - T_ - B) * (1 - (math.log(rows_bt[i][line])
                                                 - lo) / (hi - lo))
                near(f"그래프 {ckey} {key} {rows_bt[i]['month']} 높이",
                     ptsl[i][1], want, 0.06)
        eq(f"그래프 {ckey} 매수선 아래 음영 수", fig.count('class="zone"/>'),
           sum(1 for r in rows_bt if r["below_buy30"]))
        disc = "10% 고정" if ckey == "fixed10" else "30년 국채+3%p"
        true(f"그래프 {ckey} 캡션의 할인율", f"할인율 {disc}" in fig)

    bt = s["backtest"]

    # 2008~09 설명 문단의 숫자
    by_bt = {r["month"]: r for r in s["backtest"]["rows"]}
    eq("본문 2007-06 EPS", v_of("e07"), f'{by_bt["2007-06"]["eps"]:,.2f}')
    eq("본문 2009-03 EPS", v_of("e09"), f'{by_bt["2009-03"]["eps"]:,.2f}')
    eq("본문 2009-03 성장률 가정", v_of("g09"), pct(by_bt["2009-03"]["own30"]))
    b10 = s["backtest_fixed10"]
    true("10% 고정판 할인율이 전부 10%",
         all(abs(r["discount"] - 0.10) < 1e-12 for r in b10["rows"]))
    if b10["below_value"]["months"] == 0:
        eq("본문 10% 고정 개월", v_of("b10-months"), "한 번도")
        near10 = min((r for r in b10["rows"] if r["value_own30"]),
                     key=lambda r: r["price"] / r["value_own30"])
        eq("본문 10% 고정 최근접 달", v_of("b10-near"), near10["month"])
        eq("본문 10% 고정 수익률", v_of("b10-fwd"),
           pct(b10["above_value"]["fwd10_real_median"]))
    bt10t = [t for t in T if t[0][:1] == ["구간 (10% 고정)"]]
    if true("10% 고정 표", len(bt10t) == 1):
        for lab, key in (("매수선(안전마진 30%) 아래", "below_buy30"),
                         ("가치 아래", "below_value"),
                         ("가치 위", "above_value")):
            hit = [r for r in bt10t[0][1] if r[0] == lab]
            if true(f"10% 고정 행 {lab}", len(hit) == 1):
                eq(f"10% 고정 {lab} 개월", hit[0][1], f'{b10[key]["months"]}')
    true("모형이 보수적이라는 단서", "모형이 보수적이라는 신호" in page)

    # ---------------------------------------------- 기대수익률·요구 성장률
    irt = [t for t in T if t[0][:2] == ["성장률 가정", "기대수익률"]]
    eq("기대수익률 표 수", len(irt), 2)
    for (heads, rows), X, tag in zip(irt, (s, n), ("S&P", "나스닥")):
        for g in X["grid"]:
            hit = [r for r in rows if r[0] == g["label"]]
            if true(f"{tag} 기대수익률 행 {g['key']}", len(hit) == 1):
                eq(f"{tag} 기대수익률 {g['key']}", hit[0][1],
                   pct(g["implied_return"], 2))
                eq(f"{tag} 국채 대비 {g['key']}", hit[0][2],
                   sg(g["implied_return"] - r30, 2))
    rqt = [t for t in T if t[0][:2] == ["할인율", "요구 조건"]]
    eq("요구 성장률 표 수", len(rqt), 2)
    for (heads, rows), X, tag in zip(rqt, (s, n), ("S&P", "나스닥")):
        eq(f"{tag} 요구 성장률 행 수", len(rows), 16)
        for r in X["required"]:
            lab = f"안전마진 {int(r['margin'] * 100)}%"
            hit = [x for x in rows if x[0] == dl[r["discount_key"]]
                   and x[1] == lab]
            if not true(f"{tag} 요구 행 {r['discount_key']}/{lab}",
                        len(hit) == 1):
                continue
            if r["reachable"]:
                eq(f"{tag} 요구 {r['discount_key']}/{lab} 1년차", hit[0][2],
                   pct(r["growth_year1"]))
                eq(f"{tag} 요구 {r['discount_key']}/{lab} 10년", hit[0][3],
                   pct(r["nopat_cagr_10y"]))
            else:
                eq(f"{tag} 요구 {r['discount_key']}/{lab} 없음", hit[0][2],
                   "없음")
                eq(f"{tag} 요구 {r['discount_key']}/{lab} 천장", hit[0][4],
                   f'천장 {pts(r.get("ceiling_level"))}')
    true("요구 성장률 방향이 반대임을 명시", "방향이 반대" in page)

    # ----------------------------------------------------- 30년 기록 표
    rt = [t for t in T if t[0][:2] == ["기간", "이익 창"]]
    if true("S&P 30년 기록 표", len(rt) == 1):
        for k in ("10", "20", "30"):
            hit = [r for r in rt[0][1] if r[0] == f"{k}년"]
            w_ = s["record"]["windows"][k]
            if true(f"S&P {k}년 행", len(hit) == 1):
                eq(f"S&P {k}년 명목", hit[0][2], pct(w_["eps_cagr_nominal"], 2))
                eq(f"S&P {k}년 실질", hit[0][3], pct(w_["eps_cagr_real"], 2))
                eq(f"S&P {k}년 지수", hit[0][4],
                   pct(s["record"]["price"][k]["cagr"], 2))

    # ------------------------------------------------------ 백테스트 표
    btt = [t for t in T if t[0][:2] == ["구간", "개월 수"]]
    if true("백테스트 표", len(btt) == 1):
        for lab, key in (("매수선(안전마진 30%) 아래", "below_buy30"),
                         ("가치 아래", "below_value"),
                         ("가치 위", "above_value")):
            hit = [r for r in btt[0][1] if r[0] == lab]
            if true(f"백테스트 행 {lab}", len(hit) == 1):
                eq(f"백테스트 {lab} 개월", hit[0][1], f'{bt[key]["months"]}')
                eq(f"백테스트 {lab} 수익률", hit[0][2],
                   pct(bt[key]["fwd10_real_median"]))

    # -------------------------------------------------- CAPE 5분위 표
    ct = [t for t in T if t[0][:2] == ["CAPE 5분위", "CAPE 범위"]]
    if true("CAPE 표", len(ct) == 1):
        for b in s["forward_returns"]["buckets"]:
            hit = [r for r in ct[0][1] if r[0] == f'{b["quintile"]}분위']
            if true(f"CAPE {b['quintile']}분위 행", len(hit) == 1):
                eq(f"CAPE {b['quintile']}분위 중위", hit[0][3],
                   pct(b["fwd10_real_median"]))

    # ------------------------------------------------ 나스닥 집계·평가이익
    agg = n["aggregate"]
    at = [t for t in T if t[0] == ["지표", "값", "비고"]]
    if true("나스닥 집계 표", len(at) == 1):
        rows = {r[0]: r for r in at[0][1]}
        eq("나스닥 P/NOPAT", rows.get("P/NOPAT (기본)", [None, None])[1],
           f'{agg["pe_nopat"]:.1f}')
        eq("나스닥 P/E(순이익)", rows.get("P/E (순이익)", [None, None])[1],
           f'{agg["pe_net_income"]:.1f}')
        eq("나스닥 iShares", rows.get("iShares 공표 P/E (CNDX)",
                                      [None, None])[1],
           f'{n["ishares"]["pe"]:.1f}')
    gt = [t for t in T if t[0] == ["종목", "순이익", "NOPAT", "차이"]]
    if true("평가이익 표", len(gt) == 1):
        for g in agg["largest_mtm_gaps"]:
            hit = [r for r in gt[0][1] if r[0] == g["symbol"]]
            if true(f"평가이익 행 {g['symbol']}", len(hit) == 1):
                eq(f"평가이익 {g['symbol']} 차이", hit[0][3],
                   f'{g["gap"] / BN:+,.1f}')

    # ------------------------------------------------------- 인용문 전문
    for p in d["index_passages"]:
        mm = re.search(rf'<blockquote data-bq="{p["key"]}">(.*?)</blockquote>',
                       page, re.S)
        if not true(f"버핏 블록 {p['key']}", bool(mm)):
            continue
        got = [html.unescape(re.sub(r"<[^>]+>", "", q)).strip("“”“”")
               for q in re.findall(r"<p>(.*?)</p>", mm.group(1), re.S)]
        eq(f"버핏 {p['key']} 인용 수", len(got), len(p["quotes"]))
        for i, (a, b) in enumerate(zip(got, p["quotes"]), 1):
            eq(f"버핏 {p['key']} 인용{i} 전문", a, b)
        true(f"버핏 {p['key']} 출처", p["source_url"] in mm.group(1))
    true("3%p 가 해석임을 명시", "인용자의 해석" in page)
    true("가치에 사면 = 할인율임을 명시", "정의상 할인율" in page)
    true("기대수익률이 재평가 차익을 넣지 않음을 명시",
         "영원히 보유하며 현금흐름만 받는다" in page)
    true("순수 국채 할인율의 한계 명시", "발산" in page)
    true("2009년 약점 명시", "2009년 바닥" in page)
    true("자료 기준일", f'<b>{d["generated"]}</b>' in page)
    true("기초율 생존편향·실질 등 한계 6개", page.count("<li><b>") >= 11)
    return passed, fails


def mutations(d):
    s, n = d["spx"], d["ndx"]
    _, c = cell_of(s, "own_sustained", "bond30_plus3")
    _, cn = cell_of(n, "own_sustained", "bond30_plus3")
    g = next(x for x in s["grid"] if x["key"] == "own_sustained")
    return [
        ("S&P 격자 가치", lambda p: p.replace(f'<b>{pts(c["value"])}</b>',
                                           "<b>9,999</b>", 1)),
        ("S&P 매수선", lambda p: p.replace(
            f'<b>{pts(c["buy_level"]["30%"])}</b>', "<b>8,888</b>", 1)),
        ("매수선 지금 대비", lambda p: p.replace(
            f'<td class="r">{sg(c["buy_vs_level"]["30%"], 0)}</td>',
            '<td class="r">-1%</td>', 1)),
        ("나스닥 격자 가치", lambda p: p.replace(
            f'<b>{pts(cn["value"])}</b>', "<b>99,999</b>", 1)),
        ("판정 색 뒤집기", lambda p: p.replace(
            'data-state="under"><b>불합격</b>',
            'data-state="over"><b>불합격</b>', 1)),
        ("판정 글자 뒤집기", lambda p: p.replace(
            'data-state="under"><b>불합격</b>',
            'data-state="under"><b>합격</b>', 1)),
        ("카드 매수선", lambda p: re.sub(
            r'(data-v="spx-buy">)[^<]+', r"\g<1>1 ~ 2", p, count=1)),
        ("카드 기대수익률", lambda p: re.sub(
            r'(data-v="ndx-ir">)[^<]+', r"\g<1>9.9% ~ 9.9%", p, count=1)),
        ("카드 매수선 기대수익률", lambda p: re.sub(
            r'(data-v="spx-ir-buy">)[^<]+', r"\g<1>20.0% ~ 21.0%", p,
            count=1)),
        ("카드 가치 기대수익률", lambda p: re.sub(
            r'(data-v="ndx-ir-value">)[^<]+', r"\g<1>9.9%", p, count=1)),
        ("가치=할인율 설명 제거", lambda p: p.replace("정의상 할인율",
                                                 "대체로 할인율", 1)),
        ("판정 본문 가치", lambda p: re.sub(
            r'(data-v="v-spx">)[^<]+', r"\g<1>1~2", p, count=1)),
        ("판정 본문 CAPE", lambda p: re.sub(
            r'(data-v="cape">)[^<]+', r"\g<1>12.3", p, count=1)),
        ("본문 30년 EPS", lambda p: re.sub(
            r'(data-v="eps30">)[^<]+', r"\g<1>9.99%", p, count=1)),
        ("기대수익률 표", lambda p: p.replace(
            f'<b>{pct(g["implied_return"], 2)}</b>', "<b>12.34%</b>", 1)),
        ("요구 성장률 '없음'을 숫자로", lambda p: p.replace(
            '<td class="r" data-state="flag">없음</td>',
            '<td class="r" data-state="flag">9.9%</td>', 1)),
        ("막대 길이", lambda p: re.sub(
            r'(data-bar="spx-own_sustained-buy30" style="width:)[\d.]+',
            r"\g<1>99.0", p, count=1)),
        ("현재선 위치", lambda p: re.sub(
            r'(data-bar="ndx-now" style="left:)[\d.]+', r"\g<1>5.0", p,
            count=1)),
        ("그래프 선 한 점", lambda p: re.sub(
            r'(data-line="price" points=")([\d.]+),([\d.]+)',
            r"\g<1>\g<2>,5.0", p, count=1)),
        ("10% 고정 그래프의 한 점", lambda p: re.sub(
            r'(data-chart="fixed10".*?data-line="value" points=")'
            r'([\d.]+),([\d.]+)', r"\g<1>\g<2>,5.0", p, count=1,
            flags=re.S)),
        ("10% 고정 그래프 캡션", lambda p: p.replace("할인율 10% 고정",
                                                "할인율 30년 국채+3%p", 1)),
        ("2009년 EPS 숫자", lambda p: re.sub(
            r'(data-v="e09">)[^<]+', r"\g<1>66.00", p, count=1)),
        ("10% 고정 '한 번도' 서술", lambda p: re.sub(
            r'(data-v="b10-months">)[^<]+', r"\g<1>12개월", p, count=1)),
        ("그래프 음영 하나 제거", lambda p: p.replace(
            'class="zone"/>', 'class="zonex"/>', 1)),
        ("30년 기록 표", lambda p: p.replace(
            pct(s["record"]["windows"]["30"]["eps_cagr_nominal"], 2) + "</td>",
            "1.23%</td>", 1)),
        ("백테스트 표", lambda p: p.replace(
            f'<td class="r">{s["backtest"]["below_value"]["months"]}</td>',
            '<td class="r">1</td>', 1)),
        ("평가이익 표", lambda p: p.replace(
            f'{n["aggregate"]["largest_mtm_gaps"][0]["gap"] / BN:+,.1f}',
            "+0.1", 1)),
        ("버핏 인용 뒷부분", lambda p: p.replace(
            "space out his purchases", "concentrate his purchases", 1)),
        ("버핏 인용 블록 제거", lambda p: re.sub(
            r'<blockquote data-bq="will">.*?</blockquote>', "", p,
            flags=re.S)),
        ("3%p 해석 단서 제거", lambda p: p.replace("인용자의 해석", "규칙", 1)),
        ("2009년 약점 서술 제거", lambda p: p.replace("2009년 바닥", "그 바닥", 1)),
        ("타이틀 제거", lambda p: re.sub(r"<title>.*?</title>", "", p)),
        ("타이틀 설명문", lambda p: re.sub(
            r"<title>.*?</title>",
            "<title>S&amp;P 500 과 나스닥100 의 버핏 기준 매수 가격 보고서</title>",
            p)),
        ("keep-all 제거", lambda p: p.replace("word-break:keep-all", "")),
        ("거터 제거", lambda p: p.replace(
            "max(16px,env(safe-area-inset-left,0px))", "16px")),
        ("다크 가드 제거", lambda p: p.replace(
            ':root:not([data-theme="light"])', ":root")),
        ("doctype", lambda p: "<!doctype html>" + p),
        ("허용 안 된 호스트", lambda p: p.replace(
            "</div>", '<img src="https://evil.example.com/x.png"></div>', 1)),
        ("표를 스크롤 밖으로", lambda p: p.replace(
            '<div class="scroll"><table>', "<table>", 1)),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    d = json.load(open(DATA, encoding="utf-8"))
    page = build(d)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"wrote {OUT} ({len(page):,} bytes)")
    if a.verify or a.mutate:
        passed, fails = verify(page, d)
        print(f"페이지 검사 {passed + len(fails)}건 — 통과 {passed}, "
              f"실패 {len(fails)}")
        for f in fails[:25]:
            print("  ✗", f)
        if fails:
            return 1
    if a.mutate:
        muts = mutations(d)
        print(f"\n변이 검정 {len(muts)}건")
        survived = []
        for name, mut in muts:
            bad = mut(page)
            if bad == page:
                survived.append(f"{name} (대상 없음)")
                print(f"  ✗ {name}: 훼손 대상을 찾지 못했습니다")
                continue
            try:
                _, f2 = verify(bad, d)
            except SystemExit as exc:
                print(f"  ✓ {name}: 구조 검사에서 중단 — {exc}")
                continue
            if f2:
                print(f"  ✓ {name}: {len(f2)}건 실패 — {f2[0][:78]}")
            else:
                survived.append(name)
                print(f"  ✗ {name}: 아무 검사도 실패하지 않음 — 검사 구멍")
        if survived:
            print(f"\n변이 {len(survived)}건이 통과했습니다: {survived}")
            return 1
        print(f"  변이 {len(muts)}/{len(muts)}건 모두 포착")
    return 0


if __name__ == "__main__":
    sys.exit(main())
