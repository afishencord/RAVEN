"""SSH regression tests: no SSH client or external host is contacted."""
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import support  # Isolated settings before application imports.
from app.models import Credential, Node
from app.services import automation, execution_runner, ssh_execution


class SSHExecutionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="raven-ssh-test-")
        self.addCleanup(self.directory.cleanup)
        self.known_hosts = Path(self.directory.name) / "known_hosts"
        # Dummy public fixture. OpenSSH is mocked: assert trust configuration
        # and propagation, not actual cryptographic host-key authentication.
        self.trusted_host_keys = "app01.example.test ssh-ed25519 PUBLIC_TEST_FIXTURE\n"
        self.known_hosts.write_text(self.trusted_host_keys)
        self.known_hosts.chmod(0o644)
        settings_patch = patch.object(execution_runner.settings, "ssh_known_hosts_path", str(self.known_hosts))
        settings_patch.start()
        self.addCleanup(settings_patch.stop)
        # Bypass daemon initialization, which prepares the database.
        self.runner = execution_runner.RunnerDaemon.__new__(execution_runner.RunnerDaemon)
        self.routes = {
            "runner": lambda host, command, cred: self.runner._run_ssh(host, command, cred),
            "automation": lambda host, command, cred: automation._run_ssh(host, command, cred, 17),
        }

    @staticmethod
    def credential(kind="ssh_key", username="ops"):
        return Credential(name="ssh-fixture", kind=kind, username=username, secret_value="private-test-credential-not-real")

    def assert_safe_argv(self, argv, credential):
        ssh = argv[argv.index("ssh"):]
        self.assertEqual(ssh[1:5], ["-F", "/dev/null", "-n", "-T"])
        for option in (
            "StrictHostKeyChecking=yes",
            "GlobalKnownHostsFile=/dev/null", "VerifyHostKeyDNS=no", "UpdateHostKeys=no",
            "KbdInteractiveAuthentication=no", "ForwardAgent=no", "ClearAllForwardings=yes",
        ):
            self.assertEqual(ssh.count(option), 1)
        trust_options = [arg for arg in ssh if arg.startswith("UserKnownHostsFile=")]
        self.assertEqual(len(trust_options), 1)
        snapshot = Path(trust_options[0].split("=", 1)[1])
        self.assertNotEqual(snapshot, self.known_hosts)
        self.assertEqual(snapshot.read_text(), self.trusted_host_keys)
        self.assertEqual(stat.S_IMODE(snapshot.stat().st_mode), 0o600)
        self.assertNotIn(credential.secret_value, argv)
        self.assertEqual(ssh[-3:], ["--", "app01.example.test", "uname -s"])
        self.assertEqual(ssh[ssh.index("-l") + 1], "ops")
        self.assertNotIn("StrictHostKeyChecking=no", argv)
        self.assertNotIn("StrictHostKeyChecking=accept-new", argv)
        return ssh

    def test_key_auth_policy_and_cleanup_on_both_routes(self):
        for name, route in self.routes.items():
            with self.subTest(route=name):
                credential = self.credential()
                paths = []
                def run(argv, **kwargs):
                    ssh = self.assert_safe_argv(argv, credential)
                    for option in ("PreferredAuthentications=publickey", "PasswordAuthentication=no", "BatchMode=yes", "IdentitiesOnly=yes", "IdentityAgent=none"):
                        self.assertIn(option, ssh)
                    path = Path(argv[argv.index("-i") + 1])
                    self.assertEqual(path.read_text(), credential.secret_value)
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                    self.assertEqual(kwargs["pass_fds"], ())
                    self.assertNotIn("shell", kwargs)
                    self.assertEqual(kwargs["timeout"], 60 if name == "runner" else 17)
                    paths.extend((path, Path(next(arg.split("=", 1)[1] for arg in argv if arg.startswith("UserKnownHostsFile=")))))
                    return subprocess.CompletedProcess(argv, 0, "Linux\n", "")
                with patch.object(ssh_execution.subprocess, "run", side_effect=run) as mocked:
                    self.assertEqual(route("app01.example.test", "uname -s", credential), (0, "Linux"))
                    mocked.assert_called_once()
                self.assertTrue(paths)
                self.assertTrue(all(not path.exists() for path in paths))

    def test_password_is_passed_by_private_fd_not_argv_or_environment(self):
        for name, route in self.routes.items():
            with self.subTest(route=name):
                credential = self.credential("ssh_password")
                descriptors = []
                def run(argv, **kwargs):
                    ssh = self.assert_safe_argv(argv, credential)
                    self.assertEqual(argv[:2], ["sshpass", "-d"])
                    fd = int(argv[2])
                    self.assertEqual(kwargs["pass_fds"], (fd,))
                    self.assertEqual(os.read(fd, 4096), (credential.secret_value + "\n").encode())
                    self.assertEqual(stat.S_IMODE(os.fstat(fd).st_mode), 0o600)
                    for option in ("PreferredAuthentications=password", "PubkeyAuthentication=no", "NumberOfPasswordPrompts=1"):
                        self.assertIn(option, ssh)
                    self.assertNotIn("-p", argv)
                    self.assertNotIn("env", kwargs)
                    self.assertNotIn("shell", kwargs)
                    descriptors.append(fd)
                    return subprocess.CompletedProcess(argv, 0, "Linux", "")
                with patch.object(ssh_execution.subprocess, "run", side_effect=run):
                    self.assertEqual(route("app01.example.test", "uname -s", credential), (0, "Linux"))
                for fd in descriptors:
                    with self.assertRaises(OSError):
                        os.fstat(fd)

    def test_invalid_known_hosts_fail_before_spawn(self):
        empty = Path(self.directory.name) / "empty"
        empty.touch()
        writable = Path(self.directory.name) / "writable"
        writable.write_text("public fixture\n")
        writable.chmod(0o666)
        fifo = Path(self.directory.name) / "fifo"
        os.mkfifo(fifo)
        invalid_paths = (
            None, "", "none", "known_hosts", "~/known_hosts", "/tmp/%h",
            "/tmp/${HOME}", "/tmp/host file", "/tmp/hosts\nother", "/tmp/hosts\"other",
            str(Path(self.directory.name) / "missing"), str(empty), str(writable),
            str(fifo), self.directory.name, "/dev/null",
        )
        for name, route in self.routes.items():
            for kind in ("ssh_key", "ssh_password"):
                for path in invalid_paths:
                    with self.subTest(route=name, kind=kind, path=path):
                        with patch.object(execution_runner.settings, "ssh_known_hosts_path", path), patch.object(ssh_execution.subprocess, "run") as mocked:
                            code, output = route("app01.example.test", "uname -s", self.credential(kind))
                            self.assertEqual(code, 1)
                            self.assertIn("SSH", output)
                            mocked.assert_not_called()

    def test_unknown_and_changed_key_failures_are_not_retried_or_downgraded(self):
        for name, route in self.routes.items():
            for kind in ("ssh_key", "ssh_password"):
                for reason in ("No ED25519 host key is known and strict checking was requested.", "REMOTE HOST IDENTIFICATION HAS CHANGED!"):
                    with self.subTest(route=name, kind=kind, reason=reason):
                        credential = self.credential(kind)
                        def reject(argv, **kwargs):
                            self.assert_safe_argv(argv, credential)
                            return subprocess.CompletedProcess(argv, 255, "", reason)
                        with patch.object(ssh_execution.subprocess, "run", side_effect=reject) as mocked:
                            self.assertEqual(route("app01.example.test", "uname -s", credential), (255, reason))
                            mocked.assert_called_once()

    def test_destination_cannot_inject_options(self):
        hosts = ("-oProxyCommand=evil", "-Fconfig", "host -oStrictHostKeyChecking=no", "host\nother", "host/other", "ssh://host", "a@b@host", "@host", "host;evil", "host%h", "host:22", "$(evil)")
        users = ("-oProxyCommand=evil", "ops@host", "ops name", "ops\nname", "$(evil)")
        for name, route in self.routes.items():
            for host, user in [(host, "ops") for host in hosts] + [("app01.example.test", user) for user in users]:
                with self.subTest(route=name, host=host, user=user):
                    with patch.object(ssh_execution.subprocess, "run") as mocked:
                        self.assertEqual(route(host, "uname -s", self.credential(username=user))[0], 1)
                        mocked.assert_not_called()

    def test_embedded_username_must_match_credential(self):
        for name, route in self.routes.items():
            for user in (None, "ops"):
                with self.subTest(route=name, user=user):
                    credential = self.credential(username=user)
                    def run(argv, **kwargs):
                        self.assert_safe_argv(argv, credential)
                        return subprocess.CompletedProcess(argv, 0, "Linux", "")
                    with patch.object(ssh_execution.subprocess, "run", side_effect=run):
                        self.assertEqual(route("ops@app01.example.test", "uname -s", credential), (0, "Linux"))
            with patch.object(ssh_execution.subprocess, "run") as mocked:
                self.assertEqual(route("other@app01.example.test", "uname -s", self.credential())[0], 1)
                mocked.assert_not_called()

    def test_invalid_credentials_fail_before_spawn(self):
        credentials = [None, self.credential("bearer_token")]
        for kind, value in (("ssh_key", ""), ("ssh_key", "bad\0key"), ("ssh_password", "bad\npassword"), ("ssh_password", "bad\rpassword")):
            credential = self.credential(kind)
            credential.secret_value = value
            credentials.append(credential)
        for name, route in self.routes.items():
            for credential in credentials:
                with self.subTest(route=name, kind=credential.kind if credential else None):
                    with patch.object(ssh_execution.subprocess, "run") as mocked:
                        self.assertEqual(route("app01.example.test", "uname -s", credential)[0], 1)
                        mocked.assert_not_called()

    def test_subprocess_failures_cleanup_and_do_not_echo_secrets(self):
        for name, route in self.routes.items():
            for kind in ("ssh_key", "ssh_password"):
                for error, expected in ((subprocess.TimeoutExpired("sensitive argv", 1), 124), (FileNotFoundError("sensitive argv"), 127), (OSError("sensitive argv"), 1)):
                    with self.subTest(route=name, kind=kind, error=type(error).__name__):
                        seen = []
                        def fail(argv, **kwargs):
                            seen.append(Path(argv[argv.index("-i") + 1]) if kind == "ssh_key" else int(argv[2]))
                            seen.append(Path(next(arg.split("=", 1)[1] for arg in argv if arg.startswith("UserKnownHostsFile="))))
                            raise error
                        with patch.object(ssh_execution.subprocess, "run", side_effect=fail):
                            code, output = route("app01.example.test", "uname -s", self.credential(kind))
                            self.assertEqual(code, expected)
                            self.assertNotIn("sensitive argv", output)
                            self.assertNotIn(self.credential(kind).secret_value, output)
                        for resource in seen:
                            if isinstance(resource, Path):
                                self.assertFalse(resource.exists())
                            else:
                                with self.assertRaises(OSError):
                                    os.fstat(resource)

    def test_temporary_trust_path_cannot_expand_ssh_tokens(self):
        for component in ("temp-%h", "temp space", "temp-${HOME}"):
            directory = Path(self.directory.name) / component
            directory.mkdir()
            with self.subTest(directory=component):
                with patch.object(ssh_execution.tempfile, "tempdir", str(directory)), patch.object(ssh_execution.subprocess, "run") as mocked:
                    for route in self.routes.values():
                        result = route("app01.example.test", "uname -s", self.credential())
                        self.assertEqual(result[0], 1)
                        self.assertIn("SSH temporary directory", result[1])
                    mocked.assert_not_called()
                self.assertEqual(list(directory.iterdir()), [])

    def test_host_trust_uses_validated_descriptor_not_replaced_source_path(self):
        real_copy = ssh_execution.shutil.copyfileobj
        for name, route in self.routes.items():
            for kind in ("ssh_key", "ssh_password"):
                with self.subTest(route=name, kind=kind):
                    self.known_hosts.write_text(self.trusted_host_keys)
                    replacement = Path(self.directory.name) / "replacement"
                    replacement.write_text("app01.example.test ssh-ed25519 ATTACKER_KEY\n")
                    snapshots = []
                    def replace_path_then_copy(source, destination):
                        # After the original source descriptor is opened and
                        # checked, replace its name before any bytes are copied.
                        replacement.replace(self.known_hosts)
                        return real_copy(source, destination)
                    credential = self.credential(kind)
                    def run(argv, **kwargs):
                        self.assert_safe_argv(argv, credential)
                        self.assertIn("ATTACKER_KEY", self.known_hosts.read_text())
                        snapshots.append(Path(next(arg.split("=", 1)[1] for arg in argv if arg.startswith("UserKnownHostsFile="))))
                        return subprocess.CompletedProcess(argv, 0, "Linux", "")
                    with patch.object(ssh_execution.shutil, "copyfileobj", side_effect=replace_path_then_copy), patch.object(ssh_execution.subprocess, "run", side_effect=run):
                        self.assertEqual(route("app01.example.test", "uname -s", credential), (0, "Linux"))
                    self.assertTrue(snapshots)
                    self.assertTrue(all(not path.exists() for path in snapshots))

    def test_malformed_ssh_targets_do_not_fall_back_to_local_execution(self):
        for target in ("ssh", "ssh:", "ssh:app01", "ssh::service", "ssh:app01:"):
            with self.subTest(target=target):
                node = Node(name="ssh-test", execution_mode="runner", execution_target=target)
                with patch.object(self.runner, "_run_subprocess") as local, patch.object(execution_runner, "run_ssh") as remote:
                    result = self.runner._dispatch(node, "uname -s", self.credential(), 1)
                    self.assertEqual(result[0], 1)
                    self.assertIn("SSH execution target", result[1])
                    local.assert_not_called()
                    remote.assert_not_called()
                with patch.object(automation, "_run_subprocess") as local, patch.object(automation, "run_ssh") as remote:
                    result = automation._dispatch_validation_command(None, node, "uname -s", 17)
                    self.assertEqual(result[0], 1)
                    self.assertIn("SSH execution target", result[1])
                    local.assert_not_called()
                    remote.assert_not_called()

    def test_dispatchers_use_shared_policy(self):
        node = Node(name="ssh-test", execution_mode="runner", execution_target="ssh:ops@app01.example.test:service")
        credential = self.credential()
        with patch.object(execution_runner, "run_ssh", return_value=(255, "untrusted host")) as shared:
            self.assertEqual(self.runner._dispatch(node, "uname -s", credential, 1), (255, "untrusted host"))
            shared.assert_called_once_with("ops@app01.example.test", "uname -s", credential, known_hosts_path=str(self.known_hosts), timeout=60)
        with patch.object(automation, "run_ssh", return_value=(255, "untrusted host")) as shared:
            self.assertEqual(automation._dispatch_validation_command(None, node, "uname -s", 17), (255, "untrusted host"))
            shared.assert_called_once_with("ops@app01.example.test", "uname -s", None, known_hosts_path=str(self.known_hosts), timeout=17)


if __name__ == "__main__":
    unittest.main()
