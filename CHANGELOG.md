# Changelog

## 2026-11-02 — Organizer raw 3D workflow baseline

### Added
- Import existing SPZ scenes and triangular PLY meshes through the Organizer workflow without Marble generation. Derive local scene views and retain input identities and provenance.
- Persist the selected project and prepared source across reloads and sign-ins; provide continuation from project history.
- Cover overhead and floor objects in raw 3D localization, with independent point review and per-object outcomes. Unconfirmed positions remain gaps rather than fabricated anchors.
- Version new photo and PDF matching policies separately from existing execution receipts. Broader candidates still require historical evidence.

### Fixed
- Prevent previous projects' review state and Story readiness from leaking into newly selected materials.
- Keep environment preparation disabled while queued or running.
- Preserve browsing records and click bindings for optional source objects, including numbers 8 and 14, without granting task completion.
- Permit geometry-only repair and full compatibility revalidation of an existing Story in a separate output version.
- Support the tested collider profile in offline spatial assessment and preserve reviewed positions, source authority and navigation.
- Preserve completed execution results and unknown usage when explicitly recovering interrupted work; retain call ceilings and no automatic retries.

### Validation and limits
- Main source type checks, 20 Evidence SDK tests, the environment SDK suite, nine affected JavaScript tests, and repository/documentation checks passed.
- The broader root regression run was interrupted after a subprocess-start timing assertion failed; it is not reported as a full-suite pass. The isolated assertion passed on recheck; the broader suite remains unverified as a whole.
- Real bounded localization used exactly two authorized model calls: numbers 12 and 19 passed independent review and were included in a new Admin build. Numbers 16 and 17 remain unlocated. This is not historical approval or complete-object coverage.
- The rebuilt game passed resource checks; number 12 was rendered and clicked to open its source popup. Existing PDF and Story were not regenerated.
- IDML import, external historical research and the newly discussed player-facing exclusion policy are not implemented by this baseline.
- Private source materials, credentials, accounts, execution databases and generated game packages are excluded from Git.
