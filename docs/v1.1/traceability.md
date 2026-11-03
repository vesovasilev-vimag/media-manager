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
