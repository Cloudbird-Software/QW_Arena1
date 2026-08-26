// 视觉管线模块入口（IR-0001 W1/W2，卡 #6、#7 / AC-1、AC-2）。
// 公共面收敛为查询与组装函数；构图模板与市场词典数据资产分别在
// compositions.ts / dictionaries.ts（INV-3：可枚举，禁止散落于自由文本）。
// 后续负面提示词（W4）等同构扩展。
import {
  COMPOSITION_TEMPLATES,
  GARMENT_CATEGORIES,
  IMAGE_ROLES,
} from "./compositions.js";
import type {
  CompositionAsset,
  GarmentCategory,
  ImageRole,
} from "./compositions.js";
import {
  MARKET_DIMENSIONS,
  MARKET_VISUAL_DICTIONARIES,
  MARKETS,
} from "./dictionaries.js";
import type { Market, MarketDictionaryEntry } from "./dictionaries.js";

export type {
  CompositionAsset,
  GarmentCategory,
  ImageRole,
} from "./compositions.js";

export { GARMENT_CATEGORIES, IMAGE_ROLES } from "./compositions.js";

export type {
  Market,
  MarketDictionaryEntry,
  MarketDimension,
} from "./dictionaries.js";

export { MARKETS } from "./dictionaries.js";

/**
 * 品类 × 角色的专属构图指令（BEH-1：品类判定完成后为每个图像角色注入提示词）。
 */
export function compositionFor(
  category: GarmentCategory,
  role: ImageRole,
): string {
  return COMPOSITION_TEMPLATES[category][role];
}

/**
 * 全量构图资产清单（IFACE-1：品类→构图模板映射可枚举审查，逐条可回查）。
 */
export function listCompositionAssets(): CompositionAsset[] {
  return GARMENT_CATEGORIES.flatMap((category) =>
    IMAGE_ROLES.map((role): CompositionAsset => {
      const directive = compositionFor(category, role);
      return { category, role, directive };
    }),
  );
}

/**
 * 全量词典清单（IFACE-1：市场→视觉风格条目映射可枚举审查，逐条可回查）。
 */
export function listMarketDictionaryEntries(): MarketDictionaryEntry[] {
  return MARKETS.flatMap((market) =>
    MARKET_DIMENSIONS.map((dimension): MarketDictionaryEntry => {
      const text = MARKET_VISUAL_DICTIONARIES[market][dimension];
      return { market, dimension, text };
    }),
  );
}

/**
 * 组装图像提示词：品类构图指令 + 市场词典条目（BEH-1 + BEH-2；INV-2：
 * 场景类详情图允许纯文生图，但须同时绑定品类构图与市场词典）。
 */
export function buildImagePrompt(
  category: GarmentCategory,
  role: ImageRole,
  market: Market,
): string {
  const dictionary = MARKET_VISUAL_DICTIONARIES[market];
  const fragments = [
    "e-commerce product photo of the listed garment",
    compositionFor(category, role),
    dictionary.lighting,
    dictionary.tone,
    dictionary.style,
  ];
  return fragments.join(", ");
}
