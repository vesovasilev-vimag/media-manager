"""Deterministic synthetic providers, selectable only outside production."""

import copy
import shutil
from pathlib import Path
from typing import Any

from app.domain import GateError, Torrent
from app.settings import Settings


class EmulatedQbt:
    def __init__(self, cfg: Settings):
        if cfg.environment == "production":
            raise ValueError("Emulators forbidden in production")
        self.cfg = cfg
        self.torrents: dict[str, Torrent] = {}
        self.commands: list[tuple[str, str, dict[str, Any]]] = []
        self.pending: dict[str, tuple[str, dict[str, Any], int]] = {}
        self.fail_recheck = False

    def all(self) -> list[Torrent]:
        return [self.torrent(h) for h in self.torrents]

    def torrent(self, info_hash: str) -> Torrent:
        if info_hash not in self.torrents:
            raise GateError("TORRENT_INSTANCE_MISSING", "RecoveryRequired")
        t = self.torrents[info_hash]
        if info_hash in self.pending:
            kind, data, count = self.pending[info_hash]
            if count == 0:
                self.pending[info_hash] = (kind, data, 1)
            else:
                if kind == "setLocation":
                    source = self.path(t.save_path)
                    dest = self.path(data["location"])
                    dest.mkdir(parents=True, exist_ok=True)
                    for f in t.files:
                        target = dest / f["name"]
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if target.exists():
                            raise GateError("DESTINATION_COLLISION")
                        shutil.move(str(source / f["name"]), target)
                    t.save_path = data["location"]
                    t.content_path = data["location"] + "/" + t.files[0]["name"]
                if kind == "recheck" and self.fail_recheck:
                    t.progress, t.amount_left = 0.5, 1
                t.state = (
                    "stoppedUP"
                    if t.policy.get("intentional_pause")
                    else "queuedUP"
                    if t.policy.get("queued")
                    else "stalledUP"
                )
                del self.pending[info_hash]
        return copy.deepcopy(t)

    def path(self, qpath: str) -> Path:
        for prefix, root in [
            ("/downloads/complete", self.cfg.staging_root),
            ("/library", self.cfg.nas_root / "Library"),
            ("/torrent-store", self.cfg.nas_root / ".vimag-torrent-store"),
        ]:
            if qpath == prefix or qpath.startswith(prefix + "/"):
                return root / qpath[len(prefix) :].lstrip("/")
        raise GateError("UNMAPPED_QBT_PATH")

    def get(self, endpoint: str, **params: Any) -> Any:
        if endpoint == "torrents/pieceStates":
            return [0 if self.fail_recheck else 2]
        if endpoint == "app/preferences":
            return {"use_category_paths_in_manual_mode": False, "temp_path_enabled": False}
        if endpoint == "torrents/categories":
            return {
                c: {"savePath": "/library/" + c.title()}
                for c in ["movies", "series", "animations", "documentaries", "concerts"]
            }
        raise GateError("EMULATOR_UNSUPPORTED_READ")

    def command(self, endpoint: str, info_hash: str, **payload: Any) -> None:
        self.commands.append((endpoint, info_hash, payload))
        t = self.torrents[info_hash]
        if endpoint == "renameFile":
            source = self.path(t.save_path) / payload["oldPath"]
            target = self.path(t.save_path) / payload["newPath"]
            if target.exists():
                raise GateError("DESTINATION_COLLISION")
            source.rename(target)
            next(f for f in t.files if f["name"] == payload["oldPath"])["name"] = payload["newPath"]
        elif endpoint in {"setLocation", "recheck"}:
            self.pending[info_hash] = (endpoint, payload, 0)
            t.state = "moving" if endpoint == "setLocation" else "checkingUP"
        elif endpoint in {"stop", "start"}:
            t.state = "stoppedUP" if endpoint == "stop" else "stalledUP"
            t.policy["intentional_pause"] = endpoint == "stop"
        else:
            raise GateError("FORBIDDEN_QBT_COMMAND")


class EmulatedJellyfin:
    def health(self) -> bool:
        if self.fail_auth:
            raise GateError("JELLYFIN_AUTH_REQUIRED", "BlockedExternalDependency")
        return True

    def __init__(self) -> None:
        self.accepted = False
        self.recognize = True
        self.missing_titles: set[str] = set()
        self.refresh_count = 0
        self.fail_auth = False

    def refresh(self) -> None:
        if self.fail_auth:
            raise GateError("JELLYFIN_AUTH_REQUIRED", "BlockedExternalDependency")
        self.accepted = True
        self.refresh_count += 1

    def recognized(self, expected: dict[str, Any]) -> dict[str, Any] | None:
        if self.fail_auth:
            raise GateError("JELLYFIN_AUTH_REQUIRED", "BlockedExternalDependency")
        if self.accepted and self.recognize and expected["title"] not in self.missing_titles:
            return {
                "item_id": "synthetic-" + expected["title"],
                "path_verified": True,
                "streams_verified": True,
            }
        return None


class EmulatedTMDb:
    def search(self, title: str, media_type: str, year: int | None) -> list[dict[str, Any]]:
        return [
            {
                "id": "1",
                "title": title,
                "title_language": "en-US",
                "english_title_verified": True,
                "year": year or 2026,
                "media_type": media_type,
                "reasons": ["SYNTHETIC_CANDIDATE"],
                "poster_path": "/synthetic.jpg",
            }
        ]

    def artwork(self, image_path: str) -> bytes:
        # Minimal JPEG fixture only; never selected in production.
        return b"\xff\xd8synthetic-artwork\xff\xd9"


def create_emulators(cfg: Settings) -> tuple[EmulatedQbt, EmulatedJellyfin, EmulatedTMDb]:
    return EmulatedQbt(cfg), EmulatedJellyfin(), EmulatedTMDb()
