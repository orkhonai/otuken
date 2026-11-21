<!-- SPDX-License-Identifier: MIT -->
# Updates, Rollback, and Uninstall

## Status and pending migrations

Run status checks as the host owner:

```bash
sudo /opt/otuken/current/otuken status
sudo /opt/otuken/current/otuken migrations --pending
```

`sudo otukenctl status` provides the same status output when
`/opt/otuken/current/bin` is on `PATH` (`status` requires root on an installed
host unless `--root` is passed for local testing).

## Updating

`otuken update` verifies the signed bundle and an expiring signed channel file
(`stable.json` or `rc.json`, namespace `otuken-channel`) against the
owner-pinned release key stored in `/var/lib/otuken/control/release-signers`.

```bash
sudo /opt/otuken/current/otuken update --plan \
    --channel stable \
    --bundle /path/to/bundle \
    --version <version>

sudo /opt/otuken/current/otuken update --apply --plan-id <digest> \
    --channel stable \
    --bundle /path/to/bundle \
    --version <version>
```

Before switching `current` or executing any pending `migrations/<epoch>.py`,
Ötüken takes a checkpoint: a read-only Btrfs snapshot of `/etc/otuken` and
`/var/lib/otuken` on Btrfs hosts, or a tar export on ext4 hosts. If a migration
or `self-check` fails, Ötüken automatically restores the checkpoint.

## Recovery and rollback

- `sudo /opt/otuken/current/otuken recover` completes rollback after a hard
  interruption during an update or purge.
- `sudo /opt/otuken/current/otuken rollback --plan` and `--apply --plan-id
  <digest>` restore `/opt/otuken/current` and the pre-update config/state
  checkpoint while preserving live projects, vault pages, HQ, audit history,
  and evidence.

## Release key rotation

To rotate the pinned release signer, obtain the new key's SSH fingerprint
through an independent channel and run:

```bash
sudo /opt/otuken/current/otuken rotate-key \
    --allowed-signers /path/to/new_allowed_signers \
    --fingerprint SHA256:...
```

Rotation receipts are recorded under
`/var/lib/otuken/control/release-key-rotations/`. Rollback preserves the pinned
signer.

## Uninstall and purge

- `sudo /opt/otuken/current/otuken uninstall` removes only product-owned
  releases under `/opt/otuken` and keeps `/etc/otuken` and `/var/lib/otuken`.
- `sudo /opt/otuken/current/otuken uninstall --purge --plan` followed by
  `--apply --plan-id <digest> --confirm "purge otuken"` writes a private final
  checkpoint (excluding `credentials/` and `control/`), prints its removal
  command, and removes `/etc/otuken`, `/var/lib/otuken`, and `/opt/otuken`.
  Purge refuses to run if `/var/lib/otuken/projects` is populated.
