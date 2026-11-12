"""
엔비디아 — CEO 사임 당일의 가격을 버핏 기준으로 판정합니다.

2026년 11월 12일, 엔비디아가 8-K(Item 5.02)로 젠슨 황의 사임을 공시했고
주가가 장중 두 자릿수로 빠졌습니다. 두 가지 질문에 답합니다.

1. **지금 가격이 버핏 기준으로 매력적인가.** 기존 격자(성장률 가정 × 할인율)를
   오늘 가격으로 다시 읽고, 거꾸로 **"이 가격이 요구하는 성장률"**을 안전마진
   0·20·30·40%별로 풉니다. 요구 성장률의 상한은 증분 ROIC 입니다 — 그 위는
   재투자율이 100%를 넘어 자기 현금으로 조달할 수 없는 성장입니다.

2. **버핏이라면 CEO 리스크를 얼마나 반영했을까.** 할인율에 프리미엄을 얹는
   방식이 **아닙니다.** 그는 위험을 안전마진으로 처리하고(2007 주주총회),
   경영자 의존은 아예 **선별 기준**으로 씁니다(2007 서한: "if a business
   requires a superstar to produce great results, the business itself cannot
   be deemed great"). 그래서 이 엔진은 CEO 프리미엄을 발명하지 않고,
   **가격을 성장 가정으로 분해**합니다 — 평범한 대형주처럼 성장할 때의 가치와,
   그 위에 얹힌 "예외적 기록이 계속된다"는 값. CEO 사임이 흔드는 것은 뒤쪽입니다.

입력은 전부 기존 엔진과 1차 자료입니다. fv/fair_value.json(재무·주식수·
순현금·10년 기록), fv/buffett_standard.json(거시·기초율·버핏 인용·격자),
EDGAR(8-K 원문, 10-K 위험요인·고객집중), Yahoo(시세), 그리고 버크셔 주주서한
원문(인용문은 받은 원문과 대조해 맞지 않으면 멈춥니다).

    python3 analyse_nvda_ceo.py
    python3 analyse_nvda_ceo.py --refresh
"""

import argparse
import html as _html
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import sec_cache                                             # noqa: E402
from analyse_buffett_standard import dcf, percentile_of      # noqa: E402

FV = os.path.join(HERE, "fv", "fair_value.json")
BS = os.path.join(HERE, "fv", "buffett_standard.json")
OUT = os.path.join(HERE, "fv", "nvda_ceo.json")
CACHE = os.path.join(HERE, "fv", "nvda_cache")

CIK = "0001045810"
TICKER = "NVDA"
MM, BN = 1e6, 1e9
YEARS = 10
MARGINS = [0.0, 0.20, 0.30, 0.40]

# 요구 성장률을 풀 때의 감쇠 모양. 격자의 네 가정은 감쇠 목표가 제각각이라
# 그대로 쓰면 "요구 성장률"이 어느 모양의 것인지 알 수 없습니다. 본문 중립
# 시나리오와 같은 3.5%로 고정하고, 10년 평균 CAGR 을 함께 보고합니다 —
# 1년차 성장률만 적으면 가정이 실제보다 공격적으로 보입니다.
SOLVE_FADE_TO = 0.035

UA_WEB = "Mozilla/5.0 (compatible; portfolio-research/1.0)"
CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/"
         "{t}?range={r}&interval=1d")

# 버크셔 주주서한에서 직접 읽은 문장. **원문과 대조해 통과해야 씁니다** —
# 기억에서 적은 인용문은 한 단어가 바뀌어도 뜻이 달라지고, 이 보고서의
# 논증은 전부 이 문장들 위에 서 있습니다.
LETTERS = {
    1987: "https://www.berkshirehathaway.com/letters/1987.html",
    1989: "https://www.berkshirehathaway.com/letters/1989.html",
    1991: "https://www.berkshirehathaway.com/letters/1991.html",
    2007: "https://www.berkshirehathaway.com/letters/2007ltr.pdf",
}
PASSAGES = [
    {"key": "franchise", "year": 1991, "kind": "1차 (주주서한)",
     "title": "프랜차이즈는 경영 부실을 견디고, 사업은 견디지 못한다",
     "quote": ("An economic franchise arises from a product or service that: "
               "(1) is needed or desired; (2) is thought by its customers to "
               "have no close substitute and; (3) is not subject to price "
               "regulation."),
     "quote2": ("Moreover, franchises can tolerate mis-management. Inept "
                "managers may diminish a franchise's profitability, but they "
                "cannot inflict mortal damage."),
     "quote3": "And a business, unlike a franchise, can be killed by poor "
               "management.",
     "why": ("CEO 리스크의 크기는 CEO 가 아니라 **사업의 종류**가 정합니다. "
             "프랜차이즈면 경영 부실을 견디고, 그냥 사업이면 죽을 수도 "
             "있습니다. 그래서 첫 질문은 '후임이 누구냐'가 아니라 '엔비디아는 "
             "어느 쪽이냐'입니다.")},
    {"key": "superstar", "year": 2007, "kind": "1차 (주주서한)",
     "title": "슈퍼스타가 필요한 사업은 위대한 사업이 아니다",
     "quote": ("Additionally, this criterion eliminates the business whose "
               "success depends on having a great manager."),
     "quote2": ("But if a business requires a superstar to produce great "
                "results, the business itself cannot be deemed great."),
     "quote3": "The partnership's moat will go when the surgeon goes.",
     "why": ("버핏은 CEO 리스크를 **할인율에 얹지 않습니다.** 선별 기준으로 "
             "씁니다 — 한 사람에게 달린 사업은 애초에 사지 않습니다. 그래서 "
             "'얼마를 더 할인할까'는 버핏의 질문이 아니고, '이 해자가 사람의 "
             "것이었나 사업의 것이었나'가 버핏의 질문입니다.")},
    {"key": "change", "year": 2007, "kind": "1차 (주주서한)",
     "title": "빠르게 변하는 산업은 '지속되는 해자'에서 탈락한다",
     "quote": ("Our criterion of “enduring” causes us to rule out "
               "companies in industries prone to rapid and continuous "
               "change."),
     "quote2": "A moat that must be continuously rebuilt will eventually be "
               "no moat at all.",
     "quote3": ("Long-term competitive advantage in a stable industry is what "
                "we seek in a business."),
     "why": ("이 조건은 CEO 와 무관하게 적용됩니다. 가속컴퓨팅은 2년마다 "
             "아키텍처를 갈아 끼우는 산업이고, 해자를 계속 다시 쌓아야 하는 "
             "쪽입니다. 사임이 없었어도 이 기준에서는 통과하기 어렵습니다.")},
    {"key": "jockey", "year": 1989, "kind": "1차 (주주서한)",
     "title": "좋은 기수도 나쁜 말로는 이기지 못한다",
     "quote": ("Good jockeys will do well on good horses, but not on "
               "broken-down nags."),
     "quote2": ("I've said many times that when a management with a "
                "reputation for brilliance tackles a business with a "
                "reputation for bad economics, it is the reputation of the "
                "business that remains intact."),
     "quote3": None,
     "why": ("반대 방향으로도 읽어야 합니다. 경영자가 사업의 경제성을 "
             "이기지 못한다면, 경영자가 바뀌었다고 사업의 경제성이 사라지는 "
             "것도 아닙니다. CUDA 소프트웨어 자산과 설치 기반은 사람과 함께 "
             "걸어 나가지 않습니다.")},
    {"key": "severe_change", "year": 1987, "kind": "1차 (주주서한)",
     "title": "급격한 변화와 예외적 수익률은 잘 섞이지 않는다",
     "quote": "Severe change and exceptional returns usually don't mix.",
     "quote2": ("Experience, however, indicates that the best business "
                "returns are usually achieved by companies that are doing "
                "something quite similar today to what they were doing five "
                "or ten years ago."),
     "quote3": None,
     "why": ("오늘의 사건은 '급격한 변화' 그 자체입니다. 경영진 교체, 임시 "
             "CEO 가 CFO 를 겸임, 후임 미정 — 버핏의 표현을 빌리면 예외적 "
             "수익률을 기대하기 좋은 환경이 아닙니다.")},
]


# ------------------------------------------------------------------ 시세
def price_path(refresh, rng="6mo"):
    """
    6개월 일별 종가와 **지금 장이 열려 있는지**.

    장중이면 마지막 일봉은 미완성입니다. 그걸 '종가'라고 적는 것은 하필
    주가가 크게 움직이는 날 틀리는 방식이라, 세션 상태를 값과 함께
    들고 다닙니다.
    """
    url = CHART.format(t=TICKER, r=rng)
    raw = subprocess.run(["curl", "-sS", "--fail", "-A", UA_WEB, url],
                         capture_output=True, check=True).stdout
    res = json.loads(raw)["chart"]["result"][0]
    meta, q = res["meta"], res["indicators"]["quote"][0]
    rows = []
    for ts, o, h, l, c, v in zip(res["timestamp"], q["open"], q["high"],
                                 q["low"], q["close"], q["volume"]):
        if c is None:
            continue
        rows.append({
            "date": datetime.fromtimestamp(ts, tz=timezone.utc)
            .date().isoformat(),
            "open": o, "high": h, "low": l, "close": c, "volume": v})
    if len(rows) < 20:
        raise SystemExit(f"시세 행이 {len(rows)}개뿐입니다 — 받기 실패")
    reg = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    mkt_ts = meta.get("regularMarketTime")
    intraday = bool(mkt_ts and reg.get("start") and reg.get("end")
                    and reg["start"] <= mkt_ts < reg["end"])
    last, prev = rows[-1], rows[-2]
    high = max(rows, key=lambda r: r["high"])
    return {
        "rows": rows,
        "last": last, "previous": prev,
        "is_intraday": intraday,
        "as_of_utc": datetime.fromtimestamp(mkt_ts, tz=timezone.utc)
        .isoformat() if mkt_ts else None,
        "price": last["close"],
        "change_today": last["close"] / prev["close"] - 1,
        "change_today_at_low": last["low"] / prev["close"] - 1,
        "change_today_at_open": last["open"] / prev["close"] - 1,
        "window_high": high, "window_days": len(rows),
        "fifty_two_week_high": meta.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": meta.get("fiftyTwoWeekLow"),
        "source_url": url,
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
    }


def decompose(path):
    """
    하락을 '사건 전'과 '사건 당일'로 나눕니다.

    오늘 하루만 보면 CEO 사임이 하락의 원인처럼 읽히는데, 주가는 그 전부터
    빠지고 있었습니다. 둘을 나눠 적지 않으면 사건의 크기를 과장하게 됩니다.
    """
    hi = path["window_high"]
    prev, last = path["previous"], path["last"]
    return {
        "window_high": {"date": hi["date"], "price": hi["high"]},
        "pre_event_close": {"date": prev["date"], "price": prev["close"]},
        "now": {"date": last["date"], "price": last["close"]},
        "before_event": prev["close"] / hi["high"] - 1,
        "on_event": last["close"] / prev["close"] - 1,
        "total_from_high": last["close"] / hi["high"] - 1,
        "fifty_two_week_high": path["fifty_two_week_high"],
        "from_52w_high": last["close"] / path["fifty_two_week_high"] - 1,
    }


# ------------------------------------------------------------------ 공시
def event_8k(refresh):
    """
    사임을 공시한 8-K. **최신 8-K 를 그대로 집지 않습니다** — Item 5.02 가
    붙은 것을 고릅니다(알파벳에서 최신 8-K 가 실적 발표문이 아니어서
    파이프라인이 죽은 적이 있습니다).
    """
    sub, _, age = sec_cache.submissions(CIK, CACHE, refresh=refresh,
                                        max_age_days=0.04)
    r = sub["filings"]["recent"]
    rows = list(zip(r["form"], r["filingDate"],
                    r.get("reportDate", [""] * len(r["form"])),
                    r["accessionNumber"],
                    r.get("items", [""] * len(r["form"]))))
    hit = next((x for x in rows
                if x[0] == "8-K" and "5.02" in (x[4] or "")), None)
    if hit is None:
        raise SystemExit("최근 제출물에서 Item 5.02 가 붙은 8-K 를 찾지 "
                         "못했습니다")
    form, filed, report_date, acc, items = hit
    base = (f"https://www.sec.gov/Archives/edgar/data/{int(CIK)}/"
            f"{acc.replace('-', '')}")
    idx, _, _ = sec_cache.fetch_json(
        base + "/index.json", os.path.join(CACHE, f"{acc}_index.json"),
        max_age_days=365, refresh=refresh)
    names = [i["name"] for i in idx["directory"]["item"]]
    body = next((n for n in names
                 if re.fullmatch(r"nvda-\d{8}\.htm", n)), None)
    press = next((n for n in names if n.endswith(".htm")
                  and n != body and not n.startswith("R")
                  and "index" not in n), None)
    if not body:
        raise SystemExit(f"8-K {acc} 본문을 찾지 못했습니다: {names}")

    def text_of(name):
        p, _, _ = sec_cache.fetch(f"{base}/{name}",
                                  os.path.join(CACHE, f"{acc}_{name}"),
                                  max_age_days=365, refresh=refresh,
                                  min_bytes=2000)
        raw = open(p, errors="ignore").read()
        return re.sub(r"\s+", " ",
                      _html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()

    btxt = text_of(body)
    ptxt = text_of(press) if press else ""

    ABBREV = {"Mr", "Ms", "Mrs", "Dr", "Inc", "Corp", "Co", "Ltd", "No",
              "Jr", "Sr", "St", "Nos", "Sec", "vs"}

    def _boundary(txt, dot):
        """그 마침표가 문장 끝인가.

        ". " 를 그대로 문장 경계로 쓰면 이름의 가운데 이니셜에서 끊깁니다 —
        "Colette M. Kress" 가 "Kress, age 59, …" 로 잘려 앵커가 어긋났습니다.
        한 글자 대문자와 약어 뒤의 마침표는 경계가 아닙니다.
        """
        k = dot
        while k > 0 and (txt[k - 1].isalnum() or txt[k - 1] == "."):
            k -= 1
        tok = txt[k:dot].strip(".")
        if len(tok) == 1 and tok.isupper():
            return False
        return tok not in ABBREV

    def sentence(txt, needle):
        """그 문구가 들어 있는 문장 하나. 없으면 멈춥니다."""
        i = txt.find(needle)
        if i < 0:
            raise SystemExit(f"8-K 에서 찾지 못한 문구: {needle!r}")
        dots = [m.start() for m in re.finditer(r"\. ", txt)
                if _boundary(txt, m.start())]
        a = max([x for x in dots if x < i], default=None)
        b = min([x for x in dots if x >= i], default=None)
        return txt[(a + 2) if a is not None else 0:
                   (b + 1) if b is not None else len(txt)].strip()

    # 사유가 적혀 있는지. Item 5.02 는 사임 사유의 기재를 강제하지 않습니다.
    reason_markers = ("due to", "as a result of", "because of",
                      "disagreement", "for personal reasons", "retire")
    reason_in_filing = [m for m in reason_markers if m in btxt.lower()]

    return {
        "accession": acc, "form": form, "filed": filed,
        "report_date": report_date, "items": items,
        "url": f"{base}/{body}",
        "press_release_url": f"{base}/{press}" if press else None,
        "resignation": sentence(btxt, "accepted the resignation"),
        "interim": sentence(btxt, "interim Chief Executive Officer"),
        "chair": sentence(btxt, "as Chair of the Board"),
        "search": sentence(ptxt or btxt, "search for a permanent"),
        "earnings": sentence(ptxt, "will report its third-quarter")
        if ptxt else None,
        "reason_stated_in_filing": bool(reason_in_filing),
        "reason_markers_found": reason_in_filing,
        "submissions_age_days": age,
    }


def filing_facts(refresh):
    """10-K 에서 손으로 읽은 세 가지: 창업자 재임기간, 핵심인력 위험요인,
    고객 집중도. 전부 CEO 리스크를 재는 데 직접 쓰입니다."""
    sub, _, _ = sec_cache.submissions(CIK, CACHE, refresh=False,
                                      max_age_days=1.0)
    r = sub["filings"]["recent"]
    rows = list(zip(r["form"], r["filingDate"], r["accessionNumber"],
                    r.get("primaryDocument", [""] * len(r["form"]))))
    form, filed, acc, doc = next(x for x in rows if x[0] == "10-K")
    url = (f"https://www.sec.gov/Archives/edgar/data/{int(CIK)}/"
           f"{acc.replace('-', '')}/{doc}")
    p, _, _ = sec_cache.fetch(url, os.path.join(CACHE, f"{acc}_10k.htm"),
                              max_age_days=365, refresh=refresh,
                              min_bytes=100000)
    txt = re.sub(r"\s+", " ", _html.unescape(
        re.sub(r"<[^>]+>", " ", open(p, errors="ignore").read())))

    def must(needle):
        if needle not in txt:
            raise SystemExit(f"10-K 에서 찾지 못한 문구: {needle!r}")
        return needle

    founder = must("Jen-Hsun Huang co-founded NVIDIA in 1993 and has served "
                   "as our President, Chief Executive Officer, and a member "
                   "of the Board of Directors since our inception.")
    key_people = must("We may be unable to attract, retain, and motivate our "
                      "executives and key employees.")
    conc = must("For fiscal year 2026, sales to one direct customer "
                "represented 22% of total revenue and sales to another "
                "direct customer represented 14% of total revenue")
    # 숫자는 문장에서 다시 뽑습니다 — 손으로 옮겨 적으면 그때부터 원문과
    # 따로 놉니다.
    pcts = [int(x) / 100 for x in re.findall(r"(\d+)% of total revenue",
                                             conc)]
    return {
        "form": form, "filed": filed, "accession": acc, "url": url,
        "founder_tenure": founder,
        "founder_since": 1993,
        "key_personnel_risk_factor": key_people,
        "customer_concentration_sentence": conc,
        "customer_concentration": pcts,
        "customer_concentration_top2": sum(pcts[:2]),
    }


def buffett_passages(refresh):
    """주주서한 원문을 받아 인용문을 **대조**합니다. 한 글자라도 다르면
    멈춥니다 — 앞 60자만 맞춰 보면 뒷부분을 바꿔도 통과합니다."""
    texts = {}
    for year, url in LETTERS.items():
        name = f"brk_{year}" + (".pdf" if url.endswith(".pdf") else ".html")
        p, _, _ = sec_cache.fetch(url, os.path.join(CACHE, name),
                                  max_age_days=365, refresh=refresh,
                                  min_bytes=20000,
                                  binary=url.endswith(".pdf"))
        if url.endswith(".pdf"):
            txt = subprocess.run(["pdftotext", "-layout", p, "-"],
                                 capture_output=True, check=True,
                                 text=True).stdout
        else:
            txt = _html.unescape(re.sub(r"<[^>]+>", " ",
                                        open(p, errors="ignore").read()))
        # 서한은 줄바꿈과 하이픈으로 단어를 자릅니다. 공백을 눌러 비교하고,
        # 따옴표는 곧은 것으로 통일합니다.
        txt = (txt.replace("“", "\"").replace("”", "\"")
               .replace("’", "'").replace("‘", "'")
               .replace("–", "-").replace("—", "-"))
        texts[year] = re.sub(r"\s+", " ", txt)

    out = []
    for p_ in PASSAGES:
        src = texts[p_["year"]]
        checked = []
        for k in ("quote", "quote2", "quote3"):
            q = p_.get(k)
            if not q:
                continue
            probe = (q.replace("“", "\"").replace("”", "\"")
                     .replace("’", "'"))
            # 서한 본문은 줄 끝에서 단어를 하이픈으로 자릅니다("low- cost").
            # 공백을 느슨하게 보되 **문장 전체**를 대조합니다.
            pattern = re.escape(probe).replace(r"\ ", r"[\s-]*")
            if not re.search(pattern, src):
                raise SystemExit(
                    f"{p_['year']} 서한에서 인용문을 찾지 못했습니다 — "
                    f"원문과 다릅니다: {q[:70]}…")
            checked.append(k)
        out.append({**p_, "source_url": LETTERS[p_["year"]],
                    "verified_against_source": checked})
    return out


# ------------------------------------------------------------------ 계산
def required_growth(nopat, net_cash, shares, inc_roic, discount,
                    target_per_share, fade_to=SOLVE_FADE_TO):
    """
    목표 주당가치를 만드는 1년차 성장률.

    탐색 상한은 **증분 ROIC** 입니다. 그 위는 재투자율이 100%를 넘어 자기
    현금으로 조달할 수 없는 성장이고, 모형에 외부자금이 없으므로 답이
    아닙니다(상한을 멋대로 높게 잡았다가 '증분 ROIC 25%인데 정당화 성장률
    32%' 같은 모순이 나온 적이 있습니다).
    """
    def value(g):
        r = dcf(nopat, net_cash, shares, g, fade_to, inc_roic, discount,
                terminal_growth=0.0224, years=YEARS)
        return None if r["diverges"] else r

    lo, hi = -0.50, inc_roic * 0.9995
    v_hi = value(hi)
    if v_hi is None:
        return None
    if v_hi["value_per_share"] < target_per_share:
        return {"reachable": False,
                "ceiling_per_share": v_hi["value_per_share"],
                "ceiling_growth": hi}
    v_lo = value(lo)
    if v_lo and v_lo["value_per_share"] > target_per_share:
        return {"reachable": True, "growth": lo, "below_range": True,
                "value_per_share": v_lo["value_per_share"],
                "nopat_cagr_10y": v_lo["nopat_cagr_10y"],
                "terminal_share": v_lo["terminal_share"]}
    for _ in range(200):
        mid = (lo + hi) / 2
        v = value(mid)
        if v is None or v["value_per_share"] < target_per_share:
            lo = mid
        else:
            hi = mid
    v = value(hi)
    return {"reachable": True, "growth": hi, "below_range": False,
            "value_per_share": v["value_per_share"],
            "nopat_cagr_10y": v["nopat_cagr_10y"],
            "terminal_share": v["terminal_share"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)
    today = date.today().isoformat()
    print(f"오늘 {today} 기준")

    fv = json.load(open(FV, encoding="utf-8"))
    bs = json.load(open(BS, encoding="utf-8"))
    co_fv = next(c for c in fv["companies"] if c["ticker"] == TICKER)
    co_bs = next(c for c in bs["companies"] if c["ticker"] == TICKER)

    # ---------------------------------------------------------- 1. 사건
    ev = event_8k(a.refresh)
    print(f"  8-K {ev['filed']} {ev['accession']} items={ev['items']}")
    print(f"    {ev['resignation'][:96]}…")
    print(f"    사유 기재: {'있음' if ev['reason_stated_in_filing'] else '없음'}")
    ff = filing_facts(a.refresh)
    print(f"  10-K {ff['filed']} 고객집중 상위2 "
          f"{ff['customer_concentration_top2']:.0%}")

    # ---------------------------------------------------------- 2. 가격
    path = price_path(a.refresh)
    dec = decompose(path)
    px = path["price"]
    print(f"  주가 {px:,.2f} ({path['as_of_utc']}, "
          f"{'장중' if path['is_intraday'] else '종가'}) "
          f"· 전일 대비 {path['change_today']:+.1%} "
          f"· 시초 {path['change_today_at_open']:+.1%} "
          f"· 저가 {path['change_today_at_low']:+.1%}")
    print(f"  사건 전까지 {dec['before_event']:+.1%}, "
          f"당일 {dec['on_event']:+.1%}, 고점 대비 합계 "
          f"{dec['total_from_high']:+.1%}")

    # -------------------------------------------------- 3. 가격 기준 재계산
    # 기존 격자는 엔진이 받은 가격으로 계산돼 있습니다. 오늘 장중가로
    # 판정만 다시 합니다 — 가치(분자)는 가격과 무관하므로 그대로입니다.
    nopat = co_bs["ttm_nopat"]
    net_cash = co_bs["net_cash"]
    shares = co_bs["shares_outstanding"]
    inc_roic = co_bs["incremental_roic_used"]
    infl = bs["macro"]["breakeven_inflation_10y"]["rate"]
    discounts = {d["key"]: d for d in bs["discount_options"]}

    grid = []
    for row in co_bs["grid"]:
        cells = []
        for c in row["cells"]:
            if c.get("diverges"):
                cells.append({**c})
                continue
            v = c["value_per_share"]
            cells.append({
                **c,
                "upside_vs_price": v / px - 1,
                "price_to_value": px / v,
                "verdicts": {
                    f"{int(m * 100)}%": {
                        "buy_limit": v * (1 - m),
                        "pass": v * (1 - m) > px,
                        "gap": v * (1 - m) / px - 1,
                    } for m in MARGINS},
            })
        grid.append({**row, "cells": cells})

    # ------------------------------------------- 4. 이 가격이 요구하는 성장률
    required = []
    for key in ("bond30", "bond30_plus3", "project10", "project11"):
        d_ = discounts[key]
        for m in MARGINS:
            target = px / (1 - m)
            got = required_growth(nopat, net_cash, shares, inc_roic,
                                  d_["rate"], target)
            rec = {"discount_key": key, "discount": d_["rate"],
                   "discount_label": d_["label"],
                   "margin_of_safety": m, "target_per_share": target}
            if got is None:
                rec.update({"reachable": False, "why": "발산"})
            elif not got["reachable"]:
                rec.update({"reachable": False,
                            "ceiling_per_share": got["ceiling_per_share"],
                            "why": ("증분 ROIC 까지 성장률을 올려도 닿지 "
                                    "못합니다 — 자기 현금으로 조달 가능한 "
                                    "어떤 성장률도 이 가격을 설명하지 "
                                    "못한다는 뜻입니다.")})
            else:
                g10 = got["nopat_cagr_10y"]
                rec.update({
                    "reachable": True,
                    "growth_year1": got["growth"],
                    "nopat_cagr_10y": g10,
                    "nopat_cagr_10y_real": g10 - infl,
                    "base_rate_percentile_at_or_above": percentile_of(
                        bs["base_rates"]["net_income_10y"]["bands"],
                        g10 - infl),
                    "vs_own_cagr": got["growth"] / co_bs["own_cagr_nominal"],
                    "terminal_share": got["terminal_share"],
                    "value_per_share": got["value_per_share"]})
            required.append(rec)
    for r_ in required:
        if r_["margin_of_safety"] != 0.30:
            continue
        if r_["reachable"]:
            print(f"  안전마진 30% · {r_['discount_label']}: 1년차 "
                  f"{r_['growth_year1']:.1%} (10년 CAGR "
                  f"{r_['nopat_cagr_10y']:.1%}, 기초율 상위 "
                  f"{r_['base_rate_percentile_at_or_above']:.1%})")
        else:
            print(f"  안전마진 30% · {r_['discount_label']}: 도달 불가")

    # ------------------------------------------ 5. 가격을 성장 가정으로 분해
    # "평범한 대형주처럼 성장할 때의 가치"와 그 위에 얹힌 부분. 뒤쪽이 바로
    # CEO 사임이 흔드는 값입니다. 버핏 기준 할인율(국채+3%p)에서 봅니다.
    base_row = next(r for r in grid if r["growth_key"] == "base_rate_median")
    base_cell = next(c for c in base_row["cells"]
                     if c["discount_key"] == "bond30_plus3")
    keep_row = next(r for r in grid if r["growth_key"] == "own_sustained")
    keep_cell = next(c for c in keep_row["cells"]
                     if c["discount_key"] == "bond30_plus3")
    ordinary = base_cell["value_per_share"]
    split = {
        "discount_key": "bond30_plus3",
        "discount": discounts["bond30_plus3"]["rate"],
        "price": px,
        "ordinary_company_value": ordinary,
        "ordinary_growth_label": base_row["growth_label"],
        "premium_in_price": px - ordinary,
        "premium_share_of_price": (px - ordinary) / px,
        "exceptional_value": keep_cell["value_per_share"],
        "exceptional_growth_label": keep_row["growth_label"],
        "price_position": ((px - ordinary)
                           / (keep_cell["value_per_share"] - ordinary)),
    }
    print(f"  가격 분해: 평범한 대형주 가치 ${ordinary:,.0f} + 예외성 프리미엄 "
          f"${px - ordinary:,.0f} (가격의 {split['premium_share_of_price']:.0%})")

    # ------------------------------------------------- 6. 프랜차이즈 검정
    ys = sorted(co_fv["record"]["years"], key=lambda y: y["fiscal_year"])
    franchise = {
        "roic_years": ys,
        "roic_median": co_fv["record"]["summary"]["roic_median"],
        "roic_latest": ys[-1]["roic"],
        "roic_peak": max(ys, key=lambda y: y["roic"]),
        "operating_income_cagr": co_bs["own_cagr_nominal"],
        "revenue_cagr": co_bs["own_revenue_cagr_nominal"],
        "invested_capital_cagr": co_fv["record"]["invested_capital_cagr"],
        "trend": co_fv["record"]["trend"],
        "customer_concentration_top2": ff["customer_concentration_top2"],
        "founder_years": 2026 - ff["founder_since"],
        "tests": [
            {"criterion": "(1) 필요하거나 원하는 제품인가",
             "verdict": "충족",
             "evidence": (f"10년 매출 CAGR {co_bs['own_revenue_cagr_nominal']:.1%}, "
                          f"FY2026 매출 "
                          f"{co_fv['record']['years'][-1]['revenue'] / BN:,.0f}십억 "
                          f"달러.")},
            {"criterion": "(2) 가까운 대체재가 없다고 고객이 여기는가",
             "verdict": "다툼 있음",
             "evidence": ("CUDA 와 설치 기반은 전환비용이지만, 상위 두 고객이 "
                          f"매출의 {ff['customer_concentration_top2']:.0%}이고 "
                          "그들이 자체 가속기를 만들고 있습니다. 10-K 자신이 "
                          "고객 집중을 위험요인으로 적습니다.")},
            {"criterion": "(3) 가격 규제를 받지 않는가",
             "verdict": "부분 미충족",
             "evidence": ("가격 규제는 아니지만 수출 규제가 '팔 수 있는 "
                          "상대'를 정합니다 — 10-K 위험요인에 명시돼 "
                          "있습니다.")},
            {"criterion": "경영 부실을 견디는가 (버핏의 추가 조건)",
             "verdict": "미검증",
             "evidence": (f"창업자가 {2026 - ff['founder_since']}년 내내 "
                          "CEO 였으므로, 이 회사가 다른 경영진 아래에서 어떤 "
                          "성과를 냈는지에 대한 **관측치가 0개**입니다. "
                          "모른다는 것이 결론입니다.")},
        ],
    }

    out = {
        "generated": today,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "ticker": TICKER, "korean": co_fv["korean"],
        "company_name": co_fv["company_name"],
        "question": ("CEO 사임 당일의 가격이 버핏 기준으로 매력적인가, "
                     "그리고 버핏이라면 CEO 리스크를 어떻게 반영했을까."),
        "event": ev,
        "filing_facts": ff,
        "price": {**{k: v for k, v in path.items() if k != "rows"},
                  "rows": path["rows"][-30:]},
        "price_decomposition": dec,
        "fundamentals": {
            "data_as_of": co_fv["data_as_of"],
            "ttm_nopat": nopat, "ttm_revenue": co_bs["ttm_revenue"],
            "net_cash": net_cash, "shares_outstanding": shares,
            "market_cap": px * shares,
            "incremental_roic_used": inc_roic,
            "incremental_roic_basis": co_bs["incremental_roic_basis"],
            "next_earnings_note": ev.get("earnings"),
        },
        "macro": bs["macro"],
        "discount_options": bs["discount_options"],
        "margins_of_safety": MARGINS,
        "solve_fade_to": SOLVE_FADE_TO,
        "grid": grid,
        "required_growth": required,
        "price_split": split,
        "franchise": franchise,
        "buffett": buffett_passages(a.refresh),
        "base_rates": bs["base_rates"],
        "scenario_valuations": [
            {"scenario": v["scenario"],
             "value_per_share": v["value_per_share"],
             "assumptions": v["assumptions"],
             "upside_vs_price": v["value_per_share"] / px - 1,
             "implied_growth_at_price": v["implied_growth_at_price"]}
            for v in co_fv["valuations"]],
        "sources": {
            "fair_value_generated": fv["generated"],
            "buffett_standard_generated": bs["generated"],
            "eight_k": ev["url"], "ten_k": ff["url"],
            "price": path["source_url"],
        },
        "limits": [
            ("**장중 가격입니다.** 장이 열려 있는 동안의 값이라 이 보고서를 "
             "읽는 시점과 다릅니다. 판정은 가격에 직접 달려 있으므로 종가로 "
             "다시 돌려 보십시오."
             if path["is_intraday"] else
             "**가격은 이 날의 종가입니다.** 장중에는 시초 "
             f"{path['change_today_at_open']:+.1%}, 저가 "
             f"{path['change_today_at_low']:+.1%}까지 갔다가 "
             f"{path['change_today']:+.1%}로 마쳤습니다 — 어느 시점의 "
             "가격을 쓰느냐가 판정을 바꿉니다. 판정은 가격에 직접 달려 "
             "있으므로 다음 거래일에 다시 돌려 보십시오."),
            ("**사임 사유가 공시에 없습니다.** 8-K 는 사임 사실만 적습니다. "
             "사유에 따라 이 사건이 '승계 문제'인지 '회사에 번지는 문제'인지가 "
             "갈리는데, 지금은 알 수 없습니다. 모른다는 사실 자체를 가격에 "
             "반영해야 합니다."),
            ("**5일 뒤 실적이 나옵니다.** 3분기(FY2027) 실적 발표가 예정대로 "
             "11월 17일입니다. 영업 데이터로 사건을 확인하기 전의 판정입니다."),
            ("**TTM 은 2026-07-26 까지입니다.** 분기가 하나 비어 있고, 그 "
             "분기는 5일 뒤에 채워집니다."),
            ("**증분 ROIC 은 격자 전체에 같은 값(35%)을 씁니다.** 성장률과 "
             "할인율의 효과만 분리하기 위해서입니다. 실제 증분 수익률이 "
             "떨어지면 모든 칸이 함께 내려갑니다."),
            ("**CEO 리스크를 숫자 하나로 환산하지 않았습니다.** 버핏이 그렇게 "
             "하지 않기 때문입니다. 대신 '가격이 요구하는 성장률'과 '그 성장이 "
             "없을 때의 가치'를 나란히 둡니다."),
        ],
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(f"\nwrote {OUT} "
          f"({os.path.getsize(OUT) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
