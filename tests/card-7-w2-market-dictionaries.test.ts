// W2 验收测试（卡 #7 / AC-2，specs/IR-0001 BEH-2、INV-2、IFACE-1）。
// 测试先行：本文件先于实现单独入库（g050 fail-before——红必须是断言失败，
// import 缺失折叠为哨兵对象，见 loadVisual）。
import { describe, expect, it } from "vitest";

interface MarketDictionaryEntry {
  market: string;
  dimension: string;
  text: string;
}

interface VisualModule {
  MARKETS?: readonly string[];
  listMarketDictionaryEntries?: () => MarketDictionaryEntry[];
  buildImagePrompt?: (category: string, role: string, market: string) => string;
}

const loadVisual = async (): Promise<VisualModule> =>
  (await import("../src/visual/index.js").catch(() => ({}))) as VisualModule;

const visual = await loadVisual();

const MARKET_DIMENSIONS = ["lighting", "tone", "style"];

const dictionaryOf = (market: string): Record<string, string> =>
  Object.fromEntries(
    (visual.listMarketDictionaryEntries?.() ?? [])
      .filter((entry) => entry.market === market)
      .map((entry) => [entry.dimension, entry.text]),
  );

const promptOf = (category: string, role: string, market: string): string =>
  visual.buildImagePrompt?.(category, role, market) ?? "";

const pairsOf = <T>(xs: readonly T[]): [T, T][] =>
  xs.flatMap((a, i) => xs.slice(i + 1).map((b): [T, T] => [a, b]));

describe("W2 三市场视觉词典资产（AC-2）", () => {
  it("三市场与三维度清单已定义（given）", () => {
    const markets = visual.MARKETS ?? [];
    expect(markets.length).toBe(3);
    for (const market of markets) {
      for (const dimension of MARKET_DIMENSIONS) {
        expect(dictionaryOf(market)[dimension]?.length ?? 0).toBeGreaterThan(0);
      }
    }
  });

  it("三市场的光照、色调与风格条目两两互异（then）", () => {
    const markets = visual.MARKETS ?? [];
    expect(markets.length).toBeGreaterThan(1);
    for (const dimension of MARKET_DIMENSIONS) {
      for (const [a, b] of pairsOf(markets)) {
        expect(dictionaryOf(a)[dimension]).not.toBe(dictionaryOf(b)[dimension]);
      }
    }
  });

  it("三市场组装的图像提示词两两互异且各含本市场词典条目（BEH-2）", () => {
    const markets = visual.MARKETS ?? [];
    expect(markets.length).toBeGreaterThan(1);
    for (const [a, b] of pairsOf(markets)) {
      expect(promptOf("dresses", "main_image", a)).not.toBe(
        promptOf("dresses", "main_image", b),
      );
    }
    for (const market of markets) {
      const prompt = promptOf("dresses", "main_image", market);
      for (const dimension of MARKET_DIMENSIONS) {
        expect(prompt).toContain(dictionaryOf(market)[dimension] ?? "__none__");
      }
    }
  });

  it("词典为独立可枚举资产：清单覆盖 市场×维度 全组合且逐条可回查（IFACE-1）", () => {
    const markets = visual.MARKETS ?? [];
    const entries = visual.listMarketDictionaryEntries?.() ?? [];
    expect(entries.length).toBe(markets.length * MARKET_DIMENSIONS.length);
    for (const entry of entries) {
      expect(markets).toContain(entry.market);
      expect(MARKET_DIMENSIONS).toContain(entry.dimension);
      expect(entry.text).toBe(dictionaryOf(entry.market)[entry.dimension]);
    }
  });

  it("场景类详情图提示词同时绑定品类构图与市场词典（INV-2）", () => {
    const markets = visual.MARKETS ?? [];
    expect(markets.length).toBeGreaterThan(0);
    const first = markets[0] ?? "EN";
    const prompt =
      visual.buildImagePrompt?.("tops", "scene_image", first) ?? "";
    for (const dimension of MARKET_DIMENSIONS) {
      expect(prompt).toContain(dictionaryOf(first)[dimension] ?? "__none__");
    }
  });
});
