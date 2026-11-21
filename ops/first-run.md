<!-- SPDX-License-Identifier: MIT -->
# First Incus maintenance run

The host owner runs this during a reviewed maintenance window on an
Ubuntu 24.04 amd64 btrfs host with KVM. Keep the provider/BMC console open and
retain a second, independent SSH session. Pause other apt/build activity and
check snapshot freshness, pressure, and pending edits to live units before
starting. This run installs only the approved Incus packages on the host. Test
guests use the Incus agent and have no host NIC or host directory share.

Bring the full independently approved candidate commit ID and previous release
commit ID. Build and review the offline images on the host as described below.
Keep the checkout, image files, and logs on the host so review can inspect the
recipe and logs without moving disks to another machine.

## 1. Transfer and verify the reviewed code

As a dedicated unprivileged build user (`$build_user`), run this from the build
checkout. Use a private destination directory that already exists. The bundle
stays on the host.

```bash
# Unprivileged build user
read -rp 'Absolute path for the local Git bundle: ' bundle
read -rp 'Reviewed branch or ref (e.g. refs/heads/main): ' ref
git bundle create "$bundle" "$ref"
git bundle verify "$bundle"
git rev-parse "$ref"
```

Expect the reviewed candidate hash. The bootstrap also verifies that its
history includes the owner-supplied previous release commit ID. Obtain both
commit IDs through independent review.

On the maintenance host, pass the bundle, ref, previous commit ID, and reviewed
candidate ID to this bootstrap. It stages only the reviewed `ops` and `ci`
trees. The private directory is a separate btrfs subvolume, so parent snapshots
skip keys and large input disks. The bootstrap refuses a different revision on
re-entry.

```bash
# Host owner, via sudo
read -rp 'Local bundle on this host: ' bundle
read -rp 'Reviewed ref inside bundle (e.g. refs/heads/main): ' ref
read -rp 'Independently approved previous release commit ID: ' previous
read -rp 'Independently approved full candidate commit ID: ' commit
sudo /bin/bash -euo pipefail -s -- "$bundle" "$ref" "$previous" "$commit" <<'BOOTSTRAP'
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
bundle=$1 ref=$2 previous=$3 commit=$4
root=/root/otuken-ci-first-run
[[ $commit =~ ^[a-f0-9]{40}$ && $previous =~ ^[a-f0-9]{40}$ && -f $bundle && ! -L $bundle ]]
[[ $(findmnt -n -o FSTYPE -T /root) == btrfs ]]
[[ ! -L $root ]]
if [[ ! -e $root ]]; then
    btrfs subvolume create "$root"
    chmod 0700 "$root"
fi
[[ -d $root && $(stat -c '%u:%a:%i' "$root") == 0:700:256 ]]
exec 9>"$root/first-run.lock"
flock -n 9
repo="$root/reviewed.git"
if [[ ! -e $repo ]]; then git init --bare -q "$repo"; fi
[[ -d $repo && ! -L $repo && $(stat -c '%u:%a' "$repo") == 0:700 ]]
g() { git --git-dir="$repo" -c core.hooksPath=/dev/null "$@"; }
if [[ ! -e $root/reviewed ]]; then
    g bundle verify "$bundle"
    g fetch --no-tags -- "$bundle" "$ref:refs/heads/reviewed"
    [[ $(g rev-parse refs/heads/reviewed) == "$commit" ]]
    g merge-base --is-ancestor "$previous" "$commit"
    g update-ref refs/heads/previous "$previous"
    stage=$(mktemp -d "$root/.reviewed-XXXXXXXX")
    trap 'if [[ -d $stage ]]; then rm -r -- "$stage"; fi' EXIT
    g -c tar.umask=022 archive "$commit" ci ops | tar --no-same-owner -xf - -C "$stage"
    printf '%s\n' "$commit" > "$stage/.bootstrap-commit"
    mv -T -- "$stage" "$root/reviewed"
fi
[[ ! -L $root/reviewed && $(<"$root/reviewed/.bootstrap-commit") == "$commit" ]]
[[ $(g rev-parse refs/heads/reviewed) == "$commit" && $(g rev-parse refs/heads/previous) == "$previous" ]]
printf '%s\n' "$previous" > "$root/previous-commit"
printf '%s\n' "$commit" > "$root/reviewed-commit"
printf 'Verified reviewed checkout %s\n' "$commit"
BOOTSTRAP

run=/root/otuken-ci-first-run/reviewed/ops/first-run
```

Expect `Verified reviewed checkout <candidate>`. Stop on a different hash,
unsafe ownership, or a failed bundle verification. No package changes have
occurred. The bootstrap can be repeated with the same inputs.

If `builder-init` stopped after creating `otuken-ci-build` and before recording
`builder-uid`, use this recovery block only after approving the fix and its
new bundle. It keeps the baseline, account, and builder intent, and sets aside
the old staged checkout. It requires that the builder workspace and CI trust
setup are still absent.

```bash
# Host owner, via sudo; only to resume that interrupted builder-init
sudo /bin/bash -euo pipefail -c '
    umask 077
    root=/root/otuken-ci-first-run
    [[ ! -L $root && $(stat -c "%u:%a:%i" "$root") == 0:700:256 ]]
    exec 9>"$root/first-run.lock"
    flock -n 9
    [[ $(<"$root/builder-intent") =~ ^[a-f0-9]{64}$ ]]
    for path in "$root/"{builder-uid,builder-ready,builder-removed,trust-intent} /var/lib/otuken-ci-build; do
        [[ ! -e $path && ! -L $path ]]
    done
    id -u otuken-ci-build
    if [[ -e $root/reviewed || -L $root/reviewed ]]; then
        [[ -d $root/reviewed && ! -L $root/reviewed ]]
        saved=$(mktemp -d "$root/.interrupted-bootstrap.XXXXXXXX")
        mv -T -- "$root/reviewed" "$saved/reviewed"
        printf "Saved prior reviewed tree at %s\n" "$saved/reviewed"
    fi
'
```

Expect the existing builder UID and, on the first pass, the saved tree path.
Stop if the UID differs or a precondition fails. Repeat section 1 with the
newly reviewed descendant commit and bundle, then repeat `builder-init` in
section 3 with the same approved reference, workspace, and build user. The
helper checks the existing account and records its UID and GID. The previous
baseline is retained.

## 2. Establish baseline and recovery access

Keep an independent administrator SSH session and out-of-band console open
throughout. Verify you can open a fresh SSH connection to your admin address
between stages, and capture the host's local health baseline:

```bash
# Host owner, via sudo
# Optional: to also track a local HTTP service status across stages, run:
# sudo env OTUKEN_CI_HEALTH_URL=http://localhost:<port>/ "$run" health baseline
sudo "$run" health baseline
```

Expect `Baseline local checks OK`. This checks SSH unit health (`ssh.service` /
`ssh.socket`), asks `systemd-resolved` for a DNS answer, records the firewall
policy shape and TCP/UDP listeners, and optionally probes `OTUKEN_CI_HEALTH_URL`
if set. Evidence is root-only under `/root/otuken-ci-first-run/health`. Later
checks require the same DNS link, firewall policy structure, and (if configured)
optional HTTP probe status. Review any listener delta before continuing. Stop
on a failing check.

If you want `ops/incus-host` to monitor additional systemd services alongside
the stock Ubuntu base units (`systemd-sysctl`, `ssh`, `systemd-networkd`,
`systemd-resolved`, `apparmor`), pass a space-separated list through `sudo env`
in `OTUKEN_CI_WATCH_UNITS`.

## 3. Build and compare guest contents on the host

### Build the unprivileged reference

As your unprivileged build user (`$build_user`), run from the approved
checkout. Use a new private Btrfs workspace for each build and keep the earlier
media and logs for review.

```bash
# Unprivileged build user
checkout=$(pwd -P)
git rev-parse HEAD
read -rp 'Existing writable btrfs scratch directory: ' scratch_parent
read -rp 'Reviewed dated Noble image serial (YYYYMMDD): ' serial
build_dir=$(mktemp -d "$scratch_parent/fixture-ci.XXXXXXXX")
btrfs subvolume create "$build_dir/work"
chmod 0700 "$build_dir/work"
build_work="$build_dir/work"
printf 'Build user: %s\nBuild workspace: %s\n' "$(id -un)" "$build_work"
```

Expect the approved commit and a private workspace. Stop if either differs.

```bash
# Unprivileged build user
"$checkout/ci/fixture-fetch" "$build_work" "$serial"
"$checkout/ci/fixture-apt" "$build_work" tools > "$build_work/tool-fetch.log" 2>&1
"$checkout/ci/fixture-apt" "$build_work" guest > "$build_work/guest-fetch.log" 2>&1
for phase in base ext4 btrfs; do
    nice -n 15 ionice -c 3 "$checkout/ci/fixture-build" "$build_work" "$phase" || break
done
```

Expect `Canonical Noble image verified`, authenticated package downloads,
`FIXTURE COMPLETE base`, and successful ext4 and btrfs boot checks. Stop on
any missing completion marker. The host fetch uses the Ubuntu cloud-image
site, Ubuntu archive and security mirrors, and the pinned Zabbly repository
over HTTPS. It installs no host package. The only QEMU inputs are private
disks and read-only ISOs. Guests have no virtual NIC or host directories.
Each TCG VM runs with 3 GiB RAM, two vCPUs, idle I/O priority, and a timeout.
Run one VM at a time. Pause on live resource pressure or stale snapshots.

The Canonical verifier uses the Ubuntu cloud-image keyring, the signed
SHA-256 entry, and primary fingerprint
`D2EB44626FDDC30B513D5BB71A5D6C4C7DB87C81`. APT authenticates the exact
22 tool and 216 guest packages. Review their two manifests against signed
package metadata. These counts describe the reviewed closure for the current
fixture recipe. If APT has since changed, recover the reviewed input files from
the saved cache or stop for review.
[Canonical cloud image verification](https://documentation.ubuntu.com/public-images/public-images-how-to/verify-image-checksum/)

Each build exports inventories from inside offline TCG guests. The guests
reject a dirty ext4 filesystem or a pending ext4 journal or Btrfs tree log
before mounting the finished disks read-only with replay disabled. The ext4
and worker BIOS boot partitions must match the signed Canonical input
byte for byte. The guests inventory the root, separate boot filesystem where
present, and EFI filesystem separately. Each entry records the path, type,
mode, numeric owner and group, logical size, SHA-256, and extended-attribute
digests. A symlink's digest covers its target text. Directory sizes and
digests represent an empty payload, independent of disk layout. The guest
also exports installed package names, architectures, and versions through
its own `dpkg-query`. Gzip inventories travel over dedicated virtio serial
ports. The exporter separately inventories the nested worker and checks
that its QCOW2 bytes match the worker embedded in the ext4 fixture. Every
fixture ISO uses root ownership. Final cleanup deletes snapd runtime state,
persistent journals, the system random seed, and the ldconfig auxiliary
cache. The exporter refuses images where these paths are still present.
Btrfs conversion preserves the temporary directory modes and clears their
contents, including the converter's `blkid` cache.

```bash
# Unprivileged build user
nice -n 15 ionice -c 3 "$checkout/ci/fixture-build" "$build_work" manifests &&
    python3 -I "$checkout/ops/first_run_inputs.py" candidate-reference "$build_work" \
        > "$build_work/reference-candidate.json" &&
    sha256sum "$build_work/reference-candidate.json"
```

Expect three exported inventories and a proposed reference hash. The
candidate binds the three inventory hashes, Canonical receipt, recipe, and
tool and guest package manifests. An independent reviewer checks the exports
under `$build_work/manifests/`, the scrub and boot evidence, and the
[allowlist](fixture-allowlist.json). Exceptions are path-scoped and each has
a reason. Ordinary log churn can change regular log files and safe log
directories. Changes to owners, modes, extended attributes, symlinks,
package versions, and other unlisted files stop the run. The fstab exception
covers only UUID tokens. The embedded QCOW2 exception covers container
size and digest only, with its filesystem independently compared.
The Btrfs initramfs keeps its raw digest and compares archive members
without extracting them. Archive layout, its embedded random seed, and
the generated mdadm timestamp can vary. Changes to other member
contents, ownership, mode, or links still stop the run.

The host owner obtains the approved JSON and its SHA-256 independently. For
rehearsal, repeat the build from fresh verified inputs in a second private
workspace, one VM at a time. Keep both sets of inventories and the comparison
output.

```bash
# Unprivileged build user
read -rp 'Second fresh build workspace with exported inventories: ' repeat_work
python3 -I "$checkout/ops/first_run_inputs.py" match "$repeat_work" \
    "$build_work/reference-candidate.json" "$build_work/manifests" \
    > "$repeat_work/comparison.json" &&
sha256sum "$build_work/reference-candidate.json" "$repeat_work/comparison.json" \
    "$build_work"/manifests/*.json.gz "$repeat_work"/manifests/*.json.gz
```

Expect `"status": "passed"` in `comparison.json`. Stop on any other result
and pass the candidate, both sets of inventories, and comparison evidence for
review only after the rehearsal passes. The candidate JSON alone grants
nothing.

### Host owner creates the dedicated builder and runs the TCG build

Run the following from the host owner's sudo-capable account. Re-enter the
paths, build user name, and independently approved reference SHA-256 there. The
root helper creates a locked system account `otuken-ci-build` with
`/usr/sbin/nologin`, a private home and group (distinct from `$build_user`'s
primary group), and no sudo rule. It stages the previously verified candidate
source to a root-owned, read-only-for-the-builder recipe directory. It copies
the approved Canonical image and named package bytes to the dedicated
workspace, and pins the reviewed reference inventories in the root-owned recipe
directory. The dedicated builder extracts fresh tools, builds both disks under
TCG, boots each from a throwaway overlay, and exports its own inventories. The
unprivileged build user's disks and extracted executables stay in its
workspace.

```bash
# Host owner, via sudo
run=/root/otuken-ci-first-run/reviewed/ops/first-run
read -rp 'Unprivileged build user name recorded above: ' build_user
read -rp 'Build workspace recorded above: ' build_work
read -rp 'Owner-accessible independently reviewed reference JSON: ' reference
read -rp 'Independently approved reference SHA-256: ' reference_hash
sudo "$run" builder-init "$build_work" "$reference" "$reference_hash" "$build_user"
work=/var/lib/otuken-ci-build/home
sudo "$run" builder-build
sudo "$run" health media-built
```

Expect `Dedicated guest inventories match the independently reviewed reference`
and healthy local checks. Any difference outside the allowlist stops the run
before KVM, provenance, signers, or Incus setup. Keep both sets of inventories
for diagnosis. On firewall drift, verify your independent SSH access path
before continuing.

### Host owner grants KVM to the dedicated attestation process

The host owner runs the next block. `stat` resolves the builder from the
workspace owner, so the owner's identity is never passed to the grant. The root
helper verifies `/dev/kvm` is accessible to group `kvm`, prints the host's
`find /dev -group kvm -ls` device census, and asks you to type
`grant-kvm-access` after inspecting every listed device node. The approved
device census is recorded; any later device drift stops the run. After
repeating the inventory comparison, the helper launches the dedicated UID with
primary group `kvm` and a cleared environment. The grant lasts for the bounded
process tree, up to the 40-minute VM timeout, and changes no persistent group
memberships, modes, ACLs, or kernel settings.

```bash
# Host owner, via sudo
work=/var/lib/otuken-ci-build/home
builder=$(sudo stat -c %U -- "$work")
printf 'Attestation builder: %s\n' "$builder"
sudo find /dev -group kvm -ls
if [[ $builder == otuken-ci-build ]]; then
    sudo "$run" builder-attest &&
        sudo "$run" health media-attested
else
    printf 'STOP: unexpected workspace owner\n' >&2
fi
```

Expect `otuken-ci-build`, the reviewed KVM device census prompt
(`grant-kvm-access`), `FIXTURE ISOLATION VERIFIED`, and
`Dedicated attestation (UID and hash)`. Stop on any surprise or any failed
health, device, nested KVM, or isolation check. The ext4 fixture starts two
nested worker VMs with synthetic endpoints and checks all 7 T4, 15 T5, and
3 T6 cases. The full run uses 8 GiB and no virtual NIC to the host. This
evidence exercises the fixture; the product still needs evidence for its
production worker and guard backend.

If `builder-attest` fails and the approved fixture recipe changes, keep the
old serial and comparison logs. The old cold workspace belongs to the old
recipe. Before section 4, verify health and run section 7's rollback to
retire the failed builder and save its workspace. Confirm `Live-host
rollback complete` and check SSH access. Then archive the old first-run state
before bootstrapping the new reviewed commit.

```bash
# Host owner, via sudo; only after rollback of a failed, pre-Incus attestation
sudo /bin/bash -euo pipefail -c '
    umask 077
    state=/root/otuken-ci-first-run
    [[ ! -L $state && $(stat -c "%u:%a:%i" "$state") == 0:700:256 ]]
    exec 9>"$state/first-run.lock"
    flock -n 9
    [[ -f $state/builder-removed && -d $state/builder-evidence ]]
    for path in "$state/"{builder-attestation,fixture-approval,trust-intent,prepare-intent} \
        /var/lib/otuken-ci-build; do
        [[ ! -e $path && ! -L $path ]]
    done
    saved=$(mktemp -d /root/otuken-ci-attempt.XXXXXXXX)
    mv -T -- "$state" "$saved/first-run"
    printf "Archived first-run evidence at %s\n" "$saved/first-run"
'
```

Expect the archive path. Stop if a precondition fails. Start at section 1
with the new reviewed commit and bundle. Capture a new section 2 baseline
and use the new reference candidate and inventories in section 3.

## 4. Review the media, enroll signers, and install the runner

An independent reviewer reads the exact recipe in `ci/fixture*`,
`$work/media/evidence/`, and `PROVENANCE.json`. Check the recorded commit,
upstream Canonical receipt, all 238 package entries, both boot logs, and
all nested T4–T6 cases. Review the reference and cold inventories and their
SHA-256 entries, applied exceptions, and comparison result. The cold media is
authoritative after the comparison passes. Its four image checksums bind the
exact files admitted for CI. The host owner checks the hash independently before
typing it. Keep the evidence on the host.

### Enroll local development keys and build the signed release fixtures

**These are local development keys. The SSH release key here is not the
public release key.** The helper generates two Ed25519 keys once as root.
They live in `/root/otuken-ci-first-run/keys` with private mode 0600.
Only the public allowed-signers lines go into `/etc/otuken-ci`.
Keep the keys out of repositories, bundles, the Incus project, and guests.

```bash
# Host owner, via sudo
sudo "$run" keys
sudo "$run" releases
```

Expect two fingerprints and `Pinned local development and image keys`,
then two valid signed bundles and a valid development channel. Existing
pins and tags must match exactly. Stop on a difference. The helper signs
annotated tags with the following Git command before creating the archives.
It checks the tag type, peeled commit, and signature on every reuse.

```bash
# Host owner, via sudo; shown for review, executed by the root helper above
git --git-dir=/root/otuken-ci-first-run/reviewed.git \
    -c core.hooksPath=/dev/null -c gpg.format=ssh \
    -c user.name='otuken development signer' -c user.email=otuken-dev@localhost \
    -c user.signingkey=/root/otuken-ci-first-run/keys/development-release \
    tag -s "$tag" "$approved_commit" -m "Local development CI $label"
```

That command is the implementation used by `releases`, not a second
manual step. Tags are local to the private bare repository and contain only
the public signature. The previous fixture is the approved prior release
commit; the candidate has its own higher prerelease version. The expiring
signed channel is refreshed when its remaining validity falls below three
hours.

### Admit the verified media

```bash
# Host owner, via sudo
sudo sha256sum "$work/media/"{PROVENANCE.json,ext4.disk.qcow2,btrfs.disk.qcow2,ext4.metadata.tar.xz,btrfs.metadata.tar.xz}
sudo sha256sum "$work/media/evidence/"{fixture-recipe,tool-packages,guest-packages}.sha256 \
    "$work/media/evidence/"{ext4-boot,btrfs-boot,isolation}.serial.log
sudo sha256sum "$work/media/evidence/"{agent,cold}.{ext4,btrfs,worker}.json.gz
read -rp 'Reviewed Canonical release serial: ' serial
read -rp 'Independently reviewed PROVENANCE.json SHA-256: ' image_review
sudo "$run" ubuntu "$serial"
sudo "$run" images "$work/media" "$image_review"
sudo "$run" builder-retire
sudo "$run" runner
sudo "$run" health runner-installed
```

Expect `Canonical Noble image verified`, `Approved offline images verified
and signed`, `Dedicated builder retired`, `Verified runner`, and
`Local checks OK`. The root helper independently verifies the same Canonical
serial, copies the fixed artifacts, checks the provenance against the approved
commit and media bytes, and signs the media manifest with the local image key.
After admission, it removes the dedicated account, group, and workspace and
retains a private read-only evidence snapshot. If the builder is still busy,
follow the quiescence procedure in section 7 before retrying retirement. The
next command installs the verified runner at `/opt/otuken-ci/runner`. Verify
your independent SSH session and stop on any failure before preparing Incus.

## 5. Prepare, install, review

Run one group at a time. The helper keeps the root-only evidence pointer and
its own shell error handling. Completed prepare and install stages can be
repeated. An incomplete stage requires the rollback below.

```bash
# Host owner, via sudo
sudo "$run" prepare
sudo "$run" health prepared
```

Expect `Private maintenance evidence` and a package simulation, or the saved
preparation receipt. Review the simulation for agreed new packages only.
Stop on an upgrade or removal or a failed local check. Proceed only after
reviewing the exact simulation.

```bash
# Host owner, via sudo
sudo "$run" install
sudo "$run" health installed
```

Enter `install-incus` at the confirmation only after checking the proposed
actions. Expect `provisioned-ok` in the saved evidence directory and a capped
NIC-free project. The local checks must pass. Stop on a sysctl, service,
bridge, port, or package discrepancy.

```bash
# Host owner, via sudo
sudo "$run" review
sudo "$run" health reviewed
```

Expect evidence diffs, unchanged firewall structure, and healthy local checks.
In the private evidence, inspect listeners, service timestamps, cgroup limits,
and filesystem headroom. Stop on unexplained differences, stale snapshots, or
resource pressure.

## 6. Run the CI gates

These are three independent clean runs, one previous-release upgrade run,
then the synthetic nested isolation lane. Each clean and upgrade run
exercises its ext4 and btrfs matrix. The wrapper uses a two-hour systemd
scope for each run and keeps bounded logs.

```bash
# Host owner, via sudo
sudo "$run" ci clean clean-1
sudo "$run" health clean-1
sudo "$run" ci clean clean-2
sudo "$run" health clean-2
sudo "$run" ci clean clean-3
sudo "$run" health clean-3
sudo "$run" ci upgrade upgrade-1
sudo "$run" health upgrade-1
sudo "$run" ci isolation isolation-1
sudo "$run" health isolation-1
```

Run each pair separately and verify SSH access between pairs.
An existing successful run prints its receipt. Expect `CI lane passed`
and `ci.ok` for each run. The upgrade must include the previous signed
release, reboot, rollback, and owned uninstall. The isolation log must
contain every T4/T5/T6 case and the local guard tests. A missing nested
KVM capability, setup program, or topology control is a failed isolation
gate. Stop this maintenance run on either result.
The fixture exercises synthetic VM isolation; the production worker
backend remains a separate release requirement.

Logs, QEMU cgroup information, I/O statistics, and guest consoles are under
`/var/lib/incus/otuken-ci-evidence/<run-name>/`. Review actual I/O
and host workload latency during the first run. Stop on failed probes, stale
snapshots, saturation, or a nonzero stage. Keep the evidence.

## 7. Roll back if a stage fails

Stop scheduling. Wait for the current scope to finish, or stop only this
scope if it is still running. Keep the independent SSH session open.

```bash
# Host owner, via sudo
run=/root/otuken-ci-first-run/reviewed/ops/first-run
sudo systemctl stop otuken-ci-run.scope
```

An absent scope is expected if the runner exited already. For an
interrupted CI run, check and clear only objects attributable to that
failed run. The helper compares the instance's run marker and the
recorded image fingerprints, prints the list, and asks for a typed
confirmation. Unrecognized objects stop cleanup for owner review.

```bash
# Host owner, via sudo
read -rp 'Failed CI run name from the evidence directory: ' failed_run
sudo "$run" residue "$failed_run"
```

Expect `Dedicated CI project is empty`. Skip the residue command if CI
has never started. If the runner already cleaned everything, the command
only verifies the empty project.

If retirement or rollback reports live `otuken-ci-build` processes, allow the
active command and its QEMU timeout (40 minutes plus 20 seconds for forced
termination) to finish. For a leftover process, use the following from the
owner's sudo-capable account. It takes the maintenance procedure's lock, checks
the recorded account, and lists its processes before requesting confirmation.

```bash
# Host owner, via sudo; only when an interrupted builder still has processes
sudo /bin/bash -euo pipefail -c '
    state=/root/otuken-ci-first-run
    exec 9>"$state/first-run.lock"
    flock -n 9
    [[ ! -e $state/builder-removed && -f $state/builder-uid ]]
    IFS=: read -r user _ uid gid _ home shell < <(getent passwd otuken-ci-build)
    [[ $user == otuken-ci-build && $home == /var/lib/otuken-ci-build/home &&
        $shell == /usr/sbin/nologin && $uid =~ ^[1-9][0-9]*$ &&
        $uid:$gid == "$(<"$state/builder-uid")" ]]
    if ! pgrep -a -u "$uid"; then exit 0; fi
    read -rp "Type stop-dedicated-builder to terminate these processes: " confirm </dev/tty
    [[ $confirm == stop-dedicated-builder ]]
    pkill -TERM -u "$uid" || [[ $? == 1 ]]
    for ((attempt=0; attempt<30; attempt++)); do
        if ! pgrep -u "$uid" >/dev/null; then exit 0; fi
        sleep 1
    done
    pgrep -a -u "$uid"
    exit 1
'
```

Continue only once the account has no processes. If a process survives the
wait or the lock is still held, diagnose from the independent SSH session before
retrying. Stop if the recorded identity differs.

```bash
# Host owner, via sudo
sudo "$run" rollback
sudo "$run" health reverted
```

Read the proposed removals. Enter `restore-incus-baseline` and, when
shown, `purge-recorded-packages` only after checking direct consumers.
The command finds the saved helper from a fresh shell. Before Incus
preparation, it removes the dedicated builder, runner, and signer
anchors that have been created. After preparation or installation, it reverses
the recorded changes, preserves CI evidence before deleting the pool, verifies
rollback, and removes both `/opt/otuken-ci` and `/etc/otuken-ci`. It removes
the dedicated build account and private group after taking a read-only
snapshot of its workspace. It retains private development keys, the fixture
subvolume, and evidence under `/root` for review. Expect
`Live-host rollback complete` and healthy local checks.

If the local ownership scan times out, leave the identities in place and
retry with an explicitly reviewed bound while the disk is quiet.

```bash
# Host owner, via sudo
sudo env OTUKEN_CI_OWNERSHIP_SCAN_SECONDS=600 "$run" rollback
```

If rollback reports an unknown object, shared dependency, extra trust path,
or unresolved residue, stop and resolve it from the console. The procedure
leaves rescue routes in place and retains the evidence pointer. Keep the host
running and diagnose from the existing session or console.

### Retained evidence and optional cleanup

An interrupted runner install can leave a staging directory under
`/opt/otuken-ci/.runner-*`. The helper removes only the stage
recorded in its root-owned receipt while holding both CI locks. If an
unrecorded stage blocks rollback, inspect its owner and contents from
the console. Resolve that single directory under both CI locks before
retrying. Unknown paths are a stop condition.

Keep the unprivileged build workspace until review has verified the logs and
hashes. After confirming the correct private subvolume and preserving required
evidence, the owner may delete that one subvolume.

```bash
# Host owner, via sudo; optional, after evidence retention is confirmed
read -rp 'Unprivileged build user name: ' build_user
read -rp 'Exact recorded build work subvolume to delete: ' build_work
sudo stat -c '%U %a %n' -- "$build_work"
sudo btrfs subvolume show "$build_work"
read -rp 'Type discard-build-fixture to remove this reviewed path: ' recorded
if [[ $recorded == discard-build-fixture && $(sudo stat -c '%U:%a:%i' -- "$build_work") == "$build_user:700:256" ]]; then
    sudo btrfs subvolume delete --commit-after "$build_work"
fi
```

After verified rollback, a later maintenance cycle needs the old pointer
retired. The evidence directory itself is retained.

```bash
# Host owner, via sudo; optional, after accepting verified rollback
sudo /bin/bash -euo pipefail -c '
    pointer=/root/otuken-incus.evidence
    exec 9>/run/otuken-incus-maintenance.lock
    flock -n 9
    if [[ ! -e $pointer && ! -L $pointer ]]; then exit 0; fi
    [[ -f $pointer && ! -L $pointer && $(stat -c "%u:%a" "$pointer") == 0:600 ]]
    IFS= read -r previous < "$pointer"
    [[ $previous =~ ^/root/otuken-incus\.[[:alnum:]]{8}$ && ! -L $previous ]]
    [[ -f $previous/rollback-ok && ! -e /opt/otuken-ci && ! -e /etc/otuken-ci ]]
    rm -- "$pointer"
'
```

`/root/otuken-ci-first-run` is a private subvolume containing keys,
fixtures, and evidence. Keep it while review or CI depends on the keys.
If retiring the first-run state later, explicitly approve removal after
archiving what you need. Delete its nested read-only `builder-evidence`
snapshot first, then delete the parent with `btrfs subvolume delete` as
root.
