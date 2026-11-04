# ViMag Media Manager — release history and versioning

**Current source milestone:** **v0.2.0 (Extension)**, merged PR #13 on 2026-11-04 (merge commit `9afa8a355a2a8c562cdd33a35b0320f2de09f229`). A source milestone does **not** by itself mean that a Git tag, Docker image or production deployment exists.

## Official product sequence

| Product version | Milestone | Source / historical artifact |
|---|---|---|
| **RC-01** | First release candidate; initial import/pipeline baseline | Historical `v1.0.0-rc.1` image/tag and `docs/rc1-*` documents remain immutable. |
| **v0.1.0** | First Library maintenance and operational functionality | Historical v1.1 feature work and documents, including PR #4/#5. |
| **v0.1.1** | Increment build: Library dashboard, verified English naming and interaction improvements | PR #12, merge commit `3d34ecfa947840f7addc048eb465cde4ed079320`; historical Docker images published under `1.1.1` naming and deployed on ViMag. |
| **v0.2.0** | Extension: Library-first normalization, metadata enrichment, manual identification and review workflow | PR #13, merge commit `9afa8a355a2a8c562cdd33a35b0320f2de09f229`; production deploy/release publication must be independently verified. |

These are **retrospective product-version mappings**, not claims that the historical Git tags or container tags already exist as `v0.1.0`, `v0.1.1`, etc. Never rewrite or republish old tags/digests. Historical documents under `docs/v1.1/` and wireframes under `wireframes/v1.1/` retain their original paths so links and audit evidence do not break. Their `v1.1` headings refer to the original engineering baseline, **not** the canonical current product version.

## Numbering policy (owner-controlled)

- Before stable v1.0.0, the first component remains **0**.
- **Increment Build:** increase patch, e.g. `v0.2.0 → v0.2.1`.
- **Extension:** increase minor and reset patch, e.g. `v0.2.1 → v0.3.0`.
- The **owner explicitly decides** whether each change is Increment Build or Extension; CI/Codex must not choose a version bump on its own.
- v1.0.0 requires explicit owner approval.
- Version value must match the frontend package, lockfile, backend project metadata, release notes, Git release/tag and Docker image tag for each **newly authorized** release. Existing historical published artifact tags are never mutated.
- Release publication and production deployment are separate gates; neither is implied by a PR merge or by documentation changes.

## Release gates for v0.2.0

PR #13's CI (backend, frontend, browser) and Security (source and both container images) passed on head `ed01987564f95caf80dcb353a831adf21c7dfe66`. PR #13 merged on 2026-11-04. Live TMDb, NAS and Jellyfin production behavior were **not** tested as part of PR #13. Production writes and intake remain subject to existing authorization, backup, verification and controlled rollout requirements.

See [Library-first implementation](v1.1/library-first-normalization.md), [validation report](v1.1/library-first-report.md) and [production activation](v1.1/production-activation.md). The latter contains historical `1.1.0` examples; the release version must be selected from this document for future releases.
