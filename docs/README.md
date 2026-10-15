# PastPort Documentation Map

These documents have different authority; keep the playable pilot separate from the product target.

| Area | Read this | Authority |
|---|---|---|
| Current Muradiye Demo | [`demo/en/`](demo/en/) and [`demo/zh/`](demo/zh/) | Describes the existing pilot and its evidence limits. The running code is the final source for implementation status. |
| Product-wide plan | [`product/PRD.zh-CN.md`](product/PRD.zh-CN.md) | Canonical target requirements, reusable architecture, workflow, milestones and acceptance. Planned work is not implemented merely because it appears here. |
| Implementation blueprint | [`implementation/muradiye-to-reusable-framework.md`](implementation/muradiye-to-reusable-framework.md) | Operational module contracts, workflow transitions, implementation stages and second-site acceptance derived from the existing Muradiye artifacts. |
| Coding implementation contract | [`implementation/workflow-contract.md`](implementation/workflow-contract.md) | Canonical engineering fields, node contracts, state, persistence, recovery, API, runtime rules and task-by-task acceptance. Read only the sections needed for the current task. |
| CI and Coding Agent operations | [`engineering/ci-and-copilot.md`](engineering/ci-and-copilot.md) and repository [`AGENTS.md`](../AGENTS.md) | CI setup/maintenance and short task-routing guidance. Detailed code quality requirements are in PRD section 11. |
| Official source directory | [`Osmangazi_Google_Drive_Directory_Guide.xlsx`](../Osmangazi_Google_Drive_Directory_Guide.xlsx) | Inventory of the provided Osmangazi folder structure; it does not prove every folder is game-ready. |

The removed `workflow.md` and `scoring-and-acceptance.md` copies duplicated or contradicted the PRD. Their current requirements belong in the PRD; the Demo folder retains only implementation-specific reference material.
