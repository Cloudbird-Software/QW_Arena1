// 输出稳定性控制模块入口（IR-0001 W4 / 卡 #9，BEH-4、INV-3）。
// 图像生成调用 = 组装提示词（W1 构图 × W2 词典）+ 负面提示词（四类失败模式）
// + 固定种子——相同输入与相同参数下产出完全一致（AC-4 可复现）。
// 负面提示词与种子为本模块可枚举数据资产（INV-3：禁止散落于自由文本；
// 原独立 assets.ts 并入入口——repo-map token 预算收敛，g900 无回归）。
import { buildImagePrompt } from "../index.js";
import type { GarmentCategory, ImageRole, Market } from "../index.js";

/** 负面提示词失败模式（AC-4 固定四类）。 */
export interface NegativePromptEntry {
  mode: "text_in_image" | "watermark" | "collage" | "border";
  text: string;
}

/** 四类失败模式清单（可枚举，禁止散落）。 */
const NEGATIVE_FAILURE_MODES: readonly NegativePromptEntry["mode"][] = [
  "text_in_image",
  "watermark",
  "collage",
  "border",
];

const NEGATIVE_PROMPTS: Record<NegativePromptEntry["mode"], string> = {
  text_in_image:
    "no text, no letters, no words, no typography, no captions anywhere in the image",
  watermark: "no watermark, no logo overlay, no stamp, no signature",
  collage:
    "no collage, no split frame, no multi-panel layout, no grid of images",
  border: "no border, no frame, no outline, no decorative edge",
};

/**
 * 固定生成种子（BEH-4：相同输入与相同参数下产出可复现）。
 * 取赛题截止日为种子值——常量资产，禁止运行时随机化。
 */
export const FIXED_SEED = 20260831;

/** 一次图像生成调用的完整确定性请求（BEH-4）。 */
export interface GenerationRequest {
  prompt: string;
  negativePrompt: string;
  seed: number;
}

/**
 * 组装图像生成请求：提示词（构图+词典）+ 负面提示词（四类失败模式）+ 固定种子。
 */
export function buildGenerationRequest(
  category: GarmentCategory,
  role: ImageRole,
  market: Market,
): GenerationRequest {
  const prompt = buildImagePrompt(category, role, market);
  const negativePrompt = NEGATIVE_FAILURE_MODES.map(
    (mode) => NEGATIVE_PROMPTS[mode],
  ).join(", ");
  return { prompt, negativePrompt, seed: FIXED_SEED };
}

/**
 * 全量负面提示词清单（INV-3：以可枚举配置资产存在，逐条可回查）。
 */
export function listNegativePromptEntries(): NegativePromptEntry[] {
  return NEGATIVE_FAILURE_MODES.map((mode): NegativePromptEntry => {
    const text = NEGATIVE_PROMPTS[mode];
    return { mode, text };
  });
}
