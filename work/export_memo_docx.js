/**
 * Word export - memo replies and the Alphabet deep dive.
 *
 * Renders the block list built by export_memo_data.py. Unlike the main report
 * this one is portrait: it is mostly prose and quotation, and the widest table
 * has five columns.
 *
 * Column widths are in DXA and each table's widths sum to the 9,360 twips of
 * content between the margins; docx needs the width on the table and on every
 * cell or Google Docs renders it wrong.
 *
 * Writes work/알파벳_심층분석_및_메모회신.docx.
 */

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, WidthType, AlignmentType, ShadingType, BorderStyle,
  LevelFormat, convertInchesToTwip,
} = require("docx");

const WORK = __dirname;
// Payload and output are arguments so the second round of replies can reuse
// this renderer rather than forking it.
const PAYLOAD = process.argv[2] || "_memo_payload.json";
const OUT = process.argv[3] || "알파벳_심층분석_및_메모회신.docx";
const payload = JSON.parse(fs.readFileSync(path.join(WORK, PAYLOAD), "utf8"));

const FONT = "Malgun Gothic";
const NAVY = "1F3864";
const GREY = "595959";
const ACCENT = "8B3A2F";
const CONTENT_WIDTH = 9360;

const text = (t, opts = {}) => new TextRun({ text: t, font: FONT, ...opts });

// **bold** spans inside the prose, so emphasis survives into Word rather than
// arriving as literal asterisks.
function runs(t, base = {}) {
  const out = [];
  for (const piece of String(t).split(/(\*\*[^*]+\*\*)/g)) {
    if (!piece) continue;
    if (piece.startsWith("**") && piece.endsWith("**")) {
      out.push(text(piece.slice(2, -2), { ...base, bold: true }));
    } else {
      out.push(text(piece, base));
    }
  }
  return out;
}

const scale = (widths) => {
  const sum = widths.reduce((a, b) => a + b, 0);
  return widths.map((w) => Math.round((w / sum) * CONTENT_WIDTH));
};

function table(headers, rows, widths, numeric) {
  const w = scale(widths);
  const headerRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) =>
      new TableCell({
        width: { size: w[i], type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: NAVY, color: "auto" },
        margins: { top: 60, bottom: 60, left: 80, right: 80 },
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 0 },
          children: [text(h, { bold: true, color: "FFFFFF", size: 16 })],
        })],
      })),
  });

  const bodyRows = rows.map((r, ri) =>
    new TableRow({
      children: r.map((cell, i) =>
        new TableCell({
          width: { size: w[i], type: WidthType.DXA },
          shading: ri % 2
            ? { type: ShadingType.CLEAR, fill: "F2F4F8", color: "auto" }
            : undefined,
          margins: { top: 50, bottom: 50, left: 80, right: 80 },
          children: [new Paragraph({
            alignment: numeric.includes(i) ? AlignmentType.RIGHT : AlignmentType.LEFT,
            spacing: { after: 0 },
            children: runs(cell, { size: 16 }),
          })],
        })),
    }));

  return new Table({
    columnWidths: w,
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
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

children.push(new Paragraph({
  spacing: { after: 80 },
  children: [text(payload.title || "알파벳 심층분석 및 메모 회신",
    { bold: true, size: 36, color: NAVY })],
}));
children.push(new Paragraph({
  spacing: { after: 320 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: NAVY, space: 8 } },
  children: [text(
    `${payload.subtitle || "메모 5건 회신 · 버핏 기준 정립 · 알파벳 가치와 주가 평가"} · 생성 ${payload.generated}`,
    { size: 18, color: GREY })],
}));

const RENDER = {
  h1: (b) => children.push(new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 400, after: 160 },
    children: [text(b.text, { bold: true, size: 28, color: NAVY })],
  })),

  h2: (b) => children.push(new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 300, after: 120 },
    children: [text(b.text, { bold: true, size: 23, color: NAVY })],
  })),

  h3: (b) => children.push(new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 240, after: 100 },
    children: [text(b.text, { bold: true, size: 20, color: ACCENT })],
  })),

  p: (b) => children.push(new Paragraph({
    spacing: { after: 140, line: 288 },
    children: runs(b.text, { size: 19 }),
  })),

  note: (b) => children.push(new Paragraph({
    spacing: { before: 100, after: 180, line: 264 },
    indent: { left: 200 },
    border: { left: { style: BorderStyle.SINGLE, size: 12, color: "BFBFBF", space: 10 } },
    children: runs(b.text, { size: 17, color: GREY }),
  })),

  // Buffett in his own words, set apart so it is never mistaken for our text.
  quote: (b) => {
    children.push(new Paragraph({
      spacing: { before: 160, after: 40, line: 280 },
      indent: { left: 360, right: 200 },
      border: { left: { style: BorderStyle.SINGLE, size: 18, color: NAVY, space: 12 } },
      children: [text(`"${b.text}"`, { size: 18, italics: true, color: "1A1A1A" })],
    }));
    children.push(new Paragraph({
      spacing: { after: 200 },
      indent: { left: 360 },
      alignment: AlignmentType.RIGHT,
      children: [text(`— ${b.src}`, { size: 16, color: GREY })],
    }));
  },

  formula: (b) => children.push(new Paragraph({
    spacing: { before: 120, after: 180 },
    alignment: AlignmentType.CENTER,
    shading: { type: ShadingType.CLEAR, fill: "F2F4F8", color: "auto" },
    children: [text(b.text, { size: 18, bold: true, color: NAVY })],
  })),

  bullets: (b) => b.items.forEach((item) => children.push(new Paragraph({
    numbering: { reference: "memoBullets", level: 0 },
    spacing: { after: 120, line: 284 },
    children: runs(item, { size: 19 }),
  }))),

  table: (b) => {
    children.push(table(b.headers, b.rows, b.widths, b.numeric || []));
    children.push(new Paragraph({ spacing: { after: 200 }, children: [] }));
  },

  // The memo itself, reproduced verbatim above each reply so the question and
  // the answer stay together.
  memo: (b) => {
    children.push(new Paragraph({
      heading: HeadingLevel.HEADING_2,
      spacing: { before: 440, after: 60 },
      children: [text(b.location ? `메모 ${b.n} — ${b.location}` : `메모 ${b.n} — "${b.anchor}"`,
        { bold: true, size: 23, color: NAVY })],
    }));
    // The passage the memo was attached to, so the question is never read
    // apart from the sentence that prompted it.
    if (b.anchor_text) {
      children.push(new Paragraph({
        spacing: { before: 40, after: 20 },
        children: [text("원문 (기존 문서에서 메모가 달린 문장)", { size: 15, bold: true, color: GREY })],
      }));
      children.push(new Paragraph({
        spacing: { after: 140 },
        indent: { left: 200, right: 120 },
        shading: { type: ShadingType.CLEAR, fill: "F2F4F8", color: "auto" },
        border: { left: { style: BorderStyle.SINGLE, size: 12, color: "9AA5B1", space: 10 } },
        children: [text(`"${b.anchor_text}"`, { size: 16, color: "3A3A3A" })],
      }));
    }
    children.push(new Paragraph({
      spacing: { before: 40, after: 20 },
      children: [text("남기신 메모", { size: 15, bold: true, color: "8A5A16" })],
    }));
    children.push(new Paragraph({
      spacing: { after: 200 },
      indent: { left: 200 },
      shading: { type: ShadingType.CLEAR, fill: "FFF4E5", color: "auto" },
      border: { left: { style: BorderStyle.SINGLE, size: 18, color: "C88A2E", space: 10 } },
      children: [text(b.question, { size: 18, italics: true })],
    }));
    children.push(new Paragraph({
      spacing: { after: 60 },
      children: [text("검토 결과", { size: 15, bold: true, color: NAVY })],
    }));
  },
};

payload.blocks.forEach((b) => {
  const fn = RENDER[b.t];
  if (!fn) throw new Error(`unknown block type: ${b.t}`);
  fn(b);
});

const doc = new Document({
  numbering: {
    config: [{
      reference: "memoBullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360, hanging: 240 } } },
      }],
    }],
  },
  styles: { default: { document: { run: { font: FONT, size: 19 } } } },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: {
          top: convertInchesToTwip(0.8), bottom: convertInchesToTwip(0.8),
          left: convertInchesToTwip(0.75), right: convertInchesToTwip(0.75),
        },
      },
    },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(WORK, OUT);
  fs.writeFileSync(out, buf);
  console.log("docx ->", out);
});
