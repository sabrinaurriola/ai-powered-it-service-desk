# Development Checkpoint

**Date:** 2026-11-24 · **Checkpoint:** after WF-03 standalone validation · **Next:** WF-01 button interactions + WF-03 integration

This document records what exists, how far each part has been verified, the decisions behind it, and what to do next, so work can resume without re-deriving context. Design intent lives in docs 01–04; this file is the status record.

## Maturity levels

| Level | Meaning |
|---|---|
| **Designed** | Specified in the docs; nothing built. |
| **Implemented** | Built and exported into this repository. |
| **Runtime validated** | Executed in n8n against real Slack and Airtable in controlled, isolated tests. |
| **Integration validated** | Verified across workflow boundaries (for example WF-01 calling WF-03). |

## Component status

| Component | Designed | Implemented | Runtime validated | Integration validated |
|---|---|---|---|---|
| Airtable data model (5 tables, incl. `response_deadline`) | Yes | Yes | Yes (written by WF-01 and WF-03) | Partial (WF-01 end to end; WF-03 standalone) |
| Slack app (Events API `message.im` over HTTP) | Yes | Yes | Yes | Partial (events and messages work; interactivity not configured) |
| WF-01 Entry A: DM intake | Yes | Yes | Yes (production webhook) | Yes for Slack → n8n → Airtable → Slack; not with WF-03 |
| WF-01 Entry B: button interactions | Yes | No | No | No |
| WF-02: RAG assistance | Yes | No | No | No |
| WF-03: ticket creation | Yes | Yes | Yes, standalone with pinned input | **No** |
| WF-04: document ingestion | Yes | No | No | No |
| WF-05: timeout handling | Yes | No | No | No |
| Shared Error Trigger workflow | Yes | No | No | No |
| Local error branches in WF-03 | Yes | Yes | Yes | No |
| Offline RAG evaluation | Yes | No (no dataset or script yet) | No | No |
| Repository tooling (`validate_workflow.py`, `sanitize_export.py`) | — | Yes | Used on every export | — |

**WF-03 classification:** implemented, functionally validated for the tested standalone scenarios, ready for integration testing. Not production-ready.

## What has been verified

### WF-01 Entry A (production webhook)
- Slack DM creates one Support Request with `status = NEW`, `request_id`, Slack user id, message timestamp and description.
- Edited messages and channel messages are ignored.
- A replayed event takes the "not new" branch: no second record and no second Slack message.
- The bot replies with the request id and the two buttons.

### WF-03 (standalone, pinned input)
Passed: direct ticket creation; existing-ticket reuse; sequential duplicate prevention; invalid action rejection; invalid request-state rejection; Support Request moves to `TICKET_CREATED`; `INVALID_TICKET_REQUEST` logged; Slack confirmation delivered; simulated Slack failure (`channel_not_found`) keeps the ticket and state; `SLACK_CONFIRMATION_FAILED` logged; forced duplicate ticket detected and logged without deleting. Test data was cleaned up.

Corrected during runtime debugging: Airtable nested field references (`fields.*`), empty-item handling after a search with no match, Switch routing conditions, action validation, and the Slack recipient expression.

`response_deadline` was empty after execution, but clearing a previously populated value was not demonstrated.

## Key technical decisions

| Decision | Reason |
|---|---|
| Deterministic ids: `REQ-<slack_user_id>-<message_ts>`, `TKT-<request_id>` | A replayed event or retried call resolves to the same record, so duplicate checks are exact lookups. |
| Slack Events over HTTP, Socket Mode off | Socket Mode blocked webhook delivery to n8n during testing. |
| Standard n8n nodes only | The instance is managed; server access, environment variables and `crypto` are not assumed. |
| Airtable is the source of truth for request state; n8n validates transitions | Per the architecture; the buttons workflow must read current status before acting. |
| WF-03 decision order: Reuse → Create → Reject | An existing ticket must never be recreated; an invalid state must be rejected and logged, not silently reused. |
| `airtable_record_id` accepted by WF-03 but not trusted | The record found by `request_id` is authoritative. |
| Duplicate check runs before the Slack confirmation; it logs and never deletes | A Slack outage must not hide a suspected duplicate; deleting automatically could destroy a legitimate ticket. |
| Slack failures keep the ticket; confirmation is retried (3 attempts) and logged | Notification must be independent of ticket creation (NFR-01). |
| Local error branches log with `request_id`; a global Error Trigger is only a safety net | The global trigger does not carry the original request data. |
| Exports are sanitized before commit | n8n exports include credential references, instance id, webhook ids and pinned test data. |
| RAG retrieval settings to live in one versioned file, `config/rag_config.json` | Offline evaluation and WF-02 must use identical settings; **how the file reaches n8n is still undecided**. |

## Known limitations

- Airtable has no unique constraints or transactions; duplicate prevention is best effort. Sequential replay was tested; concurrent execution was not.
- Buttons are displayed but not wired to anything.
- Slack signature verification is not configured; behaviour of the Slack Trigger node on this instance is unconfirmed.
- No timeouts run: nothing closes requests that wait indefinitely (WF-05 not built).
- No AI path exists yet. `ANSWER_AVAILABLE` / `ESCALATION_REQUIRED` outcomes have no producer.
- `response_deadline` is written nowhere yet; WF-03 clears it, WF-01 Entry B will set it.
- Single-select values (statuses, event types, components) were chosen by the project and are defined in [03_data_model.md](03_data_model.md).
- The Airtable base and table ids appear in workflow parameters.
- All scenarios are simulated. No real employees, no measured business outcomes.

## Outstanding tests

- [ ] `confirmed_escalation` from `AWAITING_ESCALATION` creates a ticket (needs WF-01 or a hand-set status).
- [ ] A populated `response_deadline` is cleared when the ticket is created.
- [ ] End to end: DM → **Create ticket** button → WF-03 → Slack confirmation.
- [ ] Double click and stale button on an already-processed request.
- [ ] Concurrent identical executions of WF-03.
- [ ] Slack retry and failure behaviour under repeated delivery.
- [ ] Load and operational resilience.

## Next development priorities

1. **WF-01 Entry B, direct-ticket route.** Webhook for Slack interactivity; acknowledge immediately; read the current request status and reject stale or invalid actions; map the **Create ticket** button (`ticket_choice`) to WF-03 with `action = direct_ticket`; do not set `TICKET_CREATED` in WF-01 (WF-03 owns it). Then run the integration tests above.
2. Decide how Slack signature verification is done without a Code node, and test what the Slack Trigger node already does.
3. Entry B remaining routes with a **stub WF-02**: AI choice, feedback, escalation offer, decline; set `response_deadline` on `AWAITING_*` transitions. This also allows testing `confirmed_escalation`.
4. WF-05 timeouts, then WF-04 ingestion, WF-02 RAG, shared error workflow, offline evaluation.

Order follows [04_n8n_workflow_blueprints.md](04_n8n_workflow_blueprints.md). Do not start WF-02 before checking whether the native Pinecone and reranker nodes expose rank and score.

## Open questions

- Is the Slack interactivity URL reachable on the instance, and what acknowledgement time can n8n meet?
- Delivery of `rag_config.json` to n8n: fetch from a raw repository URL at the start of WF-02, or another route that needs no server access.
- Whether to replace the Airtable base and table ids in the workflow JSON with placeholders before publishing.

## Resuming work

- Environment: n8n 2.13.2 on a managed instance; Slack app with `message.im` events; Airtable base with the five tables. Credentials are created in n8n (Slack API; Airtable Personal Access Token) and are never stored in the repository. `.env` holds the Airtable token and base id for local scripts and is git-ignored.
- After importing a workflow: assign credentials, open each node once, test, then re-export and sanitize (see [n8n/README.md](../n8n/README.md)).
- Schema changes go through `airtable/build_schema.py` or the Metadata API, followed by a schema read to confirm; update [03_data_model.md](03_data_model.md) only after confirmation.
- Do not mark anything integration validated until it has run across a workflow boundary.

## Repository housekeeping

- `implementation_plan.md` in the repository root is an earlier working plan, partly superseded by this checkpoint. Decide whether to keep, move or delete it before publishing.
