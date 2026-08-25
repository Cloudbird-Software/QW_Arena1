// VLM 质检闭环模块入口（IR-0001 W3 / 卡 #8，BEH-3、INV-1、IFACE-2、BUDGET-2）。
// 评审输入引用模型返回的图片 URL（模型→URL→模型链路）；评审输出为机器可解析
// 结构化记录（四维判定 + 问题清单），供运行日志留痕与重生成决策消费。
import { QC_DIMENSIONS, REGENERATION_LIMIT } from "./dimensions.js";
import type { QCDimension } from "./dimensions.js";

export type { QCDimension } from "./dimensions.js";

/** 四维评审的结构化记录（IFACE-2：机器可解析 + 留痕运行日志）。 */
export interface QCReviewRecord {
  imageUrl: string;
  dimensions: Record<QCDimension, string>;
  issues: string[];
  passed: boolean;
  reviewedAt: string;
}

type RegenerationAction = "accept" | "regenerate" | "fallback";

/** 重生成决策：不合格携带反馈重生成（BEH-3），超限走兜底（BUDGET-2）。 */
export interface RegenerationPlan {
  action: RegenerationAction;
  feedback?: string;
}

interface RawReview {
  issues?: unknown;
  [dimension: string]: unknown;
}

/**
 * 评审输入提示词：引用模型返回的图片 URL（IFACE-2 链路约束）。
 */
export function buildReviewPrompt(imageUrl: string): string {
  return [
    "You are a strict e-commerce visual QC reviewer.",
    `Review the generated product image at ${imageUrl} against the source product facts.`,
    "Return JSON with a pass/fail verdict for each dimension (factual_consistency, composition, technical_quality, compliance) and an issues list.",
  ].join(" ");
}

/**
 * 解析模型评审输出为结构化记录；解析失败按 fail-closed 保守判不合格（INV-1：
 * VLM 质检闭环不得被降级路径替换或绕过——宁可误杀重生成，不可放过坏图）。
 */
export function reviewImage(
  imageUrl: string,
  rawReview: string,
): QCReviewRecord {
  const parsed = parseReview(rawReview);
  const dimensions = pickDimensions(parsed);
  const issues = issuesFrom(parsed);
  return {
    imageUrl,
    dimensions,
    issues,
    passed: passedFor(dimensions, issues),
    reviewedAt: new Date().toISOString(),
  };
}

/**
 * 重生成决策（BEH-3 + BUDGET-2）：合格放行；不合格且未超限携带评审反馈
 * 重生成；重生成次数用尽走兜底路径。
 */
export function planRegeneration(
  record: QCReviewRecord,
  attemptsUsed: number,
): RegenerationPlan {
  const action = decideAction(record, attemptsUsed);
  const feedback = feedbackFor(record);
  return action === "regenerate" ? { action, feedback } : { action };
}

function parseReview(raw: string): RawReview {
  try {
    return JSON.parse(raw) as RawReview;
  } catch {
    return { error: "unparseable review response" };
  }
}

function pickDimensions(parsed: RawReview): Record<QCDimension, string> {
  return Object.fromEntries(
    QC_DIMENSIONS.map((dimension) => [dimension, verdictOf(parsed, dimension)]),
  );
}

function verdictOf(parsed: RawReview, dimension: QCDimension): string {
  return parsed[dimension] === "pass" ? "pass" : "fail";
}

function issuesFrom(parsed: RawReview): string[] {
  const issues = parsed.issues;
  return Array.isArray(issues) ? issues.map(String) : ["issues list missing"];
}

function passedFor(
  dimensions: Record<QCDimension, string>,
  issues: string[],
): boolean {
  return (
    issues.length === 0 && QC_DIMENSIONS.every((d) => dimensions[d] === "pass")
  );
}

function decideAction(
  record: QCReviewRecord,
  attemptsUsed: number,
): RegenerationAction {
  if (record.passed) {
    return "accept";
  }
  if (attemptsUsed >= REGENERATION_LIMIT) {
    return "fallback";
  }
  return "regenerate";
}

function feedbackFor(record: QCReviewRecord): string {
  const failed = QC_DIMENSIONS.filter((d) => record.dimensions[d] === "fail");
  return [...failed, ...record.issues].join("; ");
}
