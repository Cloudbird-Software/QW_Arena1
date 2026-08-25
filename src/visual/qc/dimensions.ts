// VLM 质检四维定义与预算常量（IR-0001 W3 / 卡 #8，IFACE-2、BUDGET-2）。
// 纪律：四维清单与重生成上限是唯一判定口径——可枚举、禁止散落。

/** 质检四维：事实一致性 / 构图 / 技术质量 / 合规（AC-3 固定四维）。 */
export type QCDimension =
  "factual_consistency" | "composition" | "technical_quality" | "compliance";

export const QC_DIMENSIONS: readonly QCDimension[] = [
  "factual_consistency",
  "composition",
  "technical_quality",
  "compliance",
];

/** BUDGET-2：单张图质检不合格的重生成次数上限，超限后走兜底路径。 */
export const REGENERATION_LIMIT = 2;
