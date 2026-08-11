/**
 * Word export - the narrative report as a document.
 *
 * Reads the payload written by export_docx_data.py so the ranking and scoring
 * come from report.py rather than being reimplemented here.
 *
 * Landscape, because the ranking table has nine columns and squeezing it into
 * portrait would wrap every cell. Column widths are in DXA and each table's
 * widths sum to the 14,400 twips of content between the margins; docx needs the
 * width on the table and on every cell or Google Docs renders it wrong.
 *
 * Writes work/버핏기준_52개기업_분석.docx.
 */

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, WidthType, AlignmentType, ShadingType, BorderStyle,
  PageOrientation, LevelFormat, convertInchesToTwip,
} = require("docx");

const WORK = __dirname;
const payload = JSON.parse(fs.readFileSync(path.join(WORK, "_docx_payload.json"), "utf8"));

// Malgun Gothic is the standard Korean face on Windows, where most readers of
// this will open it; Word substitutes a Hangul-capable font elsewhere.
const FONT = "Malgun Gothic";
const NAVY = "1F3864";
const GREY = "595959";
const CONTENT_WIDTH = 14400;

const text = (t, opts = {}) => new TextRun({ text: t, font: FONT, ...opts });

const para = (t, opts = {}) =>
  new Paragraph({
    children: Array.isArray(t) ? t : [text(t, opts.run || {})],
    spacing: { after: opts.after ?? 120, line: 276 },
    ...(opts.paragraph || {}),
  });

const h1 = (t) =>
  new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 160 },
    children: [text(t, { bold: true, size: 28, color: NAVY })],
  });

const note = (t) =>
  new Paragraph({
    spacing: { after: 160, line: 260 },
    children: [text(t, { size: 18, color: GREY, italics: true })],
  });

function table(headers, rows, widths, opts = {}) {
  const headerRow = new TableRow({
    tableHeader: true,
    children: headers.map((hcell, i) =>
      new TableCell({
        width: { size: widths[i], type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: NAVY, color: "auto" },
        margins: { top: 60, bottom: 60, left: 80, right: 80 },
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 0 },
          children: [text(hcell, { bold: true, color: "FFFFFF", size: 17 })],
        })],
      })),
  });

  const bodyRows = rows.map((r, ri) =>
    new TableRow({
      children: r.map((cell, i) =>
        new TableCell({
          width: { size: widths[i], type: WidthType.DXA },
          shading: ri % 2
            ? { type: ShadingType.CLEAR, fill: "F2F4F8", color: "auto" }
            : undefined,
          margins: { top: 50, bottom: 50, left: 80, right: 80 },
          children: [new Paragraph({
            alignment: (opts.numeric || []).includes(i)
              ? AlignmentType.RIGHT
              : AlignmentType.LEFT,
            spacing: { after: 0 },
            children: [text(String(cell), { size: 17 })],
          })],
        })),
    }));

  return new Table({
    columnWidths: widths,
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 2, color: "BFBFBF" },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: "BFBFBF" },
      left: { style: BorderStyle.NONE },
      right: { style: BorderStyle.NONE },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 1, color: "D9D9D9" },
      insideVertical: { style: BorderStyle.NONE },
    },
    rows: [headerRow, ...bodyRows],
  });
}

const children = [];

// ---------------------------------------------------------------- title
children.push(new Paragraph({
  spacing: { after: 80 },
  children: [text("버핏 기준 52개 기업 분석", { bold: true, size: 40, color: NAVY })],
}));
children.push(new Paragraph({
  spacing: { after: 320 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: NAVY, space: 8 } },
  children: [text(`미국 50개사 정량 분석 · 한국 2개사 정성 분석 · 생성 ${payload.generated}`,
    { size: 20, color: GREY })],
}));

// ---------------------------------------------------------------- summary
children.push(h1("한눈에"));
payload.headline.forEach((t) => {
  children.push(new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: 100, line: 276 },
    children: [text(t, { size: 20 })],
  }));
});
children.push(note(payload.macro));

// ---------------------------------------------------------------- quality
children.push(h1(`1. 품질 순위 — 비금융 ${payload.n_std}개사`));
children.push(para("점수는 사업의 질만 봅니다. 가격은 다음 절에서 따로 다룹니다. 자본비용에 못 미치는 사업은 싸다고 투자 대상이 되지 않는다는 것이 원칙 1의 요지이기 때문입니다.",
  { run: { size: 20 } }));
children.push(table(
  ["순위", "티커", "기업", "총점", "ROIC 중앙값", "두자릿수 유지", "신규 ROIC", "ROIC−WACC", "해자 판정"],
  payload.quality_rows,
  [700, 900, 3000, 800, 1400, 1300, 1600, 1500, 3200],
  { numeric: [0, 3, 4, 5, 6, 7] }));
if (payload.unscoreable_rows && payload.unscoreable_rows.length) {
  children.push(para([text("점수를 낼 수 없는 기업", { bold: true, size: 20 })],
    { paragraph: { spacing: { before: 240, after: 100 } } }));
  children.push(table(["티커", "기업", "사유"], payload.unscoreable_rows,
    [1000, 3400, 10000]));
}
children.push(note("배점: ROIC 중앙값 25 · 지속성 20 · 신규 ROIC 20 · ROIC−WACC 15 · 주주이익 마진 10 · 순부채/EBITDA 5 · 이자보상배율 5 (합계 100). 백분위가 아니라 절대 기준입니다."));

// ---------------------------------------------------------------- valuation
children.push(new Paragraph({ children: [], pageBreakBefore: true }));
children.push(h1("2. 가격 — 원칙 5·6"));
children.push(para("주주이익 기준 2단계 DCF입니다. 기준 시나리오는 할인율 10%·영구성장 2.5%, 예측기간 10년입니다. 금액 단위는 십억 달러입니다.",
  { run: { size: 20 } }));
children.push(para("적정가치는 하나의 숫자가 아니라 범위로 제시합니다. 하한은 설비투자 전액을 주주이익에서 차감한 것이고, 상한은 감가상각만큼만(유지 목적) 차감한 것입니다. 버핏의 주주이익 정의는 '장기 경쟁지위와 판매량을 유지하는 데 필요한' 지출을 빼라고 하므로 후자가 정의에 더 가깝지만, 인플레이션기에는 자산 교체비용이 감가상각을 넘으므로 전자가 안전한 하한입니다.",
  { run: { size: 20 } }));
children.push(para("함축수익률은 지금 가격에 사서 가정대로 흘러갈 때 얻는 연 수익률입니다. 무위험수익률과 직접 비교하시면 됩니다. '안전마진 30% 이상인가'는 비싼 시장에서 거의 전부 '아니오'로 답이 끝나버리는 반면, 함축수익률은 종목 간 비교를 가능하게 합니다. 아래 표는 함축수익률 내림차순입니다.",
  { run: { size: 20 } }));
children.push(table(
  ["티커", "주주이익 하한", "주주이익 상한", "적정가치 하한", "적정가치 상한", "시가총액",
   "함축수익률", "순현금", "판정(하한)"],
  payload.valuation_rows,
  [1000, 1700, 1700, 1700, 1700, 1600, 1500, 1500, 2000],
  { numeric: [1, 2, 3, 4, 5, 6, 7] }));

children.push(para([text("밸류에이션을 내지 않은 기업", { bold: true, size: 20 })],
  { after: 100, paragraph: { spacing: { before: 280, after: 100 } } }));
children.push(para("아래 기업은 정규화 주주이익이 음수여서 할인할 현금흐름 자체가 없습니다. 데이터 공백이 아니라 설비투자와 운전자본이 순이익을 넘어선다는 사업 판정입니다. 금융 9개사는 프레임워크 자체가 적용되지 않아 5절에서 별도로 다룹니다.",
  { run: { size: 20 } }));
children.push(table(["티커", "기업", "정규화 주주이익"], payload.negoe_rows,
  [1400, 4000, 9000], { numeric: [] }));

// ---------------------------------------------------------------- ROE trap
children.push(new Paragraph({ children: [], pageBreakBefore: true }));
children.push(h1("3. ROE의 함정 — 원칙 2"));
children.push(para("ROE에서 ROIC를 뺀 값이 크면 보고된 자기자본이익률이 사업의 수익성이 아니라 레버리지에서 나오고 있다는 신호입니다. 다만 자사주 매입으로 자기자본이 줄어든 경우에도 같은 형태로 벌어지므로, 부채 지표를 함께 봐야 구분됩니다. 상위 12개사입니다.",
  { run: { size: 20 } }));
children.push(table(
  ["티커", "ROE", "ROIC", "차이", "순부채/EBITDA", "이자보상배율", "읽는 법"],
  payload.roe_rows, [900, 1500, 1500, 1500, 1800, 1700, 5500],
  { numeric: [1, 2, 3, 4, 5] }));

// ---------------------------------------------------------------- capital
children.push(h1("4. 자본배분 — 원칙 4"));
children.push(para("주식수 연평균 증감률입니다. 음수는 자사주 매입으로 주당 가치가 올라갔다는 뜻이고 양수는 희석입니다. 매입 상위 10개사와 희석 상위 5개사입니다.",
  { run: { size: 20 } }));
children.push(table(
  ["티커", "주식수 CAGR", "기간", "신규 ROIC", "해석"],
  payload.capital_rows, [1000, 1800, 2000, 1800, 7800], { numeric: [1, 3] }));
children.push(note("주식수는 액면분할 기준을 통일한 뒤 계산했습니다. 각 연도의 주식수는 그해 제출된 10-K의 단위로 기록되는데 10-K는 직전 2개 연도까지만 소급 수정하므로, 분할을 가로지르는 시계열을 그대로 두면 폭발적인 신주 발행처럼 보입니다. 조정 전 엔비디아는 연 41% 희석, 아마존은 연 33% 희석으로 나왔으나 실제로는 각각 4:1·10:1, 20:1 분할이었습니다. 반대로 델의 1806:1000이나 GE의 1281:1000처럼 정수가 아닌 비율은 분할이 아니라 스핀오프에 따른 주가 조정이어서 주식수에 적용하지 않았습니다."));

// ---------------------------------------------------------------- financials
children.push(new Paragraph({ children: [], pageBreakBefore: true }));
children.push(h1(`5. 금융 ${payload.n_fin}개사 — 별도 기준`));
children.push(para("ROIC와 주주이익은 산출하지 않았습니다. 은행·보험의 대차대조표에서 부채는 자금조달 수단이 아니라 영업 자산이고, 유동자산·유동부채 구분 자체가 존재하지 않아 투하자본과 운전자본이 정의되지 않기 때문입니다. 손으로 고른 목록이 아니라 SIC 6000~6799 기준으로 분류했습니다.",
  { run: { size: 20 } }));
children.push(table(
  ["티커", "기업", "업종", "ROE 중앙값", "최근 ROE", "PER", "PBR"],
  payload.fin_rows, [1000, 3000, 4400, 1600, 1500, 1400, 1500],
  { numeric: [3, 4, 5, 6] }));

// ---------------------------------------------------------------- Korea
children.push(h1("6. 한국 2개사 — 정성 분석"));
children.push(para([
  text("이 절에는 정량 수치가 없습니다. ", { bold: true, size: 20 }),
  text("삼성전자와 SK하이닉스는 SEC 등록 기업이 아니라 감사받은 재무제표를 DART에 제출하며, OpenDART API는 이 환경에 없는 인증키를 요구합니다. 앞의 50개사는 모든 숫자가 제출서류의 접수번호까지 추적되는데 이 두 곳만 기억에 의존해 숫자를 적으면 보고서 전체의 기준이 무너집니다. 그래서 사업의 성격만 프레임워크에 비추어 정리하고, 공백은 공백으로 남깁니다.", { size: 20 }),
]));
children.push(para([
  text("두 회사 모두 원칙 1과 3이 가장 혹독하게 적용되는 업종에 있습니다. ", { bold: true, size: 20 }),
  text(`메모리 반도체는 설비투자가 매출에 선행하고, 감가상각이 끝나기 전에 다음 세대 투자가 시작됩니다. 이 보고서의 미국 50개사에서도 같은 성질이 그대로 드러났습니다. 마이크론의 정규화 주주이익 마진은 비금융 ${payload.n_std}개 기업 중 최하위권이었고, 인텔은 주주이익이 음수였습니다. 메모리 사이클의 정점에서 순이익이 아무리 커도 주주이익 기준으로는 그 이익의 상당 부분이 다음 세대 공정에 재투입되어 주주에게 남지 않습니다.`, { size: 20 }),
]));
children.push(para([
  text("SK하이닉스", { bold: true, size: 20 }),
  text("는 HBM 비중이 커지면서 제품 믹스가 범용 D램에서 벗어나는 국면에 있습니다. 프레임워크상 이것이 해자에 해당하는지는 한 가지로 판별됩니다 — 사이클 저점에서도 ROIC가 자본비용을 넘는지입니다. 고점 ROIC는 메모리 업체에서 늘 높게 나오므로 판별력이 없습니다. 이 판정에는 최소 한 번의 완전한 사이클에 걸친 투하자본과 NOPAT 시계열이 필요하며 지금은 확보되지 않았습니다.", { size: 20 }),
]));
children.push(para([
  text("삼성전자", { bold: true, size: 20 }),
  text("는 반도체·디스플레이·모바일이 한 재무제표에 묶여 있어 전사 ROIC가 성격이 다른 사업들의 가중평균이 됩니다. 원칙 1을 의미 있게 적용하려면 사업부문별 영업이익과 부문 자산이 필요하고 이는 사업보고서 부문정보에 공시되지만 역시 DART 접근이 전제입니다. 전사 숫자만으로 내린 판정은 파운드리의 낮은 수익률과 메모리의 높은 수익률을 뭉개버려 어느 쪽에 대해서도 답을 주지 못합니다.", { size: 20 }),
]));
children.push(table(
  ["항목", "삼성전자", "SK하이닉스"],
  [
    ["원칙 1 · ROIC vs WACC", "판정불가 — 투하자본 시계열 없음", "판정불가 — 투하자본 시계열 없음"],
    ["원칙 2 · ROE 함정", "판정불가", "판정불가"],
    ["원칙 3 · 주주이익", "판정불가 — 구조적으로 자본집약적이라는 점만 확인", "판정불가 — 동일"],
    ["원칙 4 · 해자", "부문 혼재로 전사 판정이 무의미", "사이클 저점 ROIC가 관건, 미확보"],
    ["원칙 5·6 · 적정가치", "판정불가", "판정불가"],
  ],
  [3400, 5500, 5500]));
children.push(para([
  text("이 공백을 메우려면 ", { bold: true, size: 20 }),
  text("OpenDART 인증키(무료 발급) 하나면 됩니다. 키가 있으면 두 회사의 사업보고서 XBRL에서 미국 50개사와 동일한 항목을 동일한 방식으로 뽑아낼 수 있고, 접수번호 단위 출처와 PHASE 6 재검증까지 같은 파이프라인을 태울 수 있습니다.", { size: 20 }),
]));


// ---------------------------------------------------------------- Alphabet case
if (payload.alphabet) {
  const a = payload.alphabet;
  children.push(new Paragraph({ children: [], pageBreakBefore: true }));
  children.push(h1("7. 알파벳 사례 — 모델 맹점 점검"));
  children.push(para("이 절은 반례에서 출발합니다. 초판은 알파벳이 낙관 시나리오에서도 적정가치보다 비싸다고 판정했는데, 같은 기간 버크셔 해서웨이는 알파벳을 대규모로 매입했습니다. 둘 중 하나는 틀렸다는 뜻이므로 원인을 추적했고, 의견 차이가 아니라 모델의 실제 결함 세 가지가 나왔습니다.",
    { run: { size: 20 } }));

  children.push(para([text("사실 확인 — 버크셔의 알파벳 보유 (SEC 13F 원문)", { bold: true, size: 20 })],
    { paragraph: { spacing: { before: 240, after: 100 } } }));
  children.push(table(
    ["13F 제출일", "보유 시점", "보유 주식수", "평가액"],
    [["2025-11-14", "Q3 2025", "17,846,142주 (Class A)", "$4.34B — 신규 편입"],
     ["2026-02-17", "Q4 2025", "17,846,142주 (Class A)", "$5.59B — 주식수 동일"],
     ["2026-05-15", "Q1 2026", "54,249,798주 (A) + 3,585,215주 (C)", "$16.63B"]],
    [2400, 2400, 5200, 4400]));
  children.push(note("출처: EDGAR CIK 0001067983, 접수번호 0001193125-25-282901 · 0001193125-26-054580 · 0001193125-26-226661. Q1 2026에 3배로 늘렸고 신고 포트폴리오(약 $263B)의 6% 수준입니다."));

  children.push(para([text("결함 1 — 성장 설비투자를 사업 악화로 계산했습니다 (가장 큼)", { bold: true, size: 20 })],
    { paragraph: { spacing: { before: 240, after: 100 } } }));
  children.push(para(`버핏의 주주이익 정의는 '장기 경쟁지위와 판매량을 유지하는 데 필요한' 자본적 지출을 빼라고 합니다. 유지 목적 지출이지 자본예산 전체가 아닙니다. 초판은 설비투자 전액을 차감했습니다. 알파벳 최근 회계연도는 설비투자 $${a.capex}B에 감가상각 $${a.da}B로, 차액 $${a.growth_capex}B — 설비투자의 ${a.growth_share}가 증설 투자입니다. 이걸 전액 비용으로 치면 AI 데이터센터를 짓는 행위가 수익성 악화로 기록됩니다.`,
    { run: { size: 20 } }));
  children.push(para("이 결함은 알파벳만의 문제가 아니었습니다. 테슬라와 팔란티어는 '주주이익 음수'로 분류돼 밸류에이션 자체가 배제돼 있었는데, 성장 투자 때문이었지 사업이 나빠서가 아니었습니다. 유지 설비투자 기준으로는 음수인 기업이 하나도 없습니다.",
    { run: { size: 20 } }));

  children.push(para([text("결함 2 — 현금을 십억 단위로 잘못 봤습니다", { bold: true, size: 20 })],
    { paragraph: { spacing: { before: 240, after: 100 } } }));
  children.push(table(["항목", "수정 전", "수정 후"],
    [["유동자산", "$30.7B", "$126.8B"],
     ["순현금", "−$18B", `+$${a.net_cash}B`],
     ["ROIC (최근)", "35.4%", a.roic]],
    [4400, 5000, 5000], { numeric: [1, 2] }));
  children.push(para("현금 태그 하나만 읽고 유동 유가증권 $96B를 통째로 놓치고 있었습니다. 그 결과 투하자본이 과대계상돼 ROIC가 낮게 나왔고 순현금 부호가 뒤집혀 있었습니다. 운전자본 계산에서도 유가증권이 빠지므로 주주이익이 더 정확해집니다.",
    { run: { size: 20 } }));

  children.push(para([text("결함 3 — 태그 전환으로 생긴 연도 구멍", { bold: true, size: 20 })],
    { paragraph: { spacing: { before: 240, after: 100 } } }));
  children.push(para("알파벳은 매출 태그를 중간에 바꿔서 어느 한 태그도 10년을 온전히 덮지 못했고, FY2022 매출이 비어 있었습니다. 이제 두 태그가 겹치는 모든 연도에서 값이 정확히 일치할 때만(알파벳은 8개 연도 일치) 빈 연도를 메웁니다. 값이 하나라도 다르면 서로 다른 개념이므로 구멍을 그대로 둡니다.",
    { run: { size: 20 } }));

  children.push(para([text("남는 것은 판단 차이입니다", { bold: true, size: 20 })],
    { paragraph: { spacing: { before: 240, after: 100 } } }));
  children.push(table(["시나리오", "적정가치 하한(총 설비투자)", "적정가치 상한(유지 설비투자)", "안전마진 범위"],
    a.band_rows, [2400, 4200, 4200, 3600], { numeric: [1, 2, 3] }));
  children.push(para(`시가총액 $${a.market_cap}B 기준입니다. 낙관 시나리오에 유지 설비투자를 적용하면 안전마진이 ${a.optimistic_mos}로 플러스가 되고, 순현금 $${a.net_cash}B를 더하면 투자가능 기준선인 30%에 닿습니다. 다만 이건 낙관 가정과 유지 설비투자 가정을 동시에 채택한 결과이므로, 기준 시나리오가 여전히 비싸다는 사실을 덮지는 않습니다.`,
    { run: { size: 20 } }));

  children.push(para([text("버크셔가 본 것에 대한 추정", { bold: true, size: 20 })],
    { paragraph: { spacing: { before: 240, after: 100 } } }));
  children.push(table(["티커", "함축수익률", "ROIC 중앙값", "순현금($B)"],
    a.implied_rows, [2400, 4000, 4000, 4000], { numeric: [1, 2, 3] }));
  children.push(para("알파벳은 함축수익률 자체로는 상위권이되 1위가 아닙니다. 눈에 띄는 건 조합입니다. 위에 있는 종목들은 대부분 품질이 낮거나 순부채 상태인데, 알파벳은 ROIC 중앙값이 높고 오랫동안 두 자릿수를 지켰으며 목록에서 가장 큰 순현금을 들고 있습니다. 그리고 버크셔의 대안은 4.7% 단기국채입니다. 이 프레임워크의 '안전마진 30%' 문턱은 절대 기준이라 비싼 시장에서는 모든 종목에 '아니오'를 돌려주고 대화를 끝내버리지만, 실제 자본배분은 언제나 상대적입니다.",
    { run: { size: 20 } }));
  children.push(note("단서 두 가지. 첫째, 13F는 보유만 공시하고 매수 이유를 밝히지 않으므로 위 해석은 추정입니다. 둘째, 이 판단이 버핏 본인의 것인지 투자 담당이나 후임 경영진의 것인지는 공시로 알 수 없습니다."));

  children.push(para([text("이 사례가 남긴 구조적 한계", { bold: true, size: 20 })],
    { paragraph: { spacing: { before: 240, after: 100 } } }));
  [["과거만 봅니다.", "성장률은 과거 주주이익 CAGR에서 나오고 상한이 걸립니다. 사업이 변곡점에 있다면 과거 시계열에는 그 정보가 없습니다."],
   ["비영업 자산을 값으로 치지 않습니다.", "웨이모 같은 사업, 지분투자, 순현금은 이익 흐름에만 근거한 DCF에 들어오지 않습니다. 순현금은 별도 열로 표시만 했습니다."],
   ["할인율이 고정입니다.", "8·10·12%는 대안 수익률과 무관하게 고정돼 있습니다. 무위험수익률이 4.7%인 국면에서 10%를 요구하는 것은 상당히 높은 문턱입니다."],
   ["절대 기준이라 상대 비교를 못 합니다.", "포지션 규모나 기회비용은 이 프레임워크 밖의 문제입니다. 함축수익률 열을 넣은 것이 부분적인 보완입니다."],
  ].forEach(([hd, bd]) => {
    children.push(new Paragraph({
      numbering: { reference: "bullets", level: 0 },
      spacing: { after: 100, line: 276 },
      children: [text(hd + " ", { bold: true, size: 20 }), text(bd, { size: 20 })],
    }));
  });
}

// ---------------------------------------------------------------- limits
children.push(new Paragraph({ children: [], pageBreakBefore: true }));
children.push(h1("8. 한계와 데이터 처리 원칙"));
children.push(para("보고서에 실린 수치가 어떤 판단을 거쳤는지 밝혀둡니다. 수치를 그대로 쓰기 어려웠던 지점마다 추정으로 메우지 않고 표시하는 쪽을 택했습니다.",
  { run: { size: 20 } }));

const limits = [
  ["EBIT을 일관되게 재구성했습니다.", "릴리·엑슨모빌·IBM·머크·셰브론은 영업이익 소계를 아예 태깅하지 않습니다. 태그가 있는 회사는 보고된 영업이익을, 없는 회사는 다른 것을 쓰면 ROIC가 회사마다 다른 것을 뜻하게 됩니다. 그래서 전 종목에서 세전이익 + 이자비용으로 통일하고, 이자비용이 없는 3개사만 보고된 영업이익으로 대체했습니다."],
  ["분모는 기초·기말 평균입니다.", "기말 잔고를 쓰면 연말에 자본을 조달한 회사가 한 해 내내 그 자본으로 벌어들인 것처럼 보입니다."],
  ["필립모리스는 자기자본이 마이너스입니다.", "장기간의 자사주 매입 결과이고, 투하자본이 음수가 되는 해에는 비율 자체가 의미를 잃으므로 그런 연도는 산출하지 않고 표시만 했습니다."],
  ["베타의 설명력이 낮은 종목이 있습니다.", "5년 월간 수익률을 S&P 500에 회귀해 직접 추정했는데 엑슨모빌·머크·존슨앤드존슨 등 방어주는 결정계수가 0.05 미만입니다. 이 경우 CAPM 자기자본비용이 약하게만 식별되고 그 위에 세운 WACC도 무릅니다. 다만 DCF는 WACC가 아니라 8·10·12% 고정 할인율 3종을 쓰므로 이 약점의 영향을 받지 않습니다."],
  ["비자의 시가총액은 과소평가돼 있습니다.", "클래스 B-1·B-2·C의 전환비율은 이사회가 소송 에스크로 정산에 따라 주기적으로 재설정하므로 표지에서 도출할 수 없습니다. 클래스 A만으로 계산했습니다. 실제 전환 후 기준 시가총액은 이보다 크므로 비자의 안전마진은 표에 적힌 것보다 나쁩니다."],
  ["주주이익은 마진 기준으로 정규화했습니다.", "주주이익은 운전자본 타이밍 때문에 해마다 크게 출렁입니다. 코카콜라는 한 해에 166억 달러에서 21억 달러로 움직였습니다. 최근 5년 주주이익 마진의 중앙값을 최근 매출에 적용했습니다. 금액의 중앙값을 쓰면 성장 기업을 몇 년 전 규모로 평가하게 되어 보수적인 것이 아니라 낡은 값이 됩니다."],
  ["DCF는 점 추정이 아닙니다.", "보수·기준·낙관 3개 시나리오의 범위로만 읽어야 하며, 이 보고서는 '투자 가능 구간 안인가'라는 질문에만 답합니다. 목표주가가 아닙니다."],
  ["검증되지 않은 수치는 없습니다.", payload.verification_line],
];
limits.forEach(([head, body]) => {
  children.push(para([text(head + " ", { bold: true, size: 20 }), text(body, { size: 20 })]));
});

children.push(para([text("재현 방법", { bold: true, size: 20 })],
  { paragraph: { spacing: { before: 280, after: 100 } } }));
[
  "python3 work/build_universe.py           # 유니버스 확정",
  "python3 work/collect_sec.py --universe work/universe.json",
  "python3 work/collect_cover_shares.py     # 표지 주식수",
  "python3 work/collect_market.py           # 주가·베타·무위험수익률·ERP",
  "python3 work/analyse.py                  # PHASE 2-5",
  "python3 work/verify.py                   # PHASE 6",
  "python3 work/report.py                   # PHASE 7",
].forEach((line) => {
  children.push(new Paragraph({
    spacing: { after: 0, line: 240 },
    shading: { type: ShadingType.CLEAR, fill: "F2F4F8", color: "auto" },
    children: [new TextRun({ text: line, font: "Consolas", size: 17 })],
  }));
});

const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360, hanging: 240 } } },
      }],
    }],
  },
  styles: {
    default: {
      document: { run: { font: FONT, size: 20 } },
    },
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840, orientation: PageOrientation.LANDSCAPE },
        margin: {
          top: convertInchesToTwip(0.6), bottom: convertInchesToTwip(0.6),
          left: convertInchesToTwip(0.5), right: convertInchesToTwip(0.5),
        },
      },
    },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(WORK, "버핏기준_52개기업_분석.docx");
  fs.writeFileSync(out, buf);
  console.log("docx ->", out);
});
