// W7 验收测试（卡 #12 / AC-7，specs/IR-0001 BEH-7、INV-3、INV-4）。
// 测试先行：本文件先于实现单独入库（g050 fail-before——红必须是断言失败，
// import 缺失折叠为哨兵对象，见 loadInspection）。
import { describe, expect, it } from "vitest";

interface ImageArtifact {
  role: string;
  width: number;
  height: number;
  bytes: number;
  background: string;
}

interface ImageFinding {
  rule: string;
  message: string;
}

interface NormalizationPlan {
  artifactRole: string;
  actions: string[];
}

interface SpecThreshold {
  key: string;
  value: number;
  unit: string;
}

interface InspectionModule {
  inspectImage?: (artifact: ImageArtifact) => ImageFinding[];
  normalizeImage?: (artifact: ImageArtifact) => NormalizationPlan;
  listSpecThresholds?: () => SpecThreshold[];
}

const loadInspection = async (): Promise<InspectionModule> =>
  (await import("../src/inspection/index.js").catch(
    () => ({}),
  )) as InspectionModule;

const inspection = await loadInspection();

const rulesOf = (artifact: ImageArtifact): string[] =>
  (inspection.inspectImage?.(artifact) ?? []).map((f) => f.rule);

const mainImage = (overrides: Partial<ImageArtifact>): ImageArtifact => ({
  role: "main_image",
  width: 1300,
  height: 1300,
  bytes: 2_000_000,
  background: "white",
  ...overrides,
});

const detailImage = (overrides: Partial<ImageArtifact>): ImageArtifact => ({
  role: "detail_image",
  width: 950,
  height: 950,
  bytes: 1_000_000,
  background: "other",
  ...overrides,
});

describe("W7 产物规格校验与强制规格化（AC-7）", () => {
  it("合规产物零违规：主图白底方图 1300、详情图 950、体积达标", () => {
    expect(rulesOf(mainImage({}))).toEqual([]);
    expect(rulesOf(detailImage({}))).toEqual([]);
  });

  it("主图最短边低于 1200 被拦截（BEH-7）", () => {
    expect(rulesOf(mainImage({ width: 1199, height: 1300 }))).toContain(
      "min-side",
    );
    expect(rulesOf(mainImage({ width: 1300, height: 1199 }))).toContain(
      "min-side",
    );
  });

  it("主图非方图与非白底分别被拦截（BEH-7）", () => {
    expect(rulesOf(mainImage({ width: 1300, height: 1250 }))).toContain(
      "main-square",
    );
    expect(rulesOf(mainImage({ background: "gray" }))).toContain(
      "main-white-background",
    );
  });

  it("详情图最短边低于 900 被拦截；主图规则不套用到详情图", () => {
    const findings = rulesOf(detailImage({ width: 899 }));
    expect(findings).toContain("min-side");
    expect(findings).not.toContain("main-square");
    expect(findings).not.toContain("main-white-background");
  });

  it("单张超过 4.5MB 被拦截（INV-4 下游保障）", () => {
    expect(rulesOf(mainImage({ bytes: 4_500_001 }))).toContain("size-budget");
    expect(rulesOf(detailImage({ bytes: 4_500_001 }))).toContain("size-budget");
  });

  it("越界产物被强制规格化：动作与违规一一对应（BEH-7 then）", () => {
    const artifact = mainImage({
      width: 1199,
      height: 1250,
      background: "gray",
      bytes: 5_000_000,
    });
    const findings = inspection.inspectImage?.(artifact) ?? [];
    expect(findings.length).toBe(4);
    const plan = inspection.normalizeImage?.(artifact);
    expect(plan?.artifactRole).toBe("main_image");
    expect(plan?.actions).toContain("resize-crop-to-min-side");
    expect(plan?.actions).toContain("center-crop-square");
    expect(plan?.actions).toContain("recomposite-white-background");
    expect(plan?.actions).toContain("recompress-under-budget");
    const compliant = inspection.normalizeImage?.(mainImage({}));
    expect(compliant?.actions).toEqual([]);
  });

  it("阈值以可枚举配置资产存在（INV-3）：1200 / 900 / 4.5MB", () => {
    const thresholds = inspection.listSpecThresholds?.() ?? [];
    const byKey = Object.fromEntries(thresholds.map((t) => [t.key, t]));
    expect(byKey["main_min_side"]?.value).toBe(1200);
    expect(byKey["detail_min_side"]?.value).toBe(900);
    expect(byKey["max_image_bytes"]?.value).toBe(4_500_000);
    expect(thresholds.length).toBeGreaterThanOrEqual(3);
    for (const threshold of inspection.listSpecThresholds?.() ?? []) {
      expect(threshold.value).toBeGreaterThan(0);
      expect(threshold.unit.length).toBeGreaterThan(0);
    }
  });
});
