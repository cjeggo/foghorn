#!/usr/bin/env python3
"""Keep workflows/*.json in sync with a running n8n instance.

The repo drifted behind the live instance once already (a Section 6/7 fix made
in the n8n UI was never exported, then a blind deploy clobbered it). This is the
fix: one command to pull live -> repo, one to push repo -> live, one to show drift.

Workflows are matched between repo and server by NAME, not id - ids are per
instance, so this also handles deploying to a fresh n8n (e.g. the on-prem
server): it creates missing workflows and rewrites executeWorkflow references
and the `id` field to the new ids.

Usage:
    scripts/n8n_sync.py status          # show repo vs live drift
    scripts/n8n_sync.py export          # live  -> workflows/*.json
    scripts/n8n_sync.py deploy          # workflows/*.json -> live (+ activate)

Config (env, or a repo-root .n8n-api-key file for the key):
    N8N_URL       default http://localhost:5678
    N8N_API_KEY   n8n public-API key (Settings -> API in the n8n UI)
"""
import json
import os
import sys
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF_DIR = os.path.join(REPO, "workflows")
BASE = os.environ.get("N8N_URL", "http://localhost:5678").rstrip("/")

KEEP = ("name", "nodes", "connections", "settings")


def api_key():
    k = os.environ.get("N8N_API_KEY")
    if k:
        return k.strip()
    path = os.path.join(REPO, ".n8n-api-key")
    if os.path.exists(path):
        return open(path).read().strip()
    sys.exit("No API key: set N8N_API_KEY or create .n8n-api-key (n8n UI -> Settings -> API).")


KEY = None


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE}/api/v1{path}", data=data, method=method,
        headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:400]}")


def server_workflows():
    """name -> full server workflow object"""
    out, cursor = {}, None
    while True:
        q = "/workflows?limit=100" + (f"&cursor={cursor}" if cursor else "")
        page = call("GET", q)
        for w in page.get("data", []):
            out[w["name"]] = w
        cursor = page.get("nextCursor")
        if not cursor:
            return out


def local_files():
    return [os.path.join(WF_DIR, f) for f in sorted(os.listdir(WF_DIR)) if f.endswith(".json")]


def canon(w):
    return {k: w[k] for k in KEEP if k in w}


def body_sig(w):
    c = canon(w)
    c.pop("name", None)
    return json.dumps(c, sort_keys=True)


def write_file(path, wf, wid):
    doc = canon(wf)
    doc["id"] = wid
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")


def cmd_status():
    srv = server_workflows()
    drift = 0
    for path in local_files():
        local = json.load(open(path))
        name = local["name"]
        s = srv.get(name)
        tag = os.path.basename(path)
        if not s:
            print(f"  MISSING on server : {tag} ({name})")
            drift += 1
        elif body_sig(local) != body_sig(s):
            print(f"  DRIFT             : {tag} ({name}) - repo and live differ")
            drift += 1
        else:
            print(f"  in sync           : {tag}")
    extra = set(srv) - {json.load(open(p))["name"] for p in local_files()}
    for name in sorted(extra):
        print(f"  on server, no file: {name} (id {srv[name]['id']})")
    print(f"\n{drift} workflow(s) drifted." if drift else "\nrepo and live are in sync.")
    return drift


def cmd_export():
    srv = server_workflows()
    for path in local_files():
        name = json.load(open(path))["name"]
        s = srv.get(name)
        if not s:
            print(f"  skip {os.path.basename(path)} - not on server")
            continue
        write_file(path, s, s["id"])
        print(f"  wrote {os.path.basename(path)} <- live (id {s['id']})")


def cmd_deploy():
    srv = server_workflows()
    files = local_files()
    docs = {p: json.load(open(p)) for p in files}
    id_map = {}  # old id in repo -> deployed id

    for path, local in docs.items():
        name = local["name"]
        payload = canon(local)
        s = srv.get(name)
        if s:
            call("PUT", f"/workflows/{s['id']}", payload)
            deployed_id = s["id"]
            action = "updated"
        else:
            created = call("POST", "/workflows", payload)
            deployed_id = created["id"]
            action = "created"
        old_id = local.get("id")
        if old_id:
            id_map[old_id] = deployed_id
        local["_deployed_id"] = deployed_id
        print(f"  {action:8} {os.path.basename(path)} (id {deployed_id})")

    # Re-link executeWorkflow references + `id` fields if any id changed.
    changed = {o: n for o, n in id_map.items() if o != n}
    if changed:
        print("  re-linking sub-workflow references:", changed)
        for path, local in docs.items():
            touched = False
            for node in local.get("nodes", []):
                wf = node.get("parameters", {}).get("workflowId")
                if isinstance(wf, dict) and wf.get("value") in changed:
                    wf["value"] = changed[wf["value"]]
                    touched = True
            if touched:
                call("PUT", f"/workflows/{local['_deployed_id']}", canon(local))
                print(f"    re-pushed {os.path.basename(path)} with updated refs")

    # Persist deployed ids + any re-linked refs back to the files.
    for path, local in docs.items():
        write_file(path, local, local.pop("_deployed_id"))

    for path, local in docs.items():
        wid = json.load(open(path))["id"]
        call("POST", f"/workflows/{wid}/activate")
    print("  all activated.")


def main():
    global KEY
    KEY = api_key()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"status": cmd_status, "export": cmd_export, "deploy": cmd_deploy}.get(
        cmd, lambda: sys.exit(__doc__)
    )()


if __name__ == "__main__":
    main()
