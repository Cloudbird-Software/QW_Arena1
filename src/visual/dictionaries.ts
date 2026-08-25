// 三市场视觉风格词典数据资产（IR-0001 W2 / 卡 #7，BEH-2、INV-2、IFACE-1）。
// 纪律：本文件是唯一市场词典来源——光照/色调/风格条目可枚举、禁止散落于
// 自由文本；条目变更须与 specs/IR-0001 对应条款对齐。

/** 目标市场（赛题三语市场：英语/韩语/葡语）。 */
export type Market = "EN" | "KO" | "PT";

/** 词典维度：光照、色调、风格（AC-2 固定三维）。 */
export type MarketDimension = "lighting" | "tone" | "style";

/** 可枚举词典清单的一条记录（IFACE-1：市场→条目映射可枚举审查）。 */
export interface MarketDictionaryEntry {
  market: Market;
  dimension: MarketDimension;
  text: string;
}

export const MARKETS: readonly Market[] = ["EN", "KO", "PT"];

export const MARKET_DIMENSIONS: readonly MarketDimension[] = [
  "lighting",
  "tone",
  "style",
];

export const MARKET_VISUAL_DICTIONARIES: Record<
  Market,
  Record<MarketDimension, string>
> = {
  EN: {
    lighting: "crisp high-key studio lighting with soft controlled shadows",
    tone: "clean neutral white balance, true-to-life product colors",
    style: "modern minimal global-marketplace e-commerce editorial style",
  },
  KO: {
    lighting: "bright airy K-fashion soft lighting with gentle falloff",
    tone: "warm pastel-leaning palette with softly lifted shadows",
    style: "Korean street-style magazine aesthetic, refined and youthful",
  },
  PT: {
    lighting: "vibrant natural sunlight with golden warmth",
    tone: "saturated vivid colors with high energy and contrast",
    style: "Brazilian lifestyle editorial style, tropical and confident",
  },
};
