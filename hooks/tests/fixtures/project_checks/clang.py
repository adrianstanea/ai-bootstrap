# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""C/C++ formatting and static analysis; both run where clang lives (the devcontainer)."""

from __future__ import annotations

from ai_hooks import gitutil
from ai_hooks.model import Check, Result

CPP = ("*.c", "*.cpp", "*.h", "*.hpp")
CLANG_FORMAT = "clang-format-22"
RUNNER = "./scripts/run-clang-tidy.sh"


def run_clang_format(ctx, files):
    if ".clang-format" in files:
        files = [f for f in gitutil.tracked_files(ctx.repo) if f.endswith((".c", ".cpp", ".h", ".hpp"))]
    if ctx.mode == "fix":
        rc, out = ctx.tool([CLANG_FORMAT, "-i", *files])
        return Result.ok() if rc == 0 else Result.fail(f"clang-format failed:\n{out}")
    rc, out = ctx.tool([CLANG_FORMAT, "--dry-run", "--Werror", *files])
    hint = f"{CLANG_FORMAT} -i <files>"
    if rc == 0:
        return Result.ok()
    return Result.fail(f"C/C++ formatting issues:\n{out}\nFix with: {hint}")


def run_clang_tidy(ctx, files):
    flag = "--fix" if ctx.mode == "fix" else "--check"
    rc, out = ctx.tool([RUNNER, flag, "--fromstdin", "-"], stdin="\n".join(files) + "\n")
    if rc == 0:
        return Result.ok()
    return Result.fail(
        f"clang-tidy found issues in the touched C/C++ files:\n{out}\n"
        f"Fix them, or run {RUNNER} --fix --fromstdin - with the same file list."
    )


CHECKS = [
    Check(
        name="clang-format",
        description="Format C/C++ with clang-format (fix on edit, check on commit)",
        run=run_clang_format,
        stages={"edit": "fix", "pre-commit": "check"},
        modes=("fix", "check"),
        patterns=(*CPP, ".clang-format"),
        requires=(".clang-format",),
        needs_container=True,
    ),
    Check(
        name="clang-tidy",
        description="clang-tidy on touched C/C++ files, mirroring clang_tidy.yml in CI",
        run=run_clang_tidy,
        stages={"stop": "check", "pre-commit": "check"},
        modes=("fix", "check"),
        patterns=CPP,
        requires=(RUNNER,),
        needs_container=True,
        strict_stop=True,
    ),
]
