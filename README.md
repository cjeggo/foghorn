# security-testing-platform

n8n-orchestrated automated security testing: recon, attack-surface scanning, and (opt-in) web/API fuzzing, SQL injection testing, device-exposure lookups, and OSINT correlation, using open-source tooling.

Layers onto the existing `n8n-local` podman stack rather than duplicating it — see `docs/recon-workflow-design.md` for the full design and rationale.

## Run

From `~/repo/n8n-local`:

```
podman-compose -f docker-compose.yml -f ../security-testing-platform/docker-compose.override.yml up -d --build
```

Add `--profile fuzzing` to also start the OWASP ZAP sidecar (only needed for the web-vuln-scan branch).

n8n UI: http://localhost:5678

## Layout

- `Dockerfile.n8n` — extends the stock n8n image with `dig`, `nmap`, `sqlmap`, `recon-ng`.
- `docker-compose.override.yml` — layers the custom build + ZAP sidecar onto `n8n-local`'s stack.
- `workflows/` — n8n workflow JSON, kept in sync with the running instance via `scripts/n8n_sync.py`.
- `scripts/n8n_sync.py` — `status` (show repo/live drift), `export` (live → repo), `deploy` (repo → live, activates, re-links sub-workflow ids on a fresh instance). Needs `N8N_API_KEY` (env or repo-root `.n8n-api-key`, gitignored). **Run `export` after editing workflows in the n8n UI; run `deploy` after editing the JSON.**
- `docs/` — design docs.

Scan reports land in `n8n-local/shared/recon/` (reuses the existing `./shared` bind mount).
