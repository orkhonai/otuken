<!-- SPDX-License-Identifier: MIT -->
# ADR 0012 · The wall-board data contract

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Accepted, 2026-11-21. **Topic:** Wall-board data contract and documented usage reporting.

This record fixes the data contract that any wall-board UI or client can rely on.

## Decision

- **Facts come from the runtime, not from agents.** The guard fills nearly every field from what it controls: sandbox and process state, timers, the account adapters, the harness adapters' event streams. An agent adds only a one-line `what` (at most 140 characters, passed through the same secret scrubber as logs) through `board.report`. Which account a worker uses and how much capacity is left are never self-reported.
- **Two artifacts, files first.**
  - A snapshot, `/var/lib/otuken/board/board.json`, rewritten atomically on every change and at least every 30 seconds.
  - An append-only event log, `events.ndjson`: one CloudEvents JSON object per line, each with a server-assigned, increasing cursor (the CloudEvents `sequence` extension). Event types: `agent.started`, `agent.state_changed`, `agent.reported`, `agent.finished`, `job.opened`, `job.state_changed`, `usage.updated`, `alarm.raised`, `alarm.cleared`, `kill.tripped`, `kill.released`, `approval.requested`, `approval.resolved`.
  - A small read-only HTTP view serves the same files: `GET /v1/board.json` and `GET /v1/events?after=<cursor>` as Server-Sent Events. A board resumes from its last cursor, de-duplicates by `source` plus `id`, and reloads the snapshot when its cursor has expired.
- **Versioned.** JSON Schema 2020-12 files in the repository (`schemas/board/v1.json`), and `schema_version` in every document. Minor versions only add fields; readers ignore unknown fields. The schema and a test fixture exist before the first board is built.
- **Private by construction.** No prompt or message text, no file contents, no secrets, no provider e-mail address or account ID (only the owner's labels), no IP addresses or internal host names.
- **Read-only and authenticated.** Loopback by default; on the private network only with a read-only, scoped credential. Kill, approve and answer are a separate, authenticated guard endpoint.
- **Job state** comes from the journal (ADR 0007), so `STATUS.md` and the board cannot disagree. A `parked` job never carries an open decision, so no board shows it as waiting for the owner.
- **Entities:**

  ```yaml
  box:        {id, layer_version, generated_at, uptime_s, cpu: {load1, cores},
               memory: {total_b, available_b}, disks: [{mount, used_pct}],
               raid: {state, degraded}, snapshots: {last_at},
               backup: {offbox, last_ok_at, last_restore_test_at},
               alarms: [{id, severity, since, text}],
               kill_switch: {state: armed | tripped, scope, level, since, by}}
  accounts:   [{id, provider, plan, harnesses: [..],
               auth: {state: ok | expired | missing | unknown, checked_at},
               limits: [{name, used_pct, resets_at, window_s, elapsed_pct, pace_pp}],
               credit: {amount, currency, as_of} | null,
               source, documented: true | false, read_at,
               status: fresh | stale | unavailable | unknown}]
  projects:   [{id, repo, sandbox: {kind: vm | container, state, cpu, memory_b, disk_used_b},
               egress_classes: [..], github: {mode: app | deploy_key | none, expires_at},
               secrets: {count}}]
  jobs:       [{id, project, title, why, state, brief_ref, status_ref,
               opened_at, updated_at, deadline,
               budget: {wall_s, used_s, max_turns, max_usd}, agents: [..]}]
  agents:     [{id, role: cto | worker | reviewer | curator | browser, job, project,
               harness: {id, version}, model, account,
               where: {sandbox, workdir, branch}, what, why, run_state,
               since, heartbeat_at,
               usage: {input_tokens, output_tokens, cached_tokens, est_cost_usd} | null}]
  owner_queue: [{id, kind: approval | question | login, from, created_at, summary}]
  ```

  Job `state` is the CTO's judgment: `queued | working | needs_owner | parked | done | failed`. `run_state` is the runtime's fact: `queued | provisioning | running | waiting_owner | cancelling | succeeded | failed | cancelled`. A retry is a new run linked to the first.
- **Five operator questions map to fields:** *what* is `agents[].what` and `run_state`; *where* is `agents[].where` and `project`; *why* is `agents[].why`, which points at the job's `why` (the first line of the brief's PURPOSE); *which account* is `agents[].account`; *how much is left* is that account's `limits[]` and `credit`, with `pace_pp` (used share minus elapsed share, in percentage points) so any board can show "ahead of pace" without knowing each provider.
- **Where "how much is left" comes from.** Only documented routes in the public product, each reading labelled with its `source`:
  - Claude plans: the status-line JSON's `rate_limits.five_hour` and `seven_day`, available only after a session's first response; the harness adapter captures it from running workers.
  - ChatGPT plans: the Codex app-server's `account/rateLimits/read` and its update notification.
  - Copilot: the Copilot SDK's account usage/limit endpoint.
  - API keys: the providers' organisation usage and cost APIs (admin keys), Mistral's billing API, and the gateway's own ledger.
  - Antigravity on consumer plans, individual Cursor plans, and any provider without a documented route: `status: unavailable`, never a guess.
  - Tokens per worker: Claude Code's and Codex's OpenTelemetry export into a local collector, prompt logging off, identities stripped before anything reaches the board.
  - A reading older than 15 minutes is `stale`; it stays visible with its age and cannot feed routing that needs a fresh reading.
- **Undocumented readers** (such as calling undocumented OAuth usage endpoints directly or scraping interactive panels) are not in the public product.
- An optional OpenTelemetry bridge with the GenAI semantic conventions may export the same data; the contract does not depend on it.
- A board can be anything that reads these files or the HTTP view: a desktop display (such as [Plash](https://github.com/sindresorhus/Plash), read 2026-11-21), a phone view, or a terminal. The optional reference page is one such reader.

## Reasons

- CloudEvents requires only `id`, `source`, `specversion` and `type`, and `source` plus `id` is unique ([CloudEvents](https://raw.githubusercontent.com/cloudevents/spec/main/cloudevents/spec.md), read 2026-11-21); the `sequence` extension gives "the position of an event in the ordered sequence of events produced by a unique event source" ([sequence extension](https://raw.githubusercontent.com/cloudevents/spec/main/cloudevents/extensions/sequence.md), read 2026-11-21); "The current version is 2020-12" ([JSON Schema](https://json-schema.org/specification), read 2026-11-21).
- Claude's status line carries the limits "only for claude.ai Pro, Max, and Ultra subscribers … only after the first API response in the session" ([status line](https://code.claude.com/docs/en/statusline)); Codex documents `account/rateLimits/read` ([app-server](https://learn.chatgpt.com/docs/app-server)); the Copilot SDK documents how to read account usage ([usage and billing](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/usage-and-billing)); Antigravity documents `/usage` only as an interactive panel ([usage](https://antigravity.google/docs/cli/commands/usage)); Cursor's admin API is for teams only ([Admin API](https://cursor.com/docs/account/teams/admin-api)); all read 2026-11-21.
- Keeping undocumented OAuth usage calls out: besides being undocumented (described only by third parties such as [claude-usage](https://docs.rs/crate/claude-usage/0.2.2), read 2026-11-21), they require reading the subscription's OAuth token directly, which risks conflicting with Anthropic's terms ("collect, store, or intermediate Claude.ai credentials or session tokens", [legal and compliance](https://code.claude.com/docs/en/legal-and-compliance), read 2026-11-21). For Antigravity, a user post on Google's forum notes that undocumented alternatives risk the terms ([forum](https://discuss.ai.google.dev/t/feature-request-official-read-only-quota-api-for-third-party-apps/188769), read 2026-11-21).
- OpenTelemetry: Claude Code exports `claude_code.token.usage` and `claude_code.cost.usage`, with prompts "Redacted by default" and events carrying `user.email` ([monitoring](https://code.claude.com/docs/en/monitoring-usage)); Codex's `[otel]` section is "Disabled by default", with `log_user_prompt = false` ([advanced config](https://learn.chatgpt.com/docs/config-file/config-advanced)); the GenAI conventions are "Status: Development" ([OpenTelemetry GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)); all read 2026-11-21.
- The API-key usage routes need admin keys ([Anthropic Usage and Cost API](https://platform.claude.com/docs/en/build-with-claude/usage-cost-api), [OpenAI usage](https://developers.openai.com/api/reference/resources/organization/subresources/audit_logs/subresources/usage), read 2026-11-21).

## Disagreement, and how it was decided

- **Contract shape.** Files come first (`board.json` and `events.ndjson` in CloudEvents form, backed by JSON Schema before the first UI), paired with a thin read-only HTTP/SSE view so remote screens and phones can follow the board without tailing server files.
- **Undocumented usage readers.** Kept out of the public product to avoid token intermediation and fragile scraping.
- **`STATUS.md` against the board:** ADR 0007.

## Rejected

- Agents self-reporting their own account or remaining limits.
- OpenTelemetry as the contract itself: still in development, and heavier than a board needs.
- A control app's internal API as the contract.

## Open risks

- For several providers "how much is left" reads `unavailable` until the vendors document a route (consumer Antigravity, individual Cursor plans, xAI pools).
- Claude's documented route appears only after a worker session has had a response.

## Verification test

T13: board consumers fed unknown, stale and incompatible events.
