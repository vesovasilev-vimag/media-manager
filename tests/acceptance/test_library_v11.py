"""v1.1 contracts against real disposable PostgreSQL and isolated NAS fixtures."""

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from sqlalchemy import insert, select, update

from app import catalogue, library_policy
from app import persistence as p
from app.storage import sha256
from conftest import drive, login, synthetic_probe, torrent


def asset(
    db: p.Database, name: str = "Movies/Old/Fixture.mkv", **changes: Any
) -> dict[str, Any]:
    path = db.config.nas_root / "Library" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic-media-" + name.encode())
    data = {
        "probe": synthetic_probe(path),
        "identity": {
            "title": Path(name).stem,
            "year": 2026,
            "media_type": "movie",
            "edition": "Theatrical",
            "confirmed": True,
        },
        "bg": "NO_BG",
    }
    data.update(changes.pop("data", {}))
    row = {
        "id": p.uid(),
        "root": "library",
        "relative_path": name,
        "fingerprint": sha256(path),
        "data": data,
        **catalogue.normalized(name, data),
        **changes,
    }
    with db.transaction() as conn:
        conn.execute(insert(p.assets).values(**row))
    return db.one(select(p.assets).where(p.assets.c.id == row["id"]))


def post(client: Any, path: str, body: Any = None) -> Any:
    client.headers["Idempotency-Key"] = str(uuid4())
    return client.post("/api/v1" + path, json=body)


def plan(stack: Any, client: Any, kind: str, ids: list[str]) -> dict[str, Any]:
    response = post(client, f"/library/{kind}/plans", {"asset_ids": ids})
    assert response.status_code == 202, response.text
    drive(stack[0])
    response = client.get(f"/api/v1/library/{kind}/" + response.json()["job_id"])
    assert response.status_code == 200, response.text
    return response.json()


def approve(client: Any, kind: str, result: dict[str, Any]) -> Any:
    return post(
        client,
        f"/library/{kind}/{result['id']}/approve",
        {
            "plan_revision": result["plan"]["revision"],
            "plan_sha256": result["plan"]["sha256"],
            "confirmed": True,
        },
    )


def test_LIB_4119_sql_pagination_multistream_actual_bytes(db: p.Database) -> None:
    rows = []
    for ix in range(4119):
        cat = (
            "Series"
            if ix < 3315
            else "Movies"
            if ix < 3905
            else "Animations"
            if ix < 4027
            else "Documentaries"
        )
        probe = {
            "format": {"size": str(1000 + ix)},
            "streams": [
                {"codec_type": "video", "width": 1920, "height": 1080},
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "tags": {"language": "eng"},
                },
                {
                    "codec_type": "audio",
                    "codec_name": "ac3",
                    "tags": {"language": "bul"},
                },
                {"codec_type": "subtitle", "tags": {"language": "eng"}},
            ],
        }
        name = f"{cat}/Synthetic {ix:04}.mkv"
        data = {"probe": probe, "identity": {"title": f"Title {ix:04}"}}
        rows.append(
            {
                "root": "library",
                "relative_path": name,
                "fingerprint": f"{ix:064x}",
                "data": data,
                **catalogue.normalized(name, data),
            }
        )
    with db.transaction() as conn:
        conn.execute(insert(p.assets), rows)
    client = login(db)
    result = client.get("/api/v1/library/assets?limit=25&offset=4100").json()
    assert result["total"] == 4119 and len(result["items"]) == 19
    result = client.get(
        "/api/v1/library/assets?search=Title%204100&audio_language=bg&audio_codec=ac3&subtitle_language=en"
    ).json()
    assert result["total"] == 1 and result["items"][0]["title"] == "Title 4100"
    summary = client.get("/api/v1/library/analytics").json()["categories"]
    assert sum(c["bytes"] for c in summary) == sum(1000 + i for i in range(4119))
    assert {c["category"]: c["count"] for c in summary} == {
        "series": 3315,
        "movies": 590,
        "animations": 122,
        "documentaries": 92,
        "concerts": 0,
    }
    assert client.get("/api/v1/library/assets?sort=title;DROP").status_code == 422
    assert client.get("/api/v1/library/assets?category=../../").status_code == 422
    assert (
        client.get("/api/v1/library/assets?search=%27%20OR%201%3D1--").json()["total"]
        == 0
    )
    first = client.get("/api/v1/library/assets?limit=25").json()["items"]
    second = client.get("/api/v1/library/assets?limit=25&offset=25").json()["items"]
    assert not {r["id"] for r in first} & {r["id"] for r in second}


def test_LIB_unknown_size_and_missing_streams_are_not_absence(db: p.Database) -> None:
    a = asset(db, data={"probe": {"format": {"size": "NaN"}}})
    assert a["file_size_bytes"] is None and a["subtitle_languages"] is None
    assert (
        catalogue.normalized("Movies/a.mkv", {"probe": {"format": {"size": "9" * 40}}})[
            "file_size_bytes"
        ]
        is None
    )


def test_SCAN_incremental_missing_reappears_and_failed_scope(
    stack: Any, monkeypatch: Any
) -> None:
    worker, qbt, _, _ = stack
    db = worker.db
    a = asset(db)
    client = login(db)
    calls = []
    original = worker.probe
    worker.probe = lambda path: (calls.append(path), original(path))[1]
    for expected in [1, 1]:
        result = post(client, "/library/scans", {"category": "movies"}).json()
        drive(worker)
        assert (
            client.get("/api/v1/library/scans/" + result["id"]).json()["state"]
            == "COMPLETED"
        )
        assert len(calls) == expected
    path = db.config.nas_root / "Library" / a["relative_path"]
    path.write_bytes(b"changed-synthetic-content")
    post(client, "/library/scans", {"category": "movies"})
    drive(worker)
    assert len(calls) == 2
    # Fast re-scan must preserve fingerprint, identity, revision and BG decisions.
    stable = db.one(select(p.assets).where(p.assets.c.id == a["id"]))
    result = post(client, "/library/scans", {"category": "movies"}).json()
    drive(worker)
    assert (
        client.get("/api/v1/library/scans/" + result["id"]).json()["state"]
        == "COMPLETED"
    )
    after = db.one(select(p.assets).where(p.assets.c.id == a["id"]))
    assert after["fingerprint"] == stable["fingerprint"]
    assert after["revision"] == stable["revision"]
    assert after["data"]["identity"] == stable["data"]["identity"]
    assert len(calls) == 2
    path.unlink()
    post(client, "/library/scans", {"category": "movies"})
    drive(worker)
    assert db.one(select(p.assets))["availability"] == "MISSING"
    path.write_bytes(b"reappeared-synthetic-content")
    post(client, "/library/scans", {"category": "movies"})
    drive(worker)
    assert db.one(select(p.assets))["availability"] == "AVAILABLE"
    from app import inventory

    monkeypatch.setattr(
        inventory,
        "enumerate_category",
        lambda root: (_ for _ in ()).throw(PermissionError()),
    )
    post(client, "/library/scans", {"category": "movies"})
    drive(worker)
    assert db.one(select(p.assets))["availability"] == "AVAILABLE"
    assert not qbt.commands


def test_SCAN_does_not_contact_qbt_and_preserves_existing_dependencies(
    stack: Any,
) -> None:
    worker, qbt, _, _ = stack
    db = worker.db
    previous = asset(db, data={"dependencies": ["existing-torrent-ref"]})
    path = db.config.nas_root / "Library" / previous["relative_path"]
    with db.transaction() as conn:
        conn.execute(
            update(p.assets)
            .where(p.assets.c.id == previous["id"])
            .values(mtime_ns=path.stat().st_mtime_ns, observed_size=path.stat().st_size)
        )

    def forbidden_qbt() -> Any:
        raise AssertionError("Library scan must not query qBittorrent")

    qbt.all = forbidden_qbt
    client = login(db)
    scan = post(client, "/library/scans", {"category": "movies"}).json()
    drive(worker)
    assert client.get("/api/v1/library/scans/" + scan["id"]).json()["state"] == "COMPLETED"
    current = db.one(select(p.assets).where(p.assets.c.id == previous["id"]))
    assert current["data"]["dependencies"] == ["existing-torrent-ref"]


def test_SCAN_legacy_catalogue_bootstrap_reuses_historical_probe(
    stack: Any, monkeypatch: Any
) -> None:
    from app import inventory

    worker, _, _, _ = stack
    db = worker.db
    original = asset(db)
    source = db.config.nas_root / "Library" / original["relative_path"]
    calls = []
    worker.probe = lambda path: calls.append(path) or synthetic_probe(path)

    def must_not_hash(_path: Path) -> str:
        raise AssertionError("legacy same-size catalogue file must not be rehashed")

    monkeypatch.setattr(inventory, "sha256", must_not_hash)
    client = login(db)
    result = post(client, "/library/scans", {"category": "movies"}).json()
    drive(worker)
    assert client.get("/api/v1/library/scans/" + result["id"]).json()["state"] == "COMPLETED"
    updated = db.one(select(p.assets).where(p.assets.c.id == original["id"]))
    assert not calls
    assert updated["fingerprint"] == original["fingerprint"]
    assert updated["observed_size"] == source.stat().st_size
    assert updated["mtime_ns"] == source.stat().st_mtime_ns
    assert updated["data"]["fingerprint_verification"] == "historical_unverified"
    assert updated["revision"] == original["revision"]


def test_SCAN_overlap_guard_and_policy_zero_fs_changes(stack: Any) -> None:
    db = stack[0].db
    client = login(db)
    assert post(client, "/library/scans", {"category": "movies"}).status_code == 202
    assert post(client, "/library/scans", {"all": True}).status_code == 409
    policy = library_policy.defaults()
    result = post(
        client, "/library/policies", {"expected_revision": 0, "policy": policy}
    )
    assert result.status_code == 201 and not list(db.config.nas_root.rglob("*.mkv"))
    assert not db.rows(select(p.operations)) and not stack[1].commands
    assert (
        post(
            client, "/library/policies", {"expected_revision": 0, "policy": policy}
        ).status_code
        == 409
    )
    policy["categories"]["movies"]["routes"]["movie"]["folders"][0] = "../escape"
    assert (
        post(
            client, "/library/policies", {"expected_revision": 1, "policy": policy}
        ).status_code
        == 409
    )


def test_HIER_collection_editions_unicode_and_optional_no_unknown() -> None:
    policy = library_policy.defaults()
    identity = {
        "title": "Пример: Movie",
        "year": 2026,
        "media_type": "movie",
        "confirmed": True,
        "edition": "Extended",
        "collection_name": "Collection",
    }
    output = library_policy.render(
        policy,
        "movies",
        identity,
        {"quality_label": "1080p", "bg": "BG_TAGGED"},
        "old.mkv",
    )
    assert (
        output["path"].startswith("Movies/Collection/")
        and "BG" in output["path"]
        and "Extended" in output["path"]
    )
    identity.pop("collection_name")
    assert (
        "Unknown Collection"
        not in library_policy.render(
            policy, "movies", identity, {"quality_label": "1080p"}, "old.mkv"
        )["path"]
    )
    identity["collection_override"] = "Manual"
    assert (
        "/Manual/"
        in library_policy.render(
            policy, "movies", identity, {"quality_label": "1080p"}, "old.mkv"
        )["path"]
    )


def test_DELETE_bulk_exact_owned_sidecars_tombstone_and_legacy_guard(
    stack: Any,
) -> None:
    worker, qbt, jellyfin, _ = stack
    db = worker.db
    safe = asset(db)
    blocked = asset(db, "Movies/Blocked/Legacy.mkv")
    source = db.config.nas_root / "Library" / safe["relative_path"]
    source.with_suffix(".bg.srt").write_text("exclusive synthetic subtitles")
    shared = source.parent / "poster.jpg"
    shared.write_bytes(b"shared-unknown")
    sibling = source.parent / "Neighbour.mkv"
    sibling.write_bytes(b"sibling")
    t = torrent(db, files=[blocked["relative_path"]], save_path="/library")
    qbt.torrents[t.info_hash] = t
    client = login(db)
    result = plan(stack, client, "deletions", [safe["id"], blocked["id"]])
    assert result["counts"] == {"Planned": 1, "NeedsReview": 1}
    assert source.exists()
    assert approve(client, "deletions", result).status_code == 202
    drive(worker)
    assert not source.exists() and not source.with_suffix(".bg.srt").exists()
    assert sibling.is_file() and shared.is_file()
    assert (
        db.one(select(p.assets).where(p.assets.c.id == safe["id"]))["workflow_state"]
        == "DELETED"
    )
    assert db.one(select(p.tombstones))["asset_id"] == safe["id"]
    assert not qbt.commands and jellyfin.refresh_count > 0
    assert client.get("/api/v1/library/assets").json()["total"] == 1


def test_DELETE_plan_stale_and_write_gate(stack: Any) -> None:
    worker, *_ = stack
    db = worker.db
    a = asset(db)
    client = login(db)
    result = plan(stack, client, "deletions", [a["id"]])
    with db.transaction() as conn:
        conn.execute(
            update(p.assets).where(p.assets.c.id == a["id"]).values(revision=2)
        )
    assert approve(client, "deletions", result).status_code == 409
    result = plan(stack, client, "deletions", [a["id"]])
    assert approve(client, "deletions", result).status_code == 202
    worker.cfg.write_enabled = False
    drive(worker)
    assert (db.config.nas_root / "Library" / a["relative_path"]).is_file()
    assert not db.rows(select(p.tombstones))


def test_QUAR_bulk_reversible_collision_and_sibling_preserved(stack: Any) -> None:
    worker, *_ = stack
    db = worker.db
    a = asset(db)
    client = login(db)
    path = db.config.nas_root / "Library" / a["relative_path"]
    path.with_suffix(".bg.srt").write_bytes(b"associated-sub")
    result = plan(stack, client, "quarantines", [a["id"]])
    assert approve(client, "quarantines", result).status_code == 202
    drive(worker)
    assert not path.exists()
    manifest = db.one(select(p.quarantine))
    assert db.one(select(p.assets))["workflow_state"] == "QUARANTINED"
    post(client, f"/library/quarantine/{manifest['id']}/restore")
    drive(worker)
    assert (
        path.is_file() and path.with_suffix(".bg.srt").read_bytes() == b"associated-sub"
    )
    assert db.one(select(p.assets))["workflow_state"] == "ACTIVE"


def test_BULK_normalization_one_approval_phases_pending_retry_no_move_repeat(
    stack: Any,
) -> None:
    worker, _, jellyfin, _ = stack
    db = worker.db
    a = asset(db)
    client = login(db)
    result = plan(stack, client, "normalizations", [a["id"]])
    assert result["counts"] == {"Planned": 1}
    jellyfin.recognize = False
    assert approve(client, "normalizations", result).status_code == 202
    drive(worker, 3)
    current = client.get(f"/api/v1/library/normalizations/{result['id']}").json()
    assert current["state"] == "PublishPending"
    moves = db.rows(select(p.operations).where(p.operations.c.kind == "NORMALIZE"))
    assert len(moves) == 1
    jellyfin.recognize = True
    drive(worker)
    current = client.get(f"/api/v1/library/normalizations/{result['id']}").json()
    assert current["state"] == "CompletedWithWarnings"
    assert (
        len(db.rows(select(p.operations).where(p.operations.c.kind == "NORMALIZE")))
        == 1
    )


def test_BULK_pause_cancel_and_individual_ambiguity_continue(stack: Any) -> None:
    worker, *_ = stack
    db = worker.db
    a = asset(db)
    b = asset(db, "Movies/Other/Ambiguous.mkv", data={"identity": {}})
    client = login(db)
    result = plan(stack, client, "normalizations", [a["id"], b["id"]])
    assert result["counts"] == {"Planned": 1, "NeedsReview": 1}
    assert approve(client, "normalizations", result).status_code == 202
    post(client, f"/library/normalizations/{result['id']}/pause")
    drive(worker)
    assert (db.config.nas_root / "Library" / a["relative_path"]).exists()
    post(client, f"/library/normalizations/{result['id']}/cancel")
    drive(worker)
    assert (db.config.nas_root / "Library" / a["relative_path"]).exists()
    assert not db.rows(select(p.tombstones))


def test_DELETE_fs_failure_keeps_catalogue_partial_reconcile(
    stack: Any, monkeypatch: Any
) -> None:
    worker, *_ = stack
    db = worker.db
    a = asset(db)
    client = login(db)
    result = plan(stack, client, "deletions", [a["id"]])
    assert approve(client, "deletions", result).status_code == 202
    original = Path.unlink
    monkeypatch.setattr(
        Path, "unlink", lambda self, *a, **kw: (_ for _ in ()).throw(PermissionError())
    )
    drive(worker)
    assert db.one(select(p.assets))["workflow_state"] == "ACTIVE" and not db.rows(
        select(p.tombstones)
    )
    monkeypatch.setattr(Path, "unlink", original)
    post(client, f"/library/deletions/{result['id']}/retry")
    drive(worker)
    assert db.one(select(p.assets))["workflow_state"] == "DELETED"


def test_QUAR_bulk_restore_collision_continues_and_retry_reconciles(stack: Any) -> None:
    worker, *_ = stack
    db = worker.db
    client = login(db)
    a = asset(db)
    b = asset(db, "Movies/Other/Second.mkv")
    result = plan(stack, client, "quarantines", [a["id"], b["id"]])
    assert approve(client, "quarantines", result).status_code == 202
    drive(worker)
    manifests = db.rows(select(p.quarantine))
    original = db.config.nas_root / "Library" / a["relative_path"]
    original.write_bytes(b"synthetic-external-collision")
    response = post(
        client,
        "/library/quarantines/restores",
        {"manifest_ids": [m["id"] for m in manifests], "confirmed": True},
    )
    assert response.status_code == 202
    drive(worker)
    jid = response.json()["job_id"]
    assert db.one(select(p.jobs).where(p.jobs.c.id == jid))["state"] == "NeedsReview"
    assert original.read_bytes() == b"synthetic-external-collision"
    assert (db.config.nas_root / "Library" / b["relative_path"]).is_file()
    original.unlink()
    assert post(client, f"/library/quarantine/restores/{jid}/retry").status_code == 202
    drive(worker)
    assert all(m["state"] == "RESTORED" for m in db.rows(select(p.quarantine)))
    assert original.is_file() and not stack[1].commands


def test_DELETE_crash_after_unlink_before_verification_reconciles_once(
    stack: Any, monkeypatch: Any
) -> None:
    from datetime import timedelta

    worker, *_ = stack
    db = worker.db
    client = login(db)
    a = asset(db)
    result = plan(stack, client, "deletions", [a["id"]])
    assert approve(client, "deletions", result).status_code == 202
    original = Path.unlink
    calls = []

    def interrupted(path: Path, *args: Any, **kwargs: Any) -> None:
        original(path, *args, **kwargs)
        calls.append(path)
        raise RuntimeError("Synthetic crash after exact unlink")

    monkeypatch.setattr(Path, "unlink", interrupted)
    with pytest.raises(RuntimeError):
        worker.run_once()
    monkeypatch.setattr(Path, "unlink", original)
    with db.transaction() as conn:
        conn.execute(
            update(p.tasks)
            .where(p.tasks.c.state == "RUNNING")
            .values(lease_until=p.now() - timedelta(seconds=1))
        )
        conn.execute(update(p.leases).values(until=p.now() - timedelta(seconds=1)))
    drive(worker)
    assert len(calls) == 1 and len(db.rows(select(p.tombstones))) == 1
    assert db.one(select(p.assets))["workflow_state"] == "DELETED"


def test_V11_new_api_auth_csrf_and_separate_explicit_delete_intent(stack: Any) -> None:
    from fastapi.testclient import TestClient
    from app.api import create_app

    worker, *_ = stack
    db = worker.db
    a = asset(db)
    anonymous = TestClient(create_app(db.config, db), base_url="https://testserver")
    assert anonymous.get("/api/v1/library/analytics").status_code == 401
    assert (
        anonymous.post(
            "/api/v1/library/deletions/plans", json={"asset_ids": [a["id"]]}
        ).status_code
        == 401
    )
    client = login(db)
    csrf = client.headers.pop("X-CSRF-Token")
    assert (
        post(client, "/library/deletions/plans", {"asset_ids": [a["id"]]}).status_code
        == 403
    )
    assert not db.rows(select(p.jobs))
    client.headers["X-CSRF-Token"] = csrf
    result = plan(stack, client, "deletions", [a["id"]])
    response = post(
        client,
        f"/jobs/{result['id']}/approve",
        {
            "plan_revision": 1,
            "plan_sha256": result["plan"]["sha256"],
            "reason": "Unrelated import approval cannot authorize delete",
        },
    )
    assert response.status_code == 409
    assert not db.rows(select(p.approvals))


def test_BG_contradictory_signal_is_unknown(db: p.Database) -> None:
    from app.domain import bg_state

    analysis = {
        "streams": [
            {
                "codec_type": "audio",
                "tags": {"language": "bul", "title": "English commentary"},
            }
        ]
    }
    assert bg_state(analysis, "a" * 64, []) == "AUDIO_UNKNOWN"


def test_NORMALIZE_crash_after_link_resumes_owned_alias_without_duplicate_move(
    stack: Any, monkeypatch: Any
) -> None:
    import os
    from datetime import timedelta

    worker, *_ = stack
    db = worker.db
    a = asset(db)
    client = login(db)
    result = plan(stack, client, "normalizations", [a["id"]])
    assert approve(client, "normalizations", result).status_code == 202
    original = os.link
    calls = []

    def interrupted(source: Any, target: Any, *args: Any, **kwargs: Any) -> None:
        original(source, target, *args, **kwargs)
        calls.append(str(target))
        raise RuntimeError("Synthetic crash after link before source unlink")

    monkeypatch.setattr(os, "link", interrupted)
    with pytest.raises(RuntimeError):
        worker.run_once()
    monkeypatch.setattr(os, "link", original)
    with db.transaction() as conn:
        conn.execute(
            update(p.tasks)
            .where(p.tasks.c.state == "RUNNING")
            .values(lease_until=p.now() - timedelta(seconds=1))
        )
        conn.execute(update(p.leases).values(until=p.now() - timedelta(seconds=1)))
    drive(worker)
    assert len(calls) == 1
    assert db.one(select(p.maintenance_files))["state"] == "CompletedWithWarnings"
    assert not (db.config.nas_root / "Library" / a["relative_path"]).exists()


def test_META_known_id_string_year_collection_cache_and_owned_nfo_policy_move(
    stack: Any,
) -> None:
    worker, *_ = stack
    db = worker.db
    calls = []

    class Metadata:
        def details(self, provider_id: str, media_type: str) -> dict[str, Any]:
            calls.append(provider_id)
            return {
                "title": "Fixture",
                "year": 2026,
                "imdb_id": "tt-synthetic",
                "collection_id": "synthetic-collection",
                "collection_name": "Synthetic Collection",
            }

    worker.tmdb = Metadata()
    a = asset(
        db,
        data={
            "identity": {
                "title": "Fixture",
                "year": "2026",
                "media_type": "movie",
                "provider_id": "1",
                "confirmed": False,
                "edition": "Theatrical",
            }
        },
    )
    client = login(db)
    result = plan(stack, client, "normalizations", [a["id"]])
    assert result["counts"] == {"Planned": 1}
    assert "/Synthetic Collection/" in result["files"][0]["data"]["target"]
    assert approve(client, "normalizations", result).status_code == 202
    drive(worker)
    policy = library_policy.defaults()
    policy["categories"]["movies"]["root"] = "Films"
    assert (
        post(
            client, "/library/policies", {"expected_revision": 0, "policy": policy}
        ).status_code
        == 201
    )
    result = plan(stack, client, "normalizations", [a["id"]])
    assert result["counts"] == {"Planned": 1}
    assert approve(client, "normalizations", result).status_code == 202
    drive(worker)
    assert calls == ["1"]
    updated = db.one(select(p.assets))
    assert (
        updated["relative_path"].startswith("Films/")
        and updated["category"] == "movies"
    )
    assert (
        (db.config.nas_root / "Library" / updated["relative_path"])
        .parent.joinpath("movie.nfo")
        .is_file()
    )
    post(client, "/library/scans", {"category": "movies"})
    drive(worker)
    assert db.one(select(p.assets))["availability"] == "AVAILABLE"
