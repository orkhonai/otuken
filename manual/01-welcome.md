<!-- SPDX-License-Identifier: MIT -->
# Welcome to Ötüken

**Status: Pre-alpha (`0.0.1-prealpha.1`).** Ötüken is not ready for production
until v0.1 passes its full installer, isolation, and restore test gates. No
signed release or release key is published yet.

Ötüken is an agent-native layer for an Ubuntu 24.04 LTS server or home server
you own. It is designed as a single-owner system: one owner, their own
hardware, and their own accounts (hosting it for other people changes which
vendor terms apply). For the origin of the name, see
[Why Ötüken](../README.md#why-ötüken).

## What exists today (Milestone 1 — pre-alpha)

- **Stock Ubuntu, no custom ISO.** Installs onto Ubuntu 24.04 LTS amd64 (Btrfs
  or ext4) without repartitioning or taking over your rescue admin user.
- **Verify before execute; plan before apply.** Releases are signed with an
  offline SSH key (`ssh-keygen -Y verify`). Every change is planned first,
  bound to its plan digest under lock, and backed by Btrfs snapshots or ext4
  exports with automatic rollback.
- **Local guard prototype.** An unprivileged socket broker and privileged
  executor enforce leases, rate limits, append-only hash-chained audit logging,
  and digest-bound break-glass repairs with drift detection.
- **Offline CI harness.** Synthetic Incus VM tests for clean install, upgrade,
  rollback, and nested isolation gates.

## Planned architecture (v0.1 roadmap)

The core multi-VM and agent runtime features are designed in the ADRs and
planned for later milestones:

- **Swappable CTO seat VM *(planned)*.** A guard-bounded CTO agent will run
  inside its own VM and change the host only through the non-agent guard under
  owner policy.
- **One VM per project *(planned)*.** Each coding project will get its own KVM
  VM, egress allowlist, and scoped credentials.
- **Native subscriptions, no proxy *(planned)*.** Each subscription will run
  inside its own native agent (Claude in Claude Code, ChatGPT in Codex, and so
  on); Ötüken will never ship a consumer-login proxy.
- **Home-server local AI *(planned)*.** A local-model lane will let you run
  Ötüken as a home server, enabled per hardware profile (GPU, measured CPU, or a
  private-network OpenAI-compatible server).

See [Roadmap and Architecture](05-roadmap-and-design.md), the full
[architecture design](../docs/DESIGN.md), and the project site at
[otuken.tech](https://otuken.tech) *(coming online)*.
