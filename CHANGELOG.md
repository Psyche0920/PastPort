# Changelog

## 2026-11-08 — Eyne Bey: The Twelve Rooms r2 delivery

- Deliver the independently polished `eyne-bey-seker-han` bundle as [eyne-bey-seker-han-demo-2026-11-08-r2](https://github.com/Psyche0920/PastPort/releases/tag/eyne-bey-seker-han-demo-2026-11-08-r2); retain r1. Editable game/authoring code, the scan and assets are Release content, outside the source commit and generic Main/SDK generation path.
- Replace reading-only progression with a coherent seven-chapter main quest, two optional investigations, three main endings and consequences across 12 choice combinations. Use the supplied PDF's p.559 aerial photograph for a nine-piece puzzle and p.558 entrance photograph for three differences. Original images and full-page references are retained; a single built-in image edit produces the explicitly fictional comparison copy. Characters and the 1674 dispute remain fiction, separate from modern source photographs and the Şeker Han stand-in scan.
- Add independent first-page preparation/start controls with one shared 3D/LOD job, reading in parallel and retry. Add collision-sampled stair routes, turn toward the object before arrival, reuse the period cast without head cropping, and place language beside Menu clear of the minimap.
- Validation: 12 deterministic choice paths, wrong-answer/incomplete-puzzle and duplicate-difference checks, per-chapter save restoration, 144 connected route pairs, one complete seven-chapter Chrome playthrough, zh/en/tr activity widgets, real early scene loading and three centred arrivals. Three preparation-coordinator tests pass; native Spark LOD was exercised in the preceding character-preparation run. Each archive member is checked against its manifest. Headless rendering without LOD remained approximately 9–14 FPS; no stable-device-FPS, human story/historical acceptance or map publication claim.
- Update both READMEs, both technical PRDs and the bilingual handoff. No accounts, grants, execution databases or original 171 MB PDF are committed; no new Story or 3D generation call, production service restart or map binding change is part of this delivery.

## 2026-11-08 — Eyne Bey Subaşı Madrasa (Şeker Han Demo)

- New featured demo `eyne-bey-seker-han-demo-2026-11-08-r1`: the team's iPhone scan of the Şeker Han basement (Istanbul) as a stand-in space, with 12 hand-placed points opening real records from the Vakıf inventory, Osmangazi · Educational Institutions · Eyne Bey Subaşı Madrasa (pp. 557–561). English and Turkish records are verbatim (35 quotes checked against the PDF text, including the original typo "the the"; two excerpts marked […]); Chinese is our translation. Seven reading scenes, three choices, twelve ending texts; story and interface in Türkçe / English / 简体中文 using the shared display catalog.
- 3D runtime: the floor probe ignores ceilings above the eye (low vaults froze movement), the wall check sits above the 0.35 m step limit (stairs could not be climbed), labels behind walls are hidden (current target stays visible), and 3D labels follow the display language.
- Player map: search box (place or game name in any language, Turkish letters folded) and a "playable only" filter, on the redesigned map.
- Verified: zero model/Marble calls; 12 choice paths reach their ending; Chrome without page errors in zh/en/tr; scripted walk from entrance to chamber (stuck at the entrance with the previous runtime); Organizer import; 119 player/game tests. Not verified: full human playthrough per language, phone layout, native review of the story Turkish.

## 2026-11-08 — Automatic review translations

- Main handoff validation: 69 focused Python regressions, 16 frontend localization tests, strict typing for six affected Python files, repository/documentation contracts and whitespace checks passed. Runtime translation caches and review databases remain local, outside the source commit. No fresh recognition, Story call, public deployment or production restart was performed during the push task.

- New authorized upload SDK jobs prepare English/Turkish review translations before environment-ready, preserving original records and cache identities. Disclose separate bounded translation budget, record cumulative calls and stop safely on uncertain dispatch. Success/failure paths verified with synthetic execution; no fresh recognition, Story generation or production restart.

## 2026-11-08 — Review display translations

- Move display markers into the SDK review template for subsequent exports; localize candidate state and 3D review links without modifying persisted enum values. Live port 18840 returned 404 for the display-locales endpoint, confirming it still requires a server restart. Newly authored free text needs its own explicit translation operation; opening a page does not incur model calls.

- Add source-bound English/Turkish display caches for names, identifying features and judgment notes; language switching preserves originals, IDs, editor values and review authority. Translation is an explicit bounded text-only operation, separate from recognition.
- After explicit authorization following the initial approval rejection, translated all 136 review passages in 333 and 112 in 444 through the current Codex subscription (9 text-only calls; 245 unique cached passages). Both authoritative datasets retained identical before/after SHA-256 hashes; current reuse-source caches have zero missing entries. No recognition, Story call or production restart.

## 2026-11-08 — Admin English and Turkish system messages

- Translate backend compatibility errors, native preparation progress, legacy completion messages and IDML review labels in English and Turkish.
- Preserve source prose, object names, editable fields and captured task IDs. Remove single-character fragment substitution so unknown sentences cannot become mixed text such as None法 or Yok法.
- Format environment counts and missing object numbers as complete localized notifications. New regression cases use actual observed backend messages and exact-only embedded review labels.
- Interface assets only; no story generation, source/review data changes or workflow policy changes.

## 2026-11-08 — Native source preparation, pinned visual policy and Story contracts

- Unify normal PDF text extraction with page/line provenance and targeted local OCR for scanned or garbled pages. Preserve originals and pass verified evidence directly to native environment preparation; remove the label-layout-specific path.
- Add the native IDML + SPZ + PLY entry and stepwise Organizer preparation; initialize optional player assets locally, retain bounded budgets and saved receipts, and stop environment preparation before Story.
- Pin new IDML runs to v4 same-object visual matching and new environment runs to the v2 localization skill snapshot. Unclear minor marks remain limitations; function-only analogies are excluded. Existing runs retain their prior policies. Show pending IDML review entries directly.
- Include the current Story preparation/schema, budget/resume and English/Turkish contract updates, shared game runtime preparation, localization assets and remote-start diagnostics.
- Text-first IDML targeting and moved-camera search remain local experimental artifacts, not production features in this commit. Same-material source-first testing selected 9 targets, matched 7 and localized 6; the production baseline had 30 candidates and 9 matches/locations. Counts are not an accuracy benchmark. No private source files, model ledgers, project databases, game bundles or experimental run directories are committed.
- Validation: Evidence and Matched Environment SDK offline suites, strict application/test typing (214 files), strict SDK typing (131 files), 43 schema contracts, player contracts and repository/documentation checks passed. The application-wide run had one active-time settlement assertion failure; the focused rerun including that test passed. An i18n test now explicitly verifies intentional version-suffix omission and complete composed labels. Repository-wide Ruff is not clean (610 findings on the prior committed baseline; 738 in the current working tree), and format-check requests 100 files; these are not claimed as green. Generation, browser playthrough, human historical approval and public deployment remain separate acceptance layers.

## 2026-11-07 — Player-map game names and launch verification

- Label map nodes and place details with the verified publication edition, keeping heritage place names. Game headers and iframe titles follow the actual launched release; older saves cannot borrow the current edition label. Simplified Chinese, English and Turkish update together.
- Verify both actual published bundles through the map with an isolated player: Forty Two opens The Last Tour; Muradiye opens The Last Two Sacks walkable theatre. Sixteen localization tests and ten save/launch regressions passed. Test accounts are isolated; test services are stopped afterward. No publication bindings or game archives changed.

## 2026-11-07 — Consistent Organizer game edition names

- Resolve verified delivery names by immutable archive SHA-256, not reused import IDs. Show the same edition in package cards, version history, publication choices, published listings and upload/restore feedback, in Chinese, English and Turkish. Unidentified archives retain their import ID with an explicit unidentified-edition label.
- Distinguish maslan featured r1, The Last Two Sacks trilingual walkable theatre, The Last Tour, and historical The Dead Cast a Vote. Inspection found the 2026-11-05 UI Trial archive already contains the walkable-theatre entry; correct README, handoff and Release labels instead of claiming a verified standalone original 2D download.
- Keep package IDs, archive filenames, game bytes, publication bindings and saves unchanged. Eleven frontend tests and three-language DOM rendering checks passed; existing Organizer serves updated assets. No test service was started.

## 2026-11-07 — Organizer, map and selected games: zh / en / tr

- Add Simplified Chinese, English and Turkish selectors to Organizer and the player map; retain unsaved Organizer inputs and refresh dynamic save/release messages when language changes.
- Add a display-only localization layer for the selected Muradiye UI Trial / The Last Two Sacks walkable-theatre package, including dialogue, tasks, CSS signs, notes and endings. Keep original engine bytes, evidence IDs, decisions, source images and save format.
- Publish it as a new immutable package version; preserve historical releases and release-specific saves. Other game packages are unchanged. Download/import links are in both READMEs and the team handoff.
- Follow-up: localize wcheung / The Last Tour on Forty Two Heilbronn, including compiled objectives, same-origin 3D frames, Canvas labels and fictional SVG clues. Synchronize in-game selection back to the map using active-frame/origin/run checks; clean up frame observers on navigation. Original gameplay and save identity stay unchanged. The exact staged source passed 57 related tests serially; an initial parallel remote-launch fixture exceeded its startup time budget and passed on the serial rerun.
- Validation: 53 relevant JS tests passed on the exact staged source after integrating current main, plus 86-module syntax and repository/documentation checks. Earlier isolated browser opening, ledger-dialog and parent-language switching passed. The original engine is unchanged; all endings were not replayed in this localization run.

## 2026-11-06 — Organizer delivery organization and unpublish

- Separate Game packages, Map publications and Production history into delivery tabs. Collapse technical paths, version submission and version history; add project/status search for production records.
- Add owner-authorized, version-checked unpublish. It removes only the live site binding and retains the map node, package, publication history, saves and medals. The card disappears immediately after success; stale refreshes cannot restore it, and refresh failure does not misreport successful unpublishing as failure.
- Resolve archived production jobs by ID without listing them, preserving references from retained packages. No local history archive/restore, private account data, game bundles or publication data is included in this commit.
- Verified with isolated Organizer API regression tests, frontend controller and language tests, strict typing, lint and documentation checks. Browser testing against an isolated real API confirmed the unpublish dialog, immediate removal, persistence after refresh and retained package. This does not establish cross-device/tunnel or gameplay completion acceptance. Test services are stopped after verification.

- Player platform claims account saves only when the entry page boots `app.mjs`, where the save bridge is injected. A package with a different entry module and a leftover `session.mjs` (the 42 Heilbronn "最后一段录音" snapshot) no longer stays on "restoring account progress" forever; it is labelled local-save only. Regression test added. Rehearsal: all six `player-map-six-2026-11-06-r1` packages imported, published and opened without page errors on a fresh isolated deployment; full playthrough stamps and two-device runs not repeated.

## 2026-11-05 — wcheung release candidate

- Merge main `5805a76` into the wcheung working branch and rebuild the standalone disappearance-story demo with the shared completion bridge.
- Carry typed opening context and four investigation designs from Story preparation metadata into zero-model game assembly: picture comparison, timeline, scene search and chat-image puzzle.
- Candidate package: `wcheung-demo-2026-11-05-r1/wcheung.tar.gz`; original PDF, accounts, databases, grants and model traces are excluded.
- Deterministic three-route/four-ending traversal and Node 22 game/platform checks pass. Fresh model-generation quality testing is paused; this saved-content replay does not establish new model quality or device FPS.


## 2026-11-05

- Shared game-package platform (per `PastPort_Shared_Game_Platform_Acceptance_ZH.docx`). Organizer packages are now immutable versions with a current pointer. Uploads go in resumable 16 MB chunks with progress; the original archive is downloadable, and a materials list marks what is missing. A new version must name the current version as its base (stale bases are refused with 409), and earlier versions can be restored. Map publication records history, refuses a stale expected version and supports rollback. Organizer lists and the player map refresh every 4 seconds.
- Players: a run stays on its release, with explicit choices to continue an earlier release or start a separate new-release save; the game bar shows syncing, synced, not synced or conflict. The legacy UI Trial saves to the account in its own event-log format. The leaderboard no longer shows fictional sample travelers, and the open game now covers the header menu so “back to map” stays clickable.
- Data protection: Organizer and player services refuse to start when their persistent directory is missing or replaced. `python -m pastport organizer-backup` writes a consistent backup that can be started as an isolated restore.
- Verified on one computer with independent browser sessions and the three real packages (results in PRD §14.12). Not verified: two physical devices on different Wi-Fi, tunnel uploads, and full playthrough stamps in the browser.

- Released the featured game *The Last Two Sacks / 最后两袋* as `maslan.tar.gz` (maslan-demo-2026-11-05-r1), built on the team-handover `maslan.tar.gz` room with the shared compiler and investigation blueprint, zero model and zero Marble calls. Updated the README and handoff download links.
- Organizer setup works on any computer: `python -m pastport organizer-init` creates the private `admin` account (password typed twice, hash only, 0600, never overwrites), the start command no longer needs one person's private paths, and a missing account file now names itself and the setup command. `python -m pastport organizer` starts it with the standard local options, and the README setup is now four numbered steps. READMEs and technical PRDs use repository-relative commands.
- Routing tasks may set their own prompt, instruction and wrong-bin copy; investigation activity hints no longer mention one specific story.
- Verified: 12 engine choice combinations with 12 distinct ending texts; Chrome playthroughs in English, Chinese and at 390×844 with mid-game reload; isolated Organizer import, re-import and checksum match. Not verified: human playtest, Turkish, screen readers, historical review.

## 2026-11-03 — Finals handoff

- Updated the bilingual root handoff, READMEs and technical PRDs with the responsibilities of wcheung, maslan and wehan, the live demonstration order, and the Release-to-Organizer acceptance process.

## 2026-11-03 — IDML to playable 3D

- Added native IDML, linked graphics, site photos and existing SPZ/PLY input. Photo scanning retains coverage gaps, and IDML matching and audit run in groups of up to 16 identities with separate receipts.
- Registered the local 3D review version as Organizer history with a direct preview and Story continuation. The real run produced 108 recognized candidates, 48 source matches, 34 localized candidates and 30 projected 3D positions awaiting surface review.
- Generated Story and assembled an openable game. Published the playable baseline and startup instructions in the private Release. Startup from an extracted bundle was checked locally.

## 2026-11-02 — Organizer raw 3D workflow baseline

### Added
- Import existing SPZ scenes and triangular PLY meshes through the Organizer workflow without Marble generation. Derive local scene views and retain input identities and provenance.
- Persist the selected project and prepared source across reloads and sign-ins; provide continuation from project history.
- Cover overhead and floor objects in raw 3D localization, with independent point review and per-object outcomes. Unconfirmed positions remain gaps rather than fabricated anchors.
- Version new photo and PDF matching policies separately from existing execution receipts. Broader candidates still require historical evidence.

### Fixed
- Prevent previous projects' review state and Story readiness from leaking into newly selected materials.
- Keep environment preparation disabled while queued or running.
- Preserve browsing records and click bindings for optional source objects, including numbers 8 and 14, without granting task completion.
- Permit geometry-only repair and full compatibility revalidation of an existing Story in a separate output version.
- Support the tested collider profile in offline spatial assessment and preserve reviewed positions, source authority and navigation.
- Preserve completed execution results and unknown usage when explicitly recovering interrupted work; retain call ceilings and no automatic retries.

### Validation and limits
- Main source type checks, 20 Evidence SDK tests, the environment SDK suite, nine affected JavaScript tests, and repository/documentation checks passed.
- The broader root regression run was interrupted after a subprocess-start timing assertion failed; it is not reported as a full-suite pass. The isolated assertion passed on recheck; the broader suite remains unverified as a whole.
- Real bounded localization used exactly two authorized model calls: numbers 12 and 19 passed independent review and were included in a new Admin build. Numbers 16 and 17 remain unlocated. This is not historical approval or complete-object coverage.
- The rebuilt game passed resource checks; number 12 was rendered and clicked to open its source popup. Existing PDF and Story were not regenerated.
- IDML import, external historical research and the newly discussed player-facing exclusion policy are not implemented by this baseline.
- Private source materials, credentials, accounts, execution databases and generated game packages are excluded from Git.


## 2026-11-05 — 玩家账号持久存档（本地实现）

- 玩家地图以账号、站点和发布版本持久保存 `GameSession` 快照，含调查、选择、小游戏、位置及续幕键；启动先恢复再运行，旧浏览器无主存档不自动认领。
- 保存合并排队，使用乐观版本锁和幂等操作标识；失败可重试或导出，旧设备不能覆盖更新存档。返回地图和退出账号先等待保存。
- 私有玩家库及其备份加入 Git 忽略规则；测试端口隔离登录 cookie。
- 隔离测试：26 项存档/玩家引擎测试通过；真实四二游戏保存电脑阅读进度，重启更换游戏端口后恢复，并继续完成选择题。仓库/文档/JS 检查及相关 Python strict mypy 通过。未部署云服务，未在两台实体设备上实测，未重新验收完整剧情或所有自定义包。


## 2026-11-05 — Muradiye UI Trial 二维交付

- 从 `demo-muradiye-ui-trial` 保存原版《最后两袋》为 `muradiye-ui-trial` 交付包，32 个原版游戏/素材文件内容保持一致，新增包入口与来源清单，不包含数据库或凭据。
- 交付导入、可信预览启动器及站点发布支持带显式入口清单的静态二维包，保留既有 3D 路径和权限检查。
- 已登记本机 Organizer；地图发布操作只在隔离环境验证，未替换当前正式站点。原分支 25 项游戏测试通过；完整剧情通关和旧版云存档不属于本轮完成范围。


## 2026-11-05 — 导入旧版游戏自动连接通关回执

- 可信游戏宿主按运行时摘要识别旧版 UI Trial，并在实际结局显示后发出统一通关事件；新静态游戏可使用 `pastport:completed` 标准事件。未结束的阅读或调查不触发完成。
- 旧版本机保存键按玩家、站点和发布版本隔离，保留未绑定的历史浏览器存档。该适配不声称旧版已有跨设备存档。
- 复用现有印章主键和排行榜；重复通关不重复计分。通关桥接模块同时加入显式游戏包及 Python 安装资源清单。

- 隔离浏览器实玩五幕、三次照片配对、分账和证据桌，完成 `signed-truth` 结局；护照与地图自动盖章，刷新排行榜出现对应玩家和奖章。重开已完成存档后仍只有一枚奖章。证据保存在忽略目录的 `COMPLETION_ACCEPTANCE.json`，旧验收记录保留。


## 2026-11-05 — 玩家平台与远程 main 整合

- 合并远程便携启动和 Maslan 交付更新，保留本机匹配/展签流程修复；使用共用管理员初始化器，避免重复启动分支。
- 中英文 README、技术 PRD 和团队交接明确区分同一后台的一次导入/站点发布，与独立电脑通过 Release 下载后导入；Git 不同步制作历史、游戏资产或玩家数据库。当前仍为本机开发模式，统一云部署尚未执行。
- 合并后全量 Python 测试通过；所选 JS 检查45项通过、1项私有包夹具跳过，另有真实 UI Trial 五幕通关证据。Ruff、相关 strict mypy、仓库/文档/JS 检查通过。
- 离线 wheel 构建成功，安装资源含玩家端源码、16个站点目录和通关适配依赖；未包含账号文件、数据库或游戏压缩包。本轮没有上传新游戏包或发布新 wheel。
