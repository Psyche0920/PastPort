# Workflow 实现合同：以 Muradiye 为参考

状态：首期工程基线；本文定义待实现行为，不表示代码已经完成。本文落实现有 PRD，不扩展产品范围。正文用中文解释，代码、字段、API、错误码和 Skill 输出使用英文。团队分工沿用 PRD：Weng 负责证据，Matt（Mert）负责故事与玩家体验，Weijia 负责整合；对外姓名仍需团队核对。

按任务读取：T1 看 §3/9/14/15；T2 看 §5/7/8；T3 看 §4/6/15–17；T4 看 §8；T5 看 §10/16/18 与对应 Skill；T6 看 §9/11；T7 看 §12 和 PRD 验收。不要求每次把整篇加入模型上下文。

## 1. 阅读与实现边界

- 产品目标、四模块边界与内容审核要求见 [PRD](PRD.md)；制作方法与资料补证见[参考依据](REFERENCES.md#5-muradiye-抽象样本与制作方法)。本文唯一维护工程字段、节点协议、恢复计数和实施任务；Skill 调用与质量协议已合并为 §14–18。
- 首先实现一个可保存、可审核、可恢复的纵向流程，再接真实模型与外部研究。Muradiye 用于兼容性和规则对照；第二个官方同层级文件夹用于第一次新项目完整制作验证。
- 冻结 ID、版本/hash、审批权限、节点协议、状态和隔离规则。Weng/Matt 后续通过版本化政策与 Skill 调整来源标准、评分、任务与文案；结构改变走 Schema 版本升级。
- 一次只实现第 12 节的一个任务。Coding Agent 任务单只带目标、相关节号、输入样例、受影响路径和验收；不重复加载整份对话或全部资料。

## 2. Muradiye 抽象参考与兼容目标

下表参考固定为 [Muradiye 样本提交](https://github.com/Psyche0920/PastPort/tree/656f2ba81875855e51e12fab3862629d120c6096)，来源分支为 demo-muradiye；路径均不在 main 中。后续分支更新不自动改变本合同依据。更新参考版本须显式审查映射差异，不能无记录跟随分支最新状态。未来只导入必要且获准的小型 fixture，原始 Demo 不复制回来。

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
| `EvidenceRequest` | request_id、project_id、purpose（scope_gap/direction）、candidate_id、question、reason、affected_ids、existing_source_ids、required_evidence；scope_gap 的 candidate_id 必须为 null，direction 必须引用已选方向；不得含自授批准指令 |
| `RouteRecord` | route_id、project_id、candidate_id、version、scope_hash、ordered_places（有序 site_id/building_id）、edge_refs、entry/exit refs、source_refs、unknowns；按 ArtifactRef 保存不可变内容与 hash，审批单独保存 |
| `ValidationIssue` | code、severity（blocking/warning）、owner（evidence/narrative/assembly/runtime）、artifact_id、json_pointer、message、remediation |
| `ReviewDecision` | decision_id、gate、target_id、target_version、target_hash、decision（approved/changes_requested/rejected）、reason、actor_id、created_at；actor 来自认证上下文 |
| `NodeResult[T]` | outcome（ok/research_required/changes_required/blocked/no_feasible_story）、output_refs、issues、next_action；由应用在验证/保存 SkillResult 后生成，下一步由合法路由表决定，不能由模型指定 |

包分为内容 payload、hash 与独立审核记录：hash 计算对象为完整 payload（含 schema/内容版本及依赖 hash），不含 hash 自身、审核记录、存储路径或获取时间等非内容元数据。JSON 以固定键排序、UTF-8、无额外空白序列化；实现与样例共用一个 CanonicalSerializer。二进制文件 hash 使用原始字节。新版本不覆盖旧 payload。

| 包 | payload 必备字段 | 对外完成条件 |
|---|---|---|
| `EvidencePackage` | project_id、source_folder_id、scope、sources、sites、claims、assets、spatial_edges、route_refs、coverage、unresolved_items | 被故事引用的关键事实/媒体/空间/许可及选中路线逐项批准；包审核清单包含所需条目的当前版本/hash |
| `NarrativePackage` | project_id、evidence_package_hash、candidate_id、protagonist、characters、routes、scenes、props、decisions、endings、initial_state、locales、fiction_notice | 事实引用有效；规则可执行；故事整体终审绑定完整 payload hash |
| `RuntimePackage` | project_id、package_id、schema_version、content_version、runtime_compatibility、evidence_package_hash、narrative_package_hash、game、media_manifest | 装配检查通过；发布确认绑定该包 hash 与当前终审记录 |

候选索引是独立 `SourceIndex`，含来源引用、候选地点/主张和各自状态；Discovery 读取它，不能要求先有已批准 EvidencePackage。正式故事生成才要求批准证据。`qualified` 主张仅能采用人工明确批准的限定措辞；conflicting/insufficient 不作为确定史实或答案。

每个 Claim 包含稳定 ID、version、text、site/structure ID、time_scope、content_kind、support/refute SourceLocator、judgment、reason、approved_wording（可空）。每个 Asset 包含稳定 ID、version、原图/衍生图 hash、source locator、site/structure、mapping_state、rights_state、allowed_uses、rights_basis、alt_text；不同用途分别核对授权。每个空间边包含 from/to site、position/通行来源、核验状态、距离/耗时（可空）。Coverage 唯一枚举为 main（主线）/optional（支线）/deferred（后续路线）/excluded（不纳入），每项附理由。

### 3.1 路线的产出、审核与失效

Discovery 为候选方向提出 RouteProposal，不宣称已核验；资料模块将所选序列及地点、入口、通行依据整理为 RouteRecord，保存候选 artifact。Weng 在现有 evidence gate 审核该记录的具体版本/hash，不新增路线审核阶段。通过后，审核服务把该 ArtifactRef 写入 WorkflowState.approved_route_ref，并使其成为 EvidencePackage 的批准依赖；NarrativePackage.routes 绑定同一版本，装配时不自行换顺序。

正式 draft 前，程序核对路线属于当前项目/选中方向及范围，所有必要地点/入口/通行边有依据且审批仍有效。单建筑内部路线也须说明所用地点与关系；不要求 GPS、精确米数或不存在的移动。非空间过场明确标记，不可用来掩盖实际跳跃。未知的可选耗时可保留 null，必要的连通关系未知则不放行正式 draft。

顺序、地点、入口、必要通行边或其支持证据变更时，创建新版 RouteRecord，旧 approved_route_ref 不再适用于新版本；暂停受影响故事的正式生成/发布，回 evidence gate 核实新记录。再按地点、任务和跨场景因果检查受影响故事，重新终审和装配。旧批准只保留在原快照中，不覆盖；与路线无关的其他条目不重做。

## 4. 图状态、节点与路由

`WorkflowState` 只保存短状态和 ArtifactRef，不放 PDF 全文、照片字节或完整聊天。必备字段如下：

| 字段 | 类型 / 初始值 |
|---|---|
| schema_version、project_id、run_id、graph_version、policy_ref | 非空字符串/ArtifactRef；创建后固定 |
| revision | int，初始 0；每次状态变更递增，用于并发校验 |
| node | NodeName；初始 register_project |
| status | RunStatus；初始 queued |
| index_ref、evidence_ref、narrative_ref、runtime_ref | ArtifactRef 或 null |
| approved_route_ref | ArtifactRef 或 null；初始 null，仅审核服务在 evidence gate 批准当前 RouteRecord 后写入 |
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
| discover_story | SourceIndex + 要求 → CandidateSet（方向与维度分数/缺口） | 有候选到 select_candidate；无候选且有具体缺口到 research_evidence(scope_gap) |
| select_candidate | CandidateSet + 版本化政策 → SelectedCandidate | research_evidence(direction)；足够且有效的既有资料可复用，不能绕证据审核 |
| research_evidence | SourceIndex + EvidenceRequest + 现有来源；direction 另需 SelectedCandidate → Findings、索引更新及必要的证据/路线候选 | scope_gap 更新索引后回 discover_story；direction 到 evidence_review |
| evidence_review | 当前 evidence/RouteRecord 候选 + 所需引用清单 → 审核 interrupt；保存决定后重读审批并生成 approved_route_ref | 必审内容及路线均通过到 draft_narrative；否则定向补证或等待人决定 |
| draft_narrative | 批准证据 + approved_route_ref + 选中方向 + 锁定字段/反馈 → NarrativePackage 候选或 EvidenceRequest | narrative_review；有新事实需求则回 research_evidence(direction) |
| narrative_review | 故事候选 + 自动内容检查报告 → 终审 interrupt | assemble_package 或退回 draft_narrative/研究 |
| assemble_package | 已批准两包 + runtime 版本 → RuntimePackage 候选 | validate_package |
| validate_package | 候选包 + 规则解释器 → ValidationReport | publish_review；失败按责任归属返回 |
| publish_review | runtime hash + 检查报告 + 审批快照 → 发布 interrupt | publish_package 或退回指定责任节点 |
| publish_package | 当前有效发布决定 + 不可变包 → ReleaseRecord + 当前发布指针 | published |

Discovery 明确标为假设阶段；方向选择由 select_candidate 的确定性政策执行。缺少可追溯证据线索、核心图片可辨认性或基本空间方案的方向不能直接进入正式生成，可生成缺口请求。材料暂不可访问为 blocked；研究预算用完为 budget_exhausted；研究上限内所有方向均不可行为 no_feasible_story，并给各候选理由。部分文件失败可继续盘点，但不可静默当作“所有材料已读完”。

**无方向时的补证入口：** Discovery/索引发现可定位的范围内缺口（如某建筑功能的原文缺页或候选地点身份未明），以 purpose=scope_gap、candidate_id=null 进入同一个 research_evidence 节点；不伪造故事方向。问题须指向当前官方项目的资料/地点，禁止无目标全网找灵感。新增资料只更新候选索引，不自动获批，完成后返回 Discovery；有方向后以 purpose=direction 做定向核实。两种研究合计仍为每 run 最多 2 轮，共用所有调用和费用上限。

范围补证后仍无候选且没有可执行缺口时，材料不可访问/缺配置则 blocked；可行性依据不足则 needs_review；只有满足既定停止条件才 no_feasible_story。若研究轮数已耗尽，但所选方向所需依据和路线记录可从已存成果完整生成，允许确定性整理后交 evidence gate，不增加研究调用；否则 needs_review，不以选中方向为由重置轮数。

已存在有效索引/证据包时，register_project 校验来源、范围、版本、审批和政策适用性后记录复用决定：索引可跳到 Discovery；只有证据包、所选方向及其 RouteRecord 的审批仍有效且版本一致，才恢复 approved_route_ref 并跳到 draft_narrative。路线审批缺失或过期时回 evidence_review；无选中方向则先 Discovery，并复核已有证据是否覆盖新方向。任何入口都不能绕过正式生成的证据检查。

## 5. 审核、暂停与权限

三个固定审核 gate：evidence、narrative、publication。审核请求先以唯一 pending_review_id 和 target hash 存业务库，再进入专用 interrupt 节点；interrupt 前不做模型调用或发布。恢复使用相同 thread_id；P0 规定 thread_id 等于 run_id，审核节点读取已保存决定并验证 target hash 与当前状态一致。

LangGraph 恢复时可能从被中断节点开头重新执行，不能假设从某一行继续。因此，业务写入要幂等、模型成果要先持久化、interrupt 位置保持稳定。暂停跨版本期间不修改原图结构；graph_version 不兼容时标 blocked，走显式迁移，不直接用新图解释旧 checkpoint。[官方中断说明](https://docs.langchain.com/oss/python/langgraph/interrupts)、[持久化说明](https://docs.langchain.com/oss/python/langgraph/persistence)。

P0 为单应用实例、单图执行者；同项目同一时间一个可写 run，重复启动返回现有 run/409，不排第二条制作流水线。API 只校验并保存命令，worker 顺序消费；进程重启从业务命令记录与 checkpoint 恢复。数据库事务不跨模型/网络调用；checkpoint 与业务库分别存储，靠业务幂等记录协调，不假设两库一次提交。

审核写入与恢复命令在同一业务事务中保存。命令重放核对 decision_id、target hash 和 expected revision；过期决定返回 REVIEW_STALE。人的批准不能由模型 DTO/普通状态更新写入。启动默认只绑定本机；编辑 API 仍需认证，操作者权限在服务端配置，前端不能自报 actor。测试模拟身份仅在显式 test 配置可用。

Weng/Matt 可对具体条目提出修改，其他已批准条目保持原版本；所有被最终故事引用的必审条目满足条件才放行。故事内容发生任何变化都需要新的整体终审；未受影响条目审批可以复用，但不能把旧故事总审批套到新 hash。发布前还须重新检查来源停用与许可变化。

## 6. 重试、局部返工和 token 账本

三种计数彼此独立：研究轮（同一问题集合的一次范围补证或定向研究，两类合计最多 2 轮）、叙事修订轮（初稿之后的自动修改，最多 2 轮）、外部调用尝试（每次实际请求）。初稿不占修订轮；每轮开工先持久化 round_id，恢复同一轮不再次加一。换方向、换来源不清零。

同轮可包含多个查询/文件/章节，它们各有 ExecutionKey。技术失败且输入未变，继续该轮未完成步骤；新问题或新的修改要求是新一轮。达到轮数上限转 needs_review；费用/时间/调用预算上限转 budget_exhausted。人工也不能靠重复 resume 重置上限；额度调整单独记录授权与新上限，已花费用保留。

问题集合在 round 开始时保存不可变 manifest；其内预先授权的查询/场景子步骤属于同一轮。执行中发现新的实质问题不得偷偷追加到已冻结集合绕过轮数，生成新的 EvidenceRequest/RevisionRequest；如果只为既定问题补抓一个来源，仍可在该轮的工具预算内进行，须保留关联原因。

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

### 6.1 必须实现的崩溃恢复顺序

| 崩溃位置 | 恢复时的业务依据 | 允许的动作 |
|---|---|---|
| 审核决定与 resume 命令已提交，图尚未恢复 | 已存 decision_id、target hash、pending command 与 run revision | 消费原命令；同一决定/请求重放返回已存结果，不因已应用导致永久 REVIEW_STALE，也不再次写审批 |
| 节点产物已提交，checkpoint 未更新 | succeeded ExecutionKey 和完整产物 hash/依赖 | 节点可能重进，但读取成功结果并重新提交图状态，不再调用模型 |
| 已发模型请求，未保存响应 | 请求/预留账本、provider request ID（如有） | 标 unknown_outcome，查询供应商记录或交人；无确认不自动再次付费，预留不能当零费用释放 |
| 响应与 usage 已保存，节点未结束 | 持久响应/usage、operation_id | 从已存响应做确定性验证/转换；不得再发同一请求；usage 幂等结算 |
| 文件已写但 artifact 记录未提交 | 暂存路径、已知期望 hash、ExecutionKey | 校验后补齐记录或清理暂存再重做廉价确定性步骤；无记录文件不能直接视作已审核产物 |
| release 完整写入但发布指针未切换 | release hash、有效发布决定与 expected_old_release | 幂等完成指针切换；若已切向别的版本则冲突，不覆盖较新发布 |

服务重启先对账 pending/running/unknown 步骤，再调度图。不能只依赖 checkpoint 猜测远端是否执行；也不能因恢复业务事实而跳过 target hash/权限检查。T3 验收必须注入上述故障点并记录外部调用次数，而非只测正常 interrupt/resume。

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

幂等键作用域包含 authenticated actor、project（创建前为 actor）、HTTP method 与标准化 route；重复响应仍检查当前读取权限，不能跨用户/项目用同名 key 取到别人的结果。

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

**三类业务关系独立建模：** source/claim/asset 的证据关系、scene/task/choice/variable 的故事因果关系、site/entrance/edge 的物理邻接关系。彼此通过稳定 ID 引用；LangGraph 另管制作状态。故事选择可以分支并汇合，不代表游客需要跳到远处；“先给父节点再解锁子节点”也不能代替真实路径依据。官方文件夹是项目来源边界，不是固定场景数或一条自动成立的路线。

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

项目 Skill 已编写：[evidence-review](../skills/evidence-review/SKILL.md)、[narrative](../skills/narrative/SKILL.md)；源头、许可边界与遗产系统对照见[参考评估](REFERENCES.md)。这些文件尚未接入运行时。T5 实现 SkillLoader，按固定项目内路径读取入口、验证 mode、记录入口及实际读取 references 的 hash；Graph/模型只能读取服务端批准的引用文件，不能通过模型输出路径读取任意文件。政策版本与 SkillRef 不自动授予工具权限。

本文 §14–18 统一维护各 mode 的必填/可空输入、SkillResult 到 NodeResult/RunStatus 的映射、工具循环和效果验收。T1a 落实样段必需的强类型与 JSON Schema，T1b 随能力接入补齐对应合同；T3 验证控制分支，T5a 验证真实工具与故事效果。不得让 index 等 claim ID、让 Discovery 等已批准路线，或用各 Skill 自造的同义状态直接控制图。

| 阶段 | 加载模式 | 额外模型调用规则 |
|---|---|---|
| 复杂候选抽取 | evidence-review/index | Python 不能可靠处理语义时按需调用；普通文件清点不调用 |
| 方向发现 | narrative/discover | 读取带状态的索引，返回假设/缺口 |
| 定向补证/资料判断 | evidence-review/research 或 review | 同批产出核查理由，不为每条记录重复装入全库 |
| 正式起草/局部修订 | narrative/draft 或 revise | 只用批准快照；锁定字段与因果闭包进入请求 |
| 三个人审节点 | 不默认加载新模型 | 展示已有理由、自动报告和预览；不因为叫 review 就再付费调用一遍 |
| 按需专业复审 | 对应 Skill 的 review | 只在有具体疑点/改动时调用，计原预算；不默认增加第三个 Agent/模型 |

研究模式的 ModelGateway 输出是 `SkillResult[EvidenceFindings]`，可携带类型化 ToolRequest；应用内 ToolExecutor 分别调用 SearchGateway/SourceReader 并返回 ToolResultRef。每次生成或工具调用都是可持久化小步骤，共用现有 ExecutionKey/预算/取消/恢复规则；不用给主图再增加一个总控 Agent，也不把“允许联网”理解为无界 function-calling 循环。详细执行顺序及停止条件按§16 的调用协议。

每个关键遗产推理任务的 authoring report 保存 heritage_refs、property_used、player_premises、inference、accepted_answer、character_goal、effect_ids、later_read_points、removal_test/substitution_test；仅用于制作审核，不暴露成玩家填写表单。Mert 以[具体校准范例](../skills/narrative/references/design-calibration.md)检查推理/人物/后果；Weng 以[资料校准范例](../skills/evidence-review/references/review-examples.md)检查事实、时间、图像与许可。只点真实照片领取无关虚构物件不能作为核心遗产推理的通过依据。

源文或关键叙事变更将关联翻译标为 outdated；共享规则不变也须复核对应文案，locale 完整且处于当前版本才能发布。新报告字段按 T1a/T1b 所需范围形成强类型/JSON Schema 并提供合法/非法完整样例，不将本 Markdown 片段冒充已执行合同测试。

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

当前全部任务仍为待实施；主分支不存在表中拟建的 src、播放器或业务测试。

拟建目录：`src/pastport/{domain,application,ports,adapters,workflow,api}` 为 Python 后端；`player/` 为从合同实现的通用解释器与渲染器；`schemas/` 为导出合同；`tests/fixtures/reference/` 为最小获准样例。领域层不依赖 FastAPI、LangGraph 或供应商 SDK。不得将 Demo 的 prototype/data/scripts/tests 整体复制回 main，也不以整个 Demo 为新业务库的种子。

每项以单一目标提交；实际用户授权后才 push。共同质量遵循 [CI 规范](ENGINEERING.md)。下表是待完成的任务，不表示当前检查已存在。

| 任务 | 相关路径/产物 | 必须证明什么 |
|---|---|---|
| T1a 首个样段合同 | src/pastport/domain、schemas、tests/fixtures/reference；最小三包与一条成功路径的强类型映射 | 一个有依据的观察任务＋一次选择＋后续状态读取的完整样例；ID/hash、路线/证据审批、预算和控制结果可表达；成功/非法样例可机器验证，不复制整套 Demo |
| T1b 按需补齐合同 | 进入对应模式/Handler/工具前补其请求、结果和 Schema | §17 对应用例通过；原始完整需求保留；未实现能力明确拒绝，不用自由字典/占位成功掩盖 |
| T2 建编辑库与用例 | ports/repositories、adapters/sqlite、migrations、application/reviews | 临时库迁移；旧库不变；事务、项目隔离、不可变版本、审核过期/权限错误明确 |
| T3 图与恢复骨架 | workflow、application/runner、fake ModelGateway/ToolExecutor | 不依赖真实模型跑完三次审核与类型化研究循环；Skill→Node 路由和工具拒绝/空转分支明确；进程重启不重复已成功步骤；超限/取消不清计数 |
| T4 最小工作台与命令恢复 | api、原生编辑页面、认证/命令消费 | 从页面创建到审核/预览/发布；重复/过期/越权命令被正确处理；不手改库续跑 |
| T5a 真实材料最小样段 | 两 Skill 的加载/版本、来源/模型 adapters、最小预览 | 按 §18 对照样段；真实照片＋证据依赖推理＋人物选择＋后续可见状态；记录 Weng/Mert 判断、真实玩家理解、修改和费用；未运行情境不得标通过 |
| T5b 扩展制作能力 | 完整资料索引/外部研究适配器、政策配置、章节生成/修改 | 扩至原始目录输入、Discovery、定向补证、多场景一致性；不能靠扩大上下文掩盖样段质量失败 |
| T6 通用运行底座与装配 | application/assembly、新建 player/ 通用 interpreter/render；参考 fixture 的显式映射 | 解释器从标准包运行，不依赖 Demo 页面/数据库；固定样本三次选择共 12 种组合及时间边界用于兼容对照；证据发放由包驱动，中英共享规则、刷新不串档 |
| T7 第二官方目录验收 | 新项目数据包、运行报告、人工试玩记录 | 同一图/Schema/装配器/底座生成新游戏；无第二遗址专用 if；缺口真实报告；达到 PRD 的可玩与证据门槛 |

先 T1a→T2/T3 的样段必需部分→T5a＋T6 最小 Handler/预览；T1b 在每项新能力实现前补齐对应合同，不要求首次开工就写完全部模式和可选玩法。随后扩至完整 T3/T4/T5b/T6，最后 T7。T3 首段也必须验证三个人审关口、预算/权限拒绝及成功步骤恢复，不能以“薄切片”为由绕门禁。短期 fake 预览标“模拟生成”，不冒充真实资料生产；框架骨架与新遗址完整可玩分开验收。T5a 缺模型凭据/预算时暂停付费部分，其他工程任务可继续。

T1a 完成条件限于能机器验证的样段：三包包含各自必需字段，只使用当前片段的最小有效数据；引用、审批与版本绑定完整。暂不实现的模式、复杂条件/Handler 和非必需扩展不塞进未定形字段；通过能力声明与显式 unsupported 错误阻止使用。后续 T1b 按同一合同版本策略扩展，并保持旧样例兼容。

关键反例必须覆盖：来源 hash 变化使审批过期；错误图片/未授权资产被拒；文档中的现代特征不被当历史事实；节点/进程中断后已完成小步骤不重复；研究和修订总次数准确；发布响应未知不重复副作用；跨项目不可读草稿/存档；帮助证人的收益和耗时都实际改变后果；局部改稿不破坏其他场景的信息/时间因果。真人试玩单列，不由模型自评分代替。

T1a/T1b 样例须附固定 reference_commit、原始文件路径、对应任务/选择/后果 ID、依赖来源与许可状态、映射理由和预期状态变化；每个样例都通过当前 Schema。能用不含媒体的纯规则样例时不复制图片，需要视觉素材则仅取获准的最小衍生样本。T6 兼容项与体验改进项分开：原有执行语义用于对照；修复硬编码、照片只是装饰等弱点时须记录明确的行为变化和新验收，不静默改变或盲目保留旧设计。

## 13. 开工前还需输入什么

不阻塞 T1–T4/T6：第二目录最终选择、外部来源正式清单、故事评分细化、最终模型、长期预算、真实账号。这些使用明确 test fixture 或待配置状态。

阻塞首次付费 T5：可用供应商凭据、价格依据、调用预算和允许访问的来源策略；阻塞正式发布：真实审批身份、有效证据/照片授权/空间依据、终审及发布决定。Code Agent 不得猜密钥、自动购买额度、将测试批准转成正式审批，或因为未配模型而给 fake 成果标真实。

## 14. 按模式验证输入

共用必填：`request_id, project_id, run_id, mode, scope_ref, policy_ref, budget_ref, remaining_limits, allowed_tools`。ID/版本/hash 由应用提供，不要求模型生成。remaining_limits 含剩余调用、输入/输出 token、搜索、抓取、现金和活动时间；allowed_tools 可为空。模式之外的字段按下表决定，不能把整个 Skill 所有输入都设成必填。

| Skill / mode | 额外必填 | 可空/可省略及允许的产物 |
|---|---|---|
| evidence-review / index | `source_refs`（至少一份已登记的文件/片段） | 不要求 claim/asset IDs、EvidenceRequest、故事方向或路线；可创建候选实体/主张/图片记录与 SourceIndex |
| evidence-review / research | `index_ref, evidence_request`；请求有 purpose、具体问题和范围；仅 direction 需要已选方向 ID | scope_gap 的 candidate_id 为 null，无方向也合法；新主张用 request_id 关联；路线/图片可未知；输出 Findings、来源和未决项 |
| evidence-review / review | `evidence_candidate_ref, target_ids`（非空） | 不要求故事稿、最终路线或新 EvidenceRequest；只评估这些现有目标；新的证据需求另返回请求 |
| narrative / discover | `index_ref, requirements_ref, runtime_capabilities_ref` | 不要求批准证据、选定方向、已核验路线、旧稿、反馈或锁定字段；输出 2–3 个有来源的假设及候选空间序列，未知处单列 |
| narrative / draft | `approved_evidence_ref, selected_candidate_id, approved_route_ref, requirements_ref, runtime_capabilities_ref` | 不要求旧稿和修改反馈；locked_fields 默认为空；路线可为单建筑内有依据的场景序列；输出初稿和质量报告 |
| narrative / revise | draft 所需输入，加 `narrative_ref, revision_request` | revision_request 含反馈、目标 ID/范围及变更原因；locked_fields 可为空；输出因果闭包内的差异及新版候选 |
| narrative / review | `narrative_ref, evidence_ref, requirements_ref, runtime_capabilities_ref` | 从故事包读取路线/方向，不要求调用者重复提供；不要求修改反馈；输出具体问题、反例和质量建议 |

scope_ref 固定当前官方项目范围，不表示已知道所有地点；index 可逐步补齐地点清单。Discovery 的空间序列是待核查假设，不能称为 approved_route。正式 draft 的 route 检查与证据门禁由服务完成；不满足时返回资料研究或人审，不通过伪造路线补齐输入。

应用在付费调用前执行模式校验：缺少本模式必填字段返回 `INPUT_MISSING`，字段名写入错误明细，不调用模型。可空字段未知不算缺输入。结构合法但资料不足时，模型返回具体 gap/EvidenceRequest，不能将资料不足全部归咎为 INPUT_MISSING。没有足够候选时诚实输出已有候选与不足，不为了凑数编造。

## 15. 统一控制结果及映射

所有模式返回 `SkillResult[T]`：`request_id, skill, mode, input_refs, decision, reason_code, reason, payload, issues, changed_ids, evidence_requests, tool_request`。payload 使用该模式独立输出模型（SourceIndex/CandidateSet/EvidenceFindings/NarrativeDraft/NarrativeReview），不以自由字典跨边界；T1 导出对应 JSON Schema。输出模型名不等于模型可自建 ArtifactRef：应用验证/保存 payload 后才分配 artifact ID/hash，形成 NodeResult.output_refs。

`decision` 只有以下七种；禁止各 Skill 使用 pass、revise、continue、human_review 等同义枚举。判断事实的 supported/qualified 等属于 findings 内容，不与控制 decision 混用。

| Skill decision | 服务端验证与处理 | Workflow 结果/状态 |
|---|---|---|
| complete | 校验该模式 payload 和引用，保存产物；确认必要报告存在 | NodeResult.ok；按当前节点路由继续，仍须走既定人审 |
| request_tool | 只允许 evidence research 模式；校验单个 ToolRequest 与剩余预算，执行并回传结果 | 留在当前研究小步骤，不跳图节点、不新增研究轮 |
| research_required | 必须有具体 EvidenceRequest，保存已有候选/差异；有可选方向先 select_candidate，无方向但有明确缺口则 purpose=scope_gap | NodeResult.research_required→research_evidence；方向/范围研究共用轮数，超限转 needs_review |
| changes_required | 指明目标、问题及最小改动；检查人工锁定和剩余修订次数 | NodeResult.changes_required；留在所属模块修订，超过轮数转 needs_review |
| review_required | 保存理由与 findings；不能自动批准，也不能新增任意审批阶段 | 当前产物可交接则 NodeResult.ok→既定人审 gate；达不到交接条件则 needs_review，附待决定项 |
| blocked | 必须列阻塞原因和可恢复动作；不擅自切模型或重启 | NodeResult.blocked + WorkflowError；status=blocked；若实际是额度不足由服务改为 budget_exhausted |
| no_feasible_story | 模型仅提出建议；服务核对候选比较、已尝试方向/研究记录和剩余政策允许动作 | 核对后 NodeResult.no_feasible_story；依据不足则 needs_review，不能直接丢弃项目 |

reason_code 为稳定业务原因（如 SOURCE_INACCESSIBLE、EVIDENCE_GAP、TASK_UNSOLVABLE），不是模型自由指定状态。未知 decision、跨模式工具请求、伪造批准、非法引用和不匹配 payload 均为 `OUTPUT_INVALID`，按合同最多一次格式修复且计费；不能用默认 ok/fallback 放行。NodeResult.next_action 由程序路由产生，模型不得直接指定节点。

共同字段约束：issues/changed_ids/evidence_requests 初始为空数组；除 request_tool 外 tool_request 必须为 null。request_tool 必须携带一个合法 ToolRequest；research_required 必须携带至少一个具体 EvidenceRequest；changes_required 必须含受影响目标及修改理由；blocked 必须含可恢复动作/缺失配置；complete 的 payload 必须通过本模式输出 Schema。控制消息不能创建/覆盖输入 refs 或人类审批记录。partial payload 仅在工具请求/明确缺口时保留为候选，不作为最终已完成产物。

HumanDecision 是另一条认证 API，不能从 SkillResult.decision 推导。request_tool 不变成一个额外 LLM 调度 Agent；review_required 也不会自动增加一次模型审校。

## 16. 有界研究工具循环

研究不是一句“允许联网”：服务端提供以下确定的操作协议。其他模式只读本次提供的片段；需要新增材料则提交 EvidenceRequest。

ToolRequest 是 kind 判别联合，每次至多一个操作：

| kind | 固定参数 | 工具结果 |
|---|---|---|
| lookup_local | question_id、query、site_ids、limit（1–5） | 已有片段 locator/hash、检索状态、相关摘要；不是全文已核验声明 |
| search_web | question_id、query、source_categories、limit（1–5） | SearchHit：标题、URL、作者/机构如可得、检索时间、lead 状态 |
| read_source | question_id、source_id 或已登记 hit_id、locator（可空） | SourceDocument/片段：实际获取状态、最终 URL、原文、locator、hash 和许可线索 |

模型不提供任意文件路径、原始 shell 或自行指定远端工具名。source_id/hit_id 必须属当前项目可读范围；URL 由服务读取已登记记录，再做公网/重定向/大小/域名限制校验。博客可作寻源 lead，不能因此自动变成正式证据。

单轮顺序：

1. 服务冻结 round_id、问题 manifest、工具和模型预算，先检索已有成果；为每个问题建立已访问来源/查询指纹清单。
2. 用 evidence-review/research 让模型决定已有资料够不够：返回 findings、一个 ToolRequest，或具体阻塞。调用前做预算预留。
3. 服务验证 request 的 question_id 属该轮、工具在 allowed_tools 内、参数合法且额度足够；用 ExecutionKey 查缓存。相同输入的成功操作直接复用，并回报 reused 状态。
4. 执行一个工具，先持久化结果和费用，再将 ToolResultRef、必要原文与更新的 remaining_limits 回传同一角色。搜索结果仍为 lead；先 read_source 成功，才能声称查看了原文。
5. 模型据新材料更新支持/反证和判断，选择结束或请求下一个有价值的操作。扩大到另一个实质问题会创建新请求/研究轮；同一问题补读原文仍在原轮工具预算内。
6. 研究轮结束保存结论与未决项：scope_gap 的 complete 只更新候选索引并回 Discovery；direction 的 complete 到 evidence gate。review_required 按 §15 交接条件处理，不能把范围补证结果自动批准；缺口仍在时 research_required 或 blocked。所有分支沿用同一个轮数/费用账本。

防空转初值：每个问题每轮最多 2 次新网页搜索、4 次新来源获取、6 次 research 模型决策调用；不超过 run 更严格的总预算，参数有政策版本。相同查询+范围/同一来源版本不重复付费；改写查询但无新增原文/可用 locator/实质判断变化，连续两次则标 no_progress，提交未决项给人，不循环“再查一次”。这些计数在恢复后沿用，不因缓存命中重置。

工具拒绝、无结果、inaccessible、needs_ocr 与 network_error 是不同 ToolResult；模型不可编原文弥补。未授权工具立即输出 TOOL_NOT_ALLOWED；工具不存在时输出 TOOL_UNAVAILABLE，不假装调用。服务失败重试/未知计费结果仍按 Workflow 合同处理，不能交模型决定盲目重试。

## 17. 具体合同用例（待在 T1/T3 执行）

| 输入/返回 | 必须发生什么 |
|---|---|
| index 只有已登记官方 PDF，无 claim ID | 输入合法，生成候选索引；不能以缺 claim 为由阻塞 |
| discover 有索引但没有路线/旧稿/反馈 | 输入合法，候选路线可有未知项；不能伪造 approved_route |
| discover 无候选但有建筑功能原文缺页等具体缺口 | scope_gap、candidate_id=null 进入同一研究节点；更新索引后再 Discovery；不要求伪造方向 ID |
| scope_gap 用完两轮后选出方向，但关键依据仍不足 | needs_review；不能再以 direction 另领两轮；若只需整理现有完整依据可确定性交审核 |
| draft 只有候选证据或路线未核查 | 服务在付费生成前阻止正式 draft；指向缺口/资料审核，不自动放宽门槛 |
| evidence gate 已批事实但选中 RouteRecord 仍 pending/过期 | 不写 approved_route_ref，不启动 draft；同 gate 处理路线，不能从故事序列推定路线获批 |
| 已批路线换入口或地点次序 | 新路线 hash、审批及关联故事失效检查；无关证据条目保持，不原地覆盖路线 |
| review 缺 narrative_ref | INPUT_MISSING，模型调用数为 0 |
| research 返回 request_tool/search_web | 校验后当前小步骤执行一次，research_rounds 不变；搜索与模型调用计数增加 |
| 同 ToolRequest 在 checkpoint 恢复后重放 | 成功缓存复用，外部实际请求数不再增加 |
| narrative 输出旧枚举 pass 或请求 search_web | OUTPUT_INVALID，不当作 ok；最多有界格式修复 |
| evidence review_required | 保存核查依据后进入既定 gate，不变为人已批准 |
| read_source 未成功 | 无 inspected 原文引用；保留 lead/未知，不支持正式史实 |

## 18. 故事质量：防止“字段填满就通过”

每个关键任务的报告除原有字段外，还必须有：`player_action_id, premise_source_ids, inference_steps, consequence_read_scene_id, observable_feedback, counterexample`。引用必须指到真实场景/动作/状态；只写“推动人物成长”不算依据。

Mert 的初始验收用一个短样段做对照，不先要求完整新游戏：

- **原型 A：** 现有 Muradiye 相近片段或只点图领虚构线索的基线，明确其局限。
- **原型 B：** 同一材料/相近长度和界面，增加有证据前提的推理与可读人物后果；不靠更多提示、不同模型或更多制作时间冒充方法优势，差异单列。
- Weng 核两版的史实/图片/许可/空间边界；Mert 按具体事件评审，保存原稿、模型稿、人改稿和修改理由；模型自评只能推荐。
- 用户试玩交错 A/B 顺序；小样本为探索记录，允许偏好不同，不据此声称统计显著。P0 完整试玩仍按 PRD 的样本目标执行，样段不另造一套强制大样本要求。

不引导答案的观察问题：玩家下一步打算做什么、用了哪条遗址信息、为什么这样推断、选择牺牲了什么、后面哪里看到了后果。记录是否靠主持人代操作/解释，以及原话证据；结束后再收“想不想继续”和原因。目标是查出设计失败，不能给玩家先讲设计意图再算理解成功。

初始阻塞项：关键答案无法由已获线索推出；遗产信息只是可删除装饰却被计作核心推理；选择状态未被后续读取；人物动机与实际反应矛盾；必要行动不可达。出现任一项须修复，不以综合分平均抵消。非关键过场、定位点击、人物交流可以存在，不要求每次点击都是谜题。

14 个现有校准情境仍须真实执行。记录 `case_id, input_snapshot, skill/policy/model_version, generated_output, observed_behavior, reviewer_decision, correction, measured_usage, latency, evaluation_status`；evaluation_status 初始 not_run，区分 fixture_passed/model_evaluated/player_observed。没有实际运行不能填 passed，没有费用数据不能填 0。不通过时只改受影响规则/章节并复测相关因果闭包，保留其他有效结果。

上述能修正验收方法；在真实样段和用户试玩之前，“有趣”“稳定产出”仍是待验证目标，不能靠写规则保证。
