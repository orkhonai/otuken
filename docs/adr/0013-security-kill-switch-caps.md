<!-- SPDX-License-Identifier: MIT -->
# ADR 0013 · Security model: principals, threats, kill switch and caps

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Accepted, 2026-11-21. **Topic:** Security model, threat list, kill switch, and caps.

## Decision

**Principals, and how far each is trusted.**

| Principal | Trusted for | Not trusted for | Enforced by |
| --- | --- | --- | --- |
| Owner | everything | — | — |
| Installer and guard | deterministic, reviewed code | — | review, signed releases, CI |
| CTO (seat) | planning, routing, judging, tier-1 calls | its own host access, its own limits, the backups | guard tiers, the seat VM, policy out of its reach |
| Worker | changing its project's code | anything outside its project and job | the project VM, the egress proxy, per-job secrets |
| Vault merge step | merging proposals | secrets, network | no secrets, no egress, tool-less model calls |
| Browser VM | reading the open web | everything else | its own VM, no secrets, ephemeral profile |

**Assets:** subscription logins and API keys; GitHub credentials; project secrets; source code and unpushed work; the vault; the backups; the host; the owner's usage budgets and money.

**Threats, ranked by likelihood times damage, with the answer to each.**

1. **Prompt injection from repositories, issues, web pages and the vault while agents run unattended.** Trail of Bits turned argument injection into pre-approved commands into code execution and called sandboxing "the most effective defense available today" ([Trail of Bits](https://blog.trailofbits.com/2025/10/22/prompt-injection-to-rce-in-ai-agents/), read 2026-11-21). A 2026 write-up bypassed Claude Code's auto-mode classifier, and the vendor answered that it is "a best-effort classifier, not a security guarantee… The real boundary is OS isolation and network egress control" ([Embrace The Red](https://embracethered.com/blog/posts/2026/breaking-claude-code-opus-5-and-automode/), read 2026-11-21). *Answer:* workers run unattended only inside project VMs; egress is allowlisted per project; secrets are per job; worker output is data for the CTO, never orders; hostile-text fixtures in CI (T11). *Residual:* exfiltration through an allowed host.
2. **Supply-chain compromise of dependencies or of the agent CLIs themselves.** The Nx packages ran the victim's installed AI CLIs with `--dangerously-skip-permissions`, `--yolo` and `--trust-all-tools` to hunt for secrets ([Nx advisory](https://github.com/nrwl/nx/security/advisories/GHSA-cxm3-wv7p-598c), [Snyk](https://snyk.io/blog/weaponizing-ai-coding-agents-for-malware-in-the-nx-malicious-package)); Shai-Hulud "compromised over 500 packages" ([CISA](https://www.cisa.gov/news-events/alerts/2025/09/23/widespread-supply-chain-compromise-impacting-npm-ecosystem)) and its second wave reached more than 25,000 repositories ([Wiz](https://www.wiz.io/blog/shai-hulud-2-0-ongoing-supply-chain-attack)); Cline CLI 2.3.0 shipped a malicious postinstall ([Cline advisory](https://github.com/cline/cline/security/advisories/GHSA-9ppg-jx86-fqw7)); a 2026 wave published packages with valid SLSA Build Level 3 provenance and planted a `.claude/settings.json` SessionStart hook ([Semgrep](https://semgrep.dev/blog/2026/children-of-shai-hulud-an-analysis-of-the-the-evolution-delivery-and-spread-of-the-tanstack-shai-hulud-campaign)); all read 2026-11-21. *Answer:* harness versions pinned by digest, with a cool-down and no self-update; a new pin is tested in a disposable, unprivileged guest before promotion; dependency installs happen only inside VMs, never on the host or in the seat; a harness's user-level config is read-only inside a VM, so a package cannot plant hooks; provenance is recorded but not treated as proof of safety.
3. **Repository or agent config that executes on open.** Claude Code, Codex, Cursor and Gemini CLI all had such CVEs in 2025–2026 ([CVE-2025-59536](https://cveawg.mitre.org/api/cve/CVE-2025-59536), [CVE-2026-21852](https://cveawg.mitre.org/api/cve/CVE-2026-21852), [Check Point on Codex](https://research.checkpoint.com/2025/openai-codex-cli-command-injection-vulnerability/), [CVE-2025-54135](https://cveawg.mitre.org/api/cve/CVE-2025-54135), [CVE-2025-54136](https://cveawg.mitre.org/api/cve/CVE-2025-54136), [CVE-2026-12537](https://cveawg.mitre.org/api/cve/CVE-2026-12537), read 2026-11-21). *Answer:* per-harness hardening profiles (ADR 0007), a scrubbed environment at launch, the CTO's working directory never a project checkout, and the VM as the outer wall.
4. **Theft of subscription logins and keys.** *Answer:* ADR 0004 and ADR 0010: one login per project and never next to untrusted code, inference-only setup tokens, API keys only in the gateway, egress allowlists, provider-side revocation as a kill-switch level.
5. **Malicious MCP servers, skills and plugins:** tool poisoning ([Invariant Labs](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)), a public issue making an agent leak private repositories through the GitHub MCP server ([Invariant Labs](https://invariantlabs.ai/blog/mcp-github-vulnerability)), a trojaned `postmark-mcp` (news, [The Register](https://www.theregister.com/2025/09/29/postmark_mcp_server_code_hijacked/)), 341 of 2,857 skills on OpenClaw's hub malicious in February 2026 ([Palo Alto Networks](https://www.paloaltonetworks.com/blog/security-operations/clawhavoc-ai-agent-skills-poisoning/)); all read 2026-11-21. *Answer:* MCP servers and skills only from the signed catalog or the overlay, pinned; no marketplace auto-install.
6. **An exposed control plane:** 21,639 publicly exposed OpenClaw instances in January 2026 ([Censys](https://censys.com/blog/openclaw-in-the-wild-mapping-the-public-exposure-of-a-viral-ai-assistant/)), and a crafted link that made the client send its token to an attacker's gateway ([CVE-2026-25253](https://cveawg.mitre.org/api/cve/CVE-2026-25253)); read 2026-11-21. *Answer:* everything on loopback by default; remote access only over the private network with host-side admission; a read-only board; a separate authenticated endpoint for writes; no public port but SSH; the control app, if installed, bound to loopback.
7. **A compromised or careless CTO.** *Answer:* ADR 0006, and backups it cannot delete (ADR 0014).
8. **Cross-project leakage.** *Answer:* one VM, bridge, secret set and vault scope per project, and the canary test (T4).
9. **Sandbox escape.** *Answer:* a KVM VM per project by default; containers only as the light profile, with isolated ID maps; Incus from a maintained LTS line, patched promptly (ADR 0008).
10. **Runaway spend, time and disk.** *Answer:* the caps below; provider-side limits lag ("Enforcement is not instantaneous", [OpenAI spend limits](https://developers.openai.com/api/docs/guides/spend-limits); Google's developer AI project caps are experimental with "around a 10 minute latency", [Google AI billing](https://aistudio.google.com/docs/billing); read 2026-11-21).
11. **Account bans for terms violations.** *Answer:* ADR 0004: each subscription runs inside its own native agent; forbidden routes are hard-blocked, not merely warned about; no automated rotation; no client spoofing; the terms are re-read at each minor release.
12. **Data loss** (a disk, both mirrors, `rm -rf`, a force-push). *Answer:* snapshots, optional off-box backup, branch protection on the default branch, and refusing to delete any project with uncommitted or unpushed work.
13. **Vault poisoning.** *Answer:* ADR 0011.
14. **The owner locked out.** *Answer:* the provider's admin user is never removed; public SSH stays open until a separate, verified switch with a watchdog that reopens it; the kill switch never cuts admin access.
15. **A compromised release or updater.** *Answer:* the offline release key and signed metadata with an expiry (ADR 0001); separate build, release and host privileges; a signed recovery release; after a host-root compromise, credentials are rotated from a trusted machine and the box is restored onto a clean host.
16. **Log leakage.** *Answer:* no tokens, environment, arguments or prompt bodies in the board, audit or exec logs (exec tracing skips arguments and environment); a scrubber on every free-text field.

**Out of scope,** stated in `SECURITY.md`: a compromised hosting provider, hypervisor zero-days (mitigated by prompt patching), a malicious human admin, a compromised model vendor.

**Kill switch.** One command and one board action: `otuken kill [--job ID | --project ID | --all] [--level freeze|cut|stop|revoke]`, from SSH, from the board's authenticated action, or tripped by an alarm the policy marks as tripping (disk above 90 %, a spend cap hit, a burst of egress or policy violations). The levels escalate:
1. **freeze:** suspend every process of the scope through the cgroup freezer (`systemctl freeze`) or `incus pause`; reversible, and it keeps the evidence;
2. **cut:** drop the scope's egress in nftables and revoke its gateway tokens;
3. **stop:** interrupt each harness the way it ends a turn cleanly (SIGINT for Claude Code; Hermes's own stop command), then `systemctl kill --kill-whom=all` and `incus stop --force`; with `--all` the seat and the control app stop too;
4. **revoke:** revoke the scope's GitHub tokens and guard leases and mark its accounts for a new login.

A trip writes a persistent marker under `/var/lib/otuken/state/`, so nothing restarts after a reboot until the owner releases it over SSH (`sudo otuken resume`). Admin SSH, the remote-access path, the firewall and the snapshot timer are never cut. The CTO can trip the switch for workers but cannot release a kill the owner tripped. Time to containment is measured before any latency is promised.

**Caps.**
- *Per job:* wall clock as `RuntimeMaxSec=` on the worker's unit (default 2 hours; browser VMs 30 minutes, renewable within their lease); CPU, memory and task limits from the project VM; turn and money limits passed to the harnesses that have them, treated as soft (Claude Code's `--max-budget-usd` is a client-side estimate, and "Spend can pass the cap", [CLI reference](https://code.claude.com/docs/en/cli-reference), read 2026-11-21); retries stop after a small fixed number.
- *Per account:* a pace rule comparing used share against elapsed share of each rate window; the guard refuses a new unattended worker on an account that is more than a set number of points ahead of pace (default 20) or above 90 % used, unless the CTO records a reason or the owner overrides.
- *Loop breaker:* a worker that repeats the same failing command several times, or makes no file or git progress for a set time, is frozen and reported to the CTO instead of burning its window.
- *API keys:* the gateway's per-job, daily and monthly caps, plus provider-side limits the wizard asks for before it accepts a key ([Anthropic workspaces](https://platform.claude.com/docs/en/build-with-claude/workspaces), [OpenAI spend limits](https://developers.openai.com/api/docs/guides/spend-limits), read 2026-11-21); provider-side limits are the only cap a root agent could not undo, though they lag.
- *Paid fallback:* off, with automatic top-ups off and OpenCode Go's Extra Usage off; a route that falls back to paid use when its subscription fails is refused at pin time (T16).

## Reasons

- The 2025–2026 security incidents cited above motivate hardware-enforced VM boundaries, explicit egress allowlists, and pinned harnesses.
- `systemctl freeze` suspends a unit's processes "using cgroup freezer" ([systemctl](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html)); `incus pause` and `incus stop --force` ([pause](https://linuxcontainers.org/incus/docs/main/reference/manpages/incus/pause/), [stop](https://linuxcontainers.org/incus/docs/main/reference/manpages/incus/stop/)); SIGTERM makes Claude Code exit 143 and drop the turn ([headless](https://code.claude.com/docs/en/headless)); with Hermes a lost terminal or SIGTERM "is a disconnect" and work continues at the gateway until `/exit` or `/quit` ([Hermes CLI](https://hermes-agent.nousresearch.com/docs/user-guide/cli)); all read 2026-11-21.

## Disagreement, and how it was decided

- **Kill switch levels.** Four escalating levels (`freeze`, `cut`, `stop`, `revoke`) were chosen over a single stop command so operators can preserve forensic evidence (`freeze`) or halt exfiltration (`cut`) without destroying state.
- **Default caps:** 2 hours per worker job and 30 minutes per browser VM, with a 20 percentage-point default pace threshold.

## Rejected

- Treating a harness's own permission classifier or sandbox as the boundary.
- Relying on provider-side spend caps alone; they lag by minutes.
- A board or control API reachable from the public internet.

## Open risks

- Exfiltration through allowed hosts remains (threat 1).
- The guard is the system's single point of trust (ADR 0006).
- Time to containment is not yet measured.

## Verification tests

T6 (the guard), T7 (the kill switch at each level and scope, across a test-VM reboot, with time to containment), T11 (hostile text) and T16 (paid fallback).
