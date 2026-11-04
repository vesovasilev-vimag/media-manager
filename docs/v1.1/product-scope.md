# ViMag Media Manager v1.1 — approved product scope

**Documentation version:** 1.1.0-spec.1 (2026-11-02)
**Scope status:** approved business behaviour; engineering decisions detailed separately.
**Environment:** ViMag Docker host, PostgreSQL, qBittorrent, NAS /mnt/nas/Movies/Library, Jellyfin; production RC1 remains READ ONLY.

## LIB — Library catalogue and presentation

- Library supports **Table View** and **Card View**, both with real server-side pagination, count, selectable page size, next/previous and stable sort. The same search/filter semantics apply in both views.
- Search by **title** (not only filesystem path); additional path search may remain.
- Filters: category, video quality (SD/HD/Full HD/2K/4K/8K as resolvable from stream dimensions), audio codec/quality, audio language, subtitle language. Display audio codecs/formats, channels/bitrate where known; list available audio and subtitle streams in compact dropdowns. Distinguish missing/unknown metadata from a proven absence.
- Category analytics replace four large KPIs: chart of **file counts** and chart of **actual storage volume** per category with legible values. Real count from initial inventory: Series 3315, Movies 590, Animations 122, Documentaries 92, Concerts 0; total 4119. This snapshot is *not* a production-live invariant. Use actual `probe.format.size` for aggregate volume; never present mock volumes as actual.
- Library primary actions are compact: row `...` menu for Normalize, Quarantine, Delete; selection checkboxes and bulk-action bar. The header contains bulk Normalize and read-only Scan. Each action has short, clear dialogs rather than large separate screens.
- Sidebar can collapse to icon-only mode to increase content width; navigation remains usable and keyboard accessible, tooltip/title on collapsed icons, persistence of display preference. Keep RC1 dark mint/teal visual language.
- Preserve existing filters, view toggles and both-view pagination across menu usage. Avoid the RC1 per-audio-stream `Confirm BG`/`Revoke BG` button clutter in Library UI.
- Bulgarian audio: **if an audio stream is detected/tagged as Bulgarian, treat it as present without manual verification** for this product workflow. Retain detection provenance and allow uncertainty where metadata is missing/contradictory. BG tagging must not fabricate a language. This v1.1 policy **supersedes** v1.0 manual BG verification requirements. Bulgarian-first preservation of valuable BG editions remains.

## SCAN-01 — incremental inventory

- Manual `Обследвай библиотеката` and potentially scoped inventory; read-only with respect to NAS data.
- Incremental scan: new assets inserted; modified assets refresh probe and metadata; unmodified assets reuse cached results (path + size + mtime fast path; fingerprint/identity when needed).
- Missing paths marked `MISSING`, **never automatically deleted**; if NAS or category traversal fails, do not falsely mark its assets as missing. Recovery/reappearance restores availability. Avoid duplicate assets on verified rename/move; ambiguous cases to review.
- One active scan per overlapping scope; progress, summary counts, errors and journal; safe under restarts.
- A catalogue record's availability is distinct from quarantine/mutation workflow state.

## HIER-01, NAME-01 — configurable hierarchy and naming

**Owner-approved English naming amendment (2026-11-04):** default normalized titles, collection folders and episode titles included in templates use authoritative English metadata. TMDb search/details request `en-US` and use localized `title` / `name`; original-language fields remain separate. Existing confirmed IDs are reused with English metadata. Missing English authority or conflicting explicit manual title overrides require `NeedsReview`, never guessed translation. Only an approved exact normalization plan may change filesystem paths. This supersedes the historical original-language naming default; Bulgarian-first audio preservation remains unchanged. See [English naming implementation](english-naming.md).

- Settings → Library Organisation: nested hierarchy tree with visual drag & drop; per-category hierarchy and optional levels; drag & drop naming tokens for folder/file/subtitle formats, individual rules by media type, live example and validation.
- Approved default hierarchy:
  `Library/Movies/<Movie Title (Year)>/<video>`;
  `Library/Series/<Series Title (Year)>/Season NN/<episode>`;
  `Library/Animations/{Movies,Series}/...`;
  `Library/Documentaries/{Movies,Series}/...`;
  `Library/Concerts/<Artist - Event (Year)>/...`.
- Top-level torrent category identifiers `movies, series, animations, documentaries, concerts` remain stable, even if library presentation rules change.
- Naming tokens include title, year, season, episode, episode title, resolution/quality, BG, edition, video/audio codecs, artist/event; rendering must handle unknown values, escaping, Unicode, collisions and Jellyfin conventions. Multi-edition grouping in a single work directory, separate edition identities; series standard `Season 01`, `S01E01`.
- Saved naming/hierarchy policies are **versioned**; modifying Settings **does not** rename/move real files. A separately approved Normalization plan executes changes. Preview old/new paths and exact affected items.

## HIER-02 — TMDb movie collections

- Enabled by default with optional level `{CollectionName}` for Movies, Animations/Movies and Documentaries/Movies.
- Obtain `belongs_to_collection`/TMDb Collection ID when available; group associated films within a collection folder, each individual film keeping its own folder, editions and subtitles.
- Missing collection: omit the conditional level (no `Unknown Collection`); allow an explicit manual collection override.
- Apply changes **only** via Normalization, not by saving Settings.

## META-01 — identity/metadata enrichment

- Use TMDb as primary work metadata provider, keep linked IMDb identifier when available; reuse validated IDs already known to ViMag/Jellyfin before external searches. Match type/year/season/episode/edition, disambiguate ambiguous titles.
- High confidence automatic identification, ambiguity → NeedsReview; do not invent IDs/years or replace known correct identities blindly. Cache and respect API quotas. Metadata art/NFO owned-sidecar policy from v1.0 still applies.

## SUB-01..03 — subtitle improvement, not mere download

- Strategy B **Improve and supplement**: assess existing external/embedded subtitles; search Bulgarian candidates by media ID/hash/release and episode; evaluate FPS, duration, encoding (UTF-8/Windows-1251), timing/synchronisation, completeness, edition, source quality, language and forced/SDH type.
- Avoid assuming equal FPS/timestamps proves sync; do not label unverified timing `Synchronized`. Preserve old subtitles, do not overwrite unknown/manual edits. Convert new text subtitle assets to UTF-8 only when reliable, without mutating original archives.
- After an accepted new normalization subtitle candidate, it becomes the **primary** `<video-stem>.bg.srt` (or format-appropriate suffix). Prior primary becomes `<video-stem>.bg.ver-02.srt`, older versions shift to `ver-03` etc. Version rollover and restore must be crash-safe/idempotent.
- Archive locations and subtitle filename syntax must be tested against Jellyfin; do not accidentally expose all version archives as competing default subtitle tracks. Restore a past version without losing the prior primary. No automatic replacement with an uncertain candidate.
- Provider adaptors: OpenSubtitles first candidate, support future additional compliant providers. Missing credentials → explicit unavailable state, not a fake success.

## BULK-01 — normalization

- Scope: individual file, selected files, one category or whole library. Future policy changes can trigger a new proposed plan.
- `Analyze → Preview → one approval → automatic execution` with phased stages: **(1) metadata/identity, (2) hierarchy/naming, (3) subtitle improvements, (4) Jellyfin refresh/verification**. File-level state and locks, durable journal, policy version snapshot and explicit old→new changes.
- Safe items proceed automatically; individual ambiguous/conflicted/blocked files go to NeedsReview while others **CONTINUE**. Preview includes counts, rename/move/sidecar proposals and blocked dependencies; an accepted plan does not authorize any unrelated deletion.
- UI: compact bulk Normalize entrypoint + plan view + progress by phase and file; Pause, Resume, Cancel remaining, Retry failed, recovery details and action history. Resume after restart without reapplying moves or double-rotating subtitle history.
- `NoChange` for already correct files. No automatic Quarantine or Delete within normalization.
- Legacy qBt torrents are protected from autonomous payload rename/move; safe owned sidecars may be handled only with explicit dependency/ownership checks.

## QUAR-01 — quarantine

- Single file or selected files; include owned/associated subtitles, NFO and artwork *only if they belong to the selected media*.
- Separate protected NAS quarantine area, outside Jellyfin library; reversible **Restore to original location**. Conflicts → NeedsReview, no overwrite. No automatic retention expiry or cleanup; manual disposition only.
- Record physical destination and original paths; separate per-file statuses in bulk; dependency-blocked files do not halt independent eligible files. Refresh Jellyfin after successful moves.
- Quarantine is not deletion.

## DELETE-01 — explicit physical deletion

- **Owner-approved v1.1 delta:** Delete physically removes selected video file(s) **from NAS Library** and removes their active catalogue entries after confirmed filesystem success. Supports single-file and bulk selection with one explicit operation confirmation.
- Also remove associated per-file subtitle versions, NFO and artwork when demonstrably exclusive to the selected item; do not delete shared series/collection sidecars or adjacent episodes.
- No added NAS trash/365-day retention workflow; no silent downgrade to database-only delete. A small audit/tombstone for evidence and stable reconciliation is allowed.
- Dependency on an active or legacy torrent **blocks** delete for that item. ViMag must not delete the torrent from qBittorrent. No delete during scan/normalization/quarantine implicitly.
- Failed delete: do not claim success or prematurely erase catalogue state; journal and reconcile actual outcome. On success request Jellyfin refresh. Existing v1.0 "no permanent delete" policy is superseded **only for this explicitly initiated, confirmed DELETE-01 operation**, not automated quality cleanup.

## Wireframes

- `wireframes/v1.1/vimag-library-operations-wireframe-v1.3.html` — current Library visual baseline (collapsed sidebar).
- `wireframes/v1.1/vimag-settings-library-organization-wireframe-v1.1.html` — Settings hierarchy/naming baseline.
- Wireframes are simulated demos. Missing details such as HIER-02 are authoritative in this spec even when not yet depicted in that older settings draft. When implementation begins, reconcile UX with these requirements rather than treating missing demo controls as unapproved.
