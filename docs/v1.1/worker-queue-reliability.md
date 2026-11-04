# Worker queue reliability

An external polling failure previously prevented `run_once()` from being reached. Because a failed poll never advanced `last_poll`, the next loop polled again before claiming anything. A healthy-looking process could therefore leave eligible inventory tasks queued indefinitely. A successful long scan could also return directly into slow polling.

The Worker now has one serial task executor, independent serial polling loops for qBittorrent, Jellyfin and NAS observation, and a separate health reporter. Production polling uses separate HTTP clients so authentication and cooldown state do not race task execution. No additional task executors, queue systems or runtime containers are introduced. The dispatcher checks PostgreSQL every 0.5 seconds while idle; provider outages, exceptions or blocked polling do not precede or gate claiming. Failed observations wait the configured polling interval before the next attempt. Each provider has at most one in-flight poll: an overdue observation never starts replacement threads.

HTTP calls explicitly bound connect/pool waits to 5 seconds and read/write inactivity to 20 seconds. Timeouts become sanitized `*_TIMEOUT` dependency errors. These are per-request inactivity limits, not a total deadline for a multi-request torrent inventory. A poll taking over 30 seconds is reported as `POLL_OVERDUE` and remains isolated from dispatch. No attempt is made to kill threads or interrupt a task to recover polling.

## Health interpretation

The authenticated `/api/v1/health/ready` response and `python -m app.ops health` expose:

- `liveness`: the health reporter is alive; its durable timestamp is refreshed every 2 seconds. Reads older than 15 seconds become `STALE` / `UNKNOWN`.
- `dispatch`: `READY` for an idle dispatcher checked within 10 seconds, `BUSY` for an active task whose database owner, fencing epoch and unexpired lease still match, `STALLED` for an idle dispatcher without a recent check, `QUEUE_OVERDUE` for eligible tasks waiting over 10 seconds while locally idle, or `LEASE_LOST` when an active task no longer has valid authority. Provider degradation is reported independently. Docker health succeeds for fresh `READY` or `BUSY`, including provider outages.
- `task`: active task identifier/kind, verified lease status/expiry and, for inventory, persisted checkpoint counts, checkpoint timestamp and age. Counts change at the existing scan checkpoints. Heartbeat freshness proves lease renewal, not media-processing progress; an old checkpoint is visible evidence for diagnosis, never a timeout or automatic restart condition. Enumeration, hashing and probing can legitimately take a long time.
- `queue`: eligible task count, oldest eligibility age and an actionable diagnostic. Future `run_after` values and `BLOCKED` tasks are excluded. Overdue work behind an active task is `WAITING_FOR_ACTIVE_TASK`; idle overdue work is `DISPATCH_OVERDUE`, also emitted as a sanitized structured log event.

Compose health probes run every 5 seconds with a 15-second startup grace. Docker health status alone does not restart a container; this change adds no watchdog/autoheal mechanism. Do not connect an automatic restart policy to task duration or checkpoint age.

## Diagnosis and controlled recovery

For `DISPATCH_OVERDUE`, compare `last_dispatch_at`, heartbeat age, queue age and active lease evidence; inspect PostgreSQL connectivity/locks and Worker structured logs. If the health reporter itself cannot access PostgreSQL, its durable heartbeat becomes stale. Missing or stale evidence is not permission to clear leases or replay mutations. Preserve the task, resource leases and operation journal before any separately authorized controlled restart. For `BUSY`, inspect progress/checkpoint age and storage/provider state without interrupting a legitimate scan.

Observability never claims tasks, resets attempts, changes `run_after`, deletes leases, retries destructive work or restarts the Worker. Restart recovery continues through the existing PostgreSQL `SKIP LOCKED` claim, expired lease reconciliation, incremented fencing epoch, resource reservations and operation journal. All write gates, approvals, ownership checks and idempotency rules remain in force. This PR performs no deployment, production scan control, media changes, torrent changes or permission activation.

## Regression evidence

- `tests/acceptance/test_worker_queue.py`: unavailable, timed-out, unexpected-failure and held-open provider polls for both providers; inventory claimed within 10 seconds; next scan after long-running work; independent health/progress; overdue diagnostics without queue mutation; restart fencing and single recovered execution.
- `tests/contracts/test_adapters.py::test_provider_calls_have_bounded_timeouts_and_safe_errors`: connect/read/write/pool timeout bounds and sanitized dependency errors.
- `tests/contracts/test_worker_health.py`: stale process evidence, malformed/missing timestamps and healthy dispatch during provider degradation.
- Existing workflow/recovery, inventory idempotency, destructive safety and security regressions remain mandatory in CI.

Run `ViMag CI` and `ViMag Security` for the exact PR head. The separate PR links to their final results; local Windows checks do not substitute for Linux PostgreSQL, ffprobe, Jellyfin and container security evidence.
