// 三语字体资产清单（IR-0001 W5 / 卡 #10，BEH-5 配套）。
// 纪律：三语字体（EN/KO/PT）随产物包打包——路径常量即打包清单，可枚举审查。

/** 尺码表渲染的目标市场（与视觉管线三市场同口径）。 */
export type ChartMarket = "EN" | "KO" | "PT";

/** 打包字体资产（market → family/path 映射可枚举）。 */
export interface FontAsset {
  market: ChartMarket;
  family: string;
  path: string;
}

export const FONT_ASSETS: readonly FontAsset[] = [
  {
    market: "EN",
    family: "Noto Sans",
    path: "assets/fonts/NotoSans-Regular.ttf",
  },
  {
    market: "KO",
    family: "Noto Sans KR",
    path: "assets/fonts/NotoSansKR-Regular.otf",
  },
  {
    market: "PT",
    family: "Noto Sans",
    path: "assets/fonts/NotoSans-Regular.ttf",
  },
];
