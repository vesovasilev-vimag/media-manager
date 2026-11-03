"""Generate original, harmless media and one trackerless multi-file torrent.

Only call on disposable fixtures or the explicitly authorized postdeployment scratch
path. Never commits generated media or metainfo to Git. No existing files replaced.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def bencode(value: Any) -> bytes:
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, str):
        return bencode(value.encode())
    if isinstance(value, list):
        return b"l" + b"".join(bencode(v) for v in value) + b"e"
    if isinstance(value, dict):
        return (
            b"d"
            + b"".join(bencode(k) + bencode(value[k]) for k in sorted(value))
            + b"e"
        )
    raise TypeError("Unsupported bencode type")


def generate(root: Path) -> dict[str, Any]:
    directory = root / "vimag-rc1-original-fixture"
    directory.mkdir(parents=True, exist_ok=False)
    files = []
    for episode in (1, 2):
        name = f"ViMag Synthetic Fixture S01E{episode:02}.mkv"
        path = directory / name
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=teal:s=320x240:r=24:d=2",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={440 + episode * 100}:duration=2",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-shortest",
                str(path),
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )  # noqa: S603,S607 - fixed synthetic lavfi inputs
        files.append({"length": path.stat().st_size, "path": [name]})
    payload = b"".join((directory / f["path"][0]).read_bytes() for f in files)
    length = 16384
    pieces = b"".join(
        hashlib.sha1(payload[i : i + length], usedforsecurity=False).digest()
        for i in range(0, len(payload), length)
    )
    info = {
        "name": directory.name,
        "piece length": length,
        "pieces": pieces,
        "files": files,
    }
    info_hash = hashlib.sha1(bencode(info), usedforsecurity=False).hexdigest()
    metainfo = {
        "info": info,
        "comment": "Original ViMag synthetic fixture: generated color and sine waves, no third-party media",
        "created by": "ViMag RC1",
    }
    torrent = root / "vimag-rc1-original-fixture.torrent"
    with torrent.open("xb") as dest:
        dest.write(bencode(metainfo))
    return {
        "info_hash": info_hash,
        "torrent": str(torrent),
        "files": 2,
        "trackerless": True,
        "provider_id": None,
        "rights": "Original generated color/sine media; no external copyrighted source",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("scratch", type=Path)
    args = parser.parse_args()
    print(json.dumps(generate(args.scratch), indent=2))
