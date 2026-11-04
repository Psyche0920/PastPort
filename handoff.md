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

### 工作方式与交付

先各自下载、启动和试玩现有游戏包，在游戏包的代码和资源上打磨 Demo，可以用 Codex 辅助修改。直接修改并启动现有包无需重新运行 Main 的生成流程。

- **maslan** 负责最佳遗产试玩，重点打磨剧情、玩家行动、线索、互动反馈与结局。场景可选 2D、现有 3D 或新生成 3D。历史内容标明来源，虚构内容标明性质。
- **wcheung** 负责四二最佳试玩，重点打磨故事、任务、玩法插件和玩家端呈现，让线索、玩家操作和结果形成完整可玩的流程。完成试玩后，将适合复用的改进整理到 Story Agent、玩法、绑定和组包校验，再验证自动生成结果。
- **wehan** 负责用户端、账号、城市地图、自动化和后续平台接入。城市地图和游戏发布接入仍待建设和验证。

Main 和 SDK 的目标是基于材料生成可试玩、可继续编辑的游戏初版。主办方审核后可直接使用，或与 Codex 一起打磨并再次试玩。团队先验收优化后的游戏包，再将可复用的经验落实到 Main 和 SDK，使后续生成也能受益。直接修改游戏包不会自动改变生成流程。

用户平台建成后，将验收通过的游戏部署到可访问的位置，从地图对应遗产入口打开。地图进入游戏、资源加载和返回平台需要联调；账号或存档共享需另行对接。现有 Organizer 导入可登记并打开符合格式的试玩包；修改后仍需按实际打包规范验证导入与试玩，不代表公众平台发布功能已经完成。

答辩顺序为 **wehan 城市地图 → maslan 主试玩 → wcheung 技术复用 → wehan 后台更新**。wcheung 用四二展示换一份图文 PDF 和场景后如何匹配实物并点击查看介绍。四二作为复用样例，两处真实遗产从地图展示。耗时的生成步骤用已完成的结果说明。

每次有新版，沿用 `wcheung.tar.gz` 和 `maslan.tar.gz`，上传到 PastPort GitHub Releases，用发布标签区分版本。发布说明写清变更和试玩起点，再更新 [中文 README](README.md) 和 [英文 README](README_EN.md) 里对应的下载链接并推送。wehan 下载后导入 Organizer，在「制作进度与交付」打开同名记录试玩验收。彩排确认地图能直达主试玩，以及后台更新能在用户端看到。

### 最终交付包

用有 PastPort 仓库访问权限的 GitHub 账号下载。wcheung 的交付包可直接解包，打开包内的 `MANIFEST.md`。 [下载 wcheung 完整交付包](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/pastport-wcheung-final-handoff.tar)

#### Maslan 交付清单

| 项目 | 内容 | 下载 |
|---|---|---|
| 比赛章程与赛事说明 | 主办方发布的两份 PDF | [参赛条款](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/competition-terms.pdf) · [赛事说明](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/competition-information-note.pdf) |
| 可试玩游戏包 | Maslan 的独立试玩版本，可导入 Organizer | [可试玩游戏包](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/maslan.tar.gz) · [启动和导入说明](README_EN.md) |
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

### Working and delivery workflow

First, each owner downloads, starts and plays their existing game bundle. Polish the demo by editing the bundle’s code and assets, with Codex where useful. Editing and running an existing bundle does not require rerunning the Main generation pipeline.

- **maslan** owns the best heritage demo, focusing on story, player actions, clues, feedback and endings. Choose 2D, an existing 3D environment or a newly generated one. Cite historical sources and label fiction.
- **wcheung** owns the best 42 demo, polishing story, tasks, gameplay plugins and player presentation so clues lead to actions and consequences. After play-testing, integrate reusable improvements into Story Agent, gameplay, bindings and package checks, then validate the automated output.
- **wehan** owns the player product, accounts, city map, automation and eventual platform integration. The city map and public game publishing integration still need implementation and validation.

Main and the SDKs aim to generate a playable, editable first version from source materials. After review, an organizer may use it directly or polish and replay it with tools such as Codex. The team accepts the improved bundle first, then carries reusable lessons back into Main and the SDKs. Editing a game bundle does not automatically change subsequent generated output.

Once the user platform exists, deploy an accepted game to an accessible location and open it from the corresponding map entry. Map-to-game navigation, asset loading and return navigation need integration testing. Shared accounts or saves require additional integration. The existing Organizer importer can register and open compatible playable bundles; validate the packaging format and preview after edits. Public platform publishing remains to be built and verified.

Present in this order: **wehan (city map), maslan (featured game), wcheung (workflow reuse), wehan (Organizer update)**. Use the 42 demo to show how a different illustrated PDF and scene can be matched and how players open an object's description. The map provides the two real heritage sites. Use completed runs to explain generation steps that take longer than the live slot allows.

Upload each reviewable build to PastPort GitHub Releases as `wcheung.tar.gz` or `maslan.tar.gz`, using release tags for versions. Describe the changes and where to start playing, then update the corresponding download links in both [Chinese README](README.md) and [English README](README_EN.md) and push the edits. wehan downloads each bundle, imports it into Organizer, and tests the matching entry under **Progress & delivery**. Rehearse the map-to-game transition and verify that an Organizer edit appears in the player-facing product.

### Final handoff packages

Sign in to GitHub with access to the PastPort repository. Extract the wcheung archive and open its `MANIFEST.md`. [Download the complete wcheung handoff](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/pastport-wcheung-final-handoff.tar)

#### Maslan handoff manifest

| Item | Contents | Download |
|---|---|---|
| Competition rules and information note | Two official PDFs | [Terms and Conditions](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/competition-terms.pdf) · [Information Note](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/competition-information-note.pdf) |
| Playable game bundle | Maslan’s standalone playable build, ready for Organizer import | [Playable game bundle](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/maslan.tar.gz) · [Startup and import instructions](README_EN.md) |
| Original materials for the game bundle | Original IDML, historical image ZIP, 24 site photos, original SPZ and PLY, and JSON and CSV matching results | [Organizer source archive](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/maslan-organizer-sources.tar.gz) |
| Organizer-provided Vakıf materials (Muradiye) | Original IDML, its `Links` folder, and the chapter PDF | [Muradiye Google Drive folder](https://drive.google.com/drive/folders/18rlNGjpMhGuazgqqOUkJRDNbPEBIcTbh) |
| Team roles and presentation plan | Ownership and presentation order in this document | [Team handoff](#en) |

For work on the current demo, Maslan only needs the playable game and its source archive. wehan owns the map sites, images, data, and launch entry, and will connect the final playable build to the map once Maslan delivers it.

See the [Technical PRD](docs/TECHNICAL_PRD_EN.md) for architecture and interfaces.
