// W5 验收测试（卡 #10 / AC-5，specs/IR-0001 BEH-5、INV-4）。
// 测试先行：本文件先于实现单独入库（g050 fail-before——红必须是断言失败，
// import 缺失折叠为哨兵对象，见 loadRender）。
import { describe, expect, it, vi } from "vitest";

interface FontAsset {
  market: string;
  family: string;
  path: string;
}

interface SizeChartInput {
  market: string;
  title: string;
  columns: string[];
  rows: string[][];
}

interface RenderedChart {
  svg: string;
  width: number;
  height: number;
  fontFamily: string;
}

interface RenderModule {
  renderSizeChart?: (input: SizeChartInput, deps?: unknown) => RenderedChart;
  listFontAssets?: () => FontAsset[];
}

const loadRender = async (): Promise<RenderModule> =>
  (await import("../src/render/index.js").catch(() => ({}))) as RenderModule;

const render = await loadRender();

const chartFor = (market: string): SizeChartInput => ({
  market,
  title: { EN: "Size Chart", KO: "사이즈 차트", PT: "Tabela de Medidas" }[
    market
  ],
  columns: ["Size", "Bust", "Waist"],
  rows: [
    ["S", "88", "70"],
    ["M", "92", "74"],
  ],
});

describe("W5 尺码表详情图本地渲染（AC-5）", () => {
  it("渲染全程零模型调用（mock 计数，BEH-5）", () => {
    const noteModelCall = vi.fn();
    const chart = render.renderSizeChart?.(chartFor("EN"), {
      noteModelCall,
    });
    expect(chart?.svg.length ?? 0).toBeGreaterThan(0);
    expect(noteModelCall).not.toHaveBeenCalled();
  });

  it("三语字体随产物包打包且渲染正确嵌入（KO 字体条目）", () => {
    const assets = render.listFontAssets?.() ?? [];
    expect(assets.length).toBe(3);
    const markets = assets.map((a) => a.market);
    expect(markets).toContain("EN");
    expect(markets).toContain("KO");
    expect(markets).toContain("PT");
    const koFont = assets.find((a) => a.market === "KO");
    const koChart = render.renderSizeChart?.(chartFor("KO"));
    expect(koChart?.fontFamily).toBe(koFont?.family);
    expect(koChart?.svg).toContain(`font-family="${koFont?.family}"`);
  });

  it("三市场渲染各自嵌入对应市场字体", () => {
    const assets = render.listFontAssets?.() ?? [];
    for (const asset of assets) {
      const chart = render.renderSizeChart?.(chartFor(asset.market));
      expect(chart?.svg).toContain(`font-family="${asset.family}"`);
    }
  });

  it("本地渲染产物为白底 SVG 且含标题与全部尺码数据", () => {
    const input = chartFor("KO");
    const chart = render.renderSizeChart?.(input);
    expect(chart?.svg).toContain("<svg");
    expect(chart?.svg).toContain('fill="#ffffff"');
    expect(chart?.svg).toContain(input.title);
    for (const cell of ["S", "M", "88", "92", "70", "74"]) {
      expect(chart?.svg).toContain(cell);
    }
    expect(chart?.width ?? 0).toBeGreaterThan(0);
    expect(chart?.height ?? 0).toBeGreaterThan(0);
  });

  it("相同输入两次本地渲染产出一致（确定性，零模型）", () => {
    const first = render.renderSizeChart?.(chartFor("PT"));
    const second = render.renderSizeChart?.(chartFor("PT"));
    expect(first?.svg).toBe(second?.svg);
  });
});
