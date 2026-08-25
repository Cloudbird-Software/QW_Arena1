// W6 验收测试（卡 #11 / AC-6，specs/IR-0001 BEH-6、INV-1、BUDGET-2）。
// 测试先行：本文件先于实现单独入库（g050 fail-before——红必须是断言失败，
// import 缺失折叠为哨兵对象，见 loadFallback）。
import { describe, expect, it } from "vitest";

interface FallbackStrategy {
  kind: string;
  strategy: string;
  steps: string[];
  usesModelCall: boolean;
}

interface FallbackPlan extends FallbackStrategy {
  reason: string;
}

interface FallbackModule {
  planFallback?: (kind: string, reason: string) => FallbackPlan;
  listFallbackStrategies?: () => FallbackStrategy[];
}

const loadFallback = async (): Promise<FallbackModule> =>
  (await import("../src/fallback/index.js").catch(
    () => ({}),
  )) as FallbackModule;

const fallback = await loadFallback();

describe("W6 兜底路径收缩——单级兜底（AC-6）", () => {
  it("主路径失败注入：图片兜底为源图裁剪加本地合成（then）", () => {
    const plan = fallback.planFallback?.("image", "generation-failed");
    expect(plan?.strategy).toBe("source-crop-local-composite");
    expect(plan?.kind).toBe("image");
    expect(plan?.reason).toBe("generation-failed");
  });

  it("主路径失败注入：视频兜底为图片轮播（then）", () => {
    const plan = fallback.planFallback?.("video", "generation-failed");
    expect(plan?.strategy).toBe("image-slideshow");
    expect(plan?.kind).toBe("video");
  });

  it("质检重生成超限走同一兜底路径（BUDGET-2 衔接，不分流）", () => {
    const qcExhausted = fallback.planFallback?.("image", "qc-budget-exhausted");
    const generationFailed = fallback.planFallback?.(
      "image",
      "generation-failed",
    );
    expect(qcExhausted?.strategy).toBe(generationFailed?.strategy);
    expect(qcExhausted?.steps).toEqual(generationFailed?.steps);
  });

  it("产物包内不存在多级模型轮换降级路径（BEH-6）", () => {
    const strategies = fallback.listFallbackStrategies?.() ?? [];
    expect(strategies.length).toBe(2);
    const kinds = strategies.map((s) => s.kind).sort();
    expect(kinds).toEqual(["image", "video"]);
    for (const strategy of strategies) {
      expect(strategy.usesModelCall).toBe(false);
      const joined = [strategy.strategy, ...strategy.steps].join(" ");
      expect(joined).not.toMatch(/rotate|next-model|secondary|fallback-model/i);
    }
  });

  it("兜底步骤为本地确定性操作（源图裁剪/本地合成/轮播编码）", () => {
    const image = fallback.planFallback?.("image", "generation-failed");
    expect(image?.steps.join(" ")).toContain("source");
    expect(image?.steps.join(" ")).toContain("local");
    const video = fallback.planFallback?.("video", "generation-failed");
    expect(video?.steps.join(" ")).toContain("slideshow");
  });
});
