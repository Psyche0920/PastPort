# PastPort Coding Agent Guide

- Start with `README.md` and `docs/README.md`; read only files relevant to the task.
- Current playable behavior is documented under `docs/demo/`. Product-wide target behavior and architecture are in `docs/product/PRD.zh-CN.md`; CI instructions are in `docs/engineering/ci-and-copilot.md`.
- Preserve user changes, evidence provenance, rights states, stable IDs, and project isolation. Keep site-specific content in data, not engine branches.
- Use the least expensive model and smallest useful context. Do not reload full documents or delegate routinely.
- Run relevant checks, inspect the diff, and report only verified results. Do not push, merge, or deploy without authorization.
