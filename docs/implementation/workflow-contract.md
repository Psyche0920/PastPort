# Workflow 实现合同：以 Muradiye 为参考

状态：首期工程基线；本文定义待实现行为，不表示代码已经完成。本文落实现有 PRD，不扩展产品范围。正文用中文解释，代码、字段、API、错误码和 Skill 输出使用英文。团队分工沿用 PRD：Weng 负责证据，Matt（Mert）负责故事与玩家体验，Weijia 负责整合；对外姓名仍需团队核对。

## 1. 阅读与实现边界

- 产品目标、四模块边界与内容审核要求见 [PRD](../product/PRD.zh-CN.md)；制作方法与资料补证见[实施框架](muradiye-to-reusable-framework.md)。本文唯一维护工程字段、节点协议、恢复计数和实施任务，不在其他文件复制。
- 首先实现一个可保存、可审核、可恢复的纵向流程，再接真实模型与外部研究。Muradiye 用于兼容性和规则对照；第二个官方同层级文件夹用于第一次新项目完整制作验证。
- 冻结 ID、版本/hash、审批权限、节点协议、状态和隔离规则。Weng/Matt 后续通过版本化政策与 Skill 调整来源标准、评分、任务与文案；结构改变走 Schema 版本升级。
- 一次只实现第 12 节的一个任务。Coding Agent 任务单只带目标、相关节号、输入样例、受影响路径和验收；不重复加载整份对话或全部资料。

## 2. Muradiye 迁移依据

| 现有事实与入口 | 首期迁移要求 | 保留的行为 |
|---|---|---|
| `data/muradiye-story.json` 有五场景：arrival、courtyard、fountain、imaret、reckoning | 旧 JSON 经单独 Legacy Adapter 转成新版包；新 Schema 不以这些 ID 作为固定枚举 | 当前故事、照片引用、观察要求、三次关键选择、中英文结果 |
| `prototype/engine.mjs` 在 inspect、choose、resolveEnding 中识别特定场景/证据/选项 | 证据发放、条件文本和结局改为包内声明规则 | 找到水池取得 loading-slip；找到星形细部取得 kitchen-slip；帮助证人取得 witness |
| 原任务类型为 document、inspect、inspect-sort、caseboard | P0 只实现这四种通用 Handler，新增玩法须独立扩展合同和 Handler | 文件阅读、照片观察、分类和证据板的锁定/完成条件 |
| `imaret.cost=2`，选择另耗 0–2 个故事分钟，initial_minutes=6 | 故事分钟为整数状态；保持累计规则，超时按原先 `elapsed > initial_minutes` 判断 | 不改成真实倒计时，不因节点运行时间改变故事结果 |
| JSON 中部分 effects 未被旧引擎执行，例如 authority | 将“已执行效果”和“仅声明效果”分开列入映射报告 | 兼容迁移不擅自启用旧数据中未生效的新玩法 |
| `scripts/story_import.py` 有专属节点/任务槽映射；旧 SQL 有默认 approved | 新装配器不依赖旧映射；旧标签迁移为 legacy，缺审核依据则 pending | Demo 可作为内部参考；不能据旧标签自动批准新内容包发布 |
| 现代照片、虚构账单和证词并存 | 历史主张、现代观察和原创虚构分开存储与展示 | 现代玻璃顶/招牌不成为 1430s 的历史证据 |

Muradiye 的场景排列属于已实现叙事顺序，不自动证明实地通行连续；位置与通行依据仍按 Weng 的资料审核核对。参考 fixture 的合成审核只用于隔离测试，不得导出为正式审批。

## 3. 数据边界与三个包

Python 3.12 起步，FastAPI、Pydantic 2、LangGraph；SQLite 用标准库 Repository 加顺序编号 SQL migration。新增后端不引入 ORM、向量库或消息队列。依赖在首次安装时核对兼容并精确锁定，实际库名与版本以锁文件为准。

业务边界使用 frozen Pydantic DTO/不可变 dataclass，禁止 `dict[str, Any]` 跨模块传递。LangGraph 内部状态可使用有完整字段类型的 TypedDict；适配器入口立即验证成业务对象。JSON 拒绝额外字段和 NaN/Infinity。时间为带时区的 UTC；价格预算为整数微美元，避免浮点累计；坐标不明用 null，不用 0 冒充。

共用类型：

| 类型 | 固定字段与含义 |
|---|---|
| `ArtifactRef` | artifact_id、project_id、kind、schema_version、content_version、sha256；全部非空字符串 |
| `FolderInput` | provider（google_drive/local_manifest）、folder_id、manifest_ref（可空）；URL 在 adapter 转成 provider+稳定 ID，不以目录名作 ID |
| `ProjectRequirements` | scope_site_ids（可空，索引后补齐）、languages（P0 为 en/zh）、target_story_minutes（可空正整数）、theme_brief、accessibility_requirements、distribution_scope（internal_preview/public）；新范围经版本化更新 |
| `SourceLocator` | source_id、source_version、file_sha256、page_index（PDF 从 0 起）、printed_page（可空文本）、paragraph_or_region（可空文本）；至少一个可定位原文的位置 |
| `EvidenceRequest` | request_id、project_id、candidate_id、question、reason、affected_ids、existing_source_ids、required_evidence；不得含自授批准指令 |
| `ValidationIssue` | code、severity（blocking/warning）、owner（evidence/narrative/assembly/runtime）、artifact_id、json_pointer、message、remediation |
| `ReviewDecision` | decision_id、gate、target_id、target_version、target_hash、decision（approved/changes_requested/rejected）、reason、actor_id、created_at；actor 来自认证上下文 |
| `NodeResult[T]` | outcome（ok/research_required/changes_required/no_feasible_story）、output_refs、issues、next_action；下一步由合法路由表验证，不能由模型任意指定 |

包分为内容 payload、hash 与独立审核记录：hash 计算对象为完整 payload（含 schema/内容版本及依赖 hash），不含 hash 自身、审核记录、存储路径或获取时间等非内容元数据。JSON 以固定键排序、UTF-8、无额外空白序列化；实现与样例共用一个 CanonicalSerializer。二进制文件 hash 使用原始字节。新版本不覆盖旧 payload。

| 包 | payload 必备字段 | 对外完成条件 |
|---|---|---|
| `EvidencePackage` | project_id、source_folder_id、scope、sources、sites、claims、assets、spatial_edges、coverage、unresolved_items | 被故事引用的关键事实/媒体/空间/许可逐项批准；包审核清单包含所需条目的当前版本/hash |
| `NarrativePackage` | project_id、evidence_package_hash、candidate_id、protagonist、characters、routes、scenes、props、decisions、endings、initial_state、locales、fiction_notice | 事实引用有效；规则可执行；故事整体终审绑定完整 payload hash |
| `RuntimePackage` | project_id、package_id、schema_version、content_version、runtime_compatibility、evidence_package_hash、narrative_package_hash、game、media_manifest | 装配检查通过；发布确认绑定该包 hash 与当前终审记录 |

候选索引是独立 `SourceIndex`，含来源引用、候选地点/主张和各自状态；Discovery 读取它，不能要求先有已批准 EvidencePackage。正式故事生成才要求批准证据。`qualified` 主张仅能采用人工明确批准的限定措辞；conflicting/insufficient 不作为确定史实或答案。

每个 Claim 包含稳定 ID、version、text、site/structure ID、time_scope、content_kind、support/refute SourceLocator、judgment、reason、approved_wording（可空）。每个 Asset 包含稳定 ID、version、原图/衍生图 hash、source locator、site/structure、mapping_state、rights_state、allowed_uses、rights_basis、alt_text；不同用途分别核对授权。每个空间边包含 from/to site、position/通行来源、核验状态、距离/耗时（可空）。Coverage 为范围内每个地点记录 main/optional/deferred/excluded 及理由。

## 4. 图状态、节点与路由

`WorkflowState` 只保存短状态和 ArtifactRef，不放 PDF 全文、照片字节或完整聊天。必备字段如下：

| 字段 | 类型 / 初始值 |
|---|---|
| schema_version、project_id、run_id、graph_version、policy_ref | 非空字符串/ArtifactRef；创建后固定 |
| revision | int，初始 0；每次状态变更递增，用于并发校验 |
| node | NodeName；初始 register_project |
| status | RunStatus；初始 queued |
| index_ref、evidence_ref、narrative_ref、runtime_ref | ArtifactRef 或 null |
| selected_candidate_id、pending_review_id、pending_request_id | str 或 null |
| research_rounds_started、narrative_revisions_started | int，初始 0 |
| budget_id、usage_ledger_id | 非空字符串，消耗事实来自业务账本，不信任模型报告 |
| dirty_target_ids | 排序且去重的稳定 ID 列表；初始空 |
| last_error | WorkflowError DTO 或 null |

RunStatus 固定为 `queued / running / waiting_review / needs_changes / needs_review / budget_exhausted / blocked / failed / cancelled / no_feasible_story / published`。node 表示阶段，status 表示是否运行/等待/停止；不再把 drafting/generating 等同义阶段混入 status。UI 可显示“等待资料审核”等组合文本。终态为 published/cancelled/no_feasible_story；blocked/failed/预算耗尽可经显式恢复继续，不偷偷新建 run。

| NodeName | 输入 → 输出 | 正常下一步 |
|---|---|---|
| register_project | FolderInput + ProjectRequirements + PolicyRef → project/run/budget 记录 | inventory_sources |
| inventory_sources | 文件夹快照 → SourceManifest（含下载/失败状态） | extract_candidates |
| extract_candidates | manifest + 原文 → SourceIndex（只抽取相关候选，保留覆盖清单） | discover_story |
| discover_story | SourceIndex + 要求 → CandidateSet（2–3 个方向与维度分数/缺口） | select_candidate |
| select_candidate | CandidateSet + 版本化政策 → SelectedCandidate | research_selected_direction |
| research_selected_direction | SelectedCandidate + EvidenceRequests + 现有来源 → EvidencePackage 候选、支持/反证与缺口 | evidence_review |
| evidence_review | 当前 evidence 候选 + 所需引用清单 → 审核 interrupt；保存决定后重读业务审批 | draft_narrative 或退回 research_selected_direction |
| draft_narrative | 批准证据 + 选中方向 + 锁定字段/反馈 → NarrativePackage 候选或 EvidenceRequest | narrative_review；有新事实需求则回 research_selected_direction |
| narrative_review | 故事候选 + 自动内容检查报告 → 终审 interrupt | assemble_package 或退回 draft_narrative/研究 |
| assemble_package | 已批准两包 + runtime 版本 → RuntimePackage 候选 | validate_package |
| validate_package | 候选包 + 规则解释器 → ValidationReport | publish_review；失败按责任归属返回 |
| publish_review | runtime hash + 检查报告 + 审批快照 → 发布 interrupt | publish_package 或退回指定责任节点 |
| publish_package | 当前有效发布决定 + 不可变包 → ReleaseRecord + 当前发布指针 | published |

Discovery 明确标为假设阶段；方向选择由 select_candidate 的确定性政策执行。缺少可追溯证据线索、核心图片可辨认性或基本空间方案的方向不能直接进入正式生成，可生成缺口请求。材料暂不可访问为 blocked；研究预算用完为 budget_exhausted；研究上限内所有方向均不可行为 no_feasible_story，并给各候选理由。部分文件失败可继续盘点，但不可静默当作“所有材料已读完”。

已存在有效索引/证据包时，register_project 校验来源、范围、版本、审批和政策适用性后记录复用决定：索引可跳到 Discovery，带选中方向的已批准证据可跳到 draft_narrative。无选中方向则先 Discovery，并复核已有证据是否覆盖新方向。任何入口都不能绕过正式生成的证据检查。

## 5. 审核、暂停与权限

三个固定审核 gate：evidence、narrative、publication。审核请求先以唯一 pending_review_id 和 target hash 存业务库，再进入专用 interrupt 节点；interrupt 前不做模型调用或发布。恢复使用相同 thread_id；P0 规定 thread_id 等于 run_id，审核节点读取已保存决定并验证 target hash 与当前状态一致。

LangGraph 恢复时可能从被中断节点开头重新执行，不能假设从某一行继续。因此，业务写入要幂等、模型成果要先持久化、interrupt 位置保持稳定。暂停跨版本期间不修改原图结构；graph_version 不兼容时标 blocked，走显式迁移，不直接用新图解释旧 checkpoint。[官方中断说明](https://docs.langchain.com/oss/python/langgraph/interrupts)、[持久化说明](https://docs.langchain.com/oss/python/langgraph/persistence)。

P0 为单应用实例、单图执行者；同项目同一时间一个可写 run，重复启动返回现有 run/409，不排第二条制作流水线。API 只校验并保存命令，worker 顺序消费；进程重启从业务命令记录与 checkpoint 恢复。数据库事务不跨模型/网络调用；checkpoint 与业务库分别存储，靠业务幂等记录协调，不假设两库一次提交。

审核写入与恢复命令在同一业务事务中保存。命令重放核对 decision_id、target hash 和 expected revision；过期决定返回 REVIEW_STALE。人的批准不能由模型 DTO/普通状态更新写入。启动默认只绑定本机；编辑 API 仍需认证，操作者权限在服务端配置，前端不能自报 actor。测试模拟身份仅在显式 test 配置可用。

Weng/Matt 可对具体条目提出修改，其他已批准条目保持原版本；所有被最终故事引用的必审条目满足条件才放行。故事内容发生任何变化都需要新的整体终审；未受影响条目审批可以复用，但不能把旧故事总审批套到新 hash。发布前还须重新检查来源停用与许可变化。

## 6. 重试、局部返工和 token 账本

三种计数彼此独立：研究轮（同一问题集合的一次定向研究，最多 2 轮）、叙事修订轮（初稿之后的自动修改，最多 2 轮）、外部调用尝试（每次实际请求）。初稿不占修订轮；每轮开工先持久化 round_id，恢复同一轮不再次加一。换方向、换来源不清零。

同轮可包含多个查询/文件/章节，它们各有 ExecutionKey。技术失败且输入未变，继续该轮未完成步骤；新问题或新的修改要求是新一轮。达到轮数上限转 needs_review；费用/时间/调用预算上限转 budget_exhausted。人工也不能靠重复 resume 重置上限；额度调整单独记录授权与新上限，已花费用保留。

BudgetPolicy 必填 max_model_requests、max_input_tokens、max_output_tokens、max_search_requests、max_fetch_requests、max_active_seconds、max_cost_microusd；没有预算或价格依据就不付费运行。调用前预留保守的最大可能消耗，返回后结算并释放剩余；上下文超限先用检索选取相关原文，不能截断必需证据或自动增加预算。价格、模型、采样参数及 Skill hash 固定到 run，禁止静默换供应商。

ExecutionKey = project_id + node + unit_id + 输入 hash + Skill/Schema/政策/模型配置 hash。步骤状态为 pending/running/succeeded/retryable_failed/unknown_outcome/failed。成功结果持久化后重放直接读取；缓存只在同项目、相同权限与依赖版本内复用。阶段内按文件、研究问题或故事场景保存成果，不用一个大调用生成整份游戏后才落盘。

| 失败类别 | 首期行为（数值为可配置初始值） |
|---|---|
| 文件解析或连接建立前的临时故障 | 同小步骤最多 2 次总尝试；指数退避且占用原活动预算；确定不支持的格式不重试 |
| 模型输出 schema 错误 | 先机械检查；最多 1 次有界格式修复/重新调用，并计入请求、费用；不允许改事实或绕审批 |
| 超时/断线，远端可能已执行 | unknown_outcome；先查供应商请求记录/幂等支持，无结果则 needs_review；不自动重复付费 |
| 401/403、模型不可用、无价格/预算 | 明确原因并 blocked；不盲目重试/切模型 |
| 429/服务临时失败 | 仅在响应明确该调用未产出/无不明副作用时按 provider 策略最多 2 次总尝试；不据 429 自判余额不足 |
| 业务证据/任务不成立 | 退回责任模块的指定条目，受研究/修订轮限制；不是网络重试 |
| 取消 | 不启动新调用；清理资源；已发送调用记录 actual/unknown 消耗；不可撤销的成功发布保留为 published |

初始超时建议：单次页面访问 30 秒、模型调用 120 秒；部署前按真实 provider 测量调整。这些值不是 SLA，不能突破活动总预算。人的等待不消耗活动时间；进程异常导致时间/费用不明时保留 unknown，不补零。

依赖表记录 source fragment/asset/claim → scene/task → narrative/package。某条证据改变：先列出所有关联场景，保留无关内容；修订前还要检查跨场景人物状态、时间、信息获得与结局因果闭包。无法证明独立时扩大到相关章节/整篇内容审查，不能机械承诺“只改一个场景”。重装配可以整体重建（便宜的确定性过程），LLM 只重做受影响内容。

## 7. 持久化合同

业务库 `var/editorial.sqlite3`，checkpoint `var/checkpoints.sqlite3`，不可变产物 `var/artifacts/`，发布目录 `var/releases/`；均不入 Git。现有 `data/pastport.sqlite3` 是 legacy 参考，不能 `--replace` 覆盖新编辑库。正式迁移先备份并记录 hash；测试用临时目录。固定 SQLite 外键、WAL、短事务，写锁等待初始 5 秒。

| 表（新编辑库） | 必要唯一键/字段 |
|---|---|
| projects | project_id PK、source_provider、source_folder_id、scope_hash、name；provider+folder_id 唯一；变更范围显式创建版本，不误建新项目 |
| source_versions / source_fragments | source_id+version；project_id、origin、URL、file hash、解析/许可状态；片段有 locator、text/hash |
| claim_versions / asset_versions / spatial_versions | 对象 ID+version；project_id、payload/hash；不覆盖旧版本 |
| artifacts / artifact_dependencies | artifact_id PK、kind、project_id、版本、hash、path；consumer_id/version→dependency_id/version/hash |
| review_requests / review_decisions | request_id；gate/target/hash；decision_id 唯一；理由、真实 actor、时间，追加写入 |
| workflow_runs / execution_units | run_id；graph/policy refs、node/status、revision、取消标记；run+ExecutionKey 唯一，保存产物引用和失败状态 |
| commands / run_events | command_id 唯一、run、expected revision、payload hash、pending/applied/failed；事件保存序号、类型、原因和操作者 |
| budgets / usage_ledger | run 预算、预留/已结算/未知费用、round ID；每次请求 operation_id 唯一，记录模型配置、usage、供应商 request ID |
| releases | project_id+release_id；runtime hash、审核 ID、状态；项目发布指针用 expected_old_release 做并发比较 |

JSON payload 仅允许经版本化 Schema 校验后存储；关键关联、状态、hash 和唯一性用 SQL 列/约束保障。源文、内容审批、费用账本和 checkpoint 各有职责，不拿日志/模型文本充当审批事实。

## 8. API 与最小制作工作台

FastAPI `/api/v1`；写操作均要求认证和 Idempotency-Key，相同 key+body 返回原结果，相同 key 不同 body 返回 409。涉及现有项目/run/审核版本的写操作附 expected_revision/target_hash。只读接口同样校验项目权限；内容公开读取只使用已发布路径。

| 接口 | 输入要点 / 结果 |
|---|---|
| POST /projects | provider、folder_id、name、requirements → 201 ProjectView；重复目录返回已有项目 |
| POST /projects/{id}/runs | budget_policy、policy_ref、可选可复用 ArtifactRef → 202 RunView |
| GET /runs/{id}、GET /runs/{id}/events?after= | 当前节点/状态/缺口/计数/产物链接/可执行动作；事件游标轮询，P0 不要求 SSE |
| GET /runs/{id}/reviews | 待审内容、原文定位、模型判断/理由、版本/hash 和锁定字段 |
| POST /runs/{id}/review-decisions | request_id、逐项/整体决定、target hash、reason、expected_revision → 保存并排队自动续跑 |
| POST /runs/{id}/revisions | 反馈、受影响 ID、锁定字段、expected_revision → 修改请求；新事实回资料模块 |
| POST /runs/{id}/resume | 可恢复错误/补配置/确认处理决定 → 202；不能替代任何审核决定或清零预算 |
| POST /runs/{id}/cancel | reason、expected_revision → 请求取消 |
| GET /runs/{id}/artifacts、GET /artifacts/{id} | 按权限读取不可变产物及检查报告，不返回任意本地路径 |
| POST /projects/{id}/rollback | target_release、expected_old_release、reason → 已发布且仍合规/兼容的旧版；新建操作记录，不改旧包 |
| GET /public/projects/{id}/release | 当前发布 manifest；玩家取固定 release_id 资源，草稿不在公开目录 |

错误统一 ErrorEnvelope：code、message、retryable、owner、field_path、safe_details、run_id（可空），无堆栈/密钥/原始模型请求。校验 422、缺身份 401、无权限 403、资源不存在 404、状态/审批过期 409、预算/不可恢复业务限制 409，第三方不可用 502/503；异步节点失败显示在 RunView，不冒充成功。

最小原生 JS 工作台只有：项目/来源导入状态、运行时间线与费用、证据逐项审核、故事预览/修改/锁定、包检查与发布确认。API 完成同时给可操作页面，不能交付一条必须手工改 DB 才能继续的流水线。开发态真人账户与权限配置示例不包含实际口令。

## 9. 通用玩法合同与一个真实映射例

玩家状态：project_id、release_id、chapter_id、schema_version、current_scene_id、elapsed_minutes、observations（scene→spot ID 集合）、completed_task_ids、decisions（decision→option）、inventory（prop ID 集合）、assignments、selected_evidence、variables、ending_id。variables 只允许已声明的 bool/int/str；存档键包含项目和发布版本。跨版本存档默认要求重新开始；显式迁移需独立映射/验证，不自动忽略版本错误。

任务用 discriminated union：document（required_prop_ids）、inspect（asset_id、spots、required_spot_ids）、inspect-sort（观察要求加 cards/destinations/answer_map）、caseboard（required_prop_ids 与 exact_set 规则）。热点坐标为原图归一化 0–10000 整数，x/y 都校验范围；每个热点含等效文本按钮。文案只在 locales 中，规则引用稳定 key，不能分别在中英文文件写答案和后果。

条件首期仅 `all / any / not / has_evidence / observed_all / choice_equals / variable_equals / elapsed_gt`，使用有类型参数的树。效果首期 `grant_item / set_variable / set_relationship / add_story_time / unlock_scene / resolve_ending`；关系写到声明的 string variable。每个 rule 有 event、guard、effects、once_key；重复触发不得重复加时间或发物件。游戏动作 event 仅 document_opened/spot_observed/sorting_submitted/board_submitted/option_chosen/task_completed；rule 和 event 不允许包内任意代码。

| Muradiye 具体行为 | 新版包声明 |
|---|---|
| courtyard 已观察 pool | inspect task 完成规则 grant_item(loading-slip)，once_key 为该 task 的完成 ID |
| fountain 选择 witness/help | option_chosen 规则 grant_item(witness)、按选项 add_story_time(2) |
| imaret 观察 star 后允许分类 | sorting 的 guard 为 observed_all(star)；正确答案 grain→store、flour→kitchen；成功 grant_item(reconciliation)，完成只加 2 分钟一次 |
| 最终选择 confess、有/无 witness | 结局表分别匹配 signed-truth/unfinished-truth；同一结果再按 friend 决定关系文本、elapsed_gt(6) 决定服务反馈 |
| erase / accuse | 按数据优先匹配两个结局规则；行为与旧 resolveEnding 对照，不写选项专名到解释器中 |

结局按显式 priority 首个匹配，末尾必须有可解释 fallback；每个结果含 career/friend/service/growth 文案与可声明条件变体。装配器只校验规则与引用，不写这些结果。玩家操作先通过 Handler 校验，再在一份新状态上计算全部效果，成功后一次提交；失败不能留下半次动作。界面加载失败、缺图或保存失败须可见且提供合理的继续/重试操作。

以下是从 courtyard 实际行为抽出的规则片段（字段约定示例，不是完整游戏包；Legacy Adapter 还要补全来源/审批/语言等外层内容）：

```json
{
  "rule_id": "courtyard-task-evidence",
  "event": "task_completed",
  "target_id": "courtyard-inspect",
  "guard": {
    "kind": "observed_all",
    "scene_id": "courtyard",
    "spot_ids": ["pool"]
  },
  "effects": [
    {"kind": "grant_item", "item_id": "loading-slip"}
  ],
  "once_key": "task:courtyard-inspect:completed"
}
```

condition/effect 的 `kind` 为判别字段，target_id 对应事件对象。all/any 带 conditions 数组（至少 1 项），not 带 condition；has_evidence 带 item_id，choice_equals 带 decision_id/option_id，variable_equals 带 name/value，elapsed_gt 带 minutes。grant_item 带 item_id；set_variable/set_relationship 带 name/value；add_story_time 带非负 minutes；unlock_scene 带 scene_id；resolve_ending 带 ending_table_id。未声明 kind、未知 ID、类型不匹配或循环规则均为 blocking，不静默跳过。

## 10. 模型、Skill 与专业政策

ModelGateway 仅暴露 generate(ModelRequest[T])→ModelResult[T]；request 固定 role、SkillRef、input ArtifactRef/相关 SourceLocator、output_schema、model_config、budget reservation、operation_id。result 含强类型输出、usage、provider request ID、明确 finish/error。服务端工具执行经权限验证并入账；模型不直接写数据库或审批。先接 fake gateway，再接一个可配置真实 provider；实际供应商在价格/结构化输出能力实测后决定。

先生成结构与依赖，再按场景生成/修订；每次只带当前目标、相关证据原文、角色状态摘要与前后接口。摘要不能代替核对关键史实的原文。prompt、Skill、政策、模型和 Schema 各有 hash，修改后旧缓存是否适用由依赖规则判断，不靠 Agent 记忆。

| 政策 | 可运行初始值 | 后续负责人 |
|---|---|---|
| 候选评分 | 证据、可视觉化、人物冲突、任务可解性、空间连续性各 0–4 等权；缺口数单列；先排除硬门槛失败，再按分数，平分按稳定 candidate_id | Matt 调评分与样例，Weng 调证据/空间硬门槛；仅为项目初值 |
| 证据判断 | supported/qualified/conflicting/insufficient，附支持/反证和原文；关键条目由人确认 | Weng 调来源等级、冲突与限定表述标准 |
| 叙事检查 | 每个主线任务具线索→推理→人物目标→状态后果；照片实际参与推理；虚构边界；路线连续；能通关 | Matt 调趣味性、节奏、角色成长与提示；不改通用字段权限 |
| 外部研究 | 本库与官方提供优先；缺口触发权威补充；新域名通过可配置访问策略，来源登记后进入同一审批链 | Weng 筛机构与许可，Weijia 实现访问边界 |

外部 SearchGateway/SourceReader 返回 SearchHit/SourceDocument DTO；候选片段不等于已读原文。只读允许的 HTTP(S) 公网来源，校验域名、重定向和解析后 IP，阻止本机/私网；文件限制 400 MiB、HTML 单页 5 MiB 为初值，流式下载可继续，全部计预算。不得绕登录/付费限制；不可获取来源记 inaccessible，找合法替代来源。PDF 无可靠文本则 needs_ocr，未接 OCR 时保留缺口而非伪造已解析结果。

## 11. 装配与发布的机械规则

装配器消费批准快照，把事实出处和游戏数据分开放入包，复制获准衍生媒体，校验路径/hash、locale keys、引用、Handler 版本、审批绑定和路线状态。错误码固定前缀 EVIDENCE_/NARRATIVE_/PACKAGE_/RUNTIME_，对应唯一责任模块；同时输出精确 JSON Pointer。路线资料不全可内部预览，但不能发布为已核验的连续路线。

发布使用项目锁，先完整写不可变 release 目录，再用业务库事务比较旧指针并切换新版本；写文件成功但指针未切换仅为未发布孤立产物，可恢复/清理。发布操作 ID 唯一；指针已指向同 release 时视为已完成。包写入失败保留旧版本，回滚重新核许可与兼容。公开资源统一由获准 release 路径提供，不能把 var 或 sources 整体作为静态目录。

## 12. Code Agent 实施任务与验收

每项以单一目标提交；实际用户授权后才 push。共同质量遵循 [CI 规范](../engineering/ci-and-copilot.md)。下表是待完成的任务，不表示当前检查已存在。

| 任务 | 相关路径/产物 | 必须证明什么 |
|---|---|---|
| T1 冻结 Schema 与参考映射 | src/pastport/domain、schemas、tests/fixtures/reference；Muradiye Legacy Adapter 设计与映射清单 | 三包和节点 DTO 合法/非法样例；现有四种任务和选择都能表达；来源和审批不得伪造继承 |
| T2 建编辑库与用例 | ports/repositories、adapters/sqlite、migrations、application/reviews | 临时库迁移；旧库不变；事务、项目隔离、不可变版本、审核过期/权限错误明确 |
| T3 图与恢复骨架 | workflow、application/runner、fake ModelGateway | 不依赖真实模型跑完三次审核；进程重启恢复同 run；成功小步骤不再调用 fake；超限/取消不清计数 |
| T4 最小工作台与命令恢复 | api、原生编辑页面、认证/命令消费 | 从页面创建到审核/预览/发布；重复/过期/越权命令被正确处理；不手改库续跑 |
| T5 资料与故事真实接入 | evidence/narrative Skill、来源/模型 adapters、政策配置 | 从官方材料索引、Discovery 到定向外部补证；原文定位/许可/候选理由可查；真实费用与未知项有记录 |
| T6 通用运行底座与装配 | application/assembly、prototype 共享 interpreter/render、legacy adapter | Muradiye 现有三次选择共 12 种组合及时间边界结果保持；所有证据发放由包驱动；中英共享规则、刷新不串档 |
| T7 第二官方目录验收 | 新项目数据包、运行报告、人工试玩记录 | 同一图/Schema/装配器/底座生成新游戏；无第二遗址专用 if；缺口真实报告；达到 PRD 的可玩与证据门槛 |

T1→T2→T3 后可做 T4/T5/T6，各任务通过固定合同集成后做 T7。短期演示可先让 fake 运行包展示界面，但必须标“模拟生成”，不把 fake 通过冒充真实资料生产。新增框架骨架完成与新遗址完整可玩分开验收。

关键反例必须覆盖：来源 hash 变化使审批过期；错误图片/未授权资产被拒；文档中的现代特征不被当历史事实；节点/进程中断后已完成小步骤不重复；研究和修订总次数准确；发布响应未知不重复副作用；跨项目不可读草稿/存档；帮助证人的收益和耗时都实际改变后果；局部改稿不破坏其他场景的信息/时间因果。真人试玩单列，不由模型自评分代替。

## 13. 开工前还需输入什么

不阻塞 T1–T4/T6：第二目录最终选择、外部来源正式清单、故事评分细化、最终模型、长期预算、真实账号。这些使用明确 test fixture 或待配置状态。

阻塞首次付费 T5：可用供应商凭据、价格依据、调用预算和允许访问的来源策略；阻塞正式发布：真实审批身份、有效证据/照片授权/空间依据、终审及发布决定。Code Agent 不得猜密钥、自动购买额度、将测试批准转成正式审批，或因为未配模型而给 fake 成果标真实。
