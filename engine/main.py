# SPDX-License-Identifier: MIT
"""Owner-facing installer commands."""

import argparse
import json
import os
import subprocess
import sys
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

# The loader runs Python in isolated mode, so imports come from this release.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import install
import release as releases
from common import Error, atomic_write, digest, encode, lock, require


def parser():
    cli = argparse.ArgumentParser(prog="otuken")
    cli.add_argument("--root", type=Path, help="private filesystem for unprivileged tests")
    actions = cli.add_subparsers(dest="command", required=True)
    for command in ("verify", "plan", "apply", "install", "update", "rollback", "uninstall"):
        description = ("Use the installed signer policy as the owner. Unprivileged verification "
                       "requires a private test --root before the subcommand.") if command == "verify" else None
        action = actions.add_parser(command, description=description)
        if command in {"verify", "plan", "apply", "install", "update"}:
            action.add_argument("--bundle", type=Path)
            action.add_argument("--version")
            action.add_argument("--allowed-signers", type=Path)
        if command in {"plan", "install", "update", "rollback", "uninstall"}:
            action.add_argument("--json", action="store_true")
        if command in {"plan", "apply", "install", "update"}:
            action.add_argument("--overlay", type=Path)
        if command in {"install", "update", "rollback", "uninstall"}:
            mode = action.add_mutually_exclusive_group()
            mode.add_argument("--plan", action="store_true")
            mode.add_argument("--apply", action="store_true")
            if command == "install":
                mode.add_argument("--yes", action="store_true")
        if command in {"apply", "install", "update", "rollback", "uninstall"}:
            action.add_argument("--plan-digest", "--plan-id", dest="plan_digest")
        if command == "update":
            action.add_argument("--channel", choices=("stable", "rc"), default="stable")
        if command == "uninstall":
            action.add_argument("--purge", action="store_true")
            action.add_argument("--confirm")
    actions.add_parser("status")
    actions.add_parser("recover")
    rotation = actions.add_parser("rotate-key")
    rotation.add_argument("--allowed-signers", type=Path, required=True)
    rotation.add_argument("--fingerprint", required=True, help="fingerprint verified out of band")
    actions.add_parser("self-check")
    migration = actions.add_parser("migrations")
    migration.add_argument("--pending", action="store_true", required=True)
    guard = actions.add_parser("guard")
    guard.add_argument("args", nargs=argparse.REMAINDER)
    return cli


def read_signer(path):
    return releases.signer(releases.read_limited(path, 4096))


def selected_signer(paths, args):
    mode = install.file_mode(paths.signers)
    if mode is not None:
        require(mode == 0o600, "Installed signer policy must have mode 0600")
        pinned = read_signer(paths.signers)
        if args.allowed_signers:
            require(read_signer(args.allowed_signers) == pinned, "Caller signer differs from the installed pin")
        return pinned
    require(args.command != "update" and not install.current(paths) and not paths.record()["highest"],
            "Installed signer pin is missing; owner must enroll it with rotate-key")
    require(args.allowed_signers, "First installation requires an independently trusted --allowed-signers file")
    return read_signer(args.allowed_signers)


def read_release(paths, args):
    require(args.bundle and args.version, "Supply --bundle and --version")
    signers, fingerprint = selected_signer(paths, args)
    result = releases.verify(*releases.release_paths(args.bundle, args.version), signers)
    channel = None
    if args.command == "update":
        filename = args.bundle / f"{args.channel}.json"
        channel = releases.channel(filename, filename.with_suffix(".json.sig"), signers, args.channel, result)
    return result, channel, signers, fingerprint


def rendered(plan, as_json):
    checksum = digest(encode(plan))
    if as_json:
        print(json.dumps({"plan": plan, "digest": checksum}, indent=2))
    else:
        print(f"{plan['operation']} on {plan['filesystem']}")
        if plan["filesystem"] == "ext4":
            print("Host snapshots are unavailable. Update uses a local export. "
                  "An off-box backup is recommended.")
        if plan.get("signer"):
            print(f"Release signer: {plan['signer']}")
        if not plan["changes"]:
            print("No changes")
        for change in plan["changes"]:
            print(" ".join(str(value) for key, value in change.items() if key != "diff"))
            if change.get("diff"):
                print(change["diff"], end="")
        print(f"Plan digest: {checksum}")
    return 2 if plan["changes"] else 0


def self_check():
    import breakglass
    import guard
    import transport
    require(callable(guard.Executor) and callable(transport.serve) and callable(breakglass.run),
            "Guard runtime import failed")
    print("Runtime self-check passed")


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "self-check":
        self_check()
        return 0
    if args.command == "guard":
        from transport import main as guard_main
        return guard_main(args.args)
    paths = install.Paths(args.root)
    if args.command == "verify":
        release, _, _, fingerprint = read_release(paths, args)
        print(f"Verified {release.version} {release.checksum} ({fingerprint})")
        return 0
    if args.command == "rotate-key":
        with lock(paths.lock):
            require(not paths.recovery() and install.safe_dir(paths.control),
                    "Signer enrollment requires an installation with no pending recovery")
            require(install.current(paths) or paths.record()["highest"], "Use install to enroll the first signer")
            signer, fingerprint = read_signer(args.allowed_signers)
            require(fingerprint == args.fingerprint, "New signer does not match the independent fingerprint")
            mode = install.file_mode(paths.signers)
            previous, previous_fingerprint = read_signer(paths.signers) if mode is not None else (None, None)
            if previous != signer or mode != 0o600:
                receipts = paths.control / "release-key-rotations"
                paths.make_directory(receipts, 0o700)
                receipt = receipts / (uuid.uuid4().hex + ".json")
                event = {"event": "release-key.rotation", "at": datetime.now(UTC).isoformat(),
                         "previous": previous_fingerprint, "next": fingerprint,
                         "previous_signer": previous.decode() if previous else None,
                         "state": "requested"}
                atomic_write(receipt, encode(event))
                atomic_write(paths.signers, signer)
                atomic_write(receipt, encode({**event, "state": "installed"}))
        print(f"Pinned {fingerprint}")
        return 0
    if args.command == "status":
        version = install.current(paths)
        if version:
            install.check_release(paths.releases / version)
        print(json.dumps({"current": version, **paths.record(), "filesystem": paths.fs,
                          "recovery_pending": bool(paths.recovery())}, sort_keys=True))
        return 0
    if args.command == "migrations":
        version = install.current(paths)
        require(version, "No current release")
        owned = install.check_release(paths.releases / version)
        for epoch in install.migrations(paths, owned["files"]):
            print(epoch)
        return 0
    if args.command == "recover":
        with lock(paths.lock):
            install.recover(paths)
        return 0
    operation = "install" if args.command in {"plan", "apply"} else args.command
    yes = getattr(args, "yes", False)
    confirm_digest = getattr(args, "plan_digest", None)
    mutate = args.command == "apply" or getattr(args, "apply", False) or yes or bool(confirm_digest)
    require(not (getattr(args, "plan", False) and mutate), "Choose plan or apply")
    require(not mutate or yes or confirm_digest, "Apply requires --plan-digest")
    overlay = getattr(args, "overlay", None)

    def plan_now():
        release, channel, signers, fingerprint = (
            read_release(paths, args) if operation in {"install", "update"} else (None, None, None, None)
        )
        return install.describe(paths, operation, release, overlay=overlay, channel_digest=channel,
                                signer=fingerprint, purge=getattr(args, "purge", False)), release, signers

    if not mutate:
        return rendered(plan_now()[0], args.json)
    if paths.test and not paths.lock.parent.exists():
        paths.lock.parent.mkdir(exist_ok=True)
    with lock(paths.lock):
        paths = install.Paths(args.root)
        # A channel can expire, or the owner can rotate the key, while an apply waits.
        plan, release, signers = plan_now()
        require(yes or digest(encode(plan)) == confirm_digest, "Plan changed; review a fresh plan")
        if plan["changes"]:
            if operation in {"install", "update"}:
                install.activate(paths, plan, release, overlay=overlay, signers=signers)
            elif operation == "rollback":
                install.rollback(paths, plan)
            else:
                install.uninstall(paths, plan, args.confirm)
        print("Applied" if plan["changes"] else "No changes")
    return 0


if __name__ == "__main__":
    try:
        os.umask(0o077)
        sys.exit(main())
    except (Error, OSError, ValueError, KeyError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(f"otuken: {error}", file=sys.stderr)
        sys.exit(1)
