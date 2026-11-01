# RC1 security review notes

These notes explain intentional controls and tool findings; they do not waive failed release gates.

- API binds `0.0.0.0:8000` **inside** its container so Nginx can reach it. Production Compose publishes no API port. Bandit B104 is explicitly documented at that one call; it is not an internet exposure exception.
- ffprobe, ffmpeg fixtures and PostgreSQL tools use separate argv arrays, bounded timeouts and no shell. Executables and fixture generation parameters are operator/source-controlled. CLI paths are not an arbitrary web execution interface. Routine subprocess warnings are reviewed at the exact call sites.
- NFO reads are bounded and use `defusedxml`; DTD/entity content is rejected. Unknown or externally modified sidecars cannot auto-overwrite.
- SHA-256 protects file/plan/session evidence. SHA-1 appears only in the BitTorrent fixture's protocol-mandated info/piece hashes with `usedforsecurity=False`; it is not used for security decisions.
- Vue renders text through escaped bindings, uses no `v-html`, and bundles locally. Nginx CSP permits same-origin resources, blocks framing and external script execution. Service tokens never enter the browser bundle.
- Full runtime dependency audits and image reports are release artifacts. No vulnerability is reclassified as a passing integration test. The frontend pins patched Vue/Vite/Vitest and explicit patched glob/minimatch overrides; tests/build validate the compatible result.
- Linux filesystem tests run without bypassing a failed Windows symlink test. Actual CIFS runtime proof, token rotation and the isolated live torrent remain separate operational gates.
- No delete-library/purge endpoint exists. Quarantine approval never bypasses dependencies. Staging cleanup is single-file and proof-bound. Legacy torrents cannot be adopted on first startup or remove/re-add.

Source checks, container scan outcomes and actual publication/deployment state are recorded in the release report. Scanner image references and GitHub Actions are pinned to immutable digests/commits.
