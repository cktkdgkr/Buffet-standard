"""
The SpaceX and Tesla report as an HTML page.

Built from spx_tsla.json, the same source the Markdown and Word versions read,
so the three cannot drift apart. Not a mechanical render of the Markdown
blocks: the page's central idea is that the same filings support two different
verdicts depending on the period you measure, and that deserves a layout the
other two formats cannot give it.

    python3 export_spx_tsla_html.py
    python3 export_spx_tsla_html.py --verify
"""

import argparse
import html
import json
import os
import re
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "spx", "spx_tsla.json")
OUT = os.path.join(HERE, "spx", "spx_tsla_report.html")
MM, BN = 1e6, 1e9


def load():
    d = json.load(open(DATA))
    d["TSLA"]["ratios"]["in_service"] = {
        int(k): v for k, v in d["TSLA"]["ratios"]["in_service"].items()}
    return d


def pct(x, nd=1):
    return "—" if x is None else f"{x * 100:.{nd}f}%"


def signed(x, nd=1):
    return "—" if x is None else f"{x * 100:+.{nd}f}"


def mm(x, nd=0):
    return "—" if x is None else f"{x / MM:,.{nd}f}"


def bn(x, nd=1):
    return "—" if x is None else f"{x / BN:,.{nd}f}"


def esc(x):
    return html.escape(str(x))


def table(headers, rows, caption=None, align=None, cls=""):
    """A table in its own horizontally scrollable container."""
    align = align or (["l"] + ["r"] * (len(headers) - 1))
    out = [f'<figure class="tw {cls}">']
    out.append('<div class="scroll"><table>')
    out.append("<thead><tr>" + "".join(
        f'<th class="{a}">{esc(h)}</th>' for h, a in zip(headers, align))
        + "</tr></thead><tbody>")
    for r in rows:
        cells = []
        for i, (v, a) in enumerate(zip(r, align)):
            extra = ""
            if isinstance(v, tuple):          # (text, state)
                v, state = v
                extra = f' data-state="{state}"'
            cells.append(f'<td class="{a}"{extra}>{esc(v)}</td>')
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</tbody></table></div>")
    if caption:
        out.append(f"<figcaption>{esc(caption)}</figcaption>")
    out.append("</figure>")
    return "\n".join(out)


def build(d):
    S, T = d["SPCX"], d["TSLA"]
    SR, TR = S["ratios"], T["ratios"]
    Q = S["quarterly"]
    rr = Q["q3_run_rate_views"]
    sep = S["balance_sheets"]["2026-09-30"]
    dec = S["balance_sheets"]["2025-12-31"]
    com = (S.get("disclosed_commitments") or [None])[0]
    years_t = [y for y in T["annual_roic"] if y["fiscal_year"] >= 2016]
    seg_order = [("Connectivity", "스타링크"), ("SI", "슈퍼인텔리전스"),
                 ("Space", "발사체")]
    nopat_2025 = [y for y in years_t if y["fiscal_year"] == 2025][0]["nopat"]
    VIEW_KO = {"reported": "보고", "operating": "영업", "in_service": "가동"}

    p = []
    a = p.append

    a("<title>스페이스X 테슬라 자본수익률</title>")
    a('<meta name="claude:viewport-fit-sides" content="cover">')
    a('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
      'family=Noto+Serif+KR:wght@500;700&family=Noto+Sans+KR:wght@400;500;700'
      '&family=IBM+Plex+Mono:wght@400;500&display=swap">')

    # ---- design plan ------------------------------------------------------
    # Layout: a measured document - sticky section rail, full-bleed bands for
    # the two readings that disagree, every figure table its own scroller.
    a("""<style>
:root{
  /* neutrals pulled slightly toward the petrol accent, so greys read chosen */
  --ground:#f7f8f8; --panel:#ffffff; --panel-2:#eef1f2;
  --ink:#16201f; --ink-2:#4a5755; --ink-3:#77827f;
  --rule:#d7dddc; --rule-2:#c2cac8;
  --accent:#0f6b6f;          /* petrol: structure, links, emphasis */
  --accent-soft:#e2eeee;
  --over:#2f6b45;            /* semantic: clears the hurdle */
  --over-soft:#e6efe8;
  --under:#99452f;           /* semantic: falls short */
  --under-soft:#f6e8e4;
  --display:"Noto Serif KR",Georgia,"Times New Roman",serif;
  --body:"Noto Sans KR",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ground:#101716; --panel:#182220; --panel-2:#1f2b29;
  --ink:#e8eceb; --ink-2:#a9b5b2; --ink-3:#7f8b88;
  --rule:#2b3836; --rule-2:#3a4947;
  --accent:#5fb8ba; --accent-soft:#17302f;
  --over:#7fc08f; --over-soft:#15271c;
  --under:#e09a84; --under-soft:#2b1a15;
  color-scheme:dark;
}}
:root[data-theme="dark"]{
  --ground:#101716; --panel:#182220; --panel-2:#1f2b29;
  --ink:#e8eceb; --ink-2:#a9b5b2; --ink-3:#7f8b88;
  --rule:#2b3836; --rule-2:#3a4947;
  --accent:#5fb8ba; --accent-soft:#17302f;
  --over:#7fc08f; --over-soft:#15271c;
  --under:#e09a84; --under-soft:#2b1a15;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{background:var(--ground);color:var(--ink);font-family:var(--body);
  font-size:16px;line-height:1.72;margin:0;-webkit-text-size-adjust:100%;
  /* Korean has no hyphenation, so the default break-anywhere splits a
     compound noun across lines - the headline broke as "자/본비용". keep-all
     breaks at spaces instead. */
  word-break:keep-all;overflow-wrap:break-word}
.wrap{max-width:52rem;margin:0 auto;
  padding-left:max(16px,env(safe-area-inset-left,0px));
  padding-right:max(16px,env(safe-area-inset-right,0px));
  padding-block:0}
h1,h2,h3{font-family:var(--display);text-wrap:balance;margin:0}
h1{font-size:clamp(1.85rem,5.2vw,2.6rem);line-height:1.22;font-weight:700;
  letter-spacing:-.015em}
h2{font-size:clamp(1.3rem,3.4vw,1.6rem);line-height:1.3;font-weight:700;
  margin-block:2.6rem .25rem;letter-spacing:-.01em}
h3{font-size:1.06rem;line-height:1.4;font-weight:700;color:var(--ink);
  margin-block:2rem .2rem}
p{margin:0 0 1rem}
a{color:var(--accent);text-underline-offset:.18em}
strong{font-weight:700}
.eyebrow{font-family:var(--body);font-size:.69rem;font-weight:700;
  letter-spacing:.14em;text-transform:uppercase;color:var(--accent);
  margin:0 0 .5rem}
.lede{font-size:1.06rem;color:var(--ink-2);margin-block:.9rem 0}
.meta{font-family:var(--mono);font-size:.76rem;line-height:1.85;
  color:var(--ink-3);border-top:1px solid var(--rule);
  margin-block:1.4rem 0;padding-block:.9rem 0}
.meta b{color:var(--ink-2);font-weight:500}
header.page{padding-block:2.6rem 0}

/* the two readings that disagree: the page's central device */
.readings{display:grid;gap:1px;background:var(--rule);
  border:1px solid var(--rule);margin-block:1.4rem 0}
@media(min-width:560px){.readings{grid-template-columns:1fr 1fr}}
.reading{background:var(--panel);padding:1.15rem 1.15rem 1.25rem;min-width:0}
.reading .when{font-family:var(--mono);font-size:.72rem;font-weight:500;
  letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3)}
.reading .big{font-family:var(--display);font-size:2.35rem;font-weight:700;
  line-height:1.05;margin-block:.45rem .1rem;
  font-variant-numeric:tabular-nums}
.reading .vs{font-size:.82rem;color:var(--ink-2)}
.reading .say{font-size:.9rem;color:var(--ink-2);margin-block:.7rem 0}
.reading[data-state="under"] .big{color:var(--under)}
.reading[data-state="over"] .big{color:var(--over)}

.verdict{display:grid;gap:1px;background:var(--rule);
  border:1px solid var(--rule);margin-block:1.3rem}
@media(min-width:560px){.verdict{grid-template-columns:1fr 1fr}}
.vcard{background:var(--panel);padding:1.1rem 1.15rem;min-width:0}
.vcard h4{font-family:var(--display);font-size:1.05rem;margin:0 0 .15rem}
.vcard .tkr{font-family:var(--mono);font-size:.74rem;color:var(--ink-3)}
.vcard dl{display:grid;grid-template-columns:auto 1fr;gap:.25rem .9rem;
  margin:.75rem 0 0;font-size:.9rem}
.vcard dt{color:var(--ink-3)}
.vcard dd{margin:0;font-variant-numeric:tabular-nums;text-align:right}

.legend{font-size:.78rem;color:var(--ink-3);margin-block:1.3rem .2rem}
.legend .sw{font-family:var(--body);font-size:.68rem;font-weight:700;
  letter-spacing:.06em;padding:.1rem .34rem;margin-right:.25rem}
.legend .sw.over{color:var(--over);background:var(--over-soft)}
.legend .sw.under{color:var(--under);background:var(--under-soft)}
.legend .sw.flag{color:var(--ink);background:var(--panel-2)}
figure.tw{margin:1.1rem 0 1.3rem}
.scroll{overflow-x:auto;border:1px solid var(--rule);background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{padding:.5rem .7rem;border-bottom:1px solid var(--rule);
  white-space:nowrap}
thead th{background:var(--panel-2);font-weight:700;font-size:.76rem;
  letter-spacing:.03em;color:var(--ink-2);position:sticky;top:0}
tbody tr:last-child td{border-bottom:0}
td.r,th.r{text-align:right;font-family:var(--mono);
  font-variant-numeric:tabular-nums}
th.r{font-family:var(--body)}
td.l{font-weight:500}
/* Two different judgements, so two different marks. over/under is strictly
   the 10% hurdle; pos/neg is only the sign of a profit; flag draws the eye to
   a figure worth noticing. Using one pair for all three made a 3% operating
   margin and a 22% construction-in-progress share look like hurdle verdicts. */
td[data-state="over"]{color:var(--over);background:var(--over-soft);
  font-weight:700}
td[data-state="under"]{color:var(--under);background:var(--under-soft);
  font-weight:700}
td[data-state="pos"]{color:var(--over)}
td[data-state="neg"]{color:var(--under)}
td[data-state="flag"]{color:var(--ink);background:var(--panel-2);
  font-weight:500}
td[data-state="na"]{color:var(--ink-3)}
figcaption{font-size:.78rem;color:var(--ink-3);margin-top:.45rem;
  white-space:normal}

blockquote{margin:1.1rem 0;padding:.85rem 1rem;background:var(--accent-soft);
  border-left:3px solid var(--accent);font-size:.9rem;color:var(--ink-2)}
blockquote p{margin:0}
blockquote cite{display:block;font-family:var(--mono);font-size:.74rem;
  font-style:normal;color:var(--ink-3);margin-top:.5rem}
.callout{border:1px solid var(--rule-2);background:var(--panel);
  padding:1rem 1.1rem;margin:1.2rem 0}
.callout .k{font-family:var(--body);font-size:.7rem;font-weight:700;
  letter-spacing:.12em;text-transform:uppercase;color:var(--under);
  margin:0 0 .4rem}
.callout p:last-child{margin-bottom:0}
ul{margin:0 0 1rem;padding-left:1.15rem}
li{margin-bottom:.55rem}
.formula{font-family:var(--mono);font-size:.82rem;background:var(--panel-2);
  border:1px solid var(--rule);padding:.7rem .85rem;margin:1rem 0;
  overflow-x:auto;white-space:nowrap;color:var(--ink-2)}
footer.page{border-top:1px solid var(--rule);margin-block:3rem 0;
  padding-block:1.3rem 2.6rem;font-size:.82rem;color:var(--ink-3)}
footer.page p{margin:0 0 .5rem}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media(prefers-reduced-motion:reduce){*{animation:none!important;
  transition:none!important}}
</style>""")

    a('<div class="wrap">')

    # ---------------------------------------------------------------- header
    a('<header class="page">')
    a('<p class="eyebrow">SEC 공시 기반 자본수익률 분석</p>')
    a("<h1>스페이스X와 테슬라는 자본비용을 넘기고 있는가</h1>")
    a('<p class="lede">같은 공시가 두 가지 답을 지지합니다. 어느 기간을 '
      '재느냐에 따라 스페이스X는 문턱에 크게 미달하기도 하고, 넘기기도 '
      '합니다. 둘 다 보여드립니다.</p>')
    a('<p class="meta">'
      f'<b>자료</b> SPCX 10-Q 2026-09-30·2026-06-30 기말, 424B4 2026-06-12, '
      f'8-K 2026-10-26 · TSLA 10-K FY2025, 10-Q 2026-09-30 기말<br>'
      f'<b>주가</b> SPCX ${SR["price"]:,.2f} · TSLA ${TR["price"]:,.2f} '
      f'({d["prices"]["TSLA"]["as_of_utc"][:10]} 종가) · '
      f'<b>자본비용</b> 10% 고정<br>'
      f'<b>작성</b> {d["generated"]} · <b>검증</b> 153건 통과, 변이 15/15 '
      f'탐지</p>')
    a("</header>")

    # ------------------------------------------------- the two readings
    a("<h2>스페이스X: 기간이 판정을 바꿉니다</h2>")
    a("<p>스페이스X는 2026년 1~9월에 영업이익 "
      f"{mm(Q['nine_months_2026']['operating_income'])}백만 달러를 냈습니다. "
      "그 안에서 1~2분기는 "
      f"{mm(Q['first_half_2026']['operating_income'])}백만 달러 적자, "
      f"3분기는 {mm(Q['q3_2026']['operating_income'])}백만 달러 흑자입니다. "
      "두 기간을 평균하면 현재를 과소평가하고, 좋은 한 분기를 네 배 하면 "
      "같은 논리로 과대평가합니다. 그래서 둘 다 계산했고 어느 쪽도 정답이라 "
      "부르지 않습니다.</p>")
    a('<p class="legend"><span class="sw over">초과</span> 자본비용 10%를 '
      '넘김 &nbsp;<span class="sw under">미달</span> 넘지 못함 '
      '&nbsp;<span class="sw flag">주목</span> 눈여겨볼 수치. 흑자·적자는 '
      '색으로만 구분합니다.</p>')
    a('<div class="readings">')
    a('<div class="reading" data-state="under">'
      '<p class="when">9개월 누계를 연율화</p>'
      f'<p class="big">{pct(SR["views"]["in_service"]["roic"])}</p>'
      '<p class="vs">가동자본 기준 ROIC · 문턱까지 '
      f'{pct(-SR["views"]["in_service"]["spread_vs_wacc"])} 부족</p>'
      '<p class="say">세 관점 모두 미달 — 보고 '
      f'{pct(SR["views"]["reported"]["roic"])}, 영업 '
      f'{pct(SR["views"]["operating"]["roic"])}, 가동 '
      f'{pct(SR["views"]["in_service"]["roic"])}</p></div>')
    a('<div class="reading" data-state="over">'
      '<p class="when">3분기 속도를 연율화</p>'
      f'<p class="big">{pct(rr["in_service"]["roic"])}</p>'
      '<p class="vs">가동자본 기준 ROIC · 문턱 '
      f'{pct(rr["in_service"]["spread_vs_wacc"])} 초과</p>'
      '<p class="say">세 관점 중 둘이 초과 — 보고 '
      f'{pct(rr["reported"]["roic"])}, 영업 '
      f'{pct(rr["operating"]["roic"])}, 가동 '
      f'{pct(rr["in_service"]["roic"])}</p></div>')
    a("</div>")

    a('<div class="callout"><p class="k">먼저 정정</p>'
      '<p>이 분석을 시작할 때 저는 스페이스X를 비상장 회사라고 '
      '단정했습니다. 틀렸습니다. EDGAR에 조회하면 CIK 1181412, 나스닥 '
      'SPCX, 2026년 6월 상장(424B4 6월 12일, Class A 6억 3,890만주 × '
      '$135.00)이고 10-Q가 두 건 제출돼 있습니다. 기억이 아니라 조회가 '
      '먼저였어야 했습니다.</p></div>')

    a("<h3>NOPAT은 마이너스가 아닙니다</h3>")
    a("<p>어느 기간으로 봐도 세후영업이익은 양수입니다. 마이너스인 것은 "
      "9개월 누계 <strong>순이익</strong>이고, 그것도 1~2분기 적자와 "
      f"이자비용 1,968백만 달러 때문입니다 — 3분기 순이익은 "
      f"+4,404백만 달러입니다.</p>")
    a(table(["항목", "1~2분기", "3분기", "9개월 누계"],
            [["매출", mm(Q["first_half_2026"]["revenue"]),
              mm(Q["q3_2026"]["revenue"]),
              mm(Q["nine_months_2026"]["revenue"])],
             ["영업이익",
              (mm(Q["first_half_2026"]["operating_income"]), "neg"),
              (mm(Q["q3_2026"]["operating_income"]), "pos"),
              (mm(Q["nine_months_2026"]["operating_income"]), "pos")],
             ["NOPAT (×0.79)", (mm(Q["nopat_first_half"]), "neg"),
              (mm(Q["nopat_q3"]), "pos"),
              (mm(SR["nopat_annualised"] * 3 / 4), "pos")],
             ["capex", mm(Q["first_half_2026"]["capex"]),
              mm(Q["q3_2026"]["capex"]),
              mm(Q["nine_months_2026"]["capex"])]],
            caption="단위 백만 달러. 10-Q 2026-09-30 기말."))

    # ------------------------------------------------------- denominators
    a("<h2>세 개의 분모</h2>")
    a("<p>자본을 쏟아붓는 회사는 사업이 나빠지지 않아도 ROIC가 떨어집니다. "
      "돈을 쓰는 순간 분모가 커지지만 분자는 그 자산이 가동될 때까지 "
      "기다립니다. 알파벳 분석에서 세운 구분을 그대로 적용했습니다.</p>")
    a('<p class="formula">보고 = 자기자본 + 상환전환우선주 + 차입금 − '
      '현금·유가증권 &nbsp;│&nbsp; 영업 = 보고 − 영업권 − 무형자산 '
      '&nbsp;│&nbsp; 가동 = 영업 − 건설중자산</p>')
    a("<p>영업권을 떼는 이유는 Cursor 인수입니다. 2026년 8월 14일 지분가치 "
      "600억 달러 기준으로 주식 "
      f"{mm(42_474 * MM)}백만 달러를 주고 사들여, 영업권이 "
      f"{mm(dec['goodwill'])}에서 {mm(sep['goodwill'])}백만 달러로 "
      f"늘었습니다. 지금 투하자본의 "
      f"{pct(SR['goodwill_share_of_capital'], 0)}입니다. 영업권을 포함한 "
      "수익률은 '인수 대금을 치른 주주에게 얼마인가'를, 제외한 수익률은 "
      "'영업자산이 얼마를 버는가'를 답합니다. 둘은 다른 질문입니다.</p>")
    a(table(["분모", "6월말", "9월말", "평균", "ROIC", "문턱 대비"],
            [[VIEW_KO[k], bn(v["opening"]), bn(v["closing"]),
              bn(v["average"]), (pct(v["roic"]),
                                 "over" if v["roic"] > 0.10 else "under"),
              (signed(v["spread_vs_wacc"]) + "%p",
               "over" if v["roic"] > 0.10 else "under")]
             for k, v in rr.items()],
            caption=f"3분기 속도 기준. 단위 십억 달러. 분자는 3분기 NOPAT "
                    f"{mm(Q['nopat_q3'])}백만 달러 × 4."))
    a(table(["분모", "기초 2025-12", "기말 2026-09", "평균", "ROIC",
             "문턱 대비"],
            [[VIEW_KO[k], bn(v["opening"]), bn(v["closing"]),
              bn(v["average"]), (pct(v["roic"]), "under"),
              (signed(v["spread_vs_wacc"]) + "%p", "under")]
             for k, v in SR["views"].items()],
            caption=f"9개월 누계 연율 기준. 단위 십억 달러. 분자는 "
                    f"{mm(SR['operating_income_annualised'])}백만 달러에 "
                    f"법정세율 21%를 적용한 NOPAT "
                    f"{mm(SR['nopat_annualised'])}백만 달러."))

    # ---------------------------------------------------------- segments
    a("<h2>연결 수치가 가리는 것</h2>")
    a("<p>스페이스X는 발사체 회사가 아닙니다. 10-Q 주석 1은 세 사업부를 "
      "설명합니다 — Space(발사체), Connectivity(스타링크), 그리고 Super "
      "Intelligence(SI 인프라, Grok, Cursor, X). 경제성이 전혀 다르고, "
      "공시는 사업부별 매출·영업이익·capex를 모두 제공합니다.</p>")
    rows = []
    for key, ko in seg_order:
        v = SR["segments"][key]
        st = "pos" if v["operating_income_9m"] > 0 else "neg"
        rows.append([f"{ko}", mm(v["revenue_9m"]),
                     (mm(v["operating_income_9m"]), st),
                     (pct(v["operating_margin"], 0), st),
                     mm(v["capex_9m"]),
                     f"{v['capex_to_revenue']:.1f}×",
                     (mm(v["operating_income_less_capex"]),
                      "pos" if v["operating_income_less_capex"] > 0
                      else "neg")])
    c = S["consolidated_9m"]
    rows.append(["합계", mm(c["revenue"]["9m_2026"]),
                 (mm(c["operating_income"]["9m_2026"]), "pos"),
                 pct(c["operating_income"]["9m_2026"]
                     / c["revenue"]["9m_2026"], 0),
                 mm(c["capex"]["9m_2026"]),
                 f"{c['capex']['9m_2026'] / c['revenue']['9m_2026']:.1f}×",
                 (mm(c["operating_income"]["9m_2026"]
                     - c["capex"]["9m_2026"]), "neg")])
    a(table(["사업부", "매출", "영업이익", "마진", "capex", "capex/매출",
             "영업이익−capex"], rows,
            caption="2026년 1~9월, 단위 백만 달러. 사업부별 투하자본은 "
                    "공시되지 않으므로 사업부 ROIC는 계산하지 않았습니다 — "
                    "분모를 발명하면 그 가정이 결론이 됩니다. 대신 자기 "
                    "영업이익으로 자기 capex를 대는지를 봅니다."))
    a("<p><strong>스타링크만 양수입니다.</strong> 9개월 영업이익률 "
      f"{pct(SR['segments']['Connectivity']['operating_margin'], 0)}로 자기 "
      "capex를 대고도 "
      f"{mm(SR['segments']['Connectivity']['operating_income_less_capex'])}"
      "백만 달러가 남습니다. SI는 자기 매출의 "
      f"{SR['segments']['SI']['capex_to_revenue']:.1f}배를 쓰고 있고, 그룹 "
      "capex의 83%가 거기로 갑니다. 발사체는 적자입니다.</p>")

    a("<h3>3분기 급증은 인수 때문이 아닙니다</h3>")
    a(table(["매출 항목", "3Q2025", "3Q2026", "증가"],
            [["SI 인프라·솔루션", "359", ("7,022", "over"), "19배"],
             ["스타링크 소비자", "1,986", ("3,121", "over"), "+57%"],
             ["스타링크 기업·정부", "1,111", ("2,127", "over"), "+91%"],
             ["X 광고", "454", "538", "+18%"],
             ["발사체", "1,666", "1,767", "+6%"]],
            caption="단위 백만 달러. 10-Q 매출 분해."))
    a("<p>Cursor 기여분은 약 539백만 달러입니다 — 10-Q 프로포마 매출 "
      "15,114백만 달러와 보고 매출 14,575백만 달러의 차이. SI의 7,022백만 "
      "달러 중 대부분은 자체 증가이고, 스타링크 영업이익도 1,190에서 "
      "2,367백만 달러(마진 45%)로 좋아졌습니다. 반대로 발사체는 영업이익이 "
      "+259에서 −7백만 달러로 돌아섰습니다.</p>")

    # ------------------------------------------------ capital not earning
    a("<h2>아직 돈을 벌지 않는 자본</h2>")
    a(table(["항목", "2025-12-31", "2026-09-30", "증가"],
            [["PP&E 총액", mm(dec["ppe_gross"]), mm(sep["ppe_gross"]),
              f"{sep['ppe_gross'] / dec['ppe_gross'] - 1:+.0%}"],
             ["건설중자산", mm(dec["construction_in_progress"]),
              (mm(sep["construction_in_progress"]), "flag"),
              f"{sep['construction_in_progress'] / dec['construction_in_progress'] - 1:+.0%}"],
             ["PP&E 중 건설중 비중",
              pct(dec["construction_in_progress"] / dec["ppe_gross"], 0),
              (pct(sep["construction_in_progress"] / sep["ppe_gross"], 0),
               "flag"), ""],
             ["영업권", mm(dec["goodwill"]), mm(sep["goodwill"]),
              f"{sep['goodwill'] / dec['goodwill'] - 1:+.0%}"],
             ["계약잔고 (RPO)", "—",
              (mm(S["backlog"]["remaining_performance_obligation"]), "flag"),
              ""],
             ["선수금", mm(S["backlog"]["deferred_revenue_prior"]),
              mm(S["backlog"]["deferred_revenue"]), ""]],
            caption="단위 백만 달러."))
    a("<p>계약잔고 "
      f"{bn(S['backlog']['remaining_performance_obligation'])}십억 달러는 "
      f"연율 매출의 {SR['backlog_to_revenue_annualised']:.1f}배이고, 공시에 "
      "따르면 67%가 1년 내, 27%가 그 다음, 6%가 이후에 인식됩니다. 이건 "
      "앞으로의 매출을 뒷받침하지만 수익성을 뒷받침하지는 않습니다 — SI의 "
      "적자는 매출이 없어서가 아니라 매출보다 비용이 커서 납니다.</p>")

    if com:
        a("<h3>어느 재무상태표에도 아직 없는 400억 달러</h3>")
        a(table(["항목", "내용"],
                [["약정", com["what"]],
                 ["금액", f"약 {com['amount'] / BN:,.0f}십억 달러"],
                 ["체결", com["agreed"]],
                 ["개시 예정", com["expected_start"]],
                 ["기간", f"{com['term_years']}년"],
                 ["상태", com["status"]],
                 ["출처", f"{com['form']} {com['filed']} "
                        f"({com['accession']})"]],
                align=["l", "l"]))
        a(f'<blockquote><p>{esc(com["quote"])}</p>'
          f'<cite>{esc(com["form"])}, {esc(com["filed"])}</cite>'
          "</blockquote>")
        a(f"<p>{esc(com['note'])}</p>")

    # ------------------------------------------------------- annual history
    a("<h2>연간 이력 — 있는 만큼만</h2>")
    a(table(["연도", "매출", "영업이익", "순이익", "영업이익률"],
            [[n, mm(v["revenue"]),
              (mm(v["operating_income"]),
               "pos" if v["operating_income"] > 0 else "neg"),
              (mm(v["net_income"]),
               "pos" if v["net_income"] > 0 else "neg"),
              pct(v["operating_income"] / v["revenue"], 1)]
             for n, v in sorted(S["annual_from_prospectus"].items())],
            caption="등록신고서 424B4 요약재무, 단위 백만 달러. "
                    "FY2022 이전은 공개 공시에 없습니다."))
    a('<div class="callout"><p class="k">판정 불가</p>'
      "<p>버핏 기준의 핵심인 10년 일관성 검정을 스페이스X에는 적용할 수 "
      "없습니다. 10-K가 아직 없고, 감사된 연간 수치는 등록신고서의 3개 "
      "회계연도뿐입니다. 그 3년 중 영업이익 흑자는 FY2024 한 해이고 마진은 "
      "3.3%였습니다. 자료를 더 찾아 해결되는 문제가 아니라, 회사가 아직 "
      "그만큼의 공개 이력을 갖고 있지 않다는 사실입니다. "
      "<strong>판정 불가는 통과가 아닙니다.</strong></p></div>")

    # ------------------------------------------------------------- Tesla
    a("<h2>테슬라: 10년이 있는 쪽</h2>")
    a(table(["연도", "매출", "영업이익", "영업이익률", "ROIC", "문턱 대비"],
            [[f"FY{y['fiscal_year']}", mm(y["revenue"]),
              mm(y["operating_income"]), pct(y["operating_margin"], 1),
              (pct(y["roic"]),
               "over" if y["roic"] > 0.10 else "under"),
              (signed(y["roic"] - 0.10) + "%p",
               "over" if y["roic"] > 0.10 else "under")]
             for y in years_t],
            caption="단위 백만 달러. 10-K 기준."))
    a(f"<p>ROIC가 FY2022 {pct(TR['roic_peak'])}에서 FY2025 "
      f"{pct(TR['roic_latest'])}로 내려왔습니다. 10년 중위 "
      f"{pct(TR['roic_median_10y'])}, 문턱을 넘긴 해는 "
      f"{TR['years_above_wacc']}/{TR['years_usable']}년입니다. 꾸준히 "
      "자본비용을 넘긴 회사라고 하기 어렵습니다.</p>")

    a("<h3>최근에 넣은 돈이 버는 것</h3>")
    a("<p>10년 평균은 과거에 넣은 자본이 번 것을 말합니다. 판단에 필요한 "
      "것은 최근에 넣은 자본이 버는 것이고, 그건 영업이익 증가분을 "
      "투하자본 증가분으로 나눈 값입니다.</p>")
    a(table(["구간", "ΔNOPAT", "Δ투하자본", "증분 ROIC"],
            [[k, bn(v["delta_nopat"]), bn(v["delta_capital"]),
              (pct(v["incremental_roic"]),
               "over" if (v["incremental_roic"] or 0) > 0.10 else "under")]
             for k, v in TR["incremental"].items()],
            caption="단위 십억 달러."))
    inc = TR["incremental"]["FY2022→FY2025"]
    a(f"<p>FY2022에서 FY2025 사이에 투하자본이 "
      f"{bn(inc['delta_capital'])}십억 달러 늘었는데 NOPAT은 "
      f"{bn(inc['delta_nopat'])}십억 달러 줄었습니다. 증분 ROIC "
      f"{pct(inc['incremental_roic'])}는 최근 3년에 추가로 넣은 자본이 "
      "수익을 전혀 늘리지 못했다는 뜻입니다.</p>")
    a(table(["연도", "보고 ROIC", "가동자본 ROIC", "투하자본 중 건설중"],
            [[f"FY{fy}", pct(v["roic_reported"]),
              (pct(v["roic_in_service"]),
               "over" if v["roic_in_service"] > 0.10 else "under"),
              pct(v["cip_share"], 0)]
             for fy, v in sorted(TR["in_service"].items())
             if "roic_in_service" in v],
            caption="건설중자산을 분모에서 뺀 경우."))
    tp = T["ppe"]
    a("<p>건설중자산을 빼면 FY2025가 "
      f"{pct(TR['roic_latest'])}에서 "
      f"{pct(TR['in_service'][2025]['roic_in_service'])}로 올라가지만 문턱을 "
      "넘지는 못합니다. 알파벳의 38%와 달리 테슬라의 미사용 자본 비중은 "
      f"{pct(TR['in_service'][2025]['cip_share'], 0)}로, 차이를 설명할 "
      "크기가 아닙니다. 다만 테슬라도 같은 AI 설비 투자를 하고 있습니다 — "
      "PP&E의 AI·SI 인프라 항목이 2024년 12월 "
      f"{mm(tp['2024-12-31']['ai_infrastructure'])}에서 2026년 9월 "
      f"{mm(tp['2026-09-30']['ai_infrastructure'])}백만 달러로 늘었고, "
      "FY2025 10-K의 'AI infrastructure'가 3분기 10-Q에서 'SI "
      "infrastructure'로 바뀌었습니다.</p>")

    # ------------------------------------------------------------- price
    a("<h2>가격</h2>")
    a('<div class="verdict">')
    for ko, tkr, r, nopat in (
            ("스페이스X", "SPCX", SR, SR["nopat_annualised"]),
            ("테슬라", "TSLA", TR, nopat_2025)):
        need = r["market_cap"] * 0.10
        a(f'<div class="vcard"><h4>{ko}</h4>'
          f'<p class="tkr">{tkr} · 나스닥</p><dl>'
          f'<dt>주가</dt><dd>${r["price"]:,.2f}</dd>'
          f'<dt>발행주식수</dt><dd>{r["shares_outstanding"] / BN:,.3f}십억주</dd>'
          f'<dt>시가총액</dt><dd>{bn(r["market_cap"], 0)}십억 달러</dd>'
          f'<dt>연율 NOPAT</dt><dd>{bn(nopat, 1)}십억 달러</dd>'
          f'<dt>시총 / NOPAT</dt><dd>{r["market_cap"] / nopat:,.0f}배</dd>'
          f'<dt>10% 수익에 필요한 NOPAT</dt><dd>{bn(need, 0)}십억 달러</dd>'
          f'<dt>현재의 몇 배</dt><dd>{need / nopat:,.0f}배</dd>'
          "</dl></div>")
    a("</div>")
    a("<p><strong>DCF는 돌리지 않았습니다.</strong> 알파벳에서는 성장률이 "
      "떨어지는 시나리오로 현재가치를 쌓았지만, 그 계산은 출발점이 되는 "
      "정상 수익력이 있어야 성립합니다. 스페이스X는 3년 중 2년이 영업적자이고 "
      "분기마다 자본구조가 바뀌어, 어떤 숫자를 기준 수익력으로 잡아도 그 "
      "선택이 결과를 전부 결정합니다. 테슬라는 기준 수익력은 있지만 증분 "
      "ROIC가 음수여서 성장을 가정하는 모형이 가치를 늘리는 게 아니라 "
      "줄입니다. 두 경우 모두 모형이 정확도가 아니라 가정을 숨깁니다.</p>")

    # ---------------------------------------------------------- criteria
    a("<h2>버핏 기준 판정</h2>")
    a(table(["기준", "스페이스X", "테슬라"],
            [["이해할 수 있는 사업",
              "✗ 세 사업부의 경제성이 전혀 다르고, 그중 하나는 2개월 전 "
              "인수한 AI 사업",
              "△ 자동차·에너지는 명확, AI·로보틱스 비중이 커지는 중"],
             ["10년 일관된 수익력",
              "판정 불가 — 감사된 연간 수치 3년, 그중 흑자 1년",
              f"✗ 문턱 초과 {TR['years_above_wacc']}/"
              f"{TR['years_usable']}년, 중위 {pct(TR['roic_median_10y'])}"],
             ["ROIC > 자본비용 10%",
              f"△ 9개월 연율 {pct(SR['views']['in_service']['roic'])} 미달 / "
              f"3분기 속도 {pct(rr['in_service']['roic'])} 초과",
              f"✗ FY2025 {pct(TR['roic_latest'])}, 가동 기준 "
              f"{pct(TR['in_service'][2025]['roic_in_service'])}"],
             ["증분 ROIC",
              "산출 불가 (자본구조 급변) · SI capex는 자기 매출의 3.7배",
              f"✗ FY2022→25 {pct(inc['incremental_roic'])}"],
             ["낮은 부채",
              f"△ 차입금 {bn(sep['debt'], 0)}십억 달러에 현금·유가증권 "
              f"{bn(sep['cash_and_securities'], 0)}십억 달러로 순현금. "
              "단 400억 달러 리스 약정이 대기 중",
              "△ 순현금이지만 FY2025 영업이익이 축소"],
             ["가격 매력",
              f"✗ 시총/NOPAT "
              f"{SR['market_cap'] / SR['nopat_annualised']:,.0f}배",
              f"✗ 시총/NOPAT {TR['price_to_nopat']:,.0f}배"]],
            align=["l", "l", "l"]))
    a("<p><strong>스페이스X 안에서 자기 숫자로 기준을 통과하는 사업은 "
      "스타링크 하나입니다.</strong> 9개월 영업이익률 41%, 자기 capex를 자기 "
      "영업이익으로 대고, 매출이 57% 늘었습니다. 문제는 그것만 따로 살 수 "
      "없다는 것입니다 — SPCX를 사면 스타링크가 버는 돈을 SI에 넣는 결정을 "
      "함께 사게 됩니다. 지금 그 비율은 그룹 capex의 83%입니다.</p>")

    # ------------------------------------------------------------ limits
    a("<h2>이 분석의 한계</h2>")
    a("<ul>"
      "<li><strong>기간을 어떻게 잡느냐가 판정을 바꿉니다.</strong> 9개월 "
      "연율로는 세 관점 모두 미달하고, 3분기 속도로는 둘이 넘습니다. 둘 다 "
      "추정이고 방향만 반대입니다. 1~2분기 적자가 일시적인지 3분기 흑자가 "
      "지속적인지는 다음 분기들이 답할 문제입니다.</li>"
      "<li><strong>스페이스X는 10년 검정을 할 수 없습니다.</strong> 가장 "
      "중요한 한계이고 자료를 더 찾아 해결되지 않습니다. 첫 10-K가 나오는 "
      "2027년 초에 FY2026이 확정되면 4년이 됩니다.</li>"
      "<li><strong>사업부 ROIC는 계산하지 않았습니다.</strong> 사업부별 "
      "투하자본이 공시되지 않습니다. 사업부 capex를 누적해 분모를 만들 수는 "
      "있지만 그건 측정이 아니라 추정이고 결과를 좌우합니다.</li>"
      "<li><strong>Cursor 인수는 1.5개월분만 손익에 들어 있습니다.</strong> "
      "8월 14일 종료인데 영업권 48,423백만 달러는 전액 반영돼 있어, 분자와 "
      "분모의 기간이 어긋나 있습니다. 다음 분기부터 올라갈 여지가 "
      "있습니다.</li>"
      "<li><strong>자본비용 10%는 지시에 따른 고정값입니다.</strong> 두 "
      "회사의 실제 자본비용은 다르고, 특히 스페이스X는 상장 4개월째여서 "
      "시장 기반 추정이 의미를 갖기 어렵습니다.</li>"
      "</ul>")

    # ------------------------------------------------------------ footer
    a('<footer class="page">')
    a("<p>검증: 항등식(투하자본·NOPAT·ROIC·평균·PP&amp;E 순액), 합계 검정"
      "(사업부 합이 연결과 일치, 분기 합이 누계와 일치), 범위 검정"
      "(주식수·시가총액 — 배율 오류 탐지용), 공시 앵커 27건. 153건 전부 "
      "통과하고, 값을 고의로 훼손한 변이 15건을 전부 탐지합니다.</p>")
    a("<p>재현: <code>bash work/run_spx_tsla.sh</code> — 날짜·신선도 확인 → "
      "주가 → 공시 수집 → 산출 → 검증 → 보고서.</p>")
    a("<p>이 페이지의 모든 수치는 SEC 공시에서 직접 추출한 값이며, "
      "같은 데이터로 마크다운·워드·엑셀 보고서가 함께 생성됩니다. "
      "투자 판단은 읽는 분의 몫입니다.</p>")
    a("</footer>")
    a("</div>")
    return "\n".join(p)


# ------------------------------------------------------------------- verify
def verify(d, path):
    """
    Read the page's tables back and compare them to the engine.

    Same reason the Markdown gets this: rendered HTML has no formulas to
    re-evaluate, so a figure placed in the wrong row leaves no trace that
    reading the page would reveal.
    """
    text = open(path).read()
    S, T = d["SPCX"], d["TSLA"]
    SR, TR = S["ratios"], T["ratios"]
    Q = S["quarterly"]
    checks, fails = 0, []

    def cells(row_html):
        return [re.sub(r"<[^>]+>", "", c).strip()
                for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html,
                                    re.S)]

    # Rows are grouped by the table they belong to. Scanning every row in the
    # page and taking the first match compared Tesla's FY2025 against
    # SpaceX's, because both tables have a row labelled FY2025.
    tables = []
    for t in re.findall(r"<table>(.*?)</table>", text, re.S):
        tables.append([cells(r) for r in re.findall(r"<tr>(.*?)</tr>", t,
                                                    re.S)])
    rows = [r for t in tables for r in t]

    def num(s):
        s = s.replace(",", "").replace("%p", "").replace("%", "")
        s = s.replace("×", "").replace("배", "").replace("+", "").strip()
        try:
            return float(s)
        except ValueError:
            return None

    def find(first_cell, header_has=None):
        """
        The row with this label. `header_has` picks the table first, which is
        how Tesla's FY2025 row is told apart from SpaceX's.
        """
        for t in tables:
            if header_has and not (t and any(header_has in c
                                             for c in t[0])):
                continue
            for r in t[1:] if header_has else t:
                if r and r[0] == first_cell:
                    return r
        return None

    def expect(got, want, label, nd=0):
        nonlocal checks
        checks += 1
        if got is None:
            fails.append(f"{label}: 값 없음 (기대 {want})")
        elif round(got, nd) != round(want, nd):
            fails.append(f"{label}: {got} != {round(want, nd)}")

    # quarterly split
    r = find("영업이익")
    checks += 1
    if not r:
        fails.append("분기 표의 영업이익 행 없음")
    else:
        expect(num(r[1]), Q["first_half_2026"]["operating_income"] / MM,
               "1~2분기 영업이익")
        expect(num(r[2]), Q["q3_2026"]["operating_income"] / MM,
               "3분기 영업이익")
        expect(num(r[3]), Q["nine_months_2026"]["operating_income"] / MM,
               "9개월 영업이익")

    # the two ROIC tables, by the big numbers in the readings panel
    for state, want in (("under", SR["views"]["in_service"]["roic"]),
                        ("over", Q["q3_run_rate_views"]["in_service"]["roic"])):
        checks += 1
        m = re.search(rf'data-state="{state}">\s*<p class="when">.*?'
                      rf'<p class="big">([-\d.]+)%</p>', text, re.S)
        if not m:
            fails.append(f"readings 패널 {state} 없음")
        else:
            expect(float(m.group(1)), want * 100, f"readings {state}", 1)

    # segments
    for key, ko in (("Connectivity", "스타링크"), ("SI", "슈퍼인텔리전스"),
                    ("Space", "발사체")):
        r = find(ko)
        checks += 1
        if not r:
            fails.append(f"사업부 행 없음: {ko}")
            continue
        v = SR["segments"][key]
        expect(num(r[1]), v["revenue_9m"] / MM, f"{ko} 매출")
        expect(num(r[2]), v["operating_income_9m"] / MM, f"{ko} 영업이익")
        expect(num(r[5]), v["capex_to_revenue"], f"{ko} capex배수", 1)

    # Tesla years
    by = {y["fiscal_year"]: y for y in T["annual_roic"]}
    for fy in range(2016, 2026):
        # "영업이익률" appears in SpaceX's annual table too; "ROIC" is in
        # Tesla's header and not in SpaceX's, which is what tells them apart.
        r = find(f"FY{fy}", header_has="ROIC")
        checks += 1
        if not r:
            fails.append(f"테슬라 FY{fy} 행 없음")
            continue
        expect(num(r[1]), by[fy]["revenue"] / MM, f"TSLA FY{fy} 매출")
        expect(num(r[4]), by[fy]["roic"] * 100, f"TSLA FY{fy} ROIC", 1)

    # incremental
    for label, v in TR["incremental"].items():
        r = find(label)
        checks += 1
        if not r:
            fails.append(f"증분 행 없음: {label}")
            continue
        expect(num(r[3]), v["incremental_roic"] * 100, f"{label} 증분", 1)

    # the semantic colour has to agree with the arithmetic: a figure above the
    # hurdle marked "under" would read as the opposite of what it is.
    checks += 1
    bad = []
    for m in re.finditer(r'<td class="r" data-state="(over|under)">'
                         r'([-\d.,]+)%</td>', text):
        state, val = m.group(1), float(m.group(2).replace(",", ""))
        if state == "over" and val <= 10.0 and val > 0:
            bad.append(f"{val}% 가 over")
        if state == "under" and val > 10.0:
            bad.append(f"{val}% 가 under")
    if bad:
        fails.append(f"문턱 색상 표기 오류: {bad[:4]}")

    # structural requirements from the page contract
    for needle, label in (("<title>", "title"),
                          ('claude:viewport-fit-sides', "viewport meta"),
                          ("max(16px,env(safe-area-inset-left,0px))",
                           "좌측 거터"),
                          ("prefers-color-scheme:dark", "다크 테마"),
                          ('[data-theme="dark"]', "테마 토글"),
                          ("background:var(--ground)", "body 배경")):
        checks += 1
        if needle not in text.replace(" ", "").replace("\n", "") \
                and needle not in text:
            fails.append(f"페이지 요건 누락: {label}")

    print(f"HTML 검사 {checks}건 중 통과 {checks - len(fails)}건, "
          f"실패 {len(fails)}건")
    for f in fails[:20]:
        print(f"  실패: {f}")
    return 1 if fails else 0


MUTATIONS = [
    ("분기 영업이익", "<td class=\"r\" data-state=\"pos\">2,791</td>",
     "<td class=\"r\" data-state=\"pos\">3,791</td>"),
    ("readings 패널 수치", '<p class="big">20.0%</p>',
     '<p class="big">25.0%</p>'),
    ("테슬라 ROIC", '<td class="r" data-state="under">7.2%</td>',
     '<td class="r" data-state="under">9.2%</td>'),
    ("문턱 색상 반전", '<td class="r" data-state="over">20.0%</td>',
     '<td class="r" data-state="under">20.0%</td>'),
    ("사업부 행 삭제", "<td class=\"l\">스타링크</td>",
     "<td class=\"l\">삭제됨</td>"),
    ("다크 테마 제거", "prefers-color-scheme:dark", "prefers-color-scheme:x"),
    ("좌측 거터 제거", "max(16px,env(safe-area-inset-left,0px))",
     "16px"),
]


def mutate(d):
    """Corrupt the rendered page and confirm verify() fails on each."""
    import shutil
    import subprocess
    original = open(OUT).read()
    backup = OUT + ".bak"
    shutil.copy2(OUT, backup)
    caught, ran = 0, 0
    print("\n변이 검정 — 페이지를 훼손했을 때 검사가 실패해야 정상")
    try:
        for label, a_, b_ in MUTATIONS:
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
            print(f"  {'탐지' if hit else '놓침':<6}{label:<18}{line[:62]}")
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
