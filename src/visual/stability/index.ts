// 输出稳定性控制模块入口（IR-0001 W4 / 卡 #9，BEH-4、INV-3）。
// 图像生成调用 = 组装提示词（W1 构图 × W2 词典）+ 负面提示词（四类失败模式）
// + 固定种子——相同输入与相同参数下产出完全一致（AC-4 可复现）。
import { buildImagePrompt } from "../index.js";
import type { GarmentCategory, ImageRole, Market } from "../index.js";
import {
  FIXED_SEED,
  NEGATIVE_FAILURE_MODES,
  NEGATIVE_PROMPTS,
} from "./assets.js";
import type { NegativePromptEntry } from "./assets.js";

export type { NegativePromptEntry } from "./assets.js";

export { FIXED_SEED } from "./assets.js";

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
