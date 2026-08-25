// 品类构图模板数据资产（IR-0001 W1 / 卡 #6，BEH-1、INV-3、IFACE-1）。
// 纪律：本文件是唯一构图指令来源——全部条目可枚举、禁止散落于自由文本；
// 改动条目=改变视觉输出，须与 specs/IR-0001 对应条款对齐。

/** 图像角色：主图（白底本体）、详情图（参考锚定）、场景图（允许纯文生图，INV-2）。 */
export type ImageRole = "main_image" | "detail_image" | "scene_image";

/** 服装品类（与尺码表分组同口径：上装/下装/连衣裙/外套）。 */
export type GarmentCategory = "tops" | "bottoms" | "dresses" | "outerwear";

/** 可枚举资产清单的一条记录（IFACE-1：输入到输出的映射可枚举审查）。 */
export interface CompositionAsset {
  category: GarmentCategory;
  role: ImageRole;
  directive: string;
}

export const IMAGE_ROLES: readonly ImageRole[] = [
  "main_image",
  "detail_image",
  "scene_image",
];

export const GARMENT_CATEGORIES: readonly GarmentCategory[] = [
  "tops",
  "bottoms",
  "dresses",
  "outerwear",
];

export const COMPOSITION_TEMPLATES: Record<
  GarmentCategory,
  Record<ImageRole, string>
> = {
  tops: {
    main_image:
      "front-facing top laid flat and centered on a pure white seamless background, shoulders symmetrical, garment filling 80% of frame, invisible-mannequin styling, no model, no props",
    detail_image:
      "extreme close-up on the collar, placket and fabric weave of the top, angled 45 degrees, texture filling the entire frame, shallow depth of field",
    scene_image:
      "top worn by a model in rule-of-thirds placement against a minimal sunlit studio scene, soft daylight from the left, garment as the single focal point",
  },
  bottoms: {
    main_image:
      "front-facing trousers or skirt centered vertically on a pure white seamless background, waistband at top frame edge, garment filling 80% of frame, invisible-mannequin styling, no model, no props",
    detail_image:
      "extreme close-up on the waistband, stitching and hardware of the bottoms, angled 45 degrees, texture filling the entire frame, shallow depth of field",
    scene_image:
      "bottoms worn by a walking model in rule-of-thirds placement on a clean urban pavement, natural afternoon light, garment as the single focal point",
  },
  dresses: {
    main_image:
      "full-length front-facing dress centered on a pure white seamless background, silhouette symmetrical, hem at bottom frame edge, garment filling 85% of frame, invisible-mannequin styling, no model, no props",
    detail_image:
      "close-up on the bodice seam, waistline and fabric drape of the dress, angled 30 degrees, drape filling the entire frame, shallow depth of field",
    scene_image:
      "dress worn by a standing model in centered symmetrical placement in an airy open field, golden-hour backlight, garment as the single focal point",
  },
  outerwear: {
    main_image:
      "front-facing outerwear jacket or coat centered on a pure white seamless background, arms relaxed and symmetrical, garment filling 85% of frame, invisible-mannequin styling, no model, no props",
    detail_image:
      "extreme close-up on the lapel, zipper or buttons and shell fabric of the outerwear, angled 45 degrees, texture filling the entire frame, shallow depth of field",
    scene_image:
      "outerwear worn by a model in rule-of-thirds placement against a cool overcast city backdrop, diffused daylight, garment as the single focal point",
  },
};
