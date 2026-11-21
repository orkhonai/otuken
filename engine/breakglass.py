# SPDX-License-Identifier: MIT
"""Run exact owner-authorized root repairs and record detective drift alarms."""

import hashlib
import os
import pwd
import re
import select
import stat
import subprocess
import tempfile
import time
from pathlib import Path

import backup
import install
from audit import EMPTY, HEAD, Audit
from common import Error, atomic_write, digest, encode, lock, require

SYSTEMCTL = "/usr/bin/systemctl"
OUTPUT_LIMIT = 1024 * 1024
RUNTIME_SECONDS = 120
DEFAULT_VERIFY_TIMEOUT = 360
RC_FILES = (".profile", ".bash_profile", ".bash_login", ".bashrc", ".bash_logout",
            ".zshenv", ".zprofile", ".zshrc", ".zlogin", ".zlogout", ".kshrc", ".cshrc",
            ".tcshrc", ".login", ".logout", ".pam_environment", ".ssh/rc",
            ".config/fish", ".config/systemd", ".local/share/systemd/user",
            ".ssh/authorized_keys", ".ssh/authorized_keys2")
REPAIR_ERRORS = (Error, OSError, ValueError, subprocess.SubprocessError)


def unit_name(checksum):
    return f"otuken-break-glass-{checksum}.service"


def cgroup_empty(checksum):
    events = Path("/sys/fs/cgroup/system.slice") / unit_name(checksum) / "cgroup.events"
    try:
        return "populated 0" in events.read_text().splitlines()
    except FileNotFoundError:
        return True


def account_homes(root):
    """Include interactive accounts, root, and accounts with a lingering user manager."""
    linger = root / "var/lib/systemd/linger"
    names = {path.name for path in linger.iterdir()} if linger.is_dir() else set()
    homes = {root / "root"}
    for entry in pwd.getpwall():
        interactive = entry.pw_shell.rsplit("/", 1)[-1] not in {"false", "nologin", ""}
        if ((entry.pw_uid == 0 or entry.pw_name in names or interactive)
                and entry.pw_dir.startswith("/") and entry.pw_dir != "/"):
            homes.add(root / entry.pw_dir.lstrip("/"))
    return sorted(homes)


def persistence_paths(root, homes):
    for home in homes:
        yield from (home / name for name in RC_FILES)
        yield from sorted(home.glob(".*rc"))
    for version in sorted((root / "usr/lib").glob("python3*")):
        for directory in ("dist-packages", "site-packages"):
            yield from sorted((version / directory).glob("*.pth"))
            yield version / directory / "sitecustomize.py"


def census(paths, rescue_homes, transient_unit, *, errors):
    audit = paths.data / "audit"
    checks = [
        paths.code, paths.control, audit, paths.data / "journal", paths.data / "credentials",
        *(paths.root / name for name in (
            "etc", "var/spool/cron", "usr/local", "usr/lib/systemd", "usr/lib/udev",
            "usr/lib/tmpfiles.d", "usr/lib/sysctl.d", "usr/lib/modules-load.d", "var/lib/systemd/linger",
            "run/systemd/system", "run/systemd/system.control", "run/systemd/transient",
            "run/systemd/generator", "run/systemd/generator.early", "run/systemd/generator.late",
            "var/lib/dpkg/status", "var/lib/dpkg/info",
        )),
        *persistence_paths(paths.root, rescue_homes),
    ]
    exclude = {audit / name for name in ("events.jsonl", "ledger.json", "ledger.pending.json", "guard.lock")}
    exclude.add(paths.root / "run/systemd/transient" / transient_unit)
    files = {}

    def visit(path):
        if path in exclude or str(path) in files:
            return
        try:
            info = path.lstat()
        except FileNotFoundError:
            return
        except OSError:
            errors.append(str(path))
            return
        try:
            fingerprint = hashlib.sha256(encode([info.st_mode, info.st_uid, info.st_gid]))
            for name in sorted(os.listxattr(path, follow_symlinks=False)):
                fingerprint.update(encode(name))
                fingerprint.update(hashlib.sha256(os.getxattr(path, name, follow_symlinks=False)).digest())
            if stat.S_ISLNK(info.st_mode):
                fingerprint.update(encode(os.readlink(path)))
            elif stat.S_ISREG(info.st_mode):
                with path.open("rb") as stream:
                    fingerprint.update(hashlib.file_digest(stream, "sha256").digest())
            files[str(path)] = fingerprint.hexdigest()
            if stat.S_ISDIR(info.st_mode):
                for child in sorted(path.iterdir()):
                    visit(child)
        except OSError:
            errors.append(str(path))

    for path in checks:
        visit(path)
    return files


def checkpoints(paths, errors):
    result = {}
    store = paths.data / "backups"
    try:
        entries = [*store.iterdir(), *paths.data.parent.glob("otuken-purge-*")]
        for entry in sorted(entries):
            for path in [entry, *sorted(entry.iterdir())] if entry.is_dir() and not entry.is_symlink() else [entry]:
                info = path.lstat()
                stamp = [info.st_ino, info.st_uid, info.st_gid, info.st_mode, info.st_size,
                         info.st_mtime_ns, info.st_ctime_ns]
                if stat.S_ISDIR(info.st_mode) and info.st_ino == 256 and paths.fs == "btrfs":
                    metadata = subprocess.check_output(["/usr/bin/btrfs", "subvolume", "show", str(path)],
                                                       text=True, timeout=5)
                    uuid = re.search(r"^\s*UUID:\s+(\S+)", metadata, re.MULTILINE)
                    require(uuid, "Checkpoint subvolume UUID unavailable")
                    stamp.append(uuid[1])
                result[str(path)] = digest(encode(stamp))
    except REPAIR_ERRORS:
        errors.append(str(store))
    return result


def package_verification(timeout=DEFAULT_VERIFY_TIMEOUT):
    result = subprocess.run(
        ["/usr/bin/ionice", "-c", "3", "/usr/bin/nice", "-n", "19",
         "/usr/bin/dpkg", "--verify", "--verify-format=rpm"],
        capture_output=True, timeout=timeout, check=False, env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
    )
    require(result.returncode == 0 and not result.stderr, "dpkg verification incomplete")
    failures = {}
    for line in result.stdout.decode(errors="replace").splitlines():
        prefix, separator, path = line.partition(" /")
        require(separator, "Unrecognized dpkg verification report")
        if prefix.startswith("missing"):
            path = path.partition(" (")[0]
        failures["/" + path] = digest(line.encode())
    return failures


def usr_inventory(root, timeout):
    usr = root / "usr"
    if not usr.is_dir():
        return {}
    result = subprocess.check_output(
        ["/usr/bin/ionice", "-c", "3", "/usr/bin/nice", "-n", "19",
         "/usr/bin/find", str(usr), "-xdev", "(", "-type", "f", "-o", "-type", "l", ")",
         "-printf", r"%i %C@ %p\0"],
        timeout=timeout,
    )
    inventory = {}
    for row in filter(None, result.split(b"\0")):
        inode, changed, name = row.split(b" ", 2)
        inventory[os.fsdecode(name)] = (inode, changed)
    return inventory


def snapshot(paths, rescue_homes, transient_unit, *, timeout=DEFAULT_VERIFY_TIMEOUT, edge=None):
    errors = []
    state = census(paths, rescue_homes, transient_unit, errors=errors)
    try:
        packages = package_verification(timeout)
    except REPAIR_ERRORS:
        packages = {}
        errors.append("dpkg --verify")
    try:
        usr = usr_inventory(paths.root, timeout)
    except REPAIR_ERRORS:
        usr = {}
        errors.append("/usr inventory")
    concurrent = []
    if edge:
        other = census(paths, rescue_homes, transient_unit, errors=errors)
        etc = str(paths.root / "etc")
        transient = str(paths.root / "run/systemd/transient")
        concurrent = [path for path in other.keys() | state.keys()
                      if (path == etc or path.startswith((etc + "/", transient + "/")))
                      and other.get(path) != state.get(path)]
        if edge == "before":
            state = other
    state.update(checkpoints(paths, errors))
    return {"files": state, "packages": packages, "usr": usr, "errors": errors, "concurrent": concurrent}


def drift(before, after, targets):
    concurrent = set(before.get("concurrent", ())) | set(after.get("concurrent", ()))
    report = {"declared": [], "unexpected": [], "concurrent": sorted(concurrent)}
    pairs = [(source, before[source], after[source]) for source in ("files", "packages")]
    if "/usr inventory" not in before["errors"] + after["errors"]:
        covered = before["files"].keys() | after["files"].keys()
        pairs.append(("usr-inventory", *({path: stamp for path, stamp in phase.get("usr", {}).items()
                                          if path not in covered} for phase in (before, after))))
    for source, old, new in pairs:
        for path in sorted(old.keys() | new.keys()):
            if old.get(path) == new.get(path):
                continue
            declared = any(path == target.rstrip("/") or (target.endswith("/") and path.startswith(target))
                           for target in targets)
            change = "added" if path not in old else "removed" if path not in new else "changed"
            if source == "packages" and path in concurrent and not declared:
                continue
            report["declared" if declared else "unexpected"].append(
                {"source": source, "path": path, "change": change}
            )
    report["unavailable"] = sorted(set(before["errors"] + after["errors"]))
    return report


def audit_stamp(audit):
    with lock(audit.directory / "guard.lock"):
        state = audit.read({})
        size = audit.journal.stat().st_size
    return size, state


def transient_command(checksum):
    return [
        "/usr/bin/systemd-run", "--wait", "--collect", "--pipe", "--quiet",
        f"--unit={unit_name(checksum)}", "--slice=system.slice", "--service-type=exec", "--working-directory=/",
        "--uid=0", "--gid=0", "--setenv=PATH=/usr/sbin:/usr/bin:/sbin:/bin", "--setenv=LANG=C.UTF-8",
        "--setenv=BASH_ENV=/dev/null", f"--property=RuntimeMaxSec={RUNTIME_SECONDS}s",
        "--property=TimeoutStopSec=5s", "--property=KillMode=control-group",
        "--property=ExitType=main", "--property=SendSIGKILL=yes", "--property=TimeoutStartSec=10s",
        "/bin/bash", "--noprofile", "--norc", "-s",
    ]


def capture_output(pipe, stream, deadline, limit=OUTPUT_LIMIT):
    written = 0
    truncated = False
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([pipe], [], [], remaining)[0]:
            raise Error("Break-glass output deadline exceeded")
        chunk = os.read(pipe.fileno(), 16384)
        if not chunk:
            return truncated
        retained = chunk[:limit - written]
        stream.write(retained)
        written += len(retained)
        truncated |= len(retained) != len(chunk)


def execute(checksum, script, output):
    unit = unit_name(checksum)
    deadline = time.monotonic() + RUNTIME_SECONDS + 20
    truncated = False
    with tempfile.TemporaryFile() as source, output.open("xb") as stream:
        source.write(script.encode())
        source.seek(0)
        with subprocess.Popen(
            transient_command(checksum), stdin=source, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
        ) as process:
            try:
                truncated = capture_output(process.stdout, stream, deadline)
                status = process.wait(timeout=max(0, deadline - time.monotonic()))
            finally:
                try:
                    subprocess.run([SYSTEMCTL, "stop", unit], capture_output=True, timeout=10, check=False)
                    require(cgroup_empty(checksum), "Break-glass cgroup still has processes")
                finally:
                    if process.poll() is None:
                        process.kill()
                    stream.flush()
                    os.fsync(stream.fileno())
    return status, truncated


def run(paths, checksum, script, targets):
    with lock(paths.lock):
        require(not paths.recovery(), "Installer recovery is pending")
        version = install.current(paths)
        require(version, "No installed release")
        install.check_release(paths.releases / version)
        record = paths.record()["previous"]
        protected = [record["backup"]] if record else []
        backup.prune(paths, protected)
        checkpoint = backup.create(paths, install.choices(paths)[0])
        backup.prune(paths, [*protected, checkpoint])

        output_dir = paths.data / "evidence" / "break-glass"
        paths.make_directory(output_dir, 0o700)
        unit = unit_name(checksum)
        timeout = int(os.environ.get("OTUKEN_DPKG_VERIFY_SECONDS", DEFAULT_VERIFY_TIMEOUT))
        require(60 <= timeout <= 1800, "Package verification timeout must be 60–1800 seconds")
        rescue_homes = account_homes(paths.root)
        audit = Audit(paths.data / "audit")
        anchor, audit_before = audit_stamp(audit)
        before = snapshot(paths, rescue_homes, unit, timeout=timeout, edge="before")
        log = output_dir / f"{checksum}.log"
        status, truncated, error = None, False, None
        try:
            status, truncated = execute(checksum, script, log)
        except REPAIR_ERRORS as failure:
            error = type(failure).__name__
        after = snapshot(paths, sorted(set(rescue_homes) | set(account_homes(paths.root))),
                         unit, timeout=timeout, edge="after")
        report = drift(before, after, targets)
        try:
            size, audit_after = audit_stamp(audit)
            audit.check_chain(audit_after, through=size, anchor=(anchor, audit_before.get(HEAD, EMPTY)))
        except REPAIR_ERRORS:
            report["unexpected"].append({"source": "audit", "path": str(audit.directory), "change": "unverified"})
        file = output_dir / f"{checksum}.json"
        atomic_write(file, encode({**report, "exit_status": status, "output_truncated": truncated,
                                   "run_error": error, "log": str(log), "checkpoint": checkpoint,
                                   "targets": targets, "script_sha256": digest(script.encode())}))
        return {"ok": status == 0, "alarm": bool(report["unexpected"] or report["unavailable"]),
                "report": str(file), "unexpected": len(report["unexpected"]), "unavailable": len(report["unavailable"]),
                "concurrent": len(report["concurrent"])}
