# PastPort Stylization SDK

## Current integration contract

| Item | Current behavior |
|---|---|
| Inputs | Matched environment, panorama/3D appearance, reference style and explicit execution grant. |
| Outputs | Styled panorama/appearance, source-bound Style3DVariant and candidate quality records. |
| Workflow | Lock source → generate or reuse appearance → apply/check → export without changing geometry. |
| Technology | Python 3.12, image transport, SPZ appearance processing and optional ffmpeg/Poppler. |

Unified architecture and exact current verification scope: [Technical PRD](../../docs/TECHNICAL_PRD.md#sdk-modules). Main reuses the registered upstream outputs and saved Story in its current replay entry; this is not a new recognition/rendering/model run.

Independent distribution `pastport-stylization==0.1.0`, namespace
`pastport_stylization`. Depends one-way on `pastport-matched-environment==0.1.0` for reviewed
museum formats, metered execution, scene geometry and shared-content authority.
Matched Environment and Evidence never import this package. Main enables it through the
optional `authoring` extra; `authoring-codex` explicitly adds the provider.
Installation alone does not execute any workflow.

Install the Matched Environment wheel first, then this wheel, or install both through the
workspace. Add `[codex]` only to use the existing subscription adapter. Poppler
and ffmpeg remain explicit external tools for the workflows that need them.
No credentials, live databases or tour data are distributed.

## Typed API and commands

`pastport_stylization.sdk` exports `EnvironmentStylizationAgent`,
`AutomaticStyleRun`, `AutomaticStyleDelivery`, `StyleInput`, `AnimationRun`,
`AnimationDelivery`, `Style3DRun`, `Style3DDelivery`, and injected transport ports.
The source-bound appearance manifest `Style3DVariant` is owned by Matched Environment so that
review and export work without installing generation code. Image capability/result
wire models also stay with Matched Environment's shared metered execution boundary.

- `pastport-stylization-agent --help`: bounded planning, generation and review.
- `pastport-animate --help`: full-sphere panorama workflow.
- `pastport-style3d --help`: appearance processing with geometry unchanged.
- `pastport-stylize-studio --help`: separate local staff portal.

Existing grants, source hashes, isolated workspaces, cancellation/receipt and
bounded repair rules remain in force. A candidate is pending human acceptance;
no installation or offline test demonstrates visual quality or production safety.
Matched Environment's studio no longer mounts the stylization portal implicitly; launch its
separate command explicitly. Each standalone portal shows only its own navigation; Main frontend integration
requires an explicit composition adapter.

## Source responsibilities

| Source | Responsibility |
|---|---|
| `sdk.py` | Typed public facade |
| `application/`, `workflow/` | Panorama/3D orchestration, progress and bounded repair |
| `domain/` | Stylization commands, plans, reviews and deliveries |
| `adapters/` | Image transport and SPZ appearance processing |
| `api/`, `web/` | Separate local staff portal and preview |
| `animation_assets/` | Existing upstream style policy/reference resources |
| `UPSTREAM.md`, `LICENSE` | Source revision and retained notices |

This is a source split from the revision in UPSTREAM, not a claim that the upstream
branch itself already has three distributions. Prior private deep imports under
`pastport_matched_environment.application.stylization*` move to this namespace; shared readers
use `pastport_matched_environment.application.appearance`.

<!-- BEGIN FILE INVENTORY -->
## 文件结构与用途

每个文件的用途直接写在同一行。以下覆盖本范围内的 **43 个维护文件**；依赖环境、缓存、私有产物和历史备份不属于源码清单。

```text
stylization-sdk/
├── src/
│   └── pastport_stylization/
│       ├── adapters/
│       │   ├── __init__.py  # Independent PastPort appearance processing package.
│       │   ├── codex_image.py  # Subscription image edits using native Codex app-server image-generation events.
│       │   └── spz_style.py  # Bake a registered painted panorama into SPZ v2 DC appearance coefficients. The legacy SPZ layout/color constants follow Niantic's public format specification. No positions, scales, rotations, opacities or point counts are changed.
│       ├── animation_assets/
│       │   ├── approved-style-v2.json  # 第二版风格配置：参考图与策略文件哈希及验收准则。
│       │   ├── approved-style-v2.png  # 第二版批准风格参考图，供对应视点转绘对照。
│       │   ├── approved-style.png  # 第一版批准风格参考图，供转绘外观对照。
│       │   ├── policy-v1.txt  # 第一版转绘风格与几何保留策略。
│       │   └── policy-v2.txt  # 第二版转绘风格与细节保留策略。
│       ├── api/
│       │   ├── __init__.py  # Independent PastPort appearance processing package.
│       │   └── stylization_studio.py  # Upload, estimate and explicitly start supported VR/3D stylization jobs.
│       ├── application/
│       │   ├── __init__.py  # Independent PastPort appearance processing package.
│       │   ├── animation.py  # Complete-sphere animation of a labelled reference museum, without source writes.
│       │   ├── animation_cli.py  # Subscription-powered labelled-museum animation; no separate paid API fallback.
│       │   ├── animation_style.py  # Versioned user-approved visual standard shared by generation and criticism.
│       │   ├── automatic_stylization.py  # Format-independent job orchestration over the supported native VR/3D contracts.
│       │   ├── stylization3d.py  # Apply the existing panorama-animation output to an isolated real 3D asset.
│       │   ├── stylization3d_cli.py  # Bake existing full-sphere artwork into an isolated 3D appearance candidate.
│       │   ├── stylization3d_preview.py  # Serve one isolated styled tour with the existing review/3D runtime.
│       │   ├── stylization3d_tour.py  # One source-bound tour package in, one styled independent-world tour package out.
│       │   ├── stylization_agent.py  # Reference-guided agent with real model decisions and at most one repair round.
│       │   ├── stylization_agent_cli.py  # Run the standalone reference-guided agent through the existing metered SDK.
│       │   └── stylization_progress.py  # Read-only progress from actual execution receipts and saved Agent checkpoints.
│       ├── domain/
│       │   ├── __init__.py  # Independent PastPort appearance processing package.
│       │   ├── stylization3d.py  # Stylization-owned commands and delivery records; Museum owns appearance manifests.
│       │   └── stylization_agent.py  # Typed decisions for one initial generation and at most one repair round.
│       ├── web/
│       │   ├── styled-tour-preview.html  # 应用转绘外观后的导览预览页面。
│       │   ├── stylization.css  # 转绘工作台布局和样式。
│       │   ├── stylization.html  # 转绘工作台页面结构。
│       │   └── stylization.js  # 转绘工作台的任务配置、状态与预览控制。
│       ├── workflow/
│       │   ├── __init__.py  # Independent PastPort appearance processing package.
│       │   ├── animation.py  # Typed LangGraph entrypoint for chaining labelled VR -> animation -> Story Agent.
│       │   ├── environment_stylization.py  # Two typed paths sharing the existing panorama animation implementation.
│       │   ├── stylization3d.py  # Alternative typed LangGraph path alongside the original panorama animation node.
│       │   └── stylization_agent.py  # Independent LangGraph node; the agent owns its one-repair decision lifecycle.
│       ├── __init__.py  # Independent PastPort appearance processing package.
│       ├── py.typed  # PEP 561 类型标记，让安装方的类型检查器识别本包类型。
│       └── sdk.py  # Typed appearance API with injected, metered transports and no implicit execution.
├── tests/
│   ├── __init__.py  # Offline appearance package boundary tests.
│   └── test_sdk.py  # 回归测试：Reject malformed cross-package input and preserve resume style authority.
├── LICENSE  # 本模块的许可证；分发源码或安装包时保留。
├── README.md  # 本模块的使用入口、输入输出及完整文件用途说明。
├── UPSTREAM.md  # 上游来源、提取范围及归属说明；不是运行入口。
└── pyproject.toml  # 本项目的包名、依赖、命令入口与构建配置。
```
<!-- END FILE INVENTORY -->
