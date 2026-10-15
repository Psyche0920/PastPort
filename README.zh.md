# PastPort · 最后两袋

这是 Bursa 的 Muradiye 建筑群线上叙事试玩版。玩家扮演试任文书员优素福：一笔货物分类错误让替他担保的搬运学徒陷入嫌疑。玩家需要观察真实遗址照片、收集虚构案件单据、决定是否帮助证人，并核对谷物与面粉的去向。

## 项目文档

- [文档导航：当前 Demo 与产品规划的边界](docs/README.md)
- [Muradiye 当前 Demo 资料](docs/demo/README.md)
- [全产品 PRD 与可复用系统目标](docs/product/PRD.zh-CN.md)
- [Osmangazi 官方资料目录说明表](Osmangazi_Google_Drive_Directory_Guide.xlsx)
- [CI 与 Copilot 使用规范](docs/engineering/ci-and-copilot.md)

## 打开中文版

先按下方方法启动本地网页服务，再打开 `http://127.0.0.1:8000/prototype/index.zh.html`。英文版入口为 `http://127.0.0.1:8000/prototype/`。页面右上方可切换语言；两种语言共用同一份本地游戏进度。

## 启动与检查

```bash
python3 -m http.server 8000 --bind 127.0.0.1
python3 scripts/build_database.py --replace
python3 -m unittest discover -s tests -v
node --test tests/test_story_engine.mjs
```

中文版剧情与遗址资料位于 `data/locales/zh/`，对应的页面、交互和剧情规则位于 `prototype/index.zh.html`、`prototype/app.zh.js` 和 `prototype/engine.zh.mjs`。英文版继续使用项目根目录下的英文数据和前端文件。两版共用图片、样式、来源链接与同一组稳定内容 ID。

人物、账目、证词、事件和选择结果均为原创虚构；建筑信息与照片说明以带出处的资料目录为准。GPS 与 3D 尚未接入。
