<!-- SPDX-License-Identifier: MIT -->
# ADR 0001 · Install, releases, updates and rollback

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Accepted, 2026-11-21. **Topic:** Install, releases, updates and rollback.

## Decision

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

## Reasons

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

## Disagreement, and how it was decided

- **One-line bootstrap.** Offering a `curl … | bash` bootstrap that embeds its verification key was rejected: the loader runs before anything has verified the loader, leaving TLS to the host as the sole protection for code running as root. Decided: no pipe-to-shell in the README or on the website. Install ergonomics are met by one copy-paste verification block and by the cloud-init path.
- **Whole-system rollback.** The btrfs and Launchpad sources above show bootable whole-system rollback fails for a root at subvolume ID 5 and for Ubuntu's `subvol=@` mount, so the product does not promise it.
- **Channel names:** `stable` and `rc`, matching Omarchy's naming.
- **Where HQ and the vault live:** `/var/lib/otuken`, rather than `/srv/otuken`, so all product state sits under one root for snapshots and backups.

## Rejected

- A custom ISO or a prebuilt image (above). Packer now ships under the Business Source License ([Packer LICENSE](https://raw.githubusercontent.com/hashicorp/packer/main/LICENSE), read 2026-11-21); prebuilt Incus images can come from CI instead.
- Running from a moving branch.
- Pure Bash for plan/apply (fragile at this size); Ansible (above); Nix or system-manager, which bring Nix onto a box meant to stay stock; Go for now, which needs a toolchain and a binary to sign (revisit if the guard needs it).
- gpg as the primary signature: a stock box already verifies SSH signatures; gpg arrives with an apt repository later.

## Open risks

- The offline release key is a single point of trust; its loss or theft is a release-wide incident until rotation is rehearsed.
- ext4 hosts have no host snapshots, so rollback there rests on the pre-update export; the plan says so.
- needrestart exclusions delay library fixes for long-running units until the guard restarts them between jobs.

## Verification tests

T8 (installer matrix) and T17 (nested KVM), in ADR 0002.
