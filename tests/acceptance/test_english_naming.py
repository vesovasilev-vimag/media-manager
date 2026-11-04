"""English proposals preserve catalogue/media until an authorized exact plan executes."""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import insert, select

from app import bulk, library_policy
from app import persistence as p
from app.domain import GateError
from app.storage import sha256
from conftest import drive, login
from test_library_v11 import approve, asset, plan, post


class EnglishMetadata:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.title = "Parasite"
        self.collection_name: str | None = "English Collection"

    def details(self, provider_id: str, media_type: str) -> dict[str, Any]:
        self.calls.append(provider_id)
        return {
            "provider_id": provider_id,
            "title": self.title,
            "original_title": "기생충",
            "title_language": "en-US",
            "english_title_verified": True,
            "year": 2026,
            "collection_id": "2",
            "collection_name": self.collection_name,
            "collection_language": "en-US" if self.collection_name else None,
            "imdb_id": "tt-synthetic",
        }

    def episode(self, provider_id: str, season: int, episode: int) -> dict[str, Any]:
        self.calls.append(f"{provider_id}:{season}:{episode}")
        return {"episode_title": "The Beginning", "episode_title_language": "en-US"}


def identified(db: p.Database, **identity: Any) -> dict[str, Any]:
    return asset(
        db,
        data={
            "identity": {
                "title": "기생충",
                "provider_id": "1",
                "year": 2026,
                "media_type": "movie",
                "confirmed": True,
                "edition": "Director's Cut",
                "custom_preserved": "evidence",
                **identity,
            },
            "bg": "BG_VERIFIED",
        },
    )


def test_confirmed_tmdb_id_gets_english_plan_without_catalogue_or_media_mutation(
    stack: Any,
) -> None:
    worker, qbt, *_ = stack
    worker.tmdb = provider = EnglishMetadata()
    a = identified(worker.db)
    path = worker.cfg.nas_root / "Library" / a["relative_path"]
    before = sha256(path)
    client = login(worker.db)
    worker.cfg.write_enabled = False
    result = plan(stack, client, "normalizations", [a["id"]])
    assert result["counts"] == {"Planned": 1}
    proposed = result["files"][0]["data"]
    assert "/English Collection/Parasite (2026)/Parasite (2026)" in proposed["target"]
    assert proposed["identity"]["provider_id"] == "1"
    assert proposed["identity"]["edition"] == "Director's Cut"
    assert proposed["identity"]["custom_preserved"] == "evidence"
    assert "BG" in proposed["target"]
    assert proposed["identity"]["original_title"] == "기생충"
    assert worker.db.one(select(p.assets).where(p.assets.c.id == a["id"])) == a
    assert sha256(path) == before and not qbt.commands
    assert approve(client, "normalizations", result).status_code == 202
    drive(worker)
    assert path.is_file() and sha256(path) == before
    assert not worker.db.rows(select(p.operations))
    assert provider.calls == ["1"]


@pytest.mark.parametrize("manual", ["marker", "historical-audit"])
def test_explicit_manual_title_override_requires_review(
    stack: Any, manual: str
) -> None:
    worker, *_ = stack
    worker.tmdb = EnglishMetadata()
    a = identified(
        worker.db,
        **({"title_provenance": "manual-override"} if manual == "marker" else {}),
    )
    if manual == "historical-audit":
        with worker.db.transaction() as conn:
            worker.db.event(
                conn, "synthetic-admin", "LIBRARY_IDENTITY_CONFIRMED", a["id"]
            )
    with pytest.raises(GateError, match="MANUAL_TITLE_OVERRIDE_REVIEW"):
        bulk.identity(worker, a)
    assert (
        worker.db.one(select(p.assets).where(p.assets.c.id == a["id"]))["data"][
            "identity"
        ]["title"]
        == "기생충"
    )


@pytest.mark.parametrize(
    "key,language", [("tmdb:movie:1", "bg-BG"), ("tmdb:en-US:movie:1", "bg-BG")]
)
def test_wrong_language_and_legacy_caches_are_never_reused_as_english(
    stack: Any, key: str, language: str
) -> None:
    worker, *_ = stack
    worker.tmdb = provider = EnglishMetadata()
    a = identified(worker.db)
    with worker.db.transaction() as conn:
        conn.execute(
            insert(p.settings_table).values(
                key=key,
                value={
                    "title": "기생충",
                    "cached_at": p.now().isoformat(),
                    "cache_language": language,
                },
            )
        )
    assert bulk.identity(worker, a)["title"] == "Parasite"
    assert bulk.identity(worker, a)["title"] == "Parasite"
    assert provider.calls == ["1"]


def test_expired_english_cache_refresh_failure_does_not_reuse_stale_title(
    stack: Any,
) -> None:
    worker, *_ = stack

    class Offline(EnglishMetadata):
        def details(self, provider_id: str, media_type: str) -> dict[str, Any]:
            raise GateError("TMDB_UNAVAILABLE", "BlockedExternalDependency")

    worker.tmdb = Offline()
    a = identified(worker.db)
    with worker.db.transaction() as conn:
        conn.execute(
            insert(p.settings_table).values(
                key="tmdb:en-US:movie:1",
                value={
                    "title": "Stale Title",
                    "title_language": "en-US",
                    "english_title_verified": True,
                    "cache_language": "en-US",
                    "cached_at": (p.now() - timedelta(days=2)).isoformat(),
                },
            )
        )
    with pytest.raises(GateError, match="TMDB_UNAVAILABLE"):
        bulk.identity(worker, a)


def test_missing_authoritative_english_title_becomes_needs_review(stack: Any) -> None:
    worker, *_ = stack

    class Missing(EnglishMetadata):
        def details(self, provider_id: str, media_type: str) -> dict[str, Any]:
            raise GateError("ENGLISH_TITLE_UNAVAILABLE")

    worker.tmdb = Missing()
    a = identified(worker.db)
    result = plan(stack, login(worker.db), "normalizations", [a["id"]])
    assert result["counts"] == {"NeedsReview": 1}
    assert result["files"][0]["data"]["error_code"] == "ENGLISH_TITLE_UNAVAILABLE"
    assert not worker.db.rows(select(p.operations))


def test_english_series_and_episode_template_and_language_scoped_cache(
    stack: Any,
) -> None:
    worker, *_ = stack
    worker.tmdb = provider = EnglishMetadata()
    provider.title = "Attack on Titan"
    a = identified(
        worker.db, media_type="show", season=1, episodes=[1], episode_title="始まり"
    )
    # Synthetic category changed only in the in-memory evaluator fixture.
    a = {**a, "category": "series"}
    policy = library_policy.defaults()
    policy["categories"]["series"]["routes"]["show"]["filename"] += [
        " - ",
        "{EpisodeTitle}",
    ]
    identity = bulk.identity(worker, a, policy)
    rendered = library_policy.render(
        policy,
        "series",
        identity,
        {"quality_label": "1080p", "bg": "BG_TAGGED"},
        "source.mkv",
    )
    assert rendered["path"].startswith(
        "Series/Attack on Titan (2026)/Season 01/Attack on Titan S01E01"
    )
    assert "The Beginning" in rendered["path"] and "BG" in rendered["path"]
    assert identity["original_episode_title"] == "始まり"
    assert bulk.identity(worker, a, policy)["episode_title"] == "The Beginning"
    assert provider.calls == ["1", "1:1:1"]


def test_untranslated_collection_blocks_only_when_used_by_policy(stack: Any) -> None:
    worker, *_ = stack
    worker.tmdb = provider = EnglishMetadata()
    provider.collection_name = None
    a = identified(worker.db)
    with pytest.raises(GateError, match="ENGLISH_COLLECTION_UNAVAILABLE"):
        bulk.identity(worker, a)
    policy = library_policy.defaults()
    policy["collections"] = False
    assert bulk.identity(worker, a, policy)["title"] == "Parasite"


def test_manual_identity_metadata_edit_preserves_unrelated_fields_and_records_language(
    stack: Any,
) -> None:
    worker, *_ = stack
    a = identified(worker.db)
    original = a["data"]["identity"]
    client = login(worker.db)
    response = post(
        client,
        f"/library/assets/{a['id']}/identity",
        {
            "expected_revision": a["revision"],
            "identity": {
                "title": "Parasite",
                "year": 2026,
                "media_type": "movie",
                "provider_id": "1",
                "edition": "Director's Cut",
                "title_language": "en-US",
                "english_title_verified": True,
            },
        },
    )
    assert response.status_code == 200
    updated = worker.db.one(select(p.assets).where(p.assets.c.id == a["id"]))
    assert (
        updated["data"]["identity"]["custom_preserved"] == original["custom_preserved"]
    )
    assert updated["data"]["bg"] == "BG_VERIFIED"
    assert updated["relative_path"] == a["relative_path"]
    assert updated["data"]["identity"]["title_provenance"] == "manual-override"
