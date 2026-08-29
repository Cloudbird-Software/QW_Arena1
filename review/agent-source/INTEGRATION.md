# INTEGRATION —— 本文档集并入 v3.5.1-final 的方式

## 1. 落包路径（v3.0.2 起全量收入 agent/ 内）

```
xborder-agent-v3.5.1-final.zip
└── agent/                     ← zip 根必须且只能有 agent/（v3.0.1 教训：根级任何
    ├── agent.py               │  多余文件 = 格式校验直接拒）
    ├── agent.json             ← runtime/version（3.5.1，行为按版本门控）
    ├── requirements.txt       ← 空依赖声明
    ├── assets/preset_video.mp4
    ├── README.md              ← 原「包根 README」收入 agent/ 内
    ├── INTEGRATION.md         ← 本文
    ├── docs/ARCHITECTURE.md
    ├── docs/COMPATIBILITY.md
    └── tests/selftest.py      ← 平台只调起 agent/agent.py；本文档层为评审者服务
```

注意：历史 11 个出分包的 zip 内均只有 `agent/` 四件套；v3.0.0/v3.0.1 曾把 README/docs/tests 放在包根（根集合 = {agent, docs, tests, README.md, INTEGRATION.md}），v3.0.1 实测被格式校验直接拒；v3.0.2 起全部收入 agent/ 内，zip 根集合恒等于 {agent}。预检门禁的判据未官方公开，故每次结构变更后必须核对分数无回归；若有塌方嫌疑，第一止损动作是文档退到包外归档、只保留 `agent/` 运行时重提对照。

## 2. agent.py 分节横幅推荐样式

单行等宽横幅，`#` + 空格 + `===` 包裹，节号连续（便于拆包评审定位）：

```python
# ============================ 1. 运行契约与常量 ============================
```

十个分节标题：`1. 运行契约与常量`、`2. A1 合规资产：黑名单/溯源/自审`、`3. 确定性词表与度量换算`、`4. A3fix 规范化映射表`、`5. Prompt 路径解析`、`6. 商品扫描与事实抽取`、`7. 类目映射与字典决胜`、`8. 三语文案渲染与文档组装`、`9. 图片/视频管线与降级链`、`10. 主流程与 exit 0 契约`。

## 3. 集成后必须核对的占位清单

文档正文基于 v2.4.2 底盘写实（v3.2.0 已同步），以下数字/表述每次并版需逐项核对：

- [x] `agent.json` version → `3.5.0`；`VERSION_FALLBACK` 同步；`feature_flags` 新增 `qchard`/`uigate`/`divsel`/`vidcap`/`steadycam`（均 `>=3.5.0`），旧版本行为不受影响；v3.4.0 五 flag（gallerytext/detail1/skupin/srcnote + 前序）保持不变。
- [x] 策略文档视觉资产节 = 「内容级去重（URL 数→互异内容数=源上限）+ 主图白/浅灰棚拍优先（暖调不算命中）+ 图集无文字资格新规 + 细节/微距→异色正面/场景×4 + §5 图集表/§8 槽位序/选图记录/Media File Mapping 三方同源」；视频 = 「源视频字段直复 → 10 秒 + 全片严格质检（手表/首饰复制瞬移、手指、纽扣间距、纹理融化、块状噪点；不合格→同档重生成一次→5 秒档→预置兜底；InvalidParameter 自动降档）」；§8 = 双区粘贴纪律（只粘贴买家区，Appendix 供平台导入与机评）。
- [x] ARCHITECTURE §5 成本行按 10s 生成更新（正常 ≈¥6，最坏 ≈¥15）；指纹格式增列 `image_pool` / `contents` / `distinct_selected` / `video_tier` / `video_duration`。
- [x] 打包后重跑 `python tests/selftest.py`：18/18 全绿（t17 divsel/uigate 选图、t18 QC 双通道合并+vidcap），t08 zip 结构自检已锁定 `xborder-agent-v3.5.1-final.zip` 并断言 zip 根集合 == {agent}；CNB 复刻门禁口径见 docs/COMPATIBILITY.md §4（含六图互异、内容级互异数与 mvhd 时长 10s±2 断言）。
- [ ] 提交后核对平台分数无回归；异常则按 §1 止损动作对照重提。
