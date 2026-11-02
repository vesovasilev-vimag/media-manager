"""Explicit maintenance plans, live dependency recheck and reversible quarantine."""

from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import persistence as p
from app.domain import GateError, digest
from app.storage import contained, reversible_move, sha256


def worker_path(cfg: Any, qpath: str) -> Path:
    for prefix, root in [
        ("/library/", cfg.nas_root / "Library"),
        ("/torrent-store/", cfg.nas_root / ".vimag-torrent-store"),
        ("/downloads/complete/", cfg.staging_root),
    ]:
        if qpath.startswith(prefix):
            return contained(root, qpath[len(prefix) :], existing=True)
    raise GateError("DEPENDENCY_PATH_UNMAPPED")


def dependencies(
    worker: Any, asset: dict[str, Any], snapshot: list[Any] | None = None
) -> list[dict[str, str]]:
    result = []
    source = contained(
        worker.cfg.nas_root, asset.get("source") or "Library/" + asset["relative_path"]
    )
    size = source.stat().st_size if source.is_file() else asset.get("file_size_bytes")
    for torrent in worker.qbt.all() if snapshot is None else snapshot:
        for file in torrent.files:
            qpath = torrent.save_path.rstrip("/") + "/" + file["name"]
            if qpath == "/library/" + asset["relative_path"]:
                result.append(
                    {"torrent": digest(torrent.info_hash), "reason": "DIRECT_PAYLOAD_MAPPING"}
                )
                continue
            if size is not None and file["size"] != size:
                continue
            try:
                candidate = worker_path(worker.cfg, qpath)
                if sha256(candidate) == asset["fingerprint"]:
                    result.append(
                        {"torrent": digest(torrent.info_hash), "reason": "SHARED_CONTENT"}
                    )
            except (GateError, OSError):
                result.append(
                    {"torrent": digest(torrent.info_hash), "reason": "UNRESOLVED_DEPENDENCY"}
                )
    return result


def execute(worker: Any, task: dict[str, Any]) -> bool:
    db = worker.db
    job = db.one(select(p.jobs).where(p.jobs.c.id == task["job_id"]))
    plan = db.one(
        select(p.plans)
        .where(p.plans.c.job_id == task["job_id"])
        .order_by(p.plans.c.revision.desc())
    )
    d = plan["data"]
    verified_ops = db.rows(
        select(p.operations).where(
            p.operations.c.plan_id == plan["id"],
            p.operations.c.kind == d["action"],
            p.operations.c.status == "VERIFIED",
        )
    )
    if verified_ops:
        target = contained(worker.cfg.nas_root, d["target"], existing=True)
        if sha256(target) != d["fingerprint"]:
            raise GateError("MAINTENANCE_RECONCILE_FAILED", "RecoveryRequired")
        worker.jellyfin.refresh()
        worker.state(job["id"], "MaintenanceVerified", 7)
        return True
    if not db.rows(
        select(p.approvals).where(
            p.approvals.c.plan_id == plan["id"], p.approvals.c.sha256 == plan["sha256"]
        )
    ):
        raise GateError("MAINTENANCE_APPROVAL_REQUIRED")
    worker.write_gate()
    worker.nas_health()
    resources = [
        "library-scan",
        "destination:" + d["source"].casefold(),
        "destination:" + d["target"].casefold(),
    ]
    db.reserve(task, resources)
    asset = db.one(select(p.assets).where(p.assets.c.id == d["asset_id"]))
    if d["action"] in {"QUARANTINE", "NORMALIZE"} and dependencies(worker, asset):
        raise GateError("DEPENDENCY_BLOCKED")
    source = contained(worker.cfg.nas_root, d["source"])
    target = contained(worker.cfg.nas_root, d["target"])
    if d["action"] == "NORMALIZE" and source.parent != target.parent and source.parent.exists():
        if any(
            path.suffix.lower() in {".nfo", ".jpg", ".png", ".srt", ".ass", ".vtt"}
            for path in source.parent.iterdir()
        ):
            raise GateError("SIDECARS_REQUIRE_SEPARATE_PLAN")
    op, fresh = db.intent(task, plan, d["action"], d["asset_id"], d)
    if fresh:
        reversible_move(
            worker.cfg.nas_root,
            d["source"],
            d["target"],
            d["fingerprint"],
            lambda: worker.fence(task, resources),
        )
    elif source.exists() or not target.is_file() or sha256(target) != d["fingerprint"]:
        raise GateError("QUARANTINE_RECONCILE_REQUIRED", "RecoveryRequired")
    with db.transaction() as conn:
        if d["action"] == "QUARANTINE":
            conn.execute(
                pg_insert(p.quarantine)
                .values(
                    id=d["manifest_id"],
                    asset_id=d["asset_id"],
                    plan_sha256=plan["sha256"],
                    state="QUARANTINED",
                    data={
                        "source": d["source"],
                        "target": d["target"],
                        "fingerprint": d["fingerprint"],
                        "job_id": job["id"],
                    },
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            conn.execute(
                update(p.assets)
                .where(p.assets.c.id == asset["id"])
                .values(workflow_state="QUARANTINED", revision=p.assets.c.revision + 1)
            )
        elif d["action"] == "RESTORE":
            conn.execute(
                update(p.quarantine)
                .where(p.quarantine.c.id == d["manifest_id"])
                .values(state="RESTORED")
            )
            conn.execute(
                update(p.assets)
                .where(p.assets.c.id == asset["id"])
                .values(workflow_state="ACTIVE", revision=p.assets.c.revision + 1)
            )
        elif d["action"] == "NORMALIZE":
            conn.execute(
                update(p.assets)
                .where(p.assets.c.id == asset["id"])
                .values(
                    relative_path=d["target"].removeprefix("Library/"),
                    data={
                        **asset["data"],
                        "identity": d["identity"],
                        "normalization_verified": True,
                    },
                )
            )
        db.event(conn, "worker", d["action"] + "_VERIFIED", job["id"])
    db.op_status(op, "VERIFIED", {"content_verified": True, "restore_available": True})
    worker.state(job["id"], "MaintenanceVerified", 7)
    # Catalog must be refreshed independently. This is not an operational Import Completed claim.
    worker.jellyfin.refresh()
    return True
