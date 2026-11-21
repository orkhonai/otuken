<!-- SPDX-License-Identifier: MIT -->
# ADR 0005 · The local AI lane (home-server support)

*One of the decision records of the Ötüken architecture; the same text is a section of [DESIGN.md](../DESIGN.md), which also holds the review summary, the disagreement table, and the verification test list.*

**Status:** Accepted, 2026-11-21 (updated for home-server hardware profiles). **Topic:** Local AI model lane.

## Decision

- **First-class planned lane, enabled per hardware profile.** Ötüken is designed so owners can run it not only on hosted servers, but also as a home server with local AI models. The local-model module stays in the core design and is configured according to the host's hardware profile:
  1. **GPU / unified-memory home server:** enables the on-box model server directly after hardware detection, sized to available VRAM/unified memory while preserving the host and VM memory reserves.
  2. **Private-network model server:** connects Ötüken to an OpenAI-compatible model server the owner already runs elsewhere on their local network (for example a workstation or dedicated GPU box), with its own explicit egress rule.
  3. **CPU-only server:** offered as an experimental, measured lane — enabled only after the installer benchmarks the candidate on the actual machine (`llama-bench`, two to four minutes) and prints tokens per second, time to first token on a representative agent prompt, RAM footprint and how many fewer project VMs that leaves, and the model weights' own licence. A coding subscription is never treated as a licence to any weights.
- **Runtime:** a pinned `llama-server` (MIT) bound to loopback under its own systemd user with an API key and bounded slots; harness timeouts raised to 30 minutes for the local profile; wired into harnesses that accept a custom OpenAI-compatible endpoint (Pi and omp, OpenCode, Hermes, Codex, Kilo, Cline); Claude Code only as a separate opt-in profile; Antigravity and Cursor CLI cannot use a custom local endpoint. The wizard recommends Pi for local work when prompts need to stay compact.
- **Plain expectations on CPU-only hardware:** before downloading weights onto a CPU-only machine, the wizard states clearly what the measured benchmark means (memory footprint, throughput, cold-prompt latency) so owners know when local inference fits triage, summaries, commit messages, and small edits versus when cloud subscriptions or a GPU home server are needed for heavy coding.

## Reasons

- Home-server users with GPUs, Apple Silicon / unified-memory machines, or dedicated local inference hosts need local AI as a native lane — both for offline/private work and for untrusted repositories where subscription logins are kept out of project VMs (ADR 0004).
- On a CPU-only x86_64 server with AVX2 and dual-channel memory bandwidth, gpt-oss-20b measured 23.2 tok/s generation and 67 tok/s prompt processing on an 8-core Zen 4 desktop ([OpenBenchmarking](https://mail.openbenchmarking.org/performance/test/pts/llama-cpp/0d11057dae615d0dbe31c8df288a8275bc721fd1), read 2026-11-21 through its mirror), falling as context grows ([ik_llama.cpp discussion 758](https://github.com/ikawrakow/ik_llama.cpp/discussions/758), read 2026-11-21). gpt-oss-120b's file alone is about 63 GB ([Hugging Face listing](https://huggingface.co/api/models/ggml-org/gpt-oss-120b-GGUF/tree/main), read 2026-11-21). Measuring on the target hardware avoids misleading estimates.
- First-token latency matters for agent prompts: at 40–60 tok/s on CPU, a cold 10k-token agent prompt takes minutes, longer than default stream timeouts of most harnesses (Codex and Pi 300 s, OpenCode a 5-minute header timeout) ([Claude Code environment variables](https://code.claude.com/docs/en/env-vars), [Codex advanced config](https://learn.chatgpt.com/docs/config-file/config-advanced), [OpenCode providers](https://opencode.ai/docs/providers/), [Pi models](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md), read 2026-11-21).
- Quality: on Terminal-Bench 2.1, the best local-size model listed scored 44.9 and gpt-oss-20b scored 13.9 ([Artificial Analysis](https://artificialanalysis.ai/evaluations/terminalbench-2-1), read 2026-11-21).
- Anthropic "doesn't support routing Claude Code to non-Claude models through any gateway" ([LLM gateway](https://code.claude.com/docs/en/llm-gateway), read 2026-11-21), hence the separate profile.
- `llama.cpp` serves an OpenAI-compatible API ([llama.cpp](https://github.com/ggml-org/llama.cpp), read 2026-11-21).
- Weight licences are separate from subscriptions.

## Disagreement, and how it was decided

- Refusing to download weights entirely (remote URL only) is too strict for home-server owners with GPUs or large unified memory, while silently enabling large models on small CPU-only servers hurts VM memory headroom and causes timeouts. Decided: keep the local AI lane in the design as a hardware-profile-driven module supporting GPU hosts, private-network endpoints, and measured CPU trials.

## Rejected

- vLLM on CPU-only AVX2 hosts: AVX2 has "limited features", and vLLM does not load GGUF files ([vLLM CPU](https://docs.vllm.ai/en/latest/getting_started/installation/cpu/), read 2026-11-21).
- LM Studio: its terms forbid redistribution ([LM Studio terms](https://lmstudio.ai/app-terms), read 2026-11-21).
- Ollama is acceptable only if its default 4,096-token context on CPU-only boxes is raised ([Ollama context length](https://docs.ollama.com/context-length), read 2026-11-21).

## Open risks

- CPU speed figures are hardware-dependent; the installer measures before recommending a model (T15).
- A loaded 20 GiB model shares host memory with project VMs (ADR 0008); hardware profiles must account for the combined memory budget.
- Exact home-server hardware profiles (GPU, unified-memory hosts, and model catalog defaults) are under active design.
