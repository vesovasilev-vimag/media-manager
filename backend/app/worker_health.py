"""Read-only queue diagnostics. Observations never reclaim tasks or restart processes."""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app import persistence as p

DISPATCH_SECONDS = 10
HEARTBEAT_SECONDS = 15


def age_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0, (p.now() - datetime.fromisoformat(value)).total_seconds())
    except (TypeError, ValueError):
        return None


def observed_health(value: dict[str, Any]) -> dict[str, Any]:
    """Evaluate durable health at read time, including a stopped monitor/process."""
    age = age_seconds(value.get("time"))
    result = {**value, "heartbeat_age_seconds": age}
    if age is None or age > HEARTBEAT_SECONDS:
        result.update(state="STALE", liveness="UNKNOWN", dispatch="UNKNOWN")
    return result


def queue_diagnostics(
    db: p.Database, active: dict[str, Any] | None, last_dispatch: str
) -> dict[str, Any]:
    now = p.now()
    counts = db.one(
        select(func.count().label("count"), func.min(p.tasks.c.run_after).label("oldest")).where(
            p.tasks.c.state.in_(["QUEUED", "RETRYABLE", "RECONCILING"]), p.tasks.c.run_after <= now
        )
    )
    oldest = counts["oldest"]
    age = max(0, (now - oldest).total_seconds()) if oldest else 0
    dispatch_age = age_seconds(last_dispatch)
    dispatch = (
        "READY" if dispatch_age is not None and dispatch_age <= DISPATCH_SECONDS else "STALLED"
    )
    task = None
    if active:
        rows = db.rows(select(p.tasks).where(p.tasks.c.id == active["id"]))
        row = rows[0] if rows else None
        valid = bool(
            row
            and row["state"] == "RUNNING"
            and row["lease_owner"] == active["lease_owner"]
            and row["lease_epoch"] == active["lease_epoch"]
            and row["lease_until"] > now
            and not active.get("heartbeat_failed")
        )
        dispatch = "BUSY" if valid else "LEASE_LOST"
        task = {
            "id": active["id"],
            "kind": active["kind"],
            "lease_valid": valid,
            "lease_until": row["lease_until"].isoformat() if row and row["lease_until"] else None,
        }
        if active["kind"] == "INVENTORY":
            scans = db.rows(select(p.scans).where(p.scans.c.task_id == active["id"]))
            if scans:
                scan = scans[0]
                task["progress"] = {
                    "state": scan["state"],
                    **{
                        key: scan["data"].get(key, 0)
                        for key in ("processed", "new", "changed", "unchanged", "missing", "failed")
                    },
                }
                task["progress"]["note"] = "CHECKPOINT_COUNTS_NOT_A_DEADLINE"
                task["progress"]["checkpoint_at"] = scan["data"].get("checkpoint_at")
                task["progress"]["checkpoint_age_seconds"] = age_seconds(
                    scan["data"].get("checkpoint_at")
                )
    diagnostic = "NO_OVERDUE_TASKS"
    if age > DISPATCH_SECONDS:
        diagnostic = "WAITING_FOR_ACTIVE_TASK" if active else "DISPATCH_OVERDUE"
        if active is None and dispatch == "READY":
            dispatch = "QUEUE_OVERDUE"
    return {
        "dispatch": dispatch,
        "task": task,
        "queue": {
            "eligible_count": counts["count"],
            "oldest_eligible_age_seconds": age,
            "diagnostic": diagnostic,
            "action": "Inspect dispatch heartbeat, PostgreSQL locks/connectivity and Worker logs; preserve leases and journal before controlled recovery."
            if diagnostic == "DISPATCH_OVERDUE"
            else None,
        },
    }
