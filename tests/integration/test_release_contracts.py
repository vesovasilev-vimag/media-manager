import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

import pytest
import yaml
from sqlalchemy import insert, select

from app import persistence as p
from app.domain import GateError
from app.storage import sha256
from conftest import login, ROOT, drive, onboard, torrent


def test_production_four_containers_worker_only_single_nas_bind() -> None:
    config = yaml.safe_load((ROOT / "deploy/compose.prod.yaml").read_text())
    assert set(config["services"]) == {"web", "api", "worker", "db"}
    for name, service in config["services"].items():
        assert "build" not in service and "ports" not in service
        if name in {"web", "api"}:
            assert "volumes" not in service
    volumes = config["services"]["worker"]["volumes"]
    assert len([v for v in volumes if v["source"] == "/mnt/nas/Movies"]) == 1
    assert all(v["bind"]["create_host_path"] is False for v in volumes)
    # Production writes are deliberately opt-in, never hardwired either way.
    # The private deployment environment must explicitly choose its run mode,
    # while the shipped example remains read-only until preflight.
    environment = config["services"]["worker"]["environment"]
    assert environment["VIMAG_WRITE_ENABLED"].startswith(
        "${VIMAG_WRITE_ENABLED:?"
    )
    assert environment["VIMAG_AUTOMATIC_INTAKE"].startswith(
        "${VIMAG_AUTOMATIC_INTAKE:?"
    )
    assert config["services"]["api"]["environment"]["VIMAG_WRITE_ENABLED"] == environment["VIMAG_WRITE_ENABLED"]
    example = (ROOT / "deploy/env.example").read_text()
    assert "\\nVIMAG_WRITE_ENABLED=false\\n" in "\\n" + example
    assert "\\nVIMAG_AUTOMATIC_INTAKE=false\\n" in "\\n" + example
    assert config["networks"]["backend"]["internal"] is True
    assert (
        config["services"]["db"]["environment"]["POSTGRES_USER"]
        == "vimag_cluster_admin"
    )
    for name in ["api", "worker"]:
        assert "db_admin_password" not in config["services"][name]["secrets"]
    assert any(
        v["target"] == "/docker-entrypoint-initdb.d/10-vimag.sql" and v["read_only"]
        for v in config["services"]["db"]["volumes"]
    )


def test_pending_manifest_cannot_be_deployed() -> None:
    spec = importlib.util.spec_from_file_location(
        "manifest", ROOT / "deploy/scripts/validate-release.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError):
        module.validate(
            json.loads((ROOT / "deploy/release-manifest.pending.json").read_text())
        )


def test_queue_claim_unique_and_resource_epochs_monotonic(db: p.Database) -> None:
    with db.transaction() as conn:
        conn.execute(insert(p.tasks), [{"kind": "INVENTORY"}, {"kind": "INVENTORY"}])
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(db.claim, ["worker-a", "worker-b"]))
    assert first is not None and second is not None and first["id"] != second["id"]
    db.reserve(first, ["destination:movies/synthetic"])
    epoch = first["resource_epochs"]["destination:movies/synthetic"]
    with pytest.raises(GateError, match="RESOURCE_BUSY"):
        db.reserve(second, ["destination:movies/synthetic"])
    db.finish_task(first, "DONE")
    db.reserve(second, ["destination:movies/synthetic"])
    assert second["resource_epochs"]["destination:movies/synthetic"] > epoch
    db.fence(second, ["destination:movies/synthetic"])
    with pytest.raises(GateError, match="LEASE_LOST"):
        db.fence(first, ["destination:movies/synthetic"])


def test_approved_normalization_reversible_journal_no_unknown_sidecar_write(
    stack: Any,
) -> None:
    worker, _, _, _ = stack
    source = worker.cfg.nas_root / "Library/Movies/old-name.mkv"
    source.parent.mkdir()
    source.write_bytes(b"synthetic-normalization-media")
    aid = p.uid()
    with worker.db.transaction() as conn:
        conn.execute(
            insert(p.assets).values(
                id=aid,
                root="library",
                relative_path="Movies/old-name.mkv",
                fingerprint=sha256(source),
                data={"bg": "NO_BG"},
            )
        )
    client = login(worker.db)
    result = client.post(
        f"/api/v1/library/assets/{aid}/normalization-plan",
        json={
            "identity": {"title": "Synthetic", "year": 2026, "media_type": "movie"},
            "quality_label": "1080p",
            "reason": "Synthetic explicit normalization review",
        },
    )
    assert result.status_code == 202
    plan = result.json()
    client.headers["Idempotency-Key"] = str(uuid4())
    result = client.post(
        f"/api/v1/library/normalization-plans/{plan['id']}/approve",
        json={
            "plan_revision": plan["revision"],
            "plan_sha256": plan["sha256"],
            "reason": "Exact synthetic plan approved",
        },
    )
    assert result.status_code == 202
    drive(worker)
    target = worker.cfg.nas_root / plan["data"]["target"]
    assert (
        target.read_bytes() == b"synthetic-normalization-media" and not source.exists()
    )
    assert worker.db.one(select(p.operations))["status"] == "VERIFIED"


def test_T23_shared_content_dependencies_ignore_inode_counts(stack: Any) -> None:
    from app.maintenance import dependencies

    worker, qbt, _, _ = stack
    t = torrent(worker.db)
    other = torrent(worker.db, index=2)
    source = worker.cfg.staging_root / t.files[0]["name"]
    # Two torrent identities intentionally reference the same exact byte path.
    other.files = t.files
    qbt.torrents = {t.info_hash: t, other.info_hash: other}
    library = worker.cfg.nas_root / "Library/Movies/shared.mkv"
    library.parent.mkdir()
    library.write_bytes(source.read_bytes())
    conflicts = dependencies(
        worker, {"relative_path": "Movies/shared.mkv", "fingerprint": sha256(library)}
    )
    assert len(conflicts) == 2 and all(
        c["reason"] == "SHARED_CONTENT" for c in conflicts
    )


def test_T17_worker_preserves_intentional_pause_without_start(stack: Any) -> None:
    worker, qbt, _, _ = stack
    t = torrent(
        worker.db,
        state="stoppedUP",
        policy={"intentional_pause": True, "queued": False},
    )
    jid = onboard(worker, qbt, t)
    drive(worker)
    assert (
        worker.db.one(select(p.jobs).where(p.jobs.c.id == jid))["state"]
        == "CompletedWithWarnings"
    )
    assert not any(c[0] == "start" for c in qbt.commands)
    assert qbt.torrent(t.info_hash).state == "stoppedUP"
