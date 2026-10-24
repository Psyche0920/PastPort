# Photo Document Tool — Active Plan

Owner: wehan. Specification: [technical PRD](technical/PRD_PDF_EVIDENCE_REVIEW.md).
Operations: [installation and running](../README.md).

| Task | Owner | Dependencies | Deliverable and acceptance | Status |
| --- | --- | --- | --- | --- |
| PDF-DOC | wehan | Original mapping demo; finite Codex grant | Photos + historical PDF to consistently numbered, traceable PDF and IDML; atomic paired output and repeat safety | Implemented; offline graph, repeat execution, PDF layout, IDML XML/media closure, strict typing and lint checked. Full fresh real-model and native InDesign acceptance pending |
| PDF-ISOLATE | wehan | User-confirmed independent branch boundary | Root-installable document tool; remove inherited main framework, game/VR code and unrelated docs/checks; preserve runtime data | Implemented; root locked install, command help, strict mypy (42 Python files), Ruff and standalone repository checks verified; main remains unchanged |

There is no planned integration into main, no review backend and no downstream structured API.
Do not start a live material run without explicit inputs and a finite authorized grant. Next
acceptance is a user-run real sample and native InDesign inspection; record actual issues rather
than claiming offline fixtures establish historical accuracy or cross-site reuse.
