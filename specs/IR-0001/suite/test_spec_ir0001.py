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
            for part in m.groups():
                self.assertGreaterEqual(len(part.strip()), 8, f"AC-{i} 某段过短（摆拍式 AC）")

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
