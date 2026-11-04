"""Authenticated v1.1 maintenance intents. Filesystem work belongs to Worker."""

from typing import Any, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import catalogue, library_policy
from app import persistence as p
from app.domain import CATEGORIES, GateError, digest


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_ids: list[UUID] = Field(default_factory=list, max_length=10000)
    category: Literal["movies", "series", "animations", "documentaries", "concerts"] | None = None
    all: bool = False


class PolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    policy: dict[str, Any]


class PolicyPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy: dict[str, Any]
    category: str
    identity: dict[str, Any]
    data: dict[str, Any] = Field(default_factory=dict)
    path: str = "preview.mkv"


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_revision: int = Field(ge=1)
    plan_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    confirmed: bool


class IdentityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    identity: dict[str, Any]


class SubtitleAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_revision: int = Field(ge=1)
    fingerprint: str = Field(pattern="^[a-f0-9]{64}$")
    content: str = Field(min_length=1, max_length=1048576)
    edition: str
    fps: float | None = Field(None, gt=0, le=240)
    duration: float = Field(gt=0)
    language: Literal["bg"] = "bg"
    kind: Literal["normal", "forced", "sdh"] = "normal"
    complete: bool
    timing_confirmed: bool
    source_quality: Literal["reviewed", "unknown"]
    provider: str = Field(min_length=1, max_length=80)
    release: str = Field(min_length=1, max_length=200)


class RestoreScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_ids: list[UUID] = Field(min_length=1, max_length=10000)
    confirmed: bool


def register(app: FastAPI, db: p.Database, admin: Any, command: Any) -> None:
    @app.get("/api/v1/library/analytics", dependencies=[Depends(admin)])
    def analytics() -> dict[str, Any]:
        return catalogue.analytics(db)

    def enqueue_scan(conn: Any, scope: list[str], actor: str) -> dict[str, Any]:
        conn.execute(text("SELECT pg_advisory_xact_lock(4710011)"))
        active = (
            conn.execute(
                select(p.scans)
                .join(p.tasks, p.tasks.c.id == p.scans.c.task_id)
                .where(p.tasks.c.state.in_(["QUEUED", "RUNNING", "RECONCILING", "RETRYABLE"]))
            )
            .mappings()
            .all()
        )
        if any(set(row["scope"]) & set(scope) for row in active):
            raise GateError("SCAN_SCOPE_BUSY")
        sid, tid = p.uid(), p.uid()
        conn.execute(insert(p.tasks).values(id=tid, kind="INVENTORY"))
        conn.execute(insert(p.scans).values(id=sid, task_id=tid, scope=scope, state="QUEUED"))
        db.event(conn, actor, "INVENTORY_REQUESTED", sid)
        return {"id": sid, "operation_id": tid}

    @app.post("/api/v1/library/scans", status_code=202)
    def scan(
        body: Scope, request: Request, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, Any]:
        if body.asset_ids:
            raise GateError("SCAN_REQUIRES_CATEGORY_SCOPE")
        with db.transaction() as conn:
            return command(
                conn,
                request,
                session["user_id"],
                body.model_dump(mode="json"),
                lambda: enqueue_scan(
                    conn, [body.category] if body.category else list(CATEGORIES), session["user_id"]
                ),
            )

    app.state.enqueue_scan = enqueue_scan

    @app.get("/api/v1/library/scans/{scan_id}", dependencies=[Depends(admin)])
    def scan_status(scan_id: UUID) -> dict[str, Any]:
        return db.one(select(p.scans).where(p.scans.c.id == str(scan_id)))

    @app.get("/api/v1/library/policies", dependencies=[Depends(admin)])
    def policies() -> dict[str, Any]:
        rows = db.rows(select(p.policies).order_by(p.policies.c.revision.desc()))
        return {
            "items": rows,
            "active": rows[0] if rows else {"revision": 0, "data": library_policy.defaults()},
        }

    @app.post("/api/v1/library/policies", status_code=201)
    def save_policy(
        body: PolicyInput, request: Request, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, Any]:
        library_policy.validate_for_save(body.policy)
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                conn.execute(text("SELECT pg_advisory_xact_lock(4710012)"))
                revision = conn.execute(
                    select(func.coalesce(func.max(p.policies.c.revision), 0))
                ).scalar_one()
                if revision != body.expected_revision:
                    raise GateError("POLICY_REVISION_STALE")
                pid = p.uid()
                conn.execute(
                    insert(p.policies).values(
                        id=pid,
                        revision=revision + 1,
                        data=body.policy,
                        sha256=digest(body.policy),
                        actor=session["user_id"],
                    )
                )
                db.event(conn, session["user_id"], "LIBRARY_POLICY_SAVED", pid)
                return {"id": pid, "revision": revision + 1, "data": body.policy}

            return command(conn, request, session["user_id"], body.model_dump(mode="json"), apply)

    @app.post("/api/v1/library/policies/preview")
    def preview(body: PolicyPreview, session: dict[str, Any] = Depends(admin)) -> dict[str, str]:
        return library_policy.render(
            body.policy, body.category, body.identity, body.data, body.path
        )

    @app.get("/api/v1/library/assets/{asset_id}/identity-candidates", dependencies=[Depends(admin)])
    def identity_candidates(asset_id: UUID) -> dict[str, Any]:
        rows = db.rows(
            select(p.evidence_tables["identity_candidates"])
            .where(p.evidence_tables["identity_candidates"].c.asset_id == str(asset_id))
            .order_by(p.evidence_tables["identity_candidates"].c.created_at.desc())
            .limit(1)
        )
        return {"items": rows[0]["data"].get("candidates", []) if rows else []}

    @app.post("/api/v1/library/assets/{asset_id}/identity")
    def identity(
        asset_id: UUID,
        body: IdentityInput,
        request: Request,
        session: dict[str, Any] = Depends(admin),
    ) -> dict[str, Any]:
        from pydantic import TypeAdapter, ValidationError

        from app.domain import Identity

        fields = set(Identity.__dataclass_fields__) | {
            "imdb_id",
            "collection_id",
            "collection_name",
            "collection_override",
            "episode_title",
            "event",
            "provenance",
            "collection_language",
            "collection_override_language",
            "episode_title_language",
        }
        if not set(body.identity) <= fields:
            raise GateError("INVALID_IDENTITY")
        value = {**body.identity, "confirmed": True}
        value["title_provenance"] = "manual-override"
        try:
            parsed: Identity = TypeAdapter(Identity).validate_python(
                {k: v for k, v in value.items() if k in Identity.__dataclass_fields__}
            )
        except ValidationError:
            raise GateError("INVALID_IDENTITY") from None
        if parsed.provider_id and not parsed.provider_id.isdecimal():
            raise GateError("INVALID_PROVIDER_ID")
        if not parsed.title or not 1880 <= parsed.year <= 2200:
            raise GateError("INVALID_IDENTITY")
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                if conn.execute(
                    select(p.leases.c.resource_key).where(
                        p.leases.c.resource_key.in_(["library-scan", "asset:" + str(asset_id)]),
                        p.leases.c.until > p.now(),
                    )
                ).first():
                    raise GateError("ASSET_MAINTENANCE_BUSY")
                row = (
                    conn.execute(
                        select(p.assets).where(p.assets.c.id == str(asset_id)).with_for_update()
                    )
                    .mappings()
                    .one_or_none()
                )
                if not row or row["revision"] != body.expected_revision:
                    raise GateError("ASSET_REVISION_STALE")
                previous = row["data"].get("identity") or {}
                merged = {**previous, **value}
                if (
                    value["title"] != previous.get("title")
                    or value.get("provider_id") != previous.get("provider_id")
                ) and not value.get("english_title_verified"):
                    merged["title_language"] = None
                    merged["english_title_verified"] = False
                if value.get("collection_override") != previous.get(
                    "collection_override"
                ) and not value.get("collection_override_language"):
                    merged["collection_override_language"] = None
                data = {**row["data"], "identity": merged}
                conn.execute(
                    update(p.assets)
                    .where(p.assets.c.id == str(asset_id))
                    .values(
                        data=data,
                        revision=row["revision"] + 1,
                        **catalogue.normalized(row["relative_path"], data),
                    )
                )
                db.event(conn, session["user_id"], "LIBRARY_IDENTITY_CONFIRMED", str(asset_id))
                return {"revision": row["revision"] + 1}

            return command(conn, request, session["user_id"], body.model_dump(mode="json"), apply)

    # Separate explicit intent endpoints; normalization can never authorize delete/quarantine.
    def add_operation(route: str, kind: str) -> None:
        @app.post("/api/v1/library/" + route + "/plans", status_code=202, name=kind + "_plan")
        def plan(
            body: Scope, request: Request, session: dict[str, Any] = Depends(admin)
        ) -> dict[str, Any]:
            if (
                sum([bool(body.asset_ids), bool(body.category), body.all]) != 1
                or kind != "NORMALIZE"
                and not body.asset_ids
            ):
                raise GateError("EXACT_SCOPE_REQUIRED")
            with db.transaction() as conn:

                def apply() -> dict[str, Any]:
                    jid, tid = p.uid(), p.uid()
                    scope = body.model_dump(mode="json")
                    if body.asset_ids:
                        found = conn.execute(
                            select(p.assets.c.id).where(
                                p.assets.c.id.in_([str(v) for v in body.asset_ids]),
                                p.assets.c.workflow_state == "ACTIVE",
                            )
                        ).all()
                        if len(found) != len(set(body.asset_ids)):
                            raise GateError("SCOPE_ASSET_UNAVAILABLE")
                    policy = (
                        conn.execute(
                            select(p.policies).order_by(p.policies.c.revision.desc()).limit(1)
                        )
                        .mappings()
                        .first()
                    )
                    conn.execute(
                        insert(p.jobs).values(
                            id=jid,
                            kind="BULK_" + kind,
                            state="Analyzing",
                            data={
                                "scope": scope,
                                "policy": policy["data"] if policy else library_policy.defaults(),
                                "policy_revision": policy["revision"] if policy else 0,
                            },
                        )
                    )
                    conn.execute(insert(p.tasks).values(id=tid, job_id=jid, kind="BULK_ANALYZE"))
                    db.event(conn, session["user_id"], kind + "_ANALYSIS_REQUESTED", jid)
                    return {"job_id": jid, "operation_id": tid, "state": "Analyzing"}

                return command(
                    conn, request, session["user_id"], body.model_dump(mode="json"), apply
                )

        @app.get(
            "/api/v1/library/" + route + "/{job_id}",
            dependencies=[Depends(admin)],
            name=kind + "_status",
        )
        def status(
            job_id: UUID, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
        ) -> dict[str, Any]:
            job = db.one(
                select(p.jobs).where(p.jobs.c.id == str(job_id), p.jobs.c.kind == "BULK_" + kind)
            )
            files = db.rows(
                select(p.maintenance_files)
                .where(p.maintenance_files.c.job_id == str(job_id))
                .order_by(p.maintenance_files.c.id)
                .offset(offset)
                .limit(limit)
            )
            groups = db.rows(
                select(p.maintenance_files.c.state, func.count().label("count"))
                .where(p.maintenance_files.c.job_id == str(job_id))
                .group_by(p.maintenance_files.c.state)
            )
            plans = db.rows(
                select(p.plans)
                .where(p.plans.c.job_id == str(job_id))
                .order_by(p.plans.c.revision.desc())
                .limit(1)
            )
            for file in files:
                data = file["data"]
                file["data"] = {
                    **data,
                    "sidecar_proposals": [
                        {k: v for k, v in proposal.items() if k != "content_hex"}
                        for proposal in data.get("sidecar_proposals", [])
                    ],
                }
                if data.get("subtitle_candidate"):
                    file["data"]["subtitle_candidate"] = {
                        "id": data["subtitle_candidate"]["id"],
                        "status": "Accepted",
                    }
            compact_plan = {k: v for k, v in plans[0].items() if k != "data"} if plans else None
            if compact_plan is not None:
                compact_plan["data"] = {
                    "action": kind,
                    "policy_revision": job["data"]["policy_revision"],
                    "entry_count": len(plans[0]["data"]["entries"]),
                }
            return {
                **job,
                "files": files,
                "counts": {r["state"]: r["count"] for r in groups},
                "plan": compact_plan,
                "history": db.rows(
                    select(p.audit)
                    .where(p.audit.c.target == str(job_id))
                    .order_by(p.audit.c.created_at.desc())
                    .limit(50)
                ),
                "operations": db.rows(
                    select(p.operations)
                    .where(p.operations.c.job_id == str(job_id))
                    .order_by(p.operations.c.created_at.desc())
                    .limit(100)
                ),
            }

        @app.post(
            "/api/v1/library/" + route + "/{job_id}/approve",
            status_code=202,
            name=kind + "_approve",
        )
        def approve(
            job_id: UUID, body: Approval, request: Request, session: dict[str, Any] = Depends(admin)
        ) -> dict[str, Any]:
            with db.transaction() as conn:

                def apply() -> dict[str, Any]:
                    job = (
                        conn.execute(
                            select(p.jobs)
                            .where(p.jobs.c.id == str(job_id), p.jobs.c.kind == "BULK_" + kind)
                            .with_for_update()
                        )
                        .mappings()
                        .one_or_none()
                    )
                    plan = (
                        conn.execute(
                            select(p.plans).where(
                                p.plans.c.job_id == str(job_id),
                                p.plans.c.revision == body.plan_revision,
                            )
                        )
                        .mappings()
                        .first()
                    )
                    if (
                        not job
                        or not plan
                        or not body.confirmed
                        or job["revision"] != body.plan_revision
                        or plan["sha256"] != body.plan_sha256
                        or job["state"] != "AwaitingApproval"
                    ):
                        raise GateError("REPLAN_REQUIRED")
                    for file in conn.execute(
                        select(p.maintenance_files).where(
                            p.maintenance_files.c.job_id == str(job_id)
                        )
                    ).mappings():
                        if file["state"] == "Planned":
                            asset = (
                                conn.execute(
                                    select(p.assets).where(p.assets.c.id == file["asset_id"])
                                )
                                .mappings()
                                .one()
                            )
                            if (
                                asset["revision"] != file["data"]["asset_revision"]
                                or asset["fingerprint"] != file["data"]["fingerprint"]
                            ):
                                raise GateError("PLAN_ASSET_STALE")
                    conn.execute(
                        pg_insert(p.approvals)
                        .values(
                            plan_id=plan["id"],
                            sha256=plan["sha256"],
                            actor=session["user_id"],
                            action="APPROVE_" + kind,
                        )
                        .on_conflict_do_nothing()
                    )
                    tid = p.uid()
                    conn.execute(
                        insert(p.tasks).values(id=tid, job_id=str(job_id), kind="BULK_EXECUTE")
                    )
                    conn.execute(
                        update(p.jobs).where(p.jobs.c.id == str(job_id)).values(state="Queued")
                    )
                    db.event(conn, session["user_id"], kind + "_APPROVED", str(job_id))
                    return {"job_id": str(job_id), "operation_id": tid}

                return command(
                    conn, request, session["user_id"], body.model_dump(mode="json"), apply
                )

        @app.post(
            "/api/v1/library/" + route + "/{job_id}/{action}",
            status_code=202,
            name=kind + "_control",
        )
        def control(
            job_id: UUID,
            action: Literal["pause", "resume", "cancel", "retry"],
            request: Request,
            session: dict[str, Any] = Depends(admin),
        ) -> dict[str, Any]:
            with db.transaction() as conn:

                def apply() -> dict[str, Any]:
                    conn.execute(text("SELECT pg_advisory_xact_lock(4710013)"))
                    job = (
                        conn.execute(
                            select(p.jobs)
                            .where(p.jobs.c.id == str(job_id), p.jobs.c.kind == "BULK_" + kind)
                            .with_for_update()
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if not job:
                        raise GateError("PLAN_NOT_APPROVED")
                    if job["revision"] == 0:
                        if action not in {"retry", "resume"}:
                            raise GateError("ANALYSIS_NOT_APPROVED")
                        conn.execute(
                            update(p.tasks)
                            .where(
                                p.tasks.c.job_id == str(job_id),
                                p.tasks.c.kind == "BULK_ANALYZE",
                                p.tasks.c.state != "RUNNING",
                            )
                            .values(state="RECONCILING", run_after=p.now())
                        )
                        conn.execute(
                            update(p.jobs)
                            .where(p.jobs.c.id == str(job_id))
                            .values(state="Analyzing")
                        )
                        db.event(
                            conn, session["user_id"], "MAINTENANCE_ANALYSIS_RETRY", str(job_id)
                        )
                        return {"job_id": str(job_id), "requested": "retry-analysis"}
                    approved = conn.execute(
                        select(p.approvals.c.id)
                        .join(p.plans)
                        .where(
                            p.plans.c.job_id == str(job_id),
                            p.approvals.c.action == "APPROVE_" + kind,
                        )
                    ).first()
                    if not approved:
                        raise GateError("PLAN_NOT_APPROVED")
                    data = {
                        **job["data"],
                        "cancel_remaining": action == "cancel"
                        or job["data"].get("cancel_remaining", False),
                    }
                    if action == "retry":
                        if data["cancel_remaining"]:
                            raise GateError("CANCELLED_REPLAN_REQUIRED")
                        conn.execute(
                            update(p.maintenance_files)
                            .where(
                                p.maintenance_files.c.job_id == str(job_id),
                                p.maintenance_files.c.state.in_(
                                    ["Failed", "PublishPending", "RecoveryRequired"]
                                ),
                            )
                            .values(state="Planned")
                        )
                    conn.execute(
                        update(p.jobs)
                        .where(p.jobs.c.id == str(job_id))
                        .values(paused=action == "pause", data=data)
                    )
                    # Existing queued/running task observes the durable control at its next file checkpoint.
                    active = conn.execute(
                        select(p.tasks.c.id).where(
                            p.tasks.c.job_id == str(job_id),
                            p.tasks.c.kind == "BULK_EXECUTE",
                            p.tasks.c.state.in_(["RUNNING", "QUEUED", "RECONCILING", "RETRYABLE"]),
                        )
                    ).first()
                    if not active:
                        conn.execute(
                            insert(p.tasks).values(job_id=str(job_id), kind="BULK_EXECUTE")
                        )
                    db.event(conn, session["user_id"], "MAINTENANCE_" + action.upper(), str(job_id))
                    return {"job_id": str(job_id), "requested": action}

                return command(conn, request, session["user_id"], {"action": action}, apply)

    add_operation("normalizations", "NORMALIZE")
    add_operation("quarantines", "QUARANTINE")
    add_operation("deletions", "DELETE")

    @app.post("/api/v1/library/quarantines/restores", status_code=202)
    def bulk_restore(
        body: RestoreScope, request: Request, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, Any]:
        if not body.confirmed:
            raise GateError("RESTORE_CONFIRMATION_REQUIRED")
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                manifests = (
                    conn.execute(
                        select(p.quarantine).where(
                            p.quarantine.c.id.in_([str(v) for v in body.manifest_ids]),
                            p.quarantine.c.state == "QUARANTINED",
                        )
                    )
                    .mappings()
                    .all()
                )
                if len(manifests) != len(set(body.manifest_ids)):
                    raise GateError("RESTORE_MANIFEST_STALE")
                jid, pid, tid = p.uid(), p.uid(), p.uid()
                entries = []
                conn.execute(
                    insert(p.jobs).values(id=jid, kind="BULK_RESTORE", state="Queued", revision=1)
                )
                for manifest in manifests:
                    if not manifest["data"].get("bulk"):
                        raise GateError("LEGACY_MANIFEST_REQUIRES_SINGLE_RESTORE")
                    files = [
                        {**e, "source": e["target"], "target": e["source"]}
                        for e in manifest["data"]["files"]
                    ]
                    data = {
                        "manifest_id": manifest["id"],
                        "files": files,
                        "title": manifest["data"].get("title"),
                        "source": manifest["data"]["target"],
                        "target": manifest["data"]["source"],
                    }
                    entries.append({"asset_id": manifest["asset_id"], **data})
                    conn.execute(
                        insert(p.maintenance_files).values(
                            job_id=jid, asset_id=manifest["asset_id"], state="Planned", data=data
                        )
                    )
                data = {"action": "RESTORE", "entries": entries}
                conn.execute(
                    insert(p.plans).values(
                        id=pid, job_id=jid, revision=1, sha256=digest(data), data=data
                    )
                )
                conn.execute(
                    insert(p.approvals).values(
                        plan_id=pid,
                        sha256=digest(data),
                        actor=session["user_id"],
                        action="APPROVE_RESTORE",
                    )
                )
                conn.execute(insert(p.tasks).values(id=tid, job_id=jid, kind="BULK_RESTORE_GROUP"))
                db.event(conn, session["user_id"], "BULK_RESTORE_APPROVED", jid)
                return {"job_id": jid, "operation_id": tid}

            return command(conn, request, session["user_id"], body.model_dump(mode="json"), apply)

    @app.post("/api/v1/library/quarantine/restores/{job_id}/retry", status_code=202)
    def retry_restore(
        job_id: UUID, request: Request, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, Any]:
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                job = (
                    conn.execute(select(p.jobs).where(p.jobs.c.id == str(job_id)).with_for_update())
                    .mappings()
                    .one_or_none()
                )
                if not job or job["kind"] not in {"RESTORE", "BULK_RESTORE"}:
                    raise GateError("RESTORE_JOB_REQUIRED")
                active = conn.execute(
                    select(p.tasks.c.id).where(
                        p.tasks.c.job_id == str(job_id),
                        p.tasks.c.state.in_(["RUNNING", "QUEUED", "RECONCILING", "RETRYABLE"]),
                    )
                ).first()
                if active:
                    raise GateError("RESTORE_ALREADY_RUNNING")
                conn.execute(
                    update(p.tasks)
                    .where(p.tasks.c.job_id == str(job_id))
                    .values(state="RECONCILING", run_after=p.now())
                )
                conn.execute(
                    update(p.maintenance_files)
                    .where(
                        p.maintenance_files.c.job_id == str(job_id),
                        p.maintenance_files.c.state != "Completed",
                    )
                    .values(state="Planned")
                )
                conn.execute(
                    update(p.jobs)
                    .where(p.jobs.c.id == str(job_id))
                    .values(state="Queued", paused=False)
                )
                db.event(conn, session["user_id"], "RESTORE_RETRY_REQUESTED", str(job_id))
                return {"job_id": str(job_id)}

            return command(conn, request, session["user_id"], {}, apply)

    @app.post("/api/v1/library/assets/{asset_id}/subtitles/accept", status_code=201)
    def accept_subtitle(
        asset_id: UUID,
        body: SubtitleAccept,
        request: Request,
        session: dict[str, Any] = Depends(admin),
    ) -> dict[str, Any]:
        from app.subtitles import evaluate, media_evidence

        asset = db.one(select(p.assets).where(p.assets.c.id == str(asset_id)))
        if asset["revision"] != body.asset_revision or asset["fingerprint"] != body.fingerprint:
            raise GateError("SUBTITLE_VIDEO_CHANGED")
        media = media_evidence(
            asset["data"], asset["fingerprint"], asset["data"].get("identity", {}).get("edition")
        )
        verification = {
            "actor": session["user_id"],
            "time": p.now().isoformat(),
            "video_fingerprint": body.fingerprint,
            "subtitle_sha256": digest(body.content),
            "timing_confirmed": body.timing_confirmed,
        }
        if (
            not body.complete
            or body.source_quality != "reviewed"
            or abs(body.duration - media["duration"]) > 1
        ):
            raise GateError("SUBTITLE_EDITION_COMPLETENESS_REVIEW")
        candidate = body.model_dump(mode="json")
        evaluation = evaluate(candidate, media, body.content.encode(), verification)
        if evaluation["status"] != "Synchronized":
            raise GateError("SUBTITLE_TIMING_NOT_VERIFIED")
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                cid = p.uid()
                current = (
                    conn.execute(
                        select(p.assets).where(p.assets.c.id == str(asset_id)).with_for_update()
                    )
                    .mappings()
                    .one_or_none()
                )
                if (
                    not current
                    or current["revision"] != body.asset_revision
                    or current["fingerprint"] != body.fingerprint
                ):
                    raise GateError("SUBTITLE_VIDEO_CHANGED")
                conn.execute(
                    insert(p.evidence_tables["subtitle_candidates"]).values(
                        id=cid,
                        asset_id=str(asset_id),
                        data={
                            **candidate,
                            "verification": verification,
                            "evaluation": evaluation,
                            "status": "Accepted",
                        },
                    )
                )
                db.event(conn, session["user_id"], "LIBRARY_SUBTITLE_ACCEPTED", str(asset_id))
                return {"id": cid, "status": "Accepted", "apply_via": "Normalization"}

            return command(conn, request, session["user_id"], body.model_dump(mode="json"), apply)

    @app.get("/api/v1/library/assets/{asset_id}/subtitles/versions", dependencies=[Depends(admin)])
    def versions(asset_id: UUID) -> dict[str, Any]:
        return {
            "items": db.rows(
                select(p.subtitle_versions)
                .where(p.subtitle_versions.c.asset_id == str(asset_id))
                .order_by(p.subtitle_versions.c.generation.desc())
            )
        }

    @app.post(
        "/api/v1/library/assets/{asset_id}/subtitles/versions/{generation}/restore", status_code=202
    )
    def restore_subtitle(
        asset_id: UUID, generation: int, request: Request, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, Any]:
        db.one(
            select(p.subtitle_versions).where(
                p.subtitle_versions.c.asset_id == str(asset_id),
                p.subtitle_versions.c.generation == generation,
            )
        )
        asset = db.one(
            select(p.assets).where(
                p.assets.c.id == str(asset_id), p.assets.c.workflow_state == "ACTIVE"
            )
        )
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                jid, pid, tid = p.uid(), p.uid(), p.uid()
                data = {
                    "asset_id": str(asset_id),
                    "generation": generation,
                    "fingerprint": asset["fingerprint"],
                }
                conn.execute(insert(p.jobs).values(id=jid, kind="SUBTITLE_RESTORE", revision=1))
                conn.execute(
                    insert(p.plans).values(
                        id=pid, job_id=jid, revision=1, sha256=digest(data), data=data
                    )
                )
                conn.execute(
                    insert(p.approvals).values(
                        plan_id=pid,
                        sha256=digest(data),
                        actor=session["user_id"],
                        action="RESTORE_SUBTITLE",
                    )
                )
                conn.execute(
                    insert(p.tasks).values(id=tid, job_id=jid, kind="SUBTITLE_RESTORE", data=data)
                )
                db.event(conn, session["user_id"], "SUBTITLE_RESTORE_APPROVED", jid)
                return {"job_id": jid, "operation_id": tid}

            return command(conn, request, session["user_id"], {"generation": generation}, apply)
