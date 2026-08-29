# xborder-material-agent v3.5.1-final

> **Current version: 3.6.2**（2026-08-29）。相对 v3.5.6 的差异：mainscene 默认关闭（代码保留 + XB_MAINSCENE=1 灰度）、上架一致性闸门（货号/品类名词/色码/人群口径/测量 sanity）、机评文本修复（A5 竞品脱敏、A3 源数据逐项对照表、A4 摘要前置）、视频三通道质检与构图锚定、打包 Pillow（仅 mainscene 使用）。历史版本叙述见下文。

一句话：纯 Python 标准库的单文件跨境商品素材 Agent —— 读取一个商品 JSON，确定性地产出恰好 11 个上架素材文件（三语文案 / 6 图 / 1 视频 / 策略文档），总以 exit 0 收口。提交史：20 次提交全部进入评分（无一静默失败），分数区间 54.17–84.72。

## 运行契约

```bash
python agent/agent.py --version          # 打印 agent.json 的 version，exit 0
python agent/agent.py --prompt "<任务文本>"   # 完整运行，恒 exit 0
```

- 运行环境：Debian 12 + Python 3.12，零第三方依赖，内存 <100MB。
- 输入/输出目录从 prompt 按关键词解析：取含 `input` 的路径为输入、含 `output` 的路径为输出（各取最后一个）；官方默认 `/home/user/ws/input|output`。关键词过滤保证 prompt 中的 `en/ko/pt` 等枚举片段不会被误认为路径。
- 模型调用仅需环境变量 `DASHSCOPE_API_KEY`；缺失时自动降级为全占位产出，进程仍 exit 0。

## 产物清单（恰好 11 个文件，不多不少）

| 文件 | 说明 |
|---|---|
| `product_description_en/ko/pt.md` | 双区三语文案：买家区（标题公式=材质+品类+人群+特征、Highlights 属性值自然语序嵌入、本地化属性零 CJK、SKU 汇总表+真实胸围/衣长 cm 列（供应商尺码表 VL-OCR 提取，失败不添加并如实记录；脚注只写 supplier-measured size chart，无 offerId/文件名）+码制对照列（US 体重段/KR 55-88/BR P-XGG，真实测量存在时降级辅助参考）、亚洲码偏小警示、色差声明、自然语言图文（颜色词 SKU 权威化，未命中写 as shown）、买家保障+平台能力句）+ Platform Data Appendix（SKU 全量唯一一份/类目映射/AE 对照/CJK 对照/Media File Mapping/自审/溯源） |
| `main_image.jpeg` + `detail_image_1..5.jpeg` | 内容级去重选图：图池=主图+SKU 图+description 字段内嵌图（v3.3.0 扩容：商品实测 55 条 URL → 32 张互异内容）；全池下载字节哈希分组（同内容留代表，互异数=源数据上限）→VL 分批打分（内容类型识别：尺码表/面料微距/背面/侧面/场景/主色 + 同镜头组判重，同姿势同构图组内只取一张）→图集无文字资格新规（v3.4.0：VL 判定含文字/水印/拼图的图一律出局，描述图不豁免；尺码表截图=数据源图仅 OCR 提数不入图集）→目标结构：main=白/浅灰棚拍正面（暖调/木纹/米黄墙不算命中，未命中如实记录；主图颜色 SKU 色点名，匹配成功即不写 as shown）、detail_1=细节/微距（真细节拼图优先）、detail_2..5=异色正面/场景×4；类别缺口如实记录；六图取自合格互异内容（互异内容 <6 张时溢出槽复用末张详情，兼容语义）；VL 失败回退源图顺序直投；下载失败全量切换 1024×1024 占位 PNG |
| `product_video.mp4` | 源数据自带视频字段直接复用（零生成风险）；否则 wan2.7-i2v 图生视频（720P/10s，首帧=最终选定主图；全片严格 VL 质检：手表/首饰复制瞬移、手指、纽扣间距、纹理融化、块状噪点——不合格同档重生成一次→5s 档→预置兜底；仅支持 5s 的版本/区域按 InvalidParameter 自动降档；实际档位与质检结论如实入指纹与报告） |
| `strategy_document.md` | 满配运营策略报告（单位经济 / 三市场 / 合规登记册） |

输出目录运行后与上述清单严格一致：无日志文件、无中间产物。

## 设计亮点

1. **Determinism first（确定性优先）**：文案零模型调用——路径解析、事实抽取、类目映射决胜、三语渲染、标题转写与营销导语全部为查表与规则；LLM 只用于 i2v 视频与值级翻译（后者带硬验证器，失败即回退中文原文）。
2. **全链路降级（graceful degradation）**：源图→重试×3→复活轮→占位 PNG；选图→内容级去重（URL 全池下载哈希分组）→VL 打分互异代表（主图白/浅灰棚拍优先、详情颜色覆盖）→VL 全失败回退源序直投；视频→源视频字段直复→i2v（10s→全片严格质检重生成→5s 档）→预置 mp4（assets 缺失时 base64 内嵌重建）；字典缺失→类目区块优雅跳过；24 分钟全局硬闸→各慢阶段短路兜底；启动即提前落盘 11 件兜底产物——任何时点被杀都有完整产物。
3. **平台兼容实证**：同期复杂工程化管线（Node，66 单测，watchdog/异步任务链）0/14 平台全败，本极简底盘 11/11 出分——对照实验定位为平台投递层预检门禁，详见 `docs/COMPATIBILITY.md` 的 decision record。
4. **诚实层（v3.2.0 起持续加固）**：自审表全部数字来自本次运行真实统计（图池 URL 数/内容级互异数/全文档 CJK 行数为最终渲染文本两遍复算）；尺码数据只来自供应商尺码表 OCR 并与 SKU 斤档交叉校验，提取失败不添加该列（下界），绝不编造；买家区不含内贸字段（货号/下游市场/跨境货源）、竞品平台名与编造样例数据；KR 发货时效只写「직배송 리드타임 참조」不做无法核实的当日发单承诺；PT 补 Pix·12x 平台标准能力句。

## v3.4.0 变更摘要（红队 Round 1-3 三轮合体修复）

- 图集重组（A）：gallery 无文字资格新规——VL has_text/水印/拼图图一律出局（d00 尺码截图、d02 中文横幅自动出局；d00 转为「数据源图」仅供 OCR 提数）；真细节拼图启用为 detail_1（VL 判无文字为前提，细节类优先；否则六图=主图+四色场景+最佳剩余）。
- 三方同源（A/F1）：选图定稿后 §5/§8 图集表、Run Report 选图记录、Appendix Media File Mapping 三处由同一份 slots 元数据渲染，杜绝选图记录与实际字节错位。
- 泄露与一致性（B/F2/F5）：买家区尺码表脚注改「supplier-measured size chart」（无 offerId 无文件名，溯源细节只在 Appendix）；Appendix 新增源数据冲突注记（属性衣长 vs 尺码表数值冲突时「listed per source; chart takes precedence for measurements」）。
- 文案收尾（C/F6-F14）：PT 去「sem juros」免息承诺；EN/PT/KO 涤纶改「lightweight/leve/가벼운」不宣称透气；EN 尺码表方向词 above；KO 尺码建议统一「1~2 사이즈 크게」；EN/PT 删韩码说明残留；PT 句首大写修正；主图颜色直接点名 SKU 色（匹配成功时不再回避）；KO 싱글 브레스티드 / PT Single Breasted (abotoamento frontal)。
- 自审扩展（D）：自审表新增「图内文字扫描（最终六图）」与「场景第三方商标」两行（VL 实测，含数据源图身份与备用池道具风险注记）；合规登记册新增视频音轨行（模型生成环境音，无第三方音乐）。
- 策略文档（E）：§5/§8 按最终图集回写；KR 口径统一 55-88（S 起）与 KO 表一致；BR 口径 P/M/G/GG/XGG 与 PT 表一致；删除「44-88 全段」「PP-P-G-GG」旧口径。

## v3.5.1 变更摘要（亲验闭环：终筛换图 + 文案去冗余）

v3.5.0 真实产物二次亲验：近似重复已消除、视频明显干净（双通道质检放行可辩护），但 detail_5 底部 "▼" 翻页箭头仍在——20 字段一般化批量打分对小幅 UI 残留显著性不足，has_ui_symbols 漏判，资格门拦不住。

- 图集终筛（rescreen）：对最终六图做一次高显著度定向追问（"上下边缘白色横带内含黑色三角/箭头/角标？"），命中即换入合格备选（备选取合格+未用+视觉距离最大者；主图不换）；换图发生在 slots 三方同源渲染之前，§5/§8/Media File Mapping 自动一致；无备选时如实披露（residual）。新增 1 次 VL 调用/商品。
- vidcap 姿态短语去冗余：cat=front 且 pose=front 时不再重复追加 "shown from the front"。

## v3.5.0 变更摘要（视觉亲验迭代——评审者亲看产物后的修复）

本版动机：v3.4.0 真实产物经逐帧/逐图人工检视发现三类硬伤——视频伪影漏检（~2s 手表复制、4-6s 门襟融化、6-9s 块状噪点均被单次宽松 VL 质检放行）、图集视觉级近似重复（detail_2/detail_5 同拍摄同姿势仅裁切不同）与 UI 符号残留（detail_5 底部 ▼）、文案模板感（图文五行同句式、视频描述仅一行）。

- 视频双通道质检（qchard）：原全片严格检之外新增对抗严格检（明确列出 i2v 已知伪影清单，temp 0.3），任一通道任一缺陷命中即不合格，顺延既有重生成→5s 档→预置兜底梯子；两通道均不可用仍如实标 skip。
- 生成侧降险（steadycam + divsel 首帧）：i2v 运动 prompt 由 dolly-in 推近改为静止机位+面料轻摆（推近特写正是手表/纽扣复制伪影高发区）；首帧在主图配饰负担（VL accessory_load）过高时改选低配饰槽位。
- 视觉级去重选图（divsel）：VL 屏幕新增 pose/accessory_load/has_ui_symbols/letterbox 字段（零新增调用，扩展既有分批打分）；选图排序引入「与任一已选的最小视觉距离」（颜色/姿态/场景/视角），同机位近似重复不再入图集；备选不足时如实记录。
- 图集资格门扩展（uigate）：UI 符号残留（▼▲►★●等角标箭头）与均匀留白边框（letterbox）一律出局，计入自审披露。
- 文案差分化（vidcap）：Image Descriptions 按 VL 姿态标签逐行差分（三语短语白名单渲染）；Video Description 按实际视频终态渲染（i2v 写实测秒数与首帧同源声明，preset 兜底如实写兜底），视频落定后三语文档重写一遍。
- 自审与策略：自审表补 UI 剔除披露与分隔符修正；策略文档 §5 增视觉级去重与双通道质检陈述（仅 3.5.0+）。

## v3.3.0 变更摘要（红队 Round 2 合并修复 + 内容级升级）

- 图池扩容：description 字段（详情页 HTML）内嵌图全部入池（<img src> 与裸 URL 双通道提取，保序去重）。
- 选图升级：VL 分批多图打分（新字段 is_size_chart/is_fabric_macro/is_side_view/same_shot_group）；六槽目标结构对标真实 listing；同镜头组组内只取一张。
- 真实尺码数据：qwen3.5-ocr 读供应商尺码表图提取每码档胸围/衣长 cm，交叉校验后写入三语买家区 SKU 表；删除 KO 编造胸围句。
- 色标权威化：买家区颜色词一律取 SKU 颜色值（URL 文件名色优先，VL 主色须命中 SKU 色），修三语 blue 错标。
- 码表修正：KR 44-88（88=plus，删自造 99/99+）；US 参考列按主流体重对照修正。
- 买家区净化：删 linter 行/编造样例/deterministic 措辞/内贸字段；图文清单改自然语言（文件名对照移 Appendix）；PT 重音全量修复（模板常量根因）。
- 口径修正：全文档 CJK 行数两遍复算（三语同源生成）；附录类目映射行值补翻；策略文档与 §2/§3/§5/§6 与新行为对齐（KR 44-88、竞品带注① 统一、敏感性舍入口径统一）。

## 目录结构

```
agent/                 运行时主体（平台调起层，平台兼容纪律全在此层）
  agent.py             单文件底盘（~2600 行，10 节横幅，见 INTEGRATION.md §2）
  agent.json           runtime/version（行为按版本门控）
  assets/preset_video.mp4   视频兜底资产
  requirements.txt     空依赖声明
docs/ARCHITECTURE.md   架构、可靠性设计与工程决策记录
docs/COMPATIBILITY.md  平台兼容性调查实录与打包纪律
tests/selftest.py      零依赖离线自检（python tests/selftest.py）
INTEGRATION.md         集成者说明（本文档集并入包的方式）
```

## 如何验证

```bash
python tests/selftest.py    # 离线自检：路径陷阱/黑名单边界/词表往返/占位 PNG/stub 11 文件/zip 结构/mvhd 时长/互异选图去重与回退
```

发布门禁：打包后在 CNB 云端 1:1 复刻官方验证环境（Debian12 + Py3.12 + squid 白名单）完整跑通——`--version` → 官方 prompt 全运行 → 11 文件清点 → 图片字节数断言（真 JPEG 而非占位 PNG）→ exit 0，全绿方可提交。复现步骤见 `docs/COMPATIBILITY.md` 第 4 节。
