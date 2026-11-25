# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""End to end: the real launcher, a throwaway repo, a fake docker, and stub tools.

The expectations in the parity tests are the commands the old per-tool shell hooks and
.githooks/pre-commit issued, so a change here that alters them is a behaviour change.
"""

from __future__ import annotations

import json
import os

try:
    from .helpers import HOOKS_DIR, RepoTestCase, write_executable
except ImportError:  # discovered with `-s tests` and no `-t .`
    from helpers import HOOKS_DIR, RepoTestCase, write_executable

ROOT = "/workspaces/example"


def edit(path, tool="Edit"):
    return {"tool_name": tool, "tool_input": {"file_path": path}}


class EditStageTest(RepoTestCase):
    def test_cpp_edit_runs_clang_format_in_the_container(self):
        path = self.touch_file("lib/a.cpp")
        rc, out, _ = self.run_hook("PostToolUse", edit(path))
        self.assertEqual((rc, out), (0, ""))
        calls = self.docker_calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["root"], ROOT)
        self.assertEqual(calls[0]["command"], ["clang-format-22", "-i", "lib/a.cpp"])

    def test_new_file_gets_a_license_header_and_other_files_do_not(self):
        created = self.touch_file("lib/new.cpp")
        self.run_hook("PostToolUse", edit(created, "Write"))
        commands = [c["command"] for c in self.docker_calls()]
        self.assertIn(["python3", "scripts/check_license_headers.py", "--fix", "--files", "-"], commands)
        self.docker_log.unlink()
        self.run_hook("PostToolUse", edit(created, "Edit"))
        self.assertNotIn("check_license_headers.py", json.dumps(self.docker_calls()))

    def test_files_outside_the_repo_are_ignored(self):
        outside = self.tmp / "elsewhere.cpp"
        outside.write_text("x")
        self.run_hook("PostToolUse", edit(str(outside)))
        self.assertEqual(self.docker_calls(), [])

    def test_markdown_is_formatted_on_the_host_not_in_the_container(self):
        path = self.touch_file("docs/a.md")
        self.run_hook("PostToolUse", edit(path))
        self.assertEqual(self.docker_calls(), [])
        self.assertEqual(self.stub_calls(), ["docs-tooling.sh format docs/a.md"])

    def test_format_failure_blocks_with_the_tool_output(self):
        path = self.touch_file("lib/a.cpp")
        rc, out, _ = self.run_hook("PostToolUse", edit(path), FAKE_DOCKER_RC="1", FAKE_DOCKER_OUT="bad syntax")
        decision = json.loads(out)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("bad syntax", decision["reason"])

    def test_exit2_block_mode_for_claude(self):
        path = self.touch_file("lib/a.cpp")
        rc, out, err = self.run_hook("PostToolUse", edit(path), "--block-mode", "exit2", FAKE_DOCKER_RC="1")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("clang-format", err)

    def test_missing_devcontainer_skips_with_a_warning(self):
        path = self.touch_file("lib/a.cpp")
        rc, out, err = self.run_hook("PostToolUse", edit(path), AI_HOOKS_ENV="none")
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("devcontainer not running", json.loads(out)["systemMessage"])
        # reported once per session
        self.assertEqual(self.run_hook("PostToolUse", edit(path), AI_HOOKS_ENV="none")[1], "")

    def test_edit_in_a_linked_worktree_runs_there(self):
        worktree = self.repo / ".worktrees" / "w1"
        self.git("worktree", "add", "-q", str(worktree), "-b", "w1")
        path = str(worktree / "lib" / "b.cpp")
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as handle:
            handle.write("x")
        self.run_hook("PostToolUse", edit(path))
        self.assertEqual(self.docker_calls()[0]["root"], f"{ROOT}/.worktrees/w1")

    def test_apply_patch_touches_every_listed_file(self):
        self.touch_file("lib/a.cpp")
        self.touch_file("lib/b.cpp")
        patch = "*** Begin Patch\n*** Update File: lib/a.cpp\n*** Update File: lib/b.cpp\n"
        payload = {"tool_name": "apply_patch", "tool_input": {"input": patch}}
        self.run_hook("PostToolUse", payload)
        self.assertEqual(self.docker_calls()[0]["command"], ["clang-format-22", "-i", "lib/a.cpp", "lib/b.cpp"])

    def test_checks_whose_repo_capability_is_missing_stay_silent(self):
        (self.repo / "scripts" / "run-clang-tidy.sh").unlink()
        (self.repo / ".clang-format").unlink()
        path = self.touch_file("lib/a.cpp")
        rc, out, err = self.run_hook("PostToolUse", edit(path))
        self.assertEqual((rc, out, err), (0, "", ""))
        self.assertEqual(self.docker_calls(), [])


class StopStageTest(RepoTestCase):
    def _edit(self, rel):
        self.run_hook("PostToolUse", edit(self.touch_file(rel)))
        if self.docker_log.exists():
            self.docker_log.unlink()

    def test_clang_tidy_runs_on_exactly_the_touched_files(self):
        self._edit("lib/a.cpp")
        rc, out, _ = self.run_hook("Stop", {})
        self.assertEqual((rc, out), (0, ""))
        call = self.docker_calls()[0]
        self.assertEqual(call["command"], ["./scripts/run-clang-tidy.sh", "--check", "--fromstdin", "-"])
        self.assertEqual(call["stdin"], "lib/a.cpp\n")

    def test_failure_blocks_and_a_clean_run_is_not_repeated(self):
        self._edit("lib/a.cpp")
        rc, out, _ = self.run_hook("Stop", {}, FAKE_DOCKER_RC="1", FAKE_DOCKER_OUT="tidy says no")
        self.assertIn("tidy says no", json.loads(out)["reason"])
        self.docker_log.unlink()
        self.assertEqual(self.run_hook("Stop", {})[1], "")
        self.assertEqual(len(self.docker_calls()), 1)
        self.docker_log.unlink()
        self.run_hook("Stop", {})
        self.assertEqual(self.docker_calls(), [])

    def test_unsatisfiable_gate_stops_blocking_after_the_limit(self):
        self._edit("lib/a.cpp")
        blocked = [
            "decision" in self.run_hook("Stop", {}, FAKE_DOCKER_RC="1", AI_HOOKS_MAX_STOP_BLOCKS="2")[1]
            for _ in range(4)
        ]
        self.assertEqual(blocked, [True, True, False, False])

    def test_stop_without_edits_does_nothing(self):
        self.assertEqual(self.run_hook("Stop", {}), (0, "", ""))
        self.assertEqual(self.docker_calls(), [])

    def test_missing_devcontainer_never_blocks_stop(self):
        self._edit("lib/a.cpp")
        rc, out, _ = self.run_hook("Stop", {}, AI_HOOKS_ENV="none")
        decision = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertNotIn("decision", decision)
        self.assertIn("clang-tidy skipped: devcontainer not running", decision["systemMessage"])

    def test_cmake_change_runs_the_test_workflow_on_the_host(self):
        write_executable(self.bin / "cmake", "#!/usr/bin/env bash\nprintf 'cmake %s\\n' \"$*\" >> \"$STUB_LOG\"\n")
        self._edit("lib/CMakeLists.txt")
        self.run_hook("Stop", {})
        self.assertEqual(self.stub_calls(), ["cmake --workflow --preset cmake-tests-linux"])
        self.assertEqual(self.docker_calls(), [])

    def test_cmake_failure_blocks_with_the_output(self):
        write_executable(self.bin / "cmake", "#!/usr/bin/env bash\necho 'configure exploded'; exit 1\n")
        self._edit("CMakeLists.txt")
        _, out, _ = self.run_hook("Stop", {})
        self.assertIn("configure exploded", json.loads(out)["reason"])

    def test_cli_python_edit_triggers_the_full_cli_gate(self):
        self._edit("cli/src/mod.py")
        self.run_hook("Stop", {})
        self.assertEqual(self.docker_calls()[0]["command"], ["uv", "run", "task", "check"])
        self.assertEqual(self.docker_calls()[0]["cwd"], "cli")

    def test_docs_lint_runs_on_touched_markdown(self):
        self._edit("doc/a.md")
        self.stub_log.unlink()
        self.run_hook("Stop", {})
        self.assertEqual(
            self.stub_calls(),
            ["docs-tooling.sh format --check --fromstdin -", "docs-tooling.sh lint --fromstdin -"],
        )

    def test_a_reedited_file_is_checked_again(self):
        self._edit("lib/a.cpp")
        self.run_hook("Stop", {})
        self.docker_log.unlink()
        self._edit("lib/a.cpp")
        self.run_hook("Stop", {})
        self.assertEqual(len(self.docker_calls()), 1)


class PreToolAndSessionStartTest(RepoTestCase):
    def test_unsigned_commit_is_denied(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}
        rc, out, _ = self.run_hook("PreToolUse", payload)
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual((rc, decision["permissionDecision"]), (0, "deny"))

    def test_signed_commit_and_other_tools_pass(self):
        ok = {"tool_name": "Bash", "tool_input": {"command": "git commit --signoff -m x"}}
        self.assertEqual(self.run_hook("PreToolUse", ok)[1], "")
        other = {"tool_name": "Read", "tool_input": {"file_path": "x"}}
        self.assertEqual(self.run_hook("PreToolUse", other)[1], "")

    def test_session_start_syncs_the_cli_venv_when_missing(self):
        self.run_hook("SessionStart", {})
        commands = [c["command"] for c in self.docker_calls()]
        self.assertEqual(commands, [["test", "-x", "cli/.venv/bin/python"]])
        # the fake docker reports success for the probe, so no uv sync is needed

    def test_session_start_activates_githooks(self):
        write_executable(self.repo / ".githooks" / "pre-commit", "#!/bin/sh\n")
        self.run_hook("SessionStart", {})
        self.assertEqual(
            self.git("config", "--local", "core.hooksPath").strip(),
            str(HOOKS_DIR.parent / "githooks"),
        )

    def test_a_crashing_hook_never_breaks_the_session(self):
        rc, out, err = self.run_hook("PostToolUse", {"tool_name": "Edit", "tool_input": {"file_path": 5}})
        self.assertEqual((rc, out), (0, ""))


class GitHooksTest(RepoTestCase):
    def _stage(self, rel):
        self.touch_file(rel)
        self.git("add", rel)

    def test_staged_cpp_runs_format_tidy_and_license_checks(self):
        self._stage("lib/a.cpp")
        rc, _, _ = self.run_cli("git", "pre-commit")
        self.assertEqual(rc, 0)
        commands = [c["command"] for c in self.docker_calls()]
        self.assertIn(["clang-format-22", "--dry-run", "--Werror", "lib/a.cpp"], commands)
        self.assertIn(["./scripts/run-clang-tidy.sh", "--check", "--fromstdin", "-"], commands)
        self.assertIn(["python3", "scripts/check_license_headers.py", "--check", "--files", "-"], commands)

    def test_a_failing_check_rejects_the_commit_with_the_bypass_hint(self):
        self._stage("lib/a.cpp")
        rc, _, err = self.run_cli("git", "pre-commit", FAKE_DOCKER_RC="1", FAKE_DOCKER_OUT="bad")
        self.assertEqual(rc, 1)
        self.assertIn("--no-verify", err)

    def test_python_paths_are_passed_relative_to_cli(self):
        self._stage("cli/src/mod.py")
        self.run_cli("git", "pre-commit")
        ruff = [c for c in self.docker_calls() if c["cwd"] == "cli"]
        self.assertEqual(
            ruff[0]["command"],
            ["sh", "-c", "uv run --locked task format-check && uv run --locked task lint"],
        )

    def test_staged_workflow_yaml_runs_zizmor(self):
        self._stage(".github/workflows/ci.yml")
        rc, _, _ = self.run_cli("git", "pre-commit")
        self.assertEqual(rc, 0)
        self.assertEqual(
            self.stub_calls(),
            [
                "uvx pre-commit run zizmor --config .pre-commit-config.yaml "
                "--files .github/workflows/ci.yml"
            ],
        )

    def test_zizmor_failure_rejects_the_commit(self):
        self._stage(".github/workflows/ci.yml")
        rc, _, err = self.run_cli("git", "pre-commit", STUB_RC="1", STUB_OUT="zizmor finding")
        self.assertEqual(rc, 1)
        self.assertIn("zizmor finding", err)

    def test_staged_shell_scripts_run_shellcheck(self):
        self._stage("scripts/run.sh")
        self._stage(".githooks/pre-commit")
        rc, _, _ = self.run_cli("git", "pre-commit")
        self.assertEqual(rc, 0)
        calls = [c for c in self.stub_calls() if c.startswith("shellcheck")]
        self.assertEqual(
            calls, ["shellcheck --severity warning -- .githooks/pre-commit scripts/run.sh"]
        )

    def test_shellcheck_findings_reject_the_commit(self):
        self._stage("scripts/run.sh")
        rc, _, err = self.run_cli("git", "pre-commit", STUB_RC="1", STUB_OUT="SC2086 finding")
        self.assertEqual(rc, 1)
        self.assertIn("SC2086 finding", err)

    def test_non_shell_files_do_not_run_shellcheck(self):
        self._stage("lib/notes.txt")
        self.run_cli("git", "pre-commit")
        self.assertEqual([c for c in self.stub_calls() if c.startswith("shellcheck")], [])

    def test_missing_devcontainer_rejects_the_commit(self):
        self._stage("lib/a.cpp")
        rc, _, err = self.run_cli("git", "pre-commit", AI_HOOKS_ENV="none")
        self.assertEqual(rc, 1)
        self.assertIn("devcontainer not running", err)

    def test_cli_root_python_and_configuration_changes_trigger_the_gate(self):
        for path in ("cli/conftest.py", "cli/pyproject.toml", "cli/uv.lock"):
            with self.subTest(path=path):
                self._stage(path)
                self.run_cli("git", "pre-commit")
                self.assertTrue(any(c["cwd"] == "cli" for c in self.docker_calls()))

    def test_formatter_does_not_depend_on_clang_tidy_script(self):
        (self.repo / "scripts/run-clang-tidy.sh").unlink()
        self._stage("lib/a.cpp")
        rc, _, err = self.run_cli("git", "pre-commit", FAKE_DOCKER_RC="1")
        self.assertEqual(rc, 1)
        self.assertIn("C/C++ formatting issues", err)

    def test_check_crash_rejects_the_commit(self):
        extra = self.tmp / "checks"
        extra.mkdir()
        (extra / "broken.py").write_text(
            "from ai_hooks.model import Check\n"
            "def run(ctx, files):\n"
            "    raise RuntimeError('broken validator')\n"
            "CHECK = Check('broken', 'broken check', run, "
            "stages={'pre-commit': 'check'}, patterns=('*.txt',))\n"
        )
        self._stage("file.txt")
        rc, _, err = self.run_cli("git", "pre-commit", AI_HOOKS_CHECKS_PATH=str(extra))
        self.assertEqual(rc, 1)
        self.assertIn("broken validator", err)

    def test_nothing_staged_is_a_no_op(self):
        self.assertEqual(self.run_cli("git", "pre-commit")[0], 0)
        self.assertEqual(self.docker_calls(), [])

    def test_commit_msg_strips_the_co_author_trailer(self):
        message = self.tmp / "MSG"
        message.write_text("subject\n\nbody\n\nCo-authored-by: A <a@b.c>\n")
        self.assertEqual(self.run_cli("git", "commit-msg", str(message))[0], 0)
        self.assertEqual(message.read_text(), "subject\n\nbody\n")


class TaskContractTest(RepoTestCase):
    def test_run_reports_json_and_exit_status(self):
        self.touch_file("lib/a.cpp")
        rc, out, _ = self.run_cli("run", "clang-tidy", "--files", "lib/a.cpp", "--json")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), [{"check": "clang-tidy", "status": "pass", "message": ""}])
        rc, out, _ = self.run_cli("run", "clang-tidy", "--files", "lib/a.cpp", "--json", FAKE_DOCKER_RC="1")
        self.assertEqual((rc, json.loads(out)[0]["status"]), (1, "fail"))

    def test_fix_mode_is_available_per_check(self):
        self.touch_file("lib/a.cpp")
        self.run_cli("run", "clang-format", "--mode", "fix", "--files", "lib/a.cpp")
        self.assertEqual(self.docker_calls()[0]["command"], ["clang-format-22", "-i", "lib/a.cpp"])

    def test_files_from_stdin_and_stage_selection(self):
        self.run_cli("run", "--stage", "pre-commit", "--files-from", "-", stdin="lib/a.cpp\n")
        self.assertGreaterEqual(len(self.docker_calls()), 3)

    def test_usage_errors_exit_2(self):
        self.assertEqual(self.run_cli("run", "no-such-check", "--all")[0], 2)
        self.assertEqual(self.run_cli("run", "docs")[0], 2)

    def test_list_json_describes_every_check(self):
        rc, out, _ = self.run_cli("list", "--json")
        names = {row["name"] for row in json.loads(out)}
        self.assertEqual(rc, 0)
        self.assertTrue({"clang-format", "clang-tidy", "docs", "cmake-tests", "commit-policy"} <= names)

    def test_a_check_added_through_the_extension_path_is_picked_up(self):
        extra = self.tmp / "extra"
        extra.mkdir()
        (extra / "demo.py").write_text(
            "from ai_hooks.model import Check, Result\n"
            "CHECK = Check('demo', 'demo check', lambda ctx, files: Result.ok('ran'), patterns=('*.txt',))\n"
        )
        rc, out, _ = self.run_cli("run", "demo", "--files", "a.txt", AI_HOOKS_CHECKS_PATH=str(extra))
        self.assertEqual((rc, out.strip()), (0, "[pass] demo: ran"))
