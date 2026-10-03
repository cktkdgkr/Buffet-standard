"""
Readable names for the fifty tickers.

The names that come back from the SEC are registrant names, which are not
written for reading: COSTCO WHOLESALE CORP /NEW, APPLIED MATERIALS INC /DE,
WELLS FARGO & COMPANY/MN. The suffixes are state-of-incorporation markers and
the capitalisation is an artefact of the filing system. They are kept in the
data and shown in the workbook's components sheet so every row can still be
traced back to the filer, but the reports use these instead.

Two names carry a history that matters when reading a ten-year series:

  GE   filed as General Electric for most of the window and is now GE
       Aerospace. The FY2016-FY2023 figures are the conglomerate - power,
       renewables, healthcare and aviation together - and are not comparable to
       the aviation-only company the ticker now refers to.
  GEV  GE Vernova was spun out of that conglomerate in April 2024, which is why
       it has four years of data rather than ten.

check() is called by verify_roic.py so a ticker added to the study without a
name here fails a test rather than printing a blank.
"""

# ticker: (readable English, Korean, one-line note or "")
NAMES = {
    "AAPL": ("Apple", "애플", ""),
    "ABBV": ("AbbVie", "애브비", "2013년 애보트에서 분사"),
    "AMAT": ("Applied Materials", "어플라이드 머티리얼즈", ""),
    "AMD": ("Advanced Micro Devices", "AMD", ""),
    "AMZN": ("Amazon.com", "아마존", ""),
    "ANET": ("Arista Networks", "아리스타 네트웍스", ""),
    "AVGO": ("Broadcom", "브로드컴", ""),
    "AXP": ("American Express", "아메리칸 익스프레스", ""),
    "BAC": ("Bank of America", "뱅크오브아메리카", ""),
    "BRK-B": ("Berkshire Hathaway", "버크셔 해서웨이", ""),
    "C": ("Citigroup", "씨티그룹", ""),
    "CAT": ("Caterpillar", "캐터필러", ""),
    "COST": ("Costco Wholesale", "코스트코", ""),
    "CSCO": ("Cisco Systems", "시스코 시스템즈", ""),
    "CVX": ("Chevron", "셰브론", ""),
    "DELL": ("Dell Technologies", "델 테크놀로지스", "2018년 재상장"),
    "GE": ("General Electric / GE Aerospace", "제너럴 일렉트릭",
           "2024년 GE 에어로스페이스로 사명 변경. FY2023까지는 복합기업 "
           "기준이므로 현재의 항공엔진 단일 사업과 직접 비교 불가"),
    "GEV": ("GE Vernova", "GE 버노바",
            "2024년 4월 GE에서 분사 — 그래서 산출 연도가 4년"),
    "GOOG": ("Alphabet", "알파벳", "구글의 모회사"),
    "GS": ("Goldman Sachs Group", "골드만삭스", ""),
    "HD": ("Home Depot", "홈디포", ""),
    "IBM": ("International Business Machines", "IBM", ""),
    "INTC": ("Intel", "인텔", ""),
    "JNJ": ("Johnson & Johnson", "존슨앤드존슨", ""),
    "JPM": ("JPMorgan Chase", "JP모건 체이스", ""),
    "KLAC": ("KLA", "KLA", "2019년까지 사명은 KLA-Tencor"),
    "KO": ("Coca-Cola", "코카콜라", ""),
    "LLY": ("Eli Lilly", "일라이 릴리", ""),
    "LRCX": ("Lam Research", "램리서치", ""),
    "MA": ("Mastercard", "마스터카드", ""),
    "META": ("Meta Platforms", "메타 플랫폼스",
             "2021년까지 사명은 Facebook"),
    "MRK": ("Merck & Co.", "머크", ""),
    "MS": ("Morgan Stanley", "모건스탠리", ""),
    "MSFT": ("Microsoft", "마이크로소프트", ""),
    "MU": ("Micron Technology", "마이크론 테크놀로지", ""),
    "NFLX": ("Netflix", "넷플릭스", ""),
    "NVDA": ("NVIDIA", "엔비디아", "1월 결산 — 본문의 회계연도 표기 참고"),
    "ORCL": ("Oracle", "오라클", "5월 결산"),
    "PANW": ("Palo Alto Networks", "팔로알토 네트웍스", "7월 결산"),
    "PG": ("Procter & Gamble", "프록터앤드갬블", "P&G · 6월 결산"),
    "PLTR": ("Palantir Technologies", "팔란티어 테크놀로지스",
             "2020년 상장"),
    "PM": ("Philip Morris International", "필립모리스 인터내셔널", ""),
    "RTX": ("RTX", "RTX",
            "2023년까지 사명은 Raytheon Technologies. 2020년 "
            "레이시온·유나이티드테크놀로지스 합병"),
    "TSLA": ("Tesla", "테슬라", ""),
    "TXN": ("Texas Instruments", "텍사스 인스트루먼츠", ""),
    "UNH": ("UnitedHealth Group", "유나이티드헬스 그룹", ""),
    "V": ("Visa", "비자", "9월 결산"),
    "WFC": ("Wells Fargo", "웰스파고", ""),
    "WMT": ("Walmart", "월마트", "1월 결산"),
    "XOM": ("Exxon Mobil", "엑슨모빌", ""),
}


def korean(ticker):
    return NAMES.get(ticker, (ticker, ticker, ""))[1]


def english(ticker):
    return NAMES.get(ticker, (ticker, ticker, ""))[0]


def note(ticker):
    return NAMES.get(ticker, (ticker, ticker, ""))[2]


def label(ticker, form="full"):
    """
    form="full"  →  애플 (Apple, AAPL)
    form="short" →  애플 (AAPL)
    form="plain" →  애플

    Korean names are stored without brackets of their own so the ticker and the
    English name can be bracketed here without nesting, and a company whose
    Korean name is already its ticker - IBM, KLA, AMD, RTX - does not get the
    ticker printed twice.
    """
    ko, en = korean(ticker), english(ticker)
    if form == "plain":
        return ko
    if ko == ticker:
        return ko if form == "short" else f"{ticker} ({en})"
    if form == "short":
        return f"{ko} ({ticker})"
    if ko == en:
        return f"{ko} ({ticker})"
    return f"{ko} ({en}, {ticker})"


def joined(tickers, form="short"):
    return ", ".join(label(t, form) for t in tickers)


def check(tickers):
    """Tickers in the study with no name here, and names with no ticker."""
    have, want = set(NAMES), set(tickers)
    return sorted(want - have), sorted(have - want)
