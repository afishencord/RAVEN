"""Shared, deny-by-default Flock command authorization.

Policies contain complete commands, never prefixes, globs or shell programs.
The returned argv is the *only* representation the agent may execute.
"""
from __future__ import annotations

import re
import shlex
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any


class FlockPolicyError(ValueError):
    pass


# Explicit interpreters, privilege/transport wrappers and command launchers are
# not supported. This is not an OS sandbox: administrators must still review
# each complete argv, the executable and any files/configuration it consumes.
_UNSUPPORTED_EXECUTABLES = {
    "sh", "bash", "dash", "ash", "zsh", "ksh", "fish", "csh", "tcsh",
    "env", "sudo", "su", "doas", "busybox", "xargs", "exec", "nohup",
    "chroot", "nsenter", "unshare", "ssh", "scp", "sftp", "docker", "podman",
    "perl", "ruby", "node", "nodejs", "php", "lua", "tclsh", "wish",
    "awk", "gawk", "mawk", "nawk", "expect", "pwsh", "powershell",
}
_SHELL_SYNTAX = set(";|&<>`$*?[]{}~")


def _value(policy: Any, key: str) -> Any:
    return policy.get(key) if isinstance(policy, Mapping) else getattr(policy, key, None)


def parse_command(command: Any) -> list[str]:
    if not isinstance(command, str) or not command.strip():
        raise FlockPolicyError("A non-empty command is required")
    if any(ord(char) < 32 or ord(char) == 127 or char in _SHELL_SYNTAX for char in command):
        raise FlockPolicyError("Shell syntax, expansions and control characters are not supported")
    try:
        argv = shlex.split(command, posix=True)
    except ValueError as exc:
        raise FlockPolicyError("Malformed command quoting") from exc
    if not argv or not argv[0].startswith("/"):
        raise FlockPolicyError("Commands require an absolute executable path")
    executable = PurePosixPath(argv[0])
    if ".." in executable.parts or str(executable) != argv[0]:
        raise FlockPolicyError("Executable paths must be canonical absolute paths")
    name = executable.name.lower()
    if name in _UNSUPPORTED_EXECUTABLES or re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", name):
        raise FlockPolicyError("Shells, interpreters, privilege wrappers and transports are not supported")
    return argv


def policy_timeout(policy: Any) -> int:
    timeout = _value(policy, "task_timeout_seconds")
    if type(timeout) is not int or not 1 <= timeout <= 86400:
        raise FlockPolicyError("Policy requires a valid task timeout (1-86400 seconds)")
    return timeout


def authorize_command(policy: Any, command: Any) -> list[str]:
    if _value(policy, "is_enabled") is not True:
        raise FlockPolicyError("No enabled Flock policy is assigned")
    policy_timeout(policy)
    allowlist = _value(policy, "command_allowlist")
    if not isinstance(allowlist, list) or not allowlist:
        raise FlockPolicyError("Flock command allowlist is empty or missing")
    # One invalid entry invalidates the whole policy rather than silently
    # broadening or partially interpreting a misconfigured policy.
    permitted = [parse_command(entry) for entry in allowlist]
    argv = parse_command(command)
    if argv not in permitted:
        raise FlockPolicyError("Command is not in the Flock policy's exact argv allowlist")
    return argv
