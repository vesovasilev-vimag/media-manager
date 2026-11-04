# ViMag Media Manager v1.1

> **2026-11-04 Library-first amendment:** For NAS Library inspection, enrichment and normalization, [Library-first normalization](library-first-normalization.md) supersedes historical torrent-dependency gating below. Torrent records and `missingFiles` are not Library normalization blockers. Physical ownership, fingerprints, paths, collisions, exact approvals, leases, journal/recovery and production write authorization remain mandatory. Delete/quarantine and download/import retain their separate dependency protections.

**Status:** owner-approved requirements consolidated on 2026-11-02; implementation separately authorized by the owner on 2026-11-02 on `codex/v1.1-library-maintenance`, [PR #4](https://github.com/vesovasilev-vimag/media-manager/pull/4). See [progress](implementation-progress.md), [engineering decisions](implementation-decisions.md), [traceability](traceability.md), and [operations/recovery](operations-and-recovery.md). No production release/deployment is authorized by this work.
**Documentation version:** 1.1.0-spec.1. **Baseline:** existing `codex/rc1` source and published immutable `v1.0.0-rc.1` artifact.

**Implementation handoff:** the repository owner merged PR #4 during verification; [PR #5](https://github.com/vesovasilev-vimag/media-manager/pull/5) holds the final quarantine-state upgrade compatibility correction. See the [implementation report](implementation-report.md) for commit/check evidence and deployment prerequisites.
**Scope:** library management, maintenance and approved UI; preserve existing RC1 ingest/seeding/security behaviour unless explicitly modified below.

## Approved requirements and reference read order

1. `docs/v1.1/product-scope.md` — authoritative owner-approved behaviour and UI decisions.
2. `docs/v1.1/engineering-contract.md` — engineering constraints, API/data model and acceptance.
3. `docs/v1.1/decisions.md` — decisions ledger, supersession and explicitly unverified technical matters.
4. `wireframes/v1.1/vimag-library-operations-wireframe-v1.3.html` — approved interactive Library visual reference.
5. `wireframes/v1.1/vimag-settings-library-organization-wireframe-v1.1.html` — approved Settings visual reference.
6. Original `docs/technical-scope-v1.0.md`, `docs/implementation-design-v1.0.md`, `AGENTS.md`, `docs/rc1-release-report.md` — still apply for unaffected architecture and non-negotiable safety.

## Source-of-truth precedence

For v1.1 work only: explicit owner decisions in v1.1 docs take precedence over conflicting v1.0 product decisions (notably BG language confirmation and specifically authorized physical delete). Unaffected v1.0 engineering safeguards remain in force. An approved mock/wireframe does not confer operational permission for writes.

## Workflow / repo sync checkpoint

The documentation-only checkpoint below is historical. The owner's later implementation kickoff separately authorizes the feature branch above, while retaining the production safety boundary.

This documentation branch is **documentation-only**, not a Codex implementation branch. Do not modify application source, deploy, toggle `VIMAG_WRITE_ENABLED`/`VIMAG_AUTOMATIC_INTAKE`, process existing torrents, or re-tag `v1.0.0-rc.1` as part of documentation sync. First verify repository links and file contents, review/merge docs as agreed, then separately prepare a short Codex kickoff referring to the repo paths and commit.

## Versioning

- **v1.0**: immutable RC1 release + historical approved source documents; do not overwrite.
- **v1.1**: additive versioned documentation and wireframes under `docs/v1.1/` and `wireframes/v1.1/`.
- `spec.1` is a documentation baseline, **not** a release version, image build or deployment approval.

## Current Library UX reference (PR #12)

Use [Library interactive wireframe v1.2](../../wireframes/vimag-media-manager-library-v1.2.html) alongside [Library dashboard specifications](library-dashboard.md) and [English naming](english-naming.md) for current Library designs. The [full-product v1.0 wireframe](../../wireframes/vimag-media-manager-v1.0.html) is historical for the Library area; its old demo explorer must not be treated as the latest Library UX contract. No merge, image publication, deploy, or production write is authorized by this documentation update.
