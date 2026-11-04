"""Real providers. Credentials never leave their Worker process."""

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.domain import CATEGORIES, GateError, Torrent, relative
from app.settings import Settings


class Remote:
    def __init__(
        self,
        name: str,
        base: str,
        headers: dict[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        parsed = urlsplit(base)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise GateError("INVALID_SERVICE_URL")
        self.name = name
        self.rate_limited_until = 0.0
        self.http = httpx.Client(
            base_url=base.rstrip("/") + "/",
            headers=headers,
            timeout=httpx.Timeout(connect=5, read=20, write=20, pool=5),
            follow_redirects=False,
            transport=transport,
            trust_env=False,
        )

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if time.monotonic() < self.rate_limited_until:
            raise GateError(self.name + "_RETRY_LATER", "FailedRecoverable")
        try:
            response = self.http.request(method, path.lstrip("/"), **kwargs)
        except httpx.TimeoutException:
            raise GateError(self.name + "_TIMEOUT", "BlockedExternalDependency") from None
        except httpx.HTTPError:
            raise GateError(self.name + "_UNAVAILABLE", "BlockedExternalDependency") from None
        if response.status_code in {401, 403}:
            raise GateError(self.name + "_AUTH_REQUIRED", "BlockedExternalDependency")
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "60")
            delay = min(3600, max(1, int(retry_after))) if retry_after.isdecimal() else 60
            self.rate_limited_until = time.monotonic() + delay
            raise GateError(self.name + "_RETRY_LATER", "FailedRecoverable")
        if response.status_code >= 500:
            raise GateError(self.name + "_RETRY_LATER", "FailedRecoverable")
        if not 200 <= response.status_code < 300:
            raise GateError(self.name + "_REQUEST_REJECTED", "NeedsReview")
        return response


class QBittorrent(Remote):
    def __init__(self, config: Settings, transport: httpx.BaseTransport | None = None):
        key = config.secret(config.qbt_api_key_file).get_secret_value()
        headers = {
            "Origin": config.qbt_url.rstrip("/"),
            "Referer": config.qbt_url.rstrip("/") + "/",
        }
        if key:
            headers["Authorization"] = "Bearer " + key
        super().__init__("QBT", config.qbt_url, headers, transport)
        self.config = config
        self.authenticated = bool(key)

    def login(self) -> None:
        if self.authenticated:
            return
        username = self.config.secret(self.config.qbt_username_file).get_secret_value()
        password = self.config.secret(self.config.qbt_password_file).get_secret_value()
        if not username or not password:
            raise GateError("QBT_AUTH_REQUIRED", "BlockedExternalDependency")
        result = self.request(
            "POST", "api/v2/auth/login", data={"username": username, "password": password}
        )
        if result.status_code not in {200, 204} or not self.http.cookies:
            raise GateError("QBT_AUTH_REQUIRED", "BlockedExternalDependency")
        # Verify session instead of trusting body/status/cookie name.
        self.request("GET", "api/v2/app/version")
        self.authenticated = True

    def get(self, path: str, **params: Any) -> Any:
        self.login()
        return self.request("GET", "api/v2/" + path, params=params).json()

    def version(self) -> dict[str, str]:
        self.login()
        return {
            "qbt": self.request("GET", "api/v2/app/version").text,
            "api": self.request("GET", "api/v2/app/webapiVersion").text,
        }

    def snapshot(self, raw: dict[str, Any]) -> Torrent:
        h = raw["hash"]
        if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", h):
            raise GateError("INVALID_TORRENT_HASH")
        files = self.get("torrents/files", hash=h)
        safe_files = [
            {k: f[k] for k in ("index", "name", "size", "progress", "priority") if k in f}
            for f in files
        ]
        for f in safe_files:
            relative(f["name"])
        policy = {
            k: raw.get(k)
            for k in (
                "force_start",
                "ratio_limit",
                "seeding_time_limit",
                "inactive_seeding_time_limit",
                "super_seeding",
                "seq_dl",
            )
        }
        policy["intentional_pause"] = raw["state"] in {"pausedUP", "stoppedUP"}
        policy["queued"] = raw["state"] == "queuedUP"
        return Torrent(
            h.lower(),
            int(raw.get("added_on", 0)),
            raw["category"],
            raw["save_path"],
            raw["content_path"],
            raw["state"],
            float(raw["progress"]),
            int(raw.get("amount_left", -1)),
            bool(raw["auto_tmm"]),
            safe_files,
            policy,
        )

    def all(self) -> list[Torrent]:
        return [self.snapshot(raw) for raw in self.get("torrents/info")]

    def torrent(self, info_hash: str) -> Torrent:
        result = self.get("torrents/info", hashes=info_hash)
        if len(result) != 1:
            raise GateError("TORRENT_INSTANCE_MISSING", "RecoveryRequired")
        return self.snapshot(result[0])

    def command(self, endpoint: str, info_hash: str, **payload: Any) -> None:
        if endpoint not in {
            "stop",
            "start",
            "renameFile",
            "renameFolder",
            "setLocation",
            "recheck",
        }:
            raise GateError("FORBIDDEN_QBT_COMMAND")
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", info_hash):
            raise GateError("INVALID_TORRENT_HASH")
        if any(k in payload for k in {"hashes", "hash", "deleteFiles", "category"}):
            raise GateError("FORBIDDEN_QBT_PAYLOAD")
        self.login()
        key = "hash" if endpoint in {"renameFile", "renameFolder"} else "hashes"
        self.request("POST", "api/v2/torrents/" + endpoint, data={key: info_hash, **payload})

    def add_fixture(self, torrent_bytes: bytes, category: str) -> None:
        if category not in CATEGORIES or not self.config.write_enabled:
            raise GateError("WRITE_GATE_CLOSED")
        self.login()
        self.request(
            "POST",
            "api/v2/torrents/add",
            data={
                "savepath": "/downloads/complete",
                "autoTMM": "false",
                "category": category,
                "stopped": "true",
            },
            files={
                "torrents": ("vimag-synthetic.torrent", torrent_bytes, "application/x-bittorrent")
            },
        )


class Jellyfin(Remote):
    def __init__(self, config: Settings, transport: httpx.BaseTransport | None = None):
        super().__init__(
            "JELLYFIN",
            config.jellyfin_url,
            {"X-Emby-Token": config.secret(config.jellyfin_api_key_file).get_secret_value()},
            transport,
        )

    def libraries(self) -> list[dict[str, Any]]:
        return self.request("GET", "Library/VirtualFolders").json()

    def health(self) -> bool:
        return bool(self.request("GET", "System/Info").json().get("Version"))

    def refresh(self) -> None:
        self.request("POST", "Library/Refresh")

    def recognized(self, expected: dict[str, Any]) -> dict[str, Any] | None:
        if expected.get("media_type") == "show":
            series = (
                self.request(
                    "GET",
                    "Items",
                    params={
                        "Recursive": "true",
                        "IncludeItemTypes": "Series",
                        "Fields": "ProviderIds,Path",
                        "AnyProviderIdEquals": "tmdb." + expected["provider_id"],
                    }
                    if expected.get("provider_id")
                    else {
                        "Recursive": "true",
                        "IncludeItemTypes": "Series",
                        "Fields": "ProviderIds,Path",
                        "SearchTerm": expected["title"],
                    },
                )
                .json()
                .get("Items", [])
            )
            series = [
                s
                for s in series
                if s.get("ProductionYear") == expected["year"]
                and (
                    str(s.get("ProviderIds", {}).get("Tmdb")) == expected.get("provider_id")
                    if expected.get("provider_id")
                    else s.get("Name") == expected["title"]
                )
            ]
            if len(series) != 1:
                return None
            params = {
                "Recursive": "true",
                "IncludeItemTypes": "Episode",
                "ParentId": series[0]["Id"],
                "Fields": "Path,ProviderIds,MediaSources,MediaStreams",
                "Limit": 2000,
            }
            catalog = self.request("GET", "Items", params=params).json().get("Items", [])
            matches = []
            for item in catalog:
                if (
                    item.get("ParentIndexNumber") != expected["season"]
                    or item.get("IndexNumber") != expected["episodes"][0]
                    or item.get("IndexNumberEnd", expected["episodes"][0])
                    != expected["episodes"][-1]
                ):
                    continue
                sources = [
                    s
                    for s in item.get("MediaSources", [])
                    if s.get("Path") == expected["jellyfin_path"] and s.get("MediaStreams")
                ]
                if len(sources) != 1:
                    continue
                streams = sources[0]["MediaStreams"]
                if expected.get("bg") in {"BG_VERIFIED", "BG_TAGGED", "BG_DETECTED"} and not any(
                    s.get("Type") == "Audio" and s.get("Language") in {"bul", "bg"} for s in streams
                ):
                    continue
                if expected.get("subtitle") in {"Matched", "Synchronized"} and not any(
                    s.get("Type") == "Subtitle" and s.get("Language") in {"bul", "bg"}
                    for s in streams
                ):
                    continue
                if expected.get("subtitle_path") and not any(
                    s.get("Type") == "Subtitle" and s.get("Path") == expected["subtitle_path"]
                    for s in streams
                ):
                    continue
                matches.append(
                    {
                        "item_id": item["Id"],
                        "series_id": series[0]["Id"],
                        "path_verified": True,
                        "streams_verified": True,
                    }
                )
            return matches[0] if len(matches) == 1 else None
        response = self.request(
            "GET",
            "Items",
            params={
                "Recursive": "true",
                "Fields": "Path,ProviderIds,MediaSources,MediaStreams",
                "IncludeItemTypes": "Movie,Episode,MusicVideo",
                "Limit": 200,
                "AnyProviderIdEquals": "tmdb." + expected["provider_id"],
            }
            if expected.get("provider_id")
            else {
                "Recursive": "true",
                "Fields": "Path,ProviderIds,MediaSources,MediaStreams",
                "IncludeItemTypes": "Movie,Episode,MusicVideo",
                "SearchTerm": expected["title"],
                "Limit": 200,
            },
        )
        matches = []
        for item in response.json().get("Items", []):
            sources = item.get("MediaSources", [])
            paths = {item.get("Path"), *(s.get("Path") for s in sources)}
            if expected["jellyfin_path"] not in paths:
                continue
            if (
                expected.get("provider_id")
                and str(item.get("ProviderIds", {}).get("Tmdb")) != expected["provider_id"]
            ):
                continue
            if item.get("ProductionYear") != expected["year"]:
                continue
            if expected.get("media_type") == "show" and (
                item.get("ParentIndexNumber") != expected["season"]
                or item.get("IndexNumber") != expected["episodes"][0]
                or item.get("IndexNumberEnd", expected["episodes"][0]) != expected["episodes"][-1]
            ):
                continue
            exact_sources = [s for s in sources if s.get("Path") == expected["jellyfin_path"]]
            if not exact_sources or not exact_sources[0].get("MediaStreams"):
                continue
            streams = exact_sources[0]["MediaStreams"]
            if expected.get("bg") in {"BG_VERIFIED", "BG_TAGGED", "BG_DETECTED"} and not any(
                s.get("Type") == "Audio" and s.get("Language") in {"bul", "bg"} for s in streams
            ):
                continue
            if expected.get("subtitle") in {"Matched", "Synchronized"} and not any(
                s.get("Type") == "Subtitle" and s.get("Language") in {"bul", "bg"} for s in streams
            ):
                continue
            if expected.get("subtitle_path") and not any(
                s.get("Type") == "Subtitle" and s.get("Path") == expected["subtitle_path"]
                for s in streams
            ):
                continue
            matches.append({"item_id": item["Id"], "path_verified": True, "streams_verified": True})
        return matches[0] if len(matches) == 1 else None


class TMDb(Remote):
    def __init__(self, config: Settings, transport: httpx.BaseTransport | None = None):
        super().__init__(
            "TMDB",
            "https://api.themoviedb.org/3/",
            {
                "Authorization": "Bearer "
                + config.secret(config.tmdb_api_key_file).get_secret_value()
            },
            transport,
        )

    def search(self, title: str, media_type: str, year: int | None) -> list[dict[str, Any]]:
        route = "tv" if media_type == "show" else "movie"
        params: dict[str, Any] = {"query": title, "language": "bg-BG", "include_adult": "false"}
        if year:
            params["first_air_date_year" if route == "tv" else "year"] = year
        candidates = self.request("GET", "search/" + route, params=params).json().get("results", [])
        return [
            {
                "id": str(c["id"]),
                "title": c.get("original_title", c.get("original_name")),
                "year": int((c.get("release_date") or c.get("first_air_date") or "0")[:4]),
                "media_type": media_type,
                "poster_path": c.get("poster_path"),
                "backdrop_path": c.get("backdrop_path"),
                "reasons": ["TITLE_YEAR_CANDIDATE_ONLY"],
            }
            for c in candidates[:10]
        ]

    def details(self, provider_id: str, media_type: str) -> dict[str, Any]:
        if not provider_id.isdecimal():
            raise GateError("INVALID_PROVIDER_ID")
        route = "tv" if media_type == "show" else "movie"
        data = self.request(
            "GET", route + "/" + provider_id, params={"append_to_response": "external_ids"}
        ).json()
        date = data.get("release_date") or data.get("first_air_date") or ""
        collection = data.get("belongs_to_collection") or {}
        return {
            "provider_id": str(data["id"]),
            "title": data.get("original_title", data.get("original_name")),
            "year": int(date[:4]) if date[:4].isdecimal() else None,
            "imdb_id": data.get("imdb_id") or data.get("external_ids", {}).get("imdb_id"),
            "collection_id": str(collection["id"]) if collection.get("id") else None,
            "collection_name": collection.get("name"),
            "provenance": "TMDb-detail",
            "poster_path": data.get("poster_path"),
            "backdrop_path": data.get("backdrop_path"),
        }

    def artwork(self, image_path: str) -> bytes:
        if not re.fullmatch(r"/[a-zA-Z0-9]+\.(jpg|png)", image_path):
            raise GateError("INVALID_ARTWORK_PATH")
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
            try:
                response = client.get("https://image.tmdb.org/t/p/w780" + image_path)
                if response.status_code != 200 or len(response.content) > 10 * 1024**2:
                    raise GateError("ARTWORK_UNAVAILABLE", "BlockedExternalDependency")
                return response.content
            except httpx.HTTPError:
                raise GateError("ARTWORK_UNAVAILABLE", "BlockedExternalDependency") from None


def probe(path: Path, executable: str = "ffprobe") -> dict[str, Any]:
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell; executable is operator-configured
            [executable, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_output=True,
            timeout=120,
            check=False,
            shell=False,
        )  # noqa: S603
        if result.returncode or len(result.stdout) > 8 * 1024**2:
            raise GateError("MEDIA_PROBE_FAILED")
        data: dict[str, Any] = json.loads(result.stdout)
        if not any(s.get("codec_type") == "video" for s in data.get("streams", [])):
            raise GateError("NO_VIDEO_STREAM")
        # Format filename and arbitrary tags can contain private data; retained only in protected DB.
        return data
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise GateError("MEDIA_PROBE_FAILED") from None
