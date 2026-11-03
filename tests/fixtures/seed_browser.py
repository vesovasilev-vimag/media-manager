"""Seed original media only into the explicit synthetic Docker-volume mount."""

import os
import shutil
import subprocess
from pathlib import Path

if os.environ.get("VIMAG_BROWSER_FIXTURES") != "original-synthetic-media-only":
    raise RuntimeError("Synthetic browser fixture intent is required")
root = Path("/nas-movies/Library")
if not Path("/nas-movies").is_mount():
    raise RuntimeError("Requires isolated synthetic NAS Docker volume")
for category in ["Movies", "Series", "Animations", "Documentaries", "Concerts"]:
    (root / category).mkdir(parents=True, exist_ok=True)
source = Path("/tmp/vimag-browser-original.mkv")
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
        "-metadata:s:a:0",
        "language=eng",
        "-shortest",
        str(source),
    ],
    check=True,
    capture_output=True,
    timeout=30,
)  # noqa: S603,S607
for ix in range(30):
    title = f"BrowserFixture {ix:02}"
    folder = root / "Movies" / (title + " (2026)")
    folder.mkdir(exist_ok=True)
    video = folder / (title + " (2026) - 240p.mkv")
    shutil.copyfile(source, video)
    (folder / "movie.nfo").write_text(
        f"<movie><title>{title}</title><year>2026</year></movie>"
    )
    video.with_suffix(".bg.srt").write_text(
        "1\n00:00:00,100 --> 00:00:01,000\nSynthetic subtitle\n"
    )
print("Seeded 30 original synthetic browser fixtures")
