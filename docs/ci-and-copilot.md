# CI and Copilot

PastPort CI runs on pull requests, pushes to main, and manual dispatch. It uses GitHub Actions with read-only repository permission and pinned Action commits. Python 3.12 and Node 24 are the runtime families; setup resolves patches and logs the actual installed versions. No package installation, API key, source PDF download or model request is needed for these checks.

## Checks

| Check | What it verifies |
|---|---|
| quality | Python and JavaScript syntax; valid tracked JSON |
| python-tests | Five database tests using temporary databases, including narrative import, assets and editorial-task priority |
| player-tests | Eight deterministic tests for task gates, choices, consequences, save/restore and English/Chinese structure |
| ci | Fails unless every required job succeeds, including when an upstream job fails or is cancelled |

The five original photographs are tracked. The large inventory PDF and a developer's existing SQLite database are not required by CI. Tests must never overwrite the authoritative review database.

Run existing regression checks locally:

```bash
python3 -m unittest discover -s tests -v
node --test tests/test_story_engine.mjs
python3 -m compileall -q scripts tests
```

Use `node --check path/to/file.js` for changed JavaScript files. No third-party lint/type tooling has been configured yet. Ruff, strict mypy for new Python modules, browser smoke and dual-project package validation must be added with the corresponding implementation, not reported as passing now.

## Working with Copilot

Use a short task: objective, relevant paths, acceptance criteria and forbidden scope. Root AGENTS.md contains shared rules; .github/copilot-instructions.md is a short Copilot entry point. Copilot feature availability depends on the account plan and repository policy. Do not purchase or enable a paid overage to complete an ordinary task without authorization.

Let Copilot edit a small branch and run relevant tests. Review the actual diff and GitHub Checks results. Give it only relevant error lines when requesting a fix; expand context for approvals, budgets, migrations or cross-project state. Use optional AI review selectively rather than on every commit. Human code review and evidence/content approvals remain separate requirements.

## Merge controls

Configure the `ci` check as required on main when branch protection is available. Require a human reviewer and dismiss outdated approvals. Repository settings, account availability and a green workflow are separate facts; a workflow file alone cannot enforce a merge restriction.

## Verify the gate

From Actions > PastPort CI > Run workflow, leave `failure_probe` false for a normal run. Set it true only for an intentional failure test. This raises a test failure in quality and must make the final ci job fail while ordinary product tests remain unchanged. A red run titled as a failure probe is expected; run a normal check afterward. No source mutation or model charge is involved.

CI success is engineering evidence. It does not certify historical accuracy, publishing rights, route realism or player enjoyment. There is no deployment step in this workflow.
