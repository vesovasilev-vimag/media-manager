from datetime import timedelta

from app import persistence as p
from app.worker_health import observed_health


def test_stale_process_cannot_look_ready_from_old_durable_health() -> None:
    health = observed_health(
        {
            "time": (p.now() - timedelta(seconds=16)).isoformat(),
            "state": "READY",
            "dispatch": "BUSY",
        }
    )
    assert health["state"] == "STALE"
    assert health["liveness"] == "UNKNOWN" and health["dispatch"] == "UNKNOWN"


def test_long_running_task_and_provider_failure_do_not_fail_dispatch_health() -> None:
    health = observed_health(
        {
            "time": p.now().isoformat(),
            "state": "DEGRADED",
            "liveness": "ALIVE",
            "dispatch": "BUSY",
            "qbt": "QBT_TIMEOUT",
        }
    )
    assert health["dispatch"] == "BUSY" and health["liveness"] == "ALIVE"
    assert health["state"] == "DEGRADED"


def test_missing_or_invalid_heartbeat_is_unknown() -> None:
    for value in ({}, {"time": "bad"}, {"time": "2026-01-01"}):
        assert observed_health(value)["state"] == "STALE"
