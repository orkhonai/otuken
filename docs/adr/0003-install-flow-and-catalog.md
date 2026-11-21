<!-- SPDX-License-Identifier: MIT -->
# ADR 0003 · The install flow and the worker catalog

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Accepted, 2026-11-21. **Topic:** Install flow and worker catalog.

## Decision

The flow, as the owner sees it. Every step has a plain terminal fallback, so the install never depends on a model answering.

1. **Base** (deterministic, no model): ADR 0001. Result: the guard, snapshots, Incus, a firewall with SSH open, the board endpoint, an empty HQ and vault, and the CTO's seat VM.
2. **CTO harness.** Only harnesses that pass the CTO bar for their pinned version can be chosen (ADR 0007); the others show as experimental. The installer puts the pinned version into the seat and runs that harness's own login. From here the CTO talks to the owner; the wizard keeps running underneath.
3. **Workers.** The catalog's twelve, each shown with its licence, the subscriptions it can use natively, its headless mode, its test status and its popularity evidence. Unticked agents are not installed; `otuken add <harness>` adds any of them later.
4. **Subscriptions and logins** (ADR 0004). The owner ticks what they pay for. Each subscription runs inside its own native agent (Claude in Claude Code, ChatGPT in Codex, and so on) using the provider's own login flow inside the VM where that agent runs, relayed to the owner's screen as a URL and code or a QR code for the phone. Skipping is allowed; enrollment resumes later without re-running the base.
5. **Local AI lane** (ADR 0005), enabled per hardware profile (GPU home server, measured CPU profile, or private-network model server).
6. **Optional cross-use module** (ADR 0004), off by default, with a terms screen per provider.
7. **Optional modules:** remote access (Tailscale, WireGuard or none), off-box backup, vault sync, the control-app integration (bb), exec audit.
8. **Board.** The contract is always on, on loopback; publishing it on the private network and a minimal reference page are options (ADR 0012).
9. **Smoke test.** Each installed worker does one tiny real job in a throwaway sandbox (create a file, run a test, commit to a scratch branch), and the board must show the job, the worker, its account and a fresh usage-limit reading where documented. Setup reports green only after that.

**The twelve on the first screen.** The list is catalog data, not code. "Supported" means the role test passed on the pinned version; installing is not support.

| # | Agent | Licence | Native subscription | Headless entry | Popularity evidence (2026) |
| --- | --- | --- | --- | --- | --- |
| 1 | Claude Code | proprietary | Anthropic plans | `claude -p` | 65.5 % (SO); 39 % at work (JB); 156.5k stars; 21.7 M npm downloads a week |
| 2 | Codex CLI | Apache-2.0 | ChatGPT plans | `codex exec` | 29.5 % (SO); 16 % (JB); 136.0k stars; 27.5 M npm a week |
| 3 | GitHub Copilot CLI | proprietary | Copilot plans | `copilot -p` | Copilot 58.7 % (SO); 1.87 M npm a week |
| 4 | Cursor CLI | proprietary | Cursor plans | `agent -p` | Cursor 25.5 % (SO); 12 % (JB) |
| 5 | Antigravity CLI | proprietary | Google AI Pro and Ultra (owner-run only on consumer plans, ADR 0004) | `agy -p` | 16.0 % (SO); Google's successor to Gemini CLI for consumer plans |
| 6 | OpenCode | MIT | Copilot and ChatGPT (sanctioned), API keys | `opencode run --standalone` | 13.6 % (SO); 7 % (JB); 228.3k stars |
| 7 | Pi | MIT | ChatGPT (sanctioned), API keys | `pi -p`, `--mode rpc` | 4.4 % (SO); #4 CLI agent by tokens on OpenRouter; 123.1k stars; 6.6 M npm a week |
| 8 | oh-my-pi | MIT | as Pi | `omp -p`, `omp acp` | #7 on OpenRouter; 39.6k stars |
| 9 | Hermes Agent | MIT | ChatGPT (sanctioned), API keys | `hermes -z`, `hermes acp` | #1 on OpenRouter; 10.2 % in SO's orchestration-tools question; 265.0k stars |
| 10 | Kilo Code CLI | MIT | ChatGPT (sanctioned), SuperGrok (candidate, ADR 0004), API keys | `kilo run --auto` | #3 on OpenRouter; 3.2 % (SO); 28.1k stars |
| 11 | Cline CLI | Apache-2.0 | GLM plan, API keys | `cline "…"` | 4.5 % (SO); 71.8k stars |
| 12 | Mistral Vibe | Apache-2.0 | Mistral plans | `vibe --prompt … --auto-approve` | 3.2 % (SO); 231.5k PyPI downloads a week |

SO is the Stack Overflow Developer Survey 2026, "Have you used any of the following coding agents or assistants in the past year?" ([survey data](https://survey.stackoverflow.co/2026/ai/data), [question page](https://survey.stackoverflow.co/2026/ai/data/ai-code-agent), [results post](https://stackoverflow.blog/2026/10/06/the-results-of-the-2026-developer-survey-are-here/), read 2026-11-21). JB is JetBrains' AI coding agent adoption study, May–July 2026 ([JetBrains Research](https://blog.jetbrains.com/research/2026/08/ai-coding-agent-adoption-2026/), read 2026-11-21). OpenRouter ranks one day of usage through 2026-11-20 and counts only apps routed through it ([OpenRouter](https://openrouter.ai/apps/category/coding/cli-agent), read 2026-11-21). Stars and downloads were read from `api.github.com/repos/<repo>`, `api.npmjs.org/downloads/point/last-week/<package>` and `pypistats.org/api/packages/<package>/recent` on 2026-11-21. Survey shares cover each product's surfaces, not only its CLI, and npm counts include CI installs and undercount tools installed by curl. Headless entries are from each vendor's documentation.

**One screen further:** Grok Build ([xAI](https://x.ai/news/grok-build-cli), read 2026-11-21), Kimi Code CLI (interactive use only on its plan), Qwen Code, Goose, Aider, Gemini CLI (API keys only), Junie CLI, Kiro CLI, Amp, Factory Droid, Crush (FSL, not open source). **Not offered:** Roo Code (shut down on 2026-05-15), Continue and the OpenHands CLI (no longer maintained) ([Roo Code](https://github.com/RooCodeInc/Roo-Code), [Continue](https://github.com/continuedev/continue), [OpenHands CLI](https://github.com/OpenHands/OpenHands-CLI), read 2026-11-21).

## Reasons

- The rule for the twelve: the six primary CTO candidate harnesses, plus OpenCode, then the next five by survey share and usage, preferring a native agent for each subscription an owner is likely to hold.
- Gemini CLI is not the Google consumer worker: "On June 18, 2026, Gemini CLI and Gemini Code Assist IDE extensions will stop serving requests for Google AI Pro and Ultra"; it remains for paid API keys ([Google Developers Blog](https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/), read 2026-11-21).
- OpenCode runs `--standalone`, because by default "OpenCode discovers or starts one shared background server for your user account", which would join projects together ([OpenCode CLI](https://opencode.ai/docs/cli/), read 2026-11-21).
- The smoke test and the terminal fallback make "installed" mean "works".

## Disagreement, and how it was decided

- Replacing Kilo Code and Mistral Vibe with Aider and goose was weighed and rejected: Aider has 2.1 % in the same survey against 3.2 % each for Kilo and Vibe, and Aider's last PyPI release was 0.86.2 of 2026-02-12 ([PyPI](https://pypi.org/pypi/aider-chat/json), read 2026-11-21); Kilo is #3 by tokens on OpenRouter; Vibe is the native agent for Mistral plans. Aider and goose stay available one screen further in the catalog.

## Rejected

- A twelve-agent install as the only path; every agent stays one command away.
- Calling an agent supported because its binary installs.

## Open risks

- Survey shares measure products, not CLIs, and popularity moves monthly; the catalog is reviewed at every release.
- Vendors change headless flags weekly; the adapter tests in ADR 0007 are what counts.
