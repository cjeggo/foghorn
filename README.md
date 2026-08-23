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
- `workflows/` — exported n8n workflow JSON (version-controlled copies of what's built in the running instance).
- `docs/` — design docs.

Scan reports land in `n8n-local/shared/recon/` (reuses the existing `./shared` bind mount).
