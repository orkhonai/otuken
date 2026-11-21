<!-- SPDX-License-Identifier: MIT -->
# Security

Report vulnerabilities privately through GitHub Private Vulnerability Reporting
on [`orkhonai/otuken`](https://github.com/orkhonai/otuken/security/advisories/new)
(enabled when the repository is published; do not open a public issue for a
security report). Include the affected release, prerequisites and a reproducible
description using synthetic data. Keep credentials and live host details out of
reports.

The owner holds host administration. The installer accepts only an SSH-signed
release that matches the reviewed plan digest. The unprivileged guard service
hands the original Unix socket descriptor to the executor. The executor
gets the requester identity from kernel peer credentials. The privileged executor
keeps the owner socket, request leases, approvals and audit ledger. The owner
reviews an exact break-glass request and approves its digest on the local
owner socket. The executor claims the approved text, journals it with its SHA-256 digest
and starts it as real host root in a two-minute systemd service. It checks
that the service cgroup is empty afterwards. Independently managed units can
outlive that cgroup. Output is capped at 1 MiB.
The owner declares expected file paths and reviews the private report for
changes outside them and unavailable checks. The census tracks creations and
inode changes under `/usr` and login and systemd persistence paths of root, interactive and
lingering users. Changes observed outside the service window are listed
separately for review. The alarm is detective.
The owner must review the script as code with full host authority, including
the ability to change audit records. Keep credentials out of script text
and output. An interruption requires owner reconciliation.

Milestone 1 has no guest-facing guard transport, Incus worker backend,
egress controls, or unattended guard units. The journal uses an append-only inode and a hash chain linked to the ledger.
The host owner can still change root-owned files and inode flags. The threat model assumes trusted hardware,
hosting provider, hypervisor, human administrator and model vendor.
[Threat model](docs/adr/0013-security-kill-switch-caps.md)
