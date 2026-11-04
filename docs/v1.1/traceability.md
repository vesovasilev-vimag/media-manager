# v1.1 verification traceability

Generated only from executed JUnit results. Live production gates are separate. [Machine-readable evidence](automated-evidence.json).

| Requirement | Backend status | Exact executed references |
|---|---|---|
| LIB-01..04 | PASS | `tests/acceptance/test_library_v11.py:75`; `tests/acceptance/test_library_v11.py:144` |
| BG-01 | PASS | `tests/acceptance/test_library_v11.py:504`; `tests/acceptance/test_policies.py:84` |
| SCAN-01 | PASS | `tests/acceptance/test_library_v11.py:155`; `tests/acceptance/test_library_v11.py:199` |
| HIER-01 / NAME-01 / HIER-02 | PASS | `tests/acceptance/test_library_v11.py:199`; `tests/acceptance/test_library_v11.py:225`; `tests/acceptance/test_library_v11.py:555` |
| META-01 | PASS | `tests/acceptance/test_library_v11.py:361`; `tests/acceptance/test_library_v11.py:555` |
| SUB-01..03 | PASS | `tests/acceptance/test_subtitle_history_v11.py:61`; `tests/acceptance/test_subtitle_history_v11.py:87`; `tests/acceptance/test_subtitle_history_v11.py:133`; `tests/acceptance/test_subtitle_history_v11.py:180`; `tests/acceptance/test_subtitle_history_v11.py:231` |
| BULK-01..03 | PASS | `tests/acceptance/test_library_v11.py:335`; `tests/acceptance/test_library_v11.py:361`; `tests/acceptance/test_library_v11.py:518` |
| QUAR-01 | PASS | `tests/acceptance/test_library_v11.py:314`; `tests/acceptance/test_library_v11.py:402` |
| DELETE-01 | PASS | `tests/acceptance/test_library_v11.py:263`; `tests/acceptance/test_library_v11.py:295`; `tests/acceptance/test_library_v11.py:379`; `tests/acceptance/test_library_v11.py:432`; `tests/acceptance/test_library_v11.py:467` |
| Migration / recovery | PASS | `tests/integration/test_migration_v11.py:14`; `tests/integration/test_operations.py:22`; `tests/integration/test_operations.py:81` |

NAV-01, Table/Card state, dialogs and token drag/drop are also covered by `frontend/tests/library.test.ts` and `frontend/e2e/workspace.spec.ts`; their separate frontend/browser JUnit artifacts must pass on the reviewed source.

All 60 historical T/IT identifiers have executed regression references in automated-evidence.json. T-25 and T-42 use the explicit owner-approved v1.1 supersessions above; RC1's original evidence/report are not rewritten.

Real Jellyfin evidence: `tests/fixtures/jellyfin_contract.py`, pinned server and internal-only network in `tests/compose.jellyfin.yaml`; CI artifact `jellyfin-v11.json` verifies collections, four edition sources and exclusion of subtitle history. Production Jellyfin/CIFS/qBt/provider checks remain deployment prerequisites.

## Library-first amendment acceptance (2026-11-04)

| Requirement | Exact regression evidence |
|---|---|
| Legacy missingFiles/reference independence in planning/execution | `test_library_first.py::test_legacy_missing_files_references_do_not_block_plan_or_execution`, `::test_compatible_single_normalization_ignores_legacy_references` |
| Full-library inspection/enrichment; unresolved peers continue | `test_library_first.py::test_scan_enriches_all_categories_and_keeps_unidentified_in_review`; existing `test_library_v11.py` scan regressions |
| English names and strict auto-identification | `test_library_first.py::test_strict_unique_title_year_identification_and_english_preview`; existing `test_english_naming.py` and `test_tmdb_english.py` |
| Manual search, ID lookup, persisted corrections/reanalysis | `test_library_first.py::test_manual_tmdb_search_correction_reanalysis_and_persistence`, `::test_known_tmdb_id_lookup_is_language_scoped_and_read_only` |
| Preview state filters and NoChange | `test_library_first.py::test_preview_review_filters_and_already_normalized_are_server_side` |
| Fingerprint/collision/ownership safeguards | `test_library_first.py::test_filesystem_hazards_require_review_despite_legacy_decoupling` (five hazards); existing restart/lease/sidecar regressions |
| Unauthorized/unapproved/write-disabled mutations blocked | `test_library_first.py::test_correction_invalidates_approval_and_reanalysis_requires_auth`, `::test_unapproved_and_write_disabled_normalizations_cannot_mutate`; existing security suite |
| Torrent polling cannot starve Library tasks | `test_library_first.py::test_torrent_poll_failure_does_not_starve_library_worker` |
| Bidirectional duplicate evidence, no replacement | `test_library_first.py::test_new_duplicate_inspection_relationships_are_bidirectional` |
| Review UX, full-scan scope, exact per-asset corrections | `frontend/tests/library-first.test.ts`; `frontend/e2e/library-first.spec.ts` desktop/mobile |

All Python test references above are under `tests/acceptance/` except TMDb contracts under `tests/contracts/`. No production integration claim is made. See [implementation and validation report](library-first-report.md).
