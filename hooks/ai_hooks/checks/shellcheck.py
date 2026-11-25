# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""ShellCheck for shell scripts, on edit and on commit.

Severity and `source` handling come from the repository's `.shellcheckrc`, so the hook and a
manual `shellcheck` run agree. Findings at warning level and above fail the check.
"""

from __future__ import annotations

from ..model import Check, Result

# Extensionless git hook scripts (.githooks/ in projects, githooks/ here) have no `.sh` suffix.
PATTERNS = ("*.sh", ".githooks/*", "githooks/*")
SEVERITY = "warning"


def run(ctx, files):
    rc, out = ctx.local(["shellcheck", "--severity", SEVERITY, "--", *files])
    if rc == 127:
        if ctx.stage == "pre-commit":
            return Result.fail("shellcheck is not installed; install it and try again")
        return Result.skip("shellcheck skipped: shellcheck is not installed", env=True)
    if rc != 0:
        return Result.fail(f"shellcheck findings:\n{out}\nFix with: shellcheck -x <file>")
    return Result.ok()


CHECK = Check(
    name="shellcheck",
    description="ShellCheck shell scripts (warning and above) on edit and commit",
    run=run,
    stages={"edit": "check", "pre-commit": "check"},
    patterns=PATTERNS,
)
