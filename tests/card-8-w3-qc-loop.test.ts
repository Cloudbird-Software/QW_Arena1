// W3 验收测试（卡 #8 / AC-3，specs/IR-0001 BEH-3、INV-1、IFACE-2、BUDGET-2）。
// 测试先行：本文件先于实现单独入库（g050 fail-before——红必须是断言失败，
// import 缺失折叠为哨兵对象，见 loadQc）。
import { describe, expect, it } from "vitest";

interface QCReviewRecord {
  imageUrl: string;
  dimensions: Record<string, string>;
  issues: string[];
  passed: boolean;
  reviewedAt: string;
}

interface RegenerationPlan {
  action: string;
  feedback?: string;
}

interface QcModule {
  reviewImage?: (imageUrl: string, rawReview: string) => QCReviewRecord;
  buildReviewPrompt?: (imageUrl: string) => string;
  planRegeneration?: (
    record: QCReviewRecord,
    attemptsUsed: number,
  ) => RegenerationPlan;
}

const loadQc = async (): Promise<QcModule> =>
  (await import("../src/visual/qc/index.js").catch(() => ({}))) as QcModule;

const qc = await loadQc();

const QC_DIMENSIONS = [
  "factual_consistency",
  "composition",
  "technical_quality",
  "compliance",
];

const URL = "https://model.example/generated/img-001.png";

const reviewOf = (imageUrl: string, rawReview: string): QCReviewRecord =>
  qc.reviewImage?.(imageUrl, rawReview) ?? {
    imageUrl: "",
    dimensions: {},
    issues: [],
    passed: false,
    reviewedAt: "",
  };

const planOf = (
  record: QCReviewRecord,
  attemptsUsed: number,
): RegenerationPlan =>
  qc.planRegeneration?.(record, attemptsUsed) ?? { action: "" };

const passingReview: string = JSON.stringify({
  factual_consistency: "pass",
  composition: "pass",
  technical_quality: "pass",
  compliance: "pass",
  issues: [],
});

const failingReview: string = JSON.stringify({
  factual_consistency: "fail",
  composition: "pass",
  technical_quality: "fail",
  compliance: "pass",
  issues: ["garment color differs from source image", "visible seam artifact"],
});

describe("W3 VLM 质检闭环（AC-3）", () => {
  it("评审输入引用模型返回的图片 URL（IFACE-2 链路约束）", () => {
    const prompt = qc.buildReviewPrompt?.(URL) ?? "";
    expect(prompt.length).toBeGreaterThan(0);
    expect(prompt).toContain(URL);
  });

  it("四维评审记录为机器可解析结构化记录（IFACE-2）", () => {
    const record = reviewOf(URL, failingReview);
    expect(record.imageUrl).toBe(URL);
    expect(Object.keys(record.dimensions).length).toBe(QC_DIMENSIONS.length);
    for (const dimension of QC_DIMENSIONS) {
      expect(record.dimensions[dimension]).toBe(
        JSON.parse(failingReview)[dimension],
      );
    }
    expect(record.issues).toContain("garment color differs from source image");
    expect(record.reviewedAt.length).toBeGreaterThan(0);
  });

  it("不合格记录判定 passed 为 false，合格记录为 true", () => {
    expect(reviewOf(URL, failingReview).passed).toBe(false);
    expect(reviewOf(URL, passingReview).passed).toBe(true);
  });

  it("解析失败时保守判定不合格（fail-closed，INV-1 不得绕过）", () => {
    const record = reviewOf(URL, "not-json-at-all");
    expect(record.passed).toBe(false);
    expect(record.issues.length).toBeGreaterThan(0);
    expect(record.imageUrl).toBe(URL);
  });

  it("重生成计数与 BUDGET-2 上限：0/1 次重生成，第 2 次后走兜底", () => {
    const record = reviewOf(URL, failingReview);
    expect(planOf(record, 0).action).toBe("regenerate");
    expect(planOf(record, 1).action).toBe("regenerate");
    expect(planOf(record, 2).action).toBe("fallback");
    expect(planOf(reviewOf(URL, passingReview), 0).action).toBe("accept");
  });

  it("不合格重生成计划携带评审反馈（BEH-3 反馈透传）", () => {
    const record = reviewOf(URL, failingReview);
    const plan = planOf(record, 0);
    expect(plan.action).toBe("regenerate");
    expect(plan.feedback ?? "").toContain("garment color differs");
  });
});
