<!-- SPDX-License-Identifier: MIT -->
# AGENTS.md

Guide for coding agents and contributors working in **Ötüken** (`orkhonai/otuken`).

## Repository Layout

- `otuken`, `bin/otuken`, `bin/otukenctl` — CLI entry points (`otuken` invokes `engine/main.py`; `otukenctl` is the control CLI).
- `engine/` — Python 3 standard-library installer, release verifier, backup/checkpoint engine, guard executor, break-glass runner, and Unix socket transport. No third-party Python dependencies.
- `install/` — Server install assets and systemd unit templates (`install/systemd/otuken-guard-request.service`).
- `migrations/` — Signed run-once state migrations (`migrations/<10-digit-epoch>.py`).
- `default/` — Read-only defaults shipped inside signed releases (`default/guard-policy.json`, `default/installer.json`).
- `config/` — Owner-editable configuration templates for `/etc/otuken/`.
- `manual/` — Operator-facing manual linked from `README.md`.
- `docs/` — Architecture design (`docs/DESIGN.md`), ADRs (`docs/adr/`), and fetched-tool inventory (`docs/THIRD-PARTY-TOOLS.md`).
- `ci/` — Offline Incus CI runner, preflight checks, and synthetic isolation fixture builders.
- `ops/` — Host maintenance and first-run Incus CI helpers.
- `test/` — Unprivileged unit test suite (`./test/all`) and linter entry point (`./test/lint`).
- `version` — Current semantic release version.

## Core Invariants

1. **Zero non-stdlib runtime dependencies in `engine/`**: the installer must run on stock Ubuntu 24.04 LTS amd64 with `/usr/bin/python3 -I -B`.
2. **Verify before execute; plan before apply**: releases are verified with `ssh-keygen -Y verify` before extracting any archive member; mutating operations require a matching plan digest under lock.
3. **Separate code, config, and state**: `/opt/otuken` (read-only releases), `/etc/otuken` (owner choices and private overlay), `/var/lib/otuken` (state, vault, HQ, audit, checkpoints, credentials).
4. **Never leak private data**: hostnames, IP addresses, credentials, account labels, and machine-specific configuration live in the owner's private overlay (`/etc/otuken/overlay`), never in this public repository.
5. **Licensing and REUSE 3.3**: MIT license only; never copy AGPL, FSL, or unlicensed code into the repository. Keep SPDX headers and `REUSE.toml` clean (`reuse lint`).
6. **Work safety**: never delete uncommitted or unpushed project work; never run live host modifications or `sudo` during unit tests.

## Running Checks

```bash
./test/all   # Unprivileged unit test suite (no root or VMs required)
./test/lint  # ruff, ShellCheck, and REUSE compliance
```

Full VM installer, upgrade, rollback, and nested isolation gates require an Ubuntu 24.04 amd64 KVM host with Incus; see [`ci/README.md`](ci/README.md).
