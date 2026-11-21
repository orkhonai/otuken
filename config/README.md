<!-- SPDX-License-Identifier: MIT -->
# Configuration templates

Example owner-editable configuration files for `/etc/otuken/`.

- `guard-policy.json.example`: copy to `/etc/otuken/guard-policy.json` (owned
  by `root:root`, mode `0600`) to set guard policy ceilings.
- `overlay/installer.json.example`: place under your private overlay directory
  at `/etc/otuken/overlay/installer.json` (or pass `--overlay DIR` during
  `otuken install`).

Owner-specific hostnames, keys, account labels, and private preferences belong
in a separate private overlay repository checked out at `/etc/otuken/overlay`,
never in this public repository.
