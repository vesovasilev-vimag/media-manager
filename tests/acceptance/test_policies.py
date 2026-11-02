from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app.domain import (
    GateError,
    Identity,
    bg_state,
    compare,
    digest,
    eligible,
    final_state,
    match_identity,
    name_for,
    seeding_capable,
)
from app.storage import (
    atomic_sidecar,
    cleanup_staging,
    contained,
    hardlink,
    reversible_move,
    sha256,
)
from app.subtitles import evaluate, sync_proposal
from conftest import synthetic_probe, torrent


def version(bg: str = "BG_VERIFIED", **changes: Any) -> dict[str, Any]:
    return {
        "identity_key": "tmdb:movie:1",
        "edition": "Theatrical",
        "integrity": True,
        "height": 1080,
        "codec": "h264",
        "bitrate": 8000000,
        "bg": bg,
        **changes,
    }


def test_T02_T28_keep_bg_and_materially_better_english() -> None:
    result = compare(
        version(),
        version("NO_BG", height=2160, hdr="HDR10", material_improvement_verified=True),
    )
    assert result["decision"] == "KeepBoth"
    assert "PRESERVE_VERIFIED_BG" in result["reason_codes"]
    assert "bitrate" in result["factors"] and "codec" in result["factors"]


def test_resolution_alone_never_proves_quality() -> None:
    assert (
        compare(version(), version("NO_BG", height=2160))["decision"]
        == "KeepBGPreferred"
    )


def test_T03_better_bg_recommendation_preserves_existing() -> None:
    assert (
        compare(version(), version(material_improvement_verified=True))["decision"]
        == "PreferBetterBG"
    )


def test_T21_distinct_editions() -> None:
    assert compare(version(), version(edition="Extended"))["reason_codes"] == [
        "DIFFERENT_EDITIONS"
    ]


def test_T07_T29_competing_provider_ids_require_review() -> None:
    candidates = [
        {"id": "1", "media_type": "movie", "year": 2026},
        {"id": "2", "media_type": "movie", "year": 2026},
    ]
    assert match_identity(candidates, None, "movie", 2026) is None
    assert match_identity(candidates, "1", "show", 2026) is None
    assert match_identity(candidates, "1", "movie", 2026) == candidates[0]


def test_T25_v11_detected_tag_accepted_with_provenance(db: Any) -> None:
    t = torrent(db)
    path = db.config.staging_root / t.files[0]["name"]
    analysis = synthetic_probe(path)
    analysis["streams"][1]["tags"]["language"] = "bul"
    state = bg_state(analysis, sha256(path), [])
    assert state == "BG_TAGGED"
    name = name_for(
        "movies",
        Identity("Synthetic", 2026, "movie", confirmed=True),
        "1080p",
        state,
        ".mkv",
    )
    # BG-01 supersedes v1.0 manual confirmation; provenance remains BG_TAGGED.
    assert " BG" in name


def test_T26_stream_bound_evidence_survives_byte_identical_copy(
    db: Any, tmp_path: Path
) -> None:
    import shutil

    t = torrent(db)
    source = db.config.staging_root / t.files[0]["name"]
    analysis = synthetic_probe(source)
    evidence = [
        {
            "fingerprint": sha256(source),
            "stream_key": digest(analysis["streams"][1]),
            "source": "human-confirmed",
            "actor": "test-admin",
            "verified_at": "2026-11-01",
        }
    ]
    copied = tmp_path / "copy.mkv"
    shutil.copyfile(source, copied)
    assert bg_state(analysis, sha256(copied), evidence) == "BG_VERIFIED"
    assert " BG" in name_for(
        "movies",
        Identity("Synthetic", 2026, "movie", confirmed=True),
        "1080p",
        "BG_VERIFIED",
        ".mkv",
    )


def test_T27_wrong_stream_or_file_rejected(db: Any) -> None:
    t = torrent(db)
    path = db.config.staging_root / t.files[0]["name"]
    analysis = synthetic_probe(path)
    evidence = [
        {
            "fingerprint": "f" * 64,
            "stream_key": digest(analysis["streams"][1]),
            "source": "human-confirmed",
            "actor": "admin",
            "verified_at": "now",
        }
    ]
    assert bg_state(analysis, sha256(path), evidence) != "BG_VERIFIED"
    evidence[0]["fingerprint"] = sha256(path)
    evidence[0]["stream_key"] = "0" * 64
    assert bg_state(analysis, sha256(path), evidence) != "BG_VERIFIED"


def test_T24_special_multi_episode_naming() -> None:
    path = name_for(
        "animations",
        Identity(
            "Synthetic Show",
            2026,
            "show",
            "1",
            season=0,
            episodes=[1, 2],
            confirmed=True,
        ),
        "1080p",
        "NO_BG",
        ".mkv",
    )
    assert (
        path
        == "Animations/Series/Synthetic Show (2026) [tmdbid-1]/Season 00/Synthetic Show S00E01-E02 - 1080p - Theatrical.mkv"
    )


def test_T15_traversal_and_symlink(db: Any, tmp_path: Path) -> None:
    from app.domain import relative

    for path in [
        "../escape",
        "/absolute",
        "a/../../b",
        "a\\b",
        "a//b",
        "C:/escape",
        "NUL.txt",
        "file.",
    ]:
        with pytest.raises(GateError):
            relative(path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = db.config.nas_root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.fail("Symlink fixture needs supported OS privileges: " + str(exc))
    with pytest.raises(GateError, match="SYMLINK"):
        contained(db.config.nas_root, "escape/file.mkv")


def test_T16_T17_zero_upload_and_intentional_pause(db: Any) -> None:
    t = torrent(
        db, state="stoppedUP", policy={"intentional_pause": True, "queued": False}
    )
    assert seeding_capable(t, "/downloads/complete", t.policy, True)
    assert not seeding_capable(
        t, "/downloads/complete", {"intentional_pause": False}, True
    )


def test_T18_IT03_IT04_manual_tmm_completion(db: Any) -> None:
    t = torrent(db)
    assert eligible(t, baseline=False, seen_before=False, cutover=True)
    assert not eligible(
        replace(t, auto_tmm=True), baseline=False, seen_before=False, cutover=True
    )
    partial = replace(t, progress=0.5, amount_left=1)
    assert (db.config.staging_root / t.files[0]["name"]).exists()
    assert not partial.complete()


def test_T19_no_hardlink_fallback(db: Any, monkeypatch: Any) -> None:
    import os

    root = db.config.nas_root
    (root / "source").write_bytes(b"synthetic")

    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("synthetic unsupported hardlink")

    monkeypatch.setattr(os, "link", fail)
    with pytest.raises(GateError, match="HARDLINK_UNAVAILABLE"):
        hardlink(root, "source", "target", sha256(root / "source"), lambda: None)
    assert (
        not (root / "target").exists()
        and (root / "source").read_bytes() == b"synthetic"
    )


@pytest.mark.parametrize("filename", ["movie.nfo", "poster.jpg"])
def test_T20_T32_T41_IT16_unknown_or_edited_sidecars(db: Any, filename: str) -> None:
    root = db.config.nas_root
    path = root / filename
    path.write_bytes(b"manual-content")
    with pytest.raises(GateError):
        atomic_sidecar(
            root, filename, b"replacement", None, lambda: None, "backups/old"
        )
    with pytest.raises(GateError, match="SIDECAR_CONFLICT"):
        atomic_sidecar(
            root, filename, b"replacement", "0" * 64, lambda: None, "backups/old"
        )
    assert path.read_bytes() == b"manual-content"


def test_T40_owned_sidecar_atomic_update_failure_preserves_old(db: Any) -> None:
    root = db.config.nas_root
    first = atomic_sidecar(
        root, "movie.nfo", b"old-owned", None, lambda: None, "backups/no-old"
    )

    def crash() -> None:
        raise RuntimeError("synthetic crash before replace")

    with pytest.raises(RuntimeError):
        atomic_sidecar(
            root,
            "movie.nfo",
            b"new-owned",
            first,
            lambda: None,
            "backups/old",
            before_replace=crash,
        )
    assert (root / "movie.nfo").read_bytes() == b"old-owned"
    final = atomic_sidecar(
        root, "movie.nfo", b"new-owned", first, lambda: None, "backups/retry"
    )
    assert final == sha256(root / "movie.nfo")
    assert (root / "backups/retry").read_bytes() == b"old-owned"


def test_T31_quarantine_and_restore_preserve_bytes(db: Any) -> None:
    root = db.config.nas_root
    asset = root / "Library/synthetic.mkv"
    asset.write_bytes(b"owned-synthetic-media")
    fingerprint = sha256(asset)
    reversible_move(
        root,
        "Library/synthetic.mkv",
        "Quarantine/synthetic.mkv",
        fingerprint,
        lambda: None,
    )
    assert (
        not asset.exists() and sha256(root / "Quarantine/synthetic.mkv") == fingerprint
    )
    reversible_move(
        root,
        "Quarantine/synthetic.mkv",
        "Library/synthetic.mkv",
        fingerprint,
        lambda: None,
    )
    assert asset.read_bytes() == b"owned-synthetic-media"


def test_T43_IT09_cleanup_only_orphan_staging(db: Any) -> None:
    root, staging = db.config.nas_root, db.config.staging_root
    (staging / "orphan.mkv").write_bytes(b"synthetic")
    library = root / "Library/keep.mkv"
    library.write_bytes(b"synthetic")
    quarantine = root / "Quarantine"
    quarantine.mkdir()
    (quarantine / "keep.mkv").write_bytes(b"quarantined")
    proof = dict.fromkeys(
        [
            "owned_staging",
            "nas_integrity",
            "mapping_verified",
            "rechecked",
            "seeding_capable",
            "dependency_scan_complete",
        ],
        True,
    )
    with pytest.raises(GateError, match="CLEANUP_BLOCKED"):
        cleanup_staging(
            staging,
            "orphan.mkv",
            sha256(library),
            destination=library,
            dependencies=[{"torrent": "synthetic"}],
            proof=proof,
            fence=lambda: None,
        )
    assert (staging / "orphan.mkv").exists()
    cleanup_staging(
        staging,
        "orphan.mkv",
        sha256(library),
        destination=library,
        dependencies=[],
        proof=proof,
        fence=lambda: None,
    )
    assert (
        not (staging / "orphan.mkv").exists()
        and library.exists()
        and (quarantine / "keep.mkv").exists()
    )


def test_T06_T33_subtitle_mismatch_preserves_original() -> None:
    original = b"1\n00:00:01,000 --> 00:00:02,000\nSynthetic Bulgarian cue\n"
    media = {"edition": "Theatrical", "fingerprint": "a" * 64, "duration": 5, "fps": 24}
    candidate = {"edition": "Extended", "fingerprint": "a" * 64, "fps": 25}
    assert evaluate(candidate, media, original)["status"] == "Mismatch"
    proposal = sync_proposal(original, 1, 1)
    assert b"00:00:02,000" in proposal and b"00:00:01,000" in original
    assert (
        evaluate({**candidate, "edition": "Theatrical", "fps": 24}, media, proposal)[
            "status"
        ]
        == "NeedsReview"
    )


def test_T34_T35_T36_terminal_gate() -> None:
    good = {"integrity": True, "published": True, "subtitle": "Unavailable"}
    assert final_state([good], True, True) == "CompletedWithWarnings"
    assert final_state([{**good, "published": False}], True, True) == "PublishPending"
    assert (
        final_state([good, {**good, "published": False}], True, True)
        == "PublishPending"
    )
    assert final_state([good], True, False) == "RecoveryRequired"
