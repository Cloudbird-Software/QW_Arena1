// 负面提示词与固定种子数据资产（IR-0001 W4 / 卡 #9，BEH-4、INV-3）。
// 纪律：负面提示词覆盖四类失败模式（图内文字/水印/拼图/边框）——可枚举、
// 禁止散落于自由文本；条目变更须与 specs/IR-0001 对应条款对齐。

/** 负面提示词失败模式（AC-4 固定四类）。 */
type NegativeFailureMode = "text_in_image" | "watermark" | "collage" | "border";

export const NEGATIVE_FAILURE_MODES: readonly NegativeFailureMode[] = [
  "text_in_image",
  "watermark",
  "collage",
  "border",
];

/** 可枚举负面提示词清单的一条记录（INV-3：可回查）。 */
export interface NegativePromptEntry {
  mode: NegativeFailureMode;
  text: string;
}

export const NEGATIVE_PROMPTS: Record<NegativeFailureMode, string> = {
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
