# RC1 evidence and acceptance traceability

**Status:** INITIAL — tests not yet implemented or executed. This file is an evidence ledger, not a claim that any scenario passed.

Read `docs/technical-scope-v1.0.md` and `docs/implementation-design-v1.0.md` for the **full** test definitions. This table is an index; concise descriptions do not replace exact preconditions and expected behavior. Codex must populate every evidence entry and never pass a test merely because code exists.

State vocabulary: `NOT_RUN` → `PASS` / `FAIL` / `BLOCKED`; `PASS` requires a deterministic, executed test and an exact file/CI run reference. For live tests, include date, environment and sanitized observable result. If a scenario needs live infrastructure, report separate `CI` and `LIVE` evidence in the evidence column. Do not leak private media paths/hashes or secrets.

## A. Approved Technical Scope: 43 scenarios

| ID | Scenario (consult source for complete semantics) | Status | Exact automated test and live evidence |
|---|---|---|---|
| T-01 | New movie | NOT_RUN | — |
| T-02 | Existing 1080p verified BG, new 2160p EN | NOT_RUN | — |
| T-03 | Better new BG version | NOT_RUN | — |
| T-04 | Season pack с много епизоди | NOT_RUN | — |
| T-05 | NAS unavailable по време на copy | NOT_RUN | — |
| T-06 | BG subtitle timing mismatch | NOT_RUN | — |
| T-07 | Ambiguous metadata | NOT_RUN | — |
| T-08 | Existing torrent dependency | NOT_RUN | — |
| T-09 | completion event идва 3 пъти | NOT_RUN | — |
| T-10 | crash след copy, преди DB update | NOT_RUN | — |
| T-11 | qBt \`setLocation\` е отговорил 200, реалното местене продължава | NOT_RUN | — |
| T-12 | qBt recheck открива incomplete pieces | NOT_RUN | — |
| T-13 | destination collision | NOT_RUN | — |
| T-14 | category се сменя преди cutover | NOT_RUN | — |
| T-15 | symlink/path escaping извън позволения root | NOT_RUN | — |
| T-16 | няма peers/скоростта на upload е нула | NOT_RUN | — |
| T-17 | потребителят умишлено е спрял torrent | NOT_RUN | — |
| T-18 | Automatic Torrent Management / category path | NOT_RUN | — |
| T-19 | NAS не поддържа hardlinks | NOT_RUN | — |
| T-20 | ръчно редактиран NFO | NOT_RUN | — |
| T-21 | еднакъв TMDb ID, различна edition | NOT_RUN | — |
| T-22 | Jellyfin refresh accepted, scan не е приключил | NOT_RUN | — |
| T-23 | два torrents сеедват общо съдържание | NOT_RUN | — |
| T-24 | multi-episode + Season 00 | NOT_RUN | — |
| T-25 | \`bul\` audio tag, но реален звук на друг език | NOT_RUN | — |
| T-26 | Human BG verification с валиден stream fingerprint, copy без byte change | NOT_RUN | — |
| T-27 | Некоректен prior BG evidence за друг stream/file | NOT_RUN | — |
| T-28 | 1080p BG verified срещу 2160p EN със съществено по-добро качество | NOT_RUN | — |
| T-29 | Auto-match само по сходно title/year с competing provider IDs | NOT_RUN | — |
| T-30 | Quarantine proposal за inferior version с активен torrent dependency | NOT_RUN | — |
| T-31 | Изрично одобрена quarantine без dependency и с валиден snapshot | NOT_RUN | — |
| T-32 | Непознат/ръчно редактиран \`movie.nfo\` или \`poster.jpg\` | NOT_RUN | — |
| T-33 | BG subtitles са за неправилна edition или timing drift | NOT_RUN | — |
| T-34 | NAS + qBt + Jellyfin verified, BG subtitles unavailable | NOT_RUN | — |
| T-35 | Jellyfin refresh 200, no recognized media entry | NOT_RUN | — |
| T-36 | Mixed torrent: единият Child има failed publish | NOT_RUN | — |
| T-37 | Достъп до UI/API без валидна admin сесия или с изтекла сесия | NOT_RUN | — |
| T-38 | Невалидна/липсваща CSRF защита при approve или quarantine | NOT_RUN | — |
| T-39 | Неавтентикиран completion hook опитва administrative command | NOT_RUN | — |
| T-40 | ViMag-owned NFO/artwork с непроменен content hash | NOT_RUN | — |
| T-41 | Ръчно променен или непознат NFO/artwork, или Jellyfin NFO saver го е модифицирал | NOT_RUN | — |
| T-42 | Администратор опитва permanent library delete след одобрена quarantine | NOT_RUN | — |
| T-43 | AD-16 cleanup на verified staging файл, докато library и quarantine assets съществуват | NOT_RUN | — |

## B. Implementation Design: 17 technical scenarios

| ID | Scenario (consult source for complete semantics) | Status | Exact automated test and live evidence |
|---|---|---|---|
| IT-01 | При първо включване се откриват 92 legacy torrents | NOT_RUN | — |
| IT-02 | Нов torrent се добавя с Manual TMM и \`savepath=/downloads/complete\` | NOT_RUN | — |
| IT-03 | Категория с NAS savePath, но new Manual TMM | NOT_RUN | — |
| IT-04 | \`temp_path_enabled=false\` и file exists при progress < 1 | NOT_RUN | — |
| IT-05 | Паралелен duplicate polling/crawler event | NOT_RUN | — |
| IT-06 | Worker crash след изпратен \`setLocation\` | NOT_RUN | — |
| IT-07 | Предварително изтекъл resource lease по време на move | NOT_RUN | — |
| IT-08 | API key rotation/401 | NOT_RUN | — |
| IT-09 | Temporary source still referenced by qBt/another torrent | NOT_RUN | — |
| IT-10 | CIFS inode mismatch, но hardlink content shares writes | NOT_RUN | — |
| IT-11 | Jellyfin scan API връща 200, но липсва item | NOT_RUN | — |
| IT-12 | Стар qBt torrent със същия hash е remove/re-add | NOT_RUN | — |
| IT-13 | PostgreSQL restore върху празна dev среда | NOT_RUN | — |
| IT-14 | Реалният Jellyfin token е невалиден/ревокиран | NOT_RUN | — |
| IT-15 | Издадено е ново приложение, а DB migration не е compatible с rollback | NOT_RUN | — |
| IT-16 | Старо име на NFO е ръчно променено и хешът се различава | NOT_RUN | — |
| IT-17 | Нов torrent, добавен ръчно през VueTorrent след cutover | NOT_RUN | — |

## C. Infrastructure/operational gates

| Gate | Known evidence as of kickoff | Remaining evidence | Status |
|---|---|---|---|
| G-01 qBittorrent | Web API authenticated GET works: qBt 5.2.0, API 2.15.1, existing 92 baseline, prefs and five categories inspected | New owned fixture: Manual TMM, local path, API rename/move, async completion, recheck and seeding; no legacy writes | PARTIAL |
| G-02 NAS | SMB/CIFS hardlink and shared-write tests passed on host and scratch Docker with UID:GID 1000:1000 | Actual Worker UID + production mount, qBt torrent store permissions and NAS disconnect | PARTIAL |
| G-03 Jellyfin | Library integration requirements documented | Real library types/root mapping, NFO/edition grouping, async item verification | OPEN |
| G-04 Recovery | Operation journal/reconciliation design approved | Failure injection, restart/replay, duplicate-move protection, rollback proof | OPEN |
| G-05 Media & quality | BG-first and identity policies approved | Representative media samples, stream-bound BG evidence, subtitle sync/provider checks | OPEN |
| G-06 Inventory | NAS category structure described; read-only inventory requirement approved | Full read-only catalog and torrent dependency mapping before maintenance | OPEN |
| G-DB-01 Database | PostgreSQL persistent queue, locks and backup policy designed | Real disposable PostgreSQL migration/backup/restore, lease and crash safety tests | OPEN |

**Legacy freeze:** snapshot actual qBt torrent set at deployment, initially expected 92; immutable `LEGACY_READ_ONLY` baseline. Changes to existing torrents are forbidden.

## D. Release gating checklist

- [ ] All 43 T scenarios implemented, executed, evidenced (or explicit live-only blockade; never called PASS without evidence).
- [ ] All 17 IT scenarios implemented, executed, evidenced (or explicit live-only blockade).
- [ ] Frontend lint/typecheck/unit/build passes; seven screens backed by real API (no demo-only production UI).
- [ ] Backend formatting/lint/types/tests and OpenAPI/schema validation pass.
- [ ] PostgreSQL migrations and backup/restore proven in disposable environment.
- [ ] Auth/CSRF/secrets/path guards, safe cleanup and anti-legacy mutation regression passes.
- [ ] Container builds, reproducibility, image security scans and secret scans pass.
- [ ] Two Docker Hub images published with actual immutable digests and release manifest.
- [ ] On ViMag, backup/safety/permissions and read-only integration checked after deployment.
- [ ] Exactly one **new, authorized, harmless test torrent** tested after deployment; seeding and Jellyfin evidence attached.
- [ ] `WRITE_ENABLED` remains false outside explicit isolated test operation until controlled production cutover.
- [ ] `docs/rc1-release-report.md` contains truthful status, CI links, image digests, deploy status and remaining blockers.

**No intermediate owner sign-off is requested.** This file must be updated by Codex during the uninterrupted implementation, not filled with optimistic checkboxes.
