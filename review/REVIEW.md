# 审查索引：v3.6.1「主图场景化 + 跨境可用性」迭代

审查对象：`xborder-agent-v3.6.1-final.zip`（发布包，含打包 Pillow）+ `agent-source/`（源码快照）。
基底：v3.5.6（已验证收割包）。本轮新增 = mainscene 双杠杆（产品无关元方法）。

## 本轮做了什么

1. **真实电商视频基准研究**：HF `FashionVideo/xhs_video_data` 40 条真实女装视频逐帧看片（benchmark/xhs_sheets/ + FINDINGS.md）——单镜头为主流、转身展示链是核心动作语汇、音轨普遍存在。
2. **真实目录图片基准**：Livostyle（美区 DTC）+ H&M 各 40 张（FINDINGS_IMAGES.md）——印证白底主图 + 场景详情的选图策略。
3. **视频侧 v3.5.2→v3.5.6**：转身展示链（全品类+全身门槛）→ 构图锚定（消灭 dolly-in 伪影带）→ 三通道 QC（时序一致性）。红队两轮实测：伪影清洁度 3/10 → 7/10（可辩护）。
4. **图片侧 v3.6.0/3.6.1 mainscene**：主图死白场景化（白转透明 → wanx-background-generation-v2 → 本地合成【主体像素 100% 回贴原图】→ VL 同款 A/B 择优，失败回退源图）+ 小图池详情补缺（白底前提前置路由）。
5. **目录级验证**：Task_Data 全部 11 商品全量真跑，10 新商品全 exit 0、11 文件契约全保。结果：主图场景化 4 采纳、补缺 1 采纳 + 1 次 VL 拦截（伪影）、非白底诚实回退、视频梯子全正常（诚实回退预置片 1 例）。

## 关键文件

| 路径 | 内容 |
|---|---|
| review/agent-source/ | v3.6.1 源码快照（agent.py ~5600 行 + selftest 22 项） |
| xborder-agent-v3.6.1-final.zip | 发布包（7.8MB，含打包 Pillow） |
| benchmark/catalog_before_after.jpg | **必看**：三品类主图 BEFORE/AFTER |
| benchmark/v360_review.jpg | 场景化主图 + 视频帧一致性 |
| benchmark/ring_proof.jpg | 配饰溯源证据（源图自带） |
| benchmark/xhs_sheets/ | 真实视频基准接触表 |
| benchmark/FINDINGS.md | 视频基准研究全文 |
| benchmark/FINDINGS_IMAGES.md | 图片基准研究全文 |
| redteam/round-4.md | 视频专项红队结案报告 |

## 已知边界（如实声明）

- 图片 = 供应商原图直选（零像素生成；去重/质检/合规筛查为机器加工）——合规册"仅授权源图直投、零二创"。
- 视频 = Wan2.7 i2v 生成（源数据无视频）。
- mainscene 场景化：商品本体像素零改动（构造保证：生成图仅作背景层，本地合成），VL A/B 不过即回退；matte 质量不足时自动放弃（v3.6.1 验证跑实测触发回退）。
- distinct<5 的商品（源素材不足）在 Run Report 显式建议人工复核后再发布。
