# src/render —— 本地渲染模块（IR-0001 W5）

## 职责

零模型调用的确定性本地渲染：尺码表详情图（SVG，白底，三语字体嵌入）。
字体打包清单在 fonts.ts（可枚举资产）。

## 不变量

- 渲染路径全程零模型调用、零网络（BEH-5）——`RenderDeps.noteModelCall`
  仅供管线审计注入，本模块永不调用。
- 相同输入产出完全一致（确定性）。

## 禁止

- 不引入图像处理第三方依赖（stdlib only）。
- 不做模型调用或提示词组装（归 src/visual）。

## 独立验证

`make test tests/card-10-w5-sizechart-render.test.ts`
