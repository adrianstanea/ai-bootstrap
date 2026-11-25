# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Per-session record of edited files and which checks already passed on them.

It lives under the git common directory, so it is shared by every worktree of a checkout, is
never part of the tree, and needs no ignore rules.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from . import gitutil

STALE_AFTER_SECONDS = 7 * 24 * 3600


class SessionState:
    def __init__(self, directory: Path, session_id: str) -> None:
        self.path = directory / f"{session_id or 'nosession'}.json"
        self.files: List[str] = []
        # check -> file -> [mtime_ns, size] at the time it passed
        self.passed: Dict[str, Dict[str, List[int]]] = {}
        self.stop_blocks = 0
        # Per-check outcome keyed by the work-tree fingerprint it was computed for.
        self.results: Dict[str, dict] = {}
        self.last_block_fp = ""
        self.last_failing: List[str] = []
        self.env_notified: List[str] = []
        self._load()

    @classmethod
    def for_repo(cls, repo: Path, session_id: str) -> Optional["SessionState"]:
        common = gitutil.common_dir(str(repo))
        if common is None:
            return None
        return cls(common / "ai-hooks" / "state", session_id)

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        self.files = [f for f in data.get("files", []) if os.path.exists(f)]
        passed = data.get("passed", {})
        self.passed = {
            name: done for name, done in passed.items() if isinstance(done, dict)
        } if isinstance(passed, dict) else {}
        self.stop_blocks = int(data.get("stop_blocks", 0))
        self.results = data.get("results", {})
        self.last_block_fp = data.get("last_block_fp", "")
        self.last_failing = data.get("last_failing", [])
        self.env_notified = data.get("env_notified", [])

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Advisory lock around read-modify-write; a no-op where fcntl is unavailable."""
        try:
            import fcntl
        except ImportError:
            yield
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = open(str(self.path) + ".lock", "a")
        except OSError:
            yield
            return
        with handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def save(self) -> None:
        """Merge with what other hook processes wrote since load, then replace atomically."""
        with self._locked():
            self._merge_from_disk()
            tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
            data = {
                "files": self.files,
                "passed": self.passed,
                "stop_blocks": self.stop_blocks,
                "results": self.results,
                "last_block_fp": self.last_block_fp,
                "last_failing": self.last_failing,
                "env_notified": self.env_notified,
            }
            try:
                tmp.write_text(json.dumps(data))
                os.replace(str(tmp), str(self.path))
            finally:
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def _merge_from_disk(self) -> None:
        """Union in files and notifications another process saved; ours win for the rest."""
        try:
            disk = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        for name in disk.get("files", []):
            if name not in self.files and os.path.exists(name):
                self.files.append(name)
        for key in disk.get("env_notified", []):
            if key not in self.env_notified:
                self.env_notified.append(key)

    def touch(self, absolute: str) -> None:
        if absolute not in self.files:
            self.files.append(absolute)
        # An edited file must be verified again by every check.
        for done in self.passed.values():
            done.pop(absolute, None)

    @staticmethod
    def _stamp(absolute: str) -> Optional[List[int]]:
        try:
            st = os.stat(absolute)
        except OSError:
            return None
        return [st.st_mtime_ns, st.st_size]

    def pending(self, check_name: str, candidates: List[str]) -> List[str]:
        """Files not yet verified, or changed on disk since they passed (any writer)."""
        done = self.passed.get(check_name, {})
        return [f for f in candidates if f not in done or done[f] != self._stamp(f)]

    def mark_passed(self, check_name: str, files: List[str]) -> None:
        done = self.passed.setdefault(check_name, {})
        for f in files:
            stamp = self._stamp(f)
            if stamp is not None:
                done[f] = stamp

    def prune_stale(self) -> None:
        directory = self.path.parent
        if not directory.is_dir():
            return
        cutoff = time.time() - STALE_AFTER_SECONDS
        for entry in directory.glob("*.json"):
            try:
                if entry.stat().st_mtime < cutoff:
                    entry.unlink()
            except OSError:
                pass

    def passed_at(self, check_name: str, fingerprint: str) -> bool:
        entry = self.results.get(check_name, {})
        roots = entry.get("roots") or {}
        return entry.get("fp") == fingerprint and bool(roots) and all(v == "pass" for v in roots.values())

    def record(self, check_name: str, fingerprint: str, status: str, root: str = "") -> None:
        """Keep one outcome per (check, root) for the fingerprint; passed_at needs all to pass."""
        entry = self.results.get(check_name, {})
        if entry.get("fp") != fingerprint:
            entry = {"fp": fingerprint, "roots": {}}
        entry["roots"][root] = status
        self.results[check_name] = entry

    def notify_env_once(self, key: str) -> bool:
        """True the first time key is reported in this session."""
        if key in self.env_notified:
            return False
        self.env_notified.append(key)
        return True
