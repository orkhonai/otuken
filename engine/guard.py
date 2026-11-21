# SPDX-License-Identifier: MIT
"""Typed requests and owner decisions. The privileged ledger owns all authority."""

import hashlib
import os
import re
import secrets
import stat
import subprocess
import threading
import time
from pathlib import Path, PurePosixPath

from audit import HEAD, Audit
from common import Error, digest, encode, lock, read_json, require

IDENTIFIER = re.compile(r"[a-z][a-z0-9-]{0,62}")
TOKEN = re.compile(r"[a-f0-9]{32}")
VERBS = {"project.reserve": 1, "project.release": 1, "host.maintenance": 2, "host.script": 3}
DEFAULTS = {"max_projects": 4, "per_verb_per_hour": 10}
MAX_SCRIPT = 8192
REQUEST_RETENTION = 86400
MAX_LIVE_REQUESTS = 10000


def exact(obj, keys):
    require(isinstance(obj, dict) and set(obj) == set(keys), "Unexpected request fields")


def identifier(value):
    require(isinstance(value, str) and IDENTIFIER.fullmatch(value), "Invalid identifier")
    return value


def token(value):
    require(isinstance(value, str) and TOKEN.fullmatch(value), "Invalid request or lease ID")
    return value


def positive(value, maximum):
    require(type(value) is int and 0 < value <= maximum, "Number outside allowed range")
    return value


def validate_request(request):
    exact(request, ("id", "lease", "project", "job", "verb", "args"))
    for field in ("id", "lease"):
        token(request[field])
    for field in ("project", "job"):
        identifier(request[field])
    verb = request["verb"]
    require(isinstance(verb, str) and verb in VERBS, "Operation is outside the fixed list")
    args = request["args"]
    if verb == "host.maintenance":
        exact(args, ("enabled",))
        require(type(args["enabled"]) is bool, "Maintenance requires a boolean")
    elif verb == "host.script":
        exact(args, ("script", "targets") if isinstance(args, dict) and "targets" in args else ("script",))
        script = args["script"]
        require(isinstance(script, str) and "\x00" not in script
                and 0 < len(script.encode()) <= MAX_SCRIPT, "Invalid script")
        targets = args.get("targets", [])
        require(isinstance(targets, list) and len(targets) <= 32, "Invalid break-glass targets")
        for target in targets:
            require(isinstance(target, str) and 1 < len(target.encode()) <= 256 and target.startswith("/")
                    and not any(ord(char) < 32 for char in target)
                    and target.rstrip("/") == str(PurePosixPath(target)) and ".." not in PurePosixPath(target).parts
                    and target.rstrip("/") != "", "Expected a canonical absolute repair target")
    else:
        exact(args, ())
    return request


def policy(path):
    caps = read_json(path, DEFAULTS)
    exact(caps, DEFAULTS)
    positive(caps["max_projects"], DEFAULTS["max_projects"])
    positive(caps["per_verb_per_hour"], DEFAULTS["per_verb_per_hour"])
    return caps


def initial_state():
    return {"leases": {}, "requests": {}, "projects": {}, "rates": {},
            "maintenance": False, "halted": False, "alert": False}


class Executor:
    def __init__(self, directory, policy_path, *, script_runner, clock=time.time,
                 script_reaped=lambda _key: True, append_only=False):
        self.directory = Path(directory)
        self.policy_path = Path(policy_path)
        info = self.directory.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o700, "Unsafe executor state directory")
        self.script_runner = script_runner
        self.script_reaped = script_reaped
        self.clock = clock
        self.running = None
        self.audit = Audit(self.directory)
        with lock(self.directory / "guard.lock"):
            if append_only:
                self.audit.append_only()
            state = self.state()
            self.audit.check_chain(state)
            if HEAD not in state and (self.audit.ledger.exists() or self.audit.tail()):
                self.save(state, "journal.enrolled", legacy=self.audit.legacy_prefix())

    def state(self):
        return self.audit.read(initial_state())

    def save(self, state, event, **fields):
        self.audit.save(state, {"event": event, "at": int(self.clock()), **fields})

    def prune(self, state):
        now = int(self.clock())
        for old_key, item in list(state["requests"].items()):
            request = item["request"]
            key = request["lease"] + ":" + request["id"]
            expires = item.setdefault("expires", state["leases"].get(request["lease"], {}).get("expires", now))
            if old_key != key or (item["status"] != "running" and expires + REQUEST_RETENTION <= now):
                del state["requests"][old_key]
            if item["status"] == "running" or expires + REQUEST_RETENTION > now:
                state["requests"][key] = item

    @staticmethod
    def find_request(state, request_id, *, lease=None, checksum=None):
        items = [item for item in state["requests"].values()
                 if item["request"]["id"] == request_id
                 and (lease is None or item["request"]["lease"] == lease)
                 and (checksum is None or item["digest"] == checksum)]
        require(len(items) <= 1, "Request ID is ambiguous; supply its lease")
        return items[0] if items else None

    def lease(self, state, actor, request):
        lease = state["leases"].get(request["lease"], {})
        require(lease.get("actor") == actor and not lease.get("revoked")
                and lease["expires"] > self.clock() and lease["project"] == request["project"]
                and lease["job"] == request["job"] and request["verb"] in lease["verbs"],
                "Lease is unknown, expired, revoked or out of scope")
        return lease

    def grant(self, state, command):
        exact(command, ("action", "actor", "project", "job", "verbs", "ttl", "budget"))
        actor = positive(command["actor"], 2**31 - 1)
        verbs = command["verbs"]
        require(isinstance(verbs, list) and 0 < len(verbs) <= len(VERBS)
                and all(isinstance(verb, str) and verb in VERBS for verb in verbs)
                and len(set(verbs)) == len(verbs), "Invalid lease operation list")
        identifier(command["project"])
        identifier(command["job"])
        state["leases"] = {key: lease for key, lease in state["leases"].items()
                           if lease["expires"] > self.clock() and not lease.get("revoked")}
        require(len(state["leases"]) < 128 and not state["halted"], "Lease ceiling reached or guard halted")
        key = secrets.token_hex(16)
        state["leases"][key] = {"actor": actor, "project": command["project"], "job": command["job"],
                                "verbs": verbs, "expires": int(self.clock()) + positive(command["ttl"], 3600),
                                "budget": positive(command["budget"], 100)}
        self.save(state, "lease.granted", actor=actor, project=command["project"], job=command["job"])
        return {"lease": key, "expires": state["leases"][key]["expires"]}

    def submit(self, actor, request):
        validate_request(request)
        positive(actor, 2**31 - 1)
        with lock(self.directory / "guard.lock"):
            state = self.state()
            require(not state["halted"], "Guard is halted")
            self.prune(state)
            lease = self.lease(state, actor, request)
            key = request["id"]
            scoped = request["lease"] + ":" + key
            checksum = hashlib.sha256(encode(request)).hexdigest()
            if scoped in state["requests"]:
                item = state["requests"][scoped]
                require(item["actor"] == actor and item["digest"] == checksum,
                        "Idempotency key already used for another request")
                return {"id": key, "status": item["status"], "digest": checksum}
            live = sum(item["expires"] > self.clock() or item["status"] == "running"
                       for item in state["requests"].values())
            require(lease["budget"] > 0 and live < MAX_LIVE_REQUESTS, "Request budget exhausted")
            verb = request["verb"]
            caps = policy(self.policy_path)
            recent = [stamp for stamp in state["rates"].get(verb, []) if stamp > self.clock() - 3600]
            require(len(recent) < caps["per_verb_per_hour"], "Operation rate limit exceeded")
            state["rates"][verb] = [*recent, int(self.clock())]
            lease["budget"] -= 1
            item = {"actor": actor, "digest": checksum, "status": "pending", "request": request, "expires": lease["expires"]}
            if VERBS[verb] == 1:
                self.reserve_or_release(state, request, caps)
                item["status"] = "done"
            state["requests"][scoped] = item
            self.save(state, "request." + item["status"], id=key, actor=actor, verb=verb,
                      project=request["project"], job=request["job"], digest=checksum)
            return {"id": key, "status": item["status"], "digest": checksum}

    @staticmethod
    def reserve_or_release(state, request, caps):
        projects = state["projects"]
        project, job = request["project"], request["job"]
        identity = projects.get(project)
        if request["verb"] == "project.reserve":
            require(not state["maintenance"], "Project admission is paused for maintenance")
            require(identity == job or (identity is None and len(projects) < caps["max_projects"]),
                    "Project already belongs to another job or project ceiling reached")
            projects[project] = job
        else:
            require(identity in {None, job}, "Project belongs to another job")
            projects.pop(project, None)

    def approve(self, state, command):
        exact(command, ("action", "id", "digest"))
        key = token(command["id"])
        item = self.find_request(state, key, checksum=command["digest"])
        require(item and item["status"] == "pending" and not state["halted"] and not self.running
                and item["digest"] == command["digest"], "Approval does not match a pending plan")
        request = item["request"]
        self.lease(state, item["actor"], request)
        verb = request["verb"]
        if verb == "host.script":
            require(not state["alert"], "Clear the previous break-glass alert first")
            item["status"] = "running"
            state["alert"] = True
            args = request["args"]
            self.save(state, "script.claimed", id=key, digest=item["digest"], actor=item["actor"],
                      script=args["script"], script_sha256=digest(args["script"].encode()),
                      targets=args.get("targets", []))
            self.running = key
            threading.Thread(target=self.finish_script, args=(item,), daemon=True).start()
            return {"id": key, "status": "running"}
        state["maintenance"] = request["args"]["enabled"]
        item["status"] = "done"
        self.save(state, "request.approved", id=key, verb=verb, digest=item["digest"])
        return {"id": key, "status": item["status"]}

    def finish_script(self, claimed):
        request = claimed["request"]
        key = request["id"]
        checksum = claimed["digest"]
        result = {"ok": False, "alarm": True}
        script = request["args"]["script"]
        try:
            result = self.script_runner(checksum, script, request["args"].get("targets", []))
        except (Error, OSError, ValueError, subprocess.SubprocessError) as error:
            result["error"] = type(error).__name__
        finally:
            with lock(self.directory / "guard.lock"):
                self.running = None
                state = self.state()
                item = self.find_request(state, key, checksum=checksum)
                require(item and item["status"] == "running", "Break-glass claim drifted")
                item["status"] = "done" if result["ok"] else "failed"
                item["result"] = result
                state["alert"] = not result["ok"] or result["alarm"]
                self.save(state, "request.approved" if result["ok"] else "script.failed",
                          id=key, verb="host.script", digest=checksum, script_sha256=digest(script.encode()),
                          result=result)

    def owner(self, command):
        require(isinstance(command, dict), "Invalid owner command")
        action = command.get("action")
        with lock(self.directory / "guard.lock"):
            state = self.state()
            self.prune(state)
            require(not self.running or action in {"inspect", "status", "halt"}, "Break-glass is active")
            if action == "grant":
                return self.grant(state, command)
            if action == "approve":
                return self.approve(state, command)
            if action == "inspect":
                exact(command, ("action", "id", "lease") if "lease" in command else ("action", "id"))
                lease = token(command["lease"]) if "lease" in command else None
                item = self.find_request(state, token(command["id"]), lease=lease)
                require(item, "Unknown request")
                return item
            if action == "revoke":
                exact(command, ("action", "lease"))
                lease = state["leases"].get(token(command["lease"]))
                require(lease, "Unknown lease")
                lease["revoked"] = True
                self.save(state, "lease.revoked", actor=lease["actor"])
                return {"revoked": True}
            if action == "status":
                exact(command, ("action",))
                return {name: state[name] for name in ("maintenance", "halted", "alert", "projects")}
            if action in ("halt", "resume", "clear-alert"):
                exact(command, ("action",))
                if action == "clear-alert":
                    for item in state["requests"].values():
                        if item["status"] in {"running", "failed"}:
                            require(self.script_reaped(item["digest"]), "Break-glass cgroup still exists")
                            if item["status"] == "running":
                                item["status"] = "failed"
                    state["alert"] = False
                else:
                    state["halted"] = action == "halt"
                    if state["halted"]:
                        for lease in state["leases"].values():
                            lease["revoked"] = True
                self.save(state, "owner." + action)
                return {"ok": True}
            raise Error("Unknown owner action")
