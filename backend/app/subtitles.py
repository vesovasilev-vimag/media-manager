"""Subtitle matching and non-destructive timing proposals."""

import re
from typing import Any

from app.adapters import Remote
from app.domain import GateError, digest
from app.settings import Settings


class OpenSubtitles(Remote):
    def __init__(self, config: Settings):
        super().__init__(
            "SUBTITLES",
            "https://api.opensubtitles.com/api/v1/",
            {
                "Api-Key": config.secret(config.subtitle_api_key_file).get_secret_value(),
                "User-Agent": "ViMagMediaManager v1.0.0-rc.1",
            },
        )

    def search(
        self,
        provider_id: str,
        media_type: str,
        season: int | None = None,
        episode: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "tmdb_id": provider_id,
            "languages": "bg",
            "type": "episode" if media_type == "show" else "movie",
        }
        if season is not None:
            params.update(season_number=season, episode_number=episode)
        data = self.request("GET", "subtitles", params=params).json()
        return [
            {
                "provider": "OpenSubtitles",
                "id": str(row["id"]),
                "status": "CandidateFound",
                "attributes": row["attributes"],
                "reasons": ["TIMING_REQUIRES_VERIFICATION"],
            }
            for row in data.get("data", [])[:20]
        ]

    def download(self, file_id: int) -> bytes:
        result = self.request(
            "POST", "download", json={"file_id": file_id, "sub_format": "srt"}
        ).json()
        from urllib.parse import urlsplit

        import httpx

        url = result.get("link", "")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith(".opensubtitles.com")
        ):
            raise GateError("SUBTITLE_DOWNLOAD_HOST_REJECTED")
        try:
            with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
                response = client.get(url)
                if response.status_code != 200 or len(response.content) > 5 * 1024**2:
                    raise GateError("SUBTITLE_DOWNLOAD_FAILED")
                return response.content
        except httpx.HTTPError:
            raise GateError("SUBTITLE_DOWNLOAD_FAILED", "BlockedExternalDependency") from None


TIMING = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def cues(content: bytes) -> list[tuple[float, float]]:
    try:
        value = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise GateError("SUBTITLE_ENCODING_REVIEW") from None
    if len(content) > 5 * 1024**2 or "\x00" in value:
        raise GateError("SUBTITLE_INVALID")
    result: list[tuple[float, float]] = []
    for match in TIMING.finditer(value):
        nums = list(map(int, match.groups()))
        start, end = (
            nums[0] * 3600 + nums[1] * 60 + nums[2] + nums[3] / 1000,
            nums[4] * 3600 + nums[5] * 60 + nums[6] + nums[7] / 1000,
        )
        if end <= start or (result and start < result[-1][0]):
            raise GateError("SUBTITLE_INVALID_TIMING")
        result.append((start, end))
    if not result:
        raise GateError("SUBTITLE_NO_CUES")
    return result


def evaluate(
    candidate: dict[str, Any],
    media: dict[str, Any],
    content: bytes,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parsed = cues(content)
    reasons = []
    if candidate.get("edition") != media.get("edition"):
        reasons.append("EDITION_MISMATCH")
    if candidate.get("fingerprint") != media.get("fingerprint"):
        reasons.append("VIDEO_FINGERPRINT_UNBOUND")
    if parsed[-1][1] > media["duration"] + 1:
        reasons.append("TIMING_OUT_OF_BOUNDS")
    if candidate.get("fps") and media.get("fps") and abs(candidate["fps"] - media["fps"]) > 0.01:
        reasons.append("FPS_DRIFT")
    if candidate.get("offset", 0) or candidate.get("drift", 0):
        reasons.append("TIMING_DRIFT")
    state = "Mismatch" if reasons else "NeedsReview"
    if not reasons and verification and verification.get("actor") and verification.get("time"):
        if (
            verification.get("video_fingerprint") == media["fingerprint"]
            and verification.get("subtitle_sha256") == digest(content.decode("utf-8-sig"))
            and verification.get("timing_confirmed") is True
        ):
            state = "Synchronized"
    return {
        "status": state,
        "reasons": reasons or ["HUMAN_TIMING_CHECK_REQUIRED"],
        "cues": len(parsed),
    }


def sync_proposal(content: bytes, offset: float, scale: float) -> bytes:
    if not -300 <= offset <= 300 or not 0.9 <= scale <= 1.1:
        raise GateError("SYNC_OUT_OF_RANGE")
    cues(content)

    def replace(match: re.Match[str]) -> str:
        nums = list(map(int, match.groups()))
        values = []
        for ix in (0, 4):
            ms = round(
                (
                    (nums[ix] * 3600 + nums[ix + 1] * 60 + nums[ix + 2] + nums[ix + 3] / 1000)
                    * scale
                    + offset
                )
                * 1000
            )
            if ms < 0:
                raise GateError("NEGATIVE_CUE")
            h, rem = divmod(ms, 3600000)
            m, rem = divmod(rem, 60000)
            s, mill = divmod(rem, 1000)
            values.append(f"{h:02}:{m:02}:{s:02},{mill:03}")
        return " --> ".join(values)

    return TIMING.sub(replace, content.decode("utf-8-sig")).encode("utf-8")
