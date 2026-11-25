# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Execution context handed to every check."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

from .record import factory, record
from .execenv import ExecEnv


@record
class Context:
    repo: Path
    env: ExecEnv
    stage: str = "task"
    mode: str = "check"
    session_id: str = ""
    command: str = ""
    # Working directory of the tool call, used to find which repository a command targets.
    cwd: str = ""
    message_file: str = ""
    # True when the files are a git index snapshot, so line-level tools may use --staged.
    staged: bool = False
    extra: Dict[str, str] = factory(dict)

    def exists(self, rel_path: str) -> bool:
        return (self.repo / rel_path).exists()

    def tool(self, argv, cwd: str = ".", stdin: Optional[str] = None, env=None) -> Tuple[int, str]:
        """Run a devcontainer tool (clang-format, ruff via uv, ...)."""
        return self.env.run_tool(self.repo, argv, cwd, stdin, env)

    def local(self, argv, cwd: str = ".", stdin: Optional[str] = None, env=None) -> Tuple[int, str]:
        """Run a host-side tool (docs tooling, cmake) with the repo's environment preamble."""
        # The login profile fills in tools such as cmake when the IDE started the agent from a
        # shell (such as zsh) that never activated the workspace; the caller's PATH stays first.
        return self.env.run_local(self.repo, argv, cwd, stdin, env, profile_fallback=True)

    def derive(self, repo: Path, **changes) -> "Context":
        values = dict(self.__dict__)
        values.update(repo=repo, **changes)
        return Context(**values)
