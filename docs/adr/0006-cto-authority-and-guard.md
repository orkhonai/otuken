<!-- SPDX-License-Identifier: MIT -->
# ADR 0006 · The CTO's authority, bounded by a non-agent guard

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Accepted, 2026-11-21. **Topic:** CTO authority and deterministic host guard.

## Decision

- **Order.** The owner runs the deterministic installer as root; no model is involved. It lays down the base, the guard, the credential store, the board endpoint and the seat. The guard then starts the CTO in the seat. From there the CTO guides setup the way a sysadmin would: it talks to the owner, proposes choices (workers, subscriptions, local AI profile, modules), runs the login flows, explains failures and retries. It changes the host only through the guard, which renders the exact plan and applies it with the same deterministic engine. If no model is reachable (no login yet, a provider outage), the same steps run from the terminal wizard. The install never depends on a model behaving.
- **The seat.** The CTO runs as root inside its own KVM VM (2 vCPU, 4–6 GiB). On a host without KVM the seat is an unprivileged host user, and the plan says isolation is weaker.
- **What the CTO owns:** everything except five things: the guard (its code and policy), the audit trail, the host credential store, the backups, and the owner's rescue path. It acts on everything else by tier:

  | Tier | How | Examples |
  | --- | --- | --- |
  | 0. Direct | root inside the seat; no guard involved | install tools in the seat, edit HQ, run git and scripts, keep its own notes |
  | 1. Through the guard, automatic within policy limits | a typed call checked against policy and ceilings, written to the audit log, refused with a reason when out of bounds | create, start, stop, snapshot or delete a project sandbox (delete refuses unpushed work); start, steer and stop workers; bind an existing secret to a project; mint a one-repository GitHub token; add a domain from an allowed egress class; start a browser VM; install a harness version listed in the signed catalog; read usage limits; report to the board; set a job's state; propose vault changes; read-only host diagnostics (unit status, journal excerpts, disk and RAID state); trip the kill switch on any scope |
  | 2. Through the guard, owner-approved | the guard holds the request with its rendered plan; the owner approves over SSH (`sudo otuken approve <id>`) or with an authenticated board action | host packages outside the catalog, new open ports or public exposure, users, raising a ceiling, new egress classes, enabling a module (cross-use, off-box backup, local model), creating a secret (the owner types the value), policy edits |
  | 3. Owner-approved root script | the CTO writes an exact script; the guard shows it in full with its digest; the owner approves it over SSH only; the executor runs the exact approved text once as real host root, after a checkpoint, in a time-bounded systemd cgroup; the journal records the script and its hash, with bounded output and a post-run drift report | host work no typed verb covers: a broken service, a one-off repair |

- **Tier 3 trust and detection.** The owner authorizes real root to do repairs such as restarting services or editing system configuration. The cgroup bounds and reaps processes that stay in it. An approved root script can start work outside that cgroup, including a separately managed service. The drift alarm is detective. It compares all of `/etc`, cron storage, `/usr/local`, units, package verification, the guard state and rescue paths before and after. The census also covers new files under `/usr` and login and user-unit persistence for root, interactive and lingering accounts. Undeclared stable changes and incomplete checks latch an alarm. The report lists changes observed outside the script window separately. Host root can alter the guard or the evidence, so the owner must review the exact script as privileged code. Tier-1 and tier-2 operations remain typed and policy-bound. The shipped unprivileged broker unit (`install/systemd/otuken-guard-request.service`) drops `CAP_DAC_READ_SEARCH` and denies all three `io_uring` syscalls. The privileged executor runs outside the broker sandbox.
- **No agent-held host root.** The product has no interactive root session for an agent and no standing-root switch. A root shell on the host stays the human's: the provider's admin user, which the installer never removes or changes.
- **The guard** contains no model and runs as two processes: an unprivileged request service that parses, validates, rate-limits, queues and leases requests, and a tiny root executor that runs only fixed templates and alone holds the Incus admin socket. No agent, the CTO included, gets an Incus credential.
  - Callers on the host are identified by the socket they use and `SO_PEERCRED`; VMs reach the guard over vsock and are identified by their vsock ID, plus a per-generation lease. A guest's network address is never its identity.
  - Every mutation carries a lease (project, job, allowed verbs, expiry, budget) and an idempotency key; each CTO generation and each worker launch has its own identity, and a handover rotates the CTO's authority. Interrupted requests are reconciled against the real resources before a retry.
  - Each verb has a rate limit (a token bucket; for example ten `project.create` an hour) and the guard keeps global ceilings (running instances, a disk floor, the host's RAM and CPU reserve).
  - The typed tier-1 and tier-2 endpoints refuse raw shell, arbitrary paths, images or URLs, devices, mounts and free-form Incus flags.
  - Policy is root-owned under `/etc/otuken/`; the CTO can propose policy, never write it.
  - The audit log is append-only (chained journal and dedicated journald namespace), optionally shipped off-box. Timers and caps go through systemd and cgroups; credentials go to units with `LoadCredential=`, not environment files.
  - Each product project's sandboxes live in a restricted Incus project (`restricted=true`, `limits.*`), so a request that slips past the guard still cannot create a privileged container or pass that project's ceilings.
- **No path from a project VM to the seat's control channel** or to the control app's API. Worker output reaches the CTO only as files and board events.
- **One tool surface for every harness:** an MCP server (`otuken mcp`, a small stdio shim inside each VM that talks to the guard with that VM's lease) and a CLI (`otukenctl`) with the same operations, so a harness without MCP loses nothing.

## Reasons

- An agent is bounded only by something it cannot rewrite. A CTO with host root can stop the guard, edit the policy, read every login and delete the snapshots, so every guard becomes advisory.
- The seat is a VM because the CTO reads the most injected text (worker output, the web, the vault) and has the widest tool access; a VM limits a compromised CTO to its own machine plus the guard's verbs.
- Two processes, so that a parsing bug lands in an unprivileged process.
- Incus's Unix socket "always grants full access" ([Incus README](https://raw.githubusercontent.com/lxc/incus/main/README.md), read 2026-11-21), and full socket access gives administrative control including attaching host devices and filesystems ([Incus security](https://linuxcontainers.org/incus/docs/main/explanation/security/), read 2026-11-21).
- 2026 brought Incus fixes for cases where "Restricted project users can create resources in the default project, bypassing project isolation" ([Incus news](https://linuxcontainers.org/incus/news/), read 2026-11-21), so restricted projects are a second wall, never the boundary.
- `SO_PEERCRED` "returns the credentials of the peer process connected to this socket" ([unix(7)](https://man7.org/linux/man-pages/man7/unix.7.html), read 2026-11-21). Incus proxy devices forward Unix sockets only into containers, and VMs get NAT/TCP only ([proxy device](https://raw.githubusercontent.com/lxc/incus/main/doc/reference/devices_proxy.md), read 2026-11-21); Incus records each VM's `volatile.vsock_id` ([configuration options](https://raw.githubusercontent.com/lxc/incus/main/doc/config_options.txt), read 2026-11-21).
- `RuntimeMaxSec=` ([systemd.service](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)), `systemctl freeze` ([systemctl](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html)) and `LoadCredential=` ([systemd.exec](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)), all read 2026-11-21.
- sudo with a command allowlist fails on programs that spawn shells or read files, "a curated list of Unix-like executables that can be used to bypass local security restrictions in misconfigured systems" ([GTFOBins](https://gtfobins.github.io/), read 2026-11-21).

## Disagreement, and how it was decided

- **Where the CTO runs.** Running the CTO as a host user shares the host kernel, leaving it one local privilege escalation away from the guard, credential store, and backups. Decided: seat VM; host user only on hosts without KVM.
- **Agent-held host root.** A time-boxed root session lets an agent install persistence that outlives the time box, and standing root removes the guard boundary altogether. Tier 3 gives the CTO reach for one-off host repairs while keeping every root action bound to the owner's explicit, recorded approval of an exact script digest.

## Rejected

- Standing `sudo NOPASSWD: ALL` for the CTO.
- sudo with a command allowlist.
- Root inside a confined systemd unit: a root process with enough capability to administer the box has enough to escape the confinement.
- A second model as the guard: enforcement must be deterministic, and a model judge can be prompt-injected like the CTO. A model may advise on tier-2 requests, never gate them.
- No host operational reach for the CTO at all.

## Open risks

- Tier-3 scripts depend on the owner reading them, and approval fatigue is the failure mode. They are SSH-only, shown in full, rate-limited and counted on the board.
- The guard's bugs are the system's bugs: it stays small, tested and fuzzed (T6).
- vsock identity must be shown not to be spoofable by another VM (T6).

## Verification test

T6: raw management requests, expired leases, path escapes, replayed mutations and malformed requests are refused; rate limits hold; a worker cannot reach the owner socket or the seat's channel; a VM cannot present another VM's identity; an approved tier-3 script runs exactly once, and a changed script needs a new approval.
