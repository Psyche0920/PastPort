# PastPort

将可追溯的遗产资料转化为有人物、判断、选择与后果的互动游戏。Python 负责制作 workflow 和共享服务；原生 JS 负责游戏规则与浏览器试玩。

**当前初版已具备共享 workflow、审核/预算/恢复、游戏底座和浏览器工作台。** Weng/Mert 可以接入自己的模块并固定另一侧独立测试。正式模块联合接入、真实材料/许可、付费模型、真人试玩、远端 CI 和生产仍需各自验收。

## 团队协作入口

| 文档 | 只维护什么 |
|---|---|
| [PRD / 当前架构与代码库说明](docs/README.md) | 产品目标、整体架构、现有能力、接口与操作规范 |
| [Active Plan](docs/ACTIVE_PLAN.md) | 当前范围/限制、任务、负责人、依赖、验收和阻塞 |
| [Decision Log](docs/DECISION_LOG.md) | 关键决定、理由、取舍和替代关系 |
| [Change Log](docs/CHANGELOG.md) | 已验证的主要交付、状态和证据 |

Coding Agent 遵循 [AGENTS.md](AGENTS.md)，从当前任务和受影响模块开始，按需读规范片段；不每轮通读四份文档。任务经过验收才标完成；跨模块交付先确认合同和固定参照模块。规则只在总说明 §15 维护，不在各处重复。

## 模块与主要文件用途

模块 README 列出所有直属源文件用途；总说明维护跨模块规则，避免重复。

| 模块 | 用途 | 主要文件 | 文件清单 |
|---|---|---|---|
| 包入口 | 启动、类型导出、统一诊断配置 | `__main__.py` 启动；`contracts.py` 导出；`observability.py` JSON 日志 | [包 README](src/pastport/README.md) |
| domain | 不依赖框架的不可变合同、校验与身份 | `modules.py` 模块消息；`evidence.py` 证据；`game.py` 玩法；`workflow.py` 状态/预算 | [domain](src/pastport/domain/README.md) |
| ports | 可替换的模块、存储、模型与运行边界 | `modules.py` 业务 Protocol；`execution.py` 共享服务；`resources.py` 资源读取 | [ports](src/pastport/ports/README.md) |
| application | 业务用例、审批/预算、模型/工具、装配发布、预览/存档 | `service.py` 编辑用例；`execution_runtime.py` 服务装配；`publication.py` 发布；`player_service.py` 存档 | [application](src/pastport/application/README.md) |
| adapters | SQLite、文件、供应商与 Node 进程的 I/O 实现 | `database.py` 业务持久化；`content.py` 本地模块；`model_provider.py` 供应商；`player_process.py` JS 桥 | [adapters](src/pastport/adapters/README.md) |
| workflow | 单执行者、持久图与合法阶段调度 | `worker.py` 执行/恢复；`stages.py` 节点；`branching.py` 返工/补证 | [workflow](src/pastport/workflow/README.md) |
| player | 跨浏览器/Node 共用的确定性玩法解释器 | `runtime.mjs` 原子动作；`rules.mjs` 条件/效果；`runner.mjs` Python 协议入口 | [player](src/pastport/player/README.md) |
| api | 认证 HTTP、私有资源与浏览器工作台 | `app.py` composition/routes；`private_views.py` 预览/原文；`workbench.mjs` 工作台；`request_logging.py` 请求关联 | [api](src/pastport/api/README.md) |
| development | 离线模块/故障/浏览器验收与合同生成工具 | `module_check.py` 单模块；`module_acceptance.py` 四组合；`fault_acceptance.py` 故障；`browser_check.py` 浏览器 | [development](src/pastport/development/README.md) |

`tests/` 是行为/合同/故障/浏览器测试，`schemas/` 是生成合同，`skills/` 是专业方法，`tools/` 是检查工具，`references/` 是资料来源。保留必要来源证明和运行时审计；从当前基线记录关键决定和主要交付，不追补旧历史，不新增归档或每次变更一个文件。

## 快速检查

```bash
uv sync --locked --group dev
uv run --no-sync python tools/check_repository.py
uv run --no-sync python tools/check_handoff.py
uv run --no-sync python -m pastport.development.module_acceptance --output acceptance-artifacts/framework.json
```

完整启动与测试命令见总说明 §§3、14。运行日志为安全 JSON stderr；远端日志收集、保留/轮转和生产部署未启用。未授权不提交、推送、合并、付费调用或部署。
