<!-- SPDX-License-Identifier: MIT -->
# Decision records

Architecture decision records for **Ötüken** (`otuken`), one file each. The
full design document, including the summary, disagreement table, and
verification test matrix, is [DESIGN.md](../DESIGN.md).

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-install-and-releases.md) | Install, releases, updates and rollback | Accepted |
| [0002](0002-ci-and-release-gate.md) | Self-hosted CI and the release gate | Accepted |
| [0003](0003-install-flow-and-catalog.md) | The install flow and the worker catalog | Accepted |
| [0004](0004-subscriptions-and-logins.md) | Subscriptions and logins: native agent per subscription, no consumer-login proxy | Accepted |
| [0005](0005-local-model.md) | The local AI lane (home-server support) | Accepted |
| [0006](0006-cto-authority-and-guard.md) | The CTO's authority, bounded by a non-agent guard | Accepted |
| [0007](0007-swappable-cto-contract.md) | A swappable CTO: the contract, the supervisor and handover | Accepted |
| [0008](0008-project-vms.md) | One KVM VM per project | Accepted; T2 |
| [0009](0009-vm-storage-bake-off.md) | VM storage on a btrfs-only host | Open; T1 decides |
| [0010](0010-least-privilege-and-browsers.md) | Least knowledge and least privilege per project, and browser VMs | Accepted; T10 |
| [0011](0011-vault.md) | The vault: a self-improving LLM wiki | Accepted |
| [0012](0012-board-contract.md) | The wall-board data contract | Accepted |
| [0013](0013-security-kill-switch-caps.md) | Security model: principals, threats, kill switch and caps | Accepted |
| [0014](0014-backups.md) | Backups | Accepted |
| [0015](0015-core-and-private-overlay.md) | Core vs. private overlay separation | Accepted |
| [0016](0016-license-and-notice.md) | Licence, NOTICE and what the product may redistribute | Accepted |
| [0017](0017-name-and-prior-art.md) | Name, trademarks and prior art | Accepted |
