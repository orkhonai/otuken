<!-- SPDX-License-Identifier: MIT -->
# Contributing

Read the [manual](manual/01-welcome.md), the [design](docs/DESIGN.md), and the
[ADRs](docs/adr/README.md) before changing the installer, guard, or sandbox
boundary. Keep machine-specific configuration in a separate private overlay
checkout (`/etc/otuken/overlay`) and runtime credentials in an owner-managed
credential store. Use synthetic fixtures. Keep uncommitted and unpushed project
work intact.

Run the local checks as an unprivileged user:

```bash
./test/all   # Python unittest suite (engine, guard, break-glass, CI helpers)
./test/lint  # ruff, ShellCheck across all CLI/CI/ops scripts, and REUSE 3.3 lint
```

## Releases

Build a release archive from a reviewed signed tag using
`git archive --format=tar.gz --prefix="otuken-$version/" "$tag"`.
The tag's `version` file must match the archive name. Publish the archive,
`release.pub`, `SHA256SUMS`, and `SHA256SUMS.sig`. Sign the checksum file
using `ssh-keygen -Y sign -n otuken-release` and the offline release key. The
SSH signing principal is `otuken-release`. Publish the release-key fingerprint
with each signed GitHub release (and on [otuken.tech](https://otuken.tech) once
the site is live).

For updates, publish `stable.json` or `rc.json` beside the bundle. Its four
fields are `channel`, `version`, `sha256`, and `expires` (UTC, to the second,
with the `Z` suffix). Sign its exact bytes with the `otuken-channel` namespace.
The first approved apply enrolls one owner-verified ED25519 signer in
`/var/lib/otuken/control/release-signers`. To rotate it or enroll a legacy
install, the owner runs the trusted loader with
`rotate-key --allowed-signers PATH --fingerprint SHA256:...` using a
fingerprint obtained independently. The control directory keeps rotation
receipts with the previous signer. Rollback preserves the pin. Rehearse key
rotation and revocation before the first publication.

Migrations are signed release files named `migrations/<10-digit-epoch>.py`.
They receive the config and data directories as arguments. Keep them limited
to rollback-managed config and state, and idempotent across an interrupted
run. A fresh installation marks historical migrations as the baseline.
Reinstalls with retained data checkpoint it before running pending migrations.
Include initial defaults under `default/` in the base install. For btrfs the
installer snapshots the product subvolumes, and for ext4 it exports the
corresponding trees. Rollback preserves live project work, the vault, HQ,
evidence, and history. The owner must stop guard processes before offline
lifecycle maintenance. [CI fixture contract](ci/README.md)

## Local guard prototype

On a disposable installed host, run the executor from a host owner session
with `otuken guard executor --broker-uid UID`, using the numeric UID of a
dedicated unprivileged broker account (`otuken-guard`). For the request socket,
the owner creates `/run/otuken/request` with mode 0755 and that account as
owner. Run the broker with the shipped
`install/systemd/otuken-guard-request.service` after creating the dedicated
account and request directory. This unit drops `CAP_DAC_READ_SEARCH` and blocks
the `io_uring` syscalls. The broker passes the original connected descriptor to
the executor. The executor reads the request and gets its identity from kernel
peer credentials. Publish any owner guard policy separately at
`/etc/otuken/guard-policy.json`, with root ownership and mode 0600.

Each invocation of `otuken guard owner` or `otuken guard request` (or via
`otukenctl owner` / `otukenctl request`) reads one newline-terminated JSON
object from standard input. The owner grants a lease for a client UID, project,
job, allowed verbs, TTL, and request budget. The client sends a UUID-shaped
hexadecimal `id`, `lease`, `project`, `job`, `verb`, and `args`. Use
`project.reserve` and `project.release` for capacity bookkeeping. The owner can
`inspect` a pending `host.maintenance` or `host.script` request and `approve`
its exact `id` and `digest`. For `host.script`, include `args.targets` to
declare expected absolute file paths. A trailing slash includes a directory's
descendants. Omit the list for an empty declaration. The owner approves the
script and targets in one digest. Poll `inspect` for the execution result and
private drift report. The report and capped output live in
`/var/lib/otuken/evidence/break-glass`. Review undeclared stable changes and
the separately listed paths that changed outside the service window. In a busy
maintenance window the owner can set `OTUKEN_DPKG_VERIFY_SECONDS` to 60–1800
seconds in the executor environment. The default is 360 seconds per package
check. Owner `halt` revokes outstanding leases and keeps the guard halted
across restarts. Owner `resume` permits new leases. The local protocol and
ledger are milestone scaffolding.
