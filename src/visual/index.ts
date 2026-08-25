// 视觉管线模块入口（IR-0001 W1，卡 #6 / AC-1）。
// 公共面收敛为两个查询函数；构图数据资产在 compositions.ts（INV-3：可枚举，
// 禁止散落于自由文本）。后续市场词典（W2）、负面提示词（W4）等同构扩展。
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

export type {
  CompositionAsset,
  GarmentCategory,
  ImageRole,
} from "./compositions.js";

export { GARMENT_CATEGORIES, IMAGE_ROLES } from "./compositions.js";

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
 * 全量资产清单（IFACE-1：品类→构图模板映射可枚举审查，逐条可回查）。
 */
export function listCompositionAssets(): CompositionAsset[] {
  return GARMENT_CATEGORIES.flatMap((category) =>
    IMAGE_ROLES.map((role): CompositionAsset => {
      const directive = compositionFor(category, role);
      return { category, role, directive };
    }),
  );
}
