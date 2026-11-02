import hashlib
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import insert, select

from app import persistence as p
from app.domain import GateError
from app.subtitle_history import decode_text, publish
from app.subtitles import evaluate
from conftest import drive, login
from test_library_v11 import approve, asset, plan, post


def publication(stack: Any, a: dict[str, Any], content: bytes, key: str) -> None:
    worker = stack[0]
    db = worker.db
    jid, pid, tid = p.uid(), p.uid(), p.uid()
    with db.transaction() as conn:
        conn.execute(insert(p.jobs).values(id=jid))
        conn.execute(
            insert(p.plans).values(
                id=pid,
                job_id=jid,
                revision=1,
                sha256=hashlib.sha256(key.encode()).hexdigest(),
                data={},
            )
        )
        conn.execute(
            insert(p.tasks).values(id=tid, job_id=jid, kind="SYNTHETIC_SUBTITLE")
        )
    task = db.claim("synthetic-subtitle-test")
    assert task is not None
    db.reserve(task, ["library-scan"])
    record = db.one(select(p.plans).where(p.plans.c.id == pid))
    publish(
        worker,
        task,
        record,
        a,
        content,
        {"source": "synthetic-tested"},
        ["library-scan"],
        key,
    )
    publish(
        worker,
        task,
        record,
        a,
        content,
        {"source": "synthetic-tested"},
        ["library-scan"],
        key,
    )
    db.finish_task(task, "DONE")


def test_SUB_encoding_duration_fps_edition_completeness() -> None:
    content = "1\n00:00:00,100 --> 00:00:01,000\nБългарски текст\n".encode("cp1251")
    converted, encoding = decode_text(content, "windows-1251")
    assert encoding == "Windows-1251" and "Български" in converted.decode()
    with pytest.raises(GateError):
        decode_text(content)
    media = {"fingerprint": "a", "edition": "Theatrical", "duration": 2, "fps": 24}
    candidate = {
        "fingerprint": "a",
        "edition": "Extended",
        "duration": 6,
        "fps": 25,
        "complete": False,
    }
    result = evaluate(candidate, media, converted)
    assert result["status"] == "Mismatch"
    assert {
        "EDITION_MISMATCH",
        "FPS_DRIFT",
        "DURATION_MISMATCH",
        "INCOMPLETE_SUBTITLE",
    } <= set(result["reasons"])
    candidate = {"fingerprint": "a", "edition": "Theatrical", "duration": 2, "fps": 24}
    assert evaluate(candidate, media, converted)["status"] == "NeedsReview"


def test_SUB_primary_versions_replay_restore_and_delete_exclusive_history(
    stack: Any,
) -> None:
    db = stack[0].db
    a = asset(db)
    contents = [
        f"1\n00:00:00,100 --> 00:00:01,000\nSynthetic variant {i}\n".encode()
        for i in range(3)
    ]
    for i, content in enumerate(contents):
        publication(stack, a, content, str(i))
    versions = db.rows(
        select(p.subtitle_versions).order_by(p.subtitle_versions.c.generation)
    )
    assert len(versions) == 3
    latest = versions[-1]["data"]
    assert [Path(e["path"]).name.split(".ver-")[1] for e in latest["history"]] == [
        "02.srt",
        "03.srt",
    ]
    assert [
        (db.config.nas_root / e["path"]).read_bytes() for e in latest["history"]
    ] == [contents[1], contents[0]]
    primary = db.config.nas_root / latest["primary"]
    assert primary.read_bytes() == contents[2]
    assert not list((db.config.nas_root / "Library").rglob("*.ver-*.srt"))
    client = login(db)
    response = post(client, f"/library/assets/{a['id']}/subtitles/versions/1/restore")
    assert response.status_code == 202
    drive(stack[0])
    assert primary.read_bytes() == contents[0]
    latest = db.rows(
        select(p.subtitle_versions).order_by(p.subtitle_versions.c.generation.desc())
    )[0]
    assert (
        db.config.nas_root / latest["data"]["history"][0]["path"]
    ).read_bytes() == contents[2]
    result = plan(stack, client, "deletions", [a["id"]])
    assert approve(client, "deletions", result).status_code == 202
    drive(stack[0])
    assert not primary.exists()
    assert not list(
        (db.config.nas_root / ".vimag-subtitle-history" / a["id"]).rglob("*.srt")
    )


def test_SUB_crash_after_primary_before_manifest_reconciles(
    stack: Any, monkeypatch: Any
) -> None:
    worker = stack[0]
    db = worker.db
    a = asset(db)
    publication(stack, a, b"1\n00:00:00,100 --> 00:00:01,000\nOriginal\n", "first")
    from app import subtitle_history

    original = subtitle_history.atomic_sidecar
    interrupted = False

    def crash(root: Path, rel: str, *args: Any, **kwargs: Any) -> Any:
        nonlocal interrupted
        result = original(root, rel, *args, **kwargs)
        if rel.startswith("Library/") and not interrupted:
            interrupted = True
            raise RuntimeError("synthetic crash after primary replace")
        return result

    monkeypatch.setattr(subtitle_history, "atomic_sidecar", crash)
    with pytest.raises(RuntimeError):
        publication(
            stack, a, b"1\n00:00:00,100 --> 00:00:01,000\nReplacement\n", "crashed"
        )
    monkeypatch.setattr(subtitle_history, "atomic_sidecar", original)
    task = db.one(select(p.tasks).where(p.tasks.c.state == "RUNNING"))
    record = db.one(select(p.plans).where(p.plans.c.job_id == task["job_id"]))
    # Same durable task lease/resources; simulates reconciliation before lease transfer.
    task["resource_epochs"] = {"library-scan": db.one(select(p.leases))["epoch"]}
    publish(
        worker,
        task,
        record,
        a,
        b"1\n00:00:00,100 --> 00:00:01,000\nReplacement\n",
        {},
        ["library-scan"],
        "crashed",
    )
    assert len(db.rows(select(p.subtitle_versions))) == 2
    latest = db.rows(
        select(p.subtitle_versions).order_by(p.subtitle_versions.c.generation.desc())
    )[0]
    assert len(latest["data"]["history"]) == 1
