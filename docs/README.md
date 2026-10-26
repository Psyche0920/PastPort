# PastPort Documentation

Start with [PastPort_PRD_CN](PastPort_PRD_CN.md) or [PastPort_PRD_EN](PastPort_PRD_EN.md). They are two language editions of the same initial specification, with matching section IDs, interface names and acceptance IDs.

| Need | Read |
|---|---|
| Understand the product and team deliverables | PRD [part 1](PastPort_PRD_EN.md#part-product) |
| Implement contracts, main integration and parallel work | PRD [part 2](PastPort_PRD_EN.md#part-technical), especially [2.9](PastPort_PRD_EN.md#s2-9) |
| Implement the Story production coordinator and module handoffs | [Automation technical design](technical/STORY_AGENT_AUTOMATION.md) |
| Build stories, select/develop plugins and deliver a game | PRD [part 3](PastPort_PRD_EN.md#part-topic) |
| Run the existing code, inspect current APIs or recover a run | [Implementation Guide](IMPLEMENTATION_GUIDE.md) |
| Choose the next task, dependencies and acceptance | [Active Plan](ACTIVE_PLAN.md) |
| Understand significant accepted choices | [Decision Log](DECISION_LOG.md) |
| See verified deliveries from this initial baseline | [Change Log](CHANGELOG.md) |
| Use fixed target contracts and synthetic handoff examples | [SDK reference](technical/sdk-v1/README.md) |
| Maintain CI and Agent tooling | [CI guide](ci-and-copilot.md), [Agent rules](../AGENTS.md) |

The Chinese PRD defines the intended meaning if translation differs; correct both editions together. Actual code/generated schemas define existing executable behavior. Target SDK Schema 1.0.0, plugin API 1.0.0 and runtime wire 0.2.0 are not yet production capabilities. Current main remains wire 0.1.0 until implementation and acceptance.

Owners: **wehan** — shared contracts/main/VR Studio; **wcheung** — source reading/museum; **maslan** — Story Agent/game making/plugins. Each person edits their assigned paths; shared contracts have one owner.

Read the assigned task and relevant sections only. Source references, generated schemas and synthetic fixtures have practical uses and are retained; obsolete PRD copies and discussion histories are removed.
