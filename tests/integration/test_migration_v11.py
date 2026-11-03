from argparse import Namespace
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import insert, select, text

from app import persistence as p
from app import rc1_schema
from app.ops import backup
from conftest import ROOT


def test_v11_upgrade_real_rc1_rows_and_backup_recovery(
    db: p.Database, tmp_path: Path
) -> None:
    cfg = Config(str(ROOT / "backend/alembic.ini"))
    cfg.cmd_opts = Namespace(x=["disposable=true"])
    command.downgrade(cfg, "0001")
    aid, jid, pid = p.uid(), p.uid(), p.uid()
    quarantined_id, restored_id = p.uid(), p.uid()
    with db.transaction() as conn:
        conn.execute(
            insert(rc1_schema.assets).values(
                id=aid,
                root="library",
                relative_path="Movies/Synthetic.mkv",
                fingerprint="a" * 64,
                data={
                    "identity": {"title": "Prior RC1 title"},
                    "probe": {
                        "format": {"size": "1234567890123"},
                        "streams": [
                            {
                                "codec_type": "audio",
                                "codec_name": "aac",
                                "tags": {"language": "bul"},
                            }
                        ],
                    },
                },
            )
        )
        for asset_id, state in [
            (quarantined_id, "QUARANTINED"),
            (restored_id, "RESTORED"),
        ]:
            conn.execute(
                insert(rc1_schema.assets).values(
                    id=asset_id,
                    root="library",
                    relative_path=f"Movies/{asset_id}.mkv",
                    fingerprint="d" * 64,
                    data={"category": "movies"},
                )
            )
            conn.execute(
                insert(rc1_schema.quarantine).values(
                    asset_id=asset_id,
                    state=state,
                    plan_sha256="e" * 64,
                    data={"original": f"Library/Movies/{asset_id}.mkv"},
                )
            )
        conn.execute(insert(rc1_schema.jobs).values(id=jid))
        conn.execute(
            insert(rc1_schema.plans).values(
                id=pid, job_id=jid, revision=1, sha256="b" * 64, data={"rc1": True}
            )
        )
        conn.execute(
            insert(rc1_schema.operations).values(
                job_id=jid,
                plan_id=pid,
                op_key="rc1-synthetic-recovery",
                kind="MOVE",
                status="COMMAND_REQUESTED",
                intent={"rc1": True},
            )
        )
    before = backup(db, tmp_path / "rc1-pre-upgrade.backup")
    assert before["schema"] == "0001"
    command.upgrade(cfg, "head")
    row = db.one(select(p.assets).where(p.assets.c.id == aid))
    assert row["title"] == "Prior RC1 title" and row["file_size_bytes"] == 1234567890123
    assert row["audio_languages"] == ["bg"] and row["availability"] == "AVAILABLE"
    assert (
        db.one(select(p.assets).where(p.assets.c.id == quarantined_id))[
            "workflow_state"
        ]
        == "QUARANTINED"
    )
    assert (
        db.one(select(p.assets).where(p.assets.c.id == restored_id))["workflow_state"]
        == "ACTIVE"
    )
    assert (
        len(db.rows(select(p.quarantine))) == 2
    )  # Original restore evidence survives.
    assert db.one(select(p.operations))["status"] == "COMMAND_REQUESTED"
    with db.transaction() as conn:
        conn.execute(
            insert(p.policies).values(
                revision=1, data={"synthetic": True}, sha256="c" * 64, actor="fixture"
            )
        )
    after = backup(db, tmp_path / "v11-post-upgrade.backup")
    assert after["schema"] == "0002" and before["sha256"] != after["sha256"]
    with db.transaction() as conn:
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM pg_trigger WHERE tgname='library_catalogue_changed'"
                )
            ).scalar_one()
            == 1
        )
