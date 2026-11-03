"""Local structured operational logs: no payloads, filenames, hashes or credentials."""

import json
from datetime import UTC, datetime


def emit(
    event: str,
    *,
    job_id: str | None = None,
    operation_id: str | None = None,
    step: int | None = None,
    phase: str = "observe",
    severity: str = "INFO",
    duration_ms: int | None = None,
    result: str | None = None,
    error_code: str | None = None,
    service: str = "worker",
) -> None:
    # Call sites supply fixed event/error enums, never remote strings or exception repr.
    print(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "event": event,
                "job_id": job_id[:12] if job_id else None,
                "operation_id": operation_id[:12] if operation_id else None,
                "step": step,
                "phase": phase,
                "severity": severity,
                "duration_ms": duration_ms,
                "result": result,
                "error_code": error_code,
                "service": service,
            }
        ),
        flush=True,
    )
