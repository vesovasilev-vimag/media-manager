import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import uvicorn
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, TypeAdapter, ValidationError
from sqlalchemy import String, delete, func, insert, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import persistence as p
from app.domain import CATEGORIES, STEPS, GateError, digest, safe_note
from app.ops import operational_status
from app.settings import Settings

HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
DUMMY = HASHER.hash(secrets.token_urlsafe(32))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(Input):
    username: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: SecretStr


class Setup(Credentials):
    setup_token: SecretStr


class PlanAction(Input):
    plan_revision: int = Field(ge=1)
    plan_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=1000)


class Review(Input):
    expected_revision: int = Field(ge=0)
    item_id: UUID
    material_improvement_verified: bool = False
    identity: dict[str, Any] | None = None
    quality_decision: (
        Literal["KeepBoth", "KeepBGPreferred", "PreferBetterBG", "NeedsReview", "Skip"] | None
    ) = None
    reason: str = Field(min_length=1, max_length=1000)


class AssetEvidence(Input):
    fingerprint: str = Field(pattern="^[0-9a-f]{64}$")
    stream_key: str = Field(pattern="^[0-9a-f]{64}$")
    action: Literal["verify", "revoke"]
    reason: str = Field(min_length=1, max_length=1000)


class Evidence(AssetEvidence):
    item_id: UUID


class SubtitleReview(Input):
    item_id: UUID
    fingerprint: str = Field(pattern="^[0-9a-f]{64}$")
    edition: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=1048576)
    timing_confirmed: bool
    reason: str = Field(min_length=1, max_length=1000)


class SubtitleSync(Input):
    content: str = Field(min_length=1, max_length=1048576)
    offset: float = Field(ge=-300, le=300)
    scale: float = Field(ge=0.9, le=1.1)


class SidecarApproval(PlanAction):
    relative_path: str = Field(min_length=1, max_length=900)
    observed_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class NormalizeReview(Input):
    identity: dict[str, Any]
    quality_label: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=1000)


def create_app(config: Settings | None = None, database: p.Database | None = None) -> FastAPI:
    cfg = config or Settings()
    cfg.validate_runtime()
    db = database or p.Database(cfg)
    app = FastAPI(
        title="ViMag Media Manager",
        version="1.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.db, app.state.config = db, cfg

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            {"code": str(exc.detail)}, status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(GateError)
    async def gate_error(_: Request, exc: GateError) -> JSONResponse:
        status = 404 if exc.code == "NOT_FOUND" else 423 if "BLOCKED" in exc.code else 409
        return JSONResponse({"code": exc.code, "state": exc.state}, status_code=status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo submitted password/secret values in validation responses.
        return JSONResponse(
            {"code": "INVALID_INPUT", "fields": [str(e["loc"][-1]) for e in exc.errors()]},
            status_code=422,
        )

    @app.middleware("http")
    async def headers(request: Request, call_next: Any) -> Response:
        if request.headers.get("host", "").split(":")[0] != cfg.allowed_host:
            return JSONResponse({"code": "INVALID_HOST"}, status_code=400)
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
            }
        )
        return response

    def origin_check(request: Request) -> None:
        if request.headers.get("origin") != cfg.origin:
            raise HTTPException(403, "INVALID_ORIGIN")

    def admin(request: Request) -> dict[str, Any]:
        token = request.cookies.get("vimag_session", "")
        found = db.rows(
            select(p.sessions).where(
                p.sessions.c.token_hash == token_hash(token), p.sessions.c.expires_at > p.now()
            )
        )
        if not token or not found:
            raise HTTPException(401, "SESSION_REQUIRED")
        session = found[0]
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            csrf = request.headers.get("x-csrf-token", "")
            if (
                request.headers.get("origin") != cfg.origin
                or not csrf
                or not secrets.compare_digest(token_hash(csrf), session["csrf_hash"])
            ):
                with db.transaction() as conn:
                    db.event(conn, session["user_id"], "CSRF_DENIED")
                raise HTTPException(403, "CSRF_REQUIRED")
            key = request.headers.get("idempotency-key", "")
            if not 16 <= len(key) <= 128:
                raise HTTPException(400, "IDEMPOTENCY_KEY_REQUIRED")
        return session

    def password_valid(value: SecretStr) -> str:
        password = value.get_secret_value()
        if not 14 <= len(password) <= 256:
            raise HTTPException(422, "PASSWORD_LENGTH_14_TO_256")
        return password

    def rate_limit(request: Request, name: str) -> None:
        # Global per-username limit prevents spoofed proxy/IP bypass.
        key = token_hash(name.casefold())
        with db.transaction() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(4710002)"))
            row = (
                conn.execute(select(p.rate_limits).where(p.rate_limits.c.key == key))
                .mappings()
                .first()
            )
            if row and row["until"] > p.now() and row["attempts"] >= 5:
                db.event(conn, "anonymous", "LOGIN_RATE_LIMIT")
                limited = True
            else:
                limited = False
                active = row if row is not None and row["until"] > p.now() else None
                conn.execute(
                    pg_insert(p.rate_limits)
                    .values(
                        key=key,
                        attempts=active["attempts"] + 1 if active else 1,
                        until=active["until"] if active else p.now() + timedelta(minutes=15),
                    )
                    .on_conflict_do_update(
                        index_elements=["key"],
                        set_={
                            "attempts": active["attempts"] + 1 if active else 1,
                            "until": active["until"] if active else p.now() + timedelta(minutes=15),
                        },
                    )
                )
        if limited:
            raise HTTPException(429, "LOGIN_RATE_LIMIT")

    def command(
        conn: Any, request: Request, actor: str, payload: Any, action: Any
    ) -> dict[str, Any]:
        key = request.headers["idempotency-key"]
        fingerprint = digest([request.url.path, payload])
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": key})
        previous = (
            conn.execute(select(p.idempotency).where(p.idempotency.c.key == key)).mappings().first()
        )
        if previous:
            if previous["actor"] != actor or previous["request_hash"] != fingerprint:
                raise GateError("IDEMPOTENCY_CONFLICT")
            return dict(previous["response"])
        response = action()
        conn.execute(
            insert(p.idempotency).values(
                key=key, actor=actor, request_hash=fingerprint, response=response
            )
        )
        return response

    @app.get("/api/v1/health/live")
    def live() -> dict[str, Any]:
        return {"alive": True, "version": "1.1.0"}

    @app.post("/api/v1/auth/setup", status_code=201)
    def setup(body: Setup, request: Request) -> dict[str, bool]:
        origin_check(request)
        rate_limit(request, "setup")
        expected = cfg.secret(cfg.setup_token_file).get_secret_value()
        if not expected or not secrets.compare_digest(
            body.setup_token.get_secret_value(), expected
        ):
            raise HTTPException(403, "SETUP_DENIED")
        password = password_valid(body.password)
        with db.transaction() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(4710003)"))
            if conn.execute(select(p.users.c.id)).first():
                raise HTTPException(409, "ALREADY_ENROLLED")
            user = p.uid()
            conn.execute(
                insert(p.users).values(
                    id=user, username=body.username, password_hash=HASHER.hash(password)
                )
            )
            db.event(conn, user, "ADMIN_ENROLLED")
        return {"created": True}

    @app.post("/api/v1/auth/login")
    def login(body: Credentials, request: Request, response: Response) -> dict[str, str]:
        origin_check(request)
        rate_limit(request, body.username)
        found = db.rows(select(p.users).where(p.users.c.username == body.username))
        valid: bool = False
        try:
            valid = HASHER.verify(
                found[0]["password_hash"] if found else DUMMY, body.password.get_secret_value()
            )
        except (VerifyMismatchError, VerificationError):
            valid = False
        if not valid or not found:
            with db.transaction() as conn:
                db.event(conn, "anonymous", "LOGIN_DENIED")
            raise HTTPException(401, "LOGIN_DENIED")
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with db.transaction() as conn:
            conn.execute(
                insert(p.sessions).values(
                    user_id=found[0]["id"],
                    token_hash=token_hash(token),
                    csrf_hash=token_hash(csrf),
                    expires_at=p.now() + timedelta(hours=cfg.session_hours),
                )
            )
            conn.execute(
                delete(p.rate_limits).where(
                    p.rate_limits.c.key == token_hash(body.username.casefold())
                )
            )
            db.event(conn, found[0]["id"], "LOGIN_SUCCESS")
        response.set_cookie(
            "vimag_session",
            token,
            httponly=True,
            secure=cfg.cookie_secure,
            samesite="strict",
            max_age=cfg.session_hours * 3600,
            path="/api",
        )
        # CSRF secret is readable by client code; session cookie remains HttpOnly.
        response.set_cookie(
            "vimag_csrf", csrf, secure=cfg.cookie_secure, samesite="strict", path="/"
        )
        return {"csrf_token": csrf}

    @app.post("/api/v1/auth/logout")
    def logout(response: Response, session: dict[str, Any] = Depends(admin)) -> dict[str, bool]:
        with db.transaction() as conn:
            conn.execute(delete(p.sessions).where(p.sessions.c.id == session["id"]))
            db.event(conn, session["user_id"], "LOGOUT")
        response.delete_cookie(
            "vimag_session", path="/api", secure=cfg.cookie_secure, httponly=True, samesite="strict"
        )
        response.delete_cookie("vimag_csrf", path="/", secure=cfg.cookie_secure, samesite="strict")
        return {"logged_out": True}

    @app.post("/api/v1/auth/password")
    def rotate_password(
        body: Credentials, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, bool]:
        with db.transaction() as conn:
            conn.execute(
                update(p.users)
                .where(p.users.c.id == session["user_id"])
                .values(password_hash=HASHER.hash(password_valid(body.password)))
            )
            conn.execute(delete(p.sessions))
            db.event(conn, session["user_id"], "PASSWORD_ROTATED")
        return {"sessions_revoked": True}

    @app.get("/api/v1/me")
    def me(session: dict[str, Any] = Depends(admin)) -> dict[str, Any]:
        return {"user_id": session["user_id"], "role": "admin", "expires_at": session["expires_at"]}

    @app.get("/api/v1/health/ready", dependencies=[Depends(admin)])
    def ready() -> dict[str, Any]:
        with db.transaction() as conn:
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        health = db.rows(select(p.settings_table).where(p.settings_table.c.key == "worker_health"))
        value = health[0]["value"] if health else {"state": "UNKNOWN"}
        age = (
            max(0, (p.now() - datetime.fromisoformat(value["time"])).total_seconds())
            if value.get("time")
            else None
        )
        value = {**value, "heartbeat_age_seconds": age}
        if age is not None and age > max(120, cfg.poll_seconds * 3):
            value["state"] = "STALE"
        return {
            "database": revision == "0002",
            "schema": revision,
            "worker": value,
            "write_enabled": cfg.write_enabled,
            "automatic_intake": cfg.automatic_intake,
            "production_authorized": operational_status(db)["production_authorized"],
        }

    @app.get("/api/v1/dashboard", dependencies=[Depends(admin)])
    def dashboard() -> dict[str, Any]:
        counts = db.rows(
            select(p.jobs.c.state, func.count().label("count")).group_by(p.jobs.c.state)
        )
        return {
            "counts": {r["state"]: r["count"] for r in counts},
            "health": ready(),
            "steps": STEPS,
            "recent": db.rows(select(p.audit).order_by(p.audit.c.created_at.desc()).limit(20)),
        }

    @app.get("/api/v1/jobs", dependencies=[Depends(admin)])
    def list_jobs(
        state: str | None = None,
        category: str | None = None,
        search: str = Query("", max_length=128),
        bg: str | None = None,
        quality: str | None = None,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        query = select(p.jobs, p.torrents.c.scope, p.torrents.c.snapshot).outerjoin(p.torrents)
        if state:
            query = query.where(p.jobs.c.state == state)
        if category:
            query = query.where(p.torrents.c.snapshot["category"].astext == category)
        if search:
            pattern = "%" + search.replace("%", "\\%").replace("_", "\\_") + "%"
            query = query.where(
                or_(
                    p.jobs.c.data.cast(String).ilike(pattern),
                    p.jobs.c.id.cast(String).ilike(pattern),
                    p.torrents.c.snapshot.cast(String).ilike(pattern),
                )
            )
        if bg:
            query = query.where(
                p.jobs.c.id.in_(select(p.items.c.job_id).where(p.items.c.data["bg"].astext == bg))
            )
        if quality:
            query = query.where(
                p.jobs.c.id.in_(
                    select(p.items.c.job_id).where(
                        p.items.c.data["quality_label"].astext == quality
                    )
                )
            )
        rows = db.rows(query.order_by(p.jobs.c.created_at.desc()).limit(limit).offset(offset))
        children = (
            db.rows(select(p.items).where(p.items.c.job_id.in_([r["id"] for r in rows])))
            if rows
            else []
        )
        for row in rows:
            row["media_items"] = [c for c in children if c["job_id"] == row["id"]]
        return {
            "items": rows,
            "offset": offset,
            "limit": limit,
        }

    @app.get("/api/v1/jobs/{job_id}", dependencies=[Depends(admin)])
    def job_detail(job_id: UUID) -> dict[str, Any]:
        jid = str(job_id)
        result = db.one(select(p.jobs).where(p.jobs.c.id == jid))
        result["media_items"] = db.rows(select(p.items).where(p.items.c.job_id == jid))
        result["operations"] = db.rows(
            select(p.operations)
            .where(p.operations.c.job_id == jid)
            .order_by(p.operations.c.created_at)
        )
        result["timeline"] = db.rows(
            select(p.audit).where(p.audit.c.target == jid).order_by(p.audit.c.created_at)
        )
        result["steps"] = STEPS
        result["maintenance_files"] = db.rows(
            select(p.maintenance_files).where(p.maintenance_files.c.job_id == jid)
        )
        return result

    @app.get("/api/v1/jobs/{job_id}/plan", dependencies=[Depends(admin)])
    def job_plan(job_id: UUID) -> dict[str, Any]:
        return db.one(
            select(p.plans)
            .where(p.plans.c.job_id == str(job_id))
            .order_by(p.plans.c.revision.desc())
            .limit(1)
        )

    @app.get("/api/v1/jobs/{job_id}/operations", dependencies=[Depends(admin)])
    def job_operations(job_id: UUID) -> list[dict[str, Any]]:
        return db.rows(
            select(p.operations)
            .where(p.operations.c.job_id == str(job_id))
            .order_by(p.operations.c.created_at)
        )

    @app.post("/api/v1/jobs/{job_id}/approve", status_code=202)
    def approve(
        job_id: UUID, body: PlanAction, request: Request, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, Any]:
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                job = (
                    conn.execute(select(p.jobs).where(p.jobs.c.id == str(job_id)).with_for_update())
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
                    or job["kind"].startswith("BULK_")
                    or job["revision"] != body.plan_revision
                    or plan["sha256"] != body.plan_sha256
                ):
                    raise GateError("REPLAN_REQUIRED", "ReplanRequired")
                conn.execute(
                    pg_insert(p.approvals)
                    .values(
                        plan_id=plan["id"],
                        sha256=plan["sha256"],
                        actor=session["user_id"],
                        action="APPROVE_IMPORT",
                    )
                    .on_conflict_do_nothing(index_elements=["plan_id", "action"])
                )
                conn.execute(
                    update(p.jobs).where(p.jobs.c.id == str(job_id)).values(state="PlanReady")
                )
                conn.execute(insert(p.tasks).values(job_id=str(job_id), kind="IMPORT"))
                db.event(
                    conn,
                    session["user_id"],
                    "IMPORT_APPROVED",
                    str(job_id),
                    {"revision": body.plan_revision},
                )
                return {"job_id": str(job_id), "state": "PlanReady"}

            return command(conn, request, session["user_id"], body.model_dump(mode="json"), apply)

    @app.post("/api/v1/jobs/{job_id}/review", status_code=202)
    def review(
        job_id: UUID, body: Review, request: Request, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, Any]:
        from app.domain import Identity, identity_dict

        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                job = (
                    conn.execute(select(p.jobs).where(p.jobs.c.id == str(job_id)).with_for_update())
                    .mappings()
                    .first()
                )
                item = (
                    conn.execute(
                        select(p.items).where(
                            p.items.c.id == str(body.item_id), p.items.c.job_id == str(job_id)
                        )
                    )
                    .mappings()
                    .first()
                )
                if not job or not item:
                    raise GateError("NOT_FOUND")
                if job["revision"] != body.expected_revision:
                    raise GateError("REPLAN_REQUIRED", "ReplanRequired")
                if conn.execute(
                    select(p.operations.c.id).where(p.operations.c.job_id == str(job_id))
                ).first():
                    raise GateError("OPERATION_ALREADY_PREPARED", "RecoveryRequired")
                data = dict(item["data"])
                if body.identity:
                    try:
                        identity: Identity = TypeAdapter(Identity).validate_python(body.identity)
                    except ValidationError:
                        raise HTTPException(422, "INVALID_IDENTITY") from None
                    identity.confirmed = True
                    data["identity"] = identity_dict(identity)
                    data["identity_review"] = {
                        "actor": session["user_id"],
                        "time": p.now().isoformat(),
                        "reason": safe_note(body.reason),
                    }
                if body.quality_decision:
                    data["quality_review"] = {
                        "decision": body.quality_decision,
                        "material_improvement_verified": body.material_improvement_verified,
                        "actor": session["user_id"],
                        "time": p.now().isoformat(),
                        "reason": safe_note(body.reason),
                    }
                conn.execute(
                    update(p.items).where(p.items.c.id == str(body.item_id)).values(data=data)
                )
                conn.execute(
                    update(p.jobs)
                    .where(p.jobs.c.id == str(job_id))
                    .values(state="Comparing", revision=job["revision"] + 1)
                )
                conn.execute(insert(p.tasks).values(job_id=str(job_id), kind="IMPORT"))
                db.event(
                    conn,
                    session["user_id"],
                    "ITEM_REVIEWED",
                    str(job_id),
                    {"item_id": str(body.item_id)},
                )
                return {"job_id": str(job_id), "state": "Comparing"}

            return command(conn, request, session["user_id"], body.model_dump(mode="json"), apply)

    @app.post("/api/v1/jobs/{job_id}/{action}", status_code=202)
    def control(
        job_id: UUID,
        action: Literal["pause", "resume", "retry"],
        request: Request,
        session: dict[str, Any] = Depends(admin),
    ) -> dict[str, Any]:
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                row = (
                    conn.execute(select(p.jobs).where(p.jobs.c.id == str(job_id)).with_for_update())
                    .mappings()
                    .first()
                )
                if not row:
                    raise GateError("NOT_FOUND")
                if row["kind"].startswith("BULK_"):
                    raise GateError("USE_MAINTENANCE_CONTROLS")
                if row["state"] in {"Completed", "CompletedWithWarnings"}:
                    raise GateError("TERMINAL_JOB")
                conn.execute(
                    update(p.jobs)
                    .where(p.jobs.c.id == str(job_id))
                    .values(paused=action == "pause")
                )
                if action != "pause":
                    conn.execute(
                        insert(p.tasks).values(
                            job_id=str(job_id), kind="IMPORT", state="RECONCILING"
                        )
                    )
                db.event(conn, session["user_id"], "JOB_" + action.upper(), str(job_id))
                return {"job_id": str(job_id), "requested": action}

            return command(conn, request, session["user_id"], {"action": action}, apply)

    @app.get("/api/v1/library/assets", dependencies=[Depends(admin)])
    def library(
        review: bool = False,
        category: Literal["movies", "series", "animations", "documentaries", "concerts"]
        | None = None,
        search: str = Query("", max_length=128),
        video_quality: Literal["SD", "HD", "Full HD", "2K", "4K", "8K"] | None = None,
        audio_codec: str | None = Query(None, pattern="^[a-z0-9_]{1,32}$"),
        audio_language: str | None = Query(None, pattern="^([a-z]{2,3}|unknown|none)$"),
        subtitle_language: str | None = Query(None, pattern="^([a-z]{2,3}|unknown|none)$"),
        sort: Literal["title", "category", "quality", "size", "path"] = "title",
        order: Literal["asc", "desc"] = "asc",
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        from app.catalogue import page

        return page(
            db,
            {
                "review": review,
                "category": category,
                "search": search,
                "video_quality": video_quality,
                "audio_codec": audio_codec,
                "audio_language": audio_language,
                "subtitle_language": subtitle_language,
                "sort": sort,
                "order": order,
                "limit": limit,
                "offset": offset,
            },
        )

    @app.get("/api/v1/library/duplicates", dependencies=[Depends(admin)])
    def duplicates() -> dict[str, Any]:
        return {
            "items": db.rows(
                select(p.evidence_tables["quality_decisions"])
                .order_by(p.evidence_tables["quality_decisions"].c.created_at.desc())
                .limit(200)
            )
        }

    @app.get("/api/v1/transfers", dependencies=[Depends(admin)])
    def transfers() -> dict[str, Any]:
        return {
            "items": db.rows(
                select(p.operations).order_by(p.operations.c.created_at.desc()).limit(200)
            )
        }

    @app.get("/api/v1/subtitles", dependencies=[Depends(admin)])
    def subtitles() -> dict[str, Any]:
        rows = db.rows(
            select(
                p.evidence_tables["subtitle_candidates"],
                p.items.c.data.label("context"),
                p.assets.c.data.label("asset_context"),
                p.assets.c.revision.label("asset_revision"),
                p.assets.c.fingerprint.label("asset_fingerprint"),
            )
            .outerjoin(p.items, p.items.c.id == p.evidence_tables["subtitle_candidates"].c.item_id)
            .outerjoin(
                p.assets, p.assets.c.id == p.evidence_tables["subtitle_candidates"].c.asset_id
            )
            .order_by(p.evidence_tables["subtitle_candidates"].c.created_at.desc())
            .limit(200)
        )
        for row in rows:
            if row["asset_context"] is not None:
                row["context"] = {**row["asset_context"], "fingerprint": row["asset_fingerprint"]}
            row.pop("asset_context")
            row.pop("asset_fingerprint")
        return {"items": rows}

    @app.get("/api/v1/settings", dependencies=[Depends(admin)])
    def settings() -> dict[str, Any]:
        return {
            "sections": db.rows(
                select(p.settings_table).where(
                    p.settings_table.c.key.in_(
                        ["automation", "storage", "quality", "naming", "worker_health"]
                    )
                )
            ),
            "write_enabled": cfg.write_enabled,
            "categories": CATEGORIES,
            "version": "1.1.0",
        }

    @app.put("/api/v1/settings/{section}", status_code=202)
    def save_settings(
        section: Literal["automation", "storage"],
        body: dict[str, int],
        request: Request,
        session: dict[str, Any] = Depends(admin),
    ) -> dict[str, Any]:
        allowed = (
            {"poll_seconds": (15, 300), "retry_budget": (1, 5)}
            if section == "automation"
            else {"min_free_gib": (10, 10000)}
        )
        if not body or any(
            k not in allowed or not allowed[k][0] <= v <= allowed[k][1] for k, v in body.items()
        ):
            raise HTTPException(422, "INVALID_SETTING")
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                conn.execute(
                    pg_insert(p.settings_table)
                    .values(key=section, value=body)
                    .on_conflict_do_update(
                        index_elements=["key"],
                        set_={"value": body, "revision": p.settings_table.c.revision + 1},
                    )
                )
                db.event(conn, session["user_id"], "SETTINGS_UPDATED", section)
                return {"section": section, "saved": True}

            return command(conn, request, session["user_id"], body, apply)

    @app.post("/api/v1/library/scan", status_code=202)
    def scan(request: Request, session: dict[str, Any] = Depends(admin)) -> dict[str, Any]:
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                return app.state.enqueue_scan(conn, list(CATEGORIES), session["user_id"])

            return command(conn, request, session["user_id"], {}, apply)

    @app.get("/api/v1/audit", dependencies=[Depends(admin)])
    def audit_log(offset: int = Query(0, ge=0)) -> dict[str, Any]:
        return {
            "items": db.rows(
                select(p.audit).order_by(p.audit.c.created_at.desc()).offset(offset).limit(100)
            )
        }

    @app.get("/api/v1/openapi.json", dependencies=[Depends(admin)])
    def openapi() -> dict[str, Any]:
        return app.openapi()

    @app.post("/api/v1/media/bg-evidence", status_code=202)
    def bg_evidence(
        body: Evidence, request: Request, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, Any]:
        from app.domain import bg_state

        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                item = (
                    conn.execute(
                        select(p.items).where(p.items.c.id == str(body.item_id)).with_for_update()
                    )
                    .mappings()
                    .first()
                )
                if not item or item["data"]["fingerprint"] != body.fingerprint:
                    raise GateError("EVIDENCE_FINGERPRINT_MISMATCH")
                transferred = (
                    conn.execute(
                        select(p.operations.c.id).where(p.operations.c.job_id == item["job_id"])
                    ).first()
                    is not None
                )
                if body.stream_key not in {
                    digest(s)
                    for s in item["data"]["probe"]["streams"]
                    if s.get("codec_type") == "audio"
                }:
                    raise GateError("EVIDENCE_STREAM_MISMATCH")
                value = {
                    "fingerprint": body.fingerprint,
                    "stream_key": body.stream_key,
                    "source": "human-confirmed",
                    "actor": session["user_id"],
                    "verified_at": p.now().isoformat(),
                    "revoked": body.action == "revoke",
                }
                conn.execute(
                    insert(p.evidence_tables["bg_audio_evidence"]).values(
                        item_id=str(body.item_id), data=value
                    )
                )
                data = dict(item["data"])
                data["bg"] = bg_state(data["probe"], data["fingerprint"], [value])
                conn.execute(
                    update(p.items).where(p.items.c.id == str(body.item_id)).values(data=data)
                )
                if transferred:
                    job = (
                        conn.execute(select(p.jobs).where(p.jobs.c.id == item["job_id"]))
                        .mappings()
                        .one()
                    )
                    conn.execute(
                        update(p.jobs)
                        .where(p.jobs.c.id == item["job_id"])
                        .values(
                            data={
                                **job["data"],
                                "bg_rename_proposal": {
                                    "item_id": item["id"],
                                    "fingerprint": body.fingerprint,
                                    "state": "NeedsReview",
                                    "bg": data["bg"],
                                },
                            }
                        )
                    )
                else:
                    conn.execute(
                        update(p.jobs)
                        .where(p.jobs.c.id == item["job_id"])
                        .values(revision=p.jobs.c.revision + 1, state="ReplanRequired")
                    )
                db.event(
                    conn,
                    session["user_id"],
                    "BG_" + body.action.upper(),
                    item["job_id"],
                    {"stream_key": body.stream_key},
                )
                return {"bg": data["bg"], "replan_required": True}

            return command(conn, request, session["user_id"], body.model_dump(mode="json"), apply)

    @app.post("/api/v1/library/assets/{asset_id}/quarantine-plan", status_code=202)
    def quarantine_plan(
        asset_id: UUID, request: Request, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, Any]:
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                asset = (
                    conn.execute(select(p.assets).where(p.assets.c.id == str(asset_id)))
                    .mappings()
                    .first()
                )
                if not asset:
                    raise GateError("NOT_FOUND")
                if (
                    asset["data"].get("dependencies")
                    or conn.execute(
                        select(p.refs.c.id).where(p.refs.c.asset_id == str(asset_id))
                    ).first()
                ):
                    raise GateError("DEPENDENCY_BLOCKED")
                manifest_id, job_id, plan_id = p.uid(), p.uid(), p.uid()
                data = {
                    "action": "QUARANTINE",
                    "asset_id": str(asset_id),
                    "manifest_id": manifest_id,
                    "source": "Library/" + asset["relative_path"],
                    "target": "Quarantine/" + manifest_id + "/" + asset["relative_path"],
                    "fingerprint": asset["fingerprint"],
                }
                conn.execute(
                    insert(p.jobs).values(
                        id=job_id, kind="QUARANTINE", state="AwaitingApproval", revision=1
                    )
                )
                conn.execute(
                    insert(p.plans).values(
                        id=plan_id, job_id=job_id, revision=1, sha256=digest(data), data=data
                    )
                )
                db.event(conn, session["user_id"], "QUARANTINE_PROPOSED", job_id)
                return {
                    "id": plan_id,
                    "job_id": job_id,
                    "revision": 1,
                    "sha256": digest(data),
                    "data": data,
                }

            return command(conn, request, session["user_id"], {"asset_id": str(asset_id)}, apply)

    @app.post("/api/v1/library/quarantine-plans/{plan_id}/approve", status_code=202)
    def approve_quarantine(
        plan_id: UUID, body: PlanAction, request: Request, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, Any]:
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                plan = (
                    conn.execute(select(p.plans).where(p.plans.c.id == str(plan_id)))
                    .mappings()
                    .first()
                )
                if (
                    not plan
                    or plan["revision"] != body.plan_revision
                    or plan["sha256"] != body.plan_sha256
                    or plan["data"].get("action") != "QUARANTINE"
                ):
                    raise GateError("REPLAN_REQUIRED")
                asset_id = plan["data"]["asset_id"]
                asset = (
                    conn.execute(select(p.assets).where(p.assets.c.id == asset_id)).mappings().one()
                )
                if (
                    asset["fingerprint"] != plan["data"]["fingerprint"]
                    or asset["data"].get("dependencies")
                    or conn.execute(
                        select(p.refs.c.id).where(p.refs.c.asset_id == asset_id)
                    ).first()
                ):
                    raise GateError("DEPENDENCY_BLOCKED")
                conn.execute(
                    pg_insert(p.approvals)
                    .values(
                        plan_id=str(plan_id),
                        sha256=plan["sha256"],
                        actor=session["user_id"],
                        action="APPROVE_QUARANTINE",
                    )
                    .on_conflict_do_nothing(index_elements=["plan_id", "action"])
                )
                task_id = p.uid()
                conn.execute(
                    insert(p.tasks).values(id=task_id, job_id=plan["job_id"], kind="QUARANTINE")
                )
                db.event(conn, session["user_id"], "QUARANTINE_APPROVED", plan["job_id"])
                return {"operation_id": task_id, "job_id": plan["job_id"]}

            return command(conn, request, session["user_id"], body.model_dump(mode="json"), apply)

    @app.get("/api/v1/library/quarantine", dependencies=[Depends(admin)])
    def quarantines() -> dict[str, Any]:
        return {"items": db.rows(select(p.quarantine).order_by(p.quarantine.c.created_at.desc()))}

    @app.post("/api/v1/library/quarantine/{manifest_id}/restore", status_code=202)
    def restore(
        manifest_id: UUID, request: Request, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, Any]:
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                manifest = (
                    conn.execute(select(p.quarantine).where(p.quarantine.c.id == str(manifest_id)))
                    .mappings()
                    .first()
                )
                if not manifest or manifest["state"] != "QUARANTINED":
                    raise GateError("RESTORE_NOT_AVAILABLE")
                job_id, plan_id, task_id = p.uid(), p.uid(), p.uid()
                data = {
                    "action": "RESTORE",
                    "asset_id": manifest["asset_id"],
                    "manifest_id": str(manifest_id),
                    "source": manifest["data"]["target"],
                    "target": manifest["data"]["source"],
                    "fingerprint": manifest["data"]["fingerprint"],
                }
                if manifest["data"].get("bulk"):
                    data["files"] = [
                        {**entry, "source": entry["target"], "target": entry["source"]}
                        for entry in manifest["data"]["files"]
                    ]
                conn.execute(
                    insert(p.jobs).values(id=job_id, kind="RESTORE", state="Queued", revision=1)
                )
                conn.execute(
                    insert(p.plans).values(
                        id=plan_id, job_id=job_id, revision=1, sha256=digest(data), data=data
                    )
                )
                conn.execute(
                    insert(p.approvals).values(
                        plan_id=plan_id,
                        sha256=digest(data),
                        actor=session["user_id"],
                        action="APPROVE_RESTORE",
                    )
                )
                conn.execute(
                    insert(p.tasks).values(
                        id=task_id,
                        job_id=job_id,
                        kind="BULK_RESTORE" if manifest["data"].get("bulk") else "RESTORE",
                    )
                )
                db.event(conn, session["user_id"], "RESTORE_APPROVED", job_id)
                return {"operation_id": task_id, "job_id": job_id}

            return command(
                conn, request, session["user_id"], {"manifest_id": str(manifest_id)}, apply
            )

    @app.post("/api/v1/subtitles/sync-proposal")
    def subtitle_sync(
        body: SubtitleSync, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, Any]:
        from app.subtitles import sync_proposal

        content = sync_proposal(body.content.encode(), body.offset, body.scale)
        with db.transaction() as conn:
            db.event(conn, session["user_id"], "SUBTITLE_SYNC_PROPOSED")
        return {
            "content": content.decode(),
            "status": "NeedsReview",
            "sha256": token_hash(content.decode()),
            "original_preserved": True,
        }

    @app.post("/api/v1/subtitles/verify", status_code=202)
    def subtitle_verify(
        body: SubtitleReview, request: Request, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, Any]:
        from app.subtitles import evaluate

        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                item = (
                    conn.execute(
                        select(p.items).where(p.items.c.id == str(body.item_id)).with_for_update()
                    )
                    .mappings()
                    .first()
                )
                if not item or item["data"]["fingerprint"] != body.fingerprint:
                    raise GateError("SUBTITLE_VIDEO_FINGERPRINT_MISMATCH")
                d = item["data"]
                if not d.get("identity"):
                    raise GateError("IDENTITY_REVIEW_REQUIRED")
                media = {
                    "fingerprint": d["fingerprint"],
                    "edition": d["identity"]["edition"],
                    "duration": float(d["probe"]["format"]["duration"]),
                }
                verification = {
                    "actor": session["user_id"],
                    "time": p.now().isoformat(),
                    "video_fingerprint": body.fingerprint,
                    "subtitle_sha256": digest(body.content),
                    "timing_confirmed": body.timing_confirmed,
                }
                evaluation = evaluate(
                    {"fingerprint": body.fingerprint, "edition": body.edition},
                    media,
                    body.content.encode(),
                    verification,
                )
                if evaluation["status"] != "Synchronized":
                    raise GateError("SUBTITLE_TIMING_NOT_VERIFIED")
                candidate_id, task_id = p.uid(), p.uid()
                value = {
                    **evaluation,
                    "content": body.content,
                    "verification": verification,
                    "status": "VerifiedPendingAttach",
                }
                conn.execute(
                    insert(p.evidence_tables["subtitle_candidates"]).values(
                        id=candidate_id, item_id=str(body.item_id), data=value
                    )
                )
                conn.execute(
                    insert(p.tasks).values(
                        id=task_id,
                        job_id=item["job_id"],
                        kind="SUBTITLE_ATTACH",
                        data={"candidate_id": candidate_id},
                    )
                )
                db.event(
                    conn,
                    session["user_id"],
                    "SUBTITLE_TIMING_VERIFIED",
                    item["job_id"],
                    {"candidate_id": candidate_id},
                )
                return {
                    "operation_id": task_id,
                    "candidate_id": candidate_id,
                    "status": "VerifiedPendingAttach",
                }

            return command(conn, request, session["user_id"], body.model_dump(mode="json"), apply)

    @app.post("/api/v1/jobs/{job_id}/sidecars/approve", status_code=202)
    def approve_sidecar(
        job_id: UUID,
        body: SidecarApproval,
        request: Request,
        session: dict[str, Any] = Depends(admin),
    ) -> dict[str, Any]:
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                job = (
                    conn.execute(select(p.jobs).where(p.jobs.c.id == str(job_id)).with_for_update())
                    .mappings()
                    .first()
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
                    or plan["sha256"] != body.plan_sha256
                    or job["revision"] != body.plan_revision
                ):
                    raise GateError("REPLAN_REQUIRED")
                conflict = job["data"].get("sidecar_conflicts", {}).get(body.relative_path)
                if not conflict or conflict["observed_sha256"] != body.observed_sha256:
                    raise GateError("SIDECAR_APPROVAL_STALE")
                action = "SIDECAR:" + digest(
                    [body.relative_path, body.observed_sha256, conflict["proposed_sha256"]]
                )
                conn.execute(
                    pg_insert(p.approvals)
                    .values(
                        plan_id=plan["id"],
                        sha256=plan["sha256"],
                        actor=session["user_id"],
                        action=action,
                    )
                    .on_conflict_do_nothing(index_elements=["plan_id", "action"])
                )
                task_id = p.uid()
                conn.execute(insert(p.tasks).values(id=task_id, job_id=str(job_id), kind="IMPORT"))
                db.event(
                    conn,
                    session["user_id"],
                    "SIDECAR_EXACT_REPLACEMENT_APPROVED",
                    str(job_id),
                    {"plan_id": plan["id"], "old_sha256": body.observed_sha256},
                )
                return {"operation_id": task_id}

            return command(conn, request, session["user_id"], body.model_dump(mode="json"), apply)

    @app.post("/api/v1/library/assets/{asset_id}/normalization-plan", status_code=202)
    def normalization_plan(
        asset_id: UUID,
        body: NormalizeReview,
        request: Request,
        session: dict[str, Any] = Depends(admin),
    ) -> dict[str, Any]:
        from pathlib import PurePosixPath

        from app.domain import Identity, name_for

        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                asset = (
                    conn.execute(select(p.assets).where(p.assets.c.id == str(asset_id)))
                    .mappings()
                    .first()
                )
                if not asset:
                    raise GateError("NOT_FOUND")
                if asset["workflow_state"] != "ACTIVE":
                    raise GateError("SCOPE_ASSET_UNAVAILABLE")
                if (asset["data"].get("identity") or {}).get("supplementary"):
                    raise GateError("SUPPLEMENTARY_MATERIAL_REVIEW")
                category = next(
                    (
                        k
                        for k, v in CATEGORIES.items()
                        if asset["relative_path"].startswith(v + "/")
                    ),
                    None,
                )
                if not category:
                    raise GateError("CATEGORY_CONFLICT")
                try:
                    identity: Identity = TypeAdapter(Identity).validate_python(body.identity)
                except ValidationError:
                    raise HTTPException(422, "INVALID_IDENTITY") from None
                identity.confirmed = True
                from app.english_metadata import require_english

                require_english(body.identity)
                target = name_for(
                    category,
                    identity,
                    body.quality_label,
                    asset["data"].get("bg", "AUDIO_UNKNOWN"),
                    PurePosixPath(asset["relative_path"]).suffix,
                )
                if target == asset["relative_path"]:
                    raise GateError("ALREADY_NORMALIZED")
                job_id, plan_id = p.uid(), p.uid()
                data = {
                    "action": "NORMALIZE",
                    "asset_id": str(asset_id),
                    "source": "Library/" + asset["relative_path"],
                    "target": "Library/" + target,
                    "fingerprint": asset["fingerprint"],
                    "asset_revision": asset["revision"],
                    "identity": body.identity,
                    "approval_required": True,
                }
                conn.execute(
                    insert(p.jobs).values(
                        id=job_id, kind="NORMALIZE", state="AwaitingApproval", revision=1
                    )
                )
                conn.execute(
                    insert(p.plans).values(
                        id=plan_id, job_id=job_id, revision=1, sha256=digest(data), data=data
                    )
                )
                db.event(conn, session["user_id"], "NORMALIZATION_PROPOSED", job_id)
                return {
                    "id": plan_id,
                    "job_id": job_id,
                    "revision": 1,
                    "sha256": digest(data),
                    "data": data,
                }

            return command(conn, request, session["user_id"], body.model_dump(mode="json"), apply)

    @app.post("/api/v1/library/normalization-plans/{plan_id}/approve", status_code=202)
    def approve_normalization(
        plan_id: UUID, body: PlanAction, request: Request, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, Any]:
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                plan = (
                    conn.execute(select(p.plans).where(p.plans.c.id == str(plan_id)))
                    .mappings()
                    .first()
                )
                if (
                    not plan
                    or plan["data"].get("action") != "NORMALIZE"
                    or plan["sha256"] != body.plan_sha256
                    or plan["revision"] != body.plan_revision
                ):
                    raise GateError("REPLAN_REQUIRED")
                asset = (
                    conn.execute(select(p.assets).where(p.assets.c.id == plan["data"]["asset_id"]))
                    .mappings()
                    .one()
                )
                if (
                    asset["revision"] != plan["data"].get("asset_revision")
                    or asset["fingerprint"] != plan["data"]["fingerprint"]
                ):
                    raise GateError("PLAN_ASSET_STALE")
                conn.execute(
                    pg_insert(p.approvals)
                    .values(
                        plan_id=plan["id"],
                        sha256=plan["sha256"],
                        actor=session["user_id"],
                        action="APPROVE_NORMALIZE",
                    )
                    .on_conflict_do_nothing(index_elements=["plan_id", "action"])
                )
                task_id = p.uid()
                conn.execute(
                    insert(p.tasks).values(id=task_id, job_id=plan["job_id"], kind="NORMALIZE")
                )
                db.event(conn, session["user_id"], "NORMALIZATION_APPROVED", plan["job_id"])
                return {"operation_id": task_id}

            return command(conn, request, session["user_id"], body.model_dump(mode="json"), apply)

    @app.post("/api/v1/library/assets/{asset_id}/bg-evidence", status_code=202)
    def asset_bg_evidence(
        asset_id: UUID,
        evidence_body: AssetEvidence,
        request: Request,
        session: dict[str, Any] = Depends(admin),
    ) -> dict[str, Any]:
        from app.domain import bg_state

        body = evidence_body.model_dump(mode="json")
        if (
            set(body) != {"fingerprint", "stream_key", "action", "reason"}
            or body["action"] not in {"verify", "revoke"}
            or not isinstance(body["reason"], str)
        ):
            raise HTTPException(422, "INVALID_EVIDENCE")
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                asset = (
                    conn.execute(
                        select(p.assets).where(p.assets.c.id == str(asset_id)).with_for_update()
                    )
                    .mappings()
                    .first()
                )
                if not asset or asset["fingerprint"] != body["fingerprint"]:
                    raise GateError("EVIDENCE_FINGERPRINT_MISMATCH")
                analysis = asset["data"].get("probe", {})
                if body["stream_key"] not in {
                    digest(s) for s in analysis.get("streams", []) if s.get("codec_type") == "audio"
                }:
                    raise GateError("EVIDENCE_STREAM_MISMATCH")
                value = {
                    "fingerprint": body["fingerprint"],
                    "stream_key": body["stream_key"],
                    "source": "human-confirmed",
                    "actor": session["user_id"],
                    "verified_at": p.now().isoformat(),
                    "revoked": body["action"] == "revoke",
                    "reason": safe_note(body["reason"]),
                }
                conn.execute(
                    insert(p.evidence_tables["bg_audio_evidence"]).values(
                        asset_id=str(asset_id), data=value
                    )
                )
                prior = (
                    conn.execute(
                        select(p.evidence_tables["bg_audio_evidence"])
                        .where(p.evidence_tables["bg_audio_evidence"].c.asset_id == str(asset_id))
                        .order_by(p.evidence_tables["bg_audio_evidence"].c.created_at)
                    )
                    .mappings()
                    .all()
                )
                latest = {row["data"]["stream_key"]: row["data"] for row in prior}
                state = bg_state(analysis, asset["fingerprint"], list(latest.values()))
                conn.execute(
                    update(p.assets)
                    .where(p.assets.c.id == str(asset_id))
                    .values(
                        data={**asset["data"], "bg": state, "bg_rename_proposal": "NeedsReview"}
                    )
                )
                db.event(
                    conn, session["user_id"], "ASSET_BG_" + body["action"].upper(), str(asset_id)
                )
                return {"bg": state, "rename": "NeedsReview"}

            return command(conn, request, session["user_id"], body, apply)

    @app.post("/api/v1/subtitles/{candidate_id}/download", status_code=202)
    def download_subtitle(
        candidate_id: UUID, request: Request, session: dict[str, Any] = Depends(admin)
    ) -> dict[str, Any]:
        with db.transaction() as conn:

            def apply() -> dict[str, Any]:
                candidate = (
                    conn.execute(
                        select(p.evidence_tables["subtitle_candidates"]).where(
                            p.evidence_tables["subtitle_candidates"].c.id == str(candidate_id)
                        )
                    )
                    .mappings()
                    .first()
                )
                if not candidate or candidate["data"].get("provider") != "OpenSubtitles":
                    raise GateError("SUBTITLE_CANDIDATE_UNAVAILABLE")
                task_id = p.uid()
                conn.execute(
                    insert(p.tasks).values(
                        id=task_id,
                        kind="SUBTITLE_DOWNLOAD",
                        data={"candidate_id": str(candidate_id)},
                    )
                )
                db.event(conn, session["user_id"], "SUBTITLE_DOWNLOAD_REQUESTED", str(candidate_id))
                return {"operation_id": task_id, "state": "DownloadRequested"}

            return command(
                conn, request, session["user_id"], {"candidate_id": str(candidate_id)}, apply
            )

    from app.library_api import register

    register(app, db, admin, command)
    return app


if __name__ == "__main__":
    # Container interface only; production Compose publishes no API port.
    uvicorn.run(create_app(), host="0.0.0.0", port=8000, proxy_headers=False, access_log=False)  # noqa: S104  # nosec B104
