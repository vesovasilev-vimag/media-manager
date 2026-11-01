# RC1 engineering decisions ledger

**Purpose:** Capture implementation-level choices made autonomously by Codex. This file is **not** an alternative to the approved Technical Scope / Implementation Design.

| Date | ID | Decision | Evidence / reason | Source conflict? | Validation |
|---|---|---|---|---|---|
| 2026-11-01 | KICK-01 | Full v1.0 scope, one uninterrupted RC1 implementation; no owner-facing checkpoints | Owner's Codex kickoff instruction | No | 43 T + 17 IT traceability |
| 2026-11-01 | KICK-02 | Keep automated development and CI tests, but perform real-device integration and one live torrent validation only after deployment | Owner's requested release order, security and legacy safeguards | No | CI reports + postdeploy evidence |
| 2026-11-01 | KICK-03 | PostgreSQL, four runtime containers and two custom images | Approved Implementation Design v1.0 | No | DB and Compose tests |

## Rules for further entries

| 2026-11-01 | ENG-08 | Preserve all rights to original application code until the owner grants a license; retain dependency notices | Implementation Design leaves public-code licensing open; no unsolicited grant | No | LICENSE and THIRD_PARTY.md |
| 2026-11-01 | ENG-09 | Runtime Python 3.13.18 / Alpine 3.24.3, FFmpeg 8.1.3, PostgreSQL 17.11 client/server; pinned image digests | Replaced old Debian/FFmpeg packages after actual Trivy findings; removed unused pip/ensurepip from runtime | No | Final container scans; patched-runtime Linux regression |
| 2026-11-01 | ENG-10 | Resource epochs increase across task owners and survive lease release; heartbeat renews only currently held epochs | Fault tests exposed revived expired sidecar leases; no task may revive unclaimed resources | No | PostgreSQL lease and pending-publication regressions |
| 2026-11-01 | ENG-11 | Unknown new paused/started state after recheck stops for review | Worker did not issue a stop, so it cannot attribute that state change to itself or override user intent | No | Intentional pause regression; live G-01 remains separate |

| 2026-11-01 | ENG-01 | Python 3.13.9, PostgreSQL 17, SQLAlchemy Core/Alembic; synchronous bounded Worker I/O | Four-container approved design; locks in backend/uv.lock and requirements*.lock | No | Executed Linux PostgreSQL acceptance suite; final evidence pending |
| 2026-11-01 | ENG-02 | Exact provider ID/type/year agreement or explicit human identity; no fabricated confidence score | G-05 calibration is still open; title/year alone yields candidates | No | tests/acceptance/test_policies.py |
| 2026-11-01 | ENG-03 | Quality recommendations require explicit material-improvement evidence; always preserve BG editions | No uncalibrated resolution/bitrate threshold | No | T-02/T-03/T-28 tests |
| 2026-11-01 | ENG-04 | Session 8h; Argon2id 64 MiB/3 iterations/4 lanes; 5 failed logins per username per 15min | Conservative initial security configuration; session hashes only in PostgreSQL | No | tests/acceptance/test_security.py |
| 2026-11-01 | ENG-05 | One NAS move at a time; 90s leases; 20s intake poll; retry budget 3; 100GiB/5% reserve | Initial conservative parameters, not production measurements | No | Runtime configuration; final NAS measurements remain gated |
| 2026-11-01 | ENG-06 | Recheck must be observed, followed by complete pieces; an accepted command alone cannot pass | Prevent stale completion snapshots from becoming recheck proof | No | tests/acceptance/test_workflow.py |
| 2026-11-01 | ENG-07 | Dev-only emulators; production configuration rejects emulated adapters and insecure cookies | Deterministic synthetic tests cannot stand in for live evidence | No | Linux test suite; production gates separately open |

For each undecided technical value, record date, stable ID, decision, evidence, alternative considered and test reference. Do not redefine product scope, silently downgrade a feature, hardcode private infrastructure data, or turn a missing external service into a fake `PASS`. Measured operational defaults belong in versioned configuration and test evidence.

Record blockers in the release report rather than asking recurring owner questions. If user input is truly unavoidable, finish all independent work before reporting a single, consolidated external dependency.
## ENG-12 — Autonomous RC tag preparation

The `codex/rc1` release workflow repeats CI/security, verifies the authorized Docker Hub namespace and token presence, then uses a narrowly scoped `contents: write` job to create the exact RC tag. It refuses any tag pointing elsewhere; publication checks out that tag and verifies its commit, and refuses existing image tags. This permits the authorized uninterrupted release without depending on workstation Git credentials. No production permission or write gate is changed.

## ENG-13 — Operational diagnosis and calibrated quality review

Worker emits local structured JSON state/task spans with reduced internal IDs and elapsed duration, without media paths, torrent hashes, HTTP payloads or exception repr. Authenticated readiness exposes Jellyfin independently and marks expired Worker heartbeats STALE. Quality comparison extracts actual ffprobe factors for both versions; source provenance and unknown HDR remain explicitly unverified. Until G-05 calibration passes, material improvement requires an explicit admin checkbox plus recorded reason, actor and time; resolution alone never supplies that evidence.
