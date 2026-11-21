<!-- SPDX-License-Identifier: MIT -->
# ADR 0014 · Backups

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Accepted, 2026-11-21. **Topic:** Local snapshots and off-box backups.

## Decision

- **Local layer.** btrfs snapshots stay as the hourly layer: read-only, kept 48 hours, skipped when the filesystem is above 70 % full, plus one before every update. On ext4 the pre-update export takes their place. A snapshot on the same disks is not a backup.
- **Off-box backup** is an optional module, off by default and offered at install; while it is off, the board shows a standing notice. It uses restic, encrypted, to either a rest-server started with `--append-only` or S3-compatible storage with Object Lock in compliance mode. Pruning runs only from the backup side, with age-based retention set on an independent system; the box, and therefore the CTO, never holds a credential that can delete or rewrite backups.
- **Scope:** `/etc/otuken` and `/var/lib/otuken` (state, journal, audit, HQ, vault, evidence) and the project registry. Projects themselves travel by git push, or by a per-project export the owner opts into. Provider logins and the host credential store are left out and re-created by logging in after a restore.
- **Restore:** install Ötüken on a fresh Ubuntu, run `otuken restore`, log in again, and start the projects you need. CI restores a backup into a fresh VM once per release, and a failing restore blocks the release. The board shows the last good backup and the last restore test.

## Reasons

- restic encrypts with AES-256 and authenticates with Poly1305-AES ([restic references](https://restic.readthedocs.io/en/stable/100_references.html)); rest-server's `--append-only` "allows creation of new backups but prevents deletion and modification of existing backups" ([rest-server](https://github.com/restic/rest-server)); under S3 compliance mode an object "can't be overwritten or deleted by any user, including the root user" ([S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)); restic warns that in append-only mode a compromised writer can influence count-based pruning, hence age-based retention from an independent system ([restic forget](https://restic.readthedocs.io/en/stable/060_forget.html#security-considerations-in-append-only-mode)); all read 2026-11-21.
- Borg 1.4 is an acceptable alternative; for Borg 2.0 the project says "Do not use it in production yet" ([BorgBackup](https://borgbackup.org/), read 2026-11-21).
- Logins stay out because a restored refresh token may already have been rotated, and a backup full of live logins is a theft target.

## Rejected

- Backups the box can delete.
- RAID1 or local snapshots as the disaster plan.

## Open risks

- An owner who leaves off-box backup off accepts losing host state if the server fails.
- The restic key ceremony: a passphrase on standard input for v0.1, and an optional key file in the owner's private overlay.

## Verification test

T14: restore a backup into a fresh VM, once per release.
