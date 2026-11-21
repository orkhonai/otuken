<!-- SPDX-License-Identifier: MIT -->
# ADR 0009 · VM storage on a btrfs-only host

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Open, 2026-11-21: documentation alone does not decide; verification test T1 does. **Topic:** VM storage pool selection on a single-filesystem btrfs host.

## Decision

- **A benchmark bake-off (T1) decides the default pool on btrfs-only hosts.**
- **Candidates:**
  1. an Incus `dir` pool on the existing btrfs, with bounded VM disks;
  2. the same, with the pool directory set to NOCOW (`chattr +C`);
  3. an Incus btrfs pool with each VM's `size.state` set to twice its root disk, as Incus documents for this case;
  4. an LVM-thin pool on a loop-backed NOCOW file (ZFS on a loop file only if measured, with its memory cache capped).
- **Criteria:** clone and snapshot time; restore time; sustained random-write throughput and latency during a real build; behaviour as the host filesystem fills toward 90 %; recovery after an unclean stop; memory overhead; how cleanly a project's disk is removed. Ties go to the simplest option.
- **Until T1 reports,** CI and test VMs use candidate 1 (`dir` pool), the simplest to inspect and remove. Admission charges each VM's reserved disk against real free space, starting with a 20 % free-space floor, and the guard watches each project's actual disk use.
- **Never repartition an existing host in an unattended install.** On a fresh machine with spare block devices, the installer offers a dedicated partition or disk for a ZFS or btrfs pool, which is Incus's recommended setup.

## Reasons

- On an already-partitioned btrfs host, every option trades off against one of Incus's own recommendations ("The two best options for use with Incus are ZFS and Btrfs", on a dedicated disk or partition) ([Incus storage drivers](https://raw.githubusercontent.com/lxc/incus/main/doc/reference/storage_drivers.md), read 2026-11-21):
  - a btrfs pool: "you should never use VMs with Btrfs storage pools" unless `size.state` is set to twice the root disk size; Btrfs "doesn't natively support storing block devices", so a VM is one big file that "might cause issues when creating snapshots"; and "users can trivially escape any quotas that are set" ([Incus btrfs driver](https://linuxcontainers.org/incus/docs/main/reference/storage_btrfs/), read 2026-11-21);
  - loop-backed storage "isn't recommended for production use", and the directory backend "should be considered as a last resort option" (storage drivers page above); directory pools copy whole files on clone and snapshot, and set limits only on ext4 or XFS with project quotas ([dir driver](https://raw.githubusercontent.com/lxc/incus/main/doc/reference/storage_dir.md), read 2026-11-21);
  - a loop-backed pool still shares the host filesystem's failure and capacity limits, and a loop-backed ZFS pool adds ARC memory overhead that needs measurement.

## Disagreement, and how it was decided

- Every candidate conflicts with at least one Incus recommendation on a single btrfs filesystem, so documentation cannot rank them. Measurement T1 decides; candidate 1 is the initial starting point for test VMs because it is the simplest to inspect and clean up.

## Rejected

- Repartitioning an existing host during an unattended install.
- Choosing a pool on documentation alone without workload measurement.
- A btrfs pool for VMs without the `size.state` setting, which Incus explicitly warns against.

## Open risks

- Thin pools can run out of data or metadata space; both are tracked.
- Sparse VM disks can overcommit the host; admission counts reserved bytes, not used ones.
- If no candidate is acceptable on a btrfs-only host, VMs remain bounded until a dedicated disk is added.

## Verification test

T1, the bake-off above.
