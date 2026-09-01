# security-testing-platform

n8n-orchestrated automated security testing. A single authorised operator triggers
a scan from a web form; the platform runs reconnaissance, attack-surface mapping,
and a set of opt-in active tests, then produces a structured Markdown report whose
"what to do next" section is **deterministic** — every finding is routed to a
specific tool by rule, not guessed by an LLM.

It is a **discovery / attack-surface-mapping tool**: it assesses a target as an
anonymous external attacker would. It does not authenticate and it does not run
exploits — it names the exploit and leaves it to a human (or the separate,
parked exploitation phase).

Layered as a podman compose override on an n8n + Postgres + Qdrant base stack
rather than duplicating it — see [Setup](#setup).

Status: PoC. Runs locally against the bundled test targets; not yet pointed at
any real target.

---

## Rules of engagement

Everything here applies **only against a target with explicit, documented
authorisation** — the `authorized` checkbox on the form is a UI gate, not a
substitute for a signed-off scope. Within an authorised engagement the hard
technical boundary is: never encrypt target data, never wipe or destroy data,
never cause denial-of-service or degrade availability. Active tests that touch
those lines (query-depth bombing, password brute-force, DoS templates) are
deliberately excluded even where a tool supports them.

---

## Setup

The deployment below is the **PoC setup**: a single host, every service local,
placeholder secrets, and the bundled deliberately-vulnerable test targets. Notes
marked **On real hardware** flag what would change for an actual deployment.

The platform is a custom n8n image (recon tooling baked in) plus an OWASP ZAP
sidecar, layered as a compose override onto the
[`self-hosted-ai-starter-kit`](https://github.com/n8n-io/self-hosted-ai-starter-kit)
(n8n + Postgres + Qdrant). It runs under **podman**.

### 1. Prerequisites

- `podman` with `podman compose`
- **Ollama** reachable from the host — used only for the two LLM-authored report
  sections; the rest of the pipeline degrades gracefully if it's down
- ~15 GB free disk for the image build — `nmap` + NSE, the `wpscan` vulnerability
  DB, `nuclei` templates and a SecLists wordlist are all baked in at build time

### 2. Directory layout

Clone this repo and the base stack as **siblings** — the override compose
references the base stack with `../` paths:

```
<parent>/
  security-testing-platform/   # this repo
  n8n-local/                   # the base stack (next step)
```

### 3. Base stack

```
git clone https://github.com/n8n-io/self-hosted-ai-starter-kit.git n8n-local
cd n8n-local
cp .env.example .env
mkdir -p shared/recon
```

The base compose puts n8n, Postgres and Qdrant on a shared `demo` network,
mounts `./shared` into the n8n container, and sets
`OLLAMA_HOST=host.containers.internal:11434` so n8n can reach an Ollama running
on the host.

> **On real hardware:** `.env.example` ships throwaway values
> (`N8N_ENCRYPTION_KEY=super-secret-key`, a default Postgres password, a
> placeholder JWT secret). Replace all of them before the stack is reachable
> from anything but localhost.

### 4. Ollama

```
ollama pull qwen3:8b
```

> **On real hardware:** a larger model (14–32B class) noticeably improves the
> generated report sections — see `docs/future-improvements.md`.

### 5. Build and start

```
cd n8n-local
podman compose \
  -f docker-compose.yml \
  -f ../security-testing-platform/docker-compose.override.yml \
  --profile fuzzing up -d --build
```

`--profile fuzzing` also starts the ZAP sidecar, needed for the `webVulnScan`
branch and AJAX-spider endpoint discovery. The first build is slow (tool
downloads, the wpscan DB, nuclei templates). n8n comes up at
`http://localhost:5678`.

### 6. First-run n8n

Open `http://localhost:5678` and create the owner account (local, one time).

### 7. Ollama credential

In n8n: **Credentials → New → Ollama**, base URL
`http://host.containers.internal:11434`. Name it anything.

### 8. Deploy the workflows

`scripts/n8n_sync.py` pushes `workflows/*.json` into the running instance —
creating the six workflows, re-linking the sub-workflow references, and
activating them.

```
# in n8n: Settings → n8n API → create an API key
cd security-testing-platform
echo '<the key>' > .n8n-api-key        # gitignored
scripts/n8n_sync.py deploy
```

Then open **Sub - Single Host Recon → Ollama Chat Model** and set its credential
to the one from step 7 — the credential binding is the one thing `n8n_sync.py`
can't carry.

### 9. Test targets

`test-targets/docker-compose.yml` is a **separate** stack (not tied to n8n's
lifecycle) — deliberately-vulnerable ground-truth targets on the same `demo`
network:

| Target | Image | Exercises |
|---|---|---|
| `juice-shop` | `bkimminich/juice-shop` | SPA + REST API, JS-bundle route extraction, AJAX spider, security headers |
| `sqli-labs` | `acgpiano/sqli-labs` | SQL injection ground truth (sqlmap) |
| `metasploitable2` | `tleemcjr/metasploitable2` | vulnerable network services, nmap NSE, known-CVE matching |
| `wordpress` | `wordpress:6.5` + MariaDB | clean modern WordPress — "no known vulns" baseline |
| `wordpress-vuln` | `wordpress:4.7.0` + MariaDB | WordPress with ~120 real core CVEs (NVD), XML-RPC, user enum |
| `dvga` | `dolevf/dvga` | GraphQL: introspection, field-suggestion leak, batching, GET queries |

```
podman compose -f test-targets/docker-compose.yml up -d
test-targets/wp-setup.sh          # finishes the WordPress installs, pins site URLs
```

The vulnerable targets publish host ports on `192.168.56.1` (a host-only
adapter) so a testing VM can reach them but the wider LAN cannot — edit the
compose to `127.0.0.1` if you have no such adapter. metasploitable2's privileged
ports use a `+10000` host-side offset (rootless podman can't bind below 1024).

> **On real hardware:** don't run this stack anywhere but an isolated lab.

### 10. Run a scan

Open the **Recon / Attack-Surface Scan** form in n8n (the Form Trigger node on
`recon-attack-surface-scan` shows its production URL). Enter a target, tick
**authorized**, pick a `scanIntensity`, tick any active-test toggles, submit. The
report lands in `n8n-local/shared/recon/<target>-<timestamp>.md`.

### Keeping workflows in sync

The running instance and `workflows/*.json` drift apart if the workflows are
edited in the UI without exporting (this has bitten the project):

```
scripts/n8n_sync.py status     # show repo vs live drift
scripts/n8n_sync.py export     # live  -> workflows/*.json
scripts/n8n_sync.py deploy     # workflows/*.json -> live (+ activate, re-link sub-workflow ids)
```

Needs `N8N_API_KEY` (env, or the gitignored `.n8n-api-key` at the repo root).
**Run `export` after editing in the UI; run `deploy` after editing the JSON.**
`deploy` matches workflows by name, so it also stands the platform up on a fresh
n8n instance.

---

## What it does

The operator picks a `scanIntensity` (`dns-only` / `dns+ports` / `dns+ports+web`)
and optionally ticks any of the active-test toggles. Everything else is automatic.

### Always (per intensity)

- **DNS** — A/AAAA/MX/NS/TXT/SOA
- **Subdomains** — Certificate Transparency logs (crt.sh)
- **WHOIS**
- **Cloud / network attribution** — ASN, CNAME chain, cloud provider, Azure region;
  a deterministic target profile synthesised from the evidence
- **Port scan** (`dns+ports`+) — `nmap -sV --version-light` + safe NSE scripts
  (`banner`, `ftp-anon`, `smb-os-discovery`, `vulners`), top 100 ports
- **Known-CVE matching** — nmap `vulners` output, deduped, split into
  *exploitable* (public exploit at matching CVSS) vs *research-only*
- **TLS / certificate analysis** — `testssl.sh` (protocol/cipher/cert grading, SANs)
- **Web app detection + shallow crawl** (`dns+ports+web`) — bounded crawl,
  same-origin, depth 2
- **Content discovery** — static wordlist (SecLists common.txt) + real paths
  pulled out of the compiled JS bundle, baselined against a soft-404 signature
- **AJAX-spider endpoint discovery** — ZAP browser-driven, finds SPA routes and
  parameterised requests that server-rendered HTML never exposes
- **Security headers + cookie flags** audit
- **Forms / parameter surface** extraction
- **Vulnerable components** — `retire.js` against the fetched JS, independently
  verified against OSV.dev
- **Sensitive file exposure** — flags backup/config/source-control patterns
  (`.env`, `.git/`, `.bak`, …) and fetches a content excerpt to confirm
- **WordPress** (auto, if detected) — `wpscan` enumeration (core/plugin/theme
  versions, users, XML-RPC, readme, backups), then **CVE lookup against NVD**
  by CPE (no paid WPScan token). Exploit-backed CVEs → Metasploit; the rest → searchsploit
- **GraphQL** (auto, if an endpoint is found) — introspection, field-suggestion
  schema leak, queries-over-GET (CSRF surface), array batching (amplification)

### Opt-in (form toggles, each with its own consent line)

- **`sqlInjectionTest`** — `sqlmap` against discovered parameterised endpoints
  (`--level=1 --risk=1`), escalates to `--dump` framing on a confirmed hit
- **`webVulnScan`** — ZAP spider + active scan
- **`nucleiScan`** — nuclei templated scan (`http/exposures`,
  `http/misconfiguration`, `http/default-logins`) against the origin; CVE
  findings deduped against nmap-vulners and the WordPress NVD list

### The report

1. MITRE ATT&CK reconnaissance (TA0043) coverage
2. Attack-surface summary + **deterministic executive risk summary** (severity,
   count, most-serious finding — computed, not LLM)
3. DNS / WHOIS / subdomains
4. Open ports & services
5. **Confirmed findings** — evidence-backed, per category
6. **"If I were attacking this"** — every finding routed to `{tool, command,
   rationale, verification}` **by rule**. Reinvented-from-the-Kali-review: the
   LLM narrates, it does not choose tools
7. **ATT&CK-aligned next-phase plan** — LLM-authored, constrained to the layers
   and tools Section 6 actually surfaced
8. Testing coverage & gaps — explicit disclosure of what was and wasn't tested

Reports are per-host. A CIDR (≤ /24) fans out to one report per live host plus a
network-sweep summary.

---

## Layout

- `Dockerfile.n8n` — n8n rebuilt on `node:20-alpine` with the tooling baked in:
  `dig`, `nmap` + NSE, `whois`, `sqlmap`, `recon-ng`, `gobuster` + SecLists,
  `testssl.sh`, `retire.js`, `wpscan` + vuln DB, `nuclei` + templates
- `docker-compose.override.yml` — custom n8n build + ZAP sidecar over `n8n-local`
- `test-targets/` — the vulnerable-target stack + `wp-setup.sh`
- `workflows/` — n8n workflow JSON (source of truth via `n8n_sync.py`):
  - `recon-attack-surface-scan.json` — the form entry point + CIDR fan-out
  - `sub-single-host-recon.json` — the main pipeline (~50 nodes)
  - `sub-sql-injection-test.json`, `sub-web-vulnerability-scan.json`,
    `sub-wordpress-scan.json`, `sub-nuclei-scan.json` — dispatched heavy tools
- `scripts/n8n_sync.py` — repo ↔ live workflow sync
- `docs/future-improvements.md` — parked ideas, not committed work
