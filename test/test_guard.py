# SPDX-License-Identifier: MIT

import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from common import Error, digest
from guard import REQUEST_RETENTION, Executor
from transport import call, forward, handoff, listen, owner_dispatch, socket_frame


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.now = 1000
        self.actor = os.getuid() or 1001
        self.effects = []
        self.executor = self.new_executor()

    def new_executor(self):
        return Executor(self.directory, self.directory / "policy.json",
                        script_runner=self.script, clock=lambda: self.now)

    def script(self, key, body, targets):
        self.effects.append((key, body, targets))
        return {"ok": body != "exit 1", "alarm": False}

    def grant(self, project="project-a", *, verbs=None, ttl=30, budget=5):
        return self.executor.owner({"action": "grant", "actor": self.actor, "job": "job-a",
                                    "project": project, "ttl": ttl, "budget": budget,
                                    "verbs": verbs or ["project.reserve", "project.release",
                                                       "host.maintenance", "host.script"]})["lease"]

    def request(self, lease, sequence=1, *, verb="project.reserve", project="project-a", args=None):
        return {"lease": lease, "id": f"{sequence:032x}", "project": project,
                "job": "job-a", "verb": verb, "args": args or {}}

    def wait_script(self, request_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = self.executor.owner({"action": "inspect", "id": request_id})["status"]
            if status != "running":
                return status
            time.sleep(0.01)
        self.fail("Break-glass worker did not finish")

    def test_fake_executor_behind_unprivileged_transport(self):
        if os.geteuid() == 0:
            self.skipTest("peer credentials test runs unprivileged")
        request = self.request(self.grant())
        front = self.directory / "request.sock"
        executor_path = self.directory / "executor.sock"

        def accept_once(listener, handle):
            conn, _ = listener.accept()
            with conn:
                handle(conn)

        with listen(front, 0o600, self.actor) as listener, listen(executor_path, 0o600, self.actor) as executor:
            threads = [
                threading.Thread(target=accept_once,
                                 args=(executor, handoff(self.executor, self.actor, front)), daemon=True),
                threading.Thread(target=accept_once,
                                 args=(listener, lambda sock: forward(sock, executor_path, executor_uid=self.actor)),
                                 daemon=True),
            ]
            for thread in threads:
                thread.start()
            self.assertEqual(call(front, request, expected_uid=self.actor)["status"], "done")
            for thread in threads:
                thread.join(2)
                self.assertFalse(thread.is_alive())

    def test_slow_partial_frame_has_an_absolute_deadline(self):
        receiver, sender = socket.socketpair()
        with receiver, sender:
            sender.sendall(b"{")
            start = time.monotonic()
            with self.assertRaisesRegex(Error, "deadline"):
                socket_frame(receiver, seconds=0.10)
            self.assertLess(time.monotonic() - start, 0.5)

    def test_leases_scope_rate_budget_and_fixed_list(self):
        lease = self.grant(budget=1)
        request = self.request(lease)
        with self.assertRaisesRegex(Error, "scope"):
            self.executor.submit(self.actor + 1, request)
        with self.assertRaisesRegex(Error, "identifier"):
            self.executor.submit(self.actor, {**request, "project": "../invalid"})
        with self.assertRaisesRegex(Error, "fixed list"):
            self.executor.submit(self.actor, {**request, "verb": "incus.raw"})
        with self.assertRaisesRegex(Error, "fields"):
            self.executor.submit(self.actor, {**request, "args": {"raw": True}})
        result = self.executor.submit(self.actor, request)
        self.assertEqual(self.executor.submit(self.actor, request), result)
        with self.assertRaisesRegex(Error, "already used"):
            self.executor.submit(self.actor, {**request, "verb": "project.release"})
        with self.assertRaisesRegex(Error, "budget"):
            self.executor.submit(self.actor, self.request(lease, 2))
        self.directory.joinpath("policy.json").write_text('{"max_projects":1,"per_verb_per_hour":1}')
        another = self.grant("project-b")
        with self.assertRaisesRegex(Error, "rate"):
            self.executor.submit(self.actor, self.request(another, 3, project="project-b"))
        self.now += 3600
        with self.assertRaisesRegex(Error, "expired"):
            self.executor.submit(self.actor, request)
        another = self.grant("project-b")
        with self.assertRaisesRegex(Error, "ceiling"):
            self.executor.submit(self.actor, self.request(another, 3, project="project-b"))

    def test_owner_approval_binds_exact_script_and_only_runs_once(self):
        request = self.request(self.grant(), verb="host.script", args={"script": "printf fixture", "targets": ["/etc/fixture.conf"]})
        result = self.executor.submit(self.actor, request)
        self.assertEqual(result["status"], "pending")
        command = {"action": "approve", "id": request["id"], "digest": result["digest"]}
        with self.assertRaisesRegex(Error, "Owner"):
            owner_dispatch(self.executor, 0)(self.actor, command)
        with self.assertRaisesRegex(Error, "pending plan"):
            self.executor.owner({**command, "digest": "different"})
        self.assertEqual(self.effects, [])
        self.assertEqual(self.executor.owner(command)["status"], "running")
        self.assertEqual(self.wait_script(request["id"]), "done")
        with self.assertRaisesRegex(Error, "pending plan"):
            self.executor.owner(command)
        self.assertEqual(self.effects, [(result["digest"], "printf fixture", ["/etc/fixture.conf"])])
        events = (self.directory / "events.jsonl").read_text()
        claimed = json.loads(events.splitlines()[2])
        self.assertEqual(claimed["script"], "printf fixture")
        self.assertEqual(claimed["script_sha256"], digest(b"printf fixture"))
        self.assertEqual(claimed["targets"], ["/etc/fixture.conf"])
        self.assertNotIn(request["lease"], events)
        self.assertEqual([json.loads(row)["event"] for row in events.splitlines()],
                         ["lease.granted", "request.pending", "script.claimed", "request.approved"])

    def test_host_approval_and_halt_survive_executor_restart(self):
        lease = self.grant()
        request = self.request(lease, verb="host.maintenance", args={"enabled": True})
        pending = self.executor.submit(self.actor, request)
        self.assertFalse(self.executor.owner({"action": "status"})["maintenance"])
        self.executor.owner({"action": "approve", "id": pending["id"], "digest": pending["digest"]})
        self.executor.owner({"action": "halt"})
        self.executor = self.new_executor()
        status = self.executor.owner({"action": "status"})
        self.assertTrue(status["halted"])
        self.assertTrue(status["maintenance"])
        with self.assertRaisesRegex(Error, "halted"):
            self.executor.submit(self.actor, request)
        self.executor.owner({"action": "resume"})
        with self.assertRaisesRegex(Error, "revoked"):
            self.executor.submit(self.actor, request)

    def test_script_failure_remains_latched(self):
        lease = self.grant()
        failure = self.executor.submit(self.actor, self.request(lease, verb="host.script", args={"script": "exit 1"}))
        approval = {"action": "approve", "id": failure["id"], "digest": failure["digest"]}
        self.assertEqual(self.executor.owner(approval)["status"], "running")
        self.assertEqual(self.wait_script(failure["id"]), "failed")
        self.executor = self.new_executor()
        self.assertTrue(self.executor.owner({"action": "status"})["alert"])
        self.assertEqual(self.executor.owner({"action": "inspect", "id": failure["id"]})["status"], "failed")
        self.executor.owner({"action": "clear-alert"})
        self.assertFalse(self.executor.owner({"action": "status"})["alert"])


    def test_active_script_does_not_block_owner_status(self):
        started = threading.Event()
        finish = threading.Event()

        def run_fixture(_key, _script, _targets):
            started.set()
            return {"ok": finish.wait(5), "alarm": False}

        self.executor.script_runner = run_fixture
        request = self.request(self.grant(), verb="host.script", args={"script": "true"})
        result = self.executor.submit(self.actor, request)
        try:
            self.assertEqual(self.executor.owner({"action": "approve", "id": result["id"],
                                                  "digest": result["digest"]})["status"], "running")
            self.assertTrue(started.wait(2))
            self.assertTrue(self.executor.owner({"action": "status"})["alert"])
            self.assertEqual(self.executor.submit(self.actor, self.request(request["lease"], 2))["status"], "done")
            with self.assertRaisesRegex(Error, "active"):
                self.executor.owner({"action": "clear-alert"})
        finally:
            finish.set()
        self.assertEqual(self.wait_script(request["id"]), "done")

    def test_successful_script_reports_and_latches_a_detective_alarm(self):
        self.executor.script_runner = lambda *_: {"ok": True, "alarm": True, "report": "/fixture/report.json"}
        request = self.request(self.grant(), verb="host.script", args={"script": "true"})
        result = self.executor.submit(self.actor, request)
        self.executor.owner({"action": "approve", "id": result["id"], "digest": result["digest"]})
        self.assertEqual(self.wait_script(request["id"]), "done")
        self.assertTrue(self.executor.owner({"action": "status"})["alert"])
        item = self.executor.owner({"action": "inspect", "id": request["id"]})
        self.assertEqual(item["result"]["report"], "/fixture/report.json")

    def test_expired_requests_are_pruned_and_ids_are_lease_scoped(self):
        first = self.grant()
        old = self.request(first)
        self.executor.submit(self.actor, old)
        second = self.grant()
        self.assertEqual(self.executor.submit(self.actor, self.request(second))["status"], "done")
        with self.assertRaisesRegex(Error, "ambiguous"):
            self.executor.owner({"action": "inspect", "id": old["id"]})
        self.now += REQUEST_RETENTION + 31
        third = self.grant()
        self.assertEqual(self.executor.submit(self.actor, self.request(third))["status"], "done")
        self.assertEqual(len(self.executor.state()["requests"]), 1)

    def test_audit_chains_and_detects_past_event_edits(self):
        self.executor.submit(self.actor, self.request(self.grant()))
        journal = self.directory / "events.jsonl"
        first, last = journal.read_bytes().splitlines(keepends=True)
        self.assertEqual(json.loads(last)["previous"], digest(first))
        self.assertIn("ledger", json.loads(last))
        journal.write_bytes(first.replace(b"lease.granted", b"lease.changed") + last)
        with self.assertRaisesRegex(Error, "Broken audit chain"):
            self.new_executor()


    def test_post_repair_audit_can_extend_the_pre_repair_anchor(self):
        lease = self.grant()
        audit = self.executor.audit
        anchor = (audit.journal.stat().st_size, audit.head())
        self.executor.submit(self.actor, self.request(lease))
        audit.check_chain(self.executor.state(), through=audit.journal.stat().st_size, anchor=anchor)
        with self.assertRaisesRegex(Error, "lost its pre-repair anchor"):
            audit.check_chain(self.executor.state(), through=audit.journal.stat().st_size,
                              anchor=(anchor[0], "a" * 64))

    def test_audit_recovery_commits_a_claim_once_after_the_ledger_write_fails(self):
        with patch("audit.atomic_write", wraps=self._fail_ledger_once()) as fail:
            with self.assertRaisesRegex(OSError, "fixture"):
                self.grant()
            self.assertEqual(fail.call_count, 2)
        self.executor = self.new_executor()
        events = (self.directory / "events.jsonl").read_text().splitlines()
        self.assertEqual(len(events), 1)
        self.assertEqual(len(self.executor.state()["leases"]), 1)

    def _fail_ledger_once(self):
        from common import atomic_write

        def write(path, data):
            if path.name == "ledger.json":
                raise OSError("fixture")
            atomic_write(path, data)

        return write


if __name__ == "__main__":
    unittest.main()
