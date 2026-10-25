# Environment Stylization Agent

Owner: wehan. Branch: `codex/environment-stylization`.

This is a standalone application Agent and typed LangGraph node, not a new chat,
provider or global Codex configuration. Model decisions are real SDK calls: the
Agent plans the art direction from images, examines generated imagery and decides
whether severe defects justify one repair. Code retains import/export, source and
identity checks, budgets, locks, cancellation behavior and the repair limit.

## Approved standard

`animation_assets/approved-style-v2.png` is the exact viewpoint-two sample accepted
by the user. Its hash, policy hash and criteria live in `approved-style-v2.json`.
The image is supplied to both planning/generation and every reviewer call. Text
states preservation and operational constraints; it does not substitute for the
reference image. The model judges observable blur, major style departure, object
or structural changes and conflicting shared distant features. Small aesthetic
differences are minor and do not trigger repainting. Perspective, occlusion and
normal equirectangular distortion are not automatically treated as conflicts.

## Execution contract

Input: `AutomaticStyleRun`, using an inspected supported native VR/3D `StyleInput`,
a fresh isolated workspace and one finite `SubscriptionGrant`. The Agent accepts
1–6 viewpoints within the existing 100-call grant. Larger inputs need separately
planned batches; they cannot silently exceed this limit. Outputs retain the
original object IDs, evidence, editable introductions and navigation contract.

1. Freeze the approved reference, base policy, request and original image evidence.
2. Ask the model to plan art direction and cross-view consistency; missing source
   information can produce a saved needs-input result rather than invented data.
3. Generate the initial whole tour using the existing six-direction workflow.
4. Review every source/output panorama pair against the reference, then review
   adjacent viewpoint pairs for supported cross-view conflicts.
5. If there are no critical findings, return the candidate without repainting.
6. If there are critical findings, generate one complete repair round with the
   findings and prior candidates as constrained context, then review it once.
7. Return the final candidate and report. Remaining severe findings are flagged;
   there is no second repair, automatic allowance increase or endless loop.

The repair is a complete tour round, not selective inpainting. This keeps the
existing assembly route and gives an explicit worst-case allowance. It can cost
more than a future targeted repair tool. No second model review can route back
to generation after that round.

The model receives source and generated **panorama images**, not screenshots of
walking through the 3D renderer. `model_review_pass` therefore means image-review
pass, not human acceptance, repaired geometry, verified hidden surfaces or accepted
3D walking. Non-adjacent pairs are not exhaustively compared. Current SPZ baking
and opt-in surface projection retain their documented limits.

## Allowance and recovery

One durable `SubscriptionExecutor` ledger covers planning, images and reviews.
Both semantic and image transports use the existing Codex subscription route.
For N viewpoints, the normal route requires 8N model calls; the worst case with
one complete repair and a final review requires 16N−1. For two viewpoints that is
normally 16 and at most 31: 12 initial image calls, up to 12 repair image calls,
plus planning and reviews. Unused reserved calls are not dispatched.

The staff page displays this estimate before start. Limits remain optional: blank
uses the displayed finite suggestions; a smaller call budget cannot start a run
that cannot cover its declared worst case. Token estimates include an unmeasured
review allowance, not a guaranteed price. A token threshold gates subsequent calls
and cannot cap the in-flight turn's usage. No generation starts on upload.

Resume retains the original grant, reference, policy and frozen stage requests.
Completed SDK receipts are reused. Unknown usage remains recovery-required and
is never cleared by changing workspaces or automatically retrying. Old jobs retain
their original pipeline mode. Each upload creates a fresh task and new generation
workspace, even for identical files. Environment grouping is only for display;
only explicit resume of the same run reuses its own completed receipts.

## API and LangGraph

CLI: `pastport-stylization-agent --request /absolute/path/to/automatic-run.json`.
The request uses the same `AutomaticStyleRun` contract as the upload adapter.
`EnvironmentStylizationAgent(ffmpeg, semantic, images)` accepts injected transport
ports. `StylizationAgentNode` and `build_stylization_agent_graph` expose the Agent
as one node to the parent graph. Domain models do not import SDKs or frameworks.

`AutomaticStyleDelivery` adds `agent_report` and `model_review` while retaining the
same archive/environment/tour fields. Reports, the plan, approved standard,
reference and policy are added to the output archive. The staff record exposes
Agent review separately from Preview/Download. A saved output is a candidate;
model approval never becomes human approval or historical evidence.

## Source-purpose map

| Source | Purpose |
|---|---|
| `application/animation_style.py` | Validated approved reference and frozen-resume style resolution |
| `animation_assets/approved-style-v2.*`, `policy-v2.txt` | Actual approved sample, hashes and preservation policy |
| `domain/stylization_agent.py` | Typed planning, findings, severity and final report |
| `application/stylization_agent.py` | Bounded model/tool decisions and one-repair lifecycle |
| `application/stylization_agent_cli.py` | SDK transport composition and CLI |
| `workflow/stylization_agent.py` | Parent LangGraph adapter |
| `api/stylization_studio.py` | Staff consent, estimates, records and review download |

Validation: scoped strict mypy, Ruff, JavaScript syntax and diff checks only. No
new live model/Agent run or runtime/browser acceptance test was performed for this
implementation. The user performs output acceptance; new paid generation was not
triggered to validate code. The standalone checkout lacks `tools/check_repository.py`,
so that repository gate is not reported as passing.

## Live progress

`application/stylization_progress.py` reads completed execution receipts and saved
Agent phase files without modifying them. The staff page shows planning, initial
generation, reference/pair reviews, optional single repair, final review and saving;
per-view direction counts and review counts are actual saved work. Progress is not
an acceptance score or an invented global percentage. Unavailable/stale data is
reported rather than assumed successful. The current-task panel is above preview.

`GET /api/stylization/progress` serves the typed snapshot after normal server startup.
For an already running service, a temporary read-only bridge can publish sanitized
snapshots beneath the ignored `web/.runtime` cache, served by the existing static
route. It is bounded to at most one day and the owned parent process lifetime.
This lets the page update without restarting an active model job. New server
starts use the normal API. No prompts, source paths, secrets or provider payloads
are exposed in the progress snapshot; it cannot dispatch, resume or change usage.
