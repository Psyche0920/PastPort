# PastPort

将官方遗产资料转化为有史实依据、有人物成长的互动游戏，并用同一制作流程复制到其他遗址。

**当前状态：架构与规范准备阶段。** `main` 尚无业务框架、LangGraph 服务或通用播放器；`tools/` 仅用于仓库检查。两个项目 Skill 已编写，尚未接入模型与运行时，也未完成真实效果评测。

| 从哪里开始 | 内容 |
|---|---|
| [产品需求 PRD](docs/PRD.md) | 产品逻辑、四模块职责、资料/故事底线、范围、分工、里程碑和验收 |
| [Workflow 实现合同](docs/WORKFLOW.md) | 数据与状态、节点/API、恢复/预算、通用玩法、Skill 协议及 T1–T7 实施任务 |
| [工程与 CI 规范](docs/ENGINEERING.md) | Coding Agent、代码质量、协作、当前检查与未来检查接入 |
| [参考依据](docs/REFERENCES.md) | Muradiye 抽象方法、遗产系统与开源 Skill 源头、许可和采用边界 |

项目 Skill：[资料审核](skills/evidence-review/SKILL.md)、[情节制作](skills/narrative/SKILL.md)。只按任务读取相关入口和范例。

官方目录说明表与比赛条款保留在 `references/`，它们是来源材料，不代表内容已获审核通过。

## 分支与样本

- `main`：通用产品、框架与 Workflow 的规范及后续实现。
- [demo-muradiye](https://github.com/Psyche0920/PastPort/tree/demo-muradiye)：完整中英 Demo、照片、数据、SQL、脚本和历史回归测试。main 只保留抽象参考，不复制 Demo。

开发从实现合同的 **T1a：首个短样段的类型/Schema 与抽象映射** 开始；其他模式在接入前按 T1b 补齐，不先铺完整后台。Muradiye 的固定样本版本见 Workflow §2，用来对照兼容性；第二个官方同层级文件夹用于首次完整新项目试跑。

## 当前检查

```bash
python3 tools/check_repository.py
```

检查文件、链接、Skill 元数据及语法；不会启动游戏、调用模型或验证故事质量。本地新 CI 配置使用同一命令，尚待提交、推送并在 GitHub 上验证生效；本地通过不代表远端已通过。
