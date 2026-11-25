# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Small git helpers. All of them tolerate a missing repository by returning None/empty."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence


def _git(cwd: str, *args: str) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
        )
    except (OSError, ValueError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _existing_dir(path: str) -> str:
    current = Path(path)
    while not current.is_dir() and current != current.parent:
        current = current.parent
    return str(current)


def toplevel(path: str) -> Optional[Path]:
    """Root of the worktree that contains path, which need not exist yet."""
    out = _git(_existing_dir(path), "rev-parse", "--show-toplevel")
    return Path(out).resolve() if out else None


def common_dir(path: str) -> Optional[Path]:
    out = _git(_existing_dir(path), "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(out).resolve() if out else None


def is_ignored(repo: Path, rel_path: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "-q", "--", rel_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def _lines(out: Optional[str]) -> List[str]:
    return [line for line in (out or "").splitlines() if line]


def staged_files(repo: Path) -> List[str]:
    return _lines(_git(str(repo), "diff", "--cached", "--name-only", "--diff-filter=ACMR"))


def changed_since(repo: Path, base: str) -> List[str]:
    return _lines(_git(str(repo), "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"))


def tracked_files(repo: Path) -> List[str]:
    return _lines(_git(str(repo), "ls-files"))


def relative_to(repo: Path, absolute: str) -> Optional[str]:
    try:
        return os.path.relpath(os.path.realpath(absolute), str(repo)) if absolute else None
    except ValueError:
        return None


def fingerprint(repo: Path, extra_files: Sequence[str] = ()) -> str:
    """Hash of the paths and (mtime, size) of files changed vs HEAD, untracked files, and extras."""
    names = set(_lines(_git(str(repo), "diff", "--name-only", "HEAD")))
    names.update(_lines(_git(str(repo), "ls-files", "--others", "--exclude-standard")))
    import hashlib

    digest = hashlib.sha1()
    entries = [(name, str(repo / name)) for name in names] + [(p, p) for p in extra_files]
    for label, path in sorted(entries):
        try:
            st = os.stat(path)
            stamp = f"{st.st_mtime_ns}:{st.st_size}"
        except OSError:
            stamp = "gone"
        digest.update(f"{label}\0{stamp}\0".encode())
    return digest.hexdigest()
