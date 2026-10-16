# PastPort Coding Agent Guide

- Read README.md, then only the task-relevant sections. Product requirements: docs/PRD.md. Implementation, Skill protocol and T1–T7 tasks: docs/WORKFLOW.md. Code quality and CI: docs/ENGINEERING.md. Research origins: docs/REFERENCES.md.
- These main-branch documents are authoritative; other working-copy PRDs and the demo branch are historical references. Keep contracts in WORKFLOW, not duplicated in Skills. Review follow-through: docs/PRD.md section 13; ARCHITECTURE_REFINEMENT.md is only a redirect.
- Respect the requested deliverable: guidance/documentation work does not authorize implementation, new runtime files, CI changes or paid calls. Keep planned, implemented and verified states explicit.
- main is the reusable-framework branch; T1a shared contracts are implemented, while workflow/services/player remain pending. The complete pilot is on demo-muradiye. Do not copy its app/data/media/tests into main; derive minimal permitted fixtures only when implementing a task.
- Use skills/evidence-review or skills/narrative only for the relevant professional mode; their files are not a running Agent system.
- Preserve user changes, provenance, rights, human approval boundaries, stable IDs, project isolation and cumulative budgets. Keep site content in packages, not engine branches.
- Use the least expensive suitable model and smallest useful context. Work on one implementation task at a time; do not routinely delegate or reload full documents.
- After explicit implementation authorization, prioritize the smallest playable evidence–inference–choice–consequence slice. Preserve approval/budget boundaries; expand authoring UI only after the real-material pilot. Deterministic candidate ranking is a recommendation; initial direction selection requires a recorded human decision.
- Run relevant checks and inspect the diff. Contract setup/checks are in docs/CONTRACTS.md; also run uv run --no-sync python tools/check_repository.py; report planning checks separately from runtime/model/player validation. Do not push, merge or deploy without authorization.
