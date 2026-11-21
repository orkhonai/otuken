<!-- SPDX-License-Identifier: MIT -->
# Guard and Security

Ötüken separates agent reasoning from host authority. The host guard contains
no language model and splits into two processes:

1. **Unprivileged request broker** (`otuken guard service`, run via
   `install/systemd/otuken-guard-request.service` as `otuken-guard`): listens
   on `/run/otuken/request/guard.sock`, drops `CAP_DAC_READ_SEARCH`, blocks
   `io_uring` syscalls, and forwards the original connected Unix socket
   descriptor to the executor.
2. **Privileged executor** (`otuken guard executor --broker-uid UID`): reads
   requests directly from the handed-off descriptor, derives requester identity
   from kernel `SO_PEERCRED`, enforces leases, rate limits, and owner policy in
   `/etc/otuken/guard-policy.json`, and maintains a hash-chained, append-only
   audit journal in `/var/lib/otuken/audit/events.jsonl`.

## Owner approval and break-glass repairs

- Tier-1 verbs (`project.reserve`, `project.release`) execute automatically
  within lease and policy bounds.
- Tier-2 (`host.maintenance`) and tier-3 (`host.script`) requests queue until
  the owner inspects and approves the exact request `id` and `digest` on
  `/run/otuken/owner.sock` (`otukenctl owner`).
- Approved `host.script` repairs run once as root inside a time-bounded systemd
  unit (`otuken-break-glass-<digest>.service`, 120 seconds, 1 MiB capped
  output), preceded by a checkpoint and compared against a pre/post drift
  census covering `/etc`, `/usr`, systemd units, persistence paths, and `dpkg
  --verify`. Undeclared changes or incomplete checks latch an alert until the
  owner clears it.

For the full threat model and vulnerability reporting guidance, see
[`SECURITY.md`](../SECURITY.md) and
[ADR 0013](../docs/adr/0013-security-kill-switch-caps.md).
