<!-- SPDX-License-Identifier: MIT -->
# Defaults

Read-only product defaults shipped inside signed releases under
`/opt/otuken/releases/<version>/default/`.

- `guard-policy.json`: default guard admission and rate ceilings (`max_projects`
  and `per_verb_per_hour`, matching `engine/guard.py`).
- `installer.json`: default installer choices (`snapshot_free_percent`).

Do not edit files under `/opt/otuken/`. Place owner-managed configuration under
`/etc/otuken/` instead; see [`config/`](../config/README.md).
