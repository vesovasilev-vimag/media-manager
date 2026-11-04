# ViMag v1.1 — approved decision ledger

> **2026-11-04 Library-first amendment:** For NAS Library inspection, enrichment and normalization, [Library-first normalization](library-first-normalization.md) supersedes historical torrent-dependency gating below. Torrent records and `missingFiles` are not Library normalization blockers. Physical ownership, fingerprints, paths, collisions, exact approvals, leases, journal/recovery and production write authorization remain mandatory. Delete/quarantine and download/import retain their separate dependency protections.

**Version:** 1.1.0-spec.1 · 2026-11-02 · Documentation-only sync

| ID | Decision | Supersession / note |
|---|---|---|
| LIB-01 | Card + Table, server pagination both, search by title | RC1 limited page read fixed |
| LIB-02 | category/video quality/audio quality/audio language/subtitle language filters | API enhancement |
| LIB-03 | drop-down audio/subtitle tracks; video/audio technical metadata | Based on ffprobe data |
| LIB-04 | graphics all categories: file counts + actual storage volumes | Mock volumes not data |
| NAV-01 | collapsible sidebar, icon-only, content expansion | latest library wireframe v1.3 |
| BG-01 | detected BG audio accepted automatically, no manual confirmation UI | replaces AD-04c/AD-05 manual gate for v1.1 |
| SCAN-01 | incremental, missing → mark, probe only new/changed | not v1.0 full re-scan |
| HIER-01 | configurable nested folder tree by category, drag/drop, versions | settings don't mutate files |
| NAME-01 | drag/drop naming tokens, per category, live preview | safe policy version |
| HIER-02 | movie collections enabled, conditional `{CollectionName}`, manual override | TMDb Collection ID |
| META-01 | TMDb primary, linked IMDb ID where available, ambiguity review | don't hallucinate IDs |
| SUB-01 | strategy B: improve and supplement Bulgarian subtitles | don't overwrite unverified |
| SUB-02 | include FPS, file duration, encoding, edition, timing, completeness | explicit owner refinement |
| SUB-03 | latest accepted subs primary; previous `ver-02`, `ver-03`…; restore old | test Jellyfin visibility |
| BULK-01 | scopes file/selected/category/all; AUTO after one plan approval | phases specified |
| BULK-02 | per-file CONTINUE on problem, NeedsReview, pause/resume/retry/recovery | durable journal |
| BULK-03 | execution phases: identity → naming/hierarchy → subtitles → Jellyfin | owner decision A |
| QUAR-01 | scope BOTH: single and group; no auto cleanup; restore ORIGINAL | owner decision both/manual/original |
| DELETE-01 | scope BOTH: single and group; physically delete NAS media and ALL exclusive sidecars | supersedes v1.0 only for explicit delete |

## Important behavioural distinctions

- **SCAN:** read-only to NAS; **NORMALIZE:** approved rename/move/enrich, never auto-quarantine/delete.
- **QUARANTINE:** reversible move outside Library; **DELETE:** confirmed physical removal from Library and catalogue; do not invent a trash-management feature.
- **Legacy qBittorrent protection** and no global write enable persist, despite owner's opt-in to explicit delete as a v1.1 function.
- **BG detections** are accepted for UI/naming once identified by stream metadata; do not assert an undetected language or alter source media bytes.
- **Movie Collections** belong to versioned hierarchy, not hard-coded file structure.

## Matters reserved for engineering verification, not owner re-decision

- Accurate SMB/CIFS and hardlink semantics for selected file operations (preflight/blocked).
- Jellyfin subtitle version naming/default track visibility, collection folder recognition and refresh confirmation.
- Translation of effective file ownership from library inventory vs torrent payload and sidecar ownership.
- External TMDb/OpenSubtitles API quotas, subtitle version comparison accuracy and fallback coverage.
- Migration and job idempotency behaviour and failure injection under synthetic test fixtures.

Do not represent these as already validated on the production host. Documentation approval is not blanket operational authorization.
