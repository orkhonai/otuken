<!-- SPDX-License-Identifier: MIT -->
# ADR 0002 · Self-hosted CI and the release gate

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Accepted, 2026-11-21. **Topic:** CI and the release gate.

## Decision

- **CI is a script in the repository** (`ci/run`) that any owner can run on a KVM host. On a shared host it runs inside a capped Incus project (`otuken-ci`), with CPU, memory and I/O limits that leave live services and running jobs their room. A systemd timer or manual invocation starts it; logs go to the run's evidence directory, and posting a GitHub commit status is optional.
- **Each run**, in throwaway VMs launched from a pinned, verified Ubuntu 24.04 cloud image (`incus launch images:ubuntu/24.04/cloud --vm -e` or offline verified fixtures):
  1. a clean install on btrfs and on ext4, through both the manual and the cloud-init entry points;
  2. a second apply in the same VM: empty plan, no service restarted, no duplicate resource, no data lost;
  3. a reboot of the **test VM** (never of the host), then a check that every service, rule and timer comes back;
  4. install the previous release, seed a project, a vault page and a policy, `update` to the candidate, reboot the test VM, run a job, then rehearse `rollback` and `uninstall` (public SSH reopened);
  5. the isolation tests: project A cannot read project B's secret by any route, including from root inside A (T4); a worker cannot reach the guard's owner socket or the seat's control channel (T6); egress outside the allowlist fails over IPv4 and IPv6 (T5); the kill switch holds across a test-VM reboot (T7); interruption and retry of an apply are safe;
  6. destroy the VMs.
- The installer launches VMs itself, so the test VMs need nested KVM. Where it is missing, the installer tests and the VM-isolation tests run separately, and both must pass.
- A backup restore into a fresh VM runs once per release, not per change, because it is slow; a failing restore blocks the release.
- CI VMs use sanitized fixtures only: no live credentials, no release keys, no control sockets. Subscription smoke tests stay separate from untrusted pull-request CI.
- **Release gate** (v0.1 bar): three clean runs and one upgrade run on Ubuntu 24.04, with logs; the cross-project secret test; two CTO harnesses and two worker harnesses passing a real job in both roles (ADR 0007).
- **Public repository CI:** unit and lint jobs, and VM jobs if hosted runners can boot full VMs fast enough, run on GitHub-hosted runners. Any self-hosted runner never executes pull requests from forks; hardware tests run only for maintainer-approved branches and tags.

## Reasons

- Self-hosted runners are free today ([GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), read 2026-11-21), though GitHub announced and then postponed a per-minute charge for them ([GitHub pricing changes](https://github.com/resources/insights/2026-pricing-changes-for-github-actions), read 2026-11-21). A plain script depends on neither.
- Ephemeral Incus instances get "deleted when stopped" ([incus launch](https://linuxcontainers.org/incus/docs/main/reference/manpages/incus/launch/), read 2026-11-21).
- "self-hosted runners should almost never be used for public repositories on GitHub" ([GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use), read 2026-11-21); GitHub also documents how a compromise can persist on a self-hosted runner ([compromised runners](https://docs.github.com/en/actions/concepts/security/compromised-runners), read 2026-11-21).
- Hosted runners are "free and unlimited on public repositories" ([GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners), read 2026-11-21), and KVM has been usable on them since 2024 ([GitHub changelog](https://github.blog/changelog/2024-04-02-github-actions-hardware-accelerated-android-virtualization-now-available/), read 2026-11-21); whether full VMs boot fast enough there remains to be measured.

## Rejected

- A GitHub Actions self-hosted runner as the only CI path: self-hosted runner pricing has been in flux, and public PRs cannot safely execute on a self-hosted host.
- Forgejo's runner (requires a Forgejo server) and Buildkite (hosted control plane) ([Forgejo runner](https://forgejo.org/docs/latest/admin/actions/runner-installation/), [Buildkite pricing](https://buildkite.com/pricing/), read 2026-11-21).

## Open risks

- Nested KVM inside Incus VMs depends on host kernel and CPU configuration and must be verified per CI host (T17).
- Self-hosted CI on a shared host competes with live workloads; resource caps must be enforced before the first run.

## Verification tests

T8 (installer matrix, idempotence, test-VM reboot, upgrade, rollback, uninstall) and T17 (nested KVM).
