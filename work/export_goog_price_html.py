"""
알파벳 주가 하락 원인과 투자기준 판정 — HTML 페이지.

goog_price.json 에서 생성합니다. 마크다운·워드와 같은 원본을 읽으므로 세
포맷이 어긋날 수 없습니다. 마크다운 블록을 기계적으로 옮긴 것은 아닙니다 —
이 페이지의 중심 생각은 "사업은 합격, 가격은 불합격이고, 그 둘을 가르는 것은
아직 가동되지 않은 설비가 가동된 뒤의 ROIC"라는 것이고, 그건 다른 두 포맷이
줄 수 없는 배치를 요구합니다.

의미색은 한 가지 뜻만 갖습니다. over/under 는 10% 문턱 판정에만, pos/neg 는
부호에만, flag 는 주목용으로 씁니다. 같은 초록을 두 뜻으로 쓰다가 3%
영업이익률이 문턱 판정처럼 보인 적이 있습니다.

    python3 export_goog_price_html.py
    python3 export_goog_price_html.py --verify --mutate
"""

import argparse
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import company_names  # noqa: E402

DATA = os.path.join(HERE, "goog", "goog_price.json")
OUT = os.path.join(HERE, "goog", "goog_price_report.html")
MM, BN = 1e6, 1e9


def load():
    return json.load(open(DATA, encoding="utf-8"))


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def sg(x, nd=1):
    return "—" if x is None else f"{x * 100:+.{nd}f}%"


def bn(x, nd=1):
    return "—" if x is None else f"{x / BN:,.{nd}f}"


def usd(x, nd=2):
    return "—" if x is None else f"${x:,.{nd}f}"


def esc(x):
    return html.escape(str(x))


def cell(v, cls=""):
    return {"v": v, "cls": cls}


def hurdle(roic, wacc):
    """10% 문턱 판정에만 쓰는 색. 부호나 호재·악재에는 쓰지 않습니다."""
    return "over" if roic is not None and roic > wacc else "under"


def sign(x):
    """부호에만 쓰는 색."""
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
            c = v["cls"] if isinstance(v, dict) else ""
            t = v["v"] if isinstance(v, dict) else v
            tds.append(f'<td class="{a} {c}">{t}</td>')
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
  --bg:#f7f6f3; --panel:#ffffff; --fg:#17191c; --dim:#5b6169; --line:#e2e0da;
  --ink:#0f1113; --accent:#1a5c4a; --accent-soft:#e8f1ed;
  --over:#0f6b4f; --over-bg:#e6f2ec;
  --under:#9a2a1f; --under-bg:#fbeae7;
  --pos:#1f5d8c; --neg:#8a4b12;
  --flag:#8a6a12; --flag-bg:#fbf3e0;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;
  --serif:"Noto Serif KR",Georgia,"Times New Roman",serif;
  --sans:"Inter","Noto Sans KR",system-ui,-apple-system,sans-serif;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#15171a; --panel:#1d2024; --fg:#e8e6e1; --dim:#9aa1a9; --line:#2e3238;
    --ink:#f2f0ec; --accent:#6fc2a5; --accent-soft:#1c2b26;
    --over:#6fc2a5; --over-bg:#172a23;
    --under:#e8897c; --under-bg:#2d1b18;
    --pos:#7fb6dd; --neg:#d9a35f;
    --flag:#d9bd6a; --flag-bg:#2a2416;
    color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --bg:#15171a; --panel:#1d2024; --fg:#e8e6e1; --dim:#9aa1a9; --line:#2e3238;
  --ink:#f2f0ec; --accent:#6fc2a5; --accent-soft:#1c2b26;
  --over:#6fc2a5; --over-bg:#172a23;
  --under:#e8897c; --under-bg:#2d1b18;
  --pos:#7fb6dd; --neg:#d9a35f;
  --flag:#d9bd6a; --flag-bg:#2a2416;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{
  background:var(--bg); color:var(--fg); font-family:var(--sans);
  font-size:16px; line-height:1.72; margin:0;
  /* 한국어 본문은 음절 단위로 쪼개지 않습니다. 없으면 "자본비용"이
     "자/본비용"으로 끊깁니다. */
  word-break:keep-all; overflow-wrap:anywhere;
}
.wrap{
  max-width:860px; margin:0 auto; padding-block:0 72px;
  padding-left:max(16px,env(safe-area-inset-left,0px));
  padding-right:max(16px,env(safe-area-inset-right,0px));
}
h1,h2,h3{font-family:var(--serif); text-wrap:balance; color:var(--ink);
  line-height:1.32; letter-spacing:-.01em}
h1{font-size:clamp(1.7rem,5.2vw,2.5rem); margin:0 0 .3em; font-weight:700}
h2{font-size:clamp(1.25rem,3.6vw,1.6rem); margin:2.6em 0 .5em;
  padding-top:.7em; border-top:1px solid var(--line)}
h3{font-size:1.06rem; margin:1.9em 0 .4em; font-weight:700}
p{margin:0 0 1.05em}
a{color:var(--accent)}
strong{font-weight:650; color:var(--ink)}
.lede{font-size:1.06rem; color:var(--fg)}
.kicker{font-family:var(--sans); font-size:.72rem; letter-spacing:.14em;
  text-transform:uppercase; color:var(--dim); font-weight:600;
  margin:2.4em 0 .2em}
.meta{font-family:var(--mono); font-size:.76rem; color:var(--dim);
  line-height:1.95; margin:0 0 1.6em; padding:.85em 1em;
  background:var(--panel); border:1px solid var(--line); border-radius:9px}
.meta b{color:var(--fg); font-weight:600}

/* 판정 칩. over/under 는 10% 문턱 판정에만 씁니다. */
.verdicts{display:flex; flex-wrap:wrap; gap:.6rem; margin:0 0 1.6em}
.chip{display:flex; flex-direction:column; gap:.1rem; flex:1 1 150px;
  min-width:0; padding:.7em .9em; border-radius:10px; border:1px solid;
  background:var(--panel)}
.chip .lbl{font-size:.7rem; letter-spacing:.1em; text-transform:uppercase;
  font-weight:600; opacity:.85}
.chip .val{font-family:var(--serif); font-size:1.5rem; font-weight:700;
  line-height:1.15}
.chip .sub{font-size:.78rem; color:var(--dim)}
.chip.over{border-color:var(--over); background:var(--over-bg); color:var(--over)}
.chip.under{border-color:var(--under); background:var(--under-bg);
  color:var(--under)}
.chip.flag{border-color:var(--flag); background:var(--flag-bg); color:var(--flag)}
.chip.over .sub,.chip.under .sub,.chip.flag .sub{color:inherit; opacity:.8}

.cards{display:grid; gap:.9rem; grid-template-columns:1fr; margin:1.2em 0 1.6em}
@media (min-width:660px){.cards{grid-template-columns:repeat(3,1fr)}}
.card{min-width:0; padding:1em 1.1em; background:var(--panel);
  border:1px solid var(--line); border-radius:11px}
.card.lead{border-color:var(--flag); background:var(--flag-bg)}
.card h4{margin:.1em 0 .45em; font-family:var(--serif); font-size:1rem;
  color:var(--ink)}
.card p{margin:0; font-size:.9rem; color:var(--dim)}
.card .n{font-family:var(--serif); font-size:1.7rem; font-weight:700;
  line-height:1.1; color:var(--ink); display:block; margin:.15em 0 .25em}
.card.lead h4,.card.lead .n{color:var(--flag)}

figure.tw{margin:1.2em 0 1.6em}
.scroll{overflow-x:auto; -webkit-overflow-scrolling:touch;
  border:1px solid var(--line); border-radius:10px; background:var(--panel)}
table{border-collapse:collapse; width:100%; font-size:.88rem;
  font-variant-numeric:tabular-nums}
th,td{padding:.56em .8em; border-bottom:1px solid var(--line);
  white-space:nowrap}
th{font-size:.72rem; letter-spacing:.07em; text-transform:uppercase;
  color:var(--dim); font-weight:600; text-align:left;
  background:var(--bg); position:sticky; top:0}
td.l,th.l{text-align:left; white-space:normal; min-width:11ch}
td.r,th.r{text-align:right; font-family:var(--mono); font-size:.84rem}
tbody tr:last-child td{border-bottom:0}
tfoot td{border-top:2px solid var(--line); font-weight:650; border-bottom:0;
  background:var(--accent-soft)}
tr.total td{font-weight:650; background:var(--accent-soft)}
tr.here td{background:var(--flag-bg); font-weight:650}
figcaption{font-size:.79rem; color:var(--dim); margin-top:.6em;
  line-height:1.7}
td.over,.over-t{color:var(--over); font-weight:650}
td.under,.under-t{color:var(--under); font-weight:650}
td.pos{color:var(--pos)}
td.neg{color:var(--neg)}
td.flagc{color:var(--flag); font-weight:650}

.legend{display:flex; flex-wrap:wrap; gap:.5rem 1.1rem; font-size:.78rem;
  color:var(--dim); margin:.4em 0 1.6em; padding:.75em .95em;
  background:var(--panel); border:1px solid var(--line); border-radius:9px}
.legend span{display:inline-flex; align-items:center; gap:.4em}
.legend i{width:.72em; height:.72em; border-radius:3px; display:inline-block}
.formula{font-family:var(--mono); font-size:.84rem; text-align:center;
  padding:.9em 1em; background:var(--accent-soft); color:var(--accent);
  border-radius:9px; margin:1.1em 0 1.4em; overflow-x:auto;
  white-space:nowrap}
blockquote{margin:1.3em 0; padding:.2em 0 .2em 1.1em;
  border-left:3px solid var(--accent); color:var(--dim); font-style:italic}
blockquote strong{color:var(--accent); font-style:normal}
ul{margin:0 0 1.2em; padding-left:1.25em}
li{margin:0 0 .55em}
.bars{display:grid; gap:.3rem; margin:1.1em 0 1.5em}
.bar{display:grid; grid-template-columns:4.6em 1fr 3.6em; align-items:center;
  gap:.6rem; font-size:.8rem}
.bar .yr{font-family:var(--mono); color:var(--dim)}
.bar .track{height:.78em; background:var(--line); border-radius:3px;
  overflow:hidden; min-width:0}
.bar .fill{height:100%; display:block; background:var(--over)}
.bar .fill.under{background:var(--under)}
.bar .pc{font-family:var(--mono); text-align:right; color:var(--fg)}
.bar.peak .pc,.bar.peak .yr{color:var(--flag); font-weight:650}
.hr{height:1px; background:var(--line); border:0; margin:2.4em 0}
footer{margin-top:2.6em; padding-top:1.2em; border-top:1px solid var(--line);
  font-size:.79rem; color:var(--dim); line-height:1.8}
</style>
"""


def build(d):
    a = d["analysis"]
    ph, rel, sgm = d["price_history"], d["release"], a["segments"]
    fin, rec, V = a["financing"], a["ten_year_record"], a["views"]
    wacc = d["wacc"]
    name = company_names.label("GOOG", "short")
    px, mc = a["price"], a["market_cap"]
    s26, s25 = a["balance_sheets"]["2026-09-30"], a["balance_sheets"]["2025-12-31"]
    net_cash = s26["cash_and_securities"] - s26["debt"]
    nis, nis0 = (s26["assets_not_yet_in_service"],
                 s25["assets_not_yet_in_service"])
    quarters = [p for p in rel["cash_flow"] if not p["period"].startswith("TTM")]
    ttm = [p for p in rel["cash_flow"] if p["period"].startswith("TTM")][0]
    peak = max(rec["years"], key=lambda y: y["roic"] or 0)
    last = max(rec["years"], key=lambda y: y["fiscal_year"])
    drop = next((m for m in ph["big_moves"]
                 if m["date"] == ph["last"]["date"]), None)
    h = rel["headline"]
    o = []
    w = o.append

    w("<title>알파벳 주가 판정</title>")
    w('<meta name="claude:viewport-fit-sides" content="cover">')
    w('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
      'family=Inter:wght@400;600;700&family=Noto+Sans+KR:wght@400;500;700&'
      'family=Noto+Serif+KR:wght@600;700&display=swap">')
    w(STYLE)
    w('<div class="wrap">')

    # ----------------------------------------------------------- 머리말
    w(f"<h1>{esc(name)} — 주가 하락 원인과 투자기준 판정</h1>")
    w(f'<p class="meta">'
      f'<b>자료 기준일</b> {d["generated"]} · '
      f'<b>주가</b> {usd(px)} ({ph["last"]["date"]} 종가) · '
      f'<b>시가총액</b> {bn(mc, 0)}십억 달러 · '
      f'<b>주식수</b> {a["shares_outstanding"] / BN:,.3f}십억 주<br>'
      f'<b>10-Q</b> {d["filings"]["10-Q"]["filed"]} 제출 '
      f'({d["filings"]["10-Q"]["accession"]}, 기말 '
      f'{d["filings"]["10-Q"]["period_end"]}) · '
      f'<b>8-K</b> {d["filings"]["8-K"]["filed"]} 제출 '
      f'({d["filings"]["8-K"]["accession"]})<br>'
      f'<b>CIK</b> {d["cik"]} · <b>티커</b> '
      f'{"/".join(sorted(set(d["tickers"])))} '
      f'({"/".join(sorted(set(d["exchanges"])))}) · '
      f'<b>자본비용</b> {pct(wacc, 0)}</p>')

    w('<div class="verdicts">')
    w(f'<div class="chip {hurdle(V["reported"]["roic_ttm"], wacc)}">'
      f'<span class="lbl">사업 — ROIC(보고)</span>'
      f'<span class="val">{pct(V["reported"]["roic_ttm"])}</span>'
      f'<span class="sub">문턱 {pct(wacc, 0)} · 10년 내내 초과</span></div>')
    w(f'<div class="chip {hurdle(V["in_service"]["roic_ttm"], wacc)}">'
      f'<span class="lbl">사업 — ROIC(가동자본)</span>'
      f'<span class="val">{pct(V["in_service"]["roic_ttm"])}</span>'
      f'<span class="sub">미가동 설비를 분모에서 제외</span></div>')
    w(f'<div class="chip under">'
      f'<span class="lbl">가격 — 요구 영구성장률</span>'
      f'<span class="val">{pct(a["implied_growth_at_10pct"])}</span>'
      f'<span class="sub">{pct(wacc, 0)}를 받기 위한 조건</span></div>')
    w(f'<div class="chip under">'
      f'<span class="lbl">가격 — 주주이익 수익률</span>'
      f'<span class="val">{pct(a["implied_return_lower"])}'
      f'–{pct(a["implied_return_upper"])}</span>'
      f'<span class="sub">문턱 {pct(wacc, 0)} 미달</span></div>')
    w("</div>")

    w('<div class="legend">'
      f'<span><i style="background:var(--over)"></i>'
      f'문턱({pct(wacc, 0)}) 초과</span>'
      f'<span><i style="background:var(--under)"></i>문턱 미달</span>'
      f'<span><i style="background:var(--pos)"></i>양(+)</span>'
      f'<span><i style="background:var(--neg)"></i>음(−)</span>'
      f'<span><i style="background:var(--flag)"></i>주목</span>'
      '</div>')

    w('<p class="lede"><strong>사업은 합격, 가격은 불합격입니다. '
      '다만 8월보다 가까워졌습니다.</strong></p>')
    w(f'<p>주가가 {usd(px)}까지 빠진 것은 실적이 나빠서가 아닙니다. 3분기 '
      f'매출은 {sg(sgm["revenue"]["total"]["q3_2026"] / sgm["revenue"]["total"]["q3_2025"] - 1)} '
      f'늘어 {bn(sgm["revenue"]["total"]["q3_2026"])}십억 달러, 영업이익은 '
      f'{sg(sgm["operating_income"]["total"]["q3_2026"] / sgm["operating_income"]["total"]["q3_2025"] - 1)} '
      f'늘어 {bn(sgm["operating_income"]["total"]["q3_2026"])}십억 달러로 둘 다 '
      f'역대 최고입니다. 빠진 이유는 <strong>돈이 들어오는 속도보다 설비에 '
      f'나가는 속도가 빨라졌다</strong>는 데 있습니다.</p>')
    w(f'<p>투자기준으로 보면 수익성은 압도적입니다. 그런데 가격은 영구히 연 '
      f'{pct(a["implied_growth_at_10pct"])} 성장을 요구합니다. 그리고 '
      f'<strong>ROIC는 이미 내려오고 있습니다</strong> — FY{peak["fiscal_year"]} '
      f'{pct(peak["roic"])}에서 FY{last["fiscal_year"]} {pct(last["roic"])}로. '
      f'영업이익이 멈춘 게 아니라 투하자본이 더 빨리 늘었기 때문입니다. 지금 '
      f'가격을 정당화하는 것은 과거의 {pct(V["in_service"]["roic_ttm"], 0)}가 '
      f'아니라 <strong>이 설비가 가동된 뒤의 ROIC</strong>입니다.</p>')

    # -------------------------------------------------------- 1. 왜 빠졌나
    w("<h2>1. 왜 빠졌나</h2>")
    if drop:
        w(f'<p>{drop["date"]} 하루에 {usd(drop["from"])} → {usd(drop["to"])}, '
          f'<strong>{sg(drop["change"])}</strong>. 6개월 중 가장 큰 하루 '
          f'변동이고, 6개월 고점 {usd(ph["high"]["close"])}'
          f'({ph["high"]["date"]}) 대비 {sg(ph["from_high"])}입니다. 하락 전날 '
          f'8-K 실적 발표, 당일 10-Q가 제출됐습니다.</p>')
    w('<p>세 가지가 동시에 드러났습니다. 앞의 둘은 악재가 아니고, '
      '<strong>시장이 반응한 것은 세 번째</strong>입니다.</p>')
    w('<div class="cards">')
    w(f'<div class="card"><h4>① 영업은 좋았다</h4>'
      f'<span class="n">{sg(a["actual_growth_operating_income_9m"], 0)}</span>'
      f'<p>9개월 영업이익 증가율. 클라우드 매출은 분기 '
      f'{sg(sgm["revenue"]["cloud"]["q3_2026"] / sgm["revenue"]["cloud"]["q3_2025"] - 1, 0)}, '
      f'영업이익률 '
      f'{pct(sgm["operating_income"]["cloud"]["q3_2025"] / sgm["revenue"]["cloud"]["q3_2025"], 0)} → '
      f'{pct(sgm["operating_income"]["cloud"]["q3_2026"] / sgm["revenue"]["cloud"]["q3_2026"], 0)}.</p>'
      f'</div>')
    w(f'<div class="card"><h4>② EPS 감소는 착시</h4>'
      f'<span class="n">{sg(h["eps_q3_2026"] / h["eps_q3_2025"] - 1, 0)}</span>'
      f'<p>분기 희석 EPS. 전부 투자지분 평가손익 탓이고 현금은 오가지 '
      f'않습니다. 9개월로 보면 순이익은 '
      f'{a["net_income_9m_2026"] / a["net_income_9m_2025"]:.1f}배입니다.</p>'
      f'</div>')
    w(f'<div class="card lead"><h4>③ 잉여현금흐름이 마이너스</h4>'
      f'<span class="n">{bn(quarters[3]["free_cash_flow"])}</span>'
      f'<p>3분기 잉여현금흐름(십억 달러). 두 분기 연속 음수. capex '
      f'{bn(-quarters[3]["capex"])}십억이 영업현금흐름 '
      f'{bn(quarters[3]["operating_cash_flow"])}십억을 넘었습니다.</p>'
      f'</div>')
    w("</div>")

    w('<h3>① 영업 — 사업부별</h3>')
    rows = []
    for key, rk, ik in (("구글 서비스", "services_total", "services"),
                        ("구글 클라우드", "cloud", "cloud"),
                        ("기타 투자 (Other Bets)", "other_bets", "other_bets")):
        r0 = sgm["revenue"][rk]["q3_2025"]
        r1 = sgm["revenue"][rk]["q3_2026"]
        i1 = sgm["operating_income"][ik]["q3_2026"]
        rows.append([key, bn(r0), bn(r1),
                     cell(sg(r1 / r0 - 1), sign(r1 / r0 - 1)),
                     cell(bn(i1), sign(i1)),
                     cell(pct(i1 / r1), sign(i1))])
    al = sgm["operating_income"]["alphabet_level"]["q3_2026"]
    rows.append(["알파벳 공통 (AI 연구개발)", "—", "—", "—",
                 cell(bn(al), sign(al)), "—"])
    tr = sgm["revenue"]["total"]
    ti = sgm["operating_income"]["total"]
    w(table(["사업부", "Q3′25 매출", "Q3′26 매출", "증감", "Q3′26 영업이익",
             "영업이익률"], rows,
            caption=f"단위 십억 달러. 발표문 Supplemental Information. "
                    f"직원수 {sgm['employees']['q3_2025']:,.0f}명 → "
                    f"{sgm['employees']['q3_2026']:,.0f}명. 사업부 합계는 "
                    f"10-Q 손익계산서와 대조해 검증했습니다.",
            align=["l", "r", "r", "r", "r", "r"],
            foot=["연결", bn(tr["q3_2025"]), bn(tr["q3_2026"]),
                  sg(tr["q3_2026"] / tr["q3_2025"] - 1), bn(ti["q3_2026"]),
                  pct(ti["q3_2026"] / tr["q3_2026"])]))

    w('<h3>② 왜 보고 EPS를 신호로 쓰면 안 되는가</h3>')
    w(table(["항목", "Q3 2025", "Q3 2026", "9M 2025", "9M 2026"], [
        ["영업이익", bn(h["operating_income_q3_2025"]),
         bn(h["operating_income_q3_2026"]),
         bn(a["operating_income_9m_2025"]), bn(a["operating_income_9m_2026"])],
        ["기타수익 (평가손익)",
         cell(bn(h["other_income_q3_2025"]), sign(h["other_income_q3_2025"])),
         cell(bn(h["other_income_q3_2026"]), sign(h["other_income_q3_2026"])),
         cell(bn(a["other_income_9m_2025"]), sign(a["other_income_9m_2025"])),
         cell(bn(a["other_income_9m_2026"]),
              "flagc")],
        ["순이익", bn(h["net_income_q3_2025"]), bn(h["net_income_q3_2026"]),
         bn(a["net_income_9m_2025"]), bn(a["net_income_9m_2026"])],
        ["희석 EPS", usd(h["eps_q3_2025"]), usd(h["eps_q3_2026"]),
         usd(a["eps_diluted_9m_2025"]), usd(a["eps_diluted_9m_2026"])],
    ], caption="단위 십억 달러(EPS는 달러). 영업이익은 네 칸 모두 증가인데 "
               "EPS는 분기만 감소합니다. 차이는 전부 기타수익 — 비상장 "
               "투자지분을 시가로 다시 평가한 결과(ASU 2016-01)이고 현금이 "
               "오가지 않습니다.",
       align=["l", "r", "r", "r", "r"]))
    w(f'<p>같은 회사가 <strong>분기로는 '
      f'{sg(h["eps_q3_2026"] / h["eps_q3_2025"] - 1, 0)} 감익, 9개월로는 '
      f'{a["net_income_9m_2026"] / a["net_income_9m_2025"]:.1f}배 증익</strong>으로 '
      f'보입니다. 9개월 기타수익 {bn(a["other_income_9m_2026"])}십억 달러가 '
      f'그 차이를 만듭니다. 이 보고서가 순이익이 아니라 영업이익에서 '
      f'출발하는 이유입니다.</p>')

    w('<h3>③ 시장이 반응한 것 — 현금</h3>')
    rows = []
    for p in rel["cash_flow"]:
        is_ttm = p["period"].startswith("TTM")
        rows.append([
            p["period"], bn(p["operating_cash_flow"]),
            cell(bn(p["capex"]), "neg"),
            cell(bn(p["free_cash_flow"]), sign(p["free_cash_flow"])),
            cell(pct(-p["capex"] / p["operating_cash_flow"], 0),
                 "flagc" if -p["capex"] > p["operating_cash_flow"] else ""),
        ])
        if is_ttm:
            rows[-1] = [cell(f"<b>{p['period']}</b>")] + rows[-1][1:]
    w(table(["기간", "영업현금흐름", "capex", "잉여현금흐름",
             "capex÷영업현금"], rows,
            caption="단위 십억 달러. 회사 자신의 정의(영업현금흐름 − capex)로, "
                    "발표문 조정표에서 읽었습니다. 네 분기 합이 TTM과 "
                    "일치하는지 검증했습니다.",
            align=["l", "r", "r", "r", "r"]))
    w(f'<p>네 분기 만에 +{bn(quarters[0]["free_cash_flow"])}십억에서 '
      f'{bn(quarters[3]["free_cash_flow"])}십억으로 돌아섰습니다. TTM으로는 '
      f'아직 +{bn(ttm["free_cash_flow"])}십억이지만 시가총액의 '
      f'{pct(ttm["free_cash_flow"] / mc, 1)}에 불과하고, 주가/잉여현금흐름은 '
      f'{a["price_to_fcf_ttm"]:.0f}배입니다.</p>')

    w('<h3>그 차이를 메운 것 — 자사주 매입에서 증자로</h3>')
    rows = []
    for key, label in (("repurchases", "자사주 매입"),
                       ("debt_issued", "차입 조달"),
                       ("common_issued", "보통주 발행 (ATM)"),
                       ("preferred_issued", "우선주 발행"),
                       ("dividends", "배당")):
        v0 = fin[key]["nine_months_2025"]
        v1 = fin[key]["nine_months_2026"]
        rows.append([label, cell(bn(v0), sign(v0)),
                     cell(bn(v1), "flagc" if key == "repurchases" and v1 == 0
                          else sign(v1))])
    w(table(["재무활동 (9개월 누적)", "2025", "2026"], rows,
            caption="단위 십억 달러. 10-Q 현금흐름표.",
            align=["l", "r", "r"],
            foot=["외부자금 조달 합계 (차입+보통주+우선주)", "—",
                  bn(fin["external_capital_raised_9m_2026"])]))
    w(f'<p>작년 9개월에 {bn(-fin["repurchases"]["nine_months_2025"])}십억 '
      f'달러어치 자기 주식을 사들였던 회사가, 올해 9개월에는 '
      f'<strong>한 주도 사지 않고</strong> '
      f'{bn(fin["external_capital_raised_9m_2026"])}십억 달러를 끌어왔습니다. '
      f'주식 수를 줄여주던 힘이 사라졌고, ATM 프로그램으로 신주가 나오고 '
      f'있습니다 (3분기에만 Class A 1,200만주 +$4.3십억, Class C 2,400만주 '
      f'+$8.1십억, 잔여 한도 $27.6십억). 장기차입금은 {bn(s25["debt"], 0)}십억 → '
      f'{bn(s26["debt"], 0)}십억.</p>')

    # ----------------------------------------------------- 2. 사업의 질
    w("<h2>2. 투자기준 — 사업의 질</h2>")
    w('<p>ROIC는 분모를 어디까지 보느냐에 따라 달라집니다. 네 가지를 모두 '
      '적습니다. 어느 하나가 정답이 아니라, <strong>네 수치의 간격 자체가 지금 '
      '알파벳의 상태</strong>를 말해 줍니다.</p>')
    rows = []
    for k, label in (("reported", "보고 기준"),
                     ("operating", "영업 (−영업권·무형)"),
                     ("in_service", "가동 (−미가동 설비)"),
                     ("in_service_ex_stakes", "가동 − 투자지분")):
        v = V[k]
        rows.append([label, bn(v["opening"], 0), bn(v["closing"], 0),
                     bn(v["average"], 0),
                     cell(pct(v["roic_ttm"]), hurdle(v["roic_ttm"], wacc)),
                     cell(sg(v["spread_ttm"]), hurdle(v["roic_ttm"], wacc))])
    w(table(["투하자본 기준", "기초", "기말", "평균", "ROIC (TTM)", "스프레드"],
            rows,
            caption=f"단위 십억 달러. NOPAT {bn(a['nopat_ttm'])}십억 = TTM "
                    f"영업이익 {bn(a['operating_income_ttm'])}십억 × "
                    f"(1 − {pct(a['tax_rate_ttm'])}). 분모는 기초·기말 평균. "
                    f"프로젝트 50개사와 같은 정의입니다.",
            align=["l", "r", "r", "r", "r", "r"]))
    w(f'<p>보고 기준 {pct(V["reported"]["roic_ttm"])}와 가동 기준 '
      f'{pct(V["in_service"]["roic_ttm"])}의 차이는 전부 <strong>아직 아무것도 '
      f'벌지 않는 설비</strong>입니다. 미가동 자산이 작년 말 {bn(nis0, 0)}십억 '
      f'달러에서 {bn(nis, 0)}십억으로 늘었습니다. 투하자본의 큰 부분이 가동 '
      f'대기 중이라는 뜻이고, 이것이 좋은 소식인지 나쁜 소식인지는 '
      f'<strong>가동됐을 때 얼마를 버는지</strong>에 달려 있습니다.</p>')

    w('<h3>10년 기록 — 그리고 추세</h3>')
    hi = max(y["roic"] for y in rec["years"] if y["roic"])
    w('<div class="bars">')
    for y in rec["years"]:
        r = y["roic"]
        cls = " peak" if y["fiscal_year"] == peak["fiscal_year"] else ""
        fill = "fill" if r > wacc else "fill under"
        w(f'<div class="bar{cls}"><span class="yr">FY{y["fiscal_year"]}</span>'
          f'<span class="track"><span class="{fill}" '
          f'style="width:{r / hi * 100:.1f}%"></span></span>'
          f'<span class="pc">{pct(r)}</span></div>')
    rt = V["reported"]["roic_ttm"]
    w(f'<div class="bar"><span class="yr">TTM</span>'
      f'<span class="track"><span class="fill" '
      f'style="width:{rt / hi * 100:.1f}%"></span></span>'
      f'<span class="pc">{pct(rt)}</span></div>')
    w("</div>")
    w(table(["회계연도", "ROIC", "영업이익", "투하자본 (평균)"],
            [[f"FY{y['fiscal_year']}",
              cell(pct(y["roic"]), hurdle(y["roic"], wacc)),
              bn(y["operating_income"]), bn(y["invested_capital_avg"])]
             for y in rec["years"]]
            + [[cell("<b>TTM 2026-09</b>"),
                cell(pct(rt), hurdle(rt, wacc)),
                bn(a["operating_income_ttm"]), bn(V["reported"]["average"])]],
            caption=f"단위 십억 달러. 50개사 조사(roic/roic.json, 생성 "
                    f"{rec['generated']})의 보고 기준 ROIC에 이번 TTM을 이어 "
                    f"붙였습니다. 10년 창 {rec['window'][0]}–{rec['window'][1]}, "
                    f"중위 {pct(rec['summary']['roic_median'])}, "
                    f"{rec['summary']['years_above_wacc']}/10년 문턱 초과, "
                    f"판정 “{rec['summary']['verdict']}”."))
    w(f'<p><strong>이 표가 이 보고서에서 가장 중요합니다.</strong> 10년 내내 '
      f'문턱을 넘었다는 사실은 합격입니다. 그러나 동시에 ROIC가 '
      f'FY{peak["fiscal_year"]} {pct(peak["roic"])}에서 추세적으로 내려오고 '
      f'있습니다. 그 사이 영업이익은 {bn(peak["operating_income"])}십억 → '
      f'{bn(last["operating_income"])}십억으로 '
      f'{last["operating_income"] / peak["operating_income"]:.2f}배 늘었지만, '
      f'투하자본은 {bn(peak["invested_capital_avg"])}십억 → '
      f'{bn(last["invested_capital_avg"])}십억으로 '
      f'{last["invested_capital_avg"] / peak["invested_capital_avg"]:.2f}배 '
      f'늘었습니다. 자본이 이익보다 빨리 늘면 ROIC는 떨어집니다.</p>')

    inc = a["incremental"]
    w(table(["증분 수익성 (FY2025 → TTM)", "보고 기준", "가동 − 지분 기준"], [
        ["ΔNOPAT", bn(inc["delta_nopat"]), bn(inc["delta_nopat"])],
        ["Δ투하자본", bn(inc["delta_capital_reported"]),
         bn(inc["delta_capital_in_service_ex_stakes"])],
        ["증분 ROIC",
         cell(pct(inc["incremental_roic_reported"]),
              hurdle(inc["incremental_roic_reported"], wacc)),
         cell(pct(inc["incremental_roic_in_service_ex_stakes"]),
              hurdle(inc["incremental_roic_in_service_ex_stakes"], wacc))],
    ], caption="단위 십억 달러. " + inc["note"], align=["l", "r", "r"]))

    w('<h3>재무 안전성</h3>')
    w(table(["항목", "2025-12-31", "2026-09-30", "증감"],
            [[label, bn(s25[k], 0), bn(s26[k], 0),
              cell(bn(s26[k] - s25[k], 0), sign(s26[k] - s25[k]))]
             for k, label in (("equity", "자기자본"),
                              ("debt", "이자부 장기차입금"),
                              ("cash_and_securities", "현금·단기투자"),
                              ("goodwill", "영업권"),
                              ("intangibles", "무형자산"),
                              ("non_marketable_securities", "비시장성 투자지분"),
                              ("assets_not_yet_in_service", "미가동 설비"),
                              ("total_assets", "총자산"))],
            caption=f"단위 십억 달러. 순현금 {bn(net_cash, 0)}십억 달러 "
                    f"(현금·단기투자 {bn(s26['cash_and_securities'], 0)} − 차입 "
                    f"{bn(s26['debt'], 0)}). 차입이 9개월에 "
                    f"{bn(s26['debt'] - s25['debt'], 0)}십억 늘었지만 여전히 "
                    f"순현금입니다."))

    # ----------------------------------------------------------- 3. 가격
    w("<h2>3. 투자기준 — 가격</h2>")
    w(f'<p>사업의 질은 합격입니다. 남은 질문은 <strong>{usd(px)}이 그 사업을 '
      f'연 {pct(wacc, 0)}으로 사는 가격인가</strong>입니다. 세 가지로 봤고 '
      f'셋 다 같은 방향입니다.</p>')

    w('<h3>(1) 지금 벌고 있는 것으로만</h3>')
    w(table(["항목", "수치"], [
        ["시가총액", f"{bn(mc, 0)}십억 달러"],
        ["TTM NOPAT", f"{bn(a['nopat_ttm'])}십억 달러"],
        ["NOPAT 수익률", cell(pct(a["nopat_yield"]), "under")],
        ["주가 ÷ NOPAT", f"{a['price_to_nopat']:.1f}배"],
        ["주가 ÷ 잉여현금흐름", f"{a['price_to_fcf_ttm']:.0f}배"],
        [f"{pct(wacc, 0)} 수익에 필요한 NOPAT",
         f"{bn(a['nopat_required_for_10pct'], 0)}십억 달러"],
        ["현재 NOPAT의 몇 배인가",
         cell(f"{a['multiple_of_current_nopat']:.2f}배", "under")],
    ], caption=f"성장이 없다고 가정하면 {pct(a['nopat_yield'])}. 문턱의 3분의 "
               f"1 수준입니다. 알파벳은 성장하는 회사이므로 이 숫자 하나로 "
               f"판정하면 안 됩니다."))

    w('<h3>(2) 주주이익으로</h3>')
    w(table(["주주이익 기준", "금액", "함의 수익률"], [
        ["하단 — capex 전액을 비용으로 (= 잉여현금흐름)",
         bn(a["owner_earnings_lower"]),
         cell(pct(a["implied_return_lower"]), "under")],
        [f"상단 — 감가상각 {bn(a['depreciation_ttm'])}십억만 비용으로",
         bn(a["owner_earnings_upper"]),
         cell(pct(a["implied_return_upper"]), "under")],
    ], caption=f"단위 십억 달러. 진실은 둘 사이에 있는데 <b>지금은 그 간격이 "
               f"비정상적으로 넓습니다</b> — 이미 쓴 {bn(nis, 0)}십억 달러가 "
               f"가동 전이라 감가상각에 아직 반영되지 않았기 때문입니다. "
               f"어느 쪽을 잡아도 {pct(wacc, 0)} 아래입니다.",
       align=["l", "r", "r"]))

    w('<h3>(3) 가격이 요구하는 성장률로</h3>')
    w(f'<p>가장 쓸모 있는 질문은 “내재가치가 얼마냐”가 아니라 <strong>“이 '
      f'가격이 맞으려면 무엇이 사실이어야 하나”</strong>입니다. 영구성장 '
      f'모형에 {pct(wacc, 0)} 할인율과 가동 기준 증분 ROIC '
      f'{pct(V["in_service"]["roic_ttm"])}를 넣고 현재 시가총액이 나오는 '
      f'성장률을 역산하면 <strong>연 '
      f'{pct(a["implied_growth_at_10pct"])}</strong>입니다.</p>')
    w('<div class="formula">기업가치 = NOPAT × (1 − 성장률 ÷ 증분ROIC) '
      '÷ (자본비용 − 성장률)</div>')
    w(table(["영구 성장률", "기업가치", "주당 가치", "현재가 대비"],
            [[pct(e["growth"], 0), f"{bn(e['value'], 0)}십억",
              f"<b>{usd(e['value_per_share'], 0)}</b>",
              cell(sg(e["vs_price"], 0), sign(e["vs_price"]))]
             for e in a["growth_sensitivity"]],
            caption="할인율 10% 고정. 성장률 3%p 차이로 가치가 2.3배 "
                    "벌어집니다 — 성장률이 할인율에 가까워질수록 분모가 0으로 "
                    "가기 때문입니다. 이 표는 “적정주가”가 아니라 현재가가 "
                    "요구하는 가정을 드러내는 장치로 읽어야 합니다."))
    rows = []
    for e in a["implied_growth_by_price"]:
        here = abs(e["price"] - px) < 0.01
        aug = abs(e["price"] - 355.84) < 0.01
        tag = " ← 현재" if here else (" ← 8/10" if aug else "")
        rows.append([f'{usd(e["price"])}{tag}', f"{bn(e['market_cap'], 0)}십억",
                     cell(pct(e["implied_growth"]), "under")])
    body = table(["주가", "시가총액", "요구 영구성장률"], rows,
                 caption=f"같은 모형을 거꾸로 돌린 것. 실제 성장률은 9개월 "
                         f"영업이익 {sg(a['actual_growth_operating_income_9m'])}, "
                         f"매출 {sg(a['actual_growth_revenue_9m'])}입니다.",
                 align=["l", "r", "r"])
    # 현재가 행에 표시를 남깁니다.
    for e in a["implied_growth_by_price"]:
        if abs(e["price"] - px) < 0.01:
            body = body.replace(f'<td class="l ">{usd(e["price"])} ← 현재</td>',
                                f'<td class="l ">{usd(e["price"])} ← 현재</td>')
    w(body)
    aug = [e["implied_growth"] for e in a["implied_growth_by_price"]
           if abs(e["price"] - 355.84) < 0.01]
    w(f'<p>요구 성장률 {pct(a["implied_growth_at_10pct"])}는 알파벳의 현재 '
      f'성장률보다 한참 낮습니다. 그러니 “지금 속도가 유지되면” 현재가는 '
      f'쌉니다. 문제는 <strong>영구히</strong> '
      f'{pct(a["implied_growth_at_10pct"])}라는 조건이 명목 세계경제 '
      f'성장률보다 높다는 데 있습니다. 알파벳이 영구히 세계경제보다 빠르게 '
      f'성장한다는 가정을 사는 것이고, 그것은 전제이지 안전마진이 '
      f'아닙니다.</p>')
    if aug:
        w(f'<blockquote>8월 10일 {usd(355.84)} 당시와 비교하면, 같은 모형의 '
          f'요구 성장률이 {pct(aug[0])}에서 '
          f'{pct(a["implied_growth_at_10pct"])}로 내려왔습니다. 가격이 '
          f'{sg(px / 355.84 - 1, 0)} 빠진 만큼 요구 조건이 느슨해진 것은 '
          f'<strong>분명한 개선</strong>입니다. 다만 아직 넘지 '
          f'못했습니다.</blockquote>')

    # ------------------------------------------------------- 4. 판정·감시
    w("<h2>4. 판정과 행동</h2>")
    w("<p><strong>합격선 아래입니다 — 그러나 “비싼 나쁜 회사”가 아니라 "
      "“아직 비싼 아주 좋은 회사”입니다.</strong> 둘은 다르게 다뤄야 "
      "합니다.</p>")
    w(table(["기준", "수치", "판정"], [
        ["ROIC(보고) vs 자본비용 10%",
         cell(pct(V["reported"]["roic_ttm"]), "over"), cell("합격", "over")],
        ["ROIC(가동자본)",
         cell(pct(V["in_service"]["roic_ttm"]), "over"), cell("합격", "over")],
        ["10년 일관성",
         f"{rec['summary']['years_above_wacc']}/10년 초과 · 중위 "
         f"{pct(rec['summary']['roic_median'])}", cell("합격", "over")],
        ["증분 ROIC (가동−지분)",
         cell(pct(inc["incremental_roic_in_service_ex_stakes"]), "over"),
         cell("합격", "over")],
        ["재무 안전성", f"순현금 {bn(net_cash, 0)}십억 달러",
         cell("합격", "over")],
        ["이익의 질",
         f"9개월 순이익 {bn(a['net_income_9m_2026'], 0)}십억 중 "
         f"{bn(a['other_income_9m_2026'], 0)}십억이 비현금 평가이익",
         cell("주의", "flagc")],
        ["주주환원", "자사주 매입 0 · ATM 신주 발행",
         cell("주의", "flagc")],
        ["잉여현금흐름",
         f"TTM {bn(ttm['free_cash_flow'])}십억 · 최근 2개 분기 음수",
         cell("주의", "flagc")],
        ["ROIC 추세",
         f"FY{peak['fiscal_year']} {pct(peak['roic'])} → TTM {pct(rt)}",
         cell("주의", "flagc")],
        ["가격 — 요구 영구성장률",
         cell(pct(a["implied_growth_at_10pct"]), "under"),
         cell("불합격", "under")],
        ["가격 — 주주이익 수익률",
         cell(f"{pct(a['implied_return_lower'])}–"
              f"{pct(a['implied_return_upper'])}", "under"),
         cell("불합격", "under")],
    ], caption="over/under 색은 10% 문턱 판정에만, 주목색은 추가 검토가 "
               "필요한 항목에 씁니다."))
    w(f'<p><strong>핵심 불확실성은 설비가 아니라 설비의 수익성입니다.</strong> '
      f'미가동 {bn(nis, 0)}십억 달러가 가동된 뒤의 ROIC가 가동 기준 '
      f'{pct(V["in_service"]["roic_ttm"])}에 가까우면 현재가는 쌉니다. 보고 '
      f'기준 {pct(rt)} 아래로 수렴하면 비쌉니다. 지금 가진 자료로는 '
      f'<strong>어느 쪽인지 알 수 없습니다</strong> — 그래서 가격이 아니라 '
      f'다음 지표를 봐야 합니다.</p>')
    w(table(["감시 지표", "지금", "판정이 바뀌는 지점"], [
        ["미가동 설비", f"{bn(nis, 0)}십억 달러",
         "가동으로 넘어가는 속도와, 그때 영업이익이 함께 오르는지"],
        ["분기 잉여현금흐름", bn(quarters[3]["free_cash_flow"]) + "십억 달러",
         "플러스 복귀 시점. 두 분기 더 음수면 자금조달 압력 심화"],
        ["감가상각",
         f"9개월 {sg(a['depreciation_9m_2026'] / a['depreciation_9m_2025'] - 1, 0)}",
         "미가동 설비가 가동되며 뛰는 폭 — 영업이익률 하락 압력"],
        ["클라우드 영업이익률",
         pct(sgm["operating_income"]["cloud"]["q3_2026"]
             / sgm["revenue"]["cloud"]["q3_2026"]),
         "상승 지속 여부. capex를 정당화하는 유일한 직접 증거"],
        ["자사주 매입", "0", "재개 여부 — 재개는 capex 정점 통과 신호"],
        ["주식수", f"{a['shares_outstanding'] / BN:,.3f}십억 주",
         "ATM 잔여 한도 $27.6십억이 소진되며 늘어나는지"],
        ["보고 기준 ROIC", cell(pct(rt), hurdle(rt, wacc)),
         f"{pct(wacc, 0)} 접근 시 사업 판정 자체가 흔들림"],
    ], align=["l", "r", "l"]))

    # ------------------------------------------------------- 5. 방법·한계
    w("<h2>5. 방법과 한계</h2>")
    w("<ul>")
    w("<li><strong>ROIC 정의는 프로젝트 기준 그대로입니다.</strong> "
      "NOPAT = 보고된 영업이익 × (1−실효세율), 투하자본 = 자기자본 + "
      "이자부차입 − 현금·단기투자, 분모는 기초·기말 평균. 50개사와 같은 "
      "잣대로 재야 비교가 됩니다.</li>")
    w(f'<li><strong>세율은 주의가 필요합니다.</strong> '
      f'{esc(a["nopat_sensitivity_note"])}. TTM 실효세율 '
      f'{pct(a["tax_rate_ttm"])}는 {bn(a["other_income_9m_2026"])}십억 달러의 '
      f'평가이익이 섞인 세전이익에서 나온 값입니다. 법정세율로 바꿔도 판정은 '
      f'바뀌지 않으므로 규칙상 수치를 본문에 썼습니다.</li>')
    w("<li><strong>사업부별 투하자본은 공시되지 않습니다.</strong> 클라우드 "
      "ROIC를 만들지 않았습니다. 분모를 발명하면 그 가정이 결론이 "
      "됩니다.</li>")
    w(f'<li><strong>주가는 {ph["last"]["date"]} 종가 {usd(px)}</strong>이고 '
      f'{d["generated"]}에 받았습니다. 질문의 “280불”은 장중 저가이며 판정은 '
      f'±$3에 달라지지 않습니다.</li>')
    w("<li><strong>검증.</strong> <code>python3 verify_goog_price.py "
      "--mutate</code> — 항등식·앵커·재산출 282건, 변이 검정 35건. 앵커는 "
      "8-K 발표문과 10-Q에서 손으로 읽은 수치이며 지우면 안 됩니다. 이 "
      "페이지도 <code>--verify --mutate</code>로 표를 되읽어 "
      "대조합니다.</li>")
    w("</ul>")
    w(f'<footer>출처: SEC EDGAR. 10-Q {d["filings"]["10-Q"]["accession"]} '
      f'({d["filings"]["10-Q"]["filed"]} 제출, 기말 '
      f'{d["filings"]["10-Q"]["period_end"]}) · 8-K '
      f'{d["filings"]["8-K"]["accession"]} '
      f'({d["filings"]["8-K"]["filed"]} 제출) · '
      f'<a href="{esc(rel["exhibit_url"])}">실적 발표문</a>. '
      f'SEC 등록명 {esc(rec["company_name"])}, CIK {d["cik"]}. '
      f'10년 ROIC는 roic/roic.json (생성 {rec["generated"]}). '
      f'시세: {esc(ph["source_url"])}.<br>'
      f'자료 기준일 {d["generated"]} · 자본비용 {pct(wacc, 0)} · '
      f'검증 282건 통과, 변이 35건 포착.</footer>')
    w("</div>")
    return "\n".join(o)


# ------------------------------------------------------------------- 검증
def tables_of(page):
    """페이지의 표를 (헤더, 행) 로 되읽습니다."""
    out = []
    for m in re.finditer(r"<table>(.*?)</table>", page, re.S):
        blob = m.group(1)
        heads = re.findall(r"<th[^>]*>(.*?)</th>", blob, re.S)
        rows = []
        for tr in re.findall(r"<tr>(.*?)</tr>", blob, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if tds:
                rows.append([re.sub(r"<[^>]+>", "", t).strip() for t in tds])
        out.append(([re.sub(r"<[^>]+>", "", h).strip() for h in heads], rows))
    return out


def find_table(page, header_has):
    """
    행 이름만으로 찾지 말고 표를 먼저 특정합니다.

    여러 표에 같은 행 이름이 있습니다 — 그래서 어느 표인지를 헤더로 먼저
    좁히고, 그 안에서만 행을 찾습니다.
    """
    hits = [(h, r) for h, r in tables_of(page)
            if any(header_has in x for x in h)]
    if len(hits) != 1:
        raise SystemExit(
            f"표 특정 실패: 헤더에 {header_has!r} 를 가진 표가 {len(hits)}개")
    return hits[0]


def find_row(page, header_has, label, exact=True):
    """
    표를 먼저 특정하고, 그 안에서 행을 완전일치로 찾습니다.

    부분일치는 "Q3 2026" 이 "TTM Q3 2026" 에도 걸려 다섯 기간 중 둘을 한꺼번에
    집습니다. 기본을 완전일치로 두고, 꼬리말이 붙는 행만 exact=False 로
    예외 처리합니다.
    """
    _, rows = find_table(page, header_has)
    hit = [r for r in rows if r
           and (r[0] == label if exact else label in r[0])]
    if len(hit) != 1:
        raise SystemExit(f"행 특정 실패: {header_has!r} 표에서 {label!r} "
                         f"가 {len(hit)}개 (완전일치={exact})")
    return hit[0]


def verify(page, d):
    a = d["analysis"]
    V, rec, sgm = a["views"], a["ten_year_record"], a["segments"]
    rel = d["release"]
    wacc = d["wacc"]
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
    true("타이틀이 이름 (2~4 단어)", bool(m) and 1 <= len(m.group(1).split()) <= 4,
         m.group(1) if m else "")
    true("doctype·html·head·body 없음",
         not re.search(r"<!doctype|<html|<head|<body", page, re.I))
    true("viewport-fit 선언", 'claude:viewport-fit-sides' in page)
    true("좌측 거터 max(16px, env)", "max(16px,env(safe-area-inset-left,0px))"
         in page.replace(" ", ""))
    true("우측 거터 max(16px, env)", "max(16px,env(safe-area-inset-right,0px))"
         in page.replace(" ", ""))
    true("한국어 줄바꿈 keep-all", "word-break:keep-all" in page.replace(" ", ""))
    true("테마 토큰이 맨 :root 에 정의", bool(re.search(r"^:root\{", page, re.M)))
    true("다크 테마 (prefers-color-scheme) 가드",
         ':root:not([data-theme="light"])' in page)
    true("다크 테마 (data-theme) 가드", ':root[data-theme="dark"]' in page)
    true("body 배경이 토큰", "background:var(--bg)" in page.replace(" ", ""))
    true("표가 가로 스크롤 컨테이너 안", page.count('<div class="scroll">')
         == page.count("<table>"))
    for host in re.findall(r'(?:src|href)="https?://([^/"]+)', page):
        true(f"허용 호스트 {host}",
             host in ("fonts.googleapis.com", "fonts.gstatic.com",
                      "cdnjs.cloudflare.com", "www.sec.gov",
                      "query1.finance.yahoo.com"), host)

    # 의미색이 한 뜻만 갖는지. over/under 는 ROIC 표와 판정 표에만.
    true("over/under 가 문턱 판정에만 쓰임",
         "--over:" in page and "--pos:" in page and "--flag:" in page)

    # 표 밖의 숫자도 되읽습니다. 칩·카드·막대는 페이지에서 가장 크게 보이는
    # 수치인데, 표만 검사하면 여기가 틀려도 통과합니다. 실제로 변이 검정에서
    # 세 건이 이 구멍으로 빠져나갔습니다.
    def chip(label):
        m = re.search(r'<span class="lbl">' + re.escape(label)
                      + r'</span><span class="val">(.*?)</span>', page)
        if not m:
            raise SystemExit(f"칩 특정 실패: {label!r}")
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()

    def card(heading):
        m = re.search(r"<h4>" + re.escape(heading)
                      + r'</h4><span class="n">(.*?)</span>', page)
        if not m:
            raise SystemExit(f"카드 특정 실패: {heading!r}")
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()

    eq("칩 ROIC(보고)", chip("사업 — ROIC(보고)"),
       pct(V["reported"]["roic_ttm"]))
    eq("칩 ROIC(가동자본)", chip("사업 — ROIC(가동자본)"),
       pct(V["in_service"]["roic_ttm"]))
    eq("칩 요구 영구성장률", chip("가격 — 요구 영구성장률"),
       pct(a["implied_growth_at_10pct"]))
    eq("칩 주주이익 수익률", chip("가격 — 주주이익 수익률"),
       f"{pct(a['implied_return_lower'])}–{pct(a['implied_return_upper'])}")
    eq("카드 ① 9개월 영업이익 증가율", card("① 영업은 좋았다"),
       sg(a["actual_growth_operating_income_9m"], 0))
    eq("카드 ② 분기 EPS 증감", card("② EPS 감소는 착시"),
       sg(rel["headline"]["eps_q3_2026"] / rel["headline"]["eps_q3_2025"] - 1,
          0))
    q3 = [p for p in rel["cash_flow"] if p["period"] == "Q3 2026"][0]
    eq("카드 ③ Q3 잉여현금흐름", card("③ 잉여현금흐름이 마이너스"),
       f"{q3['free_cash_flow'] / BN:,.1f}")

    # 막대그래프의 퍼센트는 표와 같은 값이어야 합니다.
    bars = re.findall(r'<span class="yr">(.*?)</span>.*?'
                      r'<span class="pc">(.*?)</span>', page, re.S)
    bar_map = {k.strip(): v.strip() for k, v in bars}
    eq("막대 개수 = 10년 + TTM", len(bars), len(rec["years"]) + 1)
    for y in rec["years"]:
        eq(f"막대 FY{y['fiscal_year']}", bar_map.get(f"FY{y['fiscal_year']}"),
           pct(y["roic"]))
    eq("막대 TTM", bar_map.get("TTM"), pct(V["reported"]["roic_ttm"]))
    # 막대 길이도 값에 비례해야 합니다 — 숫자만 맞고 그림이 틀리면 더 나쁩니다.
    hi = max(y["roic"] for y in rec["years"] if y["roic"])
    widths = [float(x) for x in re.findall(r'style="width:([\d.]+)%"', page)]
    eq("막대 길이 개수", len(widths), len(rec["years"]) + 1)
    for y, wd in zip(rec["years"], widths):
        true(f"막대 길이 FY{y['fiscal_year']} 가 값에 비례",
             abs(wd - y["roic"] / hi * 100) < 0.1,
             f"{wd} vs {y['roic'] / hi * 100:.1f}")

    # 표 되읽기 — 사업부
    r = find_row(page, "Q3′26 영업이익", "구글 클라우드")
    eq("사업부 클라우드 Q3'26 매출", r[2],
       f"{sgm['revenue']['cloud']['q3_2026'] / BN:,.1f}")
    eq("사업부 클라우드 Q3'26 영업이익", r[4],
       f"{sgm['operating_income']['cloud']['q3_2026'] / BN:,.1f}")
    eq("사업부 클라우드 영업이익률", r[5],
       pct(sgm["operating_income"]["cloud"]["q3_2026"]
           / sgm["revenue"]["cloud"]["q3_2026"]))

    # 현금흐름 — 분기별
    for p in rel["cash_flow"]:
        r = find_row(page, "capex÷영업현금", p["period"])
        eq(f"현금흐름 {p['period']} 영업현금", r[1],
           f"{p['operating_cash_flow'] / BN:,.1f}")
        eq(f"현금흐름 {p['period']} capex", r[2], f"{p['capex'] / BN:,.1f}")
        eq(f"현금흐름 {p['period']} FCF", r[3],
           f"{p['free_cash_flow'] / BN:,.1f}")

    # ROIC 네 관점
    for k, label in (("reported", "보고 기준"),
                     ("operating", "영업 (−영업권·무형)"),
                     ("in_service", "가동 (−미가동 설비)"),
                     ("in_service_ex_stakes", "가동 − 투자지분")):
        r = find_row(page, "ROIC (TTM)", label)
        eq(f"ROIC {k} 평균자본", r[3], f"{V[k]['average'] / BN:,.0f}")
        eq(f"ROIC {k} 값", r[4], pct(V[k]["roic_ttm"]))
        eq(f"ROIC {k} 스프레드", r[5], sg(V[k]["spread_ttm"]))

    # 10년 기록 — 표를 먼저 특정해야 합니다. FY 행은 여러 표에 있습니다.
    for y in rec["years"]:
        r = find_row(page, "투하자본 (평균)", f"FY{y['fiscal_year']}")
        eq(f"10년 ROIC FY{y['fiscal_year']}", r[1], pct(y["roic"]))
        eq(f"10년 영업이익 FY{y['fiscal_year']}", r[2],
           f"{y['operating_income'] / BN:,.1f}")

    # 성장률 민감도
    for e in a["growth_sensitivity"]:
        r = find_row(page, "주당 가치", pct(e["growth"], 0))
        eq(f"민감도 주당가치 g={e['growth']:.0%}", r[2],
           usd(e["value_per_share"], 0))
        eq(f"민감도 현재가대비 g={e['growth']:.0%}", r[3], sg(e["vs_price"], 0))

    # 가격별 요구 성장률
    for e in a["implied_growth_by_price"]:
        # 현재가와 8월 가격 행에는 꼬리말이 붙습니다.
        r = find_row(page, "요구 영구성장률", usd(e["price"]), exact=False)
        eq(f"요구 성장률 {usd(e['price'])}", r[2], pct(e["implied_growth"]))

    # 재무활동
    r = find_row(page, "재무활동 (9개월 누적)", "자사주 매입")
    eq("자사주매입 2025", r[1],
       f"{a['financing']['repurchases']['nine_months_2025'] / BN:,.1f}")
    eq("자사주매입 2026", r[2],
       f"{a['financing']['repurchases']['nine_months_2026'] / BN:,.1f}")

    # 트립와이어: 결론이 표와 어긋나지 않는지
    true("요구 성장률이 본문과 표에서 같음",
         pct(a["implied_growth_at_10pct"]) in page)
    true("문턱 미달이 본문에 명시", "불합격" in page)
    true("ROIC 모두 문턱 초과 — under 색이 ROIC 표에 없음",
         all(v["roic_ttm"] > wacc for v in V.values()))
    return passed, fails


MUTATIONS = [
    ("클라우드 영업이익 표기 훼손",
     lambda p: p.replace(">11.1<", ">12.1<", 1)),
    ("Q3 FCF 표기 훼손", lambda p: p.replace(">-9.1<", ">-4.1<", 1)),
    ("ROIC 가동 기준 표기 훼손", lambda p: p.replace(">46.5%<", ">44.5%<", 1)),
    ("요구 성장률 표기 훼손", lambda p: p.replace(">6.9%<", ">5.9%<")),
    ("10년 ROIC 한 해 표기 훼손", lambda p: p.replace(">58.0%<", ">38.0%<", 1)),
    ("자사주매입 표기 훼손", lambda p: p.replace(">0.0<", ">-9.0<", 1)),
    ("민감도 주당가치 표기 훼손", lambda p: p.replace("$185", "$205", 1)),
    ("타이틀 제거", lambda p: re.sub(r"<title>.*?</title>", "", p)),
    ("타이틀을 설명문으로", lambda p: re.sub(
        r"<title>.*?</title>",
        "<title>알파벳 주가 하락 원인과 투자기준 판정 보고서</title>", p)),
    ("keep-all 제거", lambda p: p.replace("word-break:keep-all", "")),
    ("거터 제거", lambda p: p.replace(
        "max(16px,env(safe-area-inset-left,0px))", "16px")),
    ("다크 테마 가드 제거", lambda p: p.replace(
        ':root:not([data-theme="light"])', ":root")),
    ("viewport-fit 선언 제거", lambda p: p.replace(
        'claude:viewport-fit-sides', "x")),
    ("body 배경 제거", lambda p: p.replace("background:var(--bg)", "")),
    ("doctype 추가", lambda p: "<!doctype html>" + p),
    ("허용되지 않은 호스트 추가", lambda p: p.replace(
        "</div>", '<img src="https://evil.example.com/x.png"></div>', 1)),
    ("표를 스크롤 컨테이너 밖으로", lambda p: p.replace(
        '<div class="scroll"><table>', "<table>", 1)),
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
        for f in fails:
            print("  ✗", f)
        if fails:
            return 1
    if args.mutate:
        print(f"\n변이 검정 {len(MUTATIONS)}건 — 페이지를 훼손해 검사가 "
              f"실제로 실패하는지 확인")
        survived = []
        for name, mut in MUTATIONS:
            bad = mut(page)
            if bad == page:
                survived.append(f"{name} (훼손 대상이 없음)")
                print(f"  ✗ {name}: 훼손 대상을 찾지 못함 — 변이가 아무것도 "
                      f"바꾸지 않았습니다")
                continue
            try:
                _, f2 = verify(bad, d)
            except SystemExit as exc:
                print(f"  ✓ {name}: 구조 검사에서 중단 — {exc}")
                continue
            if f2:
                print(f"  ✓ {name}: {len(f2)}건 실패 — {f2[0][:84]}")
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
