// W4 验收测试（卡 #9 / AC-4，specs/IR-0001 BEH-4、INV-3）。
// 测试先行：本文件先于实现单独入库（g050 fail-before——红必须是断言失败，
// import 缺失折叠为哨兵对象，见 loadStability）。
import { describe, expect, it } from "vitest";

interface NegativePromptEntry {
  mode: string;
  text: string;
}

interface GenerationRequest {
  prompt: string;
  negativePrompt: string;
  seed: number;
}

interface StabilityModule {
  buildGenerationRequest?: (
    category: string,
    role: string,
    market: string,
  ) => GenerationRequest;
  listNegativePromptEntries?: () => NegativePromptEntry[];
  FIXED_SEED?: number;
}

const loadStability = async (): Promise<StabilityModule> =>
  (await import("../src/visual/stability/index.js").catch(
    () => ({}),
  )) as StabilityModule;

const stability = await loadStability();

const FAILURE_MODES = ["text_in_image", "watermark", "collage", "border"];

const requestOf = (market: string): GenerationRequest =>
  stability.buildGenerationRequest?.("dresses", "main_image", market) ?? {
    prompt: "",
    negativePrompt: "",
    seed: -1,
  };

describe("W4 输出稳定性控制——固定种子与负面提示词（AC-4）", () => {
  it("相同商品输入与相同生成参数：两次调用产出完全一致的请求（可复现）", () => {
    const first = stability.buildGenerationRequest?.(
      "dresses",
      "main_image",
      "EN",
    );
    const second = stability.buildGenerationRequest?.(
      "dresses",
      "main_image",
      "EN",
    );
    expect(first?.seed).toBe(second?.seed);
    expect(first?.prompt).toBe(second?.prompt);
    expect(first?.negativePrompt).toBe(second?.negativePrompt);
    expect(first?.seed ?? -1).toBeGreaterThan(0);
  });

  it("固定种子为常量资产（BEH-4：调用携带固定种子）", () => {
    const markets = ["EN", "KO", "PT"];
    for (const market of markets) {
      expect(requestOf(market).seed).toBe(stability.FIXED_SEED ?? -2);
    }
  });

  it("负面提示词覆盖图内文字、水印、拼图、边框四类失败模式（then）", () => {
    const negativePrompt = requestOf("EN").negativePrompt;
    const entries = stability.listNegativePromptEntries?.() ?? [];
    expect(entries.length).toBe(FAILURE_MODES.length);
    for (const mode of FAILURE_MODES) {
      const entry = entries.find((e) => e.mode === mode);
      expect(entry?.text.length ?? 0).toBeGreaterThan(0);
      expect(negativePrompt).toContain(entry?.text ?? "__missing__");
    }
  });

  it("负面提示词以可枚举配置资产存在：清单逐条可回查（INV-3）", () => {
    const entries = stability.listNegativePromptEntries?.() ?? [];
    expect(entries.length).toBe(FAILURE_MODES.length);
    for (const entry of entries) {
      expect(FAILURE_MODES).toContain(entry.mode);
      expect(entry.text.length).toBeGreaterThan(0);
    }
  });

  it("负面提示词在所有市场一致注入（BEH-4 对一切调用生效）", () => {
    const negativePrompt = requestOf("KO").negativePrompt;
    const entries = stability.listNegativePromptEntries?.() ?? [];
    for (const entry of entries) {
      expect(negativePrompt).toContain(entry.text);
    }
  });
});
