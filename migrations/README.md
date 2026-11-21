<!-- SPDX-License-Identifier: MIT -->
# Migrations

Signed, run-once state and configuration migrations live here as
`migrations/<10-digit-epoch>.py`.

- Each migration receives two positional arguments: the config directory
  (`/etc/otuken`) and the data directory (`/var/lib/otuken`).
- Migrations must touch only rollback-managed configuration and state, and must
  be idempotent across an interrupted run.
- Fresh installations record historical migrations as baseline markers under
  `/var/lib/otuken/state/migrations/` without executing them.
- Updates and reinstalls with retained data take a pre-update checkpoint
  (Btrfs snapshot or ext4 export) before executing pending migrations.
- List pending migrations with `otuken migrations --pending`.

The repository starts with an empty migrations set before v0.1.
