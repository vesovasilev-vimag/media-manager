from typing import Any
from uuid import uuid4
import json
from datetime import timedelta

from sqlalchemy import insert, select

from app import persistence as p
from app.domain import digest
from conftest import login, drive, onboard, torrent


def test_health_reports_jellyfin_outage_and_stale_worker(stack: Any) -> None:
    worker, _, jellyfin, _ = stack
    jellyfin.fail_auth = True
    worker.poll()
    client = login(worker.db)
    health = client.get("/api/v1/health/ready").json()["worker"]
    assert health["qbt"] == "READY" and health["jellyfin"] == "JELLYFIN_AUTH_REQUIRED"
    assert health["state"] == "DEGRADED"
    worker.health({"state": "READY"})
    from sqlalchemy import update

    with worker.db.transaction() as conn:
        conn.execute(
            update(p.settings_table)
            .where(p.settings_table.c.key == "worker_health")
            .values(
                value={
                    "state": "READY",
                    "time": (p.now() - timedelta(hours=1)).isoformat(),
                }
            )
        )
    assert client.get("/api/v1/health/ready").json()["worker"]["state"] == "STALE"


def test_operational_logs_exclude_media_and_remote_payloads(
    stack: Any, capsys: Any
) -> None:
    worker, qbt, _, _ = stack
    onboard(worker, qbt, torrent(worker.db))
    drive(worker)
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert any(
        row["event"] == "TASK_ATTEMPT" and row["duration_ms"] >= 0 for row in rows
    )
    assert all(
        {
            "timestamp",
            "phase",
            "severity",
            "job_id",
            "operation_id",
            "result",
            "error_code",
            "service",
        }
        <= row.keys()
        for row in rows
    )
    assert "Synthetic 2026" not in json.dumps(rows) and "downloads" not in json.dumps(
        rows
    )


def test_T26_T27_library_bg_evidence_preserves_bytes(stack: Any) -> None:
    worker, qbt, _, _ = stack
    onboard(worker, qbt, torrent(worker.db))
    drive(worker)
    asset = worker.db.one(select(p.assets))
    client = login(worker.db)
    body = {
        "fingerprint": asset["fingerprint"],
        "stream_key": asset["data"]["stream_keys"][0]["key"],
        "action": "verify",
        "reason": "Synthetic exact stream verification",
    }
    path = worker.cfg.nas_root / "Library" / asset["relative_path"]
    before = path.read_bytes()
    assert (
        client.post(
            f"/api/v1/library/assets/{asset['id']}/bg-evidence", json=body
        ).json()["bg"]
        == "BG_VERIFIED"
    )
    client.headers["Idempotency-Key"] = str(uuid4())
    assert (
        client.post(
            f"/api/v1/library/assets/{asset['id']}/bg-evidence",
            json={**body, "action": "revoke"},
        ).json()["bg"]
        != "BG_VERIFIED"
    )
    assert path.read_bytes() == before


def test_T06_T33_provider_candidate_download_is_review_only(
    stack: Any, monkeypatch: Any
) -> None:
    worker, qbt, _, _ = stack
    onboard(worker, qbt, torrent(worker.db))
    drive(worker)
    item = worker.db.one(select(p.items))
    candidate_id = p.uid()
    with worker.db.transaction() as conn:
        conn.execute(
            insert(p.evidence_tables["subtitle_candidates"]).values(
                id=candidate_id,
                item_id=item["id"],
                data={
                    "provider": "OpenSubtitles",
                    "attributes": {"files": [{"file_id": 123}]},
                    "status": "NeedsReview",
                },
            )
        )
    content = b"1\n00:00:00,100 --> 00:00:01,800\nSynthetic subtitle\n"
    monkeypatch.setattr(
        "app.worker.OpenSubtitles.download",
        lambda self, file_id: content if file_id == 123 else b"",
    )
    client = login(worker.db)
    assert client.post(f"/api/v1/subtitles/{candidate_id}/download").status_code == 202
    drive(worker)
    result = worker.db.one(
        select(p.evidence_tables["subtitle_candidates"]).where(
            p.evidence_tables["subtitle_candidates"].c.id == candidate_id
        )
    )
    assert (
        result["data"]["content"] == content.decode()
        and result["data"]["status"] == "NeedsReview"
    )
    assert not list((worker.cfg.nas_root / "Library").rglob("*.srt"))


def test_T01_verified_subtitle_attaches_then_republishes_complete(stack: Any) -> None:
    worker, qbt, jellyfin, _ = stack
    jid = onboard(worker, qbt, torrent(worker.db))
    drive(worker)
    client = login(worker.db)
    item = worker.db.one(select(p.items))
    srt = "1\n00:00:00,100 --> 00:00:01,800\nСинтетичен български субтитър\n"
    response = client.post(
        "/api/v1/subtitles/verify",
        json={
            "item_id": item["id"],
            "fingerprint": item["data"]["fingerprint"],
            "edition": "Theatrical",
            "content": srt,
            "timing_confirmed": True,
            "reason": "Synthetic exact-video timing verification",
        },
    )
    assert response.status_code == 202
    drive(worker)
    assert (
        worker.db.one(select(p.jobs).where(p.jobs.c.id == jid))["state"] == "Completed"
    )
    plan = worker.db.one(select(p.plans))
    video = worker.cfg.nas_root / "Library" / plan["data"]["entries"][0]["destination"]
    assert video.with_suffix(".bg.srt").read_text(encoding="utf-8") == srt
    assert jellyfin.refresh_count == 2
    assert [c[0] for c in qbt.commands].count("setLocation") == 1


def test_T26_T27_bg_verify_revoke_from_authenticated_api(stack: Any) -> None:
    worker, qbt, _, _ = stack
    onboard(worker, qbt, torrent(worker.db))
    drive(worker, 1)
    client = login(worker.db)
    item = worker.db.one(select(p.items))
    body = {
        "item_id": item["id"],
        "fingerprint": item["data"]["fingerprint"],
        "stream_key": digest(item["data"]["probe"]["streams"][1]),
        "action": "verify",
        "reason": "Synthetic stream verification",
    }
    assert (
        client.post(
            "/api/v1/media/bg-evidence", json={**body, "stream_key": "0" * 64}
        ).status_code
        == 409
    )
    client.headers["Idempotency-Key"] = str(uuid4())
    assert (
        client.post("/api/v1/media/bg-evidence", json=body).json()["bg"]
        == "BG_VERIFIED"
    )
    client.headers["Idempotency-Key"] = str(uuid4())
    assert (
        client.post(
            "/api/v1/media/bg-evidence", json={**body, "action": "revoke"}
        ).json()["bg"]
        != "BG_VERIFIED"
    )
    assert len(worker.db.rows(select(p.evidence_tables["bg_audio_evidence"]))) == 2


def test_T32_sidecar_external_edit_requires_exact_explicit_revision(stack: Any) -> None:
    worker, qbt, _, _ = stack
    jid = onboard(worker, qbt, torrent(worker.db))
    drive(worker, 1)
    plan = worker.db.one(select(p.plans))
    destination = (
        worker.cfg.nas_root / "Library" / plan["data"]["entries"][0]["destination"]
    )
    destination.parent.mkdir(parents=True)
    sidecar = destination.parent / "movie.nfo"
    sidecar.write_text("<movie><title>External edit</title></movie>")
    old = sidecar.read_bytes()
    drive(worker)
    job = worker.db.one(select(p.jobs).where(p.jobs.c.id == jid))
    assert job["state"] == "NeedsReview" and sidecar.read_bytes() == old
    conflict = next(iter(job["data"]["sidecar_conflicts"].values()))
    client = login(worker.db)
    response = client.post(
        f"/api/v1/jobs/{jid}/sidecars/approve",
        json={
            "plan_revision": plan["revision"],
            "plan_sha256": plan["sha256"],
            "relative_path": conflict["relative_path"],
            "observed_sha256": conflict["observed_sha256"],
            "reason": "Synthetic exact replacement approval",
        },
    )
    assert response.status_code == 202
    drive(worker)
    assert (
        worker.db.one(select(p.jobs).where(p.jobs.c.id == jid))["state"]
        == "CompletedWithWarnings"
    )
    assert sidecar.read_bytes() != old
    backup_files = list(
        (worker.cfg.nas_root / ".vimag-sidecar-backups").rglob("movie.nfo")
    )
    assert any(path.read_bytes() == old for path in backup_files)
