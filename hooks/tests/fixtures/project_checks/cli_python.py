# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""The cli/ Python project: ruff on edit and commit, the full task gate before stopping, and
the devcontainer venv it needs."""

from __future__ import annotations

from ai_hooks.model import Check, Result

PATTERNS = ("cli/*.py", "cli/pyproject.toml", "cli/uv.lock")
PROJECT = "cli/pyproject.toml"


def run_ruff(ctx, files):
    if ctx.mode == "fix":
        relative = [f[len("cli/"):] for f in files if f.endswith(".py")]
        if not relative:
            return Result.ok()
        script = 'uv run ruff format "$@" && uv run ruff check --fix "$@"'
        rc, out = ctx.tool(["sh", "-c", script, "sh", *relative], cwd="cli")
        return Result.ok() if rc == 0 else Result.fail(f"ruff format/lint-fix failed:\n{out}")
    if ctx.stage == "pre-commit":
        rc, out = ctx.tool(
            ["sh", "-c", "uv run --locked task format-check && uv run --locked task lint"],
            cwd="cli",
        )
        return Result.ok() if rc == 0 else Result.fail(f"CLI formatting/lint checks failed:\n{out}")
    relative = [f[len("cli/"):] for f in files]
    script = 'uv run ruff format --check "$@" && uv run ruff check "$@"'
    rc, out = ctx.tool(["sh", "-c", script, "sh", *relative], cwd="cli")
    return Result.ok() if rc == 0 else Result.fail(f"ruff format/lint issues:\n{out}")


def run_gate(ctx, files):
    rc, out = ctx.tool(["uv", "run", "task", "check"], cwd="cli")
    if rc == 0:
        return Result.ok()
    return Result.fail(
        f"CLI checks (task check: lint-all + test) failed after Python file changes:\n{out}"
    )


def run_venv(ctx, files):
    rc, _ = ctx.tool(["test", "-x", "cli/.venv/bin/python"])
    if rc == 0:
        return Result.ok()
    rc, out = ctx.tool(["uv", "sync"], cwd="cli")
    return Result.ok() if rc == 0 else Result.fail(f"failed to create cli/.venv in the devcontainer:\n{out}")


CHECKS = [
    Check(
        name="cli-python",
        description="ruff format and lint for cli/ (fix on edit, check on commit)",
        run=run_ruff,
        stages={"edit": "fix", "pre-commit": "check"},
        modes=("fix", "check"),
        patterns=PATTERNS,
        requires=(PROJECT,),
        needs_container=True,
    ),
    Check(
        name="cli-gate",
        description="Full cli/ gate (task check: lint, typecheck, tests) before the agent stops",
        run=run_gate,
        stages={"stop": "check"},
        patterns=PATTERNS,
        requires=(PROJECT,),
        needs_container=True,
        strict_stop=True,
    ),
    Check(
        name="cli-venv",
        description="Make sure cli/.venv works inside the devcontainer",
        run=run_venv,
        stages={"session-start": "fix"},
        modes=("fix",),
        requires=(PROJECT,),
        needs_container=True,
    ),
]
