# ViMag Media Manager — Implementation Design v1.0

**Документ:** `docs/implementation-design-v1.0.md`  
**Статус:** **ОДОБРЕН — Implementation Design v1.0; разрешен за публикуване в GitHub**  
**Дата:** 01.11.2026 г.  
**Repository:** [vesovasilev-vimag/media-manager](https://github.com/vesovasilev-vimag/media-manager)  
**Нормативна основа:** [Technical Scope v1.0 — APPROVED](technical-scope-v1.0.md), Interactive Wireframe v1.0  
**Обхват на настоящия документ:** реализационна архитектура, данни, интерфейси, контейнеризация, доставки, тестове и безопасен cutover.  
**Не е разрешение за:** промяна на qBittorrent конфигурация, работа върху 92-та съществуващи torrents, създаване/промяна на NAS библиотечни файлове, production deployment или започване на разработката без отделно съгласие.

> **Водещ принцип:** ViMag взема решенията и управлява Import Job; **qBittorrent е авторитетът за физическо преместване/преименуване на файлове от активен torrent**. Резултатът се счита за успешен едва след проверена целостта на данните, валидно torrent mapping/seeding-capability и потвърдена публикация в Jellyfin. Съществуващите torrents не се променят.

## Съдържание

1. [Източници, доказателства и статус](#1-източници-доказателства-и-статус)
2. [Приети ограничения и реално установена инфраструктура](#2-приети-ограничения-и-реално-установена-инфраструктура)
3. [Архитектурни решения](#3-архитектурни-решения)
4. [Компонентен модел и комуникация](#4-компонентен-модел-и-комуникация)
5. [Development → Registry → Production](#5-development--registry--production)
6. [Docker Compose, volumes и security boundaries](#6-docker-compose-volumes-и-security-boundaries)
7. [Staging Pool и ownership на torrents](#7-staging-pool-и-ownership-на-torrents)
8. [qBittorrent Web API integration contract](#8-qbittorrent-web-api-integration-contract)
9. [Седемстъпков Import Job и state machine](#9-седемстъпков-import-job-и-state-machine)
10. [Физически планове: simple/multi-file/mixed torrent](#10-физически-планове-simplemulti-filemixed-torrent)
11. [PostgreSQL schema и транзакционни граници](#11-postgresql-schema-и-транзакционни-граници)
12. [Persistent queue, leases и concurrency](#12-persistent-queue-leases-и-concurrency)
13. [Operation journal, reconciliation и recovery](#13-operation-journal-reconciliation-и-recovery)
14. [Категории, идентификация и naming](#14-категории-идентификация-и-naming)
15. [BG evidence, quality engine и дубликати](#15-bg-evidence-quality-engine-и-дубликати)
16. [Subtitle, sidecar и quarantine lifecycle](#16-subtitle-sidecar-и-quarantine-lifecycle)
17. [Jellyfin publication contract](#17-jellyfin-publication-contract)
18. [Backend API, authentication и UI](#18-backend-api-authentication-и-ui)
19. [Secrets, audit и operational hardening](#19-secrets-audit-и-operational-hardening)
20. [Monitoring, backup и rollback](#20-monitoring-backup-и-rollback)
21. [Тестова стратегия и validation gates](#21-тестова-стратегия-и-validation-gates)
22. [Поетапно внедряване и безопасен cutover](#22-поетапно-внедряване-и-безопасен-cutover)
23. [Repository структура и definition of done](#23-repository-структура-и-definition-of-done)
24. [Отворени реализационни параметри и sign-off](#24-отворени-реализационни-параметри-и-sign-off)
25. [Технически референции](#25-технически-референции)

---

## 1. Източници, доказателства и статус

В този документ има три отделни категории информация:

- **[ACCEPTED]** — политика от одобрения Technical Scope или изрично потвърдено архитектурно решение в последващия разговор.
- **[OBSERVED]** — стойност, получена от представен CLI/Web API диагностичен резултат на ViMag; това не означава, че сме имали пряк административен достъп до машината.
- **[DESIGN]** — конкретно инженерно предложение за новата реализация. Приема се окончателно при одобряване на този Implementation Design.
- **[GATE]** — нещо, което трябва да се докаже с изолиран тест, преди write-capable pilot или production.

**Източник на продуктовите правила:** 22 приети избора от Technical Scope v1.0, включително Bulgarian-first, един локален admin, NFO/artwork ownership, no permanent library delete, 7-step Jobs и 43 acceptance теста **T-01…T-43**. Този документ **не изменя тихомълком** одобрения продуктово-функционален scope. Там, където старият scope предлага SQLite, Redis-free backend или completion hook, настоящият документ формализира последващо договорените технически промени като проектни решения, без да променя защитните инварианти.

**Важни нови договорености [ACCEPTED]:**

1. Всичко в production е контейнеризирано; **source code се разработва на локалния компютър** във VS Code и се съхранява в GitHub.
2. GitHub Actions изгражда и публикува готови images в Docker Hub; **ViMag прави pull, не build**; production updates са контролирани.
3. **Import Staging Pool = `/mnt/storage/qbt/complete`**; анализ/quality/naming/approval предхождат финалното преместване.
4. qBittorrent изпълнява физическото torrent-aware move/rename по нареждане на ViMag. Worker проверява действителния резултат, възстановява seeding и публикува към Jellyfin.
5. **92 съществуващи torrents са изключени от автоматични промени**. Нови torrents се регистрират автоматично като ViMag-managed **само след cutover и само когато са изпълнени всички строги eligibility условия**; не се изисква отделно ръчно потвърждение на всеки обикновен нов torrent.
6. NAS torrent tree + hardlinks се използват за подходящите multi-file/season packs, при доказан безопасен mount/permissions модел.

**Технически предложения за приемане с настоящия документ [DESIGN]:** PostgreSQL вместо първоначално предложената SQLite; четири runtime контейнера и два собствено разработени images; PostgreSQL persistent queue без Redis/RabbitMQ; двуфазен release с ръчно потвърждение; предварително дефинирани ownership/lease/reconciliation контракти. Точните версии и числовите лимити остават фиксирани чрез release manifest и измервания.

## 2. Приети ограничения и реално установена инфраструктура

### 2.1 Snapshot на ViMag — доказан с предоставена диагностика [OBSERVED]

| Компонент | Установено състояние |
|---|---|
| Host | Linux `ViMag` |
| Docker | Compose; работеща мрежа `vimag_default`; Traefik v3.6 по предоставения предходен контекст |
| qBittorrent | `lscr.io/linuxserver/qbittorrent:latest`, контейнер `qbittorrent`, WebUI/API на port `8080` **без published host port** |
| qBittorrent API | qBittorrent **v5.2.0**, Web API **2.15.1**, вътрешен HTTP endpoint достижим и удостоверен през Docker IP |
| Authentication | Съществуващ `admin`; API login върна `204`, cookie бе получена и последващ `GET` върна `200` |
| Download mount | `/mnt/storage/qbt` → `/downloads` (RW) |
| Download directories | `/mnt/storage/qbt/complete`, `/mnt/storage/qbt/incomplete` |
| Local FS | `/dev/sda2`, **NTFS** (`fuseblk`), DATA; **не** е избрано хранилище за PostgreSQL |
| NAS share | `//192.168.10.11/Movies` → `/mnt/nas/Movies` чрез `autofs` + **CIFS/SMB** |
| NAS capacity, към теста | ~22 TB общо, ~6.2 TB използвани, ~16 TB свободни; **не гаранция за бъдещ капацитет** |
| qBt NAS mount | `/mnt/nas/Movies/Library` → `/library` (RW) |
| Default qBt `save_path` | `/downloads/complete` |
| qBt `temp_path` | `/downloads/incomplete` |
| qBt `temp_path_enabled` | **false** — няма глобално активен incomplete temp режим |
| qBt `auto_tmm_enabled` | **true** за нови torrents по подразбиране |
| qBt `use_category_paths_in_manual_mode` | **false** |
| qBt TMM triggers | category-changed, torrent-changed, save-path-changed = **true** |
| Categories | `movies`, `series`, `animations`, `documentaries`, `concerts`; `savePath` са `/library/<Category>` |
| Existing torrents | **92 общо**, **57 Automatic**, **35 Manual**; **всички 92** със save path под `/library` на NAS |
| Existing category distribution | movies 43, series 42, animations 7, documentaries 0, concerts 0 |
| Completion hook | `autorun_enabled=false`; старият `jellyfin-scan.sh` съществува, но не се изпълнява като активен hook |
| API protection | Host Header Validation/CSRF Protection активни; `bypass_local_auth=false` |
| Host NAS hardlinks | `ln`/read/unlink тест: **PASS** |
| Isolated Docker hardlinks | write-through + unlink от един NAS bind mount, UID:GID `1000:1000`: **PASS** |
| NAS inode/link count | CIFS връща несъответстващи inode IDs и `st_nlink=1`; **не** се използват като самостоятелно доказателство за dependency/cleanup |
| Jellyfin | Реален endpoint `https://media.vimag.app` е бил използван от стария скрипт; реалните library types и API integration още не са проверени |

**Корекция на старо предположение:** при `temp_path_enabled=false` директорията `incomplete` не е глобално активна. Във v1 **новите torrents може да записват директно в `/downloads/complete`, докато още се изтеглят**. Това е очаквано; **директорията не доказва завършване**. Worker обработва само след qBt-reported completion + стабилен file inventory. Не променяме глобално Temp Path, за да пресъздадем недоказан `incomplete → complete` workflow.

### 2.2 Непроменяеми инварианти [ACCEPTED]

- **Няма операции** върху 92-та съществуващи torrents от импортния write pipeline (дори когато категорията им съвпада с нова).
- Изборът на една от петте категории е от потребителя; ViMag не сменя top-level категория автоматично.
- `BG_VERIFIED` изисква достоверно evidence, не само `bul`/`bg` stream tag.
- Не променяме video/audio bytes, не remux-ваме, не transcoding-ваме и не изтриваме окончателно библиотечни медии.
- Quarantine само след конкретно одобрение и проверка на dependencies, с Restore; няма permanent delete API във v1.
- Auto-cleanup се допуска **само** за доказано излишен локален/staging source, не за библиотеката, quarantine, sidecars с непознат ownership или qBt entry.
- Никакъв terminal success без verified NAS media integrity + qBt mapping/seeding-capability + Jellyfin item verification; само липсата на нефатални BG subtitles допуска `CompletedWithWarnings`.
- Рисковите операции винаги имат durable journal **преди** външния side effect, idempotency, reconciliation и audit.

## 3. Архитектурни решения

| ID | Решение | Статус | Обосновка / граница |
|---|---|---|---|
| IMPL-01 | Dev във VS Code → GitHub → GitHub Actions → Docker Hub → pull в ViMag | [ACCEPTED] | На ViMag няма source checkout/build; няма unattended production update. |
| IMPL-02 | `web`, `api`, `worker`, `db` като четири runtime контейнера | [DESIGN] | API остава отзивчив при дълги NAS операции; DB не е exposed. |
| IMPL-03 | Два собствени images: `media-manager-web` и `media-manager-backend` (ползван от API и Worker) | [DESIGN] | Еднакви версии на business logic и schema contracts. |
| IMPL-04 | PostgreSQL като безплатна persistent DB, вместо SQLite | [DESIGN] | Контролирана конкуренция, транзакции, audit, JSONB, queue leases, отделни API/Worker; без Redis/RabbitMQ. |
| IMPL-05 | Complete directory = физически staging; PostgreSQL = logical staging/job ledger | [ACCEPTED] | Без второ локално копие на големи torrents. |
| IMPL-06 | New torrents: Manual TMM + `/downloads/complete` + запазена категория | [ACCEPTED / GATE] | Съществуващите category NAS paths остават непроменени; реален add тест е задължителен. |
| IMPL-07 | qBt API е физическият изпълнител на active torrent rename/move | [ACCEPTED / GATE] | `setLocation` не е „информирай qBt за вече преместен файл“; async verification. |
| IMPL-08 | Simple torrents → qBt-managed direct move; multi-file → NAS torrent tree + hardlinks | [ACCEPTED / GATE] | CIFS/Docker host hardlinks са тествани; production worker permissions и qBt relocation остават за тест. |
| IMPL-09 | Jellyfin refresh само след safety checks и sidecar readiness | [ACCEPTED] | Refresh accepted ≠ scan completed ≠ catalog verified. |
| IMPL-10 | Read-only baseline inventory за старите 92 torrents и отделно registry за ViMag-managed torrents | [DESIGN] | Policy guard дори при API bug/queue duplication. |
| IMPL-11 | PostgreSQL queue с `FOR UPDATE SKIP LOCKED`, lease + fencing token | [DESIGN] | Няма безкрайни in-memory jobs; един logical worker в pilot. |
| IMPL-12 | Ръчно контролирано production deployment с immutable image digests | [DESIGN] | Rollback на код и контролирани DB migrations; без `latest`. |
| IMPL-13 | qBt 5.2 API key за machine-to-machine auth (ако е създаден) | [DESIGN / GATE] | Без WebUI password в Worker; **един ключ за инсталацията**, не per-role token; пази се като secret. |

**Правило за конфликт:** при несъвместимост между техническо предложение и approved Technical Scope продуктово изискване надделява. Установен технически blocker не позволява изключение „за да завършим job“; Job спира за review/recovery.

## 4. Компонентен модел и комуникация

```text
Windows/Linux development PC — VS Code
  └── Git push → GitHub (vesovasilev-vimag/media-manager)
                  └── GitHub Actions: lint/test/SBOM → Docker build & sign/attest → Docker Hub
                                                                            │
                                                                            ▼ (manual, version/digest pinned)
ViMag Linux / Docker Compose ────────────────────────────────────────────────┐
 Traefik / VPN / HTTPS                                                      │
    │                                                                        │
    ▼                                                                        │
 [web: Vue 3 static assets via Nginx] ── /api proxy ──► [api: FastAPI]      │
                                           │               │                 │
                                           │               ▼                 │
                                           └────────► [PostgreSQL] ◄── [worker: Python/ffprobe]
                                                                  │
                                              ┌───────────────────┼─────────────────────┐
                                              ▼                   ▼                     ▼
                                      qBittorrent 5.2 API    SMB/CIFS NAS           Jellyfin API
                                         (Docker DNS)       (single worker bind)    (internal URL)
                                              │                   │
                                        /downloads/complete  /nas-movies/
                                              └── qBt move ─────► │
                                                       verify ──► Jellyfin publish
```

| Service | Image | Какво прави | Важни ограничения |
|---|---|---|---|
| `media-manager-web` | `vesovasilev/media-manager-web:<release>` | Компилиран Vue 3 интерфейс, Nginx, same-origin `/api` proxy | Без filesystem mounts, без secrets, без бизнес права. |
| `media-manager-api` | `vesovasilev/media-manager-backend:<release>` | FastAPI, auth, settings, review/approval, web endpoints, job read/query | Няма NAS/download RW mounts; не изпълнява големи файлови операции. |
| `media-manager-worker` | същият backend image | ffprobe/MediaInfo, TMDb, planning, qBt API, NAS/sidecars/hardlinks, Jellyfin verify, recovery | Единственият ViMag компонент с media mounts; без Docker socket; job-guarded commands. |
| `media-manager-db` | official `postgres:<pinned-release>` | PostgreSQL queue, inventories, plans, audit, admin data | Само във вътрешна DB мрежа; локален Linux persistent volume; backup. |

**Не са отделни v1 services:** Redis, RabbitMQ, Elasticsearch, cron sidecar, transcoder, Samba server, Jellyfin instance, qBittorrent instance, external DB admin UI. Съществуващите qBittorrent/Jellyfin/Traefik се използват като външни интеграции.

**Async tasks:** HTTP request връща `202 Accepted` с ID за продължителните операции; UI чете състояние през API polling или Server-Sent Events (SSE) с fallback към polling. Няма задължителен WebSocket/Redis broker.

## 5. Development → Registry → Production

### 5.1 Етапи и отговорности

```text
Developer PC (VS Code)
  ├─ git clone / feature branch
  ├─ local Compose: web + api + worker + PostgreSQL + synthetic fixtures
  ├─ unit/integration tests (no production NAS access)
  └─ git push / pull request
           │
GitHub repository — main
  ├─ PR checks: lint, typecheck, unit, migrations, contract tests, security checks
  ├─ tagged release workflow: vMAJOR.MINOR.PATCH
  └─ GitHub Actions (Buildx) → Docker Hub (two versioned images)
           │
ViMag
  ├─ explicitly selected release manifest + image digests
  ├─ backup + dry-run / prerequisites
  ├─ pull prebuilt images; one-off database migration
  ├─ docker compose up -d; health/readiness verification
  └─ operator sign-off; rollback runbook
```

- **Repository:** GitHub е единственият източник на истина за source code; локалният компютър е development workstation. Production не pull-ва `main` и не клонира сорса.
- **Build:** GitHub Actions изгражда Linux images за архитектурата на ViMag. `uname -m`/`docker info` на ViMag трябва да се проверят преди първи release; не се приема на доверие `linux/amd64`.
- **Versioning:** `v1.0.0`, `v1.0.1` и т.н.; отделни images `web`/`backend` с еднакъв release ID, Git SHA, SBOM и digest. `latest` не е production selector.
- **Publication:** pull request → tests; tag/release → build/push с Docker Hub token от GitHub Actions secrets; името `vesovasilev` се потвърждава като действителен registry namespace при конфигуриране.
- **Deploy:** ръчен approval, промяна само на image references в release manifest, `docker compose pull`, еднократни миграции, `docker compose up -d`, health и smoke tests. При проблем — спиране и документиран rollback, не автоматична поредица от рестарти на рисков Worker.
- **Reproducibility:** изпълнимите версии на Python/Node/base images се pin-ват, dependency lockfiles са задължителни, а production deploy ползва image **digest**. В release metadata се пазят SHA, датата, миграционната ревизия и compatibility range.

### 5.2 Secrets и конфигурация по среда

| Тип | GitHub repo | GitHub Actions | ViMag |
|---|---|---|---|
| Source/settings templates | Да (`.env.example`) | Build context | Release artifact |
| Docker Hub credentials | Не | Scoped Actions secret | Read-only registry credentials само ако images са private |
| PostgreSQL password | Не | Никога в build | Compose secret file |
| qBt API key | Не | Никога в build | Worker-only secret file |
| Jellyfin API token | Не | Никога в build | Worker-only secret file |
| TMDb/subtitle keys | Не | Няма нужда за build | Worker-only secret files |
| `.env` с реални стойности | Не | Не | Локално, права 0600 |

**Security action:** старият `jellyfin-scan.sh` съдържа действително изглеждащ token, който е бил споделен в разговора. Преди production нов Jellyfin API token трябва да бъде генериран, а старият — ревокиран. Нито старият token, нито secret конфигурации се добавят в repository или в този документ.

## 6. Docker Compose, volumes и security boundaries

### 6.1 Runtime storage

```text
/home/veso/docker/media-manager/      # хост configuration tree, НЕ source checkout
├── compose.yaml                     # версиониран deployment artifact
├── .env                             # НЕ в GitHub
├── secrets/                         # 0700, файлове 0600
├── config/                          # nonsecret runtime settings
├── data/postgres/                   # локален Linux filesystem; gate G-DB-01
├── backups/                         # локален резервен файл + външно копие
└── logs/                            # файлове или Docker logging driver

/mnt/storage/qbt/
├── complete/                        # physical import staging; NTFS
└── incomplete/                      # съществува, но temp_path_enabled=false

/mnt/nas/Movies/                     # ЕДИН worker bind mount
├── .vimag-torrent-store/            # само след migration gate; не се сканира от Jellyfin
└── Library/
    ├── Movies/
    ├── Series/
    ├── Animations/{Movies,Series}/
    ├── Documentaries/{Movies,Series}/
    └── Concerts/
```

**PostgreSQL disk placement:** `/mnt/storage` е NTFS/fuseblk; PostgreSQL data directory трябва да е на **проверена, локална Linux файлова система** с подходящи `fsync`, ownership и atomic semantics (обикновено ext4 или XFS). Пътят под `/home/veso/docker/media-manager/data/postgres` е **кандидат**, а не доказателство за тип FS. Проверка `findmnt -T` на хоста и тест за персистентност са блокиращи. Нито PGDATA, нито queue/audit се поставят на CIFS или NTFS FUSE mount.

### 6.2 Mount matrix

| Контейнер | Host → Container | Права | Защо |
|---|---|---|---|
| `web` | няма media binds | — | Само статични assets/HTTP proxy |
| `api` | няма media binds | — | Само DB и admin endpoints |
| `worker` | `/mnt/storage/qbt` → `/downloads` | RW, allowlisted subpaths в приложението | ffprobe + безопасни staging операции; без модифициране на активните torrent bytes |
| `worker` | `/mnt/nas/Movies` → `/nas-movies` | RW, вътрешен allowlist | Един CIFS bind за hardlinks и sidecars; само във валидни roots |
| `db` | local Linux host `data/postgres` → PGDATA | RW, само Postgres UID | Persistent DB |
| **съществуващ qBt** | `/mnt/storage/qbt` → `/downloads` | съществуващ RW | Без промяна в този mount |
| **съществуващ qBt** | `/mnt/nas/Movies/Library` → `/library` | съществуващ RW | 92 текущи torrents остават на същите пътища |
| **бъдещ qBt** | `/mnt/nas/Movies/.vimag-torrent-store` → `/torrent-store` | RW, след проверка | qBt-managed move за multi-file torrents; Docker config промяна едва при pilot |

**Важно за hardlinks:** Worker работи през **един** `/nas-movies` bind и прави `os.link('/nas-movies/.vimag-torrent-store/...', '/nas-movies/Library/...')`; не прави hardlink между самостоятелни Docker mount points. Не се разчита на CIFS inode номера/link counts за доказване на shared dependencies. Тестът с UID:GID `1000:1000` е успешен; реалният Worker UID/GID/ACL се валидира отделно.

### 6.3 Compose skeleton — **illustrative**, не deployable configuration

Следващият YAML показва **service layout и зависимости**, не е готов за изпълнение: образите все още не съществуват, секрети/мрежи/labels и реалните PGDATA paths не са конфигурирани, а root директориите не са създадени. Точните production image digests ще дойдат от release manifest.

```yaml
# illustrative compose.yaml; DO NOT DEPLOY AS IS
services:
  web:
    image: vesovasilev/media-manager-web:<RELEASE_DIGEST>
    networks: [vimag, backend]
    depends_on:
      api: {condition: service_healthy}
    read_only: true
    # Traefik labels/hostname only after network + DNS review.

  api:
    image: vesovasilev/media-manager-backend:<RELEASE_DIGEST>
    command: ["python", "-m", "app.api"]
    networks: [vimag, backend]
    secrets: [db_password]
    depends_on:
      db: {condition: service_healthy}
    # No NAS/download mounts, no host port publication.

  worker:
    image: vesovasilev/media-manager-backend:<RELEASE_DIGEST>
    command: ["python", "-m", "app.worker"]
    networks: [vimag, backend]
    secrets: [db_password, qbt_api_key, jellyfin_api_key]
    depends_on:
      db: {condition: service_healthy}
    volumes:
      - type: bind
        source: /mnt/storage/qbt
        target: /downloads
        bind: {create_host_path: false}
      - type: bind
        source: /mnt/nas/Movies
        target: /nas-movies
        bind: {create_host_path: false}
    # No docker.sock; network and uid must be verified.

  db:
    image: postgres:<PINNED_VERSION_AND_DIGEST>
    networks: [backend]
    secrets: [db_password]
    # POSTGRES_PASSWORD_FILE points to /run/secrets/db_password.
    # Use a verified Linux-filesystem data mount and correct PGDATA for chosen major.

networks:
  vimag:
    external: true
    name: vimag_default
  backend:
    internal: true

secrets:
  db_password: {file: ./secrets/db_password}
  qbt_api_key: {file: ./secrets/qbt_api_key}
  jellyfin_api_key: {file: ./secrets/jellyfin_api_key}
```

**Не се изпълнява с `docker compose up`**, преди да бъде заменено с завършен audited deployment template. В реалния Compose се добавят `healthcheck`, `restart`, ресурси, `read_only`, `tmpfs`, `user`, `cap_drop`, правилната PGDATA, Nginx/API reverse-proxy правила, Traefik labels, защита от Docker auto-created source paths и секрети според точния runtime. Образите се задават по digest със синтаксис `image: repo@sha256:...`, а не буквалния placeholder `<RELEASE_DIGEST>`.

### 6.4 Network contract

- Външна мрежа `vimag_default`: `web`/`api`/`worker`, Traefik, съществуващ qBt и необходимите service endpoints.
- Вътрешна `backend`: `api`/`worker`/`db`. PostgreSQL **няма** `ports:` към хоста; само през DB network.
- Traefik маршрутизира само UI host `manager.vimag.app` (кандидат, DNS за потвърждение) към `web` с HTTPS/Tailscale perimeter. Nginx reverse-proxy към `api` под **same-origin `/api`**; без публична qBt WebUI/API експозиция.
- Worker говори с qBt през Docker DNS (кандидат `http://qbittorrent:8080`, доказването на Host Header Validation остава gate), с Jellyfin през валиден internal route и с TMDb/subtitle providers при необходимост.
- Не изключваме Host Header Validation/CSRF Protection на qBt за удобство. При нужда конфигурираме **конкретно разрешен host** и го тестваме, без `bypass_local_auth`.

## 7. Staging Pool и ownership на torrents

### 7.1 Какво е staging

**Физически слой:** `/downloads/complete` (host `/mnt/storage/qbt/complete`), **без дублиране на torrent payload**.  
**Логически слой:** PostgreSQL `import_jobs`, `import_plans`, `job_tasks`, evidence, approvals и operation journal.

**Текущо `temp_path_enabled=false`:** нови torrents със `savepath=/downloads/complete` могат да записват **частични файлове** в тази папка. Не се използва файлово наличие, файлово име или директория като completion proof. Първо се проверява qBt `progress`/torrent state, липса на `moving`/`checking`, file inventory и стабилни данни. `ffprobe` преди завършване е само безвреден preview, не import approval.

### 7.2 Ownership registry — защита на 92-та стари torrents

Преди cutover се прави **read-only baseline snapshot** на текущите torrents от API (hash, category, `auto_tmm`, save_path, added/completed timestamps ако са налични, и redacted signatures в audit). В DB се записва:

- `management_scope=LEGACY_READ_ONLY` за първоначално установените **92** torrents;
- `management_scope=VIMAG_MANAGED` за **доказано нов** torrent след cutover, който удовлетворява автоматичното eligibility правило (извън baseline, нов instance, category от allowlist, Manual TMM, точно `/downloads/complete`, без qBt path drift), или след изричен operator onboarding на отделен нов torrent;
- `management_scope=EXTERNAL_UNMANAGED` за други неизяснени torrents; никакви write операции;
- `management_scope=TEST_FIXTURE` за изолирани тестове, които никога не използват production library.

**Сигурност:** списъкът с hashes се пази вътрешно в DB, но не се изнася в публичен GitHub, диагностични logs или Web UI без нужда. Повторно добавен torrent със същия hash се различава чрез локално `torrent_instance_id`/поколение; никога не се приема автоматично за стария managed entry. Не е достатъчна само дата на добавяне.

**Write guards (проверяват се server-side на всеки POST):**

```text
assert job.management_scope == VIMAG_MANAGED
assert torrent_instance_matches_snapshot(job.torrent_instance_id, qbt_current)
assert no_external_category_or_path_drift
assert plan_revision_and_fingerprint_current
assert verified_allowed_source_and_destination_roots
assert valid_operation_lease_and_fencing_token
```

Изключение: безопасни read-only inventory/quality справки може да анализират старите 92 torrents. **Това не е разрешение за rename, move, stop, start, recheck или cleanup на тях.**

### 7.3 Приемане на нов torrent — фази

1. **Pilot:** само контролирано добавяне на нов тестов torrent чрез qBt API с `autoTMM=false`, `savepath=/downloads/complete` и избрана една от петте категории; след add се чете обратно действителното `auto_tmm/save_path/category`. Съществуващите category paths **не се редактират**.
2. **Verification:** доказва се, че този нов torrent **не** е автоматично преместен на NAS и че qBt completion е отделно наблюдаемо събитие.
3. **Cutover:** едва след успешен pilot се преценява смяна на **default за бъдещи torrents** (`auto_tmm_enabled=false`) така, че ръчно добавени torrents през VueTorrent да остават локално. Това е **планирана глобална настройка за бъдещо добавяне**, не операция за превключване на mode на 92-та съществуващи; прави се само след before/after snapshot и доказателство, че не провокира relocation. След cutover Worker **автоматично onboard-ва** само новите torrents, които отговарят едновременно на следните условия: липса от legacy baseline, валидно ново torrent instance/generation, разрешена категория, `auto_tmm=false`, `save_path=/downloads/complete`, qBt completion доказано, никакъв външен file/category/path drift и валидно enabled production policy. Несъвместимите torrents остават за review, а не се придърпват обратно от NAS.
4. **Manual-add exceptions:** ако външен клиент добави нов torrent с Automatic TMM или NAS save path, ViMag го класифицира като `EXTERNAL_UNMANAGED/NeedsReview`. Не го премества обратно към локалния диск автоматично.
5. **No qBt category remapping:** петте категории запазват съществуващите `/library/...` save paths, защото промяната може да задвижи 57-те стари Automatic TMM torrents.

### 7.4 Как разбираме, че е завършен

- Основно: read-only polling на `/api/v2/torrents/info` или `/api/v2/sync/maindata`, с incremental reconciliation; ориентировъчен интервал 15–30 секунди **[DESIGN; измерва се]**.
- Входът за Job е **durable discovery**, не edge-only event. Повторен trigger или рестарт на Worker не създава втори физически move.
- Провери `progress=1.0` (с допустим точен API representation), актуалния state, `amount_left`/piece completion и че torrent не е в moving/checking/error състояние; извлечи file list `/torrents/files` и snapshots.
- `paused` или `stalled` не доказват incomplete, а upload speed 0 не доказва проблем. При външно изменена категория, save path или file tree → `ReplanRequired`.
- Existing `autorun_enabled=false`; старият `jellyfin-scan.sh` не се активира като паралелен completion hook. За v1 се използва polling с periodic full reconcile; евентуален webhook е бъдеща оптимизация, не source of truth.

## 8. qBittorrent Web API integration contract

### 8.1 Transport и authentication

| Поле | Дизайн |
|---|---|
| qBt версия | **Observed:** v5.2.0 |
| Web API версия | **Observed:** 2.15.1 |
| Вътрешен host | Docker DNS `qbittorrent:8080`, **GATE** за точния Host header/resolve; не `172.18.0.5` като постоянна стойност |
| Authentication | **Предпочитано:** qBt 5.2 API key (`Authorization: Bearer ...`) през Worker secret; key generation/rotation е отделна контролирана операция |
| Fallback | Existing `admin` WebUI session с cookie jar; qBt 5.2 допуска login `HTTP 204`; session cookie името не се hardcode-ва |
| Secrets | Няма credentials в URL, source, image, logs или DB audit payloads |
| HTTP requests | Timeouts, backoff, `Origin`/`Referer` при cookie login според qBt защити; `POST` за state changes, не GET |
| Forbidden / 401 | Не retry-вай с различни пароли; `BlockedExternalDependency/AuthRequired`, operator action |

**qBt 5.2 API key ограничение:** инсталацията поддържа един machine API key, който **не е per-role token**. Ако се използва, трябва да се пази строго само в Worker, а application authorization да остане изцяло в ViMag. Създаването на ключ ще бъде изрично извършено при integration setup, без да отслабваме WebUI защитите.

### 8.2 Endpoint matrix — документ за разработчика, не резултат от write тест

| Цел | Метод / Endpoint | Payload / наблюдение | Правило |
|---|---|---|---|
| Health/version | `GET /api/v2/app/version`, `GET /api/v2/app/webapiVersion` | Очаквани v5.2.0/2.15.1 | Проверено read-only |
| Preferences | `GET /api/v2/app/preferences` | `auto_tmm_enabled`, `use_category_paths_in_manual_mode`, save/temp paths | Проверено read-only |
| Categories | `GET /api/v2/torrents/categories` | category `savePath` | Проверено read-only |
| Current torrents | `GET /api/v2/torrents/info` | hash, state, progress, save_path, category, `auto_tmm` | Проверено read-only |
| Torrent files | `GET /api/v2/torrents/files` | `hash`, per-file path/index/priority | При pilot да се провери exact schema |
| Detailed torrent | `GET /api/v2/torrents/properties` | `hash`, seeding/ratio/connection/pause evidence | Pilot validation |
| Incremental polling | `GET /api/v2/sync/maindata` | `rid` snapshot/delta; fallback full reconcile | Pilot validation |
| Controlled new add | `POST /api/v2/torrents/add` | `savepath=/downloads/complete`, `category=...`, `autoTMM=false` | **Само нов TEST_FIXTURE**, след explicit authorization |
| Stop for transfer | `POST /api/v2/torrents/stop` (5.x) | `hashes=<one_hash>` | Само managed torrent, only when required; пази state |
| Start after transfer | `POST /api/v2/torrents/start` (5.x) | `hashes=<one_hash>` | Само ако original torrent/user policy го допуска |
| Rename torrent file | `POST /api/v2/torrents/renameFile` | `hash`, `oldPath`, `newPath` | Само active plan; следи actual file list |
| Rename torrent folder | `POST /api/v2/torrents/renameFolder` | `hash`, `oldPath`, `newPath` | Само active plan; collision protection |
| Move torrent tree | `POST /api/v2/torrents/setLocation` | `hashes=<one_hash>`, `location=<container_path>` | qBt управлява физическия move; следи `moving`, paths, files |
| Integrity | `POST /api/v2/torrents/recheck` | `hashes=<one_hash>` | Поддържа се, но ефектите върху state се тестват |
| Automatic management | `POST /api/v2/torrents/setAutoManagement` | Само за нов, изрично owned torrent | Преди pilot се сверява точният endpoint/semantics |
| Preferences mutation | `POST /api/v2/app/setPreferences` | Само controlled cutover с backup | **Не** се извиква от нормален Import Job |

**Забранено за v1:** `hashes=all` при write операции, `torrents/delete`, `deleteFiles=true`, неразрешени `setCategory`, автоматично `editCategory`, глобален `setPreferences` от job worker, принудителен resume на умишлено paused/ratio-limited torrent.

**Не приемаме HTTP 200 за крайно потвърждение.** API методът може да е приел команда, докато filesystem операцията е все още в процес. Последваща read-after-write верификация на exact `save_path`, file paths, move state, recheck и qBt policy е задължителна. Реалните 5.2.0 write endpoint/return semantics се доказват само с test fixture.

### 8.3 Path normalization между Worker и qBt

| Host path | Worker path | qBt path |
|---|---|---|
| `/mnt/storage/qbt/complete` | `/downloads/complete` | `/downloads/complete` |
| `/mnt/nas/Movies/Library` | `/nas-movies/Library` | `/library` |
| `/mnt/nas/Movies/.vimag-torrent-store` | `/nas-movies/.vimag-torrent-store` | `/torrent-store` **след бъдещ qBt mount** |

DB съхранява **логически storage root + relative path + mount mapping revision**, не един произволен Docker absolute path като универсална истина. Mapping функцията връща container path по конкретната външна система. Преди write проверяваме containment (root allowlist, no traversal, no symlink escape), наличен NAS mount и че qBt вижда дестинацията.

**CIFS/autofs особеност:** `exists('/nas-movies/Library')` не е достатъчен NAS health check. Валидираме реалния CIFS mount identity, writable target/root, service ACL, свободно място и readback на тестов self-owned scratch file в предвидена зона (при write-capable gate), без да допускаме `autofs` fallback към празна локална директория.

## 9. Седемстъпков Import Job и state machine

### 9.1 User-facing стъпки [ACCEPTED]

| Стъпка | Worker operations | Exit gate |
|---|---|---|
| **01 Download completed** | Poll/reconcile qBt; ownership; dedup event; initial snapshot | Durable Parent Job + file inventory |
| **02 Identify & inspect** | ffprobe, streams, release parsing, TMDb candidates, `BG_*` evidence | High-confidence match или `NeedsReview` |
| **03 Compare with library** | Editions, quality factors, BG-first, existing versions and dependencies | Keep/keep-both/review decision и plan revision |
| **04 Organize & enrich** | Preflight, approved plan, qBt rename/move, verify, **early restore of seeding**, hardlinks, NFO/artwork | NAS/torrent checks successful |
| **05 Find BG subtitles** | Existing → embedded → trusted provider → timing/sync review | Verified subtitles или explicit `Unavailable` |
| **06 Publish to Jellyfin** | Trigger refresh + poll/Jellyfin ID and streams verification | `PublishedVerified` |
| **07 Verify qBittorrent seeding** | Final qBt state/mapping/pieces/policy and cleanup eligibility | `Completed` / `CompletedWithWarnings` |

Step 04 **вече** трябва да върне torrent в сеедваемо състояние. Step 07 е независимо финално потвърждение, а не моментът на първото resume.

### 9.2 Вътрешни operational states [DESIGN]

```text
Discovered → Queued → Inspecting → Comparing → PlanReady
                                      ├─ NeedsReview / AwaitingApproval ─┐
                                      └──────────────────────────────────┤
                                                                         ▼
Preflight → Prepared → RenameRequested → RenameVerified → MoveRequested
  → MovingObserved → DestinationPresent → IntegrityVerified
  → TorrentMappingVerified → TorrentRechecked → SeedingCapable
  → HardlinksVerified? → Enriching → SubtitleReview/Unavailable/Verified
  → RefreshRequested → PublishPending → PublishedVerified
  → FinalSeedingCheck → Completed | CompletedWithWarnings
```

Orthogonal/control states: `Paused`, `BlockedExternalDependency`, `ReplanRequired`, `FailedRecoverable`, `RecoveryRequired`, `CancelledBeforeMove`, `StrategyUnavailable`, `Reconciling`.

**Състояние на Job ≠ състояние на конкретна file operation.** Всяка рискова операция има собствен execution record и отделни `requested/observed/verified` маркери.

### 9.3 Терминални резултати [ACCEPTED]

| State | Terminal | Допустимо само при |
|---|---|---|
| `Completed` | Да | Verified NAS bytes + qBt mapping/recheck/seeding-capability + Jellyfin entry; без невършени критични Child checks и предупреждения |
| `CompletedWithWarnings` | Да | Същите критични проверки, но безопасно пропуснати/неналични BG subtitles или друго изрично noncritical deviation |
| `PublishPending` | Не | Refresh е приет, но Jellyfin item/list/library verification не е потвърдена |
| `RecoveryRequired` | Не | Unknown move state, failed pieces, dangerous divergence, missing NAS files или риск от data loss |
| `NeedsReview` | Не | Неясна identity/quality/category/collision/edition/subtitle; не продължава опасно |
| `ReplanRequired` | Не | Променен qBt state/file list/category, source/destination или policy revision |

### 9.4 Parent/Child структура

- Един Parent Job = един torrent instance (hash плюс lifecycle generation), с множество `media_items`.
- Child Media Item има отделен identity, edition, filename plan, subtitle и Jellyfin verification; **физическият torrent-level move е само един**.
- Mixed independent movies/seasons са Child Items; cross-category mismatch не се прехвърля автоматично в различна top-level категория.
- Parent terminal success е позволен само когато всяко критично Child е verified. `CompletedWithWarnings` се агрегира, ако warning-ите са само нефатални.

## 10. Физически планове: simple/multi-file/mixed torrent

### 10.1 Strategy A — прост torrent [ACCEPTED / GATE]

**Предпоставки:** ViMag-managed torrent, един медиен video asset или доказано съвместим file tree, валидна категория, без конфликт с вече съществуващата версия, тестово доказан rename+move механизъм.

1. Snapshot на qBt `hash`, original relative files, `save_path`, category, `auto_tmm`, user pause/queue/force-start/ratio policy и active dependencies.
2. Canonical destination plan, например qBt `/library/Movies/The Matrix (1999) [tmdbid-603]/` (точната семантика на `setLocation` — parent directory vs content root — се валидира по fixture).
3. Lock parent torrent + destination; write-ahead journal; проверка за достъпен NAS, пространство, collisions и план revision.
4. Torrent-aware rename `renameFile`/`renameFolder` чрез qBt, само ако е необходим, и **readback** на file list (не `mv` извън qBt).
5. qBt `setLocation` за уникалния hash; poll moving state и физически проверявай destination. Local NTFS → CIFS е **cross-filesystem transfer** и може да е дълъг, не атомарен.
6. Verify size/fingerprint, qBt file paths и actual location; при необходимост завърши `recheck`; възстанови оригиналната seeding/paused политика при валидно content mapping.
7. Добави **отделни** verified sidecars, subtitle artifacts и публикувай към Jellyfin; final seeding confirmation.

**Безопасно прекъсване:** при crash/timeout без доказан final state НЕ изпращаме повторно `setLocation`/rename на сляпо; reconcile source+destination+qBt state и маркирай `RecoveryRequired`, ако доказателствата са противоречиви.

### 10.2 Strategy B — multi-file/season pack [ACCEPTED / host+Docker hardlinks tested]

```text
qBt local staging:
  /downloads/complete/<torrent-owned-tree>/*

qBt-managed move AFTER approval:
  /torrent-store/<torrent-instance-id>/<original torrent tree>/*
  (host: /mnt/nas/Movies/.vimag-torrent-store/...)

Worker single NAS bind:
  /nas-movies/.vimag-torrent-store/.../original-file.mkv
          │ os.link, without payload mutation
          ▼
  /nas-movies/Library/Series/Show (Year)/Season 01/Show S01E01 - 1080p.mkv
```

1. Съхрани оригиналната multi-file torrent структура в NAS store така, че qBt да вижда и seed-ва **същите относителни файлове/bytes**.
2. qBt управлява move към `/torrent-store/...`; Worker използва един `/nas-movies` bind за `os.link` към Jellyfin-facing имената.
3. За всеки hardlink проверявай content alias на scratch/proof без да променяш реалните video bytes. **Не използвай `st_ino`/`st_nlink` от CIFS като самостоятелен validator.**
4. Не допусни Jellyfin library да сканира hidden torrent store. На Jellyfin се предоставят само правилно именуваните Library paths.
5. Никога не модифицирай или „оптимизирай“ video bytes през hardlink; NFO/artwork/subtitles са **отделни файлове**. При недостъпни links/ACL → `StrategyUnavailable/NeedsReview`, **без автоматично второ голямо копие**.
6. При повторно изпълнение Worker различава вече създаден от него hardlink от collision/непознат файл чрез durable manifest + readback evidence; без неконтролирано overwrite.

**Ключов gate:** успешният изолиран Docker тест е бил с UID:GID 1000:1000 и scratch-only mount. Нужен е финален тест с реалния Worker service UID, qBt `/torrent-store` mount и конкретните permission semantics; **не създаваме директорията или не променяме qBt Compose преди отделен approval за pilot**.

### 10.3 Strategy C — mixed independent items

- Parent torrent е една physical move/seeding единица.
- Child Items се публикуват по различни subpaths **само ако са в рамките на одобрената top-level категория** и има тестово доказан file-to-item mapping; hardlinks са подходящи, когато destination subpaths се различават.
- Не местим директно отделен файл от qBt tree, ако това нарушава torrent mapping.
- Двусмислена категория, липсващи епизоди, nested data files, collision или cross-root conflict → `NeedsReview`/explicit unsupported plan.

### 10.4 Data integrity, seeding и cleanup

- `ffprobe` е metadata inspection, не целост на всички bytes. За torrent използваме qBt piece verification/recheck и независими file/size/hash доказателства където е необходимо.
- `SeedingCapable`: валиден qBt mapping и проверено content integrity, **не** задължително текущо upload към peer. Preserve user-chosen pause/queue/ratio/force state; автоматично resume само когато политиката го допуска.
- Ако qBt сам е преместил source към NAS, **не** правим второ `rm` на стария root „за всеки случай“. AD-16 cleanup се разрешава само за отделно доказан orphan staging artifact, след journal + dependency/ownership checks.
- Permanent library deletion е невъзможна операция във v1.0 — **няма endpoint, няма Worker command, няма scheduled purge**.

## 11. PostgreSQL schema и транзакционни граници

### 11.1 Защо PostgreSQL [DESIGN]

**Избор:** един безплатен PostgreSQL container, с фиксирана major/minor версия и persistent data volume върху локална Linux файлова система. Изборът позволява транзакционни job-ове, `JSONB` за доказателства, валидирани външни ключове, audit и queue с `SKIP LOCKED`. Без Redis/RabbitMQ при един Worker и ограничен брой media jobs.

**Важно:** PostgreSQL транзакция **не може атомарно** да commit-не NAS `os.link`, qBt `setLocation` и Jellyfin refresh. Използваме persisted **saga/operation journal** и reconcile, а не обещание за distributed ACID.

### 11.2 Логически модел и ownership на данните

| Таблица | Минимални колони / ключове | Отговорност |
|---|---|---|
| `app_users` | `id`, `username`, `password_hash`, `created_at`, `disabled_at` | Един локален admin; без default password |
| `admin_sessions` | `id`, `user_id`, `token_hash`, `csrf_hash`, `expires_at`, `revoked_at` | Защитени persistent sessions |
| `qbt_clients` | `id`, `logical_name`, `api_version`, `mount_map_revision`, `config_revision` | Не-secret qBt интеграционни metadata |
| `torrent_instances` | `id`, `client_id`, `info_hash`, `generation`, `management_scope`, `added_at`, `first_seen_at` | **Legacy vs managed guard**, remove/re-add защита |
| `torrent_snapshots` | `id`, `torrent_instance_id`, `collected_at`, `snapshot_hash`, `settings_json` | Предишна категория/save path/file inventory/състояние за recovery |
| `import_jobs` | `id`, `torrent_instance_id`, `kind`, `state`, `step`, `plan_revision`, `policy_revision`, `updated_at` | Parent import lifecycle |
| `job_media_items` | `id`, `job_id`, `identity_id`, `episode_key`, `edition_key`, `state` | Child works/episodes, independent publish/subtitle state |
| `media_inspections` | `id`, `asset_id`, `file_fingerprint`, `ffprobe_json`, `stream_digest`, `checked_at` | Технически evidence, без претенция за full integrity |
| `identity_candidates` | `id`, `media_item_id`, `provider`, `provider_id`, `confidence`, `reasons_json` | Explainable match и manual review |
| `library_assets` | `id`, `identity_key`, `edition_key`, `quality_variant`, `logical_root`, `relative_path`, `storage_status` | Library inventory и multiple versions |
| `media_file_refs` | `id`, `asset_id`, `torrent_instance_id`, `relative_path`, `link_proof_ref`, `status` | Logical dependency map между файлове/torrents |
| `bg_audio_evidence` | `id`, `asset_id`, `stream_key`, `evidence_state`, `source`, `actor_id`, `fingerprint`, `verified_at` | `BG_VERIFIED` provenance, revoke/review |
| `quality_decisions` | `id`, `job_item_id`, `policy_revision`, `decision`, `reason_codes`, `evidence_json` | BG-first/Keep Both/NeedsReview |
| `import_plans` | `id`, `job_id`, `revision`, `plan_sha256`, `plan_json`, `state`, `created_at` | Immutable per-revision destination/cutover plan |
| `approvals` | `id`, `plan_id`, `plan_sha256`, `actor_id`, `action`, `approved_at`, `revoked_at` | Approval само за конкретния plan fingerprint |
| `job_tasks` | `id`, `job_id`, `kind`, `state`, `priority`, `run_after`, `attempts`, `lease_epoch`, `lease_until` | Durable PostgreSQL queue |
| `resource_leases` | `resource_key`, `owner_task_id`, `lease_epoch`, `lease_until` | per-torrent/per-destination serialization |
| `file_operations` | `id`, `job_id`, `plan_id`, `operation_type`, `status`, `intent_json`, `observed_json`, `verified_at` | Write-ahead journal: qBt/FS side effects |
| `sidecar_manifests` | `id`, `asset_id`, `relative_path`, `owner`, `last_written_sha256`, `policy_revision` | Само ViMag-owned unchanged NFO/artwork могат да се update-ват |
| `subtitle_candidates` | `id`, `media_item_id`, `provider`, `language`, `edition_key`, `status`, `timing_evidence` | Match/sync/review status |
| `jellyfin_verifications` | `id`, `media_item_id`, `request_at`, `jellyfin_item_id`, `library_id`, `verified_at`, `state` | Refresh request ≠ verified catalog |
| `quarantine_manifests` | `id`, `asset_id`, `original_path`, `quarantine_path`, `approved_plan_sha256`, `restore_json` | Обратим quarantine + Restore |
| `audit_events` | `id`, `job_id`, `actor_kind`, `actor_id`, `event_type`, `payload_redacted`, `occurred_at` | Append-only наблюдаемост без секрети |
| `service_settings` | `key`, `value_json`, `revision`, `updated_by`, `updated_at` | Нечувствителни конфигурации; секретите са само refs |
| `schema_migrations` | Alembic revision | Migration history/compatibility |

**Нормализация:** `torrent_instances` (физически torrent lifecycle) ≠ `import_jobs` (logical attempt) ≠ `job_media_items` (individual media identity) ≠ `library_assets` (canonical media version) ≠ `media_file_refs` (file path and seeding dependency). Не използваме само info hash като универсален immutable ID за всяко бъдещо добавяне/повторно добавяне.

### 11.3 Примерен SQL за основния lifecycle (ориентир)

Примерът демонстрира типове и ограничения, **не** е окончателната Alembic migration. Вътрешният код генерира UUIDs; думите `state`/`kind` се ограничават чрез валидирани enums и DB checks в първите миграции.

```sql
CREATE TABLE torrent_instances (
  id               uuid PRIMARY KEY,
  client_id        uuid NOT NULL,
  info_hash        text NOT NULL,
  generation       integer NOT NULL CHECK (generation > 0),
  management_scope text NOT NULL CHECK (
    management_scope IN ('LEGACY_READ_ONLY', 'VIMAG_MANAGED',
                         'EXTERNAL_UNMANAGED', 'TEST_FIXTURE')),
  first_seen_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (client_id, info_hash, generation)
);

CREATE TABLE import_jobs (
  id                   uuid PRIMARY KEY,
  torrent_instance_id  uuid NOT NULL REFERENCES torrent_instances(id),
  kind                 text NOT NULL,
  state                text NOT NULL,
  current_step         smallint NOT NULL CHECK (current_step BETWEEN 1 AND 7),
  plan_revision        integer NOT NULL DEFAULT 0,
  policy_revision      integer NOT NULL DEFAULT 1,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (torrent_instance_id, kind)
);

CREATE TABLE import_plans (
  id           uuid PRIMARY KEY,
  job_id       uuid NOT NULL REFERENCES import_jobs(id),
  revision     integer NOT NULL CHECK (revision > 0),
  plan_sha256  text NOT NULL,
  plan_json    jsonb NOT NULL,
  state        text NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (job_id, revision),
  UNIQUE (job_id, plan_sha256)
);

CREATE TABLE job_tasks (
  id           uuid PRIMARY KEY,
  job_id       uuid NOT NULL REFERENCES import_jobs(id),
  task_kind    text NOT NULL,
  state        text NOT NULL,
  priority     integer NOT NULL DEFAULT 100,
  run_after    timestamptz NOT NULL DEFAULT now(),
  attempts     integer NOT NULL DEFAULT 0,
  lease_owner  text,
  lease_epoch  bigint NOT NULL DEFAULT 0,
  lease_until  timestamptz,
  last_error   text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_job_tasks_ready ON job_tasks (run_after, priority, created_at)
  WHERE state IN ('QUEUED', 'RETRYABLE');

CREATE TABLE file_operations (
  id             uuid PRIMARY KEY,
  job_id         uuid NOT NULL REFERENCES import_jobs(id),
  plan_id        uuid NOT NULL REFERENCES import_plans(id),
  op_key         text NOT NULL UNIQUE,
  operation_type text NOT NULL,
  status         text NOT NULL,
  intent_json    jsonb NOT NULL,
  observed_json  jsonb,
  requested_at   timestamptz NOT NULL DEFAULT now(),
  verified_at    timestamptz
);
```

**Migration rule:** SQL schema е строго версионирана; `migration job` се изпълнява **еднократно** преди стартиране на новите API и Worker; две инстанции не опитват миграции паралелно. Backup и schema compatibility check предхождат migration. Non-backward-compatible migration не се комбинира с произволен rollback на стар image.

### 11.4 Индекси и консистентност

- Уникален **active import** по `torrent_instance_id + job_kind`; duplicate completion event обновява последния известен state/queue, не създава втори move.
- `job_media_items` има стабилен `item_key` за сериен номер, edition и content identity; предотвратява дублиране при restart.
- `import_plans` са immutable по revision; редакция създава **нова** revision/sha и анулира зависимите approvals.
- `file_operations.op_key` е детерминистичен идемпотентен ключ `(job, plan_revision, operation_kind, target_key)`; не се преизползва за друга filesystem операция.
- `audit_events` са append-only на application level; в backup се запазват заедно с plans/operations.
- Не пазим WebUI password, qBt API key, Jellyfin token, tracker passkeys, full announce URLs, HTTP authorization headers или секрети в JSONB, audit и exception traces.

## 12. Persistent queue, leases и concurrency

### 12.1 Queue claiming [DESIGN]

PostgreSQL гарантира атомарно claim-ване на task от множество workers чрез `FOR UPDATE SKIP LOCKED`. Логическият Worker е **един** във v1 pilot, но моделът е подготвен за безопасно мащабиране.

```sql
WITH candidate AS (
  SELECT id
  FROM job_tasks
  WHERE state IN ('QUEUED', 'RETRYABLE')
    AND run_after <= now()
  ORDER BY priority ASC, run_after ASC, created_at ASC
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
UPDATE job_tasks AS t
SET state = 'RUNNING',
    lease_owner = :worker_id,
    lease_epoch = t.lease_epoch + 1,
    lease_until = now() + interval '60 seconds',
    attempts = t.attempts + 1,
    updated_at = now()
FROM candidate
WHERE t.id = candidate.id
RETURNING t.*;
```

Това е **claim transaction**, която се commit-ва бързо. Не се държи SQL транзакция отворена през многочасов NAS move. Worker изпраща heartbeat и удължава lease. При crash/restart task преминава през `Reconciling`, **не** през безусловен втори move.

### 12.2 Ресурсни locks

Освен task lease се резервират durable `resource_leases` с монотонен `lease_epoch` за:

- `qbt:<client-id>:<torrent-instance-id>` — една физическа операция за torrent;
- `destination:<normalized-root-and-relative-path>` — без конкурентни collision/write;
- `nas-move` — ограничен брой тежки SMB transfers (начално **1**, конфигурируемо след измервания);
- `library-scan` и `jellyfin-publish` — отделни quota/parallelism лимити;
- `sidecar:<asset-id>:<path>` — ownership-safe optimistic updates.

Lease token/epoch се проверява отново **преди всяко външно действие**. След expiry на lease предишната задача губи правото да изпраща нови API/FS commands; нова задача е длъжна първо да reconcile-не текущите qBt/NAS данни. Външен qBt move, който вече е стартиран, не може да бъде отменен просто чрез освобождаване на DB lease — reconciliation остава задължителен.

### 12.3 Retry budget и backpressure

Предложени **стартови** настройки, подлежащи на измерване преди production:

| Операция | Concurrency | Retry policy |
|---|---:|---|
| qBt physical move / large SMB I/O | 1 | Само safe/reconciled retries; никога blind `setLocation` repeat |
| ffprobe/metadata inspection | 2 | Ограничен брой retry при transient I/O; corrupt media → review |
| TMDb/subtitle network calls | 2 | Exponential backoff, уважение към provider rate limit |
| Jellyfin refresh | 1 active refresh orchestration | Debounce + independent item verification |
| DB maintenance/backup | 1 | Scheduled off-peak; coordination с schema миграции |

`retry_count`, timeout, min NAS free bytes/%, volume reserved и log retention са **операционни параметри**, не фиктивно доказани SLA. Не се изпълнява безкрайно повторение на copy/rename при конфликт на файловете.

## 13. Operation journal, reconciliation и recovery

### 13.1 Persist-before-side-effect protocol

Всяка опасна операция има:

1. **Preflight:** актуален plan hash, source snapshot, разрешени mounts, NAS health, permissions, space, collision, ownership/approval, seeding policy.
2. **Intent transaction:** запис `file_operations(status='PREPARED', op_key, immutable inputs)` плюс audit преди API/FS действие.
3. **Command dispatch:** еднократна команда с correlation ID и външен resource reference; DB `COMMAND_REQUESTED`.
4. **Observe:** polling на действителното qBt/file state (например `MovingObserved`, `DestinationPresent`).
5. **Verify:** integrity, qBt file list/recheck, dependencies, sidecar ownership или Jellyfin published item. Едва тогава `VERIFIED`.
6. **Finalize:** преминаване към следващата стъпка, release на resource lease, audit. При разминаване — `RecoveryRequired` или `NeedsReview`.

```text
PREPARED → COMMAND_REQUESTED → OBSERVED → DATA_VERIFIED → MAPPING_VERIFIED
   │               │                 │
   └───────────────┴─────────────────┴─► UNKNOWN/RECONCILING (never silent retry)
```

**Устойчивост на crash:** когато worker стартира, първо намира `RUNNING` tasks с изтекъл lease и nonterminal `file_operations`. Сверява qBt state, NAS files и immutable plan. Ако qBt вече е преместил файла, преминава директно към verification без повторно `setLocation`. Ако доказателствата са непълни, спира командите и иска review. Няма автоматично изтриване на „полуготови“ NAS файлове.

### 13.2 Safe recovery matrix

| Събитие | Действие |
|---|---|
| qBt HTTP 200, `moving` още активно | Продължи наблюдението, без следваща операция |
| qBt API timeout след изпратен `setLocation` | Readback + reconcile; не повторно `setLocation` без доказателство, че не е започнал |
| NAS offline/autofs невалиден | `BlockedExternalDependency`; source+DB journal се запазват |
| Worker crash след успешен qBt move, преди DB update | Свери qBt save_path/files и physical data; mark verified only if confirmed |
| Случаен overwrite/collision опасност | Стоп преди mutation; `NeedsReview`, no implicit replace |
| qBt recheck непълен/failed | `RecoveryRequired`; не cleanup, не Jellyfin terminal success |
| qBt manually paused/ratio-limited | Запази user policy; `SeedingCapable` ≠ currently uploading |
| Промяна на категория/файлове по време на approval | `ReplanRequired`, старата approval ревизия става невалидна |
| Subtitle provider outage | `Unavailable` с warning, ако всички критични checks са минали |
| Jellyfin refresh accepted, item липсва | `PublishPending`, повторна верификация без повторен NAS move |
| Quarantine restore destination collision | Review/нов restore plan, без overwrite |
| DB offline | Worker не изпълнява нови side effects; qBt може да продължи нормално seed/download |

### 13.3 Transaction boundary и cleanup

**AD-16** е отделна, защитена операция, **не** неизбежен последен ред на move handler. `cleanup_eligible` изисква:

- документално proof за завършен move, проверена destination integrity и валидни qBt pieces/mapping;
- proof, че source е временен local/staging artifact, не library/quarantine/seed target;
- нулеви live qBt dependencies към source path, включително други torrent instances;
- доверен ownership/mount mapping и точен file identity (не само inode/link count на CIFS);
- отделен journal и idempotent delete на **конкретен самостоятелен orphan file**, без рекурсивно изтриване на произволна директория.

При всяко съмнение: `CleanupBlocked` и review. Physical remove на библиотечен/quarantine asset **не се реализира** във v1.0.

## 14. Категории, идентификация и naming

### 14.1 Категории [ACCEPTED]

| qBt `category` | Library root | Поддиректории / правила |
|---|---|---|
| `movies` | `Library/Movies` | `Title (Year) [tmdbid-ID]/` |
| `series` | `Library/Series` | `Series Title (Year)/Season NN/` |
| `animations` | `Library/Animations` | **`Movies/` или `Series/`** според установения тип |
| `documentaries` | `Library/Documentaries` | **`Movies/` или `Series/`** според установения тип |
| `concerts` | `Library/Concerts` | `Artist - Event (Year)/` при надеждни данни |

Не се допуска автоматична смяна на избраната qBt top-level категория. При conflict между category и media type — `NeedsReview`.

### 14.2 Идентификация

Последователност: qBt file/release name → media type/category compatibility → локален metadata parse → TMDb search/candidate ranking → optional cross-check на runtime/episode/edition → explicit high-confidence decision или `NeedsReview`.

- `provider_id` се записва **само ако е установен**, не placeholder.
- Episode mapping е задължителен за season packs; `Season 00`, multipart и S01E01-E02 са отделни случаи.
- При concert без надеждно събитие/артист/година → review, без измислени metadata.
- Всеки match пази explainable reason codes и версия на matcher/rules. Confidence cutoffs се калибрират чрез G-05 и не се хардкодират без реални samples.

### 14.3 Naming contract

```text
Movies/
└── The Matrix (1999) [tmdbid-603]/
    ├── The Matrix (1999) [tmdbid-603] - 1080p BG - Theatrical.mkv
    ├── The Matrix (1999) [tmdbid-603] - 2160p HDR - Extended.mkv
    ├── movie.nfo
    └── poster.jpg

Animations/Series/
└── Example Animated Show (2018)/
    └── Season 01/
        └── Example Animated Show S01E01 - 1080p.mkv
```

**Пълният movie filename prefix** трябва да съответства на folder name (включително year/provider ID) за Jellyfin multiple versions. Edition се пази самостоятелно в DB, независимо от Jellyfin grouping. `BG` suffix се добавя **само** при `BG_VERIFIED`. Субтитри: `<exact video filename stem>.bg.srt` или проверен Jellyfin-supported pattern.

**Path safety:** Unicode normalization, character escaping, `..`/absolute path/symlink guards, length limits, case-insensitive collisions, няма overwrite на съществуващи версии без plan. Всички paths се валидират от Worker спрямо logical root, а не директно от UI string.

## 15. BG evidence, quality engine и дубликати

### 15.1 BG audio [ACCEPTED]

`BG_VERIFIED` само от човешко потвърждение или **проверимо** предходно доказателство, свързано с file+stream fingerprint. `BG_TAGGED`, `BG_SUSPECTED`, `AUDIO_UNKNOWN`, `NO_BG` не са еквивалентни на verified. `ffprobe` открива tracks/tags, но **не проверява езика чрез прослушване**.

Всяко ръчно Verify/Revoke пази actor, timestamp, stream identity, file fingerprint и audit event. Ако payload или stream identity се промени, proof се преоценява. Последващо rename за добавяне на `BG` не се изпълнява директно върху активен torrent извън qBt-aware plan.

### 15.2 Explainable Quality Engine [ACCEPTED]

Фактори: edition identity, media integrity, source/encode quality, resolution, context-aware bitrate, HDR/DV, video/audio codecs, streams/channels, BG evidence, subtitle quality и seeding dependencies. Не се приема „най-голям файл/най-висока резолюция = най-добър“.

| Сравнение | Препоръка |
|---|---|
| 1080p BG verified срещу 2160p EN с доказана съществена качествена разлика | `KeepBoth` |
| BG verified срещу EN със сходно качество | `KeepBGPreferred` |
| Better verified BG версия | `PreferBetterBG`, старата **не** се изтрива |
| Theatrical срещу Extended | Различни editions, не обикновен duplicate |
| Missing/contradictory evidence | `NeedsReview`, не silent replacement |

Quality decision е **предложение**, не permission за quarantine/delete. Измеримият праг „съществено по-добра“ се калибрира в G-05. При неподкрепени media types качеството не се оценява с измислен numerical score.

### 15.3 Duplicate/Quarantine boundary

Класове: byte-identical, same-title/same-edition/quality variant, different-edition, ambiguous metadata, shared-content-dependency. Потребителят вижда сравнение и причини. Quarantine е отделен approve → dependency recheck → reversible move → manifest → restore-capable lifecycle. Няма auto-quarantine и няма permanent library delete във v1.0.

## 16. Subtitle, sidecar и quarantine lifecycle

### 16.1 Bulgarian subtitles [ACCEPTED]

Приоритет: verified existing external → проверен embedded BG stream → exact-version subtitle provider candidate → предложена sync корекция → manual review. `CandidateFound`, `Matched`, `Synchronized`, `Mismatch`, `Unavailable`, `NeedsReview` са различни състояния.

**Правила:**

- Не се прикрепя subtitle автоматично само защото има `.bg.srt`, `bul` language tag или съвпадащо заглавие; edition/runtime/FPS/timing/release се проверяват.
- При недоказан subtitle sync и риск за вече съществуващ файл се иска review; оригиналният subtitle остава непокътнат.
- Subtitle provider adapter е optional и конфигурируем; външните услуги подлежат на authentication, лицензионни условия, rate limits и timeouts.
- Няма UI декларация „Synchronized“ без доказано съответствие. Ако всички критични media/NAS/qBt/Jellyfin проверки са успешни, липсата на субтитри може да доведе до `CompletedWithWarnings`.

### 16.2 NFO/artwork ownership [ACCEPTED]

**Автоматичен update се допуска само когато файлът е доказано създаден от ViMag и е непроменен след последното ViMag записване.**

```text
Read DB ownership manifest → expected last_written_sha256
    │
Read actual current file hash (and no manual lock)
    ├─ match + plan current + no concurrent writer → write temp sidecar
    │                                             → verify → safe replace → new manifest/audit
    └─ mismatch / unknown owner / missing path / Jellyfin edit
                                      → SidecarConflict/NeedsReview; preserve existing bytes
```

- Проверяваме правата и физическия mount преди запис; временното копие се създава в **същата** целева директория, когато safe atomic replace действително е потвърден върху CIFS.
- Не използваме NFO filename като ownership proof. Jellyfin NFO saver, ако променя същия файл, се счита за външен writer; изключваме write loop чрез ownership/конфигурационна политика.
- `movie.nfo`, `tvshow.nfo`, artwork и episode NFO имат отделни manifest records, а не една обща метка „папката е наша“.
- При explicit approval за замяна на чужд/редактиран файл се записва backup/rollback reference и точният стар hash, преди overwrite. Одобрението важи за конкретен revision.

### 16.3 Quarantine + Restore [ACCEPTED]

- Предварително inventory + before/after preview, dependency map и seeding proof.
- Човешко `ApproveQuarantine` за конкретен asset и plan hash; няма auto-quarantine.
- Няма action за физическо изтриване на library asset, дори след approval.
- Restore е самостоятелно журналируем действие, с collision check и content verification.
- Quarantine не се purge-ва по таймер; retention политика не дава implicit permission за permanent delete.
- Използват се allowlisted quarantine roots и отделни access/ownership контроли. Quarantine на файл, който служи за seed или се споделя с други torrents, остава блокирана.

## 17. Jellyfin publication contract

### 17.1 Тригери и верификация [ACCEPTED]

Старият `jellyfin-scan.sh` доказва, че Jellyfin refresh може да се задейства с `POST /ScheduledTasks/Running/{id}` или fallback `POST /Library/Refresh`, но използва cooldown/delay и **не доказва** item-level publication. `autorun_enabled=false` е потвърдено; скриптът не се включва отново паралелно.

В новия Worker:

1. Изчаква `TorrentMappingVerified`, `IntegrityVerified` и `SeedingCapable`, плюс готовите Jellyfin-facing paths и проверените sidecars.
2. Определя правилния Jellyfin Movies/Shows library root от категоризацията и media type.
3. Групира безопасно refresh заявки, но държи **отделен verification record за всеки Child Media Item**.
4. Стартира refresh през проверения Jellyfin endpoint, с нов валиден token.
5. Наблюдава Jellyfin scheduled-task scan completion (когато API предоставя достоверно състояние) **и** проверява Item/Provider ID/path/edition/streams през Jellyfin API. Самият `HTTP 200/204` е `RefreshRequested`, не `PublishedVerified`.
6. При недостъпен Jellyfin, missing version/edition, duplicate index или невалидно съвпадение → `PublishPending`/`NeedsReview`; retry **без повторен qBt move**.

### 17.2 Library type integration [G-03]

| Physical library subtree | Желан Jellyfin content type |
|---|---|
| `Library/Movies` | Movies |
| `Library/Series` | Shows |
| `Library/Animations/Movies` | Movies |
| `Library/Animations/Series` | Shows |
| `Library/Documentaries/Movies` | Movies |
| `Library/Documentaries/Series` | Shows |
| `Library/Concerts` | Metadata/model според реалната Jellyfin настройка; тестов gate |

Не включваме един и същ physical path в две сканиращи библиотеки. `Library` root, torrent store и nested subfolders се валидират за **double indexing**. Movie filename prefix съвпада с директорията, edition/quality variants се проверяват на действителната Jellyfin версия. Нито един от тези настройки не е доказан с текущата диагностика — G-03 остава отворен.

### 17.3 Seeding не зависи от Jellyfin

Ако Jellyfin е offline, провереният qBt torrent остава в оригиналния seeding/paused state. `PublishPending` не връща данните на локалния диск, не блокира qBt seeding и не извиква втори move. Възстановяването обработва само публикацията.

## 18. Backend API, authentication и UI

### 18.1 Application API v1 [DESIGN]

Same-origin `/api/v1/*` с session-based authentication; HTTP body JSON, освен специални endpoints. Long-running commands → `202` + `operation_id`, non-blocking. Всички mutation endpoints изискват `Idempotency-Key` и optimistic `plan_revision`/`plan_sha256` за операции, които зависят от план.

| Method | Endpoint | Роля / резултат |
|---|---|---|
| `POST` | `/api/v1/auth/setup` | Първоначално enrollment **само при празна DB**, с еднократен setup token от secret/console; без default credentials |
| `POST` | `/api/v1/auth/login` | Един admin; rate limits; Secure/HttpOnly cookie + CSRF setup |
| `POST` | `/api/v1/auth/logout` | Session revocation + audit |
| `GET` | `/api/v1/me` | Session state, permission set |
| `GET` | `/api/v1/dashboard` | Queues, counters, disk/NAS/qBt/Jellyfin health |
| `GET` | `/api/v1/jobs` | Filter/pagination/sort; management scope, state, category |
| `GET` | `/api/v1/jobs/{job_id}` | Parent + Child items, timeline, evidence, errors |
| `GET` | `/api/v1/jobs/{job_id}/plan` | Immutable current plan, before/after, dependencies |
| `POST` | `/api/v1/jobs/{job_id}/review` | Human identity/quality/subtitle decisions; new plan revision |
| `POST` | `/api/v1/jobs/{job_id}/approve` | Approve current plan fingerprint; actor+audit |
| `POST` | `/api/v1/jobs/{job_id}/pause` | Pause orchestration, **не** blanket qBt stop |
| `POST` | `/api/v1/jobs/{job_id}/resume` | Reconcile then continue |
| `POST` | `/api/v1/jobs/{job_id}/retry` | Reconcile then bounded retry, not blind replay |
| `GET` | `/api/v1/jobs/{job_id}/operations` | Requested/observed/verified file/torrent ops |
| `GET` | `/api/v1/library/assets` | Inventory + versions, verified BG, stream summaries |
| `GET` | `/api/v1/library/duplicates` | Compare candidates / keep / review |
| `POST` | `/api/v1/library/quarantine-plans/{id}/approve` | Exact plan approval; never delete |
| `POST` | `/api/v1/library/quarantine/{id}/restore` | Validated restoration plan + journal |
| `GET` | `/api/v1/subtitles` | Matching/timing/review state |
| `GET` | `/api/v1/settings` | Public-safe settings без secrets |
| `PUT` | `/api/v1/settings/{section}` | Validated nonsecret settings + revision/audit |
| `GET` | `/api/v1/health/live` | Process-only liveness (no secrets) |
| `GET` | `/api/v1/health/ready` | DB/worker/read-only dependencies and write gate |
| `GET` | `/api/v1/events` | Authenticated SSE при implement; polling fallback |

**Не съществуват във v1:** `/delete-library-file`, `/purge-quarantine`, admin bypass routes, arbitrary filesystem path execution endpoints, qBt `hashes=all` operations.

**Възможно допълнение:** при по-късно разрешен ingest API към ViMag се допуска `POST /api/v1/intake`, но **с отделно machine credential, ограничено до enqueue** — без admin mutations. За v1 предпочитаме qBt API polling и няма нужда от completion webhook.

### 18.2 Пример за approve request/response

```json
{
  "plan_id": "00000000-0000-0000-0000-000000000101",
  "plan_revision": 4,
  "plan_sha256": "<sha256-of-canonical-plan>",
  "decision": "APPROVE_IMPORT",
  "reason": "Manual review completed"
}
```

- При невалидна сесия `401`, няма admin read/write.
- При липсващ/невалиден CSRF token `403`; никакви side effects.
- При stale plan hash `409 Conflict` (`REPLAN_REQUIRED`), с четим error code.
- При duplicate `Idempotency-Key` връщаме същия operation ID, не стартираме втори qBt move.
- При resource dependency `423 Locked`/`409` с explicit `DEPENDENCY_BLOCKED`/`RECOVERY_REQUIRED` (конкретният status contract се фиксира с OpenAPI).
- Admin session е отделна от machine qBt key; никога не изпращаме qBt/Jellyfin credentials към браузъра.

### 18.3 UI binding към одобрения Wireframe

| UX екран | Данни/действия в реалната версия |
|---|---|
| Dashboard | Jobs, health, staging counts, pending approvals, warnings |
| Job Details | 7-step timeline, parent/child items, evidence, reason codes, approvals/retry |
| Library Explorer | Category tree, artworks, audio evidence, quality variants, Jellyfin links |
| Duplicate Comparison | BG-first factors, editions, dependency graph, Keep Both/Quarantine Proposal |
| Move Queue / Import Pool | Staging, transfer strategy, queue priority, per-move verified progress, errors |
| Subtitle Manager | Candidate sources, edition/time mismatch, manual verify/selection |
| Settings | qBt/Jellyfin connect health, mappings, quality rules, profile, secrets configured/missing |

Дизайнът остава dark/desktop-first с mint/teal акценти. Статусите идват от **persisted backend state**, не от HTML demo таймери. Различава се ясно `Requested`, `Running`, `Verified`, `Failed`, `NeedsReview` и `RecoveryRequired`.

## 19. Secrets, audit и operational hardening

### 19.1 Authentication [ACCEPTED P-01]

- Един локален admin акаунт във v1; задължителна начална регистрация, без статична фабрична парола.
- Паролата се съхранява само като **Argon2id** hash с per-user salt и одобрени cost параметри; настройките се фиксират при implementation security review.
- Сесия чрез `Secure`, `HttpOnly`, подходящ `SameSite`, ротация/expiry и server-side revoke; state-changing requests изискват CSRF проверка.
- API авторизира **всяко** действие (не само UI route). Audit за login, approve, retry, quarantine/restore, setting changes, qBt/NAS действия.
- Setup endpoint се изключва при създаден admin; първоначален setup token е еднократен и не се печата във външен лог.

### 19.2 API credential и network security

- qBt 5.2 machine API key, ако бъде конфигуриран, е с широки права и **един за инсталацията**. Worker-only secret, без копиране към API/Web контейнера; ротация с контролирано прекъсване.
- Jellyfin API token се подменя преди pilot заради предходно споделена стойност; JF token не се embed-ва в скриптове, Compose и docs.
- WebUI 8080 остава **без host published port** според установеното текущо състояние; не отваряме HTTP API публично.
- `web` и `api` нямат media mounts; само Worker има read/write allowlisted volumes.
- `worker` няма `/var/run/docker.sock`, privileged mode, host PID или произволни shell commands от потребителски input. ffprobe е с argv без shell interpolation, resource/time limits.
- NAS path containment: absolute normalization, `realpath`/open flags, symlink guards, collision protection и проверка на bind/mount identity.
- `CIFS inode`/link-count аномалии не са повод за автоматично изтриване; dependencies се установяват с DB/file manifest и qBt mapping.

### 19.3 Логове и лични/чувствителни данни

- Структурирани JSON logs: timestamp, `job_id`, `operation_id`, step, phase, severity, duration, result/error_code, remote service name.
- НЕ логваме WebUI/Jellyfin/DB passwords, API keys, authorization/cookies, tracker passkeys, tokenized URLs, пълни HTTP bodies с credentials.
- Torrent hashes, local filenames и library paths могат да разкриват лична media активност; в общи operational logs се използват редуцирани IDs; detailed data е само в authenticated DB/UI.
- Health endpoints връщат ограничени агрегирани състояния; никакви secrets и user inventories.
- Не се създава публичен telemetry/analytics pipeline. Данните остават локално на ViMag.

## 20. Monitoring, backup и rollback

### 20.1 Runtime metrics и alerts [DESIGN]

| Метрика | Значение / alert |
|---|---|
| `jobs_by_state` | Queued, NeedsReview, Moving, PublishPending, RecoveryRequired |
| `oldest_queued_age` | Backlog или blocked worker |
| `worker_heartbeat_age` | Worker stop/hang |
| `nas_mount_available` | CIFS/autofs real accessibility |
| `nas_free_bytes` | Забрана за cutover под минималния резерв |
| `db_ready` | PG connection + schema revision |
| `qbt_api_ready` | Authenticated API version + reachability |
| `jellyfin_ready` | API reachability, publish backlog |
| `move_bytes / operation_duration` | Инерция/скорост, наблюдавана, не фиктивен progress |
| `failed_recheck`, `unsafe_cleanup_blocked` | Непосредствено human review |
| `sidecar_conflicts` | Jellyfin/NFO external ownership issues |

Здравето се показва в UI. Readiness за обслужване на заявки е различно от readiness за **производствени write операции**: API може да е online, докато NAS е offline и Worker правилно не стартира move.

### 20.2 Backups

- PostgreSQL `pg_dump`/consistent backup по schedule, с checksum и архив **извън** DB data volume; отделно копие извън локалния диск; restore test преди release.
- Pre-cutover snapshot/backup на qBittorrent config и fastresume state; не се заменят автоматично чрез backup restore на работещ qBt.
- Versioned (nonsecret) settings и naming/quality policy; `audit_events`, ownership manifests и `file_operations` са критични за recovery.
- Backup cadence/retention са конфигурируеми operational параметри; предложен baseline: дневни backup-и, седмично независимо копие и периодичен **реален restore test**. Сроковете се фиксират при deployment design.
- Docker image rollback ≠ DB schema rollback. При несъвместима migration се изисква предварително дефиниран compatibility/backup plan; без автоматичен drop/recreate на DB.

### 20.3 Operational runbook

1. `READ_ONLY_MODE=true` / `WRITE_ENABLED=false` — Worker само наблюдава при инцидент.
2. Проверка на `import_jobs`/`file_operations` и Worker heartbeats.
3. Проверка на qBt source/destination mapping и NAS mount без destructive commands.
4. Safe reconciliation и manual review при непотвърдено състояние.
5. Restore от DB backup само при ясна процедура, **без** разминаване между DB и действителния NAS/qBt state.
6. Deployment rollback към предходен image digest само след schema compatibility check и evidence capture.

**Не се използва автоматичен container updater за production.** Всяка нова версия има reviewable release manifest, approval, smoke tests и rollback path.

## 21. Тестова стратегия и validation gates

### 21.1 Видове тестове

| Layer | Среда | Задължителна проверка |
|---|---|---|
| Unit | Dev/CI | Policy engine, canonical names, category routing, path containment, plan fingerprint, error classification |
| API contract | Dev/CI | OpenAPI schemas, CSRF, admin session, idempotency, stale plan hash, read/write separation |
| DB integration | Ephemeral Postgres container | Alembic migrations, constraints, `SKIP LOCKED`, expired lease recovery, audit durability |
| Adapter mocks | Dev/CI | qBt 5.2 204/cookie/API key, `setLocation` async, invalid state, Jellyfin refresh pending |
| Filesystem fixture | Docker на dev/pilot | Synthetic files, single/multi-file, hardlink alias, collision, checksum, failover |
| Security | Dev/CI | Secrets never logged, no traversal/symlink escape, auth/CSRF, no forbidden delete endpoint |
| Actual qBt integration | ViMag, **изолиран нов тестов torrent** | Add Manual TMM/local, rename, move, recheck, seeding policy, no changes to legacy torrents |
| NAS/CIFS integration | ViMag, scratch only | Production Worker UID, one bind, ACL, hardlink, mount availability, no overwrite |
| Jellyfin integration | ViMag, test library path | Movies/Shows mapping, editions, no double indexing, catalog verification |
| Recovery/fault injection | Fixture/pilot | NAS outage, qBt timeout, worker crash, lost DB lease, replay, restore |
| UAT | UI + real integrations with fixtures | 7 screens / 7 workflow steps; all scope tests T-01…T-43 |

### 21.2 Проследимост към 43-те scope acceptance tests

| Тестове от Technical Scope | Компонент и защита |
|---|---|
| **T-01…T-08** | Import workflow, Bulgarian-first, season packs, NAS failure, subtitle mismatch, ambiguous TMDb, dependency block |
| **T-09…T-13** | Queue idempotency, crash recovery, async qBt `setLocation`, recheck failure, destination collision |
| **T-14…T-19** | Category drift, path escape, zero-upload-is-not-failure, intentional pause, AutoTMM conflict, unsupported hardlinks |
| **T-20…T-24** | NFO edit ownership, editions, Jellyfin refresh-not-complete, shared torrents, specials/multi-episode indexing |
| **T-25…T-29** | `BG_TAGGED` vs verified, stream fingerprints, Keep Both, high-confidence identity |
| **T-30…T-33** | Quarantine dependency gate, reversible restore, unknown sidecars, subtitle mismatch |
| **T-34…T-36** | `CompletedWithWarnings`, `PublishPending`, critical Child aggregation |
| **T-37…T-39** | Login/session/CSRF and machine/interactive privilege separation |
| **T-40…T-41** | Automatic writes only to unchanged ViMag-owned NFO/artwork |
| **T-42…T-43** | Permanent library deletion unavailable; verified staging-only cleanup |

**Не променяме определенията в Scope v1.0.** За всеки T-xx трябва да има изпълним автоматизиран тест или документиран UAT/integration test с evidence (logs, state, artifacts), очакван резултат и release gate.

### 21.3 G-01…G-06 — фактически статус към 01.11.2026

| Gate | Налични доказателства | Статус | Какво още блокира production |
|---|---|---|---|
| **G-01 qBittorrent** | v5.2.0 / API 2.15.1; успешен 204 login + cookie; categories, `auto_tmm`, 92 torrents, NAS paths четени през API | **Discovery PASS / write integration OPEN** | Controlled new test torrent: Manual TMM, setLocation/rename/recheck/stop-start semantics, seeding policy, default mode cutover proof |
| **G-02 NAS / hardlinks** | CIFS/autofs, share capacity; host hardlink PASS; isolated Docker single-bind write-through/unlink PASS | **Functional PASS / runtime validation OPEN** | Actual Worker UID/GID and shared mount, CIFS refresh, scratch sidecar atomicity, qBt `/torrent-store` mount and privileges |
| **G-03 Jellyfin** | Стар скрипт е ползвал refresh API; `autorun_enabled=false` | **OPEN** | Real server auth, library roots/types, NFO saver, multi-version/edition behavior, verified item identity, no double-index |
| **G-04 Recovery** | Approved journal/lease design | **OPEN** | Controlled failure injection с restore evidence и no duplicate moves |
| **G-05 Media/quality** | Quality/BG-first rules approved | **OPEN** | Реални sample fixtures, verified BG evidence calibration, subtitle providers/timing, identity thresholds |
| **G-06 Inventory** | Baseline 92 qBt torrents; NAS read-only list не е правен в тази сесия | **OPEN** | Read-only inventory на всички 5 категории и qBt dependency map; snapshot за maintenance work |

**Допълнителен deployment gate G-DB-01:** реалната файлова система под PostgreSQL data path, durable storage/backup и DB restore test трябва да са проверени **преди инсталиране на PostgreSQL на ViMag**. Това не замества G-01…G-06; добавено е конкретно за избора PostgreSQL.

**Един успешен read-only API тест не затваря write интеграцията.** **Един успешен hardlink scratch тест не доказва production permissions за новия Worker.** Така статусът на всеки gate остава технически точен.

### 21.4 Допълнителни Implementation-specific acceptance tests

| ID | Сценарий | Строго очакване |
|---|---|---|
| **IT-01** | При първо включване се откриват 92 legacy torrents | Само `LEGACY_READ_ONLY`, нула qBt write calls |
| **IT-02** | Нов torrent се добавя с Manual TMM и `savepath=/downloads/complete` | Остава локално след download, категорията се запазва |
| **IT-03** | Категория с NAS savePath, но new Manual TMM | Категорията не предизвиква автоматичен NAS move |
| **IT-04** | `temp_path_enabled=false` и file exists при progress < 1 | **Не** се създава completed Import Job |
| **IT-05** | Паралелен duplicate polling/crawler event | Един Job, един Import Plan, един torrent-level move |
| **IT-06** | Worker crash след изпратен `setLocation` | Нов Worker reconcile-ва, не повтаря blindly API командата |
| **IT-07** | Предварително изтекъл resource lease по време на move | Старият Worker не изпраща повече команди, new reconcile-first |
| **IT-08** | API key rotation/401 | AuthRequired; няма повторни login brute-force опити |
| **IT-09** | Temporary source still referenced by qBt/another torrent | CleanupBlocked, source остава |
| **IT-10** | CIFS inode mismatch, но hardlink content shares writes | Няма false delete; manifest/dependency логика работи |
| **IT-11** | Jellyfin scan API връща 200, но липсва item | `PublishPending`, без втори move |
| **IT-12** | Стар qBt torrent със същия hash е remove/re-add | Нов `torrent_instance_id`/generation и explicit review на повторно добавяне; без bypass на legacy gate |
| **IT-13** | PostgreSQL restore върху празна dev среда | Jobs, audit, journal и миграционна ревизия се възстановяват |
| **IT-14** | Реалният Jellyfin token е невалиден/ревокиран | Health/PublishPending; съществуващото seeding не се нарушава |
| **IT-15** | Издадено е ново приложение, а DB migration не е compatible с rollback | Release gate блокира автоматично връщане на image |
| **IT-16** | Старо име на NFO е ръчно променено и хешът се различава | Skip+diff/review, никакъв overwrite |
| **IT-17** | Нов torrent, добавен ръчно през VueTorrent след cutover | Автоматично `VIMAG_MANAGED` само ако всички eligibility условия са изпълнени; без ръчно одобрение за всеки стандартен torrent |

## 22. Поетапно внедряване и безопасен cutover

### 22.1 Фаза A — Design и developer environment

**Вход:** одобрен настоящ документ.  
**Действия:** създаване на директориите в repository, dev Compose на работния компютър, PostgreSQL/Alembic, FastAPI, Worker skeleton, Vue UI, mock qBt/Jellyfin, synthetic fixtures.  
**Изход:** зелени тестове, без достъп до production NAS/torrents.

### 22.2 Фаза B — Read-only adapters и baseline

- Реализиране на qBt authenticated connector + read-only torrent/category/preferences polling; **без `POST` към qBt**.
- Read-only NAS inventory и Jellyfin connectivity; frontend показва Job discovery, но не разрешава опасни действия.
- Създаване на `LEGACY_READ_ONLY` baseline на **92-та текущи torrents**; snapshots с category/save path/autoTMM. След cutover автоматично се onboard-ват само доказано нови и съвместими torrents, докато несъвместимите/външни остават EXTERNAL_UNMANAGED за review.
- Технически read-only deployment на ViMag (без write mounts, `WRITE_ENABLED=false`) е отделно действие и изисква **изрично разрешение**, независимо от одобрението на дизайна.

### 22.3 Фаза C — Isolated write fixtures

След отделно разрешение за тестове: създаваме **нов, собствен/разрешен тестов torrent** с незначителни scratch bytes, **без да променяме 92-та съществуващи**. Работим с отделни test directories и test library.

1. Потвърди API key/session и qBt `add` с `autoTMM=false`, explicit local savepath, валидна category.
2. Потвърди, че след completion torrent остава в `/downloads/complete`.
3. Тествай rename, `setLocation`, recheck, restoration на original seeding policy и independent Jellyfin verification.
4. Тествай NAS torrent store + Worker hardlinks с реалните mounts/UID и scratch-only target; G-02 runtime complete.
5. Изпълни worker crash/API timeout/NAS detach/restart failure injection и root path collision tests.

**Никога не изпълнявай тестов move върху някой от 92-та legacy torrents.**

### 22.4 Фаза D — Controlled default cutover (само нови torrents)

**Предусловия:** G-01 write pilot PASS, G-02 runtime PASS, G-03/G-04 PASS за разрешените операции, backup/snapshot на qBt settings/fastresume, confirmed dry-run и explicit operator approval.

1. Export/backup на текущата qBt конфигурация и актуален baseline на 92-та torrents.
2. Ако тестът е доказал безопасност, сменяме **само default TMM за бъдещо добавяне** на Manual. **Не** редактираме петте category save paths и **не** масово setAutoManagement на съществуващи torrents.
3. Уверяваме се, че `use_category_paths_in_manual_mode=false` продължава да е активна.
4. Тества се **нов** torrent, добавен както през API, така и през VueTorrent UI, за да не изпадне неволно в NAS директория.
5. Worker приема само `VIMAG_MANAGED` и local path `/downloads/complete`; отхвърля всеки неочакван NAS save path.
6. Миграцията може да бъде спряна чрез application `WRITE_ENABLED=false` и контролирано връщане на default настройката след snapshot/проверка; **не местим обратно реални torrents автоматично**.

### 22.5 Фаза E — Limited production pilot

С отделно изрично разрешение: 1–3 **нови** медийни items, само след валидирани G-01…G-05, ясни тестови ограничения и наличен backup. Наблюдаваме copy speed, qBt mapping/recheck, Jellyfin verification, rollback proof и DB recovery. G-06 е блокер за Library Maintenance, не непременно за единичен нов import.

### 22.6 Фаза F — Production enablement

Production `WRITE_ENABLED=true` само след резултатите от pilot, sign-off на tests T-01…T-43 в релевантния release scope, създадени backup/monitoring, персистентни secrets, versioned Docker Hub images и ръчно одобрен deployment. Следваща версия се обновява **само с изричен release approval**, без silent watchtower/auto-updater.

**Rollback scope:** rollback на приложение/конфигурация може да е автоматизиран като команда, но връщане на файлове/разположение на torrent след cross-FS move е **самостоятелен reconciliation/compensation plan**, не „docker compose down/up“.

## 23. Repository структура и definition of done

### 23.1 Предложена mono-repo структура

```text
media-manager/
├── README.md
├── LICENSE                           # policy to be decided before public code release
├── .gitignore
├── .env.example                       # no secrets
├── docs/
│   ├── technical-scope-v1.0.md         # approved and published
│   ├── implementation-design-v1.0.md  # approved design; production gates remain
│   ├── api-contract-v1.yaml            # OpenAPI — generated and reviewed
│   ├── qbt-integration-runbook.md
│   ├── storage-mount-matrix.md
│   ├── operations-and-recovery.md
│   ├── deployment-and-backup.md
│   └── adr/                            # explicit architecture decisions
├── wireframes/
│   └── vimag-media-manager-v1.0.html
├── frontend/
│   ├── src/                            # Vue 3 / TypeScript / Vite
│   ├── public/
│   ├── tests/
│   ├── Dockerfile                       # multi-stage build → Nginx
│   └── package-lock.json               # or selected lockfile
├── backend/
│   ├── app/
│   │   ├── api/                        # FastAPI routes/auth/schemas
│   │   ├── domain/                     # jobs, policies, ownership, quality
│   │   ├── adapters/                   # qBt, Jellyfin, TMDb, subtitles, filesystem
│   │   ├── worker/                     # queue handlers, reconcile, schedules
│   │   ├── persistence/                # ORM/models + repositories
│   │   ├── security/
│   │   └── settings.py
│   ├── alembic/                         # migrations
│   ├── tests/
│   ├── pyproject.toml                   # pinned dependencies
│   └── Dockerfile                       # ONE image, two entrypoints
├── deploy/
│   ├── compose.dev.yaml                # synthetic files only
│   ├── compose.prod.yaml               # images only (NO build)
│   ├── env.example
│   ├── scripts/                        # deploy/backup/restore with safety checks
│   └── release-manifest.schema.json
├── tests/
│   ├── fixtures/                       # own/public-domain synthetic fixtures
│   ├── contracts/
│   ├── integration/
│   └── acceptance/
└── .github/workflows/
    ├── ci.yml
    ├── build-release.yml
    └── security.yml
```

Това е **предложена структура**, не инструкция автоматично да се добави код към GitHub. Публичният repository не съдържа production Compose secrets, real `.torrent` metadata, потребителски медийни файлове, API keys или tracker URLs.

### 23.2 Development milestones

| Milestone | Съдържание | Done когато |
|---|---|---|
| **M1 — Foundation** | Repo/dev Compose, PostgreSQL/Alembic, auth/CSRF, health, CI | Tests + reproducible dev stack |
| **M2 — Read-only integration** | qBt/Jellyfin health, torrents baseline, inventory dashboard | 92 legacy records read-only; no qBt write calls |
| **M3 — Staging & planning** | ffprobe, identity/quality engine, naming, approvals, Import Pool UI | Real plans with evidence, zero mutations |
| **M4 — Safe transfer engine** | Journal, leases, qBt adapter, single-file strategy, hardlinks, reconciliation | Isolated fixture G-01/G-02/G-04 passed |
| **M5 — Media enrichment** | Sidecar ownership, subtitles, Jellyfin publish verify, quarantine restore | T-20…T-43 relevant scenarios passed |
| **M6 — Delivery** | GitHub Actions, Docker Hub images, production Compose/backup, pilot | Signed-off release + rollback + controlled ViMag pilot |

### 23.3 Definition of Done за v1.0 release

- **Functional:** одобрените седем екрана, седем workflow стъпки, Bulgarian-first, categories/editions, quarantine+restore и 43 scope test scenarios са покрити.
- **Safety:** никой legacy torrent не е променен; няма implicit file deletion; release не позволява unverified cleanup, unchecked overwrites или broad qBt commands.
- **Data:** jobs/plans/audit/manifests преживяват рестарт; backup/restore, SQL migrations и failover тестове са изпълнени.
- **Ops:** versioned images, no build on ViMag, health/readiness, manual deploy approval, documented rollback, secret rotation.
- **Evidence:** G-01…G-06 (според активирания модул), G-DB-01 и интеграционни safety fixtures имат протоколи с резултат PASS, не само устно предположение.

## 24. Отворени реализационни параметри и sign-off

### 24.1 Какво е решено и какво остава за проверка

| Тема | Предложено/прието | Нужна проверка преди production |
|---|---|---|
| Docker-only production | **Прието** | Final Compose и мрежи |
| Работа във VS Code + GitHub + Docker Hub | **Прието** | Архитектура на ViMag (`amd64`/`arm64`), namespace и CI credentials |
| API/Worker/Web/DB | **Прието като Implementation Design v1.0** | Image tags, ресурси и healthchecks |
| PostgreSQL вместо SQLite | **Прието като Implementation Design v1.0** | Версия/PGDATA, local Linux filesystem, backup-restore |
| Staging Pool `complete` | **Прието** | Fixture prove `Manual TMM` и category save paths behavior |
| Preserve 92 existing torrents | **Прието** | Baseline snapshot + write guards |
| qBt API | **Read-only потвърдено** | New-fixture write semantics, auth key, `setLocation` progress/recheck |
| NAS hardlinks | **Host + Docker scratch PASS** | Actual Worker UID/qBt mount/ACL и NAS outage tests |
| Jellyfin publish | **Принцип приет** | Real Jellyfin libraries, version grouping и item verification |
| Quality and BG audio | **Политика приета** | Representative calibration и evidence checks |
| Subtitle providers | **Политика приета** | Избор на providers, лицензни условия и integration tests |
| Cleanup/quarantine | **Политика приета** | Journal, dependency verification и restore proof |
| Queue concurrency | **Стартово 1 NAS move** | Реални трансфери, retry timeouts, свободно място |
| Image updates | **Manual digest-pinned releases** | Build pipeline и rollback rehearsal |

### 24.2 Изискващи измерване operational values

**Не са фиксирани като емпирични факти:** max concurrent moves, ffprobe timeout, NAS minimum free bytes/%, retry/backoff ceiling, worker heartbeat period/lease length, file-hash strategy for large movies, DB backups cadence/retention, Jellyfin scan timeout, BG quality confidence cutoffs и subtitle sync thresholds. Тези стойности се записват като versioned config и се приемат след реални измервания/тестове.

### 24.3 Review/approval checklist

- [x] Приемам четирите Docker runtime контейнера и два собствени images.
- [x] Приемам PostgreSQL като DB и persistent queue без Redis/RabbitMQ.
- [x] Приемам `LEGACY_READ_ONLY` baseline за 92 torrents и write само за ViMag-managed нови torrents.
- [x] Приемам Worker ownership на qBt orchestration, но не на самостоятелен move на активен torrent payload.
- [x] Приемам `temp_path_enabled=false` като текущо състояние; `complete/` може да съдържа незавършени файлове, които се игнорират до qBt completion.
- [x] Приемам hardlink модел с един Worker NAS bind и без `st_ino`-only cleanup решения.
- [x] Приемам PostgreSQL job ledger/leases, operation journal и recovery-first strategy.
- [x] Приемам tag-based GitHub Actions → Docker Hub и manual production deployment.
- [x] Потвърждавам, че реални файлови операции/ново deployment изискват отделно разрешение след G-01…G-06 и G-DB-01.

**Статус след одобрение:** **APPROVED FOR DOCUMENTATION / GitHub publication authorized** на 01.11.2026 г. Настоящото одобрение и публикация **не означават разрешение за разработка, deployment, промени на NAS или qBittorrent**. Development kick-off и production cutover изискват отделни решения; G-01…G-06 и G-DB-01 остават приложими.

## 25. Технически референции

**Нормативни вътрешни документи**

1. [ViMag Technical Scope v1.0 — Approved](technical-scope-v1.0.md) — приетите 22 избора, 43 теста и G-01…G-06.
2. [ViMag Interactive Wireframe v1.0](../wireframes/vimag-media-manager-v1.0.html) — седемте UX екрана и осемте demo сценария.
3. Предоставени CLI/API отчети от ViMag на 01.11.2026 г.: qBittorrent v5.2.0 / Web API 2.15.1, 92 torrents, TMM settings, CIFS mount, isolated NAS/Docker hardlink tests. Отчетите са **потребителски доказателства**, не независим достъп до сървъра.

**Публични технически спецификации**

4. [qBittorrent WebUI API (qBittorrent 5.0)](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-%28qBittorrent-5.0%29) — read/write endpoints и параметри; 5.2.0 behavior задължително се тества с fixture.
5. [qBittorrent API Key Authentication (v5.2.0+)](https://github.com/qbittorrent/qBittorrent/wiki/API-Key-Authentication-%28%E2%89%A5v5.2.0%29) — single `Bearer` API key за machine integration.
6. [PostgreSQL: `SELECT` / `FOR UPDATE SKIP LOCKED`](https://www.postgresql.org/docs/current/sql-select.html) — queue claim pattern; не е подходящо за общ консистентен snapshot, а за queue-like contention.
7. [Docker Compose services / bind mounts](https://docs.docker.com/reference/compose-file/services/) — long syntax bind mounts и `create_host_path: false`.
8. [Docker Build with GitHub Actions](https://docs.docker.com/build/ci/github-actions/) — reproducible build/push pipeline.
9. [Jellyfin Movies](https://jellyfin.org/docs/general/server/media/movies/) и [TV Shows](https://jellyfin.org/docs/general/server/media/shows/) — naming, versions и episode structures.
10. [Jellyfin Local NFO](https://jellyfin.org/docs/general/server/metadata/nfo/) — local NFO precedence и ownership conflict handling.

---

**Финално правило:** `Approved Technical Scope` → `Reviewed Implementation Design` → `Development with fixtures` → `Proven qBt/NAS/Jellyfin safety gates` → `Explicitly approved production cutover`. Нито един преход не се случва автоматично само защото предходният документ е публикуван.
