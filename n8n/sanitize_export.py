"""Strip instance-specific and test data from an n8n workflow export before it is committed.

Usage:
    python -I n8n/sanitize_export.py n8n/workflows/*.json          # rewrite in place
    python -I n8n/sanitize_export.py --check n8n/workflows/*.json  # report only, exit 1 if anything is left

Removed: top-level meta (instanceId), id, versionId; pinData contents; per-node credentials
(credential ids and names) and webhookId (part of the public webhook URL).
Node parameters, connections and settings are left untouched.
"""
import json
import sys
from pathlib import Path

args = [a for a in sys.argv[1:] if a != "--check"]
check_only = "--check" in sys.argv[1:]
dirty = False

for name in args:
    path = Path(name)
    wf = json.loads(path.read_text(encoding="utf-8"))
    removed = []

    for key in ("meta", "id", "versionId"):
        if key in wf:
            del wf[key]
            removed.append(key)
    if wf.get("pinData"):
        removed.append(f"pinData({', '.join(wf['pinData'])})")
    wf["pinData"] = {}
    for node in wf.get("nodes", []):
        for key in ("credentials", "webhookId"):
            if key in node:
                del node[key]
                removed.append(f"{node['name']}.{key}")

    if removed:
        dirty = True
        print(f"{path}: {'would remove' if check_only else 'removed'} {len(removed)} item(s): {', '.join(removed)}")
        if not check_only:
            path.write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        print(f"{path}: clean")

sys.exit(1 if (dirty and check_only) else 0)
