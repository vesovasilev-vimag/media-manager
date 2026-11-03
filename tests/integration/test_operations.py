import subprocess
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, insert, select, text

from app import persistence as p
from app.adapters import probe
from app.domain import GateError
from app.ops import backup, compatible, restore
from app.storage import hardlink_scratch, sha256
from conftest import ROOT


def test_IT10_hardlink_shared_writes_without_inode_reliance(db: p.Database) -> None:
    proof = hardlink_scratch(db.config.nas_root)
    assert proof == {"shared_write": True, "inode_trusted": False}


def test_IT13_postgres_backup_restore_jobs_journal_audit(
    db: p.Database, tmp_path: Path
) -> None:
    jid, pid = p.uid(), p.uid()
    with db.transaction() as conn:
        conn.execute(insert(p.jobs).values(id=jid))
        conn.execute(
            insert(p.plans).values(
                id=pid,
                job_id=jid,
                revision=1,
                sha256="1" * 64,
                data={"synthetic": True},
            )
        )
        conn.execute(
            insert(p.operations).values(
                job_id=jid,
                plan_id=pid,
                op_key="synthetic",
                kind="MOVE",
                status="COMMAND_REQUESTED",
                intent={"synthetic": True},
            )
        )
        db.event(conn, "test", "SYNTHETIC_BACKUP_PROOF", jid)
    path = tmp_path / "snapshot.backup"
    manifest = backup(db, path)
    assert path.is_file() and len(manifest["sha256"]) == 64
    cfg = db.config.model_copy(update={"db_name": "vimag_rc1_restore_test"})
    admin_engine = create_engine(
        cfg.database_url().set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as conn:
        # Fixed disposable database name, never an input-derived production database.
        conn.execute(
            text("DROP DATABASE IF EXISTS vimag_rc1_restore_test WITH (FORCE)")
        )
        conn.execute(
            text(
                "CREATE DATABASE vimag_rc1_restore_test TEMPLATE template0 LOCALE_PROVIDER icu ICU_LOCALE 'und'"
            )
        )
    restore(cfg, path, manifest, confirmed_empty=True)
    restored = p.Database(cfg)
    assert restored.one(select(p.jobs))["id"] == jid
    assert restored.one(select(p.operations))["status"] == "COMMAND_REQUESTED"
    assert restored.one(select(p.audit))["kind"] == "SYNTHETIC_BACKUP_PROOF"
    with pytest.raises(GateError, match="EMPTY_DATABASE"):
        restore(cfg, path, manifest, confirmed_empty=True)
    restored.engine.dispose()
    admin_engine.dispose()


def test_IT15_incompatible_schema_rollback_blocked() -> None:
    assert not compatible("0002", {"compatible_schemas": ["0001"]})
    assert compatible("0001", {"compatible_schemas": ["0001"]})


def test_migration_downgrade_upgrade_disposable_only(db: p.Database) -> None:
    cfg = Config(str(ROOT / "backend/alembic.ini"))
    with pytest.raises(RuntimeError, match="disposable"):
        command.downgrade(cfg, "base")
    from argparse import Namespace

    cfg.cmd_opts = Namespace(x=["disposable=true"])
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    with db.transaction() as conn:
        assert (
            conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0002"
        )


def test_real_ffprobe_synthetic_media_not_header_integrity_claim(
    tmp_path: Path,
) -> None:
    media = tmp_path / "synthetic.mkv"
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
            "sine=frequency=440:duration=2",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-metadata:s:a:0",
            "language=bul",
            "-shortest",
            str(media),
        ],
        check=True,
        timeout=30,
        capture_output=True,
    )  # noqa: S603,S607
    analysis = probe(media)
    assert any(s.get("codec_type") == "video" for s in analysis["streams"])
    assert any(s.get("tags", {}).get("language") == "bul" for s in analysis["streams"])
    assert len(sha256(media)) == 64
