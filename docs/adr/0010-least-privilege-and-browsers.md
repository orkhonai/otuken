<!-- SPDX-License-Identifier: MIT -->
# ADR 0010 · Least knowledge and least privilege per project, and browser VMs

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Accepted, 2026-11-21; split execution is an experiment (T10). **Topic:** Per-project secrets, GitHub access, egress filtering, tools, and browser VMs.

## Decision

- **Files.** A project VM sees its own repository, its caches and the inputs its job was given. No host directory is mounted into it; no host home, no SSH agent forwarding, no other project's volume, no host socket.
- **Secrets.** The owner adds them with `sudo otuken secret set <project> NAME` (value on standard input) or as a password-manager reference resolved at injection. When a job starts, the guard writes only the secrets its `job.json` declares into the VM's tmpfs (`/run/secrets`, mode 0600) and removes them when the job ends. Secrets never appear in images, snapshots or logs.
- **GitHub.** The owner registers a GitHub App through the manifest flow during install and installs it on chosen repositories. The guard keeps the App key as a systemd credential and mints, per job, an installation token narrowed to the project's repository and to `contents` and `pull_requests` write; it expires after one hour. Git gets it through a credential helper that asks the guard; `gh` reads `GH_TOKEN`. Fetch and write are separate scopes; publishing, CI secrets and deploy credentials stay outside the VM. Deploy keys are a fallback only. Branch protection on the default branch is recommended at install.
- **Egress.** One Incus bridge per project, NAT off, with an ACL that rejects everything except TCP to the host's proxy; recursive DNS turned off in that bridge's dnsmasq; port isolation on. Domain policy lives in an explicit HTTP CONNECT proxy on the host (Squid), one listener per project, with an allowlist built from classes: the harness's published domains, `github`, package registries, documentation, and `open-web` only for browser VMs and research jobs. IP literals, private and link-local address ranges and cloud metadata addresses are refused; traffic between VMs is denied; every CONNECT is logged.
- **API keys never enter a VM.** The optional gateway (ADR 0004, lane B) holds them, and a VM gets a per-job token with a money cap. The gateway is a small purpose-built service in the trusted base: per-job bearer tokens, an endpoint and model allowlist, per-job, daily and monthly caps, no request or response bodies in logs.
- **Subscription logins:** ADR 0004 (each subscription inside its own native agent; one per project; never next to code the owner did not write).
- **Split execution** is an experiment (T10) that would take subscription logins out of project VMs: the unmodified subscription CLI runs in a runner that keeps the login outside the project VM and sends its shell commands into the VM (Claude Code can wrap every shell command it spawns with `CLAUDE_CODE_SHELL_PREFIX`), with project-level settings, hooks and MCP turned off. It becomes the default only if coding quality holds and the runner's own file tools cannot read the login.
- **Tools.** The MCP servers and skills available in a project are listed in its `job.json` and come only from the signed catalog or the overlay. Project-level harness configuration is ignored unless allowed. Each VM's guard endpoint offers only that project's tools (for example, `vault.search` limited to the project's pages and shared pages).
- **Permission modes.** Inside the VM, workers run unattended as an unprivileged user. Where a harness has a reviewing mode, it is layered on top and never relied on.
- **Browser VMs** (`browser.start --profile <profile> --ttl 30m`): a VM from a browser image (Chromium with the DevTools protocol, and an optional view for the owner to watch), the `open-web` egress class, no secrets, and an ephemeral profile unless the owner signs in to a named persistent profile, kept separate per site. The DevTools port is reachable only from the sandbox that asked, for the session's lifetime. One browser per VM, 2 vCPU and 4 GiB; the guard destroys it at the end of its time-to-live.

## Reasons

- GitHub App installation tokens "expire after 1 hour" and accept `repositories` and `permissions` to narrow them ([GitHub Docs](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app), read 2026-11-21); with the manifest flow, owners "only need to follow a URL and name the app" ([App manifest](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest), read 2026-11-21); deploy keys never expire ([deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys), read 2026-11-21).
- Without OVN, Incus has no per-project networks of its own (`features.networks` "requires the server to be configured for OVN"), hence one bridge per project ([Incus projects](https://linuxcontainers.org/incus/docs/main/reference/projects/), read 2026-11-21). Incus ACLs filter by address only, have no domain names, and "cannot be used to block baseline service rules" such as DHCP and DNS to the bridge's own dnsmasq ([network ACLs](https://linuxcontainers.org/incus/docs/main/howto/network_acls/), read 2026-11-21).
- An explicit proxy, not a transparent one: TLS Encrypted Client Hello hides the server name on the wire ([RFC 9849](https://www.rfc-editor.org/rfc/rfc9849.html), read 2026-11-21), and domain fronting or a literal IP bypasses name-based filtering ([Vercel Sandbox firewall](https://vercel.com/docs/sandbox/concepts/firewall), read 2026-11-21). Squid is packaged in noble ([packages.ubuntu.com](https://packages.ubuntu.com/noble/squid), read 2026-11-21), and Claude Code publishes the domains it needs ([network configuration](https://code.claude.com/docs/en/network-config.md), read 2026-11-21).
- Credentials injected outside the boundary, so that "The agent never sees the actual credentials" ([Agent SDK secure deployment](https://code.claude.com/docs/en/agent-sdk/secure-deployment), read 2026-11-21).
- `CLAUDE_CODE_SHELL_PREFIX` is a "Command prefix that wraps shell commands Claude Code spawns" ([environment variables](https://code.claude.com/docs/en/env-vars), read 2026-11-21).
- Unattended mode only inside a boundary: "Always run --dangerously-skip-permissions sessions inside a container, a VM, or the sandbox runtime" ([sandbox environments](https://code.claude.com/docs/en/sandbox-environments.md), read 2026-11-21); Claude Code refuses that flag when launched as root ([devcontainer](https://code.claude.com/docs/en/devcontainer.md), read 2026-11-21).
- Browsers in VMs: Playwright MCP "is not a security boundary" and its Docker image runs Chromium with `--no-sandbox` ([Playwright MCP](https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md), read 2026-11-21), and running Chromium as root in a container "will disable the Chromium sandbox" ([Playwright Docker](https://playwright.dev/docs/docker), read 2026-11-21).

## Disagreement, and how it was decided

- **The API-key gateway.** A small custom gateway was chosen over LiteLLM: this component holds real API keys in the trusted base, and LiteLLM carries a large dependency graph and suffered supply-chain incidents in 2026 ([BleepingComputer](https://bleepingcomputer.com/news/security/popular-litellm-pypi-package-compromised-in-teampcp-supply-chain-attack), [Help Net Security](https://www.helpnetsecurity.com/2026/10/22/litellm-compromised-supply-chain-attack-pypi-docker/), 2026-11-21).
- **Secret delivery.** tmpfs files per job are simple and cleaned up when the job ends; a read-once socket remains a possible later hardening.
- **GitHub access.** GitHub App short-lived installation tokens are the default; deploy keys stay a fallback only because they never expire.

## Rejected

- Mounting host directories into project VMs, one shared Unix user for all projects, and tokens written into `.git/config`.
- Transparent name-based filtering (ECH, above).

## Open risks

- An allowed host can still carry data out, including a model provider's own API used with an attacker's key ([Embrace The Red](https://embracethered.com/blog/posts/2025/claude-abusing-network-access-and-anthropic-api-for-data-exfiltration/), read 2026-11-21).
- Bridge ACLs without OVN must be shown to cover IPv4 and IPv6 cleanly.
- The small custom gateway is new code holding keys; it needs its own tests and review before it is enabled.

## Verification tests

T4 (cross-project canary), T5 (egress) and T10 (split execution).
