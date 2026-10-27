"""Isolated Flock authorization/identity tests. Subprocess execution is mocked."""
import copy
import stat
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from tests import support
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import flock_agent as api
from app.auth import get_password_hash
from app.database import Base
from app.deps import get_db
from app.models import FlockAgent, FlockEnrollmentToken, FlockPolicy, FlockTask, Node
from app.services import flock, flock_agent
from app.services.flock_identity_migration import migrate_flock_agent_identities
from app.services.flock_policy import FlockPolicyError, authorize_command

COMMAND = "/usr/bin/systemctl --no-pager status demo.service"
POLICY = {"is_enabled": True, "task_timeout_seconds": 30, "command_allowlist": [COMMAND]}
ENROLLMENT_TOKEN = "public-flock-security-enrollment-fixture-1234"


class CommandPolicyTests(unittest.TestCase):
    def test_exact_argv_and_equivalent_quoting(self):
        self.assertEqual(authorize_command(POLICY, COMMAND), COMMAND.split())
        self.assertEqual(authorize_command(POLICY, '/usr/bin/systemctl --no-pager status "demo.service"'), COMMAND.split())

    def test_missing_disabled_empty_and_malformed_policy(self):
        bad = [None, {}, {**POLICY, "is_enabled": False}, {**POLICY, "is_enabled": 1},
               {**POLICY, "command_allowlist": []}, {**POLICY, "command_allowlist": None},
               {**POLICY, "command_allowlist": COMMAND}, {**POLICY, "command_allowlist": [COMMAND, ""]},
               {**POLICY, "command_allowlist": [COMMAND, None]},
               {**POLICY, "task_timeout_seconds": 0}, {**POLICY, "task_timeout_seconds": True}]
        for policy in bad:
            with self.subTest(policy=policy), self.assertRaises(FlockPolicyError):
                authorize_command(policy, COMMAND)

    def test_prefix_argument_and_shell_bypasses(self):
        for command in (
            COMMAND + " --help", COMMAND + "-extra", COMMAND.replace("status", "restart"),
            COMMAND + "; /bin/echo denied", COMMAND + " && /bin/echo denied",
            COMMAND + "\n/bin/echo denied", COMMAND + " | /bin/cat", COMMAND + " > /tmp/result",
            COMMAND + " $(/bin/echo denied)", COMMAND + " `id`", COMMAND + " *",
            "sudo " + COMMAND, "/usr/bin/sudo -n " + COMMAND,
            "systemctl --no-pager status demo.service", "/usr/bin/../bin/systemctl --no-pager status demo.service",
            COMMAND + "\0", "", None,
        ):
            with self.subTest(command=command), self.assertRaises(FlockPolicyError):
                authorize_command(POLICY, command)

    def test_unsafe_allowlist_entries_denied_even_with_exact_match(self):
        for command in ("/bin/sh -c true", "/bin/bash -c true", "/usr/bin/python3.12 -c pass",
                        "/usr/bin/env /bin/echo hello", "/usr/bin/sudo /bin/echo hello",
                        "/usr/bin/ssh localhost /bin/echo hello", "/bin/echo *", "/bin/echo '"):
            with self.subTest(command=command), self.assertRaises(FlockPolicyError):
                authorize_command({**POLICY, "command_allowlist": [command]}, command)

    def test_execution_is_exact_argv_without_sudo_or_shell(self):
        completed = Mock(returncode=0, stdout="mock output", stderr="")
        with patch.object(flock_agent.subprocess, "run", return_value=completed) as run, patch.object(flock_agent, "_sudo_available", return_value=True) as sudo:
            self.assertEqual(flock_agent._execute(COMMAND, 999, POLICY), (0, "mock output"))
            run.assert_called_once_with(COMMAND.split(), shell=False, stdin=flock_agent.subprocess.DEVNULL, capture_output=True, text=True, timeout=30, check=False)
            sudo.assert_not_called()

    def test_missing_claim_policy_and_unknown_type_never_spawn(self):
        tasks = [
            {"command": COMMAND, "task_type": "command", "timeout_seconds": 30},
            {"command": COMMAND, "task_type": "command", "timeout_seconds": 30, "policy": {**POLICY, "is_enabled": False}},
            {"command": COMMAND, "task_type": "unknown", "timeout_seconds": 30, "policy": POLICY},
            {"command": COMMAND + " --help", "task_type": "command", "timeout_seconds": 30, "policy": POLICY},
            {"command": COMMAND, "task_type": "command", "timeout_seconds": True, "policy": POLICY},
        ]
        with patch.object(flock_agent.subprocess, "run") as run:
            for task in tasks:
                with self.subTest(task=task):
                    self.assertEqual(flock_agent._execute_task(task)[0], 126)
            self.assertEqual(flock_agent._execute(COMMAND, 30)[0], 126)
            run.assert_not_called()


class PrivateAgentStateTests(unittest.TestCase):
    def test_atomic_state_is_private_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private" / "agent.json"
            state = {"agent_id": "test-agent", "agent_token": "test-token"}
            with patch.object(flock_agent, "_state_path", return_value=path):
                self.assertIsNone(flock_agent._load_state())
                flock_agent._save_state(state)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertEqual(flock_agent._load_state(), state)
                self.assertEqual(list(path.parent.glob(".flock-state-*")), [])

    def test_insecure_corrupt_and_symlink_state_never_becomes_first_enrollment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.json"
            with patch.object(flock_agent, "_state_path", return_value=path):
                path.write_text('{"agent_id":"id","agent_token":"secret"}')
                path.chmod(0o644)
                with self.assertRaises(RuntimeError):
                    flock_agent._load_state()
                path.chmod(0o600)
                for content in ("{invalid", "{}", "[]", '{"agent_id":"id","agent_token":null}'):
                    path.write_text(content)
                    with self.subTest(content=content), self.assertRaises(RuntimeError):
                        flock_agent._load_state()
                other = Path(directory) / "other.json"
                path.rename(other)
                path.symlink_to(other)
                with self.assertRaises(RuntimeError):
                    flock_agent._load_state()
                before = other.read_text()
                flock_agent._save_state({"agent_id": "id", "agent_token": "new"})
                self.assertFalse(path.is_symlink())
                self.assertEqual(other.read_text(), before)


class FlockAPISecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.enrollment_hash = get_password_hash(ENROLLMENT_TOKEN)

    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with self.sessions() as db:
            policy = FlockPolicy(name="test-policy", is_default=True, **POLICY)
            db.add(policy)
            db.flush()
            db.add(FlockEnrollmentToken(name="test-enrollment", token_hash=self.enrollment_hash, policy_id=policy.id))
            db.commit()
            self.policy_id = policy.id
        app = FastAPI()
        app.include_router(api.router)

        def test_db():
            with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = test_db
        self.client = TestClient(app)  # No lifespan, daemon or listening socket.
        self.addCleanup(self.client.close)
        self.payload = {"name": "Server A", "hostname": "host-a.example", "enrollment_token": ENROLLMENT_TOKEN, "metadata_json": {"owner": "original"}}
        response = self.client.post("/flock/enroll", json=self.payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.identity = response.json()
        self.agent_id = self.identity["agent_id"]
        self.headers = {"Authorization": "Bearer " + self.identity["agent_token"]}

    def snapshot(self):
        with self.sessions() as db:
            a = db.query(FlockAgent).filter_by(agent_id=self.agent_id).one()
            return (a.id, a.agent_id, a.token_hash, a.name, a.hostname, a.policy_id, a.node_id, copy.deepcopy(a.metadata_json))

    def dispatch(self, command=COMMAND):
        with patch.object(api, "_require_internal_token"):
            return self.client.post("/flock/internal/dispatch", json={"target": "flock:" + self.agent_id, "command": command})

    def queue(self, command=COMMAND, task_type="command"):
        with self.sessions() as db:
            agent = db.query(FlockAgent).filter_by(agent_id=self.agent_id).one()
            task = FlockTask(agent_id=agent.id, command=command, timeout_seconds=60, task_type=task_type)
            db.add(task)
            db.commit()
            return task.id

    def claim(self):
        return self.client.post(f"/flock/agents/{self.agent_id}/tasks/claim", headers=self.headers)

    def test_duplicate_name_or_hostname_never_mutates_identity(self):
        before = self.snapshot()
        for changes in ({}, {"name": "server a", "hostname": "new.example"},
                        {"name": "Other", "hostname": "HOST-A.EXAMPLE."},
                        {"name": "Ｓｅｒｖｅｒ Ａ", "hostname": "new.example"}):
            with self.subTest(changes=changes):
                response = self.client.post("/flock/enroll", json={**self.payload, **changes, "metadata_json": {"owner": "attacker"}})
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(self.snapshot(), before)
        with self.sessions() as db:
            self.assertEqual(db.query(FlockAgent).count(), 1)
            self.assertEqual(db.query(Node).count(), 1)

    def test_rejoin_requires_proof_and_retains_credentials_and_tasks(self):
        task_id = self.queue()
        before = self.snapshot()
        payload = {**self.payload, "existing_agent_id": self.agent_id, "metadata_json": {"owner": "replacement"}}
        for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": self.headers["Authorization"] + "x" * 80}):
            self.assertEqual(self.client.post("/flock/enroll", json=payload, headers=headers).status_code, 401)
            self.assertEqual(self.snapshot(), before)
        response = self.client.post("/flock/enroll", json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["agent_token"], self.identity["agent_token"])
        self.assertEqual(response.json()["agent_id"], self.agent_id)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.claim().json()["id"], task_id)

    def test_rejoin_cannot_rebind_name_or_hostname(self):
        before = self.snapshot()
        for field in ("name", "hostname"):
            payload = {**self.payload, "existing_agent_id": self.agent_id, field: "new-identity"}
            self.assertEqual(self.client.post("/flock/enroll", json=payload, headers=self.headers).status_code, 409)
        self.assertEqual(self.snapshot(), before)

    def test_heartbeat_cannot_rebind_hostname(self):
        before = self.snapshot()
        response = self.client.post(f"/flock/agents/{self.agent_id}/heartbeat", json={"hostname": "replacement.example", "metadata_json": {"owner": "replacement"}}, headers=self.headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.snapshot(), before)
        response = self.client.post(f"/flock/agents/{self.agent_id}/heartbeat", json={"hostname": "HOST-A.EXAMPLE."}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.snapshot()[4], before[4])

    def test_dispatch_denial_never_queues_or_waits(self):
        for updates in ({"command_allowlist": []}, {"is_enabled": False}, {"command_allowlist": ["/bin/echo hello"]}):
            with self.subTest(updates=updates), self.sessions() as db:
                policy = db.get(FlockPolicy, self.policy_id)
                policy.is_enabled = True
                policy.command_allowlist = [COMMAND]
                for key, value in updates.items():
                    setattr(policy, key, value)
                db.commit()
            with patch.object(api, "wait_for_task_result") as wait:
                response = self.dispatch()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["exit_code"], 126)
                self.assertIsNone(response.json()["task_id"])
                wait.assert_not_called()
            with self.sessions() as db:
                self.assertEqual(db.query(FlockTask).count(), 0)

    def test_invalid_internal_token_cannot_dispatch(self):
        for headers in ({}, {"X-Flock-Internal-Token": "invalid"}):
            with patch.object(api, "wait_for_task_result") as wait:
                response = self.client.post("/flock/internal/dispatch", json={"target": "flock:" + self.agent_id, "command": COMMAND}, headers=headers)
                self.assertEqual(response.status_code, 401)
                wait.assert_not_called()

    def test_disabled_or_missing_enrollment_policy_never_invents_a_default(self):
        with self.sessions() as db:
            db.get(FlockPolicy, self.policy_id).is_enabled = False
            db.commit()
        response = self.client.post("/flock/enroll", json={**self.payload, "name": "New", "hostname": "new"})
        self.assertEqual(response.status_code, 403)
        with self.sessions() as db:
            db.query(FlockEnrollmentToken).update({"policy_id": None})
            db.commit()
        response = self.client.post("/flock/enroll", json={**self.payload, "name": "New", "hostname": "new"})
        self.assertEqual(response.status_code, 403)
        with self.sessions() as db:
            self.assertEqual(db.query(FlockPolicy).count(), 1)
            self.assertEqual(db.query(FlockAgent).count(), 1)

    def test_missing_assignment_never_uses_default(self):
        with self.sessions() as db:
            db.query(FlockAgent).filter_by(agent_id=self.agent_id).update({"policy_id": None})
            db.commit()
        self.assertEqual(self.dispatch().json()["exit_code"], 126)
        heartbeat = self.client.post(f"/flock/agents/{self.agent_id}/heartbeat", json={}, headers=self.headers)
        self.assertIsNone(heartbeat.json()["policy"])

    def test_allowed_dispatch_queues_once_with_bounded_timeout(self):
        def finish(db, task, **kwargs):
            task.status, task.exit_code, task.output = "success", 0, "mock result"
            return task
        with patch.object(api, "wait_for_task_result", side_effect=finish) as wait:
            response = self.dispatch()
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(wait.call_count, 1)
        with self.sessions() as db:
            task = db.query(FlockTask).one()
            self.assertEqual((task.command, task.timeout_seconds), (COMMAND, 30))

    def test_policy_revocation_rechecked_before_claim(self):
        task_id = self.queue()
        with self.sessions() as db:
            db.get(FlockPolicy, self.policy_id).is_enabled = False
            db.commit()
        self.assertIsNone(self.claim().json())
        with self.sessions() as db:
            task = db.get(FlockTask, task_id)
            self.assertEqual((task.status, task.exit_code), ("failed", 126))
        self.assertEqual(self.queue(task_type="unenroll"), self.claim().json()["id"])

    def test_unknown_and_non_allowlisted_queued_tasks_fail_before_claim(self):
        for command, task_type in ((COMMAND + " --help", "command"), (COMMAND, "unknown")):
            task_id = self.queue(command=command, task_type=task_type)
            self.assertIsNone(self.claim().json())
            with self.sessions() as db:
                self.assertEqual(db.get(FlockTask, task_id).exit_code, 126)

    def test_claim_contains_current_policy_and_bounded_timeout(self):
        task_id = self.queue()
        response = self.claim()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], task_id)
        self.assertEqual(body["timeout_seconds"], 30)
        self.assertEqual(body["policy"]["command_allowlist"], [COMMAND])
        self.assertTrue(body["policy"]["is_enabled"])

    def test_ambiguous_cross_field_alias_fails_closed(self):
        response = self.client.post("/flock/enroll", json={**self.payload, "name": self.payload["hostname"], "hostname": "other.example"})
        self.assertEqual(response.status_code, 200, response.text)
        with self.sessions() as db:
            self.assertIsNone(flock.resolve_agent_target(db, self.payload["hostname"]))
            self.assertEqual(flock.resolve_agent_target(db, "flock:" + self.agent_id).agent_id, self.agent_id)

    def test_pending_or_revoked_agents_cannot_rejoin_or_receive_commands(self):
        for state in ("unenroll_pending", "unenrolled"):
            with self.sessions() as db:
                db.query(FlockAgent).filter_by(agent_id=self.agent_id).update({"status": state})
                db.commit()
            response = self.client.post("/flock/enroll", json={**self.payload, "existing_agent_id": self.agent_id}, headers=self.headers)
            self.assertEqual(response.status_code, 409 if state == "unenroll_pending" else 401)
            self.assertEqual(self.dispatch().json()["status"], "failed")


class IdentityMigrationTests(unittest.TestCase):
    def legacy_engine(self, rows):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE flock_agents (id INTEGER PRIMARY KEY, name TEXT, hostname TEXT, agent_id TEXT, token_hash TEXT)"))
            for row_id, name, hostname in rows:
                connection.execute(text("INSERT INTO flock_agents VALUES (:id, :name, :host, :agent, :token)"),
                                   {"id": row_id, "name": name, "host": hostname, "agent": f"id-{row_id}", "token": "unchanged-hash"})
        return engine

    def test_additive_idempotent_migration_retains_ids_and_tokens(self):
        engine = self.legacy_engine([(1, " Server A ", "HOST-A.EXAMPLE.")])
        migrate_flock_agent_identities(engine)
        migrate_flock_agent_identities(engine)
        with engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM flock_agents")).mappings().one()
        self.assertEqual((row["agent_id"], row["token_hash"]), ("id-1", "unchanged-hash"))
        self.assertEqual((row["name_key"], row["hostname_key"]), ("server a", "host-a.example"))
        self.assertEqual(len([i for i in inspect(engine).get_indexes("flock_agents") if i["unique"]]), 2)

    def test_conflicts_fail_preflight_without_record_or_schema_destruction(self):
        for rows in ([(1, "Server A", "a"), (2, "server a", "b")],
                     [(1, "A", "HOST.EXAMPLE."), (2, "B", "host.example")]):
            with self.subTest(rows=rows):
                engine = self.legacy_engine(rows)
                with self.assertRaisesRegex(RuntimeError, "Conflicting Flock"):
                    migrate_flock_agent_identities(engine)
                self.assertNotIn("name_key", {c["name"] for c in inspect(engine).get_columns("flock_agents")})
                with engine.connect() as connection:
                    self.assertEqual(connection.execute(text("SELECT count(*) FROM flock_agents")).scalar(), 2)
                    self.assertEqual(connection.execute(text("SELECT DISTINCT token_hash FROM flock_agents")).scalar(), "unchanged-hash")

    def test_database_uniqueness_closes_concurrent_insert_race(self):
        # Both connections observe absence before either inserts. A database
        # constraint (not merely a pre-insert lookup) must pick one winner.
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine("sqlite:///" + str(Path(directory) / "race.db"))
            try:
                Base.metadata.create_all(engine)
                sessions = sessionmaker(bind=engine)
                barrier = threading.Barrier(2)

                def insert(number):
                    with sessions() as db:
                        self.assertIsNone(db.query(FlockAgent).first())
                        barrier.wait(timeout=5)
                        db.add(FlockAgent(agent_id=f"agent-{number}", name="same name", hostname=f"host-{number}", token_hash=f"hash-{number}"))
                        try:
                            db.commit()
                            return "inserted"
                        except IntegrityError:
                            db.rollback()
                            return "conflict"

                with ThreadPoolExecutor(max_workers=2) as pool:
                    self.assertCountEqual(pool.map(insert, [1, 2]), ["inserted", "conflict"])
                with sessions() as db:
                    self.assertEqual(db.query(FlockAgent).count(), 1)
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
