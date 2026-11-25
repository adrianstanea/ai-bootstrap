# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""BSD-3-Clause license headers, via the host repo's check_license_headers.py."""

from __future__ import annotations

from ..model import Check, Result

SCRIPT = "scripts/check_license_headers.py"


def run(ctx, files):
    flag = "--fix" if ctx.mode == "fix" else "--check"
    rc, out = ctx.tool(["python3", SCRIPT, flag, "--files", "-"], stdin="\n".join(files) + "\n")
    if rc == 0:
        return Result.ok()
    return Result.fail(f"license header {ctx.mode} failed:\n{out}")


CHECK = Check(
    name="license-header",
    description="Inject (on file creation) or verify (on commit) the license header",
    run=run,
    stages={"create": "fix", "pre-commit": "check"},
    modes=("fix", "check"),
    requires=(SCRIPT,),
    needs_container=True,
)
