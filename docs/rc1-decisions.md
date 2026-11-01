# RC1 engineering decisions ledger

**Purpose:** Capture implementation-level choices made autonomously by Codex. This file is **not** an alternative to the approved Technical Scope / Implementation Design.

| Date | ID | Decision | Evidence / reason | Source conflict? | Validation |
|---|---|---|---|---|---|
| 2026-11-01 | KICK-01 | Full v1.0 scope, one uninterrupted RC1 implementation; no owner-facing checkpoints | Owner's Codex kickoff instruction | No | 43 T + 17 IT traceability |
| 2026-11-01 | KICK-02 | Keep automated development and CI tests, but perform real-device integration and one live torrent validation only after deployment | Owner's requested release order, security and legacy safeguards | No | CI reports + postdeploy evidence |
| 2026-11-01 | KICK-03 | PostgreSQL, four runtime containers and two custom images | Approved Implementation Design v1.0 | No | DB and Compose tests |

## Rules for further entries

For each undecided technical value, record date, stable ID, decision, evidence, alternative considered and test reference. Do not redefine product scope, silently downgrade a feature, hardcode private infrastructure data, or turn a missing external service into a fake `PASS`. Measured operational defaults belong in versioned configuration and test evidence.

Record blockers in the release report rather than asking recurring owner questions. If user input is truly unavoidable, finish all independent work before reporting a single, consolidated external dependency.
