# SPDX-License-Identifier: MIT
"""Local guard sockets. The executor reads the original client connection."""

import argparse
import collections
import json
import os
import socket
import stat
import struct
import sys
import threading
import time
from pathlib import Path

from common import Error, encode, lock, require
from guard import Executor, exact, positive

RUNTIME = Path("/run/otuken")
OWNER = RUNTIME / "owner.sock"
EXECUTOR = RUNTIME / "executor.sock"
REQUEST = RUNTIME / "request" / "guard.sock"
MAX_MESSAGE = 64 * 1024
FRAME_SECONDS = 3
FRAME_ERRORS = (OSError, ValueError, TypeError, RecursionError)


def strict_object(pairs):
    obj = dict(pairs)
    require(len(obj) == len(pairs), "Duplicate JSON fields")
    return obj


def decode(raw):
    require(raw.endswith(b"\n") and len(raw) <= MAX_MESSAGE, "Invalid message frame")
    return json.loads(raw, object_pairs_hook=strict_object)


def peer_uid(sock):
    creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", creds)[1]


def socket_frame(conn, seconds=FRAME_SECONDS):
    deadline = time.monotonic() + seconds
    buffer = bytearray()
    while len(buffer) < MAX_MESSAGE:
        remaining = deadline - time.monotonic()
        require(remaining > 0, "Message frame deadline exceeded")
        conn.settimeout(remaining)
        try:
            chunk = conn.recv(min(8192, MAX_MESSAGE - len(buffer)))
        except TimeoutError:
            raise Error("Message frame deadline exceeded") from None
        require(chunk, "Incomplete message frame")
        buffer.extend(chunk)
        if b"\n" in chunk:
            head, _, rest = buffer.partition(b"\n")
            require(not rest, "Only one request per connection is supported")
            return decode(head + b"\n")
    raise Error("Invalid message frame")


def reply(conn, *, result=None, error=None):
    try:
        conn.settimeout(1)
        conn.sendall(encode({"error": error} if error is not None else {"result": result}))
    except OSError:
        pass


def respond(conn, dispatch):
    try:
        reply(conn, result=dispatch(peer_uid(conn), socket_frame(conn)))
    except Error as exc:
        reply(conn, error=str(exc))
    except FRAME_ERRORS:
        reply(conn, error="Invalid request or unavailable service")


class Connections:
    def __init__(self, per_uid=2, total=32):
        self.per_uid = per_uid
        self.total = total
        self.active = collections.Counter()
        self.lock = threading.Lock()

    def start(self, conn, handler):
        uid = peer_uid(conn)
        with self.lock:
            allowed = self.active[uid] < self.per_uid and self.active.total() < self.total
            if allowed:
                self.active[uid] += 1
        if not allowed:
            # No writes to a rejected peer from the accept thread.
            conn.close()
            return

        def work():
            try:
                with conn:
                    handler(conn)
            finally:
                with self.lock:
                    self.active[uid] -= 1
                    if not self.active[uid]:
                        del self.active[uid]

        threading.Thread(target=work, daemon=True).start()


def serve(listener, handler, *, per_uid=2):
    connections = Connections(per_uid=per_uid)
    while True:
        conn, _ = listener.accept()
        connections.start(conn, handler)


def call(path, request, *, expected_uid=None, timeout=5):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(str(path))
        if expected_uid is not None:
            require(peer_uid(sock) == expected_uid, "Unexpected service identity")
        sock.sendall(encode(request))
        response = socket_frame(sock, timeout)
    if "error" in response:
        raise Error(response["error"])
    exact(response, ("result",))
    return response["result"]


def listen(path, mode, uid):
    if path.is_socket() and not path.is_symlink():
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.settimeout(1)
            try:
                probe.connect(str(path))
            except ConnectionRefusedError:
                path.unlink()
            else:
                raise Error(f"Socket is already serving: {path}")
    require(not path.exists() and not path.is_symlink(), "Unsafe existing socket path")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    os.chown(path, uid, -1)
    path.chmod(mode)
    listener.listen(32)
    return listener


class RateLimit:
    def __init__(self):
        self.calls = collections.OrderedDict()
        self.lock = threading.Lock()

    def check(self, uid):
        now = time.monotonic()
        with self.lock:
            if uid not in self.calls and len(self.calls) >= 128:
                self.calls.popitem(last=False)
            credits, last = self.calls.pop(uid, (8, now))
            credits = min(8, credits + now - last)
            self.calls[uid] = (max(0, credits - 1), now)
        require(credits >= 1, "Request-service rate limit exceeded")


def forward(client, executor_path, *, executor_uid):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.settimeout(1)
            upstream.connect(str(executor_path))
            require(peer_uid(upstream) == executor_uid, "Unexpected executor identity")
            require(socket.send_fds(upstream, [b"C"], [client.fileno()]) == 1, "Incomplete connection handoff")
    except (Error, OSError):
        reply(client, error="Executor unavailable")


def handoff(executor, broker_uid, request_path, *, limiter=None):
    connections = Connections()
    rate = limiter or RateLimit()

    def request(conn):
        def dispatch(uid, payload):
            range_checked = positive(uid, 2**31 - 1)
            rate.check(range_checked)
            return executor.submit(range_checked, payload)
        respond(conn, dispatch)

    def receive(upstream):
        if peer_uid(upstream) != broker_uid:
            return
        upstream.settimeout(1)
        try:
            marker, fds, flags, _ = socket.recv_fds(upstream, 1, 4, socket.MSG_CMSG_CLOEXEC)
        except OSError:
            return
        try:
            if marker != b"C" or len(fds) != 1 or flags & socket.MSG_CTRUNC:
                return
            try:
                client = socket.socket(fileno=fds[0])
            except OSError:
                return
            fds.clear()
            try:
                require(client.family == socket.AF_UNIX and client.type == socket.SOCK_STREAM
                        and client.getsockname() == str(request_path), "Unexpected client descriptor")
                client.getpeername()  # A connected descriptor is required.
                connections.start(client, request)
            except (Error, OSError):
                client.close()
        finally:
            for fd in fds:
                os.close(fd)

    return receive


def owner_dispatch(executor, owner_uid):
    def dispatch(uid, command):
        require(uid == owner_uid, "Owner socket requires owner identity")
        return executor.owner(command)
    return dispatch


def start_executor(broker_uid):
    import breakglass
    import install

    require(os.geteuid() == 0, "Executor requires the host owner")
    paths = install.Paths()
    require(install.current(paths), "Install a release before starting the executor")
    runtime = paths.runtime
    if not install.safe_dir(runtime):
        runtime.mkdir(mode=0o755)
        runtime.chmod(0o755)
    require(not stat.S_IMODE(runtime.stat().st_mode) & 0o022, "Unsafe guard runtime")
    mode = install.file_mode(paths.guard_policy)
    require(mode in {None, 0o600}, "Guard policy must have mode 0600")
    legacy_policy = paths.config / "overlay/guard-policy.json"
    require(mode is not None or not (legacy_policy.exists() or legacy_policy.is_symlink()),
            "Owner must publish the legacy guard policy outside the overlay")
    executor = Executor(paths.data / "audit", paths.guard_policy,
                        script_runner=lambda key, script, targets: breakglass.run(paths, key, script, targets),
                        script_reaped=breakglass.cgroup_empty, append_only=True)
    with (
        lock(paths.root / "run/otuken-executor.lock"),
        listen(OWNER, 0o600, 0) as owner,
        listen(EXECUTOR, 0o600, broker_uid) as broker,
    ):
        def handle_owner(connection):
            respond(connection, owner_dispatch(executor, 0))
        threading.Thread(target=serve, args=(owner, handle_owner), daemon=True).start()
        serve(broker, handoff(executor, broker_uid, REQUEST), per_uid=16)


def main(argv):
    cli = argparse.ArgumentParser(prog="otuken guard")
    commands = cli.add_subparsers(dest="role", required=True)
    executor = commands.add_parser("executor")
    executor.add_argument("--broker-uid", type=int, required=True)
    commands.add_parser("service")
    commands.add_parser("owner")
    commands.add_parser("request")
    args = cli.parse_args(argv)
    if args.role == "executor":
        start_executor(positive(args.broker_uid, 2**31 - 1))
    elif args.role == "service":
        require(os.geteuid() != 0, "Request service must run unprivileged")
        parent = REQUEST.parent.lstat()
        require(stat.S_ISDIR(parent.st_mode) and parent.st_uid == os.geteuid()
                and not parent.st_mode & 0o022, "Unsafe request socket directory")
        with listen(REQUEST, 0o666, os.geteuid()) as listener:
            def relay(connection):
                forward(connection, EXECUTOR, executor_uid=0)
            serve(listener, relay)
    else:
        owner = args.role == "owner"
        require(not owner or os.geteuid() == 0, "Owner command requires the host owner")
        result = call(OWNER if owner else REQUEST, decode(sys.stdin.buffer.readline(MAX_MESSAGE + 1)),
                      expected_uid=0 if owner else None)
        print(json.dumps(result, indent=2))
    return 0
