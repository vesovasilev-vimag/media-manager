"""Per-file maintenance saga: exact plans, one approval, checkpointed execution."""

import os
import re
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import catalogue, library_policy
from app import persistence as p
from app.domain import GateError, digest
from app.maintenance import dependencies
from app.storage import collision, contained, sha256

DONE = {
    "Completed",
    "CompletedWithWarnings",
    "NoChange",
    "NeedsReview",
    "Failed",
    "RecoveryRequired",
    "Cancelled",
}


def update_file(db: p.Database, file: dict[str, Any], **values: Any) -> None:
    with db.transaction() as conn:
        conn.execute(
            update(p.maintenance_files)
            .where(p.maintenance_files.c.id == file["id"])
            .values(**values)
        )


def dependency_guard(
    worker: Any,
    asset: dict[str, Any],
    snapshot: list[Any] | None = None,
    plan_id: str | None = None,
    source_rel: str | None = None,
) -> None:
    if asset["data"].get("dependencies") or worker.db.rows(
        select(p.refs.c.id).where(p.refs.c.asset_id == asset["id"])
    ):
        raise GateError("DEPENDENCY_BLOCKED")
    if dependencies(worker, {**asset, "source": source_rel}, snapshot):
        raise GateError("DEPENDENCY_BLOCKED")
    source_rel = source_rel or "Library/" + asset["relative_path"]
    path = contained(worker.cfg.nas_root, source_rel)
    # A positive link count is additional blocking evidence; a CIFS count of 1 proves nothing.
    if path.exists() and path.stat().st_nlink > 1:
        known_targets = set()
        if plan_id:
            for op in worker.db.rows(
                select(p.operations).where(
                    p.operations.c.plan_id == plan_id, p.operations.c.status == "COMMAND_REQUESTED"
                )
            ):
                intent = op["intent"]
                if intent.get("source") == source_rel and intent.get("target"):
                    target = contained(worker.cfg.nas_root, intent["target"])
                    if (
                        target.is_file()
                        and sha256(target) == asset["fingerprint"]
                        and os.path.samefile(path, target)
                    ):
                        known_targets.add(intent["target"])
        if not known_targets or path.stat().st_nlink != 1 + len(known_targets):
            raise GateError("HARDLINK_OWNERSHIP_UNKNOWN")


def associated(worker: Any, asset: dict[str, Any]) -> list[dict[str, Any]]:
    root = worker.cfg.nas_root
    source = contained(root, "Library/" + asset["relative_path"], existing=True)
    result = []
    videos = [
        x
        for x in source.parent.iterdir()
        if x.suffix.lower() in {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts"}
    ]
    same_stem = [x for x in videos if x.stem.casefold() == source.stem.casefold()]
    if len(same_stem) != 1:
        raise GateError("SIDECAR_ASSOCIATION_AMBIGUOUS")
    paths = [source]
    # Exact video-stem binding excludes sibling episodes and collection/show artwork.
    paths.extend(
        x
        for x in source.parent.iterdir()
        if x.name.startswith(source.stem + ".")
        and x.suffix.lower() in {".srt", ".ass", ".ssa", ".vtt", ".nfo"}
    )
    owned = worker.db.rows(select(p.sidecars).where(p.sidecars.c.root == "nas"))
    common_names = {"movie.nfo", "poster.jpg", "backdrop.jpg"}
    peers = worker.db.rows(
        select(p.assets.c.relative_path).where(
            p.assets.c.workflow_state == "ACTIVE", p.assets.c.id != asset["id"]
        )
    )
    singleton = (
        (asset["data"].get("identity") or {}).get("media_type") in {"movie", "concert"}
        and len(videos) == 1
        and not any(x.is_dir() for x in source.parent.iterdir())
        and not any(
            PurePosixPath(r["relative_path"]).parent == PurePosixPath(asset["relative_path"]).parent
            for r in peers
        )
    )
    for row in owned:
        owned_path = PurePosixPath(row["relative_path"])
        common = (
            singleton
            and owned_path.parent.as_posix() == source.parent.relative_to(root).as_posix()
            and owned_path.name in common_names
        )
        exclusive = (
            row["data"].get("asset_id") == asset["id"]
            and row["data"].get("exclusive") is True
            and (owned_path.name not in common_names or common)
        )
        if exclusive or common:
            path = contained(root, row["relative_path"], existing=True)
            if sha256(path) != row["sha256"] or row["locked"]:
                raise GateError("SIDECAR_CONCURRENT_EDIT")
            paths.append(path)
    versions = worker.db.rows(
        select(p.subtitle_versions).where(p.subtitle_versions.c.asset_id == asset["id"])
    )
    for version in versions:
        entries = [
            {"path": version["data"]["blob"], "sha256": version["data"]["sha256"]},
            *version["data"].get("history", []),
        ]
        for entry in entries:
            if not entry["path"].startswith(".vimag-subtitle-history/" + asset["id"] + "/"):
                raise GateError("SUBTITLE_HISTORY_OWNERSHIP_UNKNOWN")
            path = contained(root, entry["path"], existing=True)
            if sha256(path) != entry["sha256"]:
                raise GateError("SUBTITLE_ARCHIVE_CHANGED")
            paths.append(path)
    for path in sorted(set(paths)):
        rel = path.relative_to(root).as_posix()
        contained(root, rel, existing=True)
        st = path.stat()
        result.append(
            {
                "source": rel,
                "sha256": sha256(path),
                "size": st.st_size,
                "mtime_ns": st.st_mtime_ns,
                "video": path == source,
            }
        )
    return result


def identity(
    worker: Any, asset: dict[str, Any], policy: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Only established IDs can auto-confirm; title-only candidates remain reviewable."""
    known = dict(asset["data"].get("identity") or {})
    name = PurePosixPath(asset["relative_path"]).stem
    episode = re.search(r"(?i)S(\d{1,3})E(\d{1,3})(?:-?E(\d{1,3}))?", name)
    known.setdefault(
        "media_type",
        "show"
        if episode or asset["category"] == "series"
        else "concert"
        if asset["category"] == "concerts"
        else "movie",
    )
    if episode:
        known.setdefault("season", int(episode[1]))
        known.setdefault(
            "episodes", list(range(int(episode[2]), int(episode[3] or episode[2]) + 1))
        )
    if isinstance(known.get("year"), str) and known["year"].isdecimal():
        known["year"] = int(known["year"])
    year = re.search(r"\b(19\d{2}|20\d{2})\b", name)
    if not known.get("year") and year:
        known["year"] = int(year[0])
    explicit = re.search(r"(?i)tmdb(?:id)?[- _]?(\d+)", asset["relative_path"])
    stored = re.fullmatch(r"tmdb:(movie|show):(\d+)", asset.get("identity_key") or "")
    if not known.get("provider_id") and (explicit or stored):
        if explicit:
            known["provider_id"] = explicit[1]
        elif stored:
            known["provider_id"] = stored[2]
    known.setdefault("edition", "Unknown")
    provider_id = known.get("provider_id")
    if not provider_id and not known.get("confirmed"):
        title = re.split(r"(?i)\b(?:19\d{2}|20\d{2}|S\d+E\d+)\b", name.replace(".", " "))[0].strip(
            " -_"
        )
        candidates = worker.tmdb.search(title, known.get("media_type", "movie"), known.get("year"))
        with worker.db.transaction() as conn:
            conn.execute(
                insert(p.evidence_tables["identity_candidates"]).values(
                    asset_id=asset["id"],
                    data={
                        "candidates": candidates,
                        "fingerprint": asset["fingerprint"],
                        "source": "TMDb-search",
                        "status": "NeedsReview",
                    },
                )
            )
        raise GateError("AMBIGUOUS_IDENTITY" if candidates else "IDENTITY_UNAVAILABLE")
    from app.english_metadata import propose

    return propose(worker, asset, known, policy or library_policy.defaults())


def analyze(worker: Any, task: dict[str, Any]) -> None:
    db = worker.db
    db.reserve(task, ["library-scan"])
    worker.nas_health()
    job = db.one(select(p.jobs).where(p.jobs.c.id == task["job_id"]))
    if job["revision"]:
        return
    kind = job["kind"].removeprefix("BULK_")
    scope = job["data"]["scope"]
    query = select(p.assets).where(p.assets.c.workflow_state == "ACTIVE")
    if scope["asset_ids"]:
        query = query.where(p.assets.c.id.in_(scope["asset_ids"]))
    if scope["category"]:
        query = query.where(p.assets.c.category == scope["category"])
    entries = []
    planning_torrents = worker.qbt.all()
    catalog_folders: dict[str, list[dict[str, Any]]] = {}
    for row in db.rows(
        select(
            p.assets.c.id, p.assets.c.relative_path, p.assets.c.data["identity"].label("identity")
        ).where(p.assets.c.workflow_state == "ACTIVE")
    ):
        catalog_folders.setdefault(
            str(PurePosixPath("Library/" + row["relative_path"]).parent), []
        ).append(row)
    for asset in db.rows(query.order_by(p.assets.c.id)):
        existing = db.rows(
            select(p.maintenance_files).where(
                p.maintenance_files.c.job_id == job["id"],
                p.maintenance_files.c.asset_id == asset["id"],
            )
        )
        if existing:
            entries.append(
                {"asset_id": asset["id"], **existing[0]["data"], "state": existing[0]["state"]}
            )
            continue
        state = "Planned"
        d: dict[str, Any] = {
            "asset_revision": asset["revision"],
            "fingerprint": asset["fingerprint"],
            "source": "Library/" + asset["relative_path"],
            "title": asset["title"],
            "action": kind,
            "warnings": [],
            "manifest_id": p.uid(),
        }
        try:
            if asset["availability"] != "AVAILABLE":
                raise GateError("ASSET_MISSING")
            source = contained(worker.cfg.nas_root, d["source"], existing=True)
            if sha256(source) != asset["fingerprint"]:
                raise GateError("ASSET_CHANGED")
            dependency_guard(worker, asset, planning_torrents)
            d["files"] = associated(worker, asset)
            known_paths = {e["source"] for e in d["files"]}
            d["preserved_sidecars"] = [
                x.relative_to(worker.cfg.nas_root).as_posix()
                for x in source.parent.iterdir()
                if x.suffix.lower() in {".nfo", ".jpg", ".png"}
                and x.relative_to(worker.cfg.nas_root).as_posix() not in known_paths
            ]
            if kind == "NORMALIZE":
                d["identity"] = identity(worker, asset, job["data"]["policy"])
                candidates = db.rows(
                    select(p.evidence_tables["subtitle_candidates"])
                    .where(
                        p.evidence_tables["subtitle_candidates"].c.asset_id == asset["id"],
                        p.evidence_tables["subtitle_candidates"].c.data["status"].astext
                        == "Accepted",
                    )
                    .order_by(p.evidence_tables["subtitle_candidates"].c.created_at.desc())
                    .limit(1)
                )
                if candidates:
                    d["subtitle_candidate"] = {
                        "id": candidates[0]["id"],
                        "data": candidates[0]["data"],
                    }
                    subkind = candidates[0]["data"].get("kind", "normal")
                    suffix = ".bg.srt" if subkind == "normal" else f".bg.{subkind}.srt"
                    primary = source.with_suffix(suffix)
                    if primary.exists():
                        owned = db.rows(
                            select(p.sidecars).where(
                                p.sidecars.c.root == "nas",
                                p.sidecars.c.relative_path
                                == primary.relative_to(worker.cfg.nas_root).as_posix(),
                                p.sidecars.c.locked.is_(False),
                            )
                        )
                        if not owned or owned[0]["sha256"] != sha256(primary):
                            raise GateError("SUBTITLE_PRIMARY_NOT_OWNED")
                rendered = library_policy.render(
                    job["data"]["policy"],
                    asset["category"],
                    d["identity"],
                    asset["data"],
                    asset["relative_path"],
                )
                target = "Library/" + rendered["path"]
                d["target"] = target
                from app.library_enrichment import proposals

                d["sidecar_proposals"] = proposals(worker, asset, d["identity"], target)
                old = PurePosixPath(d["source"])
                new = PurePosixPath(target)
                if d["identity"]["media_type"] in {"movie", "concert"}:
                    for peer in catalog_folders.get(str(new.parent), []):
                        other = peer["identity"] or {}
                        if peer["id"] != asset["id"] and (
                            not other.get("confirmed")
                            or (
                                other.get("provider_id")
                                and d["identity"].get("provider_id")
                                and other["provider_id"] != d["identity"]["provider_id"]
                            )
                        ):
                            raise GateError("WORK_DIRECTORY_IDENTITY_CONFLICT")
                for entry in d["files"]:
                    path = PurePosixPath(entry["source"])
                    entry["target"] = (
                        entry["source"]
                        if entry["source"].startswith(".vimag-subtitle-history/")
                        else (
                            target
                            if entry["video"]
                            else str(new.parent / (new.stem + path.name[len(old.stem) :]))
                            if path.name.startswith(old.stem + ".")
                            else str(new.parent / path.name)
                        )
                    )
                for proposal in d["sidecar_proposals"]:
                    for entry in d["files"]:
                        if not entry["video"] and entry.get("target") == proposal["target"]:
                            owned = db.rows(
                                select(p.sidecars).where(
                                    p.sidecars.c.root == "nas",
                                    p.sidecars.c.relative_path == entry["source"],
                                    p.sidecars.c.sha256 == entry["sha256"],
                                    p.sidecars.c.locked.is_(False),
                                )
                            )
                            if not owned:
                                raise GateError("SIDECAR_OWNERSHIP_REVIEW")
                            proposal["expected"] = entry["sha256"]
                d["phases"] = ["Identity", "Hierarchy", "Subtitles", "Jellyfin"]
                # Preserve unknown directory-owned sidecars by requiring separate ownership review.
                if old.parent != new.parent and any(
                    x.name in {"movie.nfo", "poster.jpg", "backdrop.jpg", "tvshow.nfo"}
                    for x in source.parent.iterdir()
                ):
                    selected_paths = {e["source"] for e in d["files"]}
                    if any(
                        x.relative_to(worker.cfg.nas_root).as_posix() not in selected_paths
                        for x in source.parent.iterdir()
                        if x.name in {"movie.nfo", "poster.jpg", "backdrop.jpg", "tvshow.nfo"}
                    ):
                        raise GateError("SHARED_SIDECARS_REQUIRE_REVIEW")
            elif kind == "QUARANTINE":
                for ix, entry in enumerate(d["files"]):
                    entry["target"] = (
                        ".vimag-quarantine/"
                        + d["manifest_id"]
                        + "/"
                        + str(ix)
                        + "/"
                        + PurePosixPath(entry["source"]).name
                    )
                d["target"] = next(e["target"] for e in d["files"] if e["video"])
            elif kind != "DELETE":
                raise GateError("INVALID_MAINTENANCE_KIND")
            for entry in d["files"]:
                if entry.get("target") and entry["target"] != entry["source"]:
                    collision(contained(worker.cfg.nas_root, entry["target"]))
            entries.append({"asset_id": asset["id"], **d, "state": state})
        except (GateError, OSError) as error:
            state = "NeedsReview"
            d["error_code"] = (
                error.code if isinstance(error, GateError) else "FILESYSTEM_UNAVAILABLE"
            )
            entries.append({"asset_id": asset["id"], **d, "state": state})
        with db.transaction() as conn:
            db.assert_lease(conn, task)
            conn.execute(
                pg_insert(p.maintenance_files)
                .values(job_id=job["id"], asset_id=asset["id"], state=state, data=d)
                .on_conflict_do_nothing()
            )
    # Detect case-folded composite collisions across the full plan, not just per directory page.
    targets: dict[str, list[str]] = {}
    for entry in entries:
        for file in entry.get("files", []):
            if file.get("target"):
                targets.setdefault(file["target"].casefold(), []).append(entry["asset_id"])
    conflicted = {aid for ids in targets.values() if len(ids) > 1 for aid in ids}
    work_folders: dict[str, list[tuple[str, str]]] = {}
    for entry in entries:
        if kind == "NORMALIZE" and entry.get("target") and entry.get("identity"):
            work_identity = entry["identity"]
            signature = digest(
                [
                    work_identity.get("media_type"),
                    work_identity.get("provider_id") or work_identity.get("title"),
                    work_identity.get("year"),
                ]
            )
            work_folders.setdefault(
                str(PurePosixPath(entry["target"]).parent).casefold(), []
            ).append((entry["asset_id"], signature))
    conflicted |= {
        aid
        for group in work_folders.values()
        if len({sig for _, sig in group}) > 1
        for aid, _ in group
    }
    with db.transaction() as conn:
        for entry in entries:
            if entry["asset_id"] in conflicted:
                entry["state"], entry["error_code"] = "NeedsReview", "PLAN_DESTINATION_COLLISION"
                conn.execute(
                    update(p.maintenance_files)
                    .where(
                        p.maintenance_files.c.job_id == job["id"],
                        p.maintenance_files.c.asset_id == entry["asset_id"],
                    )
                    .values(
                        state="NeedsReview",
                        data={k: v for k, v in entry.items() if k not in {"asset_id", "state"}},
                    )
                )
        data = {
            "action": kind,
            "policy_revision": job["data"]["policy_revision"],
            "policy": job["data"]["policy"],
            "entries": entries,
        }
        conn.execute(
            insert(p.plans).values(job_id=job["id"], revision=1, sha256=digest(data), data=data)
        )
        conn.execute(
            update(p.jobs)
            .where(p.jobs.c.id == job["id"])
            .values(revision=1, state="AwaitingApproval")
        )
        db.event(conn, "worker", "MAINTENANCE_PLAN_READY", job["id"], {"count": len(entries)})


def effect(
    worker: Any,
    task: dict[str, Any],
    plan: dict[str, Any],
    entry: dict[str, Any],
    kind: str,
    resources: list[str],
) -> None:
    db = worker.db
    op, fresh = db.intent(task, plan, kind, entry["source"], entry)
    source = contained(worker.cfg.nas_root, entry["source"])
    target = contained(worker.cfg.nas_root, entry["target"]) if entry.get("target") else None
    if op["status"] == "VERIFIED":
        if source != target and source.exists():
            raise GateError("SOURCE_REAPPEARED_AFTER_OPERATION", "RecoveryRequired")
        if target and (not target.is_file() or sha256(target) != entry["sha256"]):
            raise GateError("DESTINATION_CHANGED", "RecoveryRequired")
        return
    if target == source:
        if sha256(source) != entry["sha256"]:
            raise GateError("ASSET_CHANGED", "RecoveryRequired")
        db.op_status(op, "VERIFIED")
        return
    if source.exists() and (
        sha256(source) != entry["sha256"]
        or source.stat().st_size != entry["size"]
        or source.stat().st_mtime_ns != entry["mtime_ns"]
    ):
        raise GateError("MANIFEST_CHANGED", "RecoveryRequired")
    if fresh or op["status"] == "PREPARED":
        if not source.is_file() or source.stat().st_mtime_ns != entry["mtime_ns"]:
            raise GateError("MANIFEST_CHANGED", "ReplanRequired")
        if target:
            collision(target)
        db.op_status(op, "COMMAND_REQUESTED")
    elif not target and not source.exists() and op["status"] != "COMMAND_REQUESTED":
        raise GateError("DELETE_RECONCILE_UNKNOWN", "RecoveryRequired")
    worker.fence(task, resources)
    if target:
        if not target.exists():
            if not source.exists():
                raise GateError("MOVE_RECONCILE_UNKNOWN", "RecoveryRequired")
            target.parent.mkdir(parents=True, exist_ok=True)
            contained(worker.cfg.nas_root, entry["target"])
            os.link(source, target)
        if sha256(target) != entry["sha256"]:
            raise GateError("DESTINATION_CHANGED", "RecoveryRequired")
    if source.exists():
        contained(worker.cfg.nas_root, entry["source"], existing=True)
        if sha256(source) != entry["sha256"]:
            raise GateError("MANIFEST_CHANGED", "RecoveryRequired")
        worker.fence(task, resources)
        source.unlink()  # Exactly one journaled, confirmed manifest entry; never recursive.
    if source.exists() or target and sha256(target) != entry["sha256"]:
        raise GateError("FILESYSTEM_POSTCONDITION_FAILED", "RecoveryRequired")
    db.op_status(
        op, "VERIFIED", {"absent": not source.exists(), "destination_verified": bool(target)}
    )


def execute(worker: Any, task: dict[str, Any]) -> bool:
    db = worker.db
    worker.write_gate()
    worker.nas_health()
    db.reserve(task, ["library-scan"])
    job = db.one(select(p.jobs).where(p.jobs.c.id == task["job_id"]))
    plan = db.one(
        select(p.plans).where(p.plans.c.job_id == job["id"], p.plans.c.revision == job["revision"])
    )
    kind = job["kind"].removeprefix("BULK_")
    if not db.rows(
        select(p.approvals).where(
            p.approvals.c.plan_id == plan["id"],
            p.approvals.c.sha256 == plan["sha256"],
            p.approvals.c.action == "APPROVE_" + kind,
        )
    ):
        raise GateError("MAINTENANCE_APPROVAL_REQUIRED")
    files = db.rows(
        select(p.maintenance_files)
        .where(p.maintenance_files.c.job_id == job["id"])
        .order_by(p.maintenance_files.c.id)
    )
    for file in files:
        current = db.one(select(p.jobs).where(p.jobs.c.id == job["id"]))
        if current["paused"]:
            worker.state(job["id"], "Paused", 4)
            return True
        if current["data"].get("cancel_remaining"):
            if file["state"] not in DONE:
                update_file(db, file, state="Cancelled")
            continue
        if file["state"] in DONE:
            continue
        d = file["data"]
        task["finish_current_file"] = True
        resources = ["library-scan", "asset:" + file["asset_id"]] + [
            "destination:" + e.get("target", e["source"]).casefold() for e in d["files"]
        ]
        try:
            db.reserve(task, resources)
            asset = db.one(select(p.assets).where(p.assets.c.id == file["asset_id"]))
            if kind == "NORMALIZE":
                expected = library_policy.render(
                    job["data"]["policy"],
                    asset["category"],
                    d["identity"],
                    asset["data"],
                    asset["relative_path"],
                )
                if "Library/" + expected["path"] != d["target"]:
                    raise GateError("ENGLISH_PLAN_TARGET_DRIFT")
            if file["phase"] == 0:
                if (
                    asset["revision"] != d["asset_revision"]
                    or asset["fingerprint"] != d["fingerprint"]
                ):
                    raise GateError("ASSET_REVISION_STALE")
                # Validate the entire exact manifest before the first physical side effect.
                for entry in d["files"]:
                    path = contained(worker.cfg.nas_root, entry["source"], existing=True)
                    if (
                        sha256(path) != entry["sha256"]
                        or path.stat().st_mtime_ns != entry["mtime_ns"]
                    ):
                        raise GateError("MANIFEST_CHANGED")
                update_file(db, file, state="Running", phase=1, attempts=file["attempts"] + 1)
            worker.state(
                job["id"], "Running", 4, {"phase": "Hierarchy" if kind == "NORMALIZE" else kind}
            )
            if file["phase"] < 2:
                # Resume with sources which may already be moved/deleted; never infer no deps from absence.
                dependency_guard(worker, asset, plan_id=plan["id"])
                for entry in d["files"]:
                    effect(worker, task, plan, entry, kind, resources)
                with db.transaction() as conn:
                    if kind == "DELETE":
                        conn.execute(
                            pg_insert(p.tombstones)
                            .values(
                                asset_id=asset["id"],
                                job_id=job["id"],
                                data={
                                    "path": asset["relative_path"],
                                    "fingerprint": asset["fingerprint"],
                                    "plan": plan["sha256"],
                                },
                            )
                            .on_conflict_do_nothing()
                        )
                        conn.execute(
                            update(p.assets)
                            .where(p.assets.c.id == asset["id"])
                            .values(workflow_state="DELETED", revision=p.assets.c.revision + 1)
                        )
                    elif kind == "QUARANTINE":
                        conn.execute(
                            pg_insert(p.quarantine)
                            .values(
                                id=d["manifest_id"],
                                asset_id=asset["id"],
                                plan_sha256=plan["sha256"],
                                state="QUARANTINED",
                                data={**d, "bulk": True, "job_id": job["id"]},
                            )
                            .on_conflict_do_nothing()
                        )
                        conn.execute(
                            update(p.assets)
                            .where(p.assets.c.id == asset["id"])
                            .values(workflow_state="QUARANTINED", revision=p.assets.c.revision + 1)
                        )
                    else:
                        data = {
                            **asset["data"],
                            "identity": d["identity"],
                            "category": asset["category"],
                        }
                        rel = d["target"].removeprefix("Library/")
                        conn.execute(
                            update(p.assets)
                            .where(p.assets.c.id == asset["id"])
                            .values(
                                relative_path=rel,
                                data=data,
                                revision=p.assets.c.revision + 1,
                                **catalogue.normalized(rel, data),
                            )
                        )
                        for entry in d["files"]:
                            conn.execute(
                                update(p.sidecars)
                                .where(
                                    p.sidecars.c.root == "nas",
                                    p.sidecars.c.relative_path == entry["source"],
                                )
                                .values(relative_path=entry["target"])
                            )
                    conn.execute(
                        update(p.maintenance_files)
                        .where(p.maintenance_files.c.id == file["id"])
                        .values(phase=2)
                    )
                    db.event(
                        conn,
                        "worker",
                        kind + "_FILESYSTEM_VERIFIED",
                        job["id"],
                        {"file_id": file["id"]},
                    )
            warnings = list(d.get("warnings", []))
            if kind == "NORMALIZE" and file["phase"] < 3:
                from app.library_enrichment import apply
                from app.subtitle_history import improve

                current_asset = db.one(select(p.assets).where(p.assets.c.id == file["asset_id"]))
                apply(worker, task, plan, current_asset, d.get("sidecar_proposals", []), resources)

                warning = improve(worker, task, plan, file, resources)
                if warning:
                    warnings.append(warning)
                if d.get("subtitle_candidate"):
                    latest_asset = db.one(select(p.assets).where(p.assets.c.id == file["asset_id"]))
                    subkind = d["subtitle_candidate"]["data"].get("kind", "normal")
                    suffix = ".bg.srt" if subkind == "normal" else f".bg.{subkind}.srt"
                    subpath = str(PurePosixPath(d["target"]).with_suffix(suffix)).removeprefix(
                        "Library/"
                    )
                    mapping = {
                        e["source"].removeprefix("Library/"): e["target"].removeprefix("Library/")
                        for e in d["files"]
                    }
                    external = [
                        {**s, "path": mapping.get(s["path"], s["path"])}
                        for s in latest_asset["data"].get("external_subtitles", [])
                        if mapping.get(s["path"], s["path"]) != subpath
                    ]
                    external.append(
                        {"path": subpath, "language": "bg", "kind": subkind, "source": "ViMag"}
                    )
                    data = {**latest_asset["data"], "external_subtitles": external}
                    with db.transaction() as conn:
                        conn.execute(
                            update(p.assets)
                            .where(p.assets.c.id == file["asset_id"])
                            .values(
                                data=data,
                                revision=p.assets.c.revision + 1,
                                **catalogue.normalized(latest_asset["relative_path"], data),
                            )
                        )
                update_file(db, file, phase=3, data={**d, "warnings": warnings})
            worker.jellyfin.refresh()
            if kind == "NORMALIZE":
                final_path = contained(worker.cfg.nas_root, d["target"], existing=True)
                if sha256(final_path) != d["fingerprint"]:
                    raise GateError("NAS_FINAL_INTEGRITY_FAILED", "RecoveryRequired")
                expected = {
                    **d["identity"],
                    "bg": asset["data"].get("bg"),
                    "jellyfin_path": worker.cfg.jellyfin_library_root.rstrip("/")
                    + "/"
                    + d["target"].removeprefix("Library/"),
                }
                if d.get("subtitle_candidate"):
                    subkind = d["subtitle_candidate"]["data"].get("kind", "normal")
                    suffix = ".bg.srt" if subkind == "normal" else f".bg.{subkind}.srt"
                    expected["subtitle"] = "Synchronized"
                    expected["subtitle_path"] = str(
                        PurePosixPath(expected["jellyfin_path"]).with_suffix(suffix)
                    )
                if not worker.jellyfin.recognized(expected):
                    update_file(db, file, state="PublishPending", phase=3)
                    continue
            update_file(
                db,
                file,
                state="NoChange"
                if kind == "NORMALIZE"
                and d["source"] == d["target"]
                and not d.get("subtitle_candidate")
                and all(s["expected"] == s["sha256"] for s in d.get("sidecar_proposals", []))
                else "CompletedWithWarnings"
                if warnings
                else "Completed",
                phase=4,
                data={**d, "warnings": warnings},
            )
        except (GateError, OSError) as error:
            if isinstance(error, GateError) and error.code in {
                "LEASE_LOST",
                "RESOURCE_LEASE_LOST",
                "LEASE_HEARTBEAT_FAILED",
                "WRITE_GATE_CLOSED",
            }:
                raise
            state = (
                "RecoveryRequired"
                if isinstance(error, GateError) and error.state == "RecoveryRequired"
                else "NeedsReview"
                if isinstance(error, GateError) and error.state in {"NeedsReview", "ReplanRequired"}
                else "Failed"
            )
            update_file(
                db,
                file,
                state=state,
                data={
                    **d,
                    "error_code": error.code
                    if isinstance(error, GateError)
                    else "FILESYSTEM_FAILED",
                },
            )
    remaining = db.rows(
        select(p.maintenance_files).where(p.maintenance_files.c.job_id == job["id"])
    )
    states = {f["state"] for f in remaining}
    if "PublishPending" in states:
        worker.state(job["id"], "PublishPending", 6)
        return False
    state = (
        "Cancelled"
        if "Cancelled" in states
        else "NeedsReview"
        if states & {"NeedsReview", "Failed", "RecoveryRequired"}
        else "CompletedWithWarnings"
        if "CompletedWithWarnings" in states or any(f["data"].get("warnings") for f in remaining)
        else "Completed"
    )
    worker.state(job["id"], state, 7)
    return True


def restore(worker: Any, task: dict[str, Any]) -> None:
    db = worker.db
    worker.write_gate()
    worker.nas_health()
    plan = db.one(select(p.plans).where(p.plans.c.job_id == task["job_id"]))
    d = plan["data"]
    resources = ["library-scan", "asset:" + d["asset_id"]]
    db.reserve(task, resources)
    manifest = db.one(select(p.quarantine).where(p.quarantine.c.id == d["manifest_id"]))
    if manifest["state"] == "RESTORED":
        for entry in d["files"]:
            target = contained(worker.cfg.nas_root, entry["target"], existing=True)
            if sha256(target) != entry["sha256"]:
                raise GateError("RESTORE_DESTINATION_CHANGED", "RecoveryRequired")
        worker.jellyfin.refresh()
        worker.state(task["job_id"], "MaintenanceVerified", 7)
        return
    asset = db.one(select(p.assets).where(p.assets.c.id == d["asset_id"]))
    video = next(e for e in d["files"] if e["video"])
    if contained(worker.cfg.nas_root, video["source"]).exists():
        dependency_guard(worker, asset, plan_id=plan["id"], source_rel=video["source"])
    for entry in d["files"]:
        effect(worker, task, plan, entry, "RESTORE", resources)
    with db.transaction() as conn:
        conn.execute(
            update(p.quarantine)
            .where(p.quarantine.c.id == d["manifest_id"])
            .values(state="RESTORED")
        )
        conn.execute(
            update(p.assets)
            .where(p.assets.c.id == d["asset_id"])
            .values(
                workflow_state="ACTIVE", availability="AVAILABLE", revision=p.assets.c.revision + 1
            )
        )
        db.event(conn, "worker", "QUARANTINE_RESTORED", task["job_id"])
    worker.jellyfin.refresh()
    worker.state(task["job_id"], "MaintenanceVerified", 7)


def restore_group(worker: Any, task: dict[str, Any]) -> None:
    db = worker.db
    worker.write_gate()
    worker.nas_health()
    db.reserve(task, ["library-scan"])
    plan = db.one(select(p.plans).where(p.plans.c.job_id == task["job_id"]))
    if not db.rows(
        select(p.approvals).where(
            p.approvals.c.plan_id == plan["id"],
            p.approvals.c.sha256 == plan["sha256"],
            p.approvals.c.action == "APPROVE_RESTORE",
        )
    ):
        raise GateError("RESTORE_APPROVAL_REQUIRED")
    for file in db.rows(
        select(p.maintenance_files).where(p.maintenance_files.c.job_id == task["job_id"])
    ):
        if file["state"] == "Completed":
            continue
        resources = ["library-scan", "asset:" + file["asset_id"]]
        try:
            db.reserve(task, resources)
            asset = db.one(select(p.assets).where(p.assets.c.id == file["asset_id"]))
            video = next(e for e in file["data"]["files"] if e["video"])
            if contained(worker.cfg.nas_root, video["source"]).exists():
                dependency_guard(worker, asset, plan_id=plan["id"], source_rel=video["source"])
            for entry in file["data"]["files"]:
                effect(worker, task, plan, entry, "RESTORE", resources)
            with db.transaction() as conn:
                conn.execute(
                    update(p.quarantine)
                    .where(p.quarantine.c.id == file["data"]["manifest_id"])
                    .values(state="RESTORED")
                )
                conn.execute(
                    update(p.assets)
                    .where(p.assets.c.id == file["asset_id"])
                    .values(
                        workflow_state="ACTIVE",
                        availability="AVAILABLE",
                        revision=p.assets.c.revision + 1,
                    )
                )
                conn.execute(
                    update(p.maintenance_files)
                    .where(p.maintenance_files.c.id == file["id"])
                    .values(state="Completed", phase=4)
                )
                db.event(
                    conn, "worker", "QUARANTINE_RESTORED", task["job_id"], {"file_id": file["id"]}
                )
        except (GateError, OSError) as error:
            if isinstance(error, GateError) and error.code in {
                "LEASE_LOST",
                "RESOURCE_LEASE_LOST",
                "LEASE_HEARTBEAT_FAILED",
            }:
                raise
            update_file(
                db,
                file,
                state="NeedsReview",
                data={
                    **file["data"],
                    "error_code": error.code
                    if isinstance(error, GateError)
                    else "FILESYSTEM_FAILED",
                },
            )
    worker.jellyfin.refresh()
    failed = db.rows(
        select(p.maintenance_files.c.id).where(
            p.maintenance_files.c.job_id == task["job_id"],
            p.maintenance_files.c.state != "Completed",
        )
    )
    worker.state(task["job_id"], "NeedsReview" if failed else "MaintenanceVerified", 7)
