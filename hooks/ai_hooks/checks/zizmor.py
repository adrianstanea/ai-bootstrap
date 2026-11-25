# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Run zizmor through its upstream pre-commit hook for staged YAML files."""

from __future__ import annotations

import os

from ..model import Check, Result

CONFIG = ".pre-commit-config.yaml"


def run(ctx, files):
    command = [
        "uvx",
        "pre-commit",
        "run",
        "zizmor",
        "--config",
        os.environ.get("AI_HOOKS_PRE_COMMIT_CONFIG", CONFIG),
        "--files",
        *files,
    ]
    rc, out = ctx.local(command)
    if rc != 0:
        return Result.fail(f"zizmor pre-commit hook failed:\n{out}")
    return Result.ok(out.strip())


CHECK = Check(
    name="zizmor",
    description="Scan staged GitHub Actions YAML with zizmor",
    run=run,
    stages={"pre-commit": "check"},
    patterns=("*.yaml", "*.yml"),
)
