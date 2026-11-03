import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app import persistence as p
from app.api import create_app
from app.domain import Torrent
from app.emulated import create_emulators
from app.settings import Settings
from app.worker import Worker

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def database_config() -> Settings:
    # This fixture may never target an operator's normal database.
    cfg = Settings(
        environment="test",
        adapters="emulated",
        db_host=os.environ.get("VIMAG_TEST_DB_HOST", "127.0.0.1"),
        db_port=int(os.environ.get("VIMAG_TEST_DB_PORT", "55432")),
        db_name="vimag_rc1_test",
        db_password_file=ROOT / "deploy/secrets/db_password",
        write_enabled=True,
        min_free_bytes=0,
        min_free_percent=0,
        allowed_host="testserver",
        origin="https://testserver",
    )
    if os.environ.get("VIMAG_TEST_DATABASE") != "disposable":
        raise RuntimeError(
            "Set VIMAG_TEST_DATABASE=disposable for the dedicated local test database"
        )
    engine = create_engine(
        cfg.database_url().set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with engine.connect() as conn:
        if not conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname='vimag_rc1_test'")
        ).first():
            conn.execute(
                text(
                    "CREATE DATABASE vimag_rc1_test TEMPLATE template0 LOCALE_PROVIDER icu ICU_LOCALE 'und'"
                )
            )
    engine.dispose()
    os.environ.update(
        {
            "VIMAG_DB_HOST": cfg.db_host,
            "VIMAG_DB_PORT": str(cfg.db_port),
            "VIMAG_DB_NAME": cfg.db_name,
            "VIMAG_DB_PASSWORD_FILE": str(cfg.db_password_file),
        }
    )
    command.upgrade(Config(str(ROOT / "backend/alembic.ini")), "head")
    return cfg


@pytest.fixture
def db(database_config: Settings, tmp_path: Path) -> p.Database:
    cfg = database_config.model_copy(
        update={
            "staging_root": tmp_path / "staging",
            "nas_root": tmp_path / "nas",
            "setup_token_file": tmp_path / "setup_token",
        }
    )
    cfg.staging_root.mkdir()
    (cfg.nas_root / "Library").mkdir(parents=True)
    cfg.setup_token_file.write_text("synthetic-setup-token-for-tests-only")
    db = p.Database(cfg)
    with db.transaction() as conn:
        names = ",".join('"' + t.name + '"' for t in reversed(p.metadata.sorted_tables))
        conn.execute(text("TRUNCATE " + names + " CASCADE"))
    yield db
    db.engine.dispose()


def synthetic_probe(path: Path) -> dict[str, Any]:
    return {
        "format": {"duration": "2.0", "size": str(path.stat().st_size)},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "height": 1080,
                "r_frame_rate": "24/1",
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "tags": {"language": "eng"},
            },
        ],
    }


@pytest.fixture
def stack(db: p.Database) -> tuple[Worker, Any, Any, Any]:
    qbt, jellyfin, tmdb = create_emulators(db.config)
    worker = Worker(db, qbt, jellyfin, tmdb, synthetic_probe)
    return worker, qbt, jellyfin, tmdb


def torrent(
    db: p.Database, index: int = 1, files: list[str] | None = None, **changes: Any
) -> Torrent:
    names = files or ["Synthetic 2026 tmdbid-1.mkv"]
    records = []
    for ix, name in enumerate(names):
        path = db.config.staging_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic-owned-by-test-" + bytes([index, ix]) * 100)
        records.append(
            {
                "index": ix,
                "name": name,
                "size": path.stat().st_size,
                "priority": 1,
                "progress": 1,
            }
        )
    values = dict(
        info_hash=f"{index:040x}",
        added_on=1800000000 + index,
        category="movies",
        save_path="/downloads/complete",
        content_path="/downloads/complete/" + names[0],
        state="stalledUP",
        progress=1.0,
        amount_left=0,
        auto_tmm=False,
        files=records,
        policy={"intentional_pause": False, "queued": False},
    )
    return Torrent(**(values | changes))


def onboard(worker: Worker, qbt: Any, t: Torrent) -> str:
    db = worker.db
    db.discover([])
    from sqlalchemy import update

    with db.transaction() as conn:
        conn.execute(
            update(p.clients).values(
                cutover_at=p.now() - __import__("datetime").timedelta(days=2)
            )
        )
    # Use clock-derived, post-cutover addition time; no hardcoded legacy count.
    t.added_on = int(p.now().timestamp())
    qbt.torrents[t.info_hash] = t
    created = db.discover([t], automatic=True)
    assert len(created) == 1
    return created[0]


def drive(worker: Worker, rounds: int = 30) -> None:
    from sqlalchemy import update

    for _ in range(rounds):
        with worker.db.transaction() as conn:
            conn.execute(
                update(p.tasks)
                .where(p.tasks.c.state == "RECONCILING")
                .values(run_after=p.now())
            )
        if not worker.run_once():
            break


def login(db: p.Database) -> TestClient:
    client = TestClient(create_app(db.config, db), base_url="https://testserver")
    client.headers.update({"Origin": "https://testserver"})
    result = client.post(
        "/api/v1/auth/setup",
        json={
            "username": "operator",
            "password": "synthetic-password-for-test-only",
            "setup_token": "synthetic-setup-token-for-tests-only",
        },
    )
    assert result.status_code == 201
    result = client.post(
        "/api/v1/auth/login",
        json={"username": "operator", "password": "synthetic-password-for-test-only"},
    )
    assert result.status_code == 200
    client.headers.update(
        {"X-CSRF-Token": result.json()["csrf_token"], "Idempotency-Key": str(uuid4())}
    )
    return client
