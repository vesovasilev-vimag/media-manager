from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update

from app import persistence as p
from app.api import create_app
from conftest import login, drive, onboard, torrent


def test_T37_auth_expired_session_all_admin_routes(db: p.Database) -> None:
    client = TestClient(create_app(db.config, db), base_url="https://testserver")
    for path in [
        "/dashboard",
        "/jobs",
        "/library/assets",
        "/library/duplicates",
        "/subtitles",
        "/settings",
        "/transfers",
        "/health/ready",
        "/audit",
        "/openapi.json",
    ]:
        assert client.get("/api/v1" + path).status_code == 401
    client = login(db)
    assert client.get("/api/v1/dashboard").status_code == 200
    with db.transaction() as conn:
        conn.execute(update(p.sessions).values(expires_at=p.now()))
    assert client.get("/api/v1/dashboard").status_code == 401


def test_T38_missing_csrf_no_side_effect_security_audit(stack: Any) -> None:
    worker, qbt, _, _ = stack
    client = login(worker.db)
    jid = onboard(worker, qbt, torrent(worker.db))
    drive(worker, 1)
    plan = worker.db.one(select(p.plans))
    del client.headers["X-CSRF-Token"]
    result = client.post(
        f"/api/v1/jobs/{jid}/approve",
        json={
            "plan_revision": plan["revision"],
            "plan_sha256": plan["sha256"],
            "reason": "synthetic",
        },
    )
    assert result.status_code == 403
    assert not worker.db.rows(select(p.approvals))
    assert worker.db.rows(select(p.audit).where(p.audit.c.kind == "CSRF_DENIED"))


def test_T39_machine_hook_has_no_admin_privileges(db: p.Database) -> None:
    client = TestClient(create_app(db.config, db), base_url="https://testserver")
    client.headers.update({"Authorization": "Bearer synthetic-machine-only-token"})
    assert client.post("/api/v1/intake", json={"command": "approve"}).status_code == 404
    assert (
        client.put("/api/v1/settings/automation", json={"retry_budget": 2}).status_code
        == 401
    )


def test_T42_no_permanent_delete_endpoint(db: p.Database) -> None:
    client = login(db)
    for path in [
        "/library/delete",
        "/library/purge",
        "/library/quarantine/delete",
        "/delete-library-file",
        "/purge-quarantine",
    ]:
        assert client.post("/api/v1" + path).status_code == 404
    for route in create_app(db.config, db).routes:
        assert "DELETE" not in getattr(route, "methods", set())


def test_T08_T23_T30_dependency_cannot_be_overridden(stack: Any) -> None:
    worker, qbt, _, _ = stack
    client = login(worker.db)
    t = torrent(worker.db)
    onboard(worker, qbt, t)
    aid = p.uid()
    with worker.db.transaction() as conn:
        conn.execute(
            insert(p.assets).values(
                id=aid,
                root="library",
                relative_path="Movies/synthetic.mkv",
                fingerprint="a" * 64,
                data={"dependencies": [t.info_hash, "other-synthetic-torrent"]},
            )
        )
    result = client.post(f"/api/v1/library/assets/{aid}/quarantine-plan")
    assert result.status_code == 423
    assert not worker.db.rows(select(p.quarantine))


def test_T31_approved_quarantine_restore_journal(stack: Any) -> None:
    from app.storage import sha256

    worker, _, _, _ = stack
    client = login(worker.db)
    path = worker.cfg.nas_root / "Library/Movies/Synthetic.mkv"
    path.parent.mkdir()
    path.write_bytes(b"synthetic-owned-quarantine-fixture")
    aid = p.uid()
    with worker.db.transaction() as conn:
        conn.execute(
            insert(p.assets).values(
                id=aid,
                root="library",
                relative_path="Movies/Synthetic.mkv",
                fingerprint=sha256(path),
                data={"dependencies": []},
            )
        )
    proposed = client.post(f"/api/v1/library/assets/{aid}/quarantine-plan")
    assert proposed.status_code == 202
    plan = proposed.json()
    client.headers["Idempotency-Key"] = str(uuid4())
    result = client.post(
        f"/api/v1/library/quarantine-plans/{plan['id']}/approve",
        json={
            "plan_revision": plan["revision"],
            "plan_sha256": plan["sha256"],
            "reason": "synthetic explicit approval",
        },
    )
    assert result.status_code == 202
    drive(worker)
    manifest = worker.db.one(select(p.quarantine))
    assert manifest["state"] == "QUARANTINED" and not path.exists()
    assert (
        worker.db.one(select(p.operations).where(p.operations.c.kind == "QUARANTINE"))[
            "status"
        ]
        == "VERIFIED"
    )
    client.headers["Idempotency-Key"] = str(uuid4())
    assert (
        client.post(f"/api/v1/library/quarantine/{manifest['id']}/restore").status_code
        == 202
    )
    drive(worker)
    assert path.read_bytes() == b"synthetic-owned-quarantine-fixture"
    assert worker.db.one(select(p.quarantine))["state"] == "RESTORED"


def test_idempotency_and_stale_revision(stack: Any) -> None:
    worker, qbt, _, _ = stack
    client = login(worker.db)
    jid = onboard(worker, qbt, torrent(worker.db))
    drive(worker, 1)
    plan = worker.db.one(select(p.plans))
    body = {
        "plan_revision": plan["revision"],
        "plan_sha256": plan["sha256"],
        "reason": "synthetic",
    }
    first = client.post(f"/api/v1/jobs/{jid}/approve", json=body)
    second = client.post(f"/api/v1/jobs/{jid}/approve", json=body)
    assert (
        first.status_code == second.status_code == 202 and first.json() == second.json()
    )
    assert len(worker.db.rows(select(p.approvals))) == 1
    client.headers["Idempotency-Key"] = str(uuid4())
    assert (
        client.post(
            f"/api/v1/jobs/{jid}/approve", json={**body, "plan_sha256": "0" * 64}
        ).status_code
        == 409
    )


def test_login_rate_limit_cookie_logout_rotation(db: p.Database) -> None:
    client = login(db)
    cookies = client.cookies
    assert cookies.get("vimag_session")
    for cookie in cookies.jar:
        assert cookie.secure
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/me").status_code == 401
    for _ in range(5):
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": "operator", "password": "wrong"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "operator", "password": "wrong"}
        ).status_code
        == 429
    )


def test_secret_validation_never_echoes_input(db: p.Database) -> None:
    client = TestClient(create_app(db.config, db), base_url="https://testserver")
    secret = "synthetic-private-input-never-echo"
    result = client.post(
        "/api/v1/auth/login", json={"username": {}, "password": secret, "extra": secret}
    )
    assert result.status_code == 422 and secret not in result.text
