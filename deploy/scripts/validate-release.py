"""Validate release inputs and immutable digest manifest for pre-1.0 ViMag."""
import argparse
import json
import re
import tomllib
from pathlib import Path

REPOS = {"web": "vesovasilev/media-manager-web", "backend": "vesovasilev/media-manager-backend", "postgres": "postgres"}

def validate_source(version):
    if not re.fullmatch(r"0\.[0-9]+\.[0-9]+", version):
        raise ValueError("Version must be 0.MINOR.PATCH")
    pkg = json.loads(Path("frontend/package.json").read_text())
    lock = json.loads(Path("frontend/package-lock.json").read_text())
    with Path("backend/pyproject.toml").open("rb") as f:
        backend = tomllib.load(f)
    versions = [pkg["version"], lock["version"], lock["packages"][""]["version"], backend["project"]["version"]]
    if versions != [version] * 4:
        raise ValueError("Source package versions disagree with requested release")

def validate_manifest(path, version, commit):
    data = json.loads(Path(path).read_text())
    if data.get("version") != version or data.get("commit") != commit:
        raise ValueError("Manifest version/commit mismatch")
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Invalid source commit")
    if data.get("compatible_schemas") != ["0002"]:
        raise ValueError("Unexpected DB schema")
    if sorted(data.get("platforms", [])) != ["linux/amd64", "linux/arm64"]:
        raise ValueError("Missing expected architectures")
    for name, repo in REPOS.items():
        if not re.fullmatch(re.escape(repo) + r"@sha256:[a-f0-9]{64}", data.get("images", {}).get(name, "")):
            raise ValueError("Missing digest for " + name)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--manifest")
    parser.add_argument("--commit")
    args = parser.parse_args()
    validate_source(args.version)
    if args.manifest:
        if not args.commit:
            parser.error("--commit required with --manifest")
        validate_manifest(args.manifest, args.version, args.commit)
    print("RELEASE_VALID")
