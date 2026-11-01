"""Fail-closed, image-only deployment. Does not enable media writes."""
import json
import os
import subprocess
import sys
from pathlib import Path

from importlib.util import module_from_spec, spec_from_file_location


def run(argv: list[str], **kwargs):
    return subprocess.run(argv, check=True, timeout=600, **kwargs)


def main() -> None:
    manifest_path = Path(sys.argv[1]).resolve(strict=True)
    spec = spec_from_file_location("release_validation", Path(__file__).with_name("validate-release.py"))
    validation = module_from_spec(spec)
    spec.loader.exec_module(validation)
    manifest = json.loads(manifest_path.read_text())
    validation.validate(manifest)
    compose = ["docker", "compose", "--env-file", ".env", "-f", "compose.prod.yaml"]
    config = json.loads(run(compose + ["config", "--format", "json"], capture_output=True, text=True).stdout)
    services = config["services"]
    if set(services) != {"web", "api", "worker", "db"}:
        raise RuntimeError("Unreviewed runtime layout")
    for name, image in {"web": "web", "api": "backend", "worker": "backend", "db": "postgres"}.items():
        if services[name]["image"] != manifest["images"][image] or services[name].get("build") or services[name].get("ports"):
            raise RuntimeError("Image/build/port safety mismatch: " + name)
    if str(services["worker"]["environment"]["VIMAG_WRITE_ENABLED"]).lower() != "false":
        raise RuntimeError("First deployment must be read-only")
    pgdata = next(v["source"] for v in services["db"]["volumes"] if v["target"] == "/var/lib/postgresql/data")
    run(["sh", "scripts/preflight.sh"], env={**os.environ, "PGDATA_HOST": pgdata})
    evidence = json.loads(Path("config/preflight-evidence.json").read_text())
    for key in ["private_tls_verified", "secrets_permissions_verified", "jellyfin_token_rotated", "host_database_restore_verified", "qbt_backup_verified"]:
        if evidence.get(key) is not True:
            raise RuntimeError("External deployment precondition missing: " + key)
    run(compose + ["pull"])
    run(compose + ["up", "-d", "--wait", "db"])
    privileges = run(compose + ["exec", "-T", "db", "psql", "-U", "vimag", "-d", "vimag", "-tAc", "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user"], capture_output=True, text=True).stdout.strip()
    if privileges != "f|f|f|f|f":
        raise RuntimeError("Runtime database role has forbidden cluster privileges; deployment stopped")
    # Capture the pre-migration state, including a genuinely empty first database.
    backup = Path("backups/predeploy.backup")
    backup.parent.mkdir(parents=True, exist_ok=True)
    exists = run(compose + ["exec", "-T", "db", "psql", "-U", "vimag", "-d", "vimag", "-tAc", "SELECT to_regclass('public.alembic_version')"], capture_output=True, text=True).stdout.strip()
    schema = run(compose + ["exec", "-T", "db", "psql", "-U", "vimag", "-d", "vimag", "-tAc", "SELECT version_num FROM alembic_version"], capture_output=True, text=True).stdout.strip() if exists else "EMPTY"
    with backup.open("xb") as output:
        run(compose + ["exec", "-T", "db", "pg_dump", "-U", "vimag", "-d", "vimag", "-Fc", "--no-owner", "--no-acl"], stdout=output)
    os.chmod(backup, 0o600)
    import hashlib
    checksum = hashlib.sha256(backup.read_bytes()).hexdigest()
    backup.with_suffix(".manifest.json").write_text(json.dumps({"sha256": checksum, "schema": schema, "format": "pg_dump-custom", "source_commit": manifest["commit"], "stage": "before_migration"}))
    run(compose + ["run", "--rm", "--no-deps", "api", "python", "-m", "alembic", "upgrade", "head"])
    run(compose + ["up", "-d"])
    print("READ_ONLY_DEPLOYMENT_STARTED: verify live health and record baseline before any isolated fixture authorization")


if __name__ == "__main__":
    main()
