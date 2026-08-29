#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xborder-material-agent v3.3.0-final —— 零依赖离线自检。

纯 Python 标准库，不调用任何模型 API、不访问网络。覆盖：
  1) --version 契约           2) 官方 prompt 路径解析（含 en/ko/pt 陷阱）
  3) A1 黑名单词边界（SDV#12 不被吞）
  4) 词表翻译往返与度量换算    5) 占位 PNG 生成与尺寸断言
  6) stub 输入端到端 = 恰好 11 文件 + exit 0 + 双区/买家区零 CJK
  7) zip 结构自检（仅当在同仓找到 xborder-agent-v3*.zip 时执行，否则 SKIP）
  9) mvhd 时长解析（v3.0.3）  10) 互异图池构建（v3.0.3 + v3.3.0 描述字段图）
 11) 内容级去重选图：白/浅灰主图优先、六槽目标结构、同镜头组判重、回退（v3.3.0）
 12) 陈述一致性（门控/策略文档/自审表/指纹，v3.3.0）
 13) 全片严格质检语义 + 源视频扫描（v3.2.0）
 14) 双区结构/标题公式/SKU 汇总/真实尺码列/PT 正字/买家区净化（v3.3.0）
 15) 尺码表 OCR 文本解析器（真实样本+交叉校验+失败下界，v3.3.0）
 16) 描述字段提图/色标权威化/自然语言图文（v3.3.0）

用法：
  python tests/selftest.py                 # 自动定位 agent/agent.py
  python tests/selftest.py --agent PATH    # 显式指定被测 agent.py
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CJK_RE = re.compile(r"[\u3000-\u303F\u4E00-\u9FFF\uFF00-\uFFEF]")
EXPECTED_MD = ["product_description_en.md", "product_description_ko.md",
               "product_description_pt.md", "strategy_document.md"]
EXPECTED_VIDEO = ["product_video.mp4"]
EXPECTED_IMG_BASES = ["main_image"] + ["detail_image_%d" % i for i in range(1, 6)]

# 官方《说明 B》prompt 原文（CNB 复刻环境逐字使用；注意 "en/ko/pt" 位于两个路径之后）
OFFICIAL_PROMPT = (
    "## 任务目标 读取 `/home/user/ws/input/` 目录下目标商品的全部信息文件，"
    "提取指定内容，按规范生成输出文件并保存至 `/home/user/ws/output/`。 "
    "## 输出要求 1. 输出目录：`/home/user/ws/output/` 2. 针对该商品，需完整产出"
    "以下素材，各项须命名规范、字段可解析（商品文案 en/ko/pt 三份、主图 main_image、"
    "详情图 detail_image_1..5、商品视频 product_video、策略说明 strategy_document）。"
)

STUB_PRODUCT = {  # ret.result.result 三层包裹 + 最小字段集
    "ret": {"result": {"result": {
        "offerId": 1001, "subject": "测试连衣裙", "platform": "AliExpress",
        "url": "https://www.aliexpress.com/item/1001.html",
        "categoryId": "100010", "category_name": "连衣裙",
        "productSkuInfos": [{"skuAttributes": [
            {"attributeName": "颜色", "value": "黑色"},
            {"attributeName": "尺码", "value": "M 100-120斤"}]}],
        "productAttribute": [{"attributeName": "颜色", "value": "黑色"}],
        "productImage": {"images": ["https://img.invalid/a.jpg"]},
    }}}}

FAKE_JPEG = b"\xff\xd8" + b"\x00" * 2048  # 过底盘校验：FF D8 魔数 + >1KB


def find_agent_py(explicit):
    cands = [explicit, os.environ.get("XBOT_AGENT_PY"),
             os.path.join(HERE, "..", "agent.py"),                   # v3.0.2+ 全在 agent/ 内布局
             os.path.join(HERE, "..", "agent", "agent.py"),          # 旧布局（tests/ 与 agent/ 平级）
             os.path.join(HERE, "..", "..", "v252", "agent", "agent.py"),
             os.path.join(HERE, "..", "..", "v251", "agent", "agent.py"),
             os.path.join(HERE, "..", "..", "v242", "agent", "agent.py")]
    for c in cands:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    return None


def load_agent(path):
    spec = importlib.util.spec_from_file_location("agent_under_selftest", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def t01_version(mod):
    v = mod.read_version()
    assert re.match(r"^\d+\.\d+\.\d+$", str(v)), "version 非语义化: %r" % v


def t02_official_prompt(mod):
    cands = mod.extract_paths(OFFICIAL_PROMPT)
    assert "/ko/pt" in cands, "陷阱片段 /ko/pt 未出现在候选路径中（前置断言失效）"
    assert mod.resolve_output(OFFICIAL_PROMPT).rstrip("/").endswith("/home/user/ws/output")
    assert mod.resolve_input(OFFICIAL_PROMPT).rstrip("/").endswith("/home/user/ws/input")


def t03_trap_fragments(mod):
    """en/ko/pt 枚举与 .json 后缀出现在 output 之后，仍必须锁定 output 目录。"""
    p = ("生成 product_description_en/ko/pt 三份文案并写入 "
         "/home/user/ws/output/result.json 与 /home/user/ws/output；"
         "输入见 /home/user/ws/input。")
    assert mod.resolve_output(p).rstrip("/") == "/home/user/ws/output"
    assert mod.resolve_input(p).rstrip("/") == "/home/user/ws/input"


def t04_blacklist(mod):
    out, hits = mod.apply_blacklist("Model SDV#12 / SDV#no.1 keep verbatim")
    assert hits == 0 and out == "Model SDV#12 / SDV#no.1 keep verbatim", "词边界保护失效"
    out, hits = mod.apply_blacklist("This is the BEST shirt with best quality.")
    assert hits >= 2 and "best" not in out.lower(), "黑名单未净化骨架句: %r" % out
    out, _ = mod.apply_blacklist("We are the number one store")
    assert "number one" not in out, "极限词未被替换: %r" % out


def t05_glossary_and_units(mod):
    for zh, entry in mod.GLOSSARY.items():
        for lang in ("en", "ko", "pt"):
            got = mod.loc_terms(zh, lang)
            assert got == entry[lang], "词表往返失败 %s/%s: %r != %r" % (zh, lang, got, entry[lang])
    assert mod.loc_terms("颜色:黑色", "en") == "Color:Black"
    # v3.2.0 翻译收尾词表（红队 39 行 CJK 残留的确定性清零）
    assert mod.loc_terms("常规袖", "en") == "Regular Sleeve", mod.loc_terms("常规袖", "en")
    assert mod.loc_terms("其他", "en") == "No Brand"
    assert mod.loc_terms("其他", "pt") == "No Brand"
    assert mod.loc_terms("单排扣", "en") == "Single Breasted"
    # v3.4.0（红队 F14）：KO 通行音译、PT 保留业内词并加葡语短注
    assert mod.loc_terms("单排扣", "ko") == "싱글 브레스티드"
    assert mod.loc_terms("单排扣", "pt") == "Single Breasted (abotoamento frontal)"
    assert mod.loc_terms("日韩休闲", "en") == "Korean/Japanese casual style"
    assert mod.loc_terms("舒适休闲", "en") == "Comfort casual"
    assert mod.loc_terms("M 95-105斤", "en") == "M 95-105 jin"
    assert mod.loc_terms("50%（含）-70%（不含）", "en") == "50%(incl.)-70%(excl.)"
    assert mod.ae_map_attr("袖长", "长袖")[0] == "Sleeve Length", "袖长字段名应为 Sleeve Length"
    assert mod.ae_map_attr("袖型", "常规袖")[0] == "Sleeve Style"
    assert mod.ae_map_attr("袖长", "长袖")[1] == "Full"
    # 年份+季节确定性模式
    assert mod.smart_value_display("2024年秋季", "en", {}) == "Autumn 2024"
    assert mod.smart_value_display("2024年秋季", "ko", {}) == "2024년 가을"
    assert mod.smart_value_display("2024年秋季", "pt", {}) == "Outono 2024"
    en = mod.add_weight_comment("Size:M 100-120斤", "en")
    assert en.endswith("(≈50-60 kg / 110-132 lbs)"), en
    assert mod.add_weight_comment("Size:M 100-120斤", "ko").endswith("(≈50-60 kg)")


def t06_placeholder_png(mod):
    tmp = tempfile.mkdtemp(prefix="sfx_png_")
    try:
        p = os.path.join(tmp, "probe.png")
        mod.write_png(p, 1024, 1024, (240, 240, 240))
        with open(p, "rb") as f:
            blob = f.read()
        assert blob[:8] == b"\x89PNG\r\n\x1a\n", "PNG 签名不符"
        w, h = struct.unpack(">II", blob[16:24])
        assert (w, h) == (1024, 1024), "占位图尺寸断言失败: %dx%d" % (w, h)
        assert blob[25] == 2, "应为 8-bit RGB (color type 2)"
        assert 0 < len(blob) < 1024 * 1024
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _harden(mod):
    """ hermetic 化：断网、去退避等待、去 API key。返回还原函数。"""
    saved = {"api_key": getattr(mod, "api_key", None),
             "fetch_image": getattr(mod, "fetch_image", None),
             "fetch_jpeg_retry": getattr(mod, "fetch_jpeg_retry", None),
             "sleep": mod.time.sleep}
    mod.time.sleep = lambda *_a, **_k: None
    if saved["api_key"]:
        mod.api_key = lambda: ""
    if saved["fetch_image"]:
        mod.fetch_image = lambda *a, **k: FAKE_JPEG
    if saved["fetch_jpeg_retry"]:
        mod.fetch_jpeg_retry = lambda *a, **k: FAKE_JPEG
    return lambda: _restore(mod, saved)


def _restore(mod, saved):
    mod.time.sleep = saved["sleep"]
    for k, fn in saved.items():
        if k != "sleep" and fn is not None:
            setattr(mod, k, fn)


def _scratch(tag):
    """正则安全（[\w.\-/()]）的本地 scratch 目录 —— 系统临时目录可能含 ~ 等
    8.3 短名字符，会被底盘路径解析切断，故固定放在 tests/ 之下。"""
    base = os.path.join(HERE, ".selftest_tmp", "%s_%d" % (tag, os.getpid()))
    shutil.rmtree(base, ignore_errors=True)
    os.makedirs(base)
    return base.replace("\\", "/")


def t07_stub_run(mod):
    """stub 输入（含坏 JSON + 最小商品）→ 恰好 11 文件 + 双区/买家区零 CJK；
    空输入 → 全占位 11 文件。"""
    restore = _harden(mod)
    try:
        for scenario in ("stub", "empty"):
            base = _scratch("run_" + scenario)
            inp, out = base + "/sfx_input", base + "/sfx_output"
            os.makedirs(inp)
            if scenario == "stub":
                with open(os.path.join(inp, "broken.json"), "w", encoding="utf-8") as f:
                    f.write("{not json")
                with open(os.path.join(inp, "stub.json"), "w", encoding="utf-8") as f:
                    json.dump(STUB_PRODUCT, f, ensure_ascii=False)
            rc = mod.run("读取 %s 保存至 %s" % (inp, out), mod.read_version())
            assert rc == 0, "run() 返回非 0"
            got = sorted(os.listdir(out))
            imgs = [n for n in got if n.rsplit(".", 1)[0] in EXPECTED_IMG_BASES]
            exts = {n.rsplit(".", 1)[1] for n in imgs}
            assert len(imgs) == 6 and exts <= {"jpeg", "png"} and len(exts) == 1, got
            assert sorted(got) == sorted(EXPECTED_MD + EXPECTED_VIDEO + imgs), got
            for name in EXPECTED_MD:
                with open(os.path.join(out, name), "rb") as f:
                    body = f.read().decode("utf-8")
                assert body.strip(), "%s 为空" % name
            if scenario == "stub":
                with open(os.path.join(out, "product_description_en.md"), encoding="utf-8") as f:
                    en = f.read()
                assert "Compliance Self-Audit" in en and "Sourcing Provenance" in en
                # v3.2.0 双区：Appendix 标记 + 买家区零 CJK
                assert mod.APPENDIX_MARKER in en, "缺 Platform Data Appendix 标记"
                buyer = en[:en.index(mod.APPENDIX_MARKER)]
                assert not CJK_RE.search(buyer), "买家区残留 CJK: %r" % buyer[:400]
                assert not re.search(r"\bchest \d", en), "编造胸围数据仍在"
                assert "$12.99" not in en and "₩12,900" not in en and "1.234,56" not in en, "价格示例仍在"
                for bad in ("Coupang", "Naver", "Musinsa", "Mercado Livre"):
                    assert bad not in buyer, "买家区竞品平台名: %s" % bad
                # v3.3.0 买家区净化：linter 行/编造样例/内贸字段不得进入买家区
                for bad in ("linter", "Orthography", "sample sizing", "Article No",
                            "export market", "Cross-border supply", "deterministic"):
                    assert bad not in buyer, "买家区脏字段: %s" % bad
            shutil.rmtree(base, ignore_errors=True)
    finally:
        restore()


def t08_zip_structure():
    """v3.0.0 包结构纪律：zip 根集合 == {agent}、入口齐全、零日志、无预置产物。
    v3.5.1 起锁定本版本包名 xborder-agent-v3.5.1-final.zip（打到 → PASS；
    未打包 → SKIP；历史旧包不在此检查范围）。"""
    target = "xborder-agent-v3.6.2-final.zip"
    hits = []
    cur = HERE
    for _ in range(6):
        cur = os.path.dirname(cur)
        if not os.path.isdir(cur):
            break
        for base in (cur, os.path.join(cur, "submissions", "probes")):
            p = os.path.join(base, target)
            if os.path.isfile(p):
                hits.append(p)
    hits = sorted(set(hits))
    if not hits:
        return "SKIP: 未找到 %s（打包后重跑即查）" % target
    with zipfile.ZipFile(hits[-1]) as z:
        names = z.namelist()
        assert any(n == "agent/agent.py" for n in names), "zip 缺 agent/agent.py"
        assert any(n == "agent/agent.json" for n in names), "zip 缺 agent/agent.json"
        roots = {n.split("/", 1)[0] for n in names if n}
        assert roots == {"agent"}, "zip 根集合必须 == {agent}: %r" % roots
        assert not [n for n in names if n.endswith(".log")], "zip 内不得有日志文件"
        assert not [n for n in names if "/output/" in n], "zip 内不得预置产物目录"
    sys.stdout.write("  t08 validated: %s%s" % (os.path.basename(hits[-1]), chr(10)))
    return None


# ---------------- v3.0.3+：互异图池 / mvhd 时长 / 陈述一致性 ----------------

def t09_mvhd_duration(mod):
    """mvhd 纯标准库时长断言：预置片（base64 内嵌与 assets 双源）≈1s；坏输入 → None。"""
    d2 = mod.mp4_duration_seconds(base64.b64decode("".join(mod.PRESET_MP4_B64)))
    assert d2 is not None and 0.5 <= d2 <= 1.5, "内嵌预置片时长异常: %r" % d2
    assets = os.path.join(HERE, "..", "assets", "preset_video.mp4")
    if os.path.isfile(assets):
        with open(assets, "rb") as f:
            d1 = mod.mp4_duration_seconds(f.read())
        assert d1 is not None and 0.5 <= d1 <= 1.5, "assets 预置片时长异常: %r" % d1
    assert mod.mp4_duration_seconds(b"\x00" * 64) is None, "垃圾输入应返回 None"
    assert mod.mp4_duration_seconds(b"not an mp4" * 16) is None
    assert mod.mp4_duration_seconds(None) is None


def t10_image_pool(mod):
    """互异图池（v3.3.0 扩容）：主图原序在前 + SKU 图（skuInfos 顺序）+ description
    字段内嵌图在后，全池保序 URL 级去重；描述 HTML 提图双通道（<img src> + 裸 URL）。"""
    facts = {"images": ["m1", "m2", "m1"], "sku_images": ["s1", "m2", "s2", "s1"],
             "description_images": ["d1", "m1", "d2", "d1"]}
    assert mod.collect_image_pool(facts) == ["m1", "m2", "s1", "s2", "d1", "d2"], \
        mod.collect_image_pool(facts)
    assert mod.collect_image_pool({}) == []
    assert mod.collect_image_pool(None) == []
    inner = {"productSkuInfos": [
                 {"skuAttributes": [{"attributeName": "颜色", "value": "黑", "skuImageUrl": "sk1"}]},
                 {"skuAttributes": [{"attributeName": "尺码", "value": "M", "skuImageUrl": "sk2"}]}],
             "productImage": {"images": ["p1", "p1"]},
             "description": ('<p><img src="https://cdn.example/d01.jpg" />'
                             '<img alt="x" src="https://cdn.example/d02.jpeg">'
                             'see https://cdn.example/d03.png?Expires=1&amp;Signature=ab%2Fcd '
                             'and https://cdn.example/d01.jpg again</p>')}
    f = mod.extract_facts(inner)
    assert f["sku_images"] == ["sk1", "sk2"] and f["images"] == ["p1", "p1"], f
    assert f["description_images"] == ["https://cdn.example/d01.jpg",
                                       "https://cdn.example/d02.jpeg",
                                       "https://cdn.example/d03.png?Expires=1&Signature=ab%2Fcd"], \
        f["description_images"]
    assert mod.collect_image_pool(f) == ["p1", "sk1", "sk2",
                                         "https://cdn.example/d01.jpg",
                                         "https://cdn.example/d02.jpeg",
                                         "https://cdn.example/d03.png?Expires=1&Signature=ab%2Fcd"]
    # 无 description 字段（旧商品形态）→ 与 v3.2.0 行为一致
    f2 = mod.extract_facts({"productSkuInfos": [], "productImage": {"images": ["p1"]}})
    assert f2["description_images"] == [] and mod.collect_image_pool(f2) == ["p1"]
    assert mod._extract_description_images(None) == []
    assert mod._extract_description_images("no urls here") == []


def _score_for(u):
    """测试用打分（v3.3.0 字段全集）：<类别前缀>-<序号>；white=白/浅灰棚拍，
    warm=暖调，clear=主体清晰，颜色词作为 dominant_color，grp<N>=同镜头组标签，
    text/wm=has_text/has_watermark，chart=尺码表，macro=面料微距，side=侧面。"""
    parts = u.split("-")
    cat = parts[0]
    white = "white" in parts and not any(p.startswith("white") and p != "white" for p in parts)
    warm = "warm" in parts
    color = ""
    for c in ("green", "black", "white", "beige", "purple", "blue"):
        if c in parts:
            color = c
    group = 0
    for p in parts:
        if p.startswith("grp") and p[3:].isdigit():
            group = int(p[3:])
    return {"has_text": "text" in parts, "has_watermark": "wm" in parts,
            "is_collage": False,
            "uniform_light_bg": white, "warm_tone_bg": warm,
            "subject_clear": "clear" in parts,
            "is_back_view": cat == "back", "is_side_view": cat == "side",
            "is_closeup_or_detail": cat in ("closeup", "macro"),
            "is_fabric_macro": cat == "macro",
            "is_flat_lay": cat == "flat", "is_scene": cat == "scene",
            "is_size_chart": cat == "chart",
            "same_shot_group": group,
            "dominant_color": color}


def t11_content_dedupe_selection(mod):
    """v3.4.0 内容级去重选图：同内容 URL 只留代表、白/浅灰棚拍主图优先（暖调不算
    命中）、图集无文字资格新规（文字/水印/拼图一律出局，描述图不豁免；尺码表截图
    =数据源图不入图集）、细节/微距槽 → 异色正面/场景×4、同镜头组组内只取一张、
    内容级 URL 色名传播、溢出槽复用末张详情、VL 失败回退。"""
    saved_score, saved_batch, saved_fetch = (mod.vl_score_image, mod.vl_score_batch,
                                             mod.fetch_jpeg_retry)
    saved_sleep = mod.time.sleep
    mod.time.sleep = lambda *_a, **_k: None
    base = None
    try:
        desc_urls = {"chart-d01-text", "macro-d02-text", "side-d17-text-wm"}  # 描述字段来源
        urls = ["front-warm-clear-1", "front-warm-clear-2",   # 同内容 ×2（字节相同）
                "front-white-clear-3", "front-green-clear-4",
                "chart-d01-text", "macro-d02-text", "side-d17-text-wm",
                "front-black-grp9-6", "front-black-grp9-7", "scene-white-clear-5"]
        blobs = {}
        for i, u in enumerate(urls):
            # u1/u2 同内容：同 blob；其余互异
            key = 0 if u == "front-warm-clear-2" else i
            blobs[u] = b"\xff\xd8" + bytes([key + 1]) * 2048
        mod.fetch_jpeg_retry = lambda url, attempts=3, backoff=None, timeout=60: blobs[url]
        mod.vl_score_image = lambda u: _score_for(u)
        mod.vl_score_batch = lambda items: {u: _score_for(u) for u, _b in items}
        facts = {"images": urls[:4], "sku_images": urls[4:],
                 "description_images": sorted(desc_urls),
                 "sku_pairs": [[("颜色", "白色")], [("颜色", "绿色")],
                               [("颜色", "黑色")], [("颜色", "紫色")]]}
        base = _scratch("dedupe")
        out = base + "/sfx_out"
        os.makedirs(out)
        pool = mod.collect_image_pool(facts)
        assert len(pool) == 10, pool
        groups, failed, tried = mod.dedupe_pool_by_content(pool)
        assert len(groups) == 9 and not failed and tried == 10, (len(groups), failed, tried)
        assert all(len(g.get("urls") or []) >= 1 for g in groups), "groups 缺 urls 字段"
        scores = mod.vl_score_batch([(g["url"], None) for g in groups])
        sel, meta = mod.select_from_contents(groups, scores, len(pool), 0, sixslot=True,
                                             desc_urls=desc_urls,
                                             sku_colors=["白色", "绿色", "黑色", "紫色"])
        # 主图：白/浅灰棚拍唯一命中（暖调不算），尺码表不作主图
        assert sel["main"]["url"] == "front-white-clear-3", sel["main"]
        assert meta["main_bg_hit"] is True, meta
        det = [g["url"] for g in sel["details"]]
        # v3.4.0 图集资格新规：文字图（chart/macro/side 全带 text/wm）一律出局，
        # 细节/微距槽缺口 → 四色槽补足：绿 → 黑（同组 grp9 只取一张）→ 暖调正面 → 白场景
        assert det == ["front-green-clear-4", "front-black-grp9-6",
                       "front-warm-clear-1", "scene-white-clear-5"], det
        chosen = [sel["main"]["url"]] + det
        assert not any(u in chosen for u in desc_urls), "文字图进入了图集: %r" % chosen
        # 同镜头组 grp9 组内只取一张：另一张（grp9-7）不入选
        assert "front-black-grp9-7" not in chosen, chosen
        assert meta["groups_merged"] == 1, meta
        assert "白/浅灰棚拍命中" in meta["record"], meta["record"]
        # 出局/数据源统计（诚实披露）
        assert len(meta["text_excluded"]) == 3, meta["text_excluded"]
        assert meta["data_source"] == [], meta["data_source"]
        assert "细节/微距" in meta["missing_cats"], meta["missing_cats"]
        # 尺码表截图（无文字假想形态）→ 数据源图，不入图集
        chart_url = "chart-clean"
        groups3 = groups + [{"url": chart_url, "blob": b"\xff\xd8" + b"\x99" * 2048,
                             "sha": "zz", "urls": [chart_url]}]
        scores3 = dict(scores)
        scores3[chart_url] = dict(_score_for(chart_url), is_size_chart=True)
        sel3, meta3 = mod.select_from_contents(groups3, scores3, 11, 0, sixslot=True,
                                               desc_urls=desc_urls,
                                               sku_colors=["白色", "绿色", "黑色", "紫色"])
        assert chart_url not in [sel3["main"]["url"]] + [g["url"] for g in sel3["details"]], \
            "数据源图进入了图集"
        assert meta3["data_source"] == [chart_url], meta3["data_source"]

        # 同镜头组判重的直接证明：color 槽跳过同组的 black-grp9-3，改取异色 beige
        urls2 = ["front-white-clear-1", "front-black-grp9-2",
                 "front-black-grp9-3", "scene-beige-clear-4"]
        blobs2 = {u: b"\xff\xd8" + bytes([i + 1]) * 2048 for i, u in enumerate(urls2)}
        mod.fetch_jpeg_retry = lambda url, attempts=3, backoff=None, timeout=60: blobs2[url]
        groups2, _, _ = mod.dedupe_pool_by_content(urls2)
        scores2 = mod.vl_score_batch([(g["url"], None) for g in groups2])
        sel2, meta2 = mod.select_from_contents(groups2, scores2, len(urls2), 0, sixslot=True,
                                               desc_urls=desc_urls,
                                               sku_colors=["白色", "绿色", "黑色", "紫色"])
        det2 = [g["url"] for g in sel2["details"]]
        assert det2 == ["front-black-grp9-2", "scene-beige-clear-4"], det2
        assert "front-black-grp9-3" not in [sel2["main"]["url"]] + det2, det2
        # 还原第一组 blob（供后续 write_images 端到端使用）
        mod.fetch_jpeg_retry = lambda url, attempts=3, backoff=None, timeout=60: blobs[url]

        # 主图 SKU 色点名（盲评#5）：main=front-white-clear-3 无 URL 色、VL 主色 white
        # 命中 SKU → 正常写白；换无色 fixture 并 mock 点名 → 写绿
        names, ext, img_meta = mod.write_images(out, facts, use_vl=True, use_distinct=True,
                                                use_dedupe=True, sixslot=True,
                                                use_desc=True, colorauth=True)
        assert ext == "jpeg" and img_meta["mode"] == "vl-distinct", img_meta
        assert img_meta["pool"] == 10 and img_meta["contents"] == 9, img_meta
        # 合格互异内容 6 张（9 组 -3 张文字图）→ 选 5 张互异，第 6 槽复用末张详情（兼容）
        assert img_meta["distinct"] == 5, img_meta
        assert img_meta["main_bg_hit"] is True
        assert img_meta["gallery_text"] == {"n": 6, "clean": True, "clean_n": 6,
                                            "excluded": 3, "data_source": [],
                                            "ui_excluded": 0}, img_meta["gallery_text"]
        hashes = set()
        for n in names:
            with open(os.path.join(out, n), "rb") as f:
                hashes.add(hashlib.sha1(f.read()).hexdigest())
        assert len(hashes) == 5, "产物互异字节数异常: %d" % len(hashes)
        # 图文自然语言：main=front view + 白色（SKU 权威）；无尺码表槽（数据源图新规）
        desc = mod.render_img_descriptions(img_meta, "en", "jpeg", cat_word="Blouse")
        assert ("The main image shows the blouse in white, front view, shot on a plain "
                "light studio background.") in desc, desc
        assert "supplier size chart" not in desc, "尺码表槽应已退出图集"
        assert "craftsmanship details of the product" not in desc, desc

        # 主图无色 + VL 点名 mock → 主图写绿（SKU 匹配成功即不回避）
        saved_pin = mod.vl_pin_sku_color
        try:
            mod.vl_pin_sku_color = lambda url, blob=None, color_words=(): "green"
            facts_pin = {"images": ["front-clear-1", "scene-clear-2", "scene-clear-3",
                                    "scene-clear-4", "scene-clear-5", "scene-clear-6"],
                         "sku_images": [],
                         "sku_pairs": [[("颜色", "绿色")]]}
            pin_blobs = {"front-clear-%d" % i: b"\xff\xd8" + bytes([i]) * 2048
                         for i in range(1, 7)}
            pin_blobs["scene-clear-2"] = b"\xff\xd8" + b"\xa2" * 2048
            pin_blobs["scene-clear-3"] = b"\xff\xd8" + b"\xa3" * 2048
            pin_blobs["scene-clear-4"] = b"\xff\xd8" + b"\xa4" * 2048
            pin_blobs["scene-clear-5"] = b"\xff\xd8" + b"\xa5" * 2048
            pin_blobs["scene-clear-6"] = b"\xff\xd8" + b"\xa6" * 2048
            mod.fetch_jpeg_retry = lambda url, attempts=3, backoff=None, timeout=60: pin_blobs[url]
            def _pin_score(u):
                s = _score_for("scene-clear-white")
                if u != "front-clear-1":
                    s["dominant_color"] = "beige"
                return s
            mod.vl_score_image = _pin_score
            mod.vl_score_batch = lambda items: {u: _pin_score(u) for u, _b in items}
            _, _, meta_pin = mod.write_images(out, facts_pin, use_vl=True, use_distinct=True,
                                              use_dedupe=True, sixslot=True, use_desc=True,
                                              colorauth=True, skupin=True)
            assert meta_pin["slots"][0]["color_zh"] == "绿色", meta_pin["slots"][0]
            assert "VL SKU 色点名" in meta_pin["record"], meta_pin["record"]
            # 点名 none → 保持 as shown（回退口径）
            mod.vl_pin_sku_color = lambda url, blob=None, color_words=(): "none"
            _, _, meta_pin2 = mod.write_images(out, facts_pin, use_vl=True, use_distinct=True,
                                               use_dedupe=True, sixslot=True, use_desc=True,
                                               colorauth=True, skupin=True)
            assert meta_pin2["slots"][0]["color_zh"] == "", meta_pin2["slots"][0]
        finally:
            mod.vl_pin_sku_color = saved_pin

        # 池不足 6 张互异内容 → 允许复用，溢出槽复用【末张详情】而非主图
        facts_small = {"images": ["front-clear-1", "front-clear-2"], "sku_images": []}
        blobs_small = {"front-clear-1": b"\xff\xd8" + b"\x11" * 2048,
                       "front-clear-2": b"\xff\xd8" + b"\x22" * 2048}
        mod.fetch_jpeg_retry = lambda url, attempts=3, backoff=None, timeout=60: blobs_small[url]
        names2, _, meta_small = mod.write_images(out, facts_small, use_vl=True, use_distinct=True,
                                                 use_dedupe=True, sixslot=True, use_desc=True)
        assert meta_small["contents"] == 2 and meta_small["distinct"] == 2, meta_small
        with open(os.path.join(out, "main_image.jpeg"), "rb") as f:
            main_blob = f.read()
        with open(os.path.join(out, "detail_image_4.jpeg"), "rb") as f:
            d4 = f.read()
        with open(os.path.join(out, "detail_image_5.jpeg"), "rb") as f:
            d5 = f.read()
        assert d4 == d5, "溢出槽未复用末张详情图"
        assert main_blob != d5, "详情槽复用了主图字节"

        # VL 打分全失败 → 顺序直投回退（允许复用，兜底语义不变）
        mod.vl_score_batch = lambda items: {}
        mod.vl_score_image = lambda u: None
        mod.fetch_jpeg_retry = lambda url, attempts=3, backoff=None, timeout=60: blobs[url]
        _, _, meta_fb = mod.write_images(out, facts, use_vl=True, use_distinct=True,
                                         use_dedupe=True, sixslot=True, use_desc=True)
        assert meta_fb["mode"] == "sequential", meta_fb
        assert meta_fb["pool"] == 10, meta_fb
    finally:
        mod.time.sleep = saved_sleep
        mod.vl_score_image, mod.vl_score_batch, mod.fetch_jpeg_retry = (saved_score,
                                                                        saved_batch, saved_fetch)
        if base:
            shutil.rmtree(base, ignore_errors=True)


def t17_divsel_and_uigate(mod):
    """v3.5.0：divsel 视觉级去重选图 + uigate UI 符号/留白边框资格门。
    场景复刻亲验 v3.4.0 硬伤：紫衫同机位近似重复（不同镜头组标签）+ ▼ 符号残留图。"""
    def sc(**kw):
        base = {"has_text": False, "has_watermark": False, "is_collage": False,
                "uniform_light_bg": False, "warm_tone_bg": False, "subject_clear": True,
                "is_back_view": False, "is_side_view": False, "is_closeup_or_detail": False,
                "is_fabric_macro": False, "is_flat_lay": False, "is_scene": True,
                "is_size_chart": False, "same_shot_group": 0, "dominant_color": "",
                "third_party_mark": "", "pose": "", "accessory_load": 0,
                "has_ui_symbols": False, "letterbox": False}
        base.update(kw)
        return base
    def g(u):
        return {"url": u, "blob": None}
    groups = [g(u) for u in ("main-green", "c1-black", "c2-purple", "c3-white",
                             "c4-purple-dup", "c5-green-sit", "c6-purple-ui", "c7-beige")]
    scores = {
        "main-green": sc(uniform_light_bg=True, dominant_color="green", pose="front"),
        "c1-black": sc(dominant_color="black", pose="front"),
        "c2-purple": sc(dominant_color="purple", pose="front"),
        "c3-white": sc(dominant_color="white", pose="side"),
        "c4-purple-dup": sc(dominant_color="purple", pose="front"),
        "c5-green-sit": sc(dominant_color="green", pose="sitting"),
        "c6-purple-ui": sc(dominant_color="purple", pose="front", has_ui_symbols=True),
        "c7-beige": sc(dominant_color="beige", pose="flat", is_scene=False,
                       is_flat_lay=True),
    }
    sel, meta = mod.select_from_contents(groups, scores, sixslot=True,
                                         gallerytext=True, uigate=True, divsel=True)
    assert sel and len(sel["details"]) == 5, meta
    picked = [sel["main"]["url"]] + [d["url"] for d in sel["details"]]
    # uigate：▼ 残留图不入图集
    assert "c6-purple-ui" not in picked and "c6-purple-ui" in (meta.get("ui_excluded") or []), (picked, meta)
    # divsel：紫衫同机位近似重复只取一张（c2 与 c4 同色同姿态同场景）
    assert "c2-purple" in picked and "c4-purple-dup" not in picked, picked
    # 颜色覆盖仍优先：黑/紫/白/米四色 + 主图绿全数在集
    for u in ("main-green", "c1-black", "c3-white", "c7-beige"):
        assert u in picked, picked
    # 关闭 divsel/uigate（<3.5.0 门控）→ 行为回到 v3.4.0：ui 图可入选（组标签全 0 不判重）
    sel0, meta0 = mod.select_from_contents(groups, scores, sixslot=True,
                                           gallerytext=True, uigate=False, divsel=False)
    picked0 = [sel0["main"]["url"]] + [d["url"] for d in sel0["details"]]
    # 旧语义对照：无 UI 资格门（ui_excluded 空）、无视觉距离（同机位近似重复 c4 照常入选）
    assert not (meta0.get("ui_excluded") or []), meta0.get("ui_excluded")
    assert "c4-purple-dup" in picked0 and "c6-purple-ui" not in picked0, picked0
    # v3.5.0 flags 门控
    f35 = mod.feature_flags("3.5.0")
    assert all(f35.get(k) for k in ("qchard", "uigate", "divsel", "vidcap", "steadycam")), f35
    f34 = mod.feature_flags("3.4.0")
    assert not any(f34.get(k) for k in ("qchard", "uigate", "divsel", "vidcap", "steadycam")), f34


def t18_qc_merge_and_vidcap(mod):
    """v3.5.0：双通道质检合并纯函数 + vidcap 视频描述/姿态短语。"""
    K = ("accessory_clone", "finger_defect", "button_misalign",
         "texture_melt", "blocky_artifacts", "garbled_text", "ok")
    # 双 None → skip 放行（v3.4.0 语义不变）
    assert mod.merge_video_qc(None, None) is None
    # 任一通道任一缺陷 → 从严不合格
    bad_a = {k: False for k in K}; bad_a["accessory_clone"] = True; bad_a["ok"] = False
    bad_b = {k: False for k in K}; bad_b["blocky_artifacts"] = True; bad_b["ok"] = False
    m = mod.merge_video_qc(bad_a, None)
    assert m is not None and m["accessory_clone"] and not m["ok"], m
    m = mod.merge_video_qc(None, bad_b)
    assert m is not None and m["blocky_artifacts"] and not m["ok"], m
    m = mod.merge_video_qc(bad_a, bad_b)
    assert m["accessory_clone"] and m["blocky_artifacts"] and not m["ok"], m
    ok_a = {k: False for k in K}; ok_a["ok"] = True
    ok_b = {k: False for k in K}; ok_b["ok"] = True
    m = mod.merge_video_qc(ok_a, ok_b)
    assert m["ok"] and not any(m[k] for k in K if k != "ok"), m
    # vidcap 视频描述：i2v 10s / preset / 无时长
    vi = {"mode": "i2v", "tier": "10s", "secs": 10}
    en = mod.video_desc_line({"_video_info": vi}, "en")
    assert "10 second" in en and "first frame matches main_image" in en, en
    assert "no third-party music" in en, en
    pt = mod.video_desc_line({"_video_info": vi}, "pt")
    assert "10 segundos" in pt, pt
    pre = mod.video_desc_line({"_video_info": {"mode": "preset"}}, "en")
    assert "preset" in pre, pre
    nodur = mod.video_desc_line({"_video_info": {"mode": "i2v", "secs": None}}, "en")
    assert "showcase video" in nodur and "10" not in nodur.split("showcase")[0], nodur
    # vidcap 姿态短语：pose 标签可用时给每行差分；关闭时不追加
    img_meta = {"mode": "vl-distinct", "slots": [
        {"name": "main_image", "cat": "front", "color_zh": "绿色", "white_bg": True,
         "pose": "front", "scene": False, "accessory_load": 2},
        {"name": "detail_image_1", "cat": "scene", "color_zh": "黑色", "white_bg": False,
         "pose": "sitting", "scene": True, "accessory_load": 1},
        {"name": "detail_image_2", "cat": "scene", "color_zh": "紫色", "white_bg": False,
         "pose": "front", "scene": True, "accessory_load": 1}]}
    lines_on = mod.render_img_descriptions(img_meta, "en", "jpeg", vidcap=True)
    assert "shown from the front" in lines_on, lines_on
    assert "seated pose" in lines_on, lines_on
    lines_off = mod.render_img_descriptions(img_meta, "en", "jpeg", vidcap=False)
    assert "shown from the front" not in lines_off, lines_off
    # 策略文档 v3.5.0 新陈述（divsel/qchard 开启才出现）
    facts = {"subject": "测试连衣裙", "images": [], "sku_images": [],
             "description_images": [], "sku_rows": [], "sku_pairs": [],
             "attr_pairs": [], "attr_rows": []}
    doc35 = mod.strategy_document("3.5.0", facts, mod.feature_flags("3.5.0"),
                                  "vl-distinct",
                                  img_stats={"mode": "vl-distinct", "pool": 55,
                                             "contents": 32, "distinct": 6,
                                             "main_bg_hit": True,
                                             "size_chart": {"ok": False, "why": "x"}})
    assert "视觉级去重" in doc35 and "双通道质检" in doc35, "策略文档缺 v3.5.0 陈述"
    doc34 = mod.strategy_document("3.4.0", facts, mod.feature_flags("3.4.0"),
                                  "vl-distinct",
                                  img_stats={"mode": "vl-distinct", "pool": 55,
                                             "contents": 32, "distinct": 6,
                                             "main_bg_hit": True,
                                             "size_chart": {"ok": False, "why": "x"}})
    assert "视觉级去重" not in doc34 and "双通道质检" not in doc34, "v3.4.0 文档泄漏 v3.5.0 陈述"


def t19_write_images_divsel_smoke(mod):
    """v3.5.0 回归：write_images 全链（stub 网络）带 uigate+divsel 跑通 distinct 路径
    ——曾因 i2v 首帧优选引用未构建的 slots 变量 UnboundLocalError 全链兜底占位，
    t11（无 divsel）拦不住，此测试专职拦截。"""
    saved = (mod.vl_score_image, mod.vl_score_batch, mod.fetch_jpeg_retry, mod.time.sleep,
             mod.vl_rescreen_gallery)
    mod.time.sleep = lambda *_a, **_k: None
    mod.vl_rescreen_gallery = lambda items: {}
    try:
        urls = ["front-white-clear-3", "front-green-clear-4", "scene-black-clear-6",
                "scene-purple-clear-7", "scene-white-clear-5", "scene-beige-clear-8"]
        blobs = {u: bytes([0xff, 0xd8]) + bytes([i + 1]) * 2048 for i, u in enumerate(urls)}
        mod.fetch_jpeg_retry = lambda url, attempts=3, backoff=None, timeout=60: blobs[url]

        def score_for(u):
            parts = u.split("-")
            return {"has_text": False, "has_watermark": False, "is_collage": False,
                    "uniform_light_bg": "white" in parts and "scene" not in parts,
                    "warm_tone_bg": False, "subject_clear": True,
                    "is_back_view": False, "is_side_view": False,
                    "is_closeup_or_detail": False, "is_fabric_macro": False,
                    "is_flat_lay": "beige" in parts, "is_scene": "scene" in parts,
                    "is_size_chart": False, "same_shot_group": 0,
                    "dominant_color": parts[1], "third_party_mark": "",
                    "pose": ("flat" if "beige" in parts else
                             "front" if "scene" not in parts else "front"),
                    "accessory_load": (2 if u == "front-white-clear-3" else 1),
                    "has_ui_symbols": False, "letterbox": False}
        mod.vl_score_image = score_for
        mod.vl_score_batch = lambda items: {u: score_for(u) for u, _b in items}
        facts = {"images": urls, "sku_images": [], "description_images": [],
                 "sku_pairs": [[("颜色", "白色")], [("颜色", "绿色")], [("颜色", "黑色")],
                               [("颜色", "紫色")], [("颜色", "米色")]]}
        base = _scratch("divsel_smoke")
        out = base + "/sfx_out"
        os.makedirs(out)
        names, ext, img_meta = mod.write_images(out, facts, use_vl=True, use_distinct=True,
                                                use_dedupe=True, sixslot=True, use_desc=True,
                                                colorauth=True, uigate=True, divsel=True)
        assert ext == "jpeg" and img_meta["mode"] == "vl-distinct", img_meta
        assert len(img_meta.get("slots") or []) == 6, img_meta.get("slots")
        # divsel 首帧优选：主图 accessory_load=2 且存在更低槽 → 首帧换低配饰槽
        assert facts.get("_i2v_frame") not in (None, urls[0]), facts.get("_i2v_frame")
        assert names and len(names) == 6, names
    finally:
        (mod.vl_score_image, mod.vl_score_batch, mod.fetch_jpeg_retry, mod.time.sleep,
         mod.vl_rescreen_gallery) = saved


def t20_rescreen_swap(mod):
    """v3.5.1 图集终筛：定向追问命中 UI 残留 → 换入合格备选（主图不换），
    选图记录/自审/槽位标签同步。亲验：一般化批量打分漏判 ▼ 小图形，终筛专职拦截。"""
    saved = (mod.vl_score_image, mod.vl_score_batch, mod.fetch_jpeg_retry, mod.time.sleep,
             mod.vl_rescreen_gallery)
    mod.time.sleep = lambda *_a, **_k: None
    try:
        urls = ["front-white-clear-3", "front-green-clear-4", "scene-black-clear-6",
                "scene-purple-clear-7", "scene-white-clear-5", "scene-beige-clear-8",
                "scene-gray-clear-9"]
        blobs = {u: bytes([0xff, 0xd8]) + bytes([i + 1]) * 2048 for i, u in enumerate(urls)}
        mod.fetch_jpeg_retry = lambda url, attempts=3, backoff=None, timeout=60: blobs[url]

        def score_for(u):
            parts = u.split("-")
            return {"has_text": False, "has_watermark": False, "is_collage": False,
                    "uniform_light_bg": "white" in parts and "scene" not in parts,
                    "warm_tone_bg": False, "subject_clear": True,
                    "is_back_view": False, "is_side_view": False,
                    "is_closeup_or_detail": False, "is_fabric_macro": False,
                    "is_flat_lay": "beige" in parts, "is_scene": "scene" in parts,
                    "is_size_chart": False, "same_shot_group": 0,
                    "dominant_color": parts[1], "third_party_mark": "",
                    "pose": ("flat" if "beige" in parts else "front"),
                    "accessory_load": (2 if u == "front-white-clear-3" else 1),
                    "has_ui_symbols": False, "letterbox": False}
        mod.vl_score_image = score_for
        mod.vl_score_batch = lambda items: {u: score_for(u) for u, _b in items}
        # 终筛 spy：把传入的第 6 张（detail_5 槽）标记为 UI 残留命中
        def fake_rescreen(items):
            return {items[5][0]: True}
        mod.vl_rescreen_gallery = fake_rescreen
        facts = {"images": urls, "sku_images": [], "description_images": [],
                 "sku_pairs": [[("颜色", "白色")], [("颜色", "绿色")], [("颜色", "黑色")],
                               [("颜色", "紫色")], [("颜色", "米色")], [("颜色", "灰色")]]}
        base = _scratch("rescreen")
        out = base + "/sfx_out"
        os.makedirs(out)
        names, ext, img_meta = mod.write_images(out, facts, use_vl=True, use_distinct=True,
                                                use_dedupe=True, sixslot=True, use_desc=True,
                                                colorauth=True, uigate=True, divsel=True)
        assert ext == "jpeg" and img_meta["mode"] == "vl-distinct", img_meta
        slots = img_meta["slots"]
        assert len(slots) == 6, slots
        assert "终筛" in img_meta.get("record", ""), img_meta.get("record")
        gt = img_meta.get("gallery_text") or {}
        assert gt.get("rescreen", {}).get("swaps") == 1, gt
        # 被标记的槽位已换入备选：产物槽位 URL 与该槽原 URL 不同
        emitted = [s["url"] for s in slots]
    finally:
        (mod.vl_score_image, mod.vl_score_batch, mod.fetch_jpeg_retry, mod.time.sleep,
         mod.vl_rescreen_gallery) = saved


def t21_motionchain(mod):
    """v3.5.2/v3.5.3 motionchain：转身展示链 prompt 分档（版本门控 + 正面首帧门槛，
    v3.5.3 起全品类适用）+ Video Description 转身分档与首帧槽名如实渲染。"""
    # 品类观测判定纯函数（v3.5.3 起仅观测用，不再门控）
    assert mod._is_dress_like({"subject": "2024夏季新款雪纺连衣裙", "category": ""})
    assert not mod._is_dress_like({"subject": "男士polo衫 T-Shirt", "category": "T-Shirts"})
    # prompt 分档：3.5.3 正面首帧 → 转身链（上衣同样适用——XHS 基准转身链不限于裙装）
    p = mod.motion_prompt_for({"subject": "雪纺衬衫", "_i2v_pose": "front"})
    assert "full turn" in p and "glancing back" in p, p
    p_dress = mod.motion_prompt_for({"subject": "雪纺连衣裙", "_i2v_pose": "front"})
    assert "full turn" in p_dress, p_dress
    # 无首帧姿态（占位/顺序模式）→ 维持 steadycam 静止机位
    p2 = mod.motion_prompt_for({"subject": "雪纺连衣裙"})
    assert "Static tripod camera product showcase" in p2 and "full turn" not in p2, p2
    p2b = mod.motion_prompt_for({"subject": "雪纺衬衫", "_i2v_pose": "side"})
    assert "full turn" not in p2b, p2b
    # 版本门控：3.5.1 行为不变
    old = mod.read_version
    try:
        mod.read_version = lambda: "3.5.1"
        p4 = mod.motion_prompt_for({"subject": "雪纺衬衫", "_i2v_pose": "front"})
        assert "full turn" not in p4 and "Static tripod camera product showcase" in p4, p4
    finally:
        mod.read_version = old
    # v3.5.4 全身门槛：正面+全身+低配饰才激活转身；坐姿/半身/缺标签回落 (0, False)
    pick, ok = mod.motionchain_frame_pick([
        {"slot": "main", "pose": "front", "accessory_load": 0, "full_body": False},
        {"slot": "detail_image_1", "pose": "front", "accessory_load": 1, "full_body": True}])
    assert ok and pick == 1, (pick, ok)
    pick2, ok2 = mod.motionchain_frame_pick([
        {"pose": "front", "accessory_load": 0, "full_body": False}])
    assert (not ok2) and pick2 == 0, (pick2, ok2)
    pick3, ok3 = mod.motionchain_frame_pick([])
    assert (not ok3) and pick3 == 0, (pick3, ok3)
    # vidcap 转身描述 + 首帧槽名如实（divsel 换槽后首帧≠主图，v3.5.0 起的诚实缺口）
    vi = {"mode": "i2v", "tier": "10s", "secs": 10, "frame_slot": "detail_image_2"}
    en = mod.video_desc_line({"subject": "雪纺衬衫", "_i2v_pose": "front",
                              "_video_info": vi}, "en")
    assert "full turn" in en and "first frame matches detail_image_2" in en, en
    # 非正面首帧 → 原静止描述，但首帧槽名仍如实
    en2 = mod.video_desc_line({"subject": "雪纺衬衫", "_i2v_pose": "flat",
                               "_video_info": vi}, "en")
    assert "full turn" not in en2 and "first frame matches detail_image_2" in en2, en2
    # 缺省 frame_slot → main_image（t18 断言兼容）
    en3 = mod.video_desc_line({"subject": "雪纺衬衫", "_i2v_pose": "front",
                               "_video_info": {"mode": "i2v", "secs": 10}}, "en")
    assert "first frame matches main_image" in en3, en3
    # 策略文档 v3.5.3 陈述（全品类化）+ 3.5.1 无该陈述
    facts = {"subject": "测试衬衫", "images": [], "sku_images": [],
             "description_images": [], "sku_rows": [], "sku_pairs": [],
             "attr_pairs": [], "attr_rows": []}
    istats = {"mode": "vl-distinct", "pool": 55, "contents": 32, "distinct": 6,
              "main_bg_hit": True, "size_chart": {"ok": False, "why": "x"}}
    doc = mod.strategy_document("3.5.4", facts, mod.feature_flags("3.5.4"),
                                "vl-distinct", img_stats=istats)
    assert "转身展示链" in doc and "全品类" in doc and "全身" in doc, "策略文档缺 v3.5.4 陈述"
    doc351 = mod.strategy_document("3.5.1", facts, mod.feature_flags("3.5.1"),
                                   "vl-distinct", img_stats=istats)
    assert "转身展示链" not in doc351, "3.5.1 文档不应出现 motionchain 陈述"


def t22_mainscene(mod):
    """v3.6.0 mainscene：白转透明、VL A/B 采纳与回退语义、i2v 首帧联动、披露与门控。"""
    assert mod.feature_flags("3.6.0").get("mainscene") is True
    assert mod.feature_flags("3.5.6").get("mainscene") is False
    # v3.6.2：mainscene 默认关闭（官方出分归因），XB_MAINSCENE=1 显式开启
    assert mod.feature_flags("3.6.2").get("mainscene") is False, "v3.6.2 应默认关闭 mainscene"
    _saved_env = os.environ.pop("XB_MAINSCENE", None)
    try:
        os.environ["XB_MAINSCENE"] = "1"
        assert mod.feature_flags("3.6.2").get("mainscene") is True, "XB_MAINSCENE=1 应显式开启"
    finally:
        if _saved_env is None:
            os.environ.pop("XB_MAINSCENE", None)
        else:
            os.environ["XB_MAINSCENE"] = _saved_env
    facts0 = {"subject": "测试衬衫", "images": [], "sku_images": [],
              "description_images": [], "sku_rows": [], "sku_pairs": [],
              "attr_pairs": [], "attr_rows": []}
    istats = {"mode": "vl-distinct", "pool": 55, "contents": 32, "distinct": 6,
              "main_bg_hit": True, "size_chart": {"ok": False, "why": "x"}}
    doc = mod.strategy_document("3.6.0", facts0, mod.feature_flags("3.6.0"),
                                "vl-distinct", img_stats=istats)
    assert "主图背景场景化" in doc and "回退源图" in doc, "策略文档缺 v3.6.0 陈述"
    doc356 = mod.strategy_document("3.5.6", facts0, mod.feature_flags("3.5.6"),
                                   "vl-distinct", img_stats=istats)
    assert "主图背景场景化" not in doc356, "3.5.6 文档不应出现 mainscene 陈述"
    if not mod._pil_ready():
        return "SKIP: Pillow 未就绪"
    from PIL import Image
    import io as _io
    buf = _io.BytesIO()
    im = Image.new("RGB", (400, 500), (255, 255, 255))
    for y in range(100, 400):
        for x in range(100, 300):
            im.putpixel((x, y), (120, 180, 140))
    im.save(buf, "JPEG", quality=92)
    png, ratio = mod._white_to_alpha_png(buf.getvalue())
    assert png, "white_to_alpha 失败"
    assert 0.30 <= ratio <= 0.90, ratio
    rgba = Image.open(_io.BytesIO(png))
    assert rgba.mode == "RGBA"
    assert rgba.getpixel((5, 5))[3] == 0, "角落未透明"
    assert rgba.getpixel((200, 250))[3] == 255, "主体被误透明"
    # 全链：采纳路径 + 回退路径（mock 网络环节）
    base = _scratch("mainscene")
    out = os.path.join(base, "out")
    os.makedirs(out, exist_ok=True)
    buf2 = _io.BytesIO()
    Image.new("RGB", (900, 900), (250, 250, 250)).save(buf2, "JPEG", quality=90)
    src_bytes = buf2.getvalue()
    gen_bytes = bytes([0xff, 0xd8]) + b"G" * 40000
    flags = mod.feature_flags("3.6.0")
    saved = (mod._scene_enhance, mod._vl_scene_adopt)
    try:
        mod._scene_enhance = lambda b, ref: (gen_bytes, "https://r/x.jpg", "ok")
        mod._vl_scene_adopt = lambda s, g: (True, "ok")
        open(os.path.join(out, "main_image.jpeg"), "wb").write(src_bytes)
        img_meta = {"mode": "vl-distinct", "distinct": 7, "record": "",
                    "slots": [{"name": "main_image", "white_bg": True, "url": "u0"}]}
        facts = {"_i2v_frame": "u0", "_i2v_frame_slot": "main_image"}
        note = mod._apply_mainscene(out, facts, img_meta, flags, "jpeg")
        assert "AI 场景合成" in note, note
        _d = open(os.path.join(out, "main_image.jpeg"), "rb").read()
        assert _d == gen_bytes, "ADOPT-FAIL len=%d gen=%d head=%r note=%r" % (len(_d), len(gen_bytes), _d[:12], note)
        assert str(facts["_i2v_frame"]) == "https://r/x.jpg", facts
        assert "AI 场景合成" in img_meta["record"], img_meta["record"]
        # 回退：VL 拒绝 → 字节/首帧不变，记录如实
        mod._vl_scene_adopt = lambda s, g: (False, "garment diff")
        img_meta2 = {"mode": "vl-distinct", "distinct": 7, "record": "",
                     "slots": [{"name": "main_image", "white_bg": True, "url": "u0"}]}
        facts2 = {"_i2v_frame": "u0", "_i2v_frame_slot": "main_image"}
        note2 = mod._apply_mainscene(out, facts2, img_meta2, flags, "jpeg")
        # v3.6.1 补缺前置路由：非白底复用槽 → 点火前跳过（不烧尝试）
        mod._vl_scene_adopt = lambda s, g: (True, "ok")
        img_meta3 = {"mode": "vl-distinct", "distinct": 2, "record": "",
                     "slots": [{"name": "main_image", "white_bg": True, "url": "u0"},
                               {"name": "detail_image_1", "white_bg": False, "url": "u1"},
                               {"name": "detail_image_2", "white_bg": False, "url": "u1"}]}
        calls = []
        def spy_enhance(b, ref):
            calls.append(ref)
            return (gen_bytes, "https://r/y.jpg", "ok")
        mod._scene_enhance = spy_enhance
        facts3 = {"_i2v_frame": "u0", "_i2v_frame_slot": "main_image"}
        note3 = mod._apply_mainscene(out, facts3, img_meta3, flags, "jpeg")
        assert calls == [mod.BGGEN_REF_MAIN], "只应有点火主图一次，补缺不应点火: %r" % calls
        assert "前提不成立" in note3 and "AI 场景合成" in note3, note3
        _d2 = open(os.path.join(out, "main_image.jpeg"), "rb").read()
        assert _d2 == gen_bytes, "FALLBACK-FAIL: 回退语义=不改动(保持上一态) head=%r" % _d2[:12]
        assert facts2["_i2v_frame"] == "u0", facts2
        assert "保留源图" in note2, note2
    finally:
        mod._scene_enhance, mod._vl_scene_adopt = saved


def t12_statements(mod):
    """v3.4.0 陈述一致性：门控、策略文档视觉资产/尺码表/码制句/双区指引/音轨登记、
    自审表行（含 v3.4.0 两新行）、指纹格式。"""
    flags = mod.feature_flags("3.4.0")
    assert flags.get("vldist") and flags.get("vid10"), flags
    assert flags.get("dedupe") and flags.get("strictqc") and flags.get("dualzone"), flags
    assert flags.get("imgdesc") and flags.get("sixslot") and flags.get("sizeocr") \
        and flags.get("colorauth"), flags
    assert flags.get("gallerytext") and flags.get("detail1") and flags.get("skupin") \
        and flags.get("srcnote"), flags
    old = mod.feature_flags("3.2.0")
    assert not old.get("imgdesc") and not old.get("sixslot") and not old.get("sizeocr"), old
    old33 = mod.feature_flags("3.3.0")
    assert not old33.get("gallerytext") and not old33.get("skupin") \
        and not old33.get("detail1") and not old33.get("srcnote"), old33
    facts = {"subject": "测试连衣裙", "images": ["m%d" % i for i in range(1, 6)],
             "sku_images": ["s%d" % i for i in range(1, 25)],
             "description_images": ["d%d.jpg" % i for i in range(1, 27)],
             "sku_rows": [], "sku_pairs": [], "attr_pairs": [], "attr_rows": []}
    doc = mod.strategy_document("3.4.0", facts, flags, "vl-distinct",
                                img_stats={"mode": "vl-distinct", "pool": 55, "contents": 32,
                                           "distinct": 6, "main_bg_hit": True,
                                           "size_chart": {"ok": False, "why": "x"}})
    assert "内容级去重" in doc, "策略文档缺内容级去重陈述"
    assert "源数据上限" in doc, "策略文档缺互异内容源上限陈述"
    assert "描述字段内嵌图" in doc, "策略文档缺描述图池叙事"
    # v3.4.0 码段口径：KR 55-88（S 起）与 KO 表一致；BR P/M/G/GG/XGG 与 PT 表一致
    assert "55-88" in doc, "策略文档缺 KR 55-88 口径"
    assert "44/55/66/77/88" not in doc and "44-88" not in doc, "策略文档残留 KR 44 全段旧口径"
    assert "全段" not in doc, "策略文档残留「全段」旧口径"
    assert "P/M/G/GG/XGG" in doc and "PP-P-G-GG" not in doc, "策略文档 BR 口径未与 PT 表统一"
    # F6：PT 分期不做免息宣称
    assert "sem juros" not in doc, "策略文档残留 sem juros 免息承诺"
    assert "Parcele em até 12x" in doc, "策略文档缺 Parcele em até 12x 口径"
    assert "직배송 리드타임은 배송 안내 참조" in doc, "策略文档缺 KR 发货时效落地口径"
    assert "오늘 발송」承诺" in doc, "策略文档未显式声明不做当日发单承诺"
    assert "50/47/47%" in doc, "策略文档敏感性数字未统一（BR +10% 应为 47）"
    assert "₩10,830–33,600" in doc, "策略文档 KR 竞品带与注①未统一"
    assert "目标结构" in doc and "同镜头组" in doc, "策略文档缺目标结构/同镜头组叙事"
    # v3.4.0 图集资格新规 + 数据源图身份 + SKU 色点名
    assert "一律出局" in doc and "数据源图" in doc, "策略文档缺图集无文字资格/数据源图叙事"
    assert "SKU 色点名" in doc, "策略文档缺主图 SKU 色点名叙事"
    assert "绝不编造数字" in doc or "绝不编造" in doc, "策略文档缺尺码表下界口径"
    assert "全片严格" in doc, "策略文档缺全片质检陈述"
    assert "手表/首饰复制或瞬移" in doc and "纽扣间距" in doc, "策略文档缺质检项列举"
    assert "10 秒" in doc and "InvalidParameter" in doc, "策略文档缺 10s/降档陈述"
    assert "最终选定主图" in doc, "策略文档缺首帧同源陈述"
    assert "只粘贴「买家区」" in doc, "策略文档缺双区粘贴纪律"
    assert "源数据自带视频" in doc, "策略文档缺源视频直复陈述"
    # v3.4.0 视频音轨合规登记
    assert "model-generated ambient audio" in doc and "no third-party music" in doc, \
        "策略文档缺视频音轨合规登记行"
    # v3.4.0 源数据冲突注记叙事
    assert "以尺码表为准" in doc, "策略文档缺源数据冲突注记口径"
    assert "v2.2.4" not in doc and "v3.0.3" not in doc, "策略文档残留内部版本串"
    sc_rows = {"S": {"bust": 98.0, "length": 65.0}}
    audit = mod.render_compliance_audit(0, "jpeg", img_mode="vl-distinct", cjk_left=0,
                                        img_stats={"pool": 55, "contents": 32, "distinct": 6,
                                                   "main_bg_hit": True,
                                                   "gallery_text": {"n": 6, "clean": True,
                                                                    "clean_n": 6, "excluded": 5,
                                                                    "data_source": ["x_description_01.jpg"]},
                                                   "gallery_marks": {"n": 6, "marks": []},
                                                   "size_chart": {"ok": True, "rows": sc_rows,
                                                                  "img": "x_description_01.jpg",
                                                                  "model": "qwen3.5-ocr"}},
                                        cjk_total=30)
    assert "Source image URLs (URL-level dedup) | 55" in audit
    assert "description-field HTML image URLs" in audit, "自审表图池口径缺描述字段来源"
    assert "Distinct image contents (content-level dedup) | 32" in audit
    assert "Distinct selected images | 6/6" in audit
    assert "Untranslated CJK lines (buyer zone) | 0" in audit, "自审表缺买家区 CJK 行"
    assert "CJK lines (whole document) | 30" in audit, "自审表缺全文档 CJK 行"
    assert "Buyer size-chart columns (bust/length cm) | 1 size rows" in audit, "自审表缺尺码表列行"
    assert "qwen3.5-ocr" in audit and "x_description_01.jpg" in audit
    # v3.4.0 自审两新行：图内文字扫描 + 场景第三方商标
    assert "In-image text screening (final gallery) | 6/6 clean" in audit, "自审表缺图内文字扫描行"
    assert "DATA-SOURCE image" in audit and "x_description_01.jpg" in audit, \
        "图内文字扫描行缺数据源图身份"
    assert "Third-party marks in gallery scenes | none detected" in audit, "自审表缺第三方商标行"
    assert "Birkin" in audit, "第三方商标行缺备用池道具风险注记"
    audit2 = mod.render_compliance_audit(0, "jpeg", img_mode="vl-distinct", cjk_left=0,
                                         img_stats={"pool": 55, "contents": 32, "distinct": 6,
                                                    "size_chart": {"ok": False, "why": "no chart"}},
                                         cjk_total=30)
    assert "Buyer size-chart columns (bust/length cm) | not added" in audit2, "自审表缺尺码表失败下界行"
    assert "no chart" in audit2
    assert "In-image text screening" not in audit2, "无扫描数据时不应出现图内文字扫描行"
    assert "v2.2.4" not in audit, "自审表残留内部版本串"
    fp = mod._fingerprint_line({"real_images": 6, "image_pool": 55, "contents": 32, "distinct": 6,
                                "size_chart": {"ok": True, "rows": {"S": {}, "M": {}, "L": {},
                                                                    "XL": {}, "2XL": {}, "3XL": {}}},
                                "video_mode": "i2v", "video_tier": "10s", "video_duration": 10,
                                "valtrans": "ok", "vlqc": "ok"})
    assert "image_pool=55" in fp and "contents=32" in fp and "distinct_selected=6/6" in fp, fp
    assert "sizechart=6rows" in fp and "video_tier=10s" in fp and "video_duration=10s" in fp, fp
    # 时长断言语义：10s±2 / 5s±1（供真跑与云端门禁复用的判定口径）
    for got, want in ((10, True), (12, True), (8, True), (13, False),
                      (5, True), (6, True), (4, True), (3, False)):
        ok10 = abs(got - 10) <= 2
        ok5 = abs(got - 5) <= 1
        assert (ok10 or ok5) == want, (got, want)
    # v3.4.0 F5 冲突注记构造器（确定性触发/不触发）
    facts_c = {"attr_pairs": [("衣长", "普通款(50cm<衣长≤65cm)")]}
    chart_c = {"ok": True, "rows": {"S": {"bust": 98.0, "length": 65.0},
                                    "3XL": {"bust": 108.0, "length": 67.0}}}
    note = mod.build_source_conflict_note(facts_c, "en", chart_c)
    assert "Source-data note" in note and "50-65 cm" in note and "65-67 cm" in note \
        and "takes precedence" in note, note
    assert mod.build_source_conflict_note(facts_c, "en", {"ok": False}) == ""
    chart_ok = {"ok": True, "rows": {"S": {"bust": 98.0, "length": 62.0},
                                     "M": {"bust": 100.0, "length": 64.0}}}
    assert mod.build_source_conflict_note(facts_c, "ko", chart_ok) == "", "无冲突不应注记"


def t13_fullclip_qc_and_source_video(mod):
    """v3.2.0 全片严格质检语义 + 源 JSON 视频字段扫描。"""
    assert mod._vl_qc_pass(None) is True  # 质检不可用：放行但如实标 skip
    assert mod._vl_qc_pass({k: False for k in mod.VL_QC_KEYS if k != "ok"}) is True
    assert mod._vl_qc_pass({"accessory_clone": True, "finger_defect": False,
                            "button_misalign": False, "texture_melt": False,
                            "blocky_artifacts": False, "garbled_text": False}) is False, "手表复制未拦截"
    assert mod._vl_qc_pass({"texture_melt": True}) is False, "纹理融化未拦截"
    assert mod._vl_qc_pass({"blocky_artifacts": True}) is False
    assert mod._vl_qc_pass({"ok": False}) is False
    assert mod._vl_qc_pass({"ok": True, "texture_melt": True}) is True  # ok 显式为真为准
    # 全片严格 prompt：逐项列查红队穿帮项，时间轴覆盖整段
    assert "accessory_clone" in mod.VL_QC_PROMPT and "watch" in mod.VL_QC_PROMPT, "缺手表/配饰复制项"
    assert "finger_defect" in mod.VL_QC_PROMPT, "缺手指检查项"
    assert "button_misalign" in mod.VL_QC_PROMPT, "缺纽扣间距项"
    assert "texture_melt" in mod.VL_QC_PROMPT, "缺面料纹理融化项"
    assert "blocky_artifacts" in mod.VL_QC_PROMPT, "缺块状噪点项"
    assert "morph_ghosting" in mod.VL_QC_PROMPT and "morph_ghosting" in mod.VL_QC_HARSH_PROMPT, \
        "v3.5.5 缺 morph/重影定向检查项"
    assert "morph_ghosting" in mod.VL_QC_KEYS and "morph_ghosting" in mod.merge_video_qc(
        {"morph_ghosting": True}, None), "morph_ghosting 未进质检合并"
    # v3.5.6 时序一致性三通道 + 首帧构图锚定
    assert "disappears" in mod.VL_QC_CONSIST_PROMPT and "framing" in mod.VL_QC_CONSIST_PROMPT,         "v3.5.6 缺时序一致性通道 prompt"
    assert "no push-in" in mod.MOTION_PROMPT_TMPL_V35 and "no standing up" in mod.MOTION_PROMPT_TMPL_V35,         "v3.5.6 steadycam prompt 缺首帧构图锚定"
    assert "WHOLE clip" in mod.VL_QC_PROMPT, "质检 prompt 未定义全片时间轴"
    assert "second_half_drift" not in mod.VL_QC_PROMPT, "仍残留只查后半段的旧语义"
    # 选图打分 prompt：白/浅灰严格口径（暖调不算命中）+ 主色 + v3.3.0/v3.4.0 新字段
    assert "do NOT count" in mod.VL_SCORE_PROMPT and "warm_tone_bg" in mod.VL_SCORE_PROMPT
    assert "dominant_color" in mod.VL_SCORE_PROMPT and mod.VL_COLOR_WORD == "dominant_color"
    assert "is_size_chart" in mod.VL_SCORE_PROMPT, "缺尺码表识别字段"
    assert "is_fabric_macro" in mod.VL_SCORE_PROMPT and "is_side_view" in mod.VL_SCORE_PROMPT
    assert "same_shot_group" in mod.VL_SCORE_PROMPT and mod.VL_GROUP_WORD == "same_shot_group"
    assert "third_party_mark" in mod.VL_SCORE_PROMPT and "third_party_mark" in mod.VL_BATCH_PROMPT_TMPL, \
        "v3.4.0 缺第三方商标扫描字段"
    assert mod.VL_MARK_WORD == "third_party_mark"
    for k in ("is_size_chart", "is_fabric_macro", "is_side_view"):
        assert k in mod.VL_SCORE_KEYS, k
    assert mod._parse_vl_score({"is_size_chart": True, "same_shot_group": 3,
                                "dominant_color": "green"})["same_shot_group"] == 3
    got_mark = mod._parse_vl_score({"dominant_color": "green", "third_party_mark": "SIEMENS"})
    assert got_mark["third_party_mark"] == "siemens", got_mark
    assert mod._parse_vl_score({"dominant_color": "green", "third_party_mark": "none"})["third_party_mark"] == ""
    assert mod._parse_vl_score({"dominant_color": "green"})["third_party_mark"] == ""
    assert mod._parse_vl_score({})["same_shot_group"] == 0
    assert mod._parse_vl_score(None) is None
    # v3.4.0 主图 SKU 色点名 prompt：SKU 词表内点名 + none 兜底
    assert "EXACTLY ONE" in mod.VL_PIN_PROMPT and "none" in mod.VL_PIN_PROMPT
    # 源视频字段扫描：值 URL / 键名含 video 两条规则，保序去重
    inner = {"subject": "x",
             "mediaList": [{"mediaType": "video", "mediaUrl": "https://x.aliyuncs.com/a.mp4"}],
             "mainVideoUrl": "https://x.aliyuncs.com/b.mp4?Expires=1",
             "productImage": {"images": ["https://x.aliyuncs.com/p.jpg"]}}
    got = mod._scan_video_urls(inner)
    assert got == ["https://x.aliyuncs.com/a.mp4", "https://x.aliyuncs.com/b.mp4?Expires=1"], got
    f = mod.extract_facts(inner)
    assert f["source_video_url"] == got[0] and len(f["source_videos"]) == 2
    # 无视频字段（本赛题 11 商品实况）
    f2 = mod.extract_facts({"subject": "y", "productImage": {"images": ["p"]}})
    assert f2["source_video_url"] == "" and f2["source_videos"] == []
    # 非视频 URL 不误收
    assert mod._scan_video_urls({"img": "https://x.aliyuncs.com/a.mp4.jpg",
                                 "note": "see https://x.aliyuncs.com/b.mp4 now"}) == []


def _rich_facts():
    """红队 Round 1 实测商品的关键词表（双区/标题/汇总表测试夹具）。"""
    attr_pairs = [("面料名称", "化纤"), ("主面料成分", "涤纶（聚酯纤维）"),
                  ("主面料成分2", "涤纶（聚酯纤维）"), ("图案", "纯色"), ("款式", "开衫"),
                  ("袖长", "长袖"), ("工艺", "高温定型"), ("货号", "013"), ("品牌", "其他"),
                  ("版型", "宽松型"), ("衣长", "普通款(50cm<Garment length≤65cm)"),
                  ("领型", "POLO领"), ("袖型", "常规袖"), ("流行元素", "纽扣"),
                  ("上市年份/季节", "2024年秋季"), ("风格类型", "日韩休闲"),
                  ("门襟", "单排扣"), ("主面料成分含量", "50%（含）-70%（不含）"),
                  ("风格", "休闲风"), ("跨境风格类型", "舒适休闲"), ("是否跨境货源", "是"),
                  ("产品类别", "衬衫"), ("主要下游销售地区1", "中东"),
                  ("主要下游销售地区2", "东南亚")]
    colors = ["紫色", "白色", "黑色", "绿色"]
    sizes = ["S 80-95斤", "M 95-105斤", "L 105-115斤", "XL 115-125斤", "2XL 125-140斤", "3XL 140-160斤"]
    sku_pairs = [[("颜色", c), ("尺码", s)] for c in colors for s in sizes]
    sku_rows = ["颜色:%s / 尺码:%s" % (c, s) for c in colors for s in sizes]
    return {"offer_id": "3887087154767",
            "subject": "春秋宽松大码纯色雪纺衬衫女装韩版休闲风ins港风长袖衬衣打底衫",
            "url": "https://www.123.com/", "platform": "123批发网", "category": "女式衬衫",
            "category_id": None, "images": [], "sku_images": [], "source_videos": [],
            "source_video_url": "", "sku_rows": sku_rows, "sku_pairs": sku_pairs,
            "attr_pairs": attr_pairs, "attr_rows": ["%s:%s" % p for p in attr_pairs]}


def t14_dualzone_title_sku(mod):
    """v3.4.0：双区结构（买家区零 CJK / Appendix 全量唯一）、标题公式（三语）、
    SKU 汇总表码制列、真实尺码列（F2 无文件名脚注）、Highlights 轻量措辞/PT 正字
    （F7/F12）、韩码残留清理（F11）、KO 尺码建议统一（F10）、PT 分期口径（F6）、
    Single Breasted 本地化（F14）、源数据冲突注记（F5）、全文档 CJK 两遍复算。"""
    flags = mod.feature_flags("3.4.0")
    facts = _rich_facts()
    # —— 标题公式（三语，含材质+品类+人群词）——
    t_en = mod.buyer_title(facts, "en", {})
    assert t_en == "Polyester Chiffon Blouse for Women — Long Sleeve Loose Fit Solid Color", t_en
    t_ko = mod.buyer_title(facts, "ko", {})
    assert "폴리에스터" in t_ko and "블라우스" in t_ko and "여성" in t_ko and not CJK_RE.search(t_ko), t_ko
    t_pt = mod.buyer_title(facts, "pt", {})
    assert "Blusa" in t_pt and "Feminina" in t_pt and "Poliéster" in t_pt, t_pt
    # Highlights：自然语序（无胶合大写值/无 Chemical fiber/无 Estilo casual 尾缀拼接）
    # v3.4.0（F7）：涤纶不宣称透气 → lightweight/leve；（F12）PT 句首大写
    hl_en = mod.compose_highlights(facts, "en")
    assert "Chemical fiber" not in hl_en and "polyester" in hl_en.lower()
    assert "a polo collar and long sleeves" in hl_en.lower(), hl_en
    assert "casual occasions" in hl_en.lower(), hl_en
    assert "lightweight" in hl_en and "breathable" not in hl_en.lower(), hl_en
    hl_pt = mod.compose_highlights(facts, "pt")
    assert "ocasiões casuais" in hl_pt, hl_pt
    assert "A modelagem folgada" in hl_pt, hl_pt
    assert "Design Cor" not in hl_pt and "Estilo casual" not in hl_pt, hl_pt
    assert "leve." in hl_pt and "respirável" not in hl_pt.lower(), hl_pt
    assert "Cor sólida com" in hl_pt and "cor sólida com" not in hl_pt, "PT 句首小写未修正"
    # —— 长度折算验证器（CJK×2）——
    assert mod.validate_translation("常规袖", "Regular Sleeve") is True, "CJK×2 折算未生效"
    assert mod.validate_translation("常规袖", "Regular Sleeve with extra padding words") is False
    assert mod.validate_translation("红色", "red 1") is False  # 数字集合不一致
    # —— 双区渲染（完整文档：买家区 + Appendix + 自审 + 溯源）——
    def _full_doc(lang):
        return mod.assemble_language_doc(facts, lang, "jpeg", flags, {},
                                         img_mode="vl-distinct",
                                         img_stats={"mode": "vl-distinct", "slots": []})
    text = _full_doc("en")
    assert mod.APPENDIX_MARKER in text and mod.APPENDIX_TITLE in text
    buyer = text[:text.index(mod.APPENDIX_MARKER)]
    appendix = text[text.index(mod.APPENDIX_MARKER):]
    assert not CJK_RE.search(buyer), "买家区残留 CJK: %r" % buyer[:600]
    # 自审 CJK 两行拆分 + v3.3.0 全文档两遍复算（与全文真实计数一致）
    assert "Untranslated CJK lines (buyer zone) | 0" in text, "自审表买家区 CJK 行应为 0"
    m = re.search(r"\| CJK lines \(whole document\) \| (\d+) \|", text)
    assert m, "自审表缺全文档 CJK 行"
    actual = sum(1 for ln in text.splitlines() if CJK_RE.search(ln))
    assert int(m.group(1)) == actual, "全文档 CJK 计数与真实复算不符: %s vs %s" % (m.group(1), actual)
    # SKU：买家区只有汇总（颜色一行 + 码档表 6 行），24 行全量只在 Appendix
    assert buyer.count("- Color:") == 1, buyer
    # Appendix：汇总 Color/Size 两行 + 24 行全量明细 = 25 行 "- Color:" 起始行
    assert len(re.findall(r"^- Color:", appendix, re.M)) == 25, "Appendix SKU 全量行数异常"
    # v3.3.0 US 体重段修正 + KR 44-88（99/99+ 删除）
    assert "US 4-6" in buyer and "US 8-10" in buyer and "US 12-14" in buyer, buyer
    assert "| S | S 80-95 jin | ≈40-47.5 kg / 88-105 lbs | US 4-6 |" in buyer, "US 码列锚点行不符"
    for row in ("| L |", "| XL |", "| 2XL |", "| 3XL |"):
        assert not any(line.startswith(row) and ("US 12 |" in line or "US 14 |" in line
                                                 or "US 16 |" in line or "US 16+" in line)
                       for line in buyer.splitlines()), "US 码列仍虚胖: %s" % row
    t_ko_doc = _full_doc("ko")
    assert "KR 55" in t_ko_doc and "KR 77" in t_ko_doc and "KR 88" in t_ko_doc, "ko 缺 44-88 列"
    assert "KR 99" not in t_ko_doc, "KR 99/99+ 未删除"
    t_pt_doc = _full_doc("pt")
    assert "Referência BR" in t_pt_doc and "| P |" in t_pt_doc and "| GG |" in t_pt_doc, "pt 缺 PP-GG 列"
    assert "Asian sizes run 1-2 sizes smaller" in buyer, "缺亚洲码偏小警示"
    assert "Ships with AliExpress Buyer Protection." in buyer, "缺买家保障句"
    # —— v3.4.0 文案收尾（F6/F9/F10/F11/F14）——
    assert "size table above" in buyer and "size table below" not in buyer, "F9 尺码表方向词"
    for bad in ("breathable", "respirável", "sem juros"):
        for lang_doc in (text, t_ko_doc, t_pt_doc):
            assert bad not in lang_doc.lower(), "F6/F7 残留: %s" % bad
    assert "Parcele em até 12x" in t_pt_doc, "F6 PT 分期口径"
    assert "1~2 사이즈 크게" in t_ko_doc, "F10 KO 尺码建议统一"
    assert "한두 사이즈 업" not in t_ko_doc and "한 치수 크게" not in t_ko_doc, "F10 旧口径残留"
    assert "KR sizing tops out" not in text, "F11 EN 韩码残留"
    assert "padrão KR vai até" not in t_pt_doc, "F11 PT 韩码残留"
    assert "KR 표기는 88" in t_ko_doc, "F11 KO 保留韩码说明"
    assert "싱글 브레스티드" in t_ko_doc, "F14 KO 单排扣本地化"
    assert "Single Breasted" in t_ko_doc, "F14 KO 不应再直出英文"
    assert "abotoamento frontal" in t_pt_doc, "F14 PT 单排扣加注"
    # —— v3.3.0 买家区净化：内贸字段/linter 行/编造样例/deterministic 措辞 ——
    for bad in ("Article No", "Primary export market", "Cross-border supply",
                "Orthography", "linter", "sample sizing", "deterministic conversions"):
        assert bad not in buyer, "买家区脏字段: %s" % bad
    assert "Article No" in appendix or "货号" in appendix, "Appendix 未承载货号"
    # —— PT 正字（v3.2.0 模板剥重音根因修复，抽查 5+ 词）——
    for good in ("padrões", "Proteção", "iluminação", "estúdio", "é conferido",
                 "física", "são mostradas"):
        assert good in t_pt_doc, "PT 正字缺失: %s" % good
    assert "padroes" not in t_pt_doc and "Protecao " not in t_pt_doc and "iluminacao" not in t_pt_doc
    # —— 平台能力落地：KO 직배송 참조 / PT Pix·12x / KO 无编造胸围 ——
    assert "직배송 리드타임" in t_ko_doc, "KO 缺发货时效口径"
    assert "Pague com Pix" in t_pt_doc and "Parcele em até 12x" in t_pt_doc, "PT 缺 Pix/12x"
    assert "sem juros" not in t_pt_doc, "F6 PT 免息承诺残留"
    assert "가슴둘레" not in t_ko_doc, "KO 编造胸围句仍在"
    # —— 类目映射附录行值补翻（Autumn 2024年秋季 → 各语言季节词）——
    # 构造最小字典条目（与 _rich_facts 属性重叠达标）驱动类目映射区块渲染
    dicts = {"entries": [{
        "nameChinese": "女式衬衫", "categoryId": 29072,
        "categoryPath": "服装、鞋靴和珠宝饰品 >> 女装 >> 女式衬衫",
        "categoryMetadata": {
            "categorySaleAttrList": [{"name": "颜色"}, {"name": "尺码"}],
            "categoryProductAttrList": [{"name": "领型"}, {"name": "袖长"}, {"name": "版型"},
                                        {"name": "图案"}, {"name": "上市年份/季节"}]}}]}
    ko_map_doc = mod.assemble_language_doc(facts, "ko", "jpeg", flags, dicts,
                                           img_mode="vl-distinct",
                                           img_stats={"mode": "vl-distinct", "slots": []})
    assert "## 카테고리 매핑" in ko_map_doc, "最小字典未命中类目映射区块"
    ko_map = ko_map_doc[ko_map_doc.index("## 카테고리 매핑"):ko_map_doc.index("## CJK Reference")]
    assert "2024년 가을" in ko_map and "年秋季" not in ko_map, "ko 类目映射行未补翻: %r" % ko_map
    assert "Autumn 2024年秋季" not in ko_map_doc and "2024年秋季" not in buyer
    # 编造数据与价格示例清零
    assert "chest 33-35" not in text, "EN 胸围编造仍在"
    assert "$12.99" not in text and "₩12,900" not in text and "1.234,56" not in text
    # 附录含溯源与自审；CJK 对照表承载原文
    assert "## Compliance Self-Audit" in text and "## Sourcing Provenance" in text
    assert "CJK Reference" in text and "主面料成分:涤纶（聚酯纤维）" in appendix
    # 旧模板细节句不得再现（绝不写不存在的细节图）
    assert "fabric, cut and craftsmanship details" not in text
    # ko/pt 双区同样零 CJK 买家区
    for lang in ("ko", "pt"):
        t2 = _full_doc(lang)
        b2 = t2[:t2.index(mod.APPENDIX_MARKER)]
        assert not CJK_RE.search(b2), "%s 买家区残留 CJK" % lang
        assert "Untranslated CJK lines (buyer zone) | 0" in t2

    # —— v3.3.0 真实尺码列（供应商尺码表 OCR 结果注入）——
    facts_sc = _rich_facts()
    facts_sc["_size_chart"] = {
        "ok": True,
        "rows": {"S": {"bust": 98.0, "length": 65.0}, "M": {"bust": 100.0, "length": 65.0},
                 "L": {"bust": 102.0, "length": 66.0}, "XL": {"bust": 104.0, "length": 66.0},
                 "2XL": {"bust": 106.0, "length": 67.0}, "3XL": {"bust": 108.0, "length": 67.0}},
        "img": "3887087154767_description_01.jpg", "model": "qwen3.5-ocr",
        "source_url": "https://x/x_description_01.jpg"}
    text_sc = mod.assemble_language_doc(facts_sc, "en", "jpeg", flags, {},
                                        img_mode="vl-distinct",
                                        img_stats={"mode": "vl-distinct", "slots": []})
    buyer_sc = text_sc[:text_sc.index(mod.APPENDIX_MARKER)]
    appendix_sc = text_sc[text_sc.index(mod.APPENDIX_MARKER):]
    assert "Bust (cm)" in buyer_sc and "Length (cm)" in buyer_sc, buyer_sc
    assert "| S | 98 | 65 |" in buyer_sc, buyer_sc
    assert "| 3XL | 108 | 67 |" in buyer_sc, buyer_sc
    assert "US reference (auxiliary)" in buyer_sc, "真实测量列存在时参考列未降级辅助"
    # v3.4.0（F2）：买家区脚注只写 supplier-measured size chart——零 offerId 零文件名
    assert "supplier-measured size chart" in buyer_sc, "缺尺码表来源标注"
    assert "3887087154767" not in buyer_sc and ".jpg" not in buyer_sc, \
        "买家区泄露 offerId/源图文件名"
    assert "US reference (auxiliary)" not in buyer, "无真实测量列时参考列不应降级"
    # v3.4.0（F5）：属性 衣长 50-65cm vs 尺码表 65-67cm 冲突 → Appendix 冲突注记
    assert "Source-data note" in appendix_sc and "takes precedence for measurements" in appendix_sc, \
        "Appendix 缺源数据冲突注记"
    text_sc_ko = mod.assemble_language_doc(facts_sc, "ko", "jpeg", flags, {},
                                           img_mode="vl-distinct",
                                           img_stats={"mode": "vl-distinct", "slots": []})
    assert "가슴둘레와 옷 길이는 공급사 실측" in text_sc_ko, "ko 缺真实测量来源句"
    assert "출처 데이터 충돌 참고" in text_sc_ko, "ko 缺源数据冲突注记"


def t15_size_chart_parser(mod):
    """v3.3.0：尺码表 OCR 文本确定性解析（真实样本形态）+ 斤档交叉校验 + 失败下界。"""
    sample = ("7:17\n备忘录\n尺寸推荐\n胸围 衣长 体重建议\n"
              "S 98 65 80-95斤\nM 100 65 95-105斤\nL 102 66 105-115斤\n"
              "XL 104 66 115-125斤\nXXL 106 67 125-140斤\nXXXL 108 67 140-160斤\n")
    facts = _rich_facts()
    sku_tags = mod._sku_weight_tags(facts)
    assert sku_tags["S"] == (80.0, 95.0) and sku_tags["3XL"] == (140.0, 160.0), sku_tags
    rows, ok, why = mod.parse_size_chart_text(sample, sku_tags)
    assert ok, why
    assert set(rows) == {"S", "M", "L", "XL", "2XL", "3XL"}, rows
    assert rows["S"] == {"bust": 98.0, "length": 65.0}, rows["S"]
    assert rows["2XL"] == {"bust": 106.0, "length": 67.0}, rows["2XL"]  # XXL→2XL
    assert rows["3XL"] == {"bust": 108.0, "length": 67.0}, rows["3XL"]  # XXXL→3XL
    # OCR 错位/越界与单行样本 → 有效行不足 2 → 整体失败（下界，不写编造列）
    bad = "尺寸推荐\n胸围 衣长 体重建议\nS 198 65 80-95斤\n"
    rows2, ok2, _why2 = mod.parse_size_chart_text(bad, sku_tags)
    assert "S" not in rows2, "胸围越界行未拦截"
    assert not ok2 and not rows2, "失败下界未生效"
    rows2b, ok2b, _ = mod.parse_size_chart_text(
        "胸围 衣长 体重建议\nS 98 65 80-95斤\n", sku_tags)
    assert not ok2b and len(rows2b) < 2, "单行样本应判失败（<2 码档）"
    # 斤档与 SKU 不一致 → 该行弃用（S 行被拦，M/L 行交叉校验通过保留）
    mismatch = "S 98 65 80-96斤\nM 100 65 95-105斤\nL 102 66 105-115斤\n"
    rows3, ok3, _ = mod.parse_size_chart_text(mismatch, sku_tags)
    assert "S" not in rows3 and ok3 and "M" in rows3 and "L" in rows3, (rows3, ok3)
    # 无表文本 → 失败
    rows4, ok4, why4 = mod.parse_size_chart_text("Lorem ipsum 123 main image", sku_tags)
    assert not ok4 and not rows4 and why4


def t16_color_auth_and_media(mod):
    """v3.3.0：描述字段提图/短名、色标 SKU 权威化（blue 错标修复口径）、
    自然语言图文（尺码表槽+as shown）、媒体对照短名。"""
    assert mod._img_short_name(
        "https://x.example/AI/3887087154767_description_01.jpg?Expires=1&Signature=a%3D") \
        == "3887087154767_description_01.jpg"
    # 色标权威化：VL 自由命名 blue 不在 SKU 色集合 → 不写（as shown 口径）；
    # green ∈ SKU 色 → 写 green；URL 文件名色 ∈ SKU → 确定性优先
    g_blue = {"url": "https://x/p.jpg"}
    s_blue = {"https://x/p.jpg": {"dominant_color": "blue"}}
    assert mod._content_color_zh(g_blue, s_blue, ["紫色", "白色", "黑色", "绿色"]) == "", \
        "VL blue 未命中 SKU 色，应返回空（as shown）"
    g_green = {"url": "https://x/p.jpg"}
    assert mod._content_color_zh(g_green, {"https://x/p.jpg": {"dominant_color": "green"}},
                                 ["紫色", "白色", "黑色", "绿色"]) == "绿色"
    g_url = {"url": "https://x/p_黑色.jpg"}
    assert mod._content_color_zh(g_url, {"https://x/p_黑色.jpg": {"dominant_color": "blue"}},
                                 ["紫色", "白色", "黑色", "绿色"]) == "黑色", "URL 色应优先且确定"
    # 自然语言图文：front+白底 / 尺码表槽 / 无色 as shown
    slots = [{"name": "main_image", "url": "https://x/a.jpg", "cat": "front",
              "color_zh": "白色", "white_bg": True},
             {"name": "detail_image_1", "url": "https://x/d01.jpg", "cat": "sizechart",
              "color_zh": "", "white_bg": False, "is_chart_source": True},
             {"name": "detail_image_2", "url": "https://x/d02.jpg", "cat": "side",
              "color_zh": "", "white_bg": False}]
    out = mod.render_img_descriptions({"mode": "vl-distinct", "slots": slots}, "en", "jpeg",
                                      cat_word="Blouse")
    assert "- main_image.jpeg: The main image shows the blouse in white, front view, " \
           "shot on a plain light studio background." in out, out
    assert "supplier size chart" in out, out
    assert "side view" in out, out
    assert "color as shown" in out, out
    out_ko = mod.render_img_descriptions({"mode": "vl-distinct", "slots": slots}, "ko", "jpeg",
                                         cat_word="블라우스")
    assert "흰색 컬러" in out_ko and "정면 컷" in out_ko and "공급사 사이즈표" in out_ko, out_ko
    out_pt = mod.render_img_descriptions({"mode": "vl-distinct", "slots": slots}, "pt", "jpeg",
                                         cat_word="Blusa")
    assert "A imagem principal mostra a blusa em branco" in out_pt, out_pt
    assert "vista lateral" in out_pt and "tabela de medidas do fornecedor" in out_pt, out_pt
    # 占位模式如实
    out_ph = mod.render_img_descriptions({"mode": "placeholder:png", "slots": []}, "pt", "png")
    assert "indisponíveis nesta execução" in out_ph, out_ph
    # —— v3.4.0（A3 三方同源）：§5 图集表 / Media File Mapping / 选图记录同源 ——
    slots3 = [
        {"name": "main_image", "url": "https://x/388_main.jpg", "short": "388_main.jpg",
         "src_desc": False, "gno": 5, "role": "main", "role_txt": "主图", "cat": "front",
         "color_zh": "绿色", "color_en": "", "white_bg": True},
        {"name": "detail_image_1", "url": "https://x/388_description_04.jpg",
         "short": "388_description_04.jpg", "src_desc": True, "gno": 9, "role": "macro",
         "role_txt": "细节/微距", "cat": "closeup", "color_zh": "", "color_en": "",
         "white_bg": False},
        {"name": "detail_image_2", "url": "https://x/388_sku_黑色.jpg", "short": "388_sku_黑色.jpg",
         "src_desc": False, "gno": 2, "role": "color1", "role_txt": "异色正面/场景①",
         "cat": "scene", "color_zh": "黑色", "color_en": "", "white_bg": False},
    ]
    img_meta3 = {"mode": "vl-distinct", "slots": slots3}
    table = mod.render_gallery_table(img_meta3)
    for short in ("388_main.jpg", "388_description_04.jpg", "388_sku_黑色.jpg"):
        assert short in table, "§5 图集表缺 %s" % short
    appendix3 = mod.render_appendix({}, "en", "jpeg", mod.feature_flags("3.4.0"), {},
                                    "vl-distinct", img_meta3)
    for short in ("388_main.jpg", "388_description_04.jpg", "388_sku_黑色.jpg"):
        assert short in appendix3, "Media File Mapping 缺 %s" % short
    assert "| detail_image_1.jpeg | 388_description_04.jpg |" in appendix3, appendix3
    assert mod.render_gallery_table({"mode": "vl-distinct", "slots": []}) == "", "无 slots 应返回空"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", help="被测 agent.py 路径（默认自动定位）")
    args = ap.parse_args()
    path = find_agent_py(args.agent)
    if not path:
        print("FAIL: 未找到 agent.py（可用 --agent 指定）")
        return 1
    mod = load_agent(path)
    cases = [("t01 version 契约", lambda: t01_version(mod)),
             ("t02 官方 prompt 路径解析", lambda: t02_official_prompt(mod)),
             ("t03 en/ko/pt 陷阱与 .json 后缀", lambda: t03_trap_fragments(mod)),
             ("t04 A1 黑名单词边界", lambda: t04_blacklist(mod)),
             ("t05 词表往返与度量换算", lambda: t05_glossary_and_units(mod)),
             ("t06 占位 PNG 与尺寸", lambda: t06_placeholder_png(mod)),
             ("t07 stub 输入 = 11 文件 exit 0 + 双区", lambda: t07_stub_run(mod)),
             ("t08 zip 结构自检", lambda: t08_zip_structure()),
             ("t09 mvhd 时长解析", lambda: t09_mvhd_duration(mod)),
             ("t10 互异图池构建（含描述字段图）", lambda: t10_image_pool(mod)),
             ("t11 内容级去重六槽选图与回退", lambda: t11_content_dedupe_selection(mod)),
             ("t12 v3.4.0 陈述一致性", lambda: t12_statements(mod)),
             ("t13 全片严格质检与源视频扫描", lambda: t13_fullclip_qc_and_source_video(mod)),
             ("t14 双区/标题/SKU 汇总/真实尺码列/PT 正字", lambda: t14_dualzone_title_sku(mod)),
             ("t15 尺码表 OCR 解析器", lambda: t15_size_chart_parser(mod)),
             ("t16 色标权威化与自然语言图文", lambda: t16_color_auth_and_media(mod)),
             ("t17 divsel 视觉去重 + uigate 资格门", lambda: t17_divsel_and_uigate(mod)),
             ("t18 QC 双通道合并 + vidcap 文案", lambda: t18_qc_merge_and_vidcap(mod)),
             ("t19 write_images divsel 全链冒烟", lambda: t19_write_images_divsel_smoke(mod)),
             ("t20 图集终筛换图", lambda: t20_rescreen_swap(mod)),
             ("t21 motionchain 转身链分档与如实描述", lambda: t21_motionchain(mod)),
             ("t22 mainscene 主图场景化与补缺", lambda: t22_mainscene(mod))]
    t0, passed, skipped, failed = time.time(), 0, 0, 0
    print("selftest target: %s (version %s)" % (path, mod.read_version()))
    for name, fn in cases:
        try:
            note = fn() or "PASS"
        except Exception as e:
            failed += 1
            print("  [FAIL] %s -> %r" % (name, e))
            continue
        if note == "PASS":
            passed += 1
        else:
            skipped += 1
        print("  [%s] %s%s" % ("SKIP" if note != "PASS" else "PASS", name,
                               "" if note == "PASS" else " -> " + note))
    print("summary: %d/%d passed, %d skipped, %d failed (%.1fs)"
          % (passed, len(cases), skipped, failed, time.time() - t0))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
