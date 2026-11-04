"""Library maintenance is independent of legacy torrent lifecycle state."""

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update

from app import persistence as p
from app.api import create_app
from app.domain import GateError
from conftest import drive, login, torrent
from test_english_naming import EnglishMetadata, identified
from test_library_v11 import approve, asset, plan, post


def no_torrents() -> Any:
    raise AssertionError("Library maintenance queried qBittorrent")


def test_torrent_poll_failure_does_not_starve_library_worker(stack: Any) -> None:
    worker, *_ = stack
    calls = []

    def unavailable() -> None:
        raise GateError("QBT_UNAVAILABLE", "BlockedExternalDependency")

    def independent_task() -> bool:
        calls.append("library-task")
        worker.running = False
        return True

    worker.poll = unavailable
    worker.run_once = independent_task
    worker.run()
    assert calls == ["library-task"]


def test_legacy_missing_files_references_do_not_block_plan_or_execution(
    stack: Any,
) -> None:
    worker, qbt, *_ = stack
    db = worker.db
    a = asset(db, data={"dependencies": [{"state": "missingFiles", "legacy": True}]})
    with db.transaction() as conn:
        conn.execute(
            insert(p.refs).values(
                asset_id=a["id"],
                root="library",
                relative_path=a["relative_path"],
                data={"state": "missingFiles"},
            )
        )
    t = torrent(
        db, state="missingFiles", files=[a["relative_path"]], save_path="/library"
    )
    qbt.torrents[t.info_hash] = t
    qbt.all = no_torrents
    client = login(db)
    result = plan(stack, client, "normalizations", [a["id"]])
    assert result["counts"] == {"Planned": 1}
    assert result["files"][0]["review_state"] == "Ready"
    assert approve(client, "normalizations", result).status_code == 202
    drive(worker)
    current = client.get(f"/api/v1/library/normalizations/{result['id']}").json()
    assert current["state"] == "CompletedWithWarnings"
    assert not qbt.commands
    assert (
        db.one(select(p.assets).where(p.assets.c.id == a["id"]))["data"]["dependencies"]
        == a["data"]["dependencies"]
    )


def test_scan_enriches_all_categories_and_keeps_unidentified_in_review(
    stack: Any,
) -> None:
    worker, qbt, *_ = stack
    worker.tmdb = EnglishMetadata()
    worker.tmdb.search = lambda title, media_type, year: []
    qbt.all = no_torrents
    db = worker.db
    known = identified(db, year=None)
    unresolved = asset(db, "Animations/Unknown.mkv", data={"identity": {}})
    for folder in ("Series", "Documentaries", "Concerts"):
        asset(db, f"{folder}/Unidentified.mkv", data={"identity": {}})
    client = login(db)
    scan = post(client, "/library/scans", {"all": True}).json()
    drive(worker)
    summary = client.get("/api/v1/library/scans/" + scan["id"]).json()
    assert summary["state"] == "COMPLETED"
    assert summary["data"]["processed"] == 5
    updated = db.one(select(p.assets).where(p.assets.c.id == known["id"]))
    assert updated["data"]["identity"]["title"] == "Parasite"
    assert updated["data"]["identity"]["year"] == 2026
    assert updated["data"]["identity"]["original_title"] == "기생충"
    assert updated["data"]["identity"]["imdb_id"] == "tt-synthetic"
    assert updated["data"]["bg"] == "BG_VERIFIED"
    queue = client.get("/api/v1/library/review?limit=2").json()
    assert queue["total"] == 4 and len(queue["items"]) == 2
    item = db.one(select(p.assets).where(p.assets.c.id == unresolved["id"]))
    assert item["data"]["inspection"]["state"] == "Unidentified"
    assert item["relative_path"] == unresolved["relative_path"]


def test_manual_tmdb_search_correction_reanalysis_and_persistence(stack: Any) -> None:
    worker, qbt, *_ = stack
    worker.tmdb = provider = EnglishMetadata()
    provider.search = lambda title, media_type, year: [
        {"id": "1", "title": "Parasite", "year": 2026, "media_type": "movie"}
    ]
    qbt.all = no_torrents
    db = worker.db
    a = asset(db, "Movies/Mystery.mkv", data={"identity": {}})
    client = login(db)
    search = post(
        client,
        f"/library/assets/{a['id']}/identity-search",
        {"title": "Parasite", "media_type": "movie"},
    )
    assert search.status_code == 202
    drive(worker)
    assert (
        client.get(
            "/api/v1/library/inspections/" + search.json()["operation_id"]
        ).json()["state"]
        == "DONE"
    )
    assert (
        client.get(f"/api/v1/library/assets/{a['id']}/identity-candidates").json()[
            "items"
        ][0]["id"]
        == "1"
    )
    saved = post(
        client,
        f"/library/assets/{a['id']}/identity",
        {
            "expected_revision": a["revision"],
            "category": "documentaries",
            "identity": {
                "title": "Parasite",
                "year": 2026,
                "media_type": "movie",
                "provider_id": "1",
                "edition": "Director's Cut",
                "collection_override": "Manual Collection",
                "collection_override_language": "en-US",
                "separate_edition": True,
            },
        },
    )
    assert saved.status_code == 200
    reanalysis = post(client, f"/library/assets/{a['id']}/reanalyze")
    assert reanalysis.status_code == 202
    drive(worker)
    changed = client.get(f"/api/v1/library/assets/{a['id']}").json()
    assert changed["category"] == "documentaries"
    assert changed["data"]["inspection"]["state"] == "Identified"
    assert changed["relative_path"] == a["relative_path"]
    identity = changed["data"]["identity"]
    assert (
        identity["collection_override"] == "Manual Collection"
        and identity["separate_edition"]
    )
    neighbour = asset(db, "Movies/Neighbour.mkv")
    for folder in ("Series", "Animations", "Documentaries", "Concerts"):
        (worker.cfg.nas_root / "Library" / folder).mkdir(exist_ok=True)
    scan = post(client, "/library/scans", {"all": True}).json()
    drive(worker)
    assert (
        client.get("/api/v1/library/scans/" + scan["id"]).json()["state"] == "COMPLETED"
    )
    assert (
        client.get(f"/api/v1/library/assets/{a['id']}").json()["data"]["identity"]
        == identity
    )
    result = plan(stack, client, "normalizations", [a["id"]])
    assert (
        "Documentaries/Movies/Manual Collection/Parasite (2026)"
        in result["files"][0]["data"]["target"]
    )
    assert (
        client.get(f"/api/v1/library/assets/{a['id']}").json()["category"]
        == "documentaries"
    )
    assert (
        client.get(f"/api/v1/library/assets/{neighbour['id']}").json()["category"]
        == "movies"
    )


def test_strict_unique_title_year_identification_and_english_preview(
    stack: Any,
) -> None:
    worker, qbt, *_ = stack
    provider = EnglishMetadata()
    provider.search = lambda title, media_type, year: [
        {"id": "1", "title": "Parasite", "year": 2026, "media_type": "movie"}
    ]
    worker.tmdb = provider
    qbt.all = no_torrents
    a = asset(worker.db, "Movies/Parasite 2026.mkv", data={"identity": {}})
    client = login(worker.db)
    post(client, f"/library/assets/{a['id']}/reanalyze")
    drive(worker)
    current = client.get(f"/api/v1/library/assets/{a['id']}").json()
    assert current["data"]["identity"]["confirmed"]
    result = plan(stack, client, "normalizations", [a["id"]])
    assert "Parasite (2026)" in result["files"][0]["data"]["target"]
    assert "기생충" not in result["files"][0]["data"]["target"]


@pytest.mark.parametrize(
    "hazard", ["fingerprint", "collision", "hardlink", "sidecar", "directory"]
)
def test_filesystem_hazards_require_review_despite_legacy_decoupling(
    stack: Any, hazard: str
) -> None:
    worker, qbt, *_ = stack
    qbt.all = no_torrents
    db = worker.db
    a = asset(db)
    source = worker.cfg.nas_root / "Library" / a["relative_path"]
    client = login(db)
    if hazard == "fingerprint":
        source.write_bytes(b"changed")
    elif hazard == "hardlink":
        os.link(source, source.with_suffix(".alias"))
    elif hazard == "sidecar":
        (source.parent / "movie.nfo").write_text("unknown-owned-sidecar")
    else:
        initial = plan(stack, client, "normalizations", [a["id"]])
        target = worker.cfg.nas_root / initial["files"][0]["data"]["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if hazard == "directory":
            (target.parent / "Uncatalogued.mkv").write_bytes(b"unknown-work")
        else:
            target.write_bytes(b"unrelated-media")
    result = plan(stack, client, "normalizations", [a["id"]])
    assert result["counts"] == {"NeedsReview": 1}
    assert result["files"][0]["data"]["error_code"] != "DEPENDENCY_BLOCKED"
    assert source.exists() and not qbt.commands


def test_correction_invalidates_approval_and_reanalysis_requires_auth(
    stack: Any,
) -> None:
    worker, qbt, *_ = stack
    qbt.all = no_torrents
    a = asset(worker.db)
    client = login(worker.db)
    anonymous = TestClient(
        create_app(worker.cfg, worker.db), base_url="https://testserver"
    )
    assert (
        anonymous.post(f"/api/v1/library/assets/{a['id']}/reanalyze").status_code == 401
    )
    result = plan(stack, client, "normalizations", [a["id"]])
    with worker.db.transaction() as conn:
        conn.execute(
            update(p.assets).where(p.assets.c.id == a["id"]).values(revision=2)
        )
    assert approve(client, "normalizations", result).status_code == 409
    drive(worker)
    assert not worker.db.rows(select(p.operations))


def test_unapproved_and_write_disabled_normalizations_cannot_mutate(stack: Any) -> None:
    worker, qbt, *_ = stack
    qbt.all = no_torrents
    a = asset(worker.db)
    client = login(worker.db)
    result = plan(stack, client, "normalizations", [a["id"]])
    with worker.db.transaction() as conn:
        conn.execute(insert(p.tasks).values(job_id=result["id"], kind="BULK_EXECUTE"))
    drive(worker)
    assert not worker.db.rows(select(p.operations))
    result = plan(stack, client, "normalizations", [a["id"]])
    assert approve(client, "normalizations", result).status_code == 202
    worker.cfg.write_enabled = False
    drive(worker)
    assert not worker.db.rows(select(p.operations))
    assert (worker.cfg.nas_root / "Library" / a["relative_path"]).exists()


def test_known_tmdb_id_lookup_is_language_scoped_and_read_only(stack: Any) -> None:
    worker, qbt, *_ = stack
    worker.tmdb = provider = EnglishMetadata()
    qbt.all = no_torrents
    a = asset(worker.db, data={"identity": {}})
    client = login(worker.db)
    response = post(
        client,
        f"/library/assets/{a['id']}/identity-lookup",
        {"provider_id": "1", "media_type": "movie"},
    )
    assert response.status_code == 202
    drive(worker)
    candidate = client.get(
        f"/api/v1/library/assets/{a['id']}/identity-candidates"
    ).json()["items"][0]
    assert candidate["title"] == "Parasite" and candidate["title_language"] == "en-US"
    assert candidate["original_title"] == "기생충" and candidate["id"] == "1"
    assert provider.calls == ["1"]
    assert worker.db.one(select(p.assets).where(p.assets.c.id == a["id"])) == a
    assert not worker.db.rows(select(p.operations))
    assert (
        post(
            client,
            f"/library/assets/{a['id']}/identity-lookup",
            {"provider_id": "../1", "media_type": "movie"},
        ).status_code
        == 422
    )


def test_preview_review_filters_and_already_normalized_are_server_side(
    stack: Any,
) -> None:
    worker, qbt, *_ = stack
    qbt.all = no_torrents
    db = worker.db
    ready = asset(db)
    unresolved = asset(db, "Movies/Mystery.mkv", data={"identity": {}})
    client = login(db)
    result = plan(stack, client, "normalizations", [ready["id"], unresolved["id"]])
    base = f"/api/v1/library/normalizations/{result['id']}"
    assert (
        client.get(base + "?review_state=Ready&limit=1").json()["files"][0]["asset_id"]
        == ready["id"]
    )
    assert (
        client.get(base + "?review_state=Unidentified").json()["files"][0]["asset_id"]
        == unresolved["id"]
    )
    assert not client.get(base + "?review_state=Conflict").json()["files"]
    assert client.get(base + "?review_state=invalid").status_code == 422
    assert approve(client, "normalizations", result).status_code == 202
    drive(worker)
    fresh = plan(stack, client, "normalizations", [ready["id"]])
    assert fresh["files"][0]["review_state"] == "AlreadyNormalized"
    assert (
        client.get(
            f"/api/v1/library/normalizations/{fresh['id']}?review_state=AlreadyNormalized"
        ).json()["files"][0]["asset_id"]
        == ready["id"]
    )


def test_new_duplicate_inspection_relationships_are_bidirectional(stack: Any) -> None:
    worker, qbt, *_ = stack
    qbt.all = no_torrents
    root = worker.cfg.nas_root / "Library" / "Movies"
    root.mkdir()
    for name in ("First.mkv", "Second.mkv"):
        (root / name).write_bytes(b"identical-synthetic-video")
    client = login(worker.db)
    scan = post(client, "/library/scans", {"category": "movies"}).json()
    drive(worker)
    assert (
        client.get("/api/v1/library/scans/" + scan["id"]).json()["state"] == "COMPLETED"
    )
    rows = worker.db.rows(select(p.assets))
    assert len(rows) == 2
    for row in rows:
        versions = row["data"]["inspection"]["versions"]
        assert len(versions) == 1 and versions[0]["asset_id"] != row["id"]
        assert versions[0]["reason"] == "identical-bytes"
    assert not worker.db.rows(select(p.operations))


def test_compatible_single_normalization_ignores_legacy_references(stack: Any) -> None:
    worker, qbt, *_ = stack
    qbt.all = no_torrents
    a = asset(worker.db, data={"dependencies": [{"state": "missingFiles"}]})
    client = login(worker.db)
    result = post(
        client,
        f"/library/assets/{a['id']}/normalization-plan",
        {
            "identity": a["data"]["identity"],
            "quality_label": "Full HD",
            "reason": "Synthetic exact review",
        },
    )
    assert result.status_code == 202
    plan = result.json()
    assert (
        post(
            client,
            f"/library/normalization-plans/{plan['id']}/approve",
            {
                "plan_revision": plan["revision"],
                "plan_sha256": plan["sha256"],
                "reason": "Synthetic explicit approval",
            },
        ).status_code
        == 202
    )
    drive(worker)
    assert (worker.cfg.nas_root / plan["data"]["target"]).is_file()
    assert not (worker.cfg.nas_root / plan["data"]["source"]).exists()
    assert not qbt.commands
