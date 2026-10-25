# Matched PDF + new VR automation

## Scope

Input: an already matched PDF containing numbered modern objects, photographic
references, historical associations and evidence; plus a fresh supported schema 4
static panorama tour. Output: the demonstrated VR presentation and editable review
backend. The browser is the complete user entrypoint; no interactive Codex session
or hand-authored intermediate data is required.

Photo-to-PDF creation, automatic matching from raw historical material, prior-result
replay, main-framework integration and cloud publishing are outside this branch's
current scope. Their exclusive entrypoints and implementations are removed.

## Fixed workflow and contracts

Register immutable PDF/tour assets, inspect matched entries and exact native source
quotations, review the historical relationship catalog, freshly localize each modern
object per viewpoint, audit hotspot overlays, review physical whole/part relations,
and assemble the reference review/VR runtime. Signatures and typed contracts live in
code; the shared policy is `prompts/environment_policy_v1.txt`.

Reuse the demonstrated UI and interaction, never its object answers or coordinates.
Preserve source numbering, evidence, original panorama bytes and navigation. A part
needs supported membership in its whole and a position consistent with attachment or
containment; uncertain/rejected parts retain evidence without independent hotspots.
Unknown visibility or localization produces explicit gaps, not invented positions.

## Execution, persistence and recovery

Use the existing SDK transport through immutable finite subscription grants and the
persistent execution ledger. Enforce bounded file/image inputs, explicit model
selection, cancellation and process ownership. No implicit provider fallback, paid
bypass, automatic uncertain retry or reset of unknown usage is permitted.

Different source inputs produce isolated result databases. Identical input/model/
policy in the same project reuses the existing result and human edits. Existing links
continue to point at their own result. Text/position edits persist with conflict and
version checks. Restart serves stored results without regenerating their database.
Legacy jobs from removed workflows remain on disk but are not offered by the portal.

Uploads use safe relative paths, bounded archive extraction and localhost/origin
protections. Imported scripts do not execute. Only packaged runtime code serves
results. Studio shutdown releases its owned build and result processes.

## Acceptance

The user manually checks runtime, output quality and placement and reports targeted
issues. This cleanup deliberately runs no tests, models or services at the user's
request. Prior synthetic or real-run evidence is historical, not validation of this
revision. Do not claim Demo-quality recognition or cross-site accuracy from assembly
or schema checks. The current plan and changelog record status and limitations.
