"""Queue starvation regressions against real PostgreSQL and synthetic providers only."""

import time
from datetime import timedelta
from threading import Event, Thread
from typing import Any

import pytest
from sqlalchemy import insert, select, update

from app import persistence as p
from app.domain import GateError
from app.worker import Worker
from app.worker_health import observed_health, queue_diagnostics


def enqueue(db: p.Database, **values: Any) -> str:
    with db.transaction() as conn:
        return str(
            conn.execute(
                insert(p.tasks)
                .values(kind="INVENTORY", **values)
                .returning(p.tasks.c.id)
            ).scalar_one()
        )


@pytest.mark.parametrize("provider", ["qbt", "jellyfin"])
@pytest.mark.parametrize("failure", ["unavailable", "timeout", "unexpected", "slow"])
def test_inventory_dispatch_survives_provider_poll_failure(
    stack: Any, monkeypatch: Any, provider: str, failure: str
) -> None:
    worker, qbt, jellyfin, _ = stack
    worker.cfg.write_enabled = False
    polled, release, claimed = Event(), Event(), Event()
    errors: list[BaseException] = []

    def unavailable(*args: Any, **kwargs: Any) -> Any:
        polled.set()
        if failure == "slow":
            assert release.wait(15)
            return (
                {"use_category_paths_in_manual_mode": False}
                if provider == "qbt"
                else True
            )
        if failure == "unexpected":
            raise ValueError("synthetic-private-payload-never-log")
        raise GateError(
            provider.upper() + ("_TIMEOUT" if failure == "timeout" else "_UNAVAILABLE"),
            "BlockedExternalDependency",
        )

    monkeypatch.setattr(
        qbt if provider == "qbt" else jellyfin,
        "get" if provider == "qbt" else "health",
        unavailable,
    )

    def inventory(task: dict[str, Any]) -> None:
        assert polled.wait(5)
        assert task["kind"] == "INVENTORY"
        claimed.set()
        worker.running = False

    monkeypatch.setattr(worker, "inventory", inventory)
    task_id = enqueue(worker.db)

    def run() -> None:
        try:
            worker.run()
        except BaseException as error:
            errors.append(error)

    started = time.monotonic()
    runner = Thread(target=run, daemon=True)
    runner.start()
    try:
        assert claimed.wait(10), "Eligible INVENTORY starved behind provider polling"
        assert time.monotonic() - started < 10
    finally:
        worker.running = False
        release.set()
        runner.join(5)
    assert not runner.is_alive() and not errors
    task = worker.db.one(select(p.tasks).where(p.tasks.c.id == task_id))
    assert task["state"] == "DONE" and task["attempts"] == 1
    assert not qbt.commands


def test_long_inventory_is_observable_and_next_scan_claims_promptly(
    stack: Any, monkeypatch: Any
) -> None:
    worker, _, _, _ = stack
    worker.cfg.lease_seconds = 6
    first_started, release_first, second_started = Event(), Event(), Event()
    release_provider, polled = Event(), Event()
    first = enqueue(worker.db)

    def slow_poll() -> None:
        polled.set()
        assert release_provider.wait(20)

    monkeypatch.setattr(worker, "poll_qbittorrent", slow_poll)

    def inventory(task: dict[str, Any]) -> None:
        if task["id"] == first:
            worker.db.reserve(task, ["library-scan"])
            # Durable progress from hours earlier must not become a task deadline.
            with worker.db.transaction() as conn:
                conn.execute(
                    update(p.tasks)
                    .where(p.tasks.c.id == first)
                    .values(created_at=p.now() - timedelta(hours=6))
                )
                conn.execute(
                    insert(p.scans).values(
                        task_id=first,
                        scope=["movies"],
                        state="RUNNING",
                        data={
                            "processed": 1234,
                            "checkpoint_at": (p.now() - timedelta(hours=2)).isoformat(),
                        },
                    )
                )
            first_started.set()
            assert release_first.wait(15)
        else:
            second_started.set()
            worker.running = False

    monkeypatch.setattr(worker, "inventory", inventory)
    runner = Thread(target=worker.run, daemon=True)
    runner.start()
    try:
        assert first_started.wait(5) and polled.wait(5)
        initial_lease = worker.db.one(select(p.tasks).where(p.tasks.c.id == first))[
            "lease_until"
        ]
        second = enqueue(worker.db, run_after=p.now() - timedelta(seconds=81))
        deadline = time.monotonic() + 5
        health: dict[str, Any] = {}
        while time.monotonic() < deadline:
            rows = worker.db.rows(
                select(p.settings_table).where(
                    p.settings_table.c.key == "worker_health"
                )
            )
            health = rows[0]["value"] if rows else {}
            current_lease = worker.db.one(select(p.tasks).where(p.tasks.c.id == first))[
                "lease_until"
            ]
            if (
                health.get("queue", {}).get("diagnostic") == "WAITING_FOR_ACTIVE_TASK"
                and current_lease > initial_lease
            ):
                break
            Event().wait(0.05)
        assert current_lease > initial_lease, (
            "Long scan lost its independent task heartbeat"
        )
        resource = worker.db.one(select(p.leases).where(p.leases.c.task_id == first))
        assert resource["until"] > initial_lease
        assert observed_health(health)["liveness"] == "ALIVE"
        assert health["dispatch"] == "BUSY"
        assert health["task"]["lease_valid"] is True
        assert health["task"]["progress"]["processed"] == 1234
        assert health["task"]["progress"]["checkpoint_age_seconds"] >= 7200
        assert health["queue"]["diagnostic"] == "WAITING_FOR_ACTIVE_TASK"
        released = time.monotonic()
        release_first.set()
        assert second_started.wait(10)
        assert time.monotonic() - released < 10
    finally:
        worker.running = False
        release_first.set()
        release_provider.set()
        runner.join(5)
    assert not runner.is_alive()
    assert worker.db.one(select(p.tasks).where(p.tasks.c.id == second))["attempts"] == 1


def test_overdue_diagnostics_do_not_claim_or_retry_tasks(stack: Any) -> None:
    worker, qbt, _, _ = stack
    db = worker.db
    overdue = enqueue(db, run_after=p.now() - timedelta(seconds=81))
    enqueue(db, run_after=p.now() + timedelta(hours=1))
    enqueue(db, state="BLOCKED", run_after=p.now() - timedelta(hours=1))
    before = db.rows(select(p.tasks))
    diagnostics = queue_diagnostics(
        db, None, (p.now() - timedelta(seconds=81)).isoformat()
    )
    assert diagnostics["dispatch"] == "STALLED"
    assert diagnostics["queue"]["eligible_count"] == 1
    assert diagnostics["queue"]["oldest_eligible_age_seconds"] >= 81
    assert diagnostics["queue"]["diagnostic"] == "DISPATCH_OVERDUE"
    assert "PostgreSQL" in diagnostics["queue"]["action"]
    worker.report_health()
    assert db.rows(select(p.tasks)) == before
    assert db.one(select(p.tasks).where(p.tasks.c.id == overdue))["attempts"] == 0
    assert not qbt.commands


def test_restart_preserves_inventory_fencing_and_recovers_once(
    stack: Any, monkeypatch: Any
) -> None:
    worker, qbt, jellyfin, tmdb = stack
    db = worker.db
    task_id = enqueue(db)
    old = db.claim(worker.owner)
    assert old is not None
    db.reserve(old, ["library-scan"])
    restarted = Worker(db, qbt, jellyfin, tmdb, worker.probe)
    assert restarted.run_once() is False
    with db.transaction() as conn:
        conn.execute(
            update(p.tasks)
            .where(p.tasks.c.id == task_id)
            .values(lease_until=p.now() - timedelta(seconds=1))
        )
        conn.execute(
            update(p.leases)
            .where(p.leases.c.task_id == task_id)
            .values(until=p.now() - timedelta(seconds=1))
        )
    executions = []

    def inventory(task: dict[str, Any]) -> None:
        db.reserve(task, ["library-scan"])
        assert task["lease_epoch"] == old["lease_epoch"] + 1
        with pytest.raises(GateError, match="LEASE_LOST"):
            db.heartbeat(old)
        executions.append(task["id"])

    monkeypatch.setattr(restarted, "inventory", inventory)
    assert restarted.run_once() is True
    assert restarted.run_once() is False
    assert executions == [task_id]
    assert db.one(select(p.tasks).where(p.tasks.c.id == task_id))["state"] == "DONE"
