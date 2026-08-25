// 兜底策略数据资产（IR-0001 W6 / 卡 #11，BEH-6、INV-1）。
// 纪律：每种媒体类型恰一条策略——单级兜底，禁止多级模型轮换降级路径；
// 策略步骤全部为本地确定性操作，零模型调用。

/** 需要兜底的媒体类型。 */
export type MediaKind = "image" | "video";

/** 触发兜底的原因：主路径生成失败，或质检重生成超限（BUDGET-2）。 */
export type FallbackReason = "generation-failed" | "qc-budget-exhausted";

/** 可枚举兜底策略（产物包内唯一降级路径，可审查）。 */
export interface FallbackStrategy {
  kind: MediaKind;
  strategy: string;
  steps: string[];
  usesModelCall: boolean;
}

export const FALLBACK_STRATEGIES: Record<MediaKind, FallbackStrategy> = {
  image: {
    kind: "image",
    strategy: "source-crop-local-composite",
    steps: [
      "fetch source product image from the input package",
      "center-crop the source image to a square canvas",
      "local composite onto a pure white background at target size",
    ],
    usesModelCall: false,
  },
  video: {
    kind: "video",
    strategy: "image-slideshow",
    steps: [
      "collect the generated product detail images",
      "local slideshow encode to mp4 at 1280x720",
    ],
    usesModelCall: false,
  },
};
