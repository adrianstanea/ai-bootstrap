# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
""".ai-hooks.toml: defaults, validation, layering, and what the engine does with it."""

from __future__ import annotations

import os
import unittest

from ai_hooks import config
from ai_hooks.execenv import ExecEnv

try:
    from .helpers import RepoTestCase, write_executable
except ImportError:  # run as a top-level module by `unittest discover -s tests`
    from helpers import RepoTestCase, write_executable


class ParseTest(unittest.TestCase):
    def test_empty_file_gives_project_neutral_defaults(self):
        cfg = config.parse({}, present=False)
        self.assertEqual((cfg.container_name, cfg.root_var, cfg.env_script), ("", "", ""))
        self.assertEqual(cfg.pr_workflow, "the pull-request-workflow skill")
        self.assertEqual(cfg.gitleaks_branches, ())

    def test_values_are_read(self):
        cfg = config.parse(
            {
                "container": {"name": "proj", "workspace": "/w/proj"},
                "env": {"root_var": "PROJ_ROOT", "script": "env.sh", "unset": ["OLD_DIR"]},
                "gitleaks": {"config": "gl.toml", "branches": ["release-*"]},
            },
            present=True,
        )
        self.assertEqual(cfg.container_workspace, "/w/proj")
        self.assertEqual(cfg.unset, ("OLD_DIR",))
        self.assertEqual(cfg.gitleaks_branches, ("release-*",))

    def test_variable_names_reach_the_shell_only_when_valid(self):
        for bad in ({"env": {"root_var": "X; rm -rf /"}}, {"env": {"unset": ["A B"]}}):
            with self.assertRaises(ValueError):
                config.parse(bad, present=True)

    def test_list_fields_reject_other_types(self):
        with self.assertRaises(ValueError):
            config.parse({"gitleaks": {"branches": [1]}}, present=True)

    def test_project_values_override_user_values(self):
        merged = config._merge(
            {"policy": {"pr_workflow": "user", "commit_doc": "u.md"}},
            {"policy": {"pr_workflow": "project"}},
        )
        self.assertEqual(merged["policy"], {"pr_workflow": "project", "commit_doc": "u.md"})


class EngineTest(RepoTestCase):
    def test_without_a_container_name_docker_is_never_probed(self):
        (self.repo / ".ai-hooks.toml").write_text("")
        config._load.cache_clear()
        env = ExecEnv.detect("docker")
        env.repo = self.repo
        old = os.environ["PATH"]
        os.environ["PATH"] = f"{self.bin}{os.pathsep}{old}"
        try:
            self.assertEqual(env.mode, "none")
        finally:
            os.environ["PATH"] = old
        self.assertFalse(self.docker_log.exists())

    def test_preamble_exports_the_root_variable_and_sources_the_env_script(self):
        (self.repo / ".ai-hooks.toml").write_text(
            '[env]\nroot_var = "PROJ_ROOT"\nscript = "env.sh"\nunset = ["STALE"]\n'
        )
        (self.repo / "env.sh").write_text("export FROM_SCRIPT=yes\n")
        config._load.cache_clear()
        env = ExecEnv("local")
        rc, out = env.run_local(
            self.repo, ["sh", "-c", 'echo "$PROJ_ROOT|$FROM_SCRIPT|${STALE:-gone}"'],
            env={"STALE": "x"},
        )
        self.assertEqual((rc, out.strip()), (0, f"{self.repo}|yes|gone"))

    def test_env_script_that_moves_the_root_is_an_error(self):
        (self.repo / ".ai-hooks.toml").write_text('[env]\nroot_var = "PROJ_ROOT"\nscript = "env.sh"\n')
        (self.repo / "env.sh").write_text("export PROJ_ROOT=/elsewhere\n")
        config._load.cache_clear()
        rc, out = ExecEnv("local").run_local(self.repo, ["true"])
        self.assertNotEqual(rc, 0)
        self.assertIn("PROJ_ROOT is /elsewhere", out)

    def test_config_command_prints_lists_one_item_per_line(self):
        (self.repo / ".ai-hooks.toml").write_text('[gitleaks]\nbranches = ["a-*", "b"]\n')
        rc, out, _ = self.run_cli("config", "gitleaks.branches")
        self.assertEqual((rc, out.splitlines()), (0, ["a-*", "b"]))
        rc, _, _ = self.run_cli("config", "gitleaks.missing")
        self.assertEqual(rc, 1)

    def test_project_checks_load_at_pre_tool(self):
        write_executable(
            self.repo / ".ai-hooks" / "checks" / "deny_rm.py",
            "from ai_hooks.model import Check, Result\n"
            "def run(ctx, files):\n"
            "    return Result.fail('no rm -rf') if 'rm -rf' in ctx.command else Result.ok()\n"
            "CHECK = Check(name='deny-rm', description='d', run=run, stages={'pre-tool': 'check'})\n",
        )
        payload = {"tool_name": "Bash", "tool_input": {"command": "rm -rf build"}}
        rc, out, err = self.run_hook("PreToolUse", payload)
        self.assertIn("no rm -rf", out + err)

    def test_linked_worktree_uses_the_main_checkout_config(self):
        (self.repo / ".ai-hooks.toml").write_text('[policy]\npr_workflow = "the main rules"\n')
        # A synced config file is an untracked link, so a new worktree does not get it.
        self.git("rm", "-q", "--cached", ".ai-hooks.toml")
        with open(self.repo / ".git" / "info" / "exclude", "a", encoding="utf-8") as handle:
            handle.write("/.ai-hooks.toml\n")
        self.git("commit", "-q", "-m", "untrack config")
        worktree = self.tmp / "wt"
        self.git("worktree", "add", "-q", "-b", "wt", str(worktree))
        self.assertFalse((worktree / ".ai-hooks.toml").exists())
        config._load.cache_clear()
        config.owning_root.cache_clear()
        self.assertEqual(config.load(worktree).pr_workflow, "the main rules")

    def test_doctor_reports_the_config_file(self):
        rc, out, _ = self.run_cli("doctor")
        self.assertEqual(rc, 0)
        self.assertIn(str(self.repo / ".ai-hooks.toml"), out)


if __name__ == "__main__":
    unittest.main()
