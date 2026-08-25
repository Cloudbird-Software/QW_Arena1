// W8 验收测试（卡 #13 / AC-8，specs/IR-0001 BEH-8）。
// 测试先行：本文件先于实现单独入库（g050 fail-before——红必须是断言失败，
// import 缺失折叠为哨兵对象，见 loadStrategy）。
import { describe, expect, it } from "vitest";

interface StrategySection {
  id: string;
  heading: string;
}

interface StrategyInput {
  costLines: string[];
  comparisonLines: string[];
  adaptationLines: string[];
  runLogRef: string;
}

interface StrategyDocument {
  markdown: string;
  sections: string[];
}

interface StrategyModule {
  buildStrategyDocument?: (input: StrategyInput) => StrategyDocument;
  listStrategySections?: () => StrategySection[];
}

const loadStrategy = async (): Promise<StrategyModule> =>
  (await import("../src/strategy/index.js").catch(
    () => ({}),
  )) as StrategyModule;

const strategy = await loadStrategy();

const SAMPLE_INPUT: StrategyInput = {
  costLines: [
    "图像生成 12 次调用 × ¥0.08 = ¥0.96",
    "VLM 质检 6 次调用 × ¥0.03 = ¥0.18",
  ],
  comparisonLines: [
    "人工流程单商品素材约 4 小时，本管线约 12 分钟",
    "人工设计师单商品成本约 ¥200，本管线约 ¥1.2",
  ],
  adaptationLines: [
    "换品类：仅需品类判定输入与构图模板资产（无代码改动）",
    "换市场：EN/KO/PT 词典资产已内置，新增市场=新增一条词典条目",
  ],
  runLogRef: "AGENT_LOG_DIR/run_manifest.json",
};

describe("W8 策略说明文档三节（AC-8）", () => {
  it("三节齐备：成本估算 / 效率对比 / 适配成本声明（BEH-8）", () => {
    const document = strategy.buildStrategyDocument?.(SAMPLE_INPUT);
    expect(document?.sections.length).toBe(3);
    expect(document?.markdown).toContain("单商品成本估算");
    expect(document?.markdown).toContain("与人工流程的效率对比");
    expect(document?.markdown).toContain("换品类与换市场适配成本声明");
  });

  it("各节内容含对应输入数据", () => {
    const markdown = strategy.buildStrategyDocument?.(SAMPLE_INPUT)?.markdown;
    for (const line of [
      ...SAMPLE_INPUT.costLines,
      ...SAMPLE_INPUT.comparisonLines,
      ...SAMPLE_INPUT.adaptationLines,
    ]) {
      expect(markdown).toContain(line);
    }
  });

  it("数据与运行日志可追溯（runLogRef 留痕）", () => {
    const markdown = strategy.buildStrategyDocument?.(SAMPLE_INPUT)?.markdown;
    expect(markdown).toContain(SAMPLE_INPUT.runLogRef);
  });

  it("节结构以可枚举资产存在：三节定义逐条可回查（INV-3）", () => {
    const sections = strategy.listStrategySections?.() ?? [];
    expect(sections.length).toBe(3);
    const ids = sections.map((s) => s.id);
    expect(new Set(ids).size).toBe(3);
    for (const section of sections) {
      expect(section.heading.length).toBeGreaterThan(0);
    }
    const second = strategy.listStrategySections?.() ?? [];
    expect(second.map((s) => s.id)).toEqual(ids);
  });

  it("文档为 markdown 结构：主标题 + 节标题", () => {
    const markdown = strategy.buildStrategyDocument?.(SAMPLE_INPUT)?.markdown;
    expect(markdown?.startsWith("# ")).toBe(true);
    expect((markdown?.match(/^## /gm) ?? []).length).toBe(3);
  });
});
