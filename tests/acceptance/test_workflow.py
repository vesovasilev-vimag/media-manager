from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select, update

from app import persistence as p
from app.domain import GateError, Identity
from app.worker import Worker
from conftest import drive, onboard, torrent


def job_state(db: p.Database, jid: str) -> str:
    return db.one(select(p.jobs).where(p.jobs.c.id == jid))["state"]


def test_T01_new_movie_full_workflow(stack: Any) -> None:
    worker, qbt, jellyfin, _ = stack
    t = torrent(worker.db)
    jid = onboard(worker, qbt, t)
    drive(worker)
    assert job_state(worker.db, jid) == "CompletedWithWarnings"
    plan = worker.db.one(select(p.plans).where(p.plans.c.job_id == jid))
    path = worker.cfg.nas_root / "Library" / plan["data"]["entries"][0]["destination"]
    assert (
        path.is_file()
        and (path.parent / "movie.nfo").is_file()
        and (path.parent / "poster.jpg").is_file()
    )
    assert jellyfin.refresh_count == 1
    assert [c[0] for c in qbt.commands].count("setLocation") == 1
    assert [c[0] for c in qbt.commands].count("recheck") == 1
    assert (
        worker.db.one(select(p.items).where(p.items.c.job_id == jid))["data"][
            "published"
        ]
        is True
    )


def test_T04_season_pack_one_move_multiple_children(stack: Any) -> None:
    worker, qbt, jellyfin, _ = stack
    t = torrent(
        worker.db,
        files=[
            "Pack/Synthetic 2026 tmdbid-1 S01E01.mkv",
            "Pack/Synthetic 2026 tmdbid-1 S01E02.mkv",
        ],
        category="series",
    )
    jid = onboard(worker, qbt, t)
    drive(worker)
    assert job_state(worker.db, jid) == "CompletedWithWarnings"
    items = worker.db.rows(select(p.items).where(p.items.c.job_id == jid))
    assert len(items) == 2 and all(c["data"]["published"] for c in items)
    assert len([c for c in qbt.commands if c[0] == "setLocation"]) == 1
    assert (
        len(
            worker.db.rows(
                select(p.operations).where(p.operations.c.kind == "HARDLINK")
            )
        )
        == 2
    )


def test_T05_nas_outage_retains_source_and_intent(stack: Any, monkeypatch: Any) -> None:
    worker, qbt, _, _ = stack
    t = torrent(worker.db)
    jid = onboard(worker, qbt, t)
    original = worker.nas_health

    def offline(*args: Any) -> None:
        raise GateError("NAS_OFFLINE", "BlockedExternalDependency")

    monkeypatch.setattr(worker, "nas_health", offline)
    drive(worker)
    assert job_state(worker.db, jid) == "BlockedExternalDependency"
    assert (worker.cfg.staging_root / t.files[0]["name"]).is_file()
    assert not qbt.commands
    monkeypatch.setattr(worker, "nas_health", original)


def test_T09_IT05_parallel_duplicate_discovery(stack: Any) -> None:
    worker, qbt, _, _ = stack
    t = torrent(worker.db)
    jid = onboard(worker, qbt, t)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(
            pool.map(lambda _: worker.db.discover([t], automatic=True), range(3))
        )
    assert results == [[], [], []]
    drive(worker)
    assert len(worker.db.rows(select(p.jobs))) == 1
    assert len(worker.db.rows(select(p.plans))) == 1
    assert [c[0] for c in qbt.commands].count("setLocation") == 1
    assert job_state(worker.db, jid) == "CompletedWithWarnings"


def test_T10_IT06_crash_after_dispatch_reconciles_no_second_move(stack: Any) -> None:
    worker, qbt, jellyfin, tmdb = stack
    jid = onboard(worker, qbt, torrent(worker.db))
    for _ in range(10):
        drive(worker, 1)
        if any(c[0] == "setLocation" for c in qbt.commands):
            break
    assert [c[0] for c in qbt.commands].count("setLocation") == 1
    restarted = Worker(worker.db, qbt, jellyfin, tmdb, worker.probe)
    drive(restarted)
    assert [c[0] for c in qbt.commands].count("setLocation") == 1
    assert job_state(worker.db, jid) == "CompletedWithWarnings"


def test_T11_http_accepted_is_not_completed(stack: Any) -> None:
    worker, qbt, _, _ = stack
    jid = onboard(worker, qbt, torrent(worker.db))
    for _ in range(10):
        drive(worker, 1)
        if any(c[0] == "setLocation" for c in qbt.commands):
            break
    assert job_state(worker.db, jid) not in {"Completed", "CompletedWithWarnings"}
    assert (
        worker.db.one(select(p.operations).where(p.operations.c.kind == "MOVE"))[
            "status"
        ]
        == "COMMAND_REQUESTED"
    )


def test_T12_failed_pieces_blocks_terminal_and_cleanup(stack: Any) -> None:
    worker, qbt, _, _ = stack
    qbt.fail_recheck = True
    jid = onboard(worker, qbt, torrent(worker.db))
    drive(worker)
    assert job_state(worker.db, jid) == "RecoveryRequired"
    assert not worker.db.rows(
        select(p.operations).where(p.operations.c.kind == "CLEANUP")
    )


def test_T13_destination_collision_never_overwritten(stack: Any) -> None:
    from app.domain import name_for

    worker, qbt, _, _ = stack
    t = torrent(worker.db)
    path = (
        worker.cfg.nas_root
        / "Library"
        / name_for(
            "movies",
            Identity("Synthetic", 2026, "movie", "1", confirmed=True),
            "1080p",
            "NO_BG",
            ".mkv",
        )
    )
    path.parent.mkdir(parents=True)
    path.write_bytes(b"existing-external-content")
    jid = onboard(worker, qbt, t)
    drive(worker)
    assert (
        job_state(worker.db, jid) == "NeedsReview"
        and path.read_bytes() == b"existing-external-content"
    )
    assert not qbt.commands


def test_T14_category_drift_invalidates_plan(stack: Any) -> None:
    worker, qbt, _, _ = stack
    t = torrent(worker.db)
    jid = onboard(worker, qbt, t)
    drive(worker, 1)
    qbt.torrents[t.info_hash].category = "concerts"
    drive(worker)
    assert job_state(worker.db, jid) == "ReplanRequired"
    assert not any(c[0] == "setLocation" for c in qbt.commands)


def test_T22_T35_IT11_jellyfin_pending_never_repeats_move(stack: Any) -> None:
    worker, qbt, jellyfin, _ = stack
    jellyfin.recognize = False
    jid = onboard(worker, qbt, torrent(worker.db))
    drive(worker, 15)
    assert job_state(worker.db, jid) == "PublishPending", worker.db.one(
        select(p.jobs).where(p.jobs.c.id == jid)
    )["data"]
    assert [c[0] for c in qbt.commands].count("setLocation") == 1
    jellyfin.recognize = True
    drive(worker)
    assert job_state(worker.db, jid) == "CompletedWithWarnings"


def test_T36_mixed_child_publish_failure_blocks_parent(stack: Any) -> None:
    worker, qbt, jellyfin, _ = stack
    t = torrent(worker.db, files=["A 2026 tmdbid-1.mkv", "B 2026 tmdbid-1.mkv"])
    jid = onboard(worker, qbt, t)
    jellyfin.missing_titles.add("B")
    drive(worker, 15)
    assert job_state(worker.db, jid) == "PublishPending", worker.db.one(
        select(p.jobs).where(p.jobs.c.id == jid)
    )["data"]
    children = worker.db.rows(select(p.items).where(p.items.c.job_id == jid))
    assert sorted(c["data"]["published"] for c in children) == [False, True]


def test_IT01_first_snapshot_any_count_legacy_zero_commands(stack: Any) -> None:
    worker, qbt, _, _ = stack
    observed = [torrent(worker.db, index=i) for i in range(1, 93)]
    worker.db.discover(observed, automatic=True)
    assert {r["scope"] for r in worker.db.rows(select(p.torrents))} == {
        "LEGACY_READ_ONLY"
    }
    assert len(worker.db.rows(select(p.torrents))) == 92 and not qbt.commands
    assert not worker.db.rows(select(p.jobs))


def test_IT12_remove_readd_legacy_hash_never_inherits_management(stack: Any) -> None:
    worker, qbt, _, _ = stack
    t = torrent(worker.db)
    worker.db.discover([t])
    worker.db.discover([])
    with worker.db.transaction() as conn:
        conn.execute(update(p.clients).values(cutover_at=p.now() - timedelta(days=1)))
    t.added_on = int(p.now().timestamp())
    worker.db.discover([t], automatic=True)
    rows = worker.db.rows(select(p.torrents).order_by(p.torrents.c.generation))
    assert [r["generation"] for r in rows] == [1, 2]
    assert (
        rows[0]["scope"] == "LEGACY_READ_ONLY"
        and rows[1]["scope"] == "EXTERNAL_UNMANAGED"
    )
    assert not worker.db.rows(select(p.jobs))


def test_IT07_expired_fence_denies_old_worker(stack: Any) -> None:
    worker, qbt, _, _ = stack
    onboard(worker, qbt, torrent(worker.db))
    task = worker.db.claim("old")
    assert task is not None
    worker.db.reserve(task, ["nas-move"])
    with worker.db.transaction() as conn:
        conn.execute(
            update(p.tasks)
            .where(p.tasks.c.id == task["id"])
            .values(lease_until=p.now() - timedelta(seconds=1))
        )
    replacement = worker.db.claim("new")
    assert replacement is not None and replacement["lease_epoch"] > task["lease_epoch"]
    with pytest.raises(GateError, match="LEASE_LOST"):
        worker.db.fence(task, ["nas-move"])
    assert not qbt.commands


def test_IT17_new_manual_post_cutover_automatic_eligibility(stack: Any) -> None:
    worker, qbt, _, _ = stack
    t = torrent(worker.db)
    onboard(worker, qbt, t)
    assert worker.db.one(select(p.torrents))["scope"] == "VIMAG_MANAGED"
    other = torrent(worker.db, index=2, auto_tmm=True)
    other.added_on = int(p.now().timestamp())
    worker.db.discover([t, other], automatic=True)
    assert (
        worker.db.one(
            select(p.torrents).where(p.torrents.c.info_hash == other.info_hash)
        )["scope"]
        == "EXTERNAL_UNMANAGED"
    )


def test_IT14_revoked_jellyfin_does_not_disturb_seeding(stack: Any) -> None:
    worker, qbt, jellyfin, _ = stack
    jellyfin.fail_auth = True
    t = torrent(worker.db)
    jid = onboard(worker, qbt, t)
    drive(worker)
    assert job_state(worker.db, jid) == "BlockedExternalDependency"
    current = qbt.torrent(t.info_hash)
    assert current.save_path.startswith("/library/") and current.complete()
    assert not any(c[0] == "stop" for c in qbt.commands)
