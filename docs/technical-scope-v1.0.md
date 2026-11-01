# ViMag Media Manager — Техническа спецификация и обхват

**Документ:** `docs/technical-scope-v1.0.md` — одобрена техническа спецификация  
**Статус:** **APPROVED — Technical Scope v1.0; всички 22 продуктови избора и консолидираният документ са одобрени; публикацията е разрешена на 01.11.2026 г.**  
**Версия:** v1.0  
**Дата:** 01.11.2026 г.  
**Проект:** [vesovasilev-vimag/media-manager](https://github.com/vesovasilev-vimag/media-manager)  
**UX основа:** Interactive HTML Wireframe v1.0 — **одобрен**  
**Имплементация:** не е стартирана; без разрешени промени по NAS, qBittorrent, Jellyfin или Docker.  
**История:** Кръг 1 (5 решения) + Кръг 2 (7 решения) + Кръг 3 (7 решения) + Финален кръг (3 решения) = **22 потвърдени избора**; AD идентификаторите обозначават архитектурни теми и някои се повтарят.

> **Цел:** Единна, пълна спецификация на приетите продуктови изисквания и ограничения преди реална разработка. Този документ е **одобрен за публикуване** на 01.11.2026 г., но не е разрешение за реални файлови операции, имплементация или deployment.

## 0. Статус и управление на решенията

| Маркер | Значение |
|---|---|
| **ПРИЕТО** | Изрично договорено продуктово изискване |
| **ПРЕДЛОЖЕНО** | Конкретно инженерно предложение, подлежащо на одобрение |
| **ОТВОРЕНО** | Решение, което все още не е взето |
| **ТЕХНИЧЕСКИ GATE** | Изисква измерване / интеграционен тест преди изпълнение, без да отменя приетата продуктова политика |
| **БЛОКЕР** | Без това решение/тестове не започваме операции върху реални файлове |
| **ИЗВЪН v1** | Не влиза в първата версия |

### 0.0 Протокол на решенията — Кръг 1 (01.11.2026) — ПРИЕТО / ТЕХНИЧЕСКИ УСЛОВНО

Петте избора по-долу са **изрично одобрени продуктови политики**. Това не е разрешение за операции върху истински файлове. Кандидатните технически механизми са предмет на read-only обследване и изолирани тестове преди изпълнение.

| ID | Избран вариант | Прието правило | Оставаща техническа проверка |
|---|---|---|---|
| **AD-01a** | **A** | За прост и съвместим torrent предпочитаме **qBittorrent-managed relocation + torrent-aware rename**, когато може да се постигне Jellyfin naming без нарушаване на file mapping. | Асинхронно API поведение, rename sequence, path mapping, TMM/категории, mount видимост и recheck. |
| **AD-01b / AD-08 / AD-17** | **A** | За multi-file/season packs предпочитаме **NAS torrent tree + Jellyfin library hardlinks**, със защита при невъзможни hardlinks и ръчен преглед на fallback. | Same-filesystem constraint, bind mounts, права, inode/mount tests, допълнителен NAS капацитет и защита от двоен scan. |
| **AD-02 / AD-20** | **A** | Manager има право на **контролирани qBittorrent операции само за текущия Job**: pause, move, rename, recheck, resume. Пази първоначалното torrent и user-policy състояние, без глобални промени. | Проверка на текущия qBt 5.x Web API, `auto_tmm`, category save paths и pause/queue semantics. |
| **AD-16** | **A** | **Автоматично cleanup само на доказано ненужни временни локални/staging копия**, след потвърдено integrity, NAS presence, qBt mapping и seeding capability. | Нужни са journal, проверка на ownership и live dependencies, no-overwrite, recovery и безопасно повторение. |
| **AD-01 / Recovery** | **A** | **Автоматичен bounded retry само за преходни и доказано безопасни грешки**; неизвестно състояние, data mismatch или риск от загуба => `RecoveryRequired` и човешки преглед. | Retry budgets/backoff, reconciler, idempotency, compensation tests. |

**Изрични граници на одобрението:**

- Изборът на hardlinks **не** дава право на самостоятелно преместване или промяна на активни torrent bytes; осигурява само второ име на NAS *след* потвърждаване на torrent tree.
- При липса на hardlink support **няма автоматично преминаване** към двойно копие или destructive операция; Job преминава към `NeedsReview/StrategyUnavailable` до одобрен fallback.
- Пълното локално cleanup не означава изтриване на библиотечни версии, sidecar файлове с непотвърден ownership, torrent entries или активни seed dependencies.
- Умишлено paused/queued torrents запазват първоначалната политика. `SeedingCapable` означава валидни данни и mapping, **не** задължителен активен upload.
- Профилът на transfer стратегията е **per Job**, а не безусловен глобален алгоритъм; тестовете могат да блокират неподдържаните сценарии, без да отменят приетите продуктови цели.

### 0.0.1 Протокол на решенията — Кръг 2 (01.11.2026) — ПРИЕТО / ИЗИСКВА ИНТЕГРАЦИОННА ПРОВЕРКА

Седемте избора **A** по-долу са изрично приети. Форматите са **функционални правила**, а не разрешение да се преименуват съществуващи файлове преди проверка на реалната Jellyfin конфигурация и qBittorrent mapping.

| ID | Решение | Приета политика | Оставаща техническа проверка |
|---|---|---|---|
| **AD-03** | **A** | `Animations/Movies/`, `Animations/Series/`, `Documentaries/Movies/`, `Documentaries/Series/` — отделни филмови и сериални подструктури. Top-level qBt категорията остава същата. | Jellyfin library paths и content types; сканиране без дублиране. |
| **AD-04a** | **A** | Имената на файловете и директориите следват **оригиналното/каноничното заглавие от надежден provider**, с възможност за ръчна корекция. | Unicode normalization, collision policy, provider fallback. |
| **AD-04b** | **A** | Различните editions (`Theatrical`, `Extended`, `Director's Cut`) се съхраняват в **една директория на произведението**, в отделни версии с edition marker и отделна edition идентичност в базата на ViMag. | Как Jellyfin представя editions спрямо versions; тестове за grouping. |
| **AD-04c** | **A** | Добавяй `BG` във video filename **само при `BG_VERIFIED`**, никога само по езиков tag или release string. | Evidence mechanism и кога е разрешено последващо преименуване на сеедван файл. |
| **AD-04d** | **A** | Сериали: `<Series Title> S01E01 - 1080p.mkv` и `Season 01/`; season/multi-episode/part variants — отделни правила. | Jellyfin version grouping и безопасен torrent mapping. |
| **AD-04e** | **A** | Концерти: `<Artist> - <Event> (<Year>)` като основна схема; при непотвърдени данни — `NeedsReview`, без измислен ID, година или артист. | Реален fallback по наличните concert metadata, multipart/disc. |
| **AD-17** | **A** | Един torrent с няколко **независими произведения** поражда един **Parent Import Job** и логически **Child Media Jobs/Items**, всеки със собствен identity/destination/subtitle/publish state. | Torrent-level операции остават общи; split, cross-category и collision cases преминават през проверки. |

**Уточнения за съвместимост и граници:**

1. **Top-level категории ≠ Jellyfin library types.** Четирите нови поддиректории остават под двете qBt категории, но за надеждна идентификация в Jellyfin трябва да се използват отделни movie/show library paths (или доказано еквивалентна конфигурация). Jellyfin предупреждава, че Mixed libraries могат да доведат до ненадеждни metadata резултати.
2. **Edition ≠ качество ≠ BG аудио.** Различни editions са отделни логически варианти, дори ако Jellyfin ги визуализира като multiple versions на един item. ViMag не ги събира в duplicate cleanup по невнимание.
3. **BG marker** не е самостоятелно доказателство; той отразява проверен evidence state. При преход `BG_TAGGED → BG_VERIFIED` името не се сменя автоматично, ако това засяга активен torrent; създава се безопасен rename plan.
4. **Mixed torrent** означава множество независими произведения, а не само season pack. Всички Child Media Jobs споделят една torrent-level physical move и seeding verification операция. Неподходящо за категорията произведение не се премества автоматично в друга top-level категория.
5. Предложените placeholders за резолюция/HDR/DV, Unicode, edition escaping, special/SDH/forced subtitles остават за техническа валидация, без да се отменя избраният naming подход.

**Източници за naming verification:** [Jellyfin — Movies](https://jellyfin.org/docs/general/server/media/movies/), [Jellyfin — Shows](https://jellyfin.org/docs/general/server/media/shows/), [Jellyfin — Libraries](https://jellyfin.org/docs/general/server/libraries/).

### 0.0.2 Протокол на решенията — Кръг 3 (01.11.2026) — 7 ИЗБОРА A ПРИЕТИ

Изборите на потребителя са окончателни **за продуктовото поведение**, но **не** означават, че конкретни алгоритми, прагове, providers или файлови операции са вече технически валидирани.

| ID | Вариант | Прието изискване | Условие/граница |
|---|---|---|---|
| **AD-05** | **A** | `BG_VERIFIED` се присвоява **само след ръчно потвърждение или предходно надеждно доказателство**. Language tag `bul`/`bg`, release name и stream title не доказват аудио сами по себе си. | Evidence provenance, stream identity, fingerprint, actor/time и възможност за revocation/re-review. |
| **AD-06** | **A** | **Многофакторна оценка на качеството**, с Bulgarian-first safeguard; спорните случаи преминават в `NeedsReview`. Не е допустим winner само по resolution/file size. | Прагове/тегла се калибрират върху реални samples, без фиктивен numeric score. |
| **AD-07** | **A** | Quality Engine **предлага** какво да се запази; inferior version влиза във **възстановима quarantine само след изрично одобрение** и dependency checks. | Финалният P-03 фиксира **никакъв permanent library delete дори след approval**; непотвърден ownership или seeding dependency блокират quarantine. |
| **AD-14** | **A** | Автоматичен metadata match **само при висока увереност**, съгласувани provider ID/type/year/episode данни; иначе `NeedsReview`. | Confidence rule е explainable и версиониран; числовите cutoffs са за измерване. |
| **AD-15** | **A** | Автоматични са само **безопасните sidecar/metadata действия** при проверен ownership и без риск от overwrite; рисковите корекции изискват предварително одобрение. | Без mutation на torrent payload; без подмяна на manually maintained NFO/artwork и библиотечни версии. |
| **AD-09** | **A** | При несинхронизирани BG subtitles системата търси подходящ кандидат/предлага sync, но **използва резултата само след проверка**. | Оригиналните subtitle файлове се пазят; provider integration и автоматизируемостта на timing verification остават технически gate. |
| **AD-18** | **A** | `CompletedWithWarnings` е разрешен **само за нефатални subtitle пропуски** след проверени NAS, Jellyfin и seeding; недовършен Jellyfin publish е `PublishPending` и **не** е `Completed`. | За publish/seeding failure няма успешен terminal status; child item status се отчита на parent job. |

**Изрични ограничения на Кръг 3:**

- **BG evidence ≠ metadata tag.** При преместване или rename доказателството се свързва с проверения stream/file; при промени, които го обезсилват, се изисква повторно потвърждение.
- **Quality recommendation ≠ permission to delete/quarantine.** Сравнението е explainable, но не извършва опасни операции самостоятелно.
- **Automatically found subtitle ≠ synchronized subtitle.** `CandidateFound`, `Matched`, `Synchronized` и `ManualReview` са отделни състояния.
- **Partial success ≠ seeding/publish failure ignored.** `CompletedWithWarnings` не маскира липсващи файлове, лош recheck, непроверено Jellyfin index entry или някой unresolved критичен Child Media Item.
- Изборът **A** за AD-15 е допълнен от **P-02/AD-19**: само непроменени ViMag-owned sidecars се обновяват автоматично; всяка външна редакция блокира overwrite и изисква review.

### 0.0.3 Протокол на решенията — Финален кръг (01.11.2026) — ПРИЕТО

Потребителят избра **A и по трите финални продуктови въпроса**. С това всички продуктови решения от четирите кръга са затворени: **5 + 7 + 7 + 3 = 22 избора**. Групираните AD идентификатори не трябва да се сумират като 22 уникални архитектурни теми.

| ID | Избор | Нормативна политика за v1.0 | Изпълнително ограничение |
|---|---|---|---|
| **P-01 / AD-10** | **A — ПРИЕТО** | **Един локален административен акаунт** с login, защитена сесия и server-side authorization на всяко API действие. Без роли Viewer/Operator във v1.0. | VPN е допълнителен периметър, не заместител на login; completion hooks ползват отделен машинен механизъм. |
| **P-02 / AD-19** | **A — ПРИЕТО** | ViMag може да създава и автоматично обновява **само свои NFO/artwork, които не са променяни след последното генериране**. Непознати или ръчно променени файлове се запазват и изискват одобрение за замяна. | Нужни са запис за ownership, последен content hash, versioned audit и проверка на конфликти с Jellyfin NFO saver. При неизвестно състояние — skip/review. |
| **P-03 / AD-07** | **A — ПРИЕТО** | **Няма операция за окончателно изтриване на библиотечни версии във v1.0**, дори след approval. Има обратима **Quarantine + Restore**. | Автоматичният cleanup на доказано ненужни временни локални/staging копия по AD-16 е различна, допустима операция. Quarantine не се purge-ва автоматично. |

**Няма оставащи отворени продуктови въпроси за обхвата v1.0.** Има шест **технически gates G-01..G-06**, които трябва да бъдат преминати преди действителни файлови операции, и измерими operational параметри, които се определят по време на implementation design. Нито едно от тези условия не е маркирано като изпълнено.

### 0.0.4 Принципи за приемане и публикуване

- **Product policy decisions: CONFIRMED** — всички 22 избора са отразени.
- **Technical Scope v1.0: APPROVED** — всички продуктови решения и консолидираният документ са изрично приети на 01.11.2026 г.
- **GitHub: PUBLICATION AUTHORIZED** — одобрените README, Technical Scope и UX wireframe се публикуват по изрично разрешение на 01.11.2026 г.
- **Development and infrastructure operations: NOT AUTHORIZED** — без backend, Docker deployment, NAS/qBittorrent/Jellyfin промени, автоматизации или реален library cleanup.
- **Technical gates: NOT VERIFIED** — приетата стратегия е цел; реалната техника трябва да премине изолирани проверки. Неподдържан сценарий остава `NeedsReview` или `StrategyUnavailable`, а не произволен fallback.

### 0.1 Критични принципи — ПРИЕТО

1. **Категорията се избира от потребителя в qBittorrent.** ViMag управлява идентификацията, имената и поддиректориите **в нея**, без тихо прехвърляне между top-level категории.
2. **Bulgarian-first with quality safeguards.** Верифицираното българско аудио се пази; съществено по-добра версия без BG audio може да съществува паралелно.
3. **Никаква неочаквана загуба на данни.** Без автоматично библиотечно изтриване, transcoding, remux или промяна на оригиналните torrent bytes.
4. **qBittorrent е авторитет за torrent file mapping.** Преместването и преименуването на активни torrents са координирани през неговия API.
5. **Всички jobs са видими, устойчиви при рестарт и проследими.** Pause, resume, retry, needs review, recovery и audit trail.
6. **Физическият move local → NAS и multi-file seeding са най-важните архитектурни блокери.** Приети са предпочитани стратегии според формата на torrent; изпълнението остава блокирано до успешни технически тестове.
7. **Одобреният wireframe описва UX**, а не доказва работещ backend.

## 1. Продукт, цели и граници

### 1.1 Какво представлява ViMag Media Manager — ПРИЕТО

Постоянна self-hosted Docker услуга с уеб интерфейс и фонов процесор на задачи, която поема обработката след qBittorrent download completion.

Поддържа два режима:

- **Automatic Intake:** нов completion event → Import Job → анализ, сравнение, безопасен import, субтитри, Jellyfin и окончателна проверка на seeding; пропуснати събития се откриват чрез reconciliation.
- **Library Maintenance:** read-only обследване на съществуващата NAS библиотека и предложения за нормализация, дубликати, metadata и субтитри; файлови операции само след ясен план и необходимите одобрения.

Това не е torrent клиент, файлов мениджър за произволни пътища или replacement на Jellyfin.

### 1.2 Функции в scope на v1

- седемте екрана и седемте workflow стъпки от wireframe;
- jobs с устойчиво състояние, история, грешки и recovery;
- един torrent → един parent job → един или повече media items;
- техническа проверка чрез ffprobe/MediaInfo;
- идентификация на заглавие, година, provider ID, edition, episodes;
- quality/duplicate comparison и Bulgarian-first;
- preflight на target path, storage и seeding dependencies;
- torrent-safe преместване според валидирана стратегия;
- NFO и artwork, български субтитри и проверка на Jellyfin publication;
- първоначална поддръжка на старата библиотека в режим на безопасен план.

### 1.3 Извън първия release

- transcoding/remux и премахване на embedded audio/subtitle tracks;
- автоматично физическо изтриване на съществуващи библиотечни версии;
- публичен интернет достъп или SaaS/multi-tenant продукт;
- AI-identification като задължителна зависимост;
- Redis, RabbitMQ, PostgreSQL без доказана необходимост;
- автоматично променяне на избраната qBittorrent категория;
- operations по реалните файлове преди преминали интеграционни тестове.

**ПРИЕТО — P-03:** ViMag v1.0 **няма физическо окончателно изтриване на библиотечни версии — дори след approval**. Поддържа само обратима Quarantine + Restore; безопасният AD-16 cleanup на временни локални/staging файлове остава разрешен при задължителните проверки.

## 2. Инфраструктура и технически предпоставки

| Компонент | Контекст |
|---|---|
| Host | ViMag, Linux |
| Контейнери | Docker Compose; Traefik v3.6 |
| Вътрешна мрежа | `vimag_default` |
| Access | Tailscale, вътрешен DNS; кандидат `https://manager.vimag.app` |
| Download | qBittorrent 5.x с VueTorrent |
| Media server | Jellyfin |
| Локален download | `/mnt/storage/qbt` |
| Крайна библиотека | `/mnt/nas/Movies/Library` |
| qBittorrent mounts | `/mnt/storage/qbt` → `/downloads`; NAS library → `/library` |
| qBittorrent config | `/home/veso/docker/qbittorrent` |
| Стар hook | `/home/veso/docker/qbittorrent/scripts/jellyfin-scan.sh` |
| Възможен stack | Vue 3, FastAPI, persistent worker, SQLite, ffprobe, TMDb |
| Repository | `vesovasilev-vimag/media-manager` |
| Бъдещ Docker Hub | `vesovasilev` |

Това е **предоставен архитектурен контекст**, не е жив одит на конфигурацията.

**БЛОКЕР — read-only discovery:** преди реализация трябва да се проверят точната версия на qBittorrent API, категория → save path, Automatic Torrent Management, UID/GID и ACL, NAS mount protocol и hardlink support, свободно място, Jellyfin library types и backup/restore.

Петте top-level категории остават непроменени:

```text
/mnt/nas/Movies/Library/
├── Animations/
├── Concerts/
├── Documentaries/
├── Movies/
└── Series/
```

## 3. Отговорности на компонентите

| Система | Какво управлява | Какво не управлява |
|---|---|---|
| **qBittorrent** | download, torrent hash, category, save path, mapping, pause/resume, recheck, seeding | naming conventions за Jellyfin и TMDb |
| **ViMag Manager** | intake, jobs, identification, поддиректории, quality, file operation orchestration, metadata, subtitles, audit | независими файлови операции, които чупят активния torrent |
| **Jellyfin** | indexing, metadata и визуализация, versions, audio/subtitle availability | torrent integrity |
| **NAS** | финално съхранение | гаранция за непрекъснато наличие без health checks |

**ПРЕДЛОЖЕН container/service модел:**

```text
qBittorrent completion hook ───────┐
                                   ├──> FastAPI Intake ───> SQLite job ledger
Periodic reconciliation ───────────┘                             │
                                                                  ▼
Vue 3 dashboard <── FastAPI read/commands <──────────── Persistent Worker
                                                                  │
                        ┌─────────────────────────────────────────┤
                        ▼                   ▼                     ▼
                    qBt Web API         ffprobe / TMDb        NAS safe move
                        └──────────────────┴─────────────────────┘
                                              │
                                     NFO / Artwork / Subtitles
                                              │
                                        Jellyfin API
                                              │
                                  Final qBt seeding verification
```

API не държи HTTP заявката отворена за 100 GB копиране. Фоновият worker изпълнява подзадачите, пази journal и подава проверени състояния към интерфейса.

## 4. Категории, routing и отговорност за поддиректориите

### 4.1 Основно правило — ПРИЕТО

Потребителят винаги избира категорията при стартиране на torrent:

| qBt `category` | NAS root | Примерен media type |
|---|---|---|
| `movies` | `Movies/` | Movie |
| `series` | `Series/` | TV Show / Episode |
| `animations` | `Animations/` | Animated Movie **или** Animated Series |
| `documentaries` | `Documentaries/` | Documentary Movie **или** Documentary Series |
| `concerts` | `Concerts/` | Concert / Live / Multipart |

**Категорията и типът произведение са две различни полета.** ViMag може да идентифицира `media_type=show` при `category=animations`, без да сменя root `Animations`.

### 4.2 Конфликти — ПРЕДЛОЖЕНО

| Ситуация | Очаквано действие |
|---|---|
| `category=movies`, TMDb намира филм | генерирай destination plan в `Movies/` |
| `category=series`, torrent съдържа сезон | генерирай season/episode plan |
| `category=movies`, съдържанието силно наподобява TV season | `Needs Review`, **не сменяй** категорията |
| category е празна/непозната | `Needs Review`, няма write |
| категорията е променена в qBt след създаден план | `ReplanRequired`; старото одобрение е невалидно |
| torrent има няколко независими произведения | parent job + child mapping, без unsafe split |

**ПРИЕТО — AD-03 (Кръг 2):** вътре в двете категории използваме `Movies/` и `Series/`. **ТЕХНИЧЕСКИ GATE:** да се съпоставят тези пътища с действителните Jellyfin Movies/Shows library roots; не се разчита на Mixed library като безусловно правилно решение.

### 4.2.1 Приета вложена структура — AD-03

```text
/mnt/nas/Movies/Library/
├── Movies/               # movie items
├── Series/               # show items
├── Animations/
│   ├── Movies/           # animated movies
│   └── Series/           # animated shows, Season XX
├── Documentaries/
│   ├── Movies/           # documentary films
│   └── Series/           # documentary shows, Season XX
└── Concerts/             # Artist - Event (Year), when verified
```

Планираните нови поддиректории не са разрешение за автоматично реорганизиране на вече съществуващите файлове. Existing Library Maintenance създава отделен preview/approval plan. Задължителен е read-only преглед на конфигурацията на Jellyfin и потвърждение, че един и същ media path не се сканира през няколко библиотеки.

### 4.3 Правила на routing engine — ПРЕДЛОЖЕНО

1. Прочети category от qBittorrent Web API, не от release filename.
2. Свържи категорията с единствен валиден top-level root.
3. Идентифицирай произведението, година, edition, епизоди.
4. Генерирай canonical relative path според naming policy.
5. Валидирай `realpath` containment, collision, permissions и torrent impact.
6. Съхрани *Import Plan* с revision/fingerprint.
7. Покажи „Original → Destination“ и защо се предлага този път.
8. При review/override позволи избор **само вътре** в съответния top-level root.
9. Преди физическа операция преизчисли план fingerprint и провери за промени.
 
## 5. Naming convention — файлови и directory правила

### 5.1 Общи принципи — ПРИЕТО

- Използвай надеждно original/canonical title, release year и provider ID (ако е приложим).
- Генерирай предвидим *destination preview* **преди** физически move.
- Оригиналният torrent/release name остава записан за audit и subtitle matching.
- Няма release-group, tracker/website тагове в стандартните крайни имена.
- Не поставяй маркер `BG` само заради `bul`/`bg` language tag; нужна е надеждна верификация.
- Edition като `Theatrical`, `Extended`, `Director's Cut` се запазва и не се смесва.
- Path components се нормализират; отхвърляй reserved chars, `..`, absolute-path injection, symlink escape, case-insensitive collision и прекомерно дълги пътища.
- Subtitle filename се базира на точното име на съответната видео версия.

### 5.2 Movies — приет шаблон на организация; детайлните suffixes са за валидация

```text
Movies/
└── The Matrix (1999) [tmdbid-603]/
    ├── The Matrix (1999) [tmdbid-603] - 2160p HDR.mkv
    ├── The Matrix (1999) [tmdbid-603] - 2160p HDR.bg.srt
    ├── The Matrix (1999) [tmdbid-603] - 1080p BG.mkv
    ├── movie.nfo
    ├── poster.jpg
    └── backdrop.jpg
```

За Jellyfin multiple versions *пълният prefix* на филмовия файл трябва да съвпада с името на директорията (включително `year`/`[tmdbid-*]`) и след него да има version label. Иначе Jellyfin може да създаде отделни заглавия.

**ПРИЕТО (AD-04c):** `BG` се изписва във видеоимето единствено за проверен `BG_VERIFIED` аудио поток. **ТЕХНИЧЕСКА ВАЛИДАЦИЯ (G-02/G-03):** точното изписване на HDR/DV и audio характеристики; grouping на версии и edition suffixes; collision, backward compatibility и torrent-aware rename.

### 5.3 Series — приет default формат; разширените edge cases за валидация

```text
Series/
└── Example Show (2021) [tmdbid-12345]/
    ├── tvshow.nfo
    ├── poster.jpg
    └── Season 01/
        ├── Example Show S01E01 - 1080p.mkv
        ├── Example Show S01E01 - 1080p.bg.srt
        ├── Example Show S01E02 - 1080p.mkv
        └── Example Show S01E02 - 1080p.bg.srt
```

Поддържай `S01E01-E02`, `Season 00` (Specials), multi-part епизоди и сезонни torrents. Разделянето на child items е логическо; физическо преименуване се извършва само чрез валидна torrent-aware стратегия.

### 5.4 Animations / Documentaries / Concerts — ПРИЕТО (Кръг 2)

**Animations** — физически root `Animations/` с две задължителни поддиректории:

```text
Animations/
├── Movies/
│   └── Cars (2006) [tmdbid-920]/
│       └── Cars (2006) [tmdbid-920] - 1080p BG.mkv
└── Series/
    └── Example Animated Show (2018) [tmdbid-ID]/
        └── Season 01/
            └── Example Animated Show S01E01 - 1080p.mkv
```

**Documentaries** — същият структурен модел, отделен от Animations и другите top-level категории:

```text
Documentaries/
├── Movies/
│   └── Documentary Title (2020) [tmdbid-ID]/
│       └── Documentary Title (2020) [tmdbid-ID] - 1080p.mkv
└── Series/
    └── Documentary Show (2022) [tmdbid-ID]/
        └── Season 01/
            └── Documentary Show S01E01 - 1080p.mkv
```

`[tmdbid-ID]` в горните примери е **само placeholder**, не реално присвоен идентификатор. При липсващ надежден ID не се добавя синтетичен provider ID.

**Concerts** — основна директория на произведението **`Artist - Event (Year)`**, само когато артист/събитие/година са надеждно установени; при липсваща година или двусмислен артист — `NeedsReview` и предложение за корекция преди publish. Използват се същите защитни правила за имена, sidecars и multipart releases:

```text
Concerts/
└── Example Artist - Example Live Event (2020)/
    ├── Example Artist - Example Live Event (2020).mkv
    ├── movie.nfo                   # само ако е приложимо
    └── poster.jpg
```

### 5.4.1 Точни правила за Movie editions и multiple versions — ПРИЕТО, с Jellyfin compatibility gate

- Movie editions са **в една директория** на едно произведение; suffix-ът включва edition marker, различен от останалите version атрибути.
- При множество версии **пълният filename prefix трябва да съвпада буквално** с името на movie folder, включително `(Year)` и `[tmdbid-ID]`, когато присъстват.
- Пример: `The Matrix (1999) [tmdbid-603] - 2160p HDR - Extended.mkv` и `The Matrix (1999) [tmdbid-603] - 1080p BG - Theatrical.mkv`.
- ViMag пази `edition_key` самостоятелно от `quality_variant`, `language_evidence` и `physical_file`. При две editions **не** се предлага изтриване като обикновен дубликат.
- Jellyfin може да представи тези файлове като **multiple versions**, без да има същия семантичен модел за editions като ViMag; verify real server version grouping и selector names преди внедряване.

### 5.4.2 Movie/Series naming policy — ПРИЕТО

| Елемент | Приет default | Техническа граница |
|---|---|---|
| Original title | канонично provider заглавие; ръчна корекция при нужда | не преименувай активно сеедван файл без qBt-aware plan |
| Movie directory | `Title (Year) [tmdbid-ID]/` при наличен ID | provider ID е optional, никога измислен |
| Movie file | `<точен movie folder name> - <quality> [BG] [Edition].mkv` | Jellyfin multi-version prefix match е задължителен |
| Series directory | `Series Title (Year) [tmdbid-ID]/Season 01/` | Season 00 / specials / packs са отделни случаи |
| Episode file | `Series Title S01E01 - 1080p.mkv` | multi-episode/part и episode multiple versions се проверяват |
| BG marker | `BG` **само** при `BG_VERIFIED` | `bul`/`bg` stream tag не достига |
| Concert directory | `Artist - Event (Year)/` | без измислени artist, year, provider ID |
| Subtitles | `<video-file-stem>.bg.srt` | съобразяване с video edition/release |

**Технически отворени въпроси, които не променят избора A:** exact quality label syntax, Unicode normalization, destination collision handling, quality label ordering и fallback за концерти без година.

### 5.5 Sidecars и ownership

| Съдържание | Предложено име/правило |
|---|---|
| Movie metadata | `movie.nfo` (съобразено с Jellyfin) |
| Show metadata | `tvshow.nfo` |
| Episode metadata | `<episode-file-stem>.nfo`, когато се използва |
| Artwork | `poster.jpg`, `backdrop.jpg` |
| BG subtitles | `<video-file-stem>.bg.srt` |
| Original subtitle files | запазват се до независима проверка и одобрен cleanup |
| Extras / trailers | класификация, без автоматично изтриване |

**ПРИЕТО — P-02/AD-19:** ViMag автоматично обновява **само ViMag-owned** NFO/artwork с непроменен content hash спрямо последното свое записване. Ако файлът е непознат, ръчно редактиран, изтрит/подменен, не може да бъде идентифициран сигурно или е променен от Jellyfin/NFO saver, **автоматичното презаписване се блокира** и системата показва diff/review. Локалният Jellyfin NFO има приоритет пред remote provider metadata. Ownership се доказва от durable manifest/DB evidence и hash, а не само от име на файл или embedded text. Изричното одобрение е за точно съдържание/ревизия; без безусловно override.

## 6. Import Job — задължителен седемстъпков lifecycle

| № | Стъпка | Основна задача | Exit condition |
|---|---|---|---|
| **01** | Download completed | Intake на qBt event, torrent hash, category, file inventory | durable, deduplicated job |
| **02** | Identify and inspect | ffprobe/MediaInfo + metadata candidate matches | confirmed match или `NeedsReview` |
| **03** | Compare with library | качества, editions, BG audio, duplicates, seeding dependencies | обосновано решение/approval |
| **04** | Organize and enrich | destination plan, safe NAS move, integrity/mapping, early seeding, NFO/artwork | безопасна NAS версия и seeding recovery |
| **05** | Find Bulgarian subtitles | subtitle identification, matching, provider/review/sync | matched / unavailable / review status |
| **06** | Publish to Jellyfin | refresh request + независима проверка на разпознаването | `PublishedVerified`, не само HTTP 200 |
| **07** | Verify qBittorrent seeding | final path, pieces, availability, config/pause state | safe `Completed` |

**Важна зависимост:** seeding трябва да се възстанови в Step 04 възможно най-рано след cutover; Step 07 прави *окончателното* потвърждение.

### 6.1 Intake и пропуснати събития — ПРЕДЛОЖЕНО

qBittorrent completion hook подава стабилен идентификатор на torrent. Backend извлича останалите данни от qBittorrent Web API, а не вярва сляпо на името/пътя от hook-а.

- `UNIQUE(client_id, torrent_hash, job_kind)` — за активния lifecycle; поведението при remove/re-add се описва отделно.
- Повторно completion event **не** създава втори move.
- Periodic reconciliation открива completed torrents, които не са получили job.
- При външна промяна на torrent file list, category или content path се създава нов plan revision; старите одобрения са невалидни.
- Parent Job обхваща цял torrent; един season pack може да има десетки child media items.
- Non-media files, attachments, multi-part releases и едновременно няколко произведения не се изхвърлят без класификация.

### 6.2 Предложени състояния

```text
Queued → Inspecting → Comparing → AwaitingApproval? → Planned
       → Preparing → Moving → Verifying → Reconnecting → Enriching
       → Subtitles → Publishing → FinalSeedingCheck → Completed
```

Допустими странични/възстановими състояния: `Paused`, `NeedsReview`, `BlockedExternalDependency`, `FailedRecoverable`, `RecoveryRequired`, `ReplanRequired`, `PublishPending`, `Cancelled`.

**ПРИЕТО — AD-18: отделни крайни и неконечни резултати:**

| Job state | Terminal? | Условия за използване |
|---|---|---|
| `Completed` | Да | NAS data/integrity, qBt mapping/seeding-capable и Jellyfin identity/versions **verified**; изискваните subtitle проверки са завършени без предупреждения. |
| `CompletedWithWarnings` | Да, с видими предупреждения | Същите критични проверки са verified, но BG subtitle е `Unavailable` или има изрично нефатално отклонение, което не е записано като „синхронизиран“. Не се извършва рисковано subtitle write. |
| `PublishPending` | **Не** | Jellyfin refresh е заявен, но scan или медийната верификация не е завършена; отделен retry, не успех. |
| `RecoveryRequired` | **Не** | Неизвестна/опасна файлово-торентна консистентност, failed piece recheck или риск за данните. |
| `NeedsReview` | **Не** | Metadata match, quality choice, subtitle selection или approval блокират следващо небезопасно действие. |

За **файловата операция** се пази отделно: `Preparing`, `Copying`, `CopyComplete`, `VerifyingIntegrity`, `UpdatingTorrent`, `Rechecking`, `SeedingVerified`, `CleanupEligible`, `Finished`.

**Parent/Child aggregation:** parent не става terminal-success при критичен незавършен Child; нефатално subtitle предупреждение на Child се издига в parent `CompletedWithWarnings` само ако всички критични проверки са успешни.

Принцип: `Requested` ≠ `Running` ≠ `Verified`. Натискане на Retry/Pause или HTTP 200 не доказва, че промяната е физически приключила.

### 6.3 Parent job / Child Media Job/Item — ПРИЕТО (AD-17)

```text
Job: qBt torrent hash <redacted>
├── File A: Example Show S01E01.mkv → Child Media Item E01
├── File B: Example Show S01E02.mkv → Child Media Item E02
├── File C: Example Show S01E03.mkv → Child Media Item E03
├── subtitle/attachments → Sidecars
└── Torrent-level cutover + seeding verification
```

Дъщерните media items имат индивидуално subtitle/metadata/Jellyfin състояние, но промените на файловата структура се координират **на torrent ниво**.

**Mixed independent items:** Parent Job остава keyed по torrent hash. Всеки Child има собствен content identity, category compatibility, provider match, approved destination preview, subtitle и Jellyfin publish state. Copy/move, cleanup и qBittorrent recheck са **еднократни torrent-level операции** (не отделна физическа миграция за всеки Child). Parent не е `Completed`, ако има опасен/unresolved Child. При mixed categories не се извършва тихо прехвърляне в друг NAS root: `NeedsReview` с визуализиран конфликт и предложение за корекция на плана.


## 7. Identify & Inspect — метаданни и технически доказателства

### 7.1 Медийни характеристики — ПРИЕТО

ffprobe/MediaInfo определят container, runtime, resolution, codec/profile, video bitrate, HDR/DV, FPS, аудиопотоци/езици/channels, embedded/external subtitles, filesize, multipart/multi-file structure.

**Важно:** успешен `ffprobe` върху headers не доказва пълна media integrity. Проверка на копираните bytes и qBittorrent recheck са отделни механизми. Full decode scan може да е опционален и resource-heavy.

### 7.2 Title identification — ПРИЕТО (AD-14), алгоритъм за калибрация

**Политика A:** автоматично се потвърждава идентификация само при **висока обяснима увереност**; в останалите случаи job спира в `NeedsReview`, без финален destination move. Входните доказателства включват parsed release name, canonical title/year, media type, TMDb/provider ID, runtime, edition и season/episode mapping.

| Сигнал | Допустимо значение | Ограничение |
|---|---|---|
| Потвърден provider ID + съвместим media type | Силен положителен сигнал | Сам по себе си не позволява изтриване на друга версия. |
| Title + year similarity | Candidate ranking | Не е достатъчен за сигурна идентичност при омонимни заглавия. |
| Runtime + edition compatibility | Допълнителна подкрепа | Director's Cut може законно да има друга продължителност. |
| Season/episode mapping | Задължителен за show/season packs | Неразпознат епизод/двусмислен multi-episode → review. |
| qBt category ↔ media type | Ограничение на destination root | Конфликт не сменя category автоматично. |

**Ръчното потвърждение** записва избрания canonical ID или основателен `NO_PROVIDER_ID`, actor, timestamp, evidence и plan revision. Provider fallback за концерти не означава изкуствено създаден TMDb ID.

**Технически остават за калибрация:** числов confidence threshold, trusted-source precedence, multilingual aliases, други providers и дублиращи се идентичности. Липсата на числов праг в draft не означава, че всички matches могат да се одобрят автоматично.

## 8. BG audio и оценка на качество

### 8.1 Bulgarian audio evidence — ПРИЕТО (AD-05)

| Състояние | Значение | Решение |
|---|---|---|
| `BG_VERIFIED` | българско аудио с **ръчно потвърждение** или предварително надеждно доказателство, обвързано с конкретния stream/file | запазване с приоритет; `BG` filename marker само при това състояние |
| `BG_TAGGED` | поточен language tag `bul`/`bg` | кандидат, но **не verified** |
| `BG_SUSPECTED` | release/stream title намеква за BG audio | needs review |
| `AUDIO_UNKNOWN` | езикът не е достатъчно установен | не предприемай risky cleanup или замяна |
| `NO_BG` | няма установено българско аудио според наличното evidence | участвa в compare; не доказва абсолютно отсъствие, ако scan е непълен |

**Evidence record** (предложение за реализация на приетата политика): source (`human-confirmed`, `trusted-prior-verification`), actor/time или source reference, original media fingerprint, stream index/identity, audit note и evidence version. `ffprobe` е средство за инвентаризация на потоците, **не** езиково прослушване. Съхраняването на потвърждение след преместване не е проблем, ако stream identity е непроменена; при съмнение за променен payload/stream или грешен предходен match се иска re-verification.

**UI:** ясно разделяне на `BG verified`, `BG tagged`, `BG suspected`, `Unknown` и `No BG`; manual Verify/Revoke с audit. Предишният release name не е самостоятелно evidence. Само `BG_VERIFIED` задейства `BG` във filename и Bulgarian-first привилегия.

### 8.2 Многофакторна quality evaluation — ПРИЕТО (AD-06)

Quality Engine оценява сравними **same-title, same-edition** версии по набор от сигнали: stream/container integrity, video source/encode/profile, effective bitrate **в контекст**, resolution, HDR/DV, audio channels/codec, BG evidence, runtime, subtitle quality и torrent dependencies. Изчислението трябва да е **обяснимо**: видими фактори, ограничения и човешки reason codes; no black-box `winner` без доказателство.

**Принципи:**

- `resolution` и `file size` не са достатъчни самостоятелно; re-encode с по-голям bitrate не гарантира по-добра картина;
- `edition` mismatch не влиза в стандартно сравнение „по-добър дубликат“;
- при сходно качество `BG_VERIFIED` остава preferred;
- при съществено по-високо качество на non-BG версия **Keep Both**, не мълчалива замяна;
- при два `BG_VERIFIED` файла се сравнява действителното качество, а старата версия не се изтрива автоматично;
- при `AUDIO_UNKNOWN`, противоречиви сигнали или липса на интегритет → `NeedsReview`;
- препоръка се различава от разрешение за quarantine/delete.

| Съществуващо съдържание | Ново съдържание | Разрешена препоръка |
|---|---|---|
| 1080p BG verified | 2160p EN, доказано съществено по-добра картина | **Keep Both** |
| 1080p BG verified | EN със сравнимо качество | **Keep BG preferred** |
| 720p BG verified | 1080p BG verified и реално по-добра | **Prefer better BG**, старата остава до одобрен lifecycle |
| Theatrical | Extended/Director's Cut | **Different editions**, no duplicate discard |
| Unknown audio | apparent superior version | **Manual review**, без автоматичен cleanup |
| Идентични bytes при няколко torrents | един content asset | **Dependency-aware**, no destructive action |

**Калибрация, не нов продуктов въпрос:** quality weights, meaningful-improvement thresholds, confidence cutoffs, bitrate normalization и HDR/DV treatment трябва да бъдат валидирани с реални sample files (особено BG версии), а не измислени предварително. Документът не обещава автоматично доказване на perceptual quality само чрез ffprobe.

## 9. Duplicate detection / quarantine — ПРИЕТО (AD-07)

**Класове:** byte-identical, same title+edition, quality variants, different editions, alternate encoding, multipart, ambiguous metadata и един physical content asset, използван от няколко torrents. Identity grouping трябва да пази отделно произведение, edition, quality variant, file и torrent dependencies.

**Приета политика A:** Quality Engine показва `Keep Preferred`, `Keep Both`, `Quarantine Proposal`, `Skip`, `Needs Review` и обоснована препоръка. **Quarantine се изпълнява само след explicit approval** на актуален plan revision и преминати dependency/permissions/integrity checks. **Не се извършва автоматично физическо изтриване.**

### 9.1 Quarantine workflow

1. Предложение за inferior version с reasons, evidence, source path, bytes, editions и torrent dependencies.
2. Validation, че **не** е активен seed target, неизяснен hardlink dependency, Jellyfin unique edition или shared content за друг torrent.
3. Explicit approval, обвързано с plan fingerprint; промяна на asset/paths/dependencies прави одобрението невалидно.
4. Действие, обхванато от recovery journal и разрешени quarantine roots; manifest с original identity и restore plan.
5. Integrity check, възможност за restore и Jellyfin refresh след успешно преместване.
6. Без automatic delete/retention purge във v1.0, освен при бъдещо изрично одобрено разширение.

**Важно:** преместването в quarantine не трябва да изчисти байтове, към които qBittorrent все още сочи. Ако hardlink и torrent-owned файл споделят inode, quarantine на един directory entry не доказва, че другият е без зависимост: manifest и link-count/paths трябва да се анализират. Услугата **никога не извиква `deleteFiles=true`** в нормалния import/maintenance workflow.

### 9.2 Delete boundary — ПРИЕТО (P-03)

**Окончателното физическо изтриване на библиотечни версии е ИЗВЪН v1.0** — независимо дали потребителят е администратор, има approval или съществува quarantine retention период. Не се предлага `Delete after approval` в production UI/API; налична подобна demo контрола от одобрения wireframe остава **неактивна/недостъпна** до отделно одобрен бъдещ scope. Не се извиква qBittorrent `deleteFiles=true` и не се изтрива torrent entry като скрит страничен ефект.

**Разрешени** са: изпращане към обратима quarantine след explicit approval и преминати dependency checks; restore към проверена дестинация; AD-16 автоматично cleanup само на верифицирани неизползвани **временни локални/staging** файлове след успешен cutover. Library/quarantine медии и ръчно поддържани sidecars никога не се третират като staging.

### 9.3 Exact duplicate и shared content

Размер, duration, stream summary и частични fingerprints помагат за кандидати; full hash/piece validation се използва при риск. При byte-identical duplicates се показват всички торент зависимости, но физическото отстраняване на shared content остава блокирано без изричен безопасен план. Quarantine и cleanup следват различни approval policies: одобреното автоматично cleanup от Кръг 1 се отнася **само до излишен staging/local source**, не до версии от библиотеката.

## 10. Cross-filesystem move и запазване на seeding — критичен модул

Локалният `/mnt/storage/qbt` и NAS `/mnt/nas/Movies/Library` са **различни физически storage ресурси**. Файлово `rename(2)` не е атомарно през две файлови системи. Не можем да обещаем ACID transaction заедно между qBittorrent, NAS и SQLite; можем да изградим **възстановима state machine**, която пази доказателства за всеки етап.

### 10.1 Задължителни инварианти — ПРИЕТО

1. Преди move се записва текущият qBt snapshot: hash, category, save_path, content_path, file list, relative names, file priorities, total bytes, progress, `auto_tmm`, seeding/pause state.
2. Destination plan и import policy revision се фиксират преди write.
3. NAS availability, mount identity, permissions, free space и collisions се проверяват непосредствено преди старта.
4. Не могат да работят два паралелни physical move jobs за същия torrent/target.
5. Оригиналните bytes не се променят (няма remux/transcode/edit на seed-ван файл).
6. qBittorrent е източникът на истина за премествания и преименувания на активен torrent.
7. Файлът **не се счита за преместен**, докато не са проверени physical presence, integrity и torrent mapping.
8. При NAS outage/API outage не се изтрива source и не се обявява success.
9. Worker restart/Retry започва с **reconciliation на текущата реалност**, не с повтаряне на предишната команда.
10. Seeding се възстановява **възможно най-рано** след безопасен cutover, преди NFO/artwork/subtitle lookup.
11. Не изтривай втори (inferior) библиотечен файл само защото друг е по-качествен.
12. Audit за всяка промяна: actor/job/plan ID/command/evidence/time/result.

### 10.2 Как се доказва, че seeding работи

**Не изискваме upload speed > 0.** Възможно е да няма peers, а състоянието `stalledUP` да е нормално. Доказваме способност за seeding с:

- валиден `save_path` и `content_path` в qBittorrent;
- липса на `missingFiles` след приключване на relocation;
- успешно проверена torrent completion/pieces (recheck при приложимия сценарий);
- torrent configuration и user-initiated pause/queue policy не са неочаквано променени;
- files са достъпни от NAS през същия namespace, който вижда qBittorrent;
- няма неочаквана промяна в `auto_tmm`, category path и tracker/seeding policy.

Контролирана кратка пауза за move/recheck може да е необходима. **ПРИЕТО:** очаква се безопасно възстановяване и бъдеща възможност за seeding, а не обещание за 100% непрекъснат upload през самата операция.

### 10.3 Приети предпочитани стратегии — ТЕХНИЧЕСКИ УСЛОВНО / БЛОКЕР НА ТЕСТОВЕТЕ AD-01

| Стратегия | Предназначение | Плюс | Съществен риск |
|---|---|---|---|
| **A. qBittorrent-managed move** | прост torrent, цялото съдържание остава в съвместима структура | qBt контролира relocation/mapping | операцията е async, Auto TMM може да влияе, rename sequence трябва да се тества |
| **B. Staged copy + qBt cutover** | нужно е управляемо copy progress/checkpointing | може да се инспектира копието преди cutover | `setLocation` не е доказана zero-copy „връзка към вече копиран файл“; риск от нов move/overwrite |
| **C. NAS canonical torrent tree + library hardlinks** | season packs и различни torrent/Jellyfin дървета | запазва seeding tree, използва малко място при hardlink support | hardlink само на **същата NAS файлова система**, NAS protocol/permissions/cross mount |
| **D. NAS canonical tree + второ library copy** | fallback при невъзможни hardlinks | отделно torrent и library дърво | двойно NAS пространство/по-сложен cleanup |

**Приети за предпочитане:** A за прости torrents, C за multi-file/season packs. B остава техническа алтернатива за допълнителна оценка; D е само възможен fallback, който изисква отделно продуктово одобрение. Нито една не може да се изпълнява върху реална библиотека, преди да бъде доказана с тестови torrents и проверка на mount/inode mapping.

### 10.4 Multi-file season pack — предпочитана NAS torrent tree + hardlinks стратегия (условна)

```text
Local:
  /mnt/storage/qbt/Example.Show.S01/
    ep01.mkv
    ep02.mkv

NAS torrent tree (qBt сеедва от тази структура):
  /mnt/nas/.../torrent-data/<torrent-hash>/
    ep01.mkv
    ep02.mkv

NAS Jellyfin library view:
  /mnt/nas/Movies/Library/Series/Example Show (2020) [tmdbid-XXXX]/
    Season 01/
      Example Show S01E01.mkv  → hardlink към NAS torrent tree, ако се поддържа
      Example Show S01E02.mkv  → hardlink към NAS torrent tree, ако се поддържа
```

Това **не** означава, че вече сме одобрили нова NAS директория `torrent-data`: exact path, видимост за qBt и mount boundary са част от техническото валидиране AD-01/08. Ако NAS не поддържа hardlink или Jellyfin не може да ги индексира правилно, **Job спира за review** и се предлага отделен fallback; не се включва автоматично второ копие.

**Важно:** Hardlink е второ име към същите bytes/inode, а не независим файл. Всяка редакция на media bytes се отразява и на двете имена — затова v1 не модифицира originals. Hardlinks **не работят** между локалния download диск и NAS.

### 10.5 qBittorrent API и Automatic Torrent Management — ПОЛИТИКА ПРИЕТА / ТЕХНИЧЕСКИ БЛОКЕР AD-02

Нужни API функции (документирани от qBittorrent):

| Операция | API role |
|---|---|
| `torrents/info`, `torrents/files`, `torrents/properties` | действителен torrent snapshot |
| `torrents/setLocation` | заявяване на relocation |
| `torrents/renameFile`, `torrents/renameFolder` | контролирана промяна в torrent file mapping |
| `torrents/recheck` | проверка на torrent pieces |
| `torrents/pause` / `resume` (или актуалните equivalents във версия 5.x) | кратка контролирана пауза |
| `torrents/setAutoManagement` | управление на Automatic Torrent Management, само след стратегия |

Критични правила:

- `setLocation` връща отговор за заявката, но **не доказва, че файловото преместване е приключило**.
- qBt category-specific save path и automatic management могат да предизвикат допълнителна relocation. Не е допустимо ViMag и qBt да си „местят файловете един на друг“.
- API поведението и промените в `auto_tmm` трябва да се проверят на **действително инсталираната 5.x build**.
- qBt `renameFile/renameFolder` не се изпълняват без актуален file list и path-collision checks.
- В нормалния Import Workflow не извикваме `deleteFiles=true`.
- Всяка промяна на qBt setting се journal-ва за възстановяване на предишното поведение.

### 10.6 Preflight и Import Plan — ПРЕДЛОЖЕНО

UI и backend създават versioned план:

```yaml
job_id: "demo-job-123"
torrent_hash: "<redacted>"
category: "movies"
media_identity: "tmdb:603"
source_root: "/mnt/storage/qbt"
destination_root: "/mnt/nas/Movies/Library/Movies"
edition: "Theatrical"
action: "ADD_VERSION"
seeding_strategy: "NOT_SELECTED_YET"
plan_revision: 1
approval_required: true
```

*Това е пример за полета, не production schema, не реален job.*

Preflight:

- [ ] torrent snapshot съвпада с plan fingerprint;
- [ ] qBt category е една от одобрените и има route;
- [ ] media identity, edition и duplicate decision са потвърдени;
- [ ] source и destination paths са в разрешените roots;
- [ ] NAS mount identity и permissions са правилни;
- [ ] има достатъчно свободно място за временни копия и крайната стратегия;
- [ ] няма collision/unsafe overwrite или неизвестен torrent dependency;
- [ ] валидирани са `auto_tmm` и path relocation implications;
- [ ] има техническа възможност за rollback;
- [ ] plan approval е актуално, ако е необходимо.

**Промяна на media match, category, file list, destination или quality policy обезсилва одобрението.**

### 10.7 Операционен journal / безопасен cutover — ПРЕДЛОЖЕНО

```text
PREPARED            → план и journal записани, ресурсите заключени
COPYING/QBT_MOVING  → transfer progress / observation на real state
DESTINATION_PRESENT → файловете са видими на NAS
DATA_VERIFIED       → size/hash/piece integrity според стратегията
QBT_MAPPING_UPDATED → qBt вижда новия file tree
QBT_RECHECKED       → torrent integrity потвърдена
SEEDING_CAPABLE     → torrent може да seed-ва или е върнат в умишлено paused state
CLEANUP_ELIGIBLE    → само след допълнителната cleanup policy
FINAL_VERIFIED      → след Jellyfin и final seeding check
```

Няма глобална ACID транзакция през различни файлови системи и външни API. Използваме **persisted state, reconcile, retry и compensation/rollback**, а не презаписване отначало.

**ПРИЕТО — AD-16:** след потвърден безопасен cutover ViMag може автоматично да премахва **само доказано ненужни локални download/staging копия**. Операцията изисква journal, сверяване на qBt active dependencies, inode/identity verification, integrity и доказателство, че source не е действащото seed copy. Съществуващите библиотечни версии и torrent entries **не се изтриват автоматично**. При неясен ownership или неизвестно състояние cleanup остава блокиран.

### 10.8 Recovery матрица

| Проблем | Състояние в job | Безопасно поведение |
|---|---|---|
| NAS отпада по време на copy | `BlockedExternalDependency` | запази source и journal; проверка след reconnect |
| Worker crash между copy и DB update | `Reconciling` | провери реалните файлове; без blind retry |
| `setLocation` е accepted, move още тече | `Moving` | наблюдение, никакъв преждевременен success |
| Recheck показва липсващи/повредени pieces | `RecoveryRequired` | блокирай cleanup, запази source |
| Destination вече съществува | `Collision/NeedsReview` | не overwrite-вай |
| Category се сменя преди move | `ReplanRequired` | генерирай нов план и approval |
| Няма subtitle provider | `SubtitleUnavailable` | изрично състояние, не загуба на media |
| Jellyfin е приел refresh, но item липсва | `PublishPending` | verify/retry, не `PublishedVerified` |
| Старият файл се използва от активен torrent | `DependencyBlocked` | блокирай quarantine/delete |
| Torrent е бил умишлено спрян от потребителя | `PausedPolicyPreserved` | не го resume-вай неволно |

### 10.9 Какво доказва „seeding healthy“

Не е задължително upload speed да е положителна — peer-ове може да липсват. UI трябва да показва отделно:

- `Torrent data verified`: файловете са валидни;
- `qBittorrent mapping verified`: torrent сочи правилното NAS съдържание;
- `Seeding capable`: може да seed-ва при подходящи peers и policy;
- `Currently uploading`: има реален upload в този момент;
- `Intentional pause/ratio limit`: qBt е спрян по оригинална политика;
- `Missing files / recheck failed`: проблем, който блокира успеха.

**Прието поведение:** кратко контролирано прекъсване за релокация/recheck може да се наложи. Не обещаваме физически невъзможна „нула секунди прекъсване“, а безопасно възстановяване на seeding.


## 11. Subtitle Manager — български субтитри — ПРИЕТО (AD-09)

### 11.1 Приоритет — ПРИЕТО

1. Съществуващи валидни BG subtitles, свързани с правилната версия.
2. Embedded Bulgarian subtitle streams.
3. External subtitles, съвместими с exact edition/release.
4. Download от конфигуриран subtitle provider — само ако provider е легален/достъпен и има валиден access.
5. **Предложена** safe synchronization, когато е възможна.
6. Manual review при нееднозначност, mismatch или невъзможност да се докаже timing.

Обработват се release name, provider identity, edition, runtime, FPS, стартов offset, drift, cue timing, encoding, subtitle language/flags и format. `.bg.srt` и content filename сами по себе си не гарантират правилен timing.

### 11.2 Състояния и действия

| Status | Значение | Действие/последствие |
|---|---|---|
| `CandidateFound` | provider/embedded/external кандидат е открит | inspect/match; не attach автоматично |
| `Matched` | кандидатът съответства на identity/edition/release с достатъчно evidence | може да се предложи за ползване след safety checks |
| `Synchronized` | проверено subtitle timing спрямо правилния видеофайл | attach/publish и audit |
| `Mismatch` | доказан timing/edition проблем | sync proposal или manual review; не silent replace |
| `Unavailable` | няма достатъчно надежден кандидат | explicit warning; допуска `CompletedWithWarnings` при успех на NAS/Jellyfin/seeding |
| `NeedsReview` | изборът/синхронизацията не са надеждно доказани | manual selection/approval; ако е безопасно да се пропусне subtitle, може `Unavailable` с видимо предупреждение, без risky write |

**Приета политика A:** system предлага търсене и синхронизация; **използване само след проверка**. Тази политика не предполага, че FPS/duration математически доказва всеки subtitle cue. При несигурен резултат потребителят получава A/B preview/manual decision. Оригиналите остават запазени и не се подменят тихомълком.

**Оставащ технически/интеграционен gate:** кои provider adapters са разрешени, rate limits, authentication, fair-use/лицензни условия, Bazarr integration feasibility, confidence/timing validation и fallback на provider outage. Достъпен provider не е prerequisite за безопасно **медийно преместване**, ако `Unavailable` е явно отчетено.

## 12. Jellyfin publication, metadata и versions

След като NAS content и qBittorrent mapping са безопасни:

1. изпрати Jellyfin library refresh request;
2. изчакай реалното обработване на scan-а;
3. провери, че очакваното произведение се появява в правилната библиотека;
4. провери идентификация, year, metadata ID, NFO/artwork и edition;
5. провери multiple versions, BG audio streams и Bulgarian subtitles;
6. ако има проблем — изрично `PublishPending`, `NeedsReview` или `FailedRecoverable`, а не скрит success.

**ПРИЕТО:** `RefreshRequested` ≠ `RefreshCompleted` ≠ `PublishedVerified`. **AD-18:** при неизпълнено Jellyfin verification job остава `PublishPending` (некрайно), не `CompletedWithWarnings`. При потвърдено Jellyfin и qBt seeding, но `SubtitleUnavailable`, резултатът може да е `CompletedWithWarnings` с ясно обяснение.

**ПРИЕТО (AD-03/04):** `Animations/Movies`, `Animations/Series`, `Documentaries/Movies` и `Documentaries/Series` са целевите поддиректории. За тях трябва да се конфигурират надеждни Jellyfin **Movies** и **Shows** library paths (проверка на конкретната инсталация; един и същ файл не бива да се индексира повторно). Jellyfin mixed libraries не са предпочитаната основна стратегия за разпознаване на тези две групи. Movie editions се съхраняват заедно на NAS, но ViMag различава editions от quality versions независимо от това как Jellyfin ги представя. Тестовете за version grouping са задължителни.

### 12.1 NFO precedence и ownership — ПРИЕТО (P-02/AD-19)

Jellyfin дава приоритет на локалния NFO над remote metadata. ViMag v1.0 прилага **optimistic concurrency + durable ownership evidence** за своите sidecars:

1. При първоначално генериране запиши `managed_by=vimag`, `path`, `media_asset_id`, provider/metadata policy revision, `written_at`, fingerprint/content hash, оригиналната последна предишна стойност при одобрена замяна и audit event в DB/manifest.
2. **Auto-update** е допустим само ако текущият файл съществува на очаквания път, текущият content hash съвпада с последния **ViMag-written** hash и не е отбелязан като manually maintained/locked. Използвай atomic replace там, където е безопасно, с journaling, rollback възможност и повторна проверка преди commit.
3. За **неизвестен, чужд, ръчно променен, locked или конфликтно изменен файл** — не презаписвай; запази съдържанието, покажи разликите и изискай explicit approval за конкретния файл и ревизия на предложението.
4. Ако Jellyfin NFO saver е активен и модифицира същия файл, промяната се третира като **външна**. Изискай проверка на конфигурацията/ownership и избягвай write loop между двете системи; не допускай concurrent overwrite.
5. При липсващ/невалиден remote metadata provider текущият валиден NFO не се нулира. Artwork следва същата ownership политика.
6. При неуспешна sidecar операция критичният файл не се маркира за успешен update; запази audit и достъпно старо съдържание.

**Реализационна калибрация, не нов продуктов въпрос:** manifest schema, hash algorithm, backup retention, atomic-write behavior върху NAS и точната Jellyfin NFO saver configuration се проверяват в G-02/G-03/G-04.

## 13. Library Maintenance — безопасен анализ на библиотеката

**ПРИЕТО:** режимът започва с read-only inventory, а не с mass-move.

Обхват на сканирането:
- петте top-level директории;
- канонично заглавие, година и provider IDs;
- потоци, качество, BG audio verification state, subtitles;
- duplicate/edition clusters;
- неправилна категория и/или именуване;
- липсващи NFO/artwork;
- зависимости от живи qBittorrent torrents.

### 13.1 Plan → Approval → Execution

```text
Read-only scan
  → Group issues (naming, duplicates, metadata, subtitles, wrong category)
  → Proposed before/after plan
  → Space and seeding dependency check
  → Explicit review/approval, where required
  → Safe job with journal and rollback eligibility
  → Independent verification
```

**ПРЕДЛОЖЕНО:** първата версия ограничава размер на batch операции и не допуска едновременно неконтролирани масови премествания. Визуализира се „колко файлове/bytes ще бъдат засегнати“ и „какво няма да се променя“.

### 13.2 Предишен инвентар

В предишния етап е посочен `all-movies.csv`: приблизително **562 видеофайла / 3.14 TB**, около 381 Movies, 99 Animations и 82 Documentaries; числата са предварителни и **не са проверени спрямо актуалния CSV** в този преглед. Series и Concerts не са били включени. Нов read-only export е задължителен преди реални Library Maintenance операции.

## 14. Persistence model — SQLite и audit

**ПРЕДЛОЖЕНО:** SQLite на локален persistent volume (не върху недостъпен понякога NAS mount), WAL mode, миграции и регулярни консистентни backup-и. Нужни са ограничения/уникалност и Foreign Keys.

| Entity | Примерни данни | Отговорност |
|---|---|---|
| `jobs` | id, client, hash, kind, status, current_step, created/updated | parent lifecycle |
| `job_media_items` | job_id, media_type, provider, edition, S/E | multi-item imports |
| `torrent_snapshots` | hash, category, paths, files, priorities, auto_tmm, original state | recovery |
| `media_inspections` | file fingerprint, ffprobe digest, streams, probe errors | evidence |
| `identity_matches` | candidates, provider ID, selected, confidence, reviewer | matching |
| `library_assets` | canonical identity, edition, path, quality, sidecars | inventory |
| `quality_decisions` | candidates, evidence, rule revision, recommended action | explainability |
| `import_plans` | revision, fingerprint, destination, strategy, required approvals | frozen plan |
| `file_operations` | source, dest, bytes, checkpoint, verified state | copy/move journal |
| `torrent_dependencies` | asset ID, torrent hash, active dependency state | safe cleanup |
| `approvals` | plan revision/hash, user, action, time | permissions |
| `subtitle_candidates` | language, provider, timing, confidence, status | subtitle workflow |
| `jellyfin_verifications` | item, refresh requested, verified item IDs, status | publish |
| `audit_events` | job/action/actor/time/result/before/after | durable audit |
| `service_settings` | category mappings, rules, policy revisions, secret references | config |

Ключови ограничения:
- `torrent_hash` е основна връзка към qBittorrent, но не е универсален primary key за безкрайни separate imports след remove/re-add;
- approval е към **точна версия на плана** и е невалидно при промяна;
- operation journal се commit-ва **преди** да се изпрати потенциално рискова команда;
- log/audit не съхранява credentials или торент tracker passkeys;
- след рестарт worker сравнява journal с действителното файлово/qBt състояние.

### 14.1 Примерно представяне на job — не финален API contract

```json
{
  "jobId": "demo-import-0001",
  "torrentHash": "<redacted>",
  "category": "movies",
  "state": "NEEDS_REVIEW",
  "currentStep": 3,
  "planRevision": 2,
  "move": {
    "state": "NOT_STARTED",
    "progressBytes": 0,
    "totalBytes": 0,
    "seedingCapable": null
  },
  "mediaItems": [
    {
      "title": "The Matrix",
      "year": 1999,
      "provider": "tmdb",
      "providerId": "603",
      "bgAudioEvidence": "BG_TAGGED"
    }
  ]
}
```

## 15. Backend API и Worker boundaries

### 15.1 Предложен потребителски API

| Method | Endpoint | Цел |
|---|---|---|
| GET | `/api/jobs` | search/filter jobs |
| GET | `/api/jobs/{id}` | подробности, child items, steps |
| POST | `/api/jobs/{id}/pause` | безопасно pause на orchestration |
| POST | `/api/jobs/{id}/resume` | resume след state check |
| POST | `/api/jobs/{id}/retry` | retry с reconciliation, а не blind repeat |
| GET | `/api/jobs/{id}/plan` | destination preview + dependencies |
| POST | `/api/jobs/{id}/approve` | одобрение на конкретен plan fingerprint |
| POST | `/api/jobs/{id}/review` | match/duplicate/subtitle choice |
| GET | `/api/library/items` | Library Explorer |
| GET | `/api/duplicates` | quality comparisons |
| GET | `/api/transfers` | Move Queue |
| GET | `/api/subtitles` | Subtitle Manager |
| GET | `/api/settings` | настройки без credentials |
| GET | `/api/health` | readiness + dependencies |

API contract е **предложен**, не окончателен. Ще са нужни authentication/authorization, pagination, CSRF protection за браузърни mutation заявки, validation, audit/correlation IDs и versioned error handling.

### 15.2 Background Worker — предложено

- един durable logical worker в първата версия или отделен worker container при реална необходимост;
- per-torrent lock и per-destination lock; bounded concurrency за NAS I/O;
- операции с precondition, persisted request, наблюдаван резултат, persist на verification;
- retry/backoff при временни API outages, но не безкраен retry при potential data corruption;
- `Pause` не означава глобално спиране на всички torrents; спира job orchestration безопасно;
- след crash/restart worker започва от **проверка на реалното състояние**;
- не добавяме Redis/RabbitMQ, ако SQLite ledger и worker са достатъчни.

## 16. UI → реални backend capabilities

| Екран (одобрен wireframe) | Необходими данни/действия |
|---|---|
| **Dashboard** | Jobs, status counters, recent activity, local/NAS health, filters |
| **Job Details** | 7-step progress, evidence, technical expander, approve/retry, media items |
| **Library Explorer** | media catalog, all 5 categories, grid/list, audio/subtitles, versions |
| **Duplicate Comparison** | versions side by side, explainable Bulgarian-first, dependencies |
| **Import / Move Queue** | source/dest, transferred bytes, physical copy, recheck, seeding |
| **Subtitle Manager** | sources, matching confidence, timing, manual candidate choice |
| **Settings** | connections, storage, naming, category mapping, quality, automation, health |

Интерфейсът показва различно: **requested**, **processing**, **verified**, **failed**, **recovery required**. Статусът следва persist-нат backend job, не симулационния таймер от HTML wireframe.

Дизайнът остава dark, desktop-first/responsive, с mint/teal акценти, компактни badges и минимален визуален шум.


## 17. Security, backup и бъдещо deployment

### 17.1 Сигурност и един административен акаунт — ПРИЕТО (P-01/AD-10)

ViMag v1.0 е частна услуга през Tailscale/Traefik, но **не се доверява автоматично на всеки клиент във VPN**. Приет е **един локален административен акаунт**; няма RBAC роли или multi-user administration в първата версия.

- **Authentication:** първоначално администраторско enrollment с безусловно изискване за задаване на уникална парола; без фиксирани default credentials; надеждно hash-ване на паролата (предложен Argon2id), без plaintext съхранение.
- **Session protection:** Secure + HttpOnly cookie, подходящ SameSite, CSRF защита за state-changing действия, expiry/invalidation при logout и password rotation; проверка на session и server-side permissions на **всеки** административен API endpoint, включително job control, approval, quarantine, restore, settings и бъдещи realtime канали.
- **Machine credentials:** qBittorrent completion webhook е отделно автентикиран вътрешен endpoint, **без** интерактивна admin сесия; ограничен до enqueue/intake, без общи admin права.
- **Network:** вътрешен Traefik/Tailscale endpoint; без публично излагане. Rate limits и защита от brute-force за login; reverse-proxy headers са trusted само от правилния proxy.
- **Secrets:** qBt/Jellyfin/TMDb/subtitle credentials живеят в секрети/config извън browser bundle и публичното GitHub repository; никога в logs, NFO или audit.
- **Filesystem:** service account с минимални права до allowlisted download/library/quarantine roots; canonical path + symlink guards, no traversal/implicit overwrite и никакъв arbitrary shell command execution от потребителски input.
- **Audit:** запис на admin login/logout, всички approve/override/quarantine/restore/retry, policy changes и опасни filesystem/API действия с actor, timestamp, target revision и резултат.
- **API:** input validation, XSS/CSRF защита, ограничен CORS, отделяне на read от write commands и reconciliation след restart.
- **Public repository hygiene:** никакви `.env`, API keys, tracker passkeys, лични media inventories или реални токени и download URLs в GitHub.

Точните настройки на hashing, session expiration и секретна ротация са **implementation parameters**, но отсъствие на authentication или server-side enforcement **не е допустимо**.

### 17.2 Backup/restore

- SQLite consistent backups на локален storage + тестове за restore;
- версия на настройки и naming/quality policy;
- преди NAS pilot — snapshot/backup на qBittorrent resume/fastresume state според реалната инсталация;
- безопасни test fixtures и известен изходен file tree;
- recovery runbook за спрял NAS, qBt API error и worker crash;
- audit/DB трябва да остават достъпни, дори когато NAS е офлайн.

### 17.3 Deployment (само ориентир, не задача в текущия етап)

```text
/home/veso/docker/media-manager/
├── docker-compose.yml       # бъдещ
├── config/
├── data/
│   └── media-manager.db
├── logs/
└── backups/
```

Планиран stack: Vue 3, FastAPI, persistent worker, SQLite, ffprobe/MediaInfo, TMDb, subtitle adapters, qBittorrent Web API, Jellyfin REST, Compose/Traefik.

**Docker Hub:** бъдеща image публикация към акаунта `vesovasilev` чрез GitHub Actions и secrets. Няма да създаваме deployment workflow, Docker image или креденшъли преди одобрения технически scope и преминали тестове.

## 18. Нефункционални изисквания

| Тема | Изискване |
|---|---|
| **Data safety** | без blind overwrite, unauthorized delete или промяна на torrent bytes |
| **Crash recovery** | durable jobs, operation journal, idempotency и reconciliation |
| **Performance** | streaming I/O, bounded copy concurrency, ограничен full hashing |
| **NAS safety** | health checks, free-space threshold и контролирано I/O натоварване |
| **Correctness** | category constraints, edition/version awareness, qBt integrity |
| **Explainability** | системата показва защо е взела match/quality/cleanup решение |
| **Observability** | per-job event history, bytes, timings, redacted errors |
| **Security** | Tailscale/internal HTTPS, least-privilege, no secrets in UI |
| **Maintainability** | adapter boundaries, migrations, policy versioning |
| **Availability** | Dashboard работи с диагностика и при временно паднал NAS/Jellyfin |
| **Compatibility** | тествани конкретни qBittorrent 5.x и Jellyfin версии |

**ЗА КАЛИБРАЦИЯ:** реалните числови limits — concurrent copies, retry backoff, minimum free space, partial hash thresholds, retention на logs/backup и performance SLO. Не се въвеждат произволни стойности преди NAS measurements; качествените и metadata thresholds следват AD-06/14.

## 19. Acceptance Criteria и тестова стратегия

### 19.1 Осемте задължителни demo сценария — ПРИЕТО

| Test | Сценарий | Очакван резултат |
|---|---|---|
| **T-01** | New movie | complete import, NFO/artwork/subtitles, Jellyfin verified, seeding verified |
| **T-02** | Existing 1080p verified BG, new 2160p EN | Bulgarian-first предлага **Keep Both** |
| **T-03** | Better new BG version | препоръчва better preferred, без автоматично delete на старата |
| **T-04** | Season pack с много епизоди | отделни Jellyfin episode items, torrent mapping/seeding валиден |
| **T-05** | NAS unavailable по време на copy | source и journal запазени, безопасно recovery |
| **T-06** | BG subtitle timing mismatch | error/review/sync proposal, без silent replace |
| **T-07** | Ambiguous metadata | Needs Review, не се прави move |
| **T-08** | Existing torrent dependency | quarantine/cleanup блокиран |

### 19.2 Допълнителни интеграционни и регресионни тестове

| Test | Проверка | Недопустим дефект |
|---|---|---|
| **T-09** | completion event идва 3 пъти | три отделни physical move операции |
| **T-10** | crash след copy, преди DB update | второ копиране/overwrite без reconciliation |
| **T-11** | qBt `setLocation` е отговорил 200, реалното местене продължава | преждевременен Completed |
| **T-12** | qBt recheck открива incomplete pieces | cleanup или Published/Completed |
| **T-13** | destination collision | silent overwrite |
| **T-14** | category се сменя преди cutover | незабелязано преместване към грешен root |
| **T-15** | symlink/path escaping извън позволения root | запис извън allowlist |
| **T-16** | няма peers/скоростта на upload е нула | фалшива seeding failure |
| **T-17** | потребителят умишлено е спрял torrent | принудителен нежелан resume |
| **T-18** | Automatic Torrent Management / category path | второ неконтролирано местене или missingFiles |
| **T-19** | NAS не поддържа hardlinks | успешен статус без реално работещ link |
| **T-20** | ръчно редактиран NFO | silent overwrite |
| **T-21** | еднакъв TMDb ID, различна edition | смесване/загуба на edition |
| **T-22** | Jellyfin refresh accepted, scan не е приключил | fake PublishedVerified |
| **T-23** | два torrents сеедват общо съдържание | физическо изтриване на shared bytes |
| **T-24** | multi-episode + Season 00 | погрешно двойно индексиране |

### 19.2.1 Допълнителни тестове за приетите политики от Кръг 3

| Test | Сценарий | Очакван резултат |
|---|---|---|
| **T-25** | `bul` audio tag, но реален звук на друг език | `BG_TAGGED`, не `BG_VERIFIED`, без filename `BG` |
| **T-26** | Human BG verification с валиден stream fingerprint, copy без byte change | evidence provenance се запазва и marker е разрешен при safe naming |
| **T-27** | Некоректен prior BG evidence за друг stream/file | evidence се отхвърля/review, без protected BG decision по чуждо доказателство |
| **T-28** | 1080p BG verified срещу 2160p EN със съществено по-добро качество | обяснимо **Keep Both**, без тих overwrite |
| **T-29** | Auto-match само по сходно title/year с competing provider IDs | `NeedsReview`, никакъв move по неясна identity |
| **T-30** | Quarantine proposal за inferior version с активен torrent dependency | approval НЕ премахва dependency block; няма filesystem mutation |
| **T-31** | Изрично одобрена quarantine без dependency и с валиден snapshot | journaled, reversible move + manifest + restore proof, без delete |
| **T-32** | Непознат/ръчно редактиран `movie.nfo` или `poster.jpg` | никакъв silent overwrite, diff/review |
| **T-33** | BG subtitles са за неправилна edition или timing drift | `Mismatch`; sync proposal/manual review; оригиналът остава |
| **T-34** | NAS + qBt + Jellyfin verified, BG subtitles unavailable | `CompletedWithWarnings` с видим missing subtitle |
| **T-35** | Jellyfin refresh 200, no recognized media entry | `PublishPending`; **не** terminal `CompletedWithWarnings` |
| **T-36** | Mixed torrent: единият Child има failed publish | Parent не става Completed до критична проверка на всеки Child |

### 19.2.2 Финални регресионни тестове за P-01, P-02 и P-03

| Test | Сценарий | Очакван резултат |
|---|---|---|
| **T-37** | Достъп до UI/API без валидна admin сесия или с изтекла сесия | Няма административен read/write достъп; защитена login процедура. |
| **T-38** | Невалидна/липсваща CSRF защита при approve или quarantine | Server-side отказ; няма side effect и има security audit. |
| **T-39** | Неавтентикиран completion hook опитва administrative command | Забранен достъп; intake-only capabilities са отделени от admin. |
| **T-40** | ViMag-owned NFO/artwork с непроменен content hash | Разрешен journaled/atomic update, запис на нов hash и audit без загуба на старите данни при failure. |
| **T-41** | Ръчно променен или непознат NFO/artwork, или Jellyfin NFO saver го е модифицирал | Auto-overwrite отказан; diff и review на конкретния файл. |
| **T-42** | Администратор опитва permanent library delete след одобрена quarantine | Няма endpoint/action за permanent delete във v1; активите остават възстановими. |
| **T-43** | AD-16 cleanup на verified staging файл, докато library и quarantine assets съществуват | Премахва се само доказано ненужният staging файл; библиотечните/quarantine файлове остават непокътнати. |

### 19.3 Минимална integration test procedure

1. Тестов единичен torrent с позволени/собствени файлове, без продукционни медии.
2. Multi-file test torrent със sample episodes и sidecars.
3. Запис на всички qBt settings и initial data tree; backup/snapshot на test state.
4. Read-only preflight и destination preview.
5. Test move с проверка на qBt save path, file list, recheck и seeding-capability.
6. Failure injection: NAS disconnect, API outage, worker crash, disk full, destination collision.
7. Повторен retry от същия journal — без дублиран physical move.
8. Rollback/compensation proof.
9. Едва след изрично разрешение — ограничен pilot върху реална библиотека с backup.

**Definition of Done за operational import (AD-18):** terminal `Completed` или `CompletedWithWarnings` само след **NAS integrity + qBt seeding capable + Jellyfin recognized**. Subtitle unavailable е ясно видимо предупреждение, а Jellyfin pending, seeding failure, unsafe file state и critical unresolved Child **блокират** terminal-success.

## 20. Финален регистър на решенията, конфликтен анализ и технически gates

### 20.0 Регистър на архитектурните теми (20 AD теми; 22 избора от въпросниците)

| ID | Област | Продуктово решение | Оставаща техническа работа |
|---|---|---|---|
| **AD-01** | Прости move операции и сложни NAS tree/hardlinks | **ПРИЕТО; стратегия A според torrent type** | Async API behavior, copy/recovery и safe cutover fixtures |
| **AD-02** | qBt управление per Job | **ПРИЕТО A** | 5.x API/rename/TMM/paused semantics |
| **AD-03** | Animations/Documentaries Movies+Series | **ПРИЕТО A** | Jellyfin Movies/Shows paths, no double-scan |
| **AD-04** | Оригинални имена, editions, verified BG marker, series/concert naming | **ПРИЕТО A** | Jellyfin naming tests, Unicode/collisions |
| **AD-05** | Българско аудио с доказателство | **ПРИЕТО A** | Evidence store, stream fingerprint/provenance |
| **AD-06** | Explainable quality и BG-first | **ПРИЕТО A** | Calibration върху реални media samples |
| **AD-07** | Quarantine след одобрение; permanent delete извън v1 | **ПРИЕТО A (Кръг 3 + P-03)** | Dependency / restore tests |
| **AD-08** | NAS hardlinks за сложни torrents | **ПРИЕТО A, технически условно** | Same-filesystem, inode, mounts и ACL tests |
| **AD-09** | BG subtitles и verified sync | **ПРИЕТО A** | Provider adapters и timing validation |
| **AD-10** | Local single admin login | **ПРИЕТО A (P-01)** | Sessions, CSRF, server-side auth tests |
| **AD-11** | Queue, retry, backups | **Принципите ПРИЕТИ** | Measured concurrency, retry budgets, retention |
| **AD-12** | Docker Hub / release CI | **ПО-КЪСЕН ЕТАП** | Secrets, image/tag governance, approval |
| **AD-13** | Library inventory | **ПРИЕТО като scope** | Read-only NAS scan и dependency map |
| **AD-14** | High-confidence identification | **ПРИЕТО A** | Explainable thresholds / provider fallback |
| **AD-15** | Safe automatic sidecars | **ПРИЕТО A** | Ownership evidence per AD-19 |
| **AD-16** | Verified local/staging cleanup | **ПРИЕТО A** | Ownership/integrity/dependency proof |
| **AD-17** | Parent Job + Child Media Items | **ПРИЕТО A** | Torrent-level cutover и cross-category reviews |
| **AD-18** | CompletedWithWarnings/PublishPending | **ПРИЕТО A** | Job state machine regression |
| **AD-19** | ViMag-owned NFO/artwork updates | **ПРИЕТО A (P-02)** | Hash/manifest, Jellyfin conflict safeguards |
| **AD-20** | Respect seeding/paused state | **ПРИЕТО A** | API transitions, ratios/user intent tests |

**Няма неразрешен продуктов избор.** Всички числови граници, конкретните API semantics на инсталацията и filesystem capabilities остават за техническа валидация, а не се маскират като утвърдени факти.

### 20.1 Конфликтен анализ — финална проверка

| Потенциален конфликт | Изход | Задължителен контрол |
|---|---|---|
| **AD-16 auto cleanup** срещу **P-03 no permanent delete** | **Съвместими:** staging ≠ library/quarantine | Операцията се допуска само за verified orphaned temporary source с проверени live dependencies; няма library delete endpoint. |
| **Quarantine after approval** срещу **active seeding/hardlinks** | **Условно съвместими** | Approval не отменя dependency block; shared inode/path е причина за отказ до безопасен план. |
| **BG_VERIFIED filename marker** срещу **qBt mapping** | **Съвместими при безопасен rename** | qBt-aware rename или hardlink path; при unsafe rename не се чупи torrent и се показва pending rename. |
| **One movie folder / multiple editions** срещу **Jellyfin grouping** | **Семантичен риск** | Exact prefix + version suffix, edition key в ViMag DB; verify Jellyfin; не смесвай различни editions при duplicate cleanup. |
| **Animations/Documentaries Movies+Series** срещу **Jellyfin mixed content** | **Изисква конфигурация** | Отделни Jellyfin Movies/Shows roots под приетите qBt категории; no double-scan. |
| **Auto-sidecar update** срещу **Jellyfin NFO saver** | **Съвместими само с ownership guards** | Hash/manifest, optimistic concurrency, skip+review на външни edits, no write loop. |
| **One admin account** срещу **per-action approval/audit** | **Няма конфликт** | Admin approval е explicit и audit-нат, не неявен при login; server-side check на текущата ревизия. |
| **BG subtitle mismatch** срещу **CompletedWithWarnings** | **Съвместими само за безопасен пропуск** | Unverified subtitle не се прикрепя като matched; failure на Jellyfin/seeding не може да бъде warning-only. |
| **High confidence TMDb** срещу **concerts without IDs** | **Съвместими чрез review** | Без измислен provider ID/year; no-ID manual flow. |
| **CompletedWithWarnings** срещу **unresolved critical child item** | **Несъвместимо като terminal success** | Няма terminal success преди всички critical Child verification gates. |
| **Private VPN** срещу **auth** | **Няма конфликт** | VPN е мрежова защита, локалният admin login е отделен задължителен слой. |

**Оценка:** няма доказано противоречие между 22-те приети продуктови избора. Техническият риск при move/seed, Jellyfin edition grouping, hardlinks и sidecar concurrency остава **блокиращ за реални операции**, докато не бъде доказана безопасността чрез G-01..G-06.

### 20.2 Технически gates (неизпълнени; блокират операции с реални медии)

| Gate | Задължително доказателство | Кога |
|---|---|---|
| **G-01 qBittorrent** | Installed 5.x build, API endpoints, TMM/category save paths, resume/stop/recheck/rename, pause/queue semantics | Преди интеграционен cutover |
| **G-02 NAS** | Mount type/UID-GID/ACL, same filesystem за hardlinks, inode/link tests, disk quota/space, atomic sidecar behavior | Преди NAS writes |
| **G-03 Jellyfin** | Реални Movies/Shows library paths, NFO saver конфигурация, multiple versions/editions, no double-scan, scan completion verification | Преди publish workflow |
| **G-04 Recovery** | Инжектирани грешки: worker crash, NAS offline, qBt API timeout, checksum fail, journal replay, restore и safe cleanup | Преди write-capable pilot |
| **G-05 Media validation** | Representative anonymized samples за BG evidence, quality thresholds, metadata confidence, subtitle providers/timing | Преди automatic decision enablement |
| **G-06 Inventory** | Read-only scan на петте NAS категории и dependency map към qBt; точни данни от inventory CSV, ако е наличен | Преди maintenance operations |

**Измерими имплементационни параметри** (не са ново продуктово гласуване): max concurrent file moves, retry budget/backoff, minimum free space, storage reserve, log/backup retention, scan timeouts и hash implementation. Те трябва да се фиксират с измервания и да бъдат документирани преди production.

### 20.3 Процедура за sign-off

1. **ИЗПЪЛНЕНО:** потребителят прегледа и изрично одобри документа Technical Scope v1.0, включително всички 22 решения.
2. **ИЗПЪЛНЕНО:** потребителят изрично разреши GitHub публикацията на README, одобрения технически scope и одобрения wireframe.
3. Одобрението и публикацията на scope **не** разрешават code implementation, Docker deployment, real file mutations или автоматични NAS jobs.
4. G-01..G-06 трябва да бъдат доказани преди безопасни интеграционни/production файлови операции. Непреминат gate запазва блокиращия статус, дори след одобрен scope.

## 21. Roadmap и release gates

| Етап | Състояние | Условие за преминаване |
|---|---|---|
| **A — UX Wireframe** | **ОДОБРЕН** | интерактивен HTML v1.0 |
| **B — Technical Scope** | **ОДОБРЕН — v1.0, всички 22 решения потвърдени** | техническите gates G-01..G-06 остават неизпълнени |
| **C — Implementation Design** | НЕ Е ЗАПОЧНАЛ | избор на seeding/move стратегия и interface contracts |
| **D — Development / Fixtures** | НЕ Е ЗАПОЧНАЛ | имплементация + automated/integration tests |
| **E — NAS/qBt pilot** | НЕ Е ЗАПОЧНАЛ | backup, integrity/recheck, rollback proof |
| **F — Production** | НЕ Е ЗАПОЧНАЛ | operational acceptance и monitoring |
| **G — Docker Hub images** | НЕ Е ЗАПОЧНАЛ | CI/CD и secrets review |

**Важно:** одобрение на този документ и публикуването му в GitHub **не означават** автоматично разрешение за deployment, файлови операции или промяна на работещия qBittorrent.

## 22. Технически референции

1. [qBittorrent WebUI API v5.0+](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-%28qBittorrent-5.0%29) — актуална публична документация; поведението трябва да се верифицира при конкретната инсталирана 5.x build.
2. [Jellyfin Movies](https://jellyfin.org/docs/general/server/media/movies/) — naming, editions, multiple versions, subtitle patterns.
3. [Jellyfin TV Shows](https://jellyfin.org/docs/general/server/media/shows/) — seasons/episodes.
4. [Jellyfin Local NFO](https://jellyfin.org/docs/general/server/metadata/nfo/) — приоритет на NFO и naming.
5. [Jellyfin Metadata Provider IDs](https://jellyfin.org/docs/general/server/metadata/identifiers/).
6. [Docker GitHub Actions](https://docs.docker.com/build/ci/github-actions/) — ориентир за бъдещ release process.

**Изходна база:** ViMag Media Manager — Master Product & UX Specification (Phase A), одобреният Interactive HTML Wireframe v1.0 и изричните потребителски решения от Кръгове 1–3 плюс финалния кръг. Публичната документация на qBittorrent/Jellyfin е използвана за техническа съвместимост. Текущите реални NAS/qBt настройки и `all-movies.csv` **не** са проверени на живо в този етап.

---

**Състояние на този артефакт:** **APPROVED — Technical Scope v1.0**, с всички 22 продуктови избора от четирите кръга и изрично разрешение за публикуване в `vesovasilev-vimag/media-manager` на 01.11.2026 г. Това е документационна версия, а не software release. **Backend/Docker разработка, deployment и реални NAS/qBittorrent/Jellyfin операции не са започвани и не се разрешават от настоящото одобрение.**
