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
        self.assertIn("QW_Arena1#2", fm, "卡绑定必须指向本仓 IR issue #2")

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

    def test_nongoals_bound(self):
        fm = frontmatter(read(SPEC))
        self.assertIn("不重写", fm, "nonGoals 须保留架构不重写边界")
        self.assertIn("治理脚手架", fm, "nonGoals 须保留治理脚手架不动边界")


if __name__ == "__main__":
    unittest.main(verbosity=2)
