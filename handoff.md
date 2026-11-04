# PastPort 决赛交接 / Finals Handoff

[中文](#zh) · [English](#en)

<a id="zh"></a>

## 中文

交付一条可现场操作的路径：从城市地图发现多处真实 vakıf 遗产，查看图文和出处，进入主试玩，再展示制作流程如何复用以及内容如何更新。

| 负责人 | 交付与验收 |
|---|---|
| **wcheung** | 基于现有四二 3D 环境打磨最佳 Demo，覆盖 Story Agent、任务设计、玩法插件、玩家端呈现和组包。对白完整，任务目标清楚，玩家能用线索操作并看到后果。将反复手改且可复用的改法加回生成规则、玩法校验、展品绑定或组包检查。用一次自动化复跑验证效果，记录仍需手调的部分。最佳可玩 Demo 是主要交付。 |
| **maslan** | 打磨答辩主试玩，自主选择 2D、重新生成 3D 或沿用已有 3D 做映射。玩家能完成一段完整体验，并用现场物件或有出处的史料做一次有后果的决定。历史内容注明出处，虚构剧情明确标记。 |
| **wehan** | 负责用户端、账号、城市地图与平台自动化。地图可打开至少两处不同的真实 vakıf 遗产，展示图文和出处并直达主试玩。现场通过 Organizer 新增或编辑内容，再回用户端确认变化。 |

答辩顺序为 **wehan 城市地图 → maslan 主试玩 → wcheung 技术复用 → wehan 后台更新**。wcheung 用四二展示换一份图文 PDF 和场景后如何匹配实物并点击查看介绍。四二作为复用样例，两处真实遗产从地图展示。耗时的生成步骤用已完成的结果说明。

每次有新版，沿用 `wcheung.tar.gz` 和 `maslan.tar.gz`，上传到 PastPort GitHub Releases，用发布标签区分版本。发布说明写清变更和试玩起点，再更新 [中文 README](README.md) 和 [英文 README](README_EN.md) 里对应的下载链接并推送。wehan 下载后导入 Organizer，在「制作进度与交付」打开同名记录试玩验收。彩排确认地图能直达主试玩，以及后台更新能在用户端看到。

### 最终交付包

使用有 PastPort 仓库访问权限的 GitHub 账号下载。解包后先打开 `MANIFEST.md`。

| 交付 | 下载 |
|---|---|
| **wcheung** | [完整包](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/pastport-wcheung-final-handoff.tar) |
| **maslan** | [第 1 段](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/pastport-maslan-final-handoff.tar.part-aa) · [第 2 段](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/pastport-maslan-final-handoff.tar.part-ab) |

wcheung 下载后可直接解包。Maslan 把两段放在同一目录，在终端运行下面两条命令。

```sh
cat pastport-maslan-final-handoff.tar.part-aa pastport-maslan-final-handoff.tar.part-ab > pastport-maslan-final-handoff.tar
tar -xf pastport-maslan-final-handoff.tar
```

交付包包含制作源文件和参考资料。按包内清单下载可试玩的 `wcheung.tar.gz` 或 `maslan.tar.gz`，再导入 Organizer。

系统设计与接口见[技术 PRD](docs/TECHNICAL_PRD.md)。

<a id="en"></a>

## English

Deliver a live, end-to-end experience. Users discover multiple real vakıf heritage sites on a city map, inspect images and historical sources, and launch the featured game. The team then demonstrates how it can reuse the production workflow and update published content.

| Owner | Delivery and acceptance |
|---|---|
| **wcheung** | Polish the strongest playable demo using the existing 42 3D environment. Own the chain from Story Agent through task design, gameplay plugins, player presentation and packaging. Dialogue must be complete, objectives clear, and clues actionable with visible consequences. Where fixes are repeatable, incorporate them into generation rules, gameplay checks, exhibit bindings or package validation. Run the automated chain once to check the improvements and record any remaining manual work. The polished playable demo is the primary deliverable. |
| **maslan** | Polish the featured game for the jury. Choose 2D, a newly generated 3D scene, or mapping into an existing 3D environment. Players should be able to complete an experience and use a site object or sourced historical clue to make a consequential choice. Cite historical sources and label fictional material. |
| **wehan** | Own the player-facing product, accounts, city map and platform automation. The map opens at least two distinct real vakıf heritage sites with images, descriptions and sources, and links directly to the featured game. Demonstrate a content addition or edit in Organizer and verify it in the player-facing product. |

Present in this order: **wehan (city map), maslan (featured game), wcheung (workflow reuse), wehan (Organizer update)**. Use the 42 demo to show how a different illustrated PDF and scene can be matched and how players open an object's description. The map provides the two real heritage sites. Use completed runs to explain generation steps that take longer than the live slot allows.

Upload each reviewable build to PastPort GitHub Releases as `wcheung.tar.gz` or `maslan.tar.gz`, using release tags for versions. Describe the changes and where to start playing, then update the corresponding download links in both [Chinese README](README.md) and [English README](README_EN.md) and push the edits. wehan downloads each bundle, imports it into Organizer, and tests the matching entry under **Progress & delivery**. Rehearse the map-to-game transition and verify that an Organizer edit appears in the player-facing product.

### Final handoff packages

Sign in to GitHub with access to the PastPort repository. Open `MANIFEST.md` after extraction.

| Handoff | Download |
|---|---|
| **wcheung** | [Full archive](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/pastport-wcheung-final-handoff.tar) |
| **maslan** | [Part 1](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/pastport-maslan-final-handoff.tar.part-aa) · [Part 2](https://github.com/Psyche0920/PastPort/releases/download/team-handover-2026-11-03/pastport-maslan-final-handoff.tar.part-ab) |

Extract the wcheung archive directly. For maslan, save both parts in the same directory and run the following commands.

```sh
cat pastport-maslan-final-handoff.tar.part-aa pastport-maslan-final-handoff.tar.part-ab > pastport-maslan-final-handoff.tar
tar -xf pastport-maslan-final-handoff.tar
```

The handoff packages contain source materials and references. Use the manifest to download the playable `wcheung.tar.gz` or `maslan.tar.gz` for Organizer import.

See the [Technical PRD](docs/TECHNICAL_PRD_EN.md) for architecture and interfaces.
