import json, os, sys, urllib.request, urllib.error

env = {}
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
TOKEN, BASE = env["AIRTABLE_TOKEN"], env["AIRTABLE_BASE_ID"]
URL = f"https://api.airtable.com/v0/meta/bases/{BASE}/tables"


def call(method, url, body=None):
    req = urllib.request.Request(
        url, method=method, data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print("ERROR", e.code, e.read().decode())
        sys.exit(1)


def text(n): return {"name": n, "type": "singleLineText"}
def long(n): return {"name": n, "type": "multilineText"}
def select(n, choices): return {"name": n, "type": "singleSelect", "options": {"choices": [{"name": c} for c in choices]}}
def link(n, tid): return {"name": n, "type": "multipleRecordLinks", "options": {"linkedTableId": tid}}
DT = {"dateFormat": {"name": "iso"}, "timeFormat": {"name": "24hour"}, "timeZone": "utc"}
def created(n): return {"name": n, "type": "createdTime"}
def modified(n): return {"name": n, "type": "lastModifiedTime"}
def dtime(n): return {"name": n, "type": "dateTime", "options": DT}
def integer(n): return {"name": n, "type": "number", "options": {"precision": 0}}
def decimal(n): return {"name": n, "type": "number", "options": {"precision": 4}}


def create(name, fields):
    existing = {t["name"]: t for t in call("GET", URL)["tables"]}
    early = [f for f in fields if f["type"] in ("createdTime", "lastModifiedTime")]
    base = [f for f in fields if f not in early]
    if name in existing:
        t = existing[name]
        print("exists", name, t["id"])
    else:
        t = call("POST", URL, {"name": name, "fields": base})
        print("created", name, t["id"])
    have = {f["name"] for f in t["fields"]}
    for f in early:
        if f["name"] not in have:
            call("POST", f"{URL}/{t['id']}/fields", f)
            print("  added", f["name"])
    return t["id"]


sr = create("Support Requests", [
    text("request_id"), text("slack_user_id"), text("slack_message_ts"), long("description"),
    select("status", ["NEW", "AI_IN_PROGRESS", "AWAITING_FEEDBACK", "AWAITING_ESCALATION",
                      "TICKET_CREATED", "RESOLVED", "CLOSED_NO_TICKET"]),
    select("feedback_outcome", ["RESOLVED", "UNRESOLVED", "UNKNOWN"]),
    select("closure_reason", ["RESOLVED", "TIMEOUT", "ESCALATION_DECLINED", "TICKET_CREATED"]),
    created("created_at"), modified("updated_at")])

ai = create("AI Sessions", [
    text("session_id"), link("request_id", sr), long("answer"), long("sources"),
    select("outcome", ["ANSWERED", "NO_RELIABLE_ANSWER", "FAILED"]), created("created_at")])

create("Retrieval Logs", [
    text("retrieval_id"), link("session_id", ai), text("document_id"), text("document_version"),
    integer("rank"), decimal("score")])

create("IT Tickets", [
    text("ticket_id"), link("request_id", sr),
    select("status", ["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"]),
    text("assigned_to"), created("created_at"), dtime("resolved_at")])

create("Operational Events", [
    text("event_id"), link("request_id", sr),
    select("event_type", ["REQUEST_CREATED", "AI_ANSWER_DELIVERED", "FEEDBACK_RECEIVED",
                          "ESCALATION_CONFIRMED", "TICKET_CREATED", "TIMEOUT_CLOSED", "WORKFLOW_ERROR"]),
    select("component", ["SLACK", "N8N", "RAG", "AIRTABLE"]),
    text("error_code"), created("timestamp")])
