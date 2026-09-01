# Future improvements

Parked ideas, not committed work. Captured 2026-09-01 while the platform is
still a PoC — revisit once it's a formalised, funded project. Nothing here is
scheduled; there's a demo on Thursday 2026-09-04 and no appetite to expand
scope before funding.

## Guiding constraint for anything LLM-related

The platform's rule is **the LLM narrates, it never decides**. Every time an LLM
was given a decision with a computable answer (severity bucketing, tool
selection) it produced real bugs — see `recon-workflow-design.md`. Test for any
new LLM use: does the task have a correct computable answer? If yes, keep it
deterministic. LLMs are only for language, summarisation, and *advisory* triage
over data a human still sees in full.

All local Ollama today is `qwen3:8b`. It's adequate for narration, weak for
anything needing real domain knowledge.

---

## LLM: more leverage within the "narrate, don't decide" line

### 1. Network-sweep synthesis  (bounded, high value)

CIDR fan-out currently produces per-host reports plus a thin summary that's just
a host→filename table. The sub-workflow already returns full per-host findings to
the parent (`Dispatch Single Host Recon (Sweep)` → `Build Network Sweep
Summary`), so the data is there. Add a once-per-sweep LLM narrative over that
deterministic input: "hosts .12 and .40 run the same outdated Apache; the whole
/24 is missing HSTS; .40 is the only one exposing SSH."

- Lives in `recon-attack-surface-scan.json`. Needs an Ollama node + `chainLlm`
  added to that workflow (it has none today).
- **Testability gap:** needs a multi-host CIDR to exercise. Host discovery
  doesn't work on this podman setup for LAN ranges (see design doc). Might work
  pointed at the internal podman bridge subnet; otherwise untestable until the
  on-prem phase.

### 3. Executive "so what" paragraph  (bounded, high value)

Plain-English business-risk translation of the confirmed findings, sitting
*above* the deterministic Executive Risk Summary in Section 2, in a clearly
labelled generated block. "An anonymous visitor can enumerate your WordPress
admin usernames and the login page has no rate limiting." Serves the
non-technical demo audience directly.

- Lives in `sub-single-host-recon.json`. Add a `chainLlm` reusing the existing
  `Ollama Chat Model` node, fed from the same point as `Analyze & Plan Next
  Phase`; splice its output into the report in `Build Report File`.
- Runs on every single-host scan → testable now against the 6 targets.

### 6a. Self-consistency lint of Section 7  (cheap, keep whenever)

Before finalising, an LLM pass checks the generated Section 7 plan against the
deterministic Sections 5/6: "you pointed at Metasploit for a CVE that Section 5
marked research-only." Tight yes/no prompt, output is a short flag list,
appended as an advisory block only if non-empty. Catches the exact contradiction
class the fixes kept chasing. Reliability caveat: an 8b model linting an 8b
model's output — keep the prompt narrow.

### 6b. Senior-pentester tradecraft review  (high value, blocked on model)

An LLM in a senior-pentester role annotating Section 6's rule-generated commands:
"the deterministic command works, but against this WAF you'd want `--random-agent
--tamper=space2comment` for a more reliable result." A feedback loop, not a
rewrite — the rule-generated command stays primary, the model adds a labelled
*operator notes* annotation.

- **Blocked on model quality.** qwen3:8b's offensive knowledge is too shallow and
  dated to trust here. Needs the 32b-class model on the on-prem box. Gated by the
  model bake-off below.
- Risk to manage: this is the place "narrate" quietly becomes "decide
  tradecraft". Keep the annotation clearly secondary and labelled non-deterministic.

### Command validation  (mostly NOT an LLM problem)

Section 6 commands reference things that may not exist in the operator's
environment — e.g. wordlist paths that are wrong on a stock Kali. Fix
deterministically:

- Decide and **document** the target operator environment (Kali, presumably).
  Section 6 commands are written *for* that environment.
- Bake a manifest of that environment: real wordlist paths, package names, binary
  locations (`/usr/share/seclists/...`, apt package `seclists`, etc).
- Add a deterministic checker resolving every Section 6 command against the
  manifest; flag or rewrite ones referencing something absent.
- For the tool subset Foghorn's own image carries (nmap, sqlmap, gobuster,
  SecLists, wpscan, nuclei) it can `test -e` / `command -v` against its own
  filesystem for free.
- LLM's only role: help author/maintain the manifest and phrase fixes.
- **Hard line:** Foghorn must never *execute* these commands against the target —
  that's the human's step, out of scope. Validate against a manifest or Foghorn's
  own container, never a live dry-run at the target.

### 2. Run-over-run diff narrative  (blocked on state, defer to on-prem)

Deterministic diff between runs of the same target (new open port, WP version
moved backwards, cert now expiring, a path that appeared), LLM writes the "what
changed" paragraph. Enables the continuous-monitoring end state.

- **Blocked on state.** Needs somewhere to keep run history. n8n is a bad store,
  and a longitudinal record of a target's weaknesses is a more sensitive asset
  than any single scan — it has a custody/retention problem a stateless tool
  doesn't. Revisit in the on-prem phase with a proper store and a policy around
  it.

---

## Local model bake-off  (prerequisite for 6b)

Compare `qwen3:8b` against `qwen2.5:14b`, `qwen2.5:32b`, `gemma2:27b`,
`mistral-small:24b` across **all** the LLM tasks (Section 7 plan, plus 1/3/6
above), using the 6 test targets as a fixed eval set. Outcome decides the
production model for the on-prem box and whether 6b is viable.

Note: "Kimi" (Moonshot K2, ~1T MoE) is not a local option — no small variant
runs on a laptop or the on-prem box via Ollama.

---

## Explicitly rejected

- **LLM as tool-output parser** (fallback when the testssl/wpscan regex fails) —
  structured extraction on a small model is unreliable and it feeds findings.
  Fix the parser instead.
- **LLM choosing scan intensity / toggles** from a natural-language request —
  that's a decision, and the form is two fields.
- **Remediation advice** — wrong audience. Foghorn's report is attacker-framed by
  design; defender guidance is a different product.
