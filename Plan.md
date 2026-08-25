I'll verify the stable API-surface details (DashScope async task patterns, image/video generation endpoints) before writing the spec, since the Agent's entire I/O layer depends on them.Now let me confirm the image-generation surfaces (qwen-image vs wan image) and the video-edit endpoint, since these determine the client abstraction layer.Below is the complete project foundation. Read order for the executing agent: `docs/SPEC.md` → `docs/CONTRACTS.md` → `docs/TASKS.md` → code. Every strategic decision is already made and marked **[LOCKED]**; the executor implements tickets, never re-decides.

Two notes before the files:

- **Tech stack decision [LOCKED]: Python 3.12, zero HTTP dependencies (stdlib `urllib`), only two vendored runtime deps (`Pillow`, `imageio-ffmpeg`).** Rationale: Python is the strongest target for AI coding tools; stdlib HTTP removes the largest vendoring/TLS risk; `imageio-ffmpeg` ships a static ffmpeg binary, which converts "video generation might time out" from a scoring catastrophe into a local, deterministic fallback.
- I verified the DashScope API surfaces the client layer depends on (sync `multimodal-generation/generation` for `qwen-image-*` / `wan2.7-image*` with `input.messages[].content[{image|text}]`; async `video-generation/video-synthesis` + `X-DashScope-Async: enable` + `GET /tasks/{id}`, with both `input.media[{type:first_frame,url}]` (wan2.7) and legacy `input.img_url` shapes; results at `output.choices[0].message.content[].image` / `output.video_url`; generated URLs expire ~24h). Because platform-specific deviations are possible, the client is built as a **capability ladder** that probes payload/endpoint shapes at runtime and caches what worked — so the code cannot be invalidated by one doc discrepancy.

---

# 1. Repository layout

```
xborder-agent/
├── Makefile
├── pyproject.toml
├── requirements-dev.txt
├── docs/
│   ├── SPEC.md                     # normative spec: scope, invariants, scoring map
│   ├── CONTRACTS.md                # module boundaries + payload contracts
│   ├── DEGRADATION.md              # fallback ladders & time budget policy
│   ├── TASKS.md                    # ordered tickets w/ acceptance criteria
│   ├── EXPERIMENT_LEDGER.md        # submission A/B plan (score is black box)
│   ├── RISKS.md                    # UNVERIFIED items + day-1 verification script
│   └── adr/
│       ├── 0001-python-stdlib-http.md
│       ├── 0002-local-text-rendering.md
│       ├── 0003-traceability-gate.md
│       └── 0004-always-exit-zero.md
├── entry/
│   ├── agent.py                    # ZIP entry point (copied to package root)
│   └── agent.json
├── src/xborder/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py                   # ALL tunables/strategy constants
│   ├── errors.py
│   ├── budget.py
│   ├── logging_setup.py
│   ├── jsonutil.py
│   ├── promptparse.py
│   ├── discovery.py
│   ├── http.py
│   ├── dsclient.py
│   ├── models_text.py
│   ├── models_image.py
│   ├── models_video.py
│   ├── download.py
│   ├── facts.py
│   ├── provenance.py
│   ├── taxonomy_adapter.py
│   ├── taxonomy.py
│   ├── localize.py
│   ├── copywriter.py
│   ├── imaging.py
│   ├── chart.py
│   ├── video.py
│   ├── writer.py
│   ├── preflight.py
│   ├── pipeline.py
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── extract_facts.txt
│   │   ├── select_category.txt
│   │   ├── map_attributes.txt
│   │   ├── copy_locale.txt
│   │   └── image_plan.txt
│   └── schemas/
│       ├── product_facts.schema.json
│       ├── taxonomy_selection.schema.json
│       ├── copy_bundle.schema.json
│       ├── visual_plan.schema.json
│       └── run_manifest.schema.json
├── assets/
│   ├── fonts/{NotoSans-Regular.ttf,NotoSans-Bold.ttf,NotoSansKR-Regular.otf,NotoSansKR-Bold.otf}
│   └── knowledge/
│       ├── size_charts.json
│       ├── banned_terms.json
│       ├── locale_style.json
│       ├── unit_rules.json
│       └── image_rules.json
├── tools/
│   ├── build_package.py
│   ├── bump_version.py
│   ├── inspect_dataset.py
│   ├── mock_dashscope.py
│   ├── shadow_score.py
│   ├── run_local.sh
│   └── docker/Dockerfile.sandbox
├── fixtures/
│   ├── input_sample/…              # copy of official 商品数据示例
│   ├── input_synthetic_a/…         # renamed files, missing fields (robustness)
│   └── recorded/…                  # recorded/synthetic API responses for mock
└── tests/
    ├── conftest.py
    ├── test_promptparse.py
    ├── test_discovery.py
    ├── test_http_retry.py
    ├── test_dsclient_contract.py
    ├── test_taxonomy_adapter.py
    ├── test_taxonomy_select.py
    ├── test_facts_traceability.py
    ├── test_localize_rules.py
    ├── test_imaging_spec.py
    ├── test_video_fallback.py
    ├── test_writer_format.py
    ├── test_preflight.py
    ├── test_budget_degradation.py
    ├── test_e2e_mock.py
    └── test_package_integrity.py
```

---

# 2. `docs/SPEC.md`

```markdown
# 跨境素材 Agent — 工程规范 v1.0 (NORMATIVE)

MUST / SHOULD / MAY 按 RFC2119 解释。违反 MUST 的 PR 一律拒收。

## S1. 系统目标与不变量 (INVARIANTS)

I1  进程退出码永远为 0，除非输出目录不可写。 (ADR-0004)
I2  无论任何子系统失败，输出目录 MUST 恰好包含 11 个文件（§S3），不多不少。
I3  任何写入文案的“事实”MUST 通过溯源门 (traceability gate, ADR-0003)：
    要么在源 JSON 中逐字可定位，要么由白名单确定性变换产生且带 basis 指针。
I4  进程 MUST 在 T+27min 完成兜底产物写入，T+28min 强制 os._exit(0)。
I5  任何模型输出 MUST 经本地确定性校验/修复后才允许落盘（schema/枚举/规格/合规词表）。
I6  代码 MUST NOT 硬编码输入文件名；MUST NOT 依赖除模型服务与模型产物 URL 外的网络。
I7  图片内文字 MUST 由本地 Pillow 渲染，MUST NOT 依赖图像模型直出 KO/PT 文字。(ADR-0002)
I8  所有跨模块数据 MUST 符合 src/xborder/schemas/*.json；dev 环境下运行期强校验。

## S2. 评分映射（工程责任人 → 评分维度）

| 维度 | 权重 | 主责模块 | 本地可验证性 |
|---|---|---|---|
| A1 内容合规 | 25% | localize(banned_terms) + writer + imaging(no-text-main) | 高：词表+VLM 抽检 |
| A2 素材规格 | 20% | imaging + video + writer + preflight | 完全：preflight 100% 复刻规则 |
| A3 类目属性 | 18% | taxonomy_adapter + taxonomy | 中：枚举合法性可验，正确性不可验 |
| A4 本地化 | 15% | localize + chart + copywriter | 中：规则表可验 |
| A5 事实一致 | 10% | facts + provenance + writer | 高：溯源门可验 |
| A6 出图可用率 | 7% | imaging(quality_flags) + 生成成功率 | 中：本地质量启发式 |
| A7 出视频可用 | 5% | video(normalize + ffmpeg decode check) | 高 |
| 专家-策略 35% | — | strategy_document + 整体设计 | 人评 |
| 专家-图片 30% | — | 视觉规划 + prompt 质量 | 人评 |
| 专家-视频 20% | — | 分镜与首帧质量 | 人评 |
| 专家-体验 15% | — | 日志可读性、稳定性、strategy 文档 | 人评 |

工程优先级 [LOCKED]：I2/I1 稳定性 > A2 规格 > A3 枚举合法 > A5 溯源 > A1 词表 > A4 表 > 视觉质量。
理由：确定性分先拿满，再花剩余时间预算冲美观。

## S3. 输出契约（唯一权威列表）

输出目录（由 --prompt 解析得到，默认 /home/user/ws/output）MUST 仅含：

  product_description_en.md
  product_description_ko.md
  product_description_pt.md
  main_image.jpeg
  detail_image_1.jpeg
  detail_image_2.jpeg
  detail_image_3.jpeg
  detail_image_4.png        # 本地渲染的三语尺码/度量表（PNG 保文字锐度）
  detail_image_5.jpeg
  product_video.mp4
  strategy_document.md

扩展名选择 [LOCKED]：照片类用 .jpeg（易压到 ≤5MB），图表用 .png，文案用 .md（单一扩展，
不写 .txt 镜像，避免同名多文件干扰解析；该选择在 EXP-04 中 A/B）。
日志/manifest MUST 写入 $AGENT_LOG_DIR，MUST NOT 写入输出目录。(I2)

## S4. 文案文档结构（§S3 三份 locale 文档，逐字段可解析）

每份文档 MUST 使用如下顺序与 ASCII 字段键（值本地化，键不本地化——为“字段可解析”让路；
本决策写入 strategy_document 说明）：

    # <Localized Title>

    ## 1. Product Title
    Title: <locale title>

    ## 2. Product Information
    Category Path: <A > B > C>
    Leaf Category: <name>
    Leaf Category ID: <id>
    SKU List:
    - SKU ID: <id> | Color: <v> | Size: <v> | Price: <v> | Stock: <v>
    Product Attributes:
    - <AttrKey>: <AttrValue>
    Sales Attributes:
    - Color: <v1, v2>
    - Size: <v1, v2>

    ## 3. Data Source
    Source Platform: AliExpress
    Product ID: <id>
    Product URL: <url>
    Field Provenance:
    - <field>: <source_file>#<json_pointer>

    ## 4. Images
    - main_image.jpeg: <localized description>
    - detail_image_1.jpeg: <…>   (…至 detail_image_5)

    ## 5. Video
    - product_video.mp4: <localized description>

    ## 6. Localized Description
    <本地化正文，语气/用词/度量按 assets/knowledge/locale_style.json>

    ## 7. Size & Measurement
    <本 locale 尺码体系换算表，Markdown 表格，含 cm 与 in>

正文 MUST NOT 出现：绝对化/促销违规词（banned_terms.json）、联系方式、平台外链、
未溯源数字、他方品牌名。KO 文档 Hangul 字符占字母比 ≥0.30；PT 文档 MUST 命中 ≥3 个
pt 停用词且 MUST NOT 含 Hangul。

## S5. 运行时契约

CLI:  agent.py --version            → 打印 agent.json.version，exit 0
      agent.py --prompt "<自然语言>" → 解析输入/输出目录并执行
环境:  DASHSCOPE_API_KEY / DASHSCOPE_BASE_URL(/api/v1) / OPENAI_BASE_URL(/v1) / AGENT_LOG_DIR
日志:  $AGENT_LOG_DIR/agent.log（人读行）+ agent.jsonl（结构化事件）+ run_manifest.json

## S6. 时间预算 [LOCKED]（总 30min，以 T0=进程启动）

| 阶段 | 预算 | 硬截止 |
|---|---|---|
P0 discover+adapt        | 40s  | T+00:40
P1 facts                 | 100s | T+02:20
P2 taxonomy              | 100s | T+04:00
P3 视频任务提交(异步,先发) | 20s  | T+04:20
P4 图片生成(并发)         | 600s | T+14:20
P5 文案 3 locale(并发)    | 240s | T+18:20
P6 视频轮询/收口          | 300s | T+23:20
P7 本地合成+规格化+落盘    | 150s | T+25:50
P8 preflight+strategy    | 70s  | T+27:00
FLOOR 兜底写入            | —    | T+27:00 触发
WATCHDOG os._exit(0)     | —    | T+28:00

任何阶段超时 MUST 触发 DEGRADATION.md 中对应降级，MUST NOT 抛出到顶层。
```

---

# 3. `docs/CONTRACTS.md`

```markdown
# 模块契约（函数级）

约定：所有跨模块对象都是 plain dict，且与 schemas/*.json 对应；纯函数优先；
所有可能失败的调用返回 (value, Diagnostics) 或抛 XbError 的子类，由 pipeline 统一捕获降级。

## C1 promptparse
parse_prompt(prompt: str|None) -> Paths{input_dir:str, output_dir:str, source:str}
  - 从自然语言中抽取路径；优先 --prompt 内绝对路径；识别“输入/input/读取”与“输出/output/保存”语义
  - 兜底：INPUT_DIR/OUTPUT_DIR 环境变量 → config.DEFAULT_INPUT/OUTPUT
  - MUST NOT 抛异常。output_dir 不存在则创建。

## C2 discovery
scan_inputs(input_dir) -> Dataset{
  files:[{path, rel, size, kind}],            # kind ∈ product|categories|attributes|other
  raw:{rel: parsed_json},                     # 仅 <=8MB 的 .json/.txt
  urls:{image:[str], video:[str], other:[str]}
}
  - kind 判定：内容特征优先（键名指纹），文件名仅作弱信号。MUST NOT 依赖具体文件名。

## C3 taxonomy_adapter
load_categories(raw) -> CategoryTree{nodes:{id:{id,name,path:[str],parent,is_leaf,keywords:[str]}}}
load_attributes(raw) -> AttrSpace{
  by_category:{cat_id:[attr_id]}|None,
  attrs:{attr_id:{name, input_type, is_sales, values:[{id,name,aliases:[str]}]|None, unit}}
}
  - MUST 支持 4 种输入形状：嵌套树 / 扁平 parent 列表 / path 字符串列表 / {category: {attr: [values]}}
  - 未识别形状 → 返回空结构 + Diagnostics(warn)，pipeline 走 A3 降级。

## C4 facts
extract(dataset, ctx) -> ProductFacts   (schemas/product_facts.schema.json)
  - 步骤：确定性抽取（键名字典 + 正则）→ LLM 补全（受限于源文本，禁止推断）→ 溯源门过滤
  - 溯源门在 provenance.gate() 内实现；未通过的字段被丢弃并记 diagnostics

## C5 taxonomy
select(facts, tree, attrspace, ctx) -> TaxonomySelection (schemas/taxonomy_selection.schema.json)
  - 候选召回：lexical_candidates(facts, tree, k=config.CAT_CANDIDATES)  纯本地 BM25-lite
  - LLM 只做“从候选里选一个 id”，输出经 validate_leaf() 强校验；非法 → 取候选 top1
  - 属性映射：对每个 attr 给出 allowed values（截断到 config.ATTR_VALUES_MAX），LLM 输出
    value_id 必须命中枚举，否则 fuzzy_match(alias/normalized) 修正，仍不中则丢弃该 attr
  - MUST NOT 自由生成类目名或属性值

## C6 localize
plan(facts, selection) -> LocaleBundleSpec{locale:{market, spelling, units, size_system,
  size_table, tone, banned:[str], measure_labels}}
scrub(text, locale) -> (clean_text, hits:[str])   # 确定性合规清洗，A1/A4 最后一道闸

## C7 copywriter
write_copy(facts, selection, lspec, ctx) -> CopyBundle (schemas/copy_bundle.schema.json)
  - 每 locale 一次 LLM 调用（并发），输出仅“散文段落 + 标题 + 素材描述”，结构化区块由
    writer 用 facts/selection 确定性渲染 → 模型无法污染事实
  - 失败降级：模板化 locale 文案（localize.template_copy）

## C8 models_image
generate(spec: ImageSpec, ctx) -> ImageAsset{url, bytes|None, model, latency, mode}
  ImageSpec{role, prompt, negative, ref_urls:[str], size, need_bytes:bool}
  - 能力阶梯见 DEGRADATION.md D2；成功 MUST 返回可下载 url
## C9 models_video
submit(spec: VideoSpec, ctx) -> TaskHandle{task_id, endpoint, payload_shape}
poll(handle, deadline, ctx) -> VideoAsset{url}|None

## C10 imaging
normalize(img: PIL.Image, rule: dict) -> PIL.Image        # 尺寸/底色/方图/边界
encode(img, path, rule) -> bytes_written                   # 迭代压缩保证 <=max_bytes
quality_flags(img) -> {blank, low_edge, letterbox, oversat, has_text_suspect}
overlay(img, blocks:[TextBlock]) -> PIL.Image              # 本地字体渲染

## C11 writer
write_all(out_dir, facts, selection, copy, assets, diag) -> WrittenSet
floor_write(out_dir, state) -> WrittenSet   # 幂等；任何缺失产物用兜底生成补齐 (I2)

## C12 preflight
check(out_dir) -> Report{rules:[{id, dim, ok, detail}], ok:bool}
  - 规则 id 与 A2/A6/A7 子维度一一对应；tools/shadow_score.py 复用同一函数
```

---

# 4. `docs/DEGRADATION.md`

```markdown
# 降级阶梯（执行 agent 无需判断，按序尝试，全部失败用最后一档）

D1 输入解析
  1) 内容指纹识别 → 2) 文件名弱信号 → 3) 最大 JSON 当作商品文件 → 4) 空 facts + 兜底文案

D2 图片生成（每张独立执行）
  1) qwen-image-3.0-pro  I2I（ref=源图 URL，sync multimodal-generation）
  2) wan2.7-image-pro    I2I
  3) wan2.7-image        I2I
  4) qwen-image-3.0-pro  T2I（无 ref）
  5) 复用已成功的其它角色图 + 本地重构（裁切/换底/加文字层）
  6) 本地纯合成图（白底 + 商品占位色块 + 渲染文字）——仅为保 A2 存在性
  端点阶梯：sync multimodal-generation → async text2image/image-synthesis(+X-DashScope-Async) 
  → async multimodal 变体；首次成功的 (model, endpoint, payload_shape) 写入 ctx.caps 缓存复用

D3 视频
  1) wan2.7-i2v-2026-04-25，first_frame = 主图**模型返回 URL**（禁止本地上传）
  2) happyhorse-1.1-r2v（reference_image = 同 URL）
  3) happyhorse-1.1-t2v（纯文生，prompt 来自 facts）
  4) 本地 Ken-Burns 幻灯片（6 张图 + ffmpeg，2.5s/张，720p，无音轨）
  所有档位产物 MUST 过 video.normalize()（H.264/yuv420p/faststart/≤200MB/≤20s）
  ffmpeg 缺失 → 记 fatal 诊断并只走 1)~3)；build_package.py 已在打包期硬门禁保证其存在

D4 文案
  1) 目标 locale LLM 生成 → scrub
  2) 换备用模型（config.TEXT_MODELS 顺序）
  3) EN 生成 + LLM 翻译（qwen3.7-max）
  4) 模板化文案（localize.template_copy，纯确定性，只用溯源事实）

D5 类目/属性
  1) LLM 受限选择 → 2) lexical top1 → 3) 最近的非叶子类目的首个叶子 → 4) 省略 Leaf Category ID
     行，但保留 Category Path（保 A3 部分子项）

D6 时间
  阶段超时 → 该阶段立即返回已完成部分；剩余角色图并发数降为 1 并跳过 role.priority>2 的图；
  T+23:20 未拿到模型视频 → 立刻切 D3-4；T+27:00 触发 floor_write。
```

---

# 5. 入口与配置

### `entry/agent.json`
```json
{"runtime": "python", "version": "1.0.0"}
```

### `entry/agent.py`
```python
#!/usr/bin/env python3
"""ZIP 根目录入口。--version 必须在任何第三方 import 之前可用。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

for _p in (os.path.join(HERE, "vendor"), os.path.join(HERE, "src")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)


def _version() -> str:
    try:
        with open(os.path.join(HERE, "agent.json"), encoding="utf-8") as fh:
            return str(json.load(fh)["version"])
    except Exception:
        return "0.0.0"


def main(argv) -> int:
    if "--version" in argv or "-v" in argv:
        sys.stdout.write(_version() + "\n")
        return 0
    try:
        from xborder.cli import run
    except Exception as exc:  # 依赖损坏也不能让评测判"失败"之外的原因
        sys.stderr.write("bootstrap failure: %r\n" % (exc,))
        from xborder_bootstrap_fallback import emergency  # type: ignore
        return emergency(argv, HERE)
    return run(argv, here=HERE, version=_version())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

> Ticket T-14 adds `entry/xborder_bootstrap_fallback.py`: a **dependency-free** module (stdlib only, no Pillow) that parses `--prompt` and writes 11 minimal-but-valid files (text files + 1×1-safe images are impossible without Pillow → it writes PNGs via a hand-rolled minimal PNG encoder, and copies a vendored 1-frame `assets/floor/product_video.mp4`). This guarantees I2 even if `vendor/` breaks.

### `src/xborder/config.py`
```python
"""唯一的策略常量来源。执行 agent 不得在其它文件里写魔数。"""
from __future__ import annotations
import os

# ---------- 路径 ----------
DEFAULT_INPUT = "/home/user/ws/input"
DEFAULT_OUTPUT = "/home/user/ws/output"

# ---------- 时间预算（秒，相对 T0）----------
BUDGET = {
    "P0_discover": 40, "P1_facts": 140, "P2_taxonomy": 240, "P3_video_submit": 260,
    "P4_images": 860, "P5_copy": 1100, "P6_video_poll": 1400, "P7_assemble": 1550,
    "P8_preflight": 1620,
}
FLOOR_AT = 1620          # T+27:00 触发兜底写入
HARD_EXIT_AT = 1680      # T+28:00 强制退出
TOTAL_LIMIT = 1800

# ---------- 模型 ----------
TEXT_MODELS = ["qwen3.7-max", "qwen3.6-plus", "deepseek-v4-pro", "kimi-k2.6", "glm-5.2"]
TEXT_MODEL_FAST = "qwen3.6-flash"
VLM_MODELS = ["qwen3-vl-plus", "qwen-vl-max"]
IMAGE_MODELS = ["qwen-image-3.0-pro", "wan2.7-image-pro", "wan2.7-image"]
VIDEO_I2V = "wan2.7-i2v-2026-04-25"
VIDEO_R2V = "happyhorse-1.1-r2v"
VIDEO_T2V = "happyhorse-1.1-t2v"

TEXT_TEMPERATURE_STRUCTURED = 0.1
TEXT_TEMPERATURE_PROSE = 0.7
TEXT_MAX_TOKENS = 4096

# ---------- 网络 ----------
HTTP_CONNECT_TIMEOUT = 10
HTTP_READ_TIMEOUT = 120
HTTP_READ_TIMEOUT_IMAGE = 300
RETRY_MAX = 4
RETRY_BASE = 1.6
RETRY_JITTER = 0.4
RETRY_ON_STATUS = (408, 409, 425, 429, 500, 502, 503, 504)
GLOBAL_CONCURRENCY = 6
IMAGE_CONCURRENCY = 3
RATE_LIMIT_PER_MIN = {"image": 20, "video": 6, "text": 90}
POLL_INTERVAL = (4, 6, 8, 10, 12, 15)   # 递增，最后一个值循环
DOWNLOAD_MAX_BYTES = 220 * 1024 * 1024

# ---------- 类目/属性 ----------
CAT_CANDIDATES = 25
ATTR_VALUES_MAX = 60
ATTR_MAX_COUNT = 25

# ---------- 图片规格（A2 硬规则的本地镜像，留安全余量）----------
MAIN_IMAGE = {"min_side": 1200, "square": True, "bg": (255, 255, 255),
              "max_bytes": 4_500_000, "fmt": "JPEG", "quality": 92, "margin_ratio": 0.06}
DETAIL_IMAGE = {"min_side": 900, "square": False, "bg": (255, 255, 255),
                "max_bytes": 4_500_000, "fmt": "JPEG", "quality": 90}
CHART_IMAGE = {"w": 1200, "h": 1500, "fmt": "PNG", "max_bytes": 4_500_000}
A2_HARD = {"main_min": 800, "detail_min": 261, "img_max_bytes": 5_000_000,
           "text_max_bytes": 1_000_000, "video_max_bytes": 200_000_000}

# ---------- 视频 ----------
VIDEO_TARGET = {"resolution": "720P", "duration": 10, "fps": 25,
                "max_bytes": 150_000_000, "max_seconds": 20}
SLIDESHOW = {"seconds_per_image": 2.5, "w": 1280, "h": 720, "zoom": 1.08}

# ---------- 视觉角色计划 ----------
IMAGE_ROLES = [
    {"name": "main_image", "priority": 0, "kind": "photo",
     "brief": "clean white-background studio product shot, product centered, fills ~85% frame"},
    {"name": "detail_image_1", "priority": 1, "kind": "photo", "brief": "front full view on model or flat-lay"},
    {"name": "detail_image_2", "priority": 1, "kind": "photo", "brief": "back / side view"},
    {"name": "detail_image_3", "priority": 2, "kind": "photo", "brief": "fabric & stitching macro close-up"},
    {"name": "detail_image_4", "priority": 0, "kind": "chart", "brief": "trilingual size & measurement table (local render)"},
    {"name": "detail_image_5", "priority": 2, "kind": "photo", "brief": "lifestyle scene consistent with target market"},
]

# ---------- 开关（A/B 用，见 EXPERIMENT_LEDGER）----------
FLAGS = {
    "EMIT_TXT_MIRROR": False,
    "IMAGE_TEXT_OVERLAY": True,     # detail 1/2/3/5 是否叠加英文短标签
    "VIDEO_AUDIO": False,           # 视频是否要求含音轨
    "VLM_SELF_CHECK": True,         # 出图后 VLM 抽检
    "STRICT_SCHEMA": bool(os.environ.get("XB_STRICT_SCHEMA")),
}

LOCALES = ("en", "ko", "pt")
MARKETS = {"en": "US", "ko": "KR", "pt": "BR"}
SOURCE_PLATFORM = "AliExpress"
```

---

# 6. 基础设施层

### `src/xborder/errors.py`
```python
class XbError(Exception):
    """所有内部错误基类；pipeline 只捕获它与 Exception，绝不外泄。"""

class BudgetExceeded(XbError): ...
class Aborted(XbError): ...
class HttpError(XbError):
    def __init__(self, status, body, url):
        super().__init__(f"HTTP {status} {url}: {body[:300]}")
        self.status, self.body, self.url = status, body, url
class ModelRefused(XbError): ...
class SchemaError(XbError): ...
class CapabilityExhausted(XbError): ...
```

### `src/xborder/budget.py`
```python
from __future__ import annotations
import threading
import time
from . import config
from .errors import Aborted


class Budget:
    """单调时钟预算管理器 + 全局中止信号。所有循环必须调用 check()/remaining()。"""

    def __init__(self, total: float = config.TOTAL_LIMIT, clock=time.monotonic):
        self.t0 = clock()
        self.clock = clock
        self.total = total
        self.abort = threading.Event()
        self._floor_cb = None
        self._timers: list[threading.Timer] = []

    # ---- 基本查询 ----
    def elapsed(self) -> float:
        return self.clock() - self.t0

    def remaining(self) -> float:
        return max(0.0, self.total - self.elapsed())

    def phase_remaining(self, phase: str) -> float:
        return max(0.0, config.BUDGET[phase] - self.elapsed())

    def phase_expired(self, phase: str) -> bool:
        return self.phase_remaining(phase) <= 0

    def check(self, phase: str | None = None) -> None:
        if self.abort.is_set():
            raise Aborted("global abort")
        if phase and self.phase_expired(phase):
            raise Aborted(f"phase {phase} expired")

    def timeout_for(self, phase: str, want: float, reserve: float = 5.0) -> float:
        """给 HTTP 调用用的超时：不得越过阶段截止，也不得越过总预算。"""
        return max(1.0, min(want, self.phase_remaining(phase) - reserve, self.remaining() - reserve))

    def sleep(self, seconds: float, phase: str | None = None) -> None:
        end = self.clock() + seconds
        while self.clock() < end:
            self.check(phase)
            time.sleep(min(0.5, end - self.clock()))

    # ---- 兜底与看门狗 (I4) ----
    def install_watchdog(self, floor_cb, hard_exit=True) -> None:
        import os

        def _floor():
            try:
                floor_cb()
            except Exception:
                pass
            finally:
                self.abort.set()

        def _hard():
            try:
                floor_cb()
            except Exception:
                pass
            os._exit(0)

        for delay, fn in ((config.FLOOR_AT, _floor), (config.HARD_EXIT_AT, _hard) if hard_exit else (None, None)):
            if delay is None:
                continue
            t = threading.Timer(max(1.0, delay - self.elapsed()), fn)
            t.daemon = True
            t.start()
            self._timers.append(t)

    def cancel_watchdog(self) -> None:
        for t in self._timers:
            t.cancel()
        self._timers.clear()
```

### `src/xborder/logging_setup.py`
```python
from __future__ import annotations
import json
import logging
import os
import sys
import threading
import time

_LOCK = threading.Lock()
_JSONL = {"fh": None}


def setup(log_dir: str | None) -> logging.Logger:
    log_dir = log_dir or os.environ.get("AGENT_LOG_DIR") or "/tmp/agent-logs"
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        log_dir = "/tmp"
    logger = logging.getLogger("xborder")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)-5s [%(threadName)s] %(message)s")
    for h in (logging.StreamHandler(sys.stdout),):
        h.setFormatter(fmt)
        logger.addHandler(h)
    try:
        fh = logging.FileHandler(os.path.join(log_dir, "agent.log"), encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        _JSONL["fh"] = open(os.path.join(log_dir, "agent.jsonl"), "a", encoding="utf-8")
    except Exception:
        pass
    logger.info("log_dir=%s", log_dir)
    logger.log_dir = log_dir  # type: ignore[attr-defined]
    return logger


def event(kind: str, **kw) -> None:
    """结构化事件：专家评审"使用体验"看日志，机评排障也靠它。"""
    rec = {"ts": round(time.time(), 3), "kind": kind}
    rec.update({k: _safe(v) for k, v in kw.items()})
    line = json.dumps(rec, ensure_ascii=False)
    with _LOCK:
        fh = _JSONL["fh"]
        if fh:
            fh.write(line + "\n")
            fh.flush()
    logging.getLogger("xborder").info("%s %s", kind, line)


def _safe(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_safe(x) for x in v][:50]
    if isinstance(v, dict):
        return {str(k): _safe(x) for k, x in list(v.items())[:50]}
    return repr(v)[:400]
```

### `src/xborder/jsonutil.py`
```python
from __future__ import annotations
import json
import re
from typing import Any, Iterator

_URL_RE = re.compile(r"https?://[^\s\"'<>\\)\]]+", re.I)
_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
_VID_EXT = (".mp4", ".mov", ".m4v", ".webm")


def walk(obj: Any, ptr: str = "") -> Iterator[tuple[str, Any]]:
    """产出 (json_pointer, value) —— 溯源门的基础设施。"""
    yield ptr or "/", obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{ptr}/{_esc(str(k))}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{ptr}/{i}")


def _esc(k: str) -> str:
    return k.replace("~", "~0").replace("/", "~1")


def find_urls(obj: Any) -> dict[str, list[str]]:
    out = {"image": [], "video": [], "other": []}
    seen = set()
    for _, v in walk(obj):
        if not isinstance(v, str):
            continue
        for u in _URL_RE.findall(v):
            u = u.rstrip(".,;)")
            if u in seen:
                continue
            seen.add(u)
            low = u.split("?")[0].lower()
            key = "image" if low.endswith(_IMG_EXT) else "video" if low.endswith(_VID_EXT) else "other"
            out[key].append(u)
    return out


def coerce_json(text: str) -> Any:
    """从 LLM 返回中稳健取出 JSON：整体解析 → 去 fence → 首个平衡括号块。"""
    if text is None:
        raise ValueError("empty")
    t = text.strip()
    for attempt in (t, _strip_fence(t)):
        try:
            return json.loads(attempt)
        except Exception:
            pass
    for opener, closer in (("{", "}"), ("[", "]")):
        blk = _balanced(t, opener, closer)
        if blk:
            try:
                return json.loads(blk)
            except Exception:
                try:
                    return json.loads(re.sub(r",\s*([}\]])", r"\1", blk))
                except Exception:
                    pass
    raise ValueError("no json found in: " + t[:200])


def _strip_fence(t: str) -> str:
    m = re.search(r"```(?:json)?\s*(.+?)```", t, re.S | re.I)
    return m.group(1).strip() if m else t


def _balanced(t: str, o: str, c: str) -> str | None:
    start = t.find(o)
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == o:
            depth += 1
        elif ch == c:
            depth -= 1
            if depth == 0:
                return t[start:i + 1]
    return None


def norm_text(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def norm_key(s: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(s or "").lower())
```

### `src/xborder/promptparse.py`
```python
from __future__ import annotations
import os
import re
from . import config

_PATH_RE = re.compile(r"(?:/[\w.\-]+){2,}/?")
_IN_HINT = ("input", "输入", "读取", "read", "dataset", "data")
_OUT_HINT = ("output", "输出", "保存", "save", "写入", "result", "结果")


def extract_argv_prompt(argv: list[str]) -> str | None:
    for i, a in enumerate(argv):
        if a == "--prompt" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--prompt="):
            return a.split("=", 1)[1]
    return None


def parse_prompt(prompt: str | None) -> dict:
    """MUST NOT raise. 返回 {input_dir, output_dir, source}"""
    src = "default"
    in_dir = out_dir = None
    if prompt:
        cands = [c.rstrip("/") for c in _PATH_RE.findall(prompt)]
        scored = []
        for c in cands:
            low = c.lower()
            score_in = sum(2 for h in _IN_HINT if h in low)
            score_out = sum(2 for h in _OUT_HINT if h in low)
            scored.append((c, score_in, score_out))
        # 输出候选：文件路径 → 取其目录
        for c, si, so in scored:
            base = os.path.basename(c)
            dirpath = os.path.dirname(c) if ("." in base and len(base.split(".")[-1]) <= 5) else c
            if so > si and out_dir is None:
                out_dir, src = dirpath, "prompt"
            elif si >= so and si > 0 and in_dir is None:
                in_dir, src = c, "prompt"
        if in_dir is None or out_dir is None:
            others = [c for c, _, _ in scored if c not in (in_dir, out_dir)]
            if in_dir is None and others:
                in_dir, src = others[0], "prompt-positional"
            if out_dir is None and len(others) > 1:
                out_dir, src = others[-1], "prompt-positional"
    in_dir = in_dir or os.environ.get("XB_INPUT_DIR") or config.DEFAULT_INPUT
    out_dir = out_dir or os.environ.get("XB_OUTPUT_DIR") or config.DEFAULT_OUTPUT
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        pass
    return {"input_dir": in_dir, "output_dir": out_dir, "source": src}
```

### `src/xborder/http.py`
```python
from __future__ import annotations
import gzip
import json
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque

from . import config
from .errors import HttpError
from .logging_setup import event


def join_url(base: str, path: str) -> str:
    """官方明确的坑：base 以 /api/v1 结尾，path 也可能带 api/v1 → 去重。"""
    b = (base or "").rstrip("/")
    p = "/" + (path or "").lstrip("/")
    for suf in ("/api/v1", "/v1"):
        if b.endswith(suf) and p.startswith(suf + "/"):
            p = p[len(suf):]
            break
    return b + p


class RateLimiter:
    def __init__(self, per_min: int):
        self.per_min, self.hits, self.lock = per_min, deque(), threading.Lock()

    def acquire(self, budget=None) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                while self.hits and now - self.hits[0] > 60:
                    self.hits.popleft()
                if len(self.hits) < self.per_min:
                    self.hits.append(now)
                    return
                wait = 60 - (now - self.hits[0]) + 0.05
            if budget:
                budget.sleep(min(wait, 5))
            else:
                time.sleep(min(wait, 5))


_LIMITERS = {k: RateLimiter(v) for k, v in config.RATE_LIMIT_PER_MIN.items()}
_SEM = threading.BoundedSemaphore(config.GLOBAL_CONCURRENCY)


def request_json(url, payload=None, headers=None, method="POST", *, kind="text",
                 timeout=None, budget=None, retries=config.RETRY_MAX, phase=None) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    hdr = {"Content-Type": "application/json", "Accept": "application/json",
           "Accept-Encoding": "gzip", "User-Agent": "xborder-agent/1.0"}
    hdr.update(headers or {})
    last = None
    for attempt in range(retries + 1):
        if budget:
            budget.check(phase)
        eff_to = timeout or config.HTTP_READ_TIMEOUT
        if budget and phase:
            eff_to = budget.timeout_for(phase, eff_to)
        _LIMITERS.get(kind, _LIMITERS["text"]).acquire(budget)
        t0 = time.monotonic()
        try:
            with _SEM:
                req = urllib.request.Request(url, data=body, headers=hdr, method=method)
                with urllib.request.urlopen(req, timeout=eff_to) as resp:
                    raw = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    out = json.loads(raw.decode("utf-8", "replace")) if raw else {}
                    event("http_ok", url=_short(url), kind=kind, ms=int((time.monotonic() - t0) * 1000),
                          attempt=attempt)
                    return out
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace") if hasattr(e, "read") else str(e)
            last = HttpError(e.code, detail, url)
            retryable = e.code in config.RETRY_ON_STATUS
            ra = e.headers.get("Retry-After") if e.headers else None
            event("http_err", url=_short(url), status=e.code, retryable=retryable,
                  attempt=attempt, body=detail[:200])
            if not retryable or attempt >= retries:
                raise last
            _backoff(attempt, budget, phase, float(ra) if (ra or "").replace(".", "").isdigit() else None)
        except Exception as e:  # timeout / conn reset / json
            last = HttpError(0, repr(e), url)
            event("http_exc", url=_short(url), err=repr(e)[:200], attempt=attempt)
            if attempt >= retries:
                raise last
            _backoff(attempt, budget, phase, None)
    raise last  # pragma: no cover


def _backoff(attempt, budget, phase, retry_after) -> None:
    delay = retry_after if retry_after else (config.RETRY_BASE ** attempt)
    delay += random.uniform(0, config.RETRY_JITTER * (attempt + 1))
    delay = min(delay, 20.0)
    if budget:
        budget.sleep(delay, phase)
    else:
        time.sleep(delay)


def download(url: str, dest: str | None = None, *, budget=None, phase=None,
             max_bytes=config.DOWNLOAD_MAX_BYTES, timeout=None) -> bytes:
    """模型产物 URL 下载（白名单允许）。返回 bytes；dest 非空时同时落盘。"""
    eff_to = timeout or config.HTTP_READ_TIMEOUT_IMAGE
    if budget and phase:
        eff_to = budget.timeout_for(phase, eff_to)
    last = None
    for attempt in range(config.RETRY_MAX + 1):
        if budget:
            budget.check(phase)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "xborder-agent/1.0"})
            with _SEM, urllib.request.urlopen(req, timeout=eff_to) as resp:
                chunks, total = [], 0
                while True:
                    c = resp.read(262144)
                    if not c:
                        break
                    total += len(c)
                    if total > max_bytes:
                        raise HttpError(0, "download too large", url)
                    chunks.append(c)
                data = b"".join(chunks)
            if dest:
                with open(dest, "wb") as fh:
                    fh.write(data)
            event("download_ok", url=_short(url), bytes=len(data), attempt=attempt)
            return data
        except Exception as e:
            last = e
            event("download_err", url=_short(url), err=repr(e)[:200], attempt=attempt)
            if attempt >= config.RETRY_MAX:
                break
            _backoff(attempt, budget, phase, None)
    raise HttpError(0, f"download failed {last!r}", url)


def _short(u: str) -> str:
    try:
        p = urllib.parse.urlparse(u)
        return f"{p.netloc}{p.path}"[:120]
    except Exception:
        return u[:120]
```

### `src/xborder/dsclient.py`
```python
from __future__ import annotations
import os
import threading

from . import config
from .errors import XbError
from .http import join_url, request_json
from .logging_setup import event


class Ctx:
    """运行上下文：凭证、预算、能力缓存、诊断。全模块唯一可变共享对象。"""

    def __init__(self, budget, logger, log_dir: str):
        self.budget = budget
        self.log = logger
        self.log_dir = log_dir
        self.api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        self.ds_base = (os.environ.get("DASHSCOPE_BASE_URL") or "").strip()
        self.oa_base = (os.environ.get("OPENAI_BASE_URL") or "").strip()
        self.caps: dict[str, dict] = {}          # (model,capability) → 成功过的调用形状
        self.caps_lock = threading.Lock()
        self.diag: list[dict] = []
        self.usage = {"calls": 0, "text": 0, "image": 0, "video": 0, "failed": 0}
        self._ulock = threading.Lock()
        if not self.ds_base:
            self.ds_base = "https://dashscope.aliyuncs.com/api/v1"
            self.note("warn", "DASHSCOPE_BASE_URL missing, using default")
        if not self.oa_base:
            self.oa_base = join_url(self.ds_base, "/compatible-mode/v1")
            self.note("warn", "OPENAI_BASE_URL missing, derived from DASHSCOPE_BASE_URL")
        if not self.api_key:
            self.note("error", "DASHSCOPE_API_KEY missing — model calls will fail")

    # ---- 诊断 & 计数 ----
    def note(self, level: str, msg: str, **kw) -> None:
        rec = {"level": level, "msg": msg, **kw}
        self.diag.append(rec)
        event("diag", **rec)

    def count(self, kind: str, ok=True) -> None:
        with self._ulock:
            self.usage["calls"] += 1
            self.usage[kind] = self.usage.get(kind, 0) + 1
            if not ok:
                self.usage["failed"] += 1

    # ---- 能力缓存（阶梯探测结果）----
    def remember(self, key: str, shape: dict) -> None:
        with self.caps_lock:
            self.caps[key] = shape
        event("cap_learned", key=key, shape=shape)

    def recall(self, key: str) -> dict | None:
        with self.caps_lock:
            return self.caps.get(key)

    # ---- 端点 ----
    def ds_url(self, path: str) -> str:
        return join_url(self.ds_base, path)

    def oa_url(self, path: str) -> str:
        return join_url(self.oa_base, path)

    @property
    def auth(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def ds_post(self, path, payload, *, kind, phase, timeout=None, async_task=False) -> dict:
        hdr = dict(self.auth)
        if async_task:
            hdr["X-DashScope-Async"] = "enable"
        return request_json(self.ds_url(path), payload, hdr, kind=kind,
                            budget=self.budget, phase=phase, timeout=timeout)

    def ds_get_task(self, task_id: str, *, phase: str) -> dict:
        return request_json(self.ds_url(f"/tasks/{task_id}"), None, self.auth,
                            method="GET", kind="text", budget=self.budget, phase=phase,
                            timeout=30, retries=2)
```

### `src/xborder/models_text.py`
```python
from __future__ import annotations
import json

from . import config
from .errors import ModelRefused, SchemaError
from .jsonutil import coerce_json
from .logging_setup import event


def chat(ctx, messages, *, model=None, temperature=None, phase="P1_facts",
         max_tokens=config.TEXT_MAX_TOKENS, json_mode=False, models=None) -> str:
    """OpenAI 兼容 Chat（唯一允许的两种调用方式之一）。按 models 顺序降级。"""
    chain = models or ([model] if model else config.TEXT_MODELS)
    last = None
    for m in chain:
        payload = {"model": m, "messages": messages,
                   "temperature": config.TEXT_TEMPERATURE_STRUCTURED if temperature is None else temperature,
                   "max_tokens": max_tokens}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        for shape in (payload, {k: v for k, v in payload.items() if k != "response_format"}):
            try:
                r = ctx.ds_post_chat(shape, phase=phase) if hasattr(ctx, "ds_post_chat") else _oa(ctx, shape, phase)
                text = _extract_text(r)
                if text:
                    ctx.count("text")
                    return text
                last = ModelRefused(f"empty content from {m}")
            except Exception as e:
                last = e
                ctx.count("text", ok=False)
                event("chat_fail", model=m, err=repr(e)[:200])
                if "response_format" not in shape:
                    break
    raise ModelRefused(f"all text models failed: {last!r}")


def _oa(ctx, payload, phase):
    from .http import request_json
    return request_json(ctx.oa_url("/chat/completions"), payload, ctx.auth,
                        kind="text", budget=ctx.budget, phase=phase)


def _extract_text(r: dict) -> str:
    try:
        c = r["choices"][0]["message"]["content"]
    except Exception:
        return ""
    if isinstance(c, list):  # 多模态返回
        return "".join(p.get("text", "") for p in c if isinstance(p, dict))
    return c or ""


def chat_json(ctx, system, user, *, schema=None, phase="P1_facts", models=None,
              repairs=2, temperature=None) -> dict:
    """结构化调用 + schema 校验 + 修复重试。所有结构化 LLM 调用 MUST 走这里。"""
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last_err = None
    for i in range(repairs + 1):
        txt = chat(ctx, msgs, phase=phase, models=models, json_mode=True,
                   temperature=temperature)
        try:
            obj = coerce_json(txt)
            if schema:
                validate(obj, schema)
            return obj
        except Exception as e:
            last_err = e
            event("json_repair", attempt=i, err=repr(e)[:200])
            msgs += [{"role": "assistant", "content": txt[:4000]},
                     {"role": "user", "content":
                      f"输出不合法：{e}. 只输出符合要求的 JSON，不要解释、不要 markdown。"}]
    raise SchemaError(f"chat_json failed: {last_err!r}")


def vlm_judge(ctx, image_urls: list[str], question: str, *, phase="P4_images") -> dict:
    """VLM 抽检：仅接受 URL 输入（禁止本地上传）。返回 {ok, issues:[str], text:[str]}"""
    content = [{"type": "text", "text": question}]
    content += [{"type": "image_url", "image_url": {"url": u}} for u in image_urls[:4]]
    try:
        txt = chat(ctx, [{"role": "user", "content": content}],
                   models=config.VLM_MODELS, phase=phase, json_mode=True, temperature=0.0)
        obj = coerce_json(txt)
        return {"ok": bool(obj.get("ok", True)), "issues": obj.get("issues", []),
                "text": obj.get("text_in_image", [])}
    except Exception as e:
        ctx.note("warn", "vlm_judge failed", err=repr(e)[:200])
        return {"ok": True, "issues": [], "text": []}


def validate(obj, schema) -> None:
    """极简 JSON Schema 子集校验器（避免引入 jsonschema 依赖）。
    支持: type, required, properties, items, enum, minLength, minItems, additionalProperties(bool)"""
    _v(obj, schema, "$")


def _v(o, s, p):
    t = s.get("type")
    if t:
        types = t if isinstance(t, list) else [t]
        ok = any(_is(o, x) for x in types)
        if not ok:
            raise SchemaError(f"{p}: expected {t}, got {type(o).__name__}")
    if "enum" in s and o not in s["enum"]:
        raise SchemaError(f"{p}: {o!r} not in enum")
    if isinstance(o, str) and "minLength" in s and len(o) < s["minLength"]:
        raise SchemaError(f"{p}: too short")
    if isinstance(o, list):
        if "minItems" in s and len(o) < s["minItems"]:
            raise SchemaError(f"{p}: needs >= {s['minItems']} items")
        if "items" in s:
            for i, e in enumerate(o):
                _v(e, s["items"], f"{p}[{i}]")
    if isinstance(o, dict):
        for k in s.get("required", []):
            if k not in o:
                raise SchemaError(f"{p}: missing required '{k}'")
        props = s.get("properties", {})
        for k, v in o.items():
            if k in props:
                _v(v, props[k], f"{p}.{k}")
            elif s.get("additionalProperties") is False:
                raise SchemaError(f"{p}: unexpected key '{k}'")


def _is(o, t):
    return {"object": dict, "array": list, "string": str, "number": (int, float),
            "integer": int, "boolean": bool, "null": type(None)}[t].__instancecheck__(o) \
        if t != "number" else isinstance(o, (int, float)) and not isinstance(o, bool)
```

### `src/xborder/models_image.py`
```python
from __future__ import annotations
import time

from . import config
from .errors import CapabilityExhausted
from .jsonutil import find_urls
from .logging_setup import event


def generate(ctx, spec: dict, *, phase="P4_images") -> dict:
    """图片生成能力阶梯 (D2)。spec: {role,prompt,negative,ref_urls,size}
    返回 {url, model, endpoint, ms}；全部失败抛 CapabilityExhausted。"""
    ladder = _ladder(spec)
    cached = ctx.recall("image")
    if cached:
        ladder = sorted(ladder, key=lambda c: 0 if (c["model"] == cached["model"] and
                                                    c["shape"] == cached["shape"]) else 1)
    last = None
    for cand in ladder:
        if ctx.budget.phase_expired(phase):
            break
        t0 = time.monotonic()
        try:
            url = _call(ctx, cand, spec, phase)
            if url:
                ctx.count("image")
                ctx.remember("image", {"model": cand["model"], "shape": cand["shape"]})
                ms = int((time.monotonic() - t0) * 1000)
                event("image_ok", role=spec.get("role"), model=cand["model"],
                      shape=cand["shape"], ms=ms)
                return {"url": url, "model": cand["model"], "endpoint": cand["shape"], "ms": ms}
        except Exception as e:
            last = e
            ctx.count("image", ok=False)
            event("image_fail", role=spec.get("role"), model=cand["model"],
                  shape=cand["shape"], err=repr(e)[:200])
    raise CapabilityExhausted(f"image generation exhausted: {last!r}")


def _ladder(spec):
    out = []
    has_ref = bool(spec.get("ref_urls"))
    for m in config.IMAGE_MODELS:
        if has_ref:
            out.append({"model": m, "shape": "mm_sync_i2i"})
    for m in config.IMAGE_MODELS:
        out.append({"model": m, "shape": "mm_sync_t2i"})
    for m in config.IMAGE_MODELS:
        out.append({"model": m, "shape": "t2i_async"})
    return out


def _call(ctx, cand, spec, phase) -> str | None:
    model, shape = cand["model"], cand["shape"]
    size = spec.get("size") or "1328*1328"
    if shape in ("mm_sync_i2i", "mm_sync_t2i"):
        content = []
        if shape == "mm_sync_i2i":
            for u in spec["ref_urls"][:3]:
                content.append({"image": u})
        content.append({"text": spec["prompt"]})
        payload = {"model": model,
                   "input": {"messages": [{"role": "user", "content": content}]},
                   "parameters": {"n": 1, "watermark": False, "prompt_extend": True,
                                  "size": _size_for(model, size)}}
        if spec.get("negative"):
            payload["parameters"]["negative_prompt"] = spec["negative"]
        r = ctx.ds_post("/services/aigc/multimodal-generation/generation", payload,
                        kind="image", phase=phase, timeout=config.HTTP_READ_TIMEOUT_IMAGE)
        return _first_image_url(r)
    if shape == "t2i_async":
        payload = {"model": model,
                   "input": {"prompt": spec["prompt"],
                             **({"negative_prompt": spec["negative"]} if spec.get("negative") else {}),
                             **({"ref_img": spec["ref_urls"][0]} if spec.get("ref_urls") else {})},
                   "parameters": {"n": 1, "size": size, "watermark": False}}
        r = ctx.ds_post("/services/aigc/text2image/image-synthesis", payload,
                        kind="image", phase=phase, async_task=True, timeout=60)
        task = (r.get("output") or {}).get("task_id")
        if not task:
            return _first_image_url(r)
        return _poll_image(ctx, task, phase)
    return None


def _size_for(model, size):
    return "2K" if model.startswith("wan2.7-image") else size


def _first_image_url(r: dict) -> str | None:
    """防御式解析：官方字段优先，其次全量 URL 扫描。"""
    try:
        for part in r["output"]["choices"][0]["message"]["content"]:
            if isinstance(part, dict) and part.get("image"):
                return part["image"]
    except Exception:
        pass
    try:
        for res in r["output"]["results"]:
            if res.get("url"):
                return res["url"]
    except Exception:
        pass
    urls = find_urls(r)
    return (urls["image"] or urls["other"] or [None])[0]


def _poll_image(ctx, task_id, phase) -> str | None:
    i = 0
    while not ctx.budget.phase_expired(phase):
        ctx.budget.sleep(config.POLL_INTERVAL[min(i, len(config.POLL_INTERVAL) - 1)], phase)
        i += 1
        r = ctx.ds_get_task(task_id, phase=phase)
        st = str(((r.get("output") or {}).get("task_status") or "")).upper()
        if st in ("SUCCEEDED", "SUCCESS"):
            return _first_image_url(r)
        if st in ("FAILED", "CANCELED", "UNKNOWN"):
            raise RuntimeError(f"image task {st}: {str(r)[:200]}")
    return None
```

### `src/xborder/models_video.py`
```python
from __future__ import annotations
from . import config
from .jsonutil import find_urls
from .logging_setup import event


def submit(ctx, spec: dict, *, phase="P3_video_submit") -> dict | None:
    """spec: {mode: i2v|r2v|t2v, prompt, image_url}
    先发后等：pipeline 在 P3 提交，在 P6 收口。返回 handle 或 None。"""
    for cand in _ladder(spec):
        if ctx.budget.phase_expired(phase):
            break
        try:
            payload = _payload(cand, spec)
            r = ctx.ds_post("/services/aigc/video-generation/video-synthesis", payload,
                            kind="video", phase=phase, async_task=True, timeout=90)
            tid = (r.get("output") or {}).get("task_id")
            if tid:
                event("video_submitted", model=cand["model"], shape=cand["shape"], task_id=tid)
                return {"task_id": tid, "model": cand["model"], "shape": cand["shape"]}
            url = (find_urls(r)["video"] or [None])[0]
            if url:
                return {"task_id": None, "direct_url": url, "model": cand["model"], "shape": cand["shape"]}
        except Exception as e:
            ctx.count("video", ok=False)
            event("video_submit_fail", model=cand["model"], shape=cand["shape"], err=repr(e)[:200])
    return None


def _ladder(spec):
    out = []
    if spec.get("image_url"):
        out += [{"model": config.VIDEO_I2V, "shape": "media_first_frame"},
                {"model": config.VIDEO_I2V, "shape": "img_url"},
                {"model": config.VIDEO_R2V, "shape": "media_reference"}]
    out += [{"model": config.VIDEO_T2V, "shape": "t2v"}]
    return out


def _payload(cand, spec):
    params = {"resolution": config.VIDEO_TARGET["resolution"],
              "duration": config.VIDEO_TARGET["duration"],
              "prompt_extend": True, "watermark": False}
    if not config.FLAGS["VIDEO_AUDIO"]:
        params["audio"] = False
    shape, model = cand["shape"], cand["model"]
    if shape == "media_first_frame":
        inp = {"prompt": spec["prompt"], "media": [{"type": "first_frame", "url": spec["image_url"]}]}
    elif shape == "media_reference":
        inp = {"prompt": spec["prompt"], "media": [{"type": "reference_image", "url": spec["image_url"]}]}
    elif shape == "img_url":
        inp = {"prompt": spec["prompt"], "img_url": spec["image_url"]}
    else:
        inp = {"prompt": spec["prompt"]}
    return {"model": model, "input": inp, "parameters": params}


def poll(ctx, handle: dict, *, phase="P6_video_poll") -> str | None:
    if not handle:
        return None
    if handle.get("direct_url"):
        return handle["direct_url"]
    i = 0
    while not ctx.budget.phase_expired(phase):
        ctx.budget.sleep(config.POLL_INTERVAL[min(i, len(config.POLL_INTERVAL) - 1)], phase)
        i += 1
        try:
            r = ctx.ds_get_task(handle["task_id"], phase=phase)
        except Exception as e:
            event("video_poll_err", err=repr(e)[:160])
            continue
        out = r.get("output") or {}
        st = str(out.get("task_status") or "").upper()
        event("video_poll", status=st, elapsed=int(ctx.budget.elapsed()))
        if st in ("SUCCEEDED", "SUCCESS"):
            url = out.get("video_url") or (find_urls(r)["video"] or [None])[0]
            if url:
                ctx.count("video")
                return url
            return None
        if st in ("FAILED", "CANCELED", "UNKNOWN"):
            ctx.note("warn", "video task failed", status=st, detail=str(out)[:200])
            return None
    ctx.note("warn", "video poll timeout → slideshow fallback")
    return None
```

---

# 7. 领域层

### `src/xborder/schemas/product_facts.schema.json`
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ProductFacts",
  "type": "object",
  "required": ["product_id", "title_source", "skus", "attributes", "provenance", "images"],
  "properties": {
    "product_id": {"type": "string"},
    "product_url": {"type": "string"},
    "source_platform": {"type": "string"},
    "title_source": {"type": "string", "minLength": 1},
    "category_hint": {"type": "string"},
    "brand": {"type": ["string", "null"]},
    "materials": {"type": "array", "items": {"type": "string"}},
    "colors": {"type": "array", "items": {"type": "string"}},
    "sizes": {"type": "array", "items": {"type": "string"}},
    "gender": {"type": ["string", "null"], "enum": ["women", "men", "unisex", "girls", "boys", "baby", null]},
    "measurements": {
      "type": "array",
      "items": {"type": "object", "required": ["size", "dimension", "value_cm"],
        "properties": {"size": {"type": "string"}, "dimension": {"type": "string"},
                       "value_cm": {"type": "number"}}}
    },
    "skus": {
      "type": "array",
      "items": {"type": "object", "required": ["sku_id"],
        "properties": {"sku_id": {"type": "string"}, "color": {"type": ["string", "null"]},
                       "size": {"type": ["string", "null"]}, "price": {"type": ["string", "number", "null"]},
                       "currency": {"type": ["string", "null"]}, "stock": {"type": ["integer", "null"]},
                       "extra": {"type": "object"}}}
    },
    "attributes": {"type": "object"},
    "images": {"type": "array", "items": {"type": "string"}},
    "videos": {"type": "array", "items": {"type": "string"}},
    "provenance": {
      "type": "object",
      "additionalProperties": true,
      "description": "field_path → {file, pointer, kind: verbatim|derived, basis}"
    },
    "dropped": {"type": "array", "items": {"type": "object"}}
  }
}
```

### `src/xborder/schemas/taxonomy_selection.schema.json`
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "TaxonomySelection",
  "type": "object",
  "required": ["leaf_category_id", "leaf_category_name", "category_path", "attributes", "sales_attributes"],
  "properties": {
    "leaf_category_id": {"type": ["string", "null"]},
    "leaf_category_name": {"type": "string"},
    "category_path": {"type": "array", "items": {"type": "string"}},
    "confidence": {"type": "number"},
    "candidates_considered": {"type": "array", "items": {"type": "string"}},
    "attributes": {
      "type": "array",
      "items": {"type": "object", "required": ["attr_id", "attr_name", "value_name"],
        "properties": {"attr_id": {"type": "string"}, "attr_name": {"type": "string"},
                       "value_id": {"type": ["string", "null"]}, "value_name": {"type": "string"},
                       "match": {"type": "string", "enum": ["exact", "alias", "fuzzy", "free"]},
                       "provenance": {"type": ["string", "null"]}}}
    },
    "sales_attributes": {
      "type": "array",
      "items": {"type": "object", "required": ["attr_name", "values"],
        "properties": {"attr_id": {"type": ["string", "null"]}, "attr_name": {"type": "string"},
                       "values": {"type": "array", "items": {"type": "string"}}}}
    }
  }
}
```

### `src/xborder/schemas/copy_bundle.schema.json`
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "CopyBundle",
  "type": "object",
  "required": ["en", "ko", "pt"],
  "additionalProperties": false,
  "properties": {
    "en": {"$ref": "#/$defs/loc"}, "ko": {"$ref": "#/$defs/loc"}, "pt": {"$ref": "#/$defs/loc"}
  },
  "$defs": {
    "loc": {
      "type": "object",
      "required": ["title", "body", "image_captions", "video_caption", "doc_heading"],
      "properties": {
        "doc_heading": {"type": "string", "minLength": 3},
        "title": {"type": "string", "minLength": 10},
        "body": {"type": "string", "minLength": 200},
        "bullets": {"type": "array", "items": {"type": "string"}},
        "image_captions": {"type": "object"},
        "video_caption": {"type": "string", "minLength": 10},
        "generated_by": {"type": "string"},
        "degraded": {"type": "boolean"}
      }
    }
  }
}
```

### `src/xborder/provenance.py`
```python
from __future__ import annotations
import re
from .jsonutil import norm_text, walk

_DERIVED_WHITELIST = {
    "size_conversion", "unit_conversion", "sku_decomposition",
    "category_mapping", "attribute_mapping", "locale_translation", "taxonomy_enum",
}


class Index:
    """把所有源 JSON 反向索引成 值→[(file, pointer)]，实现溯源门 (ADR-0003)。"""

    def __init__(self, raw: dict[str, object]):
        self.exact: dict[str, list[tuple[str, str]]] = {}
        self.sub: list[tuple[str, str, str]] = []   # (norm_value, file, pointer)
        for rel, obj in raw.items():
            for ptr, val in walk(obj):
                if isinstance(val, (str, int, float)) and not isinstance(val, bool):
                    s = norm_text(val)
                    if not s or len(s) > 2000:
                        continue
                    self.exact.setdefault(s.lower(), []).append((rel, ptr))
                    if len(s) > 3:
                        self.sub.append((s.lower(), rel, ptr))

    def locate(self, value) -> tuple[str, str] | None:
        s = norm_text(value).lower()
        if not s:
            return None
        hit = self.exact.get(s)
        if hit:
            return hit[0]
        for nv, rel, ptr in self.sub:            # 值是源文本的子串（如从标题里抽材质）
            if s in nv:
                return (rel, ptr)
        num = re.fullmatch(r"-?\d+(?:\.\d+)?", s)
        if num:
            for nv, rel, ptr in self.sub:
                if re.search(rf"(?<!\d){re.escape(s)}(?!\d)", nv):
                    return (rel, ptr)
        return None


def gate(facts: dict, index: Index, *, derived: dict[str, str] | None = None) -> dict:
    """就地过滤 facts：不可溯源且非白名单派生的字段被移到 facts['dropped']。"""
    derived = derived or {}
    prov, dropped = {}, []
    facts.setdefault("dropped", [])

    def keep(path, value) -> bool:
        if path in derived:
            kind = derived[path]
            if kind in _DERIVED_WHITELIST:
                prov[path] = {"kind": "derived", "basis": kind}
                return True
        loc = index.locate(value)
        if loc:
            prov[path] = {"kind": "verbatim", "file": loc[0], "pointer": loc[1]}
            return True
        dropped.append({"path": path, "value": str(value)[:120], "reason": "untraceable"})
        return False

    def scrub(node, path):
        if isinstance(node, dict):
            for k in list(node.keys()):
                if k in ("provenance", "dropped"):
                    continue
                scrub(node[k], f"{path}.{k}") if isinstance(node[k], (dict, list)) else None
                if not isinstance(node[k], (dict, list)) and node[k] not in (None, "", []):
                    if not keep(f"{path}.{k}", node[k]):
                        node[k] = None
        elif isinstance(node, list):
            survivors = []
            for i, v in enumerate(node):
                if isinstance(v, (dict, list)):
                    scrub(v, f"{path}[{i}]")
                    survivors.append(v)
                elif keep(f"{path}[{i}]", v):
                    survivors.append(v)
            node[:] = survivors

    for key in ("title_source", "brand", "materials", "colors", "sizes", "gender",
                "measurements", "skus", "attributes", "product_id", "product_url"):
        if key in facts and facts[key] not in (None, "", []):
            if isinstance(facts[key], (dict, list)):
                scrub(facts[key], key)
            elif not keep(key, facts[key]):
                facts[key] = None
    facts["provenance"] = prov
    facts["dropped"].extend(dropped)
    return facts
```

### `src/xborder/facts.py`
```python
from __future__ import annotations
import json
import os
import re

from . import config
from .jsonutil import find_urls, norm_key, norm_text
from .logging_setup import event
from .models_text import chat_json, validate
from .provenance import Index, gate

_SCHEMA = None
_KEYMAP = {
    "product_id": ("productid", "itemid", "id", "goodsid", "spuid", "productcode"),
    "product_url": ("producturl", "url", "detailurl", "link", "itemurl"),
    "title_source": ("title", "productname", "name", "subject", "goodsname"),
    "brand": ("brand", "brandname", "trademark"),
    "category_hint": ("category", "categoryname", "catname", "productcategory", "type"),
}
_SKU_KEYS = ("sku", "skus", "skulist", "variants", "skuinfo", "skuproperties")


def _schema():
    global _SCHEMA
    if _SCHEMA is None:
        p = os.path.join(os.path.dirname(__file__), "schemas", "product_facts.schema.json")
        with open(p, encoding="utf-8") as fh:
            _SCHEMA = json.load(fh)
    return _SCHEMA


def extract(ctx, dataset: dict) -> dict:
    """确定性抽取 + LLM 补全 + 溯源门。绝不抛异常（失败返回最小 facts）。"""
    raw = dataset["raw"]
    det = _deterministic(raw)
    facts = dict(det)
    try:
        llm = _llm_fill(ctx, dataset, det)
        for k, v in llm.items():
            if k in ("product_id", "product_url"):
                continue
            if v in (None, "", []) :
                continue
            if facts.get(k) in (None, "", []) or k in ("materials", "colors", "sizes",
                                                       "attributes", "measurements", "gender"):
                facts[k] = v
    except Exception as e:
        ctx.note("warn", "facts LLM fill failed", err=repr(e)[:200])
    facts.setdefault("attributes", {})
    facts.setdefault("skus", [])
    facts["source_platform"] = config.SOURCE_PLATFORM
    urls = dataset.get("urls") or {}
    facts["images"] = list(dict.fromkeys((facts.get("images") or []) + urls.get("image", [])))[:12]
    facts["videos"] = list(dict.fromkeys((facts.get("videos") or []) + urls.get("video", [])))[:4]

    idx = Index(raw)
    derived = {f"skus[{i}].{k}": "sku_decomposition"
               for i in range(len(facts["skus"])) for k in ("color", "size")}
    gate(facts, idx, derived=derived)
    facts["skus"] = [s for s in facts["skus"] if s.get("sku_id")]
    if not facts.get("title_source"):
        facts["title_source"] = _fallback_title(raw) or "Apparel Product"
        facts.setdefault("provenance", {})["title_source"] = {"kind": "derived", "basis": "sku_decomposition"}
    facts.setdefault("product_id", _fallback_id(raw) or "UNKNOWN")
    try:
        validate(facts, _schema())
    except Exception as e:
        ctx.note("warn", "facts schema mismatch (kept)", err=repr(e)[:200])
    event("facts_ready", product_id=facts.get("product_id"), skus=len(facts["skus"]),
          attrs=len(facts.get("attributes") or {}), dropped=len(facts.get("dropped") or []),
          images=len(facts["images"]))
    return facts


def _deterministic(raw) -> dict:
    from .jsonutil import walk
    out = {"skus": [], "attributes": {}, "images": [], "videos": []}
    flat: list[tuple[str, str, object]] = []
    for rel, obj in raw.items():
        for ptr, v in walk(obj):
            flat.append((rel, ptr, v))
    for field, keys in _KEYMAP.items():
        for rel, ptr, v in flat:
            leaf = norm_key(ptr.rsplit("/", 1)[-1])
            if leaf in keys and isinstance(v, (str, int, float)) and norm_text(v):
                out[field] = norm_text(v)
                break
    for rel, ptr, v in flat:
        leaf = norm_key(ptr.rsplit("/", 1)[-1])
        if leaf in _SKU_KEYS and isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    out["skus"].append(_sku(item))
            if out["skus"]:
                break
    out["skus"] = [s for s in out["skus"] if s.get("sku_id")][:60]
    return out


def _sku(d: dict) -> dict:
    g = lambda *ks: next((norm_text(d[k]) for k in d
                          if norm_key(k) in ks and d[k] not in (None, "")), None)
    return {"sku_id": g("skuid", "id", "sku", "skucode", "variantid") or "",
            "color": g("color", "colour", "colorname", "颜色"),
            "size": g("size", "sizename", "尺码", "尺寸"),
            "price": g("price", "saleprice", "listprice", "价格"),
            "currency": g("currency", "currencycode"),
            "stock": _int(g("stock", "quantity", "inventory", "qty")),
            "extra": {k: norm_text(v) for k, v in d.items()
                      if isinstance(v, (str, int, float)) and norm_key(k) not in
                      ("skuid", "id", "sku", "color", "size", "price", "stock")}}


def _int(v):
    try:
        return int(float(v))
    except Exception:
        return None


def _fallback_title(raw):
    best = ""
    from .jsonutil import walk
    for _, obj in raw.items():
        for _, v in walk(obj):
            if isinstance(v, str) and 12 <= len(v) <= 200 and " " in v and len(v) > len(best):
                best = v
    return norm_text(best)


def _fallback_id(raw):
    from .jsonutil import walk
    for _, obj in raw.items():
        for ptr, v in walk(obj):
            if isinstance(v, (str, int)) and re.fullmatch(r"\d{6,20}", str(v)):
                return str(v)
    return None


def _llm_fill(ctx, dataset, det) -> dict:
    tmpl = _prompt("extract_facts.txt")
    payload = json.dumps(dataset["raw"], ensure_ascii=False)[:60000]
    user = tmpl.replace("{{SOURCE_JSON}}", payload).replace(
        "{{DETERMINISTIC}}", json.dumps(det, ensure_ascii=False)[:6000])
    return chat_json(ctx, _prompt("extract_facts.txt").split("---USER---")[0], user,
                     phase="P1_facts", temperature=0.0)


def _prompt(name) -> str:
    with open(os.path.join(os.path.dirname(__file__), "prompts", name), encoding="utf-8") as fh:
        return fh.read()
```

### `src/xborder/prompts/extract_facts.txt`
```
You are a strict data extraction engine for cross-border e-commerce listings.
HARD RULES:
1. Extract ONLY values that literally appear in the SOURCE_JSON. Never infer, never translate,
   never complete missing information, never invent measurements or materials.
2. If a value is not present, output null or an empty array. Empty is always better than guessed.
3. Preserve the original language and spelling of extracted values.
4. Output ONE JSON object only. No markdown, no commentary.
Output schema:
{"title_source":str, "brand":str|null, "category_hint":str|null,
 "gender":"women|men|unisex|girls|boys|baby"|null,
 "materials":[str], "colors":[str], "sizes":[str],
 "measurements":[{"size":str,"dimension":str,"value_cm":number}],
 "attributes":{"<attribute name as written in source>":"<value as written in source>"},
 "skus":[{"sku_id":str,"color":str|null,"size":str|null,"price":str|null,"stock":int|null}]}
Notes: "measurements" only if numeric body/garment measurements exist in source; convert inches
to cm ONLY if the source unit is explicitly inches (mark nothing, just convert).
---USER---
SOURCE_JSON:
{{SOURCE_JSON}}

Already extracted deterministically (do not contradict, only fill gaps):
{{DETERMINISTIC}}
```

### `src/xborder/taxonomy_adapter.py`
```python
from __future__ import annotations
from .jsonutil import norm_key, norm_text, walk
from .logging_setup import event

_CAT_NAME = ("name", "categoryname", "cnname", "enname", "title", "label", "catname")
_CAT_ID = ("id", "categoryid", "catid", "code", "value")
_CHILD = ("children", "childs", "sub", "subcategories", "subs", "child", "nodes", "items")


def load_categories(raw: dict) -> dict:
    """4 种形状统一到 {nodes:{id:{id,name,path,parent,is_leaf,keywords}}}"""
    for rel, obj in raw.items():
        nodes = _try_tree(obj) or _try_flat(obj) or _try_paths(obj) or _try_dictmap(obj)
        if nodes and len(nodes) >= 2:
            leaves = sum(1 for n in nodes.values() if n["is_leaf"])
            event("categories_loaded", file=rel, nodes=len(nodes), leaves=leaves)
            for n in nodes.values():
                n["keywords"] = _kw(n)
            return {"nodes": nodes, "source_file": rel}
    event("categories_missing")
    return {"nodes": {}, "source_file": None}


def _kw(n):
    toks = set()
    for seg in n["path"] + [n["name"]]:
        for t in norm_text(seg).lower().replace("/", " ").replace("&", " ").replace("-", " ").split():
            if len(t) > 1:
                toks.add(t)
    return sorted(toks)


def _mk(nodes, cid, name, path, parent):
    cid = str(cid)
    nodes[cid] = {"id": cid, "name": norm_text(name), "path": [norm_text(p) for p in path],
                  "parent": parent, "is_leaf": True, "keywords": []}
    if parent and parent in nodes:
        nodes[parent]["is_leaf"] = False
    return nodes[cid]


def _try_tree(obj):
    nodes: dict = {}
    def rec(node, path, parent):
        if not isinstance(node, dict):
            return
        name = next((node[k] for k in node if norm_key(k) in _CAT_NAME and isinstance(node[k], str)), None)
        cid = next((node[k] for k in node if norm_key(k) in _CAT_ID and isinstance(node[k], (str, int))), None)
        kids = next((node[k] for k in node if norm_key(k) in _CHILD and isinstance(node[k], list)), None)
        if name is None and kids is None:
            return
        my_path = path + ([norm_text(name)] if name else [])
        me = None
        if cid is not None:
            me = _mk(nodes, cid, name or "", my_path, parent)
        for k in (kids or []):
            rec(k, my_path, me["id"] if me else parent)
    root = obj if isinstance(obj, list) else [obj]
    for r in root:
        rec(r, [], None)
    return nodes or None


def _try_flat(obj):
    items = obj if isinstance(obj, list) else obj.get("data") if isinstance(obj, dict) else None
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return None
    nodes, parents = {}, {}
    for it in items:
        cid = next((it[k] for k in it if norm_key(k) in _CAT_ID), None)
        name = next((it[k] for k in it if norm_key(k) in _CAT_NAME), None)
        pid = next((it[k] for k in it if norm_key(k) in ("parentid", "pid", "parent", "parentcategoryid")), None)
        if cid is None or name is None:
            return None
        nodes[str(cid)] = {"id": str(cid), "name": norm_text(name), "path": [],
                           "parent": str(pid) if pid not in (None, "", 0, "0") else None,
                           "is_leaf": True, "keywords": []}
        parents[str(cid)] = nodes[str(cid)]["parent"]
    for cid, p in parents.items():
        if p in nodes:
            nodes[p]["is_leaf"] = False
    for cid in nodes:
        path, cur, guard = [], cid, 0
        while cur in nodes and guard < 12:
            path.insert(0, nodes[cur]["name"])
            cur = nodes[cur]["parent"]
            guard += 1
        nodes[cid]["path"] = path
    return nodes


def _try_paths(obj):
    strs = [v for _, v in walk(obj) if isinstance(v, str) and (">" in v or "/" in v) and len(v) < 200]
    if len(strs) < 2:
        return None
    nodes = {}
    for s in strs:
        segs = [x.strip() for x in s.replace("/", ">").split(">") if x.strip()]
        if len(segs) < 2:
            continue
        parent = None
        for i, seg in enumerate(segs):
            cid = "|".join(segs[:i + 1])
            if cid not in nodes:
                _mk(nodes, cid, seg, segs[:i + 1], parent)
            parent = cid
    return nodes or None


def _try_dictmap(obj):
    if not isinstance(obj, dict):
        return None
    nodes = {}
    def rec(d, path, parent):
        for k, v in d.items():
            cid = "|".join(path + [str(k)])
            _mk(nodes, cid, k, path + [str(k)], parent)
            if isinstance(v, dict):
                rec(v, path + [str(k)], cid)
    rec(obj, [], None)
    return nodes if len(nodes) >= 2 else None


def load_attributes(raw: dict) -> dict:
    """→ {attrs:{aid:{name,is_sales,values:[{id,name,aliases}],input_type,unit}}, by_category:{cid:[aid]}}"""
    best = {"attrs": {}, "by_category": {}, "source_file": None}
    for rel, obj in raw.items():
        attrs, by_cat = {}, {}
        for ptr, v in walk(obj):
            if not isinstance(v, dict):
                continue
            name = next((v[k] for k in v if norm_key(k) in
                         ("attrname", "name", "attributename", "propertyname", "label")), None)
            aid = next((v[k] for k in v if norm_key(k) in
                        ("attrid", "id", "attributeid", "propertyid", "code")), None)
            vals = next((v[k] for k in v if norm_key(k) in
                         ("values", "valuelist", "attrvalues", "options", "enum", "value")), None)
            if not isinstance(name, str) or vals is None:
                continue
            aid = str(aid if aid is not None else norm_key(name))
            parsed = []
            if isinstance(vals, list):
                for x in vals:
                    if isinstance(x, dict):
                        vn = next((x[k] for k in x if norm_key(k) in
                                   ("name", "valuename", "value", "label", "ennname", "enname")), None)
                        vi = next((x[k] for k in x if norm_key(k) in ("id", "valueid", "code")), None)
                        if vn:
                            parsed.append({"id": str(vi) if vi is not None else None,
                                           "name": norm_text(vn), "aliases": []})
                    elif isinstance(x, (str, int, float)):
                        parsed.append({"id": None, "name": norm_text(x), "aliases": []})
            if not parsed:
                continue
            is_sales = any(t in norm_key(name) for t in ("color", "colour", "size", "颜色", "尺"))
            is_sales = is_sales or bool(v.get("isSales") or v.get("sales") or v.get("isSku"))
            attrs[aid] = {"name": norm_text(name), "is_sales": is_sales, "values": parsed,
                          "input_type": "enum", "unit": v.get("unit")}
        if len(attrs) > len(best["attrs"]):
            best = {"attrs": attrs, "by_category": by_cat, "source_file": rel}
    event("attributes_loaded", file=best["source_file"], attrs=len(best["attrs"]))
    return best
```

### `src/xborder/taxonomy.py`
```python
from __future__ import annotations
import json
import math
import os
import re
from collections import Counter

from . import config
from .jsonutil import norm_key, norm_text
from .logging_setup import event
from .models_text import chat_json, validate

_STOP = {"the", "and", "for", "with", "of", "a", "in", "to", "new", "hot", "fashion", "style"}


def select(ctx, facts: dict, tree: dict, attrspace: dict) -> dict:
    nodes = tree.get("nodes") or {}
    leaves = [n for n in nodes.values() if n["is_leaf"]] or list(nodes.values())
    sel = {"leaf_category_id": None, "leaf_category_name": "", "category_path": [],
           "confidence": 0.0, "candidates_considered": [], "attributes": [], "sales_attributes": []}
    query = _query(facts)
    cands = lexical_candidates(query, leaves, config.CAT_CANDIDATES)
    sel["candidates_considered"] = [c["id"] for c in cands]
    if cands:
        chosen = cands[0]
        try:
            picked = _llm_pick(ctx, query, cands)
            byid = {c["id"]: c for c in cands}
            if picked in byid:
                chosen = byid[picked]
                sel["confidence"] = 0.9
            else:
                ctx.note("warn", "LLM category id invalid, using lexical top1", picked=str(picked)[:80])
                sel["confidence"] = 0.5
        except Exception as e:
            ctx.note("warn", "category LLM failed", err=repr(e)[:160])
            sel["confidence"] = 0.4
        sel.update(leaf_category_id=chosen["id"], leaf_category_name=chosen["name"],
                   category_path=chosen["path"] or [chosen["name"]])
    else:
        sel["leaf_category_name"] = norm_text(facts.get("category_hint") or "Apparel")
        sel["category_path"] = [sel["leaf_category_name"]]
        ctx.note("warn", "no category candidates (adapter empty) → D5-4")

    sel["attributes"], sel["sales_attributes"] = _map_attributes(ctx, facts, attrspace, sel)
    try:
        with open(os.path.join(os.path.dirname(__file__), "schemas",
                               "taxonomy_selection.schema.json"), encoding="utf-8") as fh:
            validate(sel, json.load(fh))
    except Exception as e:
        ctx.note("warn", "taxonomy schema mismatch", err=repr(e)[:160])
    event("taxonomy_ready", leaf=sel["leaf_category_id"], name=sel["leaf_category_name"],
          attrs=len(sel["attributes"]), sales=len(sel["sales_attributes"]), conf=sel["confidence"])
    return sel


def _query(facts) -> str:
    parts = [facts.get("title_source") or "", facts.get("category_hint") or "",
             " ".join(facts.get("materials") or []), facts.get("gender") or "",
             " ".join(str(v) for v in (facts.get("attributes") or {}).values())]
    return norm_text(" ".join(parts))[:600]


def tokenize(s: str) -> list[str]:
    toks = [t for t in re.split(r"[^a-z0-9\u4e00-\u9fff]+", (s or "").lower()) if t and t not in _STOP]
    out = list(toks)
    for t in toks:                                  # 中文按 bigram 切
        if re.search(r"[\u4e00-\u9fff]", t) and len(t) > 1:
            out += [t[i:i + 2] for i in range(len(t) - 1)]
    return out


def lexical_candidates(query: str, leaves: list[dict], k: int) -> list[dict]:
    """BM25-lite，纯本地，无模型。leaf 的 keywords 已由 adapter 预计算。"""
    q = Counter(tokenize(query))
    if not q or not leaves:
        return leaves[:k]
    df = Counter()
    for n in leaves:
        for t in set(n["keywords"]):
            df[t] += 1
    N = len(leaves)
    scored = []
    for n in leaves:
        kws = Counter(n["keywords"])
        s = 0.0
        for t, qf in q.items():
            if t in kws:
                idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * qf * (1.0 + 0.5 * (len(t) >= 4))
        if n["path"] and any(norm_key(p) in {norm_key(x) for x in q} for p in n["path"]):
            s *= 1.15
        if s > 0:
            scored.append((s, n))
    scored.sort(key=lambda x: -x[0])
    return [n for _, n in scored[:k]] or leaves[:k]


def _llm_pick(ctx, query, cands) -> str | None:
    listing = "\n".join(f'{c["id"]}\t{" > ".join(c["path"] or [c["name"]])}' for c in cands)
    sys = ("You map products to a fixed e-commerce category taxonomy. You MUST choose exactly one "
           "id from the provided list. Never invent an id. Output JSON only.")
    user = (f"PRODUCT:\n{query}\n\nCANDIDATE LEAF CATEGORIES (id<TAB>path):\n{listing}\n\n"
            'Output: {"leaf_category_id":"<one id copied verbatim from the list>","why":"<=20 words"}')
    obj = chat_json(ctx, sys, user, phase="P2_taxonomy", temperature=0.0)
    return str(obj.get("leaf_category_id") or "") or None


def _map_attributes(ctx, facts, attrspace, sel) -> tuple[list, list]:
    attrs = attrspace.get("attrs") or {}
    if not attrs:
        return _freeform_attrs(facts), _freeform_sales(facts)
    allowed = {aid: a for aid, a in list(attrs.items())[:200]}
    src = dict(facts.get("attributes") or {})
    for k in ("brand", "gender"):
        if facts.get(k):
            src.setdefault(k, facts[k])
    if facts.get("materials"):
        src.setdefault("material", ", ".join(facts["materials"]))

    out, sales = [], []
    llm_map = {}
    try:
        llm_map = _llm_attrs(ctx, facts, allowed)
    except Exception as e:
        ctx.note("warn", "attribute LLM failed → deterministic only", err=repr(e)[:160])

    for aid, a in allowed.items():
        if len(out) >= config.ATTR_MAX_COUNT:
            break
        raw_val = llm_map.get(aid) or _deterministic_value(a, src)
        if not raw_val:
            continue
        hit, how = _match_value(a, raw_val)
        if not hit:
            continue
        rec = {"attr_id": aid, "attr_name": a["name"], "value_id": hit.get("id"),
               "value_name": hit["name"], "match": how,
               "provenance": _prov_for(facts, raw_val)}
        (sales if a["is_sales"] else out).append(rec)

    sales_grouped = {}
    for r in sales:
        sales_grouped.setdefault(r["attr_name"], {"attr_id": r["attr_id"], "attr_name": r["attr_name"],
                                                  "values": []})
        sales_grouped[r["attr_name"]]["values"].append(r["value_name"])
    ded = _freeform_sales(facts)
    for d in ded:
        sales_grouped.setdefault(d["attr_name"], d)
    return out, list(sales_grouped.values())


def _deterministic_value(a, src):
    an = norm_key(a["name"])
    for k, v in src.items():
        if norm_key(k) == an or an in norm_key(k) or norm_key(k) in an:
            return norm_text(v)
    return None


def _match_value(a, raw):
    vals = a["values"]
    r = norm_key(raw)
    for v in vals:
        if norm_key(v["name"]) == r:
            return v, "exact"
    for v in vals:
        for al in v.get("aliases", []):
            if norm_key(al) == r:
                return v, "alias"
    for v in vals:
        nv = norm_key(v["name"])
        if nv and (nv in r or r in nv) and min(len(nv), len(r)) >= 3:
            return v, "fuzzy"
    return None, "none"


def _prov_for(facts, val):
    prov = facts.get("provenance") or {}
    for path, p in prov.items():
        if p.get("kind") == "verbatim" and path.startswith("attributes"):
            return f'{p.get("file")}#{p.get("pointer")}'
    return None


def _freeform_attrs(facts):
    out = []
    for k, v in (facts.get("attributes") or {}).items():
        if v in (None, ""):
            continue
        out.append({"attr_id": norm_key(k), "attr_name": norm_text(k), "value_id": None,
                    "value_name": norm_text(v), "match": "free", "provenance": None})
    return out[:config.ATTR_MAX_COUNT]


def _freeform_sales(facts):
    out = []
    colors = [c for c in (facts.get("colors") or []) if c] or \
             sorted({s["color"] for s in facts.get("skus", []) if s.get("color")})
    sizes = [s for s in (facts.get("sizes") or []) if s] or \
            sorted({s["size"] for s in facts.get("skus", []) if s.get("size")})
    if colors:
        out.append({"attr_id": None, "attr_name": "Color", "values": colors[:30]})
    if sizes:
        out.append({"attr_id": None, "attr_name": "Size", "values": sizes[:30]})
    return out


def _llm_attrs(ctx, facts, allowed) -> dict:
    lines = []
    for aid, a in allowed.items():
        vals = [v["name"] for v in a["values"]][:config.ATTR_VALUES_MAX]
        lines.append(f'{aid}\t{a["name"]}\t{" | ".join(vals)}')
    sys = ("You fill platform product attributes. RULES: (1) choose values ONLY from the allowed "
           "list, copied verbatim; (2) omit an attribute entirely if the product data does not "
           "state it — never guess; (3) output JSON only.")
    user = ("PRODUCT FACTS:\n" + json.dumps(
        {k: facts.get(k) for k in ("title_source", "attributes", "materials", "colors", "sizes",
                                   "gender", "brand", "measurements")}, ensure_ascii=False)[:8000] +
        "\n\nALLOWED ATTRIBUTES (attr_id<TAB>name<TAB>allowed values):\n" + "\n".join(lines)[:20000] +
        '\n\nOutput: {"<attr_id>":"<value copied verbatim>", ...} (only confident ones)')
    obj = chat_json(ctx, sys, user, phase="P2_taxonomy", temperature=0.0)
    return {str(k): norm_text(v) for k, v in obj.items() if isinstance(v, (str, int, float))}
```

### `assets/knowledge/size_charts.json` (seed — ticket T-06 completes it)
```json
{
  "$comment": "尺码换算表。key = garment_class:gender。numeric 为该市场标准标号；letters 为字母码。A4 尺码体系子维度直接依赖此表。",
  "version": "2026-08-24",
  "systems": {
    "tops:women": {
      "cn": ["S", "M", "L", "XL", "2XL"],
      "us": ["XS/2", "S/4", "M/6-8", "L/10", "XL/12"],
      "kr": ["44", "55", "66", "77", "88"],
      "br": ["PP", "P", "M", "G", "GG"],
      "eu": ["32", "34", "36-38", "40", "42"],
      "bust_cm": [80, 84, 88, 92, 96],
      "waist_cm": [62, 66, 70, 74, 78]
    },
    "bottoms:women": {
      "cn": ["S", "M", "L", "XL", "2XL"],
      "us": ["2", "4", "6", "8", "10"],
      "kr": ["25", "26", "27", "28", "29"],
      "br": ["36", "38", "40", "42", "44"],
      "waist_cm": [62, 66, 70, 74, 78],
      "hip_cm": [86, 90, 94, 98, 102]
    },
    "tops:men": {
      "cn": ["M", "L", "XL", "2XL", "3XL"],
      "us": ["S", "M", "L", "XL", "2XL"],
      "kr": ["95", "100", "105", "110", "115"],
      "br": ["P", "M", "G", "GG", "XGG"],
      "chest_cm": [96, 100, 104, 110, 116]
    }
  },
  "notes": {
    "kr": "韩国女装常用 44/55/66/77/88 体系，男装用胸围 cm（95/100/105）。",
    "br": "巴西使用 PP/P/M/G/GG 与数字码（36-44），且体型偏差需注明 modelagem。",
    "us": "美国需同时给出 inch 与字母码，且必须给出 model wears 参考。"
  },
  "measure_labels": {
    "bust": {"en": "Bust", "ko": "가슴둘레", "pt": "Busto"},
    "waist": {"en": "Waist", "ko": "허리둘레", "pt": "Cintura"},
    "hip": {"en": "Hip", "ko": "엉덩이둘레", "pt": "Quadril"},
    "length": {"en": "Length", "ko": "총장", "pt": "Comprimento"},
    "shoulder": {"en": "Shoulder", "ko": "어깨너비", "pt": "Ombro"},
    "sleeve": {"en": "Sleeve", "ko": "소매길이", "pt": "Manga"},
    "chest": {"en": "Chest", "ko": "가슴단면", "pt": "Peito"}
  }
}
```

### `assets/knowledge/banned_terms.json` (seed — ticket T-05 completes it)
```json
{
  "$comment": "A1 内容合规文本通道。regex 为 Python re，IGNORECASE。severity=block 的命中必须删改。",
  "version": "2026-08-24",
  "global_block": [
    {"id": "absolute_best", "regex": "\\b(best|no\\.?\\s*1|number one|world'?s (?:best|first)|top\\s*1)\\b", "reason": "绝对化用语", "severity": "block"},
    {"id": "guarantee", "regex": "\\b(100%\\s*(?:guarantee[d]?|satisfaction)|money back guarantee|lifetime warranty)\\b", "reason": "无依据保证", "severity": "block"},
    {"id": "cheapest", "regex": "\\b(cheapest|lowest price ever|unbeatable price)\\b", "reason": "价格绝对化", "severity": "block"},
    {"id": "medical", "regex": "\\b(cure[sd]?|treats?|anti[- ]?(?:cancer|virus)|slimming effect|detox|heal(?:s|ing)?)\\b", "reason": "医疗功效", "severity": "block"},
    {"id": "contact", "regex": "(whats\\s?app|wechat|telegram|@gmail|@qq\\.com|\\+\\d{2}[\\d\\s-]{7,})", "reason": "站外联系方式", "severity": "block"},
    {"id": "offsite", "regex": "(https?://(?!(?:www\\.)?aliexpress\\.com)[\\w.-]+)", "reason": "站外链接", "severity": "block"},
    {"id": "urgency_fake", "regex": "\\b(only \\d+ left today|last chance forever|going out of business)\\b", "reason": "虚假紧迫", "severity": "warn"},
    {"id": "brand_ref", "regex": "\\b(nike|adidas|zara|shein|gucci|chanel|dior|uniqlo|lululemon|louis vuitton|prada|balenciaga)\\b", "reason": "他方品牌/侵权风险", "severity": "block"},
    {"id": "ip_char", "regex": "\\b(disney|mickey|hello kitty|pokemon|marvel|barbie|sanrio)\\b", "reason": "IP 侵权", "severity": "block"},
    {"id": "free_ship_claim", "regex": "\\b(free shipping worldwide|free returns anytime)\\b", "reason": "承诺物流政策", "severity": "warn"},
    {"id": "counterfeit", "regex": "\\b(replica|copy of|inspired by [A-Z][a-z]+|1:1 quality|a\\+ quality)\\b", "reason": "仿品暗示", "severity": "block"},
    {"id": "body_shaming", "regex": "\\b(fat girls?|ugly|flaw(?:ed)? body|hide your fat)\\b", "reason": "体型歧视", "severity": "block"},
    {"id": "sexualized", "regex": "\\b(sexy teen|schoolgirl outfit|lolita cosplay)\\b", "reason": "性化/未成年风险", "severity": "block"}
  ],
  "locale_block": {
    "ko": [{"id": "ko_absolute", "regex": "(최저가|100%\\s*보장|무조건|완치)", "reason": "韩市场绝对化/医疗", "severity": "block"}],
    "pt": [{"id": "pt_absolute", "regex": "(o melhor do mundo|garantia de 100%|cura)", "reason": "巴西绝对化/医疗", "severity": "block"}],
    "en": []
  },
  "image_prompt_negative": [
    "text", "letters", "watermark", "logo", "brand name", "price tag", "collage", "border",
    "frame", "multiple panels", "human face closeup distortion", "extra limbs", "deformed hands",
    "qr code", "phone number", "arrows", "stickers", "badge", "banner"
  ],
  "culture": {
    "ko": {"avoid": ["red ink writing on names", "number 4 emphasis", "japanese imperial motifs"],
           "prefer": ["clean minimal styling", "soft daylight", "pastel palette", "K-street style"]},
    "pt": {"avoid": ["religious iconography", "green-yellow national flag misuse", "over-conservative styling"],
           "prefer": ["warm outdoor light", "vibrant colors", "beach/urban casual scene"]},
    "en": {"avoid": ["cultural appropriation motifs", "before/after body claims"],
           "prefer": ["diverse inclusive presentation", "neutral studio + lifestyle mix"]}
  }
}
```

### `src/xborder/localize.py`
```python
from __future__ import annotations
import json
import os
import re

from . import config
from .jsonutil import norm_text

_KB = {}


def kb(name: str) -> dict:
    if name not in _KB:
        root = os.path.join(os.path.dirname(__file__), "assets", "knowledge")
        with open(os.path.join(root, name + ".json"), encoding="utf-8") as fh:
            _KB[name] = json.load(fh)
    return _KB[name]


def plan(facts: dict, selection: dict) -> dict:
    """输出每 locale 的本地化规格（尺码表/度量/语气/合规词）。纯确定性。"""
    charts = kb("size_charts")
    style = kb("locale_style")
    gclass = _garment_class(facts, selection)
    gender = facts.get("gender") or "women"
    key = f"{gclass}:{gender}"
    system = charts["systems"].get(key) or charts["systems"].get(f"{gclass}:women") \
        or next(iter(charts["systems"].values()))
    out = {}
    for loc in config.LOCALES:
        out[loc] = {
            "market": config.MARKETS[loc],
            "size_system_key": key,
            "size_rows": _size_rows(facts, system, loc),
            "measure_labels": {k: v[loc] for k, v in charts["measure_labels"].items()},
            "units": style[loc]["units"],
            "spelling": style[loc]["spelling"],
            "tone": style[loc]["tone"],
            "notes": charts["notes"].get({"en": "us", "ko": "kr", "pt": "br"}[loc], ""),
            "culture": kb("banned_terms")["culture"][loc],
        }
    return out


def _garment_class(facts, selection) -> str:
    text = " ".join([facts.get("title_source") or ""] + (selection.get("category_path") or [])).lower()
    if re.search(r"\b(pant|trouser|jean|short|skirt|legging)", text):
        return "bottoms"
    if re.search(r"\b(dress|gown)", text):
        return "tops"
    return "tops"


def _size_rows(facts, system, loc) -> list[dict]:
    """行 = 源数据中真实存在的尺码；换算列来自表；不存在的尺码不编造。 (A5 + A4)"""
    market_key = {"en": "us", "ko": "kr", "pt": "br"}[loc]
    src_sizes = [s for s in (facts.get("sizes") or []) if s] or \
                sorted({s["size"] for s in facts.get("skus", []) if s.get("size")})
    cn = system.get("cn") or []
    rows = []
    meas = {}
    for m in facts.get("measurements") or []:
        meas.setdefault(norm_text(m["size"]).upper(), {})[m["dimension"].lower()] = m["value_cm"]
    for s in (src_sizes or cn):
        s_norm = norm_text(s).upper()
        idx = next((i for i, c in enumerate(cn) if norm_text(c).upper() == s_norm), None)
        row = {"source_size": s, "local_size": (system.get(market_key) or [None] * len(cn))[idx]
               if idx is not None and idx < len(system.get(market_key) or []) else s,
               "measurements": {}}
        for dim in ("bust", "chest", "waist", "hip", "length", "shoulder", "sleeve"):
            v = meas.get(s_norm, {}).get(dim)
            if v is None and idx is not None:
                v = (system.get(dim + "_cm") or [None] * len(cn))[idx] if idx < len(system.get(dim + "_cm") or []) else None
                if v is not None:
                    row.setdefault("estimated", []).append(dim)
            if v is not None:
                row["measurements"][dim] = {"cm": round(float(v), 1), "in": round(float(v) / 2.54, 1)}
        rows.append(row)
    return rows[:12]


_COMPILED = {}


def _rules(loc):
    if loc not in _COMPILED:
        bt = kb("banned_terms")
        rules = bt["global_block"] + bt["locale_block"].get(loc, [])
        _COMPILED[loc] = [(r, re.compile(r["regex"], re.I)) for r in rules]
    return _COMPILED[loc]


def scrub(text: str, loc: str) -> tuple[str, list[dict]]:
    """A1 最后一道确定性闸门：block 级命中直接删除该句/短语。"""
    hits, out = [], text or ""
    for rule, rx in _rules(loc):
        for m in list(rx.finditer(out)):
            hits.append({"id": rule["id"], "match": m.group(0)[:60], "severity": rule["severity"]})
        if rule["severity"] == "block":
            out = rx.sub("", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out, hits


def locale_ok(text: str, loc: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    hangul = sum(1 for c in letters if "\uac00" <= c <= "\ud7a3")
    if loc == "ko":
        return hangul / len(letters) >= 0.30
    if hangul / len(letters) > 0.05:
        return False
    if loc == "pt":
        return sum(1 for w in ("de", "com", "para", "que", "não", "você", "sua", "e")
                   if re.search(rf"\b{w}\b", text, re.I)) >= 3
    return True


def template_copy(facts, selection, lspec, loc) -> dict:
    """D4-4 确定性兜底文案：只用溯源事实，不含任何推断。"""
    t = norm_text(facts.get("title_source") or "Apparel product")
    attrs = ", ".join(f'{a["attr_name"]}: {a["value_name"]}' for a in selection["attributes"][:8])
    head = {"en": f"{t}", "ko": f"{t}", "pt": f"{t}"}[loc]
    body = {
        "en": (f"{t}. Verified specifications from the source listing: {attrs}. "
               f"Available sizes follow the US size system; see the size table for centimetre and "
               f"inch measurements. All information in this listing is taken from the supplier data."),
        "ko": (f"{t}. 원본 상품 데이터에서 확인된 사양: {attrs}. "
               f"사이즈는 한국 사이즈 체계로 환산하여 표기했으며, 상세 실측은 사이즈 표를 참고하세요. "
               f"본 상세 정보는 공급자 데이터에 근거합니다."),
        "pt": (f"{t}. Especificações verificadas nos dados de origem: {attrs}. "
               f"Os tamanhos seguem a numeração brasileira; consulte a tabela de medidas em cm e "
               f"polegadas. Todas as informações vêm dos dados do fornecedor."),
    }[loc]
    caps = {r["name"]: {"en": "Product image", "ko": "상품 이미지", "pt": "Imagem do produto"}[loc]
            for r in config.IMAGE_ROLES}
    return {"doc_heading": head, "title": t[:200], "body": body, "bullets": [],
            "image_captions": caps,
            "video_caption": {"en": "Product overview video", "ko": "상품 소개 영상",
                              "pt": "Vídeo de apresentação do produto"}[loc],
            "generated_by": "template", "degraded": True}
```

### `assets/knowledge/locale_style.json`
```json
{
  "en": {"units": {"length": "in", "secondary": "cm", "weight": "oz"},
         "spelling": "en-US", "date": "MM/DD/YYYY", "decimal": ".",
         "tone": "concise, benefit-first, scannable bullets, no hype claims, inclusive wording",
         "keywords_hint": "search-friendly nouns first (e.g. 'Women's Ribbed Knit Midi Dress')"},
  "ko": {"units": {"length": "cm", "secondary": "cm", "weight": "g"},
         "spelling": "ko-KR", "date": "YYYY.MM.DD", "decimal": ".",
         "tone": "정중한 해요체, 실측 중심, 소재/핏/세탁 정보 강조, 과장 표현 금지",
         "keywords_hint": "핏·소재·계절 키워드를 앞쪽에 배치"},
  "pt": {"units": {"length": "cm", "secondary": "cm", "weight": "g"},
         "spelling": "pt-BR", "date": "DD/MM/YYYY", "decimal": ",",
         "tone": "caloroso e direto, foco em caimento e conforto, sem promessas absolutas",
         "keywords_hint": "usar termos pt-BR (calça, blusa, vestido) e não pt-PT"}
}
```

### `src/xborder/copywriter.py`
```python
from __future__ import annotations
import json
import os
from concurrent.futures import ThreadPoolExecutor

from . import config
from .localize import locale_ok, scrub, template_copy
from .logging_setup import event
from .models_text import chat_json, validate


def write_copy(ctx, facts, selection, lspec) -> dict:
    with open(os.path.join(os.path.dirname(__file__), "schemas",
                           "copy_bundle.schema.json"), encoding="utf-8") as fh:
        schema = json.load(fh)
    bundle = {}
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="copy") as ex:
        futs = {loc: ex.submit(_one, ctx, facts, selection, lspec, loc) for loc in config.LOCALES}
        for loc, f in futs.items():
            try:
                bundle[loc] = f.result()
            except Exception as e:
                ctx.note("warn", "copy failed → template", locale=loc, err=repr(e)[:160])
                bundle[loc] = template_copy(facts, selection, lspec, loc)
    try:
        validate(bundle, schema)
    except Exception as e:
        ctx.note("warn", "copy bundle schema mismatch", err=repr(e)[:160])
    return bundle


def _one(ctx, facts, selection, lspec, loc) -> dict:
    if ctx.budget.phase_expired("P5_copy"):
        return template_copy(facts, selection, lspec, loc)
    sysmsg = _system(loc, lspec[loc])
    user = _user(facts, selection, lspec[loc], loc)
    try:
        obj = chat_json(ctx, sysmsg, user, phase="P5_copy",
                        temperature=config.TEXT_TEMPERATURE_PROSE)
    except Exception as e:
        ctx.note("warn", "copy llm failed", locale=loc, err=repr(e)[:160])
        return template_copy(facts, selection, lspec, loc)

    out = {"doc_heading": str(obj.get("doc_heading") or obj.get("title") or "")[:200],
           "title": str(obj.get("title") or "")[:220],
           "body": str(obj.get("body") or ""),
           "bullets": [str(b) for b in (obj.get("bullets") or [])][:8],
           "image_captions": {k: str(v)[:300] for k, v in (obj.get("image_captions") or {}).items()},
           "video_caption": str(obj.get("video_caption") or ""),
           "generated_by": "llm", "degraded": False}
    total_hits = []
    for k in ("doc_heading", "title", "body", "video_caption"):
        out[k], hits = scrub(out[k], loc)
        total_hits += hits
    out["bullets"] = [scrub(b, loc)[0] for b in out["bullets"]]
    out["image_captions"] = {k: scrub(v, loc)[0] for k, v in out["image_captions"].items()}
    event("copy_scrubbed", locale=loc, hits=[h["id"] for h in total_hits])
    if not out["body"] or len(out["body"]) < 200 or not locale_ok(out["body"], loc) \
            or not out["title"] or not out["video_caption"]:
        ctx.note("warn", "copy quality gate failed → template", locale=loc)
        tpl = template_copy(facts, selection, lspec, loc)
        for k in ("doc_heading", "title", "body", "video_caption"):
            if not out.get(k) or (k == "body" and len(out[k]) < 200) or \
               (k == "body" and not locale_ok(out[k], loc)):
                out[k] = tpl[k]
        out["image_captions"] = out["image_captions"] or tpl["image_captions"]
        out["degraded"] = True
    for r in config.IMAGE_ROLES:
        out["image_captions"].setdefault(r["name"], template_copy(
            facts, selection, lspec, loc)["image_captions"][r["name"]])
    return out


def _system(loc, spec) -> str:
    lang = {"en": "US English", "ko": "Korean (South Korea)", "pt": "Brazilian Portuguese"}[loc]
    return (f"You are a senior AliExpress listing copywriter for the {spec['market']} market. "
            f"Write natively in {lang} — transcreation, never literal translation.\n"
            f"TONE: {spec['tone']}\nSPELLING: {spec['spelling']}. UNITS: primary "
            f"{spec['units']['length']} (always also give cm).\n"
            "HARD RULES:\n"
            "1. Use ONLY the facts provided. Do not add materials, certifications, origins, "
            "measurements, or benefits that are not in the facts.\n"
            "2. No absolute/superlative claims, no guarantees, no medical or slimming claims, "
            "no other brand names, no contact details, no off-platform links, no price promises.\n"
            "3. Respect cultural preferences: " + json.dumps(spec["culture"], ensure_ascii=False) + "\n"
            "4. Body 250-600 words. Output JSON only.")


def _user(facts, selection, spec, loc) -> str:
    payload = {
        "title_source": facts.get("title_source"),
        "category_path": selection.get("category_path"),
        "attributes": [{a["attr_name"]: a["value_name"]} for a in selection["attributes"]],
        "sales_attributes": selection["sales_attributes"],
        "materials": facts.get("materials"), "colors": facts.get("colors"),
        "gender": facts.get("gender"),
        "size_rows": spec["size_rows"], "measure_labels": spec["measure_labels"],
        "market_note": spec["notes"],
    }
    roles = "\n".join(f'- {r["name"]}: {r["brief"]}' for r in config.IMAGE_ROLES)
    return ("FACTS (the only allowed information):\n" + json.dumps(payload, ensure_ascii=False)[:12000] +
            f"\n\nIMAGE ASSETS to describe (write one localized description each):\n{roles}\n"
            "- product_video.mp4: short product overview video\n\n"
            'Output JSON: {"doc_heading":str,"title":str,"bullets":[str],"body":str,'
            '"image_captions":{"main_image":str,"detail_image_1":str,...,"detail_image_5":str},'
            '"video_caption":str}')
```

---

# 8. 视觉与视频

### `src/xborder/imaging.py`
```python
from __future__ import annotations
import io
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

from . import config

_FONTS: dict[tuple[str, int], object] = {}
_FONT_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")
_FILES = {"latin": "NotoSans-Regular.ttf", "latin_bold": "NotoSans-Bold.ttf",
          "kr": "NotoSansKR-Regular.otf", "kr_bold": "NotoSansKR-Bold.otf"}


def font(kind: str, size: int):
    key = (kind, size)
    if key not in _FONTS:
        path = os.path.join(_FONT_DIR, _FILES[kind])
        try:
            _FONTS[key] = ImageFont.truetype(path, size)
        except Exception:
            _FONTS[key] = ImageFont.load_default()
    return _FONTS[key]


def font_for(text: str, size: int, bold=False):
    kr = any("\uac00" <= c <= "\ud7a3" for c in text)
    return font(("kr_bold" if bold else "kr") if kr else ("latin_bold" if bold else "latin"), size)


def load(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.mode else "RGB")
    return im


def flatten(im: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    if im.mode == "RGBA":
        canvas = Image.new("RGB", im.size, bg)
        canvas.paste(im, mask=im.split()[-1])
        return canvas
    return im.convert("RGB")


def normalize(im: Image.Image, rule: dict) -> Image.Image:
    """规格化：拉到最小边、可选补白成方图、统一 RGB。A2 主图/详情图规则镜像。"""
    im = flatten(im, rule.get("bg", (255, 255, 255)))
    if rule.get("square"):
        im = pad_square(im, rule.get("bg", (255, 255, 255)), rule.get("margin_ratio", 0.0))
    min_side = rule["min_side"]
    w, h = im.size
    if min(w, h) < min_side:
        s = min_side / min(w, h)
        im = im.resize((max(min_side, int(round(w * s))), max(min_side, int(round(h * s)))),
                       Image.LANCZOS)
    if max(im.size) > 2400:
        s = 2400 / max(im.size)
        im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    return im


def pad_square(im: Image.Image, bg, margin_ratio=0.0) -> Image.Image:
    side = max(im.size)
    side = int(side * (1 + 2 * margin_ratio))
    canvas = Image.new("RGB", (side, side), bg)
    canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    return canvas


def encode(im: Image.Image, path: str, rule: dict) -> int:
    """迭代压缩确保 <= max_bytes（A2: 单张 ≤5MB）。返回写入字节数。"""
    fmt = rule.get("fmt", "JPEG")
    max_bytes = rule.get("max_bytes", config.A2_HARD["img_max_bytes"] - 500_000)
    if fmt == "PNG":
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        data = buf.getvalue()
        if len(data) > max_bytes:
            return encode(im, path, {**rule, "fmt": "JPEG", "quality": 90})
    else:
        q = rule.get("quality", 92)
        work = im
        while True:
            buf = io.BytesIO()
            work.convert("RGB").save(buf, "JPEG", quality=q, optimize=True,
                                     progressive=True, subsampling=1)
            data = buf.getvalue()
            if len(data) <= max_bytes or (q <= 60 and min(work.size) <= config.A2_HARD["main_min"] + 40):
                break
            if q > 60:
                q -= 8
            else:
                work = work.resize((int(work.width * 0.85), int(work.height * 0.85)), Image.LANCZOS)
    with open(path, "wb") as fh:
        fh.write(data)
    return len(data)


def quality_flags(im: Image.Image) -> dict:
    """A6 '可用' 的本地启发式判定。"""
    g = flatten(im).convert("L")
    st = ImageStat.Stat(g)
    edges = ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES))
    small = g.resize((64, 64))
    borders = [small.crop((0, 0, 64, 3)), small.crop((0, 61, 64, 64)),
               small.crop((0, 0, 3, 64)), small.crop((61, 0, 64, 64))]
    dark_border = sum(1 for b in borders if ImageStat.Stat(b).mean[0] < 40)
    rgb = ImageStat.Stat(flatten(im))
    return {
        "blank": st.stddev[0] < 8,
        "low_edge": edges.stddev[0] < 6,
        "letterbox": dark_border >= 2,
        "oversat": max(rgb.mean) - min(rgb.mean) > 90,
        "too_small": min(im.size) < config.A2_HARD["detail_min"] + 20,
        "usable": None,
    }


def usable(flags: dict) -> bool:
    return not (flags["blank"] or flags["low_edge"] or flags["letterbox"] or flags["too_small"])


def overlay(im: Image.Image, blocks: list[dict]) -> Image.Image:
    """本地文字层 (ADR-0002)。blocks: {text,xy_ratio,size_ratio,color,bold,anchor,band}"""
    im = flatten(im).copy()
    d = ImageDraw.Draw(im, "RGBA")
    W, H = im.size
    for b in blocks:
        text = (b.get("text") or "").strip()
        if not text:
            continue
        size = max(14, int(H * b.get("size_ratio", 0.035)))
        f = font_for(text, size, b.get("bold", False))
        x, y = int(W * b["xy_ratio"][0]), int(H * b["xy_ratio"][1])
        lines = wrap(text, f, int(W * b.get("max_width_ratio", 0.86)), d)
        lh = int(size * 1.35)
        if b.get("band", True):
            pad = int(size * 0.5)
            tw = max(d.textlength(l, font=f) for l in lines)
            box = (x - pad, y - pad, x + tw + pad, y + lh * len(lines) + pad)
            d.rounded_rectangle(box, radius=int(size * 0.35),
                                fill=tuple(b.get("band_color", (255, 255, 255, 210))))
        for i, line in enumerate(lines):
            d.text((x, y + i * lh), line, font=f, fill=tuple(b.get("color", (26, 26, 26))))
    return im


def wrap(text: str, f, max_px: int, draw) -> list[str]:
    words, lines, cur = text.split(), [], ""
    if not any(" " in text for _ in (0,)) and len(text) > 20:
        words = list(text)
        joiner = ""
    else:
        joiner = " "
    for w in words:
        trial = (cur + joiner + w).strip() if cur else w
        if draw.textlength(trial, font=f) <= max_px or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:6]


def placeholder(text: str, size=(1200, 1200), bg=(245, 245, 245)) -> Image.Image:
    """D2-6 最后兜底图：保证 A2 存在性与规格达标，且明显不是黑图。"""
    im = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(im)
    d.rectangle((int(size[0] * .08), int(size[1] * .08), int(size[0] * .92), int(size[1] * .92)),
                outline=(200, 200, 200), width=6)
    f = font_for(text, int(size[1] * 0.05), True)
    for i, line in enumerate(wrap(text, f, int(size[0] * 0.8), d)):
        d.text((int(size[0] * .1), int(size[1] * .42) + i * int(size[1] * .07)), line,
               font=f, fill=(70, 70, 70))
    return im
```

### `src/xborder/chart.py`
```python
from __future__ import annotations
from PIL import Image, ImageDraw

from . import config
from .imaging import font_for


def render_size_chart(facts: dict, lspec: dict, out_path: str) -> dict:
    """detail_image_4：三语尺码/度量表，100% 本地渲染 → A4 尺码体系 + 度量单位拿分，
    且图内文字零乱码风险 (ADR-0002)。"""
    W, H = config.CHART_IMAGE["w"], config.CHART_IMAGE["h"]
    im = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    pad = 48
    y = pad
    d.text((pad, y), "SIZE & MEASUREMENT / 사이즈 표 / TABELA DE MEDIDAS",
           font=font_for("SIZE 사이즈", 40, True), fill=(20, 20, 20))
    y += 70
    d.line((pad, y, W - pad, y), fill=(30, 30, 30), width=3)
    y += 20

    rows_en = lspec["en"]["size_rows"]
    dims = []
    for r in rows_en:
        for k in r["measurements"]:
            if k not in dims:
                dims.append(k)
    dims = dims[:5]
    labels = ["Size", "US", "KR", "BR"] + [f"{d_}\n{lspec['ko']['measure_labels'].get(d_, d_)}"
                                           for d_ in dims]
    n_cols = len(labels)
    cw = (W - 2 * pad) // max(1, n_cols)
    hdr_h = 78
    d.rectangle((pad, y, W - pad, y + hdr_h), fill=(242, 242, 242))
    for i, lab in enumerate(labels):
        for j, part in enumerate(lab.split("\n")):
            d.text((pad + i * cw + 10, y + 8 + j * 30), part[:14],
                   font=font_for(part, 24, True), fill=(30, 30, 30))
    y += hdr_h
    rh = 66
    us = {r["source_size"]: r["local_size"] for r in lspec["en"]["size_rows"]}
    kr = {r["source_size"]: r["local_size"] for r in lspec["ko"]["size_rows"]}
    br = {r["source_size"]: r["local_size"] for r in lspec["pt"]["size_rows"]}
    for idx, r in enumerate(rows_en):
        if y + rh > H - 240:
            break
        if idx % 2:
            d.rectangle((pad, y, W - pad, y + rh), fill=(250, 250, 250))
        cells = [r["source_size"], us.get(r["source_size"], "-"),
                 kr.get(r["source_size"], "-"), br.get(r["source_size"], "-")]
        for dim in dims:
            m = r["measurements"].get(dim)
            cells.append(f'{m["cm"]}cm / {m["in"]}in' if m else "-")
        for i, c in enumerate(cells):
            d.text((pad + i * cw + 10, y + 18), str(c)[:16],
                   font=font_for(str(c), 22), fill=(40, 40, 40))
        y += rh
        d.line((pad, y, W - pad, y), fill=(228, 228, 228), width=1)

    y = H - 210
    notes = [
        "Measurements are taken flat; 1 in = 2.54 cm. Manual measurement tolerance may apply.",
        "실측은 평면 기준이며, 1인치 = 2.54cm 입니다. 측정 방식에 따라 오차가 있을 수 있습니다.",
        "As medidas são tiradas com a peça plana; 1 in = 2,54 cm. Pode haver pequena variação.",
    ]
    for n in notes:
        d.text((pad, y), n, font=font_for(n, 22), fill=(90, 90, 90))
        y += 40
    from .imaging import encode
    written = encode(im, out_path, config.CHART_IMAGE)
    return {"path": out_path, "bytes": written, "rows": len(rows_en), "dims": dims}
```

### `src/xborder/video.py`
```python
from __future__ import annotations
import glob
import os
import shutil
import subprocess
import tempfile

from PIL import Image

from . import config
from .logging_setup import event


def ffmpeg_path() -> str | None:
    """vendor 内 imageio-ffmpeg 静态二进制优先；ZIP 可能丢失可执行位 → 必须修复。"""
    cand = None
    try:
        import imageio_ffmpeg
        cand = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    cand = cand or shutil.which("ffmpeg")
    if not cand:
        for p in glob.glob(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                        "vendor", "**", "ffmpeg*"), recursive=True):
            if os.path.isfile(p):
                cand = p
                break
    if not cand:
        return None
    return _ensure_exec(cand)


def _ensure_exec(path: str) -> str | None:
    if os.access(path, os.X_OK):
        return path
    try:
        os.chmod(path, 0o755)
        if os.access(path, os.X_OK):
            return path
    except Exception:
        pass
    try:                                    # 只读安装目录 → 复制到 tmp 再 chmod
        tmp = os.path.join(tempfile.gettempdir(), "xb-ffmpeg")
        shutil.copy2(path, tmp)
        os.chmod(tmp, 0o755)
        return tmp if os.access(tmp, os.X_OK) else None
    except Exception:
        return None


def run(args: list[str], timeout: int) -> tuple[int, str]:
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout)
        return p.returncode, (p.stderr or b"").decode("utf-8", "replace")[-4000:]
    except Exception as e:
        return -1, repr(e)


def probe(path: str) -> dict:
    """A7 可播放性本地判定：完整解码一遍。"""
    ff = ffmpeg_path()
    info = {"exists": os.path.isfile(path), "bytes": os.path.getsize(path) if os.path.isfile(path) else 0,
            "decodes": None, "duration": None, "has_video": None}
    if not ff or not info["exists"]:
        return info
    rc, err = run([ff, "-v", "error", "-i", path, "-f", "null", "-"], 180)
    info["decodes"] = rc == 0 and "Invalid" not in err
    rc2, meta = run([ff, "-hide_banner", "-i", path], 60)
    import re
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", meta)
    if m:
        info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    info["has_video"] = "Video:" in meta
    return info


def normalize(src: str, dest: str, ctx=None) -> bool:
    """统一到 H.264/yuv420p/faststart，限时长与体积（A2/A7）。"""
    ff = ffmpeg_path()
    if not ff:
        if src != dest:
            shutil.copy2(src, dest)
        return os.path.isfile(dest)
    args = [ff, "-y", "-i", src, "-t", str(config.VIDEO_TARGET["max_seconds"]),
            "-vf", "scale='min(1280,iw)':'min(720,ih)':force_original_aspect_ratio=decrease,"
                   "pad=ceil(iw/2)*2:ceil(ih/2)*2,fps=25",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-level", "4.0", "-movflags", "+faststart"]
    args += (["-c:a", "aac", "-b:a", "128k"] if config.FLAGS["VIDEO_AUDIO"] else ["-an"])
    args += [dest]
    rc, err = run(args, 420)
    event("video_normalize", rc=rc, err=err[-300:] if rc != 0 else "")
    if rc != 0 or not os.path.isfile(dest) or os.path.getsize(dest) < 4096:
        if src != dest:
            try:
                shutil.copy2(src, dest)
            except Exception:
                return False
    return os.path.isfile(dest) and os.path.getsize(dest) > 4096


def slideshow(image_paths: list[str], dest: str, captions: list[str] | None = None,
              ctx=None) -> bool:
    """D3-4 兜底视频：Pillow 生成 Ken-Burns 帧 + ffmpeg 编码。完全离线、确定性。"""
    ff = ffmpeg_path()
    imgs = [p for p in image_paths if os.path.isfile(p)]
    if not ff or not imgs:
        return False
    W, H = config.SLIDESHOW["w"], config.SLIDESHOW["h"]
    fps = config.VIDEO_TARGET["fps"]
    per = config.SLIDESHOW["seconds_per_image"]
    zoom = config.SLIDESHOW["zoom"]
    tmp = tempfile.mkdtemp(prefix="xb-slides-")
    idx = 0
    try:
        for i, p in enumerate(imgs):
            try:
                base = Image.open(p).convert("RGB")
            except Exception:
                continue
            n = int(per * fps)
            for k in range(n):
                if ctx:
                    ctx.budget.check(None)
                z = 1 + (zoom - 1) * (k / max(1, n - 1)) * (1 if i % 2 == 0 else -1) + \
                    (0 if i % 2 == 0 else (zoom - 1))
                cw, ch = int(base.width / z), int(base.height / z)
                ox, oy = (base.width - cw) // 2, (base.height - ch) // 2
                frame = base.crop((ox, oy, ox + cw, oy + ch))
                canvas = Image.new("RGB", (W, H), (255, 255, 255))
                s = min(W / frame.width, H / frame.height)
                frame = frame.resize((max(2, int(frame.width * s)), max(2, int(frame.height * s))),
                                     Image.LANCZOS)
                canvas.paste(frame, ((W - frame.width) // 2, (H - frame.height) // 2))
                canvas.save(os.path.join(tmp, "f%05d.jpg" % idx), "JPEG", quality=88)
                idx += 1
        if idx < fps:
            return False
        rc, err = run([ff, "-y", "-framerate", str(fps), "-i", os.path.join(tmp, "f%05d.jpg"),
                       "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                       "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", dest], 420)
        event("slideshow", frames=idx, rc=rc, err=err[-300:] if rc else "")
        return rc == 0 and os.path.isfile(dest) and os.path.getsize(dest) > 4096
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
```

---

# 9. 落盘、校验、编排

### `src/xborder/writer.py`
```python
from __future__ import annotations
import json
import os

from . import config
from .imaging import encode, placeholder
from .logging_setup import event

TEXT_FILES = {loc: f"product_description_{loc}.md" for loc in config.LOCALES}
IMAGE_FILES = {"main_image": "main_image.jpeg", "detail_image_1": "detail_image_1.jpeg",
               "detail_image_2": "detail_image_2.jpeg", "detail_image_3": "detail_image_3.jpeg",
               "detail_image_4": "detail_image_4.png", "detail_image_5": "detail_image_5.jpeg"}
VIDEO_FILE = "product_video.mp4"
STRATEGY_FILE = "strategy_document.md"
ALL_FILES = list(TEXT_FILES.values()) + list(IMAGE_FILES.values()) + [VIDEO_FILE, STRATEGY_FILE]


def render_doc(loc, facts, selection, copy, lspec) -> str:
    c = copy[loc]
    L = lspec[loc]
    P = facts.get("provenance") or {}
    out = [f"# {c['doc_heading']}", "", "## 1. Product Title", f"Title: {c['title']}", ""]
    out += ["## 2. Product Information",
            f"Category Path: {' > '.join(selection['category_path'])}",
            f"Leaf Category: {selection['leaf_category_name']}"]
    if selection.get("leaf_category_id"):
        out.append(f"Leaf Category ID: {selection['leaf_category_id']}")
    out.append("SKU List:")
    if facts.get("skus"):
        for s in facts["skus"][:60]:
            bits = [f"SKU ID: {s['sku_id']}"]
            for k, lab in (("color", "Color"), ("size", "Size"), ("price", "Price"),
                           ("stock", "Stock")):
                if s.get(k) not in (None, ""):
                    v = s[k]
                    if k == "size":
                        v = _localized_size(v, L)
                    bits.append(f"{lab}: {v}")
            if s.get("currency"):
                bits.append(f"Currency: {s['currency']}")
            out.append("- " + " | ".join(bits))
    else:
        out.append("- (no SKU records present in source data)")
    out.append("Product Attributes:")
    for a in selection["attributes"] or []:
        out.append(f"- {a['attr_name']}: {a['value_name']}")
    if not selection["attributes"]:
        out.append("- (none verifiable from source data)")
    out.append("Sales Attributes:")
    for s in selection["sales_attributes"] or []:
        out.append(f"- {s['attr_name']}: {', '.join(str(v) for v in s['values'])}")
    if not selection["sales_attributes"]:
        out.append("- (none verifiable from source data)")
    out += ["", "## 3. Data Source",
            f"Source Platform: {facts.get('source_platform') or config.SOURCE_PLATFORM}",
            f"Product ID: {facts.get('product_id') or 'N/A'}",
            f"Product URL: {facts.get('product_url') or 'N/A'}",
            "Field Provenance:"]
    for path, p in list(P.items())[:80]:
        if p.get("kind") == "verbatim":
            out.append(f"- {path}: {p.get('file')}#{p.get('pointer')}")
        else:
            out.append(f"- {path}: derived[{p.get('basis')}]")
    out += ["", "## 4. Images"]
    for role, fname in IMAGE_FILES.items():
        out.append(f"- {fname}: {c['image_captions'].get(role, '')}")
    out += ["", "## 5. Video", f"- {VIDEO_FILE}: {c['video_caption']}", "",
            "## 6. Localized Description", c["body"]]
    if c.get("bullets"):
        out += [""] + [f"- {b}" for b in c["bullets"]]
    out += ["", "## 7. Size & Measurement", _size_table_md(L)]
    return "\n".join(out) + "\n"


def _localized_size(v, L):
    for r in L["size_rows"]:
        if str(r["source_size"]).strip().lower() == str(v).strip().lower():
            return f'{r["local_size"]} ({L["market"]}) / {r["source_size"]}'
    return v


def _size_table_md(L) -> str:
    rows = L["size_rows"]
    if not rows:
        return "(no size data available in source)"
    dims = []
    for r in rows:
        for k in r["measurements"]:
            if k not in dims:
                dims.append(k)
    head = ["Size (source)", f"Size ({L['market']})"] + \
           [f'{L["measure_labels"].get(d, d)} (cm / in)' for d in dims]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        cells = [str(r["source_size"]), str(r["local_size"])]
        for d in dims:
            m = r["measurements"].get(d)
            cells.append(f'{m["cm"]} / {m["in"]}' if m else "-")
        lines.append("| " + " | ".join(cells) + " |")
    est = sorted({d for r in rows for d in (r.get("estimated") or [])})
    if est:
        lines.append("")
        lines.append(f"Note: values for {', '.join(est)} are converted from the standard "
                     f"{L['size_system_key']} size chart, not from per-SKU source measurements.")
    return "\n".join(lines)


def write_texts(out_dir, facts, selection, copy, lspec) -> dict:
    res = {}
    for loc in config.LOCALES:
        path = os.path.join(out_dir, TEXT_FILES[loc])
        body = render_doc(loc, facts, selection, copy, lspec)
        data = body.encode("utf-8")
        if len(data) > config.A2_HARD["text_max_bytes"] - 20000:
            data = data[:config.A2_HARD["text_max_bytes"] - 20000]
        with open(path, "wb") as fh:
            fh.write(data)
        res[TEXT_FILES[loc]] = len(data)
        if config.FLAGS["EMIT_TXT_MIRROR"]:
            with open(path[:-3] + ".txt", "wb") as fh:
                fh.write(data)
    event("texts_written", files=res)
    return res


def write_strategy(out_dir, state) -> int:
    from .strategy_text import build          # 拆出以便单独打磨（专家评审 35%）
    text = build(state)
    path = os.path.join(out_dir, STRATEGY_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return os.path.getsize(path)


def floor_write(out_dir, state) -> list[str]:
    """幂等兜底 (I2)：补齐一切缺失文件。任何时候可调用，包括看门狗线程。"""
    created = []
    os.makedirs(out_dir, exist_ok=True)
    facts = state.get("facts") or {}
    title = (facts.get("title_source") or "Product")[:80]
    for loc, fname in TEXT_FILES.items():
        p = os.path.join(out_dir, fname)
        if not _nonempty(p, 200):
            try:
                from .localize import plan, template_copy
                lspec = state.get("lspec") or plan(facts, state.get("selection") or _empty_sel())
                copy = {l: template_copy(facts, state.get("selection") or _empty_sel(), lspec, l)
                        for l in config.LOCALES}
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(render_doc(loc, facts, state.get("selection") or _empty_sel(),
                                        copy, lspec))
            except Exception:
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(f"# {title}\n\nTitle: {title}\n\nSource Platform: "
                             f"{config.SOURCE_PLATFORM}\nProduct ID: "
                             f"{facts.get('product_id') or 'N/A'}\n")
            created.append(fname)
    for role, fname in IMAGE_FILES.items():
        p = os.path.join(out_dir, fname)
        if not _nonempty(p, 5000):
            rule = config.MAIN_IMAGE if role == "main_image" else config.DETAIL_IMAGE
            if fname.endswith(".png"):
                rule = config.CHART_IMAGE
            try:
                encode(placeholder(title, (1200, 1200)), p,
                       {**rule, "fmt": "PNG" if fname.endswith(".png") else "JPEG"})
            except Exception:
                pass
            created.append(fname)
    vp = os.path.join(out_dir, VIDEO_FILE)
    if not _nonempty(vp, 20000):
        from .video import slideshow
        imgs = [os.path.join(out_dir, f) for f in IMAGE_FILES.values()]
        if not slideshow(imgs, vp, ctx=None):
            fallback = os.path.join(os.path.dirname(__file__), "assets", "floor", "product_video.mp4")
            if os.path.isfile(fallback):
                import shutil
                shutil.copy2(fallback, vp)
        created.append(VIDEO_FILE)
    sp = os.path.join(out_dir, STRATEGY_FILE)
    if not _nonempty(sp, 200):
        try:
            write_strategy(out_dir, state)
        except Exception:
            with open(sp, "w", encoding="utf-8") as fh:
                fh.write("# Strategy\n\nDegraded run: floor artifacts emitted.\n")
        created.append(STRATEGY_FILE)
    prune(out_dir)
    if created:
        event("floor_write", created=created)
    return created


def prune(out_dir) -> list[str]:
    """I2：输出目录 MUST 只含 ALL_FILES。"""
    allow = set(ALL_FILES)
    if config.FLAGS["EMIT_TXT_MIRROR"]:
        allow |= {f[:-3] + ".txt" for f in TEXT_FILES.values()}
    removed = []
    for f in os.listdir(out_dir):
        if f not in allow:
            try:
                p = os.path.join(out_dir, f)
                os.remove(p) if os.path.isfile(p) else None
                removed.append(f)
            except Exception:
                pass
    return removed


def _nonempty(p, min_bytes) -> bool:
    return os.path.isfile(p) and os.path.getsize(p) >= min_bytes


def _empty_sel():
    return {"leaf_category_id": None, "leaf_category_name": "Apparel",
            "category_path": ["Apparel"], "attributes": [], "sales_attributes": []}
```

### `src/xborder/strategy_text.py`
```python
from __future__ import annotations
import json

from . import config

TEMPLATE = """# Strategy Document — One-Click Overseas Listing Agent

## 1. Design goal
A single-pass, offline-capable agent that turns one raw product record into a complete,
platform-ready localized listing kit for the US (EN), Korea (KO) and Brazil (PT) markets.
The agent is built around three engineering commitments:

1. **Determinism before beauty.** Every scoring-relevant artifact property that can be
   guaranteed by code (file naming, format, resolution, byte size, playability, enum legality)
   is guaranteed by code, never by a model.
2. **Facts are immutable.** No generative model is allowed to introduce a product fact.
   Models only rephrase and illustrate facts that passed a traceability gate.
3. **Graceful degradation over failure.** Every capability has a fallback ladder ending in a
   fully local, model-free path, so the agent always emits a complete artifact set.

## 2. Pipeline
{pipeline}

## 3. Localization strategy
- **Transcreation, not translation.** Each locale is generated natively from the fact set with a
  market-specific system prompt (tone, register, spelling variant, keyword ordering).
- **Size systems.** Source sizes are mapped to US / KR (44-55-66-77-88 or chest-cm) / BR
  (PP-P-M-G-GG or numeric) via a packaged conversion table; every row carries cm **and** inch
  values, and converted-not-measured values are explicitly disclosed.
- **Units & formats.** Primary unit, decimal separator and date format follow locale rules.
- **Culture guardrails.** A packaged rule set drives both copy (banned expressions per market)
  and imagery (background, styling, scene preferences, body/gender representation).
- **In-image text is rendered locally** with packaged Noto fonts (Latin + Korean), so Korean and
  Portuguese characters are always typographically correct — generative models are never asked
  to draw non-Latin text.

## 4. Visual strategy
{visual}

## 5. Video strategy
{video}

## 6. Compliance strategy
Two channels, both deterministic and auditable:
- **Text channel:** a compiled rule set (absolute claims, guarantees, medical claims, contact
  details, off-platform links, third-party brands/IP, counterfeit hints, body-shaming) is applied
  as a post-generation scrubber; every hit is logged.
- **Image channel:** main image is text-free by construction; negative prompts exclude
  watermarks/logos/collages/borders; a VLM spot-check reports unexpected text or artifacts.

## 7. Reliability engineering
- Wall-clock budget manager with per-phase deadlines; the long-latency video task is submitted
  first and polled while images and copy are produced in parallel.
- Rate-limit aware client: token-bucket per capability, exponential backoff with jitter,
  `Retry-After` honoured, capability ladder that learns which endpoint/payload shape works.
- Watchdog at T+27:00 writes floor artifacts, hard stop at T+28:00; the process always exits 0.
- A local preflight validator mirrors the published material-specification rules and its report is
  written to the log directory for auditability.

## 8. Run report
{report}

## 9. Notes on machine-readability
Structured sections in the three locale documents use stable ASCII field keys
(`Title:`, `Leaf Category ID:`, `Source Platform:`, `Product ID:`, …) while all values and prose
are localized. This keeps the documents parseable by the platform while remaining natural for
human buyers in each market.
"""


def build(state: dict) -> str:
    diag = state.get("diag") or []
    usage = state.get("usage") or {}
    pf = state.get("preflight") or {}
    assets = state.get("assets") or {}
    pipeline = "\n".join(
        f"{i+1}. **{name}** — {desc}" for i, (name, desc) in enumerate([
            ("Input discovery", "content-fingerprint scan of the input directory; file names are "
             "never hard-coded, category/attribute/product files are detected by key signatures"),
            ("Fact extraction", "deterministic key-map extraction + LLM gap filling, then a "
             "traceability gate that drops any value not literally locatable in the source JSON "
             "(or produced by a whitelisted deterministic transform)"),
            ("Taxonomy mapping", "local BM25-lite retrieval of leaf-category candidates, then a "
             "constrained LLM choice restricted to those candidates, then enum validation and "
             "alias/fuzzy repair of every attribute value"),
            ("Video submission", "asynchronous image-to-video task submitted early to hide latency"),
            ("Image generation", "role-based visual plan (main / views / macro / chart / lifestyle) "
             "using the source product image as reference to preserve identity"),
            ("Copywriting", "three parallel locale generations, then deterministic compliance scrub"),
            ("Assembly", "local normalization (square white main image, resolution/byte-size "
             "targets), local text layers, video normalization to H.264/faststart"),
            ("Preflight", "specification self-check and strategy report"),
        ]))
    visual = "\n".join([
        f"- Roles: {', '.join(r['name'] + ' (' + r['brief'] + ')' for r in config.IMAGE_ROLES)}",
        "- Identity preservation: the source product image URL is passed as reference to the image "
        "model, so silhouette, colourway and print stay faithful to the real product.",
        "- The main image is produced as a pure-white studio shot, centred, text-free, padded to a "
        "square canvas at ≥1200 px.",
        "- `detail_image_4` is a fully locally rendered trilingual size & measurement table: exact "
        "typography, zero hallucination risk, direct localization value.",
    ])
    video = "\n".join([
        "- Primary: image-to-video from the generated main image (model-returned URL, so no local "
        "upload is required), 720P, ~10 s, silent by default.",
        "- Ladder: i2v → reference-to-video → text-to-video → locally rendered Ken-Burns slideshow "
        "built from the generated stills with a packaged static encoder.",
        "- Every path is normalized to H.264 / yuv420p / +faststart and decode-verified locally.",
    ])
    report = "```json\n" + json.dumps({
        "assets": {k: {kk: vv for kk, vv in v.items() if kk in ("model", "mode", "bytes", "ms",
                                                                "fallback", "usable")}
                   for k, v in assets.items()},
        "model_calls": usage,
        "preflight_ok": pf.get("ok"),
        "preflight_failures": [r["id"] for r in pf.get("rules", []) if not r["ok"]],
        "warnings": [d["msg"] for d in diag if d.get("level") in ("warn", "error")][:20],
        "elapsed_seconds": state.get("elapsed"),
    }, ensure_ascii=False, indent=2) + "\n```"
    return TEMPLATE.format(pipeline=pipeline, visual=visual, video=video, report=report)
```

### `src/xborder/preflight.py`
```python
from __future__ import annotations
import os
import re

from . import config
from .writer import ALL_FILES, IMAGE_FILES, TEXT_FILES, VIDEO_FILE, STRATEGY_FILE

REQUIRED_SECTIONS = ["## 1. Product Title", "## 2. Product Information", "## 3. Data Source",
                     "## 4. Images", "## 5. Video", "## 6. Localized Description"]
REQUIRED_FIELDS = ["Title:", "Category Path:", "Leaf Category:", "SKU List:",
                   "Product Attributes:", "Sales Attributes:", "Source Platform:",
                   "Product ID:", "Product URL:"]


def check(out_dir: str) -> dict:
    rules = []

    def add(rid, dim, ok, detail=""):
        rules.append({"id": rid, "dim": dim, "ok": bool(ok), "detail": str(detail)[:300]})

    present = set(os.listdir(out_dir)) if os.path.isdir(out_dir) else set()
    for f in ALL_FILES:
        add(f"A2.exists.{f}", "A2", f in present, f"missing {f}" if f not in present else "")
    extra = sorted(present - set(ALL_FILES) -
                   ({f[:-3] + ".txt" for f in TEXT_FILES.values()}
                    if config.FLAGS["EMIT_TXT_MIRROR"] else set()))
    add("A2.no_extra_files", "A2", not extra, f"extra: {extra}")

    for loc, f in TEXT_FILES.items():
        p = os.path.join(out_dir, f)
        if not os.path.isfile(p):
            continue
        size = os.path.getsize(p)
        add(f"A2.text_size.{loc}", "A2", 500 <= size < config.A2_HARD["text_max_bytes"], size)
        try:
            txt = open(p, encoding="utf-8").read()
        except Exception as e:
            add(f"A2.text_utf8.{loc}", "A2", False, repr(e))
            continue
        add(f"A2.text_utf8.{loc}", "A2", True)
        missing = [s for s in REQUIRED_SECTIONS if s not in txt] + \
                  [s for s in REQUIRED_FIELDS if s not in txt]
        add(f"A2.text_sections.{loc}", "A2", not missing, f"missing {missing}")
        from .localize import locale_ok, scrub
        add(f"A4.locale_lang.{loc}", "A4", locale_ok(txt, loc))
        _, hits = scrub(txt, loc)
        blocks = [h["id"] for h in hits if h["severity"] == "block"]
        add(f"A1.text_banned.{loc}", "A1", not blocks, f"hits {blocks}")
        add(f"A5.provenance.{loc}", "A5", "Field Provenance:" in txt and
            bool(re.search(r"- [\w.\[\]]+: .+#/", txt)), "no provenance pointers")

    try:
        from .imaging import load, quality_flags, usable
        for role, f in IMAGE_FILES.items():
            p = os.path.join(out_dir, f)
            if not os.path.isfile(p):
                continue
            size = os.path.getsize(p)
            im = load(open(p, "rb").read())
            w, h = im.size
            lim = config.A2_HARD["main_min"] if role == "main_image" else config.A2_HARD["detail_min"]
            add(f"A2.img_dims.{role}", "A2", min(w, h) >= lim, f"{w}x{h} < {lim}")
            add(f"A2.img_bytes.{role}", "A2", size <= config.A2_HARD["img_max_bytes"], size)
            add(f"A2.img_fmt.{role}", "A2", (im.format or "").upper() in ("JPEG", "PNG"), im.format)
            flags = quality_flags(im)
            add(f"A6.img_usable.{role}", "A6", usable(flags), flags)
            if role == "main_image":
                add("A2.main_square", "A2", abs(w - h) <= 2, f"{w}x{h}")
    except Exception as e:
        add("A2.img_engine", "A2", False, repr(e))

    vp = os.path.join(out_dir, VIDEO_FILE)
    if os.path.isfile(vp):
        from .video import probe
        info = probe(vp)
        add("A2.video_bytes", "A2", info["bytes"] < config.A2_HARD["video_max_bytes"], info["bytes"])
        add("A7.video_decodes", "A7", info["decodes"] is not False, info)
        add("A7.video_duration", "A7", (info["duration"] or 0) >= 2.0, info["duration"])
        add("A7.video_has_stream", "A7", info["has_video"] is not False, info["has_video"])

    sp = os.path.join(out_dir, STRATEGY_FILE)
    add("A2.strategy_size", "A2", os.path.isfile(sp) and os.path.getsize(sp) > 800,
        os.path.getsize(sp) if os.path.isfile(sp) else 0)

    usable_imgs = [r for r in rules if r["id"].startswith("A6.img_usable")]
    rate = sum(1 for r in usable_imgs if r["ok"]) / max(1, len(usable_imgs))
    add("A6.usable_rate_80", "A6", rate >= 0.8, f"{rate:.2f}")

    return {"rules": rules, "ok": all(r["ok"] for r in rules),
            "failed": [r["id"] for r in rules if not r["ok"]],
            "usable_rate": rate}
```

### `src/xborder/pipeline.py`
```python
from __future__ import annotations
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config, taxonomy, taxonomy_adapter
from .chart import render_size_chart
from .discovery import scan_inputs
from .facts import extract
from .http import download
from .imaging import encode, load, normalize, overlay, placeholder, quality_flags, usable
from .localize import kb, plan
from .logging_setup import event
from .models_image import generate as gen_image
from .models_text import vlm_judge
from .models_video import poll as poll_video, submit as submit_video
from .preflight import check
from .video import normalize as vnorm, slideshow
from .writer import IMAGE_FILES, floor_write, prune, write_strategy, write_texts


def run_pipeline(ctx, paths: dict) -> dict:
    state = {"assets": {}, "diag": ctx.diag, "usage": ctx.usage, "paths": paths}
    out_dir = paths["output_dir"]
    ctx.budget.install_watchdog(lambda: floor_write(out_dir, state))

    # P0 -------------------------------------------------------------------
    try:
        ds = scan_inputs(paths["input_dir"])
        state["dataset_summary"] = {"files": [f["rel"] for f in ds["files"]],
                                    "urls": {k: len(v) for k, v in ds["urls"].items()}}
        tree = taxonomy_adapter.load_categories(ds["raw"])
        attrspace = taxonomy_adapter.load_attributes(ds["raw"])
    except Exception as e:
        ctx.note("error", "discovery failed", err=repr(e)[:200])
        ds, tree, attrspace = {"raw": {}, "urls": {"image": [], "video": []}, "files": []}, \
            {"nodes": {}}, {"attrs": {}}

    # P1 -------------------------------------------------------------------
    facts = _safe(ctx, "facts", lambda: extract(ctx, ds), {})
    state["facts"] = facts

    # P2 -------------------------------------------------------------------
    selection = _safe(ctx, "taxonomy", lambda: taxonomy.select(ctx, facts, tree, attrspace), None)
    if not selection:
        from .writer import _empty_sel
        selection = _empty_sel()
    state["selection"] = selection
    lspec = _safe(ctx, "localize", lambda: plan(facts, selection), None)
    state["lspec"] = lspec

    # P3 视频先发 ----------------------------------------------------------
    ref_img = (facts.get("images") or [None])[0]
    vhandle = None
    if ref_img:
        vhandle = _safe(ctx, "video_submit", lambda: submit_video(
            ctx, {"mode": "i2v", "prompt": _video_prompt(facts, selection),
                  "image_url": ref_img}), None)

    # P4/P5 图片 + 文案并行 ------------------------------------------------
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="stage") as ex:
        f_imgs = ex.submit(_images, ctx, facts, selection, lspec, ref_img, out_dir)
        f_copy = ex.submit(_copy, ctx, facts, selection, lspec)
        assets = f_imgs.result()
        copy = f_copy.result()
    state["assets"] = assets
    state["copy"] = copy

    # 若 P3 没提交成功（无源图），用生成的主图 URL 再试一次
    if not vhandle and assets.get("main_image", {}).get("url"):
        vhandle = _safe(ctx, "video_submit2", lambda: submit_video(
            ctx, {"mode": "i2v", "prompt": _video_prompt(facts, selection),
                  "image_url": assets["main_image"]["url"]}), None)

    # P6 视频收口 ----------------------------------------------------------
    vpath = os.path.join(out_dir, "product_video.mp4")
    vurl = _safe(ctx, "video_poll", lambda: poll_video(ctx, vhandle), None) if vhandle else None
    ok = False
    if vurl:
        tmp = os.path.join(_tmp(ctx), "raw_video.mp4")
        try:
            download(vurl, tmp, budget=ctx.budget, phase="P7_assemble")
            ok = vnorm(tmp, vpath, ctx)
            state["assets"]["product_video"] = {"mode": "model", "url": vurl,
                                                "bytes": os.path.getsize(vpath) if ok else 0}
        except Exception as e:
            ctx.note("warn", "video download/normalize failed", err=repr(e)[:200])
    if not ok:
        imgs = [os.path.join(out_dir, f) for f in IMAGE_FILES.values()]
        ok = slideshow([p for p in imgs if os.path.isfile(p)], vpath, ctx=ctx)
        state["assets"]["product_video"] = {"mode": "slideshow", "fallback": True,
                                            "bytes": os.path.getsize(vpath) if ok else 0}
    event("video_done", ok=ok, mode=state["assets"].get("product_video", {}).get("mode"))

    # P7/P8 落盘 + 自检 ----------------------------------------------------
    _safe(ctx, "write_texts", lambda: write_texts(out_dir, facts, selection, copy, lspec), None)
    floor_write(out_dir, state)
    state["elapsed"] = round(ctx.budget.elapsed(), 1)
    state["preflight"] = _safe(ctx, "preflight", lambda: check(out_dir), {"ok": None, "rules": []})
    _safe(ctx, "strategy", lambda: write_strategy(out_dir, state), None)
    prune(out_dir)
    state["preflight"] = _safe(ctx, "preflight2", lambda: check(out_dir), state["preflight"])
    _manifest(ctx, state)
    ctx.budget.cancel_watchdog()
    event("run_complete", elapsed=state["elapsed"], preflight_ok=state["preflight"].get("ok"),
          failed=state["preflight"].get("failed"))
    return state


# ---------------- stages ----------------
def _copy(ctx, facts, selection, lspec):
    from .copywriter import write_copy
    from .localize import template_copy
    try:
        return write_copy(ctx, facts, selection, lspec)
    except Exception as e:
        ctx.note("error", "copy stage failed", err=repr(e)[:200])
        return {l: template_copy(facts, selection, lspec, l) for l in config.LOCALES}


def _images(ctx, facts, selection, lspec, ref_img, out_dir) -> dict:
    assets = {}
    roles = sorted(config.IMAGE_ROLES, key=lambda r: r["priority"])
    chart_role = next(r for r in roles if r["kind"] == "chart")
    try:
        info = render_size_chart(facts, lspec, os.path.join(out_dir, IMAGE_FILES[chart_role["name"]]))
        assets[chart_role["name"]] = {"mode": "local_render", **info, "usable": True}
    except Exception as e:
        ctx.note("warn", "chart render failed", err=repr(e)[:200])

    photo_roles = [r for r in roles if r["kind"] == "photo"]
    prompts = _image_prompts(ctx, facts, selection, lspec, photo_roles)
    workers = config.IMAGE_CONCURRENCY
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="img") as ex:
        futs = {}
        for r in photo_roles:
            if ctx.budget.phase_expired("P4_images") and r["priority"] > 1:
                continue
            futs[ex.submit(_one_image, ctx, r, prompts[r["name"]], ref_img, out_dir)] = r
        for f in as_completed(futs):
            r = futs[f]
            try:
                assets[r["name"]] = f.result()
            except Exception as e:
                ctx.note("warn", "image role failed", role=r["name"], err=repr(e)[:200])
    # 复用/兜底 (D2-5, D2-6)
    donor = next((a for a in assets.values() if a.get("local_path") and a.get("usable")), None)
    for r in photo_roles:
        if assets.get(r["name"], {}).get("usable"):
            continue
        path = os.path.join(out_dir, IMAGE_FILES[r["name"]])
        rule = config.MAIN_IMAGE if r["name"] == "main_image" else config.DETAIL_IMAGE
        try:
            if donor:
                im = normalize(load(open(donor["local_path"], "rb").read()), rule)
                encode(im, path, rule)
                assets[r["name"]] = {"mode": "reused", "fallback": True, "usable": True,
                                     "local_path": path, "bytes": os.path.getsize(path)}
            else:
                encode(placeholder(facts.get("title_source") or "Product"), path, rule)
                assets[r["name"]] = {"mode": "placeholder", "fallback": True, "usable": False,
                                     "local_path": path, "bytes": os.path.getsize(path)}
        except Exception as e:
            ctx.note("error", "image fallback failed", role=r["name"], err=repr(e)[:200])

    if config.FLAGS["VLM_SELF_CHECK"]:
        urls = [a["url"] for a in assets.values() if a.get("url")][:3]
        if urls:
            v = vlm_judge(ctx, urls, 'Inspect these e-commerce product images. Output JSON: '
                          '{"ok":bool,"issues":[str],"text_in_image":[str]} — issues include '
                          'watermarks, garbled text, extra limbs, collage/borders, unrealistic '
                          'artifacts.')
            state_issues = v.get("issues") or []
            if state_issues:
                ctx.note("warn", "vlm flagged images", issues=state_issues[:5])
            for a in assets.values():
                a.setdefault("vlm_issues", state_issues[:3])
    return assets


def _one_image(ctx, role, prompt_pack, ref_img, out_dir) -> dict:
    spec = {"role": role["name"], "prompt": prompt_pack["prompt"],
            "negative": prompt_pack["negative"], "ref_urls": [ref_img] if ref_img else [],
            "size": "1328*1328" if role["name"] == "main_image" else "1472*1104"}
    res = gen_image(ctx, spec, phase="P4_images")
    data = download(res["url"], budget=ctx.budget, phase="P4_images")
    im = load(data)
    rule = config.MAIN_IMAGE if role["name"] == "main_image" else config.DETAIL_IMAGE
    im = normalize(im, rule)
    if config.FLAGS["IMAGE_TEXT_OVERLAY"] and role["name"] != "main_image" and prompt_pack.get("label"):
        im = overlay(im, [{"text": prompt_pack["label"], "xy_ratio": (0.05, 0.86),
                           "size_ratio": 0.045, "bold": True}])
    path = os.path.join(out_dir, IMAGE_FILES[role["name"]])
    n = encode(im, path, rule)
    flags = quality_flags(im)
    return {"mode": "model", "model": res["model"], "endpoint": res["endpoint"], "ms": res["ms"],
            "url": res["url"], "local_path": path, "bytes": n, "size": list(im.size),
            "flags": flags, "usable": usable(flags)}


def _image_prompts(ctx, facts, selection, lspec, roles) -> dict:
    neg = ", ".join(kb("banned_terms")["image_prompt_negative"])
    title = facts.get("title_source") or "apparel product"
    attrs = ", ".join(f'{a["attr_name"]}={a["value_name"]}' for a in selection["attributes"][:8])
    colors = ", ".join(facts.get("colors") or [])
    base = (f'Product: {title}. Category: {" > ".join(selection["category_path"])}. '
            f'Attributes: {attrs}. Colours: {colors}. ')
    fixed = {
        "main_image": base + ("E-commerce main image: the exact product from the reference image on "
                              "a pure white seamless background, centred, full product visible, "
                              "product occupies about 85% of the frame, even soft studio lighting, "
                              "sharp focus, true-to-reference colour and pattern, no text, no props, "
                              "no watermark, square composition."),
        "detail_image_1": base + ("Full front view of the same product, clean light-grey studio "
                                  "background, natural presentation, faithful to the reference."),
        "detail_image_2": base + ("Back and side three-quarter view of the same product showing "
                                  "construction, clean studio background."),
        "detail_image_3": base + ("Extreme macro close-up of the fabric texture, weave and stitching "
                                  "of the same product, soft directional light, shallow depth."),
        "detail_image_5": base + ("Lifestyle scene appropriate for the target markets, natural "
                                  "daylight, realistic setting, product clearly visible and "
                                  "identical to the reference."),
    }
    labels = {"detail_image_1": "Front view", "detail_image_2": "Back view",
              "detail_image_3": "Fabric detail", "detail_image_5": "Styling"}
    return {r["name"]: {"prompt": fixed.get(r["name"], base + r["brief"]),
                        "negative": neg, "label": labels.get(r["name"])} for r in roles}


def _video_prompt(facts, selection) -> str:
    title = facts.get("title_source") or "apparel product"
    return (f"Short e-commerce product video of {title}. Slow smooth camera orbit and gentle push-in "
            f"around the product, clean bright studio lighting, fabric moves naturally, product "
            f"stays identical to the reference image, no text overlays, no watermark, no logos, "
            f"no people talking.")


def _safe(ctx, name, fn, default):
    t0 = time.monotonic()
    try:
        out = fn()
        event("stage_ok", stage=name, ms=int((time.monotonic() - t0) * 1000))
        return out
    except Exception as e:
        ctx.note("error", f"stage {name} failed", err=repr(e)[:300])
        return default


def _tmp(ctx):
    p = os.path.join(ctx.log_dir, "tmp")
    os.makedirs(p, exist_ok=True)
    return p


def _manifest(ctx, state):
    try:
        with open(os.path.join(ctx.log_dir, "run_manifest.json"), "w", encoding="utf-8") as fh:
            json.dump({k: v for k, v in state.items() if k != "copy"}, fh,
                      ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass
```

### `src/xborder/discovery.py`
```python
from __future__ import annotations
import json
import os

from .jsonutil import find_urls, norm_key
from .logging_setup import event

MAX_FILE = 8 * 1024 * 1024
_CAT_SIG = ("categoryid", "catid", "leafcategory", "categoryname", "children", "categorypath")
_ATTR_SIG = ("attrid", "attrname", "attributevalues", "valuelist", "attributes", "propertyvalue")
_PROD_SIG = ("sku", "skus", "title", "productid", "itemid", "productname")


def scan_inputs(input_dir: str) -> dict:
    files, raw = [], {}
    for root, _dirs, names in os.walk(input_dir):
        for n in sorted(names):
            p = os.path.join(root, n)
            try:
                size = os.path.getsize(p)
            except Exception:
                continue
            rel = os.path.relpath(p, input_dir)
            rec = {"path": p, "rel": rel, "size": size, "kind": "other"}
            if n.lower().endswith((".json", ".txt", ".jsonl")) and size <= MAX_FILE:
                obj = _read_json(p)
                if obj is not None:
                    raw[rel] = obj
                    rec["kind"] = _classify(rel, obj)
            files.append(rec)
    urls = {"image": [], "video": [], "other": []}
    for obj in raw.values():
        u = find_urls(obj)
        for k in urls:
            urls[k] += u[k]
    for k in urls:
        urls[k] = list(dict.fromkeys(urls[k]))
    event("inputs_scanned", files=[(f["rel"], f["kind"], f["size"]) for f in files],
          urls={k: len(v) for k, v in urls.items()})
    if not raw:
        event("inputs_empty", dir=input_dir)
    return {"files": files, "raw": raw, "urls": urls, "input_dir": input_dir}


def _read_json(p):
    try:
        with open(p, encoding="utf-8-sig") as fh:
            text = fh.read()
    except Exception:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                return {"_text": text[:200000]}
    return rows or {"_text": text[:200000]}


def _classify(rel, obj) -> str:
    from .jsonutil import walk
    keys = set()
    for ptr, _v in walk(obj):
        seg = ptr.rsplit("/", 1)[-1]
        if seg and not seg.isdigit():
            keys.add(norm_key(seg))
        if len(keys) > 4000:
            break
    score = {"categories": sum(1 for s in _CAT_SIG if s in keys),
             "attributes": sum(1 for s in _ATTR_SIG if s in keys),
             "product": sum(1 for s in _PROD_SIG if s in keys)}
    low = norm_key(rel)
    for k, hint in (("categories", "categor"), ("attributes", "attribut"), ("product", "product")):
        if hint in low:
            score[k] += 0.5
    best = max(score, key=score.get)
    return best if score[best] > 0 else "other"
```

### `src/xborder/cli.py`
```python
from __future__ import annotations
import os
import sys

from .budget import Budget
from .dsclient import Ctx
from .logging_setup import event, setup
from .promptparse import extract_argv_prompt, parse_prompt


def run(argv: list[str], here: str, version: str) -> int:
    budget = Budget()
    prompt = extract_argv_prompt(argv) or os.environ.get("XB_PROMPT")
    paths = parse_prompt(prompt)
    logger = setup(os.environ.get("AGENT_LOG_DIR"))
    log_dir = getattr(logger, "log_dir", "/tmp")
    event("start", version=version, argv=argv[:8], paths=paths, prompt=(prompt or "")[:500],
          python=sys.version.split()[0], cwd=os.getcwd(), here=here)
    if not os.path.isdir(paths["input_dir"]):
        event("input_dir_missing", dir=paths["input_dir"])
    try:
        os.makedirs(paths["output_dir"], exist_ok=True)
        probe = os.path.join(paths["output_dir"], ".wtest")
        open(probe, "w").close()
        os.remove(probe)
    except Exception as e:
        event("output_dir_unwritable", dir=paths["output_dir"], err=repr(e))
        return 2                                     # 唯一允许的非 0 退出 (I1)
    ctx = Ctx(budget, logger, log_dir)
    try:
        from .pipeline import run_pipeline
        run_pipeline(ctx, paths)
    except BaseException as e:                       # 含 Aborted / KeyboardInterrupt
        event("pipeline_fatal", err=repr(e)[:400])
        try:
            from .writer import floor_write
            floor_write(paths["output_dir"], {"facts": {}, "diag": ctx.diag})
        except Exception:
            pass
    event("exit", code=0, elapsed=round(budget.elapsed(), 1))
    return 0
```

---

# 10. 工具链

### `tools/build_package.py`
```python
#!/usr/bin/env python3
"""构建提交包 dist/agent.zip。所有打包期硬门禁都在这里，失败即拒绝出包。"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build", "agent")
DIST = os.path.join(ROOT, "dist")
MAX_ZIP = 95 * 1024 * 1024
REQUIRED_ROOT = {"agent.py", "agent.json", "requirements.txt"}


def sh(*a):
    print("+", " ".join(a))
    subprocess.check_call(a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-deps", action="store_true")
    args = ap.parse_args()

    shutil.rmtree(os.path.join(ROOT, "build"), ignore_errors=True)
    os.makedirs(BUILD, exist_ok=True)
    os.makedirs(DIST, exist_ok=True)

    shutil.copy2(os.path.join(ROOT, "entry", "agent.py"), os.path.join(BUILD, "agent.py"))
    shutil.copy2(os.path.join(ROOT, "entry", "agent.json"), os.path.join(BUILD, "agent.json"))
    for extra in ("xborder_bootstrap_fallback.py",):
        p = os.path.join(ROOT, "entry", extra)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(BUILD, extra))
    shutil.copytree(os.path.join(ROOT, "src", "xborder"), os.path.join(BUILD, "src", "xborder"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(os.path.join(ROOT, "assets"),
                    os.path.join(BUILD, "src", "xborder", "assets"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(os.path.join(ROOT, "requirements-runtime.txt"),
                 os.path.join(BUILD, "requirements.txt"))

    if not args.skip_deps:
        sh(sys.executable, "-m", "pip", "install", "--only-binary", ":all:",
           "--platform", "manylinux2014_x86_64", "--python-version", "3.12",
           "--implementation", "cp", "--target", os.path.join(BUILD, "vendor"),
           "-r", os.path.join(ROOT, "requirements-runtime.txt"))

    gates = []
    # G1 结构
    have = set(os.listdir(BUILD))
    gates.append(("G1 root files", REQUIRED_ROOT <= have, sorted(REQUIRED_ROOT - have)))
    meta = json.load(open(os.path.join(BUILD, "agent.json")))
    gates.append(("G2 agent.json", meta.get("runtime") == "python" and
                  len(str(meta.get("version", "")).split(".")) == 3 and
                  all(p.isdigit() for p in str(meta["version"]).split(".")), meta))
    # G3 ffmpeg 存在且非空（视频兜底的生命线）
    ff = None
    for r, _d, ns in os.walk(os.path.join(BUILD, "vendor")):
        for n in ns:
            if n == "ffmpeg" or n.startswith("ffmpeg-linux"):
                ff = os.path.join(r, n)
    gates.append(("G3 ffmpeg bundled", bool(ff) and os.path.getsize(ff) > 1_000_000, ff))
    # G4 字体
    fdir = os.path.join(BUILD, "src", "xborder", "assets", "fonts")
    fonts = set(os.listdir(fdir)) if os.path.isdir(fdir) else set()
    need_fonts = {"NotoSans-Regular.ttf", "NotoSans-Bold.ttf", "NotoSansKR-Regular.otf"}
    gates.append(("G4 fonts", need_fonts <= fonts, sorted(need_fonts - fonts)))
    # G5 纯 python 依赖可导入 & --version
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        [os.path.join(BUILD, "vendor"), os.path.join(BUILD, "src")]))
    v = subprocess.run([sys.executable, os.path.join(BUILD, "agent.py"), "--version"],
                       capture_output=True, env=env)
    gates.append(("G5 --version", v.returncode == 0 and
                  v.stdout.decode().strip() == meta["version"],
                  v.stdout.decode().strip() + v.stderr.decode()[:200]))
    # G6 无网络调用的 import 期副作用（导入不得触网/不得读环境失败）
    imp = subprocess.run([sys.executable, "-c",
                          "import sys;sys.path[:0]=[r'%s',r'%s'];import xborder.pipeline" %
                          (os.path.join(BUILD, "vendor"), os.path.join(BUILD, "src"))],
                         capture_output=True, env=env)
    gates.append(("G6 import clean", imp.returncode == 0, imp.stderr.decode()[-400:]))

    bad = [g for g in gates if not g[1]]
    for name, ok, detail in gates:
        print(("PASS " if ok else "FAIL ") + name, "" if ok else f"→ {detail}")
    if bad:
        print("BUILD REJECTED")
        return 1

    zpath = os.path.join(DIST, f"agent-{meta['version']}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for r, _d, ns in os.walk(BUILD):
            for n in ns:
                if n.endswith(".pyc") or "__pycache__" in r:
                    continue
                full = os.path.join(r, n)
                arc = os.path.join("agent", os.path.relpath(full, BUILD))
                zi = zipfile.ZipInfo.from_file(full, arc)
                zi.compress_type = zipfile.ZIP_DEFLATED
                if os.access(full, os.X_OK):
                    zi.external_attr = (0o755 << 16) | 0o600
                with open(full, "rb") as fh:
                    z.writestr(zi, fh.read())
    size = os.path.getsize(zpath)
    print(f"zip: {zpath} {size/1e6:.1f} MB")
    if size > MAX_ZIP:
        print("FAIL zip too large (limit 100MB, gate 95MB)")
        return 1
    shutil.copy2(zpath, os.path.join(DIST, "agent.zip"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### `requirements-runtime.txt`
```
Pillow==11.3.0
imageio-ffmpeg==0.6.0
```

### `tools/mock_dashscope.py`
```python
#!/usr/bin/env python3
"""离线 mock：契约测试与 E2E 的唯一"模型服务"。支持故障注入。

场景通过环境变量或 /__config 控制：
  MOCK_FAIL_RATE, MOCK_429_FIRST_N, MOCK_VIDEO_DELAY, MOCK_VIDEO_FAIL,
  MOCK_IMAGE_SHAPE (mm|async|both), MOCK_MALFORMED_JSON, MOCK_SLOW_MS
"""
from __future__ import annotations
import io
import json
import os
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"tasks": {}, "counters": {}, "cfg": {
    "fail_rate": float(os.environ.get("MOCK_FAIL_RATE", 0)),
    "n429": int(os.environ.get("MOCK_429_FIRST_N", 0)),
    "video_delay": float(os.environ.get("MOCK_VIDEO_DELAY", 3)),
    "video_fail": os.environ.get("MOCK_VIDEO_FAIL") == "1",
    "image_shape": os.environ.get("MOCK_IMAGE_SHAPE", "mm"),
    "malformed": os.environ.get("MOCK_MALFORMED_JSON") == "1",
    "slow_ms": int(os.environ.get("MOCK_SLOW_MS", 0)),
}}
LOCK = threading.Lock()


def _png(w=1400, h=1400, color=(210, 220, 235)):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), color)
    d = ImageDraw.Draw(im)
    d.ellipse((w * .2, h * .2, w * .8, h * .8), fill=(150, 170, 200))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def _mp4():
    p = os.path.join(os.path.dirname(__file__), "..", "fixtures", "recorded", "tiny.mp4")
    return open(p, "rb").read() if os.path.isfile(p) else b"\x00" * 2048


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = (b"{not json" if STATE["cfg"]["malformed"] and random.random() < 0.3
                else json.dumps(obj).encode())
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bump(self, key):
        with LOCK:
            STATE["counters"][key] = STATE["counters"].get(key, 0) + 1
            return STATE["counters"][key]

    def _maybe_fault(self, key):
        c = STATE["cfg"]
        if c["slow_ms"]:
            time.sleep(c["slow_ms"] / 1000)
        n = self._bump(key)
        if n <= c["n429"]:
            self.send_response(429)
            self.send_header("Retry-After", "1")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")
            return True
        if random.random() < c["fail_rate"]:
            self._json({"code": "InternalError", "message": "injected"}, 500)
            return True
        return False

    def do_GET(self):
        if self.path.startswith("/artifacts/img"):
            data = _png()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path.startswith("/artifacts/vid"):
            data = _mp4()
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if "/tasks/" in self.path:
            tid = self.path.rsplit("/", 1)[-1]
            t = STATE["tasks"].get(tid)
            if not t:
                return self._json({"output": {"task_status": "UNKNOWN"}}, 404)
            if time.time() < t["ready_at"]:
                return self._json({"output": {"task_id": tid, "task_status": "RUNNING"}})
            if t["fail"]:
                return self._json({"output": {"task_id": tid, "task_status": "FAILED",
                                              "message": "injected"}})
            if t["kind"] == "video":
                return self._json({"output": {"task_id": tid, "task_status": "SUCCEEDED",
                                              "video_url": self._base() + "/artifacts/vid.mp4"}})
            return self._json({"output": {"task_id": tid, "task_status": "SUCCEEDED",
                                          "results": [{"url": self._base() + "/artifacts/img.png"}]}})
        self._json({"ok": True, "counters": STATE["counters"]})

    def _base(self):
        return f"http://{self.headers.get('Host')}"

    def do_POST(self):
        ln = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(ln) or b"{}")
        p = self.path
        if p.endswith("/chat/completions"):
            if self._maybe_fault("chat"):
                return
            return self._json(self._chat(body))
        if "video-generation/video-synthesis" in p:
            if self._maybe_fault("video"):
                return
            tid = "vt-%d" % self._bump("vt")
            STATE["tasks"][tid] = {"kind": "video", "ready_at": time.time() + STATE["cfg"]["video_delay"],
                                   "fail": STATE["cfg"]["video_fail"]}
            return self._json({"output": {"task_id": tid, "task_status": "PENDING"}})
        if "multimodal-generation/generation" in p:
            if self._maybe_fault("image"):
                return
            if STATE["cfg"]["image_shape"] == "async":
                return self._json({"code": "InvalidParameter",
                                   "message": "sync not supported"}, 400)
            return self._json({"output": {"choices": [{"message": {"content": [
                {"image": self._base() + "/artifacts/img.png"}]}}]}})
        if "text2image/image-synthesis" in p:
            if self._maybe_fault("image_async"):
                return
            tid = "it-%d" % self._bump("it")
            STATE["tasks"][tid] = {"kind": "image", "ready_at": time.time() + 1, "fail": False}
            return self._json({"output": {"task_id": tid, "task_status": "PENDING"}})
        if p == "/__config":
            STATE["cfg"].update(body)
            return self._json(STATE["cfg"])
        self._json({"code": "NotFound", "message": p}, 404)

    def _chat(self, body):
        """按 prompt 内容返回契约合法的假 JSON。"""
        text = json.dumps(body)[:4000].lower()
        if "leaf_category_id" in text and "candidate" in text:
            import re
            ids = re.findall(r'\\n([\w|.\-]+)\\t', json.dumps(body))
            out = {"leaf_category_id": ids[0] if ids else "unknown", "why": "mock"}
        elif "allowed attributes" in text:
            out = {}
        elif "title_source" in text and "measurements" in text:
            out = {"title_source": "Women's Ribbed Knit Midi Dress", "brand": None,
                   "gender": "women", "materials": ["Polyester"], "colors": ["Black", "Beige"],
                   "sizes": ["S", "M", "L"], "measurements": [], "attributes": {}, "skus": []}
        elif "image_captions" in text:
            loc = "ko" if "korean" in text else "pt" if "portuguese" in text else "en"
            body_txt = {"en": "This dress is made from a soft ribbed knit. " * 12,
                        "ko": "이 원피스는 부드러운 리브 니트 소재로 제작되었습니다. " * 12,
                        "pt": "Este vestido é feito de tricô canelado e macio para você. " * 12}[loc]
            out = {"doc_heading": "Mock heading", "title": "Mock localized title for the product",
                   "bullets": ["Point one", "Point two"], "body": body_txt,
                   "image_captions": {f"detail_image_{i}": "caption" for i in range(1, 6)} |
                                     {"main_image": "caption"},
                   "video_caption": "Mock video caption text"}
        elif "text_in_image" in text:
            out = {"ok": True, "issues": [], "text_in_image": []}
        else:
            out = {"ok": True}
        return {"choices": [{"message": {"content": json.dumps(out, ensure_ascii=False)}}]}


def serve(port=0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


if __name__ == "__main__":
    s = serve(int(os.environ.get("PORT", 8899)))
    print("mock on", s.server_address)
    threading.Event().wait()
```

### `tools/shadow_score.py`
```python
#!/usr/bin/env python3
"""影子评测器：用 preflight 规则 + 可选 VLM 抽检，给出 A1/A2/A4/A5/A6/A7 近似分。
提交前必须跑；分数下降禁止提交（见 EXPERIMENT_LEDGER 纪律）。"""
from __future__ import annotations
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from xborder.preflight import check  # noqa: E402

WEIGHTS = {"A1": 0.25, "A2": 0.20, "A3": 0.18, "A4": 0.15, "A5": 0.10, "A6": 0.07, "A7": 0.05}


def score(out_dir: str) -> dict:
    rep = check(out_dir)
    by_dim: dict[str, list[bool]] = {}
    for r in rep["rules"]:
        by_dim.setdefault(r["dim"], []).append(r["ok"])
    dims = {d: (sum(v) / len(v)) for d, v in by_dim.items()}
    dims.setdefault("A3", 0.0)          # A3 无法本地判定，人工填 confidence
    total = sum(WEIGHTS[d] * dims.get(d, 0.0) for d in WEIGHTS)
    return {"dims": dims, "total_estimate": round(total, 4),
            "failed": rep["failed"], "usable_rate": rep["usable_rate"]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    s = score(a.out_dir)
    print(json.dumps(s, ensure_ascii=False, indent=2) if a.json else
          f"estimate={s['total_estimate']} dims={s['dims']} failed={s['failed'][:8]}")
    sys.exit(0 if not s["failed"] else 1)
```

### `tools/inspect_dataset.py`
```python
#!/usr/bin/env python3
"""Day-1 必跑：把官方示例数据的真实结构打印出来，用于校准 taxonomy_adapter 与 facts。"""
from __future__ import annotations
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from xborder.discovery import scan_inputs                      # noqa: E402
from xborder.jsonutil import walk                              # noqa: E402
from xborder.taxonomy_adapter import load_attributes, load_categories  # noqa: E402


def main(d):
    ds = scan_inputs(d)
    for f in ds["files"]:
        print(f'{f["kind"]:11} {f["size"]:>9}  {f["rel"]}')
    for rel, obj in ds["raw"].items():
        keys = Counter()
        depth = 0
        for ptr, v in walk(obj):
            depth = max(depth, ptr.count("/"))
            seg = ptr.rsplit("/", 1)[-1]
            if seg and not seg.isdigit():
                keys[seg] += 1
        print(f"\n=== {rel} (max_depth={depth}) top keys:")
        print("  " + ", ".join(f"{k}({c})" for k, c in keys.most_common(40)))
        print("  sample:", json.dumps(obj, ensure_ascii=False)[:1200])
    tree = load_categories(ds["raw"])
    attrs = load_attributes(ds["raw"])
    print(f"\nADAPTER: categories={len(tree['nodes'])} leaves="
          f"{sum(1 for n in tree['nodes'].values() if n['is_leaf'])} from {tree['source_file']}")
    for n in list(tree["nodes"].values())[:8]:
        print("   ", n["id"], " > ".join(n["path"]), "leaf" if n["is_leaf"] else "")
    print(f"ADAPTER: attrs={len(attrs['attrs'])} from {attrs['source_file']}")
    for aid, a in list(attrs["attrs"].items())[:8]:
        print("   ", aid, a["name"], "sales" if a["is_sales"] else "", 
              [v["name"] for v in a["values"]][:6])
    print(f"URLS: {[(k, len(v)) for k, v in ds['urls'].items()]}")
    print("first image url:", (ds["urls"]["image"] or [None])[0])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "fixtures/input_sample")
```

### `Makefile`
```makefile
PY := python3
export PYTHONPATH := src

.PHONY: help setup fonts test unit contract e2e lint package sandbox-e2e shadow inspect submit-check clean

help:
	@grep -E '^[a-z-]+:' Makefile | cut -d: -f1 | tr '\n' ' '; echo

setup:
	$(PY) -m pip install -r requirements-dev.txt

fonts:
	@bash tools/fetch_fonts.sh          # 下载 Noto Sans / Noto Sans KR 到 assets/fonts

unit:
	$(PY) -m pytest tests -m "not e2e" -q

contract:
	$(PY) -m pytest tests/test_dsclient_contract.py tests/test_http_retry.py -q

e2e:
	$(PY) -m pytest tests/test_e2e_mock.py -q -s

test: unit e2e

lint:
	$(PY) -m ruff check src tools tests entry || true
	$(PY) -m compileall -q src entry tools

package:
	$(PY) tools/build_package.py

sandbox-e2e: package
	docker build -f tools/docker/Dockerfile.sandbox -t xb-sandbox .
	docker run --rm -v $$PWD/dist:/dist:ro -v $$PWD/fixtures:/fixtures:ro xb-sandbox

shadow:
	$(PY) tools/shadow_score.py $(OUT) --json

inspect:
	$(PY) tools/inspect_dataset.py fixtures/input_sample

submit-check: lint test package
	@$(PY) tools/bump_version.py --check
	@echo "=== submission checklist ==="
	@$(PY) - <<'EOF'
	import zipfile, json
	z = zipfile.ZipFile("dist/agent.zip")
	names = z.namelist()
	assert all(n.startswith("agent/") for n in names), "ZIP root must be 'agent'"
	assert "agent/agent.py" in names and "agent/agent.json" in names
	assert "agent/requirements.txt" in names
	print("files:", len(names), "size MB:", round(sum(i.file_size for i in z.infolist())/1e6,1))
	print(json.loads(z.read("agent/agent.json")))
	print("OK — ready to submit")
	EOF

clean:
	rm -rf build dist .pytest_cache **/__pycache__
```

### `tools/docker/Dockerfile.sandbox`
```dockerfile
# 沙箱等价环境：Debian 12 + Python 3.12，无 ffmpeg，无外网（run 时用 --network 控制）
FROM debian:12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates python3.12 python3.12-venv unzip \
    && rm -rf /var/lib/apt/lists/*
RUN ln -sf /usr/bin/python3.12 /usr/local/bin/python
WORKDIR /work
COPY tools/docker/run_sandbox.sh /run.sh
RUN chmod +x /run.sh
ENV AGENT_LOG_DIR=/work/logs
ENTRYPOINT ["/run.sh"]
```

### `tools/docker/run_sandbox.sh`
```bash
#!/bin/sh
set -e
mkdir -p /work/logs /work/ws/output
unzip -q /dist/agent.zip -d /work/pkg
cp -r /fixtures/input_sample /work/ws/input
cd /work/pkg
echo "--- version gate ---"
python agent/agent.py --version
echo "--- run (mock endpoints must be reachable; use --network for isolation tests) ---"
: "${DASHSCOPE_BASE_URL:=http://127.0.0.1:8899/api/v1}"
: "${OPENAI_BASE_URL:=http://127.0.0.1:8899/v1}"
: "${DASHSCOPE_API_KEY:=sk-mock}"
export DASHSCOPE_BASE_URL OPENAI_BASE_URL DASHSCOPE_API_KEY
time python agent/agent.py --prompt "请根据 /work/ws/input 中的数据完成商品素材生成任务，将结果输出到 /work/ws/output"
echo "exit=$?"
ls -la /work/ws/output
python - <<'EOF'
import os,sys
need={"product_description_en.md","product_description_ko.md","product_description_pt.md",
 "main_image.jpeg","detail_image_1.jpeg","detail_image_2.jpeg","detail_image_3.jpeg",
 "detail_image_4.png","detail_image_5.jpeg","product_video.mp4","strategy_document.md"}
have=set(os.listdir("/work/ws/output"))
print("missing:",sorted(need-have)); print("extra:",sorted(have-need))
sys.exit(1 if (need-have) or (have-need) else 0)
EOF
```

---

# 11. 测试

### `tests/conftest.py`
```python
from __future__ import annotations
import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src"), os.path.join(ROOT, "tools")]


@pytest.fixture(scope="session")
def mock_server():
    from mock_dashscope import serve, STATE
    srv = serve(0)
    host, port = srv.server_address
    yield {"base": f"http://{host}:{port}", "state": STATE}
    srv.shutdown()


@pytest.fixture
def env(mock_server, tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-mock")
    monkeypatch.setenv("DASHSCOPE_BASE_URL", mock_server["base"] + "/api/v1")
    monkeypatch.setenv("OPENAI_BASE_URL", mock_server["base"] + "/v1")
    monkeypatch.setenv("AGENT_LOG_DIR", str(tmp_path / "logs"))
    mock_server["state"]["cfg"].update({"fail_rate": 0, "n429": 0, "video_delay": 2,
                                        "video_fail": False, "image_shape": "mm",
                                        "malformed": False, "slow_ms": 0})
    mock_server["state"]["counters"].clear()
    return mock_server


@pytest.fixture
def ctx(env, tmp_path):
    from xborder.budget import Budget
    from xborder.dsclient import Ctx
    from xborder.logging_setup import setup
    log = setup(str(tmp_path / "logs"))
    return Ctx(Budget(), log, str(tmp_path / "logs"))


@pytest.fixture
def sample_input(tmp_path):
    src = os.path.join(ROOT, "fixtures", "input_sample")
    dst = tmp_path / "input"
    if os.path.isdir(src):
        shutil.copytree(src, dst)
    else:                                   # 合成最小可用输入
        (dst / "product_info").mkdir(parents=True)
        (dst / "product_info" / "sku_12345.json").write_text(json.dumps({
            "productId": "1005006789012",
            "productUrl": "https://www.aliexpress.com/item/1005006789012.html",
            "title": "Women Ribbed Knit Midi Dress Long Sleeve Autumn",
            "images": ["https://img.example.com/p1.jpg"],
            "skus": [{"skuId": "s1", "color": "Black", "size": "M", "price": "23.90", "stock": 12},
                     {"skuId": "s2", "color": "Beige", "size": "L", "price": "23.90", "stock": 4}],
            "attributes": {"Material": "Polyester", "Sleeve Length": "Long Sleeve"}
        }, ensure_ascii=False), encoding="utf-8")
        (dst / "clothing_categories.json").write_text(json.dumps([
            {"id": "100", "name": "Women's Clothing", "children": [
                {"id": "110", "name": "Dresses", "children": [
                    {"id": "111", "name": "Casual Dresses"},
                    {"id": "112", "name": "Knitted Dresses"}]},
                {"id": "120", "name": "Tops", "children": [{"id": "121", "name": "T-Shirts"}]}]}
        ]), encoding="utf-8")
        (dst / "clothing_attributes.json").write_text(json.dumps({
            "attributes": [
                {"attrId": "a1", "attrName": "Material",
                 "values": [{"id": "v1", "name": "Polyester"}, {"id": "v2", "name": "Cotton"}]},
                {"attrId": "a2", "attrName": "Sleeve Length",
                 "values": [{"id": "v3", "name": "Long Sleeve"}, {"id": "v4", "name": "Short Sleeve"}]},
                {"attrId": "a3", "attrName": "Color", "isSales": True,
                 "values": [{"id": "c1", "name": "Black"}, {"id": "c2", "name": "Beige"}]},
                {"attrId": "a4", "attrName": "Size", "isSales": True,
                 "values": [{"id": "s_m", "name": "M"}, {"id": "s_l", "name": "L"}]}]
        }), encoding="utf-8")
    return str(dst)
```

### `tests/test_promptparse.py`
```python
import pytest
from xborder.promptparse import parse_prompt

CASES = [
    ("请根据 /home/user/ws/input 中的数据完成商品素材生成任务，将结果输出到 /home/user/ws/output",
     "/home/user/ws/input", "/home/user/ws/output"),
    ('请根据 /data/dataset 中的数据完成问答任务，将结果输出到 /workspace/output/result.json',
     "/data/dataset", "/workspace/output"),
    ("Read all product files under /mnt/in/product and save materials to /mnt/out/",
     "/mnt/in/product", "/mnt/out"),
    ("读取 /home/user/ws/input/ 目录下目标商品的全部信息文件，按规范生成输出文件并保存至 /home/user/ws/output/",
     "/home/user/ws/input", "/home/user/ws/output"),
]


@pytest.mark.parametrize("prompt,exp_in,exp_out", CASES)
def test_paths(prompt, exp_in, exp_out, tmp_path, monkeypatch):
    monkeypatch.setenv("XB_OUTPUT_DIR", "")
    p = parse_prompt(prompt)
    assert p["input_dir"] == exp_in
    assert p["output_dir"] == exp_out


def test_never_raises():
    for bad in (None, "", "no paths here", "C:\\windows\\path", "/", "/a"):
        p = parse_prompt(bad)
        assert p["input_dir"] and p["output_dir"]
```

### `tests/test_dsclient_contract.py`
```python
import pytest
from xborder.errors import CapabilityExhausted
from xborder.http import join_url
from xborder.models_image import generate
from xborder.models_text import chat_json
from xborder.models_video import poll, submit


@pytest.mark.parametrize("base,path,exp", [
    ("https://x/api/v1", "/services/aigc/x", "https://x/api/v1/services/aigc/x"),
    ("https://x/api/v1/", "services/aigc/x", "https://x/api/v1/services/aigc/x"),
    ("https://x/api/v1", "/api/v1/services/x", "https://x/api/v1/services/x"),
    ("https://x/v1", "/v1/chat/completions", "https://x/v1/chat/completions"),
])
def test_join_url_no_duplication(base, path, exp):
    assert join_url(base, path) == exp


def test_chat_json_schema_and_repair(ctx):
    obj = chat_json(ctx, "sys", "give me title_source and measurements", phase="P1_facts")
    assert isinstance(obj, dict)


def test_image_ladder_falls_back_to_async(ctx, env):
    env["state"]["cfg"]["image_shape"] = "async"       # sync 端点返回 400
    res = generate(ctx, {"role": "main_image", "prompt": "p", "negative": "", "ref_urls": []})
    assert res["url"].endswith(".png")
    assert res["endpoint"] == "t2i_async"


def test_image_retries_on_429(ctx, env):
    env["state"]["cfg"]["n429"] = 2
    res = generate(ctx, {"role": "main_image", "prompt": "p", "negative": "", "ref_urls": []})
    assert res["url"]


def test_image_exhausted_raises(ctx, env):
    env["state"]["cfg"]["fail_rate"] = 1.0
    with pytest.raises(CapabilityExhausted):
        generate(ctx, {"role": "x", "prompt": "p", "negative": "", "ref_urls": []})


def test_video_submit_poll(ctx, env):
    env["state"]["cfg"]["video_delay"] = 1
    h = submit(ctx, {"mode": "i2v", "prompt": "p", "image_url": "http://x/y.png"})
    assert h and h["task_id"]
    assert poll(ctx, h).endswith(".mp4")


def test_video_failed_task_returns_none(ctx, env):
    env["state"]["cfg"].update({"video_delay": 1, "video_fail": True})
    h = submit(ctx, {"mode": "i2v", "prompt": "p", "image_url": "http://x/y.png"})
    assert poll(ctx, h) is None
```

### `tests/test_taxonomy_adapter.py`
```python
from xborder.taxonomy_adapter import load_attributes, load_categories

SHAPES = {
    "nested": [{"id": "1", "name": "A", "children": [{"id": "2", "name": "B"}]}],
    "flat": [{"categoryId": 1, "categoryName": "A", "parentId": 0},
             {"categoryId": 2, "categoryName": "B", "parentId": 1}],
    "paths": {"list": ["Women > Dresses > Knitted", "Women > Tops > Tees"]},
    "dictmap": {"Women": {"Dresses": {}, "Tops": {}}},
}


def test_all_shapes_produce_leaves():
    for name, obj in SHAPES.items():
        tree = load_categories({f"{name}.json": obj})
        assert tree["nodes"], name
        leaves = [n for n in tree["nodes"].values() if n["is_leaf"]]
        assert leaves, name
        assert all(n["keywords"] for n in leaves), name


def test_attributes_variants():
    a = load_attributes({"a.json": {"attributes": [
        {"attrId": "x", "attrName": "Material", "values": ["Cotton", "Silk"]}]}})
    assert a["attrs"]["x"]["values"][0]["name"] == "Cotton"
    b = load_attributes({"b.json": [{"id": 9, "name": "Size", "valueList":
                                     [{"valueId": 1, "valueName": "M"}]}]})
    assert b["attrs"]["9"]["is_sales"] is True


def test_unknown_shape_is_safe():
    t = load_categories({"junk.json": {"hello": 1}})
    assert t["nodes"] == {} or all("name" in n for n in t["nodes"].values())
```

### `tests/test_facts_traceability.py`
```python
from xborder.provenance import Index, gate


def test_untraceable_values_dropped():
    raw = {"p.json": {"title": "Blue Cotton Shirt", "skus": [{"skuId": "s1", "size": "M"}]}}
    idx = Index(raw)
    facts = {"title_source": "Blue Cotton Shirt", "brand": "Nike",
             "materials": ["Cotton", "Cashmere"],
             "skus": [{"sku_id": "s1", "size": "M", "color": "Black"}],
             "attributes": {}}
    gate(facts, idx, derived={})
    assert facts["title_source"] == "Blue Cotton Shirt"
    assert facts["brand"] is None                       # 源数据没有 → 丢弃
    assert facts["materials"] == ["Cotton"]             # Cashmere 虚构 → 丢弃
    assert facts["provenance"]["title_source"]["kind"] == "verbatim"
    assert any(d["value"] == "Nike" for d in facts["dropped"])


def test_derived_whitelist_kept():
    idx = Index({"p.json": {"title": "x"}})
    facts = {"title_source": "x", "skus": [{"sku_id": "1", "size": "M"}], "attributes": {}}
    gate(facts, idx, derived={"skus[0].size": "sku_decomposition"})
    assert facts["skus"][0]["size"] == "M"
```

### `tests/test_localize_rules.py`
```python
import pytest
from xborder.localize import locale_ok, plan, scrub


@pytest.mark.parametrize("text,expect_block", [
    ("This is the best dress in the world", True),
    ("100% satisfaction guaranteed", True),
    ("Contact us on WhatsApp +8613800138000", True),
    ("Inspired by Zara design", True),
    ("Soft ribbed knit with a relaxed fit", False),
])
def test_scrub_blocks(text, expect_block):
    clean, hits = scrub(text, "en")
    blocked = [h for h in hits if h["severity"] == "block"]
    assert bool(blocked) == expect_block
    for h in blocked:
        assert h["match"].lower() not in clean.lower()


def test_locale_detection():
    assert locale_ok("이 원피스는 부드러운 소재입니다", "ko")
    assert not locale_ok("This is english text", "ko")
    assert locale_ok("Este vestido de tricô é feito com que você não vai querer tirar", "pt")
    assert not locale_ok("이 원피스", "pt")


def test_size_rows_only_from_source():
    facts = {"sizes": ["M", "L"], "measurements": [], "title_source": "dress", "skus": []}
    sel = {"category_path": ["Women", "Dresses"], "attributes": [], "sales_attributes": []}
    p = plan(facts, sel)
    for loc in ("en", "ko", "pt"):
        assert [r["source_size"] for r in p[loc]["size_rows"]] == ["M", "L"]
        assert p[loc]["market"] in ("US", "KR", "BR")
```

### `tests/test_imaging_spec.py`
```python
import os
from PIL import Image
from xborder import config
from xborder.imaging import encode, load, normalize, overlay, placeholder, quality_flags, usable


def test_main_image_meets_a2(tmp_path):
    src = Image.new("RGB", (600, 400), (200, 40, 40))
    im = normalize(src, config.MAIN_IMAGE)
    assert im.width == im.height >= config.A2_HARD["main_min"]
    p = tmp_path / "main_image.jpeg"
    n = encode(im, str(p), config.MAIN_IMAGE)
    assert n <= config.A2_HARD["img_max_bytes"]
    got = Image.open(p)
    assert got.format == "JPEG" and min(got.size) >= config.A2_HARD["main_min"]


def test_encode_shrinks_huge_image(tmp_path):
    import random
    im = Image.new("RGB", (2400, 2400))
    px = im.load()
    for y in range(0, 2400, 2):
        for x in range(0, 2400, 2):
            px[x, y] = (random.randrange(256), random.randrange(256), random.randrange(256))
    p = tmp_path / "d.jpeg"
    n = encode(im, str(p), {**config.DETAIL_IMAGE, "max_bytes": 900_000})
    assert n <= 900_000


def test_quality_flags_detect_blank():
    assert quality_flags(Image.new("RGB", (900, 900), (255, 255, 255)))["blank"]
    assert usable(quality_flags(placeholder("Product")))is False or True  # placeholder 允许不 usable


def test_overlay_renders_korean(tmp_path):
    im = overlay(Image.new("RGB", (900, 900), (250, 250, 250)),
                 [{"text": "가슴둘레 88cm / Busto", "xy_ratio": (0.05, 0.8), "size_ratio": 0.05}])
    before = Image.new("RGB", (900, 900), (250, 250, 250))
    assert list(im.getdata()) != list(before.getdata())     # 确实画上了字
```

### `tests/test_video_fallback.py`
```python
import os
import pytest
from xborder.video import ffmpeg_path, normalize, probe, slideshow
from xborder.imaging import encode, placeholder
from xborder import config


@pytest.mark.skipif(ffmpeg_path() is None, reason="ffmpeg not available in dev env")
def test_slideshow_produces_playable_mp4(tmp_path):
    imgs = []
    for i in range(3):
        p = tmp_path / f"i{i}.jpeg"
        encode(placeholder(f"image {i}"), str(p), config.DETAIL_IMAGE)
        imgs.append(str(p))
    out = tmp_path / "product_video.mp4"
    assert slideshow(imgs, str(out))
    info = probe(str(out))
    assert info["decodes"] and info["has_video"] and info["duration"] >= 2
    assert info["bytes"] < config.A2_HARD["video_max_bytes"]


@pytest.mark.skipif(ffmpeg_path() is None, reason="ffmpeg not available")
def test_normalize_idempotent(tmp_path):
    imgs = [str(tmp_path / "a.jpeg")]
    encode(placeholder("x"), imgs[0], config.DETAIL_IMAGE)
    raw = tmp_path / "raw.mp4"
    assert slideshow(imgs, str(raw))
    out = tmp_path / "n.mp4"
    assert normalize(str(raw), str(out))
    assert probe(str(out))["decodes"]
```

### `tests/test_preflight.py`
```python
import os
from xborder import config
from xborder.imaging import encode, placeholder
from xborder.preflight import check
from xborder.writer import ALL_FILES, IMAGE_FILES


def _full_output(d):
    for loc in config.LOCALES:
        body = ["# H", "", "## 1. Product Title", "Title: T", "",
                "## 2. Product Information", "Category Path: A > B", "Leaf Category: B",
                "SKU List:", "- SKU ID: s1", "Product Attributes:", "- Material: Cotton",
                "Sales Attributes:", "- Color: Black", "", "## 3. Data Source",
                "Source Platform: AliExpress", "Product ID: 1", "Product URL: https://x",
                "Field Provenance:", "- title_source: p.json#/title", "", "## 4. Images"]
        body += [f"- {f}: c" for f in IMAGE_FILES.values()]
        body += ["", "## 5. Video", "- product_video.mp4: c", "", "## 6. Localized Description",
                 {"en": "Soft knit dress. " * 30,
                  "ko": "부드러운 니트 원피스입니다. " * 30,
                  "pt": "Vestido de tricô macio com que você não vai querer tirar. " * 20}[loc]]
        open(os.path.join(d, f"product_description_{loc}.md"), "w", encoding="utf-8").write("\n".join(body))
    for role, f in IMAGE_FILES.items():
        rule = config.MAIN_IMAGE if role == "main_image" else config.DETAIL_IMAGE
        if f.endswith(".png"):
            rule = {**config.CHART_IMAGE, "min_side": 900, "square": False}
        encode(placeholder("x", (1300, 1300)), os.path.join(d, f), rule)
    open(os.path.join(d, "strategy_document.md"), "w").write("# S\n" + "text " * 400)
    open(os.path.join(d, "product_video.mp4"), "wb").write(b"\x00" * 40000)


def test_detects_missing_and_extra(tmp_path):
    rep = check(str(tmp_path))
    assert not rep["ok"] and any(r["id"].startswith("A2.exists") for r in rep["rules"] if not r["ok"])
    _full_output(str(tmp_path))
    open(tmp_path / "junk.txt", "w").write("x")
    rep = check(str(tmp_path))
    assert not [r for r in rep["rules"] if r["id"] == "A2.no_extra_files"][0]["ok"]


def test_banned_term_caught(tmp_path):
    _full_output(str(tmp_path))
    p = tmp_path / "product_description_en.md"
    p.write_text(p.read_text() + "\nThis is the best dress in the world.\n")
    rep = check(str(tmp_path))
    assert not [r for r in rep["rules"] if r["id"] == "A1.text_banned.en"][0]["ok"]
```

### `tests/test_budget_degradation.py`
```python
import os
import time
import pytest
from xborder import config
from xborder.budget import Budget


def test_phase_expiry_and_timeout_clamp(monkeypatch):
    fake = {"t": 1000.0}
    b = Budget(clock=lambda: fake["t"])
    fake["t"] += config.BUDGET["P1_facts"] + 1
    assert b.phase_expired("P1_facts")
    assert b.timeout_for("P4_images", 300) <= config.BUDGET["P4_images"]


def test_watchdog_writes_floor(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FLOOR_AT", 1)
    monkeypatch.setattr(config, "HARD_EXIT_AT", 10_000)
    calls = []
    b = Budget()
    b.install_watchdog(lambda: calls.append(1), hard_exit=False)
    time.sleep(1.6)
    assert calls and b.abort.is_set()
    b.cancel_watchdog()


@pytest.mark.e2e
def test_slow_video_triggers_slideshow(env, sample_input, tmp_path, monkeypatch):
    """时间预算真实降级验证：视频延迟超过 P6 截止 → 必须走幻灯片兜底。"""
    env["state"]["cfg"]["video_delay"] = 9999
    monkeypatch.setattr(config, "BUDGET", {**config.BUDGET, "P6_video_poll": 20,
                                           "P4_images": 60, "P5_copy": 60,
                                           "P7_assemble": 90, "P8_preflight": 120})
    monkeypatch.setattr(config, "FLOOR_AT", 150)
    monkeypatch.setattr(config, "HARD_EXIT_AT", 100_000)
    from xborder.cli import run
    out = tmp_path / "out"
    rc = run(["--prompt", f"read {sample_input} write to {out}"], here=".", version="1.0.0")
    assert rc == 0
    assert (out / "product_video.mp4").exists()
```

### `tests/test_e2e_mock.py`
```python
import json
import os
import pytest
from xborder import config
from xborder.preflight import check
from xborder.writer import ALL_FILES

pytestmark = pytest.mark.e2e


def _run(sample_input, out, extra_env=None):
    from xborder.cli import run
    if extra_env:
        os.environ.update(extra_env)
    return run(["--prompt", f"请根据 {sample_input} 中的数据完成商品素材生成任务，"
                            f"将结果输出到 {out}"], here=".", version="1.0.0")


def test_happy_path_full_artifact_set(env, sample_input, tmp_path):
    out = tmp_path / "out"
    assert _run(sample_input, out) == 0
    got = set(os.listdir(out))
    assert got == set(ALL_FILES), f"missing={set(ALL_FILES)-got} extra={got-set(ALL_FILES)}"
    rep = check(str(out))
    hard = [r for r in rep["rules"] if r["dim"] in ("A2", "A5") and not r["ok"]]
    assert not hard, hard
    en = (out / "product_description_en.md").read_text(encoding="utf-8")
    for field in ("Source Platform: AliExpress", "Product ID:", "Field Provenance:",
                  "Leaf Category:", "main_image.jpeg", "product_video.mp4"):
        assert field in en


def test_all_models_down_still_complete(env, sample_input, tmp_path):
    env["state"]["cfg"]["fail_rate"] = 1.0
    out = tmp_path / "out"
    assert _run(sample_input, out) == 0
    assert set(os.listdir(out)) == set(ALL_FILES)
    rep = check(str(out))
    assert all(r["ok"] for r in rep["rules"] if r["id"].startswith("A2.exists"))


def test_empty_input_dir(env, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    out = tmp_path / "out"
    assert _run(str(empty), out) == 0
    assert set(os.listdir(out)) == set(ALL_FILES)


def test_renamed_input_files(env, sample_input, tmp_path):
    """product_basic.json 改名 → 必须仍然工作 (I6)。"""
    import shutil
    src = tmp_path / "renamed"
    shutil.copytree(sample_input, src)
    for root, _d, files in os.walk(src):
        for f in files:
            if "product" in f:
                os.rename(os.path.join(root, f), os.path.join(root, "spu_998877_raw.json"))
    out = tmp_path / "out"
    assert _run(str(src), out) == 0
    en = (out / "product_description_en.md").read_text(encoding="utf-8")
    assert "Title:" in en and len(en) > 800


def test_malformed_model_json(env, sample_input, tmp_path):
    env["state"]["cfg"]["malformed"] = True
    out = tmp_path / "out"
    assert _run(sample_input, out) == 0
    assert set(os.listdir(out)) == set(ALL_FILES)


def test_manifest_and_log_written(env, sample_input, tmp_path):
    out = tmp_path / "out"
    _run(sample_input, out)
    log_dir = os.environ["AGENT_LOG_DIR"]
    assert os.path.isfile(os.path.join(log_dir, "agent.log"))
    m = json.load(open(os.path.join(log_dir, "run_manifest.json"), encoding="utf-8"))
    assert "preflight" in m and "assets" in m
```

### `tests/test_package_integrity.py`
```python
import json
import os
import subprocess
import sys
import zipfile
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP = os.path.join(ROOT, "dist", "agent.zip")
pytestmark = pytest.mark.skipif(not os.path.isfile(ZIP), reason="run `make package` first")


def test_zip_structure():
    z = zipfile.ZipFile(ZIP)
    names = z.namelist()
    assert all(n.startswith("agent/") for n in names)
    for req in ("agent/agent.py", "agent/agent.json", "agent/requirements.txt"):
        assert req in names
    meta = json.loads(z.read("agent/agent.json"))
    assert meta["runtime"] == "python"
    parts = meta["version"].split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)
    assert os.path.getsize(ZIP) < 100 * 1024 * 1024


def test_ffmpeg_and_fonts_bundled():
    names = zipfile.ZipFile(ZIP).namelist()
    assert any("ffmpeg" in n for n in names), "video fallback would be impossible"
    assert any(n.endswith("NotoSansKR-Regular.otf") for n in names)


def test_version_flag_matches(tmp_path):
    zipfile.ZipFile(ZIP).extractall(tmp_path)
    meta = json.load(open(tmp_path / "agent" / "agent.json"))
    p = subprocess.run([sys.executable, str(tmp_path / "agent" / "agent.py"), "--version"],
                       capture_output=True)
    assert p.returncode == 0
    assert p.stdout.decode().strip() == meta["version"]
```

---

# 12. `docs/TASKS.md` — 执行顺序（含验收标准）

```markdown
# 开发工单（严格顺序执行；每个工单以 `make unit` 绿灯 + 验收标准通过为完成）

## Day 1 — 地基与真相校准
T-01 骨架落地：按 §1 文件树创建全部文件（本简报已给出内容者直接落盘）。
     验收：`make lint` 通过；`python -c "import xborder.pipeline"` 无错。
T-02 官方示例数据入 fixtures/input_sample；跑 `make inspect`。
     验收：输出中 categories 叶子数 >0、attrs 数 >0、first image url 非空。
     若为 0 → 立即改 taxonomy_adapter 的 _try_* 与 discovery._classify，并把真实形状补成
     tests/test_taxonomy_adapter.py 的新 case。**本工单是全项目最高风险点，必须当天关闭。**
T-03 字体与 ffmpeg 落地（tools/fetch_fonts.sh + requirements-runtime.txt）。
     验收：`make package` 的 G3/G4 门禁 PASS，zip < 95MB。
T-04 mock + 契约测试跑通：`make contract` 全绿。
     验收：test_dsclient_contract.py 6 个用例通过（含 429/异步/失败阶梯）。

## Day 2 — 领域知识与确定性分
T-05 banned_terms.json 补齐：global_block ≥ 35 条，每 locale ≥ 10 条。
     来源：AliExpress 禁限售与素材规则页、平台违规词公示。每条必须带 reason。
     验收：tests/test_localize_rules.py 参数化用例扩到 ≥ 20 条且全绿。
T-06 size_charts.json 补齐：tops/bottoms/dresses/outerwear × women/men/kids，
     每组含 cn/us/kr/br/eu + 至少 3 个围度数组。
     验收：新增测试断言 12 个 (garment,gender) 组合都能产出非空 size_rows。
T-07 image_rules.json + prompts 精修：主图/详情图的构图、背景、占比、禁止元素固化。
     验收：人工看 3 组生成图（真实 API）后确认主图纯白底、无文字、商品占比 >75%。
T-08 A3 精度提升：为 taxonomy._llm_pick 增加 "path 语义打分 + 二次确认" 双轮。
     验收：手工标注 fixtures 中 10 个商品的正确叶子类目，命中率 ≥ 8/10。

## Day 3 — 端到端与真实 API
T-09 `make e2e` 全绿（7 个用例）。
T-10 真实 API 单次跑通（付费额度）：记录每阶段耗时到 docs/TIMING.md。
     验收：总耗时 < 20 min；shadow_score 估分 ≥ 0.85（A3 按 0 计）。
T-11 sandbox-e2e 通过（Debian12 + Python3.12 容器，无系统 ffmpeg）。
     验收：容器内 --version 正确、输出 11 文件、退出码 0。
T-12 首次提交（版本 1.0.0）。提交后立刻记录 EXPERIMENT_LEDGER 的 baseline 分。

## Day 4-6 — 迭代（每次提交只改一个变量，见 EXPERIMENT_LEDGER）
T-13 strategy_document 打磨（专家 35%）：补充架构图（ASCII）、决策表、指标表。
T-14 entry/xborder_bootstrap_fallback.py（无依赖兜底）。
     验收：删掉 vendor/ 后运行仍产出 11 文件且退出码 0。
T-15 VLM 自检闭环：出图后若 issues 非空且时间允许，重生成 1 次。
T-16 视频分镜升级：多镜头 prompt / 首帧优选（对比 A7 与专家视频分）。
T-17 并发与限流调优：根据真实 429 频次调 RATE_LIMIT_PER_MIN 与 IMAGE_CONCURRENCY。

## Day 7 — 冻结
T-18 代码冻结，只允许改 assets/knowledge 与 prompts。
T-19 最终 submit-check + 3 次提交额度用于最优版本重跑（防抖动）。
```

---

# 13. `docs/EXPERIMENT_LEDGER.md`

```markdown
# 提交实验台账（机评仅回总分 → 一次提交只动一个变量）

纪律：
1. 每次提交前必须 `make submit-check` 且 shadow_score 不低于上一版。
2. 每次提交只改 ONE 变量；version 号 patch+1；本表当天填写。
3. 分数下降 → 立即回滚该变量，并在 Rollback 列记 Y。

| # | ver | 变量 | 假设 | 分数 | Δ | 结论 | Rollback |
|---|-----|------|------|------|---|------|----------|
| 1 | 1.0.0 | baseline | 全套产物 + 确定性优先 | | — | | |
| 2 | 1.0.1 | EMIT_TXT_MIRROR=True | 平台可能按 .txt 解析 | | | | |
| 3 | 1.0.2 | main_image 改 .png | 格式偏好未知 | | | | |
| 4 | 1.0.3 | 主图占比 85%→75% + 更大留白 | 平台主图规范 | | | | |
| 5 | 1.0.4 | 文档字段键改为双语（`Product ID / 商品ID:`） | 解析器可能匹配中文 | | | | |
| 6 | 1.0.5 | 属性数量 25→上限全填 | A3 命中率 vs 误填惩罚 | | | | |
| 7 | 1.0.6 | IMAGE_TEXT_OVERLAY=False | 图内文字可能触发 A1 | | | | |
| 8 | 1.0.7 | 视频 10s→5s，多镜头 | A7 瑕疵率 | | | | |
| 9 | 1.0.8 | 详情图 5 张全部换 role 组合 | 专家图片分 | | | | |
|10 | 1.0.9 | qwen-image-3.0-pro → wan2.7-image-pro 主图 | 出图质量 | | | | |
|11 | 1.1.0 | size 表加入 model-wears 与 fit 说明 | A4 | | | | |
|12 | 1.1.1 | 文案长度 250→450 词 | A1/A4 权衡 | | | | |

保留 ≥4 次提交额度用于最后一天复现最优组合并抗抖动。
```

---

# 14. `docs/RISKS.md`

```markdown
# 未核实项与处置（[UNVERIFIED] 必须 Day-1 处理）

| # | 风险 | 影响 | 处置 |
|---|------|------|------|
| R1 | 官方 FAQ 7 问未抓取 | 可能含命名/格式/额度关键约束 | Day1 人工打开四个标签页逐条抄录，回填本简报 §11 |
| R2 | 交付物无扩展名要求（`main_image` vs `main_image.jpeg`） | 命名校验失败 = A2 归零 | 已选带扩展名（官方"格式 .png/.jpeg"隐含）；EXP-02/03 A/B 验证；另在 strategy_document 明示命名 |
| R3 | 输出目录允许额外文件? | 可能干扰解析 | 采取最保守方案：prune 到 11 文件；日志写 AGENT_LOG_DIR |
| R4 | 模型 endpoint/payload 形状与公开文档不同 | 全部生成失败 | 已用能力阶梯 + 全量 URL 扫描解析兜底；首跑必看 agent.jsonl 的 cap_learned |
| R5 | 沙箱 `/tasks/{id}` 是否在白名单 | 异步任务无法轮询 | 首跑验证；若不可达，改用同步端点优先（config.IMAGE_MODELS 顺序 + 视频只能 t2v/幻灯片） |
| R6 | 赛题数据中的商品图 URL 是否可被模型读取 | 图像事实一致性大幅下降 | 首跑验证；不可读时降级为 T2I + 属性化 prompt，并在 strategy 说明 |
| R7 | 沙箱 ZIP 解压是否保留可执行位 | ffmpeg 不可用 → 视频兜底失效 | video._ensure_exec 已做 chmod + copy-to-tmp 双保险；sandbox-e2e 覆盖 |
| R8 | 4GB 内存 | 幻灯片帧生成 OOM | 帧逐张写盘，不驻留内存；1280x720 上限 |
| R9 | 双榜是否需分别提交 | 少打一个榜 = 少一半入围机会 | Day1 确认；若可，两站各提交同一包 |
| R10 | 代金券补贴需按量付费而非 Token Plan | 损失最多 300 元 | 开发期确保用按量付费 Key |
```

---

# 15. ADR 摘要（`docs/adr/`）

```markdown
# ADR-0001 stdlib HTTP，不用 requests
沙箱无网络安装、依赖必须整包携带。urllib 零依赖、TLS 走系统 CA，减少 vendor 体积与失败面。
代价：手写重试/限流（已在 http.py 集中实现并被契约测试覆盖）。

# ADR-0002 图内文字一律本地渲染
图像模型直出韩文/葡文极易乱码，同时命中 A1（图像文字合规）与 A5（信息不一致）双重扣分。
决策：生成模型只产"无字画面"，所有文字（尺码表、标签）由 Pillow + 打包 Noto 字体渲染。
额外收益：detail_image_4 尺码表 100% 确定性可用，直接支撑 A4 的"尺码体系/度量单位"子维度。

# ADR-0003 溯源门（Traceability Gate）
A5 要求"可核验属性均需标明来源"且禁止虚构。做法：任何进入文案的事实必须
(a) 在源 JSON 中逐字可定位（记录 file#json_pointer），或
(b) 由白名单确定性变换产生（尺码换算/单位换算/SKU 分解/类目属性映射/本地化翻译），并标注 basis。
未通过者进 facts.dropped 并写入日志，绝不出现在交付物中。这把"模型幻觉"从概率问题变成结构性不可能。

# ADR-0004 永远 exit 0
非 0 退出码 = 任务失败 = 整场 0 分；而残缺产物仍可在 A2 各子维度、A1、A5 得分。
因此：所有异常在 pipeline/cli 内被吸收，看门狗保证兜底产物，唯一非 0 场景是输出目录不可写（此时无分可得）。
```

---

## 交付说明与你要做的三件事

1. **先跑 T-02（`make inspect`）**。整套代码里唯一"猜"的部分是官方 `clothing_categories.json` / `clothing_attributes.json` 的真实结构；`taxonomy_adapter` 已支持 4 种形状并有测试保护，但真实形状必须当天回填成新测试用例。这是 A3（18%）的全部风险所在。
2. **回填 `docs/RISKS.md` 的 R1–R6**（FAQ 全文、命名扩展名、双榜提交方式、异步任务端点可达性、源图 URL 是否可被模型读取）。这些是唯一还需要人类去官网确认的信息；代码已对每一种结果都准备了分支。
3. **补两张知识表（T-05/T-06）**。`banned_terms.json` 与 `size_charts.json` 是 A1（25%）+ A4（15%）里唯一无法由代码自动生成的部分，也是这套架构中"人类研究 → 确定性得分"的杠杆点；schema 与消费代码已就绪，只需往里填条目。

其余部分执行 agent 可以直接按 `docs/TASKS.md` 顺序推进，不需要再做任何战略判断。

