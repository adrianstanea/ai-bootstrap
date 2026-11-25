# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Stop cache validity, per-root results, concurrent state writes, and process-group kills."""

from __future__ import annotations

import multiprocessing
import os
import tempfile
import time
import unittest
from pathlib import Path

try:
    from .helpers import RepoTestCase
except ImportError:  # discovered with `-s tests` and no `-t .`
    from helpers import RepoTestCase

from ai_hooks import hooks
from ai_hooks.execenv import ExecEnv, ToolTimeout
from ai_hooks.state import SessionState


def edit(path):
    return {"tool_name": "Edit", "tool_input": {"file_path": path}}


class StopCacheTest(RepoTestCase):
    def test_a_file_changed_outside_hooks_after_passing_is_checked_again(self):
        path = self.touch_file("lib/a.cpp")
        self.run_hook("PostToolUse", edit(path))
        self.run_hook("Stop", {})
        self.docker_log.unlink()
        Path(path).write_text("int changed_by_sed;\n")  # no PostToolUse: a Bash `sed -i`
        self.run_hook("Stop", {})
        self.assertEqual(len(self.docker_calls()), 1)

    def test_an_untouched_file_is_not_checked_again(self):
        path = self.touch_file("lib/a.cpp")
        self.run_hook("PostToolUse", edit(path))
        self.run_hook("Stop", {})
        self.docker_log.unlink()
        self.run_hook("Stop", {})
        self.assertEqual(self.docker_calls(), [])


class SessionStateTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="ai-hooks-state-"))
        self.addCleanup(__import__("shutil").rmtree, str(self.dir), True)

    def test_pending_detects_content_change(self):
        f = self.dir / "f.txt"
        f.write_text("a")
        state = SessionState(self.dir / "st", "s")
        state.mark_passed("c", [str(f)])
        self.assertEqual(state.pending("c", [str(f)]), [])
        f.write_text("bb")
        self.assertEqual(state.pending("c", [str(f)]), [str(f)])

    def test_a_failure_in_one_root_is_not_masked_by_a_pass_in_another(self):
        state = SessionState(self.dir / "st", "s")
        state.record("c", "fp1", "fail", "/root/a")
        state.record("c", "fp1", "pass", "/root/b")
        self.assertFalse(state.passed_at("c", "fp1"))
        state.record("c", "fp1", "pass", "/root/a")
        self.assertTrue(state.passed_at("c", "fp1"))
        self.assertFalse(state.passed_at("c", "fp2"))

    def test_concurrent_saves_keep_every_file(self):
        directory = self.dir / "st"
        files = []
        for i in range(8):
            f = self.dir / f"f{i}"
            f.write_text("x")
            files.append(str(f))
        ctx = multiprocessing.get_context("fork")
        procs = [ctx.Process(target=_touch_and_save, args=(directory, f)) for f in files]
        for p in procs:
            p.start()
        for p in procs:
            p.join()
        self.assertTrue(all(p.exitcode == 0 for p in procs))
        self.assertEqual(sorted(SessionState(directory, "s").files), sorted(files))


def _touch_and_save(directory, path):
    state = SessionState(directory, "s")
    time.sleep(0.05)  # all processes load before any saves
    state.touch(path)
    state.save()


class ProcessGroupTest(unittest.TestCase):
    def test_timeout_kills_grandchildren(self):
        pidfile = Path(tempfile.mkdtemp(prefix="ai-hooks-pg-")) / "pid"
        env = ExecEnv("local")
        env.timeout = 0.5
        start = time.time()
        with self.assertRaises(ToolTimeout):
            env.run_local(Path("."), ["bash", "-c", f"sleep 60 & echo $! > {pidfile}; wait"])
        self.assertLess(time.time() - start, 10)
        pid = int(pidfile.read_text())
        time.sleep(0.2)
        with self.assertRaises(OSError):
            os.kill(pid, 0)

    def test_tool_calls_share_one_check_deadline(self):
        env = ExecEnv("local")
        env.timeout = 10
        env.start_check_deadline(0.6)
        env.run_local(Path("."), ["sleep", "0.4"])
        with self.assertRaises(ToolTimeout):
            env.run_local(Path("."), ["sleep", "0.4"])
        with self.assertRaises(ToolTimeout):  # exhausted: not even started
            env.run_local(Path("."), ["true"])

    def test_overrun_marks_stragglers(self):
        from ai_hooks.context import Context
        from ai_hooks.model import Check, Result

        check = Check(name="slow", description="", run=lambda c, f: time.sleep(0.5) or Result.ok(),
                      stages={"stop": "check"})
        saved, hooks.STOP_WAIT_BUDGET, hooks.stragglers = hooks.STOP_WAIT_BUDGET, 0.05, False
        try:
            hooks._run_concurrently([(check, Context(repo=Path("."), env=ExecEnv("none")), [], [])])
            self.assertTrue(hooks.stragglers)
        finally:
            hooks.STOP_WAIT_BUDGET, hooks.stragglers = saved, False


if __name__ == "__main__":
    unittest.main()
