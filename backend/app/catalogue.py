"""Materialized probe fields and PostgreSQL-wide catalogue queries."""

import re
from pathlib import PurePosixPath
from typing import Any
from weakref import WeakKeyDictionary

from sqlalchemy import case, func, or_, select

from app import persistence as p
from app.domain import CATEGORIES

LANGUAGES = {
    "bul": "bg",
    "eng": "en",
    "deu": "de",
    "ger": "de",
    "fra": "fr",
    "fre": "fr",
    "spa": "es",
    "jpn": "ja",
    "rus": "ru",
    "ita": "it",
}

CACHE: WeakKeyDictionary[p.Database, tuple[int, list[dict[str, Any]]]] = WeakKeyDictionary()


def language(value: Any) -> str:
    value = str(value or "und").lower()
    return LANGUAGES.get(value, value if re.fullmatch(r"[a-z]{2,3}", value) else "und")


def integer(value: Any) -> int | None:
    if str(value).isdecimal() and 0 <= int(value) <= 9223372036854775807:
        return int(value)
    return None


def normalized(path: str, data: dict[str, Any]) -> dict[str, Any]:
    probe = data.get("probe") or {}
    streams = probe.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    width = max((integer(s.get("width")) or 0 for s in videos), default=0)
    height = max((integer(s.get("height")) or 0 for s in videos), default=0)
    quality = (
        "8K"
        if width >= 7680 or height >= 4320
        else "4K"
        if width >= 3840 or height >= 2160
        else "2K"
        if width >= 2048
        else "Full HD"
        if width >= 1920 or height >= 1080
        else "HD"
        if width >= 1280 or height >= 720
        else "SD"
        if width or height
        else None
    )
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    subtitles = [s for s in streams if s.get("codec_type") == "subtitle"]
    return {
        "title": (data.get("identity") or {}).get("title") or PurePosixPath(path).stem,
        "category": data.get("category")
        or next((k for k, v in CATEGORIES.items() if path.startswith(v + "/")), None),
        "video_quality": quality,
        "audio_codecs": sorted(
            {str(s.get("codec_name", "unknown")).lower() for s in audio}
            | ({"dts_hd_ma"} if any(s.get("profile") == "DTS-HD MA" for s in audio) else set())
        )
        if "streams" in probe
        else ["unknown"],
        "audio_languages": sorted({language(s.get("tags", {}).get("language")) for s in audio})
        if "streams" in probe
        else ["und"],
        # NULL means uninspected; [] means probe found no embedded or inventoried external tracks.
        "subtitle_languages": sorted(
            {language(s.get("tags", {}).get("language")) for s in subtitles}
            | {language(s.get("language")) for s in data.get("external_subtitles", [])}
        )
        if "streams" in probe
        else None,
        "file_size_bytes": integer(probe.get("format", {}).get("size")),
    }


def filters(criteria: dict[str, Any]) -> list[Any]:
    a = p.assets.c
    result = [a.workflow_state == "ACTIVE"]
    if criteria.get("search"):
        pattern = (
            "%"
            + criteria["search"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            + "%"
        )
        result.append(
            or_(a.title.ilike(pattern, escape="\\"), a.relative_path.ilike(pattern, escape="\\"))
        )
    for name in ("category", "video_quality"):
        if criteria.get(name):
            result.append(a[name] == criteria[name])
    for name, column in [
        ("audio_codec", a.audio_codecs),
        ("audio_language", a.audio_languages),
        ("subtitle_language", a.subtitle_languages),
    ]:
        value = criteria.get(name)
        if value == "unknown":
            result.append(
                or_(
                    column.is_(None),
                    column.contains(["unknown" if name == "audio_codec" else "und"]),
                )
            )
        elif value == "none":
            result.append(column == [])
        elif value:
            result.append(column.contains([value]))
    return result


def page(db: p.Database, criteria: dict[str, Any]) -> dict[str, Any]:
    clauses = filters(criteria)
    columns = {
        "title": func.lower(p.assets.c.title),
        "category": p.assets.c.category,
        "size": p.assets.c.file_size_bytes,
        "quality": case(
            {"SD": 1, "HD": 2, "Full HD": 3, "2K": 4, "4K": 5, "8K": 6},
            value=p.assets.c.video_quality,
            else_=0,
        ),
        "path": p.assets.c.relative_path,
    }
    sort = columns[criteria.get("sort", "title")]
    sort = sort.desc() if criteria.get("order") == "desc" else sort.asc()
    # One repeatable snapshot for count + page; ID tie-break makes equal values stable.
    with db.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            total = conn.execute(
                select(func.count()).select_from(p.assets).where(*clauses)
            ).scalar_one()
            rows = (
                conn.execute(
                    select(p.assets)
                    .where(*clauses)
                    .order_by(sort.nulls_last(), p.assets.c.id)
                    .limit(criteria["limit"])
                    .offset(criteria["offset"])
                )
                .mappings()
                .all()
            )
    return {
        "items": [display(dict(row)) for row in rows],
        "total": total,
        "limit": criteria["limit"],
        "offset": criteria["offset"],
    }


def display(row: dict[str, Any]) -> dict[str, Any]:
    streams = row["data"].get("probe", {}).get("streams")
    row["streams"] = (
        None
        if streams is None
        else [
            {
                "index": s.get("index"),
                "type": s.get("codec_type"),
                "codec": s.get("codec_name"),
                "profile": s.get("profile"),
                "language": language(s.get("tags", {}).get("language")),
                "channels": s.get("channels"),
                "bitrate": integer(s.get("bit_rate")),
                "width": s.get("width"),
                "height": s.get("height"),
                "provenance": "ffprobe-stream-tag",
            }
            for s in streams
        ]
    )
    return row


def analytics(db: p.Database) -> dict[str, Any]:
    generation = db.rows(
        select(p.settings_table.c.revision).where(
            p.settings_table.c.key == "library_catalogue_generation"
        )
    )
    revision = generation[0]["revision"] if generation else None
    cached = CACHE.get(db)
    rows = (
        cached[1]
        if cached and revision is not None and cached[0] == revision
        else db.rows(
            select(
                p.assets.c.category,
                func.count().label("count"),
                func.coalesce(func.sum(p.assets.c.file_size_bytes), 0).label("bytes"),
                func.count(p.assets.c.file_size_bytes).label("known_sizes"),
            )
            .where(p.assets.c.workflow_state == "ACTIVE")
            .group_by(p.assets.c.category)
        )
    )
    if revision is not None:
        CACHE[db] = (revision, rows)
    known = {row["category"]: {**row, "bytes": int(row["bytes"])} for row in rows}
    return {
        "categories": [
            known.get(k, {"category": k, "count": 0, "bytes": 0, "known_sizes": 0})
            for k in CATEGORIES
        ],
        "snapshot_at": p.now(),
        "last_scan": db.rows(select(p.scans).order_by(p.scans.c.created_at.desc()).limit(1)),
    }
