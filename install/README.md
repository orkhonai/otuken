<!-- SPDX-License-Identifier: MIT -->
# Install assets

Server installation units and layout assets shipped with Ötüken releases.

- `systemd/otuken-guard-request.service`: systemd unit for the unprivileged
  guard request broker (`User=otuken-guard`, drops `CAP_DAC_READ_SEARCH`, blocks
  `io_uring` syscalls, restricts address families to `AF_UNIX`).

See [`manual/02-install.md`](../manual/02-install.md) for the verified
installation flow and [`CONTRIBUTING.md`](../CONTRIBUTING.md) for local guard
prototype setup.
