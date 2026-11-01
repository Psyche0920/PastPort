# Gameplay Preparation and Presentation SDK

## Current integration contract

| Item | Current behavior |
|---|---|
| Inputs | Checked locked Story, capability catalog, source/spatial snapshot and prepared museum. |
| Outputs | GameplayPlan, exact plugin parameters/lifecycle proof, canonical environment and presentation input. |
| Workflow | Compile declared intent → verify actual plugin/solution → bind object/station/view/UI; assembly stays separate. |
| Technology | Python typed facade, shared Node/JS host and deterministic local compilation; no model calls. |

Unified architecture and exact current verification scope: [Technical PRD](../../docs/TECHNICAL_PRD.md#sdk-modules). Main reuses the registered upstream outputs and saved Story in its current replay entry; this is not a new recognition/rendering/model run.

`pastport-gameplay==0.1.0rc2` uses `pastport==0.2.1rc4` as its single shared runtime.
It makes no model calls. Python 3.12 and Node.js are required.

| Stage | Input | Output |
|---|---|---|
| prepare | Validated locked Story directory | Typed gameplay plan, lifecycle receipts, canonical environment |
| present | Same Story, preparation, existing museum | Exact task/plugin/source/view/navigation/UI bindings (`story-input.json`) |
| Separate assembler | Prepared story input, museum resources | Playable game bundle |

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --find-links /absolute/path/wheels pastport-gameplay==0.1.0rc2 pastport-story==0.1.0rc4
.venv/bin/pastport-gameplay prepare --story-run /absolute/story --output /absolute/new-preparation
.venv/bin/pastport-gameplay present --story-run /absolute/story --preparation /absolute/new-preparation --museum /absolute/museum --output /absolute/new-presentation/story-input.json
```

Outputs must be new paths. Wrong hashes, catalog versions, source/space identities,
unsupported tasks and unsolvable puzzles fail explicitly. No implicit reading fallback.
Museum assets, private PDFs, saves and credentials are not included in distributions.
Shared host code, Skills and schemas live once in the shared runtime wheel, not in
both SDK wheels. The assembler is a separate shared-runtime tool; this SDK does not
publish, serve or package games. Current adapter supports the verified two-view
museum and reading/coverage plugins, not arbitrary games or arbitrary scene counts.

| Source | Purpose |
|---|---|
| client.py | Typed preparation/presentation API with bounded local subprocesses |
| cli.py / __main__.py | Installed command and module entry points |
| __init__.py / py.typed | Public typed exports |

<!-- BEGIN FILE INVENTORY -->
## 文件结构与用途

每个文件的用途直接写在同一行。以下覆盖本范围内的 **8 个维护文件**；依赖环境、缓存、私有产物和历史备份不属于源码清单。

```text
gameplay-sdk/
├── src/
│   └── pastport_gameplay/
│       ├── __init__.py  # Gameplay preparation and presentation; shared engine is a pinned dependency.
│       ├── __main__.py  # Python 模块命令入口，将 python -m 调用转交本包 CLI。
│       ├── cli.py  # Local SDK commands; all generation calls remain in Story.
│       ├── client.py  # Installed local production stages over the single shared gameplay host.
│       └── py.typed  # PEP 561 类型标记，让安装方的类型检查器识别本包类型。
├── LICENSE  # 本模块的许可证；分发源码或安装包时保留。
├── README.md  # 本模块的使用入口、输入输出及完整文件用途说明。
└── pyproject.toml  # 本项目的包名、依赖、命令入口与构建配置。
```
<!-- END FILE INVENTORY -->
