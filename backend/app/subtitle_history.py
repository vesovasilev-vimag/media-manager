"""Immutable subtitle generations outside Jellyfin, one atomic primary publication."""

import hashlib
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import persistence as p
from app.domain import GateError, digest
from app.storage import atomic_sidecar, contained, sha256
from app.subtitles import OpenSubtitles, evaluate


def decode_text(content: bytes, declared: str | None = None) -> tuple[bytes, str]:
    try:
        value = content.decode("utf-8-sig")
        encoding = "UTF-8"
    except UnicodeDecodeError:
        if declared not in {"windows-1251", "cp1251"}:
            raise GateError("SUBTITLE_ENCODING_REVIEW") from None
        try:
            value = content.decode("cp1251")
        except UnicodeDecodeError:
            raise GateError("SUBTITLE_ENCODING_REVIEW") from None
        if not any("\u0400" <= c <= "\u04ff" for c in value):
            raise GateError("SUBTITLE_ENCODING_REVIEW") from None
        encoding = "Windows-1251"
    if "\ufffd" in value or "\x00" in value:
        raise GateError("SUBTITLE_ENCODING_REVIEW")
    return value.encode("utf-8"), encoding


def publish(
    worker: Any,
    task: dict[str, Any],
    plan: dict[str, Any],
    asset: dict[str, Any],
    content: bytes,
    evidence: dict[str, Any],
    resources: list[str],
    replay_key: str,
) -> None:
    db = worker.db
    kind = evidence.get("kind", "normal")
    if kind not in {"normal", "forced", "sdh"}:
        raise GateError("INVALID_SUBTITLE_KIND")
    suffix = ".bg.srt" if kind == "normal" else f".bg.{kind}.srt"
    rel = str(PurePosixPath("Library/" + asset["relative_path"]).with_suffix(suffix))
    primary = contained(worker.cfg.nas_root, rel)
    desired = hashlib.sha256(content).hexdigest()
    versions = db.rows(
        select(p.subtitle_versions)
        .where(p.subtitle_versions.c.asset_id == asset["id"])
        .order_by(p.subtitle_versions.c.generation.desc())
    )
    prior = next((v for v in versions if v["data"]["primary"] == rel), None)
    ops = db.rows(
        select(p.operations).where(
            p.operations.c.op_key
            == digest([task["job_id"], plan["sha256"], "SUBTITLE_PRIMARY", replay_key])
        )
    )
    if ops:
        op = ops[0]
        intent = op["intent"]
        if intent["sha256"] != desired:
            raise GateError("SUBTITLE_REPLAY_MISMATCH", "RecoveryRequired")
        if op["status"] == "VERIFIED":
            if not primary.is_file() or sha256(primary) != desired:
                raise GateError("SUBTITLE_PRIMARY_EXTERNALLY_CHANGED", "RecoveryRequired")
            return
    else:
        owned = db.rows(
            select(p.sidecars).where(
                p.sidecars.c.root == "nas",
                p.sidecars.c.relative_path == rel,
                p.sidecars.c.locked.is_(False),
            )
        )
        actual = sha256(primary) if primary.is_file() else None
        if primary.exists() and (not owned or owned[0]["sha256"] != actual):
            raise GateError("SUBTITLE_PRIMARY_NOT_OWNED")
        if actual == desired:
            return
        generation = (versions[0]["generation"] if versions else 0) + 1
        archive_root = f".vimag-subtitle-history/{asset['id']}/{generation}"
        history = []
        if actual:
            history.append({"source": rel, "sha256": actual})
        if prior:
            history.extend(prior["data"].get("history", []))
        history = [
            {**entry, "path": f"{archive_root}/{PurePosixPath(rel).stem}.ver-{ix + 2:02}.srt"}
            for ix, entry in enumerate(history)
        ]
        intent = {
            "primary": rel,
            "sha256": desired,
            "old_sha256": actual,
            "generation": generation,
            "history": history,
            "evidence": evidence,
            "blob": archive_root + "/primary.srt",
        }
        op, _ = db.intent(task, plan, "SUBTITLE_PRIMARY", replay_key, intent)

    def fence() -> None:
        worker.fence(task, resources)

    for entry in intent["history"]:
        target = contained(worker.cfg.nas_root, entry["path"])
        if not target.exists():
            source = contained(
                worker.cfg.nas_root, entry.get("source") or entry["path"], existing=True
            )
            if sha256(source) != entry["sha256"]:
                raise GateError("SUBTITLE_ARCHIVE_CHANGED", "RecoveryRequired")
            atomic_sidecar(
                worker.cfg.nas_root,
                entry["path"],
                source.read_bytes(),
                None,
                fence,
                ".vimag-sidecar-backups/" + op["id"],
            )
        elif sha256(target) != entry["sha256"]:
            raise GateError("SUBTITLE_ARCHIVE_COLLISION", "RecoveryRequired")
    blob = contained(worker.cfg.nas_root, intent["blob"])
    if not blob.exists():
        atomic_sidecar(
            worker.cfg.nas_root,
            intent["blob"],
            content,
            None,
            fence,
            ".vimag-sidecar-backups/" + op["id"],
        )
    elif sha256(blob) != desired:
        raise GateError("SUBTITLE_BLOB_CHANGED", "RecoveryRequired")
    db.op_status(op, "COMMAND_REQUESTED")
    if not primary.is_file() or sha256(primary) != desired:
        atomic_sidecar(
            worker.cfg.nas_root,
            rel,
            content,
            intent["old_sha256"],
            fence,
            ".vimag-sidecar-backups/" + op["id"] + "/primary.srt",
        )
    if sha256(primary) != desired:
        raise GateError("SUBTITLE_PRIMARY_READBACK_FAILED", "RecoveryRequired")
    stored = {
        **intent,
        "history": [
            {"source": e["path"], "path": e["path"], "sha256": e["sha256"]}
            for e in intent["history"]
        ],
    }
    with db.transaction() as conn:
        conn.execute(
            pg_insert(p.subtitle_versions)
            .values(asset_id=asset["id"], generation=intent["generation"], data=stored)
            .on_conflict_do_nothing()
        )
        conn.execute(
            pg_insert(p.sidecars)
            .values(
                root="nas",
                relative_path=rel,
                sha256=desired,
                data={"asset_id": asset["id"], "exclusive": True},
            )
            .on_conflict_do_update(
                index_elements=["root", "relative_path"],
                set_={"sha256": desired, "data": {"asset_id": asset["id"], "exclusive": True}},
            )
        )
        db.event(
            conn,
            "worker",
            "SUBTITLE_PRIMARY_PUBLISHED",
            task["job_id"],
            {"generation": intent["generation"]},
        )
    db.op_status(op, "VERIFIED")


def improve(
    worker: Any,
    task: dict[str, Any],
    plan: dict[str, Any],
    file: dict[str, Any],
    resources: list[str],
) -> str | None:
    asset = worker.db.one(select(p.assets).where(p.assets.c.id == file["asset_id"]))
    candidate = file["data"].get("subtitle_candidate")
    if candidate:
        d = candidate["data"]
        content, encoding = decode_text(d["content"].encode(), "utf-8")
        media = {
            "fingerprint": asset["fingerprint"],
            "edition": file["data"]["identity"].get("edition"),
            "duration": float(asset["data"]["probe"]["format"]["duration"]),
        }
        result = evaluate(d, media, content, d.get("verification"))
        if result["status"] != "Synchronized":
            raise GateError("SUBTITLE_TIMING_NOT_VERIFIED")
        publish(
            worker,
            task,
            plan,
            asset,
            content,
            {
                **result,
                "encoding": encoding,
                "candidate_id": candidate["id"],
                "kind": d.get("kind", "normal"),
            },
            resources,
            file["id"],
        )
        return None
    # Provider searches are explicitly recorded; metadata/FPS equality alone never replaces a primary.
    if worker.cfg.secret(worker.cfg.subtitle_api_key_file).get_secret_value():
        identity = file["data"]["identity"]
        try:
            candidates = OpenSubtitles(worker.cfg).search(
                identity.get("provider_id", ""),
                identity["media_type"],
                identity.get("season"),
                (identity.get("episodes") or [None])[0],
            )
        except GateError:
            return "SUBTITLE_PROVIDER_UNAVAILABLE"
        with worker.db.transaction() as conn:
            for candidate in candidates:
                conn.execute(
                    insert(p.evidence_tables["subtitle_candidates"]).values(
                        asset_id=asset["id"],
                        data={
                            **candidate,
                            "fingerprint": asset["fingerprint"],
                            "edition": identity.get("edition"),
                            "phase": "ImproveAndSupplement",
                        },
                    )
                )
        return "SUBTITLE_CANDIDATES_NEED_TIMING_REVIEW" if candidates else "SUBTITLE_UNAVAILABLE"
    return "SUBTITLE_PROVIDER_UNAVAILABLE"


def restore(worker: Any, task: dict[str, Any]) -> None:
    db = worker.db
    asset = db.one(select(p.assets).where(p.assets.c.id == task["data"]["asset_id"]))
    worker.write_gate()
    worker.nas_health()
    resources = ["library-scan", "asset:" + asset["id"]]
    db.reserve(task, resources)
    version = db.one(
        select(p.subtitle_versions).where(
            p.subtitle_versions.c.asset_id == asset["id"],
            p.subtitle_versions.c.generation == task["data"]["generation"],
        )
    )
    blob = contained(worker.cfg.nas_root, version["data"]["blob"], existing=True)
    if sha256(blob) != version["data"]["sha256"]:
        raise GateError("SUBTITLE_ARCHIVE_CHANGED")
    path = contained(worker.cfg.nas_root, "Library/" + asset["relative_path"], existing=True)
    if sha256(path) != task["data"]["fingerprint"]:
        raise GateError("SUBTITLE_VIDEO_CHANGED")
    plan = db.one(select(p.plans).where(p.plans.c.job_id == task["job_id"]))
    publish(
        worker,
        task,
        plan,
        asset,
        blob.read_bytes(),
        {
            "restored_generation": version["generation"],
            "kind": version["data"]["evidence"].get("kind", "normal"),
        },
        resources,
        task["id"],
    )
    worker.jellyfin.refresh()
    worker.state(task["job_id"], "MaintenanceVerified", 7)
