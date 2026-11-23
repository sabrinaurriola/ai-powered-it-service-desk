"""Static checks for an n8n workflow export before importing it.

Usage: python -I n8n/validate_workflow.py n8n/workflows/<file>.json

Checks structure only. It cannot prove that parameters are accepted by the
node UI; open each node after import to confirm.
"""
import json
import re
import sys
from pathlib import Path

wf_path = Path(sys.argv[1])
versions = json.loads((Path(__file__).parent / "node_versions.json").read_text(encoding="utf-8"))
known = versions["nodes"]
unverified = versions.get("unverified", {})

errors, warnings = [], []
wf = json.loads(wf_path.read_text(encoding="utf-8"))

nodes = wf.get("nodes", [])
names = [n.get("name") for n in nodes]
ids = [n.get("id") for n in nodes]

for key in ("name", "nodes", "connections"):
    if key not in wf:
        errors.append(f"missing top-level key: {key}")
if len(set(names)) != len(names):
    errors.append("duplicate node names")
if len(set(ids)) != len(ids):
    errors.append("duplicate node ids")

for n in nodes:
    label = n.get("name", "?")
    for key in ("type", "typeVersion", "position", "id", "name", "parameters"):
        if key not in n:
            errors.append(f"{label}: missing {key}")
    t, v = n.get("type"), n.get("typeVersion")
    if t in unverified and t not in known:
        if v != unverified[t]:
            errors.append(f"{label}: typeVersion {v} != guessed {unverified[t]} for {t}")
        warnings.append(f"{label}: typeVersion {v} for {t} is a guess, not from the reference export")
    elif t not in known:
        warnings.append(f"{label}: type {t} not in reference export (unverified)")
    elif v != known[t]:
        errors.append(f"{label}: typeVersion {v} != {known[t]} for {t} in n8n {versions['n8n_version']}")
    if "credentials" in n:
        for cred in n["credentials"].values():
            if re.search(r"(?i)(token|secret|password|key)", json.dumps(cred)) and len(cred.get("id", "")) > 40:
                errors.append(f"{label}: credentials look like a secret")

for src, outs in wf.get("connections", {}).items():
    if src not in names:
        errors.append(f"connection source not a node: {src}")
    for branch in outs.get("main", []):
        for link in branch:
            if link["node"] not in names:
                errors.append(f"connection target not a node: {src} -> {link['node']}")

# Every expression that references another node must name an existing node.
text = json.dumps(wf)
for ref in set(re.findall(r"\$\('([^']+)'\)", text.replace("\\'", "'"))):
    if ref not in names:
        errors.append(f"expression references missing node: {ref}")

# Every non-trigger node should be reachable from a trigger.
targets = {l["node"] for o in wf.get("connections", {}).values() for b in o.get("main", []) for l in b}
for n in nodes:
    if n["name"] not in targets and "Trigger" not in n["type"] and "webhook" not in n["type"]:
        warnings.append(f"{n['name']}: no incoming connection")

for w in warnings:
    print("WARN ", w)
for e in errors:
    print("ERROR", e)
print(f"{len(nodes)} nodes, {len(errors)} errors, {len(warnings)} warnings (n8n {versions['n8n_version']} reference)")
sys.exit(1 if errors else 0)
