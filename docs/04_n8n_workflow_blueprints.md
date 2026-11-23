# n8n Workflow Node Blueprints

Implementation reference for the AI-Powered IT Service Desk MVP. Node names are indicative; some steps may require multiple nodes.

## WF-01 — Intake & Routing

**Entry A: New Slack DM**

| Step | Node | Action |
|---|---|---|
| 1 | Slack Trigger | Receive `message.im` events. |
| 2 | IF | Ignore bot messages, subtypes, and non-DM events. |
| 3 | Edit Fields | Extract user, channel, message timestamp, text; derive stable `request_id`. |
| 4 | Airtable Search → IF | Skip already registered Slack messages. |
| 5 | Airtable Create | Register Support Request as `NEW`. |
| 6 | Slack Send Message | Present **Try AI assistance** / **Create ticket** buttons. |

**Entry B: Slack button interactions (separate Webhook entry)**

| Step | Node | Action |
|---|---|---|
| 1 | Webhook + verification | Receive interactions, verify Slack signature, acknowledge promptly. |
| 2 | Edit Fields → Switch | Parse `request_id` and action: AI, direct ticket, resolved, unresolved, escalate yes/no. |
| 3 | Airtable Search → IF | Read current request state; reject stale or invalid transitions. |
| 4 | Airtable Update / Execute Sub-workflow | Update state; call WF-02 or WF-03 as appropriate. On entering `AWAITING_FEEDBACK` or `AWAITING_ESCALATION`, set `response_deadline` (now + configurable hours); clear it on closure or `TICKET_CREATED`. |
| 5 | IF → Slack Send Message | On `ANSWER_AVAILABLE`, send answer, sources, **Resolved / Still need help** buttons; otherwise offer **Create ticket / No, thanks**. |
| 6 | Airtable Update | Record confirmed resolution or declined escalation; never infer resolution from silence. |

**Failure branch:** If WF-02 errors, log locally, mark the open AI Session `outcome=FAILED`, and offer human support. An optional Slack message update can remove used buttons but is not a concurrency guarantee. Slack requests require timely acknowledgment; verify that n8n can process work after acknowledgment without losing events.

## WF-02 — RAG Assistance

| Step | Node | Action |
|---|---|---|
| 1 | Execute Sub-workflow Trigger | Receive `request_id`, Airtable record ID, and question. |
| 2 | Airtable Create | Open AI Session. |
| 3 | Embeddings + Pinecone Retrieval | Search approved document chunks. |
| 4 | Cohere Reranker | Reorder retrieved chunks by relevance. |
| 5 | Airtable Create | Log ranked document IDs, versions, ranks, and available scores **before generation**. |
| 6 | IF / Code | Check configured evidence sufficiency criteria. |
| 7 | LLM Chain | Generate one answer from selected context. |
| 8 | Parser + Code | Validate structure; verify cited IDs occur in retrieved set. |
| 9 | Airtable Update → Edit Fields | Save outcome; return `ANSWER_AVAILABLE` or `ESCALATION_REQUIRED`. |

Insufficient evidence, invalid output, or AI failure returns an escalation outcome. Citation-ID checks do **not** prove factual groundedness; assess that offline. First verify whether native retrieval nodes expose ranked metadata; use HTTP APIs only if needed.

## WF-03 — Ticket Creation

| Step | Node | Action |
|---|---|---|
| 1 | Execute Sub-workflow Trigger | Receive `request_id`, Airtable record ID, and `action` (`direct_ticket` or `confirmed_escalation`). The record ID is accepted but not trusted: the request is looked up by `request_id`. |
| 2 | Airtable Search (×2) | Read the Support Request; look for an existing ticket (`ticket_id = TKT-<request_id>` or a ticket linked to the request). |
| 3 | Switch | **Reuse:** a ticket exists and the action is recognised. **Create:** no ticket, the request exists, and the action matches the status (`direct_ticket` from `NEW`, `confirmed_escalation` from `AWAITING_ESCALATION`). **Reject (fallback):** everything else, including an unrecognised action. |
| 4 | Airtable Create | Create the ticket `OPEN`, linked to the request (Create path only). |
| 5 | Airtable Update | Set the request to `TICKET_CREATED` and clear `response_deadline` (Reuse and Create paths). |
| 6 | Airtable Search → IF → Airtable Create | Count tickets for the request **before** notifying; if more than one exists, log `DUPLICATE_TICKET_SUSPECTED`. Never deletes. Errors here do not block the confirmation. |
| 7 | Slack Send Message | Confirm the ticket to the employee; 3 attempts, then error output. |
| 8 | Airtable Create (error outputs) | Reject path logs `INVALID_TICKET_REQUEST`; a failed Slack confirmation logs `SLACK_CONFIRMATION_FAILED`. The ticket and request state are preserved. |

Reusing an existing ticket must not create another. Identical custom IDs and pre-creation checks **do not** guarantee uniqueness under concurrent Airtable writes; flag suspected duplicates rather than silently deleting them.

**Status:** implemented and runtime-validated standalone (pinned input); not yet integration-tested with WF-01. See [05_development_checkpoint.md](05_development_checkpoint.md).

## WF-04 — Document Ingestion

| Step | Node | Action |
|---|---|---|
| 1 | Authorized Form Trigger | Accept approved document upload/update. |
| 2 | Code / Edit Fields | Validate file; attach `document_id` and version. |
| 3 | Document Loader + Text Splitter | Extract and chunk content. |
| 4 | Embeddings + Pinecone Insert | Index chunks with document/version metadata. |
| 5 | Logging | Record ingestion outcome and failures. |

Define and test a version-replacement procedure before updates. Verify supported Pinecone deletion/filtering behavior; ensure outdated chunks are not returned.

## WF-05 — Timeout Handling

| Step | Node | Action |
|---|---|---|
| 1 | Schedule Trigger | Periodically scan for expired response deadlines. |
| 2 | Airtable Search | Find `AWAITING_FEEDBACK` / `AWAITING_ESCALATION` with expired `response_deadline`. |
| 3 | Airtable Search → IF | Recheck current state and deadline before closing. |
| 4 | Airtable Update | Set `CLOSED_NO_TICKET` and `closure_reason=TIMEOUT`. Set `feedback_outcome=UNKNOWN` only if the previous status was `AWAITING_FEEDBACK`; from `AWAITING_ESCALATION` keep the existing value (e.g. `UNRESOLVED`). |
| 5 | Operational Event | Log closure; optional Slack notification. |

`response_deadline` (Airtable Date with time, UTC) exists in **Support Requests**; WF-01 sets and clears it. Explicit **No, thanks** uses `CLOSED_NO_TICKET` with a distinct decline reason, not `UNKNOWN` feedback.

## Shared Error Handling

| Node | Action |
|---|---|
| Error Trigger | Capture failed executions where supported. |
| Edit Fields | Extract workflow/execution IDs and error details. |
| Airtable Create | Log Operational Event when Airtable is reachable. |
| IF → Slack | Alert the administrator when intervention is needed. |

Use **local error branches** for failures needing `request_id` and business fallback. The global Error Trigger is a safety net and may not contain original request data. If Airtable is down, rely on n8n execution records and alerts.

## Offline RAG Evaluation

Use a versioned JSON/CSV dataset and a standalone test script or manually triggered test harness—not a required production workflow. Retrieval settings (top-k, embedding model, reranker, evidence threshold) come from one versioned file, `config/rag_config.json` (with `config_version`). Define how it reaches n8n (raw-URL fetch at WF-02 start, or a deployment copy readable by n8n) and verify that WF-02 and the evaluation script report the same `config_version` and hash. Record `config_version` with every evaluation result. Measure Recall@3, Precision@3, answer correctness, groundedness, and escalation accuracy against acceptance criteria defined before final testing.

## Cross-Workflow Rules

- Pass both the stable business `request_id` and the **Airtable record ID** when creating linked records.
- Check current status before applying actions; Slack retries and double clicks can repeat events.
- Keep ticket notifications separate from ticket creation and its retries.
- Verify Slack interaction signatures and acknowledgment behavior in the actual n8n environment; signing-secret implementation is deployment-dependent.
- Log technical failures without storing credentials or unnecessary sensitive payloads.
- Treat duplicate prevention as best effort, not exactly-once delivery.

## Implementation Sequence

1. **Slack connection + WF-01 basic intake:** One DM → one Airtable Support Request; repeated event → no second request.
2. **WF-03 ticketing:** Existing-ticket reuse; Slack notification failure does not create another ticket.
3. **WF-01 interactions + WF-05:** Buttons, state checks, feedback, escalation, declines, and timeout closures. Use a **stub WF-02** (fixed `ESCALATION_REQUIRED` or `ANSWER_AVAILABLE`) to exercise every lifecycle path before RAG exists.
4. **WF-04 ingestion:** Versioned documents searchable; outdated versions excluded.
5. **WF-02 RAG:** Retrieval metadata verified; unsupported questions escalate.
6. **Error handling + evaluation:** Test API failures, repeated events, routing, and offline RAG metrics.

**First milestone:** A real Slack DM creates exactly one Support Request in Airtable.
