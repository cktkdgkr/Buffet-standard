"""
nvda_ceo.json 을 HTML 페이지로 냅니다. 보고서 포맷은 HTML 하나입니다.

엔진의 JSON 하나만 읽습니다 — 페이지가 수치를 들고 있으면 엔진과 어긋납니다.
--verify 는 만들어진 페이지의 표·칩·막대·인용문을 되읽어 엔진 값과 대조하고,
--mutate 는 페이지를 고의로 훼손해 그 검사가 실제로 실패하는지 확인합니다.

    python3 export_nvda_ceo_html.py
    python3 export_nvda_ceo_html.py --verify --mutate
"""

import argparse
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "fv", "nvda_ceo.json")
OUT = os.path.join(HERE, "fv", "nvda_ceo_report.html")
MM, BN = 1e6, 1e9
MOS_MAIN = "30%"
DISCOUNT_ORDER = ["bond30", "bond30_plus3", "project10", "project11"]


def esc(x):
    return html.escape(str(x))


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def sg(x, nd=1):
    return "—" if x is None else f"{x * 100:+.{nd}f}%"


def usd(x, nd=0):
    return "—" if x is None else f"${x:,.{nd}f}"


def bn(x, nd=1):
    return "—" if x is None else f"{x / BN:,.{nd}f}"


def cell(txt, state=""):
    return (txt, state) if state else txt


def table(headers, rows, caption=None, align=None):
    align = align or (["l"] + ["r"] * (len(headers) - 1))
    o = ['<figure class="tw">', '<div class="scroll"><table>',
         "<thead><tr>" + "".join(
             f'<th class="{a}">{esc(h)}</th>'
             for h, a in zip(headers, align)) + "</tr></thead><tbody>"]
    for r in rows:
        tds = []
        for v, a in zip(r, align):
            st = ""
            if isinstance(v, tuple):
                v, st = v
                st = f' data-state="{st}"' if st else ""
            tds.append(f'<td class="{a}"{st}>{v}</td>')
        o.append("<tr>" + "".join(tds) + "</tr>")
    o.append("</tbody></table></div>")
    if caption:
        o.append(f"<figcaption>{caption}</figcaption>")
    o.append("</figure>")
    return "\n".join(o)


def build(d):
    ev, ff = d["event"], d["filing_facts"]
    p, dec = d["price"], d["price_decomposition"]
    f = d["fundamentals"]
    px = p["price"]
    sp = d["price_split"]
    dmap = {x["key"]: x for x in d["discount_options"]}
    infl = d["macro"]["breakeven_inflation_10y"]["rate"]
    buf = {b["key"]: b for b in d["buffett"]}
    bd = dmap["bond30_plus3"]

    def gcell(growth_key, discount_key):
        row = next(r for r in d["grid"] if r["growth_key"] == growth_key)
        return row, next(c for c in row["cells"]
                         if c["discount_key"] == discount_key)

    def req(discount_key, mos):
        return next(r for r in d["required_growth"]
                    if r["discount_key"] == discount_key
                    and abs(r["margin_of_safety"] - mos) < 1e-9)

    o = []
    w = o.append

    w("<title>엔비디아 CEO 리스크 판정</title>")
    w('<meta name="claude:viewport-fit-sides" content="cover">')
    w('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
      'family=Noto+Serif+KR:wght@500;700&family=Noto+Sans+KR:wght@400;500;700'
      '&family=IBM+Plex+Mono:wght@400;500&display=swap">')

    # ---- design plan ----------------------------------------------------
    # 사건 당일의 판정문. 큰 숫자 세 개로 사실을 먼저 세우고(가격·사건 전
    # 하락·당일 하락), 그 다음에 판정을 격자로 깐다. 색은 뜻이 하나씩만:
    # over/under 는 안전마진 판정에만, pos/neg 는 부호에만, flag 는 주목에만.
    w("""<style>
:root{
  /* 중립색을 슬레이트블루 쪽으로 아주 조금 기울여 '고른 회색'으로 읽히게 */
  --bg:#f7f7f9; --panel:#ffffff; --panel2:#edeef2;
  --fg:#191b22; --dim:#4d5160; --dim2:#7b808f;
  --line:#dadce3; --line2:#c3c6d1;
  --accent:#2f4a7a;            /* 구조·링크·강조 */
  --accent-soft:#e6eaf4;
  --over:#2d6a4a;  --over-soft:#e6efe9;   /* 오직: 안전마진 판정 합격 */
  --under:#9c3f2c; --under-soft:#f7e8e3;  /* 오직: 안전마진 판정 불합격 */
  --pos:#2d6a4a;   --neg:#9c3f2c;         /* 오직: 수치의 부호 */
  --flag:#8a6410;  --flag-soft:#f6eeda;   /* 주목 (판정 아님) */
  --price:#191b22;                        /* 현재가 선 */
  --quote:#f2f1ec;                        /* 1차 인용 블록 */
  --display:"Noto Serif KR",Georgia,"Times New Roman",serif;
  --body:"Noto Sans KR",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#13141a; --panel:#1b1d25; --panel2:#232630;
  --fg:#eceef4; --dim:#a9aebd; --dim2:#7f8595;
  --line:#2e3240; --line2:#3e4354;
  --accent:#8fa6d8; --accent-soft:#1f2539;
  --over:#7fc39a; --over-soft:#15271d;
  --under:#e39a81; --under-soft:#2b1a15;
  --pos:#7fc39a; --neg:#e39a81;
  --flag:#d9b45c; --flag-soft:#2b2412;
  --price:#eceef4;
  --quote:#1f2129;
  color-scheme:dark;
}}
:root[data-theme="dark"]{
  --bg:#13141a; --panel:#1b1d25; --panel2:#232630;
  --fg:#eceef4; --dim:#a9aebd; --dim2:#7f8595;
  --line:#2e3240; --line2:#3e4354;
  --accent:#8fa6d8; --accent-soft:#1f2539;
  --over:#7fc39a; --over-soft:#15271d;
  --under:#e39a81; --under-soft:#2b1a15;
  --pos:#7fc39a; --neg:#e39a81;
  --flag:#d9b45c; --flag-soft:#2b2412;
  --price:#eceef4;
  --quote:#1f2129;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:var(--body);
  font-size:16px;line-height:1.72;margin:0;-webkit-text-size-adjust:100%;
  /* 한국어는 음절 단위로 끊어도 되는 언어가 아닙니다 — 없으면 "자본비용"이
     "자/본비용"으로 쪼개집니다. */
  word-break:keep-all;overflow-wrap:break-word}
.wrap{max-width:53rem;margin:0 auto;
  padding-left:max(16px,env(safe-area-inset-left,0px));
  padding-right:max(16px,env(safe-area-inset-right,0px));
  padding-block:0}
h1,h2,h3,h4{font-family:var(--display);text-wrap:balance;margin:0}
h1{font-size:clamp(1.8rem,5vw,2.55rem);line-height:1.2;font-weight:700;
  letter-spacing:-.015em}
h2{font-size:clamp(1.28rem,3.3vw,1.6rem);line-height:1.3;font-weight:700;
  margin-block:2.9rem .35rem;letter-spacing:-.01em;
  border-top:2px solid var(--fg);padding-block:.6rem 0}
h3{font-size:1.05rem;line-height:1.4;font-weight:700;margin-block:1.9rem .2rem}
h4{font-size:.95rem;margin-block:1.2rem .2rem;color:var(--dim)}
p{margin:0 0 1rem}
a{color:var(--accent);text-underline-offset:.18em}
ul,ol{margin:0 0 1rem;padding-left:1.15rem}
li{margin-block:.42rem}
code{font-family:var(--mono);font-size:.86em;background:var(--panel2);
  padding:.08rem .3rem;border-radius:2px}
strong{font-weight:700}
.eyebrow{font-family:var(--mono);font-size:.72rem;font-weight:500;
  letter-spacing:.1em;text-transform:uppercase;color:var(--accent);
  margin:0 0 .55rem}
.lede{font-size:1.07rem;color:var(--dim);margin-block:.9rem 0}
.meta{font-family:var(--mono);font-size:.75rem;line-height:1.9;
  color:var(--dim2);border-top:1px solid var(--line);
  margin-block:1.3rem 0;padding-block:.85rem 0}
.meta b{color:var(--dim);font-weight:500}
header.page{padding-block:2.5rem 0}
footer.page{border-top:1px solid var(--line);margin-block:3rem 0;
  padding-block:1.1rem 2.6rem;font-size:.84rem;color:var(--dim)}

.stats{display:grid;gap:1px;background:var(--line);
  border:1px solid var(--line);margin-block:1.5rem 0}
@media(min-width:640px){.stats{grid-template-columns:repeat(3,1fr)}}
.stat{background:var(--panel);padding:1rem 1.05rem 1.1rem;min-width:0}
.stat .num{display:block;font-family:var(--display);font-size:2rem;
  font-weight:700;line-height:1.05;font-variant-numeric:tabular-nums}
.stat .lab{display:block;font-size:.87rem;color:var(--dim);
  margin-block:.3rem 0}
.stat .note{display:block;font-size:.77rem;color:var(--dim2);
  margin-block:.28rem 0}
.stat[data-state="neg"] .num{color:var(--neg)}
.stat[data-state="flag"] .num{color:var(--flag)}

figure.tw{margin:1rem 0 1.4rem}
.scroll{overflow-x:auto;border:1px solid var(--line);background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{padding:.44rem .62rem;border-bottom:1px solid var(--line);
  white-space:nowrap}
thead th{background:var(--panel2);font-weight:700;font-size:.78rem;
  letter-spacing:.02em;color:var(--dim);border-bottom:1px solid var(--line2)}
tbody tr:last-child td{border-bottom:0}
td{font-family:var(--mono);font-variant-numeric:tabular-nums}
td.l,th.l{text-align:left}
td.r,th.r{text-align:right}
td.w,th.w{text-align:left;white-space:normal;min-width:14rem}
td.l,td.w{font-family:var(--body)}
td[data-state="over"]{color:var(--over);background:var(--over-soft)}
td[data-state="under"]{color:var(--under);background:var(--under-soft)}
td[data-state="pos"]{color:var(--pos)}
td[data-state="neg"]{color:var(--neg)}
td[data-state="flag"]{color:var(--flag);background:var(--flag-soft)}
figcaption{font-size:.78rem;color:var(--dim2);margin-block:.45rem 0}

/* 1차 자료 인용 */
blockquote{margin:0 0 1rem;background:var(--quote);
  border-left:3px solid var(--accent);padding:.85rem 1rem}
blockquote p{margin:0 0 .5rem;font-size:.93rem}
blockquote p:last-child{margin:0}
blockquote .src{font-family:var(--mono);font-size:.74rem;color:var(--dim2);
  display:block;margin-top:.5rem}
.en{font-family:var(--mono);font-size:.84rem;line-height:1.75;
  color:var(--dim)}

/* 하락 분해 막대 */
.fall{border:1px solid var(--line);background:var(--panel);
  padding:1rem 1.05rem;margin-block:1.2rem}
.fallbar{display:flex;height:2.1rem;border:1px solid var(--line2);
  overflow:hidden}
.fallbar span{display:block;height:100%}
.fallbar .keep{background:var(--panel2)}
.fallbar .pre{background:var(--flag);opacity:.75}
.fallbar .day{background:var(--under)}
.falllegend{display:flex;flex-wrap:wrap;gap:.2rem 1.1rem;font-size:.8rem;
  color:var(--dim);margin-top:.6rem}
.falllegend b{font-family:var(--mono);font-weight:500;color:var(--fg)}
.sw{display:inline-block;width:.7rem;height:.7rem;margin-right:.3rem;
  vertical-align:-.05rem}
.sw.pre{background:var(--flag);opacity:.75}
.sw.day{background:var(--under)}
.sw.keep{background:var(--panel2);border:1px solid var(--line2)}

/* 가격 분해 */
.split{border:1px solid var(--line);background:var(--panel);
  padding:1rem 1.05rem;margin-block:1.2rem}
.splitbar{position:relative;height:2.4rem;background:var(--panel2);
  border:1px solid var(--line2)}
.splitbar .ord{position:absolute;left:0;top:0;bottom:0;
  background:var(--accent);opacity:.8}
.splitbar .pline{position:absolute;top:-.3rem;bottom:-.3rem;width:2px;
  background:var(--price)}
.splitticks{display:flex;justify-content:space-between;
  font-family:var(--mono);font-size:.74rem;color:var(--dim2);
  margin-top:.3rem}

.callout{border:1px solid var(--line2);background:var(--panel2);
  padding:.95rem 1.05rem;margin-block:1.2rem;font-size:.93rem}
.callout b{color:var(--fg)}
.verdict{border:2px solid var(--fg);background:var(--panel);
  padding:1.05rem 1.1rem;margin-block:1.3rem}
.verdict h3{margin-top:0}
</style>""")

    w('<div class="wrap">')

    # ----------------------------------------------------------- header
    w('<header class="page">')
    w(f'<p class="eyebrow">{esc(ev["filed"])} · 8-K Item '
      f'{esc(ev["items"])} · {esc(d["ticker"])}</p>')
    w("<h1>엔비디아 CEO 사임과 오늘의 가격</h1>")
    w(f'<p class="lede">창업자가 {ff["founder_since"]}년 창업 이후 '
      f'{d["franchise"]["founder_years"]}년 내내 CEO 였던 회사에서, 이사회가 '
      f'그 사임을 <b>즉시 발효</b>로 수리했습니다. 공시에 사유는 없습니다. '
      f'주가는 시초 {sg(p["change_today_at_open"], 1)}, 장중 저가 '
      f'{sg(p["change_today_at_low"], 1)}까지 내려갔다가 '
      f'{"현재" if p["is_intraday"] else "종가"} '
      f'{sg(p["change_today"], 1)}입니다. 아래는 이 가격을 버핏 기준으로 '
      f'판정한 결과와, 버핏이라면 CEO 리스크를 어떻게 다뤘을지입니다.</p>')
    w(f'<p class="meta">'
      f'가격 <b>{usd(px, 2)}</b> · {esc(p["as_of_utc"] or "")} · '
      f'<b>{"장중 (장이 열려 있습니다)" if p["is_intraday"] else "종가"}</b>'
      f'<br>'
      f'재무 <b>TTM {esc(f["data_as_of"])}</b> (다음 분기 실적은 11월 17일) · '
      f'거시 <b>30년 국채 {pct(d["macro"]["treasury_30y"]["rate"], 2)}</b> · '
      f'기대인플레이션 <b>{pct(infl, 2)}</b><br>'
      f'자료 기준일 <b>{esc(d["generated"])}</b> · 1차 자료 8-K·10-K·'
      f'버크셔 주주서한'
      f'</p>')
    w("</header>")

    w('<div class="stats">')
    w(f'<div class="stat" data-k="price" data-state="neg">'
      f'<b class="num">{usd(px, 2)}</b>'
      f'<span class="lab">{"현재가 (장중)" if p["is_intraday"] else "종가"}</span>'
      f'<span class="note">전일 종가 {usd(p["previous"]["close"], 2)} 대비 '
      f'{sg(p["change_today"], 1)} · 장중 저가 '
      f'{usd(p["last"]["low"], 2)}({sg(p["change_today_at_low"], 1)})'
      f'</span></div>')
    w(f'<div class="stat" data-k="before" data-state="flag">'
      f'<b class="num">{sg(dec["before_event"], 1)}</b>'
      f'<span class="lab">사임 공시 <em>전까지</em>의 하락</span>'
      f'<span class="note">{esc(dec["window_high"]["date"])} 고점 '
      f'{usd(dec["window_high"]["price"], 2)} → '
      f'{esc(dec["pre_event_close"]["date"])} 종가 '
      f'{usd(dec["pre_event_close"]["price"], 2)}</span></div>')
    w(f'<div class="stat" data-k="total" data-state="neg">'
      f'<b class="num">{sg(dec["total_from_high"], 1)}</b>'
      f'<span class="lab">고점 대비 합계</span>'
      f'<span class="note">그중 당일분이 '
      f'{sg(dec["on_event"], 1)} — 하락의 대부분은 사임 전에 '
      f'일어났습니다</span></div>')
    w("</div>")

    w('<div class="verdict">')
    w("<h3>한 줄 판정</h3>")
    r30 = req("bond30_plus3", 0.30)
    r00 = req("bond30_plus3", 0.0)
    w(f'<p>버핏의 할인율(장기 국채 + 3%p = {pct(bd["rate"], 2)})과 그가 함께 '
      f'요구하는 <b>안전마진 30%</b>를 적용하면, 지금 가격 {usd(px, 2)}은 '
      f'<b data-v="req_cagr">향후 10년 NOPAT 연평균 '
      f'{pct(r30["nopat_cagr_10y"])} 성장</b>을 요구합니다 (1년차 '
      f'<b data-v="req_g1">{pct(r30["growth_year1"])}</b>에서 10년차 '
      f'{pct(d["solve_fade_to"])}로 감쇠). 매출 $50십억 초과 기업의 과거 '
      f'분포에서 그 속도는 <b data-v="req_pct">상위 '
      f'{pct(r30["base_rate_percentile_at_or_above"])}</b>입니다. '
      f'안전마진을 포기하면(0%) 요구 성장률은 '
      f'<b data-v="req_cagr0">{pct(r00["nopat_cagr_10y"])}</b>로 '
      f'내려옵니다.</p>')
    w(f'<p><b>CEO 리스크를 할인율에 얹는 것은 버핏의 방식이 아닙니다.</b> '
      f'그는 위험을 안전마진으로 처리하고, 경영자 의존은 아예 선별 기준으로 '
      f'씁니다 — "슈퍼스타가 있어야 좋은 성과가 나는 사업이라면 그 사업 '
      f'자체가 위대한 것이 아니다"(2007 서한). 그래서 이 보고서는 CEO '
      f'프리미엄을 발명하지 않고, 가격을 성장 가정으로 쪼갭니다: 지금 가격 '
      f'{usd(px, 2)} 중 <b data-v="ordinary">'
      f'{usd(sp["ordinary_company_value"])}</b>은 '
      f'엔비디아가 <em>평범한 대형주처럼</em> 성장할 때의 가치이고, 나머지 '
      f'<b data-v="premium">{usd(sp["premium_in_price"])}</b>(가격의 '
      f'<b data-v="premium_share">'
      f'{pct(sp["premium_share_of_price"], 0)}</b>)이 '
      f'&ldquo;예외적 기록이 계속된다&rdquo;는 '
      f'값입니다. 사임이 흔드는 것은 뒤쪽입니다.</p>')
    w("</div>")

    # ------------------------------------------------------- 1. 공시
    w("<h2>1. 공시가 말하는 것과 말하지 않는 것</h2>")
    w(f'<p>1차 자료는 <a href="{esc(ev["url"])}">8-K</a>와 그 '
      f'<a href="{esc(ev["press_release_url"] or ev["url"])}">보도자료'
      f'(Exhibit 99.1)</a>입니다. 사건일은 {esc(ev["report_date"])}, '
      f'제출일은 {esc(ev["filed"])}입니다. 원문 그대로 옮깁니다.</p>')
    for key, label in (("resignation", "사임 — 즉시 발효"),
                       ("interim", "임시 CEO — CFO 가 겸임"),
                       ("chair", "이사회 의장 — 사상 첫 선임"),
                       ("search", "후임 — 사내외 공개 탐색"),
                       ("earnings", "다음 실적 — 예정대로")):
        txt = ev.get(key)
        if not txt:
            continue
        w(f'<h4>{esc(label)}</h4>')
        w(f'<blockquote data-q="{key}"><p class="en">{esc(txt)}</p>'
          f'<span class="src">SEC EDGAR · 8-K {esc(ev["accession"])}'
          f'</span></blockquote>')
    w('<div class="callout">')
    w("<p><b>공시에 사임 사유는 없습니다.</b> Item 5.02 는 사유의 기재를 "
      "강제하지 않고, 이 8-K 에는 사유로 읽을 수 있는 문구가 하나도 "
      "없습니다. 사유는 이 사건이 <b>승계 문제</b>인지 <b>회사로 번지는 "
      "문제</b>인지를 가르는데, 지금은 1차 자료로 확인할 수 없습니다. "
      "보도는 이사회가 외부 로펌을 선임해 황 전 CEO 의 개인적 관계와 관련된 "
      "의혹을 조사했고, 이사회가 국가안보나 회사 기밀이 침해됐다고 볼 근거는 "
      "없다고 밝혔다고 전합니다 — <b>보도이고 공시가 아닙니다.</b> 이 "
      "보고서의 수치는 어느 것도 그 보도에 기대지 않습니다.</p>")
    w("<p>투자 판단에서 이 구분이 중요합니다. 지금까지 확인된 범위에서 이 "
      "사건은 <b>영업의 악화가 아니라 지배구조의 사건</b>입니다. 영업 "
      "데이터로 확인할 첫 기회는 5일 뒤 3분기 실적입니다.</p>")
    w("</div>")

    # ------------------------------------------------------- 2. 하락 분해
    w("<h2>2. 하락은 오늘 시작된 것이 아닙니다</h2>")
    hi = dec["window_high"]["price"]
    pre = dec["pre_event_close"]["price"]
    keep_w = px / hi * 100
    pre_w = (pre - px) / hi * 100 if pre > px else 0.0
    day_w = 0.0
    # 막대: 고점을 100 으로 두고 (남은 가격) / (사건 전 하락분) / (당일 하락분)
    keep_w = px / hi * 100
    day_w = (pre - px) / hi * 100
    pre_w = (hi - pre) / hi * 100
    w('<div class="fall">')
    w(f'<div class="fallbar">'
      f'<span class="keep" data-bar="keep" style="width:{keep_w:.2f}%"></span>'
      f'<span class="day" data-bar="day" style="width:{day_w:.2f}%"></span>'
      f'<span class="pre" data-bar="pre" style="width:{pre_w:.2f}%"></span>'
      f'</div>')
    w(f'<div class="falllegend">'
      f'<span><i class="sw keep"></i>현재가 <b>{usd(px, 2)}</b></span>'
      f'<span><i class="sw day"></i>당일 하락 '
      f'<b>{usd(pre - px, 2)}</b> ({sg(dec["on_event"], 1)})</span>'
      f'<span><i class="sw pre"></i>사임 전 하락 '
      f'<b>{usd(hi - pre, 2)}</b> ({sg(dec["before_event"], 1)})</span>'
      f'</div>')
    w("</div>")
    w(f'<p>6개월 고점 {usd(hi, 2)}({esc(dec["window_high"]["date"])})에서 '
      f'사임 공시 전날 종가 {usd(pre, 2)}까지 이미 '
      f'{sg(dec["before_event"], 1)} 내려와 있었습니다. 오늘의 '
      f'{sg(dec["on_event"], 1)}을 더한 것이 고점 대비 '
      f'{sg(dec["total_from_high"], 1)}입니다. <b>CEO 사임으로 싸졌다고 '
      f'말하면 하락의 {abs(dec["before_event"]) / abs(dec["total_from_high"]):.0%}를 '
      f'잘못 설명하는 것입니다.</b></p>')
    rows = [[r["date"], usd(r["open"], 2), usd(r["high"], 2),
             usd(r["low"], 2), usd(r["close"], 2),
             cell(f"{r['volume'] / 1e6:,.0f}M", "")]
            for r in d["price"]["rows"][-10:]]
    w(table(["날짜", "시가", "고가", "저가", "종가", "거래량"], rows,
            caption=f"최근 10거래일. 마지막 행은 "
                    + ("장중이라 미완성 일봉입니다"
                       if p["is_intraday"] else "당일 종가입니다")
                    + f" ({esc(p['as_of_utc'] or '')} 기준). "
                      f"출처 Yahoo Finance."))

    # ---------------------------------------------------- 3. 버핏 기준 격자
    w("<h2>3. 버핏 기준 판정 — 성장률 가정 × 할인율</h2>")
    w(f'<p>가치는 네 가지 성장 가정과 네 가지 할인율로 냅니다. 증분 ROIC 은 '
      f'격자 전체에 같은 값({pct(f["incremental_roic_used"], 0)}, '
      f'{esc(f["incremental_roic_basis"])})을 써서 <b>성장률과 할인율의 '
      f'효과만</b> 분리합니다. 단일 적정주가를 내지 않는 이유는 어느 칸이 '
      f'맞는지가 가정의 문제이기 때문입니다.</p>')
    rows = []
    for row in d["grid"]:
        for c in row["cells"]:
            if c.get("diverges"):
                rows.append([
                    esc(row["growth_label"]),
                    esc(dmap[c["discount_key"]]["label"]),
                    cell("발산", "flag"), "—", "—", cell("판정 불가", "flag")])
                continue
            v = c["verdicts"][MOS_MAIN]
            rows.append([
                esc(row["growth_label"]),
                esc(dmap[c["discount_key"]]["label"]),
                f"<b>{usd(c['value_per_share'])}</b>",
                cell(sg(c["upside_vs_price"], 0),
                     "pos" if c["upside_vs_price"] > 0 else "neg"),
                f"<b>{usd(v['buy_limit'])}</b>",
                cell(f"<b>{'합격' if v['pass'] else '불합격'}</b>",
                     "over" if v["pass"] else "under"),
            ])
    w(table(["성장률 가정", "할인율", "주당 가치", "현재가 대비",
             f"안전마진 {MOS_MAIN} 매수 상한", "판정"], rows,
            caption=f"판정 = 안전마진 {MOS_MAIN} 매수 상한이 현재가 "
                    f"{usd(px, 2)}보다 높은가. 초록·빨강은 이 판정에만 "
                    f"씁니다 — 현재가 대비 칸의 색은 부호일 뿐 판정이 "
                    f"아닙니다.",
            align=["w", "l", "r", "r", "r", "r"]))
    # 이 문단의 숫자는 표에서 셉니다. "전부 성장률 상한 25% 가정" 이라고
    # 적어 두었다가, 순수 국채 칸에서 기초율 가정도 합격이 되어 본문이 표와
    # 어긋났습니다.
    n_cells = sum(1 for r in d["grid"] for c in r["cells"])
    by_disc = {k: [r["growth_key"] for r in d["grid"]
                   for c in r["cells"]
                   if c["discount_key"] == k and not c.get("diverges")
                   and c["verdicts"][MOS_MAIN]["pass"]]
               for k in DISCOUNT_ORDER}
    n_pass = sum(len(v) for v in by_disc.values())
    w(f'<p>{n_cells}칸 가운데 안전마진 {MOS_MAIN}를 적용해도 합격인 칸은 '
      f'<b data-v="n_pass">{n_pass}칸</b>입니다. 그중 '
      f'<b data-v="n_pass_bond">{len(by_disc["bond30"])}칸</b>은 '
      f'<b>순수 국채 할인율</b>에서 나온 것인데, 그 할인율은 이 프로젝트가 '
      f'이미 주식에 쓸 수 없다고 결론 낸 값입니다 — 영구성장률을 명목 GDP로 '
      f'두면 분모가 음수가 되어 발산합니다. 버핏 기준(국채 + 3%p)에서는 '
      f'<b data-v="n_pass_buffett">{len(by_disc["bond30_plus3"])}칸</b>이고 '
      f'전부 <b>성장률을 상한 {pct(0.25, 0)}로 둔 가정</b>입니다. 할인율을 '
      f'10%·11%로 올리면 합격은 '
      f'<b data-v="n_pass_high">'
      f'{len(by_disc["project10"]) + len(by_disc["project11"])}칸</b>이 '
      f'됩니다. 즉 이 가격의 합격 여부는 <b>성장 가정과 할인율 둘이 '
      f'결정</b>하고, 그중 성장 가정이 바로 오늘의 사건이 흔드는 '
      f'것입니다.</p>')

    # -------------------------------------------------- 4. 요구 성장률
    w("<h2>4. 거꾸로 — 이 가격이 요구하는 성장률</h2>")
    w(f'<p>적정주가를 하나 내놓는 대신, 가격을 조건으로 바꿔 읽습니다. '
      f'<b>지금 가격이 정당화되려면 성장률이 얼마여야 하는가.</b> 탐색 '
      f'상한은 증분 ROIC {pct(f["incremental_roic_used"], 0)}입니다 — 그 '
      f'위는 재투자율이 100%를 넘어 자기 현금으로 조달할 수 없는 '
      f'성장입니다. 감쇠 모양은 10년차 {pct(d["solve_fade_to"])}로 '
      f'고정했습니다.</p>')
    rows = []
    for key in DISCOUNT_ORDER:
        for m in d["margins_of_safety"]:
            r = req(key, m)
            lab = f"안전마진 {int(m * 100)}%"
            if not r["reachable"]:
                rows.append([esc(dmap[key]["label"]), lab,
                             cell("없음", "flag"), "—", "—",
                             cell("어떤 성장률로도 설명 불가", "flag")])
                continue
            rows.append([
                esc(dmap[key]["label"]), lab,
                f"<b>{pct(r['growth_year1'])}</b>",
                f"<b>{pct(r['nopat_cagr_10y'])}</b>",
                pct(r["nopat_cagr_10y_real"]),
                cell(f"상위 {pct(r['base_rate_percentile_at_or_above'])}",
                     "flag" if r["base_rate_percentile_at_or_above"] < 0.25
                     else ""),
            ])
    w(table(["할인율", "요구 조건", "1년차 성장률", "10년 평균 CAGR",
             "같은 값의 실질", "기초율 분포에서의 위치"], rows,
            caption="이 칸의 색은 '주목'이고 판정이 아닙니다. 요구 성장률은 "
                    "<b>낮을수록 가격이 설명되기 쉽다</b>는 뜻이므로, 다른 "
                    "판정 칸과 방향이 반대입니다. 10년 평균 CAGR 을 함께 "
                    "적는 이유는 1년차만 적으면 가정이 실제보다 공격적으로 "
                    "보이기 때문입니다.",
            align=["l", "l", "r", "r", "r", "r"]))
    ni = d["base_rates"]["net_income_10y"]
    w(f'<p>기초율은 Credit Suisse HOLT <em>The Base Rate Book</em>'
      f'(2016-09-26) Exhibit 4 의 "매출 $50십억 초과" 칸입니다. 그 집단의 '
      f'10년 순이익 CAGR 은 <b>중위 {pct(ni["median"])}·평균 '
      f'{pct(ni["mean"])}(실질)</b>이고, <b>이 수치는 실질</b>이라 명목 '
      f'가정과 비교할 때는 기대인플레이션 {pct(infl, 2)}을 더해야 합니다. '
      f'표본은 10년을 생존한 기업만 포함하므로 <b>생존편향으로 위쪽으로 '
      f'치우쳐</b> 있습니다 — 즉 위 백분위는 관대하게 계산된 값입니다.</p>')

    # ------------------------------------------------- 5. 가격 분해
    w("<h2>5. 가격을 성장 가정으로 쪼개면</h2>")
    ord_w = sp["ordinary_company_value"] / sp["exceptional_value"] * 100
    px_w = px / sp["exceptional_value"] * 100
    w('<div class="split">')
    w(f'<div class="splitbar">'
      f'<span class="ord" data-bar="ordinary" '
      f'style="width:{ord_w:.2f}%"></span>'
      f'<span class="pline" data-bar="price" '
      f'style="left:{px_w:.2f}%"></span>'
      f'</div>')
    w(f'<div class="splitticks"><span>$0</span>'
      f'<span>예외성 유지 가치 {usd(sp["exceptional_value"])}</span></div>')
    w("</div>")
    w(table(["구분", "주당", "가격 대비", "무엇을 가정하는가"],
            [["평범한 대형주 가치",
              f"<b>{usd(sp['ordinary_company_value'])}</b>",
              pct(sp["ordinary_company_value"] / px, 0),
              cell(f"성장률을 {esc(sp['ordinary_growth_label'])}로 — 즉 이 "
                   f"규모 기업의 역사적 중앙값만큼만 성장한다고 볼 때", "")],
             ["예외성 프리미엄",
              cell(f"<b>{usd(sp['premium_in_price'])}</b>", "flag"),
              cell(pct(sp["premium_share_of_price"], 0), "flag"),
              cell("그 위에 시장이 얹어 놓은 값. 과거의 예외적 성장이 "
                   "이어진다는 쪽에 거는 금액입니다.", "")],
             ["(참고) 예외성 유지 가치",
              f"{usd(sp['exceptional_value'])}",
              pct(sp["exceptional_value"] / px, 0),
              cell(f"성장률을 {esc(sp['exceptional_growth_label'])}로 둘 "
                   f"때의 가치. 현재가는 평범과 예외 사이 "
                   f"{pct(sp['price_position'], 0)} 지점에 있습니다.", "")]],
            caption=f"할인율 {pct(sp['discount'], 2)}(장기 국채 + 3%p), "
                    f"안전마진 적용 전. 막대는 예외성 유지 가치를 100 으로 "
                    f"둔 것이고, 세로선이 현재가입니다.",
            align=["l", "r", "r", "w"]))
    w(f'<p>이 분해가 CEO 리스크를 재는 자리입니다. 사임이 흔드는 것은 '
      f'<b>{usd(sp["premium_in_price"])}</b>이고, 평범한 대형주 가치 '
      f'{usd(sp["ordinary_company_value"])}는 CUDA·설치기반·고객관계처럼 '
      f'사람과 함께 걸어 나가지 않는 자산에 붙어 있습니다. 거꾸로 말하면, '
      f'<b>지금 가격에서 잃을 수 있는 최대치는 전부가 아니라 가격의 '
      f'{pct(sp["premium_share_of_price"], 0)}</b>입니다 — 평범해지기만 '
      f'한다면.</p>')

    # ------------------------------------------- 6. 버핏의 CEO 리스크 처리
    w("<h2>6. 버핏이라면 CEO 리스크를 어떻게 반영했을까</h2>")
    w("<p>버핏의 글에서 CEO 리스크는 <b>할인율에 더하는 프리미엄으로 "
      "등장하지 않습니다.</b> 세 군데에 나눠 들어가 있습니다 — 사업의 "
      "분류(프랜차이즈인가), 선별 기준(슈퍼스타가 필요한 사업인가), 그리고 "
      "안전마진. 1차 자료를 전문으로 옮기고 각각을 엔비디아에 "
      "적용합니다.</p>")
    for key in ("superstar", "franchise", "change", "jockey",
                "severe_change"):
        b = buf[key]
        w(f'<h3>{esc(b["title"])}</h3>')
        w(f'<blockquote data-bq="{key}">')
        for k in ("quote", "quote2", "quote3"):
            if b.get(k):
                w(f'<p class="en">&ldquo;{esc(b[k])}&rdquo;</p>')
        w(f'<span class="src">'
          f'<a href="{esc(b["source_url"])}">{b["year"]}년 주주서한</a> · '
          f'{esc(b["kind"])} · 원문 대조 '
          f'{len(b["verified_against_source"])}문장</span>')
        w("</blockquote>")
        w(f'<p>{b["why"]}</p>')
    w('<div class="callout">')
    w(f'<p><b>그래서 버핏의 반영 방식은 세 단계입니다.</b> ① 이 사업이 '
      f'프랜차이즈인지 묻는다 → 프랜차이즈면 경영 부실을 견디므로 CEO '
      f'교체는 가격의 문제로 남고, 그냥 사업이면 치명적일 수 있다. '
      f'② 성과가 한 사람에게 달려 있었다면 애초에 사지 않는다 — 할인하지 '
      f'않고 <b>제외</b>한다. ③ 남은 불확실성은 할인율이 아니라 '
      f'<b>안전마진</b>으로 처리한다. 그래서 이 보고서는 "CEO 리스크 '
      f'프리미엄 X%p" 같은 숫자를 만들지 않았습니다. 그건 버핏의 숫자가 '
      f'아니고, 만들면 그 가정이 결론이 됩니다.</p>')
    w("</div>")

    # -------------------------------------------- 7. 프랜차이즈 검정
    w("<h2>7. 엔비디아는 프랜차이즈인가 — 1991년 기준 적용</h2>")
    fr = d["franchise"]
    w(table(["버핏의 조건", "판정", "근거"],
            [[esc(t["criterion"]),
              cell(f"<b>{esc(t['verdict'])}</b>",
                   {"충족": "over", "다툼 있음": "flag",
                    "부분 미충족": "under", "미검증": "flag"}
                   .get(t["verdict"], "")),
              cell(t["evidence"], "")] for t in fr["tests"]],
            caption="세 조건은 1991년 주주서한, 네 번째(경영 부실을 "
                    "견디는가)는 같은 서한의 추가 문장입니다. 근거는 전부 "
                    "엔비디아 자신의 10-K 와 이 프로젝트의 10년 ROIC "
                    "기록입니다.",
            align=["w", "r", "w"]))
    w(f'<blockquote data-bq="riskfactor">'
      f'<p class="en">{esc(ff["key_personnel_risk_factor"])}</p>'
      f'<p class="en">{esc(ff["customer_concentration_sentence"])}</p>'
      f'<span class="src">NVIDIA FY2026 10-K ('
      f'{esc(ff["filed"])}) · <a href="{esc(ff["url"])}">SEC EDGAR</a>'
      f'</span></blockquote>')
    w(f'<p>회사 자신이 핵심인력 이탈을 위험요인으로 적고 있고, 상위 두 '
      f'직접고객이 매출의 <b>{pct(fr["customer_concentration_top2"], 0)}</b>'
      f'입니다(FY2026). 전환비용(CUDA)과 고객집중이 같은 저울에 올라 있어 '
      f'조건 (2)는 <b>다툼 있음</b>으로 둡니다. 네 번째 조건은 판정하지 '
      f'않았습니다 — 창업자가 {fr["founder_years"]}년 내내 CEO 였으므로 '
      f'<b>이 회사가 다른 경영진 아래에서 어떤 성과를 냈는지에 대한 관측치가 '
      f'0개</b>입니다. 모른다는 것이 결론이고, 모를 때 쓰는 도구가 '
      f'안전마진입니다.</p>')

    # ------------------------------------------------- 8. 10년 기록
    w("<h2>8. 그 기록은 무엇이었나 — 10년</h2>")
    w(f'<p>판정의 분자가 되는 기록입니다. 10년 중위 ROIC '
      f'{pct(fr["roic_median"], 0)}, 10년 영업이익 CAGR '
      f'{pct(fr["operating_income_cagr"])}, 매출 CAGR '
      f'{pct(fr["revenue_cagr"])}. 이 기록 전체가 한 사람의 재임 기간에 '
      f'만들어졌다는 것이 오늘의 질문입니다.</p>')
    rows = []
    for y in fr["roic_years"]:
        rows.append([f"FY{y['fiscal_year']}", bn(y["revenue"]),
                     bn(y["operating_income"]),
                     bn(y["invested_capital_avg"]),
                     cell(pct(y["roic"], 0), "")])
    w(table(["연도", "매출", "영업이익", "평균 투하자본", "ROIC"], rows,
            caption=f"단위 십억 달러. ROIC = NOPAT ÷ 평균 투하자본. "
                    f"고점 {pct(fr['roic_peak']['roic'], 0)}"
                    f"(FY{fr['roic_peak']['fiscal_year']}) → 최근 "
                    f"{pct(fr['roic_latest'], 0)}. 고점 이후 영업이익은 "
                    f"{fr['trend']['operating_income_multiple']:.2f}배 "
                    f"늘었는데 투하자본이 "
                    f"{fr['trend']['invested_capital_multiple']:.2f}배 "
                    f"늘어서입니다 — 이익이 멈춘 것이 아닙니다."))

    # ------------------------------------------------- 9. 시나리오 대조
    w("<h2>9. 기존 4개사 시나리오와의 대조</h2>")
    w("<p>같은 가격을 이 프로젝트의 시나리오 DCF 로도 읽어 둡니다. 규칙은 "
      "기업마다 자기 기록에서 도출합니다 — 보수는 10년 CAGR÷3, 중립은 ÷2, "
      "낙관은 그대로(각각 상한 10·15·25%).</p>")
    w(table(["시나리오", "성장률", "증분ROIC", "할인율", "주당 가치",
             "현재가 대비", "정당화 성장률"],
            [[s["scenario"],
              f"{pct(s['assumptions']['growth'])} → "
              f"{pct(s['assumptions']['fade_to'])}",
              pct(s["assumptions"]["incremental_roic"]),
              pct(s["assumptions"]["discount"], 0),
              f"<b>{usd(s['value_per_share'])}</b>",
              cell(sg(s["upside_vs_price"], 0),
                   "pos" if s["upside_vs_price"] > 0 else "neg"),
              cell(pct(s["implied_growth_at_price"])
                   if s["implied_growth_at_price"] is not None else "없음",
                   "flag" if s["implied_growth_at_price"] is None else "")]
             for s in d["scenario_valuations"]],
            caption=f"TTM NOPAT {bn(f['ttm_nopat'])}십억 · 순현금 "
                    f"{bn(f['net_cash'])}십억 · 주식수 "
                    f"{f['shares_outstanding'] / 1e9:,.1f}십억 주 · "
                    f"시가총액 {bn(f['market_cap'], 0)}십억 달러.",
            align=["l", "r", "r", "r", "r", "r", "r"]))

    # ------------------------------------------------------ 10. 결론
    w("<h2>10. 결론</h2>")
    w("<ol>")
    w(f"<li><b>지금 가격은 '싸다'가 아니라 '덜 비싸다'입니다.</b> 버핏의 "
      f"할인율에 안전마진 30%를 걸면 요구 10년 CAGR 이 "
      f"{pct(r30['nopat_cagr_10y'])}이고, 이는 이 규모 기업의 역사적 분포에서 "
      f"상위 {pct(r30['base_rate_percentile_at_or_above'])}입니다. 생존편향을 "
      f"감안하면 더 빡빡합니다. 안전마진을 포기해야 "
      f"{pct(r00['nopat_cagr_10y'])}로 내려오고, 그제야 '불가능하지 않은 "
      f"가정'의 영역에 들어옵니다.</li>")
    w(f"<li><b>하락의 주인은 CEO 가 아닙니다.</b> 고점 대비 "
      f"{sg(dec['total_from_high'], 1)} 가운데 사임 전이 "
      f"{sg(dec['before_event'], 1)}입니다. 오늘 사건을 이유로 사는 것은 "
      f"이미 3주간 진행된 재평가를 하루의 뉴스로 설명하는 것입니다.</li>")
    w(f"<li><b>버핏식 CEO 리스크 반영은 할인율 가산이 아니라 제외와 "
      f"안전마진입니다.</b> 2007년 기준을 문자 그대로 적용하면 엔비디아는 "
      f"'빠르고 지속적으로 변하는 산업'이라는 이유로 <b>사임과 무관하게</b> "
      f"그의 후보군에서 탈락합니다. 사임은 그 판정을 바꾸지 않고, "
      f"'슈퍼스타 의존' 쪽 증거를 하나 더 얹습니다.</li>")
    w(f"<li><b>그래도 지금 사겠다면, 무엇을 사는지 알고 사야 합니다.</b> "
      f"가격의 {pct(sp['premium_share_of_price'], 0)}이 '예외적 기록의 "
      f"계속'이고, 그 기록은 다른 경영진 아래에서 한 번도 관측된 적이 "
      f"없습니다. 평범해지기만 해도 {usd(sp['premium_in_price'])}가 "
      f"사라지고, 그 경우의 가치는 "
      f"{usd(sp['ordinary_company_value'])}입니다.</li>")
    w(f"<li><b>5일 뒤에 더 알게 됩니다.</b> 3분기 실적이 11월 17일 "
      f"예정대로입니다. 지금 판정은 영업 데이터로 사건을 확인하기 전의 "
      f"것이고, 그 전에 결론을 굳힐 이유가 없습니다.</li>")
    w("</ol>")

    # ------------------------------------------------------ 한계
    w("<h2>이 분석의 한계</h2>")
    w("<ul>")
    for x in d["limits"]:
        w(f"<li>{x}</li>")
    w("</ul>")

    w('<footer class="page">')
    w(f'출처: '
      f'<a href="{esc(ev["url"])}">8-K (Item 5.02)</a> · '
      f'<a href="{esc(ff["url"])}">FY2026 10-K</a> · '
      f'<a href="https://www.berkshirehathaway.com/letters/">'
      f'버크셔 주주서한</a> · '
      f'<a href="{esc(d["macro"]["treasury_30y"]["source_url"])}">'
      f'국채 수익률</a> · '
      f'<a href="{esc(d["base_rates"]["source_url"])}">Base Rate Book</a> · '
      f'시세 Yahoo Finance.<br>'
      f'자료 기준일 {esc(d["generated"])} · 가격은 '
      f'{esc(p["as_of_utc"] or "")} '
      f'{"장중값" if p["is_intraday"] else "종가"}입니다. 재현: '
      f'<code>bash work/run_nvda_ceo.sh</code>.<br>'
      f'투자 판단은 읽는 분의 몫입니다.')
    w("</footer>")
    w("</div>")
    return "\n".join(o)


# ------------------------------------------------------------------- 검증
def tables_of(page):
    out = []
    for m in re.finditer(r"<table>(.*?)</table>", page, re.S):
        blob = m.group(1)
        heads = [html.unescape(re.sub(r"<[^>]+>", "", h)).strip()
                 for h in re.findall(r"<th[^>]*>(.*?)</th>", blob, re.S)]
        rows = []
        for tr in re.findall(r"<tr>(.*?)</tr>", blob, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if tds:
                rows.append([html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
                             for t in tds])
        out.append((heads, rows))
    return out


def find_table(page, header_has):
    hits = [(h, r) for h, r in tables_of(page)
            if any(header_has in x for x in h)]
    if len(hits) != 1:
        raise SystemExit(
            f"표 특정 실패: 헤더에 {header_has!r} 를 가진 표가 {len(hits)}개")
    return hits[0]


def verify(page, d):
    ev, ff = d["event"], d["filing_facts"]
    p, dec, f = d["price"], d["price_decomposition"], d["fundamentals"]
    px, sp = p["price"], d["price_split"]
    dmap = {x["key"]: x for x in d["discount_options"]}
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
            return True
        fails.append(f"{name}: 거짓 {detail}")
        return False

    def near(name, got, want, tol):
        nonlocal passed
        if got is not None and abs(got - want) <= tol:
            passed += 1
        else:
            fails.append(f"{name}: 페이지 {got} vs 엔진 {want:.4f}")

    # ---------------------------------------------------------- 페이지 요건
    true("타이틀 존재", "<title>" in page[:8192])
    m = re.search(r"<title>(.*?)</title>", page)
    true("타이틀이 이름 (2~4 단어)",
         bool(m) and 2 <= len(m.group(1).split()) <= 4,
         m.group(1) if m else "")
    true("doctype·html·head·body 없음",
         not re.search(r"<(?:!doctype|html|head|body)\b", page, re.I))
    true("viewport-fit 선언", "claude:viewport-fit-sides" in page)
    flat = page.replace(" ", "")
    true("좌측 거터", "max(16px,env(safe-area-inset-left,0px))" in flat)
    true("우측 거터", "max(16px,env(safe-area-inset-right,0px))" in flat)
    true("한국어 줄바꿈 keep-all", "word-break:keep-all" in flat)
    bare = re.search(r"^:root\{(.*?)\}", page, re.S | re.M)
    true("맨 :root 블록 존재", bool(bare))
    for tk in ("--bg", "--panel", "--fg", "--dim", "--line", "--accent",
               "--over", "--under", "--pos", "--neg", "--flag", "--price",
               "--quote"):
        true(f"토큰 {tk} 가 맨 :root 에",
             bool(bare) and f"{tk}:" in bare.group(1))
    for guard in (':root:not([data-theme="light"])',
                  ':root[data-theme="dark"]'):
        true(f"다크 가드 {guard[:26]}", guard in page)
    true("다크 블록 color-scheme", page.count("color-scheme:dark") >= 2)
    true("body 배경이 토큰", "background:var(--bg)" in flat)
    true("표가 가로 스크롤 안",
         page.count('<div class="scroll">') == page.count("<table>"))
    for host in set(re.findall(r'(?:src|href)="https?://([^/"]+)', page)):
        true(f"허용 호스트 {host}",
             host in ("fonts.googleapis.com", "fonts.gstatic.com",
                      "www.berkshirehathaway.com", "www.sec.gov",
                      "query1.finance.yahoo.com", "sorfis.com",
                      "fred.stlouisfed.org"), host)

    # --------------------------------------------------------------- 칩
    for key, want, tol in (("price", px, 0.005),
                           ("before", dec["before_event"] * 100, 0.05),
                           ("total", dec["total_from_high"] * 100, 0.05)):
        m = re.search(rf'data-k="{key}"[^>]*>\s*<b class="num">([^<]+)</b>',
                      page)
        if not true(f"칩 {key} 존재", bool(m)):
            continue
        got = float(re.sub(r"[^\d.\-+]", "", m.group(1)))
        near(f"칩 {key} 수치", got, want, tol)
    m = re.search(r'data-k="price".*?<span class="note">(.*?)</span>',
                  page, re.S)
    if true("칩 price 보조문", bool(m)):
        txt = html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))
        true("칩 price 보조문에 전일 종가",
             f"{p['previous']['close']:,.2f}" in txt, txt[:70])
        true("칩 price 보조문에 장중 저가",
             f"{p['last']['low']:,.2f}" in txt, txt[:70])

    # --------------------------------------------- 한 줄 판정 본문의 숫자
    # 표만 검사하면 본문 문장의 숫자가 틀려도 통과합니다. 변이 검정에서
    # 실제로 두 건이 이 구멍으로 빠져나갔습니다.
    r30v = next(r for r in d["required_growth"]
                if r["discount_key"] == "bond30_plus3"
                and abs(r["margin_of_safety"] - 0.30) < 1e-9)
    r00v = next(r for r in d["required_growth"]
                if r["discount_key"] == "bond30_plus3"
                and r["margin_of_safety"] == 0.0)
    for key, want in (
            ("req_cagr", f"향후 10년 NOPAT 연평균 "
                         f"{r30v['nopat_cagr_10y'] * 100:.1f}% 성장"),
            ("req_g1", f"{r30v['growth_year1'] * 100:.1f}%"),
            ("req_pct", f"상위 "
                        f"{r30v['base_rate_percentile_at_or_above'] * 100:.1f}%"),
            ("req_cagr0", f"{r00v['nopat_cagr_10y'] * 100:.1f}%"),
            ("ordinary", f"${sp['ordinary_company_value']:,.0f}"),
            ("premium", f"${sp['premium_in_price']:,.0f}"),
            ("premium_share",
             f"{sp['premium_share_of_price'] * 100:.0f}%")):
        m = re.search(rf'<b data-v="{key}">(.*?)</b>', page, re.S)
        if not true(f"판정 본문 {key} 표시", bool(m)):
            continue
        eq(f"판정 본문 {key}",
           html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip(), want)

    # ------------------------------------------------------- 공시 인용 원문
    for key in ("resignation", "interim", "chair", "search", "earnings"):
        if not ev.get(key):
            continue
        m = re.search(rf'<blockquote data-q="{key}"><p class="en">(.*?)</p>',
                      page, re.S)
        if not true(f"공시 인용 {key} 블록", bool(m)):
            continue
        eq(f"공시 인용 {key} 전문", html.unescape(m.group(1)).strip(),
           ev[key])
    true("사유 미기재를 본문에 명시",
         "공시에 사임 사유는 없습니다" in page
         and ev["reason_stated_in_filing"] is False)
    true("보도와 공시의 구분을 명시", "보도이고 공시가 아닙니다" in page)
    true("11월 17일 실적 예정 명시", "11월 17일" in page)

    # ------------------------------------------------------- 하락 분해 막대
    hi = dec["window_high"]["price"]
    bars = dict(re.findall(r'data-bar="(\w+)" style="width:([\d.]+)%"', page))
    for key, want in (("keep", px / hi * 100),
                      ("day", (dec["pre_event_close"]["price"] - px)
                       / hi * 100),
                      ("pre", (hi - dec["pre_event_close"]["price"])
                       / hi * 100)):
        if not true(f"막대 {key} 존재", key in bars):
            continue
        near(f"막대 {key} 길이가 값에 비례", float(bars[key]), want, 0.02)
    true("막대 세 토막의 합이 100",
         abs(sum(float(bars[k]) for k in ("keep", "day", "pre")
                 if k in bars) - 100) < 0.05,
         str(bars))

    # 최근 10거래일
    _, rows = find_table(page, "거래량")
    eq("시세 표 행 수", len(rows), 10)
    for r_ in p["rows"][-10:]:
        hit = [x for x in rows if x[0] == r_["date"]]
        if not true(f"시세 {r_['date']} 행", len(hit) == 1):
            continue
        eq(f"시세 {r_['date']} 종가", hit[0][4], f"${r_['close']:,.2f}")
        eq(f"시세 {r_['date']} 저가", hit[0][3], f"${r_['low']:,.2f}")

    # --------------------------------------------------------------- 격자
    _, rows = find_table(page, f"안전마진 {MOS_MAIN} 매수 상한")
    n_cells = sum(1 for r_ in d["grid"] for c in r_["cells"])
    eq("격자 표 행 수", len(rows), n_cells)
    for row in d["grid"]:
        for c in row["cells"]:
            lab = row["growth_label"]
            hit = [x for x in rows if x[0] == lab
                   and x[1] == dmap[c["discount_key"]]["label"]]
            if not true(f"격자 행 {row['growth_key']}/{c['discount_key']}",
                        len(hit) == 1):
                continue
            r_ = hit[0]
            if c.get("diverges"):
                eq(f"격자 {row['growth_key']}/{c['discount_key']} 발산",
                   r_[2], "발산")
                continue
            v = c["verdicts"][MOS_MAIN]
            eq(f"격자 {row['growth_key']}/{c['discount_key']} 가치",
               r_[2], f"${c['value_per_share']:,.0f}")
            eq(f"격자 {row['growth_key']}/{c['discount_key']} 현재가 대비",
               r_[3], f"{c['upside_vs_price'] * 100:+.0f}%")
            eq(f"격자 {row['growth_key']}/{c['discount_key']} 매수상한",
               r_[4], f"${v['buy_limit']:,.0f}")
            eq(f"격자 {row['growth_key']}/{c['discount_key']} 판정",
               r_[5], "합격" if v["pass"] else "불합격")
    by_disc = {k: sum(1 for r_ in d["grid"] for c in r_["cells"]
                      if c["discount_key"] == k and not c.get("diverges")
                      and c["verdicts"][MOS_MAIN]["pass"])
               for k in DISCOUNT_ORDER}
    for key, want in (
            ("n_pass", sum(by_disc.values())),
            ("n_pass_bond", by_disc["bond30"]),
            ("n_pass_buffett", by_disc["bond30_plus3"]),
            ("n_pass_high", by_disc["project10"] + by_disc["project11"])):
        m = re.search(rf'<b data-v="{key}">(.*?)</b>', page)
        if true(f"본문 {key} 표시", bool(m)):
            eq(f"본문 {key}", m.group(1), f"{want}칸")
    true("순수 국채 할인율의 한계를 본문에 명시",
         "주식에 쓸 수 없다" in page and "발산" in page)

    # 의미색이 산술과 어긋나지 않는지: 합격은 over, 불합격은 under 로만.
    bad = []
    for mm_ in re.finditer(r'<td class="r" data-state="(over|under)">'
                           r'<b>(합격|불합격)</b></td>', page):
        if (mm_.group(1) == "over") != (mm_.group(2) == "합격"):
            bad.append(mm_.group(0))
    true("판정 색이 판정과 일치", not bad, str(bad[:2]))

    # ---------------------------------------------------------- 요구 성장률
    _, rows = find_table(page, "10년 평균 CAGR")
    eq("요구 성장률 표 행 수", len(rows), len(d["required_growth"]))
    for r_ in d["required_growth"]:
        lab = f"안전마진 {int(r_['margin_of_safety'] * 100)}%"
        hit = [x for x in rows
               if x[0] == dmap[r_["discount_key"]]["label"] and x[1] == lab]
        tag = f"{r_['discount_key']}/{lab}"
        if not true(f"요구 행 {tag}", len(hit) == 1):
            continue
        x = hit[0]
        if not r_["reachable"]:
            eq(f"요구 {tag} 없음 표기", x[2], "없음")
            continue
        eq(f"요구 {tag} 1년차", x[2], f"{r_['growth_year1'] * 100:.1f}%")
        eq(f"요구 {tag} 10년 CAGR", x[3],
           f"{r_['nopat_cagr_10y'] * 100:.1f}%")
        eq(f"요구 {tag} 실질", x[4],
           f"{r_['nopat_cagr_10y_real'] * 100:.1f}%")
        eq(f"요구 {tag} 백분위", x[5],
           f"상위 {r_['base_rate_percentile_at_or_above'] * 100:.1f}%")
    true("요구 성장률 칸의 방향이 반대임을 명시",
         "방향이 반대" in page)
    true("기초율이 실질임을 명시", "이 수치는 실질" in page
         or "<b>이 수치는 실질</b>" in page)
    true("생존편향을 명시", "생존편향" in page)

    # ------------------------------------------------------------ 가격 분해
    _, rows = find_table(page, "무엇을 가정하는가")
    for label, want in (("평범한 대형주 가치", sp["ordinary_company_value"]),
                        ("예외성 프리미엄", sp["premium_in_price"]),
                        ("(참고) 예외성 유지 가치", sp["exceptional_value"])):
        hit = [x for x in rows if x[0] == label]
        if not true(f"분해 행 {label}", len(hit) == 1):
            continue
        eq(f"분해 {label} 주당", hit[0][1], f"${want:,.0f}")
    true("분해 프리미엄 비중 본문",
         f"{sp['premium_share_of_price'] * 100:.0f}%" in page)
    if true("분해 막대 ordinary", "ordinary" in bars):
        near("분해 막대 ordinary 비례", float(bars["ordinary"]),
             sp["ordinary_company_value"] / sp["exceptional_value"] * 100,
             0.02)
    m = re.search(r'class="pline" data-bar="price" style="left:([\d.]+)%"',
                  page)
    if true("분해 현재가 선", bool(m)):
        near("분해 현재가 선 위치", float(m.group(1)),
             px / sp["exceptional_value"] * 100, 0.02)

    # ------------------------------------------------------- 버핏 인용 전문
    for b in d["buffett"]:
        m = re.search(rf'<blockquote data-bq="{b["key"]}">(.*?)</blockquote>',
                      page, re.S)
        if not true(f"버핏 블록 {b['key']}", bool(m)):
            continue
        blob = m.group(1)
        quotes = [html.unescape(re.sub(r"<[^>]+>", "", q)).strip("“”“” ")
                  for q in re.findall(r'<p class="en">(.*?)</p>', blob, re.S)]
        want = [b[k] for k in ("quote", "quote2", "quote3") if b.get(k)]
        eq(f"버핏 {b['key']} 인용 개수", len(quotes), len(want))
        for i, (got, exp) in enumerate(zip(quotes, want), 1):
            eq(f"버핏 {b['key']} 인용{i} 전문", got, exp)
        true(f"버핏 {b['key']} 출처 링크", b["source_url"] in blob)
    true("할인율 가산이 버핏 방식이 아님을 명시",
         "할인율에 얹는 것은 버핏의 방식이 아닙니다" in page
         or "할인율에 더하는 프리미엄으로" in page)
    true("CEO 프리미엄을 만들지 않았음을 명시",
         "프리미엄을 발명하지 않" in page or "만들지 않았습니다" in page)

    # -------------------------------------------------- 프랜차이즈 검정
    _, rows = find_table(page, "버핏의 조건")
    eq("프랜차이즈 표 행 수", len(rows), len(d["franchise"]["tests"]))
    for t in d["franchise"]["tests"]:
        hit = [x for x in rows if x[0] == t["criterion"]]
        if not true(f"프랜차이즈 행 {t['criterion'][:14]}", len(hit) == 1):
            continue
        eq(f"프랜차이즈 {t['criterion'][:10]} 판정", hit[0][1], t["verdict"])
    true("10-K 위험요인 인용", ff["key_personnel_risk_factor"] in
         html.unescape(page))
    true("10-K 고객집중 인용", ff["customer_concentration_sentence"] in
         html.unescape(page))
    true("관측치 0개 서술", "관측치가 0개" in page
         or "관측치가 \n0개" in page)

    # ------------------------------------------------------------ 10년 기록
    _, rows = find_table(page, "평균 투하자본")
    eq("기록 표 행 수", len(rows), len(d["franchise"]["roic_years"]))
    for y in d["franchise"]["roic_years"]:
        hit = [x for x in rows if x[0] == f"FY{y['fiscal_year']}"]
        if not true(f"기록 FY{y['fiscal_year']} 행", len(hit) == 1):
            continue
        eq(f"기록 FY{y['fiscal_year']} 영업이익", hit[0][2],
           f"{y['operating_income'] / BN:,.1f}")
        eq(f"기록 FY{y['fiscal_year']} ROIC", hit[0][4],
           f"{y['roic'] * 100:.0f}%")

    # ----------------------------------------------------------- 시나리오
    _, rows = find_table(page, "정당화 성장률")
    eq("시나리오 표 행 수", len(rows), len(d["scenario_valuations"]))
    for s in d["scenario_valuations"]:
        hit = [x for x in rows if x[0] == s["scenario"]]
        if not true(f"시나리오 행 {s['scenario']}", len(hit) == 1):
            continue
        eq(f"시나리오 {s['scenario']} 주당가치", hit[0][4],
           f"${s['value_per_share']:,.0f}")
        eq(f"시나리오 {s['scenario']} 정당화 성장률", hit[0][6],
           f"{s['implied_growth_at_price'] * 100:.1f}%"
           if s["implied_growth_at_price"] is not None else "없음")

    # ------------------------------------------------------------- 결론·한계
    r30 = next(r for r in d["required_growth"]
               if r["discount_key"] == "bond30_plus3"
               and abs(r["margin_of_safety"] - 0.30) < 1e-9)
    true("결론의 요구 CAGR 수치",
         f"{r30['nopat_cagr_10y'] * 100:.1f}%" in page)
    true("결론의 백분위 수치",
         f"{r30['base_rate_percentile_at_or_above'] * 100:.1f}%" in page)
    true("한계 항목 수", page.count("<li>") >= len(d["limits"]) + 5)
    for needle in ("장중", "사유", "11월 17일", "증분 ROIC"):
        true(f"한계에 {needle}", needle in page)
    true("장중임을 머리말에 명시", "장이 열려 있습니다" in page
         if p["is_intraday"] else True)
    true("자료 기준일 표기", f'<b>{d["generated"]}</b>' in page)
    return passed, fails


def mutations(d):
    """변이 목록. 값은 **엔진에서 끌어옵니다** — 리터럴로 적으면 시세가
    움직인 날 '대상 없음'으로 조용히 통과합니다."""
    p, dec, sp = d["price"], d["price_decomposition"], d["price_split"]
    px = p["price"]
    cell0 = next(c for r in d["grid"] if r["growth_key"] == "own_sustained"
                 for c in r["cells"] if c["discount_key"] == "bond30_plus3")
    req0 = next(r for r in d["required_growth"]
                if r["discount_key"] == "bond30_plus3"
                and abs(r["margin_of_safety"] - 0.30) < 1e-9)
    hi = dec["window_high"]["price"]
    return [
        ("격자 주당가치 표기",
         lambda s: s.replace(f"<b>${cell0['value_per_share']:,.0f}</b>",
                             "<b>$999</b>", 1)),
        ("격자 매수상한 표기",
         lambda s: s.replace(
             f"<b>${cell0['verdicts']['30%']['buy_limit']:,.0f}</b>",
             "<b>$998</b>", 1)),
        ("판정 뒤집기",
         lambda s: s.replace('data-state="over"><b>합격</b>',
                             'data-state="under"><b>합격</b>', 1)),
        ("요구 성장률 표기",
         lambda s: s.replace(f"<b>{req0['growth_year1'] * 100:.1f}%</b>",
                             "<b>99.9%</b>", 1)),
        ("요구 10년 CAGR 표기",
         lambda s: s.replace(f"<b>{req0['nopat_cagr_10y'] * 100:.1f}%</b>",
                             "<b>88.8%</b>", 1)),
        ("기초율 백분위 표기 (표)",
         lambda s: s.replace(
             f'<td class="r" data-state="flag">상위 '
             f'{req0["base_rate_percentile_at_or_above"] * 100:.1f}%</td>',
             '<td class="r" data-state="flag">상위 77.7%</td>', 1)),
        ("합격 칸 수 표기",
         lambda s: re.sub(r'(<b data-v="n_pass">)[^<]+', r"\g<1>99칸", s,
                          count=1)),
        ("버핏 기준 합격 칸 수 표기",
         lambda s: re.sub(r'(<b data-v="n_pass_buffett">)[^<]+',
                          r"\g<1>0칸", s, count=1)),
        ("순수 국채 한계 서술 제거",
         lambda s: s.replace("주식에 쓸 수 없다", "주식에 쓸 수 있다", 1)),
        ("판정 본문 요구 CAGR",
         lambda s: re.sub(r'(<b data-v="req_cagr">)[^<]+',
                          r"\g<1>향후 10년 NOPAT 연평균 99.9% 성장", s,
                          count=1)),
        ("판정 본문 기초율 백분위",
         lambda s: re.sub(r'(<b data-v="req_pct">)[^<]+',
                          r"\g<1>상위 77.7%", s, count=1)),
        ("판정 본문 프리미엄",
         lambda s: re.sub(r'(<b data-v="premium">)[^<]+',
                          r"\g<1>$997", s, count=1)),
        ("판정 본문 프리미엄 비중",
         lambda s: re.sub(r'(<b data-v="premium_share">)[^<]+',
                          r"\g<1>99%", s, count=1)),
        ("칩 현재가 표기",
         lambda s: s.replace(f'<b class="num">${px:,.2f}</b>',
                             '<b class="num">$1.23</b>', 1)),
        ("칩 사건 전 하락 표기",
         lambda s: s.replace(
             f'<b class="num">{dec["before_event"] * 100:+.1f}%</b>',
             '<b class="num">-1.0%</b>', 1)),
        ("하락 막대 길이",
         lambda s: re.sub(r'(data-bar="pre" style="width:)[\d.]+',
                          r"\g<1>5.0", s, count=1)),
        ("분해 막대 길이",
         lambda s: re.sub(r'(data-bar="ordinary" style="width:)[\d.]+',
                          r"\g<1>95.0", s, count=1)),
        ("현재가 선 위치",
         lambda s: re.sub(r'(data-bar="price" style="left:)[\d.]+',
                          r"\g<1>5.0", s, count=1)),
        ("가격 분해 프리미엄 표기 (표)",
         lambda s: s.replace(
             f'<td class="r" data-state="flag">'
             f'<b>${sp["premium_in_price"]:,.0f}</b></td>',
             '<td class="r" data-state="flag"><b>$997</b></td>', 1)),
        ("공시 원문 한 단어",
         lambda s: s.replace("effective immediately", "effective in 2027", 1)),
        ("버핏 인용문 뒷부분",
         lambda s: s.replace("cannot inflict mortal damage",
                             "can inflict mortal damage", 1)),
        ("버핏 인용 한 블록 제거",
         lambda s: re.sub(r'<blockquote data-bq="jockey">.*?</blockquote>',
                          "", s, flags=re.S)),
        ("사유 미기재 서술 제거",
         lambda s: s.replace("공시에 사임 사유는 없습니다", "사유가 적혀 있습니다",
                             1)),
        ("보도·공시 구분 서술 제거",
         lambda s: s.replace("보도이고 공시가 아닙니다", "확인된 사실입니다", 1)),
        ("프랜차이즈 '미검증'을 충족으로",
         lambda s: s.replace("<b>미검증</b>", "<b>충족</b>", 1)),
        ("10-K 위험요인 인용 훼손",
         lambda s: s.replace("attract, retain, and motivate",
                             "attract and retain", 1)),
        ("10년 기록 ROIC 한 해",
         lambda s: s.replace(
             f">{d['franchise']['roic_years'][-1]['roic'] * 100:.0f}%<",
             ">11%<", 1)),
        ("시세 표 종가 한 칸",
         lambda s: s.replace(f'>${p["rows"][-2]["close"]:,.2f}<',
                             ">$1.00<", 1)),
        ("타이틀 제거", lambda s: re.sub(r"<title>.*?</title>", "", s)),
        ("타이틀을 설명문으로", lambda s: re.sub(
            r"<title>.*?</title>",
            "<title>엔비디아 CEO 사임에 따른 투자 판정 보고서</title>", s)),
        ("keep-all 제거", lambda s: s.replace("word-break:keep-all", "")),
        ("거터 제거", lambda s: s.replace(
            "max(16px,env(safe-area-inset-left,0px))", "16px")),
        ("다크 가드 제거",
         lambda s: s.replace(':root:not([data-theme="light"])', ":root")),
        ("맨 :root 에서 토큰 제거",
         lambda s: re.sub(r"(^:root\{.*?)--flag:[^;]+;", r"\1", s,
                          count=1, flags=re.S | re.M)),
        ("doctype 추가", lambda s: "<!doctype html>" + s),
        ("허용 안 된 호스트",
         lambda s: s.replace("</div>",
                             '<img src="https://evil.example.com/x.png">'
                             "</div>", 1)),
        ("표를 스크롤 밖으로",
         lambda s: s.replace('<div class="scroll"><table>', "<table>", 1)),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    args = ap.parse_args()
    d = json.load(open(DATA, encoding="utf-8"))
    page = build(d)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"wrote {OUT} ({len(page):,} bytes)")

    if args.verify or args.mutate:
        passed, fails = verify(page, d)
        print(f"페이지 검사 {passed + len(fails)}건 — 통과 {passed}, "
              f"실패 {len(fails)}")
        for x in fails[:25]:
            print("  ✗", x)
        if fails:
            return 1
    if args.mutate:
        muts = mutations(d)
        print(f"\n변이 검정 {len(muts)}건 — 페이지를 훼손해 검사가 실제로 "
              f"실패하는지 확인")
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
                print(f"  ✓ {name}: {len(f2)}건 실패 — {f2[0][:80]}")
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
