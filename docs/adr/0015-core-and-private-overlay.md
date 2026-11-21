<!-- SPDX-License-Identifier: MIT -->
# ADR 0015 · Core vs. private overlay separation

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Accepted, 2026-11-21. **Topic:** Separating public mechanisms from owner-specific configuration.

## Decision

**The rule:** the public repository holds mechanisms and defaults; the private overlay, a separate git repository the installer reads at `/etc/otuken/overlay`, holds every owner-specific name, address, key reference, account label, and preference. A secret and private-data scan gates publication.

- **Kept out of the public product:** machine-specific services unrelated to the agent server layer; migrations tied to one historical host (the public repository starts with an empty `migrations/` directory); hard-coded checks that refuse anything but one specific RAID/subvolume layout (replaced by detection, ADR 0001); personal workstation relays; references to one owner's internal tools in standing files.
- **Replaced by the new architecture:** shared host users as a project boundary (replaced by per-project VMs, ADR 0008); passwordless-sudo agent accounts (replaced by the guard and seat VM, ADR 0006); shared host-level account directories (replaced by per-project logins, ADR 0004); launch-convention caps (replaced by guard admission control); moving-branch installers (replaced by signed releases, ADR 0001).
- **Belongs in the private overlay (`/etc/otuken/overlay`):** hostnames and host-specific edits; custom domains, TLS publishers, and fixed listeners; remote-access admin lists, admission lists, and admin key fingerprints; hosting-provider-specific rescue notes; account labels and board names, routing preferences, model policies, private API gateway endpoints, key-file paths, password-manager vault names, deploy keys; custom CTO persona, language, and extra rules (appended to Ötüken's neutral CTO `AGENTS.md`); vault sync transport configuration; separately reviewed operator workflows.
- **Optional modules** (off unless chosen by the owner or enabled by hardware profile): the control-app integration (bb); remote access (Tailscale, WireGuard, or none), with SSH admission and watchdog logic; password-manager bridge; mobile status page and reverse proxy; additional worker harnesses beyond the CTO; local AI lane (enabled per hardware profile, ADR 0005); sanctioned cross-use registry and API-key gateway; off-box backup; vault sync; browser VM image; reference board page.
- **In the core:** the plan/apply engine built on compare-before-write atomic primitives; storage layout detection and checkpoint/snapshot engine; exec audit log (executables, not arguments) as a forensic record; systemd credential staging; pinned, digest-checked installs with vendor self-updaters off and cool-downs; hardened harness profiles (locked configs, AppArmor profile for bubblewrap); documented usage-limit adapters and pace arithmetic; the board data contract; the job contract files; refusing to delete unpushed work; leaving public SSH open until a separate, verified switch with a watchdog.

## Reasons

- Mixing owner-specific configuration into public code breaks reproducibility, prevents clean open-source distribution, and creates accidental data-exposure risks.
- Keeping the overlay as a separate git checkout allows owners to version their own rules, skills, and overlay choices independently of signed Ötüken releases.

## Disagreement, and how it was decided

- **Exec audit log:** kept in the core and on by default because it has low overhead and provides post-incident forensics (while never acting as an isolation boundary).
- **Overlay form:** a git checkout at `/etc/otuken/overlay` rather than a single `.env` file, because the overlay also carries custom skills, rules, and templates.

## Rejected

- Keeping owner-specific values in the public repository behind flags or examples filled with real host data.
- Committing private values and attempting to scrub git history later.
- Importing private-prototype history into the public repository; the public repository starts with a fresh history.

## Open risks

- Maintaining a private overlay repository requires keeping it compatible with Ötüken's overlay schema across updates.
