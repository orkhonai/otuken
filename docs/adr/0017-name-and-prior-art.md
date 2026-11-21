<!-- SPDX-License-Identifier: MIT -->
# ADR 0017 · Name, trademarks and prior art

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Accepted, 2026-11-21. **Topic:** Product naming, trademark checks, and prior art.

## Decision

- **Product name:** display name **Ötüken**, ASCII slug and CLI name **`otuken`**, control CLI **`otukenctl`**, public GitHub repository **`orkhonai/otuken`**, project website **[otuken.tech](https://otuken.tech)**.
- **Name story:** Ötüken was the Göktürk khagans' home ground; the Kül Tigin inscription says the realm is held from Ötüken; the Orkhon river flows through it — Ötüken, by Orkhon.
- **Trademark hygiene:** the name contains no "Ubuntu" and nothing ending in "-buntu"; no "Omarchy", "Oma-" or "-archy"; no vendor or model mark (Claude, Anthropic, Codex, GPT, Gemini, Antigravity, Cursor, Copilot); and it is not plain "agent", which is Cursor CLI's binary name.
- **Attribution in docs:** the README says "for an Ubuntu 24.04 LTS server" in plain text, states that Ötüken is "inspired by Omarchy" without implying endorsement, and names third-party coding agents without implying endorsement.
- **Prior art** is credited in the README and in the table below. AgentVerse OS is the closest prior art.

## Name availability and trademark checks (2026-11-21)

| Check | Date | Source | Result |
| --- | --- | --- | --- |
| npm package `otuken` | 2026-11-21 | `https://registry.npmjs.org/otuken` and `https://registry.npmjs.org/-/v1/search?text=otuken` | Available (HTTP 404; search returns 0 packages) |
| npm package `otukenctl` | 2026-11-21 | `https://registry.npmjs.org/otukenctl` | Available (HTTP 404) |
| PyPI package `otuken` | 2026-11-21 | `https://pypi.org/pypi/otuken/json` | Available (HTTP 404) |
| PyPI package `otukenctl` | 2026-11-21 | `https://pypi.org/pypi/otukenctl/json` | Available (HTTP 404) |
| GitHub repositories (`otuken`, `otukenctl`) | 2026-11-21 | `https://api.github.com/search/repositories?q=otuken+in:name`, `https://api.github.com/search/repositories?q=otukenctl`, `https://api.github.com/repos/orkhonai/otuken` | 20 small repositories match `otuken` in name, all at 0 stars (no notable project); 0 repositories match `otukenctl`; `orkhonai/otuken` is available (HTTP 404 pre-publication); GitHub user `Otuken` exists |
| USPTO trademarks (Classes 9 & 42) | 2026-11-21 | Web search of USPTO records, Justia Trademarks (`trademarks.justia.com`), Trademarkia (`trademarkia.com`) for `otuken` and `ötüken` | No active or pending USPTO registrations surfaced in Classes 9 or 42; direct interactive clearance in USPTO Trademark Search (`tmsearch.uspto.gov`) recommended before filing or v1.0 |
| EUIPO / TMview & WIPO Global Brand Database (Classes 9 & 42) | 2026-11-21 | Web search of EUIPO (`euipo.europa.eu`), TMview (`tmdn.org/tmview`), and WIPO Global Brand Database (`branddb.wipo.int`) references for `otuken` and `ötüken` | No EUIPO registrations surfaced in public web indexes; dynamic TMview and WIPO Global Brand Database portals require interactive query and should be checked directly (alongside TÜRKPATENT) before v1.0 |
| Existing third-party uses of the historical name | 2026-11-21 | Public web search | **Ötüken Neşriyat** (`otuken.com.tr`): Turkish book publisher founded 1964 (Nice Class 16, printed matter/books; unrelated class). **Ötüken AI / Ötüken Us** (`otukenai.com`, `otukenus.com`): independent web initiatives describing sovereign-AI / modular software concepts (0 matching GitHub repositories found under `otukenai`/`otukenus`; noted as an open naming risk to review directly in trademark databases before v1.0) |
| Project domain | 2026-11-21 | Owner registration | `otuken.tech` registered and held by the project owner |

## Reasons

- Canonical: "You cannot use the Trademarks in software titles"; software "for use with or on Ubuntu" may say so but must avoid "any implication of endorsement"; permission is needed for "any mark ending with the letters UBUNTU or BUNTU" and for the mark in a domain name ([Canonical IP policy](https://canonical.com/legal/intellectual-property-policy), read 2026-11-21).
- OMARCHY is a registered US trademark: registration 8250209, Class 9, registered 2026-05-12, owned by the Omacom Foundation ([USPTO TSDR](https://tsdr.uspto.gov/statusview/sn99322411), [foundation news](https://omarchy.org/news/2026/08/omacom-foundation-launches-with-8-million/), read 2026-11-21). Omarchy also has its own written plan for a headless "Omarchy Server" ([plans/server.md](https://raw.githubusercontent.com/omacom/omarchy/quattro/plans/server.md), read 2026-11-21).
- Vendors: you "can't use the Claude Code or Anthropic names or logos as part of your own product, feature, or company name" ([Claude Code legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)); OpenAI: "we do not permit our GPT brand to be used in app, product, developer or company names" and "We do not permit model names in app titles" ([OpenAI brand](https://openai.com/brand/)); Google: "Don't incorporate Google Brand Features into your own product names" ([Google trademark guidelines](https://partnermarketinghub.withgoogle.com/brands/google/trademarks-and-terms/trademark-guidelines-for-proper-usage/)); all read 2026-11-21.
- "Trademarks don't have to be identical to be confusingly similar" ([USPTO](https://www.uspto.gov/trademarks/search/likelihood-confusion)); the official search portals ([EUIPO](https://www.euipo.europa.eu/en/trade-marks/before-applying/availability), [WIPO Global Brand Database](https://www.wipo.int/en/web/global-brand-database)); "npm processes Trademark claims under GitHub's Trademark Policy" ([npm disputes](https://docs.npmjs.com/policies/disputes)); all read 2026-11-21.
- Names already in use nearby: AgentVerse OS, agentOS, AgentBox and agbox, Sprites, Conductor, Sculptor, Hermes ([AgentVerse OS](https://github.com/agentverse-os/AgentVerse-OS), [AgentBox](https://github.com/madarco/agentbox), [agbox](https://github.com/antomanc/agbox), [Sprites](https://fly.io/sprites), [Conductor](https://www.conductor.build/), [Sculptor](https://github.com/imbue-ai/sculptor), [Hermes Agent](https://github.com/NousResearch/hermes-agent), read 2026-11-21).

**Prior art** (all links read 2026-11-21):

| Project | Licence | What it is | What Ötüken takes, or how it differs | Read |
| --- | --- | --- | --- | --- |
| [AgentVerse OS](https://github.com/agentverse-os/AgentVerse-OS) | Apache-2.0 | "a personal cloud operating system for a developer and their AI agents": one command on clean Ubuntu, isolated workspaces, several coding agents, access over Tailscale only; an alpha that "lives on a single test box" | The closest prior art. It is a browser desktop with an app store; Ötüken differs on the guard-bounded CTO, native-agent subscription handling, the vault and the board contract | 2026-11-21 |
| [Omarchy](https://github.com/omacom/omarchy), [Omakub](https://github.com/omacom/omakub) | MIT | a curated Arch desktop installed from an ISO; the retired Ubuntu desktop setup | the repository shape, release, update and CI discipline (ADR 0001); Omakub's migrations kept no record of what ran | 2026-11-21 |
| [Paperclip](https://github.com/paperclipai/paperclip) | MIT | "org charts, budgets, governance, goal alignment, and agent coordination", with roles such as CEO and CTO over coding agents and agents that "wake for assigned work" | the closest prior art for the CTO and wake-up layer; it does not own the box, isolate projects or hold the host boundary | 2026-11-21 |
| [OpenHands](https://github.com/OpenHands/OpenHands) | MIT | a self-hosted control centre for several coding agents, with Docker sandboxes | overlaps on orchestration; it does not own the box | 2026-11-21 |
| [OpenClaw](https://github.com/openclaw/openclaw) | MIT | a personal agent on your own hardware | its exposed instances and malicious skills are on the threat list (ADR 0013) | 2026-11-21 |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | MIT | a self-improving agent with memory, skills, cron and gateways | a CTO candidate; its skill-write approval informs ADR 0011 | 2026-11-21 |
| [Coolify](https://github.com/coollabsio/coolify), [CasaOS](https://github.com/IceWhaleTech/CasaOS), [Dokku](https://github.com/dokku/dokku) | Apache-2.0, Apache-2.0, MIT | one-line self-hosting installers | install ergonomics; they run apps, not agents | 2026-11-21 |
| [Coder](https://github.com/coder/coder) | AGPL-3.0 | self-hosted development environments | versioned templates behind admission; its licence prevents copying | 2026-11-21 |
| [Container Use](https://github.com/dagger/container-use), [Claude Squad](https://github.com/smtg-ai/claude-squad) | Apache-2.0, AGPL-3.0 | one container or worktree per agent | the per-task isolation idea | 2026-11-21 |
| [Docker Sandboxes](https://docs.docker.com/ai/sandboxes/security/) | proprietary, free | one microVM per agent on a Docker host | an escalation option, not the default (ADR 0008) | 2026-11-21 |
| [E2B](https://github.com/e2b-dev/E2B), [Microsandbox](https://github.com/superradcompany/microsandbox), [Kata Containers](https://github.com/kata-containers/kata-containers), [Daytona](https://github.com/daytonaio/daytona) | Apache-2.0 (E2B, Microsandbox, Kata) | microVM or cloud sandboxes | a later tier, if ever | 2026-11-21 |
| [bb](https://github.com/get-bb/bb), [Vibe Kanban](https://github.com/BloopAI/vibe-kanban) | MIT, Apache-2.0 | control surfaces for agent threads | bb stays an optional module | 2026-11-21 |
| [exe.dev](https://exe.dev/), [Fly.io Sprites](https://fly.io/sprites) | proprietary | hosted computers for agents | hosted only; Ötüken runs on the owner's box | 2026-11-21 |
| [Karpathy's LLM wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) | — | the pattern for an agent-maintained wiki | ADR 0011 | 2026-11-21 |

No existing MIT-licensed project was found that combines a stock-Ubuntu server layer, a guard-bounded swappable CTO, per-project KVM VMs, a provenance-tracked vault, and a wall-board data contract.

## Disagreement

None that changes the design.

## Rejected

- Any name containing Ubuntu, Omarchy or a vendor or model mark (the policies above).
- Plain "agent", or any name that collides with a harness's binary.
- Announcing a name without recording package, GitHub, and trademark checks.

## Open risks

- AgentVerse OS overlaps in problem space; clarifying differentiation (or collaboration) should be revisited before v1.0.
- Dynamic official trademark portals (USPTO Trademark Search, EUIPO TMview, WIPO Global Brand Database, and TÜRKPATENT) should be queried interactively before v1.0, especially to confirm whether `Ötüken AI` / `Ötüken Us` holds any registered software trademark in Classes 9 or 42.
