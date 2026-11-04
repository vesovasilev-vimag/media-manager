"""Pure policy. Recommendations never authorize mutations."""

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Any

CATEGORIES = {
    "movies": "Movies",
    "series": "Series",
    "animations": "Animations",
    "documentaries": "Documentaries",
    "concerts": "Concerts",
}
STEPS = [
    "Изтегляне",
    "Идентификация и анализ",
    "Сравнение с библиотеката",
    "Организация и обогатяване",
    "Български субтитри",
    "Публикуване в Jellyfin",
    "Проверка на seeding",
]
TERMINAL = {"Completed", "CompletedWithWarnings"}
BUSY = {
    "moving",
    "checkingDL",
    "checkingUP",
    "checkingResumeData",
    "allocating",
    "metaDL",
    "error",
    "missingFiles",
    "unknown",
}


class GateError(Exception):
    def __init__(self, code: str, state: str = "NeedsReview"):
        self.code = code
        self.state = state
        super().__init__(code)


def safe_note(value: str) -> str:
    value = re.sub(r"https?://\S+", "[URL REDACTED]", value)
    return re.sub(
        r"(?i)\b(bearer|api[_-]?key|password|passkey|authorization|cookie|token)\s*[:=]?\s*[^\s,;]+",
        r"\1 [REDACTED]",
        value,
    )[:1000]


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def relative(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    parts = value.split("/")
    if (
        not value
        or len(value) > 900
        or PurePosixPath(value).is_absolute()
        or any(
            p in {"", ".", ".."}
            or len(p.encode()) > 240
            or p.endswith((" ", "."))
            or re.search(r'[\x00-\x1f\\<>:"|?*]', p)
            or re.match(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", p)
            for p in parts
        )
    ):
        raise GateError("UNSAFE_PATH")
    return value


def component(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = re.sub(r'[\x00-\x1f\\/<>:"|?*]', " - ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return relative(value)


@dataclass
class Torrent:
    info_hash: str
    added_on: int
    category: str
    save_path: str
    content_path: str
    state: str
    progress: float
    amount_left: int
    auto_tmm: bool
    files: list[dict[str, Any]]
    policy: dict[str, Any] = field(default_factory=dict)

    def complete(self) -> bool:
        return (
            self.progress == 1
            and self.amount_left == 0
            and self.state not in BUSY
            and bool(self.files)
            and all(f.get("progress", 0) == 1 for f in self.files)
        )

    def stable(self) -> dict[str, Any]:
        return {
            "hash": self.info_hash,
            "added_on": self.added_on,
            "category": self.category,
            "save_path": self.save_path.rstrip("/"),
            "auto_tmm": self.auto_tmm,
            "files": [
                {k: f[k] for k in ("index", "name", "size", "priority") if k in f}
                for f in self.files
            ],
            "policy": self.policy,
        }


def eligible(t: Torrent, *, baseline: bool, seen_before: bool, cutover: bool) -> bool:
    return (
        not baseline
        and not seen_before
        and cutover
        and t.complete()
        and t.category in CATEGORIES
        and not t.auto_tmm
        and t.save_path.rstrip("/") == "/downloads/complete"
        and all(relative(f["name"]) for f in t.files)
    )


@dataclass
class Identity:
    title: str
    year: int
    media_type: str
    provider_id: str | None = None
    edition: str = "Theatrical"
    season: int | None = None
    episodes: list[int] = field(default_factory=list)
    part: int | None = None
    artist: str | None = None
    confirmed: bool = False
    original_title: str | None = None
    original_name: str | None = None
    title_language: str | None = None
    english_title_verified: bool = False
    title_provenance: str | None = None


def name_for(category: str, i: Identity, quality: str, bg: str, extension: str) -> str:
    if not i.confirmed or not 1880 <= i.year <= 2200 or not i.title.strip():
        raise GateError("IDENTITY_UNCONFIRMED")
    if category not in CATEGORIES or i.media_type not in {"movie", "show", "concert"}:
        raise GateError("CATEGORY_CONFLICT")
    if (
        (category == "movies" and i.media_type != "movie")
        or (category == "series" and i.media_type != "show")
        or (category == "concerts" and i.media_type != "concert")
    ):
        raise GateError("CATEGORY_CONFLICT")
    if extension not in {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts"}:
        raise GateError("UNSUPPORTED_MEDIA")
    root = CATEGORIES[category]
    if category in {"animations", "documentaries"}:
        root += "/Series" if i.media_type == "show" else "/Movies"
    title = component(i.title)
    folder = f"{title} ({i.year})"
    if i.provider_id:
        if not i.provider_id.isdecimal():
            raise GateError("INVALID_PROVIDER_ID")
        folder += f" [tmdbid-{i.provider_id}]"
    label = component(quality) + (
        " BG" if bg in {"BG_VERIFIED", "BG_TAGGED", "BG_DETECTED"} else ""
    )
    if i.edition:
        label += " - " + component(i.edition)
    if i.media_type == "show":
        if i.season is None or not 0 <= i.season <= 999 or not i.episodes:
            raise GateError("EPISODE_MAPPING_REQUIRED")
        if sorted(set(i.episodes)) != i.episodes or any(e < 1 or e > 999 for e in i.episodes):
            raise GateError("INVALID_EPISODES")
        ep = f"S{i.season:02}E{i.episodes[0]:02}"
        if len(i.episodes) > 1:
            if i.episodes != list(range(i.episodes[0], i.episodes[-1] + 1)):
                raise GateError("NONCONTIGUOUS_EPISODES")
            ep += f"-E{i.episodes[-1]:02}"
        filename = f"{title} {ep}"
        if i.part:
            filename += f" - part{i.part}"
        return relative(f"{root}/{folder}/Season {i.season:02}/{filename} - {label}{extension}")
    if i.media_type == "concert":
        if not i.artist:
            raise GateError("CONCERT_ARTIST_REQUIRED")
        folder = f"{component(i.artist)} - {title} ({i.year})"
    suffix = f" - part{i.part}" if i.part else ""
    return relative(f"{root}/{folder}/{folder} - {label}{suffix}{extension}")


def bg_state(probe: dict[str, Any], fingerprint: str, evidence: list[dict[str, Any]]) -> str:
    audio = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
    for stream in audio:
        key = digest(stream)
        if any(
            e.get("fingerprint") == fingerprint
            and e.get("stream_key") == key
            and e.get("source") in {"human-confirmed", "trusted-prior-verification"}
            and e.get("actor")
            and e.get("verified_at")
            and not e.get("revoked")
            for e in evidence
        ):
            return "BG_VERIFIED"
    if any(
        s.get("tags", {}).get("language", "").lower() in {"bul", "bg"}
        and re.search(r"\b(english|английски|eng)\b", s.get("tags", {}).get("title", "").lower())
        for s in audio
    ):
        return "AUDIO_UNKNOWN"
    if any(s.get("tags", {}).get("language", "").lower() in {"bul", "bg"} for s in audio):
        return "BG_TAGGED"
    if not audio or any(s.get("tags", {}).get("language", "und") == "und" for s in audio):
        return "AUDIO_UNKNOWN"
    return "NO_BG"


def technical_profile(analysis: dict[str, Any]) -> dict[str, Any]:
    streams = analysis.get("streams", [])
    video: dict[str, Any] = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    transfer = video.get("color_transfer")
    return {
        "source": "UNVERIFIED",
        "codec": video.get("codec_name"),
        "height": video.get("height"),
        "bitrate": video.get("bit_rate") or analysis.get("format", {}).get("bit_rate"),
        "hdr": "HDR"
        if transfer in {"smpte2084", "arib-std-b67"}
        else "SDR"
        if transfer == "bt709"
        else "UNVERIFIED",
        "channels": max((int(s.get("channels", 0)) for s in audio), default=0),
        "duration": analysis.get("format", {}).get("duration"),
        "frame_rate": video.get("avg_frame_rate") or video.get("r_frame_rate"),
    }


def compare(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    factors = {
        k: [old.get(k), new.get(k)]
        for k in (
            "edition",
            "integrity",
            "source",
            "codec",
            "height",
            "bitrate",
            "hdr",
            "channels",
            "duration",
            "frame_rate",
            "bg",
        )
    }
    decision, reasons = "NeedsReview", ["INSUFFICIENT_CALIBRATED_EVIDENCE"]
    if old.get("edition") != new.get("edition"):
        decision, reasons = "KeepBoth", ["DIFFERENT_EDITIONS"]
    elif old.get("identity_key") != new.get("identity_key"):
        reasons = ["IDENTITY_MISMATCH"]
    elif not old.get("integrity") or not new.get("integrity"):
        reasons = ["INTEGRITY_UNVERIFIED"]
    elif "AUDIO_UNKNOWN" in {old.get("bg"), new.get("bg")}:
        reasons = ["AUDIO_UNKNOWN"]
    elif old.get("bg") in {"BG_VERIFIED", "BG_TAGGED", "BG_DETECTED"}:
        if new.get("bg") not in {"BG_VERIFIED", "BG_TAGGED", "BG_DETECTED"}:
            decision = "KeepBoth" if new.get("material_improvement_verified") else "KeepBGPreferred"
            reasons = [
                "PRESERVE_VERIFIED_BG",
                "MATERIAL_IMPROVEMENT_VERIFIED"
                if new.get("material_improvement_verified")
                else "QUALITY_ADVANTAGE_UNPROVEN",
            ]
        elif new.get("material_improvement_verified"):
            decision, reasons = "PreferBetterBG", ["VERIFIED_BG", "MATERIAL_IMPROVEMENT_VERIFIED"]
    elif new.get("bg") in {"BG_VERIFIED", "BG_TAGGED", "BG_DETECTED"}:
        decision, reasons = "KeepBoth", ["NEW_VERIFIED_BG", "PRESERVE_EXISTING_VERSION"]
    return {"decision": decision, "reason_codes": reasons, "factors": factors, "policy": 1}


def match_identity(
    candidates: list[dict[str, Any]], explicit_id: str | None, media_type: str, year: int | None
) -> dict[str, Any] | None:
    matches = [
        c
        for c in candidates
        if str(c.get("id")) == explicit_id
        and c.get("media_type") == media_type
        and c.get("year") == year
    ]
    return matches[0] if len(matches) == 1 else None


def seeding_capable(
    t: Torrent, expected_path: str, policy: dict[str, Any], rechecked: bool
) -> bool:
    return (
        t.complete()
        and t.save_path.rstrip("/") == expected_path.rstrip("/")
        and not t.auto_tmm
        and t.policy == policy
        and rechecked
    )


def final_state(children: list[dict[str, Any]], nas: bool, seed: bool) -> str:
    if not nas or not seed:
        return "RecoveryRequired"
    if not children or any(not c.get("published") or not c.get("integrity") for c in children):
        return "PublishPending"
    if any(c.get("subtitle") not in {"Matched", "Synchronized", "Unavailable"} for c in children):
        return "NeedsReview"
    return (
        "CompletedWithWarnings"
        if any(c.get("subtitle") == "Unavailable" for c in children)
        else "Completed"
    )


def identity_dict(identity: Identity) -> dict[str, Any]:
    return asdict(identity)
