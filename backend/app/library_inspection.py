"""NAS catalogue enrichment and review evidence, without torrent lifecycle coupling."""

import re
import unicodedata
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import Text, case, cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app import catalogue, library_policy
from app import persistence as p
from app.domain import GateError
from app.english_metadata import cached, propose


def proposal_state() -> Any:
    f = p.maintenance_files.c
    error = f.data["error_code"].astext
    return case(
        (
            error.in_(["AMBIGUOUS_IDENTITY", "IDENTITY_UNAVAILABLE", "ENGLISH_TITLE_UNAVAILABLE"]),
            "Unidentified",
        ),
        (
            error.in_(
                [
                    "DESTINATION_COLLISION",
                    "CASE_COLLISION",
                    "PLAN_DESTINATION_COLLISION",
                    "WORK_DIRECTORY_IDENTITY_CONFLICT",
                ]
            ),
            "Conflict",
        ),
        (f.state == "NeedsReview", "NeedsReview"),
        (
            (f.state == "NoChange")
            | ((f.state == "Planned") & (f.data["already_normalized"].astext == "true")),
            "AlreadyNormalized",
        ),
        else_="Ready",
    )


def parsed(asset: dict[str, Any]) -> dict[str, Any]:
    name = PurePosixPath(asset["relative_path"]).stem
    episode = re.search(r"(?i)S(\d{1,3})E(\d{1,3})(?:-?E(\d{1,3}))?", name)
    year = re.search(r"\b(19\d{2}|20\d{2})\b", name)
    title = re.split(r"(?i)\b(?:19\d{2}|20\d{2}|S\d+E\d+|tmdbid)\b", name.replace(".", " "))[0]
    return {
        "title": title.strip(" -_"),
        "year": int(year[0]) if year else None,
        "media_type": "show"
        if episode or asset["category"] == "series"
        else "concert"
        if asset["category"] == "concerts"
        else "movie",
        **(
            {
                "season": int(episode[1]),
                "episodes": list(range(int(episode[2]), int(episode[3] or episode[2]) + 1)),
            }
            if episode
            else {}
        ),
    }


def search(worker: Any, title: str, media_type: str, year: int | None) -> list[dict[str, Any]]:
    from app.domain import digest

    key = "tmdb:en-US:search:" + digest([title, media_type, year])
    return list(
        cached(worker, key, lambda: {"items": worker.tmdb.search(title, media_type, year)})["items"]
    )


def resolve(worker: Any, asset: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    known = dict(asset["data"].get("identity") or {})
    stored = re.fullmatch(r"tmdb:(movie|show):(\d+)", asset.get("identity_key") or "")
    if stored:
        known.setdefault("media_type", stored[1])
    guess = parsed(asset)
    for key, value in guess.items():
        if key != "title" and value is not None:
            known.setdefault(key, value)
    known.setdefault("edition", "Unknown")
    if known.get("supplementary"):
        raise GateError("SUPPLEMENTARY_MATERIAL_REVIEW")
    if isinstance(known.get("year"), str) and known["year"].isdecimal():
        known["year"] = int(known["year"])
    explicit = re.search(r"(?i)tmdb(?:id)?[- _]?(\d+)", asset["relative_path"])
    if not known.get("provider_id") and (explicit or stored):
        known["provider_id"] = explicit[1] if explicit else stored[2] if stored else None
    if not known.get("provider_id") and not known.get("confirmed"):
        candidates = search(worker, guess["title"], known["media_type"], known.get("year"))

        def title_key(title: str) -> str:
            return re.sub(r"[^\w]+", "", unicodedata.normalize("NFKC", title).casefold())

        matches = [
            c
            for c in candidates
            if known.get("year")
            and c.get("year") == known["year"]
            and c.get("media_type") == known["media_type"]
            and title_key(c.get("title") or "") == title_key(guess["title"])
        ]
        if len(matches) != 1:
            raise GateError("AMBIGUOUS_IDENTITY" if candidates else "IDENTITY_UNAVAILABLE")
        known["provider_id"] = str(matches[0]["id"])
        known["provenance"] = "exact-title-year:en-US"
    return propose(worker, asset, known, policy)


def inspect_asset(worker: Any, task: dict[str, Any], asset_id: str) -> None:
    """Only catalogue writes. Manual decisions and media bytes remain authoritative."""
    db = worker.db
    asset = db.one(select(p.assets).where(p.assets.c.id == asset_id))
    policies = db.rows(select(p.policies).order_by(p.policies.c.revision.desc()).limit(1))
    policy = policies[0]["data"] if policies else library_policy.defaults()
    guess = parsed(asset)
    review: dict[str, Any] = {
        "parsed": guess,
        "language": "en-US",
        "candidates": [],
    }
    identity = asset["data"].get("identity") or {}
    try:
        proposed = resolve(worker, asset, policy)
        identity = proposed
        if (
            proposed.get("provider_id")
            and proposed["media_type"] == "show"
            and proposed.get("season") is not None
            and len(proposed.get("episodes", [])) == 1
        ):
            provider_id, season, episode = (
                proposed["provider_id"],
                proposed["season"],
                proposed["episodes"][0],
            )
            value = cached(
                worker,
                f"tmdb:en-US:episode:{provider_id}:{season}:{episode}",
                lambda: worker.tmdb.episode(provider_id, season, episode),
            )
            if value.get("episode_title_language") != "en-US" or not value.get("episode_title"):
                raise GateError("ENGLISH_EPISODE_TITLE_UNAVAILABLE")
            proposed.update(episode_title=value["episode_title"], episode_title_language="en-US")
        review.update(state="Identified", proposed_identity=proposed, reason=None)
    except (GateError, OSError) as error:
        review.update(
            state="Unidentified" if not identity.get("confirmed") else "NeedsReview",
            reason=error.code if isinstance(error, GateError) else "METADATA_UNAVAILABLE",
        )
    if review["state"] != "Identified":
        try:
            review["candidates"] = search(
                worker, guess["title"], guess["media_type"], guess["year"]
            )
        except (GateError, OSError):
            pass
    related = [p.assets.c.fingerprint == asset["fingerprint"]]
    if identity.get("provider_id"):
        related.append(
            (p.assets.c.data["identity"]["provider_id"].astext == str(identity["provider_id"]))
            & (p.assets.c.data["identity"]["media_type"].astext == identity.get("media_type"))
        )
    peers = db.rows(
        select(
            p.assets.c.id,
            p.assets.c.relative_path,
            p.assets.c.fingerprint,
            p.assets.c.data["identity"].label("identity"),
        )
        .where(
            p.assets.c.id != asset_id,
            p.assets.c.workflow_state == "ACTIVE",
            or_(*related),
        )
        .order_by(p.assets.c.id)
    )
    review["versions"] = [
        {
            "asset_id": row["id"],
            "path": row["relative_path"],
            "identity": row["identity"],
            "reason": "identical-bytes"
            if row["fingerprint"] == asset["fingerprint"]
            else "same-work-edition-preserved",
        }
        for row in peers
    ]
    from app.storage import contained

    source = contained(worker.cfg.nas_root, "Library/" + asset["relative_path"], existing=True)
    associated = [
        {"path": path.relative_to(worker.cfg.nas_root).as_posix(), "kind": path.suffix.lower()}
        for path in sorted(source.parent.iterdir())
        if not path.is_symlink()
        and path.is_file()
        and (
            path.name.startswith(source.stem + ".")
            or path.name in {"movie.nfo", "tvshow.nfo", "poster.jpg", "backdrop.jpg", "folder.jpg"}
        )
        and path != source
    ]
    data = {
        **asset["data"],
        "identity": identity,
        "inspection": review,
        "associated_files": associated,
    }
    with db.transaction() as conn:
        db.assert_lease(conn, task)
        current = conn.execute(
            select(p.assets.c.revision).where(p.assets.c.id == asset_id).with_for_update()
        ).scalar_one()
        if current != asset["revision"]:
            raise GateError("ASSET_REVISION_STALE")
        if data != asset["data"]:
            conn.execute(
                update(p.assets)
                .where(p.assets.c.id == asset_id)
                .values(
                    data=data,
                    revision=current + (identity != (asset["data"].get("identity") or {})),
                    **catalogue.normalized(asset["relative_path"], data),
                )
            )
        db.event(
            conn,
            "worker",
            "LIBRARY_METADATA_INSPECTED",
            asset_id,
            {"state": review["state"], "reason": review["reason"]},
        )


def refresh_versions(worker: Any, task: dict[str, Any]) -> None:
    """Resolve both directions after all new files/identities have been inventoried."""
    rows = worker.db.rows(
        select(
            p.assets.c.id,
            p.assets.c.relative_path,
            p.assets.c.fingerprint,
            p.assets.c.data["identity"].label("identity"),
            p.assets.c.data["inspection"].label("inspection"),
        )
        .where(p.assets.c.workflow_state == "ACTIVE")
        .order_by(p.assets.c.id)
    )
    fingerprints: dict[str, list[dict[str, Any]]] = {}
    works: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        fingerprints.setdefault(row["fingerprint"], []).append(row)
        identity = row["identity"] or {}
        if identity.get("confirmed") and identity.get("provider_id"):
            works.setdefault(
                (identity.get("media_type", ""), str(identity["provider_id"])), []
            ).append(row)
    with worker.db.transaction() as conn:
        worker.db.assert_lease(conn, task)
        for row in rows:
            if not row["inspection"]:
                continue
            identity = row["identity"] or {}
            peers = {
                peer["id"]: peer
                for peer in fingerprints[row["fingerprint"]]
                + works.get((identity.get("media_type", ""), str(identity.get("provider_id"))), [])
                if peer["id"] != row["id"]
            }
            versions = [
                {
                    "asset_id": peer["id"],
                    "path": peer["relative_path"],
                    "identity": peer["identity"],
                    "reason": "identical-bytes"
                    if peer["fingerprint"] == row["fingerprint"]
                    else "same-work-edition-preserved",
                }
                for _, peer in sorted(peers.items())
            ]
            if versions != row["inspection"].get("versions"):
                conn.execute(
                    update(p.assets)
                    .where(p.assets.c.id == row["id"])
                    .values(
                        data=func.jsonb_set(
                            p.assets.c.data,
                            cast(["inspection", "versions"], ARRAY(Text)),
                            cast(versions, JSONB),
                        )
                    )
                )


def execute(worker: Any, task: dict[str, Any]) -> None:
    worker.db.reserve(task, ["library-scan", "asset:" + task["data"]["asset_id"]])
    asset_id = task["data"]["asset_id"]
    if task["data"].get("search") or task["data"].get("lookup"):
        if task["data"].get("lookup"):
            query = task["data"]["lookup"]
            value = cached(
                worker,
                f"tmdb:en-US:{query['media_type']}:{query['provider_id']}",
                lambda: worker.tmdb.details(query["provider_id"], query["media_type"]),
            )
            from app.english_metadata import require_english

            require_english(value)
            candidates = [{**value, "id": query["provider_id"], "media_type": query["media_type"]}]
        else:
            query = task["data"]["search"]
            candidates = search(worker, query["title"], query["media_type"], query.get("year"))
        from sqlalchemy import insert

        with worker.db.transaction() as conn:
            worker.db.assert_lease(conn, task)
            conn.execute(
                insert(p.evidence_tables["identity_candidates"]).values(
                    asset_id=asset_id,
                    data={"candidates": candidates, "source": "manual-TMDb-search:en-US"},
                )
            )
    else:
        from app.domain import bg_state
        from app.storage import contained, sha256

        worker.nas_health()
        asset = worker.db.one(select(p.assets).where(p.assets.c.id == asset_id))
        source = contained(worker.cfg.nas_root, "Library/" + asset["relative_path"], existing=True)
        before = source.stat()
        fingerprint = sha256(source)
        probe = worker.probe(source)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise GateError("CHANGED_DURING_SCAN")
        data = {
            **asset["data"],
            "probe": probe,
            "fingerprint_verification": "verified",
            "bg": asset["data"].get("bg")
            if fingerprint == asset["fingerprint"] and asset["data"].get("bg") == "BG_VERIFIED"
            else bg_state(probe, fingerprint, []),
        }
        data["external_subtitles"] = [
            {
                "path": path.relative_to(worker.cfg.nas_root / "Library").as_posix(),
                "language": path.name[len(source.stem) + 1 :].split(".")[0]
                if len(path.name[len(source.stem) + 1 :].split(".")) > 1
                else "und",
            }
            for path in source.parent.iterdir()
            if not path.is_symlink()
            and path.is_file()
            and path.name.startswith(source.stem + ".")
            and path.suffix.lower() in {".srt", ".ass", ".ssa", ".vtt"}
        ]
        with worker.db.transaction() as conn:
            worker.db.assert_lease(conn, task)
            conn.execute(
                update(p.assets)
                .where(p.assets.c.id == asset_id)
                .values(
                    data=data,
                    fingerprint=fingerprint,
                    mtime_ns=after.st_mtime_ns,
                    observed_size=after.st_size,
                    availability="AVAILABLE",
                    revision=asset["revision"]
                    + (fingerprint != asset["fingerprint"] or probe != asset["data"].get("probe")),
                    **catalogue.normalized(asset["relative_path"], data),
                )
            )
        inspect_asset(worker, task, asset_id)
        refresh_versions(worker, task)
