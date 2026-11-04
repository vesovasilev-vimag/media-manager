# Manual release publishing for ViMag v0.x

Workflow: `.github/workflows/publish-release.yml` — **Publish ViMag Release (manual)**. Owner must explicitly choose `main` and specify a release version such as `0.2.0`. PR merge does **not** publish an image.

The workflow runs reusable CI/Security; checks source version consistency across frontend package, lockfile and backend project; refuses an existing immutable Git tag; creates `vVERSION`; builds amd64/arm64 Docker Hub backend and web artifacts with provenance/SBOM; records SHA256 digests; and uploads a validated deployment manifest and bundle.

The existing `publish-v11.yml` and RC1 workflow remain historical and unmodified. This workflow never deploys. It cannot authorize changes to NAS, torrent state, or production write/intake settings.

**Important failure semantics:** Git tag creation precedes publication. If a build fails partway, do **not** delete/force-update the tag or reuse the image tag. Diagnose and agree a new owner-approved version for a safe retry. Never run two independent releases simultaneously.

Production deployment requires separate approval, verified off-host database backup/restore, schema compatibility and health/safety checks. Keep `VIMAG_WRITE_ENABLED=false` and `VIMAG_AUTOMATIC_INTAKE=false` for the v0.2.0 identification-only pilot.
