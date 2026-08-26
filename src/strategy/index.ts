// 策略说明文档模块入口（IR-0001 W8 / 卡 #13，BEH-8、INV-3）。
// 生成随产物包落盘的策略说明文档：单商品成本估算、与人工流程的效率对比、
// 换品类与换市场适配成本声明三节；内容由输入数据渲染，数据与运行日志
// 可追溯（runLogRef 留痕）。本模块不做成本计算本身——估算数据由管线
// 运行时统计注入（见 AGENTS.md 禁止项）。

/** 可枚举的节定义资产（INV-3：禁止在渲染逻辑外散落节定义）。 */
interface StrategySection {
  id: string;
  heading: string;
}

/** 文档输入：三节内容行 + 运行日志引用（管线运行时统计注入）。 */
interface StrategyInput {
  costLines: string[];
  comparisonLines: string[];
  adaptationLines: string[];
  runLogRef: string;
}

/** 渲染产物：markdown 全文 + 节 id 清单。 */
interface StrategyDocument {
  markdown: string;
  sections: string[];
}

/** 节定义即文档结构：id、标题与该节内容行的取数入口（一一绑定，无旁路映射）。 */
const STRATEGY_SECTIONS: readonly (StrategySection & {
  linesOf: (input: StrategyInput) => string[];
})[] = [
  {
    id: "cost-estimation",
    heading: "单商品成本估算",
    linesOf: (input) => input.costLines,
  },
  {
    id: "efficiency-comparison",
    heading: "与人工流程的效率对比",
    linesOf: (input) => input.comparisonLines,
  },
  {
    id: "adaptation-cost",
    heading: "换品类与换市场适配成本声明",
    linesOf: (input) => input.adaptationLines,
  },
];

/** 文档主标题。 */
const DOCUMENT_TITLE = "单商品视觉产物策略说明";

function renderSection(section: StrategySection, lines: string[]): string {
  return [`## ${section.heading}`, ...lines.map((line) => `- ${line}`)].join(
    "\n",
  );
}

/**
 * 生成策略说明文档（BEH-8）：三节齐备，内容由输入数据渲染，
 * 尾注留痕运行日志引用（数据可追溯）。
 */
export function buildStrategyDocument(input: StrategyInput): StrategyDocument {
  const body = STRATEGY_SECTIONS.map((section) =>
    renderSection(section, section.linesOf(input)),
  );
  const markdown = [
    `# ${DOCUMENT_TITLE}`,
    ...body,
    `> 数据与运行日志可追溯：${input.runLogRef}`,
  ].join("\n\n");
  return {
    markdown,
    sections: STRATEGY_SECTIONS.map((section) => section.id),
  };
}

/**
 * 三节定义清单（INV-3：可枚举资产逐条可回查；仅返回定义面，防外泄篡改）。
 */
export function listStrategySections(): StrategySection[] {
  return STRATEGY_SECTIONS.map((section): StrategySection => ({
    id: section.id,
    heading: section.heading,
  }));
}
