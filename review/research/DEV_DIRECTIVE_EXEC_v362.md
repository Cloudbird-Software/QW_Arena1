# DEV_DIRECTIVE_v3.6.2 执行纪要

官方出分背景：v3.5.6=84.3 / v3.6.1=78.77（Δ-5.53 归因 mainscene）。

## 已落地
- P0：mainscene 默认关闭（feature_flags 门控 (3,6,0)≤v<(3,6,2) + XB_MAINSCENE=1 灰度口子）；LF 归一（6078 CRLF 清零）+ 打包三道门禁（LF/--version/selftest）；docstring/文档版本对齐；MAISCENE→MAINSCENE；requirements 如实声明 vendored Pillow。
- P1：§3-A5=100（竞品快照脱敏 + 源数据属性逐项对照表入 Appendix）；§3-A4 窗口修复（紧凑 Market Adaptation Summary 固定进每份文案头部——judge smart_trunc 头 1800 窗口，实测 pos 77/37/84）；§4 上架一致性闸门六则（货号拦截/品类名词/色码清洗/童装判定/测量 sanity/参考码自洽，文档级终清洗，权威检测器 33/33 买家区全净）；§2 mainscene 180s 时长硬顶；§7 竞品口径去样本化 + 分辨率陈述以实测证据维持（tkhd=960×960）。

## 验收数据
- selftest 22/22；三道打包门禁全过。
- 11 商品全量真跑：11/11 exit 0、11 文件契约全保、§4 权威口径零直出。
- 本地 judge N=5：total 87.49（A5=100、A6=100；A7 本地无 ffmpeg 记 60，CNB 口径=100 → 等效 ≈89.5）。
- CNB judge N=3 回归：阻塞于评测基建——主力 DashScope key 欠费（overdue-payment），VL 模型（A2/A6/A7 评分与 agent VL 链依赖）不可用；Token Plan 目录无 VL。非 agent 缺陷；官方测评用平台 key 不受影响。

## 未竟（P2，如实报告）
- §5 视频颜色恒定性本地通道；§6 文案业务质量（卖点差异化/SEO 入文/韩语专项/图文一致/买家区瘦身）；§9 extract_paths Unicode 路径字符类。

## 附注（heredoc 转义教训）
本会话 bash heredoc 内嵌 Python 的转义多次被二次解释（\n→真换行、\d→字面量），产生过未定义变量/语法错误/静默失效三类事故。复杂补丁一律走 Write 工具写脚本文件执行；该教训已入开发纪律。
