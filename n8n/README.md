# n8n workflows

Target: n8n 2.13.2 on a shared, managed instance. Server access and environment variables are not assumed, so the workflows use standard nodes only (no Code node, no `crypto`).

| File | Purpose |
|---|---|
| `workflows/wf-01-intake-routing.json` | WF-01 Entry A: Slack DM → Support Request → choice buttons. |
| `workflows/wf-03-ticket-creation.json` | WF-03: create or reuse an IT ticket and confirm in Slack. |
| `node_versions.json` | Node types and `typeVersion`s taken from the target instance. |
| `validate_workflow.py` | Static checks before importing. |
| `sanitize_export.py` | Removes instance-specific and test data from an export before committing. |

Implementation status per workflow: [docs/05_development_checkpoint.md](../docs/05_development_checkpoint.md).

## Development loop

1. Generate or modify the workflow JSON.
2. Validate: `python -I n8n/validate_workflow.py n8n/workflows/<file>.json` (structure, node versions, connections, cross-node references; it cannot prove the node UI accepts every parameter).
3. Import into n8n, assign credentials, open each node once to confirm there are no parameter warnings.
4. Test with real Slack events, real Airtable records and the controlled cases below.
5. Fix, then **re-export from n8n** so the repository matches what was tested.
6. Sanitize before committing: `python -I n8n/sanitize_export.py n8n/workflows/*.json`. Use `--check` to verify without rewriting.

## What an export contains that must not be published

An n8n export includes credential ids and names, the instance id, node `webhookId`s (part of the public webhook URL), and pinned test data. `sanitize_export.py` removes these and leaves node parameters, connections and settings unchanged. Credentials are assigned again after each import.

Not removed: the Airtable base and table ids that appear in node parameters. They are identifiers, not secrets, but they name a private base; decide before publishing whether to keep them.

## WF-01 Entry A (basic intake)

Slack Trigger (`message`, whole workspace) → Valid DM? → Extract Fields → Find Existing Request → Is New Request? → Create Support Request → Send Choice Buttons.

- `request_id` is deterministic: `REQ-<slack_user_id>-<message_ts>`. A replayed event finds the same record and stops.
- Ignored: bot messages, message subtypes (edits), non-DM channels, empty text.
- Setup outside this repository: a Slack app with Events API on `message.im` over HTTP (Socket Mode off), bot scopes `chat:write` and `im:history`, and the production webhook URL as the Request URL.
- Credentials to assign: Slack API (Slack Trigger, Send Choice Buttons); Airtable Personal Access Token with record read/write on the base (two Airtable nodes).

Not built yet: Entry B (button interactions). The buttons are displayed but do nothing.

## WF-03 (ticket creation)

Called as a sub-workflow. Input: `request_id`, `airtable_record_id`, `action` (`direct_ticket` | `confirmed_escalation`). The request is looked up by `request_id`; `airtable_record_id` is accepted but not used.

Decision order: **Reuse** (a ticket exists and the action is recognised) → **Create** (no ticket, request exists, action matches status) → **Reject** (anything else; logs `INVALID_TICKET_REQUEST`).

After Reuse or Create: set `TICKET_CREATED` and clear `response_deadline` → count tickets for the request (logs `DUPLICATE_TICKET_SUSPECTED`, never deletes) → Slack confirmation (3 attempts; on failure logs `SLACK_CONFIRMATION_FAILED` and keeps the ticket).

Implementation notes learned during runtime testing:
- An Airtable search result exposes the record id at the top level and the columns under `fields` (for example `fields.status`, `fields.slack_user_id`).
- A search with no match needs `Always Output Data` and explicit empty-value handling in the Switch.
- Slack accepts a user id as the `channel` of a direct message.
- Nodes after a multi-item search use `.first()` rather than item pairing.

### Standalone test cases

Pin input on the Execute Workflow Trigger, using a Support Request created by a real DM:

```json
[{ "request_id": "REQ-<user>-<ts>", "airtable_record_id": "rec...", "action": "direct_ticket" }]
```

| Case | Expected | Result |
|---|---|---|
| Direct ticket creation | One ticket `TKT-<request_id>`, `OPEN`, linked; request `TICKET_CREATED`; Slack DM | Passed |
| Existing ticket reuse | `Reuse` output; no second ticket | Passed |
| Sequential replay | No second ticket | Passed |
| Invalid action | Rejected; `INVALID_TICKET_REQUEST` logged | Passed |
| Invalid request state | Rejected; event logged | Passed |
| Slack failure (`channel_not_found`) | Ticket and state kept; `SLACK_CONFIRMATION_FAILED` logged | Passed |
| Forced duplicate ticket | `DUPLICATE_TICKET_SUSPECTED` logged; nothing deleted | Passed |
| `confirmed_escalation` from `AWAITING_ESCALATION` | Ticket created | **Not yet run** |
| Clearing a previously populated `response_deadline` | Field emptied | **Not yet demonstrated** (field was confirmed empty after execution, but no populated value was tested) |
| Concurrent executions, load | — | **Not tested** |

Test data was removed after testing. Pinned data is not kept in the repository.
