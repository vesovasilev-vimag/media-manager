# Library-first implementation and validation report

Date: 2026-11-04. Baseline: v1.1.1 / PR #12 (`3d34ecf`). Dedicated branch: `feat/library-first-normalization`; target: `main`. The PR's head SHA identifies the delivered source.

Implemented independent Library normalization, full-library metadata inspection, authoritative English enrichment, persistent review evidence, manual TMDb search/ID lookup and corrections, per-asset reanalysis, filtered exact proposals and bidirectional duplicate/version evidence. Physical ownership, source integrity, collision, sidecar, authorization, revision/hash, lease and journal protections remain active. Delete/quarantine/import retain their existing dependency checks. See [workflow and API details](library-first-normalization.md) and [acceptance traceability](traceability.md#library-first-amendment-acceptance-2026-11-04).

## Local validation

| Check | Result | Evidence |
|---|---|---|
| Complete Linux backend suite, real disposable PostgreSQL, synthetic NAS | **137 passed** | `.test-artifacts/library-first-backend.xml`; test-only Docker image, all `tests/` |
| Frontend unit/component suite | **27 passed** | `.test-artifacts/library-first-frontend.xml` |
| Complete Chromium suite, desktop/mobile and real synthetic app stack | **11 passed** | `.test-artifacts/browser.xml`; new review/correction/preview screenshots at 1440px and 390px |
| Ruff formatting/lint, mypy | **PASS** | `ruff format --check backend/app tests`; `ruff check backend/app tests`; `mypy --config-file backend/pyproject.toml backend/app` |
| ESLint, TypeScript, Prettier, production frontend build | **PASS** | `npm run lint`, `npm run typecheck`, `prettier --check src tests *.json *.ts`, `npm run build`; local synthetic web image also builds |
| Bandit medium/high findings | **0** | `.test-artifacts/library-first-bandit.json` |
| Python locked dependency audit | **No known vulnerabilities** | `.test-artifacts/library-first-pip-audit.json`; Linux `pip-audit --require-hashes -r backend/requirements.lock` |
| npm dependency audit | **0 vulnerabilities** | `.test-artifacts/library-first-npm-audit.json` |
| Pinned gitleaks, redacted Git history scan | **No leaks** | 111 baseline commits scanned locally; PR Security workflow repeats on the committed head |
| Interactive Library v1.2 wireframe | **PASS** | Chromium: normalization filter, manual identification and refreshed review queue; `.test-artifacts/library-first-wireframe.png` |
| Generated OpenAPI and patch whitespace | **PASS** | `deploy/scripts/export-openapi.py`, `git diff --check` |

Local XML/JSON/screenshots are ignored test artifacts, not public production inventory. GitHub CI and Security repeat verification for the PR head, including container vulnerability scanning and the existing real Jellyfin compatibility fixture. Their current results are available on the PR; this report does not substitute old CI evidence for the new head.

The Windows npm advisory request initially failed inside the sandbox and succeeded using authorized network access. Windows pip-audit failed while preparing its temporary pip environment; the same locked audit passed in the isolated Linux test container. Initial browser lookup used exact label text including option contents; it was corrected to the accessible combobox role and the complete suite reran successfully. Backend tests emit the existing Starlette/httpx deprecation warning; no test was skipped or suppressed.

## Operational limits

- All media, database writes and provider responses used for tests were disposable synthetic fixtures. Live TMDb availability/translations, production SMB behavior and production Jellyfin recognition were not exercised.
- Exact title/type/year confirmation is deliberately conservative. Missing year, missing verified English authority, ambiguous candidates, supplementary material and conflicting manual decisions remain reviewable. No guessed translations or fabricated provider success.
- There is no schema migration in this change. JSONB inspection evidence and durable task kinds are additive; old approvals never authorize refreshed proposals. Historical dependency fields are preserved.
- No production NAS files, PostgreSQL records, qBittorrent torrents or settings were changed. Production write gates and deployment configuration were not enabled.
- No merge, release tag, release image build/publication or deployment is part of this delivery. Only local test/development images were built.

## Post-validation release ledger update

2026-11-04: CI and Security completed successfully (6/6), and PR #13 was merged to `main` (`9afa8a355a2a8c562cdd33a35b0320f2de09f229`). The accepted product-version designation is **v0.2.0 (Extension)**. References above to an unmerged PR describe the original submission and are retained for provenance. See [release history](../release-history.md). No live-provider or production validation is implied by the merge.
