// 本地渲染模块入口（IR-0001 W5 / 卡 #10，BEH-5、INV-4）。
// 尺码表详情图完全以本地 SVG 渲染生成——零模型调用、零网络、确定性输出；
// 三语字体经 font-family 嵌入（字体文件随产物包打包，见 fonts.ts）。
import { FONT_ASSETS } from "./fonts.js";
import type { ChartMarket, FontAsset } from "./fonts.js";

export type { ChartMarket, FontAsset } from "./fonts.js";

/** 尺码表输入：市场、标题、列头与数据行（由本地化层提供译文）。 */
export interface SizeChartInput {
  market: ChartMarket;
  title: string;
  columns: string[];
  rows: string[][];
}

/** 本地渲染产物：SVG 文档 + 画布尺寸 + 实际嵌入的字体。 */
export interface RenderedChart {
  svg: string;
  width: number;
  height: number;
  fontFamily: string;
}

/**
 * 模型调用审计回调（管线注入）。本地渲染路径（BEH-5）确认零调用——
 * deps 仅为声明依赖面而存在，`void deps` 显式表达"本路径不使用"。
 */
export interface RenderDeps {
  noteModelCall?: (label: string) => void;
}

const WIDTH = 900;
const ROW_HEIGHT = 32;
const TOP_OFFSET = 72;

/**
 * 渲染尺码表详情图：白底 SVG、标题、表头与数据行（BEH-5：全程零模型调用）。
 */
export function renderSizeChart(
  input: SizeChartInput,
  deps?: RenderDeps,
): RenderedChart {
  void deps;
  const font = fontFor(input.market);
  const height = TOP_OFFSET + (input.rows.length + 1) * ROW_HEIGHT;
  const svg = svgFor(input, font, height);
  return { svg, width: WIDTH, height, fontFamily: font.family };
}

/**
 * 全量字体打包清单（三语字体随产物包打包，可枚举审查）。
 */
export function listFontAssets(): FontAsset[] {
  return FONT_ASSETS.map((asset): FontAsset => ({ ...asset }));
}

function fontFor(market: ChartMarket): FontAsset {
  const found = FONT_ASSETS.find((asset) => asset.market === market);
  return found ?? (FONT_ASSETS[0] as FontAsset);
}

function svgFor(
  input: SizeChartInput,
  font: FontAsset,
  height: number,
): string {
  const header = headerRow(input, font);
  const rows = input.rows.map((row, i) => bodyRow(row, i, font)).join("\n");
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${height}" viewBox="0 0 ${WIDTH} ${height}">`,
    '<rect width="100%" height="100%" fill="#ffffff"/>',
    `<text x="24" y="36" font-family="${font.family}" font-size="20" fill="#111111">${escapeXml(input.title)}</text>`,
    header,
    rows,
    "</svg>",
  ].join("\n");
}

function headerRow(input: SizeChartInput, font: FontAsset): string {
  const y = TOP_OFFSET - 12;
  return `<text x="24" y="${y}" font-family="${font.family}" font-size="16" font-weight="bold" fill="#222222">${escapeXml(input.columns.join("    "))}</text>`;
}

function bodyRow(row: string[], index: number, font: FontAsset): string {
  const y = TOP_OFFSET + (index + 1) * ROW_HEIGHT;
  const cells = row
    .map(
      (cell, column) =>
        `<text x="${24 + column * 140}" y="${y}" font-family="${font.family}" font-size="16" fill="#333333">${escapeXml(cell)}</text>`,
    )
    .join(" ");
  return cells;
}

function escapeXml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
