// 产物规格校验（v2 官方 A2 口径：主图 ≥800×800、详情 >260、单张 ≤5MB、
// 文本 <1MB、视频 <200MB）。确定性本地校验（尺寸/字节），不调用模型；
// 违规 → 降级裁决（顺序降级并留痕 result.json）。
// 注：仓内既有 src/inspection 为 W7 的 ≥1200/≥900/4.5MB 规格（specs/IR-0001），
// 语义不同且不可改；本模块按 v2 交付包口径平行落 pipeline 层（管线唯一 QC 入口）。

interface ImageArtifact {
  role: string;
  width: number;
  height: number;
  bytes: number;
}

export interface ImageFinding {
  rule: string;
  message: string;
}

const MAIN_MIN_SIDE = 800;
const DETAIL_MIN_SIDE = 260;
const MAX_IMAGE_BYTES = 5_000_000;
const MAX_TEXT_BYTES = 1_000_000;
const MAX_VIDEO_BYTES = 200 * 1024 * 1024;

const MIN_SIDES: Record<string, number> = {
  main_image: MAIN_MIN_SIDE,
  detail_image: DETAIL_MIN_SIDE,
  // 场景图（detail_image_4/5 的 role）同样按详情图下限 >260 校验
  scene_image: DETAIL_MIN_SIDE,
};

interface ImageRule {
  id: string;
  message: string;
  violated: (a: ImageArtifact) => boolean;
}

const IMAGE_RULES: ImageRule[] = [
  {
    id: "min-side",
    message: "shortest side below the role minimum",
    violated: (a) =>
      Math.min(a.width, a.height) < MIN_SIDES[a.role || "detail_image"]!,
  },
  {
    id: "main-square",
    message: "main image is not square",
    violated: (a) => a.role === "main_image" && a.width !== a.height,
  },
  {
    id: "size-budget",
    message: "image exceeds the per-file byte budget",
    violated: (a) => a.bytes > MAX_IMAGE_BYTES,
  },
];

const ACTIONS_BY_RULE: Record<string, string> = {
  "min-side": "resize-crop-to-min-side",
  "main-square": "center-crop-square",
  "size-budget": "recompress-under-budget",
};

/**
 * 规格校验：返回全部违规；空清单=合规。
 * artifact: {role, width, height, bytes}
 */
export function inspectImage(artifact: ImageArtifact): ImageFinding[] {
  return IMAGE_RULES.filter((rule) => rule.violated(artifact)).map((rule) => ({
    rule: rule.id,
    message: rule.message,
  }));
}

/** 强制规格化计划：每条违规映射一个本地处理动作。 */
export function normalizeImage(artifact: ImageArtifact): {
  artifactRole: string;
  actions: string[];
} {
  const findings = inspectImage(artifact);
  const actions = findings.map(
    (finding) => ACTIONS_BY_RULE[finding.rule] ?? "re-encode",
  );
  return { artifactRole: artifact.role, actions };
}

/** 文本文件规格校验（<1MB）。 */
export function inspectText(bytes: number): ImageFinding[] {
  if (bytes >= MAX_TEXT_BYTES) {
    return [{ rule: "text-too-large", message: "text file must be < 1MB" }];
  }
  return [];
}

/** 视频文件规格校验（可播放优先：ftyp/box 签名 + 单文件 <200MB）。 */
export function inspectVideo(artifact: {
  bytes: number;
  hasBoxSignature: boolean;
}): ImageFinding[] {
  const findings: ImageFinding[] = [];
  if (!artifact.hasBoxSignature) {
    findings.push({
      rule: "video-box-signature",
      message: "not a valid mp4/mov container",
    });
  }
  if (artifact.bytes >= MAX_VIDEO_BYTES) {
    findings.push({
      rule: "video-too-large",
      message: "video must be < 200MB",
    });
  }
  return findings;
}

/** 阈值资产清单（官方 A2 口径，逐条可回查）。 */
export function listSpecThresholds(): Array<{
  key: string;
  value: number;
  unit: string;
}> {
  return [
    { key: "main_min_side", value: MAIN_MIN_SIDE, unit: "px" },
    { key: "detail_min_side", value: DETAIL_MIN_SIDE, unit: "px" },
    { key: "max_image_bytes", value: MAX_IMAGE_BYTES, unit: "bytes" },
    { key: "max_text_bytes", value: MAX_TEXT_BYTES, unit: "bytes" },
    { key: "max_video_bytes", value: MAX_VIDEO_BYTES, unit: "bytes" },
  ];
}
