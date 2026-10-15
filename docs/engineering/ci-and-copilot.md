# PastPort CI 与 Copilot 维护规范

本文独立维护自动检查、GitHub Actions 和 Copilot 的配置，避免这些会随代码和账号能力变化的操作细节挤进产品 PRD。产品范围和验收仍由 PastPort PRD 管理。

## 当前状态

CI 配置与简短 Copilot 指引在 [CI 接入 PR #1](https://github.com/Psyche0920/PastPort/pull/1) 中提交；最终验证运行记录为 [GitHub Actions run](https://github.com/Psyche0920/PastPort/actions/runs/38731112889)。PR 是否合并、默认分支实际启用状态以 GitHub 为准。账号设置曾显示 Copilot Cloud Agent 许可证不可用，私有仓库分支保护也受套餐限制；其他 Copilot 功能需分别核对。不得把配置文件存在误报为 GitHub 已强制执行。

实际工作流定义：[`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml)。

## GitHub Actions 与 Copilot 的使用方式

**采用方式：GitHub Actions 做自动检查；Copilot/Codex 等 Coding Agent 按需辅助开发。** 可以直接使用 Copilot 编写代码、补测试、建立 CI workflow、处理失败并提交 PR，不必自建“编程 Agent 平台”。Copilot 不替代每次提交都必须执行的确定性检查，也不替代本项目要求的人类代码评审和证据审核。

| 工具 | 在本项目做什么 | 何时使用 |
|---|---|---|
| GitHub Actions（CI） | 在受控环境重复运行格式、类型、测试、构建与报告，结果作为合并门禁 | PR、默认分支 push、手动触发；通常不消耗模型 tokens，但计算用量可能计费 |
| Copilot / 其他 Coding Agent | 理解明确任务、修改代码、运行检查、提出修复；可辅助编写 `.github/workflows/ci.yml` | 有实际研发任务时启用；记录相应订阅/用量与返工成本 |
| Copilot code review（可选） | 对 PR diff 提供问题与建议 | 风险较高或需要第二视角的 PR；不强制每次提交重复调用 |
| 人类评审者 | 核对需求、共享契约、风险和实际检查结果，决定合并；领域负责人另审内容 | 每个正式 PR 与内容审批关口 |

落地步骤（Weijia 主责）：

1. 在代码仓库确认 GitHub Actions 可用，记录实际默认分支；由人或 Copilot 创建 `ci.yml`，先接现有两组离线测试。
2. 配置依赖安装与版本锁定、最小权限和超时；通过一个正常 PR，再用失败测试确认 CI 确实拦截错误。
3. 在仓库 Settings 的 Rulesets / Branch protection 中配置本仓库实际产生的 required checks 与人工评审，验证失败时不能合并；是否可用按实际套餐/权限核对。
4. 需要 Copilot 时核对账号/组织权限并启用相应功能；提供“目标、相关路径、验收、禁止触碰范围”的小任务，从 IDE 或仓库支持的 Agent 入口执行。CI 状态从 PR 的 Checks 查看，失败后只提供有关日志片段再修复。
5. 所有 Agent 用 `AGENTS.md`；Copilot 通过简短 `.github/copilot-instructions.md` 引导到同一规范，避免维护整份重复规则。不同 Copilot 场景对指令支持不同，首次任务核对是否生效。
6. 新模块逐步接入检查矩阵，M5 前完善完整门禁。Copilot 的可用功能与费用取决于套餐/策略，不在 PRD 中承诺免费、固定配额或自动获得完整权限。

采用顺序：先建立便宜、可重复的 CI，再按需要增加付费 Coding Agent 和 AI 审查。即使不购买 Copilot，同一套 CI 与人类评审流程也能运行。[GitHub Actions](https://docs.github.com/en/actions/get-started/understand-github-actions)、[Copilot 功能](https://docs.github.com/en/copilot/concepts/copilot-surfaces/copilot-on-github)、[自定义指令](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions)。

### 自动检查的触发与共同规则

PR 和默认分支 push 执行确定性检查，允许手动运行同一套检查。合并队列只有实际启用时才配置 `merge_group`。默认测试离线、不需要供应商密钥、不抓完整 Drive、不调用付费模型。

Python/Node 版本与依赖精确锁定，由干净检出安装；不能复用开发者全局环境。Python 3.12 及当前受支持的 Node LTS 是选择起点，确认依赖兼容后把精确版本写入仓库。锁文件变更必须审查，不能安装失败后静默升级版本。

| Check | 执行与覆盖 | 失败条件 |
|---|---|---|
| `quality` | Python `ruff check`、`ruff format --check`、新模块 `mypy --strict`；JS lint/格式检查；Markdown 相对链接、JSON/Schema 基本检查 | 规则/类型错误、断链、无效 Schema；不得自动修后当原提交通过 |
| `python-tests` | 当前 unittest 保留；新增 pytest 测领域、适配器和临时 SQLite 集成；fixture Gateway 测流程、审批、预算、取消恢复 | 任一测试失败、隐藏联网、真实库写入或必需用例被跳过 |
| `player-tests` | Node 规则测试；兼容版本、中英等价、关键分支、重复动作、存档隔离 | 分支后果/答案漂移、跨包污染、无法恢复 |
| `package-tests` | 双项目 fixture 跑同一装配器；检查引用、审批 hash、媒体/许可、路由引用、兼容性；加载包跑关键规则路径 | 无效包被放行、任一 fixture 不可完成、地点专用运行代码依赖 |
| `browser-smoke` | 用固定测试服务和小型媒体，桌面/移动视口完成主线、语言切换、刷新恢复；键盘操作测试 | 关键 UI 路径无法完成、错误反馈缺失；自动检查不替代人工无障碍验收 |
| `ci` | 固定汇总检查，依赖本次适用的所有 jobs；无条件运行并验证结果 | 任一必需 job 失败/取消或意外跳过；不能仅因汇总 job 启动便标成功 |

检查分阶段接入：现有两组测试先进入 CI；新 Python 模块提交时同时接静态检查；装配器、双项目 fixture 和通用玩家端完成时分别接入对应 jobs。M5 之前表中检查必须落地。未实现的 check 不设置空任务或伪成功，也不提前在 GitHub 保护规则中要求一个永远不产生的名称。

暂不设全仓库覆盖率百分比；优先覆盖不可绕过的审批、预算、发布、恢复及任务状态边界。历史代码的类型基线显式列出范围和清理责任，不对新代码放宽 strict，不用批量 `ignore` 把失败变绿。

### CI 权限、费用与可靠性

- 普通检查设置 `permissions: contents: read`；发布任务单独授予必要权限。PR 来自 fork 时不提供模型、部署或资料密钥。
- 不在特权 `pull_request_target` / `workflow_run` 中检出并执行不可信 PR 内容。PR 标题、分支名等不直接拼入 shell；通过受控参数/环境变量传递。
- 外部 Actions 固定经核验的完整 commit SHA，并记录可读版本，定期更新；CI 依赖变更由 Weijia 评审。若实际环境支持 workflow 依赖锁文件，可评估进一步锁定，不把不兼容特性当前提。
- 每个 job 有超时，测试工作目录/SQLite/临时端口隔离；只在可重入的 PR 检查取消同分支旧运行，正式发布不能被新提交随意中断。
- 缓存键包含 OS、运行时和锁文件 hash；不跨不可信 PR 共享敏感数据。失败产物只上传脱敏报告/截图，设置保留期，禁止上传真实 DB、原件、密钥或全量模型上下文。
- 必需汇总 check 不因路径过滤永远 pending。初期以小型全套检查为主；文档仅改动可在统一检查内显式判断并执行文档检查，跳过昂贵任务须有可审计条件。
- CI 网络仅用于锁定依赖等必要安装；业务代码测试默认禁止外部业务调用。真实供应商兼容、图像能力和付费评测单独手动触发，显式设置金额/调用上限，不随每个 PR 运行。

### 测试与正式发布分开

CI 通过表示工程检查通过，不自动批准史实或公开素材。游戏内容发布仍须匹配 PRD 的证据与故事审批快照。软件部署与内容发布分别记录版本、操作者和结果；部署目标与所需人工环境审批在公开前配置。

发布按单个项目串行化：锁定目标及预期旧版本，完整写入新包后用原子指针/事务切换。失败保留旧包；回滚前核对兼容性与许可。DB schema 迁移独立备份并验证恢复，不能把回滚静态包当作已回滚数据库。

## 当前 CI 实际覆盖

| Check | 实际执行 |
|---|---|
| `quality` | Python 编译检查、跟踪中的 JavaScript 语法检查、JSON 解析 |
| `python-tests` | 5 项数据库测试，使用临时数据库 |
| `player-tests` | 8 项确定性的故事与语言回归测试 |
| `ci` | 校验所有必需 job 成功；失败、取消或跳过均会失败 |

当前不安装第三方 lint/type 依赖，不运行浏览器 smoke 或双项目内容包检查。新检查随相应功能实现并经过验证后再加入，不能把计划中的项目描述成已通过。

本地回归命令：

```bash
python3 -m unittest discover -s tests -v
node --test tests/test_story_engine.mjs
python3 -m compileall -q scripts tests
```

从 Actions > PastPort CI > Run workflow 手动运行时，`failure_probe` 默认为 false。只有需要验证失败传播时才设为 true；此时 `quality` 和最终 `ci` 应失败，两个产品测试应保持通过。完成故障演练后再运行一次正常检查。故障探针不修改产品代码，也不调用模型。

工程参考：[Actions 安全实践](https://docs.github.com/en/actions/reference/security/secure-use)、[保护分支](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)、[Copilot code review](https://docs.github.com/en/copilot/concepts/agent-capabilities/agent-powered-workflows-and-operations/code-review)。功能与权限在实际仓库启用时复核。
