# PastPort

将官方遗产资料转化为有史实依据、有人物成长的互动游戏，并用同一制作流程复制到其他遗址。

**当前状态：T1a 共享合同已实现，可进行本地契约验收。** `src/pastport/` 提供严格类型、模块 Protocol、三包与状态模型；`schemas/` 和合成 fixtures 可复现检查。尚无数据库服务、运行中的 LangGraph 或通用播放器；两个 Skill 尚未接真实模型。

2026-10-16 已修订指导规范并完成 T1a 合同实现；产品能力和 Workflow 仍待后续任务接入。逐项状态见[PRD 架构评审与优化闭环](docs/PRD.md#13-架构评审与优化闭环)。

| 从哪里开始 | 内容 |
|---|---|
| [产品需求 PRD](docs/PRD.md) | 产品逻辑、四模块职责、资料/故事底线、范围、分工、里程碑和验收 |
| [Workflow 实现合同](docs/WORKFLOW.md) | 数据与状态、节点/API、恢复/预算、通用玩法、Skill 协议及 T1–T7 实施任务 |
| [工程与 CI 规范](docs/ENGINEERING.md) | Coding Agent、代码质量、协作、当前检查与未来检查接入 |
| [参考依据](docs/REFERENCES.md) | Muradiye 抽象方法、遗产系统与开源 Skill 源头、许可和采用边界 |
| [PRD 架构评审与优化闭环](docs/PRD.md#13-架构评审与优化闭环) | 评审问题对应的权威章节、实施优先级、验证证据与负责人 |

项目 Skill：[资料审核](skills/evidence-review/SKILL.md)、[情节制作](skills/narrative/SKILL.md)。只按任务读取相关入口和范例。

官方目录说明表与比赛条款保留在 `references/`，它们是来源材料，不代表内容已获审核通过。

## 规范权威与阅读顺序

以本仓库 main 的 `docs/PRD.md` 为产品权威，`docs/WORKFLOW.md` 唯一维护字段/执行语义，`docs/ENGINEERING.md` 维护工程与 CI 规则。Skill 维护专业方法，不能另造审批或控制协议。其他工作目录的 PRD 为历史工作副本；引用时记录仓库/分支/版本，不把副本或 demo 分支当作当前框架合同。

内部负责人统一写 Weng / Matt / Weijia；旧材料中的 Mert 对应当前文档的 Matt，正式对外姓名仍待本人确认。角色名不等于已配置的认证账号。

首个产品验证是可追溯的短样段：遗产依据参与判断、人物选择有代价、后续变化可见。先验证体验与制作负担，再扩大完整后台和章节；公开内容始终执行证据、故事和发布门禁。阅读或更新规范不自动授权开始编码、调用付费模型或发布。

## 分支与样本

- `main`：通用产品、框架与 Workflow 的规范及后续实现。
- [demo-muradiye](https://github.com/Psyche0920/PastPort/tree/demo-muradiye)：完整中英 Demo、照片、数据、SQL、脚本和历史回归测试。main 只保留抽象参考，不复制 Demo。

**T1a 的实现与交接见 [共享合同基线](docs/CONTRACTS.md)**；其他模式在接入前按 T1b 补齐，不先铺完整后台。Muradiye 的固定样本版本见 Workflow §2，用来对照兼容性；第二个官方同层级文件夹用于首次完整新项目试跑。

## 当前检查

使用 Python 3.12.12 和 uv 0.12.8；精确依赖见 uv.lock。首次运行：

```bash
uv sync --locked --group dev
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy --strict src/pastport tools/check_contracts.py tests
uv run --no-sync python tools/check_contracts.py
uv run --no-sync pytest
uv run --no-sync python tools/check_repository.py
```

安装后各项分别检查类型、格式、合同/Schema、离线边界及仓库文件/链接/语法。动作向量仍为 not_run，不能宣称玩家引擎通过。本地 CI 已配置 quality、python-tests 和汇总 ci；远端运行仍待推送后核验。
