# RC1 evidence and acceptance traceability

**Status:** 67 Linux automated tests PASS; all 43 T and 17 IT identifiers traced below. External providers are emulated, PostgreSQL/filesystem/ffprobe/backup tools are real disposable fixtures. Live operational gates remain separate and unresolved. Sanitized results and source hashes: [automated evidence](rc1-automated-evidence.json).

Read `docs/technical-scope-v1.0.md` and `docs/implementation-design-v1.0.md` for the **full** test definitions. This table is an index; concise descriptions do not replace exact preconditions and expected behavior. Codex must populate every evidence entry and never pass a test merely because code exists.

State vocabulary: `NOT_RUN` → `PASS` / `FAIL` / `BLOCKED`; `PASS` requires a deterministic, executed test and an exact file/CI run reference. For live tests, include date, environment and sanitized observable result. If a scenario needs live infrastructure, report separate `CI` and `LIVE` evidence in the evidence column. Do not leak private media paths/hashes or secrets.

## A. Approved Technical Scope: 43 scenarios

| ID | Scenario (consult source for complete semantics) | Status | Exact automated test and live evidence |
|---|---|---|---|
| T-01 | New movie | PASS | `tests/acceptance/test_enrichment.py:82`; `tests/acceptance/test_workflow.py:18`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-02 | Existing 1080p verified BG, new 2160p EN | PASS | `tests/acceptance/test_policies.py:44`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-03 | Better new BG version | PASS | `tests/acceptance/test_policies.py:61`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-04 | Season pack с много епизоди | PASS | `tests/acceptance/test_workflow.py:42`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-05 | NAS unavailable по време на copy | PASS | `tests/acceptance/test_workflow.py:68`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-06 | BG subtitle timing mismatch | PASS | `tests/acceptance/test_enrichment.py:42`; `tests/acceptance/test_policies.py:350`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-07 | Ambiguous metadata | PASS | `tests/acceptance/test_policies.py:74`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-08 | Existing torrent dependency | PASS | `tests/acceptance/test_security.py:78`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-09 | completion event идва 3 пъти | PASS | `tests/acceptance/test_workflow.py:85`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-10 | crash след copy, преди DB update | PASS | `tests/acceptance/test_workflow.py:101`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-11 | qBt \`setLocation\` е отговорил 200, реалното местене продължава | PASS | `tests/acceptance/test_workflow.py:115`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-12 | qBt recheck открива incomplete pieces | PASS | `tests/acceptance/test_workflow.py:131`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-13 | destination collision | PASS | `tests/acceptance/test_workflow.py:142`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-14 | category се сменя преди cutover | PASS | `tests/acceptance/test_workflow.py:169`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-15 | symlink/path escaping извън позволения root | PASS | `tests/acceptance/test_policies.py:171`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-16 | няма peers/скоростта на upload е нула | PASS | `tests/acceptance/test_policies.py:197`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-17 | потребителят умишлено е спрял torrent | PASS | `tests/acceptance/test_policies.py:197`; `tests/integration/test_release_contracts.py:129`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-18 | Automatic Torrent Management / category path | PASS | `tests/acceptance/test_policies.py:207`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-19 | NAS не поддържа hardlinks | PASS | `tests/acceptance/test_policies.py:218`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-20 | ръчно редактиран NFO | PASS | `tests/acceptance/test_policies.py:237`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-21 | еднакъв TMDb ID, различна edition | PASS | `tests/acceptance/test_policies.py:68`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-22 | Jellyfin refresh accepted, scan не е приключил | PASS | `tests/acceptance/test_workflow.py:180`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-23 | два torrents сеедват общо съдържание | PASS | `tests/acceptance/test_security.py:78`; `tests/integration/test_release_contracts.py:108`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-24 | multi-episode + Season 00 | PASS | `tests/acceptance/test_policies.py:149`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-25 | \`bul\` audio tag, но реален звук на друг език | PASS | `tests/acceptance/test_policies.py:84`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-26 | Human BG verification с валиден stream fingerprint, copy без byte change | PASS | `tests/acceptance/test_enrichment.py:11`; `tests/acceptance/test_enrichment.py:112`; `tests/acceptance/test_policies.py:101`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-27 | Некоректен prior BG evidence за друг stream/file | PASS | `tests/acceptance/test_enrichment.py:11`; `tests/acceptance/test_enrichment.py:112`; `tests/acceptance/test_policies.py:130`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-28 | 1080p BG verified срещу 2160p EN със съществено по-добро качество | PASS | `tests/acceptance/test_policies.py:44`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-29 | Auto-match само по сходно title/year с competing provider IDs | PASS | `tests/acceptance/test_policies.py:74`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-30 | Quarantine proposal за inferior version с активен torrent dependency | PASS | `tests/acceptance/test_security.py:78`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-31 | Изрично одобрена quarantine без dependency и с валиден snapshot | PASS | `tests/acceptance/test_policies.py:279`; `tests/acceptance/test_security.py:99`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-32 | Непознат/ръчно редактиран \`movie.nfo\` или \`poster.jpg\` | PASS | `tests/acceptance/test_enrichment.py:146`; `tests/acceptance/test_policies.py:237`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-33 | BG subtitles са за неправилна edition или timing drift | PASS | `tests/acceptance/test_enrichment.py:42`; `tests/acceptance/test_policies.py:350`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-34 | NAS + qBt + Jellyfin verified, BG subtitles unavailable | PASS | `tests/acceptance/test_policies.py:365`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-35 | Jellyfin refresh 200, no recognized media entry | PASS | `tests/acceptance/test_policies.py:365`; `tests/acceptance/test_workflow.py:180`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-36 | Mixed torrent: единият Child има failed publish | PASS | `tests/acceptance/test_policies.py:365`; `tests/acceptance/test_workflow.py:194`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-37 | Достъп до UI/API без валидна admin сесия или с изтекла сесия | PASS | `tests/acceptance/test_security.py:12`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-38 | Невалидна/липсваща CSRF защита при approve или quarantine | PASS | `tests/acceptance/test_security.py:34`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-39 | Неавтентикиран completion hook опитва administrative command | PASS | `tests/acceptance/test_security.py:54`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-40 | ViMag-owned NFO/artwork с непроменен content hash | PASS | `tests/acceptance/test_policies.py:252`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-41 | Ръчно променен или непознат NFO/artwork, или Jellyfin NFO saver го е модифицирал | PASS | `tests/acceptance/test_policies.py:237`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-42 | Администратор опитва permanent library delete след одобрена quarantine | PASS | `tests/acceptance/test_security.py:64`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| T-43 | AD-16 cleanup на verified staging файл, докато library и quarantine assets съществуват | PASS | `tests/acceptance/test_policies.py:304`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |

## B. Implementation Design: 17 technical scenarios

| ID | Scenario (consult source for complete semantics) | Status | Exact automated test and live evidence |
|---|---|---|---|
| IT-01 | При първо включване се откриват 92 legacy torrents | PASS | `tests/acceptance/test_workflow.py:207`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-02 | Нов torrent се добавя с Manual TMM и \`savepath=/downloads/complete\` | PASS | `tests/contracts/test_adapters.py:12`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-03 | Категория с NAS savePath, но new Manual TMM | PASS | `tests/acceptance/test_policies.py:207`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-04 | \`temp_path_enabled=false\` и file exists при progress < 1 | PASS | `tests/acceptance/test_policies.py:207`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-05 | Паралелен duplicate polling/crawler event | PASS | `tests/acceptance/test_workflow.py:85`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-06 | Worker crash след изпратен \`setLocation\` | PASS | `tests/acceptance/test_workflow.py:101`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-07 | Предварително изтекъл resource lease по време на move | PASS | `tests/acceptance/test_workflow.py:236`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-08 | API key rotation/401 | PASS | `tests/contracts/test_adapters.py:66`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-09 | Temporary source still referenced by qBt/another torrent | PASS | `tests/acceptance/test_policies.py:304`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-10 | CIFS inode mismatch, но hardlink content shares writes | PASS | `tests/integration/test_operations.py:17`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-11 | Jellyfin scan API връща 200, но липсва item | PASS | `tests/acceptance/test_workflow.py:180`; `tests/contracts/test_adapters.py:101`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-12 | Стар qBt torrent със същия hash е remove/re-add | PASS | `tests/acceptance/test_workflow.py:218`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-13 | PostgreSQL restore върху празна dev среда | PASS | `tests/integration/test_operations.py:22`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-14 | Реалният Jellyfin token е невалиден/ревокиран | PASS | `tests/acceptance/test_workflow.py:271`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-15 | Издадено е ново приложение, а DB migration не е compatible с rollback | PASS | `tests/integration/test_operations.py:76`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-16 | Старо име на NFO е ръчно променено и хешът се различава | PASS | `tests/acceptance/test_policies.py:237`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |
| IT-17 | Нов torrent, добавен ръчно през VueTorrent след cutover | PASS | `tests/acceptance/test_workflow.py:255`; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. |

## C. Infrastructure/operational gates

| Gate | Known evidence as of kickoff | Remaining evidence | Status |
|---|---|---|---|
| G-01 qBittorrent | Web API authenticated GET works: qBt 5.2.0, API 2.15.1, existing 92 baseline, prefs and five categories inspected | New owned fixture: Manual TMM, local path, API rename/move, async completion, recheck and seeding; no legacy writes | PARTIAL |
| G-02 NAS | SMB/CIFS hardlink and shared-write tests passed on host and scratch Docker with UID:GID 1000:1000 | Actual Worker UID + production mount, qBt torrent store permissions and NAS disconnect | PARTIAL |
| G-03 Jellyfin | Library integration requirements documented | Real library types/root mapping, NFO/edition grouping, async item verification | OPEN |
| G-04 Recovery | Synthetic failure/replay, NAS failure, lease fencing and rollback tests PASS: `tests/acceptance/test_workflow.py`, `tests/integration/test_operations.py` | Host-specific recovery and restore rehearsal before pilot | PARTIAL |
| G-05 Media & quality | BG-first and identity policies approved | Representative media samples, stream-bound BG evidence, subtitle sync/provider checks | OPEN |
| G-06 Inventory | NAS category structure described; read-only inventory requirement approved | Full read-only catalog and torrent dependency mapping before maintenance | OPEN |
| G-DB-01 Database | Real disposable PostgreSQL migration down/up, pg_dump/restore, SKIP LOCKED, lease/epoch and concurrency tests PASS: `tests/integration/test_operations.py`, `tests/integration/test_release_contracts.py` | ViMag persistent volume permissions and host restore rehearsal | PARTIAL |

**Legacy freeze:** snapshot actual qBt torrent set at deployment, initially expected 92; immutable `LEGACY_READ_ONLY` baseline. Changes to existing torrents are forbidden.

## D. Release gating checklist

- [x] All 43 T scenarios implemented, executed, evidenced in synthetic automation; live gates separate.
- [x] All 17 IT scenarios implemented, executed, evidenced in synthetic automation.
- [x] Frontend lint/typecheck/unit/build passes; seven screens backed by real API.
- [x] Backend formatting/lint/types/tests and generated OpenAPI pass.
- [x] PostgreSQL migrations and backup/restore proven in disposable environment.
- [x] Auth/CSRF/secrets/path guards, safe cleanup and anti-legacy mutation regression passes.
- [ ] Container builds, reproducibility, image security scans and secret scans pass.
- [ ] Two Docker Hub images published with actual immutable digests and release manifest.
- [ ] On ViMag, backup/safety/permissions and read-only integration checked after deployment.
- [ ] Exactly one **new, authorized, harmless test torrent** tested after deployment; seeding and Jellyfin evidence attached.
- [ ] `WRITE_ENABLED` remains false outside explicit isolated test operation until controlled production cutover.
- [ ] `docs/rc1-release-report.md` contains truthful status, CI links, image digests, deploy status and remaining blockers.

**No intermediate owner sign-off is requested.** This file must be updated by Codex during the uninterrupted implementation, not filled with optimistic checkboxes.
