<!-- SPDX-License-Identifier: MIT -->
# Install and Layout

> **Pre-alpha:** No signed release or release key is published yet. The
> commands below document the Milestone 1 installer interface tested against
> local development bundles in CI.

## Prerequisites

- Stock Ubuntu 24.04 LTS amd64 with `systemd` and cgroup v2.
- Root filesystem on `btrfs` (install `btrfs-progs` first) or `ext4`.
- `/etc` and `/var/lib` must share the root filesystem type.

## Interactive plan and apply

Download a signed release bundle (`otuken-<version>.tar.gz`, `SHA256SUMS`,
`SHA256SUMS.sig`, and `release.pub`), verify `release.pub` against the SSH
fingerprint published with the signed GitHub release (and on
[otuken.tech](https://otuken.tech) once live), and run:

```bash
sudo ./otuken install --plan \
    --bundle /path/to/bundle \
    --version <version> \
    --allowed-signers /path/to/allowed_signers

sudo ./otuken install --apply --plan-id <digest> \
    --bundle /path/to/bundle \
    --version <version> \
    --allowed-signers /path/to/allowed_signers
```

You can also use `plan` and `apply --plan-digest <digest>`, and add `--json`
for machine-readable output.

Exit codes:
- `0` — plan is empty (nothing to change)
- `2` — changes are pending review
- `1` — error

## Unattended install (`cloud-init`)

Cloud-init can write a private answers directory containing `installer.json`
and invoke the verified loader with:

```bash
sudo ./otuken install \
    --bundle /path/to/bundle \
    --version <version> \
    --allowed-signers /path/to/allowed_signers \
    --overlay /path/to/answers \
    --yes
```

Never place provider logins or secrets in cloud-init user-data; complete
provider logins later inside each guest.

## Filesystem layout

Shared code, owner configuration, and runtime state never mix:

| Purpose | Path | Notes |
| --- | --- | --- |
| Read-only signed releases | `/opt/otuken/releases/<version>/`, `/opt/otuken/current` | Mode `0555` directories, ownership manifest verified on status and apply |
| Owner choices and private overlay | `/etc/otuken/` (`overlay/`, `guard-policy.json`) | Mode `0700`; backed up before updates |
| Runtime state, vault, HQ, audit, checkpoints | `/var/lib/otuken/` | Mode `0700`; `credentials/` excluded from purge exports |
| Sockets and locks | `/run/otuken/` | Runtime only |
| Verified download cache *(reserved)* | `/var/cache/otuken/` | Mode `0700`; created by the installer, unused in Milestone 1 |

Place machine-specific settings in your private overlay under
`/etc/otuken/overlay`, and guard policy ceilings separately in
`/etc/otuken/guard-policy.json` (root-owned, mode `0600`). See
[`config/README.md`](../config/README.md).
