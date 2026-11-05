# Changelog

## 2026-11-05

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
