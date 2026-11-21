<!-- SPDX-License-Identifier: MIT -->
# Offline Incus CI

The owner provisions the restricted Incus CI project and profile using the
[first-run runbook](../ops/first-run.md). The host runs only the pinned, reviewed
copy under `/opt/otuken-ci/runner`. Candidate source and tests are
extracted and executed inside the disposable guest from its signed bundle.

```bash
sudo systemd-run --scope --unit=otuken-ci-run --property=RuntimeMaxSec=2h \
    /opt/otuken-ci/runner/ci/run /path/to/offline-fixtures run-name
```

Evidence stays in `/var/lib/incus/otuken-ci-evidence/run-name`. The
scope bounds the runner, and each Incus operation has its own timeout.
After a forced timeout, confirm the CI project is empty before scheduling
another run. The runner refuses host vsock listeners until the future
guest identity policy explicitly denies the CI CIDs. The script uses one disposable outer VM at a
time. It uses Incus's guest agent to move files and verify a guest reboot by
its boot ID. Every lane needs the agent for `incus exec` and file transfer.
Incus supplies its agent configuration on a generated read-only CD-ROM.
The guest starts the service when the Incus virtio status port appears, so
the bare-QEMU build and attestation guests leave it inactive. A private
executable tmpfs holds the agent and its config on guests with `/run` mounted
`noexec`. No outer VM
has a NIC or host directory share. Run self-hosted
CI only from maintainer-approved revisions.

Install the independently verified public trust files as root at
`/etc/otuken-ci/image.allowed_signers` (principal `otuken-ci`)
and `/etc/otuken-ci/release.allowed_signers` (principal
`otuken-release`). Keep them outside the fixture tree. The runner
stages fixed inputs before verifying and importing the staged copies.
After comparing each signer with its independent fingerprint, install the
anchored files with the following commands.

```bash
sudo install -d -m 0755 /etc/otuken-ci
sudo install -o root -g root -m 0644 /path/to/verified-image-signers /etc/otuken-ci/image.allowed_signers
sudo install -o root -g root -m 0644 /path/to/verified-release-signers /etc/otuken-ci/release.allowed_signers
```

Build the offline images on the CI host as an unprivileged user. The
[first-run runbook](../ops/first-run.md#3-build-and-compare-guest-contents-on-the-host)
uses signed Canonical and package inputs, read-only media, and QEMU with
no virtual NIC. The dedicated builder uses fresh verified inputs and must
match the reviewed reference filesystem and installed package inventories
under the explicit allowlist before getting scoped KVM access. After
the nested checks pass, `PROVENANCE.json` binds both sets of inventories,
the comparison, Canonical receipt, package checksums, and exact cold
media hashes. The owner reviews and admits the cold media before
preparing Incus.

| Path | Contents |
| --- | --- |
| `IMAGES.sha256`, `IMAGES.sha256.sig` | Checksums for the four image files and SSH signature in the `otuken-ci-image` namespace |
| `ext4.metadata.tar.xz`, `ext4.disk.qcow2` | Pinned Ubuntu 24.04 amd64 cloud VM with Incus agent and an ext4 root |
| `btrfs.metadata.tar.xz`, `btrfs.disk.qcow2` | Same Ubuntu base, with a btrfs root, btrfs-progs and Incus agent |
| `previous/` | Compatible previous signed bundle and its `version` file |
| `candidate/` | Candidate signed bundle matching the checkout's `version`, plus signed `rc.json` |

Record upstream image fingerprints and how the two sanitized images were built
when signing the fixture manifest. The images need cloud-init, Python, OpenSSH
client and a clean SSH service or socket for reboot and ownership checks. Keep
image preparation, any package downloads, and signing outside the runner.
Private signing keys and live credentials never enter CI VMs.

The installer lane covers clean/manual and cloud-init installs on both
filesystems, an empty second apply, reboot, a previous-release upgrade,
rollback, and ownership-scoped uninstall. The `clean` and `upgrade`
lanes run those matrices separately and leave a `ci.ok` receipt after
the project is empty. Use `OTUKEN_CI_LANE=installer`
to run it independently when the test VM lacks nested KVM. Run
`OTUKEN_CI_LANE=isolation` on a host that supports nesting, or run
`isolation.py` inside a separate, purpose-built offline isolation host using
the same topology below. Passing both lanes is required. The release gate
also requires the harness and restore runs in
[ADR 0002](../docs/adr/0002-ci-and-release-gate.md).

## T4–T6 topology

The ext4 isolation image includes `/opt/ci-fixture/isolation-setup` and the
offline packages/images needed to exercise the candidate sandbox
configuration. This maintainer fixture starts two worker VMs plus a seat
and simulated endpoints inside the disposable outer VM and writes
`/run/ci-fixture/topology.json`. The recipe places the workers in distinct
Incus projects on separate synthetic bridges. Worker B holds the canary
and explicitly formats and mounts its dedicated blank virtual block volume
after checking the device serial. The fixture's routes, DNS and administrative
endpoints exercise the probes inside the disposable VM. A production
deployment requires its own backend evidence. The full isolation gate
fails if the fixture or nested KVM is missing. The local guard tests still
run first.

A bare QEMU TCG rehearsal can exercise guest preparation, the agent unit's
device trigger and the canary mount with a disposable SCSI test disk.
Incus 7.0 requires `/dev/kvm` and vsock to start nested workers. The KVM
attestation verifies the actual agent connections, Incus volume attachment
and the full T4–T6 checks across two nested VMs.

The JSON has `guests` mapping `worker-a` and `worker-b` (and additional named
controls if needed) to two-item arrays of Incus project and instance name,
a fresh synthetic `canary` string, two `allow` probes for IPv4 and IPv6, and
`t4`, `t5`, and `t6` maps keyed by the cases in
[`isolation.py`](isolation.py). A probe has a `kind` and `target`. File,
environment, Unix socket or HTTP probes take a string. TCP and vsock take
an address/CID and port pair. DNS takes a fixture name and `AF_INET` or
`AF_INET6`. T5 and T6 also specify a `control` client, either a named VM or
`fixture-host`. Use only endpoints created within the isolated fixture.
Every negative probe gets a positive control. The test client runs as root
in both worker VMs. The guard unit suite exercises typed validation, lease
expiry, quotas, digest-bound approval, replay and restart persistence.
Guest identity, policy-backed DNS and egress enforcement remain VM gates.
