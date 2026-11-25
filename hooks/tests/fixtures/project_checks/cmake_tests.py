# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Run the CMake test workflow after CMake files change. Linux tests run on the host."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from ai_hooks.model import Check, Result

PRESET = "cmake-tests-linux"
STALE = "is different than the directory"


def _cached_source(cache: Path) -> str:
    try:
        match = re.search(r"^CMAKE_HOME_DIRECTORY:INTERNAL=(.*)$", cache.read_text(), re.M)
    except OSError:
        return ""
    return match.group(1) if match else ""


def run(ctx, files):
    repo = ctx.repo
    env = {}
    # The configure-time resolver needs the CLI's Python dependencies.
    venv = repo / "cli" / ".venv"
    if not os.environ.get("VIRTUAL_ENV") and (venv / "bin" / "python").exists():
        env["VIRTUAL_ENV"] = str(venv)
        env["PATH"] = f"{venv / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"

    # A build dir copied in from another checkout keeps a cache that points at the old paths,
    # which CMake refuses to reuse; it is regenerable, so drop it instead of failing forever.
    build_dir = repo / "build" / PRESET
    cached = _cached_source(build_dir / "CMakeCache.txt")
    if cached and cached != str(repo):
        shutil.rmtree(str(build_dir), ignore_errors=True)

    command = ["cmake", "--workflow", "--preset", PRESET]
    rc, out = ctx.local(command, env=env)
    if rc != 0 and STALE in out:
        shutil.rmtree(str(build_dir), ignore_errors=True)
        rc, out = ctx.local(command, env=env)
    if rc == 0:
        return Result.ok()
    return Result.fail(f"{PRESET} failed after CMake file changes:\n{out}")


CHECK = Check(
    name="cmake-tests",
    description="cmake --workflow --preset cmake-tests-linux after CMake files change",
    run=run,
    stages={"stop": "check"},
    patterns=("cmake/*", "CMakeLists.txt", "*/CMakeLists.txt", "*.cmake", "CMakePresets.json"),
    requires=("CMakePresets.json",),
)
