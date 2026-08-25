// 产物规格阈值数据资产（IR-0001 W7 / 卡 #12，BEH-7、INV-3、INV-4）。
// 纪律：本文件是唯一阈值来源（可枚举、可审查）——禁止在其它文件散落
// 硬编码规格数字；阈值变更须与 specs/IR-0001 对应条款对齐。

/** 受检图片产物角色。 */
export type InspectableRole = "main_image" | "detail_image";

/** 可枚举阈值条目。 */
export interface SpecThreshold {
  key: string;
  value: number;
  unit: string;
}

/** 主图最短边下限（像素）。 */
export const MAIN_MIN_SIDE = 1200;

/** 详情图最短边下限（像素）。 */
export const DETAIL_MIN_SIDE = 900;

/** 单张图片体积上限（字节，4.5MB——INV-4 提交包 100MB 的下游保障）。 */
export const MAX_IMAGE_BYTES = 4_500_000;

export const MIN_SIDES: Record<InspectableRole, number> = {
  main_image: MAIN_MIN_SIDE,
  detail_image: DETAIL_MIN_SIDE,
};

export const SPEC_THRESHOLDS: readonly SpecThreshold[] = [
  { key: "main_min_side", value: MAIN_MIN_SIDE, unit: "px" },
  { key: "detail_min_side", value: DETAIL_MIN_SIDE, unit: "px" },
  { key: "max_image_bytes", value: MAX_IMAGE_BYTES, unit: "bytes" },
];
