# Changelog

## 2026-11-05

- Released the featured game *The Last Two Sacks / 最后两袋* as `maslan.tar.gz` (maslan-demo-2026-11-05-r1), built on the team-handover `maslan.tar.gz` room with the shared compiler and investigation blueprint, zero model and zero Marble calls. Updated the README and handoff download links.
- Organizer setup works on any computer: `python -m pastport organizer-init` creates the private `admin` account (password typed twice, hash only, 0600, never overwrites), the start command no longer needs one person's private paths, and a missing account file now names itself and the setup command. READMEs and technical PRDs use repository-relative commands.
- Routing tasks may set their own prompt, instruction and wrong-bin copy; investigation activity hints no longer mention one specific story.
- Verified: 12 engine choice combinations with 12 distinct ending texts; Chrome playthroughs in English, Chinese and at 390×844 with mid-game reload; isolated Organizer import, re-import and checksum match. Not verified: human playtest, Turkish, screen readers, historical review.

## 2026-11-03 — Finals handoff

- Updated the bilingual root handoff, READMEs and technical PRDs with the responsibilities of wcheung, maslan and wehan, the live demonstration order, and the Release-to-Organizer acceptance process.

## 2026-11-03 — IDML to playable 3D

- Added native IDML, linked graphics, site photos and existing SPZ/PLY input. Photo scanning retains coverage gaps, and IDML matching and audit run in groups of up to 16 identities with separate receipts.
- Registered the local 3D review version as Organizer history with a direct preview and Story continuation. The real run produced 108 recognized candidates, 48 source matches, 34 localized candidates and 30 projected 3D positions awaiting surface review.
- Generated Story and assembled an openable game. Published the playable baseline and startup instructions in the private Release. Startup from an extracted bundle was checked locally.

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
