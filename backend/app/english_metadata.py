"""Language-scoped, authority-backed naming proposals; no catalogue or filesystem writes."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import persistence as p
from app.domain import GateError

LANGUAGE = "en-US"


def cached(worker: Any, key: str, fetch: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    rows = worker.db.rows(select(p.settings_table).where(p.settings_table.c.key == key))
    value = rows[0]["value"] if rows else {}
    try:
        fresh = 0 <= (p.now() - datetime.fromisoformat(value["cached_at"])).total_seconds() < 86400
    except (KeyError, TypeError, ValueError):
        fresh = False
    if fresh and value.get("cache_language") == LANGUAGE:
        return dict(value)
    value = {**fetch(), "cache_language": LANGUAGE, "cached_at": p.now().isoformat()}
    with worker.db.transaction() as conn:
        conn.execute(
            pg_insert(p.settings_table)
            .values(key=key, value=value)
            .on_conflict_do_update(
                index_elements=["key"],
                set_={"value": value},
            )
        )
    return value


def require_english(identity: dict[str, Any]) -> None:
    if (
        identity.get("title_language") != LANGUAGE
        or identity.get("english_title_verified") is not True
        or not isinstance(identity.get("title"), str)
        or not identity["title"].strip()
    ):
        raise GateError("ENGLISH_TITLE_REVIEW_REQUIRED")


def propose(
    worker: Any, asset: dict[str, Any], known: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    known = dict(known)
    provider_id = known.get("provider_id")
    media_type = known["media_type"]
    if provider_id:
        provider_id = str(provider_id)
        known["provider_id"] = provider_id
        value = cached(
            worker,
            f"tmdb:{LANGUAGE}:{media_type}:{provider_id}",
            lambda: worker.tmdb.details(provider_id, media_type),
        )
        require_english(value)
        if str(value.get("provider_id")) != provider_id:
            raise GateError("METADATA_ID_CONFLICT")
        if known.get("year") and value.get("year") != known["year"]:
            raise GateError("METADATA_YEAR_CONFLICT")
        manual = (
            known.get("title_provenance") == "manual-override"
            or known.get("title_override") is True
        )
        if known.get("title") and known["title"] != value["title"]:
            # Historical manual confirmations did not carry a title-origin marker.
            manual = manual or bool(
                worker.db.rows(
                    select(p.audit.c.id)
                    .where(
                        p.audit.c.target == asset["id"],
                        p.audit.c.kind == "LIBRARY_IDENTITY_CONFIRMED",
                    )
                    .limit(1)
                )
            )
            if manual:
                raise GateError("MANUAL_TITLE_OVERRIDE_REVIEW")
        for field in (
            "title",
            "title_language",
            "english_title_verified",
            "original_title",
            "original_name",
            "imdb_id",
            "collection_id",
            "collection_name",
            "collection_language",
            "poster_path",
            "backdrop_path",
        ):
            if value.get(field) is not None:
                known[field] = value[field]
        # A missing current translation must not retain a stale collection label.
        if "collection_id" in value:
            known["collection_id"] = value.get("collection_id")
            known["collection_name"] = value.get("collection_name")
            known["collection_language"] = value.get("collection_language")
        known["year"] = known.get("year") or value.get("year")
        known["confirmed"] = True
        known["provenance"] = "reused-tmdb-id:en-US"
    require_english(known)
    rule = policy["categories"][asset["category"]]["routes"].get(media_type, {})
    templates = "".join(rule.get("folders", []) + rule.get("filename", []))
    if policy["collections"] and "{CollectionName}" in templates:
        if known.get("collection_override"):
            if known.get("collection_override_language") != LANGUAGE:
                raise GateError("ENGLISH_COLLECTION_REVIEW_REQUIRED")
        elif known.get("collection_id") or known.get("collection_name"):
            if not known.get("collection_name") or known.get("collection_language") != LANGUAGE:
                raise GateError("ENGLISH_COLLECTION_UNAVAILABLE")
    if "{EpisodeTitle}" in templates:
        episodes = known.get("episodes", [])
        if provider_id:
            if len(episodes) != 1 or known.get("season") is None:
                raise GateError("ENGLISH_EPISODE_MAPPING_REVIEW")
            season, episode = known["season"], episodes[0]
            value = cached(
                worker,
                f"tmdb:{LANGUAGE}:episode:{provider_id}:{season}:{episode}",
                lambda: worker.tmdb.episode(provider_id, season, episode),
            )
            if value.get("episode_title_language") != LANGUAGE or not value.get("episode_title"):
                raise GateError("ENGLISH_EPISODE_TITLE_UNAVAILABLE")
            if known.get("episode_title") and known["episode_title"] != value["episode_title"]:
                known.setdefault("original_episode_title", known["episode_title"])
            known.update({key: value[key] for key in ("episode_title", "episode_title_language")})
        elif not known.get("episode_title") or known.get("episode_title_language") != LANGUAGE:
            raise GateError("ENGLISH_EPISODE_TITLE_UNAVAILABLE")
    if media_type == "concert" and known.get("event") and known["event"] != known["title"]:
        raise GateError("MANUAL_EVENT_TITLE_REVIEW")
    return known
