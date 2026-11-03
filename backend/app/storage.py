"""Filesystem primitives. All effects require the caller's durable journal and fence."""

import hashlib
import json
import os
import shutil
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.domain import GateError, relative


def sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise GateError("UNSAFE_FILE")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def contained(root: Path, rel: str, *, existing: bool = False) -> Path:
    relative(rel)
    if root.is_symlink() or not root.is_dir():
        raise GateError("STORAGE_UNAVAILABLE", "BlockedExternalDependency")
    resolved_root = root.resolve(strict=True)
    current = root
    for part in rel.split("/"):
        current = current / part
        if current.is_symlink() or (current.exists() and stat.S_ISLNK(current.lstat().st_mode)):
            raise GateError("SYMLINK_BLOCKED")
    resolved = current.resolve(strict=existing)
    if not resolved.is_relative_to(resolved_root) or resolved == resolved_root:
        raise GateError("PATH_ESCAPE")
    return current


def collision(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise GateError("DESTINATION_COLLISION")
    parent = path.parent
    if parent.exists() and any(p.name.casefold() == path.name.casefold() for p in parent.iterdir()):
        raise GateError("CASE_COLLISION")


def mount_health(
    root: Path,
    expected_source: str,
    *,
    production: bool,
    required_bytes: int = 0,
    min_free: int = 0,
    min_percent: float = 0,
) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise GateError("NAS_OFFLINE", "BlockedExternalDependency")
    if production:
        if not expected_source or not Path("/proc/self/mountinfo").is_file():
            raise GateError("NAS_MOUNT_UNVERIFIED", "BlockedExternalDependency")
        valid = False
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            left, right = line.split(" - ", 1)
            fields, fs = left.split(), right.split()
            if fields[4] == str(root) and fs[0] == "cifs" and fs[1] == expected_source:
                valid = True
        if not valid:
            raise GateError("NAS_MOUNT_IDENTITY_MISMATCH", "BlockedExternalDependency")
    usage = shutil.disk_usage(root)
    if usage.free - required_bytes < max(min_free, int(usage.total * min_percent / 100)):
        raise GateError("INSUFFICIENT_SPACE", "BlockedExternalDependency")
    return {"free_bytes": usage.free, "total_bytes": usage.total, "mount_verified": True}


def hardlink_scratch(root: Path) -> dict[str, Any]:
    """Write-through proof only on random, self-owned scratch bytes. Never tests media writes."""
    with tempfile.TemporaryDirectory(prefix=".vimag-link-proof-", dir=root) as tmp:
        source, target = Path(tmp) / "source", Path(tmp) / "target"
        source.write_bytes(b"vimag-scratch-a")
        try:
            os.link(source, target)
            source.write_bytes(b"vimag-scratch-b")
            if target.read_bytes() != b"vimag-scratch-b":
                raise GateError("HARDLINK_ALIAS_UNVERIFIED", "StrategyUnavailable")
            return {"shared_write": True, "inode_trusted": False}
        except OSError:
            raise GateError("HARDLINK_UNAVAILABLE", "StrategyUnavailable") from None


def hardlink(
    root: Path, source_rel: str, dest_rel: str, fingerprint: str, fence: Callable[[], None]
) -> None:
    source, target = contained(root, source_rel, existing=True), contained(root, dest_rel)
    if sha256(source) != fingerprint:
        raise GateError("SOURCE_CHANGED", "RecoveryRequired")
    collision(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    contained(root, dest_rel)
    fence()
    try:
        os.link(source, target)
    except OSError:
        raise GateError("HARDLINK_UNAVAILABLE", "StrategyUnavailable") from None
    if sha256(target) != fingerprint:
        raise GateError("HARDLINK_INTEGRITY_FAILED", "RecoveryRequired")


def atomic_sidecar(
    root: Path,
    rel: str,
    content: bytes,
    expected: str | None,
    fence: Callable[[], None],
    backup_rel: str,
    before_replace: Callable[[], None] | None = None,
) -> str:
    path = contained(root, rel)
    if expected is None:
        collision(path)
    elif not path.is_file() or sha256(path) != expected:
        raise GateError("SIDECAR_CONFLICT")
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = contained(root, backup_rel)
    if expected is not None:
        if backup.exists():
            if sha256(backup) != expected:
                raise GateError("SIDECAR_BACKUP_CONFLICT")
        else:
            collision(backup)
            backup.parent.mkdir(parents=True, exist_ok=True)
            with path.open("rb") as source, backup.open("xb") as dest:
                shutil.copyfileobj(source, dest)
                dest.flush()
                os.fsync(dest.fileno())
        if sha256(backup) != expected:
            raise GateError("SIDECAR_BACKUP_CONFLICT")
    fd, temp_name = tempfile.mkstemp(prefix=".vimag-", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as dest:
            dest.write(content)
            dest.flush()
            os.fsync(dest.fileno())
        if before_replace:
            before_replace()
        contained(root, rel)
        if expected is not None and sha256(path) != expected:
            raise GateError("SIDECAR_CONCURRENT_EDIT")
        fence()
        if expected is None:
            # link is an atomic create-if-absent; os.replace would overwrite unknown files.
            os.link(temp, path)
        else:
            os.replace(temp, path)
        result = sha256(path)
        if result != hashlib.sha256(content).hexdigest():
            raise GateError("SIDECAR_READBACK_FAILED", "RecoveryRequired")
        return result
    finally:
        if temp.exists():
            temp.unlink()  # Self-owned temporary sidecar, never a media asset.


def reversible_move(
    root: Path, source_rel: str, dest_rel: str, fingerprint: str, fence: Callable[[], None]
) -> None:
    source, target = contained(root, source_rel, existing=True), contained(root, dest_rel)
    if sha256(source) != fingerprint:
        raise GateError("ASSET_CHANGED", "ReplanRequired")
    collision(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fence()
    # Same-share link/unlink preserves bytes and gives create-if-absent semantics.
    os.link(source, target)
    if sha256(target) != fingerprint or sha256(source) != fingerprint:
        raise GateError("MOVE_READBACK_FAILED", "RecoveryRequired")
    fence()
    source.unlink()


def cleanup_staging(
    staging: Path,
    rel: str,
    fingerprint: str,
    *,
    destination: Path,
    dependencies: list[dict[str, Any]],
    proof: dict[str, Any],
    fence: Callable[[], None],
) -> None:
    required = {
        "owned_staging",
        "nas_integrity",
        "mapping_verified",
        "rechecked",
        "seeding_capable",
        "dependency_scan_complete",
    }
    if dependencies or not all(proof.get(k) is True for k in required):
        raise GateError("CLEANUP_BLOCKED")
    source = contained(staging, rel, existing=True)
    if (
        not destination.is_file()
        or destination.resolve().is_relative_to(staging.resolve())
        or sha256(destination) != fingerprint
        or sha256(source) != fingerprint
    ):
        raise GateError("CLEANUP_PROOF_INVALID")
    fence()
    source.unlink()  # Exactly one independently proven orphan staging file; no recursive removal.


def read_nfo(path: Path) -> dict[str, Any]:
    from xml.etree import ElementTree

    from defusedxml.ElementTree import fromstring

    if path.stat().st_size > 2 * 1024**2:
        raise GateError("NFO_TOO_LARGE")
    raw = path.read_bytes()
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise GateError("NFO_UNSAFE_XML")
    try:
        tree = fromstring(raw)
        return {
            "title": tree.findtext("originaltitle") or tree.findtext("title"),
            "year": tree.findtext("year"),
            "provider_id": tree.findtext("tmdbid"),
        }
    except ElementTree.ParseError:
        return {"review": "INVALID_NFO"}


def manifest_bytes(data: dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2).encode()
