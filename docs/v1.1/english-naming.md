# Mandatory English naming and Library UX

Owner authorization: 2026-11-04. This PR targets `main`; it does not authorize merge, release publication, Docker Hub access, deployment, production database/NAS changes or torrent changes.

## Naming authority

TMDb searches and details request `en-US`. Movies use localized `title`; series use localized `name`. `original_title` and `original_name` are separate evidence, not automatic naming fallbacks. A requested locale alone is insufficient: TMDb may return a fallback. Details require an English-original work or a matching English translation record. Missing English authority produces a review error instead of guessing, transliteration, script heuristics or automatic translation.

Collection details request English and validate the separate collection translations endpoint. Episode details append translations and require English evidence. An untranslated collection blocks a plan only when enabled and included by its naming policy. An episode title is fetched when its template includes `{EpisodeTitle}`; ambiguous multi-episode title combinations require review. Concert event titles use the same English authority when linked to TMDb; a conflicting manual event value requires review. Artist names and BG/audio/edition evidence are preserved, never translated speculatively.

English metadata cache keys include `en-US`, media type and provider ID; episode keys also include season/episode. Cache entries carry their language and expire after one day. Legacy keys, mismatched-language entries, malformed dates and expired data cannot silently supply an English identity. An unavailable provider does not authorize fallback to an old non-English title merely because its ID was confirmed.

Normalization reuses confirmed IDs and updates the **proposed** identity title while preserving editions, IDs, original titles, BG evidence and unrelated metadata. Metadata retrieval writes only the language-specific cache; it does not rewrite asset identity or media paths. Explicit manual title provenance and historical identity-confirmation audit entries protect conflicting manual titles by sending them to review. The existing identity editor records manual provenance and offers an explicit English acknowledgement for authoritative human corrections; metadata edits still never move a file. Without provider authority or an explicit English confirmation, normalization requires review.

The policy renderer rejects unverified naming language, including collections/episode titles when used. Analysis creates an exact destination plan. Approval still binds its revision and hash. Execution revalidates the frozen normalization target; no metadata refresh changes an already-approved destination. Older plans lacking English evidence must be reviewed before new mutations rather than silently rewritten. Fingerprint, collision, sidecar ownership, dependency, authorization, lease/fencing and journal guards remain mandatory. Metadata edits preserve unrelated identity fields and invalidate stale English evidence when the title/ID changes without new confirmation. The legacy normalization-plan route also requires explicit English evidence.

## Library UX

The toolbar retains its icons/actions/disabled behavior with the shorter labels **Нормализация** and **Обследване**. This dedicated PR also carries the previously tested, still-unmerged Library actions changes from PR #11: one shared card/table configuration, anchored/flipping/clamped dropdowns and explicit guarded delete confirmation. It does not merge or close that earlier PR. See [Library action safety](library-actions-fix.md).

## Validation and operational boundary

`tests/contracts/test_tmdb_english.py` covers localized movie/series fields, Korean/Japanese/French originals, missing translations, English originals and collection/episode evidence. `tests/acceptance/test_english_naming.py` covers confirmed IDs, language-scoped cache reuse/invalidation, manual overrides, English templates, catalogue/media preservation and write-gate refusal. Existing synthetic fixtures now explicitly attest English test identities; safety assertions are retained. Frontend and Chromium suites cover toolbar labels, shared actions, geometry, confirmation, dismissal and duplicate prevention.

All provider tests use synthetic responses; no live TMDb credential or production service was used. Full CI and Security results are recorded on the PR for its exact head. CI container builds are test/security artifacts only; no release images or Docker Hub publication are requested or performed.

Provider contracts checked against TMDb's [search/detail guide](https://developer.themoviedb.org/docs/search-and-query-for-details), [append-to-response documentation](https://developer.themoviedb.org/docs/append-to-response), [collection translations](https://developer.themoviedb.org/reference/collection-translations) and [episode translations](https://developer.themoviedb.org/reference/tv-episode-translations).
