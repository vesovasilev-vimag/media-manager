"""Restartable incremental inventory; missing requires successful category enumeration."""

import os
from pathlib import Path
from typing import Any

from sqlalchemy import insert, select, update

from app import persistence as p
from app.catalogue import normalized
from app.domain import CATEGORIES, GateError, bg_state, digest
from app.storage import contained, read_nfo, sha256

VIDEO = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts"}


def enumerate_category(root: Path) -> list[Path]:
    if root.is_symlink() or not root.is_dir():
        raise GateError("CATEGORY_UNAVAILABLE", "BlockedExternalDependency")
    paths = []

    def failed(error: OSError) -> None:
        raise error

    for parent, dirs, files in os.walk(root, onerror=failed, followlinks=False):
        if any((Path(parent) / d).is_symlink() for d in dirs):
            raise GateError("SYMLINK_BLOCKED")
        for name in files:
            path = Path(parent) / name
            if path.suffix.lower() in VIDEO:
                if path.is_symlink():
                    raise GateError("SYMLINK_BLOCKED")
                path.stat()  # Detect failed access before any missing classification.
                paths.append(path)
    return paths


def execute(worker: Any, task: dict[str, Any]) -> None:
    db = worker.db
    db.reserve(task, ["library-scan"])
    scan_rows = db.rows(select(p.scans).where(p.scans.c.task_id == task["id"]))
    if not scan_rows:
        with db.transaction() as conn:
            conn.execute(
                insert(p.scans).values(task_id=task["id"], scope=list(CATEGORIES), state="QUEUED")
            )
        scan_rows = db.rows(select(p.scans).where(p.scans.c.task_id == task["id"]))
    scan = scan_rows[0]
    recorded = db.rows(
        select(p.audit).where(p.audit.c.target == scan["id"], p.audit.c.kind == "INVENTORY_ASSET")
    )
    outcomes = {row["data"]["path"]: row["data"]["result"] for row in recorded}
    summary: dict[str, Any] = {
        "new": 0,
        "changed": 0,
        "unchanged": 0,
        "missing": 0,
        "failed": 0,
        "processed": 0,
        "errors": [],
        "enumerated": [],
    }
    for outcome in outcomes.values():
        summary[outcome] += 1
        summary["processed"] += 1
    library = worker.cfg.nas_root / "Library"

    def progress(state: str) -> None:
        with db.transaction() as conn:
            db.assert_lease(conn, task)
            conn.execute(
                update(p.scans).where(p.scans.c.id == scan["id"]).values(state=state, data=summary)
            )

    progress("RUNNING")
    try:
        worker.nas_health()
        torrents = worker.qbt.all()  # Unavailable qBt never becomes a trusted empty dependency set.
        for category in scan["scope"]:
            successful = True
            seen: set[str] = set()
            try:
                roots = {CATEGORIES[category]}
                known = db.rows(
                    select(p.assets.c.relative_path).where(
                        p.assets.c.category == category, p.assets.c.workflow_state == "ACTIVE"
                    )
                )
                required_roots = {row["relative_path"].split("/")[0] for row in known}
                roots |= required_roots
                for policy in db.rows(select(p.policies)):
                    roots.add(policy["data"]["categories"][category]["root"])
                traversed = [
                    contained(library, name) for name in sorted(roots) if (library / name).is_dir()
                ]
                if not traversed or any(not (library / name).is_dir() for name in required_roots):
                    raise GateError("CATEGORY_UNAVAILABLE")
                paths = [path for root in traversed for path in enumerate_category(root)]
            except (OSError, GateError):
                summary["failed"] += 1
                summary["errors"].append({"category": category, "code": "ENUMERATION_INCOMPLETE"})
                continue
            for path in paths:
                try:
                    rel = path.relative_to(library).as_posix()
                    contained(library, rel, existing=True)
                    stat = path.stat()
                    previous = db.rows(
                        select(p.assets).where(
                            p.assets.c.root == "library", p.assets.c.relative_path == rel
                        )
                    )
                    prior = previous[0] if previous else None
                    if prior and prior["workflow_state"] != "ACTIVE":
                        raise GateError("INACTIVE_PATH_REAPPEARED")
                    cached = bool(
                        prior
                        and prior["mtime_ns"] == stat.st_mtime_ns
                        and prior["observed_size"] == stat.st_size
                    )
                    fingerprint = prior["fingerprint"] if cached and prior else sha256(path)
                    analysis = prior["data"]["probe"] if cached and prior else worker.probe(path)
                    # Reuse stable identity, including manual corrections; filename guesses never confirm IDs.
                    identity = (prior or {}).get("data", {}).get("identity") or {}
                    nfo = path.with_suffix(".nfo")
                    if not nfo.is_file():
                        nfo = path.parent / "movie.nfo"
                    if not identity and nfo.is_file() and not nfo.is_symlink():
                        identity = read_nfo(nfo)
                    if not prior:
                        # A rename is accepted only for exactly one missing old path with matching full bytes.
                        matches = db.rows(
                            select(p.assets).where(
                                p.assets.c.fingerprint == fingerprint,
                                p.assets.c.workflow_state == "ACTIVE",
                            )
                        )
                        matches = [
                            m
                            for m in matches
                            if not contained(library, m["relative_path"]).exists()
                        ]
                        if len(matches) == 1:
                            prior = matches[0]
                            identity = prior["data"].get("identity") or identity
                        elif matches:
                            raise GateError("AMBIGUOUS_RENAME")
                    external = []
                    for sub in path.parent.glob(path.stem + ".*"):
                        if (
                            sub.suffix.lower() in {".srt", ".ass", ".vtt", ".ssa"}
                            and not sub.is_symlink()
                        ):
                            tags = sub.name[len(path.stem) + 1 :].split(".")
                            external.append(
                                {
                                    "path": sub.relative_to(library).as_posix(),
                                    "language": tags[0] if len(tags) > 1 else "und",
                                }
                            )
                    data = {
                        **((prior or {}).get("data", {})),
                        "identity": identity,
                        "category": category,
                        "probe": analysis,
                        "bg": "BG_VERIFIED"
                        if prior
                        and prior["fingerprint"] == fingerprint
                        and prior["data"].get("bg") == "BG_VERIFIED"
                        else bg_state(analysis, fingerprint, []),
                        "inventory_only": True,
                        "stream_keys": [
                            {"index": s.get("index"), "key": digest(s)}
                            for s in analysis.get("streams", [])
                            if s.get("codec_type") == "audio"
                        ],
                        "external_subtitles": external,
                        "dependencies": [],
                    }
                    for torrent in torrents:
                        for file in torrent.files:
                            if (
                                torrent.save_path.rstrip("/") + "/" + file["name"]
                                == "/library/" + rel
                            ):
                                data["dependencies"].append(torrent.info_hash)
                    if (
                        path.stat().st_mtime_ns != stat.st_mtime_ns
                        or path.stat().st_size != stat.st_size
                    ):
                        raise GateError("CHANGED_DURING_SCAN")
                    values = {
                        "relative_path": rel,
                        "fingerprint": fingerprint,
                        "data": data,
                        "mtime_ns": stat.st_mtime_ns,
                        "observed_size": stat.st_size,
                        "availability": "AVAILABLE",
                        "last_seen": p.now(),
                        **normalized(rel, data),
                    }
                    with db.transaction() as conn:
                        db.assert_lease(conn, task)
                        if prior:
                            conn.execute(
                                update(p.assets)
                                .where(p.assets.c.id == prior["id"])
                                .values(**values, revision=prior["revision"] + (0 if cached else 1))
                            )
                        else:
                            conn.execute(insert(p.assets).values(root="library", **values))
                        outcome = "unchanged" if cached else "changed" if prior else "new"
                        if rel not in outcomes:
                            db.event(
                                conn,
                                "worker",
                                "INVENTORY_ASSET",
                                scan["id"],
                                {"path": rel, "result": outcome},
                            )
                            outcomes[rel] = outcome
                            summary[outcome] += 1
                            summary["processed"] += 1
                    seen.add(rel)
                except (OSError, GateError) as error:
                    successful = False
                    summary["failed"] += 1
                    summary["errors"].append(
                        {
                            "category": category,
                            "path": path.relative_to(library).as_posix(),
                            "code": error.code if isinstance(error, GateError) else "FILE_IO_ERROR",
                        }
                    )
                progress("RUNNING")
            if successful:
                # Revalidate the mount after traversal so disconnects cannot fabricate missing rows.
                worker.nas_health()
                if any(not root.is_dir() for root in traversed):
                    raise GateError("NAS_OFFLINE", "BlockedExternalDependency")
                with db.transaction() as conn:
                    db.assert_lease(conn, task)
                    result = conn.execute(
                        update(p.assets)
                        .where(
                            p.assets.c.category == category,
                            p.assets.c.workflow_state == "ACTIVE",
                            p.assets.c.availability != "MISSING",
                            p.assets.c.relative_path.not_in(seen),
                        )
                        .values(availability="MISSING", revision=p.assets.c.revision + 1)
                    )
                    summary["missing"] += result.rowcount
                summary["enumerated"].append(category)
        progress("COMPLETED_WITH_ERRORS" if summary["failed"] else "COMPLETED")
    except (GateError, OSError):
        summary["errors"].append({"code": "SCAN_EXTERNAL_FAILURE"})
        progress("FAILED")
        raise GateError("SCAN_EXTERNAL_FAILURE", "BlockedExternalDependency") from None
    with db.transaction() as conn:
        db.event(conn, "worker", "INVENTORY_COMPLETED", scan["id"], summary)
