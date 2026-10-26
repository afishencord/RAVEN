"""One fail-closed SSH transport for runner commands and automation validations.

Host trust is an administrator-managed input, never learned from a connection.
Keep SSH options here so password and key authentication cannot diverge.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.models import Credential


class SSHConfigurationError(ValueError):
    """A safe, credential-free error suitable for an execution result."""


@contextmanager
def _known_hosts_snapshot(configured_path: str | None) -> Iterator[str]:
    # OpenSSH expands tokens and accepts whitespace-separated filenames here.
    # Deliberately support only one literal absolute path, not an ssh_config
    # expression, an implicit home directory, or the special value "none".
    if not configured_path or not re.fullmatch(r"/[A-Za-z0-9_./-]+", configured_path):
        raise SSHConfigurationError("SSH_KNOWN_HOSTS_PATH must be a literal absolute path to a trusted known_hosts file.")
    try:
        path = Path(configured_path).resolve(strict=True)
        if not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(path)):
            raise SSHConfigurationError("SSH_KNOWN_HOSTS_PATH resolves to an unsupported path.")
        # O_NONBLOCK avoids hanging on a misconfigured FIFO/device; O_NOFOLLOW
        # prevents a replacement symlink between resolution and opening.
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or not info.st_size:
                raise SSHConfigurationError("SSH known_hosts must be a non-empty regular file.")
            if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise SSHConfigurationError("SSH known_hosts must not be writable by group or other users.")
            if info.st_uid not in {0, os.geteuid()}:
                raise SSHConfigurationError("SSH known_hosts must be owned by root or the application user.")
            # SSH otherwise reopens the original pathname after these checks.
            # Copy from the validated descriptor, not a second path lookup, to
            # prevent a replaced path/symlink from substituting attacker trust.
            with tempfile.NamedTemporaryFile(mode="w+b", prefix="raven-known-hosts-") as snapshot:
                if not re.fullmatch(r"/[A-Za-z0-9_./-]+", snapshot.name):
                    raise SSHConfigurationError("SSH temporary directory must use a literal absolute path without expansion tokens.")
                shutil.copyfileobj(handle, snapshot)
                snapshot.flush()
                yield snapshot.name
    except (OSError, RuntimeError):
        raise SSHConfigurationError("SSH known_hosts is missing or unreadable; provision verified host keys before connecting.") from None


def _destination(location: str, credential_username: str | None) -> tuple[str, str]:
    embedded_user = None
    host = location
    if "@" in location:
        if location.count("@") != 1:
            raise SSHConfigurationError("Invalid SSH destination.")
        embedded_user, host = location.split("@", 1)
        if not embedded_user:
            raise SSHConfigurationError("Invalid SSH username.")
        if credential_username and credential_username != embedded_user:
            raise SSHConfigurationError("SSH target username must match the credential username.")
    username = credential_username or embedded_user or "root"
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}\$?", username):
        raise SSHConfigurationError("Invalid SSH username.")
    # Current execution targets use ssh:[user@]host:subject. A host is a DNS
    # name or IPv4 address, never an option, URI, port, or ssh_config directive.
    labels = host.removesuffix(".").split(".")
    if len(host) > 253 or not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels):
        raise SSHConfigurationError("Invalid SSH hostname; use a DNS name or IPv4 address without a port.")
    return host, username


def _execute(argv: list[str], timeout: int, *, pass_fds: tuple[int, ...] = ()) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout,
            check=False, pass_fds=pass_fds,
        )
        return completed.returncode, "\n".join(filter(None, [completed.stdout, completed.stderr])).strip()
    except subprocess.TimeoutExpired:
        return 124, f"SSH execution timed out after {timeout} seconds."
    except FileNotFoundError:
        return 127, "SSH execution requires the ssh client and, for password authentication, sshpass."
    except OSError:
        # Do not return an exception containing argv, key material, or passwords.
        return 1, "SSH execution could not start."


def run_ssh(
    location: str,
    command: str,
    credential: Credential | None,
    *,
    known_hosts_path: str | None,
    timeout: int,
) -> tuple[int, str]:
    if not credential or credential.kind not in {"ssh_key", "ssh_password"}:
        return 1, "SSH execution requires an ssh_key or ssh_password credential."
    if not credential.secret_value or "\x00" in credential.secret_value:
        return 1, "SSH credential is empty or invalid."
    if not isinstance(command, str) or "\x00" in command:
        return 1, "Invalid SSH command."
    try:
        host, username = _destination(location, credential.username)
        with _known_hosts_snapshot(known_hosts_path) as known_hosts:
            return _authenticate(host, username, command, credential, known_hosts, timeout)
    except SSHConfigurationError as exc:
        return 1, str(exc)


def _authenticate(host: str, username: str, command: str, credential: Credential, known_hosts: str, timeout: int) -> tuple[int, str]:
    # -F prevents user/system config from installing proxy commands or alternate
    # trust sources. Unknown/changed keys fail without prompting or key learning.
    argv = [
        "ssh", "-F", "/dev/null", "-n", "-T",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "VerifyHostKeyDNS=no",
        "-o", "UpdateHostKeys=no",
        "-o", "KbdInteractiveAuthentication=no",
        "-o", "ForwardAgent=no",
        "-o", "ClearAllForwardings=yes",
        "-l", username,
    ]
    destination = ["--", host, command]
    try:
        if credential.kind == "ssh_password":
            if "\n" in credential.secret_value or "\r" in credential.secret_value:
                return 1, "SSH password must not contain line breaks."
            # sshpass reads its password from an inherited private descriptor,
            # not process arguments, environment variables, or a named file.
            with tempfile.TemporaryFile(mode="w+b") as password_file:
                password_file.write(credential.secret_value.encode("utf-8") + b"\n")
                password_file.seek(0)
                fd = password_file.fileno()
                return _execute(
                    ["sshpass", "-d", str(fd), *argv,
                     "-o", "PreferredAuthentications=password",
                     "-o", "PubkeyAuthentication=no",
                     "-o", "NumberOfPasswordPrompts=1", *destination],
                    timeout, pass_fds=(fd,),
                )

        # NamedTemporaryFile is created with mode 0600 and deleted on every exit,
        # including subprocess failures and timeouts. No secret appears in argv.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="raven-ssh-") as key_file:
            key_file.write(credential.secret_value)
            key_file.flush()
            return _execute(
                [*argv, "-i", key_file.name,
                 "-o", "PreferredAuthentications=publickey",
                 "-o", "PasswordAuthentication=no",
                 "-o", "BatchMode=yes",
                 "-o", "IdentitiesOnly=yes",
                 "-o", "IdentityAgent=none", *destination],
                timeout,
            )
    except OSError:
        return 1, "Unable to prepare protected SSH credentials."
