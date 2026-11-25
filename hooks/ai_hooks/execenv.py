# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Where tools run: inside the devcontainer, through docker exec from the host, or nowhere.

This is the single implementation of the container and worktree handling that used to be
copied into each hook script and the pre-commit hook.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import config as repo_config
from . import gitutil

ENV_MODES = ("auto", "local", "docker", "none")

# Runs inside the process that executes the tool, after any login-shell profile (which may
# export a main-checkout root variable). Args: root, cwd relative to root, command.
# AI_HOOKS_CALLER_PATH, when set, goes back in front of the PATH the profile built. The
# AI_HOOKS_* names come from .ai-hooks.toml and are validated as shell variable names, so the
# unquoted expansion and the eval only ever see identifiers.
PREAMBLE = """root=$1 cwd=$2; shift 2
unset BASH_ENV ${AI_HOOKS_UNSET:-}
if [ -n "${AI_HOOKS_CALLER_PATH:-}" ]; then PATH="$AI_HOOKS_CALLER_PATH:$PATH"; fi
unset AI_HOOKS_CALLER_PATH
cd "$root" || exit 1
var=${AI_HOOKS_ROOT_VAR:-}
if [ -n "$var" ]; then export "$var=$root"; fi
if [ -n "${AI_HOOKS_ENV_SCRIPT:-}" ] && [ -f "$AI_HOOKS_ENV_SCRIPT" ]; then
    . "./$AI_HOOKS_ENV_SCRIPT" >/dev/null || exit 1
fi
if [ -n "$var" ]; then
    eval "actual=\\${$var}"
    if [ "$actual" != "$root" ]; then
        echo "error: $var is $actual, expected $root" >&2
        exit 1
    fi
fi
unset AI_HOOKS_UNSET AI_HOOKS_ROOT_VAR AI_HOOKS_ENV_SCRIPT var actual
cd "$cwd" || exit 1
exec "$@\""""


def preamble_env(repo: Optional[Path]) -> Dict[str, str]:
    """The AI_HOOKS_* variables PREAMBLE reads for repo."""
    cfg = repo_config.load(repo)
    return {
        "AI_HOOKS_UNSET": " ".join(cfg.unset),
        "AI_HOOKS_ROOT_VAR": cfg.root_var,
        "AI_HOOKS_ENV_SCRIPT": cfg.env_script,
    }


def tail(text: str, lines: int = 40) -> str:
    return "\n".join(text.splitlines()[-lines:])


class ToolTimeout(Exception):
    """A tool ran longer than the allowed time."""


DOCKER_PS_TIMEOUT = 3
ENV_CACHE_TTL = {"docker": 300, "local": 300, "none": 30}


class ExecEnv:
    """Execution environment. `detect` resolves lazily, so events that run no containerised
    tool never pay for `docker ps`."""

    def __init__(self, mode: Optional[str], container: str = "") -> None:
        self._mode = mode
        self._container = container
        self._requested = "auto"
        self.cache_file: Optional[Path] = None
        self.timeout: Optional[float] = None
        self._lock = threading.Lock()
        self._local = threading.local()
        self._visible: Dict[str, Optional[str]] = {}
        # Repository whose .ai-hooks.toml names the container; set before the first tool runs.
        self.repo: Optional[Path] = None

    @classmethod
    def detect(cls, override: Optional[str] = None) -> "ExecEnv":
        mode = override or os.environ.get("AI_HOOKS_ENV") or "auto"
        if mode not in ENV_MODES:
            raise ValueError(f"unknown environment {mode!r}; expected one of {ENV_MODES}")
        if mode == "local" or mode == "none":
            return cls(mode)
        env = cls(None)
        env._requested = mode
        return env

    def start_check_deadline(self, seconds: Optional[float]) -> None:
        """Bound all tool calls the calling thread makes from now on by one shared deadline."""
        self._local.deadline = None if seconds is None else time.monotonic() + seconds

    def _remaining(self) -> Optional[float]:
        """Seconds a tool call may take: the per-call timeout capped by the thread's deadline."""
        deadline = getattr(self._local, "deadline", None)
        if deadline is None:
            return self.timeout
        left = max(deadline - time.monotonic(), 0.0)
        return left if self.timeout is None else min(self.timeout, left)

    @property
    def mode(self) -> str:
        self._resolve()
        return self._mode or "none"

    @property
    def container(self) -> str:
        self._resolve()
        return self._container

    def _resolve(self) -> None:
        with self._lock:
            if self._mode is not None:
                return
            cached = self._read_cache()
            if cached is not None:
                self._mode, self._container = cached
                return
            in_container = os.path.exists("/.dockerenv") or bool(os.environ.get("REMOTE_CONTAINERS"))
            if self._requested == "auto" and in_container:
                self._mode, self._container = "local", ""
            else:
                found = self._find_container()
                self._mode, self._container = ("docker", found) if found else ("none", "")
            self._write_cache()

    def _read_cache(self) -> Optional[Tuple[str, str]]:
        if self.cache_file is None:
            return None
        try:
            data = json.loads(self.cache_file.read_text())
            fresh = time.time() - float(data["ts"]) < ENV_CACHE_TTL.get(data["mode"], 0)
            if data["requested"] == self._requested and fresh:
                return data["mode"], data["container"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def _write_cache(self) -> None:
        if self.cache_file is None:
            return
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps({
                "requested": self._requested, "mode": self._mode,
                "container": self._container, "ts": time.time(),
            }))
        except OSError:
            pass

    def _find_container(self) -> str:
        name = repo_config.load(self._main_root(self.repo)).container_name if self.repo else ""
        if not name or not shutil.which("docker"):
            return ""
        try:
            proc = subprocess.run(
                ["docker", "ps", "--filter", f"name={name}", "--format", "{{.Names}}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                universal_newlines=True,
                timeout=DOCKER_PS_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        names = proc.stdout.split()
        return names[0] if proc.returncode == 0 and names else ""

    @staticmethod
    def _main_root(repo: Path) -> Path:
        common = gitutil.common_dir(str(repo))
        return common.parent if common else repo

    @property
    def has_tools(self) -> bool:
        return self.mode in ("local", "docker")

    def describe(self) -> str:
        if self.mode == "docker":
            return f"docker (container {self.container})"
        return self.mode

    def container_root(self, repo: Path) -> Tuple[Optional[str], str]:
        """Path of repo inside the container, or (None, reason). Worktrees must live below the
        main checkout, which is what the devcontainer mounts."""
        key = str(repo)
        if key in self._visible:
            return self._visible[key], ""
        main_root = self._main_root(repo)
        cfg = repo_config.load(main_root)
        workspace = cfg.container_workspace or f"/workspaces/{main_root.name}"
        if repo == main_root:
            root = workspace
        elif main_root in repo.parents:
            root = workspace + "/" + str(repo.relative_to(main_root))
        else:
            return None, (
                f"worktree {repo} is outside the mounted checkout {main_root}; keep worktrees "
                f"under {main_root}/.worktrees/ so the devcontainer sees them"
            )
        probe = subprocess.run(
            ["docker", "exec", self.container, "test", "-d", root],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        if probe.returncode != 0:
            return None, f"{repo} is not visible in container {self.container} at {root}"
        self._visible[key] = root
        return root, ""

    def run_tool(
        self,
        repo: Path,
        argv: Sequence[str],
        cwd: str = ".",
        stdin: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, str]:
        """Run argv where the devcontainer tools live: here (local) or through docker exec."""
        if self.mode == "local":
            # A login shell, as in docker mode, so tools in profile-added dirs (uv in
            # ~/.local/bin) resolve even when git or an IDE starts the hook with a bare PATH.
            return self.run_local(repo, argv, cwd, stdin, env, login=True)
        if self.mode != "docker":
            return 1, "no devcontainer available"
        root, reason = self.container_root(repo)
        if root is None:
            return 1, f"error: {reason}"
        command: List[str] = ["docker", "exec", "-i", "-e", "BASH_ENV="]
        for key, value in {**preamble_env(repo), **(env or {})}.items():
            command += ["-e", f"{key}={value}"]
        command += [self.container, "bash", "-lc", PREAMBLE, "bash", root, cwd, *argv]
        return _run(command, stdin, timeout=self._remaining())

    def run_local(
        self,
        repo: Path,
        argv: Sequence[str],
        cwd: str = ".",
        stdin: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        login: bool = False,
        profile_fallback: bool = False,
    ) -> Tuple[int, str]:
        """Run argv on this machine with the repo's environment preamble (host-side tools).

        login puts the login profile's PATH first. profile_fallback also runs a login shell but
        keeps the caller's PATH first, so the profile only supplies tools the caller lacks.
        """
        full_env = {k: v for k, v in os.environ.items() if k != "BASH_ENV"}
        full_env.update(preamble_env(repo))
        full_env.update(env or {})
        if profile_fallback:
            full_env["AI_HOOKS_CALLER_PATH"] = full_env.get("PATH", "")
        shell = ["bash", "-lc"] if login or profile_fallback else ["bash", "-c"]
        return _run([*shell, PREAMBLE, "bash", str(repo), cwd, *argv], stdin, full_env, self._remaining())


def _kill_group(proc: "subprocess.Popen[str]") -> None:
    """Kill the tool and everything it spawned; grandchildren would keep the pipes open."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, AttributeError):
        proc.kill()


def _run(
    command: Sequence[str],
    stdin: Optional[str],
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
) -> Tuple[int, str]:
    if timeout is not None and timeout <= 0:
        raise ToolTimeout(f"{command[0]} not run: time budget exhausted")
    try:
        proc = subprocess.Popen(
            list(command),
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            env=env,
            start_new_session=True,
        )
    except OSError as exc:
        return 127, f"could not run {command[0]}: {exc}"
    try:
        output, _ = proc.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        try:
            proc.communicate(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass
        raise ToolTimeout(f"{command[0]} timed out after {timeout:.0f}s")
    except BaseException:
        _kill_group(proc)
        raise
    return proc.returncode, output
