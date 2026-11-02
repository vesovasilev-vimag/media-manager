"""PostgreSQL transactions; never hold a transaction over external I/O."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    case,
    create_engine,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine

from app.domain import GateError, Torrent, digest, eligible
from app.settings import Settings

metadata = MetaData()


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(UTC)


def table(name: str, *columns: Any, constraints: tuple[Any, ...] = ()) -> Table:
    return Table(
        name,
        metadata,
        Column("id", UUID(as_uuid=False), primary_key=True, default=uid),
        Column("created_at", DateTime(timezone=True), nullable=False, default=now),
        *columns,
        *constraints,
    )


users = table(
    "app_users",
    Column("username", String(80), nullable=False, unique=True),
    Column("password_hash", String, nullable=False),
    Column("singleton", Boolean, nullable=False, default=True, unique=True),
    constraints=(CheckConstraint("singleton = true"),),
)
sessions = table(
    "admin_sessions",
    Column("user_id", UUID(as_uuid=False), ForeignKey(users.c.id)),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("csrf_hash", String(64), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)
settings_table = Table(
    "service_settings",
    metadata,
    Column("key", String, primary_key=True),
    Column("value", JSONB, nullable=False),
    Column("revision", Integer, nullable=False, default=1),
)
clients = table(
    "qbt_clients",
    Column("name", String, unique=True, nullable=False),
    Column("baseline_at", DateTime(timezone=True)),
    Column("cutover_at", DateTime(timezone=True)),
)
torrents = table(
    "torrent_instances",
    Column("client_id", UUID(as_uuid=False), ForeignKey(clients.c.id), nullable=False),
    Column("info_hash", String(64), nullable=False),
    Column("generation", Integer, nullable=False),
    Column("added_on", BigInteger, nullable=False),
    Column("scope", String, nullable=False),
    Column("present", Boolean, nullable=False, default=True),
    Column("snapshot", JSONB, nullable=False),
    constraints=(
        UniqueConstraint("client_id", "info_hash", "generation"),
        CheckConstraint("generation > 0"),
        CheckConstraint(
            "scope IN ('LEGACY_READ_ONLY','VIMAG_MANAGED','EXTERNAL_UNMANAGED','TEST_FIXTURE')"
        ),
    ),
)
snapshots = table(
    "torrent_snapshots",
    Column("torrent_id", UUID(as_uuid=False), ForeignKey(torrents.c.id)),
    Column("fingerprint", String(64), nullable=False),
    Column("data", JSONB, nullable=False),
)
jobs = table(
    "import_jobs",
    Column("torrent_id", UUID(as_uuid=False), ForeignKey(torrents.c.id), unique=True),
    Column("kind", String, nullable=False, default="IMPORT"),
    Column("state", String, nullable=False, default="Queued"),
    Column("step", Integer, nullable=False, default=1),
    Column("revision", Integer, nullable=False, default=0),
    Column("paused", Boolean, nullable=False, default=False),
    Column("data", JSONB, nullable=False, default=dict),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=now),
    constraints=(CheckConstraint("step BETWEEN 1 AND 7"),),
)
items = table(
    "job_media_items",
    Column("job_id", UUID(as_uuid=False), ForeignKey(jobs.c.id), nullable=False),
    Column("item_key", String, nullable=False),
    Column("data", JSONB, nullable=False),
    constraints=(UniqueConstraint("job_id", "item_key"),),
)
plans = table(
    "import_plans",
    Column("job_id", UUID(as_uuid=False), ForeignKey(jobs.c.id), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("data", JSONB, nullable=False),
    constraints=(UniqueConstraint("job_id", "revision"),),
)
approvals = table(
    "approvals",
    Column("plan_id", UUID(as_uuid=False), ForeignKey(plans.c.id), nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("actor", String, nullable=False),
    Column("action", String, nullable=False),
    constraints=(UniqueConstraint("plan_id", "action"),),
)
tasks = table(
    "job_tasks",
    Column("job_id", UUID(as_uuid=False), ForeignKey(jobs.c.id)),
    Column("kind", String, nullable=False),
    Column("state", String, nullable=False, default="QUEUED"),
    Column("priority", Integer, nullable=False, default=100),
    Column("run_after", DateTime(timezone=True), nullable=False, default=now),
    Column("attempts", Integer, nullable=False, default=0),
    Column("lease_owner", String),
    Column("lease_epoch", BigInteger, nullable=False, default=0),
    Column("lease_until", DateTime(timezone=True)),
    Column("data", JSONB, nullable=False, default=dict),
)
leases = Table(
    "resource_leases",
    metadata,
    Column("resource_key", String, primary_key=True),
    Column("task_id", UUID(as_uuid=False), ForeignKey(tasks.c.id), nullable=False),
    Column("epoch", BigInteger, nullable=False),
    Column("until", DateTime(timezone=True), nullable=False),
)
operations = table(
    "file_operations",
    Column("job_id", UUID(as_uuid=False), ForeignKey(jobs.c.id)),
    Column("plan_id", UUID(as_uuid=False), ForeignKey(plans.c.id)),
    Column("op_key", String, nullable=False, unique=True),
    Column("kind", String, nullable=False),
    Column("status", String, nullable=False),
    Column("intent", JSONB, nullable=False),
    Column("observed", JSONB),
    Column("verified_at", DateTime(timezone=True)),
)
assets = table(
    "library_assets",
    Column("root", String, nullable=False),
    Column("relative_path", String, nullable=False),
    Column("identity_key", String),
    Column("edition", String),
    Column("fingerprint", String(64), nullable=False),
    Column("data", JSONB, nullable=False),
    Column("title", String, nullable=False, server_default=""),
    Column("category", String),
    Column("video_quality", String),
    Column("audio_codecs", ARRAY(String), nullable=False, server_default="{}"),
    Column("audio_languages", ARRAY(String), nullable=False, server_default="{}"),
    Column("subtitle_languages", ARRAY(String)),
    Column("file_size_bytes", BigInteger),
    Column("mtime_ns", BigInteger),
    Column("observed_size", BigInteger),
    Column("availability", String, nullable=False, server_default="AVAILABLE"),
    Column("workflow_state", String, nullable=False, server_default="ACTIVE"),
    Column("last_seen", DateTime(timezone=True)),
    Column("revision", Integer, nullable=False, server_default="1"),
    constraints=(UniqueConstraint("root", "relative_path"),),
)
refs = table(
    "media_file_refs",
    Column("asset_id", UUID(as_uuid=False), ForeignKey(assets.c.id)),
    Column("torrent_id", UUID(as_uuid=False), ForeignKey(torrents.c.id)),
    Column("root", String, nullable=False),
    Column("relative_path", String, nullable=False),
    Column("data", JSONB, nullable=False, default=dict),
)
sidecars = table(
    "sidecar_manifests",
    Column("root", String, nullable=False),
    Column("relative_path", String, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("locked", Boolean, nullable=False, default=False),
    Column("data", JSONB, nullable=False),
    constraints=(UniqueConstraint("root", "relative_path"),),
)
quarantine = table(
    "quarantine_manifests",
    Column("asset_id", UUID(as_uuid=False), ForeignKey(assets.c.id)),
    Column("plan_sha256", String(64), nullable=False),
    Column("state", String, nullable=False),
    Column("data", JSONB, nullable=False),
)
audit = table(
    "audit_events",
    Column("actor", String, nullable=False),
    Column("kind", String, nullable=False),
    Column("target", String),
    Column("data", JSONB, nullable=False, default=dict),
)
idempotency = Table(
    "idempotency_requests",
    metadata,
    Column("key", String, primary_key=True),
    Column("actor", String, nullable=False),
    Column("request_hash", String, nullable=False),
    Column("response", JSONB, nullable=False),
)
rate_limits = Table(
    "auth_rate_limits",
    metadata,
    Column("key", String, primary_key=True),
    Column("attempts", Integer, nullable=False),
    Column("until", DateTime(timezone=True), nullable=False),
)
# Dedicated evidence records keep provenance separate from mutable item presentation.
evidence_tables = {
    name: table(
        name,
        Column("item_id", UUID(as_uuid=False), ForeignKey(items.c.id)),
        Column("asset_id", UUID(as_uuid=False), ForeignKey(assets.c.id)),
        Column("data", JSONB, nullable=False),
    )
    for name in (
        "media_inspections",
        "identity_candidates",
        "bg_audio_evidence",
        "quality_decisions",
        "subtitle_candidates",
        "jellyfin_verifications",
    )
}

policies = table(
    "library_policies",
    Column("revision", Integer, nullable=False, unique=True),
    Column("data", JSONB, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("actor", String, nullable=False),
)
scans = table(
    "library_scans",
    Column("task_id", UUID(as_uuid=False), ForeignKey(tasks.c.id), nullable=False),
    Column("scope", JSONB, nullable=False),
    Column("state", String, nullable=False),
    Column("data", JSONB, nullable=False, default=dict),
)
maintenance_files = table(
    "maintenance_files",
    Column("job_id", UUID(as_uuid=False), ForeignKey(jobs.c.id), nullable=False),
    Column("asset_id", UUID(as_uuid=False), ForeignKey(assets.c.id), nullable=False),
    Column("state", String, nullable=False),
    Column("phase", Integer, nullable=False, default=0),
    Column("attempts", Integer, nullable=False, default=0),
    Column("data", JSONB, nullable=False),
    constraints=(UniqueConstraint("job_id", "asset_id"),),
)
subtitle_versions = table(
    "subtitle_versions",
    Column("asset_id", UUID(as_uuid=False), ForeignKey(assets.c.id), nullable=False),
    Column("generation", Integer, nullable=False),
    Column("data", JSONB, nullable=False),
    constraints=(UniqueConstraint("asset_id", "generation"),),
)
tombstones = table(
    "asset_tombstones",
    Column("asset_id", UUID(as_uuid=False), ForeignKey(assets.c.id), nullable=False),
    Column("job_id", UUID(as_uuid=False), ForeignKey(jobs.c.id), nullable=False),
    Column("data", JSONB, nullable=False),
    constraints=(UniqueConstraint("job_id", "asset_id"),),
)


class Database:
    def __init__(self, config: Settings | None = None, engine: Engine | None = None):
        self.config = config or Settings()
        self.engine = engine or create_engine(
            self.config.database_url(), pool_pre_ping=True, hide_parameters=True
        )

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        with self.engine.begin() as conn:
            yield conn

    def rows(self, query: Any) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query).mappings()]

    def one(self, query: Any) -> dict[str, Any]:
        result = self.rows(query)
        if not result:
            raise GateError("NOT_FOUND")
        return result[0]

    def event(
        self,
        conn: Connection,
        actor: str,
        kind: str,
        target: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        # Callers supply structured reason codes and references, never raw remote payloads/errors.
        conn.execute(insert(audit).values(actor=actor, kind=kind, target=target, data=data or {}))

    def discover(self, observed: list[Torrent], automatic: bool = False) -> list[str]:
        created = []
        with self.transaction() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(4710001)"))
            client = (
                conn.execute(select(clients).where(clients.c.name == "primary")).mappings().first()
            )
            if client is None:
                cid = uid()
                conn.execute(insert(clients).values(id=cid, name="primary", baseline_at=now()))
                baseline = True
                cutover = False
            else:
                cid, baseline, cutover = client["id"], False, bool(client["cutover_at"])
            present = (
                conn.execute(select(torrents).where(torrents.c.client_id == cid)).mappings().all()
            )
            hashes = {t.info_hash for t in observed}
            for row in present:
                if row["info_hash"] not in hashes and row["present"]:
                    conn.execute(
                        update(torrents).where(torrents.c.id == row["id"]).values(present=False)
                    )
            for t in observed:
                previous = [r for r in present if r["info_hash"] == t.info_hash]
                latest = max(previous, key=lambda r: r["generation"]) if previous else None
                new_instance = (
                    not latest or not latest["present"] or latest["added_on"] != t.added_on
                )
                if new_instance:
                    if latest and latest["present"]:
                        conn.execute(
                            update(torrents)
                            .where(torrents.c.id == latest["id"])
                            .values(present=False)
                        )
                    scope = "LEGACY_READ_ONLY" if baseline else "EXTERNAL_UNMANAGED"
                    if eligible(
                        t,
                        baseline=baseline,
                        seen_before=bool(previous),
                        cutover=cutover
                        and automatic
                        and client is not None
                        and t.added_on >= int(client["cutover_at"].timestamp()),
                    ):
                        scope = "VIMAG_MANAGED"
                    tid = uid()
                    conn.execute(
                        insert(torrents).values(
                            id=tid,
                            client_id=cid,
                            info_hash=t.info_hash,
                            generation=latest["generation"] + 1 if latest else 1,
                            added_on=t.added_on,
                            scope=scope,
                            snapshot=t.stable(),
                        )
                    )
                    self.event(conn, "worker", "TORRENT_DISCOVERED", tid, {"scope": scope})
                else:
                    if latest is None or client is None:
                        raise GateError("DISCOVERY_INCONSISTENT", "RecoveryRequired")
                    tid, scope = latest["id"], latest["scope"]
                    # New incomplete torrents may become eligible on completion after cutover.
                    if (
                        scope == "EXTERNAL_UNMANAGED"
                        and latest["generation"] == 1
                        and cutover
                        and automatic
                        and t.added_on >= int(client["cutover_at"].timestamp())
                        and eligible(t, baseline=False, seen_before=False, cutover=True)
                        and latest["snapshot"] == t.stable()
                    ):
                        scope = "VIMAG_MANAGED"
                        conn.execute(
                            update(torrents).where(torrents.c.id == tid).values(scope=scope)
                        )
                if t.complete() and scope in {"VIMAG_MANAGED", "TEST_FIXTURE"}:
                    jid = uid()
                    result = conn.execute(
                        pg_insert(jobs)
                        .values(id=jid, torrent_id=tid)
                        .on_conflict_do_nothing(index_elements=["torrent_id"])
                        .returning(jobs.c.id)
                    )
                    if result.first() is not None:
                        conn.execute(
                            insert(snapshots).values(
                                torrent_id=tid, fingerprint=digest(t.stable()), data=t.stable()
                            )
                        )
                        conn.execute(insert(tasks).values(job_id=jid, kind="IMPORT"))
                        created.append(jid)
            return created

    def claim(self, owner: str) -> dict[str, Any] | None:
        with self.transaction() as conn:
            conn.execute(
                update(tasks)
                .where(tasks.c.state == "RUNNING", tasks.c.lease_until < now())
                .values(state="RECONCILING", lease_owner=None)
            )
            row = (
                conn.execute(
                    select(tasks)
                    .where(
                        tasks.c.state.in_(["QUEUED", "RETRYABLE", "RECONCILING"]),
                        tasks.c.run_after <= now(),
                    )
                    .order_by(tasks.c.priority, tasks.c.run_after)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            return dict(
                conn.execute(
                    update(tasks)
                    .where(tasks.c.id == row["id"])
                    .values(
                        state="RUNNING",
                        lease_owner=owner,
                        lease_epoch=row["lease_epoch"] + 1,
                        lease_until=now() + timedelta(seconds=self.config.lease_seconds),
                        attempts=row["attempts"] + 1,
                    )
                    .returning(tasks)
                )
                .mappings()
                .one()
            )

    def assert_lease(self, conn: Connection, task: dict[str, Any]) -> None:
        row = (
            conn.execute(select(tasks).where(tasks.c.id == task["id"]).with_for_update())
            .mappings()
            .one()
        )
        if (
            row["state"] != "RUNNING"
            or row["lease_owner"] != task["lease_owner"]
            or row["lease_epoch"] != task["lease_epoch"]
            or row["lease_until"] <= now()
        ):
            raise GateError("LEASE_LOST", "Reconciling")

    def reserve(self, task: dict[str, Any], resources: list[str]) -> None:
        with self.transaction() as conn:
            self.assert_lease(conn, task)
            for resource in sorted(set(resources)):
                result = conn.execute(
                    pg_insert(leases)
                    .values(
                        resource_key=resource,
                        task_id=task["id"],
                        epoch=1,
                        until=task["lease_until"],
                    )
                    .on_conflict_do_update(
                        index_elements=["resource_key"],
                        set_={
                            "task_id": task["id"],
                            "epoch": case(
                                (
                                    (leases.c.task_id == task["id"]) & (leases.c.until > now()),
                                    leases.c.epoch,
                                ),
                                else_=leases.c.epoch + 1,
                            ),
                            "until": task["lease_until"],
                        },
                        where=(leases.c.until < now())
                        | (
                            (leases.c.task_id == task["id"])
                            & (leases.c.epoch == task.get("resource_epochs", {}).get(resource, -1))
                        ),
                    )
                    .returning(leases.c.epoch)
                )
                reserved = result.first()
                if reserved is None:
                    raise GateError("RESOURCE_BUSY", "FailedRecoverable")
                task.setdefault("resource_epochs", {})[resource] = reserved[0]

    def fence(self, task: dict[str, Any], resources: list[str]) -> None:
        with self.transaction() as conn:
            self.assert_lease(conn, task)
            for resource in resources:
                row = (
                    conn.execute(select(leases).where(leases.c.resource_key == resource))
                    .mappings()
                    .first()
                )
                if (
                    not row
                    or row["task_id"] != task["id"]
                    or row["epoch"] != task.get("resource_epochs", {}).get(resource)
                    or row["until"] <= now()
                ):
                    raise GateError("RESOURCE_LEASE_LOST", "Reconciling")

    def heartbeat(self, task: dict[str, Any]) -> None:
        with self.transaction() as conn:
            self.assert_lease(conn, task)
            until = now() + timedelta(seconds=self.config.lease_seconds)
            conn.execute(update(tasks).where(tasks.c.id == task["id"]).values(lease_until=until))
            for resource, epoch in task.get("resource_epochs", {}).items():
                conn.execute(
                    update(leases)
                    .where(
                        leases.c.resource_key == resource,
                        leases.c.task_id == task["id"],
                        leases.c.epoch == epoch,
                        leases.c.until > now(),
                    )
                    .values(until=until)
                )
            task["lease_until"] = until

    def intent(
        self,
        task: dict[str, Any],
        plan: dict[str, Any],
        kind: str,
        target: str,
        data: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        key = digest([task["job_id"], plan["sha256"], kind, target])
        with self.transaction() as conn:
            self.assert_lease(conn, task)
            existing = (
                conn.execute(select(operations).where(operations.c.op_key == key))
                .mappings()
                .first()
            )
            if existing:
                if existing["intent"] != data:
                    raise GateError("INTENT_MISMATCH", "RecoveryRequired")
                return dict(existing), False
            op = dict(
                conn.execute(
                    insert(operations)
                    .values(
                        job_id=task["job_id"],
                        plan_id=plan["id"],
                        op_key=key,
                        kind=kind,
                        status="PREPARED",
                        intent=data,
                    )
                    .returning(operations)
                )
                .mappings()
                .one()
            )
            self.event(conn, "worker", "OPERATION_PREPARED", op["id"], {"kind": kind})
            return op, True

    def op_status(
        self, op: dict[str, Any], status: str, observed: dict[str, Any] | None = None
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                update(operations)
                .where(operations.c.id == op["id"])
                .values(
                    status=status,
                    observed=observed,
                    verified_at=now() if status == "VERIFIED" else None,
                )
            )
            self.event(conn, "worker", "OPERATION_" + status, op["id"])

    def finish_task(self, task: dict[str, Any], state: str, delay: int = 0) -> None:
        with self.transaction() as conn:
            self.assert_lease(conn, task)
            conn.execute(
                update(tasks)
                .where(tasks.c.id == task["id"])
                .values(state=state, run_after=now() + timedelta(seconds=delay), lease_until=None)
            )
            conn.execute(update(leases).where(leases.c.task_id == task["id"]).values(until=now()))
