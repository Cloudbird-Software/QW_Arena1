# Changelog

本文件记录对外可见的变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

### Added
- 初始模板工程（CI gate / hygiene / dependabot / automerge 全套护栏）。
- `src/visual` 模块：品类构图模板资产与查询面（`compositionFor` / `listCompositionAssets`）。
- `src/visual` 模块：三市场视觉词典资产与图像提示词组装（`listMarketDictionaryEntries` / `buildImagePrompt`）。
- `src/visual/qc` 子模块：VLM 质检闭环——四维评审结构化记录与重生成决策（`reviewImage` / `planRegeneration` / `buildReviewPrompt`）。
- `src/visual/stability` 子模块：输出稳定性控制——固定种子与四类失败模式负面提示词（`buildGenerationRequest` / `listNegativePromptEntries`）。
- `src/render` 模块：尺码表详情图本地渲染——白底 SVG、三语字体嵌入、零模型调用（`renderSizeChart` / `listFontAssets`）。
- `src/fallback` 模块：单级兜底——图片源图裁剪加本地合成、视频图片轮播，无多级模型轮换（`planFallback` / `listFallbackStrategies`）。
- `src/inspection` 模块：产物规格校验与强制规格化——主图白底方图 ≥1200、详情图 ≥900、单张 ≤4.5MB（`inspectImage` / `normalizeImage` / `listSpecThresholds`）。
