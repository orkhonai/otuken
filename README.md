<!-- SPDX-License-Identifier: MIT -->
<p align="center">
  <img src="logo.svg" alt="Ötüken" width="520">
</p>

# Ötüken

**Pre-alpha (`0.0.1-prealpha.1`) — not ready for production until v0.1 passes its full test suite.**
Today, Milestone 1 ships the signed installer, checkpoint/rollback engine,
local guard prototype, and offline Incus CI harness. The CTO seat VM,
per-project KVM VMs, guest identity and egress controls, native harness
logins, remote access, the vault, the wall-board service, and the local AI
lane are planned for later milestones. No signed release or release key is
published yet.

Ötüken is an MIT-licensed, agent-native layer for an Ubuntu 24.04 LTS server or
home server you own. The target architecture centres on a planned
guard-bounded, swappable CTO agent in its own VM, one isolated VM per coding
project, and a deterministic host guard that holds policy and state. In that
design, each subscription will run inside its own native agent (Claude in
Claude Code, ChatGPT in Codex, and so on) with no subscription proxy, and a
planned local AI lane will let you run Ötüken as a home server, enabled per
hardware profile (GPU, measured CPU, or a local-network model server). The
supported deployment model is one owner, their own box, and their own accounts;
hosting it for other people changes which vendor terms apply.

Project site: [otuken.tech](https://otuken.tech) *(site coming online; nothing
in the installer or verification flow depends on it — the release-key
fingerprint will be published with each signed GitHub release and on the site
once live)*.

## Why Ötüken

Ötüken was the Göktürk khagans' home ground. The Kül Tigin inscription says the
realm is held from Ötüken, and the Orkhon river flows through it — Ötüken, by
Orkhon.

## Install from a signed release

Requires stock Ubuntu 24.04 LTS amd64 with systemd and cgroup v2 (`btrfs-progs`
on Btrfs hosts). The installer does not repartition, manage SSH, or change host
networking. When signed releases are published, verify the release key's SSH
fingerprint against the signed GitHub release (and [otuken.tech](https://otuken.tech)
once live), run the block below in Bash, and review the plan before typing
`apply`:

```bash
(
    set -euo pipefail
    umask 077
    read -rp 'Release asset directory (HTTPS): ' release_url
    read -rp 'Release version: ' version
    read -rp 'Independently verified SSH fingerprint: ' fingerprint
    [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([+-][A-Za-z0-9.+-]+)?$ ]]
    sudo -- /bin/bash -euo pipefail -s -- "$release_url" "$version" "$fingerprint" <<'BOOTSTRAP'
    umask 077
    release_url=$1 version=$2 fingerprint=$3
    work=$(mktemp -d /var/cache/otuken-bootstrap.XXXXXXXX)
    trap 'rm -r -- "$work"' EXIT
    cd -- "$work"
    archive="otuken-$version.tar.gz"
    for file in release.pub SHA256SUMS SHA256SUMS.sig "$archive"; do
        curl --proto '=https' --proto-redir '=https' --tlsv1.2 -fLSs \
            "${release_url%/}/$file" -o "$file"
    done
    read -r kind public_key _ < release.pub
    [[ $kind == ssh-ed25519 ]]
    printf '%s %s\n' "$kind" "$public_key" > pinned.pub
    [[ $(ssh-keygen -lf pinned.pub | awk 'NR == 1 {print $2}') == "$fingerprint" ]]
    printf 'otuken-release %s %s\n' "$kind" "$public_key" > allowed_signers
    ssh-keygen -Y verify -f allowed_signers -I otuken-release \
        -n otuken-release -s SHA256SUMS.sig < SHA256SUMS
    awk -v name="$archive" '$2 == name { n++; print } END { if (n != 1) exit 1 }' SHA256SUMS |
        sha256sum --check --strict
    tar --no-same-owner -xzf "$archive"
    loader="./otuken-$version/otuken"
    args=(--bundle "$PWD" --version "$version" --allowed-signers "$PWD/allowed_signers")
    result=0
    "$loader" install --plan "${args[@]}" > plan.txt || result=$?
    [[ $result == 0 || $result == 2 ]]
    cat plan.txt
    digest=$(awk '/^Plan digest: / { value=$3 } END { print value }' plan.txt)
    read -rp 'Type apply to accept this plan: ' confirmation </dev/tty
    [[ $confirmation == apply ]]
    "$loader" install --apply --plan-id "$digest" "${args[@]}"
BOOTSTRAP
)
```

## The Ötüken Manual

The manual lives in [`manual/`](manual/), alongside the full
[architecture design](docs/DESIGN.md) and [decision records](docs/adr/README.md).

- [Welcome to Ötüken](manual/01-welcome.md)
- [Install and Layout](manual/02-install.md)
- [Updates, Rollback, and Uninstall](manual/03-updates-and-rollback.md)
- [Guard and Security](manual/04-guard-and-security.md)
- [Roadmap and Architecture](manual/05-roadmap-and-design.md)
- [Contributing and Release Process](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)

## Inspiration and prior art

Ötüken is inspired by [Omarchy](https://github.com/omacom/omarchy) in its
repository shape, release discipline, and run-once migrations.
[AgentVerse OS](https://github.com/agentverse-os/AgentVerse-OS) is the closest
prior art. Naming third-party coding agents or operating systems describes
compatibility and prior art only and implies no endorsement.

## License

Ötüken is released under the [MIT License](LICENSE). See [`NOTICE`](NOTICE),
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md), and
[`docs/THIRD-PARTY-TOOLS.md`](docs/THIRD-PARTY-TOOLS.md).
