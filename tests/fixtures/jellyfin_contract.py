"""Executable real-server compatibility contract. Synthetic volume, no production endpoints."""

import json
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx


def prepare() -> None:
    root = Path("/fixtures")
    for title in ["Synthetic Alpha", "Synthetic Beta"]:
        folder = root / "Library/Movies/Fixture Collection" / f"{title} (2026)"
        folder.mkdir(parents=True, exist_ok=True)
        for edition in ["Theatrical", "Extended"]:
            video = folder / f"{title} (2026) - 1080p - {edition}.mkv"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=teal:s=320x240:r=24:d=2",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=2",
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(video),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )  # noqa: S603,S607
            video.with_suffix(".bg.srt").write_text(
                "1\n00:00:00,100 --> 00:00:01,000\nSynthetic primary\n",
                encoding="utf-8",
            )
            archive = root / ".vimag-subtitle-history" / title / edition
            archive.mkdir(parents=True, exist_ok=True)
            (archive / (video.stem + ".bg.ver-02.srt")).write_text(
                "1\n00:00:00,100 --> 00:00:01,000\nSynthetic history\n"
            )
        (folder / "movie.nfo").write_text(
            f"<movie><title>{title}</title><year>2026</year><set>Fixture Collection</set></movie>"
        )


def verify() -> None:
    # Endpoint is fixed to the disposable Compose service, never operator configuration.
    headers = {
        "Authorization": 'MediaBrowser Client="ViMag contract", Device="Synthetic", DeviceId="vimag-v11-fixture", Version="1.1"'
    }
    with httpx.Client(
        base_url="http://jellyfin:8096", headers=headers, timeout=15, trust_env=False
    ) as client:
        client.get("/Startup/User").raise_for_status()
        password = secrets.token_urlsafe(32)
        client.post(
            "/Startup/User", json={"Name": "synthetic-contract", "Password": password}
        ).raise_for_status()
        client.post(
            "/Startup/Configuration",
            json={
                "UICulture": "en-US",
                "MetadataCountryCode": "BG",
                "PreferredMetadataLanguage": "en",
            },
        ).raise_for_status()
        client.post(
            "/Library/VirtualFolders",
            params={
                "name": "Synthetic Movies",
                "collectionType": "movies",
                "paths": "/fixtures/Library/Movies",
            },
            json={
                "LibraryOptions": {
                    "EnableInternetProviders": False,
                    "EnableRealtimeMonitor": False,
                    "EnableChapterImageExtraction": False,
                    "TypeOptions": [
                        {
                            "Type": "Movie",
                            "MetadataFetchers": ["Nfo"],
                            "ImageFetchers": [],
                        }
                    ],
                    "LocalMetadataReaderOrder": ["Nfo"],
                }
            },
        ).raise_for_status()
        client.post("/Startup/Complete").raise_for_status()
        auth = client.post(
            "/Users/AuthenticateByName",
            json={"Username": "synthetic-contract", "Pw": password},
        )
        auth.raise_for_status()
        client.headers["X-Emby-Token"] = auth.json()["AccessToken"]
        client.post("/Library/Refresh").raise_for_status()
        deadline = time.monotonic() + 180
        media = []
        while time.monotonic() < deadline:
            response = client.get(
                "/Items",
                params={
                    "Recursive": "true",
                    "IncludeItemTypes": "Movie",
                    "Fields": "Path,MediaSources,MediaStreams",
                },
            )
            response.raise_for_status()
            media = response.json().get("Items", [])
            sources = [s for m in media for s in m.get("MediaSources", [])]
            if len(sources) == 4 and all(
                any(s.get("Type") == "Subtitle" for s in source.get("MediaStreams", []))
                for source in sources
            ):
                break
            time.sleep(1)
        sources = [s for m in media for s in m.get("MediaSources", [])]
        assert len(media) == 2, (
            "Collection folder must retain two films with grouped editions"
        )
        assert len(sources) == 4, (
            "Both editions of both synthetic works must be discoverable"
        )
        for source in sources:
            assert "/Fixture Collection/" in source["Path"]
            subs = [
                s for s in source.get("MediaStreams", []) if s.get("Type") == "Subtitle"
            ]
            assert len(subs) == 1, (
                "Historical variants must not be scanned as competing tracks"
            )
            assert subs[0].get("Language") in {"bg", "bul"}
            assert "ver-" not in subs[0].get("Path", "")
        result = {
            "result": "PASS",
            "server_version": "10.10.7",
            "movie_count": len(media),
            "edition_sources": len(sources),
            "bg_primary_per_source": 1,
            "archived_tracks_discovered": 0,
            "production_access": False,
        }
        Path("/results").mkdir(exist_ok=True)
        Path("/results/jellyfin-v11.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result))


if __name__ == "__main__":
    prepare() if sys.argv[1] == "prepare" else verify()
