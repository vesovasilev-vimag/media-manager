"""Validate actual publication evidence; placeholders and mutable tags are rejected."""
import json
import re
import sys
from pathlib import Path


def validate(manifest: dict) -> None:
    if manifest.get("version") != "1.0.0-rc.1" or not re.fullmatch(r"[0-9a-f]{40}", manifest.get("commit", "")):
        raise ValueError("Missing immutable source identity")
    expected = {"web": "vesovasilev/media-manager-web", "backend": "vesovasilev/media-manager-backend", "postgres": "postgres"}
    for name, repository in expected.items():
        image = manifest.get("images", {}).get(name, "")
        if not re.fullmatch(re.escape(repository) + r"@sha256:[0-9a-f]{64}", image):
            raise ValueError("Missing published digest: " + name)
    if manifest.get("compatible_schemas") != ["0001"]:
        raise ValueError("Unreviewed schema compatibility")
    if not manifest.get("platforms"):
        raise ValueError("Missing architecture evidence")


if __name__ == "__main__":
    validate(json.loads(Path(sys.argv[1]).read_text()))
    print("RELEASE_MANIFEST_VALID")
