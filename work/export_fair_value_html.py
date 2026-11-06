"""
네 기업 적정주가 — HTML 페이지.

fair_value.json 에서 생성합니다. 마크다운·워드와 같은 원본이므로 세 포맷이
어긋날 수 없습니다. 페이지의 중심 생각은 **시나리오 값과 현재가를 같은 축에
얹어 눈으로 비교**하는 것입니다 — 표로는 "낙관 $331, 현재 $282"가 나란히
놓이기만 하지만, 축에 얹으면 현재가가 보수와 낙관 사이 어디에 있는지가
한눈에 보입니다.

의미색은 한 가지 뜻만 갖습니다. cheap/rich 는 "평가치 대비 현재가"에만,
pos/neg 는 부호에만, flag 는 주목용으로 씁니다.

    python3 export_fair_value_html.py
    python3 export_fair_value_html.py --verify --mutate
"""

import argparse
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DATA = os.path.join(HERE, "fv", "fair_value.json")
OUT = os.path.join(HERE, "fv", "fair_value_report.html")
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


def cheapness(value, price):
    """평가치 대비 현재가. 이 색은 이 뜻으로만 씁니다."""
    return "cheap" if value > price else "rich"


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
  --bg:#f6f5f2; --panel:#ffffff; --fg:#191b1e; --dim:#5c6269; --line:#e3e1db;
  --ink:#0e1012; --accent:#1f4e79; --accent-soft:#e9f0f6;
  --cheap:#0f6b4f; --cheap-bg:#e6f2ec;
  --rich:#9a2a1f; --rich-bg:#fbeae7;
  --pos:#1f5d8c; --neg:#8a4b12;
  --flag:#8a6a12; --flag-bg:#fbf3e0;
  --price:#17191c;
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
    --price:#f3f1ed;
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
  --price:#f3f1ed;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{
  background:var(--bg); color:var(--fg); font-family:var(--sans);
  font-size:16px; line-height:1.72; margin:0;
  /* 한국어는 음절 단위로 쪼개지 않습니다. 없으면 "자본비용"이 끊깁니다. */
  word-break:keep-all; overflow-wrap:anywhere;
}
.wrap{
  max-width:880px; margin:0 auto; padding-block:0 76px;
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

.chips{display:grid; gap:.6rem; grid-template-columns:repeat(2,1fr);
  margin:0 0 1.5em}
@media (min-width:660px){.chips{grid-template-columns:repeat(4,1fr)}}
.chip{min-width:0; padding:.75em .9em; border-radius:10px;
  border:1px solid var(--line); background:var(--panel)}
.chip .n{font-family:var(--serif); font-size:1rem; font-weight:700;
  color:var(--ink); display:block}
.chip .p{font-family:var(--mono); font-size:1.35rem; font-weight:600;
  display:block; line-height:1.3}
.chip .s{font-size:.76rem; color:var(--dim); display:block}
.chip.cheap{border-color:var(--cheap); background:var(--cheap-bg)}
.chip.rich{border-color:var(--rich); background:var(--rich-bg)}
.chip.flag{border-color:var(--flag); background:var(--flag-bg)}
.chip.cheap .p,.chip.cheap .n{color:var(--cheap)}
.chip.rich .p,.chip.rich .n{color:var(--rich)}
.chip.flag .p,.chip.flag .n{color:var(--flag)}

/* 시나리오 값과 현재가를 같은 축에 */
.scale{margin:1em 0 1.6em; padding:1em 1.1em; background:var(--panel);
  border:1px solid var(--line); border-radius:11px}
.scale .hd{display:flex; flex-wrap:wrap; gap:.4rem 1rem; align-items:baseline;
  margin-bottom:.9em}
.scale .hd .nm{font-family:var(--serif); font-size:1.08rem; font-weight:700;
  color:var(--ink)}
.scale .hd .px{font-family:var(--mono); font-size:1.08rem; font-weight:600;
  color:var(--price)}
.scale .hd .vd{font-size:.8rem; padding:.1em .6em; border-radius:99px;
  border:1px solid}
.scale .hd .vd.cheap{color:var(--cheap); border-color:var(--cheap);
  background:var(--cheap-bg)}
.scale .hd .vd.rich{color:var(--rich); border-color:var(--rich);
  background:var(--rich-bg)}
.row{display:grid; grid-template-columns:3.2em 1fr 4.6em; gap:.55rem;
  align-items:center; font-size:.82rem; margin:.3rem 0}
.row .lb{font-size:.76rem; color:var(--dim); font-weight:600}
.row .tr{position:relative; height:1.15em; min-width:0;
  background:var(--line); border-radius:3px; overflow:visible}
.row .fl{position:absolute; left:0; top:0; bottom:0; border-radius:3px;
  background:var(--accent)}
.row .fl.cheap{background:var(--cheap)}
.row .fl.rich{background:var(--rich)}
.row .vv{font-family:var(--mono); text-align:right; font-weight:600}
.axis{position:relative; height:1.9em; margin-top:.2em;
  border-top:1px dashed var(--line)}
.axis .mk{position:absolute; top:0; transform:translateX(-50%);
  font-family:var(--mono); font-size:.72rem; color:var(--dim)}
.pline{position:absolute; top:-0.2em; bottom:-0.2em; width:2px;
  background:var(--price)}
.pline::after{content:""; position:absolute; left:-3px; top:-4px;
  width:8px; height:8px; border-radius:50%; background:var(--price)}
.plab{position:absolute; transform:translateX(-50%);
  font-family:var(--mono); font-size:.72rem; font-weight:700;
  color:var(--price); white-space:nowrap}

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
td.w,th.w{text-align:left; white-space:normal; min-width:18ch;
  font-size:.82rem; color:var(--dim)}
tbody tr:last-child td{border-bottom:0}
tfoot td{border-top:2px solid var(--line); font-weight:650; border-bottom:0;
  background:var(--accent-soft)}
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
blockquote{margin:1.3em 0; padding:.2em 0 .2em 1.1em;
  border-left:3px solid var(--accent); color:var(--dim)}
blockquote strong{color:var(--accent)}
ul{margin:0 0 1.2em; padding-left:1.25em}
li{margin:0 0 .6em}
.steps{display:grid; gap:.8rem; grid-template-columns:1fr; margin:1.1em 0 1.5em}
@media (min-width:660px){.steps{grid-template-columns:repeat(3,1fr)}}
.step{min-width:0; padding:.9em 1em; background:var(--panel);
  border:1px solid var(--line); border-radius:11px}
.step .k{display:inline-block; font-size:.7rem; letter-spacing:.1em;
  font-weight:700; color:var(--accent); background:var(--accent-soft);
  padding:.15em .6em; border-radius:99px; margin-bottom:.4em}
.step b{display:block; font-family:var(--serif); font-size:1rem;
  color:var(--ink); margin-bottom:.3em}
.step p{margin:0; font-size:.88rem; color:var(--dim)}
.step em{font-style:normal; font-weight:650; color:var(--fg)}
.callout{margin:1.3em 0; padding:1em 1.15em; border-radius:11px;
  border:1px solid var(--flag); background:var(--flag-bg)}
.callout p{margin:0}
.callout strong{color:var(--flag)}
footer{margin-top:2.8em; padding-top:1.2em; border-top:1px solid var(--line);
  font-size:.78rem; color:var(--dim); line-height:1.8}
</style>
"""


def scale_block(co, applied_max):
    """시나리오 값과 현재가를 같은 축에."""
    px = co["price"]
    vals = {v["scenario"]: v["value_per_share"] for v in co["valuations"]}
    top = max(max(vals.values()), px) * 1.12
    hi = vals["낙관"]
    verdict = ("낙관에서만 현재가 위" if hi > px else "모든 시나리오에서 비쌈")
    vcls = "cheap" if hi > px else "rich"
    o = ['<div class="scale">']
    o.append('<div class="hd">'
             f'<span class="nm">{esc(co["korean"])} '
             f'({esc(co["ticker"])})</span>'
             f'<span class="px">현재 {usd(px, 2)}</span>'
             f'<span class="vd {vcls}">{verdict}</span></div>')
    for s in ORDER:
        v = vals[s]
        c = cheapness(v, px)
        o.append(f'<div class="row"><span class="lb">{s}</span>'
                 f'<span class="tr"><span class="fl {c}" '
                 f'style="width:{v / top * 100:.2f}%"></span></span>'
                 f'<span class="vv">{usd(v)}</span></div>')
    # 현재가 선과 축 눈금
    o.append('<div class="axis">')
    o.append(f'<span class="pline" style="left:{px / top * 100:.2f}%"></span>')
    o.append(f'<span class="plab" style="left:{px / top * 100:.2f}%; top:.45em">'
             f'{usd(px, 0)}</span>')
    o.append("</div>")
    o.append("</div>")
    return "\n".join(o)


def build(d):
    applied = [c for c in d["companies"] if c["model"] == "applied"]
    sx = [c for c in d["companies"]
          if c["model"] == "base_not_established"][0]

    def val(co, s):
        return [v for v in co["valuations"] if v["scenario"] == s][0]

    def nm(co):
        return f"{co['korean']}({co['ticker']})"

    o = []
    w = o.append
    w("<title>적정주가 판정</title>")
    w('<meta name="claude:viewport-fit-sides" content="cover">')
    w('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
      'family=Inter:wght@400;600;700&family=Noto+Sans+KR:wght@400;500;700&'
      'family=Noto+Serif+KR:wght@600;700&display=swap">')
    w(STYLE)
    w('<div class="wrap">')

    w("<h1>네 기업 적정주가 판정</h1>")
    w(f'<p class="meta">'
      f'<b>자료 기준일</b> {d["generated"]} · '
      f'<b>50개사 ROIC 조사</b> {d["roic_study_generated"]} 생성 · '
      f'<b>시세</b> {d["prices_fetched_utc"][:19]} UTC 수집<br>'
      f'<b>ROIC 문턱</b> {pct(d["wacc_for_roic_hurdle"], 0)} · '
      f'<b>투영</b> {d["projection_years"]}년 성장 감쇠 + 터미널 · '
      f'<b>할인율</b> 보수 11% / 중립 10% / 낙관 9%<br>'
      + " · ".join(f'<b>{esc(c["korean"])}</b> 자료기준 {c["data_as_of"]}'
                   for c in applied)
      + "</p>")

    w('<div class="chips">')
    for c in applied:
        hi = val(c, "낙관")["value_per_share"]
        cls = cheapness(hi, c["price"])
        w(f'<div class="chip {cls}">'
          f'<span class="n">{esc(c["korean"])}</span>'
          f'<span class="p">{usd(c["price"], 2)}</span>'
          f'<span class="s">보수 {usd(val(c, "보수")["value_per_share"])} · '
          f'중립 {usd(val(c, "중립")["value_per_share"])} · '
          f'낙관 {usd(hi)}</span></div>')
    w(f'<div class="chip flag">'
      f'<span class="n">{esc(sx["korean"])}</span>'
      f'<span class="p">{usd(sx["price"], 2)}</span>'
      f'<span class="s">기준이익 미성립 — 산출 불가</span></div>')
    w("</div>")

    w('<div class="legend">'
      '<span><i style="background:var(--cheap)"></i>평가치 > 현재가</span>'
      '<span><i style="background:var(--rich)"></i>평가치 < 현재가</span>'
      '<span><i style="background:var(--pos)"></i>양(+)</span>'
      '<span><i style="background:var(--neg)"></i>음(−)</span>'
      '<span><i style="background:var(--flag)"></i>주목</span>'
      '<span><i style="background:var(--price)"></i>현재가</span>'
      '</div>')

    w('<p class="lede"><strong>사업의 질은 셋 다 합격, 가격은 낙관 '
      '시나리오에서만 설명됩니다.</strong> 그리고 세 기업 모두 ROIC가 같은 '
      '모양으로 내려오고 있습니다 — 영업이익이 멈춴 게 아니라 투하자본이 더 '
      '빨리 늘어서입니다.</p>')
    for c in applied:
        w(scale_block(c, None))
    w('<p>막대는 시나리오별 주당 가치, 검은 선이 현재가입니다. '
      '<strong>보수·중립 시나리오에서는 세 기업 모두 성장률을 어떻게 잡아도 '
      '현재가가 나오지 않습니다</strong> — 뒤에서 그 이유를 산수로 '
      '보여드립니다.</p>')

    # ============================================================ 1부
    w("<h2>1부. 우리가 세운 기준</h2>")
    w("<p>순서가 중요합니다 — <strong>자료가 먼저, 사업이 다음, 가격이 "
      "마지막</strong>입니다. 가격 판정은 앞의 두 단계를 통과한 기업에만 "
      "의미가 있습니다.</p>")

    w("<h3>① 자료 — 기억으로 단정하지 않는다</h3>")
    w("<ul>"
      "<li><strong>오늘 날짜를 먼저 확인하고 오늘 기준으로 다시 "
      "수집한다.</strong> 캐시는 받은 시점을 기록하고 1일이 지나면 다시 "
      "받습니다.</li>"
      "<li><strong>학습 시점 이후에 바뀌는 사실은 전부 조회로 답한다.</strong> "
      "상장 여부·티커·결산월·주가·주식수, 그리고 모든 금액. 스페이스X를 "
      "비상장이라고 단정했다가 틀린 적이 있습니다.</li>"
      "<li><strong>보고서에 자료 기준일을 적는다.</strong> 어느 날짜에 받은 "
      "공시인지가 결론의 유효기간을 정합니다.</li>"
      "<li><strong>티커만 쓰지 않고 한글명을 함께 쓴다.</strong></li>"
      "</ul>")

    w("<h3>② 사업의 질 — ROIC가 자본비용을 넘는가</h3>")
    w('<div class="formula">NOPAT       = 보고된 영업이익 × (1 − 실효세율)\n'
      '투하자본    = 자기자본(비지배지분 포함) + 이자부차입금 − 현금·단기투자\n'
      'ROIC        = NOPAT ÷ 투하자본(기초·기말 평균)</div>')
    w("<ul>"
      f"<li><strong>정의는 바꾸지 않는다.</strong> 50개사를 같은 잣대로 재야 "
      f"비교가 됩니다. 문턱은 {pct(d['wacc_for_roic_hurdle'], 0)}.</li>"
      "<li><strong>한 해만 보지 않는다.</strong> 10년 일관성과 <strong>고점 "
      "대비 추세</strong>를 함께 봅니다.</li>"
      "<li><strong>분모를 좁혀 가며 여러 관점으로 본다.</strong> 보고 → "
      "영업권·무형 제외 → 미가동 설비 제외 → 투자지분 제외.</li>"
      "<li><strong>증분 ROIC을 본다.</strong> 새 자본 1달러가 얼마를 "
      "버는지가 미래를 말합니다.</li>"
      "<li><strong>금융업(SIC 6000–6799)은 산출하지 않는다.</strong> 은행에게 "
      "차입은 자금조달이 아니라 원재료입니다.</li>"
      "<li><strong>사업부 투하자본은 공시되지 않으므로 사업부 ROIC를 만들지 "
      "않는다.</strong> 분모를 발명하면 그 가정이 결론이 됩니다.</li>"
      "</ul>")

    w("<h3>③ 재무 안전성 · ④ 이익의 질</h3>")
    w("<ul>"
      "<li><strong>순현금인가 순차입인가</strong>, 그리고 <strong>자금조달 "
      "구조가 바뀌었는지</strong>. 자사주를 사던 회사가 증자로 돌아섰다면 "
      "재무상태표만 봐서는 놓칩니다.</li>"
      "<li><strong>영업이익에서 출발한다. 분기 순이익을 신호로 쓰지 "
      "않는다.</strong> 투자지분 평가손익이 분기 순이익을 수십억 달러 단위로 "
      "흔듭니다 — 알파벳은 같은 분기에 영업이익 +30%인데 EPS −26%였습니다.</li>"
      "<li><strong>실효세율 오염을 확인하고 법정세율 대안을 병기한다.</strong>"
      "</li>"
      "<li><strong>추정값은 추정이라고 표시한다.</strong></li>"
      "</ul>")

    w("<h3>⑤ 가격 — 가치가 아니라 요구 조건으로 본다</h3>")
    w('<div class="formula">잉여현금 = NOPAT × (1 − 성장률 ÷ 증분ROIC)'
      '      ← 성장에는 돈이 든다\n'
      '성장은 증분ROIC > 할인율 일 때만 가치를 더한다  '
      '← 작으면 매출이 커져도 가치를 깎는다</div>')
    w("<ul>"
      "<li><strong>단일 적정주가를 내지 않는다.</strong> 세 시나리오로 내고, "
      "<strong>현재 가격이 요구하는 조건</strong>을 함께 냅니다. “내재가치가 "
      "얼마냐”보다 “이 가격이 맞으려면 무엇이 사실이어야 하나”가 "
      "유용합니다.</li>"
      "<li><strong>안전마진을 본다.</strong> 평가치에서 정확히 거래되는 "
      "가격은 합격이 아닙니다.</li>"
      "<li><strong>주주이익 수익률을 함께 본다.</strong> capex 전액을 비용으로 "
      "본 하단과 감가상각만 비용으로 본 상단.</li>"
      "</ul>")
    w("<h3>⑥ 산출물 — 검증 없는 산출물은 내보내지 않는다</h3>")
    w("<ul>"
      "<li><strong>항등식·앵커·변이 검정.</strong> 값을 고의로 훼손해 검사가 "
      "실제로 실패하는지까지 확인합니다.</li>"
      "<li><strong>앵커는 공시 원문에서 손으로 읽은 수치만.</strong> 항등식은 "
      "검사 대상과 같은 데이터로 계산되므로 내부적으로 일관된 틀린 값은 "
      "통과합니다.</li>"
      "<li><strong>워드·엑셀·마크다운·HTML</strong>을 같은 원본에서 "
      "만듭니다.</li>"
      "</ul>")

    # ============================================================ 2부
    w("<h2>2부. 네 기업에 적용</h2>")
    w("<h3>시나리오를 손으로 고르지 않았습니다</h3>")
    w(f"<p>네 기업의 10년 영업이익 CAGR이 "
      f"{pct(min(c['record']['operating_income_cagr'] for c in applied))}에서 "
      f"{pct(max(c['record']['operating_income_cagr'] for c in applied))}까지 "
      f"벌어져 있습니다. 하나의 성장률을 네 기업에 똑같이 쓰면 어느 기업에도 "
      f"맞지 않습니다. 그래서 <strong>각 기업의 자기 기록에서 규칙으로 "
      f"도출</strong>하고 상한만 명시했습니다.</p>")
    w(table(["시나리오", "초기 성장률", "증분 ROIC", "할인율", "터미널"], [
        ["보수", "10년 CAGR ÷ 3 (상한 10%)", "10년 최저 ROIC (상한 15%)",
         "11%", "2.0%"],
        ["중립", "10년 CAGR ÷ 2 (상한 15%)", "10년 중위 ROIC ÷ 2 (상한 25%)",
         "10%", "2.5%"],
        ["낙관", "10년 CAGR (상한 25%)", "10년 중위 ROIC (상한 35%)",
         "9%", "3.0%"],
    ], caption="할인율과 터미널 성장률은 기업의 성질이 아니라 “내가 요구하는 "
               "수익률”이므로 네 기업에 똑같이 적용했습니다. 이 규칙을 "
               "알파벳에 적용하면 직전 보고서에서 손으로 골랐던 값과 거의 "
               "같아집니다 — 규칙으로 바꾼 것이 결론을 움직이지 않았습니다.",
       align=["l", "w", "w", "r", "r"]))
    w('<div class="callout"><p><strong>상한이 이 모형에서 가장 중요한 '
      '판단입니다.</strong> 지금의 비범한 수익률과 성장률을 영구히 연장하지 '
      '않겠다는 선언입니다. 상한이 없으면 엔비디아의 10년 CAGR 67.6%가 영구 '
      '성장률이 되어 어떤 가격도 정당화됩니다.</p></div>')

    # ---------------------------------------------- 풀어 쓴 계산 (3개 절)
    w("<h3>풀어 쓴 계산 ① — 성장률은 어디서 왔나</h3>")
    w("<p>성장률은 제가 고른 숫자가 아니라 <strong>세 단계를 거쳐 나온 "
      "값</strong>입니다.</p>")
    w('<div class="steps">')
    w('<div class="step"><span class="k">1단계</span>'
      '<b>각 기업의 지난 10년을 잰다</b>'
      '<p>영업이익이 10년 동안 연평균 몇 %로 늘었는지. 이건 가정이 아니라 '
      '공시에서 나온 <em>측정값</em>입니다.</p></div>')
    w('<div class="step"><span class="k">2단계</span>'
      '<b>시나리오별로 나눈다</b>'
      '<p>낙관 = 과거 속도가 그대로 이어진다(÷1). 중립 = 절반으로 '
      '꺾인다(÷2). 보수 = 3분의 1로 꺾인다(÷3).</p></div>')
    w('<div class="step"><span class="k">3단계</span>'
      '<b>상한을 씌운다</b>'
      '<p>과거가 아무리 빨랐어도 낙관 25%, 중립 15%, 보수 10%를 넘기지 '
      '않습니다. 엔비디아의 67.6%를 그대로 쓰면 어떤 가격도 '
      '정당화됩니다.</p></div>')
    w("</div>")
    rows = []
    for c in applied:
        g = c["record"]["operating_income_cagr"]
        row = [nm(c), cell(f"<b>{pct(g)}</b>", "flagc")]
        for s in ORDER:
            si = [x for x in c["scenario_inputs"] if x["name"] == s][0]
            raw, fin = si["growth_uncapped"], si["growth"]
            if si["growth_capped"]:
                row.append(cell(f"{pct(raw)} → <b>{pct(fin)}</b> (상한)",
                                "rich"))
            else:
                row.append(cell(f"<b>{pct(fin)}</b>", ""))
        rows.append(row)
    w(table(["기업", "10년 영업이익 CAGR (측정값)", "보수 = ÷3",
             "중립 = ÷2", "낙관 = ÷1"], rows,
            caption="붉은 칸은 상한에 걸려 깎인 값입니다. 엔비디아는 세 "
                    "시나리오 모두 상한에 걸립니다 — 그래서 엔비디아 결론이 "
                    "가장 가정 의존적입니다.",
            align=["l", "r", "r", "r", "r"]))

    w("<h4>성장률은 한 숫자가 아니라 10년에 걸친 경로입니다</h4>")
    w("<p>어떤 기업도 영원히 20%로 성장하지 못합니다. 그래서 1년차에 위 "
      "성장률로 시작해 <strong>10년에 걸쳐 직선으로 낮춥니다</strong>(감쇠 "
      "목표: 보수 2.5% / 중립 3.5% / 낙관 4.5%). 아래는 알파벳 중립의 "
      "경로입니다.</p>")
    ex = [c for c in applied if c["ticker"] == "GOOG"][0]
    exv = val(ex, "중립")
    exa = exv["assumptions"]
    w('<div class="bars">')
    gmax = max(p["growth"] for p in exv["projection"])
    for p in exv["projection"]:
        w(f'<div class="bar"><span class="yr">{p["year"]}년차</span>'
          f'<span class="track"><span class="fill" '
          f'style="width:{p["growth"] / gmax * 100:.1f}%"></span></span>'
          f'<span class="pc">{pct(p["growth"], 2)}</span></div>')
    w("</div>")

    # ② 절의 예시에 쓸 가정. ex/exv 는 ① 절에서 이미 잡아 두었습니다.
    exa_pre = exa
    w("<h3>풀어 쓴 계산 ② — 증분 ROIC은 왜 필요한가</h3>")
    w("<p><strong>성장에는 돈이 듭니다.</strong> 매출을 늘리려면 설비를 더 "
      "지어야 하고, 그 돈은 주주에게 못 갑니다. 얼마가 드는지는 “새로 넣은 "
      "1달러가 얼마를 버는가”, 즉 증분 ROIC이 정합니다.</p>")
    w('<div class="formula">'
      + esc("재투자율 = 성장률 ÷ 증분ROIC") + "\n"
      + esc("주주 몫 현금 = NOPAT × (1 − 재투자율)") + "\n\n"
      + esc(f"예) 성장 {pct(exa_pre['growth'])}, 증분ROIC "
            f"{pct(exa_pre['incremental_roic'])} → 재투자율 "
            f"{pct(exa_pre['growth'] / exa_pre['incremental_roic'])}"
            f" → 주주 몫은 NOPAT의 "
            f"{pct(1 - exa_pre['growth'] / exa_pre['incremental_roic'])}")
      + "</div>")
    w("<p>증분 ROIC이 낮을수록 같은 성장에 더 많은 돈이 들고, 주주 몫은 "
      "줄어듭니다. 이 값도 성장률과 같은 방식으로 각 기업의 <strong>자기 "
      "ROIC 기록</strong>에서 뽑았습니다.</p>")
    rows = []
    for c in applied:
        s0 = c["record"]["summary"]
        row = [nm(c), cell(pct(s0["roic_min"]), "flagc"),
               cell(pct(s0["roic_median"]), "flagc")]
        for s in ORDER:
            si = [x for x in c["scenario_inputs"] if x["name"] == s][0]
            raw, fin = si["incremental_roic_uncapped"], si["incremental_roic"]
            if si["incremental_roic_capped"]:
                row.append(cell(f"{pct(raw)} → <b>{pct(fin)}</b> (상한)",
                                "rich"))
            else:
                row.append(cell(f"<b>{pct(fin)}</b>", ""))
        rows.append(row)
    w(table(["기업", "10년 최저 ROIC", "10년 중위 ROIC",
             "보수 = 최저", "중립 = 중위÷2", "낙관 = 중위"], rows,
            caption="보수는 세 기업 모두 상한 15%에 걸립니다 — 즉 보수 "
                    "시나리오는 “지금의 비범한 수익률이 평범해진다면”을 "
                    "묻는 스트레스 테스트입니다. 예측이 아닙니다.",
            align=["l", "r", "r", "r", "r", "r"]))

    w("<h3>풀어 쓴 계산 ③ — 주당 가치는 어떻게 나왔나</h3>")
    w(f"<p>{esc(nm(ex))}의 <strong>중립 시나리오</strong>를 처음부터 끝까지 "
      f"따라가 보겠습니다. 다른 기업·시나리오도 같은 계산을 숫자만 바꿔 "
      f"한 것입니다.</p>")
    w(table(["이 시나리오의 가정", "값", "어디서 왔나"], [
        ["출발점 — TTM 세후영업이익(NOPAT)",
         cell(f"<b>{bn(ex['ttm']['nopat'])}십억</b>", "flagc"),
         cell("최근 4개 분기 영업이익 "
              f"{bn(ex['ttm']['operating_income']['value'])}십억 × "
              f"(1 − 실효세율 {pct(ex['ttm']['effective_tax_rate'])})", "")],
        ["1년차 성장률", pct(exa["growth"]),
         cell(f"10년 CAGR {pct(ex['record']['operating_income_cagr'])} ÷ 2",
              "")],
        ["10년차 성장률 (감쇠 목표)", pct(exa["fade_to"]),
         cell("중립 시나리오의 시장 가정", "")],
        ["증분 ROIC", pct(exa["incremental_roic"]),
         cell(f"10년 중위 ROIC "
              f"{pct(ex['record']['summary']['roic_median'])} ÷ 2", "")],
        ["할인율 (요구수익률)", pct(exa["discount"], 0),
         cell("중립 시나리오의 시장 가정 — 내가 요구하는 연 수익률", "")],
        ["11년차 이후 영구 성장률", pct(exa["terminal_growth"]),
         cell("중립 시나리오의 시장 가정", "")],
    ], align=["l", "r", "w"]))

    w("<h4>1~2단계 — 10년을 한 해씩 투영하고, 각 해의 현금을 오늘 값으로 "
      "당깁니다</h4>")
    w(table(["연차", "성장률", "NOPAT", "재투자율", "주주 몫 현금",
             "할인계수", "현재가치"],
            [[f"{p['year']}년차", pct(p["growth"], 2), bn(p["nopat"]),
              pct(p["reinvestment_rate"]), bn(p["free_cash_flow"]),
              f"{1 / (1 + exa['discount']) ** p['year']:.3f}",
              cell(f"<b>{bn(p['present_value'])}</b>", "")]
             for p in exv["projection"]],
            caption=f"단위 십억 달러. NOPAT은 전년 × (1+성장률), 주주 몫 "
                    f"현금은 NOPAT × (1−재투자율), 현재가치는 그 현금 ÷ "
                    f"(1+{pct(exa['discount'], 0)})의 연차 제곱입니다. "
                    f"재투자율이 55.2%에서 18.5%로 내려가는 것은 성장률이 "
                    f"낮아지면 성장에 드는 돈도 줄기 때문입니다.",
            align=["l", "r", "r", "r", "r", "r", "r"],
            foot=["10년 현재가치 합계", "", "", "", "", "",
                  bn(exv["pv_of_forecast"])]))

    w("<h4>3~5단계 — 11년차 이후를 한 덩어리로 묶고, 순현금을 더한 뒤 "
      "주식수로 나눕니다</h4>")
    last_nopat = exv["projection"][-1]["nopat"]
    term_undisc = exv["pv_of_terminal"] / (1 / (1 + exa["discount"]) ** 10)
    w(table(["단계", "계산", "값"], [
        ["① 10년치 현재가치 합계", "위 표의 마지막 줄",
         cell(f"<b>{bn(exv['pv_of_forecast'])}십억</b>", "")],
        ["② 11년차 이후 가치 (터미널)",
         cell(f"10년차 NOPAT {bn(last_nopat)} × (1+"
              f"{pct(exa['terminal_growth'])}) × (1 − "
              f"{pct(exa['terminal_growth'])}÷"
              f"{pct(exa['incremental_roic'])}) ÷ "
              f"({pct(exa['discount'], 0)} − "
              f"{pct(exa['terminal_growth'])})", ""),
         cell(f"{bn(term_undisc)}십억", "")],
        ["③ 터미널을 현재가치로",
         cell(f"② ÷ (1+{pct(exa['discount'], 0)})¹⁰", ""),
         cell(f"<b>{bn(exv['pv_of_terminal'])}십억</b>", "flagc")],
        ["④ 기업가치", "① + ③",
         cell(f"<b>{bn(exv['enterprise_value'])}십억</b>", "")],
        ["⑤ 자기자본가치", cell(f"④ + 순현금 "
                            f"{bn(ex['balance_sheet']['net_cash'])}십억", ""),
         cell(f"<b>{bn(exv['equity_value'])}십억</b>", "")],
        ["⑥ 주당 가치",
         cell(f"⑤ ÷ 주식수 "
              f"{ex['shares_outstanding']['value'] / BN:,.3f}십억 주", ""),
         cell(f"<b>{usd(exv['value_per_share'], 2)}</b>",
              cheapness(exv["value_per_share"], ex["price"]))],
    ], align=["l", "w", "r"],
       caption=f"현재가는 {usd(ex['price'], 2)}입니다. 즉 중립 가정이 맞다면 "
               f"현재가는 가치의 "
               f"{exv['price_to_value']:.2f}배 — "
               f"{sg(exv['upside_vs_market'], 0)}입니다."))
    w('<div class="callout"><p><strong>③이 전체의 '
      + pct(exv["terminal_share"], 0)
      + '를 차지합니다.</strong> 즉 가치의 대부분이 11년차 이후에서 '
        '나옵니다. 이것이 이 모형의 가장 큰 약점이고, 그래서 주당 가치를 '
        '“정답”이 아니라 “이 가정이 맞다면 이 값”으로 읽어야 '
        '합니다.</p></div>')
    w("<h4>왜 ‘할인’하는가</h4>")
    w(f"<p>내년의 1달러는 오늘의 1달러보다 못합니다. 오늘 1달러를 다른 곳에 "
      f"넣어 {pct(exa['discount'], 0)}를 벌 수 있다면, 내년의 1달러는 오늘 "
      f"기준으로 1÷1.{int(exa['discount'] * 100)} = "
      f"{1 / (1 + exa['discount']):.3f}달러의 값입니다. 10년 뒤의 1달러는 "
      f"{1 / (1 + exa['discount']) ** 10:.3f}달러입니다. 위 표의 ‘할인계수’가 "
      f"그 환산율이고, <strong>할인율이 바로 “내가 요구하는 연 수익률”"
      f"</strong>입니다. 그래서 할인율을 9%로 두면 같은 사업이 더 비싸 보이고, "
      f"11%로 두면 더 싸 보입니다 — 시나리오별로 할인율을 다르게 둔 이유입니다."
      f"</p>")

    w("<h3>한눈에 보기 — 사업의 질</h3>")
    w(table(["기업", "TTM 영업이익", "영업이익률", "10년 CAGR", "ROIC 중위",
             "순현금"],
            [[nm(c), bn(c["ttm"]["operating_income"]["value"]),
              pct(c["ttm"]["operating_margin"]),
              pct(c["record"]["operating_income_cagr"]),
              cell(pct(c["record"]["summary"]["roic_median"]), "cheap"),
              cell(bn(c["balance_sheet"]["net_cash"], 0),
                   sign(c["balance_sheet"]["net_cash"]))]
             for c in applied],
            caption=f"단위 십억 달러. 세 기업 모두 10년 내내 ROIC가 문턱 "
                    f"{pct(d['wacc_for_roic_hurdle'], 0)}을 넘었습니다 — "
                    f"사업의 질은 전부 합격입니다. 스페이스X는 10-K가 없어 "
                    f"10년 기록이 없습니다."))

    w("<h3>공통 패턴 — ROIC가 모두 내려오고 있습니다</h3>")
    w(table(["기업", "ROIC 고점", "최근", "영업이익 배수", "투하자본 배수"],
            [[nm(c),
              f"FY{c['record']['trend']['peak_fiscal_year']} "
              f"{pct(c['record']['trend']['peak_roic'])}",
              f"FY{c['record']['trend']['last_fiscal_year']} "
              f"{pct(c['record']['trend']['last_roic'])}",
              f"{c['record']['trend']['operating_income_multiple']:.2f}배",
              cell(f"{c['record']['trend']['invested_capital_multiple']:.2f}배",
                   "flagc")]
             for c in applied],
            caption="고점 이후 배수. 투하자본이 영업이익보다 빨리 늘면 ROIC는 "
                    "떨어집니다."))
    w("<p><strong>세 기업이 같은 모양입니다.</strong> 마이크로소프트가 가장 "
      "극단적입니다 — FY2019 이후 영업이익은 3.6배인데 투하자본은 "
      "10.6배입니다. <strong>가격 판정보다 이 추세가 더 중요할 수 "
      "있습니다</strong>: AI 설비 투자가 과거의 수익률로 돌아오는지가 세 기업 "
      "모두의 핵심 질문입니다.</p>")

    for c in applied:
        v_lo, v_mid, v_hi = val(c, "보수"), val(c, "중립"), val(c, "낙관")
        w(f"<h3>{esc(nm(c))} — {usd(c['price'], 2)}</h3>")
        rows = []
        for s in ORDER:
            v, a = val(c, s), val(c, s)["assumptions"]
            ig = v["implied_growth_at_price"]
            rows.append([
                s, f"{pct(a['growth'])} → {pct(a['fade_to'])}",
                pct(a["incremental_roic"]), pct(a["discount"], 0),
                cell(f"<b>{usd(v['value_per_share'])}</b>",
                     cheapness(v["value_per_share"], c["price"])),
                cell(sg(v["upside_vs_market"], 0),
                     cheapness(v["value_per_share"], c["price"])),
                cell(pct(ig) if ig is not None else "없음",
                     "" if ig is not None else "rich"),
            ])
        w(table(["시나리오", "성장률", "증분ROIC", "할인율", "주당 가치",
                 "현재가 대비", "정당화 성장률"], rows,
                caption=f"TTM 영업이익 "
                        f"{bn(c['ttm']['operating_income']['value'])}십억 × "
                        f"(1 − {pct(c['ttm']['effective_tax_rate'])}) = NOPAT "
                        f"{bn(c['ttm']['nopat'])}십억 · 주가÷NOPAT "
                        f"{c['market_cap'] / c['ttm']['nopat']:.1f}배 · "
                        f"{esc(c['ttm']['tax_note'])}",
           align=["l", "r", "r", "r", "r", "r", "r"]))
        if v_hi["upside_vs_market"] > 0:
            w(f"<p><strong>낙관 시나리오에서만 현재가보다 높습니다</strong> "
              f"({usd(v_hi['value_per_share'])}, "
              f"{sg(v_hi['upside_vs_market'], 0)}). 그 가정은 성장 "
              f"{pct(v_hi['assumptions']['growth'])}로 시작해 10년에 걸쳐 "
              f"{pct(v_hi['assumptions']['fade_to'])}로 내려가고, 새 자본이 "
              f"{pct(v_hi['assumptions']['incremental_roic'])}를 벌고, "
              f"요구수익률이 {pct(v_hi['assumptions']['discount'], 0)}라는 "
              f"것입니다.</p>")
        else:
            w(f"<p><strong>세 시나리오 모두 현재가보다 낮습니다.</strong> 가장 "
              f"관대한 낙관 가정에서도 {usd(v_hi['value_per_share'])}"
              f"({sg(v_hi['upside_vs_market'], 0)})입니다.</p>")
        w(f"<p>보수·중립에서는 성장률을 증분 ROIC 직전까지 — 즉 10년간 "
          f"잉여현금을 거의 전부 재투자하는 지점까지 — 올려도 천장이 "
          f"주당 {usd(v_lo['best_case_in_scenario']['value_per_share'])}"
          f"(보수)와 "
          f"{usd(v_mid['best_case_in_scenario']['value_per_share'])}(중립)로 "
          f"현재가 아래입니다.</p>")

    # 스페이스X
    w(f"<h3>{esc(nm(sx))} — {usd(sx['price'], 2)} (별도 취급)</h3>")
    w(f'<div class="callout"><p><strong>{esc(sx["why_not"])}</strong></p></div>')
    w(table(["기준이익 후보", "연율화 NOPAT", "내용"],
            [[b["name"], cell(bn(b["nopat"]), sign(b["nopat"])),
              cell(esc(b["note"]), "")] for b in sx["earnings_bases"]],
            caption=f"단위 십억 달러. 상반기 {bn(sx['nopat_first_half'])}십억 "
                    f"적자에 3분기 {bn(sx['nopat_q3'])}십억 흑자입니다.",
            align=["l", "r", "w"]))
    rows = []
    for b in sx["earnings_bases"]:
        if not b.get("valuations"):
            rows.append([b["name"], "—", "—", "—"])
            continue
        rows.append([b["name"]] + [
            cell(f"{usd(v['value_per_share'])} "
                 f"({sg(v['upside_vs_market'], 0)})", "rich")
            for v in b["valuations"]])
    w(table(["기준이익", "보수", "중립", "낙관"], rows,
            caption="어느 기준을 잡아도 현재가 $123.62 와는 한 자릿수 대 세 "
                    "자릿수로 벌어집니다."))
    w("<p>더 정직한 답은 거꾸로 푸는 것입니다 — <strong>현재 가격이 "
      "정당화되려면 정상상태 세후영업이익이 얼마여야 하는가.</strong> 기준을 "
      "고르지 않아도 되기 때문입니다.</p>")
    rv = sx["revenue"]
    w(table(["시나리오", "요구 NOPAT", "3분기 연율화의", "연율화 매출의"],
            [[r["scenario"], cell(f"{bn(r['required_nopat_at_price'])}십억",
                                  "rich"),
              f"{r['vs_q3_annualised']:.1f}배",
              cell(pct(r["as_share_of_q3_annualised_revenue"], 0), "rich")]
             for r in sx["reverse"]],
            caption=f"3분기 매출 연율화 {bn(rv['q3_annualised'])}십억 달러 "
                    f"(9개월 연율화 {bn(rv['nine_months_annualised'])}십억 — "
                    f"가속 중). 시가총액은 그 매출의 "
                    f"{rv['market_cap_to_q3_annualised_revenue']:.0f}배."))
    w(f"<p>가장 관대한 낙관 가정에서도 현재 가격은 <strong>지금 연율화 매출의 "
      f"{pct(sx['reverse'][2]['as_share_of_q3_annualised_revenue'], 0)}를 "
      f"세후영업이익으로 벌어야</strong> 설명됩니다. 매출이 몇 배로 커지면서 "
      f"이익률까지 올라야 한다는 뜻이고, 이것은 가치평가 문제가 아니라 "
      f"<strong>아직 존재하지 않는 규모의 사업에 대한 베팅</strong>입니다.</p>")
    seg = sx["segments_9m"]
    if isinstance(seg, dict):
        w(table(["사업부", "Q3′26 매출", "Q3′26 영업이익", "9M′26 매출",
                 "9M′26 영업이익"],
                [[k, bn(v["revenue"]["q3_2026"]),
                  cell(bn(v["operating_income"]["q3_2026"]),
                       sign(v["operating_income"]["q3_2026"])),
                  bn(v["revenue"]["9m_2026"]),
                  cell(bn(v["operating_income"]["9m_2026"]),
                       sign(v["operating_income"]["9m_2026"]))]
                 for k, v in seg.items() if isinstance(v, dict)],
                caption="단위 십억 달러. 사업부 투하자본은 공시되지 않으므로 "
                        "사업부 ROIC를 만들지 않았습니다. Connectivity가 "
                        "스타링크입니다."))

    # ============================================================ 3부
    w("<h2>3부. 판정</h2>")
    w(table(["기업", "현재가", "보수", "중립", "낙관", "판정"],
            [[nm(c), usd(c["price"], 2),
              cell(usd(val(c, "보수")["value_per_share"]), "rich"),
              cell(usd(val(c, "중립")["value_per_share"]), "rich"),
              cell(usd(val(c, "낙관")["value_per_share"]),
                   cheapness(val(c, "낙관")["value_per_share"], c["price"])),
              cell("낙관에서만 설명됨"
                   if val(c, "낙관")["upside_vs_market"] > 0
                   else "어느 시나리오에서도 비쌈",
                   cheapness(val(c, "낙관")["value_per_share"], c["price"]))]
             for c in applied]
            + [[nm(sx), usd(sx["price"], 2), "—", "—", "—",
                cell("기준이익 미성립 — 산출 불가", "flagc")]],
            align=["l", "r", "r", "r", "r", "w"]))
    w('<div class="callout"><p><strong>가장 중요한 발견은 순위가 '
      '아닙니다.</strong> 보수·중립 시나리오에서는 세 기업 모두 <strong>어떤 '
      '성장률로도 현재 가격이 설명되지 않습니다.</strong> 이유는 산수입니다: '
      '증분 ROIC이 할인율보다 조금만 높으면, 성장률을 올려도 재투자가 그만큼 '
      '늘어 주주에게 남는 현금이 줄어듭니다. 증분 ROIC 15%에서 성장률 15%면 '
      '재투자율이 100%가 되어 잉여현금이 0입니다 — 그래서 가치에 천장이 '
      '생깁니다.</p></div>')
    w(table(["기업", "보수 천장", "중립 천장", "현재가", "중립 천장의 몇 배"],
            [[nm(c),
              cell(usd(val(c, "보수")["best_case_in_scenario"]
                       ["value_per_share"]), "rich"),
              cell(usd(val(c, "중립")["best_case_in_scenario"]
                       ["value_per_share"]), "rich"),
              usd(c["price"], 2),
              cell(f"{val(c, '중립')['price_vs_best_case']:.2f}배", "rich")]
             for c in applied],
            caption="천장 = 그 시나리오의 가정 안에서 성장률만 바꿔 얻을 수 "
                    "있는 최대 주당가치. 성장률을 증분 ROIC 직전까지 올린 "
                    "지점이고, 10년간 잉여현금을 거의 전부 재투자하는 "
                    "가정입니다."))
    w("<p><strong>즉 세 기업의 현재 가격은 “지금의 높은 수익률이 계속된다”를 "
      "이미 값으로 담고 있습니다.</strong> 수익률이 평범해지는 경우를 가격이 "
      "반영하지 않습니다. 그것이 안전마진이 없다는 뜻입니다.</p>")

    w("<h3>상대 순위 (같은 잣대로 비교할 때)</h3>")
    ranked = sorted(applied, key=lambda c: -val(c, "중립")["upside_vs_market"])
    w(table(["순위", "기업", "중립 대비", "낙관 대비", "주가÷NOPAT",
             "현재가÷중립평가치"],
            [[str(i), nm(c),
              cell(sg(val(c, "중립")["upside_vs_market"], 0), "rich"),
              cell(sg(val(c, "낙관")["upside_vs_market"], 0),
                   cheapness(val(c, "낙관")["value_per_share"], c["price"])),
              f"{c['market_cap'] / c['ttm']['nopat']:.1f}배",
              f"{val(c, '중립')['price_to_value']:.2f}배"]
             for i, c in enumerate(ranked, start=1)]))
    w(f"<p>같은 규칙·같은 할인율로 재면 <strong>{esc(ranked[0]['korean'])}이 "
      f"가장 덜 비싸고 {esc(ranked[-1]['korean'])}이 가장 비쌉니다.</strong> "
      f"다만 {esc(ranked[0]['korean'])}의 상대적 저평가는 <strong>가장 가정 "
      f"의존적</strong>입니다 — 10년 CAGR "
      f"{pct(ranked[0]['record']['operating_income_cagr'])}와 ROIC 중위 "
      f"{pct(ranked[0]['record']['summary']['roic_median'])}가 둘 다 상한에 "
      f"걸려 크게 깎인 뒤의 숫자이기 때문입니다. 이미 연 매출 "
      f"{bn(ranked[0]['ttm']['revenue']['value'], 0)}십억 달러인 기업이 10년간 "
      f"{pct(val(ranked[0], '낙관')['assumptions']['growth'], 0)}로 성장한다는 "
      f"가정이 맞는지가 열린 질문입니다.</p>")

    # ============================================================ 4부
    w("<h2>4부. 방법과 한계</h2>")
    tmin = min(val(c, s)["terminal_share"] for c in applied for s in ORDER)
    tmax = max(val(c, s)["terminal_share"] for c in applied for s in ORDER)
    w("<ul>")
    w(f"<li><strong>터미널 가치가 전체의 {pct(tmin, 0)}~{pct(tmax, 0)}를 "
      f"차지합니다.</strong> 가치의 대부분이 11년차 이후에서 옵니다. 10년 "
      f"투영은 모양을 잡아 주지만 결론을 정하지는 못합니다 — 이 모형의 가장 큰 "
      f"약점이고, 그래서 단일 적정주가로 읽으면 안 됩니다.</li>")
    w("<li><strong>기업마다 자료 기준일이 다릅니다.</strong> "
      + " · ".join(f"{esc(nm(c))} {c['data_as_of']}" for c in applied)
      + ". 엔비디아는 3분기(10월 말 결산)가 아직 제출되지 않아 7월 분기가 "
        "최신입니다 — 분기 영업이익이 전분기 대비 19% 늘고 있는 기업이므로 이 "
        "한 분기 차이가 작지 않습니다.</li>")
    w("<li><strong>실효세율에 평가손익이 섞여 있습니다.</strong> 세전이익 중 "
      "영업 외 수익 비중이 "
      + " · ".join(f"{esc(nm(c))} "
                   f"{pct(c['ttm']['nonoperating_share_of_pretax'], 0)}"
                   for c in applied)
      + ". 법정세율 21%로 바꾸면 NOPAT이 "
      + " · ".join(
          f"{esc(nm(c))} "
          f"{sg(c['ttm']['nopat_at_statutory_21'] / c['ttm']['nopat'] - 1, 1)}"
          for c in applied)
      + " 움직이며, 판정은 바뀌지 않습니다.</li>")
    w("<li><strong>상한이 결론을 만듭니다.</strong> 특히 엔비디아는 성장률과 "
      "증분 ROIC이 둘 다 상한에 걸립니다. 상한을 올리면 저평가로, 내리면 "
      "고평가로 바뀝니다. 엑셀에서 직접 바꿔 보실 수 있게 수식으로 "
      "남겼습니다.</li>")
    w("<li><strong>사업부별 투하자본은 공시되지 않습니다.</strong> 사업부 "
      "ROIC를 만들지 않았습니다.</li>")
    w("<li><strong>검증.</strong> <code>python3 verify_fair_value.py "
      "--mutate</code> — 항등식·앵커·재산출·규칙재현 1,013건, 변이 검정 31건. "
      "앵커는 10-Q 손익계산서에서 손으로 읽은 분기 수치이고(마이크로소프트 "
      "2026-09-30 영업이익 $45,915m, 엔비디아 2026-07-26 $63,734m), 알파벳 "
      "TTM 영업이익은 별도 파이프라인(282건 검증)의 값과 일치합니다. 이 "
      "페이지도 <code>--verify --mutate</code>로 표를 되읽어 "
      "대조합니다.</li>")
    w("</ul>")
    w(f'<footer>출처: SEC EDGAR companyfacts와 10-Q 렌더링 · 50개사 ROIC 조사'
      f'(roic/roic.json, 생성 {d["roic_study_generated"]}, 창 '
      f'{d["roic_study_window"][0]}–{d["roic_study_window"][1]}) · 시세 '
      f'{d["prices_fetched_utc"][:10]} 수집.<br>'
      + " · ".join(f'{esc(nm(c))} CIK {c["cik"]}' for c in applied)
      + f' · {esc(nm(sx))} CIK {esc(sx["cik"])}<br>'
      f'자료 기준일 {d["generated"]} · 검증 1,013건 통과, 변이 31건 '
      f'포착.</footer>')
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


def find_table(page, header_has):
    hits = [(h, r) for h, r in tables_of(page)
            if any(header_has in x for x in h)]
    if len(hits) != 1:
        raise SystemExit(
            f"표 특정 실패: 헤더에 {header_has!r} 를 가진 표가 {len(hits)}개")
    return hits[0]


def section_of(page, heading_prefix):
    """
    h3 제목으로 시작하는 구획만 잘라냅니다.

    세 기업의 시나리오 표가 헤더를 공유하므로 헤더만으로는 특정되지
    않습니다. 행 이름만으로 찾지 말라는 규칙과 같은 문제이고, 한 단계 더 위 —
    **구획을 먼저 특정** — 로 해결합니다.
    """
    i = page.find(f"<h3>{heading_prefix}")
    if i < 0:
        raise SystemExit(f"구획 특정 실패: <h3>{heading_prefix}...")
    j = len(page)
    for tag in ("<h3>", "<h2>"):
        k = page.find(tag, i + 4)
        if 0 <= k < j:
            j = k
    return page[i:j]


def find_row(page, header_has, label, exact=True, col=0):
    """
    표를 먼저 특정하고, 그 안에서 행을 완전일치로 찾습니다.

    col 은 순위표 때문에 필요합니다 — 첫 열이 순위 번호이고 기업명이 둘째
    열에 있습니다.
    """
    _, rows = find_table(page, header_has)
    hit = [r for r in rows if len(r) > col
           and (r[col] == label if exact else label in r[col])]
    if len(hit) != 1:
        raise SystemExit(f"행 특정 실패: {header_has!r} 표에서 {label!r} 가 "
                         f"{len(hit)}개 (완전일치={exact})")
    return hit[0]


def verify(page, d):
    applied = [c for c in d["companies"] if c["model"] == "applied"]
    sx = [c for c in d["companies"]
          if c["model"] == "base_not_established"][0]
    fails, passed = [], 0

    def val(co, s):
        return [v for v in co["valuations"] if v["scenario"] == s][0]

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
    true("테마 토큰이 맨 :root 에", bool(re.search(r"^:root\{", page, re.M)))
    true("다크 (prefers-color-scheme) 가드",
         ':root:not([data-theme="light"])' in page)
    true("다크 (data-theme) 가드", ':root[data-theme="dark"]' in page)
    true("body 배경이 토큰", "background:var(--bg)" in flat)
    true("표가 가로 스크롤 안",
         page.count('<div class="scroll">') == page.count("<table>"))
    for host in set(re.findall(r'(?:src|href)="https?://([^/"]+)', page)):
        true(f"허용 호스트 {host}",
             host in ("fonts.googleapis.com", "fonts.gstatic.com",
                      "cdnjs.cloudflare.com"), host)
    # 토큰은 **맨 :root** 에 정의돼야 합니다. 다크 블록에만 있으면
    # data-theme 가 없는 기본 상태(대부분의 독자)에서 색이 비어 버립니다.
    bare = re.search(r"^:root\{(.*?)\}", page, re.S | re.M)
    true("맨 :root 블록 존재", bool(bare))
    TOKENS = ("--bg", "--panel", "--fg", "--dim", "--line", "--ink",
              "--accent", "--cheap", "--rich", "--pos", "--neg", "--flag",
              "--price")
    for tk in TOKENS:
        true(f"토큰 {tk} 가 맨 :root 에 정의됨",
             bool(bare) and f"{tk}:" in bare.group(1))
    for guard in (r':root:not\(\[data-theme="light"\]\)\{(.*?)\}',
                  r':root\[data-theme="dark"\]\{(.*?)\}'):
        m = re.search(guard, page, re.S)
        true(f"다크 블록 존재 {guard[:28]}", bool(m))
        if m:
            for tk in ("--bg", "--fg", "--cheap", "--rich", "--price"):
                true(f"다크 블록에 {tk} 재정의", f"{tk}:" in m.group(1))
            true("다크 블록에 color-scheme:dark",
                 "color-scheme:dark" in m.group(1).replace(" ", ""))

    # 축 블록: 막대 길이와 현재가 선 위치가 값에 비례하는지
    for co in applied:
        px = co["price"]
        vals = {v["scenario"]: v["value_per_share"] for v in co["valuations"]}
        top = max(max(vals.values()), px) * 1.12
        blk = re.search(
            r'<div class="scale">\s*<div class="hd">'
            r'<span class="nm">' + re.escape(co["korean"]) + r'\s*\('
            + re.escape(co["ticker"]) + r'\)</span>(.*?)</div>\s*</div>',
            page, re.S)
        true(f"{co['ticker']} 축 블록 존재", bool(blk))
        if not blk:
            continue
        body = blk.group(1)
        eq(f"{co['ticker']} 축 현재가 표기",
           (re.search(r'<span class="px">현재 (.*?)</span>', body) or
            [None, ""])[1], usd(px, 2))
        widths = [float(x) for x in
                  re.findall(r'class="fl [a-z]+" style="width:([\d.]+)%"',
                             body)]
        eq(f"{co['ticker']} 축 막대 3개", len(widths), 3)
        for s, wd in zip(ORDER, widths):
            true(f"{co['ticker']} 축 {s} 막대 길이 비례",
                 abs(wd - vals[s] / top * 100) < 0.05,
                 f"{wd} vs {vals[s] / top * 100:.2f}")
        pl = re.search(r'class="pline" style="left:([\d.]+)%"', body)
        true(f"{co['ticker']} 현재가 선 존재", bool(pl))
        if pl:
            true(f"{co['ticker']} 현재가 선 위치 비례",
                 abs(float(pl.group(1)) - px / top * 100) < 0.05,
                 f"{pl.group(1)} vs {px / top * 100:.2f}")
        labels = re.findall(r'<span class="vv">(.*?)</span>', body)
        for s, lab in zip(ORDER, labels):
            eq(f"{co['ticker']} 축 {s} 값 표기", lab, usd(vals[s]))

    # ---- 풀어 쓴 계산 절 ------------------------------------------------
    ex = [c for c in applied if c["ticker"] == "GOOG"][0]
    exv = val(ex, "중립")
    exa = exv["assumptions"]

    # ① 성장률 도출 표
    for co in applied:
        label = f"{co['korean']}({co['ticker']})"
        r = find_row(page, "10년 영업이익 CAGR (측정값)", label)
        eq(f"풀이① {co['ticker']} 10년 CAGR", r[1],
           pct(co["record"]["operating_income_cagr"]))
        for i, s in enumerate(ORDER, start=2):
            si = [x for x in co["scenario_inputs"] if x["name"] == s][0]
            want = (f"{pct(si['growth_uncapped'])} → {pct(si['growth'])} (상한)"
                    if si["growth_capped"] else pct(si["growth"]))
            eq(f"풀이① {co['ticker']} {s} 성장률", r[i], want)
        # ② 증분 ROIC 도출 표
        r = find_row(page, "10년 중위 ROIC", label)
        eq(f"풀이② {co['ticker']} 10년 최저 ROIC", r[1],
           pct(co["record"]["summary"]["roic_min"]))
        eq(f"풀이② {co['ticker']} 10년 중위 ROIC", r[2],
           pct(co["record"]["summary"]["roic_median"]))
        for i, s in enumerate(ORDER, start=3):
            si = [x for x in co["scenario_inputs"] if x["name"] == s][0]
            want = (f"{pct(si['incremental_roic_uncapped'])} → "
                    f"{pct(si['incremental_roic'])} (상한)"
                    if si["incremental_roic_capped"]
                    else pct(si["incremental_roic"]))
            eq(f"풀이② {co['ticker']} {s} 증분ROIC", r[i], want)

    # 10년 성장 경로 막대
    sec = page[page.find("<h4>성장률은 한 숫자가"):
               page.find("<h3>풀어 쓴 계산 ②")]
    bars = re.findall(r'<span class="yr">(.*?)</span>.*?'
                      r'style="width:([\d.]+)%".*?'
                      r'<span class="pc">(.*?)</span>', sec, re.S)
    eq("풀이① 성장 경로 막대 10개", len(bars), 10)
    gmax = max(p_["growth"] for p_ in exv["projection"])
    for p_, (yr, wd, lab) in zip(exv["projection"], bars):
        eq(f"풀이① 경로 {p_['year']}년차 라벨", yr, f"{p_['year']}년차")
        eq(f"풀이① 경로 {p_['year']}년차 값", lab, pct(p_["growth"], 2))
        true(f"풀이① 경로 {p_['year']}년차 막대 비례",
             abs(float(wd) - p_["growth"] / gmax * 100) < 0.05,
             f"{wd} vs {p_['growth'] / gmax * 100:.2f}")

    # ③ 연도별 투영 표
    for p_ in exv["projection"]:
        r = find_row(page, "주주 몫 현금", f"{p_['year']}년차")
        eq(f"풀이③ {p_['year']}년차 성장률", r[1], pct(p_["growth"], 2))
        eq(f"풀이③ {p_['year']}년차 NOPAT", r[2], bn(p_["nopat"]))
        eq(f"풀이③ {p_['year']}년차 재투자율", r[3],
           pct(p_["reinvestment_rate"]))
        eq(f"풀이③ {p_['year']}년차 주주몫현금", r[4],
           bn(p_["free_cash_flow"]))
        eq(f"풀이③ {p_['year']}년차 할인계수", r[5],
           f"{1 / (1 + exa['discount']) ** p_['year']:.3f}")
        eq(f"풀이③ {p_['year']}년차 현재가치", r[6], bn(p_["present_value"]))
    _, prj = find_table(page, "주주 몫 현금")
    foot = [x for x in prj if x and x[0] == "10년 현재가치 합계"]
    eq("풀이③ 합계 행 존재", len(foot), 1)
    if foot:
        eq("풀이③ 10년 현재가치 합계", foot[0][-1],
           bn(exv["pv_of_forecast"]))

    # ③ 6단계 표
    steps = {
        "① 10년치 현재가치 합계": f"{bn(exv['pv_of_forecast'])}십억",
        "③ 터미널을 현재가치로": f"{bn(exv['pv_of_terminal'])}십억",
        "④ 기업가치": f"{bn(exv['enterprise_value'])}십억",
        "⑤ 자기자본가치": f"{bn(exv['equity_value'])}십억",
        "⑥ 주당 가치": usd(exv["value_per_share"], 2),
    }
    for lab, want in steps.items():
        r = find_row(page, "어디서 왔나" if False else "단계", lab)
        eq(f"풀이③ 단계 {lab}", r[2], want)
    # 터미널 비중이 본문 서술과 같은지
    true("풀이③ 터미널 비중 서술",
         f"{pct(exv['terminal_share'], 0)}를 차지합니다" in page)
    # 출발점 NOPAT
    r = find_row(page, "어디서 왔나", "출발점 — TTM 세후영업이익(NOPAT)")
    eq("풀이③ 출발점 NOPAT", r[1], f"{bn(ex['ttm']['nopat'])}십억")
    for lab, want in (("1년차 성장률", pct(exa["growth"])),
                      ("10년차 성장률 (감쇠 목표)", pct(exa["fade_to"])),
                      ("증분 ROIC", pct(exa["incremental_roic"])),
                      ("할인율 (요구수익률)", pct(exa["discount"], 0)),
                      ("11년차 이후 영구 성장률",
                       pct(exa["terminal_growth"]))):
        r = find_row(page, "어디서 왔나", lab)
        eq(f"풀이③ 가정 {lab}", r[1], want)
    # 3단계 설명 카드
    true("풀이① 3단계 카드", page.count('<div class="step">') == 3)

    # 기업별 시나리오 표 — 구획을 먼저 자릅니다.
    for co in applied:
        sec = section_of(page, f"{co['korean']}({co['ticker']}) —")
        for s in ORDER:
            v = val(co, s)
            a = v["assumptions"]
            r = find_row(sec, "정당화 성장률", s)
            eq(f"{co['ticker']} {s} 성장률", r[1],
               f"{pct(a['growth'])} → {pct(a['fade_to'])}")
            eq(f"{co['ticker']} {s} 증분ROIC", r[2],
               pct(a["incremental_roic"]))
            eq(f"{co['ticker']} {s} 할인율", r[3], pct(a["discount"], 0))
            eq(f"{co['ticker']} {s} 주당가치", r[4],
               usd(v["value_per_share"]))
            eq(f"{co['ticker']} {s} 현재가 대비", r[5],
               sg(v["upside_vs_market"], 0))
            ig = v["implied_growth_at_price"]
            eq(f"{co['ticker']} {s} 정당화 성장률", r[6],
               pct(ig) if ig is not None else "없음")

    # 사업의 질 / 추세 / 판정 / 천장 / 순위
    for co in applied:
        label = f"{co['korean']}({co['ticker']})"
        r = find_row(page, "ROIC 중위", label)
        eq(f"{co['ticker']} TTM 영업이익", r[1],
           bn(co["ttm"]["operating_income"]["value"]))
        eq(f"{co['ticker']} 영업이익률", r[2],
           pct(co["ttm"]["operating_margin"]))
        eq(f"{co['ticker']} 10년 CAGR", r[3],
           pct(co["record"]["operating_income_cagr"]))
        eq(f"{co['ticker']} ROIC 중위", r[4],
           pct(co["record"]["summary"]["roic_median"]))
        tr = co["record"]["trend"]
        r = find_row(page, "투하자본 배수", label)
        eq(f"{co['ticker']} 추세 고점", r[1],
           f"FY{tr['peak_fiscal_year']} {pct(tr['peak_roic'])}")
        eq(f"{co['ticker']} 추세 최근", r[2],
           f"FY{tr['last_fiscal_year']} {pct(tr['last_roic'])}")
        eq(f"{co['ticker']} 추세 투하자본 배수", r[4],
           f"{tr['invested_capital_multiple']:.2f}배")
        r = find_row(page, "판정", label)
        eq(f"{co['ticker']} 판정 보수", r[2],
           usd(val(co, "보수")["value_per_share"]))
        eq(f"{co['ticker']} 판정 낙관", r[4],
           usd(val(co, "낙관")["value_per_share"]))
        r = find_row(page, "중립 천장의 몇 배", label)
        eq(f"{co['ticker']} 보수 천장", r[1],
           usd(val(co, "보수")["best_case_in_scenario"]["value_per_share"]))
        eq(f"{co['ticker']} 중립 천장", r[2],
           usd(val(co, "중립")["best_case_in_scenario"]["value_per_share"]))
        eq(f"{co['ticker']} 현재가÷중립천장", r[4],
           f"{val(co, '중립')['price_vs_best_case']:.2f}배")
        r = find_row(page, "현재가÷중립평가치", label, col=1)
        eq(f"{co['ticker']} 순위 중립 대비", r[2],
           sg(val(co, "중립")["upside_vs_market"], 0))
        eq(f"{co['ticker']} 순위 낙관 대비", r[3],
           sg(val(co, "낙관")["upside_vs_market"], 0))
        eq(f"{co['ticker']} 순위 현재가÷중립평가치", r[5],
           f"{val(co, '중립')['price_to_value']:.2f}배")

    # 스페이스X
    for b in sx["earnings_bases"]:
        r = find_row(page, "연율화 NOPAT", b["name"])
        eq(f"스페이스X {b['name']} NOPAT", r[1], bn(b["nopat"]))
    for rr in sx["reverse"]:
        r = find_row(page, "연율화 매출의", rr["scenario"])
        eq(f"스페이스X {rr['scenario']} 요구 NOPAT", r[1],
           f"{bn(rr['required_nopat_at_price'])}십억")
        eq(f"스페이스X {rr['scenario']} 매출 비중", r[3],
           pct(rr["as_share_of_q3_annualised_revenue"], 0))
    seg = sx["segments_9m"]
    for k, v in seg.items():
        if not isinstance(v, dict):
            continue
        r = find_row(page, "9M′26 영업이익", k)
        eq(f"스페이스X 사업부 {k} Q3 매출", r[1], bn(v["revenue"]["q3_2026"]))
        eq(f"스페이스X 사업부 {k} Q3 영업이익", r[2],
           bn(v["operating_income"]["q3_2026"]))

    # 트립와이어: 결론이 표와 어긋나지 않는지
    true("낙관에서만 설명된다는 서술", "낙관 시나리오에서만" in page)
    true("보수·중립에 해가 없다는 서술", "어떤 성장률로도" in page)
    true("보수·중립 정당화 성장률이 실제로 없음",
         all(val(c, s)["implied_growth_at_price"] is None
             for c in applied for s in ("보수", "중립")))
    true("낙관 정당화 성장률은 있음",
         all(val(c, "낙관")["implied_growth_at_price"] is not None
             for c in applied))
    true("스페이스X 단일 적정주가 없음", "valuations" not in sx)
    return passed, fails


MUTATIONS = [
    ("MSFT 축 막대 길이 훼손",
     lambda p: re.sub(r'(class="fl cheap" style="width:)[\d.]+',
                      r"\g<1>99.0", p, count=1)),
    ("현재가 선 위치 훼손",
     lambda p: re.sub(r'(class="pline" style="left:)[\d.]+',
                      r"\g<1>10.0", p, count=1)),
    ("축 값 표기 훼손", lambda p: p.replace('<span class="vv">$190</span>',
                                       '<span class="vv">$290</span>', 1)),
    ("시나리오 표 주당가치 훼손", lambda p: p.replace("<b>$277</b>",
                                              "<b>$377</b>", 1)),
    ("정당화 성장률 표기 훼손", lambda p: p.replace(">20.5%<", ">30.5%<", 1)),
    ("ROIC 중위 표기 훼손", lambda p: p.replace(">70.3%<", ">60.3%<", 1)),
    ("추세 투하자본 배수 표기 훼손", lambda p: p.replace(">10.59배<", ">1.59배<",
                                                1)),
    ("천장 표기 훼손", lambda p: p.replace(">$214<", ">$414<", 1)),
    ("스페이스X 요구 NOPAT 표기 훼손", lambda p: p.replace(">146.9십억<",
                                                   ">46.9십억<", 1)),
    ("스페이스X 사업부 영업이익 표기 훼손",
     lambda p: p.replace('<td class="r pos">2.4</td>',
                         '<td class="r pos">3.4</td>', 1)),
    ("결론 문장 제거", lambda p: p.replace("낙관 시나리오에서만", "모든 경우에")),
    ("타이틀 제거", lambda p: re.sub(r"<title>.*?</title>", "", p)),
    ("타이틀을 설명문으로", lambda p: re.sub(
        r"<title>.*?</title>",
        "<title>네 기업의 적정주가 판정에 관한 종합 보고서</title>", p)),
    ("keep-all 제거", lambda p: p.replace("word-break:keep-all", "")),
    ("거터 제거", lambda p: p.replace(
        "max(16px,env(safe-area-inset-left,0px))", "16px")),
    ("다크 가드 제거", lambda p: p.replace(':root:not([data-theme="light"])',
                                      ":root")),
    ("viewport-fit 제거", lambda p: p.replace("claude:viewport-fit-sides",
                                           "x")),
    ("body 배경 제거", lambda p: p.replace("background:var(--bg)", "")),
    ("doctype 추가", lambda p: "<!doctype html>" + p),
    ("허용 안 된 호스트 추가", lambda p: p.replace(
        "</div>", '<img src="https://evil.example.com/x.png"></div>', 1)),
    ("표를 스크롤 밖으로", lambda p: p.replace('<div class="scroll"><table>',
                                         "<table>", 1)),
    ("풀이① 10년 CAGR 표기 훼손", lambda p: p.replace(">20.9%<", ">30.9%<",
                                                   1)),
    ("풀이① 상한 표기 제거",
     lambda p: p.replace("67.6% → <b>25.0%</b> (상한)", "<b>25.0%</b>", 1)),
    ("풀이② 10년 최저 ROIC 표기 훼손", lambda p: p.replace(">22.2%<", ">32.2%<",
                                                    1)),
    ("풀이③ 5년차 NOPAT 표기 훼손", lambda p: p.replace(">197.0<", ">297.0<",
                                                  1)),
    ("풀이③ 1년차 재투자율 표기 훼손", lambda p: p.replace(">55.2%<", ">45.2%<",
                                                   1)),
    ("풀이③ 할인계수 표기 훼손", lambda p: p.replace(">0.909<", ">0.809<", 1)),
    ("풀이③ 10년 합계 표기 훼손", lambda p: p.replace(">729.5<", ">629.5<", 1)),
    ("풀이③ 주당가치 표기 훼손", lambda p: p.replace("<b>$164.31</b>",
                                              "<b>$194.31</b>", 1)),
    ("풀이③ 터미널 비중 서술 훼손", lambda p: p.replace("61%를 차지합니다",
                                                "41%를 차지합니다", 1)),
    ("풀이① 성장 경로 막대 길이 훼손",
     lambda p: re.sub(r'(<span class="yr">5년차</span>.*?style="width:)[\d.]+',
                      r"\g<1>99.0", p, count=1, flags=re.S)),
    ("풀이① 3단계 카드 하나 제거",
     lambda p: p.replace('<div class="step"><span class="k">3단계</span>',
                         '<div class="stepx"><span class="k">3단계</span>',
                         1)),
    ("맨 :root 에서 의미색 토큰 제거 (다크에만 남김)",
     lambda p: p.replace("--cheap:#0f6b4f; --cheap-bg:#e6f2ec;", "", 1)),
    ("다크 블록의 color-scheme 제거",
     lambda p: p.replace("color-scheme:dark;", "", 1)),
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
                print(f"  ✓ {name}: {len(f2)}건 실패 — {f2[0][:80]}")
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
