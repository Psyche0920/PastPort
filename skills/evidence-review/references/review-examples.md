# Evidence calibration: Muradiye

Load for difficult findings or policy calibration, not every batch. These examples use content from the demo-muradiye branch as test input, not freshly verified historical sources. Obtain the actual source snapshot and human decision before production adoption. Expected behaviors below are targets; no live model evaluation has been run.

## Three statements that must not collapse into one

1. A publication photograph shows an octagonal pool: candidate modern observation, supported only after inspecting the cited page/image.
2. The pool existed or was used in a particular way in the 1430s: separate time-specific historical claim needing evidence.
3. Cem left a delivery slip beside that pool: original fiction, never an archaeological finding.

The same image can support statement 1 without supporting 2 or 3. A good review narrows the record rather than approving all three or rejecting the whole source.

## Review examples

| Case and local input | Bad decision | Expected judgment/action |
|---|---|---|
| E01: photo-courtyard, claim-medrese-space; data/muradiye-story.json | Treat a modern glass cover as a 1430s clue because the photo is official | Separate present-day observation and period claim; inspect original locator; no approved period assertion from that photo alone |
| E02: fictional loading-slip/witness in the same story file | Count a fictional signature as corroborating a historical event | Keep props as original_fiction; evaluate their internal game logic elsewhere; do not add a historical support edge |
| E03: a Drive image is mapped to a filename but its building identity/rights have no review evidence | Approve mapping and publication because the folder is official | Retain provisional/unknown states independently; request mapping and reuse evidence; block final image use as required by policy |
| E04: two websites repeat one inventory passage | Increase confidence as if there were three independent sources | Record one origin chain; find a genuinely independent contrary/supporting source only where it matters |
| E05: old claims.publication_state defaults to approved | Import it as a real signed review | Preserve as legacy metadata; create pending target unless matching reviewer/decision/hash evidence exists |
| E06: a neighboring folder/site is selected | Infer a walkable direct connection or exact duration | Require location/entrance/edge evidence; preserve unknowns and scope decisions; folder proximity is not a route |
| E07: an external article appears only in search results | Cite a fabricated page or assert the full text was checked | Register a lead and retrieval failure; find an accessible authoritative original; do not claim inspected evidence |

## Output distinction

For a narrowed claim, return the source locator as supplied by the application and judgment reasoning. If no original is inspectable, return insufficient with a concrete request. Do not fill example hashes or reviewer names to make the record look complete.

Rights state is not the same as factual certainty. A correct statement can have an unusable image; an authorized photo can be incorrectly identified. Modern image provenance, historical time scope and rights each need their own finding.

## Weng's calibration task

For each case, compare the model's actual output with the expected boundary: correct entity/time, retrievable locator, support/refute relation, independent image/rights states and explicit unknowns. Count unsupported approvals, fabricated locators and missed conflicts separately. Any such critical failure blocks that policy/model configuration from production approval; do not hide it inside an average score.

Retain the exact input snapshot, Skill/policy/model hashes, actual output, human correction, latency/usage and whether external access occurred. Only revise the affected example/rule when a real failure warrants it. Local fixture success is not proof that a model researched the archive correctly.

Protocol boundary cases (index without claim IDs, optional unknown fields, review-required versus approval, cached tool replay and inaccessible originals) are defined in the [Skill protocol](../../../docs/WORKFLOW.md#17-具体合同用例待在-t1t3-执行). Use its canonical decision enum; do not invent mode-specific routing strings.
