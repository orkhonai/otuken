<!-- SPDX-License-Identifier: MIT -->
# ADR 0011 · The vault: a self-improving LLM wiki

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Accepted, 2026-11-21. **Topic:** Agent knowledge vault and sync rules.

## Decision

- **A separate git vault** for the agents, next to the owner's personal vault, not inside it. The server copy is canonical.

  ```
  /var/lib/otuken/vault/
    SCHEMA.md         page shapes and merge rules; changed only by an owner-approved change
    index.md          generated from frontmatter by code, never by a model
    log.md            append-only, one line per merge, written by the merge step
    wiki/             canonical pages
      projects/<id>/  project-scoped pages
      shared/         tools, vendors, concepts, runbooks, decisions
      contradictions/ conflicts waiting for resolution
      archive/        superseded pages, never silently deleted
    drafts/<job>/     the only folder agents write to, and only through the guard
    quarantine/       proposals the checks rejected, for the owner's digest
    outbox/owner/     pages proposed for the owner's personal vault
  /var/lib/otuken/evidence/
                      immutable source captures (text, URL, fetch time, sha256),
                      marked untrusted, outside the synced vault
  ```

  The schema file is not called `AGENTS.md`, so no harness loads it as instructions.
- **Write path: draft → checks → canonical.**
  1. An agent calls `vault.propose` (MCP or CLI) with text, a target page and sources. The guard writes the draft and fills the provenance itself from what it knows (job, project, harness and version, model, time); the agent cannot set those fields.
  2. A deterministic merge step, code and not a model, checks the schema, required provenance, links, secrets, size, allowed paths and file types. It refuses remote images, raw HTML, iframes, URLs with query strings, and anything that touches `SCHEMA.md` or `.obsidian/`. It looks for duplicates by title, alias and a nearest-neighbour search; a near match becomes an update of the existing page, not a new page.
  3. A tool-less model call with structured output (no shell, no network, no commit rights) checks whether each claim appears in its cited source and whether it contradicts a canonical page. Its patch is validated again by the deterministic step.
  4. Auto-merge happens only when every source is at least machine-confirmed and nothing was flagged; everything else goes to `quarantine/` and a daily digest. A contradiction goes to `contradictions/` and marks both pages `disputed`. Pages agents will act on (`kind: runbook`) need the owner's approval. Every merge is a commit with trailers naming the draft, the job and the sources, and it regenerates `index.md` and `log.md`.
- **Provenance**, compatible with Google's Open Knowledge Format:

  ```yaml
  id: shared/tools/incus-btrfs-pool
  kind: fact | howto | decision | runbook | reference
  scope: global | project:<id>
  status: draft | stable | disputed | stale | superseded
  generated: {by: <harness>/<version>, model: <model>, job: <id>, at: <RFC 3339 time>}
  verified: [{by: human:owner, at: <time>}]
  sources: [{id: s1, evidence: <sha256>, url: <url>, read: <date>, origin: web | owner | agent | repo}]
  trust: untrusted | machine | human   # set by the merge step: the lowest trust among the sources
  supersedes: [<ids>]
  stale_after: <date>
  ```

  No numeric confidence scores.
- **Rot and duplication.** Deterministic lint runs daily: broken links and wikilinks, orphan pages, pages without sources, pages past `stale_after` (marked stale, never deleted), two canonical pages giving different values for the same key (marked disputed). Model-assisted near-duplicate and contradiction proposals run weekly and arrive as drafts. `stale_after` by kind: about 30 days for fast-moving tool and price facts, 180 for infrastructure patterns, 365 for decisions. Retrieval returns stable pages first and shows stale and disputed pages with their status. A contradicted fact is marked superseded, not deleted.
- **Prompt-injection containment.**
  1. Nothing in the vault is an instruction. Rules live only in `AGENTS.md` and skills, outside the vault's write path. A page that should become a rule is filed as a proposed `AGENTS.md` or skill change, which the owner approves like any policy edit.
  2. Trust is fixed at write time by origin and can only go down. Summarising does not launder it; only a human verification raises it.
  3. Rule of Two per agent: the merge step reads untrusted text and writes the vault, so it has no secrets and no network; the CTO reads untrusted-tier pages only through tool-less calls.
  4. Vault text given to an agent is wrapped and marked as data, with its provenance.
  5. Least knowledge: a worker reads shared pages and its own project's pages, never another project's and never the owner's personal vault unless its job grants it. The pages a job needs are copied into its project at job start as a snapshot, so a later edit cannot change a running job, and a poisoned page inside a project can come back only as a draft.
  6. No exfiltration through the owner's apps: no remote images, HTML or query-string URLs in agent pages; agents never write `.obsidian/`, which is excluded from sync; raw captures stay outside the synced vault.
  7. Everything is reversible: the merge step can list and revert every page derived from one source, and it alerts on unusual write rates.
- **Two-way sync with the owner's own vault:** two-way at the transport level, one-way in authority. The owner's vault is mirrored to the server, read-only for agents. Agents propose into `outbox/owner/`, and the owner moves what they want. Owner edits to agent pages come back as authoritative changes (`edited_by: owner`). Deletions travel as staged tombstones with a grace period; conflicts keep both versions and the common base, and the shared copy advances only after the owner resolves them. One sync service per folder. Git on the server is the store; the transport is the owner's choice and off by default: git (desktop), Syncthing (desktop; Receive Only for the mirrored personal vault), or Obsidian's official headless client (with a paid Obsidian Sync plan; for phones).

## Reasons

- Karpathy's LLM wiki: raw sources that are "immutable — the LLM reads from them but never modifies them", a wiki that "The LLM owns… entirely", a schema file, `index.md`, an append-only `log.md`, and "lint" passes for "contradictions between pages, stale claims that newer sources have superseded, orphan pages with no inbound links"; it deliberately has no provenance schema ([LLM wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), read 2026-11-21).
- "Keep your personal vault clean and create a messy vault for your agents" (Steph Ango of Obsidian, [post](https://x.com/kepano/status/2039831289533227446), read 2026-11-21 through a mirror).
- The Open Knowledge Format already defines the provenance fields and reserves `index.md` and `log.md` ([OKF specification](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md), read 2026-11-21).
- Isolation patterns: once an agent "has ingested untrusted input, it must be constrained so that it is impossible for that input to trigger any consequential actions" ([Beurer-Kellner et al.](https://arxiv.org/abs/2506.08837)); CaMeL's separation of control and data ([CaMeL](https://arxiv.org/abs/2503.18813)); Meta's Rule of Two ([Meta](https://ai.meta.com/blog/practical-ai-agent-security/)); spotlighting cut attack success from over 50 % to under 2 % on the models tested ([Hines et al.](https://arxiv.org/abs/2403.14720)); OWASP asks to "Prevent automatic re-ingestion of an agent's own generated outputs into trusted memory" ([OWASP Agentic Top 10](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)); all read 2026-11-21.
- Poisoning works at very low rates: over 80 % attack success with under 0.1 % poisoned entries ([AgentPoison](https://arxiv.org/abs/2407.12784), read 2026-11-21), so provenance and reversal matter more than detection.
- Claude Code's own memory files "aren't enforced configuration" ([memory](https://code.claude.com/docs/en/memory), read 2026-11-21).
- Obsidian "cannot reliably restrict plugins" ([plugin security](https://obsidian.md/help/plugin-security), read 2026-11-21).
- A production LLM-wiki skill dropped confidence scores as "false precision with no calibration behind it" ([karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki), read 2026-11-21).
- Link checks with lychee and `--include-wikilinks` ([lychee](https://github.com/lycheeverse/lychee), read 2026-11-21); contradicted facts marked invalid rather than deleted, as in Graphiti ([Graphiti](https://arxiv.org/html/2501.13956), read 2026-11-21).
- Sync: Obsidian advises "Avoid syncing the same vault across multiple services… to prevent data conflicts or corruption" ([sync your notes](https://obsidian.md/help/sync-notes)); Syncthing never merges and keeps `.sync-conflict-` copies ([syncing](https://docs.syncthing.net/users/syncing.html)) and offers Receive Only folders ([folder types](https://docs.syncthing.net/users/foldertypes.html)); Obsidian's headless client `ob` is in open beta, needs Node 22 or newer and has `bidirectional`, `pull-only` and `mirror-remote` modes ([Headless Sync](https://obsidian.md/help/sync/headless)); obsidian-git's mobile support is "highly unstable" ([obsidian-git](https://github.com/Vinzent03/obsidian-git)); a Syncthing forum thread reports deletions with a Syncthing folder inside iCloud Drive and advises to "move your Syncthing folder(s) outside of the iCloud folder path" ([forum](https://forum.syncthing.net/t/problem-with-syncthing-and-icloud/21914), a community thread); all read 2026-11-21.

## Disagreement, and how it was decided

- **Pages as instructions.** Kept instructions out of the vault so knowledge and executable rules stay separate; promoting a learned pattern into a rule goes through an owner-approved `AGENTS.md` or skill proposal.
- **The owner's notes.** Kept in a separate vault rather than inside the agent vault; git remains the server-side store and one of the sync transports.
- **Raw sources.** Kept outside the synced vault under `/var/lib/otuken/evidence/` so raw captures cannot trigger remote fetches in the owner's desktop apps.
- **Lint cadence:** daily for cheap deterministic checks, weekly for model-assisted checks.

## Rejected

- Agents writing canonical pages directly.
- A vector database as the store of record; the Markdown files and git history are the truth, and an index is derived.
- Numeric confidence scores as a gate.
- Two sync services on one folder.

## Open risks

- The merge step's second check needs a model; until a login or local model is configured, drafts wait.
- The conflict behaviour of Obsidian's headless modes is not documented in detail; every transport is tested on a copy before it replaces a live sync.
- Deployments that combine sync providers should test conflicts and retain a migration plan.

## Verification tests

T11 (hostile-text fixtures cannot change grants or canonical policy) and T12 (a two-way sync drill on a copy: conflicts, deletes, round trips).
