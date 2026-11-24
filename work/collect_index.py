"""
S&P 500 과 나스닥100 지수의 30년 자료를 모읍니다.

지수에는 SEC 공시가 없습니다. 그래서 출처를 나눠 쓰고, 가능한 곳마다 **두
출처를 서로 대조**합니다.

S&P 500
  - 주당이익(EPS, 12개월 누적, 보고 기준)·P/E·주당장부가치: multpl.com 의
    월별·분기별 표. multpl 이 S&P 다우존스지수의 공표치를 옮긴 것입니다.
    S&P 원본 스프레드시트는 이 환경에서 403 으로 막힙니다.
  - 같은 EPS 의 독립 사본: 로버트 실러의 ie_data.xls (1871~2024-06). 겹치는
    기간에 두 사본이 맞는지로 multpl 의 전사를 검증합니다.
  - 가격: Yahoo ^GSPC 월말 종가(1989~)와 최근 일봉.

나스닥100
  - 지수 단위 이익은 무료로 공표되지 않습니다(나스닥의 분기 실적 노트는
    성장률만 싣습니다). 그래서 **구성종목 101개의 이익을 SEC 공시에서 직접
    모아** 지수의 이익수익률을 만듭니다.
        지수 P/E = Σ 시가총액 / Σ 12개월 순이익
    시가총액 가중 지수에서 이것은 근사가 아니라 정의입니다(가중 조화평균과
    같습니다). 나스닥100 은 상위 종목의 비중을 깎는 수정 시가총액
    가중이라 그만큼 다를 수 있고, 그 차이는 보고서에 적습니다.
  - 구성종목 명단: 나스닥 지수 사이트(indexes.nasdaqomx.com). 비중은
    구독 자료라 공개되지 않으므로 시가총액으로 계산합니다.
  - 교차확인: iShares 가 공표하는 같은 지수 추종 펀드의 P/E(CNDX). 계산
    방식이 달라(펀드 P/E 는 보유종목 P/E 의 가중평균) 일치를 기대하지는
    않지만, 크게 어긋나면 집계가 틀린 것입니다.
  - 가격: Yahoo ^NDX.

거시: 30년·10년 국채(Yahoo ^TYX/^TNX). 기대인플레이션은 FRED T10YIE 인데
FRED 가 이 환경에서 접속되지 않아, 앞선 엔진이 FRED 페이지에서 읽어 둔 값을
출처 날짜와 함께 그대로 씁니다.

    python3 collect_index.py
    python3 collect_index.py --refresh
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

OUT_DIR = os.path.join(HERE, "idx")
CACHE = os.path.join(OUT_DIR, "cache")
OUT = os.path.join(OUT_DIR, "index_raw.json")
BS = os.path.join(HERE, "fv", "buffett_standard.json")
UA_WEB = sec_cache.UA_WEB
BN = 1e9

MULTPL = "https://www.multpl.com/{slug}/table/{by}"
SHILLER = ("https://img1.wsimg.com/blobby/go/"
           "e5e77e0b-59d1-44d9-ab25-4763ac982e53/downloads/ie_data.xls")
ISHARES = {
    "SPX": ("https://www.ishares.com/us/products/239726/"
            "ishares-core-sp-500-etf", "IVV"),
    "NDX": ("https://www.ishares.com/uk/individual/en/products/253741/"
            "ishares-nasdaq-100-ucits-etf", "CNDX"),
}
NDX_MEMBERS = "https://indexes.nasdaqomx.com/Index/WeightingData"
TICKERS = "https://www.sec.gov/files/company_tickers.json"

# 순이익 태그. **지배주주 귀속을 먼저** 봅니다 — 지수 EPS 가 지배주주
# 기준이기 때문입니다. 없으면 연결 순이익.
NI_TAGS = {
    "us-gaap": ["NetIncomeLoss", "ProfitLoss",
                "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "ifrs-full": ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
}

# 세후영업이익(NOPAT)용 태그. **이 프로젝트의 기본 분자는 순이익이 아니라
# NOPAT 입니다** — 순이익에는 보유 지분의 평가손익이 섞입니다(알파벳의
# 9개월 기타수익 +$127.5십억). 지수의 이익도 같은 이유로 두 가지를 함께
# 냅니다.
OI_TAGS = {"us-gaap": ["OperatingIncomeLoss"],
           "ifrs-full": ["ProfitLossFromOperatingActivities"]}
PRETAX_TAGS = {
    "us-gaap": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic"],
    "ifrs-full": ["ProfitLossBeforeTax"]}
TAX_TAGS = {"us-gaap": ["IncomeTaxExpenseBenefit"],
            "ifrs-full": ["IncomeTaxExpenseContinuingOperations"]}
STATUTORY = 0.21
# 자기자본 — 지수의 ROE(재투자 수익률)를 만들 때 씁니다.
EQ_TAGS = {"us-gaap": ["StockholdersEquity",
                       "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
           "ifrs-full": ["EquityAttributableToOwnersOfParent", "Equity"]}

# 미국 예탁증서(ADS) 비율. 나스닥에서 거래되는 증권 1주가 보통주 몇 주인가.
# **손으로 적되 원문으로 검증합니다** — 20-F 본문에서 이 문구를 찾지 못하면
# 수집이 멈춥니다. 비율을 틀리면 시가총액이 그 배수만큼 틀립니다.
ADS = {
    "PDD": {"ratio": 4, "phrase": r"each\s+representing\s+four\s+Class\s+A"
                                  r"\s+ordinary\s+shares"},
    "ARM": {"ratio": 1, "phrase": r"each\s+representing\s+one\s+ordinary"
                                  r"\s+share"},
}


# ------------------------------------------------------------------ 시세
def yahoo(symbol, query):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{symbol}?{query}")
    raw = subprocess.run(["curl", "-sS", "--fail", "--max-time", "60",
                          "-A", UA_WEB, url],
                         capture_output=True, check=True).stdout
    return json.loads(raw)["chart"]["result"][0], url


def monthly(symbol):
    """월말 종가. 1989년부터 — 30년 창에 여유를 둡니다."""
    res, url = yahoo(symbol, "period1=600000000&period2=9999999999"
                             "&interval=1mo")
    q = res["indicators"]["quote"][0]
    rows = [{"date": datetime.fromtimestamp(t, tz=timezone.utc)
             .date().isoformat(), "close": c}
            for t, c in zip(res["timestamp"], q["close"]) if c is not None]
    # Yahoo 는 진행 중인 달에 '그 달 1일' 막대와 별도로 최신 거래일 막대를
    # 하나 더 붙여 줄 때가 있습니다(2026-11-01 막대 = 11-20 종가, 2026-11-23
    # 막대 = 11-23 종가). 달마다 마지막 막대 하나만 남깁니다 — 남기지 않으면
    # 같은 달의 종가가 둘이 되고, 무엇을 집느냐가 사전 순서에 달립니다.
    by = {}
    for r in rows:
        by[r["date"][:7]] = {"date": r["date"][:7] + "-01", "close": r["close"],
                             "bar_date": r["date"]}
    rows = [by[m] for m in sorted(by)]
    return {"rows": rows, "source_url": url}


def daily(symbol):
    """
    일봉 종가, 1995년부터. 고점·저점은 월말 종가로 찾으면 낙폭이 작게
    잡힙니다(2020년 S&P 500: 일봉 −33.9%, 월말 −20%). 그래서 순환의
    날짜와 수준은 일봉으로 정하고, 가치선은 그 달의 월별 값을 씁니다.
    """
    res, url = yahoo(symbol, "period1=788918400&period2=9999999999"
                             "&interval=1d")
    q = res["indicators"]["quote"][0]
    rows = [{"date": datetime.fromtimestamp(t, tz=timezone.utc)
             .date().isoformat(), "close": c}
            for t, c in zip(res["timestamp"], q["close"]) if c is not None]
    if len(rows) < 7000:
        raise SystemExit(f"{symbol} 일봉이 {len(rows)}개뿐입니다")
    return {"rows": rows, "source_url": url}


def latest(symbol):
    """
    최근 일봉과 **장이 열려 있는지**. 장중의 마지막 일봉은 미완성이라
    '종가'라고 적으면 틀립니다(엔비디아 사임 당일 시초 −13%, 종가 −4%).
    """
    res, url = yahoo(symbol, "range=1mo&interval=1d")
    meta, q = res["meta"], res["indicators"]["quote"][0]
    rows = [(t, c) for t, c in zip(res["timestamp"], q["close"])
            if c is not None]
    t, c = rows[-1]
    reg = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    mt = meta.get("regularMarketTime")
    return {
        "price": c,
        "date": datetime.fromtimestamp(t, tz=timezone.utc).date()
        .isoformat(),
        "previous_close": rows[-2][1] if len(rows) > 1 else None,
        "is_intraday": bool(mt and reg.get("start") and reg.get("end")
                            and reg["start"] <= mt < reg["end"]),
        "fifty_two_week_high": meta.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": meta.get("fiftyTwoWeekLow"),
        "currency": meta.get("currency"),
        "source_url": url,
    }


def fx_usd(ccy):
    """그 통화 1단위가 몇 달러인가. 위안처럼 'USDCNY' 로만 있는 것은 뒤집습니다."""
    if ccy == "USD":
        return 1.0, None
    for sym, invert in ((f"{ccy}USD%3DX", False), (f"{ccy}%3DX", True)):
        try:
            res, url = yahoo(sym, "range=5d&interval=1d")
        except subprocess.CalledProcessError:
            continue
        closes = [c for c in res["indicators"]["quote"][0]["close"] if c]
        if closes:
            v = closes[-1]
            return (1.0 / v if invert else v), url
    raise SystemExit(f"환율을 받지 못했습니다: {ccy}")


# ---------------------------------------------------------------- S&P 500
def multpl(slug, by, refresh):
    url = MULTPL.format(slug=slug, by=by)
    p, net, age = sec_cache.fetch(url, os.path.join(CACHE, f"{slug}_{by}.html"),
                                  max_age_days=1.0, refresh=refresh,
                                  min_bytes=10000)
    t = open(p, errors="ignore").read()
    m = re.search(r'<table id="datatable">(.*?)</table>', t, re.S)
    if not m:
        raise SystemExit(f"multpl {slug}: 표를 찾지 못했습니다")
    rows = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S):
        tds = [_html.unescape(re.sub(r"<[^>]+>", "", x))
               .replace(" ", "").strip()
               for x in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if len(tds) != 2 or not tds[1]:
            continue
        # 추정치에는 † 같은 표시가 붙습니다("†\n23.55"). 숫자 외의 기호가
        # 하나라도 있으면 확정치가 아니므로 쓰지 않습니다.
        if re.search(r"[^\d.,%\-\s]", tds[1]):
            continue
        rows.append({"date": datetime.strptime(tds[0], "%b %d, %Y").date()
                     .isoformat(),
                     "value": float(tds[1].replace(",", "").rstrip("%"))})
    rows.sort(key=lambda r: r["date"])
    if len(rows) < 100:
        raise SystemExit(f"multpl {slug}: 행이 {len(rows)}개뿐입니다")
    return {"rows": rows, "source_url": url,
            "fetched_age_days": age, "from_network": net}


def shiller(refresh):
    """실러 ie_data.xls 의 Data 시트: 날짜·가격·배당·이익·CPI·10년금리."""
    import xlrd
    p, net, age = sec_cache.fetch(SHILLER, os.path.join(CACHE, "ie_data.xls"),
                                  max_age_days=30.0, refresh=refresh,
                                  min_bytes=500000, binary=True)
    sh = xlrd.open_workbook(p).sheet_by_name("Data")
    head = [str(sh.cell_value(7, c)).strip() for c in range(sh.ncols)]
    want = {"Date": "date", "P": "price", "D": "dividend", "E": "earnings",
            "CPI": "cpi", "Rate GS10": "gs10", "Price": "real_tr_price",
            "CAPE": "cape"}
    # "Price" 라는 머리글은 두 번 나옵니다(실질 가격, 실질 총수익 가격).
    # 실질 총수익 가격은 두 번째입니다 — 위 행의 "Return" 으로 확인합니다.
    col = {}
    for i, h in enumerate(head):
        if h not in want:
            continue
        if h == "Price" and "Return" not in str(sh.cell_value(6, i)):
            continue
        col.setdefault(want[h], i)
    if set(col) != set(want.values()):
        raise SystemExit(f"실러 머리글이 바뀌었습니다: {head}")
    rows = []
    for r in range(8, sh.nrows):
        d = sh.cell_value(r, col["date"])
        if not isinstance(d, float):
            continue
        # 1871.1 은 10월입니다(1871.10). 소수 둘째 자리까지 문자열로 읽어야
        # 1월과 10월이 구분됩니다.
        y, mth = f"{d:.2f}".split(".")
        rec = {"date": f"{y}-{mth}"}
        for k in ("price", "dividend", "earnings", "cpi", "gs10",
                  "real_tr_price", "cape"):
            v = sh.cell_value(r, col[k])
            rec[k] = v if isinstance(v, float) else None
        rows.append(rec)
    return {"rows": rows, "source_url": SHILLER, "fetched_age_days": age,
            "last_with_earnings": max(r["date"] for r in rows
                                      if r["earnings"] is not None)}


def ishares_pe(key, refresh):
    url, fund = ISHARES[key]
    p, _, _ = sec_cache.fetch(url, os.path.join(CACHE, f"ishares_{fund}.html"),
                              max_age_days=1.0, refresh=refresh,
                              min_bytes=100000)
    flat = re.sub(r"\s+", " ", _html.unescape(
        re.sub(r"<[^>]+>", " ", open(p, errors="ignore").read())))
    # 미국 페이지: "P/E Ratio 27.49 as of Nov 19, 2026"
    # 영국 페이지: "P/E Ratio as of 19/Nov/2026 31.10"
    m = (re.search(r"P/E Ratio ([\d.]+) as of ([A-Z][a-z]{2} \d{1,2}, \d{4})",
                   flat)
         or re.search(r"P/E Ratio as of (\d{1,2}/[A-Z][a-z]{2}/\d{4}) "
                      r"([\d.]+)", flat))
    if not m:
        raise SystemExit(f"iShares {fund}: P/E 를 찾지 못했습니다")
    if m.re.pattern.startswith("P/E Ratio ("):
        pe, as_of = float(m.group(1)), datetime.strptime(
            m.group(2), "%b %d, %Y").date().isoformat()
    else:
        as_of, pe = datetime.strptime(m.group(1), "%d/%b/%Y").date()\
            .isoformat(), float(m.group(2))
    return {"fund": fund, "pe": pe, "as_of": as_of, "source_url": url,
            "method_note": ("펀드 P/E 는 보유종목 P/E 의 가중 평균입니다. "
                            "적자 종목 처리와 가중 방식이 지수 총계 P/E "
                            "(총시가총액÷총이익)와 달라 같은 값이 나오지 "
                            "않습니다.")}


# ---------------------------------------------------------------- 나스닥100
def ndx_members():
    today = date.today().isoformat()
    raw = subprocess.run(
        ["curl", "-sS", "--fail", "--max-time", "60", "-A", UA_WEB,
         "-X", "POST", "-H", "X-Requested-With: XMLHttpRequest",
         "--data", f"id=NDX&tradeDate={today}T00:00:00.000&timeOfDay=SOD",
         NDX_MEMBERS], capture_output=True, check=True).stdout
    d = json.loads(raw)
    rows = [{"symbol": x["Symbol"], "name": x["Name"]} for x in d["aaData"]]
    if not 95 <= len(rows) <= 110:
        raise SystemExit(f"나스닥100 구성종목이 {len(rows)}개입니다")
    return {"members": rows, "trade_date": today, "source_url": NDX_MEMBERS,
            "source_page": "https://indexes.nasdaqomx.com/Index/Weighting/NDX"}


def ticker_map(refresh):
    d, _, _ = sec_cache.fetch_json(TICKERS, os.path.join(CACHE, "tickers.json"),
                                   max_age_days=7.0, refresh=refresh,
                                   min_bytes=100000)
    return {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
            for v in d.values()}


def _single_quarters(rows):
    """기간 사실을 단일 분기로. 80~100일 사실은 그대로, 없는 분기는 시작일이
    같은 두 누적 사실의 차. (analyse_fair_value 와 같은 규칙)"""
    by = {}
    for s, e, v in rows:
        by.setdefault((s, e), v)
    # 12주·16주 분기(펩시코·코스트코 같은 52/53주 회계연도)를 함께 받으려고
    # 80~115일. 100일로 막으면 16주짜리 4분기가 빠져 연속 분기가 끊기고,
    # 펩시코가 "2개 분기 연율화"로 떨어졌습니다.
    q = {e: v for (s, e), v in by.items() if 80 <= (e - s).days <= 115}
    starts = {}
    for (s, e), v in by.items():
        starts.setdefault(s, []).append((e, v))
    for lst in starts.values():
        lst.sort()
        for (e0, v0), (e1, v1) in zip(lst, lst[1:]):
            if 80 <= (e1 - e0).days <= 115 and e1 not in q:
                q[e1] = v1 - v0
    return dict(sorted(q.items()))


def earnings(cf, ticker, tag_map=None):
    """
    12개월 순이익(현지 통화)과 그것을 어떻게 만들었는지.

    **후보 태그를 전부 계산해 가장 최근 기간을 담은 것을 고릅니다.** 처음엔
    "데이터가 있는 첫 태그"를 집었는데, 브로드컴·부킹·엑셀론·AEP 가 몇 년
    전에 쓰기를 멈춘 태그의 이익(최대 14년 전)을 돌려줬습니다 — 50개사
    조사가 주석으로 경고해 둔 함정 그대로입니다.

    방식은 셋: 분기 공시(10-Q)가 있으면 최근 4개 분기 합, 연차만 내는 외국
    발행인(20-F·40-F)은 최근 회계연도, 상장한 지 1년이 안 돼 연속 분기가
    넷이 안 되면 있는 분기를 연율화(표시를 남깁니다). 분기말 네 개가
    연속이 아니면(250~290일이 아니면) 합산하지 않습니다.
    """
    facts = cf.get("facts", {})
    cands, tried = [], []
    for tax, tags in (tag_map or NI_TAGS).items():
        for rank_, tag in enumerate(tags):
            node = facts.get(tax, {}).get(tag)
            if not node:
                continue
            for unit, items in node["units"].items():
                if "/" in unit:
                    continue
                rows = [(date.fromisoformat(f["start"]),
                         date.fromisoformat(f["end"]), f["val"])
                        for f in items if f.get("start")]
                if not rows:
                    continue
                q = _single_quarters(rows)
                ends = sorted(q)
                base = {"tag": f"{tax}:{tag}", "currency": unit,
                        "tag_rank": rank_}
                if len(ends) >= 4 and 250 <= (ends[-1] - ends[-4]).days <= 300:
                    last4 = ends[-4:]
                    cands.append({**base, "value": sum(q[e] for e in last4),
                                  "method": "최근 4개 분기 합",
                                  "method_rank": 0,
                                  "period_end": last4[-1],
                                  "quarters": [q[e] for e in last4]})
                annual = [(s_, e, v) for s_, e, v in rows
                          if 350 <= (e - s_).days <= 380]
                if annual:
                    s_, e, v = max(annual, key=lambda r: r[1])
                    cands.append({**base, "value": v,
                                  "method": "최근 회계연도",
                                  "method_rank": 1, "period_end": e})
                # 연속 분기가 넷이 안 되면, 끝에서부터 연속인 분기만 연율화.
                if ends:
                    run = [ends[-1]]
                    for e in reversed(ends[:-1]):
                        if 80 <= (run[0] - e).days <= 115:
                            run.insert(0, e)
                        else:
                            break
                    if 1 <= len(run) < 4:
                        cands.append({**base,
                                      "value": sum(q[e] for e in run)
                                      * 4 / len(run),
                                      "method": f"{len(run)}개 분기 연율화",
                                      "method_rank": 2,
                                      "period_end": run[-1],
                                      "quarters": [q[e] for e in run]})
                if not cands:
                    tried.append(f"{tag}/{unit}")
    if not cands:
        raise LookupError("순이익 사실 없음 — " + " / ".join(tried[:4]))
    # 가장 최근 기간 → 같은 기간이면 분기합 > 연간 > 연율화 → 태그 우선순위.
    best = max(cands, key=lambda c: (c["period_end"], -c["method_rank"],
                                     -c["tag_rank"]))
    best = {k: v for k, v in best.items()
            if k not in ("tag_rank", "method_rank")}
    best["period_end"] = str(best["period_end"])
    best["candidates_considered"] = len(cands)
    return best


def nopat(cf, ticker, ni):
    """
    세후영업이익 = 영업이익 × (1 − 실효세율). 실효세율 = 법인세 ÷ 세전이익
    (같은 12개월). 세전이익이 0 이하이거나 세율이 0~40% 밖이면 법정세율
    21% 를 쓰고 그렇다고 적습니다(50개사 조사의 트립와이어와 같은 범위).

    영업이익 소계가 없거나 기간이 순이익과 맞지 않으면 순이익을 그대로
    씁니다 — 기간이 다른 둘을 섞으면 합계가 아무것도 측정하지 않습니다.
    """
    try:
        oi = earnings(cf, ticker, OI_TAGS)
    except LookupError:
        return {"nopat": ni["value"], "basis": "순이익 (영업이익 소계 없음)",
                "operating_income": None, "tax_rate": None,
                "tax_note": None}
    if oi["period_end"] != ni["period_end"] or oi["currency"] != ni["currency"]:
        return {"nopat": ni["value"],
                "basis": (f"순이익 (영업이익 기간 {oi['period_end']} ≠ "
                          f"순이익 기간 {ni['period_end']})"),
                "operating_income": None, "tax_rate": None,
                "tax_note": None}
    rate, note = STATUTORY, "법정세율 21% (실효세율 산출 불가)"
    try:
        pt = earnings(cf, ticker, PRETAX_TAGS)
        tx = earnings(cf, ticker, TAX_TAGS)
        if (pt["period_end"] == oi["period_end"]
                and tx["period_end"] == oi["period_end"] and pt["value"] > 0):
            r = tx["value"] / pt["value"]
            if 0.0 <= r <= 0.40:
                rate, note = r, "실효세율 (법인세 ÷ 세전이익)"
            else:
                note = f"법정세율 21% (실효세율 {r:.0%} 가 0~40% 밖)"
    except LookupError:
        pass
    return {"nopat": oi["value"] * (1 - rate),
            "basis": f"영업이익 × (1 − 세율) · {oi['method']}",
            "operating_income": oi["value"], "tax_rate": rate,
            "tax_note": note}


def equity(cf):
    """가장 최근 시점의 지배주주 자기자본(현지 통화). 400일 넘게 묵었으면 버립니다."""
    best = None
    for tax, tags in EQ_TAGS.items():
        for tag in tags:
            node = cf.get("facts", {}).get(tax, {}).get(tag)
            if not node:
                continue
            for unit, items in node["units"].items():
                for f in items:
                    if f.get("start"):
                        continue
                    if best is None or f["end"] > best["as_of"]:
                        best = {"value": f["val"], "as_of": f["end"],
                                "currency": unit, "tag": f"{tax}:{tag}"}
        if best:
            break
    if best and (date.today() - date.fromisoformat(best["as_of"])).days <= 400:
        return best
    return None


def shares(cf):
    """
    발행주식수. 표지(dei)를 먼저 보고, 묵었거나 없으면 손익계산서의
    가중평균 희석주식수로.

    **companyfacts 는 차원(class axis)이 붙은 사실을 버립니다.** 그래서 종류가
    여럿인 회사(알파벳·메타·팔란티어·컴캐스트 …)는 표지 주식수가 아예 없거나,
    차원 없이 마지막으로 실린 옛 값이 남습니다 — 컴캐스트가 2009년 값을
    돌려줘 시가총액이 절반으로 나왔습니다. 그래서 날짜를 보고, 400일이
    넘으면 쓰지 않습니다.
    """
    today = date.today()
    node = cf.get("facts", {}).get("dei", {}).get(
        "EntityCommonStockSharesOutstanding")
    if node:
        items = [f for its in node["units"].values() for f in its]
        last = max(f["end"] for f in items)
        if (today - date.fromisoformat(last)).days <= 400:
            same = [f for f in items if f["end"] == last]
            vals = sorted({(f.get("frame") or "", f["val"]) for f in same})
            return {"value": sum(v for _, v in vals), "as_of": last,
                    "classes": len(vals), "source": "dei 표지 발행주식수"}
    for tax, tag in (("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),
                     ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"),
                     ("ifrs-full", "AdjustedWeightedAverageShares"),
                     ("ifrs-full", "WeightedAverageShares")):
        node = cf.get("facts", {}).get(tax, {}).get(tag)
        if not node:
            continue
        items = [f for its in node["units"].values() for f in its
                 if f.get("start")]
        if not items:
            continue
        # 가장 최근 기간, 같은 끝이면 가장 짧은(분기) 기간.
        f = max(items, key=lambda f: (f["end"], -(
            date.fromisoformat(f["end"])
            - date.fromisoformat(f["start"])).days))
        if (today - date.fromisoformat(f["end"])).days <= 460:
            return {"value": f["val"], "as_of": f["end"], "classes": None,
                    "source": f"{tax}:{tag} (최근 기간)"}
    raise LookupError("쓸 수 있는 발행주식수 없음")


def splits_after(symbol, after):
    """그 날짜 이후의 주식 분할 배수. 시세는 분할을 반영하는데 공시의 주식수는
    분할 전 것일 수 있습니다 — 샌디스크가 2026-11-20 에 8:1 로 분할해,
    분할 전 주식수 × 분할 후 주가로 시가총액이 8분의 1이 됐습니다."""
    res, _ = yahoo(symbol, "range=2y&interval=3mo&events=split")
    mult, seen = 1.0, []
    for v in ((res.get("events") or {}).get("splits") or {}).values():
        d = datetime.fromtimestamp(v["date"], tz=timezone.utc).date()
        if d.isoformat() > after:
            mult *= v["numerator"] / v["denominator"]
            seen.append({"date": d.isoformat(), "ratio": v.get("splitRatio")})
    return mult, seen


def ads_ratio(ticker, cik, refresh):
    """ADS 비율을 20-F 본문에서 확인합니다. 문구가 없으면 멈춥니다."""
    spec = ADS[ticker]
    sub, _, _ = sec_cache.submissions(cik, CACHE, refresh=refresh,
                                      max_age_days=7.0)
    r = sub["filings"]["recent"]
    hit = next(((acc, doc) for f, acc, doc in zip(
        r["form"], r["accessionNumber"], r["primaryDocument"])
        if f in ("20-F", "10-K")), None)
    if not hit:
        raise SystemExit(f"{ticker}: 20-F 를 찾지 못했습니다")
    acc, doc = hit
    url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
           f"{acc.replace('-', '')}/{doc}")
    p, _, _ = sec_cache.fetch(url, os.path.join(CACHE, f"{ticker}_annual.htm"),
                              max_age_days=90.0, refresh=refresh,
                              min_bytes=50000)
    txt = re.sub(r"\s+", " ", _html.unescape(
        re.sub(r"<[^>]+>", " ", open(p, errors="ignore").read())))
    m = re.search(spec["phrase"], txt, re.I)
    if not m:
        raise SystemExit(f"{ticker}: ADS 비율 문구를 20-F 에서 찾지 "
                         f"못했습니다 — 비율 {spec['ratio']} 를 확인하십시오")
    return {"ratio": spec["ratio"], "evidence": txt[m.start():m.end()],
            "filing_url": url}


def ndx_constituents(members, refresh):
    """구성종목마다 12개월 순이익(달러)·시가총액. 실패한 종목은 이유와 함께
    남깁니다 — 조용히 빼면 집계가 그만큼 틀린 줄 모르게 됩니다."""
    tmap = ticker_map(refresh)
    fx_cache = {}
    out, seen_cik = [], {}
    for m in members:
        sym = m["symbol"]
        rec = {"symbol": sym, "name": m["name"]}
        cik = tmap.get(sym) or tmap.get(sym.replace(".", "-"))
        if not cik:
            rec["error"] = "SEC 티커 목록에 없음"
            out.append(rec)
            continue
        rec["cik"] = cik
        # 같은 회사의 두 종류 주식(GOOG·GOOGL)은 한 번만 셉니다. 발행주식수가
        # 이미 모든 종류의 합이기 때문입니다.
        if cik in seen_cik:
            rec["duplicate_of"] = seen_cik[cik]
            out.append(rec)
            continue
        seen_cik[cik] = sym
        try:
            cf, _, _ = sec_cache.companyfacts(cik, CACHE, refresh=refresh,
                                              max_age_days=1.0)
            e = earnings(cf, sym)
            sh = shares(cf)
            nop = nopat(cf, sym, e)
            eq = equity(cf)
        except (LookupError, ValueError, KeyError) as exc:
            rec["error"] = str(exc)[:160]
            out.append(rec)
            continue
        if e["currency"] not in fx_cache:
            fx_cache[e["currency"]] = fx_usd(e["currency"])
        rate, fx_url = fx_cache[e["currency"]]
        try:
            px = latest(sym)
        except subprocess.CalledProcessError:
            rec["error"] = "시세 없음"
            out.append(rec)
            continue
        ratio = 1
        if sym in ADS:
            a = ads_ratio(sym, cik, refresh)
            ratio = a["ratio"]
            rec["ads"] = a
        split_mult, split_events = splits_after(sym, sh["as_of"])
        price_per_share = px["price"] / ratio
        mcap = sh["value"] * split_mult * price_per_share
        age = (date.today() - date.fromisoformat(e["period_end"])).days
        rec.update({
            "net_income_local": e["value"], "currency": e["currency"],
            "fx_usd": rate, "fx_source": fx_url,
            "net_income_usd": e["value"] * rate,
            "nopat_local": nop["nopat"], "nopat_usd": nop["nopat"] * rate,
            "nopat_basis": nop["basis"],
            "operating_income_usd": (nop["operating_income"] * rate
                                     if nop["operating_income"] is not None
                                     else None),
            "equity_usd": (eq["value"] * rate
                           if eq and eq["currency"] == e["currency"]
                           else None),
            "equity_as_of": eq["as_of"] if eq else None,
            "effective_tax_rate": nop["tax_rate"],
            "tax_rate_note": nop["tax_note"],
            "earnings_tag": e["tag"], "earnings_method": e["method"],
            "earnings_period_end": e["period_end"],
            "earnings_age_days": age,
            "shares": sh["value"], "shares_as_of": sh["as_of"],
            "share_classes": sh["classes"], "shares_source": sh["source"],
            "split_multiplier": split_mult, "splits": split_events,
            "earnings_candidates": e.get("candidates_considered"),
            "price": px["price"], "price_date": px["date"],
            "ads_ratio": ratio, "market_cap": mcap,
        })
        if age > 460:
            rec["error"] = f"이익 자료가 {age}일 묵었음"
        # 종목별 트립와이어: 나스닥100 편입 기업의 시가총액이 50억 달러보다
        # 작거나 P/E 가 0~3배면 주식수·분할·통화 중 하나가 틀린 것입니다.
        pe = mcap / rec["net_income_usd"] if rec["net_income_usd"] else None
        rec["pe"] = pe
        if mcap < 5 * BN or (pe is not None and 0 < pe < 3):
            rec["suspect"] = (f"시가총액 {mcap / BN:,.1f}십억 · P/E "
                              f"{pe:,.1f}" if pe else "시가총액 이상")
        out.append(rec)
        print(f"    {sym:<6} 시총 {mcap / BN:>8,.0f}십억  순이익 "
              f"{e['value'] * rate / BN:>7,.1f}십억  {e['method']}"
              + (f"  ({e['currency']})" if e["currency"] != "USD" else "")
              + (f"  ✗ {rec['error']}" if rec.get("error") else ""))
    return out


# ------------------------------------------------------- 나스닥100 P/E 기록
WPR = "https://worldperatio.com/index/nasdaq-100/"
SIBLIS = "https://siblisresearch.com/data/nasdaq-100-pe-ratio/"
SIBLIS_API = "https://siblisresearch.com/api/v1/NDX/pe-trailing?format=csv"


def ndx_pe_history(refresh):
    """
    나스닥100 의 월별 12개월 P/E (1990~). 지수 단위 이익의 30년 기록은
    무료로 공표되지 않습니다 — S&P 다우존스의 multpl 같은 사본이 없습니다.
    worldperatio.com 이 QQQ 로 계산한 월별 계열을 차트 데이터로 싣고 있어
    그것을 씁니다. **2차 출처이고 계산 방법이 공개되지 않았습니다.** 그래서
    두 가지로 검정합니다(analyse_index.ndx_pe_checks):
      - 오늘 값 ↔ 우리가 SEC 공시에서 직접 모은 구성종목 순이익 P/E.
      - 과거 값 ↔ Siblis Research 가 무료로 공개한 연말·분기말 값(계산
        방법이 다름: 회계상 일회성 손익을 뺀 '정상화' 순이익).

    날짜 표기: 차트의 점은 매월 1일로 찍혀 있지만, 그 값을 **그 달 말
    종가**로 나눠야 이익이 매끄럽습니다(월간 변화 중위 1.2% — 전월말 종가로
    나누면 5.5%, 가격의 잡음이 이익에 섞입니다). 12개월 이익은 천천히
    움직이므로 매끄러운 쪽이 맞는 해석입니다. 마지막 점만은 페이지 본문의
    '계산일'(오늘에 가까운 날) 값이라 월말 값이 아닙니다 — 따로 표시합니다.
    """
    p, net, age = sec_cache.fetch(WPR, os.path.join(CACHE, "wpr_ndx.html"),
                                  max_age_days=1.0, refresh=refresh,
                                  min_bytes=100000)
    t = open(p, encoding="utf-8", errors="ignore").read()
    m = re.search(r"detailPE_data\s*=\s*\[(.*?)\];", t, re.S)
    if not m:
        raise SystemExit("worldperatio: P/E 계열을 찾지 못했습니다")
    pts = re.findall(r"Date\.UTC\((\d+),\s*(\d+),\s*(\d+)\),\s*([-\d.]+)\]",
                     m.group(1))
    rows = [{"month": f"{int(y):04d}-{int(mo) + 1:02d}", "pe": float(v)}
            for y, mo, _, v in pts]
    if len(rows) < 400 or rows[0]["month"] > "1995-01":
        raise SystemExit(f"worldperatio: 점이 {len(rows)}개, "
                         f"시작 {rows[0]['month'] if rows else None}")
    flat = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", t)))
    c = re.search(r"P/E\) Ratio for Nasdaq 100 Index is ([\d.]+) , "
                  r"calculated on (\d{1,2} [A-Z][a-z]+ \d{4})", flat)
    if not c:
        raise SystemExit("worldperatio: 계산일 문구를 찾지 못했습니다")
    cur = {"pe": float(c.group(1)),
           "date": datetime.strptime(c.group(2), "%d %B %Y").date()
           .isoformat()}
    # 마지막 점이 본문의 현재값과 같으면 그 점은 월말 값이 아니라 계산일
    # 값입니다.
    last_live = abs(rows[-1]["pe"] - cur["pe"]) < 0.01
    return {"rows": rows, "current": cur, "last_point_is_current": last_live,
            "source_url": WPR, "fetched_age_days": age,
            "method_note": ("P/E Ratio is calculated on the QQQ Etf, whose "
                            "benchmark is the Nasdaq 100 Index (페이지 문구)")}


def siblis_ndx(refresh):
    """Siblis Research 가 무료로 공개한 나스닥100 12개월 P/E — 대조용."""
    p, _, age = sec_cache.fetch(SIBLIS, os.path.join(CACHE, "siblis_ndx.html"),
                                max_age_days=1.0, refresh=refresh,
                                min_bytes=20000)
    t = open(p, encoding="utf-8", errors="ignore").read()
    i = t.find("Ten years of trailing")
    tb = re.search(r"<table>(.*?)</table>", t[i:], re.S) if i > 0 else None
    if not tb:
        raise SystemExit("Siblis: 연말 표를 찾지 못했습니다")
    head = [re.sub(r"<[^>]+>", "", h).strip()
            for h in re.findall(r"<th scope=\"col\"[^>]*>(.*?)</th>",
                                tb.group(1))]
    col = head.index("NASDAQ 100") - 1          # 첫 열은 행 머리(th)
    mon = {m_: i_ + 1 for i_, m_ in enumerate(
        "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}
    pts = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", tb.group(1), re.S):
        th = re.search(r"<th scope=\"row\">(.*?)</th>", r)
        tds = [re.sub(r"<[^>]+>", "", x).strip()
               for x in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if not th or len(tds) <= col:
            continue
        lab = th.group(1).strip()
        a = re.fullmatch(r"(\d{4}) ([A-Z][a-z]{2})", lab)
        b = re.fullmatch(r"([A-Z][a-z]{2}) (\d{4})", lab)
        y, mo = (a.group(1), a.group(2)) if a else (b.group(2), b.group(1))
        pts.append({"month": f"{y}-{mon[mo]:02d}", "pe": float(tds[col]),
                    "source": "page"})
    if len(pts) < 10:
        raise SystemExit(f"Siblis: 연말 값이 {len(pts)}개뿐입니다")
    pa, _, _ = sec_cache.fetch(SIBLIS_API,
                               os.path.join(CACHE, "siblis_ndx_api.csv"),
                               max_age_days=1.0, refresh=refresh, min_bytes=100)
    have = {x["month"] for x in pts}
    for line in open(pa, encoding="utf-8").read().splitlines()[1:]:
        f = line.split(",")
        if len(f) == 3 and f[0] == "NDX" and f[1][:7] not in have:
            pts.append({"month": f[1][:7], "pe": float(f[2]),
                        "source": "free_api"})
    pts.sort(key=lambda x: x["month"])
    return {"points": pts, "source_url": SIBLIS, "api_url": SIBLIS_API,
            "fetched_age_days": age,
            "method_note": ("Aggregate normalised net income over the "
                            "previous twelve months. Major purely accounting "
                            "gains and losses are removed. (페이지 문구) — "
                            "월말 값")}


# ------------------------------------------------------------------ 거시
def macro():
    out = {}
    for key, sym, label in (("treasury_30y", "%5ETYX", "30년 미국 국채"),
                            ("treasury_10y", "%5ETNX", "10년 미국 국채")):
        res, url = yahoo(sym, "range=5d&interval=1d")
        v = res["meta"].get("regularMarketPrice")
        if v is None or not 0 < v < 25:
            raise SystemExit(f"{label}: {v!r}")
        out[key] = {"label": label, "percent": v, "rate": v / 100,
                    "source_url": url}
    bs = json.load(open(BS, encoding="utf-8"))
    bei = dict(bs["macro"]["breakeven_inflation_10y"])
    bei["note"] = (bei.get("note", "") + " FRED 가 이 환경에서 접속되지 "
                   "않아 앞선 엔진이 읽어 둔 값을 출처 날짜와 함께 씁니다.")
    out["breakeven_inflation_10y"] = bei
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)
    print(f"오늘 {date.today().isoformat()} 기준")

    print("  시세: ^GSPC ^NDX")
    prices = {"SPX": {"monthly": monthly("%5EGSPC"),
                      "latest": latest("%5EGSPC")},
              "NDX": {"monthly": monthly("%5ENDX"),
                      "latest": latest("%5ENDX")},
              # 30년 국채 수익률의 월별 기록 — 과거의 매수 구간을 같은 규칙으로
              # 되짚을 때 그 달의 할인율로 씁니다.
              "TYX": {"monthly": monthly("%5ETYX")}}
    # 고점·저점은 일봉으로 찾습니다.
    prices["SPX"]["daily"] = daily("%5EGSPC")
    prices["NDX"]["daily"] = daily("%5ENDX")
    for k, v in prices.items():
        if "latest" not in v:
            continue
        L = v["latest"]
        print(f"    {k} {L['price']:,.2f} ({L['date']}, "
              f"{'장중' if L['is_intraday'] else '종가'}) · 월봉 "
              f"{len(v['monthly']['rows'])}개 "
              f"{v['monthly']['rows'][0]['date']}~")

    print("  S&P 500 이익·P/E·장부가치 (multpl)")
    spx = {"eps": multpl("s-p-500-earnings", "by-month", a.refresh),
           "pe": multpl("s-p-500-pe-ratio", "by-month", a.refresh),
           "book_value": multpl("s-p-500-book-value", "by-quarter",
                                a.refresh),
           "dividend": multpl("s-p-500-dividend", "by-month", a.refresh),
           # multpl 의 이익·배당 표는 **실질(그 달 기준 불변 달러)** 입니다.
           # 페이지 문구: "12-month real earnings per share — inflation
           # adjusted, constant September, 2026 dollars". 처음엔 명목인 줄
           # 알고 실러의 명목 이익과 대조했더니 중위 54% 가 어긋났습니다 —
           # 그 대조가 이걸 잡았습니다. 같은 사이트의 CPI 로 명목으로
           # 되돌립니다.
           "cpi": multpl("cpi", "by-month", a.refresh)}
    for k, v in spx.items():
        print(f"    {k:<11} {len(v['rows'])}행 "
              f"{v['rows'][0]['date']}~{v['rows'][-1]['date']} "
              f"최근 {v['rows'][-1]['value']:,.2f}")
    print("  실러 ie_data.xls (독립 사본)")
    sh = shiller(a.refresh)
    print(f"    {len(sh['rows'])}행, 이익은 {sh['last_with_earnings']} 까지")

    print("  iShares P/E (교차확인용)")
    ish = {k: ishares_pe(k, a.refresh) for k in ISHARES}
    for k, v in ish.items():
        print(f"    {k} {v['fund']} P/E {v['pe']} ({v['as_of']})")

    print("  나스닥100 구성종목")
    mem = ndx_members()
    print(f"    {len(mem['members'])}개 ({mem['trade_date']})")
    cons = ndx_constituents(mem["members"], a.refresh)

    print("  나스닥100 P/E 30년 기록 (worldperatio) · 대조 (Siblis)")
    npe = ndx_pe_history(a.refresh)
    sib = siblis_ndx(a.refresh)
    print(f"    worldperatio {len(npe['rows'])}점 {npe['rows'][0]['month']}~"
          f"{npe['rows'][-1]['month']} · 현재 {npe['current']['pe']} "
          f"({npe['current']['date']}) · Siblis {len(sib['points'])}점")

    out = {
        "generated": date.today().isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "prices": prices, "spx": spx, "shiller": sh, "ishares": ish,
        "ndx_members": mem, "ndx_constituents": cons, "macro": macro(),
        "ndx_pe_history": npe, "siblis_ndx": sib,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    ok = [c for c in cons if "market_cap" in c and not c.get("error")]
    print(f"\n  구성종목 집계 가능 {len(ok)}개 / 명단 {len(cons)}개")
    print(f"wrote {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
