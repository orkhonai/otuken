<!-- SPDX-License-Identifier: MIT -->
# ADR 0016 · Licence, NOTICE and what the product may redistribute

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Accepted, 2026-11-21. **Topic:** Licence, NOTICE, and redistribution boundaries.

## Decision

- **MIT** for Ötüken's own code. `LICENSE` holds the MIT text, and every file carries an SPDX header or `REUSE.toml` annotation (REUSE 3.3).
- **`NOTICE`** holds the Ötüken contributors copyright line, a pointer to the two lists below, and the statement that signing in to a third-party service is between the owner and that service: the project grants no rights to any vendor's accounts or services.
- **`THIRD_PARTY_NOTICES.md`** lists only code copied into the repository, with its licence text. If an Omarchy script is copied later, its MIT notice comes with it; if code is copied from an Apache-2.0 project that has a NOTICE file, that NOTICE is carried and changes are marked.
- **`docs/THIRD-PARTY-TOOLS.md`,** generated from the signed catalog, lists every tool the installer downloads from its vendor at the owner's choice: vendor, official URL, licence or terms link, and the date checked. These tools are not in Ötüken's distribution, so they are not in `LICENSE` or `NOTICE`.
- **Never copied into the repository:** AGPL code (Claude Squad, Coder, Arrakis), FSL code (Crush), code without a licence.
- **Never published:** an image or tarball with proprietary agents preinstalled. The installer fetches each vendor's own installer, unmodified, on the owner's box, at the owner's explicit choice. Launchers pass the owner's chosen credential and block none of a harness's built-in sign-in methods.
- **The README states the supported mode:** one owner, the owner's own accounts, the owner's own box. Each subscription runs inside its own native agent (Claude in Claude Code, ChatGPT in Codex, and so on), with no subscription proxy. Hosting it for other people changes which vendor terms apply.
- **No pre-publication vendor-permission gate:** Ötüken does not redistribute proprietary agent binaries and runs each subscription solely inside the vendor's unmodified native client on the owner's own machine; publishing the MIT-licensed repository is not blocked on seeking vendor pre-approval.

## Reasons

- MIT's one condition: "The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software" ([OSI](https://opensource.org/license/mit), read 2026-11-21). Anyone may use, change, sell or host the product, including as a paid service. Compared with Apache-2.0 it has no express patent licence (§3) and no NOTICE mechanism (§4(d)) ([Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0), read 2026-11-21), and neither licence grants trademark rights. Omarchy is MIT ([Omarchy LICENSE](https://raw.githubusercontent.com/omacom/omarchy/quattro/LICENSE), read 2026-11-21).
- "Do not add to LICENSE and NOTICE dependencies which are not in the distribution" ([ASF licensing how-to](https://infra.apache.org/licensing-howto.html), read 2026-11-21).
- SPDX headers per REUSE ([REUSE 3.3](https://reuse.software/spec-3.3/), read 2026-11-21).
- Claude Code: "preinstalling or running Claude Code in your products or services (e.g. in hosted sandboxes or other agent infrastructure) requires agreeing to our Commercial Terms of Service"; "Claude Code must be installed and run as published by Anthropic"; customers "may not remove, disable, or restrict any authentication method built into it"; and the same page does not prevent "an end user from signing in to the unmodified Claude Code binary with their own Claude subscription, including where a platform hosts Claude Code" ([legal and compliance](https://code.claude.com/docs/en/legal-and-compliance), read 2026-11-21). Copilot CLI may be redistributed only "in unmodified form" and "solely as part of an application or service that provides material functionality beyond the Software itself" ([Copilot CLI licence](https://raw.githubusercontent.com/github/copilot-cli/HEAD/LICENSE.md), read 2026-11-21); Cursor's terms forbid reproducing the service ([Cursor terms](https://cursor.com/terms-of-service), read 2026-11-21).
- Licences of tools in the planned catalog, from each project's LICENSE or terms (read 2026-11-21): Claude Code, Antigravity CLI, Cursor CLI, Copilot CLI, Amp, Factory Droid, Junie and Kiro are proprietary; Codex, Cline, Mistral Vibe, Goose and Qwen Code are Apache-2.0; OpenCode, Pi, oh-my-pi, Hermes Agent and Kilo Code are MIT; Crush is FSL-1.1-MIT. Infrastructure: Incus Apache-2.0, the Tailscale client BSD-3-Clause, llama.cpp and Ollama MIT, LiteLLM MIT except its enterprise directory, restic BSD-2-Clause, Syncthing MPL-2.0, and bb MIT ([bb LICENSE](https://raw.githubusercontent.com/get-bb/bb/HEAD/LICENSE), read 2026-11-21). `obsidian-headless` is published as `UNLICENSED` ([npm](https://registry.npmjs.org/obsidian-headless/latest), read 2026-11-21), so it is only ever fetched at the owner's choice.

## Disagreement, and how it was decided

- **What NOTICE lists.** Following the ASF rule, `NOTICE` covers only copied/redistributed code and points to `docs/THIRD-PARTY-TOOLS.md` for tools fetched at install time.
- **Apache-2.0 vs. MIT.** MIT was chosen for simplicity and parity with Omarchy.

## Rejected

- AGPL: its network clause would deter the self-hosting users this product is for.
- Listing downloaded tools in `LICENSE` or `NOTICE` as if Ötüken redistributed them.

## Open risks

- Vendor terms change; the catalog's dates show when each was last checked.
