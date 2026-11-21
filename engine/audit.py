# SPDX-License-Identifier: MIT
"""Recoverable guard ledger and append-only, chained audit events."""

import json
import os
import stat
import subprocess

from common import atomic_write, digest, encode, read_json, require, sync_dir

HEAD = "journal_head"
EMPTY = "0" * 64
EVENT_LIMIT = 128 * 1024


class Audit:
    def __init__(self, directory):
        self.directory = directory
        self.journal = directory / "events.jsonl"
        self.ledger = directory / "ledger.json"
        self.pending = directory / "ledger.pending.json"

    def open(self, flags):
        fd = os.open(self.journal, flags | os.O_NOFOLLOW, 0o600)
        info = os.fstat(fd)
        if not (stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1):
            os.close(fd)
            require(False, "Unsafe append-only journal")
        return fd

    def append_only(self):
        """Enable the kernel append-only flag before the privileged service accepts requests."""
        os.close(self.open(os.O_WRONLY | os.O_CREAT | os.O_APPEND))
        flags = subprocess.check_output(["/usr/bin/lsattr", "-d", "--", self.journal], text=True).split()[0]
        if "a" not in flags:
            subprocess.run(["/usr/bin/chattr", "+a", "--", self.journal], check=True)

    def lines(self, through=None):
        if not self.journal.exists() and not self.journal.is_symlink():
            return
        with os.fdopen(self.open(os.O_RDONLY), "rb") as stream:
            while through is None or stream.tell() < through:
                row = stream.readline(EVENT_LIMIT + 1)
                if not row:
                    break
                require(len(row) <= EVENT_LIMIT, "Audit event exceeds its size limit")
                yield row
            require(through is None or stream.tell() == through, "Audit journal length changed")

    def tail(self):
        if not self.journal.exists() and not self.journal.is_symlink():
            return None
        with os.fdopen(self.open(os.O_RDONLY), "rb") as stream:
            size = stream.seek(0, os.SEEK_END)
            if not size:
                return None
            stream.seek(max(0, size - EVENT_LIMIT))
            tail = stream.read()
        require(tail.endswith(b"\n"), "Incomplete audit event")
        return tail.splitlines()[-1] + b"\n"

    def head(self):
        tail = self.tail()
        return digest(tail) if tail else EMPTY

    def check_chain(self, state, *, through=None, anchor=None):
        head = EMPTY
        chained = False
        last = None
        legacy = EMPTY
        offset = 0
        anchored = anchor is None or anchor == (0, EMPTY)
        for line in self.lines(through):
            row = json.loads(line)
            require(isinstance(row, dict) and line.endswith(b"\n"), "Malformed audit event")
            if "previous" in row:
                require(row["previous"] == head and isinstance(row.get("ledger"), str), "Broken audit chain")
                if not chained and legacy != EMPTY:
                    require(row.get("legacy") == legacy, "Legacy audit prefix changed")
                chained = True
            else:
                require(not chained, "Unchained event after journal enrollment")
                legacy = digest(legacy.encode() + line)
            head = digest(line)
            last = row
            offset += len(line)
            anchored |= anchor == (offset, head)
        require(anchored, "Audit chain lost its pre-repair anchor")
        if HEAD in state:
            body = {key: value for key, value in state.items() if key != HEAD}
            require(chained and state[HEAD] == head and last["ledger"] == digest(encode(body)),
                    "Audit journal does not match the guard ledger")
        else:
            require(not chained, "Missing guard ledger for chained audit journal")
        return head

    def recover(self):
        pending = read_json(self.pending)
        if pending is None:
            return
        payload = encode(pending["event"])
        event = pending["event"]
        state = pending["state"]
        body = {key: value for key, value in state.items() if key != HEAD}
        require(state.get(HEAD) == digest(payload) and event["ledger"] == digest(encode(body)),
                "Pending audit transaction does not match its ledger")
        head = self.head()
        require(head in {pending["event"]["previous"], digest(payload)}, "Unexpected audit head during recovery")
        if head != digest(payload):
            fd = self.open(os.O_WRONLY | os.O_CREAT | os.O_APPEND)
            try:
                require(os.write(fd, payload) == len(payload), "Short audit write")
                os.fsync(fd)
            finally:
                os.close(fd)
        atomic_write(self.ledger, encode(pending["state"]))
        self.pending.unlink()
        sync_dir(self.directory)

    def read(self, default):
        self.recover()
        state = read_json(self.ledger, default)
        tail = self.tail()
        if HEAD in state:
            require(tail and state[HEAD] == digest(tail), "Audit journal does not match the guard ledger")
            body = {key: value for key, value in state.items() if key != HEAD}
            require(json.loads(tail)["ledger"] == digest(encode(body)), "Guard ledger digest mismatch")
        elif tail:
            require("previous" not in json.loads(tail), "Guard ledger is missing")
        return state

    def legacy_prefix(self):
        checksum = EMPTY
        for line in self.lines():
            checksum = digest(checksum.encode() + line)
        return checksum

    def save(self, state, event):
        body = {key: value for key, value in state.items() if key != HEAD}
        head = self.head()
        previous = state.get(HEAD, head)
        require(previous == head, "Audit journal changed before save")
        row = {**event, "previous": previous, "ledger": digest(encode(body))}
        state[HEAD] = digest(encode(row))
        atomic_write(self.pending, encode({"event": row, "state": state}))
        self.recover()
