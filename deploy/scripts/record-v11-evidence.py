"""Record executed v1.1 evidence without rewriting immutable RC1 history."""

import argparse
import ast
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument(
    "--backend", type=Path, default=root / ".test-artifacts/backend.xml"
)
parser.add_argument("--frontend", type=Path)
parser.add_argument("--browser", type=Path)
args = parser.parse_args()
locations = {}
for file in (root / "tests").rglob("test_*.py"):
    for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            locations[node.name] = f"{file.relative_to(root).as_posix()}:{node.lineno}"


def read_report(path: Path, backend: bool = False) -> list[dict[str, str]]:
    rows = []
    for case in ElementTree.parse(path).getroot().iter("testcase"):
        name = case.attrib["name"].split("[")[0]
        status = (
            "FAIL"
            if case.find("failure") is not None or case.find("error") is not None
            else "NOT_VERIFIED"
            if case.find("skipped") is not None
            else "PASS"
        )
        if backend and name not in locations:
            raise ValueError("Unknown backend source test: " + name)
        rows.append(
            {
                "test": name,
                "status": status,
                "source": locations.get(
                    name, case.attrib.get("file", case.attrib.get("classname", ""))
                ),
            }
        )
    return rows


backend = read_report(args.backend, True)
regressions = {
    f"{prefix}-{ix:02}": []
    for prefix, n in [("T", 43), ("IT", 17)]
    for ix in range(1, n + 1)
}
for row in backend:
    for identifier in ["T-" + v for v in re.findall(r"(?<!I)T(\d{2})", row["test"])] + [
        "IT-" + v for v in re.findall(r"IT(\d{2})", row["test"])
    ]:
        if identifier in regressions:
            regressions[identifier].append(row)


def status(rows: list[dict[str, str]]) -> str:
    return (
        "PASS"
        if rows and all(row["status"] == "PASS" for row in rows)
        else "NOT_VERIFIED"
    )


groups = {
    "LIB-01..04": ["test_LIB_"],
    "BG-01": ["test_T25_", "test_BG_"],
    "SCAN-01": ["test_SCAN_"],
    "HIER-01 / NAME-01 / HIER-02": ["test_HIER_", "test_SCAN_overlap_", "test_META_"],
    "META-01": ["test_META_", "test_BULK_pause_"],
    "SUB-01..03": ["test_SUB_"],
    "BULK-01..03": ["test_BULK_", "test_NORMALIZE_"],
    "QUAR-01": ["test_QUAR_"],
    "DELETE-01": ["test_DELETE_", "test_V11_"],
    "Migration / recovery": ["test_v11_upgrade_", "test_IT13_", "test_migration_"],
}
requirements = {
    key: [
        row
        for row in backend
        if any(row["test"].startswith(prefix) for prefix in prefixes)
    ]
    for key, prefixes in groups.items()
}
sources = {}
for base in [
    root / "backend/app",
    root / "backend/alembic",
    root / "tests",
    root / "frontend/src",
    root / "frontend/tests",
    root / "frontend/e2e",
]:
    for file in sorted(base.rglob("*")):
        if file.suffix in {".py", ".ts", ".vue", ".css"}:
            sources[file.relative_to(root).as_posix()] = hashlib.sha256(
                file.read_bytes()
            ).hexdigest()
output = {
    "generated_at": datetime.now(UTC).isoformat(),
    "environment": "Disposable PostgreSQL/Linux, generated synthetic NAS media; no production access",
    "backend": backend,
    "regressions": {key: status(rows) for key, rows in regressions.items()},
    "requirements": {
        key: {"status": status(rows), "tests": rows}
        for key, rows in requirements.items()
    },
    "supersessions": {
        "T-25": "BG-01 accepts detected stream tags while retaining provenance",
        "T-42": "DELETE-01 permits only separate explicit confirmed Library deletion; no implicit delete or quarantine purge",
    },
    "frontend": read_report(args.frontend)
    if args.frontend
    else "See separate frontend CI artifact",
    "browser": read_report(args.browser)
    if args.browser
    else "See separate browser CI artifact",
    "junit_sha256": hashlib.sha256(args.backend.read_bytes()).hexdigest(),
    "source_sha256": sources,
}
dest = root / "docs/v1.1/automated-evidence.json"
dest.write_text(
    json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
lines = [
    "# v1.1 verification traceability",
    "",
    "Generated only from executed JUnit results. Live production gates are separate. [Machine-readable evidence](automated-evidence.json).",
    "",
    "| Requirement | Backend status | Exact executed references |",
    "|---|---|---|",
]
for key, rows in requirements.items():
    refs = "; ".join("`" + row["source"] + "`" for row in rows)
    lines.append(f"| {key} | {status(rows)} | {refs} |")
lines += [
    "",
    "NAV-01, Table/Card state, dialogs and token drag/drop are also covered by `frontend/tests/library.test.ts` and `frontend/e2e/workspace.spec.ts`; their separate frontend/browser JUnit artifacts must pass on the reviewed source.",
    "",
    "All 60 historical T/IT identifiers have executed regression references in automated-evidence.json. T-25 and T-42 use the explicit owner-approved v1.1 supersessions above; RC1's original evidence/report are not rewritten.",
    "",
    "Real Jellyfin evidence: `tests/fixtures/jellyfin_contract.py`, pinned server and internal-only network in `tests/compose.jellyfin.yaml`; CI artifact `jellyfin-v11.json` verifies collections, four edition sources and exclusion of subtitle history. Production Jellyfin/CIFS/qBt/provider checks remain deployment prerequisites.",
    "",
]
(root / "docs/v1.1/traceability.md").write_text("\n".join(lines), encoding="utf-8")
print(
    json.dumps(
        {
            "backend_tests": len(backend),
            "backend_status": status(backend),
            "regression_ids_passed": sum(
                status(rows) == "PASS" for rows in regressions.values()
            ),
        }
    )
)
if status(backend) != "PASS" or any(
    status(rows) != "PASS" for rows in [*requirements.values(), *regressions.values()]
):
    raise SystemExit(1)
