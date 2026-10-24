# PastPort PDF-to-VR Automation

This standalone branch starts from an independent documentation root. It specifies a clean implementation of PDF + panorama tour → numbered interactive VR + linked evidence review workbench. It does not contain main's application code.

Read the [technical PRD](docs/PRD_PDF_TO_VR_AUTOMATION.md) for architecture, main interface compatibility, processing stages, demo-derived acceptance and the integration plan.

The selected architecture uses LangGraph for a fixed workflow, with deterministic services and bounded model calls inside nodes. Initial runtime development does not require a freely planning agent.

| Work | Owner | Dependencies | Deliverable | Acceptance | Status |
|---|---|---|---|---|---|
| P0 Specification | wehan | Main target PRD/contracts; existing demo behavior | Technical PRD with interface mapping and functional cases | Reviewable contract differences and reproducible acceptance definitions | documented; runtime acceptance pending |
| P1–P5 Implementation | wehan, with affected main owners | P0 and pinned counterpart | Automatic pipeline, VR and workbench | PRD A01–A23 | pending |
| P6 Reuse/integration | wehan and affected owners | Second input set; standalone acceptance | Second-site run and selected-module main integration | PRD A24 and main regressions | pending |

There is no implemented command, model adapter or runnable server in this first documentation delivery. No private source media, review database or credentials are included.

After standalone validation, integrate selected new module files on a fresh main-based integration branch. Do not replace main's tree or blindly merge unrelated histories. Main compatibility and demo behavior are separate acceptance dimensions.
