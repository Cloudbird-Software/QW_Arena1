// 产物规格校验模块入口（IR-0001 W7 / 卡 #12，BEH-7、INV-3、INV-4）。
// 图片产物落盘后运行规格校验（主图白底方图 ≥1200 / 详情图 ≥900 / 单张
// ≤4.5MB），不满足者产出强制规格化动作计划；阈值为可枚举配置资产。
import { MAX_IMAGE_BYTES, MIN_SIDES, SPEC_THRESHOLDS } from "./thresholds.js";
import type { InspectableRole, SpecThreshold } from "./thresholds.js";

export type { InspectableRole, SpecThreshold } from "./thresholds.js";

/** 待检图片产物（落盘元数据）。 */
export interface ImageArtifact {
  role: InspectableRole;
  width: number;
  height: number;
  bytes: number;
  background: string;
}

/** 一条规格违规（机器可解析）。 */
export interface ImageFinding {
  rule: string;
  message: string;
}

/** 强制规格化计划：违规与动作一一对应（BEH-7）。 */
export interface NormalizationPlan {
  artifactRole: InspectableRole;
  actions: string[];
}

/** 一条规格规则：判定 + 对应的强制规格化动作（BEH-7 违规与动作一一对应）。 */
interface ImageRule {
  id: string;
  message: string;
  action: string;
  violated: (artifact: ImageArtifact) => boolean;
}

const IMAGE_RULES: readonly ImageRule[] = [
  {
    id: "min-side",
    message: "shortest side below the role minimum",
    action: "resize-crop-to-min-side",
    violated: (a) => Math.min(a.width, a.height) < MIN_SIDES[a.role],
  },
  {
    id: "main-square",
    message: "main image is not square",
    action: "center-crop-square",
    violated: (a) => a.role === "main_image" && a.width !== a.height,
  },
  {
    id: "main-white-background",
    message: "main image background is not pure white",
    action: "recomposite-white-background",
    violated: (a) => a.role === "main_image" && a.background !== "white",
  },
  {
    id: "size-budget",
    message: "image exceeds the per-file byte budget",
    action: "recompress-under-budget",
    violated: (a) => a.bytes > MAX_IMAGE_BYTES,
  },
];

function violationsOf(artifact: ImageArtifact): readonly ImageRule[] {
  return IMAGE_RULES.filter((rule) => rule.violated(artifact));
}

/**
 * 规格校验（BEH-7）：返回全部违规；空清单=合规。
 */
export function inspectImage(artifact: ImageArtifact): ImageFinding[] {
  return violationsOf(artifact).map((rule): ImageFinding => ({
    rule: rule.id,
    message: rule.message,
  }));
}

/**
 * 强制规格化计划（BEH-7 then）：每条违规映射其规则声明的本地处理动作；
 * 合规产物动作清单为空。
 */
export function normalizeImage(artifact: ImageArtifact): NormalizationPlan {
  const actions = violationsOf(artifact).map((rule) => rule.action);
  return { artifactRole: artifact.role, actions };
}

/**
 * 全量阈值清单（INV-3：可枚举配置资产，逐条可回查）。
 */
export function listSpecThresholds(): SpecThreshold[] {
  return SPEC_THRESHOLDS.map((threshold): SpecThreshold => ({ ...threshold }));
}
