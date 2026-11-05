# PastPort 决赛交接 / Finals Handoff

[中文](#zh) · [English](#en)

<a id="zh"></a>

## 中文

交付一条可现场操作的路径：从城市地图发现多处真实 vakıf 遗产，查看图文和出处，进入主试玩，再展示制作流程如何复用以及内容如何更新。

| 负责人 | 交付与验收 |
|---|---|
| **wcheung** | 基于现有四二 3D 环境打磨最佳 Demo，覆盖 Story Agent、任务设计、玩法插件、玩家端呈现和组包。对白完整，任务目标清楚，玩家能用线索操作并看到后果。将反复手改且可复用的改法加回生成规则、玩法校验、展品绑定或组包检查。先交付最佳可玩 Demo，随后对可复用改进做自动化复跑验证并记录仍需手调的部分。 |
| **maslan** | 打磨答辩主试玩，自主选择 2D、重新生成 3D 或沿用已有 3D 做映射。玩家能完成一段完整体验，并用现场物件或有出处的史料做一次有后果的决定。历史内容注明出处，虚构剧情明确标记。 |
| **wehan** | 负责用户端、账号、城市地图与平台自动化。地图可打开至少两处不同的真实 vakıf 遗产，展示图文和出处并直达主试玩。现场通过 Organizer 新增或编辑内容，再回用户端确认变化。 |

### 初始申请书与比赛方向

团队参考保存在本机的[初始申请书版本](references/PastPort_ROOT_CODE_Application.pdf)。它提出从真实历史空间出发，让玩家选择角色、探索建筑和物件、使用线索并通过选择改变个人成长与后续机会。申请书中的安卡拉章节是机制示例，明确不是本届比赛已确认的合格试点。PDF 本身不包含提交回执，需以实际提交记录确认最终版本。

本届以[参赛条款](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/competition-terms.pdf)为准。面向真实 vakıf 遗产做可运行的端到端体验，让用户发现多处遗产并查看历史、图片与来源，支持新增和编辑内容，现场展示核心流程。史实注明来源，依据资料的重建与原创角色、对白和情节清楚区分。

尽量在现实交付范围内靠近申请书方向：优先让玩家在一处真实遗址通过角色目标、物件线索和行动做出有后果的选择，再逐步扩展多角色、成长状态与重玩。申请书里的两个角色、五个节点、三个关键选择、任务适配和 5–8 次试玩是原先提出的 MVP 与测试目标，不代表现已完成，也不是条款中逐项规定的数量。现有地图接入、玩家成长与试玩验证按实际进度记录。

### 工作方式与交付

先各自下载、启动和试玩现有游戏包，在游戏包的代码和资源上打磨 Demo，可以用 Codex 辅助修改。直接修改并启动现有包无需重新运行 Main 的生成流程。

- **maslan** 负责最佳遗产试玩，重点打磨剧情、玩家行动、线索、互动反馈与结局。场景可选 2D、现有 3D 或新生成 3D。历史内容标明来源，虚构内容标明性质。
- **wcheung** 负责四二最佳试玩，重点打磨故事、任务、玩法插件和玩家端呈现，让线索、玩家操作和结果形成完整可玩的流程。完成试玩后，将适合复用的改进整理到 Story Agent、玩法、绑定和组包校验，再验证自动生成结果。
- **wehan** 负责用户端、账号、城市地图、自动化和后续平台接入。本机地图、交付卡片选站点发布、玩家账号/印章/排行榜已接通；共享云部署仍待实施。

Main 和 SDK 的目标是基于材料生成可试玩、可继续编辑的游戏初版。主办方审核后可直接使用，或与 Codex 一起打磨并再次试玩。团队先验收优化后的游戏包，再将可复用的经验落实到 Main 和 SDK，使后续生成也能受益。直接修改游戏包不会自动改变生成流程。

现有 Organizer 的已完成交付卡片可选择地图站点并发布，玩家地图读取同一后台已发布的版本。默认是本机运行；跨设备公网部署尚未完成。同一部署只需导入一次，各玩家不必单独拿包。队友若独立运行本机 Organizer，仍通过 Release 下载并导入；拉取 main 不同步本机历史和游戏文件。修改游戏包后仍须验证入口、资源、通关回执及存档兼容。

答辩顺序为 **wehan 城市地图 → maslan 主试玩 → wcheung 技术复用 → wehan 后台更新**。wcheung 用四二展示换一份图文 PDF 和场景后如何匹配实物并点击查看介绍。四二作为复用样例，两处真实遗产从地图展示。耗时的生成步骤用已完成的结果说明。

每次有新版，沿用 `wcheung.tar.gz` 和 `maslan.tar.gz`，上传到 PastPort GitHub Releases，用发布标签区分版本。发布说明写清变更和试玩起点，再更新 [中文 README](README.md) 和 [英文 README](README_EN.md) 里对应的下载链接并推送。wehan 下载后导入 Organizer，在「制作进度与交付」打开同名记录试玩验收。彩排确认地图能直达主试玩，以及后台更新能在用户端看到。

### 最终交付包

用有 PastPort 仓库访问权限的 GitHub 账号下载。wcheung 的交付包可直接解包，打开包内的 `MANIFEST.md`。 [下载 wcheung 完整交付包](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/pastport-wcheung-final-handoff.tar)

#### Maslan 交付清单

| 项目 | 内容 | 下载 |
|---|---|---|
| 比赛章程与赛事说明 | 主办方发布的两份 PDF | [参赛条款](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/competition-terms.pdf) · [赛事说明](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/competition-information-note.pdf) |
| 可试玩游戏包 | 主试玩《最后两袋》，可导入 Organizer；编辑源在包内 `authoring/` | [可试玩游戏包（maslan-demo-2026-11-05-r1）](https://github.com/Psyche0920/PastPort/releases/download/maslan-demo-2026-11-05-r1/maslan.tar.gz) · [发布说明](https://github.com/Psyche0920/PastPort/releases/tag/maslan-demo-2026-11-05-r1) · [旧版](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/maslan.tar.gz) · [启动和导入说明](README.md) |
| 游戏包的原始材料 | 原始 IDML、历史配图 ZIP、24 张现场照片、原始 SPZ 和 PLY、匹配结果 JSON 和 CSV | [Organizer 原始材料包](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/maslan-organizer-sources.tar.gz) |
| 主办方 Vakıf 资料（穆拉迪遗址） | 原始 IDML、配套 `Links` 文件夹和章节 PDF | [Google Drive 穆拉迪文件夹](https://drive.google.com/drive/folders/18rlNGjpMhGuazgqqOUkJRDNbPEBIcTbh) |
| 团队分工与答辩安排 | 本文中的负责人和答辩顺序 | [团队分工](#zh) |

Maslan 打磨当前试玩时，只需要可试玩游戏包和对应的原始材料包。wehan 负责地图站点、配图、数据和试玩入口，等 Maslan 交付最终可玩版本后接入地图。

系统设计与接口见[技术 PRD](docs/TECHNICAL_PRD.md)。

<a id="en"></a>

## English

Deliver a live, end-to-end experience. Users discover multiple real vakıf heritage sites on a city map, inspect images and historical sources, and launch the featured game. The team then demonstrates how it can reuse the production workflow and update published content.

| Owner | Delivery and acceptance |
|---|---|
| **wcheung** | Polish the strongest playable demo using the existing 42 3D environment. Own the chain from Story Agent through task design, gameplay plugins, player presentation and packaging. Dialogue must be complete, objectives clear, and clues actionable with visible consequences. Where fixes are repeatable, incorporate them into generation rules, gameplay checks, exhibit bindings or package validation. Deliver the polished playable demo first, then validate reusable improvements with an automated run and record remaining manual work. |
| **maslan** | Polish the featured game for the jury. Choose 2D, a newly generated 3D scene, or mapping into an existing 3D environment. Players should be able to complete an experience and use a site object or sourced historical clue to make a consequential choice. Cite historical sources and label fictional material. |
| **wehan** | Own the player-facing product, accounts, city map and platform automation. The map opens at least two distinct real vakıf heritage sites with images, descriptions and sources, and links directly to the featured game. Demonstrate a content addition or edit in Organizer and verify it in the player-facing product. |

### Original proposal and competition direction

Use the locally preserved [initial proposal version](references/PastPort_ROOT_CODE_Application.pdf) as a reference. It describes character-driven exploration of real historical places, architectural and object clues, and choices that shape personal growth and later opportunities. Its Ankara chapter is an illustration of the mechanics and explicitly not a confirmed eligible pilot for this competition. The PDF does not contain a submission receipt, so the final submitted version requires independent confirmation.

The [competition terms](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/competition-terms.pdf) govern the final delivery. Build a working end-to-end experience around real vakıf heritage, enabling users to discover multiple sites, view historical information, images and sources, and add and edit content. Demonstrate core flows live. Cite historical facts and distinguish evidence-based reconstructions from fictional characters, dialogue and events.

Move toward the proposal within the deliverable scope: first let players pursue a character goal, investigate objects and make consequential choices at a real heritage site. Extend to multiple roles, progression and replay as feasible. The proposal's two roles, five exploration nodes, three key choices, adaptive task and 5–8 playtests are proposed MVP and testing targets, not claims of completion or item-by-item numeric requirements in the competition terms. Record actual progress for map integration, character progression and play-testing.

### Working and delivery workflow

First, each owner downloads, starts and plays their existing game bundle. Polish the demo by editing the bundle’s code and assets, with Codex where useful. Editing and running an existing bundle does not require rerunning the Main generation pipeline.

- **maslan** owns the best heritage demo, focusing on story, player actions, clues, feedback and endings. Choose 2D, an existing 3D environment or a newly generated one. Cite historical sources and label fiction.
- **wcheung** owns the best 42 demo, polishing story, tasks, gameplay plugins and player presentation so clues lead to actions and consequences. After play-testing, integrate reusable improvements into Story Agent, gameplay, bindings and package checks, then validate the automated output.
- **wehan** owns the player product, accounts, city map, automation and eventual platform integration. The local map, delivery-card site publication, player accounts/stamps and leaderboard are integrated; shared public deployment remains to be implemented.

Main and the SDKs aim to generate a playable, editable first version from source materials. After review, an organizer may use it directly or polish and replay it with tools such as Codex. The team accepts the improved bundle first, then carries reusable lessons back into Main and the SDKs. Editing a game bundle does not automatically change subsequent generated output.

Completed Organizer deliveries can select a map site and publish; the player map reads that backend’s published release. The default remains local, with public cross-device deployment unfinished. One deployment imports a game once for all its players. Teammates using independent local Organizers still download Releases and import them; pulling main does not transfer local history or game files. After editing a bundle, validate its entry, assets, completion receipt and save compatibility.

Present in this order: **wehan (city map), maslan (featured game), wcheung (workflow reuse), wehan (Organizer update)**. Use the 42 demo to show how a different illustrated PDF and scene can be matched and how players open an object's description. The map provides the two real heritage sites. Use completed runs to explain generation steps that take longer than the live slot allows.

Upload each reviewable build to PastPort GitHub Releases as `wcheung.tar.gz` or `maslan.tar.gz`, using release tags for versions. Describe the changes and where to start playing, then update the corresponding download links in both [Chinese README](README.md) and [English README](README_EN.md) and push the edits. wehan downloads each bundle, imports it into Organizer, and tests the matching entry under **Progress & delivery**. Rehearse the map-to-game transition and verify that an Organizer edit appears in the player-facing product.

### Final handoff packages

Sign in to GitHub with access to the PastPort repository. Extract the wcheung archive and open its `MANIFEST.md`. [Download the complete wcheung handoff](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/pastport-wcheung-final-handoff.tar)

#### Maslan handoff manifest

| Item | Contents | Download |
|---|---|---|
| Competition rules and information note | Two official PDFs | [Terms and Conditions](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/competition-terms.pdf) · [Information Note](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/competition-information-note.pdf) |
| Playable game bundle | Featured game *The Last Two Sacks*, ready for Organizer import; editable sources in the package's `authoring/` | [Playable game bundle (maslan-demo-2026-11-05-r1)](https://github.com/Psyche0920/PastPort/releases/download/maslan-demo-2026-11-05-r1/maslan.tar.gz) · [Release notes](https://github.com/Psyche0920/PastPort/releases/tag/maslan-demo-2026-11-05-r1) · [Earlier build](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/maslan.tar.gz) · [Startup and import instructions](README_EN.md) |
| Original materials for the game bundle | Original IDML, historical image ZIP, 24 site photos, original SPZ and PLY, and JSON and CSV matching results | [Organizer source archive](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/maslan-organizer-sources.tar.gz) |
| Organizer-provided Vakıf materials (Muradiye) | Original IDML, its `Links` folder, and the chapter PDF | [Muradiye Google Drive folder](https://drive.google.com/drive/folders/18rlNGjpMhGuazgqqOUkJRDNbPEBIcTbh) |
| Team roles and presentation plan | Ownership and presentation order in this document | [Team handoff](#en) |

For work on the current demo, Maslan only needs the playable game and its source archive. wehan owns the map sites, images, data, and launch entry, and will connect the final playable build to the map once Maslan delivers it.

See the [Technical PRD](docs/TECHNICAL_PRD_EN.md) for architecture and interfaces.


## wcheung 本机开发的合入边界 / Local integration boundary

游戏包中人工打磨的剧情和资源，与 Main/SDK 源码分别交付。已复用到 Story profile/schema/compiler、玩家呈现与封装的能力，以 main 的实际提交和测试为准；其余修改按功能组审查、测试后集成，不把本机制作目录直接复制到 main。

`.runtime/`、原始照片/PDF/SPZ/mesh、grant、执行/审核数据库、备份 patch 和临时 probe 不进入 source commit。可编辑故事稿、编译后的试玩包与验证记录作为独立 release 内容交接。当前第四幕是人工创作的 runtime-package 扩展；已完成旧版存档通过精确旧包校验和共用引擎重播续接，不改历史审核状态。保存的 Spark LOD adapter 仍是特定 renderer 的准备步骤，尚未作为通用自动化验收。

Authored story/assets in a game bundle are delivered separately from Main/SDK source. Reusable Story profile/schema/compiler and player presentation/packaging capabilities are established by actual main commits and tests. Review and test remaining functional groups before integration; do not copy a local production directory directly into main. `.runtime/`, raw photos/PDF/SPZ/meshes, grants, execution/review databases, backup patches and temporary probes stay out of source commits. Editable story content, compiled playable output and verification records are separate release materials. Act IV is a human-authored runtime-package extension. Completed prior saves continue only after exact prior-package validation and replay through the shared engine; historical review authority is unchanged. The saved Spark LOD adapter remains renderer-specific preparation, not accepted general automation.


四玩法试玩版 / Four-mechanic preview: image differences, drag timeline, scene-object search and chat-image reconstruction are registered JS activities with source-backed blueprint validation and reusable Skill templates. Native illustrations and authored case screenshots are original fiction, not field photographs. A new versioned local package preserves the earlier build/saves; reading-only completion is not migrated into puzzle completion. Functional traversal, browser UI review and real-device FPS remain distinct acceptance checks. The typed Story/Gameplay SDK still requires separate intent/catalog integration before a fresh automatic chain can claim these patterns.


### 2026-11-04 零模型交付验收 / Zero-model delivery acceptance

用户报告四玩法试玩无问题后，在独立 `.runtime/delivery-r4-20261104` 从保存的故事和显式 blueprint 复跑共用编译/组包器；runtime 与呈现内容和试玩版一致。新包通过包内引擎36组分支/结局检查、正式 Organizer importer 的隔离 store 导入/重复导入/持久化与全文件 checksum、正式 preview manager HTTP资源检查，以及 browser 自动LOD→人物介绍→3D调查。交付候选为本机 Desktop/PastPort-delivery-20261104/wcheung.tar.gz；没有发布或推送，也未修改现有 Organizer 数据库。首次 LOD 在测试 browser 中耗时数分钟，未重测FPS。

Following user-reported acceptance, the saved story and explicit blueprint were replayed through shared compilation/assembly in an isolated workspace. Runtime and presentation matched the tested build. The candidate passed 36 packaged-engine route/ending combinations, production Organizer import/idempotency/persistence and all file checksums in an isolated store, production preview HTTP checks, and browser LOD preparation → character introduction → 3D investigation. No fresh model generation, publication, push, existing Organizer database changes or new FPS measurement was performed. The four-mechanic typed intent/catalog integration remains outside this zero-model acceptance.


玩家存档 / Player saves：玩家地图的账号进度已接 SQLite，复用游戏原有 `GameSession` 保存点；同账号、站点、发布版本可恢复。自定义游戏需接同一存档契约；仅改成品包不自动增加账号存档支持。跨设备访问需共享同一个平台后端，默认本机启动尚未公开部署。启动、数据目录、备份和验证边界见 [中文 README](README.md) / [English README](README_EN.md) 及 [技术 PRD](docs/TECHNICAL_PRD.md)。Account saves now persist existing GameSession checkpoints in SQLite. Accounts/sites/releases are isolated; custom games must adopt the save contract. Cross-device access requires the same backend; default local startup is not a public deployment. See the linked README and specification for startup, data, backup and validation boundaries.


共享交付 / Shared delivery：同一平台使用一次导入和站点发布，不需要每名玩家上传游戏包。独立电脑的 Organizer 历史不通过 Git 自动同步；团队继续采用 Release → 下载 → 导入 → 验收。共享云部署与回环游戏地址改造由 wehan 负责，尚未实施。Within one deployment, import/publish once for all players. Git does not synchronize independent local Organizer histories. Team handoff remains Release → download → import → acceptance. wehan owns the still-pending shared deployment and replacement of loopback game URLs.


下一执行任务 / Next execution task：由 Claude 按 [统一在线平台 PRD 第14节](docs/TECHNICAL_PRD.md#shared-online-platform) / [shared online platform §14](docs/TECHNICAL_PRD_EN.md#shared-online-platform) 分 P0–P5 实施，并用 A1–A16 验收。目标为同管理账号跨设备历史、发布游戏统一可玩、逐玩家实时存档及共享排名；现有本机证据不算统一部署验收。本次交接只编写规格，未实施或部署。This handoff specifies work only; it does not implement or deploy it.

共享游戏包平台 / Shared package platform（2026-11-05，按 `PastPort_Shared_Game_Platform_Acceptance_ZH.docx`）：同一 Organizer 中的游戏包可分块上传、下载原包、提交新版（基于当前版本，过期基线返回409）、恢复旧版，并发布或回退站点版本；后台列表和玩家地图每4秒自动刷新。玩家可继续旧版进度或另开新版存档；旧版 UI Trial 已接入账号存档。持久目录丢失时服务拒绝启动，`organizer-backup` 生成一致备份。用法见 [README](README.md#共享游戏包上传获取修改发布)，验收状态见 [技术 PRD §14.12](docs/TECHNICAL_PRD.md#shared-package-platform)。真实双设备、不同 Wi-Fi 及隧道远程验收仍需 wehan 用两台设备执行。Packages in one Organizer support chunked upload, original download, based-on-current new versions (stale bases get 409), restore, and per-site publish/rollback; staff lists and the player map refresh every 4 s. Players continue an earlier release or start a separate new-release save; the legacy UI Trial saves to accounts. Missing persistent data stops startup; `organizer-backup` writes a consistent backup. Real two-device, different-Wi-Fi and tunnel acceptance remains for wehan to run.

Temporary remote sharing: use the foreground remote.mjs entry in the host terminal; see [Chinese README](README.md) / [English README](README_EN.md). Existing data and authentication are retained with separate temporary origins. This does not provide permanent hosting, remote private previews, legacy UI Trial cloud saves or full physical-device acceptance.
