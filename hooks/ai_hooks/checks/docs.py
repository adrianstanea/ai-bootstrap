# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Markdown and RST via the host repo's scripts/docs-tooling.sh (pure Python, runs on the host)."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import List

from .. import gitutil
from ..model import Check, Result

TOOL = "./scripts/docs-tooling.sh"

DOC_TREE_DIRS = frozenset({"doc", "docs"})
TERMINAL_LANGUAGES = frozenset({"bash", "sh", "shell", "console", "shell-session", "shellsession", "zsh"})
_CODE_DIRECTIVE = re.compile(r"^\s*\.\.\s+(code-block|code|sourcecode)::\s*(\S+)", re.IGNORECASE)
SHELL_HINT = "use `.. shell::` for terminal sessions in doc trees and RST READMEs"


def in_doc_tree(rel: str) -> bool:
    """Include documentation trees and co-located RST READMEs rendered by doctools."""
    path = PurePosixPath(rel)
    if path.suffix != ".rst":
        return False
    return path.name == "README.rst" or any(part in DOC_TREE_DIRS for part in path.parts[:-1])


def shell_directive_findings(rel: str, text: str) -> List[str]:
    if rel == "README.rst":
        return []

    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        match = _CODE_DIRECTIVE.match(line)
        if match and match.group(2).lower() in TERMINAL_LANGUAGES:
            directive = f".. {match.group(1)}:: {match.group(2)}"
            findings.append(f"{rel}:{number}: `{directive}`: {SHELL_HINT}")
    return findings


def _shell_directive_problems(ctx, files) -> List[str]:
    findings: List[str] = []
    for rel in files:
        if not in_doc_tree(rel):
            continue
        path = ctx.repo / rel
        if path.is_file():
            findings += shell_directive_findings(rel, path.read_text(errors="replace"))
    return findings


def run(ctx, files):
    # Gitignored files (personal, session-local) never gate anything.
    files = [f for f in files if not gitutil.is_ignored(ctx.repo, f)]
    if not files:
        return Result.skip(silent=True)

    if ctx.mode == "fix":
        for rel in files:
            rc, out = ctx.local([TOOL, "format", rel])
            if rc != 0:
                return Result.fail(f"docs-tooling.sh format failed on {rel}:\n{out}")
        return Result.ok()

    listing = "\n".join(files) + "\n"
    problems = []
    rc, out = ctx.local([TOOL, "format", "--check", "--fromstdin", "-"], stdin=listing)
    if rc != 0:
        problems.append(out)
    rc, out = ctx.local([TOOL, "lint", "--fromstdin", "-"], stdin=listing)
    if rc != 0:
        problems.append(out)
    shell = _shell_directive_problems(ctx, files)
    if shell:
        problems.append("\n".join(shell))
    if problems:
        return Result.fail("Doc format/lint issues in touched .md/.rst files:\n" + "\n".join(problems))
    return Result.ok()


CHECK = Check(
    name="docs",
    description=(
        "Format Markdown/RST on edit; lint and format-check .md/.rst and require `.. shell::` for"
        " terminal sessions in doc trees and RST READMEs before stopping or committing"
    ),
    run=run,
    stages={"edit": "fix", "stop": "check", "pre-commit": "check"},
    modes=("fix", "check"),
    patterns=("*.md", "*.rst"),
    requires=(TOOL,),
)
