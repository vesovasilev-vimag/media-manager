"""Operator tools: schema compatibility and verified, non-destructive database backups."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select, text

from app import persistence as p
from app.domain import GateError
from app.settings import Settings


def compatible(schema: str, manifest: dict[str, Any]) -> bool:
    return schema in manifest.get("compatible_schemas", [])


def pg_env(cfg: Settings) -> dict[str, str]:
    return {
        **os.environ,
        "PGHOST": cfg.db_host,
        "PGPORT": str(cfg.db_port),
        "PGUSER": cfg.db_user,
        "PGDATABASE": cfg.db_name,
        "PGPASSWORD": cfg.secret(cfg.db_password_file).get_secret_value(),
    }


def backup(db: p.Database, destination: Path) -> dict[str, Any]:
    if destination.exists() or destination.suffix != ".backup":
        raise GateError("BACKUP_DESTINATION_REJECTED")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with db.transaction() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    result = subprocess.run(  # noqa: S603 - fixed trusted executable, separate argv, no shell
        [
            "/usr/local/bin/pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "--file",
            str(destination),
        ],
        env=pg_env(db.config),
        capture_output=True,
        check=False,
        timeout=600,
    )  # noqa: S603,S607 - fixed binary, no shell
    if result.returncode:
        raise GateError("BACKUP_FAILED", "BlockedExternalDependency")
    os.chmod(destination, 0o600)
    with destination.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest = {
        "schema": revision,
        "sha256": checksum,
        "format": "pg_dump-custom",
        "created_at": p.now().isoformat(),
        "release": "1.1.0",
    }
    destination.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def restore(
    cfg: Settings, source: Path, manifest: dict[str, Any], *, confirmed_empty: bool
) -> None:
    if not confirmed_empty or (
        manifest["schema"] != "EMPTY"
        and not compatible(manifest["schema"], {"compatible_schemas": ["0001", "0002"]})
    ):
        raise GateError("RESTORE_GATE_CLOSED")
    with source.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != manifest["sha256"]:
            raise GateError("BACKUP_CHECKSUM_MISMATCH")
    engine = create_engine(cfg.database_url(), hide_parameters=True)
    with engine.connect() as conn:
        if conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' LIMIT 1"
            )
        ).first():
            raise GateError("RESTORE_REQUIRES_EMPTY_DATABASE")
    engine.dispose()
    result = subprocess.run(  # noqa: S603 - fixed trusted executable, separate argv, no shell
        [
            "/usr/local/bin/pg_restore",
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-acl",
            "--dbname",
            cfg.db_name,
            str(source),
        ],
        env=pg_env(cfg),
        capture_output=True,
        check=False,
        timeout=600,
    )  # noqa: S603,S607 - fixed binary, no shell
    if result.returncode:
        raise GateError("RESTORE_FAILED", "RecoveryRequired")
    restored = p.Database(cfg)
    with restored.transaction() as conn:
        actual = conn.execute(text("SELECT to_regclass('public.alembic_version')")).scalar_one()
        if manifest["schema"] == "EMPTY":
            valid = actual is None
        else:
            valid = (
                actual is not None
                and conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == manifest["schema"]
            )
        if not valid:
            raise GateError("RESTORE_SCHEMA_MISMATCH")
    restored.engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["backup", "restore", "check-schema", "health"])
    parser.add_argument("path", nargs="?")
    parser.add_argument("--confirm-empty", action="store_true")
    args = parser.parse_args()
    cfg = Settings()
    db = p.Database(cfg)
    if args.action == "backup":
        print(json.dumps(backup(db, Path(args.path))))
    elif args.action == "restore":
        path = Path(args.path)
        restore(
            cfg,
            path,
            json.loads(path.with_suffix(".manifest.json").read_text()),
            confirmed_empty=args.confirm_empty,
        )
        print('{"restored":true,"reconciliation_required":true}')
    elif args.action == "check-schema":
        manifest = json.loads(Path(args.path).read_text())
        with db.transaction() as conn:
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if not compatible(revision, manifest):
            raise SystemExit("SCHEMA_INCOMPATIBLE: image rollback blocked")
        print("SCHEMA_COMPATIBLE")
    else:
        row = db.one(select(p.settings_table).where(p.settings_table.c.key == "worker_health"))
        from datetime import datetime

        age = (p.now() - datetime.fromisoformat(row["value"]["time"])).total_seconds()
        if age > 120:
            raise SystemExit("WORKER_HEARTBEAT_STALE")
        print("WORKER_HEARTBEAT_FRESH")


if __name__ == "__main__":
    main()
