# PastPort CI and Coding Agent Operations

Requirements: [PRD 2.10–2.11](PastPort_PRD_EN.md#s2-10). Exact configured jobs: [ci.yml](../.github/workflows/ci.yml). Existing commands: [Implementation Guide 14](IMPLEMENTATION_GUIDE.md#14-checks-ci-and-acceptance). Owner: wehan.

## Local configuration

The inspected workflow defines `quality`, `python-tests`, `browser-tests` and aggregate `ci`. Quality runs repository/handoff checks, Ruff, strict mypy and schema/declaration drift checks. Python tests run pytest plus module/fault acceptance. Browser tests install locked tooling and run JS/format checks plus Chromium workflow acceptance. Aggregate CI rejects failed, cancelled or skipped required jobs. Actions/dependencies are pinned, permissions are read-only and jobs are bounded.

The legacy handoff checker still allows only four files under docs/ and rejects the new canonical PRD/reference structure. The repository checker also needs explicit HTML anchor support. ENG-DOC in [Active Plan](ACTIVE_PLAN.md) tracks the required checker/test alignment. Current documentation delivery does not change workflow/tooling code or claim that CI passes.

## Use and verification

Run relevant deterministic checks locally; inspect PR Checks for the exact pushed revision. Configured YAML does not establish a successful remote run, enforced branch protection, license availability or deployment. Remote status, required check names, review enforcement and account-specific Copilot capabilities must be verified when used; no current remote verification is claimed here.

Coding Agents use root [AGENTS.md](../AGENTS.md); Copilot uses the short [entry point](../.github/copilot-instructions.md). Supply a bounded task, affected paths, contracts and acceptance. AI review is optional assistance; it does not replace deterministic checks, required human code review or professional content approval.

Ordinary CI uses disposable synthetic inputs, no paid providers, no production secrets/DBs and no full source-material downloads. Live provider checks require separate authorization and explicit usage limits. Public software/content publication is separately authorized. Preserve failure propagation, locked versions, minimal permissions, job timeouts and safe artifacts when extending CI.
