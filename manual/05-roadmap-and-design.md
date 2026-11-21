<!-- SPDX-License-Identifier: MIT -->
# Roadmap and Architecture

Ötüken is developed in milestones toward v0.1.

## Implemented (Milestone 1 — pre-alpha)

- Signed release verification (`ssh-keygen -Y verify`), signer pinning, and key
  rotation (`engine/release.py`, `engine/main.py`).
- Deterministic `--plan` / `--apply --plan-id` installer, idempotent applies,
  run-once epoch migrations, Btrfs snapshots / ext4 exports, recovery,
  rollback, and ownership-scoped uninstall/purge (`engine/install.py`,
  `engine/backup.py`).
- Local guard prototype with unprivileged descriptor-handoff broker, lease and
  rate-limit enforcement, append-only chained audit journal, and digest-bound
  break-glass repair runner with drift detection (`engine/guard.py`,
  `engine/transport.py`, `engine/audit.py`, `engine/breakglass.py`).
- Offline Incus CI harness and synthetic T4–T6 isolation fixture builder
  (`ci/`, `ops/`).

## Planned for v0.1 and beyond

- **Swappable CTO seat VM** with `AGENTS.md`, skills, guard MCP server
  (`otuken mcp`), `otukenctl`, and supervised handover
  ([ADR 0006](../docs/adr/0006-cto-authority-and-guard.md),
  [ADR 0007](../docs/adr/0007-swappable-cto-contract.md)).
- **Per-project Incus KVM VMs** with per-project egress allowlist proxies,
  tmpfs per-job secrets, one-hour GitHub App tokens, and browser VMs
  ([ADR 0008](../docs/adr/0008-project-vms.md),
  [ADR 0010](../docs/adr/0010-least-privilege-and-browsers.md)).
- **Native subscriptions and catalog:** each subscription will run inside its
  own native agent (Claude in Claude Code, ChatGPT in Codex, and so on) with no
  subscription proxy ([ADR 0003](../docs/adr/0003-install-flow-and-catalog.md),
  [ADR 0004](../docs/adr/0004-subscriptions-and-logins.md)).
- **Local AI home-server lane:** planned module enabled per hardware profile
  (GPU, measured CPU, or a private-network OpenAI-compatible server) so owners
  can run Ötüken as a home server
  ([ADR 0005](../docs/adr/0005-local-model.md)).
- **Agent vault & wall-board contract:** provenance-tracked LLM wiki with
  drafts-then-merge quarantine and a read-only CloudEvents board contract
  ([ADR 0011](../docs/adr/0011-vault.md),
  [ADR 0012](../docs/adr/0012-board-contract.md)).
- **Kill switch and off-box backups:** four-level reboot-persistent kill switch
  and append-only restic/S3 Object Lock backups
  ([ADR 0013](../docs/adr/0013-security-kill-switch-caps.md),
  [ADR 0014](../docs/adr/0014-backups.md)).

Read the full [architecture design](../docs/DESIGN.md) and
[ADR index](../docs/adr/README.md).
