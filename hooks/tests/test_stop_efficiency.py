# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Stop-loop control, concurrency, output limits, lazy environment detection, and guards."""

from __future__ import annotations

import json
import time
import unittest
from pathlib import Path

try:
    from .helpers import RepoTestCase, STUB, write_executable
except ImportError:  # discovered with `-s tests` and no `-t .`
    from helpers import RepoTestCase, STUB, write_executable

from ai_hooks import hooks, registry
from ai_hooks.context import Context
from ai_hooks.execenv import ExecEnv, ToolTimeout
from ai_hooks.model import Check, Result


def edit(path):
    return {"tool_name": "Edit", "tool_input": {"file_path": path}}


class StopLoopTest(RepoTestCase):
    def _failing_stop(self, rel="lib/a.cpp"):
        path = self.touch_file(rel)
        self.run_hook("PostToolUse", edit(path))
        out = self.run_hook("Stop", {}, FAKE_DOCKER_RC="1")[1]
        self.assertEqual(json.loads(out)["decision"], "block")
        self.docker_log.unlink()
        return path

    def test_stop_hook_active_with_unchanged_tree_allows_stop_without_running(self):
        self._failing_stop()
        rc, out, _ = self.run_hook("Stop", {"stop_hook_active": True}, FAKE_DOCKER_RC="1")
        message = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertNotIn("decision", message)
        self.assertIn("clang-tidy", message["systemMessage"])
        self.assertEqual(self.docker_calls(), [])

    def test_changed_fingerprint_reruns_even_when_stop_hook_is_active(self):
        path = self._failing_stop()
        Path(path).write_text("int changed;\n")
        _, out, _ = self.run_hook("Stop", {"stop_hook_active": True}, FAKE_DOCKER_RC="1")
        self.assertEqual(json.loads(out)["decision"], "block")
        self.assertEqual(len(self.docker_calls()), 1)

    def test_a_check_that_passed_on_the_current_fingerprint_is_not_rerun(self):
        self.run_hook("PostToolUse", edit(self.touch_file("lib/a.cpp")))
        self.run_hook("Stop", {})
        self.docker_log.unlink()
        self.run_hook("Stop", {"stop_hook_active": True})
        self.assertEqual(self.docker_calls(), [])

    def test_failure_output_is_capped_per_check_and_in_total(self):
        self.run_hook("PostToolUse", edit(self.touch_file("lib/a.cpp")))
        noise = "\n".join(f"line {i}" for i in range(500))
        _, out, _ = self.run_hook("Stop", {}, FAKE_DOCKER_RC="1", FAKE_DOCKER_OUT=noise)
        reason = json.loads(out)["reason"]
        self.assertLessEqual(len(reason), 4000)
        self.assertNotIn("line 100\n", reason)
        self.assertIn("line 499", reason)


class UnitTest(unittest.TestCase):
    def test_cap_failures_truncates_to_the_limit(self):
        text = hooks.cap_failures(["x" * 3000, "y" * 3000])
        self.assertLessEqual(len(text), hooks.MAX_TOTAL_CHARS)
        self.assertTrue(text.endswith("truncated"))

    def test_fix_hint_is_kept_once(self):
        text = registry.dedupe_fix_hint("a\nFix with: x\nb\nFix with: x\n")
        self.assertEqual(text.count("Fix with:"), 1)

    def test_independent_checks_run_concurrently_within_the_budget(self):
        def slow(ctx, files):
            time.sleep(0.5)
            return Result.ok()

        checks = [Check(name=f"c{i}", description="", run=slow, stages={"stop": "check"}) for i in range(3)]
        ctx = Context(repo=Path("."), env=ExecEnv("none"))
        tasks = [(c, ctx, [], []) for c in checks]
        start = time.time()
        results = hooks._run_concurrently(tasks)
        self.assertLess(time.time() - start, 1.2)
        self.assertEqual([r.status for _, r in results], ["pass"] * 3)

    def test_a_check_over_budget_is_skipped_not_failed(self):
        check = Check(name="slow", description="", run=lambda c, f: time.sleep(1) or Result.ok(),
                      stages={"stop": "check"})
        ctx = Context(repo=Path("."), env=ExecEnv("none"))
        saved = hooks.STOP_WAIT_BUDGET
        hooks.STOP_WAIT_BUDGET = 0.1
        try:
            (_, result), = hooks._run_concurrently([(check, ctx, [], [])])
        finally:
            hooks.STOP_WAIT_BUDGET = saved
        self.assertEqual((result.status, result.env), ("skip", True))

    def test_tool_timeout_becomes_an_environment_skip(self):
        env = ExecEnv("local")
        env.timeout = 0.2
        with self.assertRaises(ToolTimeout):
            env.run_local(Path("."), ["sleep", "5"])
        check = Check(name="t", description="", run=lambda c, f: c.local(["sleep", "5"]) and Result.ok(),
                      stages={"stop": "check"})
        ctx = Context(repo=Path("."), env=env, stage="stop")
        result = registry.execute(check, ctx, [], "check")
        self.assertEqual((result.status, result.env), ("skip", True))
        self.assertIn("timed out", result.message)


class LazyEnvAndGuardsTest(RepoTestCase):
    def test_pre_tool_bash_never_calls_docker(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "git commit --signoff -m x"}}
        self.run_hook("PreToolUse", payload)
        self.assertFalse(self.docker_log.exists())

    def test_session_start_probes_docker_once_and_caches_it(self):
        self.run_hook("SessionStart", {}, AI_HOOKS_ENV="docker")
        self.run_hook("SessionStart", {}, AI_HOOKS_ENV="docker")
        pings = [line for line in self.docker_log.read_text().splitlines() if '"ps"' in line]
        self.assertEqual(len(pings), 1)

    def test_cli_python_edit_runs_ruff_on_the_edited_files_only(self):
        self.run_hook("PostToolUse", edit(self.touch_file("cli/src/mod.py")))
        script = [c for c in self.docker_calls() if c["cwd"] == "cli"][0]["command"]
        self.assertEqual(script[:2], ["sh", "-c"])
        self.assertIn("ruff format", script[2])
        self.assertIn("ruff check --fix", script[2])
        self.assertEqual(script[4:], ["src/mod.py"])

    def test_graphify_guard_without_a_graph_is_silent_success(self):
        write_executable(self.bin / "graphify", STUB)
        rc, out, err = self.run_cli("graphify-guard", "search")
        self.assertEqual((rc, out, err), (0, "", ""))
        self.assertEqual(self.stub_calls(), [])

    def test_graphify_guard_with_a_graph_runs_hook_guard(self):
        write_executable(self.bin / "graphify", STUB)
        self.touch_file("graphify-out/graph.json", "{}")
        self.run_cli("graphify-guard", "read")
        self.assertEqual(self.stub_calls(), ["graphify hook-guard read"])

    def test_session_start_mentions_graphify_only_when_a_graph_exists(self):
        self.assertNotIn("graphify", self.run_hook("SessionStart", {})[1])
        self.touch_file("graphify-out/graph.json", "{}")
        out = json.loads(self.run_hook("SessionStart", {})[1])
        self.assertIn("graphify query", out["hookSpecificOutput"]["additionalContext"])

    def test_compact_emits_the_bundled_workflow_invariants(self):
        rc, out, _ = self.run_cli("hook", "SessionStart", "--emit-invariants")
        context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(rc, 0)
        self.assertIn("Signed-off-by", context)
        self.assertLess(len(context.split()), 300)

    def test_compact_prefers_the_project_invariants(self):
        self.touch_file(".ai-hooks/invariants.md", "Never use `std::`.\n")
        rc, out, _ = self.run_cli("hook", "SessionStart", "--emit-invariants")
        context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertEqual((rc, context), (0, "Never use `std::`."))


if __name__ == "__main__":
    unittest.main()
