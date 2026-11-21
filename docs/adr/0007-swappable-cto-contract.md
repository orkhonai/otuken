<!-- SPDX-License-Identifier: MIT -->
# ADR 0007 · A swappable CTO: the contract, the supervisor and handover

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Accepted, 2026-11-21. **Topic:** Swappable CTO contract, supervisor, and handover.

## Decision

Nothing important lives inside one harness. The CTO's job lives in five parts that every candidate can use:

1. **Job files** in the HQ repository (`/var/lib/otuken/hq`, shared into the seat): `jobs/<id>/BRIEF.md` (PURPOSE, TASK, LIMITS, DONE), `STATUS.md` (first line `STATE: <state>`, then summary, evidence and decision), `REPORT.md`, `PROJECT`, and `job.json`, the machine part the guard enforces: project, sandbox kind, accounts allowed, budget (wall clock, turns, money for API lanes), deadline, allowed tool classes, egress classes, repository and branch rule, acceptance checks. `job.json` is validated against a JSON Schema and capped by the owner's policy; the guard refuses to start a worker for a job without a valid one.
2. **Instructions:** one `AGENTS.md`, the product's CTO rules with the owner's rules from the overlay appended at install, kept under 32 KiB and under Antigravity's 20,000-token rules budget; a one-line `CLAUDE.md` containing `@AGENTS.md`; no rule that lives only in a harness-specific file.
3. **Tools:** the guard's MCP server and identical CLI (ADR 0006): `project.*`, `worker.start|tell|status|stop|wait`, `job.state`, `secret.bind`, `github.grant`, `egress.allow`, `browser.start|stop`, `usage.read`, `board.report`, `vault.search|propose`, `approval.request`, `host.diagnose`, `kill`. The tools are stateless, use neither elicitation nor tasks, and accept the MCP revisions 2025-11-25 and 2026-07-28. Worker control is harness-neutral (`worker.start --harness codex --account <label> --job <id>`); the harness adapter turns it into the pinned harness's headless invocation inside the project VM, captures its event stream, enforces the caps and tells the CTO when the worker ends.
4. **Skills:** Agent Skills folders from `/opt/otuken/current/skills` and from the overlay, linked into `.agents/skills`, `.claude/skills` and Hermes's `external_dirs`. For the CTO, product skills are on and project skills off, so a cloned repository cannot redefine the agent that owns the box.
5. **State owned by the guard:** the registry of projects, jobs, workers, accounts, leases and pending approvals, and one append-only journal from which the board, the first line of `STATUS.md` and the human status view are all derived. Job state has one record: the journal, fed by `job.state` calls. A direct edit of `STATUS.md`'s first line is read as such a call and validated. The CTO writes the rest of `STATUS.md` freely.

**The supervisor** (on the guard's unprivileged side, supervised by systemd) owns wake-ups. It persists owner messages, new jobs, finished, failed or blocked workers, resolved approvals and alarms, then feeds them to the CTO as new turns, replaying from a durable cursor after a crash, with idempotency keys derived from each event. The transport for each harness is chosen from the pinned version's tested capabilities and recorded in the catalog: ACP where the harness implements what we need natively, otherwise the harness's own structured mode. Deadlines and cancellation are always enforced by the supervisor, never left to the harness. The adapter surface is `probe` (version, capabilities, login state), `start`, `send`, `events`, `cancel` and `collect`. With bb installed, bb can play the runner's role instead; the contract never depends on it.

**Handover** (`otuken seat handover --to <harness>`):
1. Pause new admissions (queued, not lost); running workers continue.
2. The outgoing CTO writes `HANDOVER.md` from a template. If it is dead or unusable, the guard builds the checkpoint from its registry alone: approved decisions with their evidence, artifact references, unresolved checks, pending approvals and active leases.
3. Snapshot the seat, then start the new harness in a fresh seat with the same `AGENTS.md`, skills, MCP server, HQ and vault, logged in to its own account.
4. The new CTO starts read-only. Its first turn is fixed: read `HANDOVER.md` and `AGENTS.md`, call `otukenctl status`, reconcile the two, write a one-page acceptance note.
5. Only then does the guard move tier-1 authority to the new generation, atomically, and fence the old one; tool approvals expire. Rollback is the reverse switch, and the old seat's snapshot is kept.

**Support in v0.1:** Claude Code and Codex, as CTO and as worker. Each runs the same representative job in both roles, they exchange a live checkpoint, and they show success, denial, transient failure and cancellation. Pi is the fallback second harness if either fails a provider or security gate. oh-my-pi and Hermes follow, each announced only after it passes both roles. Antigravity is not a managed CTO on a consumer Google plan (ADR 0004); with a Cloud project or an API key it is a candidate like the others.

**Launch hardening per harness** (kept in the catalog):
- Claude Code: `-p` with `--strict-mcp-config` and `--setting-sources user`, never with a project checkout as its working directory, and stopped with SIGINT; not `--bare`, which skips the OAuth login.
- OpenCode: `--standalone`.
- Codex: `cli_auth_credentials_store = "file"` and an explicit sandbox flag for jobs that edit.
- oh-my-pi: a locked config with project discovery turned off.
- Hermes: `skills.write_approval: true`; its cron, memory and gateway features fenced; `hermes proxy` never enabled; stopped through its own command.
- Antigravity (API-key route only): the exit code is never trusted alone.

**What each candidate can do headless** (versions checked 2026-11-21: Antigravity CLI 1.5.12, Codex 0.171.0, Pi 1.6.0, oh-my-pi 19.0.1, Claude Code 2.1.330, Hermes Agent 0.23.3):

| | Antigravity | Codex | Pi | oh-my-pi | Claude Code | Hermes |
| --- | --- | --- | --- | --- | --- | --- |
| One-shot, machine-readable | `-p --output-format stream-json` | `exec --json` | `-p`, `--mode json` | `-p --mode json` | `-p --output-format stream-json` | `-z`, `--format stream-json` |
| Long-lived driver | `--input-format stream-json` | `app-server` | `--mode rpc` | `--mode rpc` | Agent SDK | API server, gateway |
| ACP | native | adapter | adapter | native | adapter | native |
| Known headless traps | soft-deny exits 0; a non-TTY hang reported | read-only by default; untrusted repo skips project config | no approvals, no built-in sandbox | repository inputs load without a trust gate; yolo by default | `-p` runs untrusted project hooks; can report success while background work stopped; SIGTERM drops the turn | closing the terminal detaches; work continues at the gateway |

## Reasons

- Instruction loading: Codex reads `AGENTS.md` up to "32 KiB by default" ([Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)); Antigravity has a "20,000-token aggregate rules budget" ([rules](https://antigravity.google/docs/rules)); Claude Code reads `AGENTS.md` "only when you have no CLAUDE.md" ([memory](https://code.claude.com/docs/en/memory)); in Hermes the "first match wins" among its context files ([context files](https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files)); all read 2026-11-21.
- MCP's 2026-07-28 revision reads "Make MCP stateless" and moved tasks into an extension ([MCP changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog), read 2026-11-21). Skills follow the Agent Skills specification ([agentskills.io](https://agentskills.io/specification), read 2026-11-21).
- ACP v2 "as a whole is in Preview" ([ACP v2 migration](https://agentclientprotocol.com/protocol/v2/migration), read 2026-11-21); in ACP v1 loading an existing session is optional and cancellation is a notification ([session setup](https://agentclientprotocol.com/protocol/v1/session-setup), [prompt turn](https://agentclientprotocol.com/protocol/v1/prompt-turn), read 2026-11-21).
- Claude Code: `-p` runs the hooks "even in a folder you've never trusted", and background work stops "after 10 minutes of continuous idle waiting" ([headless](https://code.claude.com/docs/en/headless)); on SIGTERM it "exits with code 143" and leaves the turn unfinished ([CLI reference](https://code.claude.com/docs/en/cli-reference)); an open issue reports `-p` returning success while background subagents were stopped ([issue 94392](https://github.com/anthropics/claude-code/issues/94392)); scheduled tasks "expire 7 days after creation" ([scheduled tasks](https://code.claude.com/docs/en/scheduled-tasks)); all read 2026-11-21. Timers and schedules therefore belong to the guard.
- OpenCode by default "discovers or starts one shared background server for your user account" ([OpenCode CLI](https://opencode.ai/docs/cli/), read 2026-11-21).
- Codex `exec` is read-only by default ([non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode), read 2026-11-21).
- Hermes writes its own skills unless `skills.write_approval: true` is set ([skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)); "Closing the terminal detaches" ([CLI](https://hermes-agent.nousresearch.com/docs/user-guide/cli)); it documents `--format stream-json` ([CLI reference](https://hermes-agent.nousresearch.com/docs/reference/cli-commands)); all read 2026-11-21.
- Antigravity's headless mode: "soft-denied: the run continues, exits 0" ([headless](https://antigravity.google/docs/cli/headless), read 2026-11-21); a non-TTY hang was reported again after its fix ([issue 318](https://github.com/google-antigravity/antigravity-cli/issues/318), read 2026-11-21).
- oh-my-pi "loads its project inputs by design" ([README](https://raw.githubusercontent.com/can1357/oh-my-pi/main/README.md)), and "The built-in default is yolo" ([approvals](https://omp.sh/docs/approvals)); read 2026-11-21.
- Pi "does not ask for approval before every tool call" and its docs note the "lack of a built-in sandbox" ([Pi security](https://raw.githubusercontent.com/earendil-works/pi/main/packages/coding-agent/docs/security.md), read 2026-11-21).

## Disagreement, and how it was decided

- **Transport.** Choosing transport by the pinned version's tested capabilities (using ACP where complete and native structured mode otherwise) avoids tying resume and cancel to preview ACP revisions.
- **The job-state record.** One guard journal is the source of truth so `STATUS.md` and the board cannot disagree; direct edits to `STATUS.md` line 1 are validated as `job.state` calls.
- **Machine job-file format:** JSON, matching the board and catalog schemas.

## Rejected

- A lowest-common-denominator wrapper that hides the harnesses; it throws away what each does best and breaks on every release.
- Harness-native memory or schedules as the store of record.
- bb as a required part of the contract.
- Translating transcripts between harnesses.
- Announcing all six CTO harnesses before each passes a real job in both roles.

## Open risks

- Six event formats: one adapter each, tested in CI against recorded transcripts.
- Harness sandboxes need user namespaces, which Ubuntu 24.04 restricts through AppArmor; Codex warns about it on 24.04 ([Codex sandboxing](https://learn.chatgpt.com/docs/sandboxing), read 2026-11-21), and Claude Code's sandbox falls back to running unsandboxed ([Claude Code sandboxing](https://code.claude.com/docs/en/sandboxing), read 2026-11-21). The installer loads the AppArmor profile once and sets the harnesses to fail closed; the VM is the boundary either way.
- The capability table comes from documentation; real runs decide (T3).

## Verification test

T3, the role tests above, including a clean swap and a swap from a failed seat with workers still running.
