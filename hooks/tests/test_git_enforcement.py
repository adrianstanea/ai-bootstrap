# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""Exercise real Git commits, pre-commit isolation, and the installed formatter."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

CONFIG_ROOT = Path(__file__).resolve().parents[2]
PROJECT_CHECKS = Path(__file__).resolve().parent / "fixtures" / "project_checks"


class GitEnforcementTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ai-git-enforcement-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.env = dict(os.environ, AI_HOOKS_ENV="local")
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "AI_HOOKS_CHECKS_PATH"):
            self.env.pop(key, None)
        self.git("init", "-q")
        self.git("config", "user.name", "Hook Test")
        self.git("config", "user.email", "hook-test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        (self.repo / ".clang-format").write_text("BasedOnStyle: LLVM\n")
        # The sample project's checks are untracked, as a synced config layer is.
        checks = self.repo / ".ai-hooks" / "checks"
        checks.mkdir(parents=True)
        for path in PROJECT_CHECKS.glob("*.py"):
            shutil.copy(path, checks / path.name)
        (self.repo / ".ai-hooks.toml").write_text("")
        with open(self.repo / ".git" / "info" / "exclude", "a", encoding="utf-8") as handle:
            handle.write("/.ai-hooks/\n/.ai-hooks.toml\n")
        (self.repo / "example.cpp").write_text("int main() { return 0; }\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Initial fixture")
        self.git("config", "core.hooksPath", str(CONFIG_ROOT / "githooks"))

    def git(self, *args, cwd=None, check=True):
        result = subprocess.run(
            ["git", *args], cwd=cwd or self.repo, env=self.env,
            capture_output=True, text=True, check=False,
        )
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    @unittest.skipUnless(
        shutil.which("clang-format-22"),
        "clang-format-22 not installed; formatting enforcement not exercised",
    )
    def test_bad_staged_cpp_is_rejected_even_when_worktree_is_fixed(self):
        before = self.git("rev-parse", "HEAD").stdout
        bad = "int main(){return 1;}\n"
        good = "int main() { return 1; }\n"
        source = self.repo / "example.cpp"
        source.write_text(bad)
        self.git("add", "example.cpp")
        source.write_text(good)
        result = self.git("commit", "-qm", "Must fail", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("C/C++ formatting issues", result.stdout + result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD").stdout, before)
        self.assertEqual(self.git("show", ":example.cpp").stdout, bad)
        self.assertEqual(source.read_text(), good)
        self.git("add", "example.cpp")
        self.git("commit", "-qm", "Valid formatting")

    def test_linked_worktree_without_config_links_is_protected(self):
        worktree = self.repo / "linked"
        self.git("worktree", "add", "-qb", "linked", str(worktree))
        self.assertFalse((worktree / ".ai-hooks").exists())
        (worktree / "example.cpp").write_text("int main(){return 1;}\n")
        self.git("add", "example.cpp", cwd=worktree)
        result = self.git("commit", "-qm", "Must fail", cwd=worktree, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("C/C++ formatting issues", result.stdout + result.stderr)

    def test_missing_tools_reject_the_commit(self):
        self.env["AI_HOOKS_ENV"] = "none"
        (self.repo / "example.cpp").write_text("int main() { return 1; }\n")
        self.git("add", "example.cpp")
        result = self.git("commit", "-qm", "Must fail", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("devcontainer not running", result.stdout + result.stderr)

    def test_bad_python_format_and_lint_are_rejected_from_the_index(self):
        cli = self.repo / "cli"
        (cli / "src").mkdir(parents=True)
        (cli / "tests").mkdir()
        (cli / "conftest.py").write_text("")
        (cli / "pyproject.toml").write_text(
            '[project]\nname = "hook-fixture"\nversion = "0.0.0"\n'
            'requires-python = ">=3.13"\n'
            '[dependency-groups]\ndev = ["ruff==0.15.13", "taskipy==1.14.1"]\n'
            '[tool.taskipy.tasks]\n'
            'format-check = "ruff format --check src tests conftest.py"\n'
            'lint = "ruff check src tests conftest.py"\n'
            '[tool.ruff.lint]\nselect = ["F"]\n'
        )
        result = subprocess.run(
            ["uv", "lock"], cwd=cli, env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        source = cli / "src/example.py"
        source.write_text("VALUE = 1\n")
        self.git("add", "cli/pyproject.toml", "cli/uv.lock", "cli/conftest.py", "cli/src")
        self.git("commit", "-qm", "Valid Python fixture")
        before = self.git("rev-parse", "HEAD").stdout
        for bad, diagnostic in (
            ("VALUE=2\n", "Would reformat"),
            ("VALUE = missing_name\n", "F821"),
        ):
            with self.subTest(diagnostic=diagnostic):
                source.write_text(bad)
                self.git("add", "cli/src/example.py")
                source.write_text("VALUE = 2\n")
                result = self.git("commit", "-qm", "Must fail", check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(diagnostic, result.stdout + result.stderr)
                self.assertEqual(self.git("rev-parse", "HEAD").stdout, before)
                self.assertEqual(self.git("show", ":cli/src/example.py").stdout, bad)
                self.assertEqual(source.read_text(), "VALUE = 2\n")
        self.git("add", "cli/src/example.py")
        self.git("commit", "-qm", "Valid Python change")
