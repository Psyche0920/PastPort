# Photo Document Tool — Decisions

## 2026-10-24 — Output boundary

The user confirmed that historical PDF + multi-angle proxy photographs produce PDF and editable
IDML only. No review backend, VR matching, game or downstream data interface is included.
The next stage reads the resulting PDF as an ordinary document. Internal inventories, immutable
assets and execution receipts remain necessary private runtime records.

## 2026-10-24 — Independent root layout

The user confirmed this branch will not integrate into main. Remove inherited main application,
game/VR code, main schemas, unrelated references, tests, checks and framework documentation.
Move the already implemented document tool to the repository root and put installation/running
instructions in the root README. Preserve its PRD, safety/typing rules, source provenance,
licensed font, lockfile and runtime data. Main and other branches remain unchanged.

The old repository checker applied main's framework assumptions; it is removed with that product.
The independent checker validates this tool's source syntax and documentation references. Strict
mypy and Ruff remain separate required checks; no real-model or native-IDML acceptance is inferred.
