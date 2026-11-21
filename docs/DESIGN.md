<!-- SPDX-License-Identifier: MIT -->
# Ötüken: the design

**Ötüken** (`otuken`, [otuken.tech](https://otuken.tech)) is an MIT-licensed,
agent-native server layer for stock Ubuntu 24.04 LTS servers and home servers,
inspired by Omarchy's repository shape, release discipline, and run-once
migrations. This document collects the architecture decision records (ADRs),
major trade-offs, and verification test matrix. Every decision also lives in
its own file under [`adr/`](adr/README.md); the text is the same.

Dated 2026-11-21.

## The ten design pillars

1. **Install and releases (ADR 0001, 0002):** a signed release tarball installed onto stock Ubuntu 24.04 LTS, verified with `ssh-keygen -Y verify`, shown as a `--plan`, and applied only with that plan's digest; cloud-init only calls it; no custom ISO and no pipe-to-shell; CI installs twice, reboots the test VM, and upgrades from the previous release.
2. **Install flow, subscriptions, and local AI (ADR 0003, 0004, 0005):** deterministic base, then the CTO seat, workers from a twelve-agent catalog, each subscription running inside its own native agent (Claude in Claude Code, ChatGPT in Codex, and so on) with no consumer-login proxy, a planned local AI lane enabled per hardware profile so owners can run Ötüken as a home server, and the board contract.
3. **CTO authority (ADR 0006):** the CTO is root inside its own VM and changes the host only through a non-agent guard (an unprivileged request broker and a tiny root executor that alone holds the Incus socket): automatically within policy limits, with the owner's approval for host changes and for exact root scripts; no agent-held host root.
4. **Swappable CTO (ADR 0007):** the job lives in files, one `AGENTS.md`, the guard's MCP tools (`otuken mcp`) and identical CLI (`otukenctl`), skills, and a guard-owned journal; the supervisor owns wake-ups; handover works even when the old CTO is dead; Claude Code and Codex first, Pi as fallback, oh-my-pi and Hermes after passing both roles.
5. **Sandboxes (ADR 0008, 0009, 0010):** one Incus 7.0 LTS KVM VM per project, containers only as an opt-in light profile, every browser in its own VM, 4 project VMs plus 1 browser as the reference 64 GiB starting ceiling, a bridge and allowlist proxy per project, tmpfs secrets per job, one-hour single-repository GitHub App tokens; the VM storage pool on btrfs-only hosts is settled by benchmark T1.
6. **Vault (ADR 0011):** a separate git vault; drafts through the guard, deterministic checks, a tool-less model check, then canonical; guard-stamped provenance and trust that only goes down; no instructions in the vault; two-way sync with the owner's vault, one-way in authority.
7. **Board contract (ADR 0012):** a JSON snapshot plus an append-only CloudEvents log with a cursor and a JSON Schema, filled from runtime facts and read-only; remaining usage limits reported only from documented vendor routes, otherwise `unavailable`.
8. **Security and backups (ADR 0013, 0014):** a threat model grounded in 2025–2026 agent security incidents; a four-level kill switch that survives a reboot; per-job and per-account caps with a loop breaker; optional off-box append-only backups without logins.
9. **Core vs. overlay (ADR 0015):** public mechanisms and defaults live in `orkhonai/otuken`; owner-specific hostnames, keys, account labels, and custom rules live in a separate private overlay repository at `/etc/otuken/overlay`.
10. **Licence and name (ADR 0016, 0017):** MIT; `NOTICE` and `THIRD_PARTY_NOTICES.md` for copied code and `docs/THIRD-PARTY-TOOLS.md` for fetched tools; never ship proprietary agents preinstalled; named Ötüken (`otuken`, `otukenctl`, `otuken.tech`); inspired by Omarchy; AgentVerse OS credited as closest prior art.

## Key architectural resolutions

| # | Topic | Decision | ADR |
| --- | --- | --- | --- |
| 1 | Pipe-to-shell bootstrap | None; verify signature and checksum, then plan and apply | ADR 0001 |
| 2 | Whole-system btrfs rollback | Not promised (root subvol ID 5 / Ubuntu `subvol=@` constraints); snapshot `/etc/otuken` and `/var/lib/otuken` | ADR 0001 |
| 3 | Where the CTO runs | Dedicated seat VM (host user fallback only without KVM) | ADR 0006 |
| 4 | Agent-held host root | None in the product; owner-approved exact tier-3 scripts with drift alarms | ADR 0006 |
| 5 | Antigravity on consumer plans | Owner-run only; managed use requires API key or Cloud project | ADR 0004 |
| 6 | Subscription logins in project VMs | Native agent per subscription; one per project, owner-approved, never next to untrusted code, never shared | ADR 0004 |
| 7 | Claude setup tokens | Inference-only token inside the single VM that uses it; never in a host-wide store | ADR 0004 |
| 8 | SuperGrok in OpenCode and Kilo | Candidate route enabled only after a pin-time plan check | ADR 0004 |
| 9 | First-screen catalog | Twelve harnesses by survey share and native subscription coverage | ADR 0003 |
| 10 | Local AI lane | Planned home-server module enabled per hardware profile (GPU, private-network server, or measured CPU) | ADR 0005 |
| 11 | API-key gateway | Small purpose-built gateway in the trusted base | ADR 0010 |
| 12 | Incus source | Zabbly 7.0 LTS with out-of-band key fingerprint verification and apt pinning | ADR 0008 |
| 13 | VM storage on btrfs-only hosts | Benchmark bake-off (T1); `dir` pool for initial CI/test VMs | ADR 0009 |
| 14 | Starting concurrency | 4 normal project VMs + 1 browser VM on reference 64 GiB host, verified by T2 | ADR 0008 |
| 15 | Harness transport | Chosen per pinned version's tested capabilities (ACP where complete, native structured mode otherwise) | ADR 0007 |
| 16 | Job-state record | One guard-owned append-only journal (`STATUS.md` line 1 validated against it) | ADR 0007 |
| 17 | Vault pages as instructions | Never; rule changes go through owner-approved `AGENTS.md`/skill proposals | ADR 0011 |
| 18 | Owner's personal notes | Separate vault with read-only mirror and `outbox/owner/` proposals | ADR 0011 |
| 19 | Raw source captures | Stored outside the synced vault in `/var/lib/otuken/evidence/` | ADR 0011 |
| 20 | Board v1 | CloudEvents files + JSON Schema + thin read-only HTTP/SSE view | ADR 0012 |
| 21 | Undocumented usage readers | Excluded from the public product | ADR 0012 |
| 22 | Fetched tools in NOTICE | Tracked separately in `docs/THIRD-PARTY-TOOLS.md` | ADR 0016 |
| 23 | GitHub access | Short-lived, per-repo GitHub App installation tokens (1 hour) | ADR 0010 |
| 24 | Kill switch | Four escalating levels (`freeze`, `cut`, `stop`, `revoke`), reboot-persistent | ADR 0013 |

## Decision records

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](adr/0001-install-and-releases.md) | Install, releases, updates and rollback | Accepted |
| [0002](adr/0002-ci-and-release-gate.md) | Self-hosted CI and the release gate | Accepted |
| [0003](adr/0003-install-flow-and-catalog.md) | The install flow and the worker catalog | Accepted |
| [0004](adr/0004-subscriptions-and-logins.md) | Subscriptions and logins: native agent per subscription, no consumer-login proxy | Accepted |
| [0005](adr/0005-local-model.md) | The local AI lane (home-server support) | Accepted |
| [0006](adr/0006-cto-authority-and-guard.md) | The CTO's authority, bounded by a non-agent guard | Accepted |
| [0007](adr/0007-swappable-cto-contract.md) | A swappable CTO: the contract, the supervisor and handover | Accepted |
| [0008](adr/0008-project-vms.md) | One KVM VM per project | Accepted; T2 |
| [0009](adr/0009-vm-storage-bake-off.md) | VM storage on a btrfs-only host | Open; T1 decides |
| [0010](adr/0010-least-privilege-and-browsers.md) | Least knowledge and least privilege per project, and browser VMs | Accepted; T10 |
| [0011](adr/0011-vault.md) | The vault: a self-improving LLM wiki | Accepted |
| [0012](adr/0012-board-contract.md) | The wall-board data contract | Accepted |
| [0013](adr/0013-security-kill-switch-caps.md) | Security model: principals, threats, kill switch and caps | Accepted |
| [0014](adr/0014-backups.md) | Backups | Accepted |
| [0015](adr/0015-core-and-private-overlay.md) | Core vs. private overlay separation | Accepted |
| [0016](adr/0016-license-and-notice.md) | Licence, NOTICE and what the product may redistribute | Accepted |
| [0017](adr/0017-name-and-prior-art.md) | Name, trademarks and prior art | Accepted |

## ADR 0001 · Install, releases, updates and rollback

**Status:** Accepted, 2026-11-21. **Topic:** Install, releases, updates and rollback.

### Decision

1. **Base.** Stock Ubuntu Server 24.04 LTS, amd64, systemd with cgroup v2, fresh or already in use. The root filesystem may be btrfs (with or without mdadm RAID1) or ext4. On btrfs the snapshot module is on; on ext4 the plan says plainly that there are no host snapshots and recommends the off-box backup module. The installer never repartitions and never changes the boot layout. Ubuntu 26.04 LTS joins the CI matrix as a non-gating target from v0.2 and becomes supported when it passes the same gate; arm64 comes later.
2. **No ISO, no image.** The product is a layer installed onto an Ubuntu box the owner already has.
3. **One signed artefact per release:** `otuken-<version>.tar.gz` (the repository at the tag), `SHA256SUMS`, and an SSH signature over `SHA256SUMS`, made with an offline release key and checked with `ssh-keygen -Y verify` against an `allowed_signers` file whose fingerprint is published with each signed GitHub release (and on [otuken.tech](https://otuken.tech) once the site is live). Git tags are signed with the same key. Key rotation and revocation are written down and rehearsed before v0.1. Sigstore bundles and GitHub artifact attestations are added once releases publish on GitHub; a gpg-signed apt repository once there are outside users.
4. **Entry points, one engine.**
   - Documented path: download the release and its signature, verify, `sudo ./otuken install --plan`, then `sudo ./otuken install --apply --plan-id <digest>`. The README shows these as one copy-paste block.
   - Unattended: a `#cloud-config` whose `write_files` drops an answers file and whose `runcmd` fetches, verifies and applies the same release with `--yes`. Provider logins stay pending, so no login or key is ever in user-data.
   - No pipe-to-shell one-liner anywhere.
5. **Plan and apply.** Every module implements `plan()` (read-only) and `apply()`. `--plan` prints files with diffs, packages, users, units, firewall rules, subvolumes and Incus objects, plus a JSON form and a plan digest. `--apply --plan-id` re-plans under a lock and refuses if the digest changed. Exit codes: 0 nothing to do, 2 changes pending, 1 error. A second apply must plan nothing and restart nothing. The engine is Python 3 standard library only, with a short Bash loader, built on compare-before-write atomic primitives.
6. **Paths.** Shared code, the owner's choices and data never mix:

   | What | Where | Owner | Local snapshot | Off-box backup |
   | --- | --- | --- | --- | --- |
   | Shared code, one directory per release | `/opt/otuken/releases/<version>/`, `/opt/otuken/current` (symlink) | root, read-only | no (re-downloadable) | no |
   | Owner's choices | `/etc/otuken/` (wizard answers, guard policy ceilings, `overlay/` = checkout of the private overlay) | root | yes | yes |
   | Product state | `/var/lib/otuken/` (`state/`, `journal/`, `board/`, `audit/`, `hq/`, `vault/`, `evidence/`) | root; `hq/` and the vault are shared into the CTO's seat (ADR 0007) | yes | yes (audit append-only) |
   | Host credential store (API keys for the gateway, the GitHub App key) | `/var/lib/otuken/credentials/` as systemd credentials | root, 0700 | yes (root-only) | no by default |
   | Sockets and runtime files | `/run/otuken/` | root | no | no |
   | Provider logins | inside the seat VM and each project VM, in each harness's own store | that VM | with that VM | no (log in again after a restore) |
   | Sandboxes | an Incus storage pool (ADR 0009) | Incus | per project | opt-in per project |
   | Caches and verified downloads | `/var/cache/otuken/` | root | no | no |

7. **Updates.** Semantic versions for the layer, separate schema versions for its contracts (board, job, catalog). Channels `stable` and `rc`; a git checkout is the contributors' `dev`. `otuken update` reads a small signed channel file with an expiry, remembers the highest version it has installed, refuses anything lower (only `otuken rollback` may go back), and treats expired metadata as an error. It then verifies, plans, snapshots `/etc/otuken` and `/var/lib/otuken` (btrfs) or exports them (ext4), applies, runs pending migrations, runs health checks, and rolls back by itself if they fail. Migrations are `migrations/<epoch>.py`, each run once, with markers in `/var/lib/otuken/state/migrations/`, on the same filesystem as the data they change; `--pending` lists what has not run. A data-format migration refuses to run without a successful pre-update snapshot or export. Harness CLIs never update themselves: their versions and digests are pinned in a signed catalog that can be refreshed between layer releases, with a cool-down before a new upstream version is pinned. unattended-upgrades stays at its security-only default; a needrestart override keeps it from restarting long-running agent units in the middle of a turn, and the guard restarts them between jobs.
8. **Uninstall and rollback.** `otuken uninstall` first reopens public SSH if the remote-access module had closed it, then removes units, rules and `/opt/otuken`, keeping `/etc/otuken` and `/var/lib/otuken`. It removes only what its ownership manifest says it installed, so packages and rules that were there before stay. `--purge` also removes the kept directories after a final snapshot and a typed confirmation (`purge otuken`), and still refuses to delete a project whose repository has uncommitted or unpushed work. Neither command touches the provider's admin user, which stays the human's rescue path. `otuken rollback` repoints `current` to the previous release and restores the pre-update snapshot of `/etc/otuken` and `/var/lib/otuken`; projects and the vault are not rolled back. The product does not promise a bootable whole-system rollback; OS-level rollback stays a rescue-mode operation.

### Reasons

- Omarchy is the model for discipline, not for the install medium. Its README says "The Omarchy ISO is the only supported way to install Omarchy" ([Omarchy ISO README](https://raw.githubusercontent.com/omacom/omarchy-iso/quattro/README.md), read 2026-11-21), and its old installer URL now says "The online installer this script used to fetch was removed in June 2026" ([omarchy.org/install](https://omarchy.org/install), read 2026-11-21). What it keeps is worth following: package-owned code, separate config and state, epoch-named run-once migrations with markers and `--pending`, channels, and CI that installs and upgrades before anything is published ([updates manual](https://raw.githubusercontent.com/omacom/omarchy/quattro/manual/30-updates.md), [omarchy-migrate](https://raw.githubusercontent.com/omacom/omarchy/quattro/bin/omarchy-migrate), [omarchy-pkgs](https://raw.githubusercontent.com/omacom/omarchy-pkgs/master/README.md), all read 2026-11-21).
- No ISO: a server layer has to land on a box that already runs Ubuntu, and Canonical allows redistributing Ubuntu "only where there has been no modification to it" ([Canonical IP policy](https://canonical.com/legal/intellectual-property-policy), read 2026-11-21).
- Migration markers live with their data: Omarchy's manual notes that after booting a pre-update snapshot "Migrations that ran after the snapshot was taken stay marked as done", because its markers live in the home directory ([Omarchy snapshots](https://raw.githubusercontent.com/omacom/omarchy/quattro/manual/47-system-snapshots.md), read 2026-11-21).
- `ssh-keygen -Y verify` is already on a stock box: the noble cloud image lists `openssh-client`, `gpgv`, `python3`, `git` and `curl`, and no minisign or cosign ([noble image manifest](https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.manifest), read 2026-11-21); minisign is only in universe ([packages.ubuntu.com](https://packages.ubuntu.com/noble/minisign), read 2026-11-21); usage per [ssh-keygen(1)](https://man.openbsd.org/ssh-keygen.1) (read 2026-11-21).
- Attestations require a public repository on Free, Pro and Team plans: "artifact attestations are only available for public repositories" ([GitHub Docs](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations), read 2026-11-21).
- Signed channel metadata, because a signature on a tarball does not stop "Rollback attacks" or "Indefinite freeze attacks" ([TUF security](https://theupdateframework.io/docs/security/), read 2026-11-21).
- The plan digest follows Terraform's saved-plan idea ([terraform plan](https://developer.hashicorp.com/terraform/cli/commands/plan), read 2026-11-21).
- Python 3 standard library: it is on the stock image (manifest above), needs no build step, and makes plan/apply diffs and JSON straightforward. Ansible was rejected because "Check mode is just a simulation" and "Modules that do not support check mode report nothing and do nothing" ([Ansible check mode](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_checkmode.html), read 2026-11-21).
- needrestart: "Starting with Ubuntu 24.04 LTS, needrestart restarts the affected services automatically by default" ([Ubuntu automatic updates](https://ubuntu.com/server/docs/how-to/software/automatic-updates/), read 2026-11-21).
- cloud-init stays a caller: `runcmd` and `write_files` run once per instance ([cloud-init modules](https://docs.cloud-init.io/en/latest/reference/modules.html), read 2026-11-21), and the same file works as a NoCloud seed ([NoCloud](https://docs.cloud-init.io/en/latest/reference/datasources/nocloud.html), read 2026-11-21) and on Incus instances ([Incus cloud-init](https://linuxcontainers.org/incus/docs/main/cloud-init/), read 2026-11-21).
- No bootable whole-system rollback on this layout: the top-level btrfs subvolume (ID 5) "cannot be removed or replaced by another subvolume" ([btrfs subvolumes](https://btrfs.readthedocs.io/en/latest/Subvolumes.html), read 2026-11-21); `snapper rollback` works by setting the default subvolume ([snapper(8)](https://manpages.ubuntu.com/manpages/noble/man8/snapper.8.html), read 2026-11-21), and Ubuntu "will ALWAYS mount subvol=@ as / and never mount the default subvolume as /" ([Launchpad 1734496](https://bugs.launchpad.net/ubuntu/+source/snapper/+bug/1734496), read 2026-11-21). A parent snapshot also skips nested subvolumes, so each data subvolume is snapshotted on its own (btrfs page above).

### Disagreement, and how it was decided

- **One-line bootstrap.** Offering a `curl … | bash` bootstrap that embeds its verification key was rejected: the loader runs before anything has verified the loader, leaving TLS to the host as the sole protection for code running as root. Decided: no pipe-to-shell in the README or on the website. Install ergonomics are met by one copy-paste verification block and by the cloud-init path.
- **Whole-system rollback.** The btrfs and Launchpad sources above show bootable whole-system rollback fails for a root at subvolume ID 5 and for Ubuntu's `subvol=@` mount, so the product does not promise it.
- **Channel names:** `stable` and `rc`, matching Omarchy's naming.
- **Where HQ and the vault live:** `/var/lib/otuken`, rather than `/srv/otuken`, so all product state sits under one root for snapshots and backups.

### Rejected

- A custom ISO or a prebuilt image (above). Packer now ships under the Business Source License ([Packer LICENSE](https://raw.githubusercontent.com/hashicorp/packer/main/LICENSE), read 2026-11-21); prebuilt Incus images can come from CI instead.
- Running from a moving branch.
- Pure Bash for plan/apply (fragile at this size); Ansible (above); Nix or system-manager, which bring Nix onto a box meant to stay stock; Go for now, which needs a toolchain and a binary to sign (revisit if the guard needs it).
- gpg as the primary signature: a stock box already verifies SSH signatures; gpg arrives with an apt repository later.

### Open risks

- The offline release key is a single point of trust; its loss or theft is a release-wide incident until rotation is rehearsed.
- ext4 hosts have no host snapshots, so rollback there rests on the pre-update export; the plan says so.
- needrestart exclusions delay library fixes for long-running units until the guard restarts them between jobs.

### Verification tests

T8 (installer matrix) and T17 (nested KVM), in ADR 0002.

## ADR 0002 · Self-hosted CI and the release gate

**Status:** Accepted, 2026-11-21. **Topic:** CI and the release gate.

### Decision

- **CI is a script in the repository** (`ci/run`) that any owner can run on a KVM host. On a shared host it runs inside a capped Incus project (`otuken-ci`), with CPU, memory and I/O limits that leave live services and running jobs their room. A systemd timer or manual invocation starts it; logs go to the run's evidence directory, and posting a GitHub commit status is optional.
- **Each run**, in throwaway VMs launched from a pinned, verified Ubuntu 24.04 cloud image (`incus launch images:ubuntu/24.04/cloud --vm -e` or offline verified fixtures):
  1. a clean install on btrfs and on ext4, through both the manual and the cloud-init entry points;
  2. a second apply in the same VM: empty plan, no service restarted, no duplicate resource, no data lost;
  3. a reboot of the **test VM** (never of the host), then a check that every service, rule and timer comes back;
  4. install the previous release, seed a project, a vault page and a policy, `update` to the candidate, reboot the test VM, run a job, then rehearse `rollback` and `uninstall` (public SSH reopened);
  5. the isolation tests: project A cannot read project B's secret by any route, including from root inside A (T4); a worker cannot reach the guard's owner socket or the seat's control channel (T6); egress outside the allowlist fails over IPv4 and IPv6 (T5); the kill switch holds across a test-VM reboot (T7); interruption and retry of an apply are safe;
  6. destroy the VMs.
- The installer launches VMs itself, so the test VMs need nested KVM. Where it is missing, the installer tests and the VM-isolation tests run separately, and both must pass.
- A backup restore into a fresh VM runs once per release, not per change, because it is slow; a failing restore blocks the release.
- CI VMs use sanitized fixtures only: no live credentials, no release keys, no control sockets. Subscription smoke tests stay separate from untrusted pull-request CI.
- **Release gate** (v0.1 bar): three clean runs and one upgrade run on Ubuntu 24.04, with logs; the cross-project secret test; two CTO harnesses and two worker harnesses passing a real job in both roles (ADR 0007).
- **Public repository CI:** unit and lint jobs, and VM jobs if hosted runners can boot full VMs fast enough, run on GitHub-hosted runners. Any self-hosted runner never executes pull requests from forks; hardware tests run only for maintainer-approved branches and tags.

### Reasons

- Self-hosted runners are free today ([GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), read 2026-11-21), though GitHub announced and then postponed a per-minute charge for them ([GitHub pricing changes](https://github.com/resources/insights/2026-pricing-changes-for-github-actions), read 2026-11-21). A plain script depends on neither.
- Ephemeral Incus instances get "deleted when stopped" ([incus launch](https://linuxcontainers.org/incus/docs/main/reference/manpages/incus/launch/), read 2026-11-21).
- "self-hosted runners should almost never be used for public repositories on GitHub" ([GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use), read 2026-11-21); GitHub also documents how a compromise can persist on a self-hosted runner ([compromised runners](https://docs.github.com/en/actions/concepts/security/compromised-runners), read 2026-11-21).
- Hosted runners are "free and unlimited on public repositories" ([GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners), read 2026-11-21), and KVM has been usable on them since 2024 ([GitHub changelog](https://github.blog/changelog/2024-04-02-github-actions-hardware-accelerated-android-virtualization-now-available/), read 2026-11-21); whether full VMs boot fast enough there remains to be measured.

### Rejected

- A GitHub Actions self-hosted runner as the only CI path: self-hosted runner pricing has been in flux, and public PRs cannot safely execute on a self-hosted host.
- Forgejo's runner (requires a Forgejo server) and Buildkite (hosted control plane) ([Forgejo runner](https://forgejo.org/docs/latest/admin/actions/runner-installation/), [Buildkite pricing](https://buildkite.com/pricing/), read 2026-11-21).

### Open risks

- Nested KVM inside Incus VMs depends on host kernel and CPU configuration and must be verified per CI host (T17).
- Self-hosted CI on a shared host competes with live workloads; resource caps must be enforced before the first run.

### Verification tests

T8 (installer matrix, idempotence, test-VM reboot, upgrade, rollback, uninstall) and T17 (nested KVM).

## ADR 0003 · The install flow and the worker catalog

**Status:** Accepted, 2026-11-21. **Topic:** Install flow and worker catalog.

### Decision

The flow, as the owner sees it. Every step has a plain terminal fallback, so the install never depends on a model answering.

1. **Base** (deterministic, no model): ADR 0001. Result: the guard, snapshots, Incus, a firewall with SSH open, the board endpoint, an empty HQ and vault, and the CTO's seat VM.
2. **CTO harness.** Only harnesses that pass the CTO bar for their pinned version can be chosen (ADR 0007); the others show as experimental. The installer puts the pinned version into the seat and runs that harness's own login. From here the CTO talks to the owner; the wizard keeps running underneath.
3. **Workers.** The catalog's twelve, each shown with its licence, the subscriptions it can use natively, its headless mode, its test status and its popularity evidence. Unticked agents are not installed; `otuken add <harness>` adds any of them later.
4. **Subscriptions and logins** (ADR 0004). The owner ticks what they pay for. Each subscription runs inside its own native agent (Claude in Claude Code, ChatGPT in Codex, and so on) using the provider's own login flow inside the VM where that agent runs, relayed to the owner's screen as a URL and code or a QR code for the phone. Skipping is allowed; enrollment resumes later without re-running the base.
5. **Local AI lane** (ADR 0005), enabled per hardware profile (GPU home server, measured CPU profile, or private-network model server).
6. **Optional cross-use module** (ADR 0004), off by default, with a terms screen per provider.
7. **Optional modules:** remote access (Tailscale, WireGuard or none), off-box backup, vault sync, the control-app integration (bb), exec audit.
8. **Board.** The contract is always on, on loopback; publishing it on the private network and a minimal reference page are options (ADR 0012).
9. **Smoke test.** Each installed worker does one tiny real job in a throwaway sandbox (create a file, run a test, commit to a scratch branch), and the board must show the job, the worker, its account and a fresh usage-limit reading where documented. Setup reports green only after that.

**The twelve on the first screen.** The list is catalog data, not code. "Supported" means the role test passed on the pinned version; installing is not support.

| # | Agent | Licence | Native subscription | Headless entry | Popularity evidence (2026) |
| --- | --- | --- | --- | --- | --- |
| 1 | Claude Code | proprietary | Anthropic plans | `claude -p` | 65.5 % (SO); 39 % at work (JB); 156.5k stars; 21.7 M npm downloads a week |
| 2 | Codex CLI | Apache-2.0 | ChatGPT plans | `codex exec` | 29.5 % (SO); 16 % (JB); 136.0k stars; 27.5 M npm a week |
| 3 | GitHub Copilot CLI | proprietary | Copilot plans | `copilot -p` | Copilot 58.7 % (SO); 1.87 M npm a week |
| 4 | Cursor CLI | proprietary | Cursor plans | `agent -p` | Cursor 25.5 % (SO); 12 % (JB) |
| 5 | Antigravity CLI | proprietary | Google AI Pro and Ultra (owner-run only on consumer plans, ADR 0004) | `agy -p` | 16.0 % (SO); Google's successor to Gemini CLI for consumer plans |
| 6 | OpenCode | MIT | Copilot and ChatGPT (sanctioned), API keys | `opencode run --standalone` | 13.6 % (SO); 7 % (JB); 228.3k stars |
| 7 | Pi | MIT | ChatGPT (sanctioned), API keys | `pi -p`, `--mode rpc` | 4.4 % (SO); #4 CLI agent by tokens on OpenRouter; 123.1k stars; 6.6 M npm a week |
| 8 | oh-my-pi | MIT | as Pi | `omp -p`, `omp acp` | #7 on OpenRouter; 39.6k stars |
| 9 | Hermes Agent | MIT | ChatGPT (sanctioned), API keys | `hermes -z`, `hermes acp` | #1 on OpenRouter; 10.2 % in SO's orchestration-tools question; 265.0k stars |
| 10 | Kilo Code CLI | MIT | ChatGPT (sanctioned), SuperGrok (candidate, ADR 0004), API keys | `kilo run --auto` | #3 on OpenRouter; 3.2 % (SO); 28.1k stars |
| 11 | Cline CLI | Apache-2.0 | GLM plan, API keys | `cline "…"` | 4.5 % (SO); 71.8k stars |
| 12 | Mistral Vibe | Apache-2.0 | Mistral plans | `vibe --prompt … --auto-approve` | 3.2 % (SO); 231.5k PyPI downloads a week |

SO is the Stack Overflow Developer Survey 2026, "Have you used any of the following coding agents or assistants in the past year?" ([survey data](https://survey.stackoverflow.co/2026/ai/data), [question page](https://survey.stackoverflow.co/2026/ai/data/ai-code-agent), [results post](https://stackoverflow.blog/2026/10/06/the-results-of-the-2026-developer-survey-are-here/), read 2026-11-21). JB is JetBrains' AI coding agent adoption study, May–July 2026 ([JetBrains Research](https://blog.jetbrains.com/research/2026/08/ai-coding-agent-adoption-2026/), read 2026-11-21). OpenRouter ranks one day of usage through 2026-11-20 and counts only apps routed through it ([OpenRouter](https://openrouter.ai/apps/category/coding/cli-agent), read 2026-11-21). Stars and downloads were read from `api.github.com/repos/<repo>`, `api.npmjs.org/downloads/point/last-week/<package>` and `pypistats.org/api/packages/<package>/recent` on 2026-11-21. Survey shares cover each product's surfaces, not only its CLI, and npm counts include CI installs and undercount tools installed by curl. Headless entries are from each vendor's documentation.

**One screen further:** Grok Build ([xAI](https://x.ai/news/grok-build-cli), read 2026-11-21), Kimi Code CLI (interactive use only on its plan), Qwen Code, Goose, Aider, Gemini CLI (API keys only), Junie CLI, Kiro CLI, Amp, Factory Droid, Crush (FSL, not open source). **Not offered:** Roo Code (shut down on 2026-05-15), Continue and the OpenHands CLI (no longer maintained) ([Roo Code](https://github.com/RooCodeInc/Roo-Code), [Continue](https://github.com/continuedev/continue), [OpenHands CLI](https://github.com/OpenHands/OpenHands-CLI), read 2026-11-21).

### Reasons

- The rule for the twelve: the six primary CTO candidate harnesses, plus OpenCode, then the next five by survey share and usage, preferring a native agent for each subscription an owner is likely to hold.
- Gemini CLI is not the Google consumer worker: "On June 18, 2026, Gemini CLI and Gemini Code Assist IDE extensions will stop serving requests for Google AI Pro and Ultra"; it remains for paid API keys ([Google Developers Blog](https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/), read 2026-11-21).
- OpenCode runs `--standalone`, because by default "OpenCode discovers or starts one shared background server for your user account", which would join projects together ([OpenCode CLI](https://opencode.ai/docs/cli/), read 2026-11-21).
- The smoke test and the terminal fallback make "installed" mean "works".

### Disagreement, and how it was decided

- Replacing Kilo Code and Mistral Vibe with Aider and goose was weighed and rejected: Aider has 2.1 % in the same survey against 3.2 % each for Kilo and Vibe, and Aider's last PyPI release was 0.86.2 of 2026-02-12 ([PyPI](https://pypi.org/pypi/aider-chat/json), read 2026-11-21); Kilo is #3 by tokens on OpenRouter; Vibe is the native agent for Mistral plans. Aider and goose stay available one screen further in the catalog.

### Rejected

- A twelve-agent install as the only path; every agent stays one command away.
- Calling an agent supported because its binary installs.

### Open risks

- Survey shares measure products, not CLIs, and popularity moves monthly; the catalog is reviewed at every release.
- Vendors change headless flags weekly; the adapter tests in ADR 0007 are what counts.

## ADR 0004 · Subscriptions and logins: native agent per subscription, no consumer-login proxy

**Status:** Accepted, 2026-11-21; vendor clarifications L1–L3 remain informational notes. **Topic:** Subscriptions, logins, and cross-use policy.

### Decision

1. **Default: each subscription runs inside its own native agent.** Claude runs inside Claude Code, ChatGPT runs inside Codex, Copilot runs inside Copilot CLI, Cursor runs inside Cursor CLI, and so on. Each agent logs in with its provider's own flow inside the VM where it runs and stores credentials in its own store. Ötüken never reads, copies, forwards, or backs up a subscription login, and ships no subscription proxy.
2. **Pooling by dispatch.** Using multiple subscriptions together is delivered by the CTO routing each job to the native agent whose subscription has room: Claude work to Claude Code, ChatGPT work to Codex, and so on. No token moves.
3. **One login per project, never next to code the owner did not write.** No login store is shared between projects, and none is moved between VMs. Each project VM gets its own login per provider the first time it uses that provider (one tap on the phone), so a compromised project exposes only its own, separately revocable session. The CTO's logins live only in the seat. A subscription login enters a project VM only if the owner allowed it for that project (the default for the owner's own repositories, shown as a risk when the project is created). Code the owner did not write (forks, outside pull requests, third-party repositories) never runs next to a subscription login: such jobs use an API-key or local-model route, or wait.
   - Claude: Claude Code's own login inside the VM is the default. An inference-only setup token created by the owner for a single VM may be kept inside that VM for unattended workers, never in a host-wide store.
   - Codex: `codex login --device-auth` with `cli_auth_credentials_store = "file"` on servers.
4. **No automated rotation** between accounts of the same provider. The owner assigns accounts to roles or projects; when one runs low, its work waits or goes to another provider's native agent or a local model.
5. **The opt-in cross-use module** (off by default) contains a route registry and nothing that proxies a consumer login:
   - **Lane A, sanctioned native cross-use,** configured in the harness itself, with no proxy in the path. Each route is a registry entry: provider, plan, allowed clients and uses, the terms URL, the date reviewed, and an expiry after which it switches itself off until it is reviewed again. A route with unclear, expired or changed permission stays off. Candidates, each enabled only after a check at pin time: ChatGPT sign-in in participating tools (OpenCode, Pi, Hermes, Kilo), with the owner's express consent to background use recorded; Copilot in OpenCode; SuperGrok in OpenCode and Kilo once the owner's exact plan is confirmed eligible (L3); GLM and MiniMax plan keys in their listed tools; OpenCode Go in its validated agents, with Extra Usage off; a Mistral key for the owner's own use; Kimi Code only in interactive sessions.
   - **Lane B, API keys behind a small host gateway** (ADR 0010): the only place real API keys live; a VM gets a per-job token with a money cap. Anthropic's monthly API credits on Max, Ultra and Team plans come in here as an API key: the sanctioned substitute for using an Anthropic plan in other agents.
   - **Refused and hard-blocked:** Claude, Google and Cursor consumer logins in any other client; managed or unattended use of `agy` on a consumer Google plan (owner-run only); unattended use of plans limited to interactive work (Kimi Code); aggregation of Z.ai plans; general-purpose re-exposure of a ChatGPT plan; client-identity spoofing; automated same-provider account rotation; silent fallback to paid usage.
6. **Not shipped, documented or linked:** CLIProxyAPI, or any tool that logs in as an official client and re-serves the plan to other tools. A custom OpenAI-compatible endpoint is allowed only as an API-key or local-model route under the same registry rules, with no risk-acceptance override.
7. **The terms are shown.** The catalog stores each provider row with its URL, quote and the date read; the wizard shows it before each login, and the terms are re-read at every minor release.

### Reasons (the providers' own words; every page read 2026-11-21)

- **Anthropic.** Usage Policy, effective 2026-11-12: "Resell, proxy, or otherwise provide access to Claude through unauthorized means, including services that route requests through consumer subscriptions or misrepresent the product or client being used" ([Usage Policy](https://www.anthropic.com/legal/aup)). Claude Code's legal page: "Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, Max, or Ultra plan credentials on behalf of their users. Moreover, developers may not collect, store, or intermediate Claude.ai credentials or session tokens"; and it does not prevent "an end user from signing in to the unmodified Claude Code binary with their own Claude subscription, including where a platform hosts Claude Code" ([legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)). The setup token is "a one-year OAuth token" that "can only make model requests" ([authentication](https://code.claude.com/docs/en/authentication)). The plan credits: "Use them to build Claude into your own apps and agents with the Claude API" ([Claude Help Center](https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-ultra-and-team-plans)). All read 2026-11-21.
- **OpenAI.** Sign in with ChatGPT terms, effective 2026-11-04, §3.1: "Do not provide general-purpose API access for other tools or unrelated requests"; no "rotating accounts" or "Pooling, transferring, reselling, gifting, or sharing ChatGPT plan usage or Authentication Tokens"; requests from "a remote runtime only that user controls"; "Obtain express consent before background use" ([SIWC terms](https://openai.com/policies/sign-in-with-chatgpt-terms/)). "Supported open-source tools remain available to all ChatGPT users" ([OpenAI Help Center](https://help.openai.com/en/articles/20001542-using-your-chatgpt-plan-in-other-apps-and-sites)), and the directory lists OpenClaw, OpenCode, Pi, T3, Amp, Conductor, Hermes Agent, Kilo Code and Warp ([SIWC directory](https://learn.chatgpt.com/docs/sign-in-with-chatgpt)). For a self-hosted VM: "Let the VM own later refreshes" ([self-hosted VMs](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms)); "serialize refreshes for the same session so two processes do not race a rotating token" ([profiles and sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions)); for Codex, "Do not share the same file across concurrent jobs or multiple machines" ([Codex CI/CD auth](https://learn.chatgpt.com/docs/auth/ci-cd-auth)); `keyring` storage "fails if it is unavailable" ([Codex auth](https://learn.chatgpt.com/docs/auth)). All read 2026-11-21.
- **Google.** Antigravity FAQ: "Antigravity CLI headless mode (agy -p) is intended for direct scripting and CI workflows. Wrapping agy inside third-party coding agents or applications, or automating account rotation, is not supported under consumer plans" ([FAQ](https://antigravity.google/docs/faq)). Antigravity terms §6: "Using third party software, tools, or services to access the Service (e.g. using OpenClaw with Antigravity OAuth) is a breach of this Agreement" ([terms](https://antigravity.google/terms)). Gemini CLI: "Using third-party software… to harvest or piggyback on Gemini CLI's OAuth authentication to access our backend services is a direct violation" ([Gemini CLI FAQ](https://github.com/google-gemini/gemini-cli/blob/main/docs/resources/faq.md)). All read 2026-11-21.
- **GitHub.** "GitHub is officially supporting using your Copilot Pro, Pro+, Business, or Enterprise subscription with OpenCode" ([GitHub changelog](https://github.blog/changelog/2026-01-16-github-copilot-now-supports-opencode/)). All read 2026-11-21.
- **xAI.** Its own posts tell SuperGrok and X Premium users to sign in from OpenCode, with a "Headless / Remote / VPS" option, and from Kilo Code ([Grok in OpenCode](https://x.ai/news/grok-opencode), [Grok in Kilo Code](https://x.ai/news/grok-kilocode)); the newer X Subscription pool covers Grok "in the Grok apps, the Grok tab on X, or Cursor" ([X Subscription](https://x.ai/news/x-subscription)). All read 2026-11-21.
- **Cursor.** A staff answer: "Using your subscription outside official clients can trigger abuse enforcement, up to and including an account ban" ([Cursor forum](https://forum.cursor.com/t/does-using-oh-my-pi-s-cursor-provider-or-an-openai-compatible-proxy-to-the-same-endpoints-violate-cursor-s-tos/167778)). All read 2026-11-21.
- **Others.** Kimi Code: "subscriptions are for interactive use only" and "Sharing your account with others through a reverse proxy is a violation" ([Kimi guidelines](https://www.kimi.com/en/help/kimi-code/community-guidelines)). Z.ai: "you may not resell, sub-resell, repackage, aggregate, proxy or otherwise provide the GLM Coding Plan to any third party" ([Z.ai terms](https://docs.z.ai/legal-agreement/subscription-terms)), and the plan is "limited to use within the following officially supported tools" ([Z.ai tools](https://docs.z.ai/devpack/tool/others)). Mistral's commercial terms §2.2(i) forbid to "integrate or combine Vibe with your own products you offer to third-parties" without written authorization ([Mistral terms](https://legal.mistral.ai/terms/commercial-terms-of-service/)). OpenCode Go "is designed for OpenCode and other coding agents that produce similar types of requests", and "Go Teams starts with Extra Usage on" ([OpenCode Go](https://opencode.ai/docs/console/go/)). Kilo documents that some subscription failures can fall back to an API key or Kilo credit ([Kilo](https://kilo.ai/docs/ai-providers/openai-chatgpt-plus-pro)), the kind of route the registry refuses. All read 2026-11-21.
- **What a consumer-login proxy is.** CLIProxyAPI "provides OpenAI/Gemini/Claude/Codex/Grok compatible API interfaces for CLI" with "round-robin load balancing" ([CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI)): the pooling, proxying and rotation the terms above forbid. All read 2026-11-21.
- **Enforcement is real** (news reports): in January 2026 Anthropic blocked tools "spoofing the Claude Code harness" ([VentureBeat](https://venturebeat.com/ai/anthropic-cracks-down-on-unauthorized-claude-usage-by-third-party-harnesses/)); OpenCode removed its Claude login after "anthropic legal requests" ([commit 973715f](https://github.com/anomalyco/opencode/commit/973715f)); Google cut off Antigravity access through third-party tools ([The Register](https://www.theregister.com/2026/02/23/google_antigravity_compute_burden/)). All read 2026-11-21.
- **One login per project.** Anthropic warns that dev containers "do not prevent a malicious project from exfiltrating anything accessible inside the container, including the Claude Code credentials stored in ~/.claude" ([devcontainer](https://code.claude.com/docs/en/devcontainer.md)); a shared or moved store is a cross-project credential; and OpenAI's "multiple machines" rule above. Claude Code users report concurrent sessions racing a single-use refresh token ([issue 24317](https://github.com/anthropics/claude-code/issues/24317), [issue 27933](https://github.com/anthropics/claude-code/issues/27933), [issue 91708](https://github.com/anthropics/claude-code/issues/91708)), which is why an inference-only setup token kept inside one VM is allowed for unattended workers. All read 2026-11-21.

### Disagreement, and how it was decided

- **Antigravity on consumer plans.** Wrapping `agy` inside third-party coding agents or applications is not supported under consumer plans per Google's FAQ. Decided: owner-run only on consumer plans; managed use needs a Google Cloud project or API key.
- **Moving one login between VMs under leases.** Rejected: OpenAI says not to share the file "across concurrent jobs or multiple machines", and a moved store is still a credential shared across projects.
- **Logins next to untrusted code.** Adopted the stricter rule: per-project logins only for owner-approved trust domains; untrusted jobs use API or local-model routes.
- **Claude setup tokens.** Kept inside the single VM that uses them rather than in a host-wide store; Claude Code's own login inside the VM remains the default.
- **xAI.** Candidate route enabled only after a pin-time check confirms the owner's plan and allowed use ([X Subscription terms](https://x.ai/legal/x-subscription-terms-of-service), read 2026-11-21).
- **Deployment gateways.** Supported only for API-key and local-model routes under owner opt-in, never consumer-login proxying.

### Rejected

- Shipping CLIProxyAPI, or an opt-in helper for it behind a terms acknowledgement.
- Treating a successful login as permission; the registry approves routes, not authentications.
- One login store mounted into several sandboxes.

### Open risks

- Terms changed frequently in 2026; a change can turn a route off overnight. The registry's expiry makes routes fail closed.
- A future change could restrict official CLIs on remote servers.
- Per-project logins cost one phone tap per new project and provider; forced re-logins over a week must be measured (T9).
- Residual: code inside a project VM can read that project's login (Anthropic's warning above), bounded by the egress allowlist and per-project revocation. Split execution (ADR 0010, T10) is the experiment that would remove it.

### Open vendor questions

- **L1, Anthropic:** edge cases around setup tokens and multiple accounts by one individual under consumer vs. commercial terms.
- **L2, Google:** whether a self-hosted supervisor driving `agy` on a consumer plan counts as direct scripting or a wrapping application.
- **L3, xAI:** whether the SuperGrok or X Subscription entitlement in OpenCode and Kilo covers unattended use.

## ADR 0005 · The local AI lane (home-server support)

**Status:** Accepted, 2026-11-21 (updated for home-server hardware profiles). **Topic:** Local AI model lane.

### Decision

- **First-class planned lane, enabled per hardware profile.** Ötüken is designed so owners can run it not only on hosted servers, but also as a home server with local AI models. The local-model module stays in the core design and is configured according to the host's hardware profile:
  1. **GPU / unified-memory home server:** enables the on-box model server directly after hardware detection, sized to available VRAM/unified memory while preserving the host and VM memory reserves.
  2. **Private-network model server:** connects Ötüken to an OpenAI-compatible model server the owner already runs elsewhere on their local network (for example a workstation or dedicated GPU box), with its own explicit egress rule.
  3. **CPU-only server:** offered as an experimental, measured lane — enabled only after the installer benchmarks the candidate on the actual machine (`llama-bench`, two to four minutes) and prints tokens per second, time to first token on a representative agent prompt, RAM footprint and how many fewer project VMs that leaves, and the model weights' own licence. A coding subscription is never treated as a licence to any weights.
- **Runtime:** a pinned `llama-server` (MIT) bound to loopback under its own systemd user with an API key and bounded slots; harness timeouts raised to 30 minutes for the local profile; wired into harnesses that accept a custom OpenAI-compatible endpoint (Pi and omp, OpenCode, Hermes, Codex, Kilo, Cline); Claude Code only as a separate opt-in profile; Antigravity and Cursor CLI cannot use a custom local endpoint. The wizard recommends Pi for local work when prompts need to stay compact.
- **Plain expectations on CPU-only hardware:** before downloading weights onto a CPU-only machine, the wizard states clearly what the measured benchmark means (memory footprint, throughput, cold-prompt latency) so owners know when local inference fits triage, summaries, commit messages, and small edits versus when cloud subscriptions or a GPU home server are needed for heavy coding.

### Reasons

- Home-server users with GPUs, Apple Silicon / unified-memory machines, or dedicated local inference hosts need local AI as a native lane — both for offline/private work and for untrusted repositories where subscription logins are kept out of project VMs (ADR 0004).
- On a CPU-only x86_64 server with AVX2 and dual-channel memory bandwidth, gpt-oss-20b measured 23.2 tok/s generation and 67 tok/s prompt processing on an 8-core Zen 4 desktop ([OpenBenchmarking](https://mail.openbenchmarking.org/performance/test/pts/llama-cpp/0d11057dae615d0dbe31c8df288a8275bc721fd1), read 2026-11-21 through its mirror), falling as context grows ([ik_llama.cpp discussion 758](https://github.com/ikawrakow/ik_llama.cpp/discussions/758), read 2026-11-21). gpt-oss-120b's file alone is about 63 GB ([Hugging Face listing](https://huggingface.co/api/models/ggml-org/gpt-oss-120b-GGUF/tree/main), read 2026-11-21). Measuring on the target hardware avoids misleading estimates.
- First-token latency matters for agent prompts: at 40–60 tok/s on CPU, a cold 10k-token agent prompt takes minutes, longer than default stream timeouts of most harnesses (Codex and Pi 300 s, OpenCode a 5-minute header timeout) ([Claude Code environment variables](https://code.claude.com/docs/en/env-vars), [Codex advanced config](https://learn.chatgpt.com/docs/config-file/config-advanced), [OpenCode providers](https://opencode.ai/docs/providers/), [Pi models](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md), read 2026-11-21).
- Quality: on Terminal-Bench 2.1, the best local-size model listed scored 44.9 and gpt-oss-20b scored 13.9 ([Artificial Analysis](https://artificialanalysis.ai/evaluations/terminalbench-2-1), read 2026-11-21).
- Anthropic "doesn't support routing Claude Code to non-Claude models through any gateway" ([LLM gateway](https://code.claude.com/docs/en/llm-gateway), read 2026-11-21), hence the separate profile.
- `llama.cpp` serves an OpenAI-compatible API ([llama.cpp](https://github.com/ggml-org/llama.cpp), read 2026-11-21).
- Weight licences are separate from subscriptions.

### Disagreement, and how it was decided

- Refusing to download weights entirely (remote URL only) is too strict for home-server owners with GPUs or large unified memory, while silently enabling large models on small CPU-only servers hurts VM memory headroom and causes timeouts. Decided: keep the local AI lane in the design as a hardware-profile-driven module supporting GPU hosts, private-network endpoints, and measured CPU trials.

### Rejected

- vLLM on CPU-only AVX2 hosts: AVX2 has "limited features", and vLLM does not load GGUF files ([vLLM CPU](https://docs.vllm.ai/en/latest/getting_started/installation/cpu/), read 2026-11-21).
- LM Studio: its terms forbid redistribution ([LM Studio terms](https://lmstudio.ai/app-terms), read 2026-11-21).
- Ollama is acceptable only if its default 4,096-token context on CPU-only boxes is raised ([Ollama context length](https://docs.ollama.com/context-length), read 2026-11-21).

### Open risks

- CPU speed figures are hardware-dependent; the installer measures before recommending a model (T15).
- A loaded 20 GiB model shares host memory with project VMs (ADR 0008); hardware profiles must account for the combined memory budget.
- Exact home-server hardware profiles (GPU, unified-memory hosts, and model catalog defaults) are under active design.

## ADR 0006 · The CTO's authority, bounded by a non-agent guard

**Status:** Accepted, 2026-11-21. **Topic:** CTO authority and deterministic host guard.

### Decision

- **Order.** The owner runs the deterministic installer as root; no model is involved. It lays down the base, the guard, the credential store, the board endpoint and the seat. The guard then starts the CTO in the seat. From there the CTO guides setup the way a sysadmin would: it talks to the owner, proposes choices (workers, subscriptions, local AI profile, modules), runs the login flows, explains failures and retries. It changes the host only through the guard, which renders the exact plan and applies it with the same deterministic engine. If no model is reachable (no login yet, a provider outage), the same steps run from the terminal wizard. The install never depends on a model behaving.
- **The seat.** The CTO runs as root inside its own KVM VM (2 vCPU, 4–6 GiB). On a host without KVM the seat is an unprivileged host user, and the plan says isolation is weaker.
- **What the CTO owns:** everything except five things: the guard (its code and policy), the audit trail, the host credential store, the backups, and the owner's rescue path. It acts on everything else by tier:

  | Tier | How | Examples |
  | --- | --- | --- |
  | 0. Direct | root inside the seat; no guard involved | install tools in the seat, edit HQ, run git and scripts, keep its own notes |
  | 1. Through the guard, automatic within policy limits | a typed call checked against policy and ceilings, written to the audit log, refused with a reason when out of bounds | create, start, stop, snapshot or delete a project sandbox (delete refuses unpushed work); start, steer and stop workers; bind an existing secret to a project; mint a one-repository GitHub token; add a domain from an allowed egress class; start a browser VM; install a harness version listed in the signed catalog; read usage limits; report to the board; set a job's state; propose vault changes; read-only host diagnostics (unit status, journal excerpts, disk and RAID state); trip the kill switch on any scope |
  | 2. Through the guard, owner-approved | the guard holds the request with its rendered plan; the owner approves over SSH (`sudo otuken approve <id>`) or with an authenticated board action | host packages outside the catalog, new open ports or public exposure, users, raising a ceiling, new egress classes, enabling a module (cross-use, off-box backup, local model), creating a secret (the owner types the value), policy edits |
  | 3. Owner-approved root script | the CTO writes an exact script; the guard shows it in full with its digest; the owner approves it over SSH only; the executor runs the exact approved text once as real host root, after a checkpoint, in a time-bounded systemd cgroup; the journal records the script and its hash, with bounded output and a post-run drift report | host work no typed verb covers: a broken service, a one-off repair |

- **Tier 3 trust and detection.** The owner authorizes real root to do repairs such as restarting services or editing system configuration. The cgroup bounds and reaps processes that stay in it. An approved root script can start work outside that cgroup, including a separately managed service. The drift alarm is detective. It compares all of `/etc`, cron storage, `/usr/local`, units, package verification, the guard state and rescue paths before and after. The census also covers new files under `/usr` and login and user-unit persistence for root, interactive and lingering accounts. Undeclared stable changes and incomplete checks latch an alarm. The report lists changes observed outside the script window separately. Host root can alter the guard or the evidence, so the owner must review the exact script as privileged code. Tier-1 and tier-2 operations remain typed and policy-bound. The shipped unprivileged broker unit (`install/systemd/otuken-guard-request.service`) drops `CAP_DAC_READ_SEARCH` and denies all three `io_uring` syscalls. The privileged executor runs outside the broker sandbox.
- **No agent-held host root.** The product has no interactive root session for an agent and no standing-root switch. A root shell on the host stays the human's: the provider's admin user, which the installer never removes or changes.
- **The guard** contains no model and runs as two processes: an unprivileged request service that parses, validates, rate-limits, queues and leases requests, and a tiny root executor that runs only fixed templates and alone holds the Incus admin socket. No agent, the CTO included, gets an Incus credential.
  - Callers on the host are identified by the socket they use and `SO_PEERCRED`; VMs reach the guard over vsock and are identified by their vsock ID, plus a per-generation lease. A guest's network address is never its identity.
  - Every mutation carries a lease (project, job, allowed verbs, expiry, budget) and an idempotency key; each CTO generation and each worker launch has its own identity, and a handover rotates the CTO's authority. Interrupted requests are reconciled against the real resources before a retry.
  - Each verb has a rate limit (a token bucket; for example ten `project.create` an hour) and the guard keeps global ceilings (running instances, a disk floor, the host's RAM and CPU reserve).
  - The typed tier-1 and tier-2 endpoints refuse raw shell, arbitrary paths, images or URLs, devices, mounts and free-form Incus flags.
  - Policy is root-owned under `/etc/otuken/`; the CTO can propose policy, never write it.
  - The audit log is append-only (chained journal and dedicated journald namespace), optionally shipped off-box. Timers and caps go through systemd and cgroups; credentials go to units with `LoadCredential=`, not environment files.
  - Each product project's sandboxes live in a restricted Incus project (`restricted=true`, `limits.*`), so a request that slips past the guard still cannot create a privileged container or pass that project's ceilings.
- **No path from a project VM to the seat's control channel** or to the control app's API. Worker output reaches the CTO only as files and board events.
- **One tool surface for every harness:** an MCP server (`otuken mcp`, a small stdio shim inside each VM that talks to the guard with that VM's lease) and a CLI (`otukenctl`) with the same operations, so a harness without MCP loses nothing.

### Reasons

- An agent is bounded only by something it cannot rewrite. A CTO with host root can stop the guard, edit the policy, read every login and delete the snapshots, so every guard becomes advisory.
- The seat is a VM because the CTO reads the most injected text (worker output, the web, the vault) and has the widest tool access; a VM limits a compromised CTO to its own machine plus the guard's verbs.
- Two processes, so that a parsing bug lands in an unprivileged process.
- Incus's Unix socket "always grants full access" ([Incus README](https://raw.githubusercontent.com/lxc/incus/main/README.md), read 2026-11-21), and full socket access gives administrative control including attaching host devices and filesystems ([Incus security](https://linuxcontainers.org/incus/docs/main/explanation/security/), read 2026-11-21).
- 2026 brought Incus fixes for cases where "Restricted project users can create resources in the default project, bypassing project isolation" ([Incus news](https://linuxcontainers.org/incus/news/), read 2026-11-21), so restricted projects are a second wall, never the boundary.
- `SO_PEERCRED` "returns the credentials of the peer process connected to this socket" ([unix(7)](https://man7.org/linux/man-pages/man7/unix.7.html), read 2026-11-21). Incus proxy devices forward Unix sockets only into containers, and VMs get NAT/TCP only ([proxy device](https://raw.githubusercontent.com/lxc/incus/main/doc/reference/devices_proxy.md), read 2026-11-21); Incus records each VM's `volatile.vsock_id` ([configuration options](https://raw.githubusercontent.com/lxc/incus/main/doc/config_options.txt), read 2026-11-21).
- `RuntimeMaxSec=` ([systemd.service](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)), `systemctl freeze` ([systemctl](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html)) and `LoadCredential=` ([systemd.exec](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)), all read 2026-11-21.
- sudo with a command allowlist fails on programs that spawn shells or read files, "a curated list of Unix-like executables that can be used to bypass local security restrictions in misconfigured systems" ([GTFOBins](https://gtfobins.github.io/), read 2026-11-21).

### Disagreement, and how it was decided

- **Where the CTO runs.** Running the CTO as a host user shares the host kernel, leaving it one local privilege escalation away from the guard, credential store, and backups. Decided: seat VM; host user only on hosts without KVM.
- **Agent-held host root.** A time-boxed root session lets an agent install persistence that outlives the time box, and standing root removes the guard boundary altogether. Tier 3 gives the CTO reach for one-off host repairs while keeping every root action bound to the owner's explicit, recorded approval of an exact script digest.

### Rejected

- Standing `sudo NOPASSWD: ALL` for the CTO.
- sudo with a command allowlist.
- Root inside a confined systemd unit: a root process with enough capability to administer the box has enough to escape the confinement.
- A second model as the guard: enforcement must be deterministic, and a model judge can be prompt-injected like the CTO. A model may advise on tier-2 requests, never gate them.
- No host operational reach for the CTO at all.

### Open risks

- Tier-3 scripts depend on the owner reading them, and approval fatigue is the failure mode. They are SSH-only, shown in full, rate-limited and counted on the board.
- The guard's bugs are the system's bugs: it stays small, tested and fuzzed (T6).
- vsock identity must be shown not to be spoofable by another VM (T6).

### Verification test

T6: raw management requests, expired leases, path escapes, replayed mutations and malformed requests are refused; rate limits hold; a worker cannot reach the owner socket or the seat's channel; a VM cannot present another VM's identity; an approved tier-3 script runs exactly once, and a changed script needs a new approval.

## ADR 0007 · A swappable CTO: the contract, the supervisor and handover

**Status:** Accepted, 2026-11-21. **Topic:** Swappable CTO contract, supervisor, and handover.

### Decision

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

### Reasons

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

### Disagreement, and how it was decided

- **Transport.** Choosing transport by the pinned version's tested capabilities (using ACP where complete and native structured mode otherwise) avoids tying resume and cancel to preview ACP revisions.
- **The job-state record.** One guard journal is the source of truth so `STATUS.md` and the board cannot disagree; direct edits to `STATUS.md` line 1 are validated as `job.state` calls.
- **Machine job-file format:** JSON, matching the board and catalog schemas.

### Rejected

- A lowest-common-denominator wrapper that hides the harnesses; it throws away what each does best and breaks on every release.
- Harness-native memory or schedules as the store of record.
- bb as a required part of the contract.
- Translating transcripts between harnesses.
- Announcing all six CTO harnesses before each passes a real job in both roles.

### Open risks

- Six event formats: one adapter each, tested in CI against recorded transcripts.
- Harness sandboxes need user namespaces, which Ubuntu 24.04 restricts through AppArmor; Codex warns about it on 24.04 ([Codex sandboxing](https://learn.chatgpt.com/docs/sandboxing), read 2026-11-21), and Claude Code's sandbox falls back to running unsandboxed ([Claude Code sandboxing](https://code.claude.com/docs/en/sandboxing), read 2026-11-21). The installer loads the AppArmor profile once and sets the harnesses to fail closed; the VM is the boundary either way.
- The capability table comes from documentation; real runs decide (T3).

### Verification test

T3, the role tests above, including a clean swap and a swap from a failed seat with workers still running.

## ADR 0008 · One KVM VM per project

**Status:** Accepted, 2026-11-21; default concurrency scaling waits for measurement T2. **Topic:** Project isolation and VM sizing.

### Decision

- **Incus is the only sandbox manager.** On a host with KVM the default is one KVM VM per project: its own kernel, its own logins, Docker and browsers without nesting tricks. The light profile, an owner opt-in per project, is an unprivileged system container with an isolated ID map, for trusted, low-risk work that needs many parallel sandboxes or fast start; it is also the fallback on hosts without KVM, where the owner must select it explicitly after the wizard says isolation is weaker. Always a VM: code the owner did not write, pull requests from forks, any browser, and the CTO's seat. The project record says `isolation: vm | container`; the CTO does not choose the hypervisor.
- **Incus 7.0 LTS from the Zabbly repository**, with the repository's signing-key fingerprint checked out of band and recorded in the signed release, a dedicated keyring with `Signed-By`, and apt pinning limited to the Incus packages. Not Ubuntu's archive package. Incus restrictions are a second wall: each product project gets a restricted Incus project from a fixed template (`restricted=true`, `limits.*`); containers get `security.idmap.isolated=true`; every instance has the guest API turned off after provisioning and port isolation on its bridge port.
- **Sizes and starting ceiling** for an illustrative 8-core / 16-thread, 64 GiB host:
  - reserve 10 GiB for the host (guard, Incus, proxy, board, page cache), 4–6 GiB for the seat, 4 GiB for one browser VM while it runs, and 8 GiB for CI while it runs;
  - a normal project VM is 2 vCPU and 6 GiB (one or two agents and an occasional build), a heavy one 4 vCPU and 12 GiB, a browser VM 2 vCPU and 4 GiB;
  - admit at most **4 normal project VMs plus one browser VM, or 2 heavy plus one browser**, raised toward 6 normal only after T2 measures peak memory, build times and host latency under concurrent builds;
  - CI and a loaded on-box local model are charged to the same pool; several agents of one job share their project's VM in separate worktrees; idle VMs stop after 30 minutes without activity and then cost only disk;
  - per-job caps (8 GiB, 200 % CPU, 512 tasks) apply inside each project VM.
- **Other runtimes:** Firecracker, Cloud Hypervisor and Kata come later, and only if VM start time or density is shown to be the bottleneck. gVisor is rejected as the boundary. Rootless Podman stays inside a project VM for its service containers. Harness sandboxes are defence in depth inside the VM, never the boundary.

### Reasons

- Incus describes containers as "a software-only way to isolate" and says that for VMs the boundary "is enforced by those hardware features" ([Incus containers and VMs](https://linuxcontainers.org/incus/docs/main/explanation/containers_and_vms/), read 2026-11-21). Coding agents run third-party code on every build (ADR 0013), and container runtimes keep having breakout bugs ([USN-7851-1](https://ubuntu.com/security/notices/USN-7851-1), read 2026-11-21).
- Each project keeps its own provider logins (ADR 0004), removing the old argument for shared containers.
- Ubuntu's package: noble ships `6.0.0-1ubuntu0.3` ([packages.ubuntu.com](https://packages.ubuntu.com/noble/incus), read 2026-11-21), whose uploads are each a "No change rebuild due to golang-1.22 update" ([changelog](https://changelogs.ubuntu.com/changelogs/pool/universe/i/incus/incus_6.0.0-1ubuntu0.3/changelog), read 2026-11-21), so none of the later security fixes are in it. 2026 brought fixes including "Restricted project users can create resources in the default project, bypassing project isolation", and the 7.0 LTS line is "supported until June 2031" ([Incus news](https://linuxcontainers.org/incus/news/), read 2026-11-21). Zabbly publishes the 7.0 LTS repository for noble ([zabbly/incus](https://github.com/zabbly/incus), read 2026-11-21), and apt sources can be pinned to a keyring with `Signed-By` ([sources.list(5)](https://manpages.ubuntu.com/manpages/noble/man5/sources.list.5.html), read 2026-11-21).
- `security.idmap.isolated` gives "non-overlapping UID/GID maps for each container" ([Incus security](https://raw.githubusercontent.com/lxc/incus/main/doc/explanation/security.md), read 2026-11-21); restricted projects and limits are documented on the projects page ([Incus projects](https://linuxcontainers.org/incus/docs/main/reference/projects/), read 2026-11-21).
- Sizing floors, not measurements: Claude Code asks for "4 GB+ RAM" ([setup](https://code.claude.com/docs/en/setup)), Codex for "4-GB minimum (8-GB recommended)" ([install](https://raw.githubusercontent.com/openai/codex/main/docs/install.md)), Anthropic's hosting guide starts at "1 GiB RAM, 5 GiB disk, and 1 CPU per agent" ([Agent SDK hosting](https://code.claude.com/docs/en/agent-sdk/hosting)), and an idle q35 VM costs about 379 MiB of host memory (a community measurement, [Incus forum](https://discuss.linuxcontainers.org/t/a-fun-project-microvms-with-incus/26889)); all read 2026-11-21.
- gVisor: file-heavy workloads are "Up to 10-200× slower" ([Agent SDK secure deployment](https://code.claude.com/docs/en/agent-sdk/secure-deployment), read 2026-11-21). Firecracker needs its own kernel, root filesystem and TAP networking ([Firecracker specification](https://raw.githubusercontent.com/firecracker-microvm/firecracker/main/SPECIFICATION.md), read 2026-11-21), so the image and network work would become the product.
- Harness sandboxes: "Sandboxing reduces risk but is not a complete isolation boundary" ([Claude Code sandboxing](https://code.claude.com/docs/en/sandboxing), read 2026-11-21).
- Docker Sandboxes are proprietary, and their "default allowed domains include broad wildcards" ([Docker Sandboxes security](https://docs.docker.com/ai/sandboxes/security/), read 2026-11-21).

### Disagreement, and how it was decided

- **The default.** KVM VMs by default; containers only as an explicit owner opt-in light profile.
- **The Incus source.** Zabbly 7.0 LTS behind a verified signing-key fingerprint gate and package pinning; a self-built Incus was rejected because maintaining security patches upstream is safer.
- **The starting ceiling.** 4 normal plus 1 browser as the reference 64 GiB admission ceiling, validated by benchmark T2 before raising further.

### Rejected

- Containers as the default on a KVM host.
- Ubuntu's archive Incus 6.0.0 package.
- Docker Sandboxes, gVisor or custom microVMs as the project boundary.

### Open risks

- Incus's 2026 security churn: patch cadence matters, and the guard does not rely on Incus restrictions alone.
- Concurrency figures are arithmetic on published floors until T2 measures real workloads.
- VM storage on a btrfs-only host is ADR 0009.

### Verification test

T2: run 4 normal and 1 browser VM with concurrent builds, and measure p95 start and build time, host interaction latency, peak resident memory and sustained I/O before confirming or raising the ceiling.

## ADR 0009 · VM storage on a btrfs-only host

**Status:** Open, 2026-11-21: documentation alone does not decide; verification test T1 does. **Topic:** VM storage pool selection on a single-filesystem btrfs host.

### Decision

- **A benchmark bake-off (T1) decides the default pool on btrfs-only hosts.**
- **Candidates:**
  1. an Incus `dir` pool on the existing btrfs, with bounded VM disks;
  2. the same, with the pool directory set to NOCOW (`chattr +C`);
  3. an Incus btrfs pool with each VM's `size.state` set to twice its root disk, as Incus documents for this case;
  4. an LVM-thin pool on a loop-backed NOCOW file (ZFS on a loop file only if measured, with its memory cache capped).
- **Criteria:** clone and snapshot time; restore time; sustained random-write throughput and latency during a real build; behaviour as the host filesystem fills toward 90 %; recovery after an unclean stop; memory overhead; how cleanly a project's disk is removed. Ties go to the simplest option.
- **Until T1 reports,** CI and test VMs use candidate 1 (`dir` pool), the simplest to inspect and remove. Admission charges each VM's reserved disk against real free space, starting with a 20 % free-space floor, and the guard watches each project's actual disk use.
- **Never repartition an existing host in an unattended install.** On a fresh machine with spare block devices, the installer offers a dedicated partition or disk for a ZFS or btrfs pool, which is Incus's recommended setup.

### Reasons

- On an already-partitioned btrfs host, every option trades off against one of Incus's own recommendations ("The two best options for use with Incus are ZFS and Btrfs", on a dedicated disk or partition) ([Incus storage drivers](https://raw.githubusercontent.com/lxc/incus/main/doc/reference/storage_drivers.md), read 2026-11-21):
  - a btrfs pool: "you should never use VMs with Btrfs storage pools" unless `size.state` is set to twice the root disk size; Btrfs "doesn't natively support storing block devices", so a VM is one big file that "might cause issues when creating snapshots"; and "users can trivially escape any quotas that are set" ([Incus btrfs driver](https://linuxcontainers.org/incus/docs/main/reference/storage_btrfs/), read 2026-11-21);
  - loop-backed storage "isn't recommended for production use", and the directory backend "should be considered as a last resort option" (storage drivers page above); directory pools copy whole files on clone and snapshot, and set limits only on ext4 or XFS with project quotas ([dir driver](https://raw.githubusercontent.com/lxc/incus/main/doc/reference/storage_dir.md), read 2026-11-21);
  - a loop-backed pool still shares the host filesystem's failure and capacity limits, and a loop-backed ZFS pool adds ARC memory overhead that needs measurement.

### Disagreement, and how it was decided

- Every candidate conflicts with at least one Incus recommendation on a single btrfs filesystem, so documentation cannot rank them. Measurement T1 decides; candidate 1 is the initial starting point for test VMs because it is the simplest to inspect and clean up.

### Rejected

- Repartitioning an existing host during an unattended install.
- Choosing a pool on documentation alone without workload measurement.
- A btrfs pool for VMs without the `size.state` setting, which Incus explicitly warns against.

### Open risks

- Thin pools can run out of data or metadata space; both are tracked.
- Sparse VM disks can overcommit the host; admission counts reserved bytes, not used ones.
- If no candidate is acceptable on a btrfs-only host, VMs remain bounded until a dedicated disk is added.

### Verification test

T1, the bake-off above.

## ADR 0010 · Least knowledge and least privilege per project, and browser VMs

**Status:** Accepted, 2026-11-21; split execution is an experiment (T10). **Topic:** Per-project secrets, GitHub access, egress filtering, tools, and browser VMs.

### Decision

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

### Reasons

- GitHub App installation tokens "expire after 1 hour" and accept `repositories` and `permissions` to narrow them ([GitHub Docs](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app), read 2026-11-21); with the manifest flow, owners "only need to follow a URL and name the app" ([App manifest](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest), read 2026-11-21); deploy keys never expire ([deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys), read 2026-11-21).
- Without OVN, Incus has no per-project networks of its own (`features.networks` "requires the server to be configured for OVN"), hence one bridge per project ([Incus projects](https://linuxcontainers.org/incus/docs/main/reference/projects/), read 2026-11-21). Incus ACLs filter by address only, have no domain names, and "cannot be used to block baseline service rules" such as DHCP and DNS to the bridge's own dnsmasq ([network ACLs](https://linuxcontainers.org/incus/docs/main/howto/network_acls/), read 2026-11-21).
- An explicit proxy, not a transparent one: TLS Encrypted Client Hello hides the server name on the wire ([RFC 9849](https://www.rfc-editor.org/rfc/rfc9849.html), read 2026-11-21), and domain fronting or a literal IP bypasses name-based filtering ([Vercel Sandbox firewall](https://vercel.com/docs/sandbox/concepts/firewall), read 2026-11-21). Squid is packaged in noble ([packages.ubuntu.com](https://packages.ubuntu.com/noble/squid), read 2026-11-21), and Claude Code publishes the domains it needs ([network configuration](https://code.claude.com/docs/en/network-config.md), read 2026-11-21).
- Credentials injected outside the boundary, so that "The agent never sees the actual credentials" ([Agent SDK secure deployment](https://code.claude.com/docs/en/agent-sdk/secure-deployment), read 2026-11-21).
- `CLAUDE_CODE_SHELL_PREFIX` is a "Command prefix that wraps shell commands Claude Code spawns" ([environment variables](https://code.claude.com/docs/en/env-vars), read 2026-11-21).
- Unattended mode only inside a boundary: "Always run --dangerously-skip-permissions sessions inside a container, a VM, or the sandbox runtime" ([sandbox environments](https://code.claude.com/docs/en/sandbox-environments.md), read 2026-11-21); Claude Code refuses that flag when launched as root ([devcontainer](https://code.claude.com/docs/en/devcontainer.md), read 2026-11-21).
- Browsers in VMs: Playwright MCP "is not a security boundary" and its Docker image runs Chromium with `--no-sandbox` ([Playwright MCP](https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md), read 2026-11-21), and running Chromium as root in a container "will disable the Chromium sandbox" ([Playwright Docker](https://playwright.dev/docs/docker), read 2026-11-21).

### Disagreement, and how it was decided

- **The API-key gateway.** A small custom gateway was chosen over LiteLLM: this component holds real API keys in the trusted base, and LiteLLM carries a large dependency graph and suffered supply-chain incidents in 2026 ([BleepingComputer](https://bleepingcomputer.com/news/security/popular-litellm-pypi-package-compromised-in-teampcp-supply-chain-attack), [Help Net Security](https://www.helpnetsecurity.com/2026/10/22/litellm-compromised-supply-chain-attack-pypi-docker/), 2026-11-21).
- **Secret delivery.** tmpfs files per job are simple and cleaned up when the job ends; a read-once socket remains a possible later hardening.
- **GitHub access.** GitHub App short-lived installation tokens are the default; deploy keys stay a fallback only because they never expire.

### Rejected

- Mounting host directories into project VMs, one shared Unix user for all projects, and tokens written into `.git/config`.
- Transparent name-based filtering (ECH, above).

### Open risks

- An allowed host can still carry data out, including a model provider's own API used with an attacker's key ([Embrace The Red](https://embracethered.com/blog/posts/2025/claude-abusing-network-access-and-anthropic-api-for-data-exfiltration/), read 2026-11-21).
- Bridge ACLs without OVN must be shown to cover IPv4 and IPv6 cleanly.
- The small custom gateway is new code holding keys; it needs its own tests and review before it is enabled.

### Verification tests

T4 (cross-project canary), T5 (egress) and T10 (split execution).

## ADR 0011 · The vault: a self-improving LLM wiki

**Status:** Accepted, 2026-11-21. **Topic:** Agent knowledge vault and sync rules.

### Decision

- **A separate git vault** for the agents, next to the owner's personal vault, not inside it. The server copy is canonical.

  ```
  /var/lib/otuken/vault/
    SCHEMA.md         page shapes and merge rules; changed only by an owner-approved change
    index.md          generated from frontmatter by code, never by a model
    log.md            append-only, one line per merge, written by the merge step
    wiki/             canonical pages
      projects/<id>/  project-scoped pages
      shared/         tools, vendors, concepts, runbooks, decisions
      contradictions/ conflicts waiting for resolution
      archive/        superseded pages, never silently deleted
    drafts/<job>/     the only folder agents write to, and only through the guard
    quarantine/       proposals the checks rejected, for the owner's digest
    outbox/owner/     pages proposed for the owner's personal vault
  /var/lib/otuken/evidence/
                      immutable source captures (text, URL, fetch time, sha256),
                      marked untrusted, outside the synced vault
  ```

  The schema file is not called `AGENTS.md`, so no harness loads it as instructions.
- **Write path: draft → checks → canonical.**
  1. An agent calls `vault.propose` (MCP or CLI) with text, a target page and sources. The guard writes the draft and fills the provenance itself from what it knows (job, project, harness and version, model, time); the agent cannot set those fields.
  2. A deterministic merge step, code and not a model, checks the schema, required provenance, links, secrets, size, allowed paths and file types. It refuses remote images, raw HTML, iframes, URLs with query strings, and anything that touches `SCHEMA.md` or `.obsidian/`. It looks for duplicates by title, alias and a nearest-neighbour search; a near match becomes an update of the existing page, not a new page.
  3. A tool-less model call with structured output (no shell, no network, no commit rights) checks whether each claim appears in its cited source and whether it contradicts a canonical page. Its patch is validated again by the deterministic step.
  4. Auto-merge happens only when every source is at least machine-confirmed and nothing was flagged; everything else goes to `quarantine/` and a daily digest. A contradiction goes to `contradictions/` and marks both pages `disputed`. Pages agents will act on (`kind: runbook`) need the owner's approval. Every merge is a commit with trailers naming the draft, the job and the sources, and it regenerates `index.md` and `log.md`.
- **Provenance**, compatible with Google's Open Knowledge Format:

  ```yaml
  id: shared/tools/incus-btrfs-pool
  kind: fact | howto | decision | runbook | reference
  scope: global | project:<id>
  status: draft | stable | disputed | stale | superseded
  generated: {by: <harness>/<version>, model: <model>, job: <id>, at: <RFC 3339 time>}
  verified: [{by: human:owner, at: <time>}]
  sources: [{id: s1, evidence: <sha256>, url: <url>, read: <date>, origin: web | owner | agent | repo}]
  trust: untrusted | machine | human   # set by the merge step: the lowest trust among the sources
  supersedes: [<ids>]
  stale_after: <date>
  ```

  No numeric confidence scores.
- **Rot and duplication.** Deterministic lint runs daily: broken links and wikilinks, orphan pages, pages without sources, pages past `stale_after` (marked stale, never deleted), two canonical pages giving different values for the same key (marked disputed). Model-assisted near-duplicate and contradiction proposals run weekly and arrive as drafts. `stale_after` by kind: about 30 days for fast-moving tool and price facts, 180 for infrastructure patterns, 365 for decisions. Retrieval returns stable pages first and shows stale and disputed pages with their status. A contradicted fact is marked superseded, not deleted.
- **Prompt-injection containment.**
  1. Nothing in the vault is an instruction. Rules live only in `AGENTS.md` and skills, outside the vault's write path. A page that should become a rule is filed as a proposed `AGENTS.md` or skill change, which the owner approves like any policy edit.
  2. Trust is fixed at write time by origin and can only go down. Summarising does not launder it; only a human verification raises it.
  3. Rule of Two per agent: the merge step reads untrusted text and writes the vault, so it has no secrets and no network; the CTO reads untrusted-tier pages only through tool-less calls.
  4. Vault text given to an agent is wrapped and marked as data, with its provenance.
  5. Least knowledge: a worker reads shared pages and its own project's pages, never another project's and never the owner's personal vault unless its job grants it. The pages a job needs are copied into its project at job start as a snapshot, so a later edit cannot change a running job, and a poisoned page inside a project can come back only as a draft.
  6. No exfiltration through the owner's apps: no remote images, HTML or query-string URLs in agent pages; agents never write `.obsidian/`, which is excluded from sync; raw captures stay outside the synced vault.
  7. Everything is reversible: the merge step can list and revert every page derived from one source, and it alerts on unusual write rates.
- **Two-way sync with the owner's own vault:** two-way at the transport level, one-way in authority. The owner's vault is mirrored to the server, read-only for agents. Agents propose into `outbox/owner/`, and the owner moves what they want. Owner edits to agent pages come back as authoritative changes (`edited_by: owner`). Deletions travel as staged tombstones with a grace period; conflicts keep both versions and the common base, and the shared copy advances only after the owner resolves them. One sync service per folder. Git on the server is the store; the transport is the owner's choice and off by default: git (desktop), Syncthing (desktop; Receive Only for the mirrored personal vault), or Obsidian's official headless client (with a paid Obsidian Sync plan; for phones).

### Reasons

- Karpathy's LLM wiki: raw sources that are "immutable — the LLM reads from them but never modifies them", a wiki that "The LLM owns… entirely", a schema file, `index.md`, an append-only `log.md`, and "lint" passes for "contradictions between pages, stale claims that newer sources have superseded, orphan pages with no inbound links"; it deliberately has no provenance schema ([LLM wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), read 2026-11-21).
- "Keep your personal vault clean and create a messy vault for your agents" (Steph Ango of Obsidian, [post](https://x.com/kepano/status/2039831289533227446), read 2026-11-21 through a mirror).
- The Open Knowledge Format already defines the provenance fields and reserves `index.md` and `log.md` ([OKF specification](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md), read 2026-11-21).
- Isolation patterns: once an agent "has ingested untrusted input, it must be constrained so that it is impossible for that input to trigger any consequential actions" ([Beurer-Kellner et al.](https://arxiv.org/abs/2506.08837)); CaMeL's separation of control and data ([CaMeL](https://arxiv.org/abs/2503.18813)); Meta's Rule of Two ([Meta](https://ai.meta.com/blog/practical-ai-agent-security/)); spotlighting cut attack success from over 50 % to under 2 % on the models tested ([Hines et al.](https://arxiv.org/abs/2403.14720)); OWASP asks to "Prevent automatic re-ingestion of an agent's own generated outputs into trusted memory" ([OWASP Agentic Top 10](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)); all read 2026-11-21.
- Poisoning works at very low rates: over 80 % attack success with under 0.1 % poisoned entries ([AgentPoison](https://arxiv.org/abs/2407.12784), read 2026-11-21), so provenance and reversal matter more than detection.
- Claude Code's own memory files "aren't enforced configuration" ([memory](https://code.claude.com/docs/en/memory), read 2026-11-21).
- Obsidian "cannot reliably restrict plugins" ([plugin security](https://obsidian.md/help/plugin-security), read 2026-11-21).
- A production LLM-wiki skill dropped confidence scores as "false precision with no calibration behind it" ([karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki), read 2026-11-21).
- Link checks with lychee and `--include-wikilinks` ([lychee](https://github.com/lycheeverse/lychee), read 2026-11-21); contradicted facts marked invalid rather than deleted, as in Graphiti ([Graphiti](https://arxiv.org/html/2501.13956), read 2026-11-21).
- Sync: Obsidian advises "Avoid syncing the same vault across multiple services… to prevent data conflicts or corruption" ([sync your notes](https://obsidian.md/help/sync-notes)); Syncthing never merges and keeps `.sync-conflict-` copies ([syncing](https://docs.syncthing.net/users/syncing.html)) and offers Receive Only folders ([folder types](https://docs.syncthing.net/users/foldertypes.html)); Obsidian's headless client `ob` is in open beta, needs Node 22 or newer and has `bidirectional`, `pull-only` and `mirror-remote` modes ([Headless Sync](https://obsidian.md/help/sync/headless)); obsidian-git's mobile support is "highly unstable" ([obsidian-git](https://github.com/Vinzent03/obsidian-git)); a Syncthing forum thread reports deletions with a Syncthing folder inside iCloud Drive and advises to "move your Syncthing folder(s) outside of the iCloud folder path" ([forum](https://forum.syncthing.net/t/problem-with-syncthing-and-icloud/21914), a community thread); all read 2026-11-21.

### Disagreement, and how it was decided

- **Pages as instructions.** Kept instructions out of the vault so knowledge and executable rules stay separate; promoting a learned pattern into a rule goes through an owner-approved `AGENTS.md` or skill proposal.
- **The owner's notes.** Kept in a separate vault rather than inside the agent vault; git remains the server-side store and one of the sync transports.
- **Raw sources.** Kept outside the synced vault under `/var/lib/otuken/evidence/` so raw captures cannot trigger remote fetches in the owner's desktop apps.
- **Lint cadence:** daily for cheap deterministic checks, weekly for model-assisted checks.

### Rejected

- Agents writing canonical pages directly.
- A vector database as the store of record; the Markdown files and git history are the truth, and an index is derived.
- Numeric confidence scores as a gate.
- Two sync services on one folder.

### Open risks

- The merge step's second check needs a model; until a login or local model is configured, drafts wait.
- The conflict behaviour of Obsidian's headless modes is not documented in detail; every transport is tested on a copy before it replaces a live sync.
- Deployments that combine sync providers should test conflicts and retain a migration plan.

### Verification tests

T11 (hostile-text fixtures cannot change grants or canonical policy) and T12 (a two-way sync drill on a copy: conflicts, deletes, round trips).

## ADR 0012 · The wall-board data contract

**Status:** Accepted, 2026-11-21. **Topic:** Wall-board data contract and documented usage reporting.

This record fixes the data contract that any wall-board UI or client can rely on.

### Decision

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

### Reasons

- CloudEvents requires only `id`, `source`, `specversion` and `type`, and `source` plus `id` is unique ([CloudEvents](https://raw.githubusercontent.com/cloudevents/spec/main/cloudevents/spec.md), read 2026-11-21); the `sequence` extension gives "the position of an event in the ordered sequence of events produced by a unique event source" ([sequence extension](https://raw.githubusercontent.com/cloudevents/spec/main/cloudevents/extensions/sequence.md), read 2026-11-21); "The current version is 2020-12" ([JSON Schema](https://json-schema.org/specification), read 2026-11-21).
- Claude's status line carries the limits "only for claude.ai Pro, Max, and Ultra subscribers … only after the first API response in the session" ([status line](https://code.claude.com/docs/en/statusline)); Codex documents `account/rateLimits/read` ([app-server](https://learn.chatgpt.com/docs/app-server)); the Copilot SDK documents how to read account usage ([usage and billing](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/usage-and-billing)); Antigravity documents `/usage` only as an interactive panel ([usage](https://antigravity.google/docs/cli/commands/usage)); Cursor's admin API is for teams only ([Admin API](https://cursor.com/docs/account/teams/admin-api)); all read 2026-11-21.
- Keeping undocumented OAuth usage calls out: besides being undocumented (described only by third parties such as [claude-usage](https://docs.rs/crate/claude-usage/0.2.2), read 2026-11-21), they require reading the subscription's OAuth token directly, which risks conflicting with Anthropic's terms ("collect, store, or intermediate Claude.ai credentials or session tokens", [legal and compliance](https://code.claude.com/docs/en/legal-and-compliance), read 2026-11-21). For Antigravity, a user post on Google's forum notes that undocumented alternatives risk the terms ([forum](https://discuss.ai.google.dev/t/feature-request-official-read-only-quota-api-for-third-party-apps/188769), read 2026-11-21).
- OpenTelemetry: Claude Code exports `claude_code.token.usage` and `claude_code.cost.usage`, with prompts "Redacted by default" and events carrying `user.email` ([monitoring](https://code.claude.com/docs/en/monitoring-usage)); Codex's `[otel]` section is "Disabled by default", with `log_user_prompt = false` ([advanced config](https://learn.chatgpt.com/docs/config-file/config-advanced)); the GenAI conventions are "Status: Development" ([OpenTelemetry GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)); all read 2026-11-21.
- The API-key usage routes need admin keys ([Anthropic Usage and Cost API](https://platform.claude.com/docs/en/build-with-claude/usage-cost-api), [OpenAI usage](https://developers.openai.com/api/reference/resources/organization/subresources/audit_logs/subresources/usage), read 2026-11-21).

### Disagreement, and how it was decided

- **Contract shape.** Files come first (`board.json` and `events.ndjson` in CloudEvents form, backed by JSON Schema before the first UI), paired with a thin read-only HTTP/SSE view so remote screens and phones can follow the board without tailing server files.
- **Undocumented usage readers.** Kept out of the public product to avoid token intermediation and fragile scraping.
- **`STATUS.md` against the board:** ADR 0007.

### Rejected

- Agents self-reporting their own account or remaining limits.
- OpenTelemetry as the contract itself: still in development, and heavier than a board needs.
- A control app's internal API as the contract.

### Open risks

- For several providers "how much is left" reads `unavailable` until the vendors document a route (consumer Antigravity, individual Cursor plans, xAI pools).
- Claude's documented route appears only after a worker session has had a response.

### Verification test

T13: board consumers fed unknown, stale and incompatible events.

## ADR 0013 · Security model: principals, threats, kill switch and caps

**Status:** Accepted, 2026-11-21. **Topic:** Security model, threat list, kill switch, and caps.

### Decision

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

### Reasons

- The 2025–2026 security incidents cited above motivate hardware-enforced VM boundaries, explicit egress allowlists, and pinned harnesses.
- `systemctl freeze` suspends a unit's processes "using cgroup freezer" ([systemctl](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html)); `incus pause` and `incus stop --force` ([pause](https://linuxcontainers.org/incus/docs/main/reference/manpages/incus/pause/), [stop](https://linuxcontainers.org/incus/docs/main/reference/manpages/incus/stop/)); SIGTERM makes Claude Code exit 143 and drop the turn ([headless](https://code.claude.com/docs/en/headless)); with Hermes a lost terminal or SIGTERM "is a disconnect" and work continues at the gateway until `/exit` or `/quit` ([Hermes CLI](https://hermes-agent.nousresearch.com/docs/user-guide/cli)); all read 2026-11-21.

### Disagreement, and how it was decided

- **Kill switch levels.** Four escalating levels (`freeze`, `cut`, `stop`, `revoke`) were chosen over a single stop command so operators can preserve forensic evidence (`freeze`) or halt exfiltration (`cut`) without destroying state.
- **Default caps:** 2 hours per worker job and 30 minutes per browser VM, with a 20 percentage-point default pace threshold.

### Rejected

- Treating a harness's own permission classifier or sandbox as the boundary.
- Relying on provider-side spend caps alone; they lag by minutes.
- A board or control API reachable from the public internet.

### Open risks

- Exfiltration through allowed hosts remains (threat 1).
- The guard is the system's single point of trust (ADR 0006).
- Time to containment is not yet measured.

### Verification tests

T6 (the guard), T7 (the kill switch at each level and scope, across a test-VM reboot, with time to containment), T11 (hostile text) and T16 (paid fallback).

## ADR 0014 · Backups

**Status:** Accepted, 2026-11-21. **Topic:** Local snapshots and off-box backups.

### Decision

- **Local layer.** btrfs snapshots stay as the hourly layer: read-only, kept 48 hours, skipped when the filesystem is above 70 % full, plus one before every update. On ext4 the pre-update export takes their place. A snapshot on the same disks is not a backup.
- **Off-box backup** is an optional module, off by default and offered at install; while it is off, the board shows a standing notice. It uses restic, encrypted, to either a rest-server started with `--append-only` or S3-compatible storage with Object Lock in compliance mode. Pruning runs only from the backup side, with age-based retention set on an independent system; the box, and therefore the CTO, never holds a credential that can delete or rewrite backups.
- **Scope:** `/etc/otuken` and `/var/lib/otuken` (state, journal, audit, HQ, vault, evidence) and the project registry. Projects themselves travel by git push, or by a per-project export the owner opts into. Provider logins and the host credential store are left out and re-created by logging in after a restore.
- **Restore:** install Ötüken on a fresh Ubuntu, run `otuken restore`, log in again, and start the projects you need. CI restores a backup into a fresh VM once per release, and a failing restore blocks the release. The board shows the last good backup and the last restore test.

### Reasons

- restic encrypts with AES-256 and authenticates with Poly1305-AES ([restic references](https://restic.readthedocs.io/en/stable/100_references.html)); rest-server's `--append-only` "allows creation of new backups but prevents deletion and modification of existing backups" ([rest-server](https://github.com/restic/rest-server)); under S3 compliance mode an object "can't be overwritten or deleted by any user, including the root user" ([S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)); restic warns that in append-only mode a compromised writer can influence count-based pruning, hence age-based retention from an independent system ([restic forget](https://restic.readthedocs.io/en/stable/060_forget.html#security-considerations-in-append-only-mode)); all read 2026-11-21.
- Borg 1.4 is an acceptable alternative; for Borg 2.0 the project says "Do not use it in production yet" ([BorgBackup](https://borgbackup.org/), read 2026-11-21).
- Logins stay out because a restored refresh token may already have been rotated, and a backup full of live logins is a theft target.

### Rejected

- Backups the box can delete.
- RAID1 or local snapshots as the disaster plan.

### Open risks

- An owner who leaves off-box backup off accepts losing host state if the server fails.
- The restic key ceremony: a passphrase on standard input for v0.1, and an optional key file in the owner's private overlay.

### Verification test

T14: restore a backup into a fresh VM, once per release.

## ADR 0015 · Core vs. private overlay separation

**Status:** Accepted, 2026-11-21. **Topic:** Separating public mechanisms from owner-specific configuration.

### Decision

**The rule:** the public repository holds mechanisms and defaults; the private overlay, a separate git repository the installer reads at `/etc/otuken/overlay`, holds every owner-specific name, address, key reference, account label, and preference. A secret and private-data scan gates publication.

- **Kept out of the public product:** machine-specific services unrelated to the agent server layer; migrations tied to one historical host (the public repository starts with an empty `migrations/` directory); hard-coded checks that refuse anything but one specific RAID/subvolume layout (replaced by detection, ADR 0001); personal workstation relays; references to one owner's internal tools in standing files.
- **Replaced by the new architecture:** shared host users as a project boundary (replaced by per-project VMs, ADR 0008); passwordless-sudo agent accounts (replaced by the guard and seat VM, ADR 0006); shared host-level account directories (replaced by per-project logins, ADR 0004); launch-convention caps (replaced by guard admission control); moving-branch installers (replaced by signed releases, ADR 0001).
- **Belongs in the private overlay (`/etc/otuken/overlay`):** hostnames and host-specific edits; custom domains, TLS publishers, and fixed listeners; remote-access admin lists, admission lists, and admin key fingerprints; hosting-provider-specific rescue notes; account labels and board names, routing preferences, model policies, private API gateway endpoints, key-file paths, password-manager vault names, deploy keys; custom CTO persona, language, and extra rules (appended to Ötüken's neutral CTO `AGENTS.md`); vault sync transport configuration; separately reviewed operator workflows.
- **Optional modules** (off unless chosen by the owner or enabled by hardware profile): the control-app integration (bb); remote access (Tailscale, WireGuard, or none), with SSH admission and watchdog logic; password-manager bridge; mobile status page and reverse proxy; additional worker harnesses beyond the CTO; local AI lane (enabled per hardware profile, ADR 0005); sanctioned cross-use registry and API-key gateway; off-box backup; vault sync; browser VM image; reference board page.
- **In the core:** the plan/apply engine built on compare-before-write atomic primitives; storage layout detection and checkpoint/snapshot engine; exec audit log (executables, not arguments) as a forensic record; systemd credential staging; pinned, digest-checked installs with vendor self-updaters off and cool-downs; hardened harness profiles (locked configs, AppArmor profile for bubblewrap); documented usage-limit adapters and pace arithmetic; the board data contract; the job contract files; refusing to delete unpushed work; leaving public SSH open until a separate, verified switch with a watchdog.

### Reasons

- Mixing owner-specific configuration into public code breaks reproducibility, prevents clean open-source distribution, and creates accidental data-exposure risks.
- Keeping the overlay as a separate git checkout allows owners to version their own rules, skills, and overlay choices independently of signed Ötüken releases.

### Disagreement, and how it was decided

- **Exec audit log:** kept in the core and on by default because it has low overhead and provides post-incident forensics (while never acting as an isolation boundary).
- **Overlay form:** a git checkout at `/etc/otuken/overlay` rather than a single `.env` file, because the overlay also carries custom skills, rules, and templates.

### Rejected

- Keeping owner-specific values in the public repository behind flags or examples filled with real host data.
- Committing private values and attempting to scrub git history later.
- Importing private-prototype history into the public repository; the public repository starts with a fresh history.

### Open risks

- Maintaining a private overlay repository requires keeping it compatible with Ötüken's overlay schema across updates.

## ADR 0016 · Licence, NOTICE and what the product may redistribute

**Status:** Accepted, 2026-11-21. **Topic:** Licence, NOTICE, and redistribution boundaries.

### Decision

- **MIT** for Ötüken's own code. `LICENSE` holds the MIT text, and every file carries an SPDX header or `REUSE.toml` annotation (REUSE 3.3).
- **`NOTICE`** holds the Ötüken contributors copyright line, a pointer to the two lists below, and the statement that signing in to a third-party service is between the owner and that service: the project grants no rights to any vendor's accounts or services.
- **`THIRD_PARTY_NOTICES.md`** lists only code copied into the repository, with its licence text. If an Omarchy script is copied later, its MIT notice comes with it; if code is copied from an Apache-2.0 project that has a NOTICE file, that NOTICE is carried and changes are marked.
- **`docs/THIRD-PARTY-TOOLS.md`,** generated from the signed catalog, lists every tool the installer downloads from its vendor at the owner's choice: vendor, official URL, licence or terms link, and the date checked. These tools are not in Ötüken's distribution, so they are not in `LICENSE` or `NOTICE`.
- **Never copied into the repository:** AGPL code (Claude Squad, Coder, Arrakis), FSL code (Crush), code without a licence.
- **Never published:** an image or tarball with proprietary agents preinstalled. The installer fetches each vendor's own installer, unmodified, on the owner's box, at the owner's explicit choice. Launchers pass the owner's chosen credential and block none of a harness's built-in sign-in methods.
- **The README states the supported mode:** one owner, the owner's own accounts, the owner's own box. Each subscription runs inside its own native agent (Claude in Claude Code, ChatGPT in Codex, and so on), with no subscription proxy. Hosting it for other people changes which vendor terms apply.
- **No pre-publication vendor-permission gate:** Ötüken does not redistribute proprietary agent binaries and runs each subscription solely inside the vendor's unmodified native client on the owner's own machine; publishing the MIT-licensed repository is not blocked on seeking vendor pre-approval.

### Reasons

- MIT's one condition: "The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software" ([OSI](https://opensource.org/license/mit), read 2026-11-21). Anyone may use, change, sell or host the product, including as a paid service. Compared with Apache-2.0 it has no express patent licence (§3) and no NOTICE mechanism (§4(d)) ([Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0), read 2026-11-21), and neither licence grants trademark rights. Omarchy is MIT ([Omarchy LICENSE](https://raw.githubusercontent.com/omacom/omarchy/quattro/LICENSE), read 2026-11-21).
- "Do not add to LICENSE and NOTICE dependencies which are not in the distribution" ([ASF licensing how-to](https://infra.apache.org/licensing-howto.html), read 2026-11-21).
- SPDX headers per REUSE ([REUSE 3.3](https://reuse.software/spec-3.3/), read 2026-11-21).
- Claude Code: "preinstalling or running Claude Code in your products or services (e.g. in hosted sandboxes or other agent infrastructure) requires agreeing to our Commercial Terms of Service"; "Claude Code must be installed and run as published by Anthropic"; customers "may not remove, disable, or restrict any authentication method built into it"; and the same page does not prevent "an end user from signing in to the unmodified Claude Code binary with their own Claude subscription, including where a platform hosts Claude Code" ([legal and compliance](https://code.claude.com/docs/en/legal-and-compliance), read 2026-11-21). Copilot CLI may be redistributed only "in unmodified form" and "solely as part of an application or service that provides material functionality beyond the Software itself" ([Copilot CLI licence](https://raw.githubusercontent.com/github/copilot-cli/HEAD/LICENSE.md), read 2026-11-21); Cursor's terms forbid reproducing the service ([Cursor terms](https://cursor.com/terms-of-service), read 2026-11-21).
- Licences of tools in the planned catalog, from each project's LICENSE or terms (read 2026-11-21): Claude Code, Antigravity CLI, Cursor CLI, Copilot CLI, Amp, Factory Droid, Junie and Kiro are proprietary; Codex, Cline, Mistral Vibe, Goose and Qwen Code are Apache-2.0; OpenCode, Pi, oh-my-pi, Hermes Agent and Kilo Code are MIT; Crush is FSL-1.1-MIT. Infrastructure: Incus Apache-2.0, the Tailscale client BSD-3-Clause, llama.cpp and Ollama MIT, LiteLLM MIT except its enterprise directory, restic BSD-2-Clause, Syncthing MPL-2.0, and bb MIT ([bb LICENSE](https://raw.githubusercontent.com/get-bb/bb/HEAD/LICENSE), read 2026-11-21). `obsidian-headless` is published as `UNLICENSED` ([npm](https://registry.npmjs.org/obsidian-headless/latest), read 2026-11-21), so it is only ever fetched at the owner's choice.

### Disagreement, and how it was decided

- **What NOTICE lists.** Following the ASF rule, `NOTICE` covers only copied/redistributed code and points to `docs/THIRD-PARTY-TOOLS.md` for tools fetched at install time.
- **Apache-2.0 vs. MIT.** MIT was chosen for simplicity and parity with Omarchy.

### Rejected

- AGPL: its network clause would deter the self-hosting users this product is for.
- Listing downloaded tools in `LICENSE` or `NOTICE` as if Ötüken redistributed them.

### Open risks

- Vendor terms change; the catalog's dates show when each was last checked.

## ADR 0017 · Name, trademarks and prior art

**Status:** Accepted, 2026-11-21. **Topic:** Product naming, trademark checks, and prior art.

### Decision

- **Product name:** display name **Ötüken**, ASCII slug and CLI name **`otuken`**, control CLI **`otukenctl`**, public GitHub repository **`orkhonai/otuken`**, project website **[otuken.tech](https://otuken.tech)**.
- **Name story:** Ötüken was the Göktürk khagans' home ground; the Kül Tigin inscription says the realm is held from Ötüken; the Orkhon river flows through it — Ötüken, by Orkhon.
- **Trademark hygiene:** the name contains no "Ubuntu" and nothing ending in "-buntu"; no "Omarchy", "Oma-" or "-archy"; no vendor or model mark (Claude, Anthropic, Codex, GPT, Gemini, Antigravity, Cursor, Copilot); and it is not plain "agent", which is Cursor CLI's binary name.
- **Attribution in docs:** the README says "for an Ubuntu 24.04 LTS server" in plain text, states that Ötüken is "inspired by Omarchy" without implying endorsement, and names third-party coding agents without implying endorsement.
- **Prior art** is credited in the README and in the table below. AgentVerse OS is the closest prior art.

### Name availability and trademark checks (2026-11-21)

| Check | Date | Source | Result |
| --- | --- | --- | --- |
| npm package `otuken` | 2026-11-21 | `https://registry.npmjs.org/otuken` and `https://registry.npmjs.org/-/v1/search?text=otuken` | Available (HTTP 404; search returns 0 packages) |
| npm package `otukenctl` | 2026-11-21 | `https://registry.npmjs.org/otukenctl` | Available (HTTP 404) |
| PyPI package `otuken` | 2026-11-21 | `https://pypi.org/pypi/otuken/json` | Available (HTTP 404) |
| PyPI package `otukenctl` | 2026-11-21 | `https://pypi.org/pypi/otukenctl/json` | Available (HTTP 404) |
| GitHub repositories (`otuken`, `otukenctl`) | 2026-11-21 | `https://api.github.com/search/repositories?q=otuken+in:name`, `https://api.github.com/search/repositories?q=otukenctl`, `https://api.github.com/repos/orkhonai/otuken` | 20 small repositories match `otuken` in name, all at 0 stars (no notable project); 0 repositories match `otukenctl`; `orkhonai/otuken` is available (HTTP 404 pre-publication); GitHub user `Otuken` exists |
| USPTO trademarks (Classes 9 & 42) | 2026-11-21 | Web search of USPTO records, Justia Trademarks (`trademarks.justia.com`), Trademarkia (`trademarkia.com`) for `otuken` and `ötüken` | No active or pending USPTO registrations surfaced in Classes 9 or 42; direct interactive clearance in USPTO Trademark Search (`tmsearch.uspto.gov`) recommended before filing or v1.0 |
| EUIPO / TMview & WIPO Global Brand Database (Classes 9 & 42) | 2026-11-21 | Web search of EUIPO (`euipo.europa.eu`), TMview (`tmdn.org/tmview`), and WIPO Global Brand Database (`branddb.wipo.int`) references for `otuken` and `ötüken` | No EUIPO registrations surfaced in public web indexes; dynamic TMview and WIPO Global Brand Database portals require interactive query and should be checked directly (alongside TÜRKPATENT) before v1.0 |
| Existing third-party uses of the historical name | 2026-11-21 | Public web search | **Ötüken Neşriyat** (`otuken.com.tr`): Turkish book publisher founded 1964 (Nice Class 16, printed matter/books; unrelated class). **Ötüken AI / Ötüken Us** (`otukenai.com`, `otukenus.com`): independent web initiatives describing sovereign-AI / modular software concepts (0 matching GitHub repositories found under `otukenai`/`otukenus`; noted as an open naming risk to review directly in trademark databases before v1.0) |
| Project domain | 2026-11-21 | Owner registration | `otuken.tech` registered and held by the project owner |

### Reasons

- Canonical: "You cannot use the Trademarks in software titles"; software "for use with or on Ubuntu" may say so but must avoid "any implication of endorsement"; permission is needed for "any mark ending with the letters UBUNTU or BUNTU" and for the mark in a domain name ([Canonical IP policy](https://canonical.com/legal/intellectual-property-policy), read 2026-11-21).
- OMARCHY is a registered US trademark: registration 8250209, Class 9, registered 2026-05-12, owned by the Omacom Foundation ([USPTO TSDR](https://tsdr.uspto.gov/statusview/sn99322411), [foundation news](https://omarchy.org/news/2026/08/omacom-foundation-launches-with-8-million/), read 2026-11-21). Omarchy also has its own written plan for a headless "Omarchy Server" ([plans/server.md](https://raw.githubusercontent.com/omacom/omarchy/quattro/plans/server.md), read 2026-11-21).
- Vendors: you "can't use the Claude Code or Anthropic names or logos as part of your own product, feature, or company name" ([Claude Code legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)); OpenAI: "we do not permit our GPT brand to be used in app, product, developer or company names" and "We do not permit model names in app titles" ([OpenAI brand](https://openai.com/brand/)); Google: "Don't incorporate Google Brand Features into your own product names" ([Google trademark guidelines](https://partnermarketinghub.withgoogle.com/brands/google/trademarks-and-terms/trademark-guidelines-for-proper-usage/)); all read 2026-11-21.
- "Trademarks don't have to be identical to be confusingly similar" ([USPTO](https://www.uspto.gov/trademarks/search/likelihood-confusion)); the official search portals ([EUIPO](https://www.euipo.europa.eu/en/trade-marks/before-applying/availability), [WIPO Global Brand Database](https://www.wipo.int/en/web/global-brand-database)); "npm processes Trademark claims under GitHub's Trademark Policy" ([npm disputes](https://docs.npmjs.com/policies/disputes)); all read 2026-11-21.
- Names already in use nearby: AgentVerse OS, agentOS, AgentBox and agbox, Sprites, Conductor, Sculptor, Hermes ([AgentVerse OS](https://github.com/agentverse-os/AgentVerse-OS), [AgentBox](https://github.com/madarco/agentbox), [agbox](https://github.com/antomanc/agbox), [Sprites](https://fly.io/sprites), [Conductor](https://www.conductor.build/), [Sculptor](https://github.com/imbue-ai/sculptor), [Hermes Agent](https://github.com/NousResearch/hermes-agent), read 2026-11-21).

**Prior art** (all links read 2026-11-21):

| Project | Licence | What it is | What Ötüken takes, or how it differs | Read |
| --- | --- | --- | --- | --- |
| [AgentVerse OS](https://github.com/agentverse-os/AgentVerse-OS) | Apache-2.0 | "a personal cloud operating system for a developer and their AI agents": one command on clean Ubuntu, isolated workspaces, several coding agents, access over Tailscale only; an alpha that "lives on a single test box" | The closest prior art. It is a browser desktop with an app store; Ötüken differs on the guard-bounded CTO, native-agent subscription handling, the vault and the board contract | 2026-11-21 |
| [Omarchy](https://github.com/omacom/omarchy), [Omakub](https://github.com/omacom/omakub) | MIT | a curated Arch desktop installed from an ISO; the retired Ubuntu desktop setup | the repository shape, release, update and CI discipline (ADR 0001); Omakub's migrations kept no record of what ran | 2026-11-21 |
| [Paperclip](https://github.com/paperclipai/paperclip) | MIT | "org charts, budgets, governance, goal alignment, and agent coordination", with roles such as CEO and CTO over coding agents and agents that "wake for assigned work" | the closest prior art for the CTO and wake-up layer; it does not own the box, isolate projects or hold the host boundary | 2026-11-21 |
| [OpenHands](https://github.com/OpenHands/OpenHands) | MIT | a self-hosted control centre for several coding agents, with Docker sandboxes | overlaps on orchestration; it does not own the box | 2026-11-21 |
| [OpenClaw](https://github.com/openclaw/openclaw) | MIT | a personal agent on your own hardware | its exposed instances and malicious skills are on the threat list (ADR 0013) | 2026-11-21 |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | MIT | a self-improving agent with memory, skills, cron and gateways | a CTO candidate; its skill-write approval informs ADR 0011 | 2026-11-21 |
| [Coolify](https://github.com/coollabsio/coolify), [CasaOS](https://github.com/IceWhaleTech/CasaOS), [Dokku](https://github.com/dokku/dokku) | Apache-2.0, Apache-2.0, MIT | one-line self-hosting installers | install ergonomics; they run apps, not agents | 2026-11-21 |
| [Coder](https://github.com/coder/coder) | AGPL-3.0 | self-hosted development environments | versioned templates behind admission; its licence prevents copying | 2026-11-21 |
| [Container Use](https://github.com/dagger/container-use), [Claude Squad](https://github.com/smtg-ai/claude-squad) | Apache-2.0, AGPL-3.0 | one container or worktree per agent | the per-task isolation idea | 2026-11-21 |
| [Docker Sandboxes](https://docs.docker.com/ai/sandboxes/security/) | proprietary, free | one microVM per agent on a Docker host | an escalation option, not the default (ADR 0008) | 2026-11-21 |
| [E2B](https://github.com/e2b-dev/E2B), [Microsandbox](https://github.com/superradcompany/microsandbox), [Kata Containers](https://github.com/kata-containers/kata-containers), [Daytona](https://github.com/daytonaio/daytona) | Apache-2.0 (E2B, Microsandbox, Kata) | microVM or cloud sandboxes | a later tier, if ever | 2026-11-21 |
| [bb](https://github.com/get-bb/bb), [Vibe Kanban](https://github.com/BloopAI/vibe-kanban) | MIT, Apache-2.0 | control surfaces for agent threads | bb stays an optional module | 2026-11-21 |
| [exe.dev](https://exe.dev/), [Fly.io Sprites](https://fly.io/sprites) | proprietary | hosted computers for agents | hosted only; Ötüken runs on the owner's box | 2026-11-21 |
| [Karpathy's LLM wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) | — | the pattern for an agent-maintained wiki | ADR 0011 | 2026-11-21 |

No existing MIT-licensed project was found that combines a stock-Ubuntu server layer, a guard-bounded swappable CTO, per-project KVM VMs, a provenance-tracked vault, and a wall-board data contract.

### Disagreement

None that changes the design.

### Rejected

- Any name containing Ubuntu, Omarchy or a vendor or model mark (the policies above).
- Plain "agent", or any name that collides with a harness's binary.
- Announcing a name without recording package, GitHub, and trademark checks.

### Open risks

- AgentVerse OS overlaps in problem space; clarifying differentiation (or collaboration) should be revisited before v1.0.
- Dynamic official trademark portals (USPTO Trademark Search, EUIPO TMview, WIPO Global Brand Database, and TÜRKPATENT) should be queried interactively before v1.0, especially to confirm whether `Ötüken AI` / `Ötüken Us` holds any registered software trademark in Classes 9 or 42.

## Design trade-offs and deliberate non-goals

1. **No consumer-login proxy.** Consumer subscription terms from Anthropic, OpenAI, Google, and Cursor forbid proxying or pooling consumer logins across unofficial clients (ADR 0004). Ötüken instead runs each subscription inside its own native agent (Claude in Claude Code, ChatGPT in Codex, and so on), pools capacity by dispatching jobs across native agents, supports provider-sanctioned cross-use routes in an opt-in registry, and routes API keys through a small host gateway.
2. **Guard-bounded CTO rather than agent-held host root.** The CTO is root inside its own seat VM and changes the host through deterministic guard verbs (automatic within policy bounds, owner-approved for host mutations, and digest-bound exact scripts for tier-3 repairs). No agent holds standing host root (ADR 0006).
3. **Staged harness support.** The catalog lists twelve harnesses with popularity and licence metadata, but "supported" is granted only after a harness passes role tests on its pinned version. v0.1 targets Claude Code and Codex as CTO and worker, with Pi as fallback; oh-my-pi and Hermes follow once validated; consumer-plan Antigravity stays owner-run only (ADR 0003, 0004, 0007).
4. **Hardware-profile local AI lane.** A coding subscription does not licence model weights, and CPU-only inference has substantial cold-prompt latency. Local AI remains a first-class planned lane so owners can run Ötüken as a home server, enabled per hardware profile (GPU/unified-memory hosts, private-network servers, or benchmarked CPU profiles) (ADR 0005).
5. **Stock-Ubuntu layer instead of a custom ISO.** Unlike Omarchy's Arch ISO, Ötüken installs onto stock Ubuntu 24.04 LTS without modifying Ubuntu media or repartitioning existing servers, while adopting Omarchy's repository shape, release verification, migration, and CI discipline (ADR 0001).
6. **Documented-only usage reporting.** The wall-board contract reports remaining limits only from documented vendor routes and labels undocumented providers `unavailable` rather than scraping or reading OAuth tokens directly (ADR 0012).
7. **Per-project login boundary until split execution.** Inside a project VM, project code can observe that project's own login until split execution (T10) proves out; egress allowlists, per-project isolation, and keeping logins out of untrusted repos mitigate the residual risk (ADR 0004, 0010).

## Verification matrix (T1–T17)

| Test | Settles | What runs | Passes when |
| --- | --- | --- | --- |
| T1 | ADR 0009 | VM storage bake-off on a btrfs-only host: `dir`, NOCOW `dir`, btrfs with `size.state`, loop-backed LVM-thin (ZFS optional) | one candidate meets clone, snapshot, restore, build-I/O, near-full-disk and unclean-stop criteria; ties go to the simplest |
| T2 | ADR 0008 | 4 normal and 1 browser VM under concurrent builds, then 5 and 6 | p95 build time and host interaction latency stay within bounds and peak memory leaves the host reserve |
| T3 | ADR 0007 | Claude Code and Codex each as CTO and as worker on the same representative job; live checkpoint exchange; clean swap and swap from a failed seat with workers running; success, denial, transient failure, cancellation | all pass on the pinned versions; Pi replaces either one if it fails a provider or security gate |
| T4 | ADR 0010 | A canary secret in project B; every route from project A (files, environment, network, guard API, provider cache, browser profile, volume), including as root inside A | no route returns it |
| T5 | ADR 0010 | Egress: IP literals, private, link-local and metadata addresses, traffic between VMs, DNS tunnelling, proxy bypass, redirects, over IPv4 and IPv6 | everything outside the allowlist is blocked |
| T6 | ADR 0006 | The guard: raw management requests, expired leases, path escapes, replayed and malformed (fuzzed) requests, rate limits, vsock identity spoofing, a worker reaching the owner socket or the seat's channel, tier-3 script approval bound to its digest | all refused; an approved script runs exactly once; a changed script needs a new approval |
| T7 | ADR 0013 | The kill switch at each level and scope, across a test-VM reboot | contained, with time to containment measured, and admin SSH intact |
| T8 | ADR 0001, 0002 | The installer matrix (btrfs and ext4; manual and cloud-init), a second apply, a test-VM reboot, an upgrade from the previous release, rollback and uninstall | three clean runs and one upgrade run, with logs |
| T9 | ADR 0004 | A week of per-project logins: forced re-logins counted; two Claude workers sharing one login in one VM; Codex refresh inside a VM | re-logins are rare enough for one tap per project; races are recorded, and the setup-token route is used where they occur |
| T10 | ADR 0010 | Split execution for Claude Code (`CLAUDE_CODE_SHELL_PREFIX`) with project settings, hooks and MCP off | coding quality holds on a fixed task set; the runner's own file tools cannot read the login; bypass attempts through built-in tools and hooks fail |
| T11 | ADR 0011, 0013 | Hostile-text fixtures in repositories, issues, web pages and vault drafts | none changes a grant, another job, or canonical policy |
| T12 | ADR 0011 | A two-way vault sync drill on a copy of a vault, for each transport: conflicts, deletes, round trips | nothing is lost silently; conflicts keep both versions and the base |
| T13 | ADR 0012 | Board consumers fed unknown, stale and incompatible events | they ignore unknown fields, show staleness, and reload on an expired cursor |
| T14 | ADR 0014 | A backup restored into a fresh VM, once per release | state, vault and a project come back; logins are re-enrolled |
| T15 | ADR 0005 | Local AI hardware-profile check: `llama-bench` and a representative agent prompt on the target host | the wizard's throughput and latency figures are measured, not extrapolated |
| T16 | ADR 0004, 0013 | Paid-fallback detection on every enabled route (for example Kilo's fallback, OpenCode Go's Extra Usage) | no route can bill silently |
| T17 | ADR 0002 | Nested KVM inside a test VM on the CI host kernel | known; if it is missing, the installer and VM-isolation tests run separately |

## Open vendor clarifications (L1–L3)

| ID | Vendor | Topic |
| --- | --- | --- |
| L1 | Anthropic | Edge cases around owner-created setup tokens and multiple accounts by one individual under consumer vs. commercial terms |
| L2 | Google | Whether a self-hosted supervisor driving `agy` on a consumer plan counts as direct scripting or a wrapping application |
| L3 | xAI | Whether SuperGrok or X Subscription entitlements in OpenCode and Kilo cover unattended use |

## Release readiness

Ötüken is **pre-alpha** until v0.1 passes its full verification gate (T1–T17,
three clean installer runs, one upgrade/rollback/uninstall run, cross-project
isolation, and backup restore).
