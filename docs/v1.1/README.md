# ViMag Media Manager v1.1 — documentation baseline

**Status:** owner-approved product requirements consolidated on 2026-11-02; engineering implementation NOT started.
**Documentation version:** 1.1.0-spec.1. **Baseline:** existing `codex/rc1` source and published immutable `v1.0.0-rc.1` artifact.
**Scope:** library management, maintenance and approved UI; preserve existing RC1 ingest/seeding/security behaviour unless explicitly modified below.

## Read order for future implementation (not an instruction to start development)

1. `docs/v1.1/product-scope.md` — authoritative owner-approved behaviour and UI decisions.
2. `docs/v1.1/engineering-contract.md` — engineering constraints, API/data model and acceptance.
3. `docs/v1.1/decisions.md` — decisions ledger, supersession and explicitly unverified technical matters.
4. `wireframes/v1.1/vimag-library-operations-wireframe-v1.3.html` — approved interactive Library visual reference.
5. `wireframes/v1.1/vimag-settings-library-organization-wireframe-v1.1.html` — approved Settings visual reference.
6. Original `docs/technical-scope-v1.0.md`, `docs/implementation-design-v1.0.md`, `AGENTS.md`, `docs/rc1-release-report.md` — still apply for unaffected architecture and non-negotiable safety.

## Source-of-truth precedence

For v1.1 work only: explicit owner decisions in v1.1 docs take precedence over conflicting v1.0 product decisions (notably BG language confirmation and specifically authorized physical delete). Unaffected v1.0 engineering safeguards remain in force. An approved mock/wireframe does not confer operational permission for writes.

## Workflow / repo sync checkpoint

This documentation branch is **documentation-only**, not a Codex implementation branch. Do not modify application source, deploy, toggle `VIMAG_WRITE_ENABLED`/`VIMAG_AUTOMATIC_INTAKE`, process existing torrents, or re-tag `v1.0.0-rc.1` as part of documentation sync. First verify repository links and file contents, review/merge docs as agreed, then separately prepare a short Codex kickoff referring to the repo paths and commit.

## Versioning

- **v1.0**: immutable RC1 release + historical approved source documents; do not overwrite.
- **v1.1**: additive versioned documentation and wireframes under `docs/v1.1/` and `wireframes/v1.1/`.
- `spec.1` is a documentation baseline, **not** a release version, image build or deployment approval.
