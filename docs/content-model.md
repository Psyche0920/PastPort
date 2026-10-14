# 内容模型与资料库

## 实体边界

| 实体 | 用途 | 扩展要点 |
|---|---|---|
| `site` | 城市中的遗产群或独立地点 | province、district、坐标、开放/访问说明 |
| `heritage_work` | 可被单独发现的 vakıf 作品 | 类型、年代、历史与文化说明、媒体、来源 |
| `structure` | 遗产群中的清真寺、经学学校、墓祠等建筑 | 父子结构、空间关系、历史/现状状态 |
| `source` | 书籍、vakfiye、研究、官方网页或档案目录 | URL、版本、页码、语言、访问日期、权利状态 |
| `claim` | 可核验的单条历史或空间陈述 | claim type、时间范围、来源关系、不确定性、审核状态 |
| `editorial_review_item` | 从旧方案或用户素材导入、尚未通过的主张 | 原文位置、核验状态、编辑备注；不进入玩家端 |
| `media_asset` | 照片、图纸、扫描件、音频或模型 | 来源文件、许可、替代文本、映射状态、节点关系 |
| `scene_node` | 游戏地图中的场景位置 | 2D 相对坐标、GPS 锚点、3D 资源、精度标签 |
| `chapter/role/choice` | 可复用的叙事内容和成长规则 | 角色目标、状态变量、道具、分支效果 |
| `task_slot/candidate` | 节点上的任务位置及人工/AI 候选 | 任务类型、证据白名单、优先级、审核状态 |
| `session/event/feedback` | 持久化游玩状态和运营分析 | 版本、动作、提示、匿名反馈与同意状态 |

## 证据等级

- `verified_fact`：由可引用的可靠来源明确支持。
- `evidence_based_reconstruction`：多个线索支持，但有复原或解释成分；需在界面标明。
- `original_fiction`：人物、事件、对话、虚构账目和选择后果；不应被误认为史实。
- `unverified`：待核验内容，只能留在编辑端，不能进入公开游戏。

证据状态与信心分开：高信心不替代来源；低信心也不自动等于错误。来源互相矛盾时保存多个来源主张并公开说明差异。

## Muradiye 首期已整理主张

1. Sultan II Murad 的 Bursa vakfiyesi 有 1430 年阿拉伯文抄本，研究文章同时使用 1907 年奥斯曼语译本；这是来源版本事实，不代表故事事件发生于该日。
2. 研究文章统计该 vakıf 有 58 项收入来源、24 类职务、89 名工作人员。
3. 文书员记录出入库，仓储人员保管物资；文章还列出厨房人员和喷泉维护职责。
4. 文章说明 imaret 每日提供两餐，并按在场者供餐；游戏文案应注明这是 vakfiye 规定/研究文章的转述，不宣称当代仍按此运营。
5. 学生津贴在阿拉伯文副本与奥斯曼语转写中存在数值/单位差异；研究者认为转写很可能有误。游戏不能把两数当作可直接换算的等值。
6. 《Vakıf Eserleri Envanteri – II. Murad Külliyesi》印刷页 120–122 记录 17 × 17 米经学学校庭院、16 间房、课堂 iwan 和八角形水池；不同来源记载了后续改造和不同用途，发布前应呈现年代与来源。
7. 图片目录的文件名多为相机编号；每张照片需在出版物页码和建筑节点间建立可复核的 crosswalk 后，才能用作定位线索。
8. 库存卷印刷页 123 记载西端的 Sıbyan Mektebi 喷泉是建筑群内唯一被认定为 vakıf 作品的喷泉，并记录砖砌壁龛、水槽和尺寸。照片索引中的具体喷泉尚未确认对应。
9. 库存卷印刷页 124–125 记载 imaret 位于清真寺东北约 20 米，约 13 × 40 米，留有烤炉痕迹、谷物与油储罐。它记载 2000 年代初开始的餐厅用途不等于当前情况。
10. 同卷印刷页 111、130–166 覆盖十三座陵墓；Şehzade Mustafa 墓条目记载 1573 年建造、再利用大理石、十六世纪 İznik 瓷砖、十四扇窗及四座石棺中一座身份不明。玩家任务应把“身份不明”当作正确且重要的证据状态。

## 本地资料来源

- 官方比赛条款与产品申请：`sources/official/ROOT&CODE Hackathon _ Terms and Conditions_ENG.pdf`、`PastPort_ROOT_CODE_Application.pdf`。
- 官方项目资料说明：`sources/official/ROOT&CODE HACKATHON - FOUNDATION HERITAGE INVENTORY PROJECT - INFORMATION NOTE.pdf`。
- Bursa 图片文件夹：<https://drive.google.com/drive/folders/18rlNGjpMhGuazgqqOUkJRDNbPEBIcTbh>。
- Bursa 穆拉迪耶相片 Links 文件夹：<https://drive.google.com/drive/folders/1HbbB-StFjGefpePbEj52DctQnnyS_HOe>。

详细来源和 claim ID 已写入 `data/muradiye.json` 与 SQLite seed。旧版 Bursa 情节方案中的“秘密诗稿在 2020 年修复时于瓷砖后发现”等内容被放入人工审核队列，现阶段只可作为明确标识的虚构构思，不能作为史料或游戏线索。

## 照片剧情版本（v2）

`media_derivatives` 保存从库存出版物提取的五张本地照片，记录来源、PDF 页序、印刷页码、图像序号与已核对建筑身份。它不更改 93 张 Drive 原片的定位状态。`scene_photos` 绑定这些已确认照片与场景。`narrative_versions` 保存浏览器实际消费的完整章节 JSON 和 SHA-256，数据库构建同时校验照片文件、来源及已发布史实。

旧节点 ID 保留以兼容任务槽；显示标题、顺序、照片、史实和默认任务均由新章节导入器同步。运行时以 `data/muradiye-story.json` 为唯一章节内容源。
