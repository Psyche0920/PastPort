# PastPort Coding Agent Guide

- Read README.md, then only the task-relevant sections. Product requirements: docs/PRD.md. Implementation, Skill protocol and T1–T7 tasks: docs/WORKFLOW.md. Code quality and CI: docs/ENGINEERING.md. Research origins: docs/REFERENCES.md.
- main is the reusable-framework branch, currently at specification stage. The complete pilot is on demo-muradiye. Do not copy its app/data/media/tests into main; derive minimal permitted fixtures only when implementing a task.
- Use skills/evidence-review or skills/narrative only for the relevant professional mode; their files are not a running Agent system.
- Preserve user changes, provenance, rights, human approval boundaries, stable IDs, project isolation and cumulative budgets. Keep site content in packages, not engine branches.
- Use the least expensive suitable model and smallest useful context. Work on one implementation task at a time; do not routinely delegate or reload full documents.
- Run relevant checks and inspect the diff. The current check is python3 tools/check_repository.py; report planning checks separately from runtime/model/player validation. Do not push, merge or deploy without authorization.
