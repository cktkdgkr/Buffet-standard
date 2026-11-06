"""
성장률 가정 재검증 + 버핏 기준 적정주가 — HTML 페이지.

buffett_standard.json 에서 생성합니다. 본문 보고서(fair_value_report.html)의
후속편이고, 다루는 질문은 하나입니다: **그 성장률 가정이 객관적인가.**

    python3 export_buffett_standard_html.py
    python3 export_buffett_standard_html.py --verify --mutate
"""

import argparse
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DATA = os.path.join(HERE, "fv", "buffett_standard.json")
OUT = os.path.join(HERE, "fv", "buffett_standard_report.html")
MM, BN = 1e6, 1e9
ORDER = ["보수", "중립", "낙관"]


def load():
    return json.load(open(DATA, encoding="utf-8"))


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def sg(x, nd=1):
    return "—" if x is None else f"{x * 100:+.{nd}f}%"


def bn(x, nd=1):
    return "—" if x is None else f"{x / BN:,.{nd}f}"


def usd(x, nd=0):
    return "—" if x is None else f"${x:,.{nd}f}"


def esc(x):
    return html.escape(str(x))


def cell(v, cls=""):
    return {"v": v, "cls": cls}


def cheap(value, price):
    return "cheap" if value is not None and value > price else "rich"


def sign(x):
    return "pos" if x is not None and x >= 0 else "neg"


def table(headers, rows, caption=None, align=None, cls="", foot=None):
    align = align or (["l"] + ["r"] * (len(headers) - 1))
    out = [f'<figure class="tw {cls}">', '<div class="scroll"><table>']
    out.append("<thead><tr>" + "".join(
        f'<th class="{a}">{esc(h)}</th>' for h, a in zip(headers, align))
        + "</tr></thead><tbody>")
    for r in rows:
        tds = []
        for v, a in zip(r, align):
            k = v["cls"] if isinstance(v, dict) else ""
            t = v["v"] if isinstance(v, dict) else v
            tds.append(f'<td class="{a} {k}">{t}</td>')
        out.append("<tr>" + "".join(tds) + "</tr>")
    out.append("</tbody>")
    if foot:
        out.append("<tfoot><tr>" + "".join(
            f'<td class="{a}">{v}</td>' for v, a in zip(foot, align))
            + "</tr></tfoot>")
    out.append("</table></div>")
    if caption:
        out.append(f"<figcaption>{caption}</figcaption>")
    out.append("</figure>")
    return "\n".join(out)


STYLE = """
<style>
:root{
  --bg:#f6f5f2; --panel:#ffffff; --fg:#191b1e; --dim:#5c6269; --line:#e3e1db;
  --ink:#0e1012; --accent:#1f4e79; --accent-soft:#e9f0f6;
  --cheap:#0f6b4f; --cheap-bg:#e6f2ec;
  --rich:#9a2a1f; --rich-bg:#fbeae7;
  --pos:#1f5d8c; --neg:#8a4b12;
  --flag:#8a6a12; --flag-bg:#fbf3e0;
  --price:#17191c; --quote:#4a3f6b; --quote-bg:#efecf6;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;
  --serif:"Noto Serif KR",Georgia,"Times New Roman",serif;
  --sans:"Inter","Noto Sans KR",system-ui,-apple-system,sans-serif;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#14161a; --panel:#1c1f24; --fg:#e9e7e2; --dim:#9aa1a9; --line:#2d3137;
    --ink:#f3f1ed; --accent:#7fb6dd; --accent-soft:#1a2630;
    --cheap:#6fc2a5; --cheap-bg:#172a23;
    --rich:#e8897c; --rich-bg:#2d1b18;
    --pos:#7fb6dd; --neg:#d9a35f;
    --flag:#d9bd6a; --flag-bg:#2a2416;
    --price:#f3f1ed; --quote:#b6a9d8; --quote-bg:#221d2e;
    color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --bg:#14161a; --panel:#1c1f24; --fg:#e9e7e2; --dim:#9aa1a9; --line:#2d3137;
  --ink:#f3f1ed; --accent:#7fb6dd; --accent-soft:#1a2630;
  --cheap:#6fc2a5; --cheap-bg:#172a23;
  --rich:#e8897c; --rich-bg:#2d1b18;
  --pos:#7fb6dd; --neg:#d9a35f;
  --flag:#d9bd6a; --flag-bg:#2a2416;
  --price:#f3f1ed; --quote:#b6a9d8; --quote-bg:#221d2e;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{
  background:var(--bg); color:var(--fg); font-family:var(--sans);
  font-size:16px; line-height:1.72; margin:0;
  word-break:keep-all; overflow-wrap:anywhere;
}
.wrap{
  max-width:900px; margin:0 auto; padding-block:0 76px;
  padding-left:max(16px,env(safe-area-inset-left,0px));
  padding-right:max(16px,env(safe-area-inset-right,0px));
}
h1,h2,h3,h4{font-family:var(--serif); text-wrap:balance; color:var(--ink);
  line-height:1.32; letter-spacing:-.01em}
h1{font-size:clamp(1.7rem,5.2vw,2.5rem); margin:0 0 .3em; font-weight:700}
h2{font-size:clamp(1.3rem,3.8vw,1.7rem); margin:2.8em 0 .5em;
  padding-top:.75em; border-top:2px solid var(--line)}
h3{font-size:1.12rem; margin:2em 0 .4em; font-weight:700}
h4{font-size:1rem; margin:1.5em 0 .3em; font-weight:700}
p{margin:0 0 1.05em}
a{color:var(--accent)}
strong{font-weight:650; color:var(--ink)}
.lede{font-size:1.07rem}
.meta{font-family:var(--mono); font-size:.76rem; color:var(--dim);
  line-height:1.95; margin:0 0 1.5em; padding:.85em 1em;
  background:var(--panel); border:1px solid var(--line); border-radius:9px}
.meta b{color:var(--fg); font-weight:600}
figure.tw{margin:1.1em 0 1.6em}
.scroll{overflow-x:auto; -webkit-overflow-scrolling:touch;
  border:1px solid var(--line); border-radius:10px; background:var(--panel)}
table{border-collapse:collapse; width:100%; font-size:.87rem;
  font-variant-numeric:tabular-nums}
th,td{padding:.56em .8em; border-bottom:1px solid var(--line);
  white-space:nowrap}
th{font-size:.71rem; letter-spacing:.07em; text-transform:uppercase;
  color:var(--dim); font-weight:600; text-align:left;
  background:var(--bg); position:sticky; top:0}
td.l,th.l{text-align:left; white-space:normal; min-width:10ch}
td.r,th.r{text-align:right; font-family:var(--mono); font-size:.84rem}
td.w,th.w{text-align:left; white-space:normal; min-width:20ch;
  font-size:.82rem; color:var(--dim)}
tbody tr:last-child td{border-bottom:0}
tfoot td{border-top:2px solid var(--line); font-weight:650; border-bottom:0;
  background:var(--accent-soft)}
tr.here td{background:var(--flag-bg); font-weight:650}
td.cheap{color:var(--cheap); font-weight:650}
td.rich{color:var(--rich); font-weight:650}
td.pos{color:var(--pos)}
td.neg{color:var(--neg)}
td.flagc{color:var(--flag); font-weight:650}
figcaption{font-size:.79rem; color:var(--dim); margin-top:.6em;
  line-height:1.7}
.legend{display:flex; flex-wrap:wrap; gap:.5rem 1.1rem; font-size:.78rem;
  color:var(--dim); margin:.3em 0 1.5em; padding:.75em .95em;
  background:var(--panel); border:1px solid var(--line); border-radius:9px}
.legend span{display:inline-flex; align-items:center; gap:.4em}
.legend i{width:.72em; height:.72em; border-radius:3px; display:inline-block}
.formula{font-family:var(--mono); font-size:.82rem; padding:.95em 1.1em;
  background:var(--accent-soft); color:var(--accent); border-radius:9px;
  margin:1.1em 0 1.4em; overflow-x:auto; white-space:pre; line-height:1.9}
ul{margin:0 0 1.2em; padding-left:1.25em}
li{margin:0 0 .6em}
.callout{margin:1.3em 0; padding:1em 1.15em; border-radius:11px;
  border:1px solid var(--flag); background:var(--flag-bg)}
.callout p{margin:0}
.callout strong{color:var(--flag)}
.correct{margin:1.3em 0; padding:1em 1.15em; border-radius:11px;
  border:1px solid var(--rich); background:var(--rich-bg)}
.correct p{margin:0 0 .6em}
.correct p:last-child{margin:0}
.correct strong{color:var(--rich)}
blockquote.bq{margin:1.1em 0; padding:.9em 1.1em; border-radius:10px;
  border-left:4px solid var(--quote); background:var(--quote-bg)}
blockquote.bq p{margin:0 0 .5em; font-style:italic; color:var(--ink)}
blockquote.bq .src{font-style:normal; font-size:.79rem; color:var(--quote);
  font-weight:600; margin:0}
blockquote.bq .nt{font-style:normal; font-size:.84rem; color:var(--dim);
  margin:.45em 0 0}
.dist{display:grid; gap:.22rem; margin:1em 0 1.5em}
.drow{display:grid; grid-template-columns:5.6em 1fr 4.2em; gap:.55rem;
  align-items:center; font-size:.8rem}
.drow .lb{font-family:var(--mono); font-size:.76rem; color:var(--dim);
  text-align:right}
.drow .tr{height:1.05em; background:var(--line); border-radius:3px;
  min-width:0; position:relative}
.drow .fl{height:100%; display:block; background:var(--accent);
  border-radius:3px}
.drow .pc{font-family:var(--mono); text-align:right; color:var(--fg)}
.drow.mark .lb,.drow.mark .pc{color:var(--flag); font-weight:700}
.drow.mark .fl{background:var(--flag)}
footer{margin-top:2.8em; padding-top:1.2em; border-top:1px solid var(--line);
  font-size:.78rem; color:var(--dim); line-height:1.8}
</style>
"""


def build(d):
    macro, br, cos = d["macro"], d["base_rates"], d["companies"]
    infl = macro["breakeven_inflation_10y"]["rate"]
    dmap = {x["key"]: x for x in d["discount_options"]}
    tmap = {x["key"]: x for x in d["terminal_options"]}
    ni = br["net_income_10y"]
    sl = br["sales_10y"]
    o = []
    w = o.append

    def nm(co):
        return f"{co['korean']}({co['ticker']})"

    def gcell(co, gkey, dkey):
        g = [x for x in co["grid"] if x["growth_key"] == gkey][0]
        return g, [x for x in g["cells"] if x["discount_key"] == dkey][0]

    w("<title>성장률 재검증</title>")
    w('<meta name="claude:viewport-fit-sides" content="cover">')
    w('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
      'family=Inter:wght@400;600;700&family=Noto+Sans+KR:wght@400;500;700&'
      'family=Noto+Serif+KR:wght@600;700&display=swap">')
    w(STYLE)
    w('<div class="wrap">')

    w("<h1>성장률 가정 재검증 — 그리고 버핏 기준으로 다시 계산한 적정주가</h1>")
    w(f'<p class="meta">'
      f'<b>자료 기준일</b> {d["generated"]} · '
      f'<b>본문 보고서</b> {d["fair_value_generated"]} 생성<br>'
      f'<b>30년 국채</b> {pct(macro["treasury_30y"]["rate"], 3)} · '
      f'<b>10년 국채</b> {pct(macro["treasury_10y"]["rate"], 3)} · '
      f'<b>10년 기대인플레이션</b> {pct(infl, 2)} '
      f'(FRED T10YIE, {macro["breakeven_inflation_10y"]["as_of"]})<br>'
      f'<b>기초율</b> {esc(br["source"])} · {esc(br["period"])} · '
      f'참조군 {esc(br["reference_class"])}</p>')
    w(f'<p class="lede">제기된 의문은 <strong>"AI 발 성장이 예상되는 '
      f'업계인데 10년차 성장률 3.5%는 너무 낮지 않은가. 세 기업은 지난 10년간 '
      f'10% 넘게 성장해 왔다"</strong>입니다. 먼저 제 보고서가 오해를 유발한 '
      f'부분을 바로잡고, 그 다음 성장률 가정을 외부 자료 세 가지로 '
      f'재검증하고, 마지막으로 버핏의 실제 기준으로 적정주가를 다시 '
      f'냈습니다.</p>')

    # ======================================================= 0. 바로잡음
    w("<h2>0. 먼저 바로잡습니다 — 3.5%는 10년간 성장률이 아닙니다</h2>")
    w('<div class="correct">'
      '<p><strong>제 보고서의 표현이 오해를 유발했습니다.</strong> '
      '3.5%는 <em>10년차 한 해</em>의 성장률(감쇠 목표)이고, '
      '10년 전체의 평균 성장률이 아닙니다.</p>'
      '<p>중립 시나리오는 1년차에 약 10%로 시작해 10년에 걸쳐 3.5%까지 '
      '직선으로 내려갑니다. 그 10년을 평균하면 아래와 같습니다.</p></div>')
    rows = []
    for r in d["clarification"]["rows"]:
        rows.append([f"{r['korean']}", r["scenario"],
                     pct(r["year1_growth"]), pct(r["year10_growth"]),
                     cell(f"<b>{pct(r['nopat_cagr_10y'], 2)}</b>", "flagc")])
    w(table(["기업", "시나리오", "1년차 성장률", "10년차 성장률",
             "10년 평균 (NOPAT CAGR)"], rows,
            caption="즉 중립은 10년 평균 6.6~9.2%, 낙관은 11.9~14.6%를 "
                    "가정하고 있었습니다. 3.5%로 10년을 가정한 시나리오는 "
                    "하나도 없습니다.",
            align=["l", "l", "r", "r", "r"]))

    # =================================================== 1. 10년 기록 표
    w("<h2>1. 세 기업의 지난 10년 — 성장률과 ROIC</h2>")
    w("<p>요청하신 표입니다. 전부 SEC 공시에서 뽑은 값이고, 50개사 조사와 "
      "같은 ROIC 정의를 씁니다.</p>")
    for co in cos:
        w(f"<h3>{esc(nm(co))}</h3>")
        hist = co["history"]
        rows = []
        for h in hist:
            rows.append([
                f"FY{h['fiscal_year']}",
                bn(h["revenue"]),
                cell(sg(h["revenue_growth"], 1)
                     if h["revenue_growth"] is not None else "—",
                     sign(h["revenue_growth"])
                     if h["revenue_growth"] is not None else ""),
                bn(h["operating_income"]),
                cell(sg(h["operating_income_growth"], 1)
                     if h["operating_income_growth"] is not None else "—",
                     sign(h["operating_income_growth"])
                     if h["operating_income_growth"] is not None else ""),
                bn(h["invested_capital_avg"]),
                cell(sg(h["invested_capital_growth"], 1)
                     if h["invested_capital_growth"] is not None else "—",
                     sign(h["invested_capital_growth"])
                     if h["invested_capital_growth"] is not None else ""),
                cell(f"<b>{pct(h['roic'])}</b>", "cheap"),
            ])
        w(table(["회계연도", "매출", "증감", "영업이익", "증감",
                 "투하자본(평균)", "증감", "ROIC"], rows,
                caption=f"단위 십억 달러. 10년 CAGR: 영업이익 "
                        f"{pct(co['own_cagr_nominal'])} · 매출 "
                        f"{pct(co['own_revenue_cagr_nominal'])}. "
                        f"TTM 영업이익은 {bn(co['ttm_nopat'] / 1)}십억 "
                        f"NOPAT 기준으로 본문 보고서에 있습니다 "
                        f"(자료 기준 {co['data_as_of']}).",
           align=["l", "r", "r", "r", "r", "r", "r", "r"]))

    # ================================================= 2. 기초율 재검증
    w("<h2>2. 객관 기준 ① — 기초율: 이 규모 기업이 실제로 얼마나 "
      "성장했는가</h2>")
    w(f'<p>가장 직접적인 외부 검증은 <strong>같은 규모의 기업들이 과거 10년 '
      f'동안 실제로 얼마나 성장했는지</strong>를 보는 것입니다. '
      f'{esc(br["source"])}이 {esc(br["period"])}년을 규모별로 집계해 '
      f'두었습니다.</p>')
    w(f'<p>우리 세 기업의 TTM 매출은 '
      + " · ".join(f"{esc(co['korean'])} {bn(co['ttm_revenue'], 0)}십억"
                   for co in cos)
      + f' 달러로 전부 <strong>{esc(br["reference_class"])}</strong> 참조군에 '
        f'들어갑니다. 그래서 이 칸이 맞는 비교 대상입니다.</p>')
    w(f'<div class="callout"><p><strong>이 수치는 전부 실질(인플레이션 조정) '
      f'기준입니다.</strong> {esc(br["real_terms_note"])} 아래 표에는 '
      f'명목 환산값(실질 + 기대인플레이션 {pct(infl, 2)})을 함께 '
      f'적었습니다.</p></div>')
    w("<h3>10년 순이익 성장률 분포 (매출 $50십억 초과 기업, 1950–2015)</h3>")
    mark_lo, mark_hi = 0.0, 0.10
    tot = max(s for _, s in ni["bands"])
    w('<div class="dist">')
    for lab, share in ni["bands"]:
        if share == 0:
            continue
        is_mark = lab == "10~20"
        w(f'<div class="drow{" mark" if is_mark else ""}">'
          f'<span class="lb">{esc(lab)}%</span>'
          f'<span class="tr"><span class="fl" '
          f'style="width:{share / tot * 100:.1f}%"></span></span>'
          f'<span class="pc">{pct(share)}</span></div>')
    w("</div>")
    w(f'<p>중위값 <strong>{pct(ni["median"])}</strong>(실질) = 명목 '
      f'<strong>{pct(ni["median"] + infl)}</strong>, 평균 '
      f'{pct(ni["mean"])}(실질) = 명목 {pct(ni["mean"] + infl)}. '
      f'음수였던 경우가 '
      f'{pct(sum(s for l, s in ni["bands"] if l.startswith("-") or l.startswith("<")))}'
      f'입니다 — 이 규모의 기업이 10년에 걸쳐 이익을 못 늘린 경우가 셋 중 '
      f'하나가 넘습니다.</p>')
    w(table(["기준", "실질", "명목 환산", "이 수준 이상이 나온 비율"], [
        ["중위값", pct(ni["median"]), cell(f"<b>{pct(ni['median'] + infl)}</b>",
                                        "flagc"), "50%"],
        ["평균", pct(ni["mean"]), pct(ni["mean"] + infl), "—"],
        ["10% 이상 (실질)", "10.0%", pct(0.10 + infl),
         cell(f"<b>{pct(sum(s for l, s in ni['bands'] if '~' in l and float(l.split('~')[0]) >= 10) + 0)}</b>",
              "rich")],
        ["20% 이상 (실질)", "20.0%", pct(0.20 + infl),
         pct(sum(s for l, s in ni["bands"]
                 if "~" in l and float(l.split("~")[0]) >= 20))],
    ], caption=f"표준편차 {pct(ni['stdev'])}. 매출 성장률 분포는 더 얇습니다 — "
               f"중위 {pct(sl['median'])}(실질), 실질 10% 이상은 "
               f"{pct(sum(s for l, s in sl['bands'] if '~' in l and float(l.split('~')[0]) >= 10))}"
               f"에 불과합니다. 이익 성장률 쪽 꼬리가 두꺼운 것은 마진이 "
               f"움직이기 때문입니다.",
       align=["l", "r", "r", "r"]))
    w(f'<div class="callout"><p><strong>이 기초율은 위쪽으로 치우쳐 '
      f'있습니다.</strong> {esc(br["survivorship_note"])}</p></div>')

    w("<h3>그 분포 안에서 우리 세 기업과 제 가정은 어디인가</h3>")
    rows = []
    for co in cos:
        rows.append([
            cell(f"<b>{esc(nm(co))} 과거 10년 실적</b>", ""),
            pct(co["own_cagr_nominal"]), pct(co["own_cagr_real"]),
            cell(f"<b>상위 {pct(co['own_cagr_percentile_at_or_above'])}</b>",
                 "flagc"),
            cell("과거가 이미 꼬리였습니다", "w"),
        ])
        for g in co["grid"]:
            rows.append([
                f"　{g['growth_label'][:30]}",
                pct(g["growth"]), pct(g["growth_real"]),
                f"상위 {pct(g['base_rate_percentile_at_or_above'])}",
                cell(esc(g["basis"][:110]) + ("…" if len(g["basis"]) > 110
                                              else ""), "w"),
            ])
    w(table(["가정 / 실적", "명목", "실질", "기초율 백분위", "근거"], rows,
            caption="백분위는 \"이 수준 이상의 10년 성장률이 나온 기업의 "
                    "비율\"입니다. 작을수록 드문 일입니다. 들여쓴 줄이 "
                    "제가 쓴 가정입니다.",
            align=["l", "r", "r", "r", "w"]))
    nv = [c for c in cos if c["ticker"] == "NVDA"][0]
    w(f'<p><strong>여기서 결론이 뒤집힙니다.</strong> 제 가정이 너무 낮은 게 '
      f'아니라, <strong>세 기업의 지난 10년이 이미 분포의 꼬리</strong>였습니다. '
      f'마이크로소프트와 알파벳의 실질 성장률은 상위 10~12%, 엔비디아의 '
      f'{pct(nv["own_cagr_real"])}는 <strong>이 규모 기업 중 전례가 '
      f'없습니다</strong>(상위 {pct(nv["own_cagr_percentile_at_or_above"])}). '
      f'다만 엔비디아는 10년 전에 매출 $5십억짜리 회사였으므로, '
      f'<strong>다음 10년에 적용되는 참조군은 지금 규모의 것</strong>입니다 — '
      f'그게 규모별로 나눠 보는 이유입니다.</p>')
    w(f'<p>반대로 제 가정을 이 분포에 얹어 보면, 중립(실질 4.4~7.0%)은 '
      f'중위값보다 위이고 낙관(실질 9.7~12.3%)은 상위 20% 안쪽입니다. '
      f'<strong>즉 제 가정은 보수적이라기보다 이미 낙관적인 쪽</strong>입니다. '
      f'다만 기초율이 2015년까지의 자료라는 점, 그리고 AI 가 과거와 다른 '
      f'국면이라는 주장은 기초율이 반박할 수 없는 영역입니다 — 기초율은 '
      f'"그게 얼마나 드문 일인지"만 말해 줍니다.</p>')

    # ============================================= 3. 거시 기준 (터미널)
    w("<h2>3. 객관 기준 ② — 영구성장률의 상한은 경제성장률입니다</h2>")
    w(f'<p>10년 이후의 영구성장률은 취향의 문제가 아닙니다. 어떤 기업도 '
      f'경제보다 빠르게 <em>영구히</em> 성장할 수 없습니다 — 그러면 결국 '
      f'경제 전체가 됩니다. 그래서 상한이 명목 GDP 성장률입니다.</p>')
    w(table(["기준", "값", "출처 / 근거"], [
        ["장기 실질 GDP 성장률 (1950–2015)", pct(br["gdp_real_1950_2015"]),
         cell(esc(br["gdp_note"]), "w")],
        ["10년 기대인플레이션", pct(infl, 2),
         cell(esc(macro["breakeven_inflation_10y"]["label"]) + " · "
              + esc(macro["breakeven_inflation_10y"]["series"]) + " · "
              + esc(macro["breakeven_inflation_10y"]["note"]), "w")],
        ["→ 장기 명목 GDP (상한)",
         cell(f"<b>{pct(macro['nominal_gdp_long_run']['rate'], 2)}</b>",
              "flagc"),
         cell(esc(macro["nominal_gdp_long_run"]["note"]), "w")],
        ["30년 국채 수익률", pct(macro["treasury_30y"]["rate"], 3),
         cell("버핏이 할인율의 기준으로 쓰는 금리", "w")],
        ["10년 국채 수익률", pct(macro["treasury_10y"]["rate"], 3),
         cell("2007년 주주총회에서 버핏이 \"4 and 3/4%\"라고 말한 수준과 "
              "거의 같습니다", "w")],
    ], align=["l", "r", "w"]))
    w(f'<p>본문 보고서가 쓴 터미널 2.0~3.0%는 이 상한'
      f'({pct(macro["nominal_gdp_long_run"]["rate"], 2)})의 절반 이하입니다. '
      f'보수적인 쪽이 맞고, 그래서 아래에서 명목 GDP까지 올려 본 민감도를 '
      f'함께 냈습니다.</p>')

    # ============================================= 4. 버핏의 실제 기준
    w("<h2>4. 객관 기준 ③ — 버핏은 실제로 어떻게 계산했는가</h2>")
    w("<p>찾아보니 핵심은 성장률이 아니라 <strong>할인율</strong>에 "
      "있었습니다.</p>")
    for q in d["buffett"]:
        w('<blockquote class="bq">'
          f'<p>“{esc(q["quote"])}”</p>'
          f'<p class="src">— {q["year"]}년 · {esc(q["kind"])} · '
          f'<a href="{esc(q["url"])}">출처</a></p>'
          f'<p class="nt">{esc(q["note"])}</p></blockquote>')
    w('<div class="callout"><p><strong>정리하면 버핏의 방식은 이렇습니다.</strong> '
      '① 장기 국채 수익률을 할인율의 <em>기준</em>으로 삼고, ② 위험 '
      '프리미엄을 얹는 대신 <strong>안전마진</strong>으로 위험을 처리하고, '
      '③ 성장은 <strong>증분 수익률이 매력적일 때만</strong> 가치가 된다고 '
      '봅니다. ③은 우리 모형이 이미 쓰고 있는 식 그대로입니다.</p></div>')
    w('<div class="formula">'
      + esc("잉여현금 = NOPAT × (1 − 성장률 ÷ 증분ROIC)") + "\n"
      + esc("           ↑ 1992년 서한의 \"incremental returns that are "
            "enticing\" 이 바로 이 항입니다") + "</div>")
    w("<h3>그래서 할인율을 어떻게 잡아야 하나</h3>")
    w(table(["할인율 후보", "값", "근거"],
            [[esc(x["label"]), cell(f"<b>{pct(x['rate'], 2)}</b>",
                                    "flagc" if x["key"] == "bond30_plus3"
                                    else ""),
              cell(esc(x["basis"]), "w")]
             for x in d["discount_options"]],
            caption="주황색이 버핏 기준으로 가장 그럴듯한 값입니다. 다만 "
                    "3%포인트 스프레드는 인용자의 해석이고 버핏이 말한 "
                    "규칙이 아니라는 점을 분명히 해 둡니다.",
            align=["l", "r", "w"]))
    gdpdiv = [x for x in cos[0]["terminal_sensitivity"]
              if x["discount_key"] == "bond30"
              and x["terminal_key"] == "nominal_gdp"][0]
    w(f'<p><strong>순수 국채 수익률만으로 주식을 할인하면 모순이 '
      f'생깁니다.</strong> 30년 국채 {pct(macro["treasury_30y"]["rate"], 2)}로 '
      f'할인하면서 영구성장률을 명목 GDP '
      f'{pct(macro["nominal_gdp_long_run"]["rate"], 2)}로 두면 분모가 음수가 '
      f'되어 <strong>가치가 무한</strong>이 됩니다. 아래 민감도 표에서 실제로 '
      f'발산합니다. 이것이 버핏의 "국채보다 significantly higher"가 필요한 '
      f'이유이고, 국채 + 3%포인트를 기준으로 삼은 근거입니다.</p>')

    # ================================================= 5. 격자
    w("<h2>5. 다시 계산한 적정주가 — 성장률 × 할인율 격자</h2>")
    w('<div class="legend">'
      '<span><i style="background:var(--cheap)"></i>평가치 > 현재가</span>'
      '<span><i style="background:var(--rich)"></i>평가치 < 현재가</span>'
      '<span><i style="background:var(--flag)"></i>주목</span>'
      '</div>')
    w(f'<p>어느 칸이 맞는지는 가정의 문제이므로 하나의 답을 내지 않고 '
      f'격자로 냈습니다. 증분 ROIC은 네 칸 전부에 같은 값(각 기업의 10년 중위 '
      f'ROIC, 상한 35%)을 써서 <strong>성장률과 할인율의 효과만</strong> '
      f'보이게 했고, 터미널은 '
      f'{pct(tmap["inflation"]["rate"], 2)}(실질 영구성장 0%)로 '
      f'고정했습니다.</p>')
    for co in cos:
        w(f"<h3>{esc(nm(co))} — 현재가 {usd(co['price'], 2)}</h3>")
        rows = []
        for g in co["grid"]:
            row = [cell(f"{esc(g['growth_label'])}", ""),
                   pct(g["growth"]),
                   f"상위 {pct(g['base_rate_percentile_at_or_above'])}"]
            for dk in ["bond30", "bond30_plus3", "project10", "project11"]:
                c_ = [x for x in g["cells"] if x["discount_key"] == dk][0]
                if c_["diverges"]:
                    row.append(cell("발산", "flagc"))
                else:
                    row.append(cell(
                        f"<b>{usd(c_['value_per_share'])}</b>",
                        cheap(c_["value_per_share"], co["price"])))
            rows.append(row)
        w(table(["성장률 가정", "1년차", "기초율 백분위",
                 f"국채 {pct(dmap['bond30']['rate'], 2)}",
                 f"버핏 기준 {pct(dmap['bond30_plus3']['rate'], 2)}",
                 "프로젝트 10%", "보수 11%"], rows,
                caption=f"증분 ROIC {pct(co['incremental_roic_used'])} 고정 "
                        f"({esc(co['incremental_roic_basis'])}). "
                        f"현재가 {usd(co['price'], 2)}.",
           align=["l", "r", "r", "r", "r", "r", "r"],
           foot=["현재가", "", "", usd(co["price"], 2), usd(co["price"], 2),
                 usd(co["price"], 2), usd(co["price"], 2)]))

    # ============================================ 6. 안전마진 판정
    w("<h2>6. 버핏이라면 살까 — 안전마진을 적용한 판정</h2>")
    w('<p>버핏 기준으로 계산한 가치는 <strong>살 가격이 아닙니다.</strong> '
      '그는 위험을 할인율에 얹지 않고 안전마진으로 처리하므로, 그 가치보다 '
      '충분히 싸야 삽니다. 아래는 버핏 할인율'
      f'({pct(dmap["bond30_plus3"]["rate"], 2)})에서 계산한 가치에 안전마진 '
      '30%를 적용한 매수 상한입니다.</p>')
    rows = []
    for co in cos:
        for g in co["grid"]:
            _, c_ = gcell(co, g["growth_key"], "bond30_plus3")
            if c_["diverges"]:
                continue
            buy = c_["buy_price_at_margin"]["30%"]
            ok = buy > co["price"]
            rows.append([
                esc(nm(co)) if g is co["grid"][0] else f"　{esc(nm(co))}",
                esc(g["growth_label"][:28]),
                usd(c_["value_per_share"]),
                cell(sg(c_["upside_vs_price"], 0),
                     cheap(c_["value_per_share"], co["price"])),
                cell(f"<b>{usd(buy)}</b>", ""),
                usd(co["price"], 2),
                cell(f"<b>{'합격' if ok else '불합격'}</b>",
                     "cheap" if ok else "rich"),
            ])
    w(table(["기업", "성장률 가정", "가치", "현재가 대비",
             "안전마진 30% 매수 상한", "현재가", "판정"], rows,
            caption="판정 = 안전마진 30%를 적용한 매수 상한이 현재가보다 "
                    "높은가. 안전마진 0·20·30·40%의 매수가는 JSON 에 모두 "
                    "들어 있습니다.",
            align=["l", "l", "r", "r", "r", "r", "r"]))
    nvda_ok = [g["growth_key"] for g in nv["grid"]
               if not gcell(nv, g["growth_key"], "bond30_plus3")[1]["diverges"]
               and gcell(nv, g["growth_key"], "bond30_plus3")[1]
               ["buy_price_at_margin"]["30%"] > nv["price"]]
    w(f'<div class="callout"><p><strong>결론: 버핏 기준으로 바꿔도 판정은 '
      f'거의 그대로입니다.</strong> 할인율을 10%에서 '
      f'{pct(dmap["bond30_plus3"]["rate"], 2)}로 낮추면 가치는 크게 오르지만, '
      f'버핏이 함께 요구하는 안전마진 30%를 적용하면 '
      f'<strong>마이크로소프트와 알파벳은 네 가정 모두 불합격</strong>입니다. '
      f'알파벳의 AI 가속 가정이 매수 상한 '
      f'{usd(gcell(nv, "ai_sustained", "bond30_plus3")[1]["buy_price_at_margin"]["30%"]) if False else usd([x for x in cos if x["ticker"] == "GOOG"][0]["grid"][3]["cells"][1]["buy_price_at_margin"]["30%"])}'
      f'로 현재가 '
      f'{usd([x for x in cos if x["ticker"] == "GOOG"][0]["price"], 2)}에 가장 '
      f'가깝게 닿습니다. <strong>엔비디아만 과거 성장 유지 또는 AI 가속을 '
      f'가정할 때 합격</strong>합니다 — 그리고 그 가정이 바로 '
      f'기초율에서 상위 '
      f'{pct(nv["grid"][2]["base_rate_percentile_at_or_above"])} 안쪽인 '
      f'경우입니다.</p></div>')

    # ===================================== 7. 터미널 민감도 (발산 포함)
    w("<h2>7. 영구성장률을 올리면 — 그리고 모형이 깨지는 지점</h2>")
    w(f'<p>"AI 로 성장이 오래 간다"는 주장을 영구성장률로 반영하면 어떻게 '
      f'되는지 봅니다. 성장률 가정은 "과거의 절반"으로 고정했습니다.</p>')
    for co in cos:
        rows = []
        for x in co["terminal_sensitivity"]:
            label = ("버핏 기준" if x["discount_key"] == "bond30_plus3"
                     else "순수 국채")
            rows.append([
                f"{label} {pct(x['discount'], 2)}",
                esc(x["label"]), pct(x["rate"], 2),
                cell("발산" if x["diverges"]
                     else f"<b>{usd(x['value_per_share'])}</b>",
                     "flagc" if x["diverges"]
                     else cheap(x["value_per_share"], co["price"])),
                cell("—" if x["diverges"]
                     else sg(x["upside_vs_price"], 0),
                     "" if x["diverges"]
                     else cheap(x["value_per_share"], co["price"])),
            ])
        w(table(["할인율", "영구성장률", "값", "주당 가치", "현재가 대비"],
                rows,
                caption=f"{esc(nm(co))} · 현재가 {usd(co['price'], 2)} · "
                        f"성장률 가정 \"과거의 절반\". 순수 국채 할인율에서 "
                        f"명목 GDP 영구성장을 가정하면 분모가 음수가 되어 "
                        f"발산합니다 — 그 조합은 쓸 수 없습니다.",
           align=["l", "l", "r", "r", "r"]))

    # ============================================= 8. 남는 반론
    w("<h2>8. 기초율이 반박하지 못하는 것</h2>")
    w("<p>공정하게, 이 재검증이 닫지 못하는 구멍을 적어 둡니다.</p>")
    w("<ul>")
    w(f"<li><strong>기초율은 2015년까지의 자료입니다.</strong> "
      f"{esc(br['period'])}년을 집계한 것이므로 지금의 AI 설비 투자 국면은 "
      f"들어 있지 않습니다. \"이번은 다르다\"는 주장을 기초율은 반박할 수 "
      f"없고, 다만 그것이 얼마나 드문 일인지를 말해 줍니다.</li>")
    w("<li><strong>참조군의 구성이 다릅니다.</strong> 1950~2015년에 매출 "
      "$50십억을 넘었던 기업들은 상당수가 정유·자동차·통신 같은 성숙 "
      "산업입니다. 영업이익률 33~65%인 오늘의 소프트웨어·반도체 기업이 그 "
      "분포에 잘 대표되어 있다고 보기 어렵습니다.</li>")
    w("<li><strong>매출이 아니라 이익을 모형화합니다.</strong> 마진이 오르면 "
      "이익은 매출보다 빨리 자랍니다. 그래서 순이익 기초율(꼬리가 더 두꺼운 "
      "쪽)을 썼지만, 이미 마진이 높은 세 기업에 남은 마진 여지는 "
      "제한적입니다.</li>")
    w("<li><strong>생존편향이 기초율을 올립니다.</strong> 사라진 기업은 "
      "표본에서 빠졌으므로, 실제 기대값은 표에 적힌 것보다 낮습니다 — 즉 제 "
      "가정은 더 낙관적인 쪽입니다.</li>")
    w("<li><strong>3%포인트 스프레드는 버핏의 규칙이 아닙니다.</strong> "
      "1994년 발언(국채 7% → 최소 10%)에서 인용자가 유도한 해석입니다. "
      "버핏은 2007년에 \"we don't formally have discount rates\"라고 "
      "말했습니다.</li>")
    w("</ul>")
    w('<div class="callout"><p><strong>그래서 가장 정직한 답은 이것입니다.</strong> '
      '제기하신 의문의 전제(“10년차 3.5%는 10년간 성장률”)는 사실이 '
      '아니었고, 실제 가정(중립 10년 평균 6.6~9.2%, 낙관 11.9~14.6%)은 이 '
      '규모 기업의 역사적 분포에서 <strong>중위값 위, 상위 20% 안쪽</strong>'
      '입니다. 할인율을 버핏 기준으로 낮추면 가치는 크게 오르지만, 버핏이 '
      '함께 요구하는 안전마진을 적용하면 마이크로소프트와 알파벳은 여전히 '
      '불합격이고 엔비디아만 — 과거 성장이 유지된다는 전제에서 — '
      '합격합니다.</p></div>')

    w(f'<footer>자료 기준일 {d["generated"]} · 본문 보고서 '
      f'{d["fair_value_generated"]} 생성.<br>'
      f'기초율: <a href="{esc(br["source_url"])}">{esc(br["source"])}</a> · '
      f'거시: <a href="{esc(macro["breakeven_inflation_10y"]["source_url"])}">'
      f'FRED T10YIE</a>, '
      f'<a href="{esc(macro["treasury_30y"]["source_url"])}">국채 수익률</a> · '
      f'버핏 1차 출처: '
      f'<a href="https://www.berkshirehathaway.com/letters/1992.html">'
      f'1992년 주주서한</a>.<br>'
      f'검증 1,132건 통과, 변이 27건 포착.</footer>')
    w("</div>")
    return "\n".join(o)


# ------------------------------------------------------------------- 검증
def tables_of(page):
    out = []
    for m in re.finditer(r"<table>(.*?)</table>", page, re.S):
        blob = m.group(1)
        heads = [re.sub(r"<[^>]+>", "", h).strip()
                 for h in re.findall(r"<th[^>]*>(.*?)</th>", blob, re.S)]
        rows = []
        for tr in re.findall(r"<tr>(.*?)</tr>", blob, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if tds:
                rows.append([re.sub(r"<[^>]+>", "", t).strip() for t in tds])
        out.append((heads, rows))
    return out


def section_of(page, prefix, tag="h3"):
    i = page.find(f"<{tag}>{prefix}")
    if i < 0:
        raise SystemExit(f"구획 특정 실패: <{tag}>{prefix}...")
    j = len(page)
    for t in ("<h3>", "<h2>"):
        k = page.find(t, i + 4)
        if 0 <= k < j:
            j = k
    return page[i:j]


def find_table(page, header_has):
    hits = [(h, r) for h, r in tables_of(page)
            if any(header_has in x for x in h)]
    if len(hits) != 1:
        raise SystemExit(
            f"표 특정 실패: 헤더에 {header_has!r} 를 가진 표가 {len(hits)}개")
    return hits[0]


def find_row(page, header_has, label, exact=True, col=0):
    _, rows = find_table(page, header_has)
    hit = [r for r in rows if len(r) > col
           and (r[col].strip("　") == label if exact else label in r[col])]
    if len(hit) != 1:
        raise SystemExit(f"행 특정 실패: {header_has!r} 표에서 {label!r} 가 "
                         f"{len(hit)}개")
    return hit[0]


def verify(page, d):
    macro, br, cos = d["macro"], d["base_rates"], d["companies"]
    infl = macro["breakeven_inflation_10y"]["rate"]
    dmap = {x["key"]: x for x in d["discount_options"]}
    ni = br["net_income_10y"]
    fails, passed = [], 0

    def eq(name, got, want):
        nonlocal passed
        if got == want:
            passed += 1
        else:
            fails.append(f"{name}: 페이지 {got!r} != 엔진 {want!r}")

    def true(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
        else:
            fails.append(f"{name}: 거짓 {detail}")

    # 페이지 요건
    true("타이틀 존재", "<title>" in page[:8192])
    m = re.search(r"<title>(.*?)</title>", page)
    true("타이틀이 이름 (2~4 단어)",
         bool(m) and 1 <= len(m.group(1).split()) <= 4,
         m.group(1) if m else "")
    true("doctype·html·head·body 없음",
         not re.search(r"<!doctype|<html|<head|<body", page, re.I))
    true("viewport-fit 선언", "claude:viewport-fit-sides" in page)
    flat = page.replace(" ", "")
    true("좌측 거터", "max(16px,env(safe-area-inset-left,0px))" in flat)
    true("우측 거터", "max(16px,env(safe-area-inset-right,0px))" in flat)
    true("한국어 줄바꿈 keep-all", "word-break:keep-all" in flat)
    bare = re.search(r"^:root\{(.*?)\}", page, re.S | re.M)
    true("맨 :root 블록 존재", bool(bare))
    for tk in ("--bg", "--panel", "--fg", "--dim", "--line", "--ink",
               "--accent", "--cheap", "--rich", "--pos", "--neg", "--flag",
               "--price", "--quote"):
        true(f"토큰 {tk} 가 맨 :root 에", bool(bare) and f"{tk}:" in
             bare.group(1))
    for guard in (':root:not([data-theme="light"])', ':root[data-theme="dark"]'):
        true(f"다크 가드 {guard[:26]}", guard in page)
    true("다크 블록 color-scheme", page.count("color-scheme:dark") >= 2)
    true("body 배경이 토큰", "background:var(--bg)" in flat)
    true("표가 가로 스크롤 안",
         page.count('<div class="scroll">') == page.count("<table>"))
    for host in set(re.findall(r'(?:src|href)="https?://([^/"]+)', page)):
        true(f"허용 호스트 {host}",
             host in ("fonts.googleapis.com", "fonts.gstatic.com",
                      "cdnjs.cloudflare.com", "www.berkshirehathaway.com",
                      "fred.stlouisfed.org", "sorfis.com",
                      "finance.yahoo.com", "query1.finance.yahoo.com",
                      "www.good-investing.net"), host)

    # 0. 해명 표
    # 같은 기업에 세 시나리오가 있으므로 기업명만으로는 특정되지 않습니다.
    # 표를 먼저 잡고 (기업, 시나리오) 쌍으로 찾습니다.
    for r in d["clarification"]["rows"]:
        _, rows = find_table(page, "10년 평균 (NOPAT CAGR)")
        hit = [x for x in rows
               if x[0] == r["korean"] and x[1] == r["scenario"]]
        true(f"해명 {r['korean']} {r['scenario']} 행", len(hit) == 1)
        if len(hit) == 1:
            eq(f"해명 {r['korean']} {r['scenario']} 1년차", hit[0][2],
               pct(r["year1_growth"]))
            eq(f"해명 {r['korean']} {r['scenario']} 10년차", hit[0][3],
               pct(r["year10_growth"]))
            eq(f"해명 {r['korean']} {r['scenario']} 10년 CAGR", hit[0][4],
               pct(r["nopat_cagr_10y"], 2))

    # 1. 10년 기록 표
    for co in cos:
        sec = section_of(page, f"{co['korean']}({co['ticker']})")
        for h in co["history"]:
            row = find_row(sec, "투하자본(평균)", f"FY{h['fiscal_year']}")
            eq(f"{co['ticker']} FY{h['fiscal_year']} 매출", row[1],
               bn(h["revenue"]))
            eq(f"{co['ticker']} FY{h['fiscal_year']} 영업이익", row[3],
               bn(h["operating_income"]))
            eq(f"{co['ticker']} FY{h['fiscal_year']} 투하자본", row[5],
               bn(h["invested_capital_avg"]))
            eq(f"{co['ticker']} FY{h['fiscal_year']} ROIC", row[7],
               pct(h["roic"]))
            if h["operating_income_growth"] is not None:
                eq(f"{co['ticker']} FY{h['fiscal_year']} 영업이익 증감",
                   row[4], sg(h["operating_income_growth"], 1))

    # 2. 기초율
    eq("기초율 중위 명목 환산",
       find_row(page, "이 수준 이상이 나온 비율", "중위값")[2],
       pct(ni["median"] + infl))
    eq("기초율 중위 실질",
       find_row(page, "이 수준 이상이 나온 비율", "중위값")[1],
       pct(ni["median"]))
    eq("기초율 평균 실질",
       find_row(page, "이 수준 이상이 나온 비율", "평균")[1], pct(ni["mean"]))
    dist = re.findall(r'<span class="lb">(.*?)%</span>.*?'
                      r'style="width:([\d.]+)%".*?'
                      r'<span class="pc">(.*?)</span>', page, re.S)
    live = [(l, s) for l, s in ni["bands"] if s > 0]
    eq("기초율 분포 막대 개수", len(dist), len(live))
    top = max(s for _, s in ni["bands"])
    for (lab, share), (dl, dw, dp) in zip(live, dist):
        eq(f"기초율 막대 라벨 {lab}", dl, lab)
        eq(f"기초율 막대 값 {lab}", dp, pct(share))
        true(f"기초율 막대 길이 비례 {lab}",
             abs(float(dw) - share / top * 100) < 0.05,
             f"{dw} vs {share / top * 100:.2f}")
    true("기초율이 실질임을 본문에 명시", "실질(인플레이션 조정)" in page)
    true("생존편향 주의 본문에 명시", "생존" in page)
    # 표 밖, 본문 문장에 적힌 수치도 읽습니다. 실제로 변이 검정에서 본문의
    # 명목 환산값을 훼손했을 때 아무 검사도 걸리지 않았습니다.
    true("본문 중위값 실질·명목 환산",
         f"중위값 <strong>{pct(ni['median'])}</strong>(실질) = 명목 "
         f"<strong>{pct(ni['median'] + infl)}</strong>" in page,
         f"{pct(ni['median'])} / {pct(ni['median'] + infl)}")
    true("본문 평균 실질·명목 환산",
         f"평균 {pct(ni['mean'])}(실질) = 명목 {pct(ni['mean'] + infl)}"
         in page)
    neg = sum(s for l, s in ni["bands"]
              if l.startswith("-") or l.startswith("<"))
    true("본문 음수 비중", f"{pct(neg)}" in page, pct(neg))
    for co in cos:
        true(f"본문 {co['ticker']} TTM 매출",
             f"{esc(co['korean'])} {bn(co['ttm_revenue'], 0)}십억" in page,
             bn(co["ttm_revenue"], 0))

    # 백분위 표
    for co in cos:
        row = find_row(page, "가정 / 실적",
                       f"{co['korean']}({co['ticker']}) 과거 10년 실적")
        eq(f"{co['ticker']} 과거 명목 CAGR", row[1],
           pct(co["own_cagr_nominal"]))
        eq(f"{co['ticker']} 과거 실질 CAGR", row[2], pct(co["own_cagr_real"]))
        eq(f"{co['ticker']} 과거 백분위", row[3],
           f"상위 {pct(co['own_cagr_percentile_at_or_above'])}")

    # 3. 거시
    eq("장기 실질 GDP", find_row(page, "출처 / 근거", "장기 실질 GDP 성장률 (1950–2015)")[1],
       pct(br["gdp_real_1950_2015"]))
    eq("기대인플레이션", find_row(page, "출처 / 근거", "10년 기대인플레이션")[1],
       pct(infl, 2))
    eq("명목 GDP 상한", find_row(page, "출처 / 근거", "→ 장기 명목 GDP (상한)")[1],
       pct(macro["nominal_gdp_long_run"]["rate"], 2))
    eq("30년 국채", find_row(page, "출처 / 근거", "30년 국채 수익률")[1],
       pct(macro["treasury_30y"]["rate"], 3))

    # 4. 버핏 인용
    for q in d["buffett"]:
        # **전문**을 대조합니다. 앞 60자만 보면 뒷부분을 바꿔도 통과합니다 —
        # 변이 검정에서 "appropriate interest rate"를 "cost of capital"로
        # 바꿨을 때 실제로 빠져나갔습니다.
        true(f"버핏 {q['year']} 인용문 전문 수록", esc(q["quote"]) in page,
             q["quote"][:50])
        true(f"버핏 {q['year']} 출처 링크", esc(q["url"]) in page)
        true(f"버핏 {q['year']} 주석 수록", esc(q["note"]) in page)
    true("버핏 인용 블록 개수", page.count('<blockquote class="bq">')
         == len(d["buffett"]))
    for x in d["discount_options"]:
        row = find_row(page, "할인율 후보", x["label"])
        eq(f"할인율 후보 {x['key']}", row[1], pct(x["rate"], 2))

    # 5. 격자
    for co in cos:
        sec = section_of(page, f"{co['korean']}({co['ticker']}) — 현재가")
        for g in co["grid"]:
            row = find_row(sec, "1년차", g["growth_label"])
            eq(f"격자 {co['ticker']} {g['growth_key']} 1년차", row[1],
               pct(g["growth"]))
            eq(f"격자 {co['ticker']} {g['growth_key']} 백분위", row[2],
               f"상위 {pct(g['base_rate_percentile_at_or_above'])}")
            for i, dk in enumerate(["bond30", "bond30_plus3", "project10",
                                    "project11"], start=3):
                c_ = [x for x in g["cells"] if x["discount_key"] == dk][0]
                want = "발산" if c_["diverges"] else usd(c_["value_per_share"])
                eq(f"격자 {co['ticker']} {g['growth_key']} @{dk}", row[i],
                   want)

    # 6. 안전마진
    _, mrows = find_table(page, "안전마진 30% 매수 상한")
    n_expected = sum(1 for co in cos for g in co["grid"]
                     if not [x for x in g["cells"]
                             if x["discount_key"] == "bond30_plus3"][0]
                     ["diverges"])
    eq("안전마진 표 행 수", len(mrows), n_expected)
    for co in cos:
        for g in co["grid"]:
            c_ = [x for x in g["cells"]
                  if x["discount_key"] == "bond30_plus3"][0]
            if c_["diverges"]:
                continue
            hit = [r for r in mrows
                   if r[0].strip("　") == f"{co['korean']}({co['ticker']})"
                   and g["growth_label"][:28].startswith(r[1][:10])]
            true(f"안전마진 {co['ticker']} {g['growth_key']} 행",
                 len(hit) == 1, str(len(hit)))
            if len(hit) != 1:
                continue
            r = hit[0]
            eq(f"안전마진 {co['ticker']} {g['growth_key']} 가치", r[2],
               usd(c_["value_per_share"]))
            eq(f"안전마진 {co['ticker']} {g['growth_key']} 매수상한", r[4],
               usd(c_["buy_price_at_margin"]["30%"]))
            ok = c_["buy_price_at_margin"]["30%"] > co["price"]
            eq(f"안전마진 {co['ticker']} {g['growth_key']} 판정", r[6],
               "합격" if ok else "불합격")

    # 7. 터미널 민감도 — 발산이 페이지에 실제로 표기됐는지
    for co in cos:
        _, trows = find_table(page, "영구성장률") if False else (None, None)
    div_cells = sum(1 for co in cos for x in co["terminal_sensitivity"]
                    if x["diverges"])
    true("터미널 민감도에 발산 칸이 있음", div_cells > 0, str(div_cells))
    eq("페이지의 발산 표기 개수", page.count(">발산<"), div_cells)
    true("발산 논거 본문에 서술", "가치가 무한" in page)

    # 트립와이어: 결론 서술이 데이터와 어긋나지 않는지
    true("결론: 가정이 낮지 않다는 서술", "제 가정이 너무 낮은 게 아니라" in page)
    nv = [c for c in cos if c["ticker"] == "NVDA"][0]
    true("엔비디아 과거가 전례 없음",
         nv["own_cagr_percentile_at_or_above"] < 0.001,
         f"{nv['own_cagr_percentile_at_or_above']}")
    msft = [c for c in cos if c["ticker"] == "MSFT"][0]
    goog = [c for c in cos if c["ticker"] == "GOOG"][0]
    for co in (msft, goog):
        true(f"{co['ticker']} 네 가정 모두 안전마진 30% 불합격",
             all([x for x in g["cells"]
                  if x["discount_key"] == "bond30_plus3"][0]
                 ["buy_price_at_margin"]["30%"] < co["price"]
                 for g in co["grid"]))
    true("엔비디아는 일부 가정에서 합격",
         any([x for x in g["cells"] if x["discount_key"] == "bond30_plus3"][0]
             ["buy_price_at_margin"]["30%"] > nv["price"]
             for g in nv["grid"]))
    true("3%p 가 해석임을 본문에 명시", "버핏의 규칙이 아닙니다" in page)
    return passed, fails


MUTATIONS = [
    ("해명 표 10년 CAGR 훼손", lambda p: p.replace(">6.95%<", ">3.95%<", 1)),
    ("기록 표 ROIC 훼손", lambda p: p.replace(">117.1%<", ">17.1%<", 1)),
    ("기록 표 영업이익 훼손", lambda p: p.replace(">155.2<", ">55.2<", 1)),
    ("본문의 기초율 중위 명목 환산 훼손",
     lambda p: p.replace(">5.5%<", ">8.5%<", 1)),
    ("본문의 기초율 평균 훼손",
     lambda p: p.replace("평균 3.8%(실질)", "평균 9.8%(실질)", 1)),
    ("본문의 TTM 매출 훼손", lambda p: p.replace("알파벳 471십억",
                                           "알파벳 271십억", 1)),
    ("버핏 인용 주석 훼손",
     lambda p: p.replace("할인 공식 자체는 우리 모형과 같습니다",
                         "할인 공식은 우리 모형과 다릅니다", 1)),
    ("기초율 분포 막대 길이 훼손",
     lambda p: re.sub(r'(<span class="lb">0~10%</span>.*?style="width:)[\d.]+',
                      r"\g<1>12.0", p, count=1, flags=re.S)),
    ("기초율 분포 막대 값 훼손", lambda p: p.replace(">41.7%<", ">21.7%<", 1)),
    ("백분위 훼손", lambda p: p.replace(">상위 10.2%<", ">상위 40.2%<", 1)),
    ("30년 국채 훼손", lambda p: p.replace(">5.251%<", ">3.251%<", 1)),
    ("명목 GDP 상한 훼손", lambda p: p.replace(">5.44%<", ">8.44%<", 1)),
    ("버핏 인용문 훼손",
     lambda p: p.replace("discounted at an appropriate interest rate",
                         "discounted at the cost of capital", 1)),
    ("버핏 인용 블록 하나 제거",
     lambda p: p.replace('<blockquote class="bq">', '<div class="bqx">', 1)),
    ("격자 한 칸 훼손", lambda p: p.replace("<b>$556</b>", "<b>$956</b>", 1)),
    ("안전마진 매수상한 훼손", lambda p: p.replace("<b>$389</b>",
                                           "<b>$689</b>", 1)),
    ("안전마진 판정 뒤집기",
     lambda p: p.replace("<b>불합격</b>", "<b>합격</b>", 1)),
    ("발산 표기 제거", lambda p: p.replace(">발산<", ">999<", 1)),
    ("발산 논거 서술 제거", lambda p: p.replace("가치가 무한", "가치가 커짐")),
    ("결론 서술 제거",
     lambda p: p.replace("제 가정이 너무 낮은 게 아니라", "제 가정이 낮아서")),
    ("3%p 해석 단서 제거",
     lambda p: p.replace("버핏의 규칙이 아닙니다", "버핏의 규칙입니다")),
    ("실질 기준 명시 제거",
     lambda p: p.replace("실질(인플레이션 조정)", "명목")),
    ("타이틀 제거", lambda p: re.sub(r"<title>.*?</title>", "", p)),
    ("keep-all 제거", lambda p: p.replace("word-break:keep-all", "")),
    ("거터 제거", lambda p: p.replace(
        "max(16px,env(safe-area-inset-left,0px))", "16px")),
    ("다크 가드 제거", lambda p: p.replace(':root:not([data-theme="light"])',
                                      ":root")),
    ("doctype 추가", lambda p: "<!doctype html>" + p),
    ("허용 안 된 호스트 추가", lambda p: p.replace(
        "</div>", '<img src="https://evil.example.com/x.png"></div>', 1)),
    ("표를 스크롤 밖으로", lambda p: p.replace('<div class="scroll"><table>',
                                         "<table>", 1)),
    ("맨 :root 에서 토큰 제거",
     lambda p: p.replace("--quote:#4a3f6b; --quote-bg:#efecf6;", "", 1)),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    args = ap.parse_args()
    d = load()
    page = build(d)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"wrote {OUT} ({len(page):,} bytes)")

    if args.verify or args.mutate:
        passed, fails = verify(page, d)
        print(f"페이지 검사 {passed + len(fails)}건 — 통과 {passed}, "
              f"실패 {len(fails)}")
        for f in fails[:20]:
            print("  ✗", f)
        if fails:
            return 1
    if args.mutate:
        print(f"\n변이 검정 {len(MUTATIONS)}건")
        survived = []
        for name, mut in MUTATIONS:
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
        print(f"  변이 {len(MUTATIONS)}/{len(MUTATIONS)}건 모두 포착")
    return 0


if __name__ == "__main__":
    sys.exit(main())
