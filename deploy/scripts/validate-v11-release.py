"""Validate immutable ViMag v1.1 publication evidence; never accept RC1 images."""
import json
import re
import sys
from pathlib import Path


def validate(manifest: dict) -> None:
    if manifest.get("version") != "1.1.0":
        raise ValueError("Wrong stable v1.1 version")
    if not re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("commit", ""))):
        raise ValueError("Invalid source commit")
    for name, repository in {"web": "vesovasilev/media-manager-web", "backend": "vesovasilev/media-manager-backend", "postgres": "postgres"}.items():
        value = str(manifest.get("images", {}).get(name, ""))
        if not re.fullmatch(re.escape(repository) + r"@sha256:[0-9a-f]{64}", value):
            raise ValueError(f"Missing immutable digest for {name}")
    if manifest.get("compatible_schemas") != ["0002"]:
        raise ValueError("Expected exact v1.1 schema 0002")
    if not manifest.get("platforms"):
        raise ValueError("No platform evidence")


if __name__ == "__main__":
    validate(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    print("V11_RELEASE_MANIFEST_VALID")
