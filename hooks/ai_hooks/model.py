# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Data model shared by checks, the dispatcher, and the CLI."""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Callable, Dict, Optional, Sequence, Tuple

from .record import factory, record

PASS = "pass"
FAIL = "fail"
SKIP = "skip"

MODES = ("fix", "check")
STAGES = ("session-start", "pre-tool", "create", "edit", "stop", "pre-commit", "commit-msg")


@record
class Result:
    status: str
    message: str = ""
    # A silent skip means a precondition (a repo capability) is absent, which is normal in
    # some checkouts; it is never reported to the user.
    silent: bool = False
    # The skip is because a tool or the devcontainer is unavailable, which the agent cannot fix.
    env: bool = False

    @classmethod
    def ok(cls, message: str = "") -> "Result":
        return cls(PASS, message)

    @classmethod
    def fail(cls, message: str) -> "Result":
        return cls(FAIL, message)

    @classmethod
    def skip(cls, message: str = "", silent: bool = False, env: bool = False) -> "Result":
        return cls(SKIP, message, silent, env)


@record(frozen=True)
class Check:
    """One check. Adding a check means defining one of these in ai_hooks/checks/.

    stages maps a stage name to the mode the check runs in at that stage. patterns are
    fnmatch globs over repo-relative paths (empty means every file). requires lists repo paths
    that must exist and unless lists repo paths whose presence disables the check, so a check
    never needs to know which checkout it is running in.
    """

    name: str
    description: str
    run: Callable[..., Result]
    stages: Dict[str, str] = factory(dict)
    modes: Tuple[str, ...] = ("check",)
    patterns: Tuple[str, ...] = ()
    requires: Tuple[str, ...] = ()
    unless: Tuple[str, ...] = ()
    needs_container: bool = False
    # At the stop stage, a missing devcontainer blocks instead of skipping.
    strict_stop: bool = False

    def matches(self, rel_path: str) -> bool:
        if not self.patterns:
            return True
        return any(fnmatchcase(rel_path, pattern) for pattern in self.patterns)

    def select(self, files: Sequence[str]) -> Sequence[str]:
        return [f for f in files if self.matches(f)]

    def validate(self) -> None:
        for stage, mode in self.stages.items():
            if stage not in STAGES:
                raise ValueError(f"check {self.name}: unknown stage {stage!r}")
            if mode not in self.modes:
                raise ValueError(f"check {self.name}: stage {stage!r} uses unsupported mode {mode!r}")


@record
class Outcome:
    """What the dispatcher tells a harness after running a stage."""

    blocked: bool = False
    message: str = ""
    warnings: Sequence[str] = ()
    detail: Optional[Sequence[Tuple[str, Result]]] = None
    # Facts for the model (SessionStart additionalContext).
    context: str = ""
