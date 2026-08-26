# QW_Arena1 — 千问 AI Arena「一键出海」参赛 Agent

跨境电商商品素材全自动生成 Agent（IR [.github#345](https://github.com/Cloudbird-Software/.github/issues/345)）。
比赛要求与项目全量冻结记录见 [Arena_Detail.md](Arena_Detail.md)。

- **语言**：Python（languages.yaml 对本仓整体豁免，[ADR-0084](https://github.com/Cloudbird-Software/archive/blob/main/adr/ADR-0084-qw-arena1-competition-python-exemption.md)——
  外部契约优先 / 比赛沙箱部署 / 有限生命周期三条件；豁免仅语言规范面，治理基线不豁免）
- **生命周期**：比赛周期仓——**2026-08-31 赛后按 ADR-0084 退役条款处置**（转 archived 或删除，
  处置前补收尾 ADR）

## Makefile 接口（CI 只认这个）

| 目标         | 作用                            |
| ------------ | ------------------------------- |
| `make setup` | 安装依赖                        |
| `make lint`  | 语法/规范检查                   |
| `make test`  | 测试套件                        |
| `make check` | lint + test，**提交前必须全绿** |

## CI 结构

- `hygiene`：密钥扫描（gitleaks）、大文件/凭据文件拦截、zizmor Actions 审计
- `check` / `quality-gates`：构建与质量门（ADR-0061）
- `adr-required`：C1 脚手架面变更须引用 ADR（ADR-0021）
- `gate`：聚合门（组织 ruleset 的必需 check，ADR-0032 严格语义）

工作流实现在 [CI-Workflows](https://github.com/Cloudbird-Software/CI-Workflows)（钉 SHA 引用）。
