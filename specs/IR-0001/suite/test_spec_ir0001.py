#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IR-0001 套件——视觉质量优先 spec 的结构+语义锚断言（adversary 目标目录契约）。

被审"实现" = impl-dir 下的 spec.md（文档对形态：本 IR 的交付物首件是条款级
规格本身）。断言四层（对齐 specs/IR-0005 套件口径）：
  L1 结构：frontmatter 字段、AC-1..AC-9 完备、条款段齐备
  L2 语义锚：真实视觉质量管线才含的机制短语
  L3 负向锚：偷懒改写最易缺的深水位标志（具体数值/三语枚举/维度计数）
  L4 一致性：AC 数、版本号、卡绑定与 IR-0001 期望对齐；防模板句复用
防"最偷懒实现"（judge-deep）口径：同义模板句无法同时命中 30+ 异质锚。
"""
import os
import re
import sys
import unittest

_cwd = os.path.abspath(os.getcwd())
IMPL = None
if os.environ.get("IMPL_DIR"):
    IMPL = os.path.normpath(os.environ["IMPL_DIR"])
elif os.path.isfile(os.path.join(_cwd, "spec.md")):
    IMPL = _cwd
elif os.path.isfile(os.path.join(_cwd, "..", "spec.md")):
    IMPL = os.path.normpath(os.path.join(_cwd, ".."))
if IMPL is None:
    raise AssertionError("无法定位 impl 目录（IMPL_DIR 未设且 cwd 上下文无 spec.md）")
SPEC = os.path.join(IMPL, "spec.md")


def read(path):
    if not os.path.isfile(path):
        raise AssertionError(f"缺文件: {path}")
    with open(path, encoding="utf-8") as f:
        return f.read()


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise AssertionError("缺 frontmatter（--- 包裹的元数据块）")
    return m.group(1)


class L1Structure(unittest.TestCase):
    def test_frontmatter_keys(self):
        fm = frontmatter(read(SPEC))
        for k in ("taskId: IR-0001", "specVersion:", "irRef:", "card:"):
            self.assertIn(k, fm, f"frontmatter 缺 {k}")

    def test_ac_complete(self):
        s = read(SPEC)
        for i in range(1, 10):
            self.assertIn(f"- id: AC-{i}", s, f"缺 AC-{i}")
        self.assertEqual(len(re.findall(r"^\s*- id: AC-\d+", s, re.M)), 9,
                         "AC 总数应为 9（编号连续且无影子条款）")

    def test_ac_gwt(self):
        s = read(SPEC)
        for i in range(1, 10):
            m = re.search(rf"- id: AC-{i}\n\s+given: (.+)\n\s+when: (.+)\n\s+then: (.+)", s)
            self.assertIsNotNone(m, f"AC-{i} 缺 given/when/then 三段")
            g, w, t = (p.strip() for p in m.groups())
            # 深度下限（S1' 补强，IR-0004 rev5 口径）：防三段皆样板短句
            self.assertGreaterEqual(len(g), 12, f"AC-{i} given 过短（<12 字）")
            self.assertGreaterEqual(len(w), 8, f"AC-{i} when 过短（<8 字）")
            self.assertGreaterEqual(len(t), 16, f"AC-{i} then 过短（<16 字）")

    def test_clause_sections(self):
        s = read(SPEC)
        for sec in ("## INV 不变量", "## BEH 行为", "## IFACE 契约",
                    "## BUDGET 预算", "## DECISION 决策", "## ASSUMPTION 假设"):
            self.assertIn(sec, s, f"缺条款段 {sec}")
        for uid in ("INV-1", "INV-2", "INV-3", "INV-4", "BEH-1", "BEH-8",
                    "IFACE-1", "IFACE-2", "BUDGET-1", "BUDGET-2",
                    "DECISION-1", "DECISION-2", "ASSUMPTION-1"):
            self.assertIn(uid, s, f"缺条款 {uid}")


class L2SemanticAnchors(unittest.TestCase):
    """真实视觉质量管线的机制短语——偷懒改写很难全部保留且位置正确。"""

    ANCHORS = [
        "品类", "构图", "主图", "详情图",
        "市场", "词典", "光照", "色调",
        "VLM", "质检", "评审", "重生成", "反馈",
        "种子", "负面提示词",
        "尺码表", "本地渲染", "字体",
        "兜底", "源图", "裁剪", "轮播",
        "白底", "方图",
        "成本估算", "效率对比", "适配成本",
        "参考图", "事实一致", "溯源门",
    ]

    def test_anchor_coverage(self):
        s = read(SPEC)
        missing = [a for a in self.ANCHORS if a not in s]
        self.assertEqual(missing, [], f"语义锚缺失: {missing}")
        # 锚密度：正文（去 frontmatter）需有一定体量，防"关键词堆砌+空壳条款"
        body = s.split("---", 2)[-1]
        self.assertGreaterEqual(len(body), 1500, "正文过薄——疑似空壳 spec")

    # ---- S1'（摆拍式 AC）补强：语义锚绑定到条款位置——关键词搬到位≠语义保留 ----
    CLAUSE_ANCHORS = [
        ("INV-1", ["三核心件", "不得被降级路径替换或绕过"]),
        ("INV-2", ["参考锚定", "场景类详情图允许纯文生图", "品类构图与市场词典"]),
        ("INV-3", ["可枚举的配置资产或代码规则", "禁止散落"]),
        ("INV-4", ["不得突破", "模型到 URL 再到模型", "环境变量读取", "严格校验"]),
        ("BEH-1", ["每个图像角色", "构图模板"]),
        ("BEH-2", ["光照、色调与风格词典条目"]),
        ("BEH-3", ["携带评审反馈", "BUDGET-2"]),
        ("BEH-4", ["固定种子", "四类失败模式"]),
        ("BEH-5", ["本地渲染", "不发起任何模型调用"]),
        ("BEH-6", ["源图裁剪", "图片轮播", "不得尝试多级模型轮换"]),
        ("BEH-7", ["白底方图", "1200", "900", "4.5"]),
        ("BEH-8", ["成本估算", "效率对比", "适配成本声明"]),
        ("IFACE-1", ["独立配置资产", "可枚举审查"]),
        ("IFACE-2", ["机器可解析", "四维判定加问题清单"]),
        ("BUDGET-2", ["上限为 2 次", "走兜底路径"]),
    ]

    def test_clause_anchor_binding(self):
        s = read(SPEC)
        clauses = dict(re.findall(r"^- ((?:INV|BEH|IFACE|BUDGET)-\d+): (.+)$", s, re.M))
        for uid, anchors in self.CLAUSE_ANCHORS:
            self.assertIn(uid, clauses, f"缺条款 {uid}")
            missing = [a for a in anchors if a not in clauses[uid]]
            self.assertEqual(missing, [], f"{uid} 条款语义锚缺失 {missing}——摆拍式改写嫌疑")

    def test_clause_normative_depth(self):
        """每条 INV/BEH/IFACE 条款须含规范性动词且 ≥20 字——空壳条款直接红。"""
        s = read(SPEC)
        clauses = re.findall(r"^- ((?:INV|BEH|IFACE|BUDGET|DECISION|ASSUMPTION)-\d+): (.+)$", s, re.M)
        self.assertGreaterEqual(len(clauses), 17, "条款总数少于 17")
        normative = ("必须", "不得", "禁止", "须", "应")
        for uid, text in clauses:
            self.assertGreaterEqual(len(text), 20, f"{uid} 条款正文短于 20 字——空壳条款")
            if uid.startswith(("INV", "BEH", "IFACE")):
                self.assertTrue(any(w in text for w in normative),
                                f"{uid} 缺规范性动词（必须/不得/禁止/须/应）——摆拍式条款")

    # ---- S2（义务降级）补强：红队第二轮攻击得手后的套件 v3 ----
    # 攻击样本：把"必须"弱化为"应/原则上须/推荐"，把硬阈值降为"参考基线"，
    # 把执行义务改为"文档声称/以记载为准"——全部锚点原样保留却背叛意图。
    STRONG_MODALITY = ("必须", "不得", "禁止")
    WEAKENING_PHRASES = [
        "原则上", "建议", "推荐", "努力", "默认", "声称", "宣称", "据称",
        "记载", "为目标", "设计目标", "参考基线", "参考值", "建议值",
        "可跳过", "可上调", "可省略", "不阻断", "深度不限", "裁量",
        "视效果", "时间紧张", "高峰期", "文档口径", "意向约束", "意向声明",
        "不视为违规", "允许偏离", "异常时回退", "受阻时", "视运行情况",
    ]

    def test_strong_modality(self):
        """INV/BEH/IFACE 义务动词必须是强规范动词（必须/不得/禁止）——"应/须"可被原则上/建议稀释。"""
        s = read(SPEC)
        clauses = re.findall(r"^- ((?:INV|BEH|IFACE)-\d+): (.+)$", s, re.M)
        self.assertGreaterEqual(len(clauses), 14, "INV/BEH/IFACE 条款不足 14 条")
        for uid, text in clauses:
            self.assertTrue(any(w in text for w in self.STRONG_MODALITY),
                            f"{uid} 缺强规范动词（必须/不得/禁止）——义务降级改写嫌疑")

    def test_no_weakening_phrases(self):
        """条款行与 AC 段禁弱化逃逸短语——把强制条款掏空为意向声明的直接红旗。"""
        s = read(SPEC)
        lines = [l for l in s.splitlines()
                 if re.match(r"^\s*(- )?(id: AC-|given:|when:|then:|(?:INV|BEH|IFACE|BUDGET)-\d+:)", l.strip())]
        for l in lines:
            hit = [w for w in self.WEAKENING_PHRASES if w in l]
            self.assertEqual(hit, [], f"弱化逃逸短语 {hit}: {l[:60]}——义务降级改写")

    # ---- S3（义务转嫁）补强：红队第三轮攻击得手后的套件 v4 ----
    # 攻击样本：强动词与锚点全部保留，但义务受托对象被换成"模板/占位符/
    # 检查单/操作手册/人工填写"——系统只需产出文档表格而不执行视觉质量管线。
    # 治理意图：BEH/IFACE 的义务主体是系统运行时行为，AC 验收的是产物与
    # 运行时效果，不是关于它们的文书。
    TRANSFER_PHRASES = [
        "操作员", "手动", "供人工", "人工填写", "人工复核", "人工挑选",
        "人工逐项", "人工携带", "手工计数", "选用表", "检查单", "检查清单",
        "工艺单", "操作手册", "台账", "占位", "字段名", "打勾", "打分栏",
        "提示词模板", "参数表", "对照表", "目录含", "标注", "写明", "载明",
        "逐项", "仅对样例", "演示场景", "首件商品", "抽样", "仅标记", "被标记",
        "等效替换", "等效改写", "视同",
    ]

    def test_no_obligation_transfer(self):
        """BEH/IFACE/INV 条款与 AC then 禁义务转嫁标记——系统义务不得转嫁给文书或人工。"""
        s = read(SPEC)
        lines = [l for l in s.splitlines()
                 if re.match(r"^\s*(- )?(id: AC-|then:|(?:INV|BEH|IFACE)-\d+:)", l.strip())]
        for l in lines:
            hit = [w for w in self.TRANSFER_PHRASES if w in l]
            self.assertEqual(hit, [], f"义务转嫁标记 {hit}: {l[:60]}——执行义务被转嫁给文书/人工")

    # ---- S4（义务时态后移）补强：红队第四轮攻击得手后的套件 v5 ----
    # 攻击样本：义务动词换成"确认/核验已发生"——系统从执行者降级为事后
    # 裁定者，锚点与强动词全部原样保留。BEH 的"校验"是执行规格校验并
    # 强制处置（原 BEH-7），"确认/核验已发生"是转述他人行为。
    TENSE_ESCAPE_AC = [
        "历史记录", "回放", "事后", "溯源核验", "审计显示", "报告确认",
        "抽验", "归档", "已携带", "已注入", "已覆盖", "已获得",
    ]
    TENSE_ESCAPE_BEH = ["确认", "核验为", "核验该"]

    def test_no_tense_escape(self):
        """AC then 禁事后证据词、BEH 条款禁"确认/核验已发生"——验收的是产物与运行时效果，不是转述。"""
        s = read(SPEC)
        thens = re.findall(r"then: (.+)", s)
        for t in thens:
            hit = [w for w in self.TENSE_ESCAPE_AC if w in t]
            self.assertEqual(hit, [], f"AC then 事后转述词 {hit}: {t[:50]}——验收时态后移")
        for l in s.splitlines():
            if re.match(r"^- BEH-\d+:", l.strip()):
                hit = [w for w in self.TENSE_ESCAPE_BEH if w in l]
                self.assertEqual(hit, [], f"BEH 时态后移词 {hit}: {l[:60]}——执行义务被改为事后核验")

    # ---- S5（逃生舱条款）补强：红队第五轮攻击得手后的套件 v6 ----
    # 攻击样本：锚点、动词、句型全部原样，仅在条款/then 句尾追加
    # "时间预算受压时按剩余额度折算执行"式逃生从句——义务变成尽力而为。
    ESCAPE_HATCH = [
        "受压时", "额度折算", "折算执行", "深度为限", "预算允许", "按剩余",
        "资源受限", "资源允许", "周期允许", "条件允许", "能力允许", "余量",
        "最低限度", "尽力完成", "或以", "或按", "或在", "或由", "或改用", "或改为",
    ]

    def test_no_escape_hatch(self):
        """BEH/INV/IFACE 条款与 AC then 禁逃生从句——强义务不得被句尾从句掏空为尽力而为。"""
        s = read(SPEC)
        lines = [l for l in s.splitlines()
                 if re.match(r"^\s*(- )?(id: AC-|then:|(?:INV|BEH|IFACE|BUDGET)-\d+:)", l.strip())]
        for l in lines:
            hit = [w for w in self.ESCAPE_HATCH if w in l]
            self.assertEqual(hit, [], f"逃生舱从句 {hit}: {l[:60]}——强义务被掏空")

    # ---- S6（前置条件堆叠）补强：红队第六轮攻击得手后的套件 v7 ----
    # 攻击样本：锚点、动词、then 全部原样，仅在 BEH 触发条件与 given/when
    # 追加"且配套资产预检通过/仅在抽选代表样本上"——义务触发面被收窄到
    # 近乎不可达，条款字面上完好无损。
    BEH_COND_STACK = ["且", "预检", "就绪", "齐备", "配额"]
    GWT_NARROW = ["，且", "预检", "抽选", "代表样本"]

    def test_no_precondition_stacking(self):
        """BEH"当…时"从句禁堆叠前置、given/when 禁收窄从句——触发条件层不得偷改验收范围。"""
        s = read(SPEC)
        for l in s.splitlines():
            st = l.strip()
            m = re.match(r"^- (BEH-\d+): 当(.+?)时[，,]", st)
            if m:
                hit = [w for w in self.BEH_COND_STACK if w in m.group(1)]
                self.assertEqual(hit, [], f"BEH 触发条件堆叠 {hit}: {l[:60]}——义务触发面被收窄")
            if re.match(r"^(- )?(given|when):", st):
                hit = [w for w in self.GWT_NARROW if w in l]
                self.assertEqual(hit, [], f"given/when 收窄从句 {hit}: {l[:60]}——验收范围被偷改")


class L3NegativeAnchors(unittest.TestCase):
    """深水位标志：具体数值、三语枚举、维度计数——偷懒改写最先丢的东西。"""

    NUMBERS = ["1200", "900", "4.5", "30 分钟", "4GB", "100MB", "36"]
    LOCALES = ["EN", "KO", "PT"]
    COUNTS = ["四维", "四类", "三节", "三市场", "三核心件", "2 次"]

    def test_numbers(self):
        s = read(SPEC)
        missing = [n for n in self.NUMBERS if n not in s]
        self.assertEqual(missing, [], f"数值锚缺失: {missing}")

    def test_locales(self):
        s = read(SPEC)
        for loc in self.LOCALES:
            self.assertIn(loc, s, f"缺目标市场枚举 {loc}")
        self.assertIn("三语", s, "缺三语字体表述")

    def test_counts(self):
        s = read(SPEC)
        missing = [c for c in self.COUNTS if c not in s]
        self.assertEqual(missing, [], f"计数锚缺失: {missing}")

    def test_no_vague_terms_in_clauses(self):
        """模糊禁词镜像（g010 口径）：AC/BEH 条款禁模糊词。"""
        s = read(SPEC)
        lines = [l for l in s.splitlines()
                 if re.match(r"^\s*(- )?(id: AC-|given:|when:|then:|BEH-\d+:)", l.strip())]
        vague = ["合理", "适当", "尽可能", "尽量", "必要时", "酌情", "大概", "等等"]
        for l in lines:
            hit = [w for w in vague if w in l]
            self.assertEqual(hit, [], f"条款含模糊词 {hit}: {l[:60]}")

    def test_no_implementation_detail(self):
        """spec 禁实现细节（spec-author 硬约束镜像）：无代码块/函数名/安装命令。"""
        s = read(SPEC)
        for bad in ("```", "def ", "class ", "import ", "npm install", "pip install"):
            self.assertNotIn(bad, s, f"spec 出现实现细节标记: {bad}")


class L4Consistency(unittest.TestCase):
    # S1' 补强：每条 AC 的 then 须含专属规范锚——摆拍式 then（"符合要求/正常输出"）直接红
    AC_THEN_ANCHORS = {
        1: ["品类专属构图指令", "构图指令不同"],
        2: ["光照、色调", "两两互异"],
        3: ["四维", "BUDGET-2", "评审反馈"],
        4: ["固定种子", "四类失败模式"],
        5: ["本地渲染", "零模型调用"],
        6: ["源图裁剪", "图片轮播", "不存在多级模型轮换"],
        7: ["白底方图", "1200", "900", "4.5"],
        8: ["成本估算", "效率对比", "适配成本声明"],
        9: ["survived", "AC-1 至 AC-8"],
    }

    def test_ac_then_anchor_binding(self):
        s = read(SPEC)
        for i, anchors in self.AC_THEN_ANCHORS.items():
            m = re.search(rf"- id: AC-{i}\n\s+given: .+\n\s+when: .+\n\s+then: (.+)", s)
            self.assertIsNotNone(m, f"AC-{i} then 段缺失")
            missing = [a for a in anchors if a not in m.group(1)]
            self.assertEqual(missing, [], f"AC-{i} then 缺专属规范锚 {missing}——摆拍式 AC")

    def test_ac_then_no_vacuous(self):
        """then 段禁空洞收尾短语（S1' 负控制）。"""
        s = read(SPEC)
        vacuous = ("符合要求", "正常输出", "满足需求", "达到预期", "完成生成", "即可", "等要求")
        thens = re.findall(r"then: (.+)", s)
        self.assertEqual(len(thens), 9)
        for t in thens:
            hit = [w for w in vacuous if w in t]
            self.assertEqual(hit, [], f"then 含空洞短语 {hit}: {t[:50]}")

    def test_identity(self):
        fm = frontmatter(read(SPEC))
        self.assertIn("irRef: IR-0001", fm, "irRef 必须是 IR-0001")
        self.assertRegex(fm, r"specVersion:\s*1\b", "specVersion 必须为 1")
        # 卡绑定与 GATE_CARD 对齐（v8 收口，2026-08-31）：本 spec 归属卡 #27
        # （W10 图片链路，PR #35 按 g010 trace-card-conflict 规则对齐——
        # 原 #2 绑定随实现卡落地退役；g010 断言 spec card == PR 卡上下文）。
        self.assertIn('card: "27"', fm, "卡绑定必须对齐当前实现卡 #27（g010 GATE_CARD 对齐）")

    def test_beh_ears(self):
        s = read(SPEC)
        behs = re.findall(r"^- (BEH-\d+): (.+)$", s, re.M)
        self.assertGreaterEqual(len(behs), 8, "BEH 条款少于 8 条")
        for uid, txt in behs:
            self.assertRegex(txt, r"^当.+时[，,]", f"{uid} 不匹配 EARS 当…时句型")

    def test_ac_then_not_boilerplate(self):
        """防模板句复用（IR-0004 rev5 J1 教训）：9 条 then 不得同句样板。"""
        s = read(SPEC)
        thens = re.findall(r"then: (.+)", s)
        self.assertEqual(len(thens), 9, "then 行数应为 9")
        prefixes = [t.strip()[:12] for t in thens]
        self.assertGreaterEqual(len(set(prefixes)), 7,
                                f"then 前缀去重仅 {len(set(prefixes))}/9——疑似模板句复用")

    # ---- S1' 第二轮（R2）补强：套件 v8，2026-08-31 ----
    # 红队攻击样本（adversary run 33396361978，verdict=insufficient）：摆拍式
    # spec 逐条命中 v7 全部锚点/强动词/结构检查（24/24 绿），实质为"空洞的
    # 视觉质量声明，无任何可执行管线定义或资产映射"——v7 锚点密度（每
    # AC/条款 2-3 锚）不足以拦住高保真摆拍。文档形态 IR 的被审物即 spec
    # 文本本身，v8 按 IR-0004 rev5 同口径升级：AC then 与全部规范性条款
    # 的**完整语义跨度**逐条钉死（正则容忍空白差异）——摆拍改写须逐字
    # 复刻规范内容才能全绿，等价于不再是摆拍。
    CANONICAL_THEN_SPANS = {
        1: "提示词含该品类专属构图指令，任取两个不同品类得到的构图指令不同，"
           "且映射以产物包内可枚举资产存在",
        2: "三份提示词分别注入对应市场的光照、色调与风格条目，且三组条目两两互异",
        3: "产出覆盖事实一致性、构图、技术质量、合规四维的机器可解析评审记录，"
           "判定不合格时携带评审反馈重生成，单图重生成次数不超过 BUDGET-2",
        4: "调用携带固定种子与负面提示词，负面提示词覆盖图内文字、水印、拼图、"
           "边框四类失败模式",
        5: "该图由本地渲染生成且全程零模型调用",
        6: "图片兜底为源图裁剪加本地合成、视频兜底为图片轮播，"
           "且产物包内不存在多级模型轮换降级路径",
        7: "主图为白底方图且最短边不低于 1200 像素、详情图最短边不低于 900 像素、"
           "单张大小不超过 4.5MB",
        8: "文档含单商品成本估算、与人工流程的效率对比、"
           "换品类与换市场适配成本声明三节",
        9: "存在 verdict 为 survived 的审计记录，"
           "且后续工作卡的验收标准逐条派生自本 spec 的 AC-1 至 AC-8",
    }

    def test_ac_then_full_canonical_spans(self):
        """S1'-R2：每条 AC then 须含完整规范语义跨度（空白差异容忍）。"""
        s = re.sub(r"\s+", "", read(SPEC))
        for i, span in self.CANONICAL_THEN_SPANS.items():
            self.assertIn(re.sub(r"\s+", "", span), s,
                          f"AC-{i} then 缺完整规范语义跨度——摆拍式高保真改写嫌疑（v8）")

    CANONICAL_CLAUSE_SPANS = {
        "INV-1": "视觉质量三核心件——品类构图模板、三市场视觉词典、VLM 质检闭环——"
                 "不得被降级路径替换或绕过",
        "INV-2": "主图与展示商品本体的详情图必须以源商品图为参考锚定（参考图生成模式）；"
                 "场景类详情图允许纯文生图，但须同时绑定品类构图与市场词典",
        "INV-3": "全部视觉控制点（构图模板、市场词典、负面提示词、规格阈值、质检反馈）"
                 "必须以可枚举的配置资产或代码规则存在，禁止散落于不可追溯的自由文本",
        "INV-4": "比赛硬约束在任何视觉质量增强中不得突破——墙钟不超过 30 分钟、"
                 "内存不超过 4GB、提交包不超过 100MB、仅白名单内 36 个模型、"
                 "中间产物只走模型到 URL 再到模型的链路、密钥只从环境变量读取、"
                 "产物命名严格校验",
        "BEH-1": "当服装品类判定完成时，系统必须为每个图像角色选取该品类对应的构图模板"
                 "并注入提示词",
        "BEH-2": "当目标市场为 EN、KO、PT 之一时，系统必须将该市场的光照、色调与风格"
                 "词典条目注入图像提示词",
        "BEH-3": "当任一生成图被质检判定为不合格时，系统必须携带评审反馈重生成该图，"
                 "重生成次数不超过 BUDGET-2",
        "BEH-4": "当图像生成调用发起时，系统必须携带固定种子与覆盖图内文字、水印、拼图、"
                 "边框四类失败模式的负面提示词",
        "BEH-5": "当尺码表详情图产出时，系统必须完全以本地渲染生成该图且不发起任何模型调用",
        "BEH-6": "当图像或视频主路径失败时，系统必须退到单一兜底——图片为源图裁剪加本地合成，"
                 "视频为图片轮播，不得尝试多级模型轮换",
        "BEH-7": "当图片产物落盘时，系统必须校验主图白底方图最短边不低于 1200 像素、"
                 "详情图最短边不低于 900 像素、单张不超过 4.5MB，不满足者被强制规格化处理",
        "BEH-8": "当策略说明文档生成时，系统必须包含单商品成本估算、与人工流程的效率对比、"
                 "换品类与换市场适配成本声明三节",
        "IFACE-1": "品类到构图模板的映射与市场到视觉风格条目的词典必须是产物包内独立配置资产，"
                   "输入到输出的映射可枚举审查",
        "IFACE-2": "VLM 质检的评审结果必须是机器可解析的结构化记录——四维判定加问题清单——"
                   "并留痕于运行日志；评审输入引用模型返回的图片 URL，"
                   "符合模型到 URL 再到模型的链路约束",
        "BUDGET-2": "单张图质检不合格的重生成次数上限为 2 次，超限后走兜底路径",
    }

    def test_clause_full_canonical_spans(self):
        """S1'-R2：全部规范性条款须含完整语义跨度（空白差异容忍）——资产映射/管线定义不可掏空。"""
        s = re.sub(r"\s+", "", read(SPEC))
        for uid, span in self.CANONICAL_CLAUSE_SPANS.items():
            self.assertIn(re.sub(r"\s+", "", span), s,
                          f"{uid} 缺完整规范语义跨度——空洞化改写嫌疑（v8）")

    def test_asset_binding_density(self):
        """S1'-R2：产物包/资产绑定密度——"空洞视觉质量声明"（无资产映射）的直接红旗。"""
        s = read(SPEC)
        self.assertGreaterEqual(s.count("产物包"), 4,
                                "产物包绑定出现 <4 次——规范内容空洞化（可执行资产映射被掏空）")
        self.assertGreaterEqual(s.count("映射"), 4,
                                "映射语义出现 <4 次——资产映射管线被掏空")
        self.assertGreaterEqual(s.count("模型"), 10,
                                "模型链路语义出现 <10 次——管线定义被掏空")

    # ---- S1' 第三轮（R3）补强：套件 v9，2026-08-31 ----
    # 红队攻击样本（adversary run 33397745534，verdict=insufficient）：
    # **逐字复制原 spec 全部规范内容 + 文末追加免责/元声明**——v8 全跨度
    # 钉死反而把攻击逼成"复制+追加"形态：条款本体完好，追加段把全文规范
    # 力整体掏空（"仅为目标声明/不构成执行义务"式）。v9 三面封死该形态：
    # 1) 全文禁元声明/免责短语（全文扫描——追加段通常不在条款行上）；
    # 2) 章节集合精确钉死（不多不少——追加 ## 段直接红）；
    # 3) 文档尾钉死（正文必须以 ASSUMPTION-1 收束——任何文末附加内容红）。
    META_DISCLAIMER = [
        "免责", "不构成", "不具约束力", "无约束力", "非强制", "仅供参考",
        "声明性", "意向性", "目标声明", "视觉目标", "不保证", "不作保证",
        "不承诺", "并非义务", "不设定义务", "不产生义务", "整体声明",
        "本文档整体", "以上条款", "所有条款均", "全部条款均", " aspirational",
        "最佳努力", "尽力而为",
    ]

    def test_no_meta_disclaimer(self):
        """S1'-R3：全文禁免责/元声明短语——复制本体+追加掏空段的直接红旗。"""
        s = read(SPEC)
        for w in self.META_DISCLAIMER:
            self.assertNotIn(w, s, f"全文出现元声明/免责短语「{w}」——规范力被整体掏空（v9）")

    CANONICAL_SECTIONS = {
        "# IR-0001 视觉质量优先（视觉管线条款级规格）",
        "## INV 不变量", "## BEH 行为", "## IFACE 契约",
        "## BUDGET 预算", "## DECISION 决策", "## ASSUMPTION 假设",
    }

    def test_section_set_exact(self):
        """S1'-R3：章节集合精确钉死——追加新章节（免责/附则/补充声明）直接红。"""
        s = read(SPEC)
        heads = {l.strip() for l in s.splitlines() if re.match(r"^#{1,2} ", l)}
        extra = heads - self.CANONICAL_SECTIONS
        self.assertEqual(extra, set(),
                         f"出现规范外章节 {extra}——追加段掏空规范力（v9）")
        missing = self.CANONICAL_SECTIONS - heads
        self.assertEqual(missing, set(), f"缺章节 {missing}")

    CANONICAL_TAIL = ("图像生成模型与视觉评审模型在比赛窗口内持续可用"
                      "且支持以 URL 引用图片输入（均在官方白名单 36 模型内）。")

    def test_document_tail(self):
        """S1'-R3：正文必须以 ASSUMPTION-1 收束——文末任何附加内容直接红。"""
        s = read(SPEC).rstrip()
        tail = re.sub(r"\s+", "", s[-len(self.CANONICAL_TAIL) - 20:])
        self.assertIn(re.sub(r"\s+", "", self.CANONICAL_TAIL), tail,
                      "文档尾部非 ASSUMPTION-1 规范收束——文末被附加内容（v9）")

    def test_nongoals_bound(self):
        fm = frontmatter(read(SPEC))
        self.assertIn("不重写", fm, "nonGoals 须保留架构不重写边界")
        self.assertIn("治理脚手架", fm, "nonGoals 须保留治理脚手架不动边界")


if __name__ == "__main__":
    unittest.main(verbosity=2)
