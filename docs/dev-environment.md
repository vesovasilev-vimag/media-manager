# ViMag Media Manager — developer environment (Windows / VS Code / Codex)

The repository is prepared as a **single Codex kickoff**, not an incremental owner-review project. Production ViMag is for **deployment and the final controlled integration test**, never for source builds or routine development.

## One-time workstation preparation

Required on the Windows development machine:

1. **Git**, **VS Code** and the **Codex extension / authenticated Codex environment**.
2. **Docker Desktop with Linux containers (WSL2 backend)**, enough local disk space for PostgreSQL and synthetic video fixtures.
3. Node.js, Python, and supporting linters as pinned by the implementation; the agent may install them in its isolated workspace. Prefer `docker compose` for reproducibility.
4. Internet access to GitHub and, for final release, Docker Hub. No VPN/NAS mounts are required in dev.

Start from PowerShell (only this is manual setup; it does not start a service):

```powershell
git clone https://github.com/vesovasilev-vimag/media-manager.git
cd media-manager
code .
```

Then start Codex on the repository with the instruction:

> Read AGENTS.md, docs/rc1-kickoff.md, docs/technical-scope-v1.0.md, docs/implementation-design-v1.0.md and the approved wireframe. Implement the **entire** approved v1.0 scope autonomously through v1.0.0-rc.1. Do not stop to ask me questions, show intermediate demos or request intermediate manual tests. Run and fix automated CI/development tests yourself; publish images to Docker Hub when secrets are available; deploy only after the release and safety preflight, then perform integration tests and one new isolated test torrent. Never modify legacy torrents.

The agent should use `codex/rc1` as its working branch (or a branch it creates from up-to-date main). Do not manually copy or paste the 25-section implementation document into Codex: it is already in the repository.

## Environment and secrets (never commit values)

GitHub Actions repository secrets needed **when the release workflow is configured**:

- `DOCKERHUB_USERNAME` — expected registry account `vesovasilev`.
- `DOCKERHUB_TOKEN` — a scoped Docker Hub access token with permission to push the two images.

Set these through GitHub repository **Settings → Secrets and variables → Actions → New repository secret** (or an equivalent managed GitHub environment). The GitHub connector used for docs cannot read or write those secrets. Do not send secret values to ChatGPT/Codex messages.

The production deployment later needs separate, locally provisioned secret files (file modes 0600/0700 where appropriate): PostgreSQL credentials, a qBt machine API key (or another authenticated method supported by the adapter), **a freshly rotated Jellyfin token**, TMDb and approved subtitle provider credentials. Do not embed credentials in source code, image layers, Compose YAML or GH logs.

The production host/Traefik network and qBt/Jellyfin access already exist, but runtime mount permissions, API keys and backups must be validated during controlled deployment; do not assume they are ready because host hardlinks worked in a scratch probe.

## Reproducible dev launch — to be implemented by Codex

Codex must provide `deploy/compose.dev.yaml`, `.env.example`, dependency lockfiles and a documented one-command local start/stop. The dev stack must use:

- Four services: web, api, worker, PostgreSQL.
- Disposable fake qBt/Jellyfin adapters and deterministic media fixtures.
- Local Docker-managed DB/files, **not** host NAS paths and never real qBt data.
- Local-only ports, health checks and a seeded demo account created safely during first-run setup (no hardcoded production password).

Codex runs and fixes tests internally. The owner will not perform interim manual regression checks; a final RC1 report is required.

## Packaging, release and deployment order

`Code complete → CI/security/fixture checks green → GitHub Actions build → Docker Hub push → pin image digests → backup/preflight → ViMag deployment (WRITE_ENABLED=false) → postdeploy integration → one new test torrent → release report`.

Only final deployed integration uses the real qBt Web API, NAS CIFS mounts and Jellyfin. Tests must be observational or isolated-scratch by default. No legacy torrent or existing library asset may be moved or removed during test.

## What cannot be automated without access

The agent cannot invent a Docker Hub token, a qBt API key, a fresh Jellyfin token, real Host SSH access, DNS/TLS certificates, a provider account, or permission to mutate existing media. On such blockers, complete all accessible code, deterministic tests, documentation and release workflows, then accurately report blocked steps rather than repeatedly asking for input or faking a published/deployed candidate.
