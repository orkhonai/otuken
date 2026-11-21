<!-- SPDX-License-Identifier: MIT -->
# ADR 0008 · One KVM VM per project

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Accepted, 2026-11-21; default concurrency scaling waits for measurement T2. **Topic:** Project isolation and VM sizing.

## Decision

- **Incus is the only sandbox manager.** On a host with KVM the default is one KVM VM per project: its own kernel, its own logins, Docker and browsers without nesting tricks. The light profile, an owner opt-in per project, is an unprivileged system container with an isolated ID map, for trusted, low-risk work that needs many parallel sandboxes or fast start; it is also the fallback on hosts without KVM, where the owner must select it explicitly after the wizard says isolation is weaker. Always a VM: code the owner did not write, pull requests from forks, any browser, and the CTO's seat. The project record says `isolation: vm | container`; the CTO does not choose the hypervisor.
- **Incus 7.0 LTS from the Zabbly repository**, with the repository's signing-key fingerprint checked out of band and recorded in the signed release, a dedicated keyring with `Signed-By`, and apt pinning limited to the Incus packages. Not Ubuntu's archive package. Incus restrictions are a second wall: each product project gets a restricted Incus project from a fixed template (`restricted=true`, `limits.*`); containers get `security.idmap.isolated=true`; every instance has the guest API turned off after provisioning and port isolation on its bridge port.
- **Sizes and starting ceiling** for an illustrative 8-core / 16-thread, 64 GiB host:
  - reserve 10 GiB for the host (guard, Incus, proxy, board, page cache), 4–6 GiB for the seat, 4 GiB for one browser VM while it runs, and 8 GiB for CI while it runs;
  - a normal project VM is 2 vCPU and 6 GiB (one or two agents and an occasional build), a heavy one 4 vCPU and 12 GiB, a browser VM 2 vCPU and 4 GiB;
  - admit at most **4 normal project VMs plus one browser VM, or 2 heavy plus one browser**, raised toward 6 normal only after T2 measures peak memory, build times and host latency under concurrent builds;
  - CI and a loaded on-box local model are charged to the same pool; several agents of one job share their project's VM in separate worktrees; idle VMs stop after 30 minutes without activity and then cost only disk;
  - per-job caps (8 GiB, 200 % CPU, 512 tasks) apply inside each project VM.
- **Other runtimes:** Firecracker, Cloud Hypervisor and Kata come later, and only if VM start time or density is shown to be the bottleneck. gVisor is rejected as the boundary. Rootless Podman stays inside a project VM for its service containers. Harness sandboxes are defence in depth inside the VM, never the boundary.

## Reasons

- Incus describes containers as "a software-only way to isolate" and says that for VMs the boundary "is enforced by those hardware features" ([Incus containers and VMs](https://linuxcontainers.org/incus/docs/main/explanation/containers_and_vms/), read 2026-11-21). Coding agents run third-party code on every build (ADR 0013), and container runtimes keep having breakout bugs ([USN-7851-1](https://ubuntu.com/security/notices/USN-7851-1), read 2026-11-21).
- Each project keeps its own provider logins (ADR 0004), removing the old argument for shared containers.
- Ubuntu's package: noble ships `6.0.0-1ubuntu0.3` ([packages.ubuntu.com](https://packages.ubuntu.com/noble/incus), read 2026-11-21), whose uploads are each a "No change rebuild due to golang-1.22 update" ([changelog](https://changelogs.ubuntu.com/changelogs/pool/universe/i/incus/incus_6.0.0-1ubuntu0.3/changelog), read 2026-11-21), so none of the later security fixes are in it. 2026 brought fixes including "Restricted project users can create resources in the default project, bypassing project isolation", and the 7.0 LTS line is "supported until June 2031" ([Incus news](https://linuxcontainers.org/incus/news/), read 2026-11-21). Zabbly publishes the 7.0 LTS repository for noble ([zabbly/incus](https://github.com/zabbly/incus), read 2026-11-21), and apt sources can be pinned to a keyring with `Signed-By` ([sources.list(5)](https://manpages.ubuntu.com/manpages/noble/man5/sources.list.5.html), read 2026-11-21).
- `security.idmap.isolated` gives "non-overlapping UID/GID maps for each container" ([Incus security](https://raw.githubusercontent.com/lxc/incus/main/doc/explanation/security.md), read 2026-11-21); restricted projects and limits are documented on the projects page ([Incus projects](https://linuxcontainers.org/incus/docs/main/reference/projects/), read 2026-11-21).
- Sizing floors, not measurements: Claude Code asks for "4 GB+ RAM" ([setup](https://code.claude.com/docs/en/setup)), Codex for "4-GB minimum (8-GB recommended)" ([install](https://raw.githubusercontent.com/openai/codex/main/docs/install.md)), Anthropic's hosting guide starts at "1 GiB RAM, 5 GiB disk, and 1 CPU per agent" ([Agent SDK hosting](https://code.claude.com/docs/en/agent-sdk/hosting)), and an idle q35 VM costs about 379 MiB of host memory (a community measurement, [Incus forum](https://discuss.linuxcontainers.org/t/a-fun-project-microvms-with-incus/26889)); all read 2026-11-21.
- gVisor: file-heavy workloads are "Up to 10-200× slower" ([Agent SDK secure deployment](https://code.claude.com/docs/en/agent-sdk/secure-deployment), read 2026-11-21). Firecracker needs its own kernel, root filesystem and TAP networking ([Firecracker specification](https://raw.githubusercontent.com/firecracker-microvm/firecracker/main/SPECIFICATION.md), read 2026-11-21), so the image and network work would become the product.
- Harness sandboxes: "Sandboxing reduces risk but is not a complete isolation boundary" ([Claude Code sandboxing](https://code.claude.com/docs/en/sandboxing), read 2026-11-21).
- Docker Sandboxes are proprietary, and their "default allowed domains include broad wildcards" ([Docker Sandboxes security](https://docs.docker.com/ai/sandboxes/security/), read 2026-11-21).

## Disagreement, and how it was decided

- **The default.** KVM VMs by default; containers only as an explicit owner opt-in light profile.
- **The Incus source.** Zabbly 7.0 LTS behind a verified signing-key fingerprint gate and package pinning; a self-built Incus was rejected because maintaining security patches upstream is safer.
- **The starting ceiling.** 4 normal plus 1 browser as the reference 64 GiB admission ceiling, validated by benchmark T2 before raising further.

## Rejected

- Containers as the default on a KVM host.
- Ubuntu's archive Incus 6.0.0 package.
- Docker Sandboxes, gVisor or custom microVMs as the project boundary.

## Open risks

- Incus's 2026 security churn: patch cadence matters, and the guard does not rely on Incus restrictions alone.
- Concurrency figures are arithmetic on published floors until T2 measures real workloads.
- VM storage on a btrfs-only host is ADR 0009.

## Verification test

T2: run 4 normal and 1 browser VM with concurrent builds, and measure p95 start and build time, host interaction latency, peak resident memory and sustained I/O before confirming or raising the ceiling.
