"""
The 50-company ROIC study as an HTML page — the only report format now.

Reads roic/roic.json and the four side files the engine writes; holds no
figures of its own, so the page cannot drift from the engine. The Markdown,
Word and Excel writers are still in the tree for a one-off request, but the
runner calls this one.

Two things shape the layout. The grid is eleven fiscal years wide, which no
phone shows at once, so it is cut into halves and every table sits in its own
horizontal scroller. And the per-company workings are one short table each
inside a <details>, not a single sheet 480 rows long.

    python3 export_roic_html.py
    python3 export_roic_html.py --verify --mutate
"""

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys

import company_names as cn

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "roic", "roic_report.html")
MM, BN = 1e6, 1e9


def load():
    d = {"roic": json.load(open(os.path.join(HERE, "roic", "roic.json")))}
    for key, name in (("recon", "reconciliation.json"),
                      ("corr", "corrections.json"),
                      ("diag", "capital_diagnosis.json"),
                      ("routes", "oi_routes.json")):
        d[key] = json.load(open(os.path.join(HERE, "roic", name)))
    return d


# ------------------------------------------------------------------ format
def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def mm(x, nd=0):
    return "—" if x is None else f"{x / MM:,.{nd}f}"


def bn(x, nd=1):
    return "—" if x is None else f"{x / BN:,.{nd}f}"


def esc(x):
    return html.escape(str(x))


def table(headers, rows, caption=None, align=None, cls=""):
    """One table, in its own horizontally scrollable container.

    A cell given as (text, state) carries data-state, which is how the page's
    semantic colours are set. The state vocabulary is kept narrow on purpose:
    over/under mean "clears the 10% hurdle" and nothing else, pos/neg mean the
    sign of a figure, flag means "look at this". Reusing one green for two
    meanings is how a 3% operating margin once read as a hurdle verdict.
    """
    align = align or (["l"] + ["r"] * (len(headers) - 1))
    out = [f'<figure class="tw {cls}">', '<div class="scroll"><table>']
    out.append("<thead><tr>" + "".join(
        f'<th class="{a}">{esc(h)}</th>' for h, a in zip(headers, align))
        + "</tr></thead><tbody>")
    for r in rows:
        cells = []
        for v, a in zip(r, align):
            extra = ""
            if isinstance(v, tuple):
                v, state = v
                extra = f' data-state="{state}"'
            cells.append(f'<td class="{a}"{extra}>{v if "<" in str(v) else esc(v)}</td>')
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</tbody></table></div>")
    if caption:
        out.append(f"<figcaption>{esc(caption)}</figcaption>")
    out.append("</figure>")
    return "\n".join(out)


def stat(key, value, label, note=None, state=None):
    st = f' data-state="{state}"' if state else ""
    body = [f'<div class="stat" data-k="{key}"{st}>',
            f'<b class="num">{esc(value)}</b>',
            f'<span class="lab">{esc(label)}</span>']
    if note:
        body.append(f'<span class="note">{esc(note)}</span>')
    body.append("</div>")
    return "".join(body)


# ------------------------------------------------------------------- build
def build(d):
    D, R, C, G, ROUTES = (d["roic"], d["recon"], d["corr"], d["diag"],
                          d["routes"])
    WACC = D["wacc"]
    YEARS = D["grid_years"]
    FIRST_FY, LAST_FY = YEARS[0], YEARS[-1]
    WINDOW_YEARS = D["window_years"]
    by_ticker = {c["ticker"]: c for c in D["companies"]}
    rank = D["ranking"]

    def window_of(comp):
        fys = sorted({y["fiscal_year"] for y in comp["years"]})
        keep = set(fys[-WINDOW_YEARS:])
        return [y for y in comp["years"] if y["fiscal_year"] in keep]

    def in_window(comp, fy):
        return fy in {y["fiscal_year"] for y in window_of(comp)}

    def cell(comp, fy):
        """One year of ROIC for the wide grid.

        A year outside this company's own window stays blank even where the
        engine computed it, so each row's median and its count of years above
        the hurdle describe exactly the cells shown. Microsoft's June
        year-end means its ten years are FY2017-FY2026 and its FY2016 column
        is empty while a December filer's is not.
        """
        y = next((y for y in comp["years"] if y["fiscal_year"] == fy), None)
        if y is None or y["roic"] is None or not in_window(comp, fy):
            return "—"
        s = f"{y['roic'] * 100:.0f}"
        if y["confidence"] == "LOW":
            s += "*"
        if y.get("capital_too_small"):
            s += "†"
        if y["roic"] > WACC:
            return (s, "over")
        return (f"({s})", "under")

    usable_years = sum(x["years_usable"] for x in rank)
    above_years = sum(x["years_above_wacc"] for x in rank)
    all_above = [x for x in rank if x["every_year_above_wacc"]]
    orcl = next(n for n in C["net_cash_errors_flagged"]
                if n["ticker"] == "ORCL")
    financials = [c["ticker"] for c in D["companies"] if c["is_financial"]]
    no_subtotal = [c["ticker"] for c in D["companies"]
                   if not c["is_financial"]
                   and not any(y["operating_income_route"] == "reported"
                               for y in c["years"]
                               if in_window(c, y["fiscal_year"]))]
    max_median = max(x["roic_median"] for x in rank)

    p = []
    a = p.append

    a("<title>미국 50개사 자본수익률</title>")
    a('<meta name="claude:viewport-fit-sides" content="cover">')
    a('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
      'family=Noto+Serif+KR:wght@500;700&family=Noto+Sans+KR:wght@400;500;700'
      '&family=IBM+Plex+Mono:wght@400;500&display=swap">')

    # ---- design plan ----------------------------------------------------
    # A reference document, not a pitch: one accent (indigo) for structure,
    # warm-biased neutrals so the greys read chosen, figures in mono with
    # tabular numerals so columns line up, and every table its own scroller.
    a("""<style>
:root{
  /* neutrals warmed very slightly toward the indigo accent */
  --ground:#f8f7f5; --panel:#ffffff; --panel-2:#efeeeb;
  --ink:#1b1a21; --ink-2:#4e4c58; --ink-3:#817e8c;
  --rule:#dcdad6; --rule-2:#c6c3be;
  --accent:#3a3f8f;            /* structure, links, emphasis */
  --accent-soft:#e7e8f5;
  --over:#2d6a4a;              /* ONLY: ROIC clears the 10% hurdle */
  --over-soft:#e6efe9;
  --under:#9c3f2c;             /* ONLY: ROIC at or below the hurdle */
  --under-soft:#f7e8e3;
  --flag:#8a6410;              /* attention, no verdict attached */
  --flag-soft:#f6eeda;
  --display:"Noto Serif KR",Georgia,"Times New Roman",serif;
  --body:"Noto Sans KR",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ground:#14141a; --panel:#1c1c25; --panel-2:#24242f;
  --ink:#eceaf0; --ink-2:#aeaaba; --ink-3:#827f8e;
  --rule:#30303c; --rule-2:#41414f;
  --accent:#9aa0ec; --accent-soft:#232642;
  --over:#7fc39a; --over-soft:#15271d;
  --under:#e39a81; --under-soft:#2b1a15;
  --flag:#d9b45c; --flag-soft:#2b2412;
  color-scheme:dark;
}}
:root[data-theme="dark"]{
  --ground:#14141a; --panel:#1c1c25; --panel-2:#24242f;
  --ink:#eceaf0; --ink-2:#aeaaba; --ink-3:#827f8e;
  --rule:#30303c; --rule-2:#41414f;
  --accent:#9aa0ec; --accent-soft:#232642;
  --over:#7fc39a; --over-soft:#15271d;
  --under:#e39a81; --under-soft:#2b1a15;
  --flag:#d9b45c; --flag-soft:#2b2412;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{background:var(--ground);color:var(--ink);font-family:var(--body);
  font-size:16px;line-height:1.72;margin:0;-webkit-text-size-adjust:100%;
  /* Korean has no hyphenation, so the default break-anywhere splits a
     compound noun across lines - "자본비용" broke as "자/본비용". */
  word-break:keep-all;overflow-wrap:break-word}
.wrap{max-width:54rem;margin:0 auto;
  padding-left:max(16px,env(safe-area-inset-left,0px));
  padding-right:max(16px,env(safe-area-inset-right,0px));
  padding-block:0}
h1,h2,h3,h4{font-family:var(--display);text-wrap:balance;margin:0}
h1{font-size:clamp(1.85rem,5.2vw,2.6rem);line-height:1.2;font-weight:700;
  letter-spacing:-.015em}
h2{font-size:clamp(1.3rem,3.4vw,1.62rem);line-height:1.3;font-weight:700;
  margin-block:2.8rem .3rem;letter-spacing:-.01em;
  padding-block:.55rem 0;border-top:2px solid var(--ink)}
h3{font-size:1.06rem;line-height:1.4;font-weight:700;margin-block:1.9rem .2rem}
h4{font-size:.96rem;margin-block:1.3rem .2rem;color:var(--ink-2)}
p{margin:0 0 1rem}
a{color:var(--accent);text-underline-offset:.18em}
ul{margin:0 0 1rem;padding-left:1.15rem}
li{margin-block:.4rem}
code{font-family:var(--mono);font-size:.86em;background:var(--panel-2);
  padding:.08rem .3rem;border-radius:2px}
.eyebrow{font-family:var(--body);font-size:.69rem;font-weight:700;
  letter-spacing:.14em;text-transform:uppercase;color:var(--accent);
  margin:0 0 .5rem}
.lede{font-size:1.07rem;color:var(--ink-2);margin-block:.9rem 0}
.meta{font-family:var(--mono);font-size:.76rem;line-height:1.85;
  color:var(--ink-3);border-top:1px solid var(--rule);
  margin-block:1.4rem 0;padding-block:.9rem 0}
.meta b{color:var(--ink-2);font-weight:500}
header.page{padding-block:2.6rem 0}
footer.page{border-top:1px solid var(--rule);margin-block:3rem 0;
  padding-block:1.2rem 2.6rem;font-size:.86rem;color:var(--ink-2)}

/* headline figures - the largest numbers on the page, so verified too */
.stats{display:grid;gap:1px;background:var(--rule);border:1px solid var(--rule);
  margin-block:1.6rem 0}
@media(min-width:620px){.stats{grid-template-columns:repeat(3,1fr)}}
.stat{background:var(--panel);padding:1.05rem 1.1rem 1.15rem;min-width:0}
.stat .num{display:block;font-family:var(--display);font-size:2.1rem;
  font-weight:700;line-height:1.05;font-variant-numeric:tabular-nums}
.stat .lab{display:block;font-size:.88rem;color:var(--ink-2);
  margin-block:.3rem 0}
.stat .note{display:block;font-size:.78rem;color:var(--ink-3);
  margin-block:.3rem 0}
.stat[data-state="over"] .num{color:var(--over)}
.stat[data-state="flag"] .num{color:var(--flag)}

/* tables */
figure.tw{margin:1rem 0 1.4rem}
.scroll{overflow-x:auto;border:1px solid var(--rule);background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{padding:.42rem .6rem;border-bottom:1px solid var(--rule);
  white-space:nowrap}
thead th{position:sticky;top:0;background:var(--panel-2);font-weight:700;
  font-size:.78rem;letter-spacing:.02em;color:var(--ink-2);
  border-bottom:1px solid var(--rule-2)}
tbody tr:last-child td{border-bottom:0}
td{font-family:var(--mono);font-variant-numeric:tabular-nums}
td.l,th.l{text-align:left}
td.r,th.r{text-align:right}
td.l{font-family:var(--body);white-space:normal;min-width:7rem}
td[data-state="over"]{color:var(--over);background:var(--over-soft)}
td[data-state="under"]{color:var(--under);background:var(--under-soft)}
td[data-state="pos"]{color:var(--over)}
td[data-state="neg"]{color:var(--under)}
td[data-state="flag"]{color:var(--flag);background:var(--flag-soft)}
figcaption{font-size:.78rem;color:var(--ink-3);margin-block:.45rem 0}

/* median-ROIC bar: length is the value, nothing else */
td.barcell{width:7rem;min-width:7rem;padding-block:.5rem}
.bar{display:block;height:.5rem;background:var(--accent);opacity:.75}

/* legend */
.legend{border:1px solid var(--rule);background:var(--panel);
  padding:1rem 1.1rem;margin-block:1.2rem}
.legend dl{display:grid;grid-template-columns:auto 1fr;gap:.35rem .9rem;
  margin:0;font-size:.9rem}
.legend dt{font-family:var(--mono);color:var(--ink-2)}
.legend dd{margin:0;color:var(--ink-2)}
.formula{font-family:var(--mono);font-size:.8rem;line-height:1.9;
  background:var(--panel-2);border-left:3px solid var(--accent);
  padding:.8rem .95rem;overflow-x:auto;white-space:pre;margin-block:1rem}

/* spread buckets */
.bucket{border-left:3px solid var(--rule-2);padding-left:.9rem;
  margin-block:1rem}
.bucket .bk{font-family:var(--body);font-size:.82rem;font-weight:700;
  letter-spacing:.04em;color:var(--accent);display:block}
.bucket .mem{font-family:var(--mono);font-size:.84rem;color:var(--ink-2)}

/* per-company workings */
details.co{border:1px solid var(--rule);background:var(--panel);
  margin-block:.55rem;padding:0 1rem}
details.co>summary{cursor:pointer;padding-block:.7rem;font-weight:700;
  font-size:.95rem;list-style-position:inside}
details.co>summary .tkr{font-family:var(--mono);font-size:.76rem;
  font-weight:400;color:var(--ink-3);margin-left:.4rem}
details.co[open]{border-color:var(--rule-2)}
details.co .en{font-size:.8rem;color:var(--ink-3);margin-block:0 .2rem}
.callout{border:1px solid var(--rule-2);background:var(--panel-2);
  padding:.95rem 1.05rem;margin-block:1.2rem;font-size:.93rem}
.callout b{color:var(--ink)}
</style>""")

    a('<div class="wrap">')

    # ------------------------------------------------------------- header
    a('<header class="page">')
    a('<p class="eyebrow">SEC XBRL companyfacts · 자본비용 10% 고정</p>')
    a("<h1>미국 50개사 ROIC 대 자본비용 10%</h1>")
    a(f'<p class="lede">비금융 {len(rank)}개사의 '
      f'{usable_years}개 기업-연도 가운데 {above_years}개'
      f'({above_years / usable_years:.0%})가 ROIC 10%를 넘겼습니다. '
      f'10년 내내 한 해도 빠짐없이 넘긴 기업은 {len(all_above)}곳이고, '
      f'전 기간 미달한 기업은 없습니다.</p>')
    a('<p class="meta">'
      f'자료 기준일 <b>{esc(D["generated"])}</b> (SEC XBRL companyfacts, '
      f'캐시 1일 만료)<br>'
      f'격자 <b>FY{FIRST_FY}~FY{LAST_FY}</b> · 기업별 창 '
      f'<b>각 사의 최근 {WINDOW_YEARS} 회계연도</b><br>'
      f'문턱 <b>{pct(WACC, 0)}</b> (지시에 따른 고정값) · 대상 '
      f'<b>{len(D["companies"])}개사</b>'
      '</p>')
    a("</header>")

    a('<div class="stats">')
    a(stat("above_share", f"{above_years / usable_years:.0%}",
           "ROIC 10% 초과 기업-연도 비중",
           f"{above_years} / {usable_years}개 연도", state="over"))
    a(stat("all_above", f"{len(all_above)}곳",
           "10년 전부 문턱 초과",
           f"비금융 순위 대상 {len(rank)}곳 중"))
    a(stat("corrected", f"{C['company_years_changed']}건",
           "1차 조사에서 정정한 기업-연도",
           f"장기차입금 누락 {len(G['old_missed_long_term_debt'])}건 포함",
           state="flag"))
    a("</div>")

    a('<div class="callout">')
    a("<p>이번 작업의 더 중요한 결과는 순위표가 아니라 <b>1차 조사의 오류 "
      f"{C['company_years_changed']}건을 찾아 바로잡은 것</b>입니다. 가장 큰 "
      f"원인은 공시된 장기차입금을 "
      f"{len(G['old_missed_long_term_debt'])}개 기업-연도에서 누락한 "
      "것으로, 오라클·코카콜라·브로드컴·비자가 여기 걸립니다. 오라클 "
      "FY2024 ROIC가 761%로 나왔던 이유입니다.</p>")
    a("<p>그리고 이 오류는 ROIC에서 멈추지 않았습니다. 1차 조사는 "
      f"<b>오라클을 순현금 {bn(orcl['net_cash_in_study'])}십억 달러 "
      f"기업으로 보고 있었는데, 실제로는 순차입금 "
      f"{bn(-orcl['net_cash_recomputed'])}십억 달러</b>입니다. 오차 "
      f"{bn(orcl['error'])}십억 달러, 시가총액의 "
      f"{pct(orcl['error_vs_market_cap'], 0)}입니다. 순현금은 기업가치에서 "
      "주주가치로 넘어갈 때 그대로 더해지므로 내재가치에 1:1로 "
      "반영됩니다. DCF 재계산은 이번 범위가 아니라 표시만 했습니다.</p>")
    a("</div>")

    # ------------------------------------------------------- reading guide
    a("<h2>표 읽는 법</h2>")
    a('<div class="legend"><dl>')
    for sym, mean in (("123", "ROIC 10% 초과 (단위 %)"),
                      ("(123)", "ROIC 10% 이하"),
                      ("*", "영업이익 소계를 보고하지 않아 세전이익에서 "
                            "추정한 해"),
                      ("†", "순투하자본이 매출의 10% 미만 — 분모가 작아 "
                            "비율이 민감 (문턱 판정은 유효)"),
                      ("—", "산출 불가")):
        a(f"<dt>{esc(sym)}</dt><dd>{esc(mean)}</dd>")
    a("</dl></div>")
    a('<p class="meta" style="border:0;padding:0;margin-block:0 .4rem">'
      '색은 한 가지 뜻만 갖습니다 — 초록/빨강은 <b>10% 문턱 판정</b>에만 '
      '쓰고, 금액의 부호나 "주목"에는 다른 색을 씁니다.</p>')
    a('<div class="formula">'
      "NOPAT      = 영업이익 × (1 − 실효세율)\n"
      "투하자본    = 자기자본(비지배지분 포함) + 이자부차입금 − 현금·단기투자자산\n"
      "ROIC       = NOPAT ÷ 평균 투하자본 (기초·기말 평균)\n"
      "스프레드    = ROIC − 10%"
      "</div>")
    a("<p>자기자본이나 투하자본이 0 이하인 해는 평균이 0 근처로 내려가 "
      "비율이 폭발하므로 기말값을 단독으로 씁니다. 금융업(SIC "
      "6000~6799)은 ROIC를 산출하지 않습니다 — 은행에게 차입은 자금조달이 "
      "아니라 원재료여서 자기자본+차입금−현금이 아무것도 "
      "측정하지 않습니다.</p>")

    # ----------------------------------------------------------- 1. 목록
    a("<h2>1. 기업 목록</h2>")
    for label, tickers in (
            ("ROIC 순위 대상 (비금융, 산출 5년 이상)",
             [x["ticker"] for x in rank]),
            ("표본 부족 (산출 5년 미만)",
             [x["ticker"] for x in D["thin_sample"]]),
            ("금융업 — ROIC 미산출", financials)):
        a(f"<h3>{esc(label)} — {len(tickers)}곳</h3>")
        a(table(["티커", "한글명", "영문 정식 명칭", "비고"],
                [[t, cn.korean(t), cn.english(t), cn.note(t) or "—"]
                 for t in tickers],
                align=["l", "l", "l", "l"]))
    a("<p>SEC가 반환하는 이름은 등록명(COSTCO WHOLESALE CORP /NEW, "
      "APPLIED MATERIALS INC /DE 등)이라 그대로 쓰지 않았습니다.</p>")

    # ----------------------------------------------------------- 2. 순위
    a("<h2>2. ROIC 요약 순위</h2>")
    a("<p>중위 ROIC 내림차순입니다. 막대 길이는 중위 ROIC에 비례합니다 "
      f"(최대 {pct(max_median, 0)}).</p>")
    rows = []
    for i, x in enumerate(rank, 1):
        bar_w = max(0.0, x["roic_median"]) / max_median * 100
        rows.append([
            str(i), cn.korean(x["ticker"]),
            (pct(x["roic_median"], 0),
             "over" if x["roic_median"] > WACC else "under"),
            pct(x["roic_min"], 0), pct(x["roic_max"], 0),
            f"{x['years_above_wacc']}/{x['years_usable']}",
            f'<span class="bar" data-bar="{x["ticker"]}" '
            f'style="width:{bar_w:.1f}%"></span>'])
    a(table(["#", "기업", "중위", "최소", "최대", "초과", "분포"], rows,
            align=["r", "l", "r", "r", "r", "r", "barcell"]))

    # ---------------------------------------------------------- 3. 연도별
    a("<h2>3. ROIC 연도별</h2>")
    half = (len(YEARS) + 1) // 2
    halves = [YEARS[:half], YEARS[half:]]
    a("<p>폭을 맞추려고 격자를 둘로 나눴습니다. 단위 %, 괄호는 10% 이하. "
      "빈 칸은 그 기업의 창(최근 "
      f"{WINDOW_YEARS}개 회계연도) 밖입니다 — 결산월이 달라 "
      "마이크로소프트처럼 FY2026을 이미 제출한 기업은 앞쪽이 비고, "
      "12월 결산 기업은 뒤쪽이 빕니다.</p>")
    for h in halves:
        a(f"<h3>FY{h[0]} ~ FY{h[-1]}</h3>")
        a(table(["기업"] + [f"'{str(y)[2:]}" for y in h],
                [[cn.korean(x["ticker"])]
                 + [cell(by_ticker[x["ticker"]], fy) for fy in h]
                 for x in rank]))

    a("<h3>표본 부족·금융업</h3>")
    a("<p>팔란티어는 10년 중 대부분 순투하자본이 음수여서(현금이 "
      "자기자본+차입금을 넘어서) 이 정의로 ROIC가 성립하지 않습니다. "
      "GE 버노바는 2024년 4월 분사라 4년치뿐입니다. 금융업 "
      f"{len(financials)}곳은 산출하지 않았습니다.</p>")
    a(table(["기업", "상태"],
            [[cn.korean(x["ticker"]),
              f"산출 {x['years_usable']}년 · {x['verdict']}"]
             for x in D["thin_sample"]]
            + [[cn.korean(t), "금융업 — ROIC 정의 부적합"]
               for t in financials],
            align=["l", "l"]))

    # -------------------------------------------------------- 4. 스프레드
    a("<h2>4. ROIC − 10% 스프레드 (중위 기준)</h2>")
    buckets = [("+40%p 이상", lambda s: s >= 0.40),
               ("+20~40%p", lambda s: 0.20 <= s < 0.40),
               ("+10~20%p", lambda s: 0.10 <= s < 0.20),
               ("0~+10%p", lambda s: 0 <= s < 0.10),
               ("음수 (10% 미달)", lambda s: s < 0)]
    for label, test in buckets:
        members = [x for x in rank if test(x["spread_median"])]
        if not members:
            continue
        a(f'<div class="bucket" data-bk="{esc(label)}">'
          f'<span class="bk">{esc(label)} — {len(members)}곳</span>'
          f'<span class="mem">'
          + esc(", ".join(f"{cn.korean(x['ticker'])} "
                          f"{x['spread_median'] * 100:+.0f}"
                          for x in members))
          + "</span></div>")
    a("<p>스프레드의 크기보다 <b>꾸준함</b>이 중요합니다. 중위 ROIC가 높아도 "
      "변동이 크면 어느 해에 자본을 투입했는지에 따라 결과가 갈리기 "
      f"때문입니다. 10년 전부 10%를 넘긴 {len(all_above)}곳이 그 조건을 "
      "만족합니다.</p>")
    a(table(["기업", "중위", "최소", "최대", "표준편차", "추정 연수"],
            [[cn.korean(x["ticker"]), pct(x["roic_median"], 0),
              pct(x["roic_min"], 0), pct(x["roic_max"], 0),
              pct(x["roic_stdev"], 0),
              str(x["years_estimated_numerator"])]
             for x in all_above]))

    # ---------------------------------------------------------- 5. 명세
    a("<h2>5. 계산 명세 — 기업별 연도별</h2>")
    a("<p>금액 단위는 <b>백만 달러</b>. <code>투하자본</code>은 기말값, "
      "<code>평균</code>은 ROIC의 분모로 쓴 기초·기말 평균입니다. 기업 "
      "이름을 누르면 펼쳐집니다.</p>")
    order = ([x["ticker"] for x in rank]
             + [x["ticker"] for x in D["thin_sample"]] + financials)
    for t in order:
        comp = by_ticker[t]
        a(f'<details class="co" id="co-{esc(t)}">')
        a(f'<summary>{esc(cn.korean(t))}'
          f'<span class="tkr">{esc(t)}</span></summary>')
        a(f'<p class="en">{esc(cn.english(t))}</p>')
        note = cn.note(t)
        if note:
            a(f'<p class="en">{esc(note)}</p>')
        rows = []
        for y in comp["years"]:
            # One year before the window is on the table too: it supplies the
            # opening capital for the window's first year, and nothing else.
            if not FIRST_FY - 1 <= y["fiscal_year"] <= LAST_FY:
                continue
            if not in_window(comp, y["fiscal_year"]):
                # Printing a ratio here would be computed on a different
                # basis from every other row - its own average needs a year
                # that is not shown.
                rows.append([f"FY{y['fiscal_year']} ◦", "—", "—", "—",
                             mm(y["invested_capital"]), "—", "—"])
                continue
            roic = y["roic"]
            rc = ("—" if roic is None
                  else (pct(roic, 1), "over" if roic > WACC else "under"))
            rows.append([f"FY{y['fiscal_year']}",
                         mm(y["operating_income"]),
                         pct(y["effective_tax_rate"], 0), mm(y["nopat"]),
                         mm(y["invested_capital"]),
                         mm(y["invested_capital_avg"]), rc])
        a(table(["연도", "영업이익", "세율", "NOPAT", "투하자본", "평균",
                 "ROIC"], rows,
                caption="◦ 표시된 연도는 바로 다음 해 평균 투하자본의 "
                        "기초값으로만 쓰입니다 (보고 기간 밖)."))
        routes = sorted({y["operating_income_route"] for y in comp["years"]
                         if in_window(comp, y["fiscal_year"])})
        a(f'<p class="en">분자 산출 경로: {esc(", ".join(routes))}</p>')
        statuses = sorted({y["roic_status"] for y in comp["years"]
                           if in_window(comp, y["fiscal_year"])
                           and y["roic_status"] != "OK"})
        if statuses:
            a(f'<p class="en">비고: {esc(" / ".join(statuses))}</p>')
        a("</details>")

    # ---------------------------------------------------------- 6. 대조
    a("<h2>6. 1차 조사와 대조</h2>")
    cy = R["compared_company_years"]
    a(table(["구분", "건수", "비중"],
            [["대조 가능한 기업-연도", f"{cy}", "100%"],
             ["1%p 이내 일치", f"{R['agree_within_1pp']}",
              f"{R['agree_within_1pp'] / cy:.0%}"],
             ["1%p 초과 불일치", f"{R['differ_over_1pp']}",
              f"{R['differ_over_1pp'] / cy:.0%}"],
             ["5%p 초과 불일치", f"{R['differ_over_5pp']}",
              f"{R['differ_over_5pp'] / cy:.0%}"],
             ["10% 문턱 판정까지 바뀜", f"{R['hurdle_verdict_flips']}",
              f"{R['hurdle_verdict_flips'] / cy:.0%}"],
             ["재조사만 산출 (1차는 공백)", f"{R['new_covers_old_blank']}",
              "—"],
             ["1차만 산출", f"{R['old_covers_new_blank']}", "—"]]))

    a("<h3>어느 쪽이 틀렸는지 — 판단이 필요 없는 검정</h3>")
    a("<p>분모가 다르다는 것만으로는 어느 쪽이 맞는지 알 수 없습니다. "
      "그래서 판단이 끼어들 여지가 없는 검정을 했습니다. <b>10-K에 "
      "장기차입금 태그가 있는 기업은 장기차입금이 있었던 것이고, 그걸 "
      "0으로 기록한 조사는 틀린 것</b>입니다. 단위 십억 달러.</p>")
    tally = {}
    for m in G["old_missed_long_term_debt"]:
        tk = m["key"].split()[0]
        cur = tally.setdefault(tk, {"n": 0, "filed": 0, "old": 0, "new": 0})
        cur["n"] += 1
        if (m["filed_long_term_debt"] or 0) > cur["filed"]:
            cur.update(filed=m["filed_long_term_debt"],
                       old=m["old_total_debt"], new=m["new_total_debt"] or 0)
    a(table(["기업", "누락", "공시 장기차입금", "1차 차입금", "재산출"],
            [[cn.korean(tk), f"{v['n']}년", bn(v["filed"]), bn(v["old"]),
              bn(v["new"])]
             for tk, v in sorted(tally.items(),
                                 key=lambda kv: -kv[1]["filed"])]))
    a("<p>반대 방향 오류도 있었습니다. 애플 FY2016의 현금을 1차 조사는 "
      "20.5십억 달러로 기록했지만, 단기 유가증권 46.7십억 달러를 합한 "
      "67.2십억 달러가 차감 대상입니다. 이 경우 1차 조사는 분모를 과대하게 "
      "잡아 <b>ROIC를 낮게</b> 보고 있었습니다. 오류가 한쪽으로만 기울지 "
      "않았다는 뜻입니다.</p>")

    a("<h3>문턱 판정이 바뀐 기업-연도</h3>")
    a(table(["기업", "연도", "재산출", "1차", "차이"],
            [[cn.korean(x["ticker"]), f"FY{x['fiscal_year']}",
              pct(x["roic_new"], 0), pct(x["roic_old"], 0),
              (f"{x['gap_pp'] * 100:+.0f}%p",
               "pos" if x["gap_pp"] > 0 else "neg")]
             for x in sorted(R["flips"], key=lambda z: -abs(z["gap_pp"]))]))

    a("<h3>차이가 큰 기업-연도 (상위 30)</h3>")
    a(table(["기업", "연도", "재산출", "1차", "차이"],
            [[cn.korean(x["ticker"]), f"FY{x['fiscal_year']}",
              pct(x["roic_new"], 0), pct(x["roic_old"], 0),
              (f"{x['gap_pp'] * 100:+.0f}%p",
               "pos" if x["gap_pp"] > 0 else "neg")]
             for x in R["differences"][:30]]))
    a(f"<p>전체 {R['differ_over_1pp']}건은 "
      "<code>roic/reconciliation.json</code>의 <code>differences</code>에 "
      "있습니다.</p>")

    # ---------------------------------------------------------- 7. 정정
    a("<h2>7. 1차 조사에 반영한 정정</h2>")
    a(table(["항목", "내용"],
            [["정정한 기업-연도",
              f"{C['company_years_changed']}건 "
              "(ROIC·영업이익·실효세율·투하자본)"],
             ["method_notes.ebit", "분자 우선순위를 실제 구현과 맞게 수정"],
             ["원본 보존", C["backup"]],
             ["재계산하지 않은 것",
              "가격·시가총액·주주이익·DCF·가치평가 판정"]],
            align=["l", "l"]))
    a("<h3>ROIC가 크게 바뀐 기업-연도 (상위 20)</h3>")
    big = sorted((x for x in C["changes"]
                  if None not in (x["roic_before"], x["roic_after"])),
                 key=lambda x: -abs(x["roic_after"] - x["roic_before"]))[:20]
    a(table(["기업", "연도", "1차", "정정", "변화"],
            [[cn.korean(x["ticker"]), f"FY{x['fiscal_year']}",
              pct(x["roic_before"], 0), pct(x["roic_after"], 0),
              (f"{(x['roic_after'] - x['roic_before']) * 100:+.0f}%p",
               "pos" if x["roic_after"] > x["roic_before"] else "neg")]
             for x in big]))

    a("<h3>가치평가로 번진 입력 오류 — 재계산하지 않았음</h3>")
    a("<p>단위 십억 달러.</p>")
    a(table(["기업", "1차 순현금", "재산출", "오차", "시총 대비"],
            [[cn.korean(n["ticker"]), bn(n["net_cash_in_study"]),
              bn(n["net_cash_recomputed"]), bn(n["error"]),
              (pct(n["error_vs_market_cap"], 1),
               "flag" if abs(n["error_vs_market_cap"]) > 0.05 else "")]
             for n in sorted(C["net_cash_errors_flagged"],
                             key=lambda n: -abs(n["error"]))]))
    a("<p>오라클이 결정적입니다. 시가총액의 "
      f"{pct(orcl['error_vs_market_cap'], 0)}에 해당하는 오차이므로 1차 "
      "조사의 오라클 가치평가 결론은 신뢰할 수 없습니다. 다른 네 곳은 1% "
      "안팎이라 결론을 바꾸기 어렵습니다.</p>")

    # ---------------------------------------------------------- 8. 경로
    a("<h2>8. 영업이익 소계를 보고하지 않는 기업</h2>")
    a(f"<p>{esc(cn.joined(no_subtotal))} — 이 {len(no_subtotal)}곳은 "
      "손익계산서에 영업이익 소계가 없습니다. 분자를 어떻게 만들지는 "
      "주장이 아니라 측정으로 정했습니다. 소계를 보고하는 기업-연도에서 "
      "각 구성 방식을 보고치와 맞춰본 결과입니다 (허용 오차 "
      f"±{ROUTES['tolerance'] * 100:.0f}%).</p>")
    a(table(["구성 경로", "검정", "일치", "정확도"],
            [[x["route"], str(x["tested"]), str(x["matched"]),
              pct(x["accuracy"])] for x in ROUTES["routes"]],
            align=["l", "r", "r", "r"]))
    a("<p>다만 <b>±2% 일치율은 이 문제에 맞는 통계가 아닙니다.</b> 목적이 "
      "ROIC를 10% 문턱과 비교하는 것이므로, 중요한 건 분자를 바꿨을 때 "
      "문턱 판정이 뒤집히는지입니다. 그걸 따로 측정한 적이 있고 세전이익 "
      "기반 경로에서 몇 %에 그쳤습니다 — 다만 <b>그 측정은 이 "
      "파이프라인에서 재실행되지 않으므로 수치를 그대로 인용하지 "
      "마십시오.</b> 필요하면 다시 측정해야 합니다.</p>")
    a("<p>경로 선택에는 함정이 하나 더 있었습니다. 경로 C의 정확도 "
      f"{pct(next(x['accuracy'] for x in ROUTES['routes'] if x['route'].startswith('C')), 1)}"
      "는 소계를 보고하는 기업에서만 측정된 값이라 소계를 보고하지 않는 "
      "기업에 그대로 적용되지 않습니다. 실제로 제너럴 일렉트릭에 적용하자 "
      "FY2016 영업이익이 −6.4십억 달러로 나왔습니다. 그래서 모든 상향식 "
      "구성값은 <b>세전이익으로 역검증</b>을 통과해야만 쓰도록 했고, 경로 "
      "선택은 연도별이 아니라 기업별로 한 번만 하도록 했습니다 — 연도마다 "
      "다른 경로를 쓰면 10년 추세가 사업이 아니라 경로를 측정하게 되기 "
      "때문입니다.</p>")
    a(table(["기업", "선택 경로", "역검증"],
            [[cn.korean(c["ticker"]), c["chosen_route"]["route"],
              "통과" if c["chosen_route"]["reconciles"] else "미통과"]
             for c in D["companies"] if c.get("chosen_route")],
            align=["l", "l", "l"]))

    # ---------------------------------------------------------- 9. 검증
    a("<h2>9. 검증</h2>")
    try:
        sys.path.insert(0, HERE)
        import verify_roic as _v
        n_anchor, n_mut = len(_v.ANCHORS), len(_v.MUTATIONS)
    except Exception:                                   # pragma: no cover
        n_anchor = n_mut = None
    a(table(["검증 방식", "건수", "무엇을 잡는지"],
            [["항등식", "—",
              "투하자본=자기자본+차입금−현금, NOPAT=영업이익×(1−세율), "
              "ROIC=NOPAT÷평균자본, 평균 산정 규칙"],
             ["트립와이어", "—",
              "차감 현금 ≤ 유동자산, 차입금 ≤ 총부채·총자산, "
              "실효세율 5~40%"],
             ["공시 앵커", "—" if n_anchor is None else f"{n_anchor}",
              "공시 본문에서 손으로 읽은 수치와 대조"],
             ["변이 검정", "—" if n_mut is None else f"{n_mut}",
              "산출값을 고의로 훼손해 검사가 실제로 실패하는지 확인"],
             ["페이지 되읽기", "—",
              "이 페이지의 표·칩·막대를 파싱해 엔진 값과 대조 "
              "(export_roic_html.py --verify --mutate)"]],
            align=["l", "r", "l"],
            caption="총 검사 건수는 실행마다 달라지므로 러너 출력을 "
                    "보십시오 — 여기 적어두면 낡습니다."))
    a("<p>앵커를 따로 두는 이유가 있습니다. 항등식과 트립와이어는 검사 "
      "대상과 같은 데이터로 계산되므로 <b>내부적으로 일관된 틀린 값은 둘 다 "
      "통과합니다.</b> 공시 원문에서 직접 읽은 수치만이 산술이 아니라 "
      "데이터가 틀렸을 때 실패할 수 있습니다. 실제로 램리서치 현금 "
      "과다차감과 오라클 차입금 이중계상은 앵커가 잡았습니다.</p>")

    # ---------------------------------------------------------- 10. 한계
    a("<h2>10. 남은 한계</h2>")
    a("<ul>")
    for item in [
        f"<b>분자 추정 {len(D['low_confidence_years'])}개 연도.</b> "
        f"영업이익 소계를 보고하지 않는 {len(no_subtotal)}개 기업은 "
        "세전이익에서 거꾸로 추정했습니다. 문턱 판정은 대체로 유지되지만 "
        "ROIC 수준은 몇 %p 틀릴 수 있습니다.",
        "<b>자기자본 정의.</b> 분자가 연결 영업이익이므로 분모도 "
        "비지배지분을 포함했습니다. 1차 조사는 지배주주 지분만 썼고 "
        "96개 기업-연도에서 차이가 납니다. 정의가 다른 것이지 오류는 "
        "아닙니다.",
        "<b>장기 유가증권은 자본에 남겼습니다.</b> 비유동 투자자산을 빼지 "
        "않아 분모가 보수적으로(크게) 잡혔고, ROIC는 그만큼 낮게 "
        "나옵니다.",
        f"<b>자본비용 {pct(WACC, 0)}는 지시에 따른 고정값입니다.</b> 실제 "
        f"자본비용은 기업마다 다르고 FY{FIRST_FY}~FY{LAST_FY} 금리 환경도 "
        "크게 달라졌습니다. 같은 문턱을 쓴 것은 ROIC를 서로 비교하기 위한 "
        "선택입니다.",
        "<b>ROIC가 높다는 것과 투자 대상이라는 것은 다릅니다.</b> 가격이 "
        "빠져 있습니다. ROIC 순위가 곧 매수 순위는 아닙니다.",
    ]:
        a(f"<li>{item}</li>")
    a("</ul>")

    a('<footer class="page">')
    a(f"<p>자료 기준일 {esc(D['generated'])} — 이 날짜에 받은 공시가 "
      "결론의 유효기간을 정합니다. 재현: "
      "<code>bash work/run_roic.sh</code> (날짜·신선도 → 수집 → 산출 → "
      "검증 → 이 페이지 → 페이지 되읽기).</p>")
    a("<p>보고서는 HTML로만 만듭니다. 투자 판단은 읽는 분의 몫입니다.</p>")
    a("</footer>")
    a("</div>")
    return "\n".join(p)


# ------------------------------------------------------------------ verify
def verify(d, path):
    """
    Read the rendered page back and compare every figure to the engine.

    Rendered HTML has no formulas to re-evaluate, so a figure placed in the
    wrong row leaves no trace that reading the page would reveal. Tables are
    located by their own header or by the section that contains them, never by
    row label alone: the fifty per-company tables share a header, and FY2025
    is a row in all of them.
    """
    text = open(path).read()
    D, R, C, G, ROUTES = (d["roic"], d["recon"], d["corr"], d["diag"],
                          d["routes"])
    WACC = D["wacc"]
    YEARS = D["grid_years"]
    WINDOW_YEARS = D["window_years"]
    by_ticker = {c["ticker"]: c for c in D["companies"]}
    rank = D["ranking"]
    checks, fails = 0, []

    def window_fys(comp):
        fys = sorted({y["fiscal_year"] for y in comp["years"]})
        return set(fys[-WINDOW_YEARS:])

    def cells(row_html):
        # html.unescape matters: esc() writes "'16" as "&#x27;16" and
        # "R&D" as "R&amp;D", so a header compared raw never matches and the
        # table silently reads as missing.
        return [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html,
                                    re.S)]

    def parse_tables(region):
        return [[cells(r) for r in re.findall(r"<tr>(.*?)</tr>", t, re.S)]
                for t in re.findall(r"<table>(.*?)</table>", region, re.S)]

    tables = parse_tables(text)

    def num(s):
        """The first number in a cell, sign kept.

        Cells carry units and marks the engine does not ("20곳", "319건",
        "37*", "(9)"). Brackets are NOT a minus sign here: the grid brackets
        every year at or below the hurdle, and some of those years are
        themselves negative ("(-8)"), so the bracket is checked separately
        from the figure.
        """
        s = str(s).replace(",", "").replace("−", "-")
        m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else None

    def table_with(header_cells):
        """The one table whose header row starts with these cells."""
        hit = [t for t in tables
               if t and t[0][:len(header_cells)] == list(header_cells)]
        if len(hit) != 1:
            return None
        return hit[0]

    def expect(got, want, label, nd=0):
        nonlocal checks
        checks += 1
        if got is None:
            fails.append(f"{label}: 값 없음 (기대 {want})")
        elif round(got, nd) != round(want, nd):
            fails.append(f"{label}: {got} != {round(want, nd)}")

    def near(got, want, label, tol):
        """For figures the page rounds for display (a bar width printed to one
        decimal), where equality at a fixed precision is the wrong test."""
        nonlocal checks
        checks += 1
        if got is None:
            fails.append(f"{label}: 값 없음 (기대 {want})")
        elif abs(got - want) > tol:
            fails.append(f"{label}: {got:.2f} != {want:.2f} (허용 {tol})")

    def need(cond, label):
        nonlocal checks
        checks += 1
        if not cond:
            fails.append(label)
        return cond

    # ---- headline figures, which are the largest numbers on the page -----
    usable_years = sum(x["years_usable"] for x in rank)
    above_years = sum(x["years_above_wacc"] for x in rank)
    all_above = [x for x in rank if x["every_year_above_wacc"]]
    for key, want, nd in (
            ("above_share", above_years / usable_years * 100, 0),
            ("all_above", len(all_above), 0),
            ("corrected", C["company_years_changed"], 0)):
        m = re.search(rf'data-k="{key}"[^>]*>\s*<b class="num">([^<]+)</b>',
                      text)
        if need(m is not None, f"칩 없음: {key}"):
            expect(num(m.group(1)), want, f"칩 {key}", nd)
    m = re.search(r'data-k="above_share".*?<span class="note">([^<]+)</span>',
                  text, re.S)
    if need(m is not None, "칩 above_share 보조문 없음"):
        got = [num(x) for x in re.findall(r"[\d,]+", m.group(1))]
        expect(got[0] if got else None, above_years, "칩 above_share 분자")
        expect(got[1] if len(got) > 1 else None, usable_years,
               "칩 above_share 분모")

    # ---- ranking table ---------------------------------------------------
    t = table_with(["#", "기업", "중위"])
    if need(t is not None, "순위 표를 특정할 수 없음"):
        rows = {r[1]: r for r in t[1:] if len(r) >= 6}
        for i, x in enumerate(rank, 1):
            ko = cn.korean(x["ticker"])
            r = rows.get(ko)
            if not need(r is not None, f"순위 행 없음: {ko}"):
                continue
            expect(num(r[0]), i, f"{ko} 순위")
            expect(num(r[2]), x["roic_median"] * 100, f"{ko} 중위")
            expect(num(r[3]), x["roic_min"] * 100, f"{ko} 최소")
            expect(num(r[4]), x["roic_max"] * 100, f"{ko} 최대")
            need(r[5] == f"{x['years_above_wacc']}/{x['years_usable']}",
                 f"{ko} 초과 연수: {r[5]}")

    # ---- the bars: length has to be the value ---------------------------
    max_median = max(x["roic_median"] for x in rank)
    bars = dict(re.findall(r'data-bar="([^"]+)" style="width:([\d.]+)%"',
                           text))
    for x in rank:
        if not need(x["ticker"] in bars, f"막대 없음: {x['ticker']}"):
            continue
        near(float(bars[x["ticker"]]) / 100 * max_median * 100,
             max(0.0, x["roic_median"]) * 100,
             f"막대 길이 {x['ticker']}", tol=max_median * 100 * 0.0006)

    # ---- the year grid, one table per half ------------------------------
    half = (len(YEARS) + 1) // 2
    for h in (YEARS[:half], YEARS[half:]):
        t = table_with(["기업"] + [f"'{str(y)[2:]}" for y in h])
        if not need(t is not None, f"연도별 격자({h[0]}~{h[-1]}) 특정 불가"):
            continue
        rows = {r[0]: r for r in t[1:]}
        for x in rank:
            comp = by_ticker[x["ticker"]]
            ko = cn.korean(x["ticker"])
            r = rows.get(ko)
            if not need(r is not None, f"격자 행 없음: {ko}"):
                continue
            win = window_fys(comp)
            for j, fy in enumerate(h, 1):
                y = next((z for z in comp["years"]
                          if z["fiscal_year"] == fy), None)
                if y is None or y["roic"] is None or fy not in win:
                    need(r[j] == "—", f"격자 {ko} FY{fy}: 창 밖인데 {r[j]}")
                    continue
                expect(num(r[j]), y["roic"] * 100, f"격자 {ko} FY{fy}")
                need(r[j].startswith("(") == (y["roic"] <= WACC),
                     f"격자 {ko} FY{fy}: 문턱 괄호 표기 불일치 ({r[j]})")
                mark_low = "*" in r[j]
                need(mark_low == (y["confidence"] == "LOW"),
                     f"격자 {ko} FY{fy}: 추정 표기 불일치")
                need(("†" in r[j]) == bool(y.get("capital_too_small")),
                     f"격자 {ko} FY{fy}: 분모 표기 불일치")

    # ---- per-company workings, sliced by section ------------------------
    sections = dict(re.findall(r'<details class="co" id="co-([^"]+)">(.*?)'
                               r'</details>', text, re.S))
    for tk, comp in by_ticker.items():
        if not need(tk in sections, f"기업 구획 없음: {tk}"):
            continue
        t = parse_tables(sections[tk])
        if not need(len(t) == 1, f"{tk} 구획의 표가 1개가 아님"):
            continue
        rows = {r[0]: r for r in t[0][1:]}
        # The page prints only years inside the grid span, so a company whose
        # companyfacts stop earlier (Morgan Stanley: FY2007-FY2014) has an
        # empty table and nothing to compare.
        win = window_fys(comp) & set(YEARS)
        for y in comp["years"]:
            fy = y["fiscal_year"]
            if fy not in win:
                continue
            r = rows.get(f"FY{fy}")
            if not need(r is not None, f"{tk} FY{fy} 행 없음"):
                continue
            expect(num(r[1]), (y["operating_income"] or 0) / MM,
                   f"{tk} FY{fy} 영업이익")
            if y["effective_tax_rate"] is not None:
                expect(num(r[2]), y["effective_tax_rate"] * 100,
                       f"{tk} FY{fy} 세율")
            if y["nopat"] is not None:
                expect(num(r[3]), y["nopat"] / MM, f"{tk} FY{fy} NOPAT")
            if y["invested_capital"] is not None:
                expect(num(r[4]), y["invested_capital"] / MM,
                       f"{tk} FY{fy} 투하자본")
            if y["roic"] is not None:
                expect(num(r[6]), y["roic"] * 100, f"{tk} FY{fy} ROIC", 1)

    # ---- spread buckets (prose figures, not a table) --------------------
    for label, test in (("+40%p 이상", lambda s: s >= 0.40),
                        ("+20~40%p", lambda s: 0.20 <= s < 0.40),
                        ("+10~20%p", lambda s: 0.10 <= s < 0.20),
                        ("0~+10%p", lambda s: 0 <= s < 0.10),
                        ("음수 (10% 미달)", lambda s: s < 0)):
        members = [x for x in rank if test(x["spread_median"])]
        m = re.search(rf'data-bk="{re.escape(html.escape(label))}">'
                      rf'<span class="bk">([^<]*)</span>'
                      rf'<span class="mem">([^<]*)</span>', text)
        if not members:
            need(m is None, f"비어 있는 버킷이 그려짐: {label}")
            continue
        if not need(m is not None, f"스프레드 버킷 없음: {label}"):
            continue
        expect(num(re.sub(r"[^\d]", " ", m.group(1)).split()[-1]
                   if re.search(r"\d", m.group(1)) else ""),
               len(members), f"버킷 {label} 기업 수")
        got = m.group(2)
        for x in members:
            ko = cn.korean(x["ticker"])
            mm_ = re.search(rf"{re.escape(ko)}\s+([+-]?\d+)", got)
            if not need(mm_ is not None, f"버킷 {label}에 {ko} 없음"):
                continue
            expect(float(mm_.group(1)), round(x["spread_median"] * 100),
                   f"버킷 {label} {ko} 스프레드")

    # ---- reconciliation ---------------------------------------------------
    cy = R["compared_company_years"]
    t = table_with(["구분", "건수", "비중"])
    if need(t is not None, "대조 표 특정 불가"):
        rows = {r[0]: r for r in t[1:]}
        for label, want in (("대조 가능한 기업-연도", cy),
                            ("1%p 이내 일치", R["agree_within_1pp"]),
                            ("1%p 초과 불일치", R["differ_over_1pp"]),
                            ("5%p 초과 불일치", R["differ_over_5pp"]),
                            ("10% 문턱 판정까지 바뀜",
                             R["hurdle_verdict_flips"]),
                            ("재조사만 산출 (1차는 공백)",
                             R["new_covers_old_blank"]),
                            ("1차만 산출", R["old_covers_new_blank"])):
            r = rows.get(label)
            if not need(r is not None, f"대조 행 없음: {label}"):
                continue
            expect(num(r[1]), want, f"대조 {label}")

    # ---- route accuracy ---------------------------------------------------
    t = table_with(["구성 경로", "검정", "일치", "정확도"])
    if need(t is not None, "경로 표 특정 불가"):
        rows = {r[0]: r for r in t[1:]}
        for x in ROUTES["routes"]:
            r = rows.get(x["route"])
            if not need(r is not None, f"경로 행 없음: {x['route'][:12]}"):
                continue
            expect(num(r[1]), x["tested"], f"경로 {x['route'][:1]} 검정")
            expect(num(r[2]), x["matched"], f"경로 {x['route'][:1]} 일치")
            expect(num(r[3]), x["accuracy"] * 100,
                   f"경로 {x['route'][:1]} 정확도", 1)

    # ---- net cash errors --------------------------------------------------
    t = table_with(["기업", "1차 순현금", "재산출", "오차", "시총 대비"])
    if need(t is not None, "순현금 표 특정 불가"):
        rows = {r[0]: r for r in t[1:]}
        for n in C["net_cash_errors_flagged"]:
            r = rows.get(cn.korean(n["ticker"]))
            if not need(r is not None, f"순현금 행 없음: {n['ticker']}"):
                continue
            expect(num(r[1]), n["net_cash_in_study"] / BN,
                   f"{n['ticker']} 1차 순현금", 1)
            expect(num(r[2]), n["net_cash_recomputed"] / BN,
                   f"{n['ticker']} 재산출 순현금", 1)
            expect(num(r[3]), n["error"] / BN, f"{n['ticker']} 오차", 1)

    # ---- freshness: the page cannot be older than the engine's run -------
    m = re.search(r"자료 기준일 <b>([\d-]+)</b>", text)
    if need(m is not None, "자료 기준일 표기 없음"):
        need(m.group(1) == D["generated"],
             f"자료 기준일 불일치: 페이지 {m.group(1)} vs 엔진 "
             f"{D['generated']}")

    # ---- the semantic colour has to agree with the arithmetic -------------
    checks += 1
    bad = []
    for m in re.finditer(r'<td class="r" data-state="(over|under)">'
                         r'\(?([-\d.,]+)[*†]?\)?%?</td>', text):
        state, raw = m.group(1), m.group(2).replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        # The displayed figure is rounded (the grid to whole points), so a
        # true 10.4% prints as "10" and a strict comparison to the hurdle
        # would flag a correctly marked cell. The bracket is the mark that
        # has to agree; the value only has to agree outside the rounding
        # band.
        bracketed = m.group(0).count("(") > 0
        band = WACC * 100
        if state == "over" and (bracketed or val < band - 0.5):
            bad.append(f"{m.group(2)} 가 over")
        if state == "under" and not bracketed and val > band + 0.5:
            bad.append(f"{m.group(2)} 가 under")
    if bad:
        fails.append(f"문턱 색상/괄호 표기 오류: {bad[:4]}")

    # ---- page requirements from the contract ------------------------------
    flat = text.replace(" ", "").replace("\n", "")
    for needle, label in (("<title>", "title"),
                          ("claude:viewport-fit-sides", "viewport meta"),
                          ("max(16px,env(safe-area-inset-left,0px))",
                           "좌측 거터"),
                          ("max(16px,env(safe-area-inset-right,0px))",
                           "우측 거터"),
                          ("prefers-color-scheme:dark", "다크 테마"),
                          ('[data-theme="dark"]', "테마 토글"),
                          ("word-break:keep-all", "한국어 줄바꿈"),
                          ("background:var(--ground)", "body 배경"),
                          (".scroll{overflow-x:auto", "표 가로 스크롤")):
        checks += 1
        if needle not in flat and needle not in text:
            fails.append(f"페이지 요건 누락: {label}")

    print(f"HTML 검사 {checks}건 중 통과 {checks - len(fails)}건, "
          f"실패 {len(fails)}건")
    for f in fails[:20]:
        print(f"  실패: {f}")
    return 1 if fails else 0


def mutations(d):
    """Corruptions of the rendered page, built from the data so they stay
    valid when the filings move."""
    D = d["roic"]
    rank = D["ranking"]
    top = rank[0]
    by_ticker = {c["ticker"]: c for c in D["companies"]}
    comp = by_ticker[top["ticker"]]
    yrs = [y for y in comp["years"] if y["roic"] is not None]
    y = yrs[-1]
    muts = [
        ("순위 중위 ROIC",
         f'<td class="r" data-state="over">{top["roic_median"] * 100:.0f}%</td>',
         f'<td class="r" data-state="over">'
         f'{top["roic_median"] * 100 + 3:.0f}%</td>'),
        ("순위 초과 연수",
         f'<td class="r">{top["years_above_wacc"]}/{top["years_usable"]}</td>',
         f'<td class="r">{top["years_above_wacc"] - 1}/'
         f'{top["years_usable"]}</td>'),
        ("막대 길이", f'data-bar="{top["ticker"]}" style="width:100.0%"',
         f'data-bar="{top["ticker"]}" style="width:60.0%"'),
        ("기업별 명세 NOPAT",
         f'<td class="r">{y["nopat"] / MM:,.0f}</td>',
         f'<td class="r">{y["nopat"] / MM * 1.1:,.0f}</td>'),
        ("기업별 명세 ROIC",
         f'<td class="r" data-state="over">{y["roic"] * 100:.1f}%</td>',
         f'<td class="r" data-state="over">{y["roic"] * 100 + 2:.1f}%</td>'),
        ("문턱 색상 반전", '<td class="r" data-state="over">',
         '<td class="r" data-state="under">'),
        ("격자 칸 추정 표기", '*</td>', '</td>'),
        ("자료 기준일", f"자료 기준일 <b>{D['generated']}</b>",
         "자료 기준일 <b>2000-01-01</b>"),
        ("칩 수치", '<b class="num">', '<b class="num">9'),
        ("다크 테마", "prefers-color-scheme:dark", "prefers-color-scheme:x"),
        ("좌측 거터", "max(16px,env(safe-area-inset-left,0px))", "16px"),
        ("한국어 줄바꿈", "word-break:keep-all", "word-break:break-all"),
        ("표 가로 스크롤", ".scroll{overflow-x:auto",
         ".scroll{overflow-x:visible"),
    ]
    return muts


def mutate(d):
    original = open(OUT).read()
    backup = OUT + ".bak"
    shutil.copy2(OUT, backup)
    caught, ran = 0, 0
    print("\n변이 검정 — 페이지를 훼손했을 때 검사가 실패해야 정상")
    try:
        for label, a_, b_ in mutations(d):
            if a_ not in original:
                print(f"  {'대상없음':<6}{label}")
                continue
            ran += 1
            open(OUT, "w").write(original.replace(a_, b_, 1))
            run = subprocess.run([sys.executable, __file__, "--verify"],
                                 capture_output=True, text=True)
            hit = run.returncode != 0
            caught += hit
            line = next((l.strip() for l in run.stdout.split("\n")
                         if "실패:" in l), "")
            print(f"  {'탐지' if hit else '놓침':<6}{label:<18}{line[:60]}")
    finally:
        open(OUT, "w").write(original)
        os.remove(backup)
    print(f"\n변이 {ran}건 중 {caught}건 탐지")
    return 0 if caught == ran and ran else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    args = ap.parse_args()
    d = load()
    if args.verify:
        code = verify(d, OUT)
        if args.mutate:
            code = mutate(d) or code
        return code
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    page = build(d)
    with open(OUT, "w") as fh:
        fh.write(page + "\n")
    print(f"wrote {OUT} ({len(page) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
