// 单级兜底模块入口（IR-0001 W6 / 卡 #11，BEH-6、INV-1、BUDGET-2）。
// 主路径失败（生成失败 / 质检重生成超限）→ 单一兜底计划：图片=源图裁剪加
// 本地合成，视频=图片轮播；产物包内不存在多级模型轮换降级路径。
import { FALLBACK_STRATEGIES } from "./strategies.js";
import type {
  FallbackReason,
  FallbackStrategy,
  MediaKind,
} from "./strategies.js";

export type {
  FallbackReason,
  FallbackStrategy,
  MediaKind,
} from "./strategies.js";

/** 一次兜底决策的计划（策略 + 触发原因）。 */
export interface FallbackPlan extends FallbackStrategy {
  reason: FallbackReason;
}

/** 媒体类型清单（模块内枚举口径，与 FALLBACK_STRATEGIES 键同源；不导出以收敛公共面）。 */
const MEDIA_KINDS: readonly MediaKind[] = ["image", "video"];

/**
 * 产出兜底计划（BEH-6）：任何失败原因都退到同一单级兜底——不分流、
 * 不轮换模型；质检重生成超限（BUDGET-2）与生成失败同路径。
 */
export function planFallback(
  kind: MediaKind,
  reason: FallbackReason,
): FallbackPlan {
  const strategy = FALLBACK_STRATEGIES[kind];
  return { ...strategy, reason };
}

/**
 * 全量兜底策略清单（可枚举审查：恰两条、零模型调用）。
 */
export function listFallbackStrategies(): FallbackStrategy[] {
  return MEDIA_KINDS.map((kind) => ({ ...FALLBACK_STRATEGIES[kind] }));
}
