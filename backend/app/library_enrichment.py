"""Exact metadata sidecar proposals; unknown/manual files are never overwritten."""

import hashlib
from pathlib import PurePosixPath
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import persistence as p
from app.domain import GateError
from app.storage import atomic_sidecar, contained, sha256


def proposals(
    worker: Any, asset: dict[str, Any], identity: dict[str, Any], target: str
) -> list[dict[str, Any]]:
    root = Element("episodedetails" if identity["media_type"] == "show" else "movie")
    for key in ["title", "year"]:
        SubElement(root, key).text = str(identity[key])
    for key, tag in [
        ("provider_id", "tmdbid"),
        ("imdb_id", "imdbid"),
        ("collection_id", "collectionnumber"),
        ("collection_name", "set"),
    ]:
        if identity.get(key):
            SubElement(root, tag).text = str(identity[key])
    if identity["media_type"] == "show":
        SubElement(root, "season").text = str(identity["season"])
        SubElement(root, "episode").text = str(identity["episodes"][0])
    path = PurePosixPath(target)
    rel = (
        str(path.with_suffix(".nfo"))
        if identity["media_type"] == "show"
        else str(path.parent / "movie.nfo")
    )
    content = tostring(root, encoding="utf-8", xml_declaration=True)
    values = [(rel, content, "NFO")]
    for key, filename in [("poster_path", "poster.jpg"), ("backdrop_path", "backdrop.jpg")]:
        if identity.get(key):
            values.append(
                (str(path.parent / filename), worker.tmdb.artwork(identity[key]), "ARTWORK")
            )
    result = []
    for rel, content, kind in values:
        existing = contained(worker.cfg.nas_root, rel)
        owned = worker.db.rows(
            select(p.sidecars).where(p.sidecars.c.root == "nas", p.sidecars.c.relative_path == rel)
        )
        expected = owned[0]["sha256"] if owned else None
        if existing.exists() and (not owned or owned[0]["locked"] or sha256(existing) != expected):
            raise GateError("SIDECAR_OWNERSHIP_REVIEW")
        result.append(
            {
                "target": rel,
                "expected": expected,
                "sha256": hashlib.sha256(content).hexdigest(),
                "content_hex": content.hex(),
                "kind": kind,
            }
        )
    return result


def apply(
    worker: Any,
    task: dict[str, Any],
    plan: dict[str, Any],
    asset: dict[str, Any],
    proposals: list[dict[str, Any]],
    resources: list[str],
) -> None:
    for proposal in proposals:
        op, _ = worker.db.intent(task, plan, "LIBRARY_SIDECAR", proposal["target"], proposal)
        path = contained(worker.cfg.nas_root, proposal["target"])
        owned = worker.db.rows(
            select(p.sidecars).where(
                p.sidecars.c.root == "nas", p.sidecars.c.relative_path == proposal["target"]
            )
        )
        if op["status"] == "VERIFIED":
            if not path.is_file() or sha256(path) != proposal["sha256"]:
                raise GateError("SIDECAR_CONCURRENT_EDIT", "RecoveryRequired")
            continue
        worker.db.op_status(op, "COMMAND_REQUESTED")
        if (
            path.is_file()
            and sha256(path) == proposal["sha256"]
            and (owned or op["status"] == "COMMAND_REQUESTED")
        ):
            pass
        else:
            atomic_sidecar(
                worker.cfg.nas_root,
                proposal["target"],
                bytes.fromhex(proposal["content_hex"]),
                proposal["expected"],
                lambda: worker.fence(task, resources),
                ".vimag-sidecar-backups/" + op["id"] + "/sidecar",
            )
        with worker.db.transaction() as conn:
            conn.execute(
                pg_insert(p.sidecars)
                .values(
                    root="nas",
                    relative_path=proposal["target"],
                    sha256=proposal["sha256"],
                    data={
                        "asset_id": asset["id"],
                        "exclusive": proposal["kind"] != "ARTWORK"
                        and asset["data"].get("identity", {}).get("media_type") == "show",
                        "op_id": op["id"],
                    },
                )
                .on_conflict_do_update(
                    index_elements=["root", "relative_path"], set_={"sha256": proposal["sha256"]}
                )
            )
        worker.db.op_status(op, "VERIFIED")
