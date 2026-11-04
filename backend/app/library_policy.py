"""Versioned hierarchy/token evaluator, shared by preview and approved plans."""

import re
from pathlib import PurePosixPath
from typing import Any

from app.domain import CATEGORIES, GateError, component, relative
from app.english_metadata import require_english

TOKENS = {
    "Title",
    "SeriesTitle",
    "Year",
    "Season",
    "Episode",
    "EpisodeTitle",
    "Resolution",
    "BG",
    "Edition",
    "VideoCodec",
    "AudioCodec",
    "Artist",
    "Event",
    "CollectionName",
    "VideoBase",
    "SubtitleLang",
}
TOKEN = re.compile(r"\{([A-Za-z]+)(?::(02))?\}")


def defaults() -> dict[str, Any]:
    result: dict[str, Any] = {"schema": 1, "collections": True, "categories": {}}
    for category, root in CATEGORIES.items():
        types = (
            ["show"]
            if category == "series"
            else ["concert"]
            if category == "concerts"
            else ["movie", "show"]
            if category in {"animations", "documentaries"}
            else ["movie"]
        )
        routes = {}
        for media_type in types:
            base = (
                ["Series" if media_type == "show" else "Movies"]
                if category in {"animations", "documentaries"}
                else []
            )
            if media_type == "show":
                folders = base + ["{SeriesTitle} ({Year})", "Season {Season:02}"]
                filename = [
                    "{SeriesTitle}",
                    " S",
                    "{Season:02}",
                    "E",
                    "{Episode:02}",
                    " - ",
                    "{Resolution}",
                    "{BG}",
                    "{Edition}",
                ]
            elif media_type == "concert":
                folders = ["{Artist} - {Event} ({Year})"]
                filename = [
                    "{Artist}",
                    " - ",
                    "{Event}",
                    " (",
                    "{Year}",
                    ")",
                    " - ",
                    "{Resolution}",
                    "{BG}",
                    "{Edition}",
                ]
            else:
                folders = base + ["{CollectionName}", "{Title} ({Year})"]
                filename = [
                    "{Title}",
                    " (",
                    "{Year}",
                    ")",
                    " - ",
                    "{Resolution}",
                    "{BG}",
                    "{Edition}",
                ]
            routes[media_type] = {
                "folders": folders,
                "filename": filename,
                "subtitle": ["{VideoBase}", ".", "{SubtitleLang}"],
            }
        result["categories"][category] = {"root": root, "routes": routes}
    return result


def _validate(policy: dict[str, Any]) -> None:
    if (
        set(policy) != {"schema", "collections", "categories"}
        or policy["schema"] != 1
        or type(policy["collections"]) is not bool
    ):
        raise GateError("INVALID_POLICY")
    if set(policy["categories"]) != set(CATEGORIES):
        raise GateError("INVALID_POLICY_CATEGORIES")
    roots = []
    for cat, conf in policy["categories"].items():
        if set(conf) != {"root", "routes"} or not isinstance(conf["root"], str):
            raise GateError("INVALID_POLICY")
        relative(conf["root"])
        if "/" in conf["root"] or component(conf["root"]) != conf["root"]:
            raise GateError("INVALID_POLICY_ROOT")
        roots.append(conf["root"].casefold())
        if set(conf["routes"]) != set(defaults()["categories"][cat]["routes"]):
            raise GateError("INVALID_MEDIA_ROUTES")
        for media_type, rule in conf["routes"].items():
            if set(rule) != {"folders", "filename", "subtitle"}:
                raise GateError("INVALID_POLICY_RULE")
            for name, parts in rule.items():
                if (
                    not isinstance(parts, list)
                    or not 1 <= len(parts) <= 32
                    or any(not isinstance(x, str) or not 1 <= len(x) <= 140 for x in parts)
                ):
                    raise GateError("INVALID_POLICY_RULE")
                for part in parts:
                    stripped = TOKEN.sub("", part)
                    if re.search(r'[\\/:*?"<>|{}\x00-\x1f]', stripped) or ".." in stripped:
                        raise GateError("UNSAFE_POLICY_TEMPLATE")
                    for token, width in TOKEN.findall(part):
                        if token not in TOKENS or width and token not in {"Season", "Episode"}:
                            raise GateError("INVALID_POLICY_TOKEN")
                        if name != "subtitle" and token in {"VideoBase", "SubtitleLang"}:
                            raise GateError("INVALID_POLICY_TOKEN")
            if "{VideoBase}" not in rule["subtitle"] or "{SubtitleLang}" not in rule["subtitle"]:
                raise GateError("SUBTITLE_VIDEO_BINDING_REQUIRED")
            identifier = (
                "{SeriesTitle}"
                if media_type == "show"
                else "{Artist}"
                if media_type == "concert"
                else "{Title}"
            )
            if not any(identifier in value for value in rule["filename"]) or not any(
                identifier in value for value in rule["folders"]
            ):
                raise GateError("IDENTITY_TOKENS_REQUIRED")
            if media_type == "show" and not all(
                any(t in s for s in rule["filename"]) for t in ["{Season:02}", "{Episode:02}"]
            ):
                raise GateError("EPISODE_TOKENS_REQUIRED")
    if len(set(roots)) != 5:
        raise GateError("CATEGORY_ROOT_COLLISION")


def validate(policy: dict[str, Any]) -> None:
    try:
        _validate(policy)
    except (TypeError, KeyError, ValueError, AttributeError):
        raise GateError("INVALID_POLICY") from None


def validate_for_save(policy: dict[str, Any]) -> None:
    validate(policy)
    for category, conf in policy["categories"].items():
        for media_type in conf["routes"]:
            for bg in ["NO_BG", "BG_TAGGED"]:
                render(
                    policy,
                    category,
                    {
                        "title": "Sample",
                        "year": 2026,
                        "media_type": media_type,
                        "confirmed": True,
                        "title_language": "en-US",
                        "english_title_verified": True,
                        "season": 1,
                        "episodes": [1],
                        "episode_title": "Sample Episode",
                        "episode_title_language": "en-US",
                        "artist": "Sample Artist",
                        "edition": "Extended",
                    },
                    {"quality_label": "1080p", "bg": bg},
                    "sample.mkv",
                )


def render(
    policy: dict[str, Any],
    category: str,
    identity: dict[str, Any],
    data: dict[str, Any],
    old_path: str,
) -> dict[str, str]:
    validate(policy)
    media_type = identity.get("media_type")
    if (
        not identity.get("confirmed")
        or not identity.get("title")
        or not isinstance(identity.get("year"), int)
        or not 1880 <= identity["year"] <= 2200
    ):
        raise GateError("IDENTITY_REVIEW_REQUIRED")
    conf = policy["categories"].get(category, {})
    require_english(identity)
    rule = conf.get("routes", {}).get(media_type)
    if not rule:
        raise GateError("CATEGORY_CONFLICT")
    streams = data.get("probe", {}).get("streams", [])
    video: dict[str, Any] = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio: dict[str, Any] = next((s for s in streams if s.get("codec_type") == "audio"), {})
    episodes = identity.get("episodes", [])
    if media_type == "show" and (identity.get("season") is None or not episodes):
        raise GateError("EPISODE_MAPPING_REQUIRED")
    collection = (
        identity.get("collection_override") or identity.get("collection_name") or ""
        if policy["collections"]
        else ""
    )
    if collection and "{CollectionName}" in "".join(rule["folders"] + rule["filename"]):
        language = (
            identity.get("collection_override_language")
            if identity.get("collection_override")
            else identity.get("collection_language")
        )
        if language != "en-US":
            raise GateError("ENGLISH_COLLECTION_REVIEW_REQUIRED")
    if "{EpisodeTitle}" in "".join(rule["folders"] + rule["filename"]) and (
        not identity.get("episode_title") or identity.get("episode_title_language") != "en-US"
    ):
        raise GateError("ENGLISH_EPISODE_TITLE_UNAVAILABLE")
    values = {
        "Title": identity["title"],
        "SeriesTitle": identity["title"],
        "Year": identity["year"],
        "Season": identity.get("season"),
        "Episode": episodes[0] if episodes else None,
        "EpisodeTitle": identity.get("episode_title", ""),
        "Resolution": data.get("quality_label")
        or (str(video["height"]) + "p" if video.get("height") else ""),
        "BG": "BG" if data.get("bg") in {"BG_TAGGED", "BG_VERIFIED", "BG_DETECTED"} else "",
        "Edition": identity.get("edition", ""),
        "VideoCodec": video.get("codec_name", ""),
        "AudioCodec": audio.get("codec_name", ""),
        "Artist": identity.get("artist", ""),
        "Event": identity.get("event") or identity["title"],
        "CollectionName": collection,
        "SubtitleLang": "bg",
    }
    if media_type == "concert" and not values["Artist"]:
        raise GateError("CONCERT_ARTIST_REQUIRED")

    def evaluate(template: str) -> str:
        def substitute(match: re.Match[str]) -> str:
            value = values.get(match[1])
            if value is None:
                raise GateError("MISSING_NAMING_VALUE")
            return str(value).zfill(2) if match[2] else str(value)

        return TOKEN.sub(substitute, template)

    def tidy(value: str) -> str:
        value = re.sub(r"\(\s*\)", "", value)
        value = re.sub(r"\s{2,}", " ", value).strip(" -.")
        return component(value) if value else ""

    folders = [conf["root"]]
    for template in rule["folders"]:
        rendered = tidy(evaluate(template))
        if rendered:
            folders.append(rendered)
    parts = []
    for token in rule["filename"]:
        value = evaluate(token)
        if token in {"{BG}", "{Edition}"} and value:
            value = " - " + value
        parts.append(value)
    filename = tidy("".join(parts))
    if media_type == "show" and len(episodes) > 1:
        if episodes != list(range(episodes[0], episodes[-1] + 1)):
            raise GateError("NONCONTIGUOUS_EPISODES")
        filename = filename.replace(
            f"E{episodes[0]:02}", f"E{episodes[0]:02}-E{episodes[-1]:02}", 1
        )
    if media_type in {"movie", "concert"} and not filename.startswith(folders[-1] + " - "):
        raise GateError("JELLYFIN_VERSION_PREFIX_REQUIRED")
    extension = PurePosixPath(old_path).suffix.lower()
    if extension not in {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts"}:
        raise GateError("UNSUPPORTED_MEDIA")
    values["VideoBase"] = filename
    subtitle = tidy("".join(evaluate(token) for token in rule["subtitle"])) + ".srt"
    if subtitle != filename + ".bg.srt":
        raise GateError("JELLYFIN_SUBTITLE_NAME_REQUIRED")
    return {"path": relative("/".join([*folders, filename + extension])), "subtitle": subtitle}
