# qBittorrent integration and isolated fixture

Observed installation at kickoff: qBt 5.2.0, Web API 2.15.1. Live write semantics remain an independent G-01 gate. The current baseline is whatever the first authenticated snapshot observes, not a hardcoded count of 92.

## Authentication and discovery

Worker reads `/run/secrets/qbt_api_key` and sends `Authorization: Bearer`. A key has installation-wide privileges and stays Worker-only. Empty API-key configuration can use separate username/password secret files; 200 or 204 login is accepted only with a cookie and a verified authenticated GET. Cookie names are not hardcoded. A 401/403 blocks processing; there is no password guessing, auth bypass or retry with alternate credentials. Host-header/CSRF protections remain enabled; the allowed internal endpoint must work without relaxing them.

First successful read-only enumeration is an immutable legacy baseline. Removed/re-added hashes receive a new generation but cannot bypass legacy protection. Existing or ambiguous entries stay `LEGACY_READ_ONLY` / `EXTERNAL_UNMANAGED`. No normal job can write them. After separately authorized cutover, new eligible torrents are discovered automatically only when generation, added time, category, Manual TMM, local save path, completion and stable inventory all agree.

Manual TMM fixture add sends `autoTMM=false`, explicit `savepath=/downloads/complete`, one exact category and a stopped state. Read back the actual settings. `temp_path_enabled=false` means incomplete bytes may be in `complete`; file presence is never completion proof. `progress=1`, `amount_left=0`, stable completed file inventory and safe qBt state are required.

## Transfer verification

Simple flat single-file torrents use `renameFile` and qBt `setLocation` into the canonical library folder. Multi-file/season/mixed torrents keep their original tree in `/torrent-store/<instance-id>` and receive Jellyfin hardlinks. Preserve all non-media torrent files in the store. One parent controls one physical move/recheck; children have independent identities, paths, subtitles and publication.

For every command, PostgreSQL intent commits first. The Worker rechecks ownership, generation, policy, plan, lease and root containment. It never sends `hashes=all`, delete, global preferences/category writes, or independent filesystem renames of active torrent bytes. An accepted command is not completion. After restart/timeout, observe qBt and files; do not replay an uncertain command.

NAS size and SHA-256, qBt mapping, an observed recheck followed by complete pieces, and original paused/queued/ratio/force policy are required. Zero upload speed is healthy when there are no peers. Seeding capability is restored before enrichment. Jellyfin outage leaves the NAS torrent seeding and publication pending.

## Postdeployment sequence (only after actual image publication)

1. Validate the immutable manifest, architecture, private Traefik access, all secrets, rotated Jellyfin token, DB restore, NAS UID/ACL and mount proofs. Start with `WRITE_ENABLED=false`.
2. Save a private baseline of actual torrents and relevant qBt preferences/categories. Back up config/fastresume according to the running installation's safe backup procedure. Do not publish hashes, tracker URLs, cookies or inventories.
3. Establish test-library Movies/Shows paths and exclude store/quarantine. Verify no overlapping indexing and NFO saver ownership conflicts.
4. Generate **one** harmless original synthetic media torrent. Never use a legacy torrent or an existing movie. Record its expected hash privately before add; on an ambiguous timeout, inspect rather than add again.
5. Permit only this new torrent instance through the scoped operational authorization record. Keep general automatic intake and the global write switch disabled outside the isolated fixture process. Add explicitly Manual; do not change the global TMM default or category paths.
6. Drive inspection, review if needed, exact plan, move, recheck, hardlinks where applicable, Jellyfin recognition and final seed checks. Capture actual results, not API response codes alone.
7. Compare baseline preferences and legacy identities before/after. Preserve the new torrent's seeding bytes on failure. Cleanup must pass the separate staging-only proof. No library/quarantine purge.

Production-wide cutover is a separate authorization and requires applicable G-01..G-06/G-DB-01 evidence. RC1 deployment and one fixture do not authorize it.

Primary contracts: [qBt API](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-%28qBittorrent-5.0%29), [API-key authentication](https://github.com/qbittorrent/qBittorrent/wiki/API-Key-Authentication-%28%E2%89%A5v5.2.0%29).
