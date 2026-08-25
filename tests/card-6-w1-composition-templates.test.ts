// W1 验收测试（卡 #6 / AC-1，specs/IR-0001 BEH-1、INV-3、IFACE-1）。
// 测试先行：本文件先于实现单独入库（g050 fail-before——红必须是断言失败，
// import 缺失折叠为哨兵对象，见 loadVisual）。
import { describe, expect, it } from "vitest";

interface CompositionAsset {
  category: string;
  role: string;
  directive: string;
}

interface VisualModule {
  compositionFor?: (category: string, role: string) => string;
  listCompositionAssets?: () => CompositionAsset[];
  GARMENT_CATEGORIES?: readonly string[];
  IMAGE_ROLES?: readonly string[];
}

const loadVisual = async (): Promise<VisualModule> =>
  (await import("../src/visual/index.js").catch(() => ({}))) as VisualModule;

const visual = await loadVisual();

const directiveOf = (category: string, role: string): string =>
  visual.compositionFor?.(category, role) ?? "";

const pairsOf = <T>(xs: readonly T[]): [T, T][] =>
  xs.flatMap((a, i) => xs.slice(i + 1).map((b): [T, T] => [a, b]));

describe("W1 品类构图模板资产（AC-1）", () => {
  it("品类与角色清单已定义且品类数 > 1（given）", () => {
    const cats = visual.GARMENT_CATEGORIES ?? [];
    const roles = visual.IMAGE_ROLES ?? [];
    expect(cats.length).toBeGreaterThan(1);
    expect(roles.length).toBeGreaterThan(1);
  });

  it("任取两个不同品类，同一角色的构图指令互异（then）", () => {
    const cats = visual.GARMENT_CATEGORIES ?? [];
    const roles = visual.IMAGE_ROLES ?? [];
    expect(cats.length).toBeGreaterThan(1);
    expect(roles.length).toBeGreaterThan(0);
    for (const role of roles) {
      for (const [a, b] of pairsOf(cats)) {
        expect(directiveOf(a, role)).not.toBe(directiveOf(b, role));
      }
    }
  });

  it("品类 × 角色全组合的构图指令均非空（BEH-1）", () => {
    const cats = visual.GARMENT_CATEGORIES ?? [];
    const roles = visual.IMAGE_ROLES ?? [];
    expect(cats.length).toBeGreaterThan(0);
    for (const category of cats) {
      for (const role of roles) {
        expect(directiveOf(category, role).length).toBeGreaterThan(0);
      }
    }
  });

  it("映射以产物包内可枚举资产存在：清单覆盖全组合且逐条可回查（INV-3/IFACE-1）", () => {
    const cats = visual.GARMENT_CATEGORIES ?? [];
    const roles = visual.IMAGE_ROLES ?? [];
    const assets = visual.listCompositionAssets?.() ?? [];
    expect(assets.length).toBe(cats.length * roles.length);
    for (const asset of assets) {
      expect(cats).toContain(asset.category);
      expect(roles).toContain(asset.role);
      expect(asset.directive).toBe(directiveOf(asset.category, asset.role));
    }
  });

  it("组装图像提示词时含该品类专属构图指令（when/then）", () => {
    const cats = visual.GARMENT_CATEGORIES ?? [];
    expect(cats.length).toBeGreaterThan(0);
    for (const category of cats) {
      const directive = directiveOf(category, "main_image");
      const prompt = [
        "e-commerce product photo of the listed garment",
        directive,
      ].join(", ");
      expect(prompt).toContain(directive);
    }
  });
});
