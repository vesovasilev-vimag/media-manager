"""Single logical Worker, PostgreSQL queue, reconcile before every effect."""

import re
import signal
import time
from pathlib import Path, PurePosixPath
from threading import Event, Thread
from typing import Any
from uuid import uuid4
from xml.etree.ElementTree import Element, SubElement, tostring

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import persistence as p
from app.adapters import Jellyfin, QBittorrent, TMDb, probe
from app.domain import (
    CATEGORIES,
    TERMINAL,
    GateError,
    Identity,
    Torrent,
    bg_state,
    compare,
    digest,
    final_state,
    identity_dict,
    name_for,
    seeding_capable,
)
from app.observability import emit
from app.settings import Settings
from app.storage import (
    atomic_sidecar,
    collision,
    contained,
    hardlink,
    hardlink_scratch,
    mount_health,
    read_nfo,
    sha256,
)
from app.subtitles import OpenSubtitles

VIDEO = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts"}


class Worker:
    def __init__(self, db: p.Database, qbt: Any, jellyfin: Any, tmdb: Any, probe_fn: Any = probe):
        self.db, self.cfg = db, db.config
        self.qbt, self.jellyfin, self.tmdb = qbt, jellyfin, tmdb
        self.probe = probe_fn
        self.owner = str(uuid4())
        self.running = True

    def health(self, value: dict[str, Any]) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                pg_insert(p.settings_table)
                .values(key="worker_health", value={**value, "time": p.now().isoformat()})
                .on_conflict_do_update(
                    index_elements=["key"], set_={"value": {**value, "time": p.now().isoformat()}}
                )
            )

    def state(self, job_id: str, state: str, step: int, data: dict[str, Any] | None = None) -> None:
        with self.db.transaction() as conn:
            row = (
                conn.execute(select(p.jobs).where(p.jobs.c.id == job_id).with_for_update())
                .mappings()
                .one()
            )
            conn.execute(
                update(p.jobs)
                .where(p.jobs.c.id == job_id)
                .values(
                    state=state, step=step, updated_at=p.now(), data={**row["data"], **(data or {})}
                )
            )
            if row["state"] != state:
                self.db.event(conn, "worker", state, job_id, {"step": step})
        emit("JOB_STATE", job_id=job_id, step=step, phase="transition", result=state)

    def update_item(self, item_id: str, values: dict[str, Any]) -> None:
        with self.db.transaction() as conn:
            row = (
                conn.execute(select(p.items).where(p.items.c.id == item_id).with_for_update())
                .mappings()
                .one()
            )
            conn.execute(
                update(p.items)
                .where(p.items.c.id == item_id)
                .values(data={**row["data"], **values})
            )

    def evidence(
        self,
        kind: str,
        data: dict[str, Any],
        item_id: str | None = None,
        asset_id: str | None = None,
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                insert(p.evidence_tables[kind]).values(
                    item_id=item_id, asset_id=asset_id, data=data
                )
            )

    def nas_health(self, required: int = 0) -> dict[str, Any]:
        return mount_health(
            self.cfg.nas_root,
            self.cfg.nas_mount_source,
            production=self.cfg.environment == "production",
            required_bytes=required,
            min_free=self.cfg.min_free_bytes,
            min_percent=self.cfg.min_free_percent,
        )

    def write_gate(self, torrent_id: str | None = None) -> None:
        if not self.cfg.write_enabled:
            raise GateError("WRITE_GATE_CLOSED", "BlockedExternalDependency")
        if self.cfg.environment != "production":
            return
        gates = self.db.rows(
            select(p.settings_table).where(p.settings_table.c.key == "operational_authorization")
        )
        if not gates:
            raise GateError("OPERATIONAL_AUTHORIZATION_MISSING", "BlockedExternalDependency")
        proof = gates[0]["value"]
        required = [
            "backup_verified",
            "database_restore_verified",
            "mounts_verified",
            "jellyfin_token_rotated",
            "legacy_baseline_verified",
            "recovery_fixtures_verified",
        ]
        if not all(proof.get(k) is True for k in required) or not proof.get("authorized_by"):
            raise GateError("SAFETY_GATES_OPEN", "BlockedExternalDependency")
        if proof.get("mode") == "one_fixture":
            if not torrent_id or torrent_id != proof.get("torrent_instance_id"):
                raise GateError("OUTSIDE_ISOLATED_FIXTURE", "BlockedExternalDependency")
        elif proof.get("mode") != "production" or not all(
            proof.get(g) for g in ["G-01", "G-02", "G-03", "G-04", "G-05", "G-DB-01"]
        ):
            raise GateError("PRODUCTION_CUTOVER_UNAUTHORIZED", "BlockedExternalDependency")

    def fence(
        self, task: dict[str, Any], resources: list[str], torrent_id: str | None = None
    ) -> None:
        if task.get("heartbeat_failed"):
            raise GateError("LEASE_HEARTBEAT_FAILED", "Reconciling")
        self.write_gate(torrent_id)
        self.db.fence(task, resources)
        if task.get("job_id"):
            job = self.db.one(select(p.jobs).where(p.jobs.c.id == task["job_id"]))
            if job["paused"]:
                raise GateError("ORCHESTRATION_PAUSED", "Paused")
        if torrent_id:
            registered = self.db.one(select(p.torrents).where(p.torrents.c.id == torrent_id))
            if (
                registered["scope"] not in {"VIMAG_MANAGED", "TEST_FIXTURE"}
                or not registered["present"]
            ):
                raise GateError("TORRENT_NOT_OWNED", "RecoveryRequired")
            current = self.qbt.torrent(registered["info_hash"])
            if current.added_on != registered["added_on"] or current.auto_tmm:
                raise GateError("TORRENT_INSTANCE_DRIFT", "ReplanRequired")

    def poll(self) -> None:
        for row in self.db.rows(
            select(p.settings_table).where(p.settings_table.c.key.in_(["automation", "storage"]))
        ):
            value = row["value"]
            if row["key"] == "automation":
                self.cfg.poll_seconds = int(value.get("poll_seconds", self.cfg.poll_seconds))
                self.cfg.retry_budget = int(value.get("retry_budget", self.cfg.retry_budget))
            elif "min_free_gib" in value:
                self.cfg.min_free_bytes = int(value["min_free_gib"]) * 1024**3
        preferences = self.qbt.get("app/preferences")
        if preferences.get("use_category_paths_in_manual_mode") is not False:
            raise GateError("MANUAL_CATEGORY_PATHS_UNSAFE", "BlockedExternalDependency")
        observed = self.qbt.all()
        self.db.discover(observed, automatic=self.cfg.automatic_intake)
        jellyfin = "READY"
        try:
            if not self.jellyfin.health():
                jellyfin = "UNAVAILABLE"
        except GateError as error:
            jellyfin = error.code
        self.health(
            {
                "qbt": "READY",
                "jellyfin": jellyfin,
                "nas": self.nas_health(),
                "state": "READY" if jellyfin == "READY" else "DEGRADED",
            }
        )

    def inspect(self, task: dict[str, Any], torrent: Torrent) -> None:
        self.state(task["job_id"], "Inspecting", 2)
        existing = self.db.rows(select(p.items).where(p.items.c.job_id == task["job_id"]))
        for file in torrent.files:
            path = PurePosixPath(file["name"])
            if path.suffix.lower() not in VIDEO:
                continue
            if any(row["item_key"] == file["name"] for row in existing):
                continue
            source = contained(self.cfg.staging_root, file["name"], existing=True)
            if source.stat().st_size != file["size"]:
                raise GateError("SOURCE_SIZE_MISMATCH", "RecoveryRequired")
            fingerprint = sha256(source)
            analysis = self.probe(source)
            video = next(s for s in analysis["streams"] if s.get("codec_type") == "video")
            item_id = p.uid()
            parsed_episode = re.search(r"(?i)S(\d{1,3})E(\d{1,3})(?:-?E(\d{1,3}))?", path.stem)
            year_match = re.search(r"\b(19\d{2}|20\d{2})\b", path.stem)
            explicit_id = re.search(r"(?i)tmdb(?:id)?[- _]?(\d+)", path.stem)
            edition = (
                "Director's Cut"
                if re.search(r"(?i)director.?s?[ ._-]*cut", path.stem)
                else "Extended"
                if re.search(r"(?i)\bextended\b", path.stem)
                else "Theatrical"
            )
            part_match = re.search(r"(?i)\b(?:part|cd|disc)[ ._-]?(\d+)\b", path.stem)
            title = re.split(r"(?i)\b(?:19\d{2}|20\d{2}|S\d+E\d+)\b", path.stem.replace(".", " "))[
                0
            ].strip(" -_")
            media_type = (
                "show"
                if parsed_episode
                else "concert"
                if torrent.category == "concerts"
                else "movie"
            )
            if not existing:
                self.state(task["job_id"], "Inspecting", 2, {"title": title})
            candidates = []
            provider_state = None
            try:
                candidates = self.tmdb.search(
                    title, media_type, int(year_match[0]) if year_match else None
                )
            except GateError as error:
                provider_state = error.code
            from app.domain import match_identity

            selected = match_identity(
                candidates,
                explicit_id[1] if explicit_id else None,
                media_type,
                int(year_match[0]) if year_match else None,
            )
            identity = None
            if selected:
                identity = identity_dict(
                    Identity(
                        selected["title"],
                        selected["year"],
                        media_type,
                        selected["id"],
                        edition=edition,
                        part=int(part_match[1]) if part_match else None,
                        confirmed=True,
                        season=int(parsed_episode[1]) if parsed_episode else None,
                        episodes=list(
                            range(
                                int(parsed_episode[2]),
                                int(parsed_episode[3] or parsed_episode[2]) + 1,
                            )
                        )
                        if parsed_episode
                        else [],
                    )
                )
            data = {
                "source_name": file["name"],
                "size": file["size"],
                "fingerprint": fingerprint,
                "probe": analysis,
                "stream_keys": [
                    {"index": s.get("index"), "key": digest(s)}
                    for s in analysis["streams"]
                    if s.get("codec_type") == "audio"
                ],
                "bg": bg_state(analysis, fingerprint, []),
                "identity": identity,
                "candidates": candidates,
                "provider_state": provider_state,
                "quality_label": f"{video.get('height', 0)}p",
                "subtitle": "NeedsReview",
                "published": False,
                "integrity": False,
            }
            with self.db.transaction() as conn:
                conn.execute(
                    pg_insert(p.items)
                    .values(id=item_id, job_id=task["job_id"], item_key=file["name"], data=data)
                    .on_conflict_do_nothing(index_elements=["job_id", "item_key"])
                )
            self.evidence(
                "media_inspections", {"fingerprint": fingerprint, "probe": analysis}, item_id
            )
            for candidate in candidates:
                self.evidence("identity_candidates", candidate, item_id)
            self.db.heartbeat(task)
        if not self.db.rows(select(p.items.c.id).where(p.items.c.job_id == task["job_id"])):
            raise GateError("NO_IMPORTABLE_VIDEO")

    def plan(
        self, task: dict[str, Any], torrent: Torrent, registered: dict[str, Any]
    ) -> dict[str, Any]:
        job = self.db.one(select(p.jobs).where(p.jobs.c.id == task["job_id"]))
        existing = self.db.rows(
            select(p.plans).where(
                p.plans.c.job_id == task["job_id"], p.plans.c.revision == job["revision"]
            )
        )
        if existing:
            return existing[0]
        self.state(task["job_id"], "Comparing", 3)
        children = self.db.rows(select(p.items).where(p.items.c.job_id == task["job_id"]))
        entries = []
        approval_required = False
        for child in children:
            d = child["data"]
            if not d.get("identity"):
                raise GateError("IDENTITY_REVIEW_REQUIRED")
            identity = Identity(**d["identity"])
            destination = name_for(
                torrent.category,
                identity,
                d["quality_label"],
                d["bg"],
                Path(d["source_name"]).suffix.lower(),
            )
            identity_key = (
                f"tmdb:{identity.media_type}:{identity.provider_id}"
                if identity.provider_id
                else digest([identity.title, identity.year, identity.media_type])
            )
            old = self.db.rows(select(p.assets).where(p.assets.c.identity_key == identity_key))
            if old:
                approval_required = True
                for asset in old:
                    video = next(s for s in d["probe"]["streams"] if s.get("codec_type") == "video")
                    decision = compare(
                        {
                            **asset["data"],
                            "edition": asset["edition"],
                            "identity_key": identity_key,
                        },
                        {
                            "identity_key": identity_key,
                            "edition": identity.edition,
                            "integrity": True,
                            "bg": d["bg"],
                            "height": video.get("height"),
                            "codec": video.get("codec_name"),
                        },
                    )
                    self.evidence(
                        "quality_decisions",
                        {**decision, "existing_asset": asset["id"]},
                        child["id"],
                    )
                if not d.get("quality_review") or d["quality_review"]["decision"] == "NeedsReview":
                    raise GateError("QUALITY_REVIEW_REQUIRED")
                if d["quality_review"]["decision"] == "Skip":
                    raise GateError("IMPORT_SKIPPED", "CancelledBeforeMove")
            target = contained(self.cfg.nas_root, "Library/" + destination)
            collision(target)
            entries.append(
                {
                    "item_id": child["id"],
                    "source_name": d["source_name"],
                    "destination": destination,
                    "fingerprint": d["fingerprint"],
                    "size": d["size"],
                    "identity_key": identity_key,
                    "identity": d["identity"],
                    "bg": d["bg"],
                }
            )
        if len({e["destination"].casefold() for e in entries}) != len(entries):
            raise GateError("PLAN_COLLISION")
        simple = (
            len(torrent.files) == 1 and len(entries) == 1 and "/" not in torrent.files[0]["name"]
        )
        plan_data = {
            "torrent_id": registered["id"],
            "snapshot": torrent.stable(),
            "strategy": "SIMPLE" if simple else "TORRENT_STORE_HARDLINKS",
            "entries": entries,
            "qbt_destination": "/library/" + str(PurePosixPath(entries[0]["destination"]).parent)
            if simple
            else "/torrent-store/" + registered["id"],
            "qbt_names": [PurePosixPath(entries[0]["destination"]).name]
            if simple
            else [f["name"] for f in torrent.files],
            "policy_revision": 1,
            "mount_revision": 1,
            "approval_required": approval_required,
        }
        with self.db.transaction() as conn:
            revision = max(1, job["revision"] + 1)
            row = dict(
                conn.execute(
                    insert(p.plans)
                    .values(
                        job_id=task["job_id"],
                        revision=revision,
                        sha256=digest(plan_data),
                        data=plan_data,
                    )
                    .returning(p.plans)
                )
                .mappings()
                .one()
            )
            conn.execute(
                update(p.jobs)
                .where(p.jobs.c.id == task["job_id"])
                .values(revision=revision, state="AwaitingApproval")
            )
            self.db.event(conn, "worker", "PLAN_CREATED", task["job_id"], {"revision": revision})
        return row

    def dispatch(
        self,
        task: dict[str, Any],
        plan: dict[str, Any],
        resources: list[str],
        kind: str,
        data: dict[str, Any],
        endpoint: str,
        torrent: Torrent,
    ) -> tuple[dict[str, Any], bool]:
        self.fence(task, resources, plan["data"]["torrent_id"])
        op, fresh = self.db.intent(task, plan, kind, torrent.info_hash, data)
        if fresh:
            self.db.op_status(op, "COMMAND_REQUESTED")
            self.fence(task, resources, plan["data"]["torrent_id"])
            self.qbt.command(endpoint, torrent.info_hash, **data)
            if endpoint == "recheck":
                self.observe_recheck(task, plan, self.qbt.torrent(torrent.info_hash))
        return op, fresh

    def check_drift(
        self, current: Torrent, plan: dict[str, Any], registered: dict[str, Any]
    ) -> None:
        d = plan["data"]
        original = d["snapshot"]
        if (
            current.added_on != registered["added_on"]
            or current.category != original["category"]
            or current.auto_tmm
            or current.save_path.rstrip("/") not in {original["save_path"], d["qbt_destination"]}
        ):
            raise GateError("TORRENT_PLAN_DRIFT", "ReplanRequired")
        expected = original["files"]
        names = [f["name"] for f in current.files]
        original_names = [f["name"] for f in expected]
        if names not in [original_names, d["qbt_names"]] or [f["size"] for f in current.files] != [
            f["size"] for f in expected
        ]:
            raise GateError("TORRENT_FILES_CHANGED", "ReplanRequired")
        # All qBt user-policy fields except transient pause/queue must remain identical.
        for k, value in original["policy"].items():
            if k not in {"intentional_pause", "queued"} and current.policy.get(k) != value:
                raise GateError("SEEDING_POLICY_DRIFT", "ReplanRequired")

    def transfer(
        self, task: dict[str, Any], plan: dict[str, Any], registered: dict[str, Any]
    ) -> bool:
        d = plan["data"]
        if self.db.rows(
            select(p.operations.c.id).where(
                p.operations.c.kind == "MOVE",
                p.operations.c.status != "VERIFIED",
                p.operations.c.job_id != task["job_id"],
            )
        ):
            raise GateError("NAS_MOVE_IN_PROGRESS", "FailedRecoverable")
        resources = [
            "nas-move",
            "torrent:" + registered["id"],
            *["destination:" + e["destination"].casefold() for e in d["entries"]],
        ]
        self.db.reserve(task, resources)
        self.nas_health(sum(e["size"] for e in d["entries"]))
        self.write_gate(registered["id"])
        current = self.qbt.torrent(registered["info_hash"])
        self.check_drift(current, plan, registered)
        if not current.complete():
            if current.state in {"moving", "checkingUP", "checkingDL", "checkingResumeData"}:
                self.state(
                    task["job_id"], "Moving" if current.state == "moving" else "Rechecking", 4
                )
                self.observe_recheck(task, plan, current)
                return False
            raise GateError("TORRENT_INCOMPLETE", "RecoveryRequired")
        if d["strategy"] == "SIMPLE" and current.files[0]["name"] != d["qbt_names"][0]:
            self.state(task["job_id"], "RenameRequested", 4)
            op, fresh = self.dispatch(
                task,
                plan,
                resources,
                "RENAME",
                {"oldPath": d["snapshot"]["files"][0]["name"], "newPath": d["qbt_names"][0]},
                "renameFile",
                current,
            )
            actual = self.qbt.torrent(current.info_hash)
            if actual.files[0]["name"] == d["qbt_names"][0]:
                self.db.op_status(op, "VERIFIED", {"mapping_verified": True})
            elif not fresh:
                raise GateError("RENAME_OUTCOME_UNKNOWN", "RecoveryRequired")
            return False
        if current.save_path.rstrip("/") != d["qbt_destination"]:
            if d["strategy"] != "SIMPLE":
                hardlink_scratch(self.cfg.nas_root)
            self.state(
                task["job_id"],
                "MoveRequested",
                4,
                {"progress_bytes": None, "progress_source": "qbt-state-only"},
            )
            op, fresh = self.dispatch(
                task,
                plan,
                resources,
                "MOVE",
                {"location": d["qbt_destination"]},
                "setLocation",
                current,
            )
            if not fresh and current.state != "moving":
                raise GateError("MOVE_OUTCOME_UNKNOWN", "RecoveryRequired")
            return False
        self.state(task["job_id"], "Verifying", 4)
        for entry in d["entries"]:
            rel = (
                "Library/" + entry["destination"]
                if d["strategy"] == "SIMPLE"
                else ".vimag-torrent-store/" + registered["id"] + "/" + entry["source_name"]
            )
            path = contained(self.cfg.nas_root, rel, existing=True)
            if path.stat().st_size != entry["size"] or sha256(path) != entry["fingerprint"]:
                raise GateError("NAS_INTEGRITY_FAILED", "RecoveryRequired")
            self.update_item(entry["item_id"], {"integrity": True})
            self.db.heartbeat(task)
        move_ops = self.db.rows(
            select(p.operations).where(
                p.operations.c.plan_id == plan["id"], p.operations.c.kind == "MOVE"
            )
        )
        if not move_ops:
            raise GateError("MOVE_OWNERSHIP_UNPROVEN", "RecoveryRequired")
        self.db.op_status(
            move_ops[0], "VERIFIED", {"nas_integrity": True, "mapping_verified": True}
        )
        recheck_ops = self.db.rows(
            select(p.operations).where(
                p.operations.c.plan_id == plan["id"], p.operations.c.kind == "RECHECK"
            )
        )
        if not recheck_ops:
            self.state(task["job_id"], "Rechecking", 4)
            self.dispatch(task, plan, resources, "RECHECK", {}, "recheck", current)
            return False
        op = recheck_ops[0]
        if not (op.get("observed") or {}).get("checking_seen"):
            self.state(task["job_id"], "Rechecking", 4, {"reason": "AWAITING_OBSERVED_RECHECK"})
            return False
        pieces = self.qbt.get("torrents/pieceStates", hash=current.info_hash)
        if not pieces or any(piece != 2 for piece in pieces):
            raise GateError("PIECE_RECHECK_FAILED", "RecoveryRequired")
        self.db.op_status(op, "VERIFIED", {"checking_seen": True, "pieces_complete": True})
        original_policy = d["snapshot"]["policy"]
        if current.policy.get("intentional_pause") != original_policy.get("intentional_pause"):
            # This engine did not issue a stop, so a new pause/start cannot be attributed
            # to us. Preserve the user's current intent rather than forcing the snapshot.
            raise GateError("EXTERNAL_PAUSE_POLICY_CHANGED", "ReplanRequired")
        if not seeding_capable(current, d["qbt_destination"], original_policy, True):
            raise GateError("SEEDING_POLICY_UNVERIFIED", "RecoveryRequired")
        # Early seeding capability restored before hardlinks/enrichment.
        self.state(
            task["job_id"], "SeedingCapable", 4, {"seeding_capable": True, "nas_integrity": True}
        )
        if d["strategy"] != "SIMPLE":
            for entry in d["entries"]:
                target = "Library/" + entry["destination"]
                intent = {
                    "source": ".vimag-torrent-store/"
                    + registered["id"]
                    + "/"
                    + entry["source_name"],
                    "target": target,
                    "fingerprint": entry["fingerprint"],
                }
                op, fresh = self.db.intent(task, plan, "HARDLINK", target, intent)
                path = contained(self.cfg.nas_root, target)
                if fresh:
                    hardlink(
                        self.cfg.nas_root,
                        intent["source"],
                        target,
                        entry["fingerprint"],
                        lambda: self.fence(task, resources, registered["id"]),
                    )
                elif not path.is_file() or sha256(path) != entry["fingerprint"]:
                    raise GateError("HARDLINK_RECONCILE_FAILED", "RecoveryRequired")
                self.db.op_status(
                    op, "VERIFIED", {"content_verified": True, "scratch_alias_proof": True}
                )
        for entry in d["entries"]:
            child = self.db.one(select(p.items).where(p.items.c.id == entry["item_id"]))
            with self.db.transaction() as conn:
                asset_id = p.uid()
                result = conn.execute(
                    pg_insert(p.assets)
                    .values(
                        id=asset_id,
                        root="library",
                        relative_path=entry["destination"],
                        identity_key=entry["identity_key"],
                        edition=entry["identity"]["edition"],
                        fingerprint=entry["fingerprint"],
                        data={
                            "identity": entry["identity"],
                            "bg": entry["bg"],
                            "integrity": True,
                            "job_id": task["job_id"],
                            "probe": child["data"].get("probe", {}),
                            "stream_keys": child["data"].get("stream_keys", []),
                        },
                    )
                    .on_conflict_do_nothing(index_elements=["root", "relative_path"])
                    .returning(p.assets.c.id)
                )
                if result.first() is not None:
                    conn.execute(
                        insert(p.refs).values(
                            asset_id=asset_id,
                            torrent_id=registered["id"],
                            root="library",
                            relative_path=entry["destination"],
                        )
                    )
        return True

    def observe_recheck(self, task: dict[str, Any], plan: dict[str, Any], current: Torrent) -> None:
        if current.state.startswith("checking"):
            ops = self.db.rows(
                select(p.operations).where(
                    p.operations.c.plan_id == plan["id"], p.operations.c.kind == "RECHECK"
                )
            )
            if ops:
                self.db.op_status(ops[0], "OBSERVED", {"checking_seen": True})

    def sidecar(self, task: dict[str, Any], plan: dict[str, Any], rel: str, content: bytes) -> None:
        registered = plan["data"]["torrent_id"]
        resources = ["sidecar:" + rel.casefold(), "torrent:" + registered]
        self.db.reserve(task, resources)
        prior_ops = self.db.rows(
            select(p.operations).where(
                p.operations.c.op_key == digest([task["job_id"], plan["sha256"], "SIDECAR", rel])
            )
        )
        if prior_ops:
            target = contained(self.cfg.nas_root, rel)
            desired = __import__("hashlib").sha256(content).hexdigest()
            if prior_ops[0]["intent"]["new_sha256"] != desired:
                raise GateError("SIDECAR_REMOTE_CONTENT_CHANGED", "ReplanRequired")
            if target.is_file() and sha256(target) == desired:
                owned = self.db.rows(
                    select(p.sidecars).where(
                        p.sidecars.c.root == "nas",
                        p.sidecars.c.relative_path == rel,
                        p.sidecars.c.sha256 == desired,
                    )
                )
                if owned or prior_ops[0]["status"] == "COMMAND_REQUESTED":
                    if not owned:
                        with self.db.transaction() as conn:
                            conn.execute(
                                pg_insert(p.sidecars)
                                .values(
                                    root="nas",
                                    relative_path=rel,
                                    sha256=desired,
                                    data={"reconciled_op": prior_ops[0]["id"]},
                                )
                                .on_conflict_do_nothing(index_elements=["root", "relative_path"])
                            )
                    self.db.op_status(prior_ops[0], "VERIFIED")
                    return
        prior = self.db.rows(
            select(p.sidecars).where(p.sidecars.c.root == "nas", p.sidecars.c.relative_path == rel)
        )
        expected = prior[0]["sha256"] if prior else None
        if prior and prior[0]["locked"]:
            raise GateError("SIDECAR_LOCKED")
        intent = {
            "target": rel,
            "expected": expected,
            "new_sha256": __import__("hashlib").sha256(content).hexdigest(),
        }
        op, fresh = (
            (prior_ops[0], False)
            if prior_ops
            else self.db.intent(task, plan, "SIDECAR", rel, intent)
        )
        target = contained(self.cfg.nas_root, rel)
        actual_hash = sha256(target) if target.is_file() else None
        if (expected is None and target.exists()) or (
            expected is not None and actual_hash != expected
        ):
            approval_action = "SIDECAR:" + digest([rel, actual_hash, intent["new_sha256"]])
            approved = self.db.rows(
                select(p.approvals).where(
                    p.approvals.c.plan_id == plan["id"],
                    p.approvals.c.sha256 == plan["sha256"],
                    p.approvals.c.action == approval_action,
                )
            )
            if not approved or actual_hash is None:
                job = self.db.one(select(p.jobs).where(p.jobs.c.id == task["job_id"]))
                conflicts = dict(job["data"].get("sidecar_conflicts", {}))
                conflicts[rel] = {
                    "relative_path": rel,
                    "observed_sha256": actual_hash,
                    "proposed_sha256": intent["new_sha256"],
                    "old_preview": target.read_text(errors="replace")[:2000]
                    if target.is_file() and target.suffix == ".nfo"
                    else "Binary or missing file",
                    "new_preview": content.decode(errors="replace")[:2000]
                    if target.suffix == ".nfo"
                    else "Binary artwork",
                }
                self.state(task["job_id"], "NeedsReview", 4, {"sidecar_conflicts": conflicts})
                raise GateError("SIDECAR_CONFLICT")
            expected = actual_hash
        if not fresh and not target.exists() and expected is not None:
            raise GateError("SIDECAR_MISSING_EXTERNAL_EDIT", "RecoveryRequired")
        backup_rel = ".vimag-sidecar-backups/" + op["id"] + "/" + Path(rel).name
        self.db.op_status(op, "COMMAND_REQUESTED")
        result = atomic_sidecar(
            self.cfg.nas_root,
            rel,
            content,
            expected,
            lambda: self.fence(task, resources, registered),
            backup_rel,
        )
        with self.db.transaction() as conn:
            conn.execute(
                pg_insert(p.sidecars)
                .values(
                    root="nas",
                    relative_path=rel,
                    sha256=result,
                    data={"backup": backup_rel, "op_id": op["id"]},
                )
                .on_conflict_do_update(
                    index_elements=["root", "relative_path"],
                    set_={"sha256": result, "data": {"backup": backup_rel, "op_id": op["id"]}},
                )
            )
            self.db.event(conn, "worker", "SIDECAR_WRITTEN", op["id"])
        self.db.op_status(op, "VERIFIED")

    def enrich(self, task: dict[str, Any], plan: dict[str, Any]) -> None:
        self.state(task["job_id"], "Enriching", 4)
        for entry in plan["data"]["entries"]:
            identity = entry["identity"]
            path = PurePosixPath("Library/" + entry["destination"])
            nfo = Element("episodedetails" if identity["media_type"] == "show" else "movie")
            SubElement(nfo, "title").text = identity["title"]
            SubElement(nfo, "originaltitle").text = identity["title"]
            SubElement(nfo, "year").text = str(identity["year"])
            if identity.get("provider_id"):
                SubElement(nfo, "uniqueid", {"type": "tmdb", "default": "true"}).text = identity[
                    "provider_id"
                ]
                SubElement(nfo, "tmdbid").text = identity["provider_id"]
            if identity["media_type"] == "show":
                SubElement(nfo, "season").text = str(identity["season"])
                SubElement(nfo, "episode").text = str(identity["episodes"][0])
                rel = str(path.with_suffix(".nfo"))
                show_nfo = Element("tvshow")
                SubElement(show_nfo, "title").text = identity["title"]
                SubElement(show_nfo, "year").text = str(identity["year"])
                if identity.get("provider_id"):
                    SubElement(
                        show_nfo, "uniqueid", {"type": "tmdb", "default": "true"}
                    ).text = identity["provider_id"]
                self.sidecar(
                    task,
                    plan,
                    str(path.parent.parent / "tvshow.nfo"),
                    tostring(show_nfo, encoding="utf-8", xml_declaration=True),
                )
            else:
                rel = str(path.parent / "movie.nfo")
            self.sidecar(task, plan, rel, tostring(nfo, encoding="utf-8", xml_declaration=True))
            child = self.db.one(select(p.items).where(p.items.c.id == entry["item_id"]))
            candidate: dict[str, Any] = next(
                (
                    c
                    for c in child["data"].get("candidates", [])
                    if c["id"] == identity.get("provider_id")
                ),
                {},
            )
            for key, filename in [("poster_path", "poster.jpg"), ("backdrop_path", "backdrop.jpg")]:
                if candidate.get(key):
                    artwork_parent = (
                        path.parent.parent if identity["media_type"] == "show" else path.parent
                    )
                    self.sidecar(
                        task,
                        plan,
                        str(artwork_parent / filename),
                        self.tmdb.artwork(candidate[key]),
                    )
            self.db.heartbeat(task)

    def subtitle_search(self, task: dict[str, Any], plan: dict[str, Any]) -> None:
        self.state(task["job_id"], "Subtitles", 5)
        for entry in plan["data"]["entries"]:
            child = self.db.one(select(p.items).where(p.items.c.id == entry["item_id"]))
            if child["data"].get("subtitle") in {"Matched", "Synchronized", "Unavailable"}:
                continue
            identity = entry["identity"]
            candidates = []
            for file in plan["data"]["snapshot"]["files"]:
                original = PurePosixPath(file["name"])
                if original.suffix.lower() != ".srt" or not original.stem.startswith(
                    PurePosixPath(entry["source_name"]).stem
                ):
                    continue
                local_rel = (
                    ".vimag-torrent-store/" + plan["data"]["torrent_id"] + "/" + file["name"]
                )
                if plan["data"]["strategy"] == "SIMPLE":
                    continue
                local = contained(self.cfg.nas_root, local_rel, existing=True)
                if local.stat().st_size <= 1048576:
                    try:
                        content = local.read_text(encoding="utf-8-sig")
                    except UnicodeDecodeError:
                        content = None
                    self.evidence(
                        "subtitle_candidates",
                        {
                            "source": "existing-external",
                            "status": "NeedsReview",
                            "content": content,
                            "original_preserved": True,
                        },
                        entry["item_id"],
                    )
            if (
                identity.get("provider_id")
                and self.cfg.secret(self.cfg.subtitle_api_key_file).get_secret_value()
            ):
                try:
                    candidates = OpenSubtitles(self.cfg).search(
                        identity["provider_id"],
                        identity["media_type"],
                        identity.get("season"),
                        (identity.get("episodes") or [None])[0],
                    )
                except GateError as error:
                    self.evidence(
                        "subtitle_candidates",
                        {"status": "Unavailable", "reason": error.code},
                        entry["item_id"],
                    )
            embedded = [
                s
                for s in child["data"]["probe"]["streams"]
                if s.get("codec_type") == "subtitle"
                and s.get("tags", {}).get("language") in {"bul", "bg"}
            ]
            if embedded:
                self.evidence(
                    "subtitle_candidates",
                    {"status": "NeedsReview", "source": "embedded", "streams": embedded},
                    entry["item_id"],
                )
            for candidate in candidates:
                self.evidence("subtitle_candidates", candidate, entry["item_id"])
            # Undemonstrated timing is never promoted to synced by filename/language alone.
            self.update_item(
                entry["item_id"],
                {
                    "subtitle": "Unavailable",
                    "subtitle_reason": "NO_VERIFIED_TIMING"
                    if embedded or candidates
                    else "NO_PROVIDER_CANDIDATE",
                },
            )

    def publish(self, task: dict[str, Any], plan: dict[str, Any]) -> bool:
        self.state(task["job_id"], "PublishPending", 6)
        resources = ["jellyfin-publish", "torrent:" + plan["data"]["torrent_id"]]
        self.db.reserve(task, resources)
        publication = self.db.rows(select(p.items).where(p.items.c.job_id == task["job_id"]))
        publication_key = digest(
            [
                [i["id"], i["data"].get("subtitle")]
                for i in sorted(publication, key=lambda i: i["id"])
            ]
        )
        op, fresh = self.db.intent(
            task,
            plan,
            "JELLYFIN_REFRESH",
            publication_key,
            {"plan_sha256": plan["sha256"], "publication": publication_key},
        )
        if fresh:
            self.fence(task, resources, plan["data"]["torrent_id"])
            self.db.op_status(op, "COMMAND_REQUESTED")
            self.jellyfin.refresh()
        all_verified = True
        for entry in plan["data"]["entries"]:
            item = self.db.one(select(p.items).where(p.items.c.id == entry["item_id"]))
            expected = {
                **entry["identity"],
                "jellyfin_path": self.cfg.jellyfin_library_root.rstrip("/")
                + "/"
                + entry["destination"],
                "bg": entry["bg"],
                "subtitle": item["data"]["subtitle"],
            }
            result = self.jellyfin.recognized(expected)
            self.evidence(
                "jellyfin_verifications",
                {"state": "PublishedVerified" if result else "PublishPending", "result": result},
                entry["item_id"],
            )
            self.update_item(entry["item_id"], {"published": bool(result), "jellyfin": result})
            all_verified &= bool(result)
        if all_verified:
            self.db.op_status(op, "VERIFIED", {"all_children_recognized": True})
        return all_verified

    def import_job(self, task: dict[str, Any]) -> bool:
        job = self.db.one(select(p.jobs).where(p.jobs.c.id == task["job_id"]))
        if job["paused"] or job["state"] in TERMINAL:
            return True
        registered = self.db.one(select(p.torrents).where(p.torrents.c.id == job["torrent_id"]))
        if registered["scope"] not in {"VIMAG_MANAGED", "TEST_FIXTURE"}:
            raise GateError("LEGACY_WRITE_FORBIDDEN", "RecoveryRequired")
        current = self.qbt.torrent(registered["info_hash"])
        if current.added_on != registered["added_on"]:
            raise GateError("TORRENT_INSTANCE_CHANGED", "ReplanRequired")
        children = self.db.rows(select(p.items).where(p.items.c.job_id == job["id"]))
        if not children:
            if not current.complete() or current.stable() != registered["snapshot"]:
                raise GateError("INTAKE_SNAPSHOT_CHANGED", "ReplanRequired")
            self.inspect(task, current)
        plan = self.plan(task, current, registered)
        if plan["data"].get("approval_required") and not self.db.rows(
            select(p.approvals).where(
                p.approvals.c.plan_id == plan["id"],
                p.approvals.c.sha256 == plan["sha256"],
                p.approvals.c.action == "APPROVE_IMPORT",
            )
        ):
            self.state(job["id"], "AwaitingApproval", 3)
            return True
        if not self.transfer(task, plan, registered):
            return False
        self.enrich(task, plan)
        self.subtitle_search(task, plan)
        if not self.publish(task, plan):
            return False
        self.state(job["id"], "FinalSeedingCheck", 7)
        current = self.qbt.torrent(registered["info_hash"])
        self.check_drift(current, plan, registered)
        children = self.db.rows(select(p.items).where(p.items.c.job_id == job["id"]))
        for entry in plan["data"]["entries"]:
            path = contained(self.cfg.nas_root, "Library/" + entry["destination"], existing=True)
            if sha256(path) != entry["fingerprint"]:
                raise GateError("FINAL_INTEGRITY_FAILED", "RecoveryRequired")
        seed = seeding_capable(
            current, plan["data"]["qbt_destination"], plan["data"]["snapshot"]["policy"], True
        )
        state = final_state([c["data"] for c in children], True, seed)
        self.state(job["id"], state, 7)
        return state in TERMINAL

    def inventory(self, task: dict[str, Any]) -> None:
        self.db.reserve(task, ["library-scan"])
        self.nas_health()
        current = self.qbt.all()  # Failure aborts scan; no fabricated empty dependency map.
        library = self.cfg.nas_root / "Library"
        for category in CATEGORIES.values():
            root = library / category
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if path.suffix.lower() not in VIDEO or path.is_symlink() or not path.is_file():
                    continue
                rel = path.relative_to(library).as_posix()
                contained(library, rel, existing=True)
                fingerprint = sha256(path)
                analysis = self.probe(path)
                nfo_path = path.parent / "movie.nfo"
                identity = (
                    read_nfo(nfo_path) if nfo_path.is_file() and not nfo_path.is_symlink() else {}
                )
                provider_id = identity.get("provider_id")
                previous = self.db.rows(
                    select(p.assets).where(
                        p.assets.c.root == "library", p.assets.c.relative_path == rel
                    )
                )
                prior = previous[0] if previous else None
                bg = bg_state(analysis, fingerprint, [])
                if prior:
                    records = self.db.rows(
                        select(p.evidence_tables["bg_audio_evidence"])
                        .where(p.evidence_tables["bg_audio_evidence"].c.asset_id == prior["id"])
                        .order_by(p.evidence_tables["bg_audio_evidence"].c.created_at)
                    )
                    latest = {record["data"]["stream_key"]: record["data"] for record in records}
                    if latest:
                        bg = bg_state(analysis, fingerprint, list(latest.values()))
                    elif (
                        prior["fingerprint"] == fingerprint
                        and prior["data"].get("bg") == "BG_VERIFIED"
                    ):
                        bg = "BG_VERIFIED"
                data = {
                    **(prior["data"] if prior and prior["fingerprint"] == fingerprint else {}),
                    "identity": identity,
                    "probe": analysis,
                    "stream_keys": [
                        {"index": s.get("index"), "key": digest(s)}
                        for s in analysis["streams"]
                        if s.get("codec_type") == "audio"
                    ],
                    "bg": bg,
                    "integrity": False,
                    "inventory_only": True,
                    "dependencies": [],
                    "issues": ["IDENTITY_REVIEW_REQUIRED"] if not provider_id else [],
                }
                for torrent in current:
                    for file in torrent.files:
                        qpath = torrent.save_path.rstrip("/") + "/" + file["name"]
                        if qpath == "/library/" + rel:
                            data["dependencies"].append(torrent.info_hash)
                with self.db.transaction() as conn:
                    conn.execute(
                        pg_insert(p.assets)
                        .values(
                            root="library",
                            relative_path=rel,
                            fingerprint=fingerprint,
                            identity_key="tmdb:movie:" + provider_id if provider_id else None,
                            edition="Unknown",
                            data=data,
                        )
                        .on_conflict_do_update(
                            index_elements=["root", "relative_path"],
                            set_={"fingerprint": fingerprint, "data": data},
                        )
                    )
                self.db.heartbeat(task)
        with self.db.transaction() as conn:
            self.db.event(conn, "worker", "INVENTORY_COMPLETED", task["id"])

    def attach_subtitle(self, task: dict[str, Any]) -> None:
        candidate = self.db.one(
            select(p.evidence_tables["subtitle_candidates"]).where(
                p.evidence_tables["subtitle_candidates"].c.id == task["data"]["candidate_id"]
            )
        )
        item = self.db.one(select(p.items).where(p.items.c.id == candidate["item_id"]))
        plan = self.db.one(
            select(p.plans)
            .where(p.plans.c.job_id == item["job_id"])
            .order_by(p.plans.c.revision.desc())
        )
        entry = next(e for e in plan["data"]["entries"] if e["item_id"] == item["id"])
        path = contained(self.cfg.nas_root, "Library/" + entry["destination"], existing=True)
        if sha256(path) != candidate["data"]["verification"]["video_fingerprint"]:
            raise GateError("SUBTITLE_VIDEO_CHANGED", "ReplanRequired")
        rel = str(PurePosixPath("Library/" + entry["destination"]).with_suffix(".bg.srt"))
        self.sidecar(task, plan, rel, candidate["data"]["content"].encode())
        self.update_item(item["id"], {"subtitle": "Synchronized", "published": False})
        with self.db.transaction() as conn:
            conn.execute(
                update(p.evidence_tables["subtitle_candidates"])
                .where(p.evidence_tables["subtitle_candidates"].c.id == candidate["id"])
                .values(data={**candidate["data"], "status": "Synchronized"})
            )
            conn.execute(
                update(p.jobs)
                .where(p.jobs.c.id == item["job_id"])
                .values(state="PublishPending", step=6)
            )
            conn.execute(insert(p.tasks).values(job_id=item["job_id"], kind="REPUBLISH"))

    def run_once(self) -> bool:
        task = self.db.claim(self.owner)
        if not task:
            return False
        started = time.monotonic()
        outcome, failure = "INTERRUPTED", None
        stop_heartbeat = Event()

        def pulse() -> None:
            while not stop_heartbeat.wait(max(1, self.cfg.lease_seconds / 3)):
                try:
                    self.db.heartbeat(task)
                except Exception:
                    task["heartbeat_failed"] = True
                    return

        heartbeat_thread = Thread(target=pulse, daemon=True)
        heartbeat_thread.start()
        try:
            if task["kind"] == "INVENTORY":
                self.inventory(task)
                done = True
            elif task["kind"] == "IMPORT":
                done = self.import_job(task)
            elif task["kind"] in {"QUARANTINE", "RESTORE", "NORMALIZE"}:
                from app.maintenance import execute

                done = execute(self, task)
            elif task["kind"] == "SUBTITLE_ATTACH":
                self.attach_subtitle(task)
                done = True
            elif task["kind"] == "SUBTITLE_DOWNLOAD":
                candidate = self.db.one(
                    select(p.evidence_tables["subtitle_candidates"]).where(
                        p.evidence_tables["subtitle_candidates"].c.id
                        == task["data"]["candidate_id"]
                    )
                )
                files = candidate["data"].get("attributes", {}).get("files", [])
                if candidate["data"].get("provider") != "OpenSubtitles" or not files:
                    raise GateError("SUBTITLE_CANDIDATE_UNAVAILABLE")
                content = OpenSubtitles(self.cfg).download(int(files[0]["file_id"]))
                from app.subtitles import cues

                cues(content)
                with self.db.transaction() as conn:
                    conn.execute(
                        update(p.evidence_tables["subtitle_candidates"])
                        .where(p.evidence_tables["subtitle_candidates"].c.id == candidate["id"])
                        .values(
                            data={
                                **candidate["data"],
                                "content": content.decode("utf-8-sig"),
                                "status": "NeedsReview",
                            }
                        )
                    )
                    self.db.event(conn, "worker", "SUBTITLE_CANDIDATE_DOWNLOADED", candidate["id"])
                done = True
            elif task["kind"] == "REPUBLISH":
                plan = self.db.one(
                    select(p.plans)
                    .where(p.plans.c.job_id == task["job_id"])
                    .order_by(p.plans.c.revision.desc())
                )
                done = self.publish(task, plan)
                if done:
                    registered = self.db.one(
                        select(p.torrents).where(p.torrents.c.id == plan["data"]["torrent_id"])
                    )
                    current = self.qbt.torrent(registered["info_hash"])
                    seed = seeding_capable(
                        current,
                        plan["data"]["qbt_destination"],
                        plan["data"]["snapshot"]["policy"],
                        True,
                    )
                    children = self.db.rows(
                        select(p.items).where(p.items.c.job_id == task["job_id"])
                    )
                    self.state(
                        task["job_id"], final_state([c["data"] for c in children], True, seed), 7
                    )
            else:
                raise GateError("UNKNOWN_TASK_KIND", "RecoveryRequired")
            self.db.finish_task(task, "DONE" if done else "RECONCILING", 1 if not done else 0)
            outcome = "DONE" if done else "RECONCILING"
        except GateError as error:
            outcome, failure = error.state, error.code
            if task.get("job_id"):
                job = self.db.one(select(p.jobs).where(p.jobs.c.id == task["job_id"]))
                self.state(task["job_id"], error.state, job["step"], {"error_code": error.code})
            safe_retry = (
                error.state in {"BlockedExternalDependency", "FailedRecoverable"}
                and task["attempts"] < self.cfg.retry_budget
            )
            try:
                self.db.finish_task(
                    task,
                    "RETRYABLE" if safe_retry else "BLOCKED",
                    min(300, 10 * 2 ** task["attempts"]),
                )
            except GateError:
                pass  # Lost lease cannot be renewed/finalized by the old worker.
            self.health({"state": error.state, "error_code": error.code})
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=5)
            emit(
                "TASK_ATTEMPT",
                job_id=task.get("job_id"),
                operation_id=task["id"],
                phase="finish",
                duration_ms=int((time.monotonic() - started) * 1000),
                result=outcome,
                error_code=failure,
                severity="WARNING" if failure else "INFO",
            )
        return True

    def run(self) -> None:
        last_poll = 0.0
        while self.running:
            try:
                if time.monotonic() - last_poll >= self.cfg.poll_seconds:
                    self.poll()
                    last_poll = time.monotonic()
                if not self.run_once():
                    time.sleep(0.5)
            except GateError as error:
                self.health({"state": error.state, "error_code": error.code})
                time.sleep(2)
            except Exception:
                # No exception repr: SQL/HTTP errors may contain secrets or private inventories.
                emit(
                    "WORKER_STOPPED",
                    phase="shutdown",
                    severity="CRITICAL",
                    error_code="UNEXPECTED_FAILURE",
                )
                raise SystemExit(1) from None


def main() -> None:
    cfg = Settings()
    cfg.validate_runtime()
    db = p.Database(cfg)
    qbt: Any
    jellyfin: Any
    tmdb: Any
    if cfg.adapters == "emulated":
        from app.emulated import create_emulators

        qbt, jellyfin, tmdb = create_emulators(cfg)
    else:
        qbt, jellyfin, tmdb = QBittorrent(cfg), Jellyfin(cfg), TMDb(cfg)
    worker = Worker(db, qbt, jellyfin, tmdb)

    def stop(_signal: int, _frame: Any) -> None:
        worker.running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    worker.run()


if __name__ == "__main__":
    main()
